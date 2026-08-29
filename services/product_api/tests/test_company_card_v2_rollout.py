from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.company_reports.company_card_v2 import rollout as rollout_module
from product_api.company_reports.company_card_v2.rollout import (
    inspect_rollout_decision,
    run_rollout_mutation,
)
from product_api.company_reports.persistence.models import (
    CompanyCardNarrativeArtifact,
    CompanyCardV2RolloutDecision,
    CompanyReportJob,
    CompanyReportPublication,
    CompanyReportPublicationBatchItem,
    CompanyReportPresentationAssignment,
    CompanyReportPresentationAssignmentJournal,
    CompanyReportPresentationPin,
    CompanyReportRecord,
    CompanyReportSubject,
)
from product_api.company_reports.persistence import (
    create_pending_report,
    enqueue_company_report_job,
    finalize_report,
)
from product_api.company_reports.persistence import publications as publications_module
from product_api.company_reports.persistence.publications import (
    claim_next_batch_item,
    create_batch,
    finalize_batch_claim,
    set_publication_control,
)
from product_api.company_reports.persistence import presentations as presentations_module
from product_api.company_reports.persistence.serialization import (
    calculate_company_report_snapshot_hash,
    company_report_to_snapshot,
)
from product_api.company_reports.seo import canonical_path
from product_api.company_reports.persistence.presentations import (
    H2_ACTIVE_PROJECTION_SCOPE,
    PresentationAssignmentConflict,
    RolloutAssignmentCommand,
    assign_rollout_pin_cas,
    bind_rollout_decision,
)
from tests_support.iteration25_rollout import (
    H1_CONTRACT,
    H2_CONTRACT,
    RELEASE_SHA,
    build_activation_decision,
    build_rollback_decision,
    prepare_unassigned_acceptance_seed,
    with_database_url,
)

TESTS_UNIT = Path(__file__).resolve().parents[1] / "tests_unit"
if str(TESTS_UNIT) not in sys.path:
    sys.path.append(str(TESTS_UNIT))

from company_report_signal_test_helpers import (  # noqa: E402
    complete_company_report,
    counterparty_facts,
)


async def _remove_synthetic_active_pins(engine) -> None:
    async with AsyncSession(bind=engine) as session:
        async with session.begin():
            await session.execute(
                delete(CompanyReportPresentationPin).where(
                    CompanyReportPresentationPin.projection_scope
                    == H2_ACTIVE_PROJECTION_SCOPE
                )
            )


def _activation_command(parsed) -> RolloutAssignmentCommand:
    decision = parsed.decision
    target = decision.targets[0]
    return RolloutAssignmentCommand(
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
        target_contract=H2_CONTRACT,
        target_pin_generation=target.expected_active_h2_pin_generation,
        source_h2_pin_generation=target.source_h2_pin_generation,
        h1_rollback_pin_generation=target.h1_rollback_pin_generation,
        expected_target_projection_digest=target.expected_active_projection_digest,
    )


async def _bind_activation(
    engine,
    parsed,
    **overrides,
) -> None:
    decision = parsed.decision
    values = {
        "decision_id": decision.decision_uuid,
        "decision_digest": parsed.decision_digest,
        "schema_version": decision.schema_version,
        "release_commit": decision.release_commit,
        "action": decision.action,
        "stage": decision.stage,
        "target_contract": decision.target_contract,
        "h2_indexable": decision.h2_indexable,
        "target_count": len(decision.targets),
    }
    values.update(overrides)
    async with AsyncSession(bind=engine) as session:
        async with session.begin():
            await bind_rollout_decision(session, **values)


async def _rollout_mutation_counts(engine) -> tuple[int, int, int]:
    async with AsyncSession(bind=engine) as session:
        return (
            int(
                await session.scalar(
                    select(func.count())
                    .select_from(CompanyReportPresentationPin)
                    .where(
                        CompanyReportPresentationPin.projection_scope
                        == H2_ACTIVE_PROJECTION_SCOPE
                    )
                )
                or 0
            ),
            int(
                await session.scalar(
                    select(func.count()).select_from(
                        CompanyReportPresentationAssignment
                    )
                )
                or 0
            ),
            int(
                await session.scalar(
                    select(func.count()).select_from(
                        CompanyReportPresentationAssignmentJournal
                    )
                )
                or 0
            ),
        )


