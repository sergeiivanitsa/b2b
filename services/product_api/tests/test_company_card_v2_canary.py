from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

TESTS_UNIT = Path(__file__).resolve().parents[1] / "tests_unit"
if str(TESTS_UNIT) not in sys.path:
    sys.path.append(str(TESTS_UNIT))

from company_report_signal_test_helpers import (  # noqa: E402
    complete_company_report,
    counterparty_facts,
)
from product_api.company_reports.company_card_v2.canary import (  # noqa: E402
    CanaryExecutionError,
    CanaryRuntimeConfig,
    _local_schema_head,
    build_canary_decisions,
    inspect_canary,
    prepare_canary,
    status_canary,
)
from product_api.company_reports.company_card_v2 import (  # noqa: E402
    canary as canary_module,
)
from product_api.company_reports.company_card_v2.canary_models import (  # noqa: E402
    CanaryExpectedAssignmentV1,
    CanaryExpectedH2V1,
    CanaryH1RollbackV1,
    CompanyCardV2CanaryPlanV1,
    CompanyCardV2CanaryReceiptV1,
    canary_plan_digest,
    parse_canary_plan_bytes,
    parse_canary_receipt_bytes,
)
from product_api.company_reports.company_card_v2.rollout import (  # noqa: E402
    RolloutRuntimeConfig,
    run_rollout_mutation,
)
from product_api.company_reports.company_card_v2.rollout_models import (  # noqa: E402
    load_rollout_decision,
)
from product_api.company_reports.persistence.models import (  # noqa: E402
    CompanyCardNarrativeArtifact,
    CompanyCardNarrativeJob,
    CompanyReportH2LifecycleHead,
    CompanyReportJob,
    CompanyReportPresentation,
    CompanyReportPresentationAssignment,
    CompanyReportPresentationAssignmentJournal,
    CompanyReportPresentationPin,
    CompanyReportPublication,
    CompanyReportRecord,
    CompanyReportSubject,
)
from product_api.company_reports.persistence.errors import (  # noqa: E402
    CompanyReportJobStateConflictError,
)
from product_api.company_reports.persistence.jobs import (  # noqa: E402
    enqueue_company_report_job,
)
from product_api.company_reports.persistence.presentations import (  # noqa: E402
    append_presentation_pin,
    assign_pin_cas,
)
from product_api.company_reports.persistence.repository import (  # noqa: E402
    create_pending_report,
    finalize_report,
)
from product_api.company_reports.persistence.publications import (  # noqa: E402
    create_batch,
    process_batch,
    set_publication_control,
)
from product_api.company_reports.persistence.serialization import (  # noqa: E402
    calculate_company_report_snapshot_hash,
    company_report_to_snapshot,
)
from product_api.company_reports.public_document_service import (  # noqa: E402
    scan_public_sitemap,
)
from tests_support.iteration25_rollout import (  # noqa: E402
    RELEASE_SHA,
    prepare_unassigned_acceptance_seed,
)


INN = "7707079463"


def _config(db_url: str, *, inn: str, key_id: str = "active_2026"):
    return CanaryRuntimeConfig(
        database_url=db_url,
        release_commit=RELEASE_SHA,
        schema_revision=_local_schema_head(),
        rollout_generation=1,
        arbitration_mask_key_id=key_id,
    )


async def _store_h1(
    engine,
    *,
    inn: str = INN,
    publish: bool,
    usable: bool = True,
    full_name: str = "ООО Канареечный тест",
    short_name: str | None = None,
) -> tuple[UUID, UUID]:
    now = datetime(2026, 8, 29, tzinfo=timezone.utc)
    report = complete_company_report(
        counterparty=counterparty_facts().model_copy(
            update={
                "inn": inn,
                "full_name": full_name,
                "short_name": short_name,
            }
        ),
        report_version="2",
    ).model_copy(
        update={
            "report_id": uuid4(),
            "generated_at": now,
            "target_identifier": inn,
            "usable_for_public_page": usable,
            "usable_for_future_scoring": usable,
        }
    )
    raw = company_report_to_snapshot(report)
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        async with session.begin():
            subject = CompanyReportSubject(
                normalized_identifier=inn,
                identifier_type="legal_entity_inn",
            )
            session.add(subject)
            await session.flush()
            session.add(
                CompanyReportRecord(
                    id=report.report_id,
                    subject_id=subject.id,
                    report_version="2",
                    writer_profile="h1_legacy_writer_v2",
                    presentation_contract="company_public_h1_v1",
                    rollout_generation=0,
                    lifecycle_status="complete",
                    started_at=now,
                    generated_at=now,
                    finished_at=now,
                    normalized_snapshot=raw,
                    snapshot_hash=calculate_company_report_snapshot_hash(raw),
                    completeness_snapshot={},
                    freshness_snapshot={},
                    warnings_snapshot=[],
                    usable_for_public_page=usable,
                    usable_for_future_scoring=usable,
                )
            )
        subject_id = subject.id
    if publish:
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            async with session.begin():
                await set_publication_control(
                    session, state="active", enabled=True
                )
                batch = await create_batch(session, limit=1, max_limit=1)
            async with session.begin():
                await process_batch(session, batch_id=batch.id)
    return subject_id, report.report_id


async def _append_h1(
    engine,
    *,
    subject_id: UUID,
    inn: str = INN,
    generated_at: datetime,
    usable: bool,
) -> UUID:
    report = complete_company_report(
        counterparty=counterparty_facts().model_copy(
            update={"inn": inn, "full_name": "ООО Новая канареечная версия"}
        ),
        report_version="2",
    ).model_copy(
        update={
            "report_id": uuid4(),
            "generated_at": generated_at,
            "target_identifier": inn,
            "usable_for_public_page": usable,
            "usable_for_future_scoring": usable,
        }
    )
    raw = company_report_to_snapshot(report)
    async with AsyncSession(bind=engine) as session:
        async with session.begin():
            session.add(
                CompanyReportRecord(
                    id=report.report_id,
                    subject_id=subject_id,
                    report_version="2",
                    writer_profile="h1_legacy_writer_v2",
                    presentation_contract="company_public_h1_v1",
                    rollout_generation=0,
                    lifecycle_status="complete",
                    started_at=generated_at,
                    generated_at=generated_at,
                    finished_at=generated_at,
                    normalized_snapshot=raw,
                    snapshot_hash=calculate_company_report_snapshot_hash(raw),
                    completeness_snapshot={},
                    freshness_snapshot={},
                    warnings_snapshot=[],
                    usable_for_public_page=usable,
                    usable_for_future_scoring=usable,
                )
            )
    return report.report_id


