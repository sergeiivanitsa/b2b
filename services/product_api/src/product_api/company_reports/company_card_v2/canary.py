"""Operator-only preparation of one production Company Card v2 canary.

This module is not imported by a router.  It does not call providers.  Its
only mutation prepares an immutable H1 rollback pin and enqueues one ordinary
H2 worker job; assignment remains the responsibility of the separately
audited rollout CLI.
"""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Callable, Literal
from uuid import UUID

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from product_api.company_reports.persistence.jobs import (
    H2_PRESENTATION_CONTRACT,
    H2_WRITER_PROFILE,
)
from product_api.company_reports.persistence.models import (
    JOB_FAILED_STATE,
    JOB_QUEUED_STATE,
    JOB_RUNNING_STATE,
    JOB_SUCCEEDED_STATE,
    PUBLICATION_POLICY_VERSION,
    CompanyReportH2LifecycleHead,
    CompanyReportJob,
    CompanyReportPresentation,
    CompanyReportPresentationAssignment,
    CompanyReportPresentationPin,
    CompanyReportPresentationStagedPointer,
    CompanyReportPublication,
    CompanyReportRecord,
    CompanyReportSubject,
)
from product_api.company_reports.persistence.presentations import (
    H2_ACTIVE_PROJECTION_SCOPE,
    H2_STAGED_PROJECTION_SCOPE,
    PresentationAssignmentConflict,
    _validate_active_h1_publication,
    _validate_h1_rollout_pin,
    append_presentation_pin,
    create_or_reuse_h2_presentation,
)
from product_api.company_reports.persistence.serialization import (
    calculate_company_report_snapshot_hash,
    company_report_from_snapshot,
)
from product_api.company_reports.seo import evaluate_publication
from product_api.settings import Settings, get_settings

from .arbitration_keyring import resolve_arbitration_mask_key
from .canary_models import (
    CANARY_PLAN_SCHEMA_VERSION,
    CANARY_RECEIPT_SCHEMA_VERSION,
    CanaryExpectedAssignmentV1,
    CanaryExpectedH2V1,
    CanaryH1RollbackV1,
    CanaryPlanError,
    CompanyCardV2CanaryPlanV1,
    CompanyCardV2CanaryReceiptV1,
    canary_plan_bytes,
    canary_plan_digest,
    canary_receipt_bytes,
    parse_canary_plan_bytes,
    parse_canary_receipt_bytes,
)
from .canonical_json import canonical_json_bytes
from .rollout_models import parse_rollout_decision
from .service import build_active_public_h2_for_pin


_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_INN = re.compile(r"^(?:[0-9]{10}|[0-9]{12})$")
_RELEASE = re.compile(r"^[0-9a-f]{40}$")
_RECOVERY_TARGET_INN = "7707079463"
_H1_CONTRACT = "company_public_h1_v1"
_ACTIVE_JOB_STATES = (JOB_QUEUED_STATE, JOB_RUNNING_STATE)
_DECISION_FILENAMES = (
    "company-card-v2-canary-activate.json",
    "company-card-v2-canary-rollback.json",
)


class CanaryExecutionError(RuntimeError):
    code = "canary_failed"

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _PrivacySafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise CanaryExecutionError("canary_arguments_invalid")


@dataclass(frozen=True, repr=False)
class CanaryRuntimeConfig:
    database_url: str
    release_commit: str
    schema_revision: str
    rollout_generation: int
    arbitration_mask_key_id: str

    def __repr__(self) -> str:
        return (
            "<CanaryRuntimeConfig "
            f"release_commit={self.release_commit!r} "
            f"schema_revision={self.schema_revision!r} "
            f"rollout_generation={self.rollout_generation!r}>"
        )


@dataclass(frozen=True)
class _H1Policy:
    report: CompanyReportRecord
    published_lastmod: datetime


@dataclass(frozen=True)
class _H1Selection:
    source_kind: Literal[
        "assignment_pin",
        "publication_pin",
        "active_publication",
        "latest_eligible_report",
    ]
    report: CompanyReportRecord
    pin_generation: int
    pin_exists: bool
    canonical_path: str
    published_lastmod: datetime


def _default_engine_factory(url: str) -> AsyncEngine:
    return create_async_engine(url, poolclass=NullPool, pool_pre_ping=False)


def _local_schema_head(
    *, script_locations: tuple[Path, ...] | None = None
) -> str:
    # Release images install product_api as a wheel, while Alembic is copied to
    # /app/alembic.  The source-tree fallback is only for local/operator tests;
    # deriving the migrations path exclusively from the installed package
    # would point inside site-packages and make every production command fail.
    if script_locations is None:
        service_root = Path(__file__).resolve().parents[4]
        script_locations = (Path("/app/alembic"), service_root / "alembic")
    location = next((path for path in script_locations if path.exists()), None)
    if (
        location is None
        or not location.is_absolute()
        or location.is_symlink()
        or not location.is_dir()
        or not (location / "env.py").is_file()
        or not (location / "versions").is_dir()
    ):
        raise CanaryExecutionError("canary_schema_invalid")
    config = Config()
    config.set_main_option("script_location", str(location))
    try:
        head = ScriptDirectory.from_config(config).get_current_head()
    except Exception as exc:
        raise CanaryExecutionError("canary_schema_invalid") from exc
    if not isinstance(head, str) or not head:
        raise CanaryExecutionError("canary_schema_invalid")
    return head


def validate_runtime_config(
    settings: Settings | object,
    *,
    target_inn: str,
    release_commit: str,
    schema_revision: str,
    require_open_gates: bool = True,
) -> CanaryRuntimeConfig:
    """Close every feature/provider gate before any database access."""

    try:
        resolved_key = resolve_arbitration_mask_key(
            key_id=getattr(
                settings, "company_card_v2_arbitration_mask_active_key_id"
            ),
            keyring_json=getattr(
                settings, "company_card_v2_arbitration_mask_keyring_json"
            ),
        )
        allowlist = getattr(settings, "company_card_v2_allowlist_inns")
        database_url = getattr(settings, "database_url")
        generation = getattr(settings, "company_card_v2_rollout_generation")
        valid = (
            type(target_inn) is str
            and _INN.fullmatch(target_inn) is not None
            and target_inn == _RECOVERY_TARGET_INN
            and type(release_commit) is str
            and _RELEASE.fullmatch(release_commit) is not None
            and type(schema_revision) is str
            and bool(schema_revision)
            and type(database_url) is str
            and bool(database_url)
            and type(generation) is int
            and generation > 0
            and type(allowlist) is list
            and allowlist == [target_inn]
            and getattr(
                settings, "company_card_v2_percentage_basis_points"
            )
            == 0
            and getattr(
                settings, "company_card_v2_arbitration_collection_enabled"
            )
            is True
            and getattr(settings, "company_card_v2_narrative_enabled") is False
            and getattr(settings, "company_card_v2_narrative_kill_switch") is True
            and getattr(settings, "company_card_v2_narrative_daily_limit") == 0
            and getattr(settings, "company_card_v2_narrative_monthly_limit") == 0
            and getattr(settings, "company_card_v2_narrative_concurrency") == 0
            and (
                not require_open_gates
                or (
                    getattr(settings, "datanewton_enabled") is True
                    and isinstance(getattr(settings, "datanewton_api_key"), str)
                    and bool(getattr(settings, "datanewton_api_key").strip())
                    and getattr(
                        settings, "company_card_v2_presentations_enabled"
                    )
                    is True
                    and getattr(settings, "company_card_v2_writer_enabled")
                    is True
                )
            )
        )
        if not valid:
            raise ValueError
    except Exception as exc:
        raise CanaryExecutionError("canary_configuration_invalid") from exc
    return CanaryRuntimeConfig(
        database_url=database_url,
        release_commit=release_commit,
        schema_revision=schema_revision,
        rollout_generation=generation,
        arbitration_mask_key_id=resolved_key.key_id,
    )