async def _immutable_subject_row_bytes(
    session: AsyncSession,
    subject_id: UUID,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    params = {"subject_id": str(subject_id)}
    report_rows = tuple(
        (
            await session.scalars(
                text(
                    f"""
                    SELECT to_jsonb(report_row)::text
                    FROM {CompanyReportRecord.__tablename__} AS report_row
                    WHERE report_row.subject_id = CAST(:subject_id AS uuid)
                    ORDER BY report_row.id
                    """
                ),
                params,
            )
        ).all()
    )
    pin_rows = tuple(
        (
            await session.scalars(
                text(
                    f"""
                    SELECT to_jsonb(pin_row)::text
                    FROM {CompanyReportPresentationPin.__tablename__} AS pin_row
                    WHERE pin_row.subject_id = CAST(:subject_id AS uuid)
                    ORDER BY
                        pin_row.subject_id,
                        pin_row.presentation_contract,
                        pin_row.generation
                    """
                ),
                params,
            )
        ).all()
    )
    artifact_rows = tuple(
        (
            await session.scalars(
                text(
                    f"""
                    SELECT to_jsonb(artifact_row)::text
                    FROM {CompanyCardNarrativeArtifact.__tablename__} AS artifact_row
                    JOIN {CompanyReportRecord.__tablename__} AS report_row
                        ON report_row.id = artifact_row.report_id
                    WHERE report_row.subject_id = CAST(:subject_id AS uuid)
                    ORDER BY artifact_row.id
                    """
                ),
                params,
            )
        ).all()
    )
    return report_rows, pin_rows, artifact_rows


async def _publication_row_bytes(
    session: AsyncSession,
    subject_id: UUID,
) -> tuple[str, ...]:
    return tuple(
        (
            await session.scalars(
                text(
                    f"""
                    SELECT to_jsonb(publication_row)::text
                    FROM {CompanyReportPublication.__tablename__} AS publication_row
                    WHERE publication_row.subject_id = CAST(:subject_id AS uuid)
                    ORDER BY publication_row.id
                    """
                ),
                {"subject_id": str(subject_id)},
            )
        ).all()
    )


@pytest.mark.asyncio
async def test_rollout_real_postgres_initial_no_assignment_plan_and_status_are_read_only(
    engine,
    db_url: str,
) -> None:
    profiles = await prepare_unassigned_acceptance_seed(engine, db_url)
    await _remove_synthetic_active_pins(engine)
    parsed, config = await build_activation_decision(
        engine,
        profiles[:1],
        decision_id="25000000-0000-4000-8000-000000000106",
        indexable=False,
    )
    config = with_database_url(config, db_url)
    assert parsed.decision.targets[0].expected_assignment_generation == 0
    before = await _rollout_mutation_counts(engine)

    plan = await inspect_rollout_decision(parsed, config, mode="plan")
    status = await inspect_rollout_decision(parsed, config, mode="status")

    assert [result.code for result in plan.results] == ["eligible"]
    assert [result.code for result in status.results] == ["pending"]
    assert plan.stopped is status.stopped is False
    assert await _rollout_mutation_counts(engine) == before == (0, 0, 0)
    async with AsyncSession(bind=engine) as session:
        assert await session.scalar(
            select(func.count()).select_from(CompanyCardV2RolloutDecision)
        ) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("binding_overrides", "command_overrides"),
    (
        ({}, {"inn": "0000000000"}),
        ({}, {"release_commit": "b" * 40}),
        ({}, {"stage": "percentage", "reason_code": "activate_percentage"}),
        ({}, {"h2_indexable": True}),
        ({}, {"target_count": 2}),
        (
            {
                "action": "rollback",
                "stage": "emergency_rollback",
                "target_contract": H1_CONTRACT,
                "h2_indexable": False,
            },
            {},
        ),
    ),
    ids=(
        "inn",
        "release",
        "stage",
        "indexability",
        "target-count",
        "action",
    ),
)
async def test_rollout_real_postgres_binding_mismatch_leaves_no_active_orphan(
    engine,
    db_url: str,
    binding_overrides: dict[str, object],
    command_overrides: dict[str, object],
) -> None:
    profiles = await prepare_unassigned_acceptance_seed(engine, db_url)
    await _remove_synthetic_active_pins(engine)
    parsed, _config = await build_activation_decision(
        engine,
        profiles[:1],
        decision_id="25000000-0000-4000-8000-000000000107",
        indexable=False,
    )
    await _bind_activation(engine, parsed, **binding_overrides)
    command = replace(_activation_command(parsed), **command_overrides)

    async with AsyncSession(bind=engine) as session:
        with pytest.raises(PresentationAssignmentConflict):
            async with session.begin():
                await assign_rollout_pin_cas(session, command=command)

    assert await _rollout_mutation_counts(engine) == (0, 0, 0)