async def _publication_identity(engine, subject_id: UUID) -> tuple[object, ...]:
    async with AsyncSession(bind=engine) as session:
        publication = await session.scalar(
            select(CompanyReportPublication).where(
                CompanyReportPublication.subject_id == subject_id
            )
        )
        assert publication is not None
        return (
            publication.id,
            publication.report_id,
            publication.canonical_path,
            publication.snapshot_hash,
            publication.batch_generation,
            publication.indexable,
            publication.published_lastmod,
        )


async def _sitemap_identity(engine) -> tuple[tuple[str, str], ...]:
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        result = await scan_public_sitemap(
            session,
            chunk_size=10,
            chunk_number=1,
            validation_window_size=10,
        )
        return tuple(
            (entry.canonical_path, entry.published_lastmod.isoformat())
            for entry in result.entries
        )


async def _prepare_surface_counts(
    engine,
    *,
    subject_id: UUID,
) -> dict[str, int]:
    async with AsyncSession(bind=engine) as session:
        h2_reports = int(
            await session.scalar(
                select(func.count())
                .select_from(CompanyReportRecord)
                .where(
                    CompanyReportRecord.subject_id == subject_id,
                    CompanyReportRecord.writer_profile
                    == "company_card_v2_writer_v3",
                )
            )
            or 0
        )
        h2_jobs = int(
            await session.scalar(
                select(func.count())
                .select_from(CompanyReportJob)
                .where(
                    CompanyReportJob.subject_id == subject_id,
                    CompanyReportJob.writer_profile
                    == "company_card_v2_writer_v3",
                )
            )
            or 0
        )
        values: dict[str, int] = {
            "h2_reports": h2_reports,
            "h2_jobs": h2_jobs,
        }
        for name, model in (
            ("presentations", CompanyReportPresentation),
            ("heads", CompanyReportH2LifecycleHead),
            ("pins", CompanyReportPresentationPin),
            ("assignments", CompanyReportPresentationAssignment),
            ("assignment_journal", CompanyReportPresentationAssignmentJournal),
            ("publications", CompanyReportPublication),
        ):
            values[name] = int(
                await session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.subject_id == subject_id)
                )
                or 0
            )
        return values


def _newer_h1_report(*, report_id: UUID, generated_at: datetime):
    return complete_company_report(
        counterparty=counterparty_facts().model_copy(
            update={
                "inn": INN,
                "full_name": "ООО Конкурирующая H1 версия",
            }
        ),
        report_version="2",
    ).model_copy(
        update={
            "report_id": report_id,
            "generated_at": generated_at,
            "target_identifier": INN,
            "usable_for_public_page": True,
            "usable_for_future_scoring": True,
        }
    )


async def _record_prepared_ready_lineage(
    engine,
    *,
    plan,
    subject_id: UUID,
    report_id: UUID,
    presentation_id: UUID,
) -> CompanyCardV2CanaryReceiptV1:
    terminal_at = datetime(2026, 8, 29, 2, tzinfo=timezone.utc)
    job_id = uuid4()
    token = uuid4()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        async with session.begin():
            report = await session.get(CompanyReportRecord, report_id)
            assert report is not None
            session.add(
                CompanyReportJob(
                    id=job_id,
                    report_id=report.id,
                    subject_id=subject_id,
                    state="succeeded",
                    writer_profile=report.writer_profile,
                    presentation_contract=report.presentation_contract,
                    rollout_generation=report.rollout_generation,
                    arbitration_collection_enabled=report.arbitration_collection_enabled,
                    arbitration_mask_key_id=report.arbitration_mask_key_id,
                    fence_generation=1,
                    worker_token=token,
                    attempt_count=1,
                    claimed_at=terminal_at,
                    heartbeat_at=terminal_at,
                    lease_expires_at=terminal_at,
                    finished_at=terminal_at,
                )
            )
            session.add(
                CompanyReportH2LifecycleHead(
                    subject_id=subject_id,
                    presentation_id=presentation_id,
                    report_id=report.id,
                    presentation_contract="company_public_h2_v1",
                    rollout_generation=report.rollout_generation,
                    head_generation=plan.expected_h2.head_generation + 1,
                )
            )
    return CompanyCardV2CanaryReceiptV1(
        schema_version="company_card_v2_canary_receipt_v1",
        plan_digest=canary_plan_digest(plan),
        target_subject_id=str(subject_id),
        head_generation=plan.expected_h2.head_generation + 1,
        presentation_id=str(presentation_id),
        report_id=str(report_id),
        job_id=str(job_id),
    )


async def _seed_ready_receipt(
    engine,
    db_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    assign_h1: bool = False,
):
    profile = (await prepare_unassigned_acceptance_seed(engine, db_url))[0]
    monkeypatch.setattr(
        "product_api.company_reports.company_card_v2.canary._RECOVERY_TARGET_INN",
        profile["inn"],
    )
    subject_id = UUID(profile["subject_id"])
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        async with session.begin():
            h2 = await session.get(
                CompanyReportRecord, UUID(profile["h2_report_id"])
            )
            h1_report = await session.get(
                CompanyReportRecord, UUID(profile["h1_report_id"])
            )
            h1_pins = list(
                (
                    await session.scalars(
                        select(CompanyReportPresentationPin)
                        .where(
                            CompanyReportPresentationPin.subject_id
                            == subject_id,
                            CompanyReportPresentationPin.presentation_contract
                            == "company_public_h1_v1",
                        )
                        .order_by(CompanyReportPresentationPin.generation)
                    )
                ).all()
            )
            h1_pin = h1_pins[-1]
            assert h2 is not None and h1_pin is not None
            assert h1_report is not None
            assert h1_report.generated_at is not None
            assert h1_pin.canonical_path is not None
            presentation = await session.scalar(
                select(CompanyReportPresentation).where(
                    CompanyReportPresentation.report_id == h2.id
                )
            )
            assert presentation is not None
            if assign_h1:
                await assign_pin_cas(
                    session,
                    subject_id=subject_id,
                    pin=h1_pin,
                    expected_generation=1,
                )
                rollback_pin = h1_pin
                expected_assignment = CanaryExpectedAssignmentV1(
                    generation=1,
                    presentation_contract="company_public_h1_v1",
                    pin_generation=h1_pin.generation,
                )
                source_kind = "assignment_pin"
                pin_exists = True
            else:
                rollback_generation = h1_pin.generation + 1
                rollback_pin = await append_presentation_pin(
                    session,
                    subject_id=subject_id,
                    report=h1_report,
                    contract="company_public_h1_v1",
                    generation=rollback_generation,
                    publication_policy_version="publication_sufficiency_v1",
                    canonical_path=h1_pin.canonical_path,
                    published_lastmod=h1_report.generated_at,
                    indexable=True,
                )
                expected_assignment = CanaryExpectedAssignmentV1(
                    generation=0,
                    presentation_contract=None,
                    pin_generation=None,
                )
                source_kind = "latest_eligible_report"
                pin_exists = False
        key_id = h2.arbitration_mask_key_id
    assert isinstance(key_id, str)
    assert isinstance(h1_report.snapshot_hash, str)
    assert rollback_pin.canonical_path is not None
    assert rollback_pin.published_lastmod is not None
    config = _config(db_url, inn=profile["inn"], key_id=key_id)
    plan = CompanyCardV2CanaryPlanV1(
        schema_version="company_card_v2_canary_plan_v1",
        release_commit=config.release_commit,
        database_schema_revision=config.schema_revision,
        rollout_generation=config.rollout_generation,
        arbitration_mask_key_id=config.arbitration_mask_key_id,
        target_subject_id=str(subject_id),
        target_inn=profile["inn"],
        expected_assignment=expected_assignment,
        h1_rollback=CanaryH1RollbackV1(
            source_kind=source_kind,
            report_id=str(h1_report.id),
            snapshot_hash=h1_report.snapshot_hash,
            pin_generation=rollback_pin.generation,
            pin_exists=pin_exists,
            publication_policy_version="publication_sufficiency_v1",
            canonical_path=rollback_pin.canonical_path,
            published_lastmod=(
                rollback_pin.published_lastmod.astimezone(timezone.utc)
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z")
            ),
        ),
        expected_h2=CanaryExpectedH2V1(
            head_generation=0,
            head_report_id=None,
            active_report_id=None,
            active_job_state=None,
        ),
    )
    receipt = await _record_prepared_ready_lineage(
        engine,
        plan=plan,
        subject_id=subject_id,
        report_id=h2.id,
        presentation_id=presentation.id,
    )
    return profile, subject_id, h2.id, config, plan, receipt