def _runtime_from_environment(
    target_inn: str,
    *,
    require_open_gates: bool,
) -> CanaryRuntimeConfig:
    release_commit = os.environ.get("PRODUCT_RELEASE_COMMIT", "")
    return validate_runtime_config(
        get_settings(),
        target_inn=target_inn,
        release_commit=release_commit,
        schema_revision=_local_schema_head(),
        require_open_gates=require_open_gates,
    )


def _validate_plan_runtime(
    plan: CompanyCardV2CanaryPlanV1,
    config: CanaryRuntimeConfig,
) -> None:
    if (
        plan.target_inn != _RECOVERY_TARGET_INN
        or plan.release_commit != config.release_commit
        or plan.database_schema_revision != config.schema_revision
        or plan.rollout_generation != config.rollout_generation
        or plan.arbitration_mask_key_id != config.arbitration_mask_key_id
    ):
        raise CanaryExecutionError("canary_plan_runtime_mismatch")


async def _assert_database_head(
    session: AsyncSession,
    expected_revision: str,
) -> None:
    rows = tuple(
        (
            await session.execute(
                text("SELECT version_num FROM alembic_version ORDER BY version_num")
            )
        )
        .scalars()
        .all()
    )
    if rows != (expected_revision,):
        raise CanaryExecutionError("canary_schema_mismatch")


def _assignment_model(
    assignment: CompanyReportPresentationAssignment | None,
) -> CanaryExpectedAssignmentV1:
    if assignment is None:
        return CanaryExpectedAssignmentV1(
            generation=0,
            presentation_contract=None,
            pin_generation=None,
        )
    return CanaryExpectedAssignmentV1(
        generation=assignment.generation,
        presentation_contract=assignment.presentation_contract,
        pin_generation=assignment.pin_generation,
    )


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CanaryExecutionError("canary_h1_invalid")
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError) as exc:
        raise CanaryExecutionError("canary_plan_invalid") from exc


def _eligible_h1_policy(
    subject: CompanyReportSubject,
    report: CompanyReportRecord,
) -> _H1Policy | None:
    try:
        if (
            report.subject_id != subject.id
            or report.writer_profile != "h1_legacy_writer_v2"
            or report.presentation_contract != _H1_CONTRACT
            or report.rollout_generation != 0
            or report.report_version not in {"1", "2"}
            or report.lifecycle_status not in {"complete", "partial"}
            or not isinstance(report.normalized_snapshot, dict)
            or not isinstance(report.snapshot_hash, str)
            or report.generated_at is None
        ):
            return None
        raw_hash = calculate_company_report_snapshot_hash(
            report.normalized_snapshot
        )
        if raw_hash != report.snapshot_hash:
            return None
        model = company_report_from_snapshot(deepcopy(report.normalized_snapshot))
        if (
            model.report_id != report.id
            or model.report_version != report.report_version
            or model.status.value != report.lifecycle_status
            or model.generated_at.astimezone(timezone.utc)
            != report.generated_at.astimezone(timezone.utc)
            or model.target_identifier != subject.normalized_identifier
            or model.counterparty is None
            or model.counterparty.inn != subject.normalized_identifier
        ):
            return None
        decision = evaluate_publication(model)
        if not decision.indexable or decision.projection is None:
            return None
        return _H1Policy(
            report=report,
            published_lastmod=report.generated_at.astimezone(timezone.utc),
        )
    except Exception:
        return None


async def _max_pin_generation(
    session: AsyncSession,
    *,
    subject_id: UUID,
    contract: str,
) -> int:
    value = await session.scalar(
        select(func.max(CompanyReportPresentationPin.generation)).where(
            CompanyReportPresentationPin.subject_id == subject_id,
            CompanyReportPresentationPin.presentation_contract == contract,
        )
    )
    return 0 if value is None else int(value)


async def _find_h1_selection(
    session: AsyncSession,
    *,
    subject: CompanyReportSubject,
    assignment: CompanyReportPresentationAssignment | None,
) -> _H1Selection:
    if assignment is not None and assignment.presentation_contract == _H1_CONTRACT:
        pin = await session.scalar(
            select(CompanyReportPresentationPin).where(
                CompanyReportPresentationPin.subject_id == subject.id,
                CompanyReportPresentationPin.presentation_contract
                == _H1_CONTRACT,
                CompanyReportPresentationPin.generation
                == assignment.pin_generation,
            )
        )
        report = None if pin is None else await session.get(
            CompanyReportRecord, pin.report_id
        )
        try:
            if pin is None:
                raise PresentationAssignmentConflict("missing H1 pin")
            _validate_h1_rollout_pin(subject=subject, pin=pin, report=report)
        except Exception as exc:
            raise CanaryExecutionError("canary_h1_invalid") from exc
        assert report is not None and pin.published_lastmod is not None
        return _H1Selection(
            source_kind="assignment_pin",
            report=report,
            pin_generation=pin.generation,
            pin_exists=True,
            canonical_path=pin.canonical_path,
            published_lastmod=pin.published_lastmod.astimezone(timezone.utc),
        )

    publication = await session.scalar(
        select(CompanyReportPublication).where(
            CompanyReportPublication.subject_id == subject.id,
            CompanyReportPublication.status == "active",
            CompanyReportPublication.indexable.is_(True),
        )
    )
    if publication is not None:
        report = await session.get(CompanyReportRecord, publication.report_id)
        try:
            if not _validate_active_h1_publication(
                subject=subject,
                publication=publication,
                report=report,
            ):
                raise PresentationAssignmentConflict("H1 is not indexable")
        except Exception as exc:
            raise CanaryExecutionError("canary_h1_invalid") from exc
        assert report is not None and publication.published_lastmod is not None
        pins = list(
            (
                await session.scalars(
                    select(CompanyReportPresentationPin)
                    .where(
                        CompanyReportPresentationPin.subject_id == subject.id,
                        CompanyReportPresentationPin.presentation_contract
                        == _H1_CONTRACT,
                        CompanyReportPresentationPin.report_id == report.id,
                    )
                    .order_by(CompanyReportPresentationPin.generation.desc())
                )
            ).all()
        )
        for pin in pins:
            try:
                _validate_h1_rollout_pin(
                    subject=subject,
                    pin=pin,
                    report=report,
                )
            except Exception as exc:
                raise CanaryExecutionError("canary_h1_invalid") from exc
        if pins:
            pin = pins[0]
            return _H1Selection(
                source_kind="publication_pin",
                report=report,
                pin_generation=pin.generation,
                pin_exists=True,
                canonical_path=pin.canonical_path,
                published_lastmod=pin.published_lastmod.astimezone(timezone.utc),
            )
        return _H1Selection(
            source_kind="active_publication",
            report=report,
            pin_generation=(
                await _max_pin_generation(
                    session, subject_id=subject.id, contract=_H1_CONTRACT
                )
            )
            + 1,
            pin_exists=False,
            canonical_path=publication.canonical_path,
            published_lastmod=publication.published_lastmod.astimezone(
                timezone.utc
            ),
        )

    # The public route, not a second history scan, owns legacy-current
    # selection.  If its newest valid report is not suitable as an exact
    # indexable rollback, fail closed instead of silently choosing an older
    # report that activation could never prove as the predecessor.
    from product_api.company_reports.persistence.public_h1 import (
        list_report_resolution_records,
    )
    from product_api.company_reports.public_h1_service import resolve_public_h1

    try:
        resolved = await resolve_public_h1(
            session, inn=subject.normalized_identifier
        )
        candidates = await list_report_resolution_records(
            session, subject.normalized_identifier
        )
    except Exception as exc:
        raise CanaryExecutionError("canary_h1_unavailable") from exc
    report = await session.get(CompanyReportRecord, resolved.report_id)
    policy = None if report is None else _eligible_h1_policy(subject, report)
    if (
        not candidates
        or candidates[0].report.id != resolved.report_id
        or resolved.projection_scope != "latest_unpublished"
        or resolved.indexable is not False
        or report is None
        or policy is None
        or policy.published_lastmod.astimezone(timezone.utc)
        != resolved.checked_at.astimezone(timezone.utc)
    ):
        raise CanaryExecutionError("canary_h1_unavailable")
    # The public H1 resolver owns the exact predecessor identity, including
    # whether its canonical slug uses the legal short or full name.  The SEO
    # policy above proves publication sufficiency, but its legacy projection
    # deliberately prefers the full name and therefore cannot own this path.
    return _H1Selection(
        source_kind="latest_eligible_report",
        report=report,
        pin_generation=(
            await _max_pin_generation(
                session, subject_id=subject.id, contract=_H1_CONTRACT
            )
        )
        + 1,
        pin_exists=False,
        canonical_path=resolved.canonical_path,
        published_lastmod=policy.published_lastmod,
    )


