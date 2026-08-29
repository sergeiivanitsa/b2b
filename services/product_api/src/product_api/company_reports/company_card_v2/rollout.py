"""Offline-only Company Card v2 rollout operator.

No router imports this module.  Mutation is bound to one canonical decision,
one release commit and one dedicated PostgreSQL physical connection holding a
session advisory lock for the complete ordered batch.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import signal
import sys
from typing import Awaitable, Callable, Literal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from .rollout_models import (
    H1_PRESENTATION_CONTRACT,
    H2_PRESENTATION_CONTRACT,
    CompanyCardV2ActivateTargetV1,
    CompanyCardV2RollbackTargetV1,
    ParsedRolloutDecisionV1,
    RolloutDecisionError,
    load_rollout_decision,
    rollout_advisory_lock_key,
)


_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_CLEANUP_TIMEOUT_SECONDS = 10.0


class RolloutExecutionError(RuntimeError):
    code = "rollout_execution_failed"

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class RolloutSigterm(RolloutExecutionError):
    """Controlled process termination raised only after connection cleanup."""

    exit_code = 143

    def __init__(self) -> None:
        super().__init__("rollout_sigterm")


class _PrivacySafeArgumentParser(argparse.ArgumentParser):
    """Raise a closed code instead of echoing operator-controlled argv."""

    def error(self, _message: str) -> None:
        raise RolloutExecutionError("rollout_arguments_invalid")


@dataclass(frozen=True, repr=False)
class RolloutRuntimeConfig:
    database_url: str
    product_release_commit: str | None
    rollout_generation: int
    allowlist_inns: tuple[str, ...]
    percentage_basis_points: int

    def __repr__(self) -> str:
        return "<RolloutRuntimeConfig redacted>"


@dataclass(frozen=True)
class RolloutTargetResult:
    ordinal: int
    code: str


@dataclass(frozen=True, repr=False)
class RolloutExecutionResult:
    decision_id: str
    decision_digest: str
    mode: str
    results: tuple[RolloutTargetResult, ...]
    stopped: bool

    def __repr__(self) -> str:
        return (
            "<RolloutExecutionResult "
            f"decision_id={self.decision_id!r} "
            f"decision_digest={self.decision_digest!r} mode={self.mode!r}>"
        )

    def public_json(self) -> dict[str, object]:
        counts: dict[str, int] = {}
        for result in self.results:
            counts[result.code] = counts.get(result.code, 0) + 1
        return {
            "decision_id": self.decision_id,
            "decision_digest": self.decision_digest,
            "mode": self.mode,
            "counts": {key: counts[key] for key in sorted(counts)},
            "targets": [
                {"ordinal": result.ordinal, "code": result.code}
                for result in self.results
            ],
            "stopped": self.stopped,
        }


EngineFactory = Callable[[str], AsyncEngine]
SignalHandlerInstaller = Callable[[Callable[[], None]], Callable[[], None]]


def _default_engine_factory(url: str) -> AsyncEngine:
    return create_async_engine(url, poolclass=NullPool, pool_pre_ping=False)


def _install_sigterm_handler(handler: Callable[[], None]) -> Callable[[], None]:
    """Install a loop-owned handler and return an idempotent restore callback."""
    if not hasattr(signal, "SIGTERM"):
        return lambda: None
    loop = asyncio.get_running_loop()
    try:
        previous = signal.getsignal(signal.SIGTERM)
        loop.add_signal_handler(signal.SIGTERM, handler)
    except (NotImplementedError, RuntimeError, ValueError):
        return lambda: None

    restored = False

    def restore() -> None:
        nonlocal restored
        if restored:
            return
        restored = True
        try:
            loop.remove_signal_handler(signal.SIGTERM)
            signal.signal(signal.SIGTERM, previous)
        except (NotImplementedError, RuntimeError, ValueError):
            pass

    return restore


def validate_runtime_binding(
    parsed: ParsedRolloutDecisionV1,
    config: RolloutRuntimeConfig,
    *,
    mutation: bool,
) -> None:
    decision = parsed.decision
    if mutation and (
        config.product_release_commit is None
        or _HEX40.fullmatch(config.product_release_commit) is None
        or config.product_release_commit != decision.release_commit
    ):
        raise RolloutExecutionError("release_commit_mismatch")
    if decision.action == "activate" and (
        config.rollout_generation != decision.rollout_generation
        or config.allowlist_inns != decision.allowlist_inns
        or config.percentage_basis_points != decision.percentage_basis_points
    ):
        raise RolloutExecutionError("rollout_configuration_mismatch")
    # Emergency rollback deliberately ignores the live writer/presentation and
    # cohort switches.  Its only runtime identity is the exact release above.


async def run_rollout_mutation(
    parsed: ParsedRolloutDecisionV1,
    config: RolloutRuntimeConfig,
    *,
    mode: Literal["apply", "rollback"],
    confirm_digest: str,
    engine_factory: EngineFactory = _default_engine_factory,
    signal_handler_installer: SignalHandlerInstaller = _install_sigterm_handler,
) -> RolloutExecutionResult:
    decision = parsed.decision
    if _HEX64.fullmatch(confirm_digest or "") is None or confirm_digest != parsed.decision_digest:
        raise RolloutExecutionError("decision_digest_confirmation_mismatch")
    if (mode == "apply") != (decision.action == "activate"):
        raise RolloutExecutionError("rollout_mode_action_mismatch")
    validate_runtime_binding(parsed, config, mutation=True)

    engine = engine_factory(config.database_url)
    connection: AsyncConnection | None = None
    driver_connection: object | None = None
    lock_acquired = False
    lock_lost = False
    lock_key = rollout_advisory_lock_key(decision.decision_id)
    backend_pid: int | None = None
    results: list[RolloutTargetResult] = []
    admission_closed = False
    sigterm_received = False
    completed_result: RolloutExecutionResult | None = None

    async def guard_lock() -> None:
        nonlocal lock_lost
        try:
            await _guard_rollout_lock(connection, backend_pid, lock_key)
        except RolloutExecutionError as exc:
            if exc.code == "rollout_lock_lost":
                lock_lost = True
            raise

    def close_admission() -> None:
        nonlocal admission_closed, sigterm_received
        admission_closed = True
        sigterm_received = True

    restore_sigterm = signal_handler_installer(close_admission)

    try:
        try:
            try:
                connection = await engine.connect()
                raw = await connection.get_raw_connection()
                driver_connection = getattr(raw, "driver_connection", None)
                try:
                    async with connection.begin():
                        row = (
                            await connection.execute(
                                text(
                                    "SELECT pg_backend_pid(), pg_try_advisory_lock(:lock_key)"
                                ),
                                {"lock_key": lock_key},
                            )
                        ).one()
                        backend_pid = int(row[0])
                        lock_acquired = bool(row[1])
                except Exception as exc:
                    raise RolloutExecutionError("rollout_lock_acquisition_failed") from exc
                _require_between_transaction_boundary(connection)
                if not lock_acquired:
                    raise RolloutExecutionError("decision_in_progress")

                try:
                    async with connection.begin():
                        await guard_lock()
                        session = _bound_session(connection)
                        try:
                            await _bind_decision(session, parsed)
                            await session.flush()
                        finally:
                            await session.close()
                except BaseException as exc:
                    if lock_lost or _backend_connection_lost(
                        connection, driver_connection
                    ):
                        lock_lost = True
                        raise RolloutExecutionError("rollout_lock_lost") from exc
                    raise
                _require_between_transaction_boundary(connection)

                for ordinal, target in enumerate(decision.targets, start=1):
                    if admission_closed:
                        results.append(
                            RolloutTargetResult(ordinal, "admission_closed")
                        )
                        break
                    try:
                        async with connection.begin():
                            await guard_lock()
                            session = _bound_session(connection)
                            try:
                                outcome = await _execute_target(
                                    session,
                                    parsed=parsed,
                                    target=target,
                                )
                                await session.flush()
                            finally:
                                await session.close()
                        _require_between_transaction_boundary(connection)
                    except RolloutExecutionError as exc:
                        if connection.in_transaction():
                            raise RolloutExecutionError(
                                "rollout_transaction_boundary_lost"
                            ) from exc
                        results.append(RolloutTargetResult(ordinal, exc.code))
                        break
                    except Exception as exc:
                        if _backend_connection_lost(connection, driver_connection):
                            lock_lost = True
                            results.append(
                                RolloutTargetResult(ordinal, "rollout_lock_lost")
                            )
                            break
                        if connection.in_transaction():
                            raise RolloutExecutionError(
                                "rollout_transaction_boundary_lost"
                            ) from exc
                        results.append(
                            RolloutTargetResult(
                                ordinal, _closed_target_error_code(exc)
                            )
                        )
                        break
                    results.append(RolloutTargetResult(ordinal, outcome))

                completed_result = RolloutExecutionResult(
                    decision_id=decision.decision_id,
                    decision_digest=parsed.decision_digest,
                    mode=mode,
                    results=tuple(results),
                    stopped=len(results) < len(decision.targets)
                    or any(
                        result.code
                        not in {"applied", "applied_current", "already_target"}
                        for result in results
                    ),
                )
            finally:
                admission_closed = True
                cleanup = asyncio.create_task(
                    _cleanup_rollout_connection(
                        connection=connection,
                        engine=engine,
                        lock_key=lock_key,
                        lock_acquired=lock_acquired,
                        primary_lock_lost=lock_lost,
                        driver_connection=driver_connection,
                    )
                )
                try:
                    await _await_cleanup_shielded(
                        cleanup,
                        timeout=_CLEANUP_TIMEOUT_SECONDS,
                    )
                except BaseException:
                    _terminate_driver(driver_connection)
                    if not cleanup.done():
                        cleanup.cancel()
                    raise
        finally:
            # Keep the controlled handler installed until advisory unlock,
            # physical close and engine disposal have all completed.
            restore_sigterm()

        if sigterm_received:
            raise RolloutSigterm()
        if completed_result is None:
            raise RolloutExecutionError("rollout_result_missing")
        return completed_result
    except asyncio.CancelledError:
        # Cancellation has already crossed the shielded cleanup boundary.
        raise


async def inspect_rollout_decision(
    parsed: ParsedRolloutDecisionV1,
    config: RolloutRuntimeConfig,
    *,
    mode: Literal["plan", "status"],
    engine_factory: EngineFactory = _default_engine_factory,
) -> RolloutExecutionResult:
    validate_runtime_binding(parsed, config, mutation=False)
    engine = engine_factory(config.database_url)
    results: list[RolloutTargetResult] = []
    try:
        async with engine.connect() as connection:
            async with connection.begin():
                await connection.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                )
                session = _bound_session(connection)
                try:
                    if not await _read_rollout_decision_binding_matches(
                        session, parsed
                    ):
                        results.append(
                            RolloutTargetResult(
                                1, "presentation_assignment_conflict"
                            )
                        )
                    else:
                        for ordinal, target in enumerate(
                            parsed.decision.targets, start=1
                        ):
                            try:
                                code = await _inspect_target(
                                    session,
                                    parsed=parsed,
                                    target=target,
                                    include_projection=mode == "plan",
                                )
                            except Exception as exc:
                                code = _closed_target_error_code(exc)
                            results.append(RolloutTargetResult(ordinal, code))
                finally:
                    await session.close()
        return RolloutExecutionResult(
            decision_id=parsed.decision.decision_id,
            decision_digest=parsed.decision_digest,
            mode=mode,
            results=tuple(results),
            stopped=any(
                result.code
                not in {"eligible", "applied_current", "already_target", "pending"}
                for result in results
            ),
        )
    finally:
        await engine.dispose()


async def _read_rollout_decision_binding_matches(
    session: AsyncSession,
    parsed: ParsedRolloutDecisionV1,
) -> bool:
    """Accept an absent binding or the one exact immutable stored binding."""
    from product_api.company_reports.persistence.models import (
        CompanyCardV2RolloutDecision,
    )

    decision = parsed.decision
    rows = list(
        (
            await session.scalars(
                select(CompanyCardV2RolloutDecision).where(
                    (CompanyCardV2RolloutDecision.decision_id
                     == decision.decision_uuid)
                    | (CompanyCardV2RolloutDecision.decision_digest
                       == parsed.decision_digest)
                )
            )
        ).all()
    )
    if not rows:
        return True
    return len(rows) == 1 and (
        rows[0].decision_id,
        rows[0].decision_digest,
        rows[0].schema_version,
        rows[0].release_commit,
        rows[0].action,
        rows[0].stage,
        rows[0].target_contract,
        rows[0].h2_indexable,
        rows[0].target_count,
    ) == (
        decision.decision_uuid,
        parsed.decision_digest,
        decision.schema_version,
        decision.release_commit,
        decision.action,
        decision.stage,
        decision.target_contract,
        decision.h2_indexable,
        len(decision.targets),
    )


def _bound_session(connection: AsyncConnection) -> AsyncSession:
    return AsyncSession(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="rollback_only",
    )


async def _bind_decision(
    session: AsyncSession,
    parsed: ParsedRolloutDecisionV1,
) -> None:
    from product_api.company_reports.persistence.presentations import (
        bind_rollout_decision,
    )

    decision = parsed.decision
    await bind_rollout_decision(
        session,
        decision_id=decision.decision_uuid,
        decision_digest=parsed.decision_digest,
        schema_version=decision.schema_version,
        release_commit=decision.release_commit,
        action=decision.action,
        stage=decision.stage,
        target_contract=decision.target_contract,
        h2_indexable=decision.h2_indexable,
        target_count=len(decision.targets),
    )


async def _execute_target(
    session: AsyncSession,
    *,
    parsed: ParsedRolloutDecisionV1,
    target: CompanyCardV2ActivateTargetV1 | CompanyCardV2RollbackTargetV1,
) -> str:
    from product_api.company_reports.persistence.presentations import (
        RolloutAssignmentCommand,
        assign_rollout_pin_cas,
    )

    decision = parsed.decision
    if isinstance(target, CompanyCardV2RollbackTargetV1):
        command = RolloutAssignmentCommand(
            decision_id=decision.decision_uuid,
            decision_digest=parsed.decision_digest,
            schema_version=decision.schema_version,
            release_commit=decision.release_commit,
            action=decision.action,
            stage=decision.stage,
            h2_indexable=decision.h2_indexable,
            target_count=len(decision.targets),
            reason_code=decision.reason_code,
            subject_id=target.subject_uuid,
            inn=target.inn,
            expected_assignment_generation=target.expected_assignment_generation,
            expected_current_contract=target.expected_current_contract,
            expected_current_pin_generation=target.expected_current_pin_generation,
            expected_rollout_generation=None,
            target_contract=H1_PRESENTATION_CONTRACT,
            target_pin_generation=target.h1_target_pin_generation,
        )
        return (await assign_rollout_pin_cas(session, command=command)).code

    command = RolloutAssignmentCommand(
        decision_id=decision.decision_uuid,
        decision_digest=parsed.decision_digest,
        schema_version=decision.schema_version,
        release_commit=decision.release_commit,
        action=decision.action,
        stage=decision.stage,
        h2_indexable=decision.h2_indexable,
        target_count=len(decision.targets),
        reason_code=decision.reason_code,
        subject_id=target.subject_uuid,
        inn=target.inn,
        expected_assignment_generation=target.expected_assignment_generation,
        expected_current_contract=target.expected_current_contract,
        expected_current_pin_generation=target.expected_current_pin_generation,
        expected_rollout_generation=decision.rollout_generation,
        target_contract=H2_PRESENTATION_CONTRACT,
        target_pin_generation=target.expected_active_h2_pin_generation,
        source_h2_pin_generation=target.source_h2_pin_generation,
        h1_rollback_pin_generation=target.h1_rollback_pin_generation,
        expected_target_projection_digest=target.expected_active_projection_digest,
    )
    return (await assign_rollout_pin_cas(session, command=command)).code


async def _inspect_target(
    session: AsyncSession,
    *,
    parsed: ParsedRolloutDecisionV1,
    target: CompanyCardV2ActivateTargetV1 | CompanyCardV2RollbackTargetV1,
    include_projection: bool,
) -> str:
    from product_api.company_reports.persistence.models import (
        CompanyReportPresentationAssignment,
        CompanyReportPresentationAssignmentJournal,
        CompanyReportPresentationPin,
        CompanyReportPublication,
        CompanyReportRecord,
        CompanyReportSubject,
    )
    from product_api.company_reports.persistence.presentations import (
        H2_ACTIVE_PROJECTION_SCOPE,
        H2_STAGED_PROJECTION_SCOPE,
        _validate_active_h1_publication,
        _validate_h1_rollout_pin,
    )

    subject = await session.get(CompanyReportSubject, target.subject_uuid)
    if subject is None or subject.normalized_identifier != target.inn:
        return "target_subject_mismatch"
    assignment = await session.scalar(
        select(CompanyReportPresentationAssignment).where(
            CompanyReportPresentationAssignment.subject_id == subject.id
        )
    )
    journal = await session.scalar(
        select(CompanyReportPresentationAssignmentJournal).where(
            CompanyReportPresentationAssignmentJournal.subject_id == subject.id,
            CompanyReportPresentationAssignmentJournal.decision_digest
            == parsed.decision_digest,
        )
    )
    if journal is not None:
        expected_journal_contract = (
            H2_PRESENTATION_CONTRACT
            if isinstance(target, CompanyCardV2ActivateTargetV1)
            else H1_PRESENTATION_CONTRACT
        )
        expected_journal_pin = (
            target.expected_active_h2_pin_generation
            if isinstance(target, CompanyCardV2ActivateTargetV1)
            else target.h1_target_pin_generation
        )
        if (
            journal.decision_id != parsed.decision.decision_uuid
            or journal.reason_code != parsed.decision.reason_code
            or journal.presentation_contract != expected_journal_contract
            or journal.pin_generation != expected_journal_pin
        ):
            return "presentation_assignment_conflict"
        if (
            assignment is not None
            and assignment.generation == journal.generation
            and assignment.presentation_contract == journal.presentation_contract
            and assignment.pin_generation == journal.pin_generation
        ):
            return "applied_current"
        return "decision_superseded"
    current = (
        0,
        None,
        None,
    ) if assignment is None else (
        assignment.generation,
        assignment.presentation_contract,
        assignment.pin_generation,
    )
    expected = (
        target.expected_assignment_generation,
        target.expected_current_contract,
        target.expected_current_pin_generation,
    )
    if current != expected:
        return "presentation_assignment_conflict"

    target_generation = (
        target.expected_active_h2_pin_generation
        if isinstance(target, CompanyCardV2ActivateTargetV1)
        else target.h1_target_pin_generation
    )
    target_contract = (
        H2_PRESENTATION_CONTRACT
        if isinstance(target, CompanyCardV2ActivateTargetV1)
        else H1_PRESENTATION_CONTRACT
    )
    pins = list(
        (
            await session.scalars(
                select(CompanyReportPresentationPin)
                .where(CompanyReportPresentationPin.subject_id == subject.id)
                .order_by(
                    CompanyReportPresentationPin.presentation_contract,
                    CompanyReportPresentationPin.generation,
                )
            )
        ).all()
    )
    existing_target = next(
        (
            pin
            for pin in pins
            if pin.presentation_contract == target_contract
            and pin.generation == target_generation
        ),
        None,
    )
    already_target = (
        assignment is not None
        and assignment.presentation_contract == target_contract
        and assignment.pin_generation == target_generation
    )
    if isinstance(target, CompanyCardV2RollbackTargetV1):
        if existing_target is None:
            return "target_h1_pin_missing"
        report = await session.get(CompanyReportRecord, existing_target.report_id)
        _validate_h1_rollout_pin(
            subject=subject,
            pin=existing_target,
            report=report,
        )
        return "already_target" if already_target else "eligible"

    source_pin = next(
        (
            pin
            for pin in pins
            if pin.presentation_contract == H2_PRESENTATION_CONTRACT
            and pin.generation == target.source_h2_pin_generation
        ),
        None,
    )
    if source_pin is None:
        return "source_h2_pin_missing"
    rollback_pin = next(
        (
            pin
            for pin in pins
            if pin.presentation_contract == H1_PRESENTATION_CONTRACT
            and pin.generation == target.h1_rollback_pin_generation
        ),
        None,
    )
    if rollback_pin is None:
        return "target_h1_pin_missing"
    report = await session.get(CompanyReportRecord, source_pin.report_id)
    if report is None:
        return "source_h2_report_missing"
    if report.rollout_generation != parsed.decision.rollout_generation:
        return "rollout_generation_mismatch"
    rollback_report = await session.get(CompanyReportRecord, rollback_pin.report_id)
    _validate_h1_rollout_pin(
        subject=subject,
        pin=rollback_pin,
        report=rollback_report,
    )

    if not parsed.decision.h2_indexable:
        if (
            assignment is not None
            and assignment.presentation_contract == H1_PRESENTATION_CONTRACT
        ):
            current_h1 = next(
                (
                    pin
                    for pin in pins
                    if pin.presentation_contract == H1_PRESENTATION_CONTRACT
                    and pin.generation == assignment.pin_generation
                ),
                None,
            )
            if current_h1 is None:
                return "presentation_assignment_conflict"
            current_report = await session.get(
                CompanyReportRecord, current_h1.report_id
            )
            _validate_h1_rollout_pin(
                subject=subject,
                pin=current_h1,
                report=current_report,
            )
            return "presentation_assignment_conflict"
        if assignment is None:
            publication = await session.scalar(
                select(CompanyReportPublication).where(
                    CompanyReportPublication.subject_id == subject.id
                )
            )
            if publication is not None and publication.status == "active":
                publication_report = await session.get(
                    CompanyReportRecord, publication.report_id
                )
                if _validate_active_h1_publication(
                    subject=subject,
                    publication=publication,
                    report=publication_report,
                ):
                    return "presentation_assignment_conflict"

    from product_api.company_reports.company_card_v2.service import (
        _resolve_exact_v3,
        build_active_public_h2_for_pin,
    )

    projection = await build_active_public_h2_for_pin(
        session,
        record=report,
        source_pin=source_pin,
        expected_subject_id=subject.id,
        expected_inn=target.inn,
        canonical_path=f"/company/{target.inn}-company",
        indexable=parsed.decision.h2_indexable,
        published_lastmod=report.generated_at,
    )
    if projection.projection_digest != target.expected_active_projection_digest:
        return "active_projection_digest_mismatch"
    exact_active = [
        pin
        for pin in pins
        if pin.presentation_contract == H2_PRESENTATION_CONTRACT
        and pin.report_id == report.id
        and pin.snapshot_hash == source_pin.snapshot_hash
        and pin.projection_scope == H2_ACTIVE_PROJECTION_SCOPE
        and pin.chart_facts_version == source_pin.chart_facts_version
        and pin.chart_facts_hash == source_pin.chart_facts_hash
        and pin.evidence_registry_version == source_pin.evidence_registry_version
        and pin.publication_policy_version == source_pin.publication_policy_version
        and pin.narrative_binding_kind == source_pin.narrative_binding_kind
        and pin.narrative_binding_key == source_pin.narrative_binding_key
        and pin.canonical_path == projection.canonical_path
        and pin.indexable is projection.indexable
        and pin.published_lastmod == report.generated_at
        and pin.projection_digest == projection.projection_digest
        and pin.narrative_binding_status == "resolved"
    ]
    if len(exact_active) > 1 or (
        exact_active
        and exact_active[0].generation
        != target.expected_active_h2_pin_generation
    ):
        return "presentation_assignment_conflict"
    if existing_target is None:
        next_generation = max(
            (
                pin.generation
                for pin in pins
                if pin.presentation_contract == H2_PRESENTATION_CONTRACT
            ),
            default=0,
        ) + 1
        if target.expected_active_h2_pin_generation != next_generation:
            return "presentation_assignment_conflict"
        return "eligible" if include_projection else "pending"
    if (
        existing_target.projection_scope != H2_ACTIVE_PROJECTION_SCOPE
        or source_pin.projection_scope not in {None, H2_STAGED_PROJECTION_SCOPE}
        or existing_target.report_id != source_pin.report_id
        or existing_target.snapshot_hash != source_pin.snapshot_hash
        or existing_target.chart_facts_version != source_pin.chart_facts_version
        or existing_target.chart_facts_hash != source_pin.chart_facts_hash
        or existing_target.evidence_registry_version
        != source_pin.evidence_registry_version
        or existing_target.publication_policy_version
        != source_pin.publication_policy_version
        or existing_target.narrative_binding_kind
        != source_pin.narrative_binding_kind
        or existing_target.narrative_binding_key != source_pin.narrative_binding_key
        or existing_target.canonical_path != projection.canonical_path
        or existing_target.indexable is not projection.indexable
        or existing_target.published_lastmod != report.generated_at
        or existing_target.projection_digest != projection.projection_digest
    ):
        return "presentation_assignment_conflict"
    await _resolve_exact_v3(
        session,
        report,
        pin=existing_target,
        expected_subject_id=subject.id,
        expected_inn=target.inn,
    )
    return "already_target" if already_target else "eligible"


async def _guard_rollout_lock(
    connection: AsyncConnection,
    backend_pid: int | None,
    lock_key: int,
) -> None:
    if backend_pid is None or connection.invalidated:
        raise RolloutExecutionError("rollout_lock_lost")
    bits = lock_key & ((1 << 64) - 1)
    classid = bits >> 32
    objid = bits & 0xFFFFFFFF
    try:
        guarded = await connection.scalar(
            text(
                "SELECT pg_backend_pid() = :backend_pid AND EXISTS ("
                "SELECT 1 FROM pg_locks WHERE locktype = 'advisory' "
                "AND pid = :backend_pid AND mode = 'ExclusiveLock' AND granted "
                "AND classid = :classid AND objid = :objid AND objsubid = 1)"
            ),
            {
                "backend_pid": backend_pid,
                "classid": classid,
                "objid": objid,
            },
        )
    except Exception as exc:
        raise RolloutExecutionError("rollout_lock_lost") from exc
    if guarded is not True:
        raise RolloutExecutionError("rollout_lock_lost")


def _require_between_transaction_boundary(connection: AsyncConnection) -> None:
    if connection.in_transaction():
        raise RolloutExecutionError("rollout_transaction_boundary_lost")


async def _cleanup_rollout_connection(
    *,
    connection: AsyncConnection | None,
    engine: AsyncEngine,
    lock_key: int,
    lock_acquired: bool,
    driver_connection: object | None,
    primary_lock_lost: bool = False,
) -> None:
    if primary_lock_lost:
        # The guard has already established that this physical session no
        # longer owns the decision lock.  Do not run an unlock query that can
        # replace the primary closed code; terminate and best-effort-close the
        # one-use connection before disposing its NullPool engine.
        _terminate_driver(driver_connection)
        if connection is not None and not connection.closed:
            try:
                await connection.close()
            except BaseException:
                pass
        try:
            await engine.dispose()
        except BaseException:
            _terminate_driver(driver_connection)
        return

    uncertain = False
    try:
        if connection is not None and not connection.closed:
            if _backend_connection_lost(connection, driver_connection):
                # A lost PostgreSQL backend cannot own a surviving session
                # advisory lock.  Terminate the invalid driver and close the
                # SQLAlchemy wrapper without replacing the primary
                # ``rollout_lock_lost`` result with a cleanup-only error.
                _terminate_driver(driver_connection)
                await connection.close()
            else:
                if connection.in_transaction():
                    await connection.rollback()
                if lock_acquired:
                    async with connection.begin():
                        unlocked = await connection.scalar(
                            text("SELECT pg_advisory_unlock(:lock_key)"),
                            {"lock_key": lock_key},
                        )
                        if unlocked is not True:
                            raise RolloutExecutionError("rollout_unlock_uncertain")
                    _require_between_transaction_boundary(connection)
                await connection.close()
    except BaseException:
        uncertain = True
        _terminate_driver(driver_connection)
        raise
    finally:
        try:
            await engine.dispose()
        except BaseException:
            uncertain = True
            _terminate_driver(driver_connection)
            raise
        finally:
            if uncertain:
                _terminate_driver(driver_connection)


async def _await_cleanup_shielded(
    cleanup: asyncio.Task[None],
    *,
    timeout: float,
) -> None:
    """Let repeated cancellation close admission but never cancel cleanup."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    cancellation_seen = False
    current = asyncio.current_task()
    while not cleanup.done():
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError("rollout cleanup timed out")
        try:
            await asyncio.wait_for(asyncio.shield(cleanup), timeout=remaining)
        except asyncio.CancelledError:
            cancellation_seen = True
            if current is not None and hasattr(current, "uncancel"):
                current.uncancel()
            continue
    await cleanup
    if cancellation_seen:
        raise asyncio.CancelledError