@pytest.mark.asyncio
async def test_canary_prepare_is_idempotent_and_has_no_public_side_effects(
    engine,
    db_url: str,
    tmp_path: Path,
) -> None:
    subject_id, _report_id = await _store_h1(engine, publish=True)
    publication_before = await _publication_identity(engine, subject_id)
    sitemap_before = await _sitemap_identity(engine)
    plan_path = (tmp_path / "canary-plan.json").resolve()
    inspected = await inspect_canary(
        target_inn=INN,
        plan_path=plan_path,
        config=_config(db_url, inn=INN),
    )
    plan = parse_canary_plan_bytes(plan_path.read_bytes())
    receipt_path = (tmp_path / "canary-receipt.json").resolve()
    assert inspected["plan_digest"]
    assert plan.h1_rollback.pin_exists is True

    first = await prepare_canary(
        plan=plan,
        confirm_digest=inspected["plan_digest"],
        receipt_path=receipt_path,
        config=_config(db_url, inn=INN),
    )
    second = await prepare_canary(
        plan=plan,
        confirm_digest=inspected["plan_digest"],
        receipt_path=receipt_path,
        config=_config(db_url, inn=INN),
    )
    assert first["status"] == "queued"
    assert second["status"] == "prepared_reused"
    assert await _publication_identity(engine, subject_id) == publication_before
    assert await _sitemap_identity(engine) == sitemap_before

    async with AsyncSession(bind=engine) as session:
        assert await session.scalar(
            select(func.count()).select_from(CompanyReportPresentationAssignment)
        ) == 0
        assert await session.scalar(
            select(func.count()).select_from(
                CompanyReportPresentationAssignmentJournal
            )
        ) == 0
        assert await session.scalar(
            select(func.count()).select_from(CompanyReportJob)
        ) == 1
        assert await session.scalar(
            select(func.count()).select_from(CompanyReportPresentation)
        ) == 1
        assert await session.scalar(
            select(func.count()).select_from(CompanyReportH2LifecycleHead)
        ) == 1
        assert await session.scalar(
            select(func.count())
            .select_from(CompanyReportPresentationPin)
            .where(
                CompanyReportPresentationPin.presentation_contract
                == "company_public_h1_v1"
            )
        ) == 1
        job = await session.scalar(select(CompanyReportJob))
        assert job is not None
        assert job.arbitration_collection_enabled is True
        assert job.arbitration_mask_key_id == "active_2026"

    status = await status_canary(
        plan=plan,
        receipt=parse_canary_receipt_bytes(receipt_path.read_bytes()),
        config=_config(db_url, inn=INN),
    )
    assert status["lifecycle"] == "queued"
    assert status["staged_resolved"] is False


@pytest.mark.asyncio
async def test_canary_prepare_pins_public_h1_canonical_idempotently_when_names_differ(
    engine,
    db_url: str,
    tmp_path: Path,
) -> None:
    subject_id, report_id = await _store_h1(
        engine,
        publish=False,
        full_name="Общество с ограниченной ответственностью Канареечный тест",
        short_name="ООО Канареечный тест",
    )
    sitemap_before = await _sitemap_identity(engine)
    plan_path = (tmp_path / "canary-plan-unpublished.json").resolve()
    inspected = await inspect_canary(
        target_inn=INN,
        plan_path=plan_path,
        config=_config(db_url, inn=INN),
    )
    plan = parse_canary_plan_bytes(plan_path.read_bytes())
    receipt_path = (tmp_path / "canary-unpublished-receipt.json").resolve()
    assert plan.h1_rollback.source_kind == "latest_eligible_report"
    assert plan.h1_rollback.pin_exists is False
    assert (
        plan.h1_rollback.canonical_path
        == f"/company/{INN}-ooo-kanareechnyi-test"
    )

    first = await prepare_canary(
        plan=plan,
        confirm_digest=inspected["plan_digest"],
        receipt_path=receipt_path,
        config=_config(db_url, inn=INN),
    )
    second = await prepare_canary(
        plan=plan,
        confirm_digest=inspected["plan_digest"],
        receipt_path=receipt_path,
        config=_config(db_url, inn=INN),
    )
    assert first["status"] == "queued"
    assert second["status"] == "prepared_reused"
    assert await _sitemap_identity(engine) == sitemap_before == ()

    async with AsyncSession(bind=engine) as session:
        assert await session.scalar(
            select(func.count()).select_from(CompanyReportPublication)
        ) == 0
        assert await session.scalar(
            select(func.count()).select_from(CompanyReportPresentationAssignment)
        ) == 0
        assert await session.scalar(
            select(func.count()).select_from(
                CompanyReportPresentationAssignmentJournal
            )
        ) == 0
        assert await session.scalar(
            select(func.count()).select_from(CompanyReportJob)
        ) == 1
        pins = list(
            (
                await session.scalars(
                    select(CompanyReportPresentationPin).where(
                        CompanyReportPresentationPin.subject_id == subject_id,
                        CompanyReportPresentationPin.presentation_contract
                        == "company_public_h1_v1",
                    )
                )
            ).all()
        )
        assert len(pins) == 1
        assert pins[0].report_id == report_id
        assert pins[0].generation == plan.h1_rollback.pin_generation
        assert pins[0].canonical_path == plan.h1_rollback.canonical_path