def _h1_plan(selection: _H1Selection) -> CanaryH1RollbackV1:
    if not isinstance(selection.report.snapshot_hash, str):
        raise CanaryExecutionError("canary_h1_invalid")
    return CanaryH1RollbackV1(
        source_kind=selection.source_kind,
        report_id=str(selection.report.id),
        snapshot_hash=selection.report.snapshot_hash,
        pin_generation=selection.pin_generation,
        pin_exists=selection.pin_exists,
        publication_policy_version=PUBLICATION_POLICY_VERSION,
        canonical_path=selection.canonical_path,
        published_lastmod=_utc_text(selection.published_lastmod),
    )


async def _active_h2_job(
    session: AsyncSession,
    *,
    subject: CompanyReportSubject,
    config: CanaryRuntimeConfig,
) -> tuple[CompanyReportJob, CompanyReportRecord] | None:
    rows = (
        await session.execute(
            select(CompanyReportJob, CompanyReportRecord)
            .join(
                CompanyReportRecord,
                CompanyReportRecord.id == CompanyReportJob.report_id,
            )
            .where(
                CompanyReportJob.subject_id == subject.id,
                CompanyReportJob.state.in_(_ACTIVE_JOB_STATES),
            )
            .order_by(CompanyReportJob.created_at, CompanyReportJob.id)
        )
    ).all()
    if not rows:
        return None
    if len(rows) != 1:
        raise CanaryExecutionError("canary_active_job_conflict")
    job, report = rows[0]
    if (
        job.subject_id != subject.id
        or report.subject_id != subject.id
        or job.report_id != report.id
        or report.lifecycle_status != "pending"
        or job.writer_profile != H2_WRITER_PROFILE
        or report.writer_profile != H2_WRITER_PROFILE
        or job.presentation_contract != H2_PRESENTATION_CONTRACT
        or report.presentation_contract != H2_PRESENTATION_CONTRACT
        or report.report_version != "3"
        or job.rollout_generation != config.rollout_generation
        or report.rollout_generation != config.rollout_generation
        or job.arbitration_collection_enabled is not True
        or report.arbitration_collection_enabled is not True
        or job.arbitration_mask_key_id != config.arbitration_mask_key_id
        or report.arbitration_mask_key_id != config.arbitration_mask_key_id
    ):
        raise CanaryExecutionError("canary_active_job_conflict")
    return job, report


async def _expected_h2(
    session: AsyncSession,
    *,
    subject: CompanyReportSubject,
    config: CanaryRuntimeConfig,
) -> CanaryExpectedH2V1:
    await _assert_pristine_h2(session, subject=subject)
    return CanaryExpectedH2V1(
        head_generation=0,
        head_report_id=None,
        active_report_id=None,
        active_job_state=None,
    )


async def _assert_pristine_h2(
    session: AsyncSession,
    *,
    subject: CompanyReportSubject,
) -> None:
    """Require no reconstructable or replaceable H2 lineage for the target."""

    head = await session.get(CompanyReportH2LifecycleHead, subject.id)
    counts = (
        await session.scalar(
            select(func.count())
            .select_from(CompanyReportRecord)
            .where(
                CompanyReportRecord.subject_id == subject.id,
                (
                    CompanyReportRecord.writer_profile == H2_WRITER_PROFILE
                )
                | (
                    CompanyReportRecord.presentation_contract
                    == H2_PRESENTATION_CONTRACT
                ),
            )
        ),
        await session.scalar(
            select(func.count())
            .select_from(CompanyReportJob)
            .where(
                CompanyReportJob.subject_id == subject.id,
                (CompanyReportJob.writer_profile == H2_WRITER_PROFILE)
                | (
                    CompanyReportJob.presentation_contract
                    == H2_PRESENTATION_CONTRACT
                ),
            )
        ),
        await session.scalar(
            select(func.count())
            .select_from(CompanyReportPresentation)
            .where(
                CompanyReportPresentation.subject_id == subject.id,
                CompanyReportPresentation.presentation_contract
                == H2_PRESENTATION_CONTRACT,
            )
        ),
        await session.scalar(
            select(func.count())
            .select_from(CompanyReportPresentationPin)
            .where(
                CompanyReportPresentationPin.subject_id == subject.id,
                CompanyReportPresentationPin.presentation_contract
                == H2_PRESENTATION_CONTRACT,
            )
        ),
        await session.scalar(
            select(func.count())
            .select_from(CompanyReportPresentationStagedPointer)
            .where(
                CompanyReportPresentationStagedPointer.subject_id
                == subject.id,
                CompanyReportPresentationStagedPointer.presentation_contract
                == H2_PRESENTATION_CONTRACT,
            )
        ),
    )
    if head is not None or any(int(value or 0) != 0 for value in counts):
        raise CanaryExecutionError("canary_h2_history_exists")


async def _build_plan(
    session: AsyncSession,
    *,
    target_inn: str,
    config: CanaryRuntimeConfig,
) -> CompanyCardV2CanaryPlanV1:
    await _assert_database_head(session, config.schema_revision)
    subject = await session.scalar(
        select(CompanyReportSubject).where(
            CompanyReportSubject.normalized_identifier == target_inn
        )
    )
    if subject is None:
        raise CanaryExecutionError("canary_target_not_found")
    assignment = await session.scalar(
        select(CompanyReportPresentationAssignment).where(
            CompanyReportPresentationAssignment.subject_id == subject.id
        )
    )
    if (
        assignment is not None
        and assignment.presentation_contract != _H1_CONTRACT
    ):
        raise CanaryExecutionError("canary_assignment_invalid")
    h1 = await _find_h1_selection(
        session, subject=subject, assignment=assignment
    )
    return CompanyCardV2CanaryPlanV1(
        schema_version=CANARY_PLAN_SCHEMA_VERSION,
        release_commit=config.release_commit,
        database_schema_revision=config.schema_revision,
        rollout_generation=config.rollout_generation,
        arbitration_mask_key_id=config.arbitration_mask_key_id,
        target_subject_id=str(subject.id),
        target_inn=target_inn,
        expected_assignment=_assignment_model(assignment),
        h1_rollback=_h1_plan(h1),
        expected_h2=await _expected_h2(
            session, subject=subject, config=config
        ),
    )