def _terminate_driver(driver_connection: object | None) -> None:
    terminate = getattr(driver_connection, "terminate", None)
    if callable(terminate):
        try:
            terminate()
        except BaseException:
            pass


def _backend_connection_lost(
    connection: AsyncConnection | None,
    driver_connection: object | None,
) -> bool:
    if connection is not None and connection.invalidated:
        return True
    is_closed = getattr(driver_connection, "is_closed", None)
    if not callable(is_closed):
        return False
    try:
        return is_closed() is True
    except BaseException:
        return True


def _closed_target_error_code(exc: BaseException) -> str:
    if isinstance(exc, RolloutExecutionError):
        return exc.code
    code = getattr(exc, "code", None)
    if code == "presentation_assignment_conflict":
        message = str(exc)
        if message == "decision_superseded":
            return "decision_superseded"
        return "presentation_assignment_conflict"
    return "rollout_target_failed"


def _runtime_from_environment() -> RolloutRuntimeConfig:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RolloutExecutionError("database_url_missing")
    release = os.environ.get("PRODUCT_RELEASE_COMMIT")
    try:
        generation = int(os.environ.get("COMPANY_CARD_V2_ROLLOUT_GENERATION", "0"))
        percentage = int(
            os.environ.get("COMPANY_CARD_V2_PERCENTAGE_BASIS_POINTS", "0")
        )
        raw_allowlist = [
            item.strip()
            for item in os.environ.get(
                "COMPANY_CARD_V2_ALLOWLIST_INNS", ""
            ).split(",")
            if item.strip()
        ]
    except (ValueError, TypeError) as exc:
        raise RolloutExecutionError("rollout_configuration_invalid") from exc
    if (
        any(
            not item.isascii()
            or not item.isdigit()
            or len(item) not in {10, 12}
            for item in raw_allowlist
        )
        or raw_allowlist != sorted(set(raw_allowlist))
        or generation < 0
        or not 0 <= percentage <= 10_000
    ):
        raise RolloutExecutionError("rollout_configuration_invalid")
    return RolloutRuntimeConfig(
        database_url=database_url,
        product_release_commit=release,
        rollout_generation=generation,
        allowlist_inns=tuple(raw_allowlist),
        percentage_basis_points=percentage,
    )