@pytest.mark.parametrize("winner", ("prepare", "h1_enqueue"))
@pytest.mark.asyncio
async def test_canary_prepare_and_new_h1_enqueue_share_subject_fence(
    engine,
    db_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    winner: str,
) -> None:
    subject_id, h1_report_id = await _store_h1(engine, publish=False)
    sitemap_before = await _sitemap_identity(engine)
    plan_path = (tmp_path / f"enqueue-{winner}-plan.json").resolve()
    inspected = await inspect_canary(
        target_inn=INN,
        plan_path=plan_path,
        config=_config(db_url, inn=INN),
    )
    plan_bytes = plan_path.read_bytes()
    plan = parse_canary_plan_bytes(plan_bytes)
    receipt_path = (tmp_path / f"enqueue-{winner}-receipt.json").resolve()
    winner_holds_fence = asyncio.Event()
    release_winner = asyncio.Event()
    enqueue_started = asyncio.Event()
    recheck_calls = 0

    async def run_prepare():
        try:
            return await prepare_canary(
                plan=plan,
                confirm_digest=inspected["plan_digest"],
                receipt_path=receipt_path,
                config=_config(db_url, inn=INN),
            )
        except Exception as exc:  # the rejected contender is asserted below
            return exc

    async def enqueue_h1(*, hold_subject: bool):
        try:
            async with AsyncSession(bind=engine, expire_on_commit=False) as session:
                async with session.begin():
                    if hold_subject:
                        subject = await session.get(
                            CompanyReportSubject,
                            subject_id,
                            with_for_update=True,
                        )
                        assert subject is not None
                        winner_holds_fence.set()
                        await release_winner.wait()
                    enqueue_started.set()
                    return await enqueue_company_report_job(session, INN)
        except Exception as exc:  # the rejected contender is asserted below
            return exc

    if winner == "prepare":
        original_recheck = canary_module._recheck_h1_source

        async def held_first_recheck(*args, **kwargs):
            nonlocal recheck_calls
            result = await original_recheck(*args, **kwargs)
            recheck_calls += 1
            if recheck_calls == 1:
                winner_holds_fence.set()
                await release_winner.wait()
            return result

        monkeypatch.setattr(
            canary_module,
            "_recheck_h1_source",
            held_first_recheck,
        )
        prepare_task = asyncio.create_task(run_prepare())
        await asyncio.wait_for(winner_holds_fence.wait(), timeout=5)
        enqueue_task = asyncio.create_task(enqueue_h1(hold_subject=False))
        await asyncio.wait_for(enqueue_started.wait(), timeout=5)
        await asyncio.sleep(0.1)
        assert enqueue_task.done() is False
        release_winner.set()
        prepare_result, enqueue_result = await asyncio.wait_for(
            asyncio.gather(prepare_task, enqueue_task),
            timeout=10,
        )

        assert isinstance(prepare_result, dict)
        assert prepare_result["status"] == "queued"
        assert isinstance(enqueue_result, CompanyReportJobStateConflictError)
        assert "writer profile conflict" in str(enqueue_result)
        assert recheck_calls == 2
        assert receipt_path.exists()
        receipt = parse_canary_receipt_bytes(receipt_path.read_bytes())
        assert receipt.plan_digest == inspected["plan_digest"]
        assert await _prepare_surface_counts(
            engine, subject_id=subject_id
        ) == {
            "h2_reports": 1,
            "h2_jobs": 1,
            "presentations": 1,
            "heads": 1,
            "pins": 1,
            "assignments": 0,
            "assignment_journal": 0,
            "publications": 0,
        }
        async with AsyncSession(bind=engine) as session:
            h1_ids = tuple(
                (
                    await session.scalars(
                        select(CompanyReportRecord.id).where(
                            CompanyReportRecord.subject_id == subject_id,
                            CompanyReportRecord.writer_profile
                            == "h1_legacy_writer_v2",
                        )
                    )
                ).all()
            )
        assert h1_ids == (h1_report_id,)
    else:
        enqueue_task = asyncio.create_task(enqueue_h1(hold_subject=True))
        await asyncio.wait_for(winner_holds_fence.wait(), timeout=5)
        prepare_task = asyncio.create_task(run_prepare())
        await asyncio.sleep(0.1)
        assert prepare_task.done() is False
        release_winner.set()
        enqueue_result, prepare_result = await asyncio.wait_for(
            asyncio.gather(enqueue_task, prepare_task),
            timeout=10,
        )

        assert not isinstance(enqueue_result, Exception)
        assert enqueue_result.reused is False
        assert isinstance(prepare_result, CompanyReportJobStateConflictError)
        assert "writer profile conflict" in str(prepare_result)
        assert not receipt_path.exists()
        assert await _prepare_surface_counts(
            engine, subject_id=subject_id
        ) == {
            "h2_reports": 0,
            "h2_jobs": 0,
            "presentations": 0,
            "heads": 0,
            "pins": 0,
            "assignments": 0,
            "assignment_journal": 0,
            "publications": 0,
        }
        async with AsyncSession(bind=engine) as session:
            pending = await session.get(
                CompanyReportRecord, enqueue_result.report_id
            )
            assert pending is not None
            assert pending.lifecycle_status == "pending"
            assert pending.writer_profile == "h1_legacy_writer_v2"

    assert plan_path.read_bytes() == plan_bytes
    assert await _sitemap_identity(engine) == sitemap_before == ()