def _validate_private_stat(value: os.stat_result, *, regular: bool) -> None:
    if regular and not stat.S_ISREG(value.st_mode):
        raise CanaryExecutionError("canary_private_file_invalid")
    if not regular and not stat.S_ISDIR(value.st_mode):
        raise CanaryExecutionError("canary_private_directory_invalid")
    if os.name != "nt":
        expected = 0o600 if regular else None
        mode = stat.S_IMODE(value.st_mode)
        if (expected is not None and mode != expected) or (
            expected is None and mode & 0o077
        ):
            raise CanaryExecutionError(
                "canary_private_file_invalid"
                if regular
                else "canary_private_directory_invalid"
            )
        if hasattr(os, "geteuid") and value.st_uid != os.geteuid():
            raise CanaryExecutionError(
                "canary_private_file_invalid"
                if regular
                else "canary_private_directory_invalid"
            )


def _require_absolute(path: Path, *, code: str) -> None:
    if not isinstance(path, Path) or not path.is_absolute():
        raise CanaryExecutionError(code)


def _read_private_bytes(path: Path) -> bytes:
    _require_absolute(path, code="canary_private_file_invalid")
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode):
            raise CanaryExecutionError("canary_private_file_invalid")
        _validate_private_stat(before, regular=True)
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            _validate_private_stat(opened, regular=True)
            if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                raise CanaryExecutionError("canary_private_file_invalid")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                return stream.read()
        finally:
            os.close(descriptor)
    except CanaryExecutionError:
        raise
    except Exception as exc:
        raise CanaryExecutionError("canary_private_file_invalid") from exc


def _read_target(path: Path) -> str:
    raw = _read_private_bytes(path)
    try:
        value = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise CanaryExecutionError("canary_target_invalid") from exc
    if _INN.fullmatch(value) is None or value != _RECOVERY_TARGET_INN:
        raise CanaryExecutionError("canary_target_invalid")
    return value


def _load_private_plan(path: Path) -> CompanyCardV2CanaryPlanV1:
    try:
        return parse_canary_plan_bytes(_read_private_bytes(path))
    except CanaryPlanError as exc:
        raise CanaryExecutionError("canary_plan_invalid") from exc


def _load_private_receipt(path: Path) -> CompanyCardV2CanaryReceiptV1:
    try:
        return parse_canary_receipt_bytes(_read_private_bytes(path))
    except CanaryPlanError as exc:
        raise CanaryExecutionError("canary_receipt_invalid") from exc


def _validate_output_parent(path: Path, *, private: bool) -> None:
    _require_absolute(path, code="canary_output_path_invalid")
    try:
        parent = path.parent
        value = parent.lstat()
        if stat.S_ISLNK(value.st_mode):
            raise CanaryExecutionError("canary_output_path_invalid")
        if private:
            _validate_private_stat(value, regular=False)
        elif not stat.S_ISDIR(value.st_mode):
            raise CanaryExecutionError("canary_output_path_invalid")
    except CanaryExecutionError:
        raise
    except Exception as exc:
        raise CanaryExecutionError("canary_output_path_invalid") from exc


def _fsync_parent_directory(path: Path) -> None:
    """Durably publish a new POSIX directory entry without following links."""

    if os.name == "nt":  # Production is POSIX; Windows cannot fsync directories.
        return
    parent = path.parent
    descriptor = -1
    try:
        before = parent.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
            raise CanaryExecutionError("canary_output_path_invalid")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(parent, flags)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            raise CanaryExecutionError("canary_output_path_invalid")
        os.fsync(descriptor)
    except CanaryExecutionError:
        raise
    except Exception as exc:
        raise CanaryExecutionError("canary_output_write_failed") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _write_private_file(path: Path, payload: bytes) -> None:
    _validate_output_parent(path, private=False)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    content_synced = False
    try:
        descriptor = os.open(path, flags, 0o600)
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(descriptor, 0o600)
            else:  # Windows has no descriptor chmod; production is POSIX.
                os.chmod(path, 0o600)
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(descriptor)
                content_synced = True
            _validate_private_stat(os.fstat(descriptor), regular=True)
        finally:
            os.close(descriptor)
        _fsync_parent_directory(path)
    except FileExistsError as exc:
        raise CanaryExecutionError("canary_output_exists") from exc
    except CanaryExecutionError:
        if not content_synced:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
        raise
    except Exception as exc:
        if not content_synced:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
        raise CanaryExecutionError("canary_output_write_failed") from exc


def _write_private_decisions(
    directory: Path,
    activate: bytes,
    rollback: bytes,
) -> None:
    _require_absolute(directory, code="canary_output_path_invalid")
    try:
        value = directory.lstat()
        if stat.S_ISLNK(value.st_mode):
            raise CanaryExecutionError("canary_private_directory_invalid")
        _validate_private_stat(value, regular=False)
    except CanaryExecutionError:
        raise
    except Exception as exc:
        raise CanaryExecutionError("canary_private_directory_invalid") from exc
    paths = tuple(directory / name for name in _DECISION_FILENAMES)
    if any(path.exists() or path.is_symlink() for path in paths):
        raise CanaryExecutionError("canary_output_exists")
    try:
        # The emergency rollback is durably published first.  A process or
        # host crash can therefore leave rollback-only or both files, never a
        # usable activation without its prebuilt rollback.
        for path, payload in (
            (paths[1], rollback),
            (paths[0], activate),
        ):
            _write_private_file(path, payload)
    except Exception:
        # Never remove rollback unless activation deletion is both confirmed
        # and durably published.  In every uncertain cleanup state retaining
        # rollback is safer than risking an activation-only directory.
        activation_absent_durable = False
        try:
            paths[0].unlink(missing_ok=True)
            if paths[0].exists() or paths[0].is_symlink():
                raise CanaryExecutionError("canary_output_write_failed")
            _fsync_parent_directory(paths[0])
            activation_absent_durable = True
        except Exception:
            pass
        if activation_absent_durable:
            try:
                paths[1].unlink(missing_ok=True)
                _fsync_parent_directory(paths[1])
            except Exception:
                pass
        raise


async def inspect_canary(
    *,
    target_inn: str,
    plan_path: Path,
    config: CanaryRuntimeConfig,
    engine_factory: Callable[[str], AsyncEngine] = _default_engine_factory,
) -> dict[str, object]:
    if target_inn != _RECOVERY_TARGET_INN:
        raise CanaryExecutionError("canary_target_invalid")
    engine = engine_factory(config.database_url)
    try:
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            async with session.begin():
                await session.execute(
                    text(
                        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                    )
                )
                plan = await _build_plan(
                    session, target_inn=target_inn, config=config
                )
        _write_private_file(plan_path, canary_plan_bytes(plan))
        return {
            "mode": "inspect",
            "plan_digest": canary_plan_digest(plan),
            "status": "ready",
        }
    finally:
        await engine.dispose()


async def _locked_subject_and_assignment(
    session: AsyncSession,
    plan: CompanyCardV2CanaryPlanV1,
) -> tuple[CompanyReportSubject, CompanyReportPresentationAssignment | None]:
    subject = await session.get(
        CompanyReportSubject, plan.subject_uuid, with_for_update=True
    )
    if subject is None or subject.normalized_identifier != plan.target_inn:
        raise CanaryExecutionError("canary_plan_stale")
    assignment = await session.scalar(
        select(CompanyReportPresentationAssignment)
        .where(CompanyReportPresentationAssignment.subject_id == subject.id)
        .with_for_update()
    )
    if _assignment_model(assignment) != plan.expected_assignment:
        raise CanaryExecutionError("canary_plan_stale")
    if (
        assignment is not None
        and assignment.presentation_contract != _H1_CONTRACT
    ):
        raise CanaryExecutionError("canary_assignment_invalid")
    return subject, assignment