@pytest.mark.asyncio
async def test_rollout_real_postgres_ga_noindex_database_constraint_is_closed(
    engine,
) -> None:
    async with AsyncSession(bind=engine) as session:
        session.add(
            CompanyCardV2RolloutDecision(
                decision_id=UUID("25000000-0000-4000-8000-000000000108"),
                decision_digest="8" * 64,
                schema_version="company_card_v2_rollout_decision_v1",
                release_commit=RELEASE_SHA,
                action="activate",
                stage="ga",
                target_contract=H2_CONTRACT,
                h2_indexable=False,
                target_count=1,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
    assert await _rollout_mutation_counts(engine) == (0, 0, 0)
    async with AsyncSession(bind=engine) as session:
        assert await session.scalar(
            select(func.count()).select_from(CompanyCardV2RolloutDecision)
        ) == 0


@pytest.mark.asyncio
async def test_rollout_real_postgres_stale_assignment_leaves_no_active_orphan(
    engine,
    db_url: str,
) -> None:
    profiles = await prepare_unassigned_acceptance_seed(engine, db_url)
    await _remove_synthetic_active_pins(engine)
    parsed, _config = await build_activation_decision(
        engine,
        profiles[:1],
        decision_id="25000000-0000-4000-8000-000000000109",
        indexable=False,
    )
    await _bind_activation(engine, parsed)
    target = parsed.decision.targets[0]
    async with AsyncSession(bind=engine) as session:
        async with session.begin():
            session.add(
                CompanyReportPresentationAssignment(
                    subject_id=target.subject_uuid,
                    presentation_contract=H1_CONTRACT,
                    pin_generation=target.h1_rollback_pin_generation,
                    generation=1,
                )
            )
    async with AsyncSession(bind=engine) as session:
        with pytest.raises(
            PresentationAssignmentConflict, match="assignment generation conflicts"
        ):
            async with session.begin():
                await assign_rollout_pin_cas(
                    session,
                    command=_activation_command(parsed),
                )
    assert await _rollout_mutation_counts(engine) == (0, 1, 0)


@pytest.mark.asyncio
async def test_rollout_real_postgres_journal_flush_failure_rolls_back_active_candidate(
    engine,
    db_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profiles = await prepare_unassigned_acceptance_seed(engine, db_url)
    await _remove_synthetic_active_pins(engine)
    parsed, _config = await build_activation_decision(
        engine,
        profiles[:1],
        decision_id="25000000-0000-4000-8000-000000000110",
        indexable=False,
    )
    await _bind_activation(engine, parsed)
    async with AsyncSession(bind=engine) as session:
        original_flush = session.flush
        flushes = 0

        async def fail_after_journal_flush(objects=None) -> None:
            nonlocal flushes
            flushes += 1
            await original_flush(objects)
            if flushes == 3:
                raise RuntimeError("synthetic journal flush failure")

        monkeypatch.setattr(session, "flush", fail_after_journal_flush)
        with pytest.raises(RuntimeError, match="synthetic journal flush failure"):
            async with session.begin():
                await assign_rollout_pin_cas(
                    session,
                    command=_activation_command(parsed),
                )
        assert flushes == 3
    assert await _rollout_mutation_counts(engine) == (0, 0, 0)


async def _claimed_h1_publication(engine):
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        async with session.begin():
            await set_publication_control(session, state="active", enabled=True)
        async with session.begin():
            batch = await create_batch(session, limit=1, max_limit=10)
            batch_id = batch.id
        async with session.begin():
            claim = await claim_next_batch_item(session, batch_id=batch_id)
            assert claim is not None
            item = await session.get(CompanyReportPublicationBatchItem, claim.item_id)
            assert item is not None
            subject_id = item.subject_id
    return claim, subject_id


async def _make_latest_sufficient_h1_candidate(engine, profile) -> None:
    # Make this subject the deterministic latest H1 manifest candidate; the
    # other synthetic H1 rows intentionally remain older comparison rows.
    generated_at = datetime(2026, 8, 29, tzinfo=timezone.utc)
    report_model = complete_company_report(
        counterparty=counterparty_facts().model_copy(
            update={
                "inn": profile["inn"],
                "full_name": profile["display_name"],
            }
        ),
        report_version="2",
    ).model_copy(
        update={
            "report_id": UUID(profile["h1_report_id"]),
            "generated_at": generated_at,
            "target_identifier": profile["inn"],
        }
    )
    snapshot = company_report_to_snapshot(report_model)
    snapshot_hash = calculate_company_report_snapshot_hash(snapshot)
    async with AsyncSession(bind=engine) as session:
        async with session.begin():
            records = list(
                (
                    await session.scalars(
                        select(CompanyReportRecord).where(
                            CompanyReportRecord.presentation_contract == H1_CONTRACT
                        )
                    )
                ).all()
            )
            record = next(
                item for item in records if item.id == report_model.report_id
            )
            record.lifecycle_status = "complete"
            record.generated_at = generated_at
            record.finished_at = generated_at
            record.normalized_snapshot = snapshot
            record.snapshot_hash = snapshot_hash
            record.usable_for_public_page = True
            pin = await session.scalar(
                select(CompanyReportPresentationPin).where(
                    CompanyReportPresentationPin.subject_id == record.subject_id,
                    CompanyReportPresentationPin.presentation_contract == H1_CONTRACT,
                    CompanyReportPresentationPin.generation == 1,
                )
            )
            assert pin is not None
            pin.snapshot_hash = snapshot_hash
            pin.canonical_path = canonical_path(
                profile["inn"], profile["display_name"]
            )
            pin.published_lastmod = generated_at
            pin.indexable = True


async def _append_newer_h1_candidate(
    engine,
    profile,
    *,
    usable: bool,
) -> UUID:
    generated_at = datetime(2026, 8, 30, tzinfo=timezone.utc)
    report_model = complete_company_report(
        counterparty=counterparty_facts().model_copy(
            update={
                "inn": profile["inn"],
                "full_name": "ООО Более новый H1 отчёт",
            }
        ),
        report_version="2",
    ).model_copy(
        update={
            "report_id": uuid4(),
            "generated_at": generated_at,
            "target_identifier": profile["inn"],
            "usable_for_public_page": usable,
            "usable_for_future_scoring": usable,
        }
    )
    snapshot = company_report_to_snapshot(report_model)
    async with AsyncSession(bind=engine) as session:
        async with session.begin():
            session.add(
                CompanyReportRecord(
                    id=report_model.report_id,
                    subject_id=UUID(profile["subject_id"]),
                    report_version="2",
                    writer_profile="h1_legacy_writer_v2",
                    presentation_contract=H1_CONTRACT,
                    rollout_generation=0,
                    lifecycle_status="complete",
                    started_at=generated_at,
                    generated_at=generated_at,
                    finished_at=generated_at,
                    normalized_snapshot=snapshot,
                    snapshot_hash=calculate_company_report_snapshot_hash(snapshot),
                    completeness_snapshot={},
                    freshness_snapshot={},
                    warnings_snapshot=[],
                    usable_for_public_page=usable,
                    usable_for_future_scoring=usable,
                )
            )
    return report_model.report_id


def _newer_h1_report(profile, report_id: UUID):
    generated_at = datetime(2026, 8, 31, tzinfo=timezone.utc)
    return complete_company_report(
        counterparty=counterparty_facts().model_copy(
            update={
                "inn": profile["inn"],
                "full_name": "ООО Новый H1 отчёт во время rollout",
            }
        ),
        report_version="2",
    ).model_copy(
        update={
            "report_id": report_id,
            "generated_at": generated_at,
            "target_identifier": profile["inn"],
            "usable_for_public_page": True,
            "usable_for_future_scoring": True,
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("usable", (True, False), ids=("eligible", "ineligible"))
async def test_rollout_real_postgres_newer_h1_after_decision_rejects_without_mutation(
    engine,
    db_url: str,
    usable: bool,
) -> None:
    profiles = await prepare_unassigned_acceptance_seed(engine, db_url)
    await _remove_synthetic_active_pins(engine)
    profile = profiles[0]
    parsed, _config = await build_activation_decision(
        engine,
        (profile,),
        decision_id="25000000-0000-4000-8000-000000000113",
        indexable=True,
    )
    await _bind_activation(engine, parsed)
    await _append_newer_h1_candidate(engine, profile, usable=usable)

    async with AsyncSession(bind=engine) as session:
        with pytest.raises(
            PresentationAssignmentConflict,
            match="unassigned H1 predecessor conflicts",
        ):
            async with session.begin():
                await assign_rollout_pin_cas(
                    session,
                    command=_activation_command(parsed),
                )

    assert await _rollout_mutation_counts(engine) == (0, 0, 0)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("snapshot_hash", "f" * 64),
        ("policy_version", "drifted_publication_policy"),
        ("canonical_path", "/company/7701234567-drifted"),
        (
            "published_lastmod",
            datetime(2026, 8, 29, tzinfo=timezone.utc) + timedelta(seconds=1),
        ),
        ("indexable", False),
    ),
)
@pytest.mark.asyncio
async def test_rollout_real_postgres_active_h1_publication_drift_rejects_exact_cas(
    engine,
    db_url: str,
    field: str,
    value: object,
) -> None:
    profiles = await prepare_unassigned_acceptance_seed(engine, db_url)
    await _remove_synthetic_active_pins(engine)
    profile = profiles[0]
    await _make_latest_sufficient_h1_candidate(engine, profile)
    claim, subject_id = await _claimed_h1_publication(engine)
    assert subject_id == UUID(profile["subject_id"])
    async with AsyncSession(bind=engine) as session:
        async with session.begin():
            await finalize_batch_claim(session, claim=claim)
    parsed, _config = await build_activation_decision(
        engine,
        (profile,),
        decision_id="25000000-0000-4000-8000-000000000114",
        indexable=True,
    )
    await _bind_activation(engine, parsed)
    async with AsyncSession(bind=engine) as session:
        async with session.begin():
            publication = await session.scalar(
                select(CompanyReportPublication).where(
                    CompanyReportPublication.subject_id == subject_id
                )
            )
            assert publication is not None
            setattr(publication, field, value)
    async with AsyncSession(bind=engine) as session:
        immutable_before = await _immutable_subject_row_bytes(session, subject_id)
        publication_before = await _publication_row_bytes(session, subject_id)

    async with AsyncSession(bind=engine) as session:
        with pytest.raises(
            PresentationAssignmentConflict,
            match=(
                "active H1 publication is invalid|"
                "unassigned H1 publication conflicts"
            ),
        ):
            async with session.begin():
                await assign_rollout_pin_cas(
                    session,
                    command=_activation_command(parsed),
                )

    assert await _rollout_mutation_counts(engine) == (0, 0, 0)
    async with AsyncSession(bind=engine) as session:
        assert await _immutable_subject_row_bytes(session, subject_id) == immutable_before
        assert await _publication_row_bytes(session, subject_id) == publication_before


@pytest.mark.asyncio
@pytest.mark.parametrize("winner", ("enqueue", "rollout"))
async def test_rollout_real_postgres_h1_enqueue_and_unassigned_apply_serialize(
    engine,
    db_url: str,
    monkeypatch: pytest.MonkeyPatch,
    winner: str,
) -> None:
    profiles = await prepare_unassigned_acceptance_seed(engine, db_url)
    await _remove_synthetic_active_pins(engine)
    profile = profiles[0]
    subject_id = UUID(profile["subject_id"])
    parsed, _config = await build_activation_decision(
        engine,
        (profile,),
        decision_id=(
            "25000000-0000-4000-8000-000000000115"
            if winner == "enqueue"
            else "25000000-0000-4000-8000-000000000116"
        ),
        indexable=True,
    )
    await _bind_activation(engine, parsed)
    async with AsyncSession(bind=engine) as session:
        publication_before = await _publication_row_bytes(session, subject_id)

    winner_holds_subject = asyncio.Event()
    release_winner = asyncio.Event()

    async def enqueue_h1(*, hold_subject: bool):
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            async with session.begin():
                if hold_subject:
                    subject = await session.get(
                        CompanyReportSubject,
                        subject_id,
                        with_for_update=True,
                    )
                    assert subject is not None
                    winner_holds_subject.set()
                    await release_winner.wait()
                return await enqueue_company_report_job(session, profile["inn"])

    async def apply_rollout() -> tuple[str, str | None]:
        async with AsyncSession(bind=engine) as session:
            try:
                async with session.begin():
                    outcome = await assign_rollout_pin_cas(
                        session,
                        command=_activation_command(parsed),
                    )
            except PresentationAssignmentConflict as exc:
                return exc.code, str(exc)
        return outcome.code, None

    if winner == "enqueue":
        winner_task = asyncio.create_task(enqueue_h1(hold_subject=True))
        await asyncio.wait_for(winner_holds_subject.wait(), timeout=10)
        contender_task = asyncio.create_task(apply_rollout())
    else:
        original_plan = presentations_module._plan_active_h2_pin_locked

        async def held_rollout_plan(*args, **kwargs):
            planned = await original_plan(*args, **kwargs)
            winner_holds_subject.set()
            await release_winner.wait()
            return planned

        monkeypatch.setattr(
            presentations_module,
            "_plan_active_h2_pin_locked",
            held_rollout_plan,
        )
        winner_task = asyncio.create_task(apply_rollout())
        await asyncio.wait_for(winner_holds_subject.wait(), timeout=10)
        contender_task = asyncio.create_task(enqueue_h1(hold_subject=False))

    await asyncio.sleep(0.1)
    assert contender_task.done() is False
    release_winner.set()
    winner_result, contender_result = await asyncio.gather(
        winner_task,
        contender_task,
    )
    if winner == "enqueue":
        enqueued = winner_result
        rollout_result = contender_result
    else:
        rollout_result = winner_result
        enqueued = contender_result

    assert rollout_result == ("applied", None)
    assert enqueued.reused is False
    assert enqueued.subject_id == subject_id
    async with AsyncSession(bind=engine) as session:
        report = await session.get(CompanyReportRecord, enqueued.report_id)
        job = await session.get(CompanyReportJob, enqueued.job_id)
        assignment = await session.scalar(
            select(CompanyReportPresentationAssignment).where(
                CompanyReportPresentationAssignment.subject_id == subject_id
            )
        )
        publication_after = await _publication_row_bytes(session, subject_id)
    assert report is not None and report.lifecycle_status == "pending"
    assert report.presentation_contract == H1_CONTRACT
    assert job is not None and job.state == "queued"
    assert assignment is not None
    assert assignment.presentation_contract == H2_CONTRACT
    assert publication_after == publication_before
    assert await _rollout_mutation_counts(engine) == (1, 1, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("winner", ("finalizer", "rollout"))
async def test_rollout_real_postgres_h1_finalization_and_unassigned_apply_serialize(
    engine,
    db_url: str,
    monkeypatch: pytest.MonkeyPatch,
    winner: str,
) -> None:
    profiles = await prepare_unassigned_acceptance_seed(engine, db_url)
    await _remove_synthetic_active_pins(engine)
    profile = profiles[0]
    subject_id = UUID(profile["subject_id"])
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        async with session.begin():
            pending = await create_pending_report(
                session,
                identifier=profile["inn"],
            )
            pending_id = pending.id
    h1_report = _newer_h1_report(profile, pending_id)
    parsed, _config = await build_activation_decision(
        engine,
        (profile,),
        decision_id=(
            "25000000-0000-4000-8000-000000000117"
            if winner == "finalizer"
            else "25000000-0000-4000-8000-000000000118"
        ),
        indexable=True,
    )
    await _bind_activation(engine, parsed)

    finalizer_holds_report = asyncio.Event()
    release_finalizer = asyncio.Event()
    rollout_reached_plan = asyncio.Event()
    release_rollout = asyncio.Event()
    original_plan = presentations_module._plan_active_h2_pin_locked

    async def held_rollout_plan(*args, **kwargs):
        planned = await original_plan(*args, **kwargs)
        rollout_reached_plan.set()
        await release_rollout.wait()
        return planned

    monkeypatch.setattr(
        presentations_module,
        "_plan_active_h2_pin_locked",
        held_rollout_plan,
    )

    async def finalize_h1(*, hold_report: bool) -> UUID:
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            async with session.begin():
                if hold_report:
                    locked = await session.get(
                        CompanyReportRecord,
                        pending_id,
                        with_for_update=True,
                    )
                    assert locked is not None
                    finalizer_holds_report.set()
                    await release_finalizer.wait()
                stored = await finalize_report(
                    session,
                    h1_report,
                    finished_at=h1_report.generated_at,
                )
                return stored.id

    async def apply_rollout() -> tuple[str, str | None]:
        async with AsyncSession(bind=engine) as session:
            try:
                async with session.begin():
                    outcome = await assign_rollout_pin_cas(
                        session,
                        command=_activation_command(parsed),
                    )
            except PresentationAssignmentConflict as exc:
                return exc.code, str(exc)
        return outcome.code, None

    if winner == "finalizer":
        finalizer_task = asyncio.create_task(finalize_h1(hold_report=True))
        await asyncio.wait_for(finalizer_holds_report.wait(), timeout=10)
        rollout_task = asyncio.create_task(apply_rollout())
        await asyncio.sleep(0.1)
        assert rollout_task.done() is False
        release_finalizer.set()
        assert await finalizer_task == pending_id
        await asyncio.wait_for(rollout_reached_plan.wait(), timeout=10)
        async with AsyncSession(bind=engine) as session:
            immutable_before = await _immutable_subject_row_bytes(
                session,
                subject_id,
            )
            publication_before = await _publication_row_bytes(session, subject_id)
        assert await _rollout_mutation_counts(engine) == (0, 0, 0)
        release_rollout.set()
        rollout_result = await rollout_task

        assert rollout_result == (
            "presentation_assignment_conflict",
            "unassigned H1 predecessor conflicts",
        )
        assert await _rollout_mutation_counts(engine) == (0, 0, 0)
        async with AsyncSession(bind=engine) as session:
            assert (
                await _immutable_subject_row_bytes(session, subject_id)
                == immutable_before
            )
            assert (
                await _publication_row_bytes(session, subject_id)
                == publication_before
            )
            assignment = await session.scalar(
                select(CompanyReportPresentationAssignment).where(
                    CompanyReportPresentationAssignment.subject_id == subject_id
                )
            )
        assert assignment is None
    else:
        rollout_task = asyncio.create_task(apply_rollout())
        await asyncio.wait_for(rollout_reached_plan.wait(), timeout=10)
        finalizer_task = asyncio.create_task(finalize_h1(hold_report=False))
        await asyncio.sleep(0.1)
        assert finalizer_task.done() is False
        release_rollout.set()
        rollout_result, finalized_id = await asyncio.gather(
            rollout_task,
            finalizer_task,
        )

        assert rollout_result == ("applied", None)
        assert finalized_id == pending_id
        assert await _rollout_mutation_counts(engine) == (1, 1, 1)
        async with AsyncSession(bind=engine) as session:
            assignment = await session.scalar(
                select(CompanyReportPresentationAssignment).where(
                    CompanyReportPresentationAssignment.subject_id == subject_id
                )
            )
        assert assignment is not None
        assert assignment.presentation_contract == H2_CONTRACT

    async with AsyncSession(bind=engine) as session:
        stored = await session.get(CompanyReportRecord, pending_id)
    assert stored is not None and stored.lifecycle_status == "complete"
    assert stored.snapshot_hash is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("winner", ("publisher", "rollout"))
async def test_rollout_real_postgres_h1_publication_noindex_h2_subject_fence(
    engine,
    db_url: str,
    monkeypatch: pytest.MonkeyPatch,
    winner: str,
) -> None:
    profiles = await prepare_unassigned_acceptance_seed(engine, db_url)
    await _remove_synthetic_active_pins(engine)
    profile = profiles[0]
    await _make_latest_sufficient_h1_candidate(engine, profile)
    claim, subject_id = await _claimed_h1_publication(engine)
    assert UUID(profile["subject_id"]) == subject_id
    parsed, _config = await build_activation_decision(
        engine,
        (profile,),
        decision_id=(
            "25000000-0000-4000-8000-000000000111"
            if winner == "publisher"
            else "25000000-0000-4000-8000-000000000112"
        ),
        indexable=False,
    )
    await _bind_activation(engine, parsed)
    winner_holds_subject = asyncio.Event()
    release_winner = asyncio.Event()

    async def finalize_publication() -> None:
        async with AsyncSession(bind=engine) as session:
            async with session.begin():
                await finalize_batch_claim(session, claim=claim)

    async def apply_rollout() -> str:
        async with AsyncSession(bind=engine) as session:
            try:
                async with session.begin():
                    outcome = await assign_rollout_pin_cas(
                        session,
                        command=_activation_command(parsed),
                    )
            except PresentationAssignmentConflict:
                return "presentation_assignment_conflict"
        return outcome.code

    if winner == "publisher":
        original_upsert = publications_module._upsert_publication

        async def held_publisher_upsert(*args, **kwargs):
            winner_holds_subject.set()
            await release_winner.wait()
            return await original_upsert(*args, **kwargs)

        monkeypatch.setattr(
            publications_module, "_upsert_publication", held_publisher_upsert
        )
        winner_task = asyncio.create_task(finalize_publication())
        await asyncio.wait_for(winner_holds_subject.wait(), timeout=5)
        contender_task = asyncio.create_task(apply_rollout())
    else:
        original_plan = presentations_module._plan_active_h2_pin_locked

        async def held_rollout_plan(*args, **kwargs):
            winner_holds_subject.set()
            await release_winner.wait()
            return await original_plan(*args, **kwargs)

        monkeypatch.setattr(
            presentations_module, "_plan_active_h2_pin_locked", held_rollout_plan
        )
        winner_task = asyncio.create_task(apply_rollout())
        await asyncio.wait_for(winner_holds_subject.wait(), timeout=5)
        contender_task = asyncio.create_task(finalize_publication())

    await asyncio.sleep(0.1)
    assert contender_task.done() is False
    release_winner.set()
    winner_result, contender_result = await asyncio.gather(
        winner_task, contender_task
    )

    async with AsyncSession(bind=engine) as session:
        publication = await session.scalar(
            select(CompanyReportPublication).where(
                CompanyReportPublication.subject_id == subject_id
            )
        )
        item = await session.get(CompanyReportPublicationBatchItem, claim.item_id)
        assignment = await session.scalar(
            select(CompanyReportPresentationAssignment).where(
                CompanyReportPresentationAssignment.subject_id == subject_id
            )
        )
    assert item is not None
    if winner == "publisher":
        assert winner_result is None
        assert contender_result == "presentation_assignment_conflict"
        assert publication is not None and publication.indexable is True
        assert item.state == "published"
        assert assignment is None
        assert await _rollout_mutation_counts(engine) == (0, 0, 0)
    else:
        assert winner_result == "applied"
        assert contender_result is None
        assert publication is None
        assert item.state == "failed"
        assert item.reason_code in {"safe_policy_error", "state_conflict"}
        assert assignment is not None
        assert assignment.presentation_contract == H2_CONTRACT
        assert await _rollout_mutation_counts(engine) == (1, 1, 1)


@pytest.mark.asyncio
async def test_rollout_real_postgres_durable_prefix_rolls_back_failed_target_and_resumes(
    engine,
    db_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profiles = await prepare_unassigned_acceptance_seed(engine, db_url)
    selected = profiles[:2]
    parsed, config = await build_activation_decision(
        engine,
        selected,
        decision_id="25000000-0000-4000-8000-000000000101",
        indexable=False,
    )
    config = with_database_url(config, db_url)
    original_execute = rollout_module._execute_target
    original_boundary = rollout_module._require_between_transaction_boundary
    executions = 0
    boundaries: list[bool] = []

    async def fail_second_after_mutation(session, *, parsed, target):
        nonlocal executions
        outcome = await original_execute(session, parsed=parsed, target=target)
        executions += 1
        if executions == 2:
            raise RuntimeError("synthetic target transaction failure")
        return outcome

    def observe_boundary(connection) -> None:
        boundaries.append(connection.in_transaction())
        original_boundary(connection)

    monkeypatch.setattr(rollout_module, "_execute_target", fail_second_after_mutation)
    monkeypatch.setattr(
        rollout_module, "_require_between_transaction_boundary", observe_boundary
    )
    first = await run_rollout_mutation(
        parsed,
        config,
        mode="apply",
        confirm_digest=parsed.decision_digest,
    )

    assert [result.code for result in first.results] == [
        "applied",
        "rollout_target_failed",
    ]
    assert first.stopped is True
    assert boundaries and not any(boundaries)
    async with AsyncSession(bind=engine) as session:
        assignments = list(
            (
                await session.scalars(
                    select(CompanyReportPresentationAssignment).order_by(
                        CompanyReportPresentationAssignment.subject_id
                    )
                )
            ).all()
        )
        journal_count = await session.scalar(
            select(func.count()).select_from(
                CompanyReportPresentationAssignmentJournal
            )
        )
    assert [assignment.subject_id for assignment in assignments] == [
        UUID(selected[0]["subject_id"])
    ]
    assert journal_count == 1

    monkeypatch.setattr(rollout_module, "_execute_target", original_execute)
    resumed = await run_rollout_mutation(
        parsed,
        config,
        mode="apply",
        confirm_digest=parsed.decision_digest,
    )
    assert [result.code for result in resumed.results] == [
        "applied_current",
        "applied",
    ]
    assert resumed.stopped is False
    async with AsyncSession(bind=engine) as session:
        assert await session.scalar(
            select(func.count()).select_from(CompanyReportPresentationAssignment)
        ) == 2
        assert await session.scalar(
            select(func.count()).select_from(
                CompanyReportPresentationAssignmentJournal
            )
        ) == 2


@pytest.mark.asyncio
async def test_rollout_real_postgres_killed_backend_reports_lock_lost_and_reacquires(
    engine,
    db_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profiles = await prepare_unassigned_acceptance_seed(engine, db_url)
    selected = profiles[:2]
    parsed, config = await build_activation_decision(
        engine,
        selected,
        decision_id="25000000-0000-4000-8000-000000000102",
        indexable=False,
    )
    config = with_database_url(config, db_url)
    original_guard = rollout_module._guard_rollout_lock
    guards = 0
    killed_pid: int | None = None

    async def terminate_before_second_target(connection, backend_pid, lock_key):
        nonlocal guards, killed_pid
        guards += 1
        if guards == 3:
            killed_pid = backend_pid
            async with engine.connect() as observer:
                terminated = await observer.scalar(
                    text("SELECT pg_terminate_backend(:backend_pid)"),
                    {"backend_pid": backend_pid},
                )
                assert terminated is True
        await original_guard(connection, backend_pid, lock_key)

    monkeypatch.setattr(
        rollout_module, "_guard_rollout_lock", terminate_before_second_target
    )
    first = await run_rollout_mutation(
        parsed,
        config,
        mode="apply",
        confirm_digest=parsed.decision_digest,
    )
    assert [result.code for result in first.results] == [
        "applied",
        "rollout_lock_lost",
    ]
    assert first.stopped is True
    assert killed_pid is not None
    async with engine.connect() as observer:
        pid_exists = await observer.scalar(
            text("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE pid=:pid)"),
            {"pid": killed_pid},
        )
        lock_exists = await observer.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_locks "
                "WHERE pid=:pid AND locktype='advisory' AND granted)"
            ),
            {"pid": killed_pid},
        )
    assert pid_exists is False
    assert lock_exists is False

    monkeypatch.setattr(rollout_module, "_guard_rollout_lock", original_guard)
    resumed = await run_rollout_mutation(
        parsed,
        config,
        mode="apply",
        confirm_digest=parsed.decision_digest,
    )
    assert [result.code for result in resumed.results] == [
        "applied_current",
        "applied",
    ]
    assert resumed.stopped is False


@pytest.mark.asyncio
async def test_rollout_real_postgres_decision_binding_race_is_single_and_exact(
    engine,
) -> None:
    decision_id = UUID("25000000-0000-4000-8000-000000000103")
    digest = "d" * 64
    barrier = asyncio.Barrier(2)

    async def bind_once():
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            async with session.begin():
                await barrier.wait()
                return await bind_rollout_decision(
                    session,
                    decision_id=decision_id,
                    decision_digest=digest,
                    schema_version="company_card_v2_rollout_decision_v1",
                    release_commit=RELEASE_SHA,
                    action="activate",
                    stage="allowlist",
                    target_contract=H2_CONTRACT,
                    h2_indexable=False,
                    target_count=1,
                )

    first, second = await asyncio.gather(bind_once(), bind_once())
    assert first.decision_id == second.decision_id == decision_id
    assert first.decision_digest == second.decision_digest == digest
    async with AsyncSession(bind=engine) as session:
        assert await session.scalar(
            select(func.count()).select_from(CompanyCardV2RolloutDecision)
        ) == 1
    async with AsyncSession(bind=engine) as session:
        async with session.begin():
            with pytest.raises(PresentationAssignmentConflict, match="identity conflicts"):
                await bind_rollout_decision(
                    session,
                    decision_id=decision_id,
                    decision_digest="e" * 64,
                    schema_version="company_card_v2_rollout_decision_v1",
                    release_commit=RELEASE_SHA,
                    action="activate",
                    stage="allowlist",
                    target_contract=H2_CONTRACT,
                    h2_indexable=False,
                    target_count=1,
                )


@pytest.mark.asyncio
async def test_rollout_real_postgres_h1_h2_h1_uses_exact_pins_and_journal_order(
    engine,
    db_url: str,
) -> None:
    profiles = await prepare_unassigned_acceptance_seed(engine, db_url)
    selected = profiles[:1]
    activation, config = await build_activation_decision(
        engine,
        selected,
        decision_id="25000000-0000-4000-8000-000000000104",
        indexable=False,
    )
    config = with_database_url(config, db_url)
    subject_id = UUID(selected[0]["subject_id"])
    async with AsyncSession(bind=engine) as session:
        before_reports, before_pins, before_artifacts = (
            await _immutable_subject_row_bytes(session, subject_id)
        )
        assert before_reports
        assert before_pins
        assert before_artifacts
    applied = await run_rollout_mutation(
        activation,
        config,
        mode="apply",
        confirm_digest=activation.decision_digest,
    )
    assert [result.code for result in applied.results] == ["applied"]
    rollback = await build_rollback_decision(
        engine,
        selected,
        decision_id="25000000-0000-4000-8000-000000000105",
    )
    rolled_back = await run_rollout_mutation(
        rollback,
        config,
        mode="rollback",
        confirm_digest=rollback.decision_digest,
    )
    assert [result.code for result in rolled_back.results] == ["applied"]

    async with AsyncSession(bind=engine) as session:
        assignment = await session.scalar(select(CompanyReportPresentationAssignment))
        journals = list(
            (
                await session.scalars(
                    select(CompanyReportPresentationAssignmentJournal).order_by(
                        CompanyReportPresentationAssignmentJournal.generation
                    )
                )
            ).all()
        )
        after_reports, after_pins, after_artifacts = (
            await _immutable_subject_row_bytes(session, subject_id)
        )
    assert assignment is not None
    assert (
        assignment.presentation_contract,
        assignment.pin_generation,
        assignment.generation,
    ) == (H1_CONTRACT, 1, 2)
    assert [journal.presentation_contract for journal in journals] == [
        H2_CONTRACT,
        H1_CONTRACT,
    ]
    assert [journal.pin_generation for journal in journals] == [
        activation.decision.targets[0].expected_active_h2_pin_generation,
        1,
    ]
    assert [journal.reason_code for journal in journals] == [
        "activate_allowlist",
        "rollback_emergency_rollback",
    ]
    assert after_reports == before_reports
    assert after_pins == before_pins
    assert after_artifacts == before_artifacts