@pytest.mark.parametrize("winner", ("finalizer", "prepare_recheck"))
@pytest.mark.asyncio
async def test_canary_prepare_and_pending_h1_finalizer_share_report_fence(
    engine,
    db_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    winner: str,
) -> None:
    subject_id, original_h1_report_id = await _store_h1(
        engine, publish=False
    )
    pending_report_id = uuid4()
    generated_at = datetime(2026, 8, 30, tzinfo=timezone.utc)
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        async with session.begin():
            pending = await create_pending_report(
                session,
                identifier=INN,
                report_id=pending_report_id,
                report_version="2",
                request_id=f"race:{pending_report_id}",
                started_at=generated_at - timedelta(minutes=1),
            )
            assert pending.subject_id == subject_id
    newer_report = _newer_h1_report(
        report_id=pending_report_id,
        generated_at=generated_at,
    )
    sitemap_before = await _sitemap_identity(engine)
    plan_path = (tmp_path / f"finalize-{winner}-plan.json").resolve()
    inspected = await inspect_canary(
        target_inn=INN,
        plan_path=plan_path,
        config=_config(db_url, inn=INN),
    )
    plan_bytes = plan_path.read_bytes()
    plan = parse_canary_plan_bytes(plan_bytes)
    assert plan.h1_report_uuid == original_h1_report_id
    receipt_path = (tmp_path / f"finalize-{winner}-receipt.json").resolve()
    winner_holds_report = asyncio.Event()
    release_winner = asyncio.Event()
    finalizer_started = asyncio.Event()
    recheck_calls = 0

    async def run_prepare():
        try:
            return await prepare_canary(
                plan=plan,
                confirm_digest=inspected["plan_digest"],
                receipt_path=receipt_path,
                config=_config(db_url, inn=INN),
            )
        except Exception as exc:  # the precise fail-closed result is asserted
            return exc

    async def finalize_h1(*, hold_after_finalize: bool):
        try:
            async with AsyncSession(bind=engine, expire_on_commit=False) as session:
                async with session.begin():
                    finalizer_started.set()
                    stored = await finalize_report(
                        session,
                        newer_report,
                        finished_at=generated_at + timedelta(minutes=1),
                    )
                    if hold_after_finalize:
                        winner_holds_report.set()
                        await release_winner.wait()
                    return stored.id
        except Exception as exc:
            return exc

    if winner == "finalizer":
        finalize_task = asyncio.create_task(
            finalize_h1(hold_after_finalize=True)
        )
        await asyncio.wait_for(winner_holds_report.wait(), timeout=5)
        prepare_task = asyncio.create_task(run_prepare())
        await asyncio.sleep(0.1)
        assert prepare_task.done() is False
        release_winner.set()
        finalize_result, prepare_result = await asyncio.wait_for(
            asyncio.gather(finalize_task, prepare_task),
            timeout=10,
        )

        assert finalize_result == pending_report_id
        assert isinstance(prepare_result, CanaryExecutionError)
        assert prepare_result.code == "canary_plan_stale"
    else:
        original_recheck = canary_module._recheck_h1_source

        async def held_first_recheck(*args, **kwargs):
            nonlocal recheck_calls
            result = await original_recheck(*args, **kwargs)
            recheck_calls += 1
            if recheck_calls == 1:
                winner_holds_report.set()
                await release_winner.wait()
            return result

        monkeypatch.setattr(
            canary_module,
            "_recheck_h1_source",
            held_first_recheck,
        )
        prepare_task = asyncio.create_task(run_prepare())
        await asyncio.wait_for(winner_holds_report.wait(), timeout=5)
        finalize_task = asyncio.create_task(
            finalize_h1(hold_after_finalize=False)
        )
        await asyncio.wait_for(finalizer_started.wait(), timeout=5)
        await asyncio.sleep(0.1)
        assert finalize_task.done() is False
        release_winner.set()
        prepare_result, finalize_result = await asyncio.wait_for(
            asyncio.gather(prepare_task, finalize_task),
            timeout=10,
        )

        assert isinstance(prepare_result, CompanyReportJobStateConflictError)
        assert "pending report does not have a matching active job" in str(
            prepare_result
        )
        assert finalize_result == pending_report_id
        assert recheck_calls == 1

    assert not receipt_path.exists()
    assert plan_path.read_bytes() == plan_bytes
    assert await _sitemap_identity(engine) == sitemap_before == ()
    assert await _prepare_surface_counts(engine, subject_id=subject_id) == {
        "h2_reports": 0,
        "h2_jobs": 0,
        "presentations": 0,
        "heads": 0,
        "pins": 0,
        "assignments": 0,
        "assignment_journal": 0,
        "publications": 0,
    }
    async with AsyncSession(bind=engine) as session:
        finalized = await session.get(CompanyReportRecord, pending_report_id)
        original = await session.get(
            CompanyReportRecord, original_h1_report_id
        )
        assert finalized is not None
        assert finalized.lifecycle_status == "complete"
        assert finalized.snapshot_hash == calculate_company_report_snapshot_hash(
            company_report_to_snapshot(newer_report)
        )
        assert original is not None
        assert original.snapshot_hash == plan.h1_rollback.snapshot_hash