def _pin_matches_plan(
    *,
    subject: CompanyReportSubject,
    report: CompanyReportRecord,
    pin: CompanyReportPresentationPin,
    plan: CompanyCardV2CanaryPlanV1,
) -> bool:
    try:
        _validate_h1_rollout_pin(subject=subject, pin=pin, report=report)
    except Exception:
        return False
    return (
        pin.generation == plan.h1_rollback.pin_generation
        and pin.report_id == plan.h1_report_uuid
        and pin.snapshot_hash == plan.h1_rollback.snapshot_hash
        and pin.publication_policy_version
        == plan.h1_rollback.publication_policy_version
        and pin.canonical_path == plan.h1_rollback.canonical_path
        and pin.published_lastmod is not None
        and pin.published_lastmod.astimezone(timezone.utc)
        == _parse_utc(plan.h1_rollback.published_lastmod)
    )


async def _recheck_h1_source(
    session: AsyncSession,
    *,
    subject: CompanyReportSubject,
    assignment: CompanyReportPresentationAssignment | None,
    plan: CompanyCardV2CanaryPlanV1,
) -> CompanyReportPresentationPin:
    source_kind = plan.h1_rollback.source_kind
    locked_h1_reports: list[CompanyReportRecord] = []
    if source_kind == "latest_eligible_report":
        # Existing H1 finalizers lock report rows without taking the subject
        # lock.  Lock the complete legacy candidate set in deterministic
        # order so none can become a newer canonical predecessor between this
        # check and H2 enqueue.
        locked_h1_reports = list(
            (
                await session.scalars(
                    select(CompanyReportRecord)
                    .where(
                        CompanyReportRecord.subject_id == subject.id,
                        CompanyReportRecord.writer_profile
                        == "h1_legacy_writer_v2",
                        CompanyReportRecord.presentation_contract
                        == _H1_CONTRACT,
                        CompanyReportRecord.rollout_generation == 0,
                    )
                    .order_by(CompanyReportRecord.id)
                    .with_for_update()
                )
            ).all()
        )
        report = next(
            (
                item
                for item in locked_h1_reports
                if item.id == plan.h1_report_uuid
            ),
            None,
        )
    else:
        report = await session.get(
            CompanyReportRecord,
            plan.h1_report_uuid,
            with_for_update=True,
        )
    if (
        report is None
        or report.subject_id != subject.id
        or report.snapshot_hash != plan.h1_rollback.snapshot_hash
    ):
        raise CanaryExecutionError("canary_plan_stale")
    existing = await session.scalar(
        select(CompanyReportPresentationPin)
        .where(
            CompanyReportPresentationPin.subject_id == subject.id,
            CompanyReportPresentationPin.presentation_contract == _H1_CONTRACT,
            CompanyReportPresentationPin.generation
            == plan.h1_rollback.pin_generation,
        )
        .with_for_update()
    )
    if existing is not None:
        if not _pin_matches_plan(
            subject=subject, report=report, pin=existing, plan=plan
        ):
            raise CanaryExecutionError("canary_plan_stale")
    elif plan.h1_rollback.pin_exists:
        raise CanaryExecutionError("canary_plan_stale")

    if source_kind == "assignment_pin":
        if (
            existing is None
            or assignment is None
            or assignment.presentation_contract != _H1_CONTRACT
            or assignment.pin_generation != existing.generation
        ):
            raise CanaryExecutionError("canary_plan_stale")
    elif source_kind in {"active_publication", "publication_pin"}:
        publication = await session.scalar(
            select(CompanyReportPublication)
            .where(
                CompanyReportPublication.subject_id == subject.id,
                CompanyReportPublication.status == "active",
                CompanyReportPublication.indexable.is_(True),
            )
            .with_for_update()
        )
        try:
            valid = (
                publication is not None
                and publication.report_id == report.id
                and publication.snapshot_hash == report.snapshot_hash
                and publication.policy_version == PUBLICATION_POLICY_VERSION
                and publication.canonical_path
                == plan.h1_rollback.canonical_path
                and publication.published_lastmod is not None
                and publication.published_lastmod.astimezone(timezone.utc)
                == _parse_utc(plan.h1_rollback.published_lastmod)
                and _validate_active_h1_publication(
                    subject=subject,
                    publication=publication,
                    report=report,
                )
            )
        except Exception as exc:
            raise CanaryExecutionError("canary_plan_stale") from exc
        if not valid:
            raise CanaryExecutionError("canary_plan_stale")
        if source_kind == "publication_pin" and existing is None:
            raise CanaryExecutionError("canary_plan_stale")
    elif source_kind == "latest_eligible_report":
        selection = await _find_h1_selection(
            session, subject=subject, assignment=assignment
        )
        if (
            selection.source_kind != source_kind
            or selection.report.id != report.id
            or selection.canonical_path != plan.h1_rollback.canonical_path
            or selection.published_lastmod.astimezone(timezone.utc)
            != _parse_utc(plan.h1_rollback.published_lastmod)
            or (
                existing is None
                and selection.pin_generation
                != plan.h1_rollback.pin_generation
            )
        ):
            raise CanaryExecutionError("canary_plan_stale")
    else:
        raise CanaryExecutionError("canary_plan_stale")

    if existing is not None:
        return existing
    pin = await append_presentation_pin(
        session,
        subject_id=subject.id,
        report=report,
        contract=_H1_CONTRACT,
        generation=plan.h1_rollback.pin_generation,
        publication_policy_version=PUBLICATION_POLICY_VERSION,
        canonical_path=plan.h1_rollback.canonical_path,
        published_lastmod=_parse_utc(plan.h1_rollback.published_lastmod),
        indexable=True,
    )
    if not _pin_matches_plan(
        subject=subject, report=report, pin=pin, plan=plan
    ):
        raise CanaryExecutionError("canary_h1_invalid")
    return pin


def _head_matches_plan(
    head: CompanyReportH2LifecycleHead | None,
    expected: CanaryExpectedH2V1,
) -> bool:
    if head is None:
        return expected.head_generation == 0 and expected.head_report_id is None
    return (
        head.head_generation == expected.head_generation
        and str(head.report_id) == expected.head_report_id
        and head.presentation_contract == H2_PRESENTATION_CONTRACT
    )


def _receipt_matches_plan_transition(
    receipt: CompanyCardV2CanaryReceiptV1,
    plan: CompanyCardV2CanaryPlanV1,
) -> bool:
    expected = plan.expected_h2
    if (
        receipt.plan_digest != canary_plan_digest(plan)
        or receipt.target_subject_id != plan.target_subject_id
    ):
        return False
    return (
        expected.head_generation == 0
        and expected.head_report_id is None
        and expected.active_report_id is None
        and expected.active_job_state is None
        and receipt.head_generation == 1
    )