def _parser() -> argparse.ArgumentParser:
    parser = _PrivacySafeArgumentParser(prog="company-card-v2-rollout")
    subparsers = parser.add_subparsers(dest="mode", required=True)
    for mode in ("validate", "plan", "status", "apply", "rollback"):
        child = subparsers.add_parser(mode)
        child.add_argument("--decision-file", required=True, type=Path)
        if mode in {"apply", "rollback"}:
            child.add_argument("--confirm-digest", required=True)
    return parser


async def _async_main(args: argparse.Namespace) -> RolloutExecutionResult | dict[str, object]:
    parsed = load_rollout_decision(args.decision_file)
    if args.mode == "validate":
        return {
            "decision_id": parsed.decision.decision_id,
            "decision_digest": parsed.decision_digest,
            "mode": "validate",
            "valid": True,
        }
    config = _runtime_from_environment()
    if args.mode in {"plan", "status"}:
        return await inspect_rollout_decision(parsed, config, mode=args.mode)
    return await run_rollout_mutation(
        parsed,
        config,
        mode=args.mode,
        confirm_digest=args.confirm_digest,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        result = asyncio.run(_async_main(_parser().parse_args(argv)))
        payload = result.public_json() if isinstance(result, RolloutExecutionResult) else result
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
        return 0
    except RolloutSigterm as exc:
        print(
            json.dumps(
                {"error": {"code": exc.code}},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return exc.exit_code
    except (RolloutDecisionError, RolloutExecutionError) as exc:
        code = getattr(exc, "code", "rollout_failed")
        print(
            json.dumps(
                {"error": {"code": code}},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 2
    except Exception:
        # The CLI is a privacy boundary.  Driver, filesystem and unexpected
        # runtime exceptions may contain URLs, credentials or target values;
        # none may escape through a traceback or raw exception string.
        print(
            json.dumps(
                {"error": {"code": "rollout_failed"}},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":  # pragma: no cover - exercised by CLI subprocess tests
    raise SystemExit(main())


__all__ = [
    "RolloutExecutionError",
    "RolloutExecutionResult",
    "RolloutRuntimeConfig",
    "RolloutSigterm",
    "RolloutTargetResult",
    "inspect_rollout_decision",
    "main",
    "run_rollout_mutation",
    "validate_runtime_binding",
]