@pytest.mark.asyncio
async def test_receipt_write_failure_rolls_back_all_prepare_mutations(
    engine,
    db_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _store_h1(engine, publish=False)
    plan_path = (tmp_path / "atomic-plan.json").resolve()
    inspected = await inspect_canary(
        target_inn=INN,
        plan_path=plan_path,
        config=_config(db_url, inn=INN),
    )
    plan = parse_canary_plan_bytes(plan_path.read_bytes())

    async with AsyncSession(bind=engine) as session:
        before_values: list[int] = []
        for model in (
            CompanyReportJob,
            CompanyReportPresentation,
            CompanyReportH2LifecycleHead,
            CompanyReportPresentationPin,
            CompanyReportPresentationAssignment,
            CompanyReportPresentationAssignmentJournal,
        ):
            before_values.append(
                int(
                    await session.scalar(select(func.count()).select_from(model))
                    or 0
                )
            )
        before = tuple(before_values)

    def fail_receipt(_path, _receipt) -> None:
        raise CanaryExecutionError("canary_output_write_failed")

    monkeypatch.setattr(
        "product_api.company_reports.company_card_v2.canary._write_or_match_receipt",
        fail_receipt,
    )
    with pytest.raises(
        CanaryExecutionError, match="canary_output_write_failed"
    ):
        await prepare_canary(
            plan=plan,
            confirm_digest=inspected["plan_digest"],
            receipt_path=(tmp_path / "atomic-receipt.json").resolve(),
            config=_config(db_url, inn=INN),
        )

    async with AsyncSession(bind=engine) as session:
        after_values: list[int] = []
        for model in (
            CompanyReportJob,
            CompanyReportPresentation,
            CompanyReportH2LifecycleHead,
            CompanyReportPresentationPin,
            CompanyReportPresentationAssignment,
            CompanyReportPresentationAssignmentJournal,
        ):
            after_values.append(
                int(
                    await session.scalar(select(func.count()).select_from(model))
                    or 0
                )
            )
        after = tuple(after_values)
    assert after == before


@pytest.mark.asyncio
async def test_committed_prepare_cannot_be_reconstructed_or_replaced(
    engine,
    db_url: str,
    tmp_path: Path,
) -> None:
    await _store_h1(engine, publish=True)
    first_plan_path = (tmp_path / "first-plan.json").resolve()
    first_inspect = await inspect_canary(
        target_inn=INN,
        plan_path=first_plan_path,
        config=_config(db_url, inn=INN),
    )
    first_plan = parse_canary_plan_bytes(first_plan_path.read_bytes())
    first_receipt_path = (tmp_path / "first-receipt.json").resolve()
    await prepare_canary(
        plan=first_plan,
        confirm_digest=first_inspect["plan_digest"],
        receipt_path=first_receipt_path,
        config=_config(db_url, inn=INN),
    )

    terminal_at = datetime(2026, 8, 29, 1, tzinfo=timezone.utc)
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        async with session.begin():
            job = await session.scalar(
                select(CompanyReportJob).where(CompanyReportJob.state == "queued")
            )
            assert job is not None
            report = await session.get(CompanyReportRecord, job.report_id)
            assert report is not None
            job.state = "failed"
            job.finished_at = terminal_at
            job.safe_failure_code = "test_terminal"
            report.lifecycle_status = "failed"
            report.finished_at = terminal_at

    second_plan_path = (tmp_path / "second-plan.json").resolve()
    with pytest.raises(CanaryExecutionError, match="canary_h2_history_exists"):
        await inspect_canary(
            target_inn=INN,
            plan_path=second_plan_path,
            config=_config(db_url, inn=INN),
        )
    assert not second_plan_path.exists()

    original_receipt = parse_canary_receipt_bytes(
        first_receipt_path.read_bytes()
    )
    status = await status_canary(
        plan=first_plan,
        receipt=original_receipt,
        config=_config(db_url, inn=INN),
    )
    assert status["lifecycle"] == "failed"
    assert status["staged_resolved"] is False
    stale_output = (tmp_path / "stale-decisions").resolve()
    stale_output.mkdir()
    os.chmod(stale_output, 0o700)
    with pytest.raises(CanaryExecutionError, match="canary_not_ready"):
        await build_canary_decisions(
            plan=first_plan,
            receipt=original_receipt,
            config=_config(db_url, inn=INN),
            authorization_reference="production-recovery",
            abort_policy_reference="production-recovery-abort",
            observation_window_seconds=60,
            h2_indexable=True,
            activate_decision_id="25000000-0000-4000-8000-000000000921",
            rollback_decision_id="25000000-0000-4000-8000-000000000922",
            output_dir=stale_output,
        )
    assert list(stale_output.iterdir()) == []

    retried = await prepare_canary(
        plan=first_plan,
        confirm_digest=first_inspect["plan_digest"],
        receipt_path=first_receipt_path,
        config=_config(db_url, inn=INN),
    )
    assert retried["status"] == "prepared_reused"
    async with AsyncSession(bind=engine) as session:
        assert await session.scalar(
            select(func.count()).select_from(CompanyReportJob)
        ) == 1


@pytest.mark.asyncio
async def test_inspect_rejects_existing_h2_assignment(
    engine,
    db_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = (await prepare_unassigned_acceptance_seed(engine, db_url))[0]
    monkeypatch.setattr(
        "product_api.company_reports.company_card_v2.canary._RECOVERY_TARGET_INN",
        profile["inn"],
    )
    subject_id = UUID(profile["subject_id"])
    async with AsyncSession(bind=engine) as session:
        h2_report = await session.get(
            CompanyReportRecord, UUID(profile["h2_report_id"])
        )
        assert h2_report is not None
        key_id = h2_report.arbitration_mask_key_id
    assert isinstance(key_id, str)
    config = _config(
        db_url,
        inn=profile["inn"],
        key_id=key_id,
    )
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        async with session.begin():
            h1_pin = await session.scalar(
                select(CompanyReportPresentationPin).where(
                    CompanyReportPresentationPin.subject_id == subject_id,
                    CompanyReportPresentationPin.presentation_contract
                    == "company_public_h1_v1",
                )
            )
            h2_pin = await session.scalar(
                select(CompanyReportPresentationPin).where(
                    CompanyReportPresentationPin.subject_id == subject_id,
                    CompanyReportPresentationPin.presentation_contract
                    == "company_public_h2_v1",
                )
            )
            assert h1_pin is not None and h2_pin is not None
            await assign_pin_cas(
                session,
                subject_id=subject_id,
                pin=h1_pin,
                expected_generation=1,
            )

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        async with session.begin():
            assignment = await session.scalar(
                select(CompanyReportPresentationAssignment).where(
                    CompanyReportPresentationAssignment.subject_id == subject_id
                )
            )
            assert assignment is not None
            assignment.presentation_contract = "company_public_h2_v1"
            assignment.pin_generation = h2_pin.generation
            assignment.generation = 2
        jobs_before = int(
            await session.scalar(select(func.count()).select_from(CompanyReportJob))
            or 0
        )

    rejected_path = (tmp_path / "rejected-h2-assignment.json").resolve()
    with pytest.raises(CanaryExecutionError, match="canary_assignment_invalid"):
        await inspect_canary(
            target_inn=profile["inn"],
            plan_path=rejected_path,
            config=config,
        )
    assert not rejected_path.exists()
    async with AsyncSession(bind=engine) as session:
        assert int(
            await session.scalar(select(func.count()).select_from(CompanyReportJob))
            or 0
        ) == jobs_before


@pytest.mark.asyncio
async def test_insufficient_h1_inspect_is_read_only(
    engine,
    db_url: str,
    tmp_path: Path,
) -> None:
    await _store_h1(engine, publish=False, usable=False)
    async with AsyncSession(bind=engine) as session:
        before_values: list[int] = []
        for model in (
            CompanyReportRecord,
            CompanyReportJob,
            CompanyReportPresentationPin,
            CompanyReportPresentationAssignment,
        ):
            before_values.append(
                int(
                    await session.scalar(select(func.count()).select_from(model))
                    or 0
                )
            )
        before = tuple(before_values)
    plan_path = (tmp_path / "rejected-plan.json").resolve()
    with pytest.raises(CanaryExecutionError, match="canary_h1_unavailable"):
        await inspect_canary(
            target_inn=INN,
            plan_path=plan_path,
            config=_config(db_url, inn=INN),
        )
    assert not plan_path.exists()
    async with AsyncSession(bind=engine) as session:
        after_values: list[int] = []
        for model in (
            CompanyReportRecord,
            CompanyReportJob,
            CompanyReportPresentationPin,
            CompanyReportPresentationAssignment,
        ):
            after_values.append(
                int(
                    await session.scalar(select(func.count()).select_from(model))
                    or 0
                )
            )
        after = tuple(after_values)
    assert after == before


@pytest.mark.asyncio
async def test_inspect_never_skips_a_newer_ineligible_h1_for_older_history(
    engine,
    db_url: str,
    tmp_path: Path,
) -> None:
    subject_id, older_report_id = await _store_h1(
        engine, publish=False, usable=True
    )
    newer_report_id = await _append_h1(
        engine,
        subject_id=subject_id,
        generated_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
        usable=False,
    )
    assert newer_report_id != older_report_id
    before = await _sitemap_identity(engine)
    plan_path = (tmp_path / "no-history-scan-plan.json").resolve()

    with pytest.raises(CanaryExecutionError, match="canary_h1_unavailable"):
        await inspect_canary(
            target_inn=INN,
            plan_path=plan_path,
            config=_config(db_url, inn=INN),
        )

    assert not plan_path.exists()
    assert await _sitemap_identity(engine) == before == ()
    async with AsyncSession(bind=engine) as session:
        assert await session.scalar(
            select(func.count()).select_from(CompanyReportPresentationPin)
        ) == 0
        assert await session.scalar(
            select(func.count()).select_from(CompanyReportJob)
        ) == 0


@pytest.mark.parametrize(
    "mutation", ("artifact", "partial", "projection_digest")
)
@pytest.mark.asyncio
async def test_indexable_decision_rejects_nonfallback_or_partial_lineage(
    engine,
    db_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    profile, subject_id, report_id, config, plan, receipt = (
        await _seed_ready_receipt(
            engine, db_url, tmp_path, monkeypatch
        )
    )
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        async with session.begin():
            if mutation == "partial":
                report = await session.get(CompanyReportRecord, report_id)
                assert report is not None
                report.lifecycle_status = "partial"
            elif mutation == "artifact":
                source_pin = await session.scalar(
                    select(CompanyReportPresentationPin).where(
                        CompanyReportPresentationPin.subject_id == subject_id,
                        CompanyReportPresentationPin.presentation_contract
                        == "company_public_h2_v1",
                        CompanyReportPresentationPin.projection_scope
                        == "staged_publication",
                        CompanyReportPresentationPin.narrative_binding_status
                        == "resolved",
                    )
                )
                assert source_pin is not None
                fallback_artifact = await session.scalar(
                    select(CompanyCardNarrativeArtifact).where(
                        CompanyCardNarrativeArtifact.report_id == report_id,
                        CompanyCardNarrativeArtifact.binding_kind == "fallback",
                    )
                )
                assert fallback_artifact is not None
                generation_key = "c" * 64
                artifact_identity = "d" * 64
                now = datetime(2026, 8, 29, 3, tzinfo=timezone.utc)
                narrative_job = CompanyCardNarrativeJob(
                    report_id=report_id,
                    snapshot_hash=source_pin.snapshot_hash,
                    generation_key=generation_key,
                    identity_version="GenerationIdentityV2",
                    generation_identity={"test": "artifact"},
                    state="finalized",
                    available_at=now,
                    gateway_dispatch_id=uuid4(),
                    dispatch_started_at=now,
                    response_received_at=now,
                    resolved_model_version="test-model",
                    validation_codes=[],
                )
                session.add(narrative_job)
                await session.flush()
                artifact = CompanyCardNarrativeArtifact(
                    report_id=report_id,
                    snapshot_hash=source_pin.snapshot_hash,
                    generation_key=generation_key,
                    binding_kind="artifact",
                    binding_key=artifact_identity,
                    artifact_identity=artifact_identity,
                    fallback_identity=None,
                    resolved_model_version="test-model",
                    raw_model_output="{}",
                    validated_render_plan_cjson=b"{}",
                    validated_render_plan_bytes_sha256="e" * 64,
                    rendered_description=fallback_artifact.rendered_description,
                    rendered_comments=[],
                    statement_ids=fallback_artifact.statement_ids,
                    evidence_ids=fallback_artifact.evidence_ids,
                    phrase_trace=fallback_artifact.phrase_trace,
                    validation_codes=[],
                    renderer_version="test-artifact-renderer",
                    rendered_output_bytes_sha256="f" * 64,
                )
                session.add(artifact)
                await session.flush()
                narrative_job.artifact_id = artifact.id
                source_pin.narrative_binding_kind = "artifact"
                source_pin.narrative_binding_key = artifact_identity
            else:
                source_pin = await session.scalar(
                    select(CompanyReportPresentationPin).where(
                        CompanyReportPresentationPin.subject_id == subject_id,
                        CompanyReportPresentationPin.presentation_contract
                        == "company_public_h2_v1",
                        CompanyReportPresentationPin.projection_scope
                        == "staged_publication",
                        CompanyReportPresentationPin.narrative_binding_status
                        == "resolved",
                    )
                )
                assert source_pin is not None
                source_pin.projection_digest = (
                    "0" * 64
                    if source_pin.projection_digest != "0" * 64
                    else "1" * 64
                )

    if mutation == "projection_digest":
        with pytest.raises(CanaryExecutionError, match="canary_h2_invalid"):
            await status_canary(plan=plan, receipt=receipt, config=config)
    else:
        status = await status_canary(
            plan=plan, receipt=receipt, config=config
        )
    if mutation == "partial":
        assert status["lifecycle"] == "ready"
        assert status["report_status"] == "partial"
    elif mutation == "artifact":
        assert status["lifecycle"] == "finalized_unresolved"
        assert status["staged_resolved"] is False

    output_dir = (tmp_path / f"rejected-{mutation}").resolve()
    output_dir.mkdir()
    os.chmod(output_dir, 0o700)
    expected_error = (
        "canary_h2_invalid"
        if mutation == "projection_digest"
        else "canary_not_ready"
    )
    with pytest.raises(CanaryExecutionError, match=expected_error):
        await build_canary_decisions(
            plan=plan,
            receipt=receipt,
            config=config,
            authorization_reference="production-recovery",
            abort_policy_reference="production-recovery-abort",
            observation_window_seconds=60,
            h2_indexable=True,
            activate_decision_id="25000000-0000-4000-8000-000000000931",
            rollback_decision_id="25000000-0000-4000-8000-000000000932",
            output_dir=output_dir,
        )
    assert list(output_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_canary_decisions_drive_h1_to_h2_to_h1(
    engine,
    db_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile, subject_id, _report_id, config, plan, receipt = (
        await _seed_ready_receipt(
            engine,
            db_url,
            tmp_path,
            monkeypatch,
            assign_h1=False,
        )
    )
    assert plan.expected_assignment.generation == 0
    assert (
        await status_canary(plan=plan, receipt=receipt, config=config)
    )["lifecycle"] == "ready"

    output_dir = (tmp_path / "decisions").resolve()
    output_dir.mkdir()
    os.chmod(output_dir, 0o700)
    built = await build_canary_decisions(
        plan=plan,
        receipt=receipt,
        config=config,
        authorization_reference="P3-production-recovery",
        abort_policy_reference="P4-production-recovery",
        observation_window_seconds=60,
        h2_indexable=True,
        activate_decision_id="25000000-0000-4000-8000-000000000901",
        rollback_decision_id="25000000-0000-4000-8000-000000000902",
        output_dir=output_dir,
    )
    activation = load_rollout_decision(
        output_dir / "company-card-v2-canary-activate.json"
    )
    rollback = load_rollout_decision(
        output_dir / "company-card-v2-canary-rollback.json"
    )
    assert built["activate_decision_digest"] == activation.decision_digest
    assert built["rollback_decision_digest"] == rollback.decision_digest
    rollout_config = RolloutRuntimeConfig(
        database_url=db_url,
        product_release_commit=RELEASE_SHA,
        rollout_generation=1,
        allowlist_inns=(profile["inn"],),
        percentage_basis_points=0,
    )
    applied = await run_rollout_mutation(
        activation,
        rollout_config,
        mode="apply",
        confirm_digest=activation.decision_digest,
    )
    assert [item.code for item in applied.results] == ["applied"]
    async with AsyncSession(bind=engine) as session:
        assignment = await session.scalar(
            select(CompanyReportPresentationAssignment).where(
                CompanyReportPresentationAssignment.subject_id == subject_id
            )
        )
        assert assignment is not None
        assert assignment.presentation_contract == "company_public_h2_v1"
        assert assignment.generation == 1

    rolled_back = await run_rollout_mutation(
        rollback,
        rollout_config,
        mode="rollback",
        confirm_digest=rollback.decision_digest,
    )
    assert [item.code for item in rolled_back.results] == ["applied"]
    async with AsyncSession(bind=engine) as session:
        assignment = await session.scalar(
            select(CompanyReportPresentationAssignment).where(
                CompanyReportPresentationAssignment.subject_id == subject_id
            )
        )
        assert assignment is not None
        assert assignment.presentation_contract == "company_public_h1_v1"
        assert assignment.generation == 2
        journal = list(
            (
                await session.scalars(
                    select(CompanyReportPresentationAssignmentJournal)
                    .where(
                        CompanyReportPresentationAssignmentJournal.subject_id
                        == subject_id
                    )
                    .order_by(
                        CompanyReportPresentationAssignmentJournal.generation
                    )
                )
            ).all()
        )
        assert [item.generation for item in journal] == [1, 2]
        assert all(item.decision_id is not None for item in journal)


@pytest.mark.asyncio
async def test_canary_decision_does_not_reuse_wrong_projection_active_pin(
    engine,
    db_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile, subject_id, _report_id, config, plan, receipt = (
        await _seed_ready_receipt(
            engine,
            db_url,
            tmp_path,
            monkeypatch,
            assign_h1=True,
        )
    )

    first_dir = (tmp_path / "first-decisions").resolve()
    first_dir.mkdir()
    os.chmod(first_dir, 0o700)
    await build_canary_decisions(
        plan=plan,
        receipt=receipt,
        config=config,
        authorization_reference="P3-production-recovery",
        abort_policy_reference="P4-production-recovery",
        observation_window_seconds=60,
        h2_indexable=True,
        activate_decision_id="25000000-0000-4000-8000-000000000911",
        rollback_decision_id="25000000-0000-4000-8000-000000000912",
        output_dir=first_dir,
    )
    first_activation = load_rollout_decision(
        first_dir / "company-card-v2-canary-activate.json"
    )
    first_target = first_activation.decision.targets[0]

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        async with session.begin():
            head = await session.get(CompanyReportH2LifecycleHead, subject_id)
            assert head is not None
            report = await session.get(CompanyReportRecord, head.report_id)
            source_pin = await session.scalar(
                select(CompanyReportPresentationPin).where(
                    CompanyReportPresentationPin.subject_id == subject_id,
                    CompanyReportPresentationPin.presentation_contract
                    == "company_public_h2_v1",
                    CompanyReportPresentationPin.projection_scope
                    == "staged_publication",
                    CompanyReportPresentationPin.narrative_binding_status
                    == "resolved",
                )
            )
            assert report is not None and source_pin is not None
            wrong_digest = (
                "0" * 64
                if first_target.expected_active_projection_digest != "0" * 64
                else "1" * 64
            )
            session.add(
                CompanyReportPresentationPin(
                    subject_id=subject_id,
                    report_id=report.id,
                    presentation_contract="company_public_h2_v1",
                    generation=first_target.expected_active_h2_pin_generation,
                    snapshot_hash=source_pin.snapshot_hash,
                    chart_facts_version=source_pin.chart_facts_version,
                    chart_facts_hash=source_pin.chart_facts_hash,
                    evidence_registry_version=source_pin.evidence_registry_version,
                    publication_policy_version=source_pin.publication_policy_version,
                    projection_scope="active_publication",
                    canonical_path=f"/company/{profile['inn']}-company",
                    indexable=True,
                    published_lastmod=report.generated_at,
                    projection_digest=wrong_digest,
                    narrative_binding_status="resolved",
                    narrative_binding_kind=source_pin.narrative_binding_kind,
                    narrative_binding_key=source_pin.narrative_binding_key,
                )
            )

    second_dir = (tmp_path / "second-decisions").resolve()
    second_dir.mkdir()
    os.chmod(second_dir, 0o700)
    await build_canary_decisions(
        plan=plan,
        receipt=receipt,
        config=config,
        authorization_reference="P3-production-recovery",
        abort_policy_reference="P4-production-recovery",
        observation_window_seconds=60,
        h2_indexable=True,
        activate_decision_id="25000000-0000-4000-8000-000000000913",
        rollback_decision_id="25000000-0000-4000-8000-000000000914",
        output_dir=second_dir,
    )
    second_activation = load_rollout_decision(
        second_dir / "company-card-v2-canary-activate.json"
    )
    second_target = second_activation.decision.targets[0]
    assert (
        second_target.expected_active_h2_pin_generation
        == first_target.expected_active_h2_pin_generation + 1
    )