async def _assert_prepared_lineage(
    session: AsyncSession,
    *,
    plan: CompanyCardV2CanaryPlanV1,
    receipt: CompanyCardV2CanaryReceiptV1,
    config: CanaryRuntimeConfig,
) -> tuple[
    CompanyReportSubject,
    CompanyReportH2LifecycleHead,
    CompanyReportPresentation,
    CompanyReportJob,
    CompanyReportRecord,
]:
    if not _receipt_matches_plan_transition(receipt, plan):
        raise CanaryExecutionError("canary_receipt_stale")
    subject = await session.get(CompanyReportSubject, receipt.subject_uuid)
    head = await session.get(CompanyReportH2LifecycleHead, receipt.subject_uuid)
    presentation = await session.get(
        CompanyReportPresentation, receipt.presentation_uuid
    )
    job = await session.get(CompanyReportJob, receipt.job_uuid)
    report = await session.get(CompanyReportRecord, receipt.report_uuid)
    assignment = await session.scalar(
        select(CompanyReportPresentationAssignment).where(
            CompanyReportPresentationAssignment.subject_id
            == receipt.subject_uuid
        )
    )
    if (
        subject is None
        or subject.id != plan.subject_uuid
        or subject.normalized_identifier != plan.target_inn
        or head is None
        or head.subject_id != subject.id
        or head.head_generation != receipt.head_generation
        or head.presentation_id != receipt.presentation_uuid
        or head.report_id != receipt.report_uuid
        or head.presentation_contract != H2_PRESENTATION_CONTRACT
        or head.rollout_generation != config.rollout_generation
        or presentation is None
        or report is None
        or presentation.id != head.presentation_id
        or presentation.subject_id != subject.id
        or presentation.report_id != report.id
        or presentation.presentation_contract != H2_PRESENTATION_CONTRACT
        or presentation.rollout_generation != config.rollout_generation
        or job is None
        or job.id != receipt.job_uuid
        or job.subject_id != subject.id
        or job.report_id != receipt.report_uuid
        or job.writer_profile != H2_WRITER_PROFILE
        or job.presentation_contract != H2_PRESENTATION_CONTRACT
        or job.rollout_generation != config.rollout_generation
        or job.arbitration_collection_enabled is not True
        or job.arbitration_mask_key_id != config.arbitration_mask_key_id
        or report.id != receipt.report_uuid
        or report.subject_id != subject.id
        or report.writer_profile != H2_WRITER_PROFILE
        or report.presentation_contract != H2_PRESENTATION_CONTRACT
        or report.report_version != "3"
        or report.rollout_generation != config.rollout_generation
        or report.arbitration_collection_enabled is not True
        or report.arbitration_mask_key_id != config.arbitration_mask_key_id
        or _assignment_model(assignment) != plan.expected_assignment
    ):
        raise CanaryExecutionError("canary_receipt_stale")
    valid_state = (
        job.state in {JOB_QUEUED_STATE, JOB_RUNNING_STATE}
        and report.lifecycle_status == "pending"
    ) or (
        job.state == JOB_SUCCEEDED_STATE
        and report.lifecycle_status in {"complete", "partial"}
    ) or (
        job.state == JOB_FAILED_STATE and report.lifecycle_status == "failed"
    )
    if not valid_state:
        raise CanaryExecutionError("canary_receipt_stale")
    return subject, head, presentation, job, report


def _prepared_receipt(
    *,
    plan: CompanyCardV2CanaryPlanV1,
    head: CompanyReportH2LifecycleHead,
    presentation: CompanyReportPresentation,
    job: CompanyReportJob,
) -> CompanyCardV2CanaryReceiptV1:
    return CompanyCardV2CanaryReceiptV1(
        schema_version=CANARY_RECEIPT_SCHEMA_VERSION,
        plan_digest=canary_plan_digest(plan),
        target_subject_id=plan.target_subject_id,
        head_generation=head.head_generation,
        presentation_id=str(presentation.id),
        report_id=str(head.report_id),
        job_id=str(job.id),
    )


def _write_or_match_receipt(
    path: Path,
    receipt: CompanyCardV2CanaryReceiptV1,
) -> None:
    try:
        _write_private_file(path, canary_receipt_bytes(receipt))
    except CanaryExecutionError as exc:
        if exc.code != "canary_output_exists":
            raise
        if _load_private_receipt(path) != receipt:
            raise CanaryExecutionError("canary_output_exists") from exc


async def prepare_canary(
    *,
    plan: CompanyCardV2CanaryPlanV1,
    confirm_digest: str,
    receipt_path: Path,
    config: CanaryRuntimeConfig,
    engine_factory: Callable[[str], AsyncEngine] = _default_engine_factory,
) -> dict[str, object]:
    digest = canary_plan_digest(plan)
    if _DIGEST.fullmatch(confirm_digest or "") is None or confirm_digest != digest:
        raise CanaryExecutionError("canary_plan_digest_mismatch")
    _validate_plan_runtime(plan, config)
    existing_receipt = None
    if receipt_path.exists() or receipt_path.is_symlink():
        existing_receipt = _load_private_receipt(receipt_path)
    engine = engine_factory(config.database_url)
    try:
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            async with session.begin():
                await _assert_database_head(session, config.schema_revision)
                subject, assignment = await _locked_subject_and_assignment(
                    session, plan
                )
                await _recheck_h1_source(
                    session,
                    subject=subject,
                    assignment=assignment,
                    plan=plan,
                )
                if existing_receipt is not None:
                    await _assert_prepared_lineage(
                        session,
                        plan=plan,
                        receipt=existing_receipt,
                        config=config,
                    )
                    receipt = existing_receipt
                    reused = True
                else:
                    if (
                        plan.expected_h2.head_generation != 0
                        or plan.expected_h2.head_report_id is not None
                        or plan.expected_h2.active_report_id is not None
                        or plan.expected_h2.active_job_state is not None
                    ):
                        raise CanaryExecutionError("canary_plan_stale")
                    await _assert_pristine_h2(
                        session,
                        subject=subject,
                    )
                    presentation, enqueued, new_head = (
                        await create_or_reuse_h2_presentation(
                            session,
                            identifier=plan.target_inn,
                            rollout_generation=config.rollout_generation,
                            arbitration_collection_enabled=True,
                            arbitration_mask_key_id=config.arbitration_mask_key_id,
                        )
                    )
                    job = await session.get(CompanyReportJob, enqueued.job_id)
                    if job is None:
                        raise CanaryExecutionError("canary_prepare_conflict")
                    receipt = _prepared_receipt(
                        plan=plan,
                        head=new_head,
                        presentation=presentation,
                        job=job,
                    )
                    if (
                        presentation.subject_id != subject.id
                        or presentation.report_id != enqueued.report_id
                        or presentation.presentation_contract
                        != H2_PRESENTATION_CONTRACT
                        or presentation.rollout_generation
                        != config.rollout_generation
                        or new_head.subject_id != subject.id
                        or new_head.report_id != enqueued.report_id
                        or enqueued.reused is not False
                    ):
                        raise CanaryExecutionError("canary_prepare_conflict")
                    await _recheck_h1_source(
                        session,
                        subject=subject,
                        assignment=assignment,
                        plan=plan,
                    )
                    await _assert_prepared_lineage(
                        session,
                        plan=plan,
                        receipt=receipt,
                        config=config,
                    )
                    reused = False
                # Persist and fsync the exact lineage before the database
                # commit.  A commit failure can only leave a stale receipt,
                # which every read-only command rejects; a successful commit
                # can never leave an unreceipted H2 mutation.
                _write_or_match_receipt(receipt_path, receipt)
        return {
            "mode": "prepare",
            "plan_digest": digest,
            "receipt_schema_version": receipt.schema_version,
            "status": "prepared_reused" if reused else "queued",
        }
    except PresentationAssignmentConflict as exc:
        raise CanaryExecutionError("canary_prepare_conflict") from exc
    finally:
        await engine.dispose()


async def _canary_lifecycle_status(
    session: AsyncSession,
    *,
    plan: CompanyCardV2CanaryPlanV1,
    receipt: CompanyCardV2CanaryReceiptV1,
    config: CanaryRuntimeConfig,
) -> dict[str, object]:
    subject, _head, _presentation, job, report = await _assert_prepared_lineage(
        session, plan=plan, receipt=receipt, config=config
    )
    if job.state in {JOB_QUEUED_STATE, JOB_RUNNING_STATE}:
        return {
            "lifecycle": job.state,
            "staged_resolved": False,
        }
    if report.lifecycle_status == "failed":
        return {"lifecycle": "failed", "staged_resolved": False}
    pointer = await session.scalar(
        select(CompanyReportPresentationStagedPointer).where(
            CompanyReportPresentationStagedPointer.subject_id == subject.id
        )
    )
    pin = None
    if pointer is not None:
        pin = await session.scalar(
            select(CompanyReportPresentationPin).where(
                CompanyReportPresentationPin.subject_id == subject.id,
                CompanyReportPresentationPin.presentation_contract
                == H2_PRESENTATION_CONTRACT,
                CompanyReportPresentationPin.generation == pointer.generation,
            )
        )
    resolved = bool(
        pointer is not None
        and pointer.presentation_contract == H2_PRESENTATION_CONTRACT
        and pin is not None
        and pin.report_id == report.id
        and pin.projection_scope == H2_STAGED_PROJECTION_SCOPE
        and pin.narrative_binding_status == "resolved"
        and pin.narrative_binding_kind == "fallback"
        and isinstance(pin.narrative_binding_key, str)
        and _DIGEST.fullmatch(pin.narrative_binding_key) is not None
        and isinstance(pin.projection_digest, str)
        and _DIGEST.fullmatch(pin.projection_digest) is not None
    )
    if resolved:
        try:
            verified = await build_active_public_h2_for_pin(
                session,
                record=report,
                source_pin=pin,
                expected_subject_id=subject.id,
                expected_inn=plan.target_inn,
                canonical_path=f"/company/{plan.target_inn}-company",
                indexable=False,
                published_lastmod=report.generated_at,
            )
            if (
                verified.indexable is not False
                or verified.report_id != str(report.id)
            ):
                raise ValueError
        except Exception as exc:
            raise CanaryExecutionError("canary_h2_invalid") from exc
    return {
        "lifecycle": (
            "ready" if resolved else "finalized_unresolved"
        ),
        "report_status": report.lifecycle_status,
        "staged_resolved": resolved,
    }


async def status_canary(
    *,
    plan: CompanyCardV2CanaryPlanV1,
    receipt: CompanyCardV2CanaryReceiptV1,
    config: CanaryRuntimeConfig,
    engine_factory: Callable[[str], AsyncEngine] = _default_engine_factory,
) -> dict[str, object]:
    _validate_plan_runtime(plan, config)
    engine = engine_factory(config.database_url)
    try:
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            async with session.begin():
                await session.execute(
                    text(
                        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                    )
                )
                await _assert_database_head(session, config.schema_revision)
                status = await _canary_lifecycle_status(
                    session, plan=plan, receipt=receipt, config=config
                )
        return {
            "mode": "status",
            "plan_digest": canary_plan_digest(plan),
            **status,
        }
    finally:
        await engine.dispose()


async def _require_decision_inputs(
    session: AsyncSession,
    *,
    plan: CompanyCardV2CanaryPlanV1,
    receipt: CompanyCardV2CanaryReceiptV1,
    config: CanaryRuntimeConfig,
    h2_indexable: bool,
) -> tuple[
    CompanyReportSubject,
    CompanyReportPresentationAssignment | None,
    CompanyReportPresentationPin,
    CompanyReportPresentationPin,
    int,
    str,
]:
    status = await _canary_lifecycle_status(
        session, plan=plan, receipt=receipt, config=config
    )
    if (
        status.get("lifecycle") != "ready"
        or status.get("staged_resolved") is not True
        or status.get("report_status") != "complete"
    ):
        raise CanaryExecutionError("canary_not_ready")
    subject = await session.get(CompanyReportSubject, plan.subject_uuid)
    assert subject is not None
    assignment = await session.scalar(
        select(CompanyReportPresentationAssignment).where(
            CompanyReportPresentationAssignment.subject_id == subject.id
        )
    )
    if (
        _assignment_model(assignment) != plan.expected_assignment
        or (
            assignment is not None
            and assignment.presentation_contract == H2_PRESENTATION_CONTRACT
        )
    ):
        raise CanaryExecutionError("canary_assignment_changed")
    h1_pin = await session.scalar(
        select(CompanyReportPresentationPin).where(
            CompanyReportPresentationPin.subject_id == subject.id,
            CompanyReportPresentationPin.presentation_contract == _H1_CONTRACT,
            CompanyReportPresentationPin.generation
            == plan.h1_rollback.pin_generation,
        )
    )
    h1_report = await session.get(CompanyReportRecord, plan.h1_report_uuid)
    if (
        h1_pin is None
        or h1_report is None
        or not _pin_matches_plan(
            subject=subject, report=h1_report, pin=h1_pin, plan=plan
        )
    ):
        raise CanaryExecutionError("canary_h1_invalid")
    head = await session.get(CompanyReportH2LifecycleHead, subject.id)
    pointer = await session.scalar(
        select(CompanyReportPresentationStagedPointer).where(
            CompanyReportPresentationStagedPointer.subject_id == subject.id
        )
    )
    if head is None or pointer is None:
        raise CanaryExecutionError("canary_not_ready")
    source_pin = await session.scalar(
        select(CompanyReportPresentationPin).where(
            CompanyReportPresentationPin.subject_id == subject.id,
            CompanyReportPresentationPin.presentation_contract
            == H2_PRESENTATION_CONTRACT,
            CompanyReportPresentationPin.generation == pointer.generation,
        )
    )
    report = await session.get(CompanyReportRecord, head.report_id)
    if (
        source_pin is None
        or report is None
        or source_pin.report_id != report.id
        or source_pin.projection_scope != H2_STAGED_PROJECTION_SCOPE
        or source_pin.narrative_binding_status != "resolved"
    ):
        raise CanaryExecutionError("canary_not_ready")
    projection = await build_active_public_h2_for_pin(
        session,
        record=report,
        source_pin=source_pin,
        expected_subject_id=subject.id,
        expected_inn=plan.target_inn,
        canonical_path=f"/company/{plan.target_inn}-company",
        indexable=h2_indexable,
        published_lastmod=report.generated_at,
    )
    pins = list(
        (
            await session.scalars(
                select(CompanyReportPresentationPin)
                .where(
                    CompanyReportPresentationPin.subject_id == subject.id,
                    CompanyReportPresentationPin.presentation_contract
                    == H2_PRESENTATION_CONTRACT,
                )
                .order_by(CompanyReportPresentationPin.generation)
            )
        ).all()
    )
    reusable = [
        pin
        for pin in pins
        if pin.projection_scope == H2_ACTIVE_PROJECTION_SCOPE
        and pin.report_id == report.id
        and pin.snapshot_hash == source_pin.snapshot_hash
        and pin.chart_facts_version == source_pin.chart_facts_version
        and pin.chart_facts_hash == source_pin.chart_facts_hash
        and pin.evidence_registry_version
        == source_pin.evidence_registry_version
        and pin.publication_policy_version
        == source_pin.publication_policy_version
        and pin.narrative_binding_kind
        == source_pin.narrative_binding_kind
        and pin.narrative_binding_key == source_pin.narrative_binding_key
        and pin.narrative_binding_status == "resolved"
        and pin.projection_digest == projection.projection_digest
        and pin.canonical_path == projection.canonical_path
        and pin.indexable is h2_indexable
        and pin.published_lastmod == report.generated_at
    ]
    if len(reusable) > 1:
        raise CanaryExecutionError("canary_active_pin_conflict")
    target_generation = (
        reusable[0].generation
        if reusable
        else max((pin.generation for pin in pins), default=0) + 1
    )
    return (
        subject,
        assignment,
        h1_pin,
        source_pin,
        target_generation,
        projection.projection_digest,
    )


async def build_canary_decisions(
    *,
    plan: CompanyCardV2CanaryPlanV1,
    receipt: CompanyCardV2CanaryReceiptV1,
    config: CanaryRuntimeConfig,
    authorization_reference: str,
    abort_policy_reference: str,
    observation_window_seconds: int,
    h2_indexable: bool,
    activate_decision_id: str,
    rollback_decision_id: str,
    output_dir: Path,
    engine_factory: Callable[[str], AsyncEngine] = _default_engine_factory,
) -> dict[str, object]:
    _validate_plan_runtime(plan, config)
    if type(h2_indexable) is not bool:
        raise CanaryExecutionError("canary_arguments_invalid")
    if h2_indexable is not True:
        # H1 rollback pins are structurally indexable.  A noindex H2
        # activation would therefore make the audited emergency rollback
        # change public indexability.  This recovery tool fails closed until
        # the owner explicitly authorizes the indexable one-company canary.
        raise CanaryExecutionError("canary_indexability_not_authorized")
    try:
        activate_uuid = UUID(activate_decision_id)
        rollback_uuid = UUID(rollback_decision_id)
        if (
            str(activate_uuid) != activate_decision_id
            or str(rollback_uuid) != rollback_decision_id
            or activate_uuid == rollback_uuid
        ):
            raise ValueError
    except (TypeError, ValueError, AttributeError) as exc:
        raise CanaryExecutionError("canary_arguments_invalid") from exc
    engine = engine_factory(config.database_url)
    try:
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            async with session.begin():
                await session.execute(
                    text(
                        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                    )
                )
                await _assert_database_head(session, config.schema_revision)
                (
                    subject,
                    assignment,
                    h1_pin,
                    source_pin,
                    active_generation,
                    projection_digest,
                ) = await _require_decision_inputs(
                    session,
                    plan=plan,
                    receipt=receipt,
                    config=config,
                    h2_indexable=h2_indexable,
                )
        current_generation = 0 if assignment is None else assignment.generation
        current_contract = (
            None if assignment is None else assignment.presentation_contract
        )
        current_pin_generation = (
            None if assignment is None else assignment.pin_generation
        )
        activate_raw = canonical_json_bytes(
            {
                "schema_version": "company_card_v2_rollout_decision_v1",
                "decision_id": activate_decision_id,
                "authorization_reference": authorization_reference,
                "release_commit": plan.release_commit,
                "rollout_generation": plan.rollout_generation,
                "action": "activate",
                "stage": "allowlist",
                "target_contract": H2_PRESENTATION_CONTRACT,
                "h2_indexable": h2_indexable,
                "allowlist_inns": [plan.target_inn],
                "percentage_basis_points": 0,
                "maximum_batch_size": 1,
                "observation_window_seconds": observation_window_seconds,
                "abort_policy_reference": abort_policy_reference,
                "targets": [
                    {
                        "subject_id": str(subject.id),
                        "inn": plan.target_inn,
                        "expected_assignment_generation": current_generation,
                        "expected_current_contract": current_contract,
                        "expected_current_pin_generation": current_pin_generation,
                        "source_h2_pin_generation": source_pin.generation,
                        "expected_active_h2_pin_generation": active_generation,
                        "expected_active_projection_digest": projection_digest,
                        "h1_rollback_pin_generation": h1_pin.generation,
                    }
                ],
            }
        )
        rollback_raw = canonical_json_bytes(
            {
                "schema_version": "company_card_v2_rollout_decision_v1",
                "decision_id": rollback_decision_id,
                "authorization_reference": authorization_reference,
                "release_commit": plan.release_commit,
                "rollout_generation": None,
                "action": "rollback",
                "stage": "emergency_rollback",
                "target_contract": _H1_CONTRACT,
                "h2_indexable": False,
                "allowlist_inns": None,
                "percentage_basis_points": None,
                "maximum_batch_size": 1,
                "observation_window_seconds": None,
                "abort_policy_reference": None,
                "targets": [
                    {
                        "subject_id": str(subject.id),
                        "inn": plan.target_inn,
                        "expected_assignment_generation": current_generation + 1,
                        "expected_current_contract": H2_PRESENTATION_CONTRACT,
                        "expected_current_pin_generation": active_generation,
                        "h1_target_pin_generation": h1_pin.generation,
                    }
                ],
            }
        )
        activate = parse_rollout_decision(activate_raw)
        rollback = parse_rollout_decision(rollback_raw)
        _write_private_decisions(output_dir, activate_raw, rollback_raw)
        return {
            "mode": "build-decisions",
            "plan_digest": canary_plan_digest(plan),
            "activate_decision_digest": activate.decision_digest,
            "rollback_decision_digest": rollback.decision_digest,
            "status": "ready",
        }
    finally:
        await engine.dispose()


def _parse_bool(value: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise argparse.ArgumentTypeError("boolean must be true or false")


def _parser() -> argparse.ArgumentParser:
    parser = _PrivacySafeArgumentParser(prog="company-card-v2-canary")
    commands = parser.add_subparsers(dest="mode", required=True)
    inspect_parser = commands.add_parser("inspect")
    inspect_parser.add_argument("--target-file", required=True, type=Path)
    inspect_parser.add_argument("--plan-file", required=True, type=Path)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--plan-file", required=True, type=Path)
    prepare_parser.add_argument("--confirm-digest", required=True)
    prepare_parser.add_argument("--receipt-file", required=True, type=Path)
    status_parser = commands.add_parser("status")
    status_parser.add_argument("--plan-file", required=True, type=Path)
    status_parser.add_argument("--receipt-file", required=True, type=Path)
    decisions_parser = commands.add_parser("build-decisions")
    decisions_parser.add_argument("--plan-file", required=True, type=Path)
    decisions_parser.add_argument("--receipt-file", required=True, type=Path)
    decisions_parser.add_argument("--authorization-reference", required=True)
    decisions_parser.add_argument("--abort-policy-reference", required=True)
    decisions_parser.add_argument(
        "--observation-window-seconds", required=True, type=int
    )
    decisions_parser.add_argument("--h2-indexable", required=True, type=_parse_bool)
    decisions_parser.add_argument("--activate-decision-id", required=True)
    decisions_parser.add_argument("--rollback-decision-id", required=True)
    decisions_parser.add_argument("--output-dir", required=True, type=Path)
    return parser


async def _async_main(args: argparse.Namespace) -> dict[str, object]:
    if args.mode == "inspect":
        target = _read_target(args.target_file)
        config = _runtime_from_environment(target, require_open_gates=True)
        return await inspect_canary(
            target_inn=target,
            plan_path=args.plan_file,
            config=config,
        )
    plan = _load_private_plan(args.plan_file)
    config = _runtime_from_environment(
        plan.target_inn,
        require_open_gates=args.mode == "prepare",
    )
    if args.mode == "prepare":
        return await prepare_canary(
            plan=plan,
            confirm_digest=args.confirm_digest,
            receipt_path=args.receipt_file,
            config=config,
        )
    receipt = _load_private_receipt(args.receipt_file)
    if args.mode == "status":
        return await status_canary(plan=plan, receipt=receipt, config=config)
    return await build_canary_decisions(
        plan=plan,
        receipt=receipt,
        config=config,
        authorization_reference=args.authorization_reference,
        abort_policy_reference=args.abort_policy_reference,
        observation_window_seconds=args.observation_window_seconds,
        h2_indexable=args.h2_indexable,
        activate_decision_id=args.activate_decision_id,
        rollback_decision_id=args.rollback_decision_id,
        output_dir=args.output_dir,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        payload = asyncio.run(_async_main(_parser().parse_args(argv)))
        print(
            json.dumps(
                payload,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    except Exception as exc:
        code = (
            exc.code
            if isinstance(exc, (CanaryExecutionError, CanaryPlanError))
            else "canary_failed"
        )
        print(
            json.dumps(
                {"error": {"code": code}},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":  # pragma: no cover - subprocess boundary
    raise SystemExit(main())


__all__ = [
    "CanaryExecutionError",
    "CanaryRuntimeConfig",
    "build_canary_decisions",
    "inspect_canary",
    "main",
    "prepare_canary",
    "status_canary",
    "validate_runtime_config",
]
