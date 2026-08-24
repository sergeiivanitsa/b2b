from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.schemas import ChatResponse

from product_api.company_reports.company_card_v2.narrative.catalog import (
    CONNECTOR_IDS,
    FALLBACK_CATALOG_VERSION,
    FALLBACK_DESCRIPTION,
    FALLBACK_PROFILE_ID,
    FALLBACK_RENDERER_VERSION,
    INTRO_TEMPLATE_ID,
    MODEL_PROFILE,
    OUTPUT_SCHEMA_VERSION,
    STATEMENT_IDS,
)
from product_api.company_reports.company_card_v2.narrative.worker import run_once
from product_api.company_reports.company_card_v2.narrative.identity import (
    FallbackIdentityV1,
    identity_key,
)
from product_api.company_reports.company_card_v2.narrative.service import (
    NarrativeLimits,
    claim_narrative_reconciliation,
    prepare_narrative_dispatch,
    reconcile_claimed_narrative_outbox,
    requeue_pre_dispatch_failure,
)
from product_api.company_reports.persistence.models import (
    CompanyCardNarrativeArtifact,
    CompanyCardNarrativeBudgetReservation,
    CompanyCardNarrativeBudgetWindow,
    CompanyCardNarrativeJob,
    CompanyCardNarrativeOutbox,
    CompanyReportPresentationAssignment,
    CompanyReportPresentationPin,
    CompanyReportPresentationStagedPointer,
    CompanyReportRecord,
    CompanyReportSubject,
)
from product_api.company_reports.persistence.narratives import (
    NarrativePersistenceError,
    claim_narrative_job,
    insert_narrative_outbox,
    job_lease,
    mark_dispatching,
    narrative_budget_windows,
    release_pre_dispatch_reservation,
    synchronize_narrative_runtime_control,
)
from product_api.company_reports.persistence.v3 import (
    calculate_company_card_v2_snapshot_hash,
    company_card_v2_from_snapshot,
)
from product_api.company_reports.persistence.serialization import (
    calculate_company_report_snapshot_hash,
)
from product_api.settings import get_settings


pytestmark = pytest.mark.asyncio
_NOW = datetime(2026, 8, 24, 12, tzinfo=UTC)
_FIXTURE = (
    Path(__file__).parents[1]
    / "tests_unit"
    / "fixtures"
    / "company_card_v2"
    / "snapshot_v3_complete.json"
)
_LEGACY_FIXTURE = (
    Path(__file__).parents[1]
    / "tests_unit"
    / "fixtures"
    / "company_reports"
    / "snapshot_v1_legacy.json"
)


def _open_settings(*, limit: int = 10):
    return get_settings().model_copy(
        update={
            "company_card_v2_narrative_enabled": True,
            "company_card_v2_narrative_kill_switch": False,
            "company_card_v2_narrative_daily_limit": limit,
            "company_card_v2_narrative_monthly_limit": limit,
            "company_card_v2_narrative_concurrency": 1,
        }
    )


def _valid_gateway_text() -> str:
    return json.dumps(
        {
            "output_schema_version": OUTPUT_SCHEMA_VERSION,
            "description_plan": {
                "intro_template_id": INTRO_TEMPLATE_ID,
                "statement_ids": list(STATEMENT_IDS),
                "connector_ids": list(CONNECTOR_IDS),
            },
            "chart_comments": [],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


async def _create_v2_report(
    session: AsyncSession,
    *,
    activity: bool = True,
) -> tuple[CompanyReportRecord, dict[str, object], str]:
    report_id = uuid4()
    snapshot = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    snapshot["report_id"] = str(report_id)
    snapshot["snapshot_schema_version"] = "company_card_v2_snapshot_v2"
    snapshot["narrative_evidence"] = {
        "schema_version": "company_card_v2_narrative_evidence_v1",
        "primary_activity_parser_version": "company_card_v2_primary_activity_parser_v1",
        "primary_activity_evidence_version": "company_card_v2_okved_primary_activity_evidence_v1",
        "source_profile_version": "company_card_v2_counterparty_okved_primary_v1",
        "primary_activity": (
            {"code": "62.01", "label": "Разработка компьютерного программного обеспечения", "is_primary": True}
            if activity
            else None
        ),
        "limitation_code": None if activity else "primary_activity_not_admitted",
    }
    parsed = company_card_v2_from_snapshot(snapshot)
    snapshot_hash = calculate_company_card_v2_snapshot_hash(parsed)
    subject = CompanyReportSubject(
        normalized_identifier="7701234567",
        identifier_type="legal_entity_inn",
    )
    session.add(subject)
    await session.flush()
    report = CompanyReportRecord(
        id=report_id,
        subject_id=subject.id,
        report_version="3",
        writer_profile="company_card_v2_writer_v3",
        presentation_contract="company_public_h2_v1",
        rollout_generation=1,
        lifecycle_status="complete",
        started_at=_NOW,
        generated_at=_NOW,
        finished_at=_NOW,
        normalized_snapshot=snapshot,
        snapshot_hash=snapshot_hash,
        warnings_snapshot=[],
        usable_for_public_page=False,
        usable_for_future_scoring=False,
    )
    session.add(report)
    await session.flush()
    await insert_narrative_outbox(
        session,
        report_id=report.id,
        snapshot_hash=snapshot_hash,
        now=_NOW,
    )
    return report, deepcopy(snapshot), snapshot_hash


async def _create_legacy_report(
    session: AsyncSession,
) -> tuple[CompanyReportRecord, dict[str, object], str]:
    report_id = uuid4()
    snapshot = json.loads(_LEGACY_FIXTURE.read_text(encoding="utf-8"))
    snapshot["report_id"] = str(report_id)
    snapshot_hash = calculate_company_report_snapshot_hash(snapshot)
    subject = CompanyReportSubject(
        normalized_identifier="0000000000",
        identifier_type="legal_entity_inn",
    )
    session.add(subject)
    await session.flush()
    report = CompanyReportRecord(
        id=report_id,
        subject_id=subject.id,
        report_version="1",
        writer_profile="h1_legacy_writer_v2",
        presentation_contract="company_public_h1_v1",
        rollout_generation=0,
        lifecycle_status="partial",
        started_at=_NOW,
        generated_at=_NOW,
        finished_at=_NOW,
        normalized_snapshot=snapshot,
        snapshot_hash=snapshot_hash,
        warnings_snapshot=[],
        usable_for_public_page=True,
        usable_for_future_scoring=False,
    )
    session.add(report)
    await session.flush()
    await insert_narrative_outbox(
        session,
        report_id=report.id,
        snapshot_hash=snapshot_hash,
        now=_NOW,
    )
    return report, deepcopy(snapshot), snapshot_hash


async def test_public_h2_read_modules_do_not_import_write_side_narrative_worker():
    root = Path(__file__).parents[1] / "src" / "product_api" / "company_reports" / "company_card_v2"
    public_sources = "\n".join((root / name).read_text(encoding="utf-8") for name in ("service.py", "public_h2.py", "public_h2_ssr_adapter.py"))
    assert "narrative.worker" not in public_sources
    assert "narrative_outbox" not in public_sources


async def test_worker_commits_one_dispatch_then_finalizes_exact_artifact_and_pin(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        async with session.begin():
            report, original_snapshot, original_hash = await _create_v2_report(session)
            report_id = report.id

    calls = []

    async def gateway(_settings, request):
        calls.append(request.gateway_dispatch_id)
        facts = json.loads(request.messages[0].content)
        assert facts["evidence_registry_version"] == original_snapshot["evidence_version"]
        assert not {
            "report_id",
            "snapshot_hash",
            "chart_facts_hash",
            "primary_activity_code",
        }.intersection(facts)
        async with session_factory() as observer:
            job = await observer.scalar(
                select(CompanyCardNarrativeJob).where(
                    CompanyCardNarrativeJob.report_id == report_id
                )
            )
            reservation = await observer.get(
                CompanyCardNarrativeBudgetReservation,
                job.generation_key,
            )
            assert job.state == "dispatching"
            assert job.gateway_dispatch_id == request.gateway_dispatch_id
            assert reservation is not None and reservation.state == "consumed"
        return ChatResponse(
            text=_valid_gateway_text(),
            model_profile=MODEL_PROFILE,
            resolved_model="narrative-test-model-v1",
            gateway_dispatch_id=request.gateway_dispatch_id,
        )

    await run_once(
        settings=_open_settings(),
        session_factory=session_factory,
        gateway_sender=gateway,
        clock=lambda: _NOW,
    )
    await run_once(
        settings=_open_settings(),
        session_factory=session_factory,
        gateway_sender=gateway,
        clock=lambda: _NOW,
    )

    assert len(calls) == 1
    async with session_factory() as session:
        report = await session.get(CompanyReportRecord, report_id)
        job = await session.scalar(
            select(CompanyCardNarrativeJob).where(
                CompanyCardNarrativeJob.report_id == report_id
            )
        )
        artifact = await session.get(CompanyCardNarrativeArtifact, job.artifact_id)
        pin = await session.scalar(
            select(CompanyReportPresentationPin).where(
                CompanyReportPresentationPin.report_id == report_id,
                CompanyReportPresentationPin.narrative_binding_status == "resolved",
            )
        )
        pointer = await session.scalar(select(CompanyReportPresentationStagedPointer))
        assert report.normalized_snapshot == original_snapshot
        assert report.snapshot_hash == original_hash
        assert job.state == "finalized"
        assert artifact is not None and artifact.binding_kind == "artifact"
        assert artifact.rendered_comments == []
        assert artifact.validation_codes == []
        assert artifact.raw_model_output == _valid_gateway_text()
        assert artifact.rendered_output_bytes_sha256 == __import__("hashlib").sha256(
            artifact.rendered_description.encode("utf-8")
        ).hexdigest()
        assert [item["statement_id"] for item in artifact.phrase_trace] == artifact.statement_ids
        assert artifact.phrase_trace[0]["scalar_start"] == 0
        assert artifact.phrase_trace[-1]["scalar_end"] == len(artifact.rendered_description)
        assert pin is not None and pin.narrative_binding_key == artifact.binding_key
        assert pin.indexable is False and pin.projection_digest is not None
        assert pointer is not None and pointer.generation == pin.generation
        assert await session.scalar(
            select(func.count(CompanyReportPresentationAssignment.id))
        ) == 0


@pytest.mark.parametrize(
    ("mode", "expected_code"),
    [
        ("timeout", "ambiguous_timeout"),
        ("dispatch_mismatch", "gateway_dispatch_id_mismatch"),
    ],
)
async def test_post_marker_failure_saves_fallback_without_retry(engine, mode, expected_code):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        async with session.begin():
            report, original_snapshot, original_hash = await _create_v2_report(session)
            report_id = report.id
    calls = 0

    async def gateway(_settings, request):
        nonlocal calls
        calls += 1
        if mode == "timeout":
            raise TimeoutError("synthetic timeout")
        return ChatResponse(
            text=_valid_gateway_text(),
            model_profile=MODEL_PROFILE,
            resolved_model="narrative-test-model-v1",
            gateway_dispatch_id=uuid4(),
        )

    for _ in range(2):
        await run_once(
            settings=_open_settings(),
            session_factory=session_factory,
            gateway_sender=gateway,
            clock=lambda: _NOW,
        )
    assert calls == 1
    async with session_factory() as session:
        report = await session.get(CompanyReportRecord, report_id)
        job = await session.scalar(
            select(CompanyCardNarrativeJob).where(
                CompanyCardNarrativeJob.report_id == report_id
            )
        )
        artifact = await session.get(CompanyCardNarrativeArtifact, job.artifact_id)
        reservation = await session.get(
            CompanyCardNarrativeBudgetReservation,
            job.generation_key,
        )
        assert report.normalized_snapshot == original_snapshot
        assert report.snapshot_hash == original_hash
        assert job.state == "fallback_finalized"
        assert job.validation_codes == [expected_code]
        assert artifact.binding_kind == "fallback"
        assert artifact.rendered_description == FALLBACK_DESCRIPTION
        assert artifact.statement_ids == [FALLBACK_PROFILE_ID]
        assert artifact.evidence_ids == [] and artifact.validation_codes == []
        assert reservation.state == "consumed"


async def test_missing_activity_and_closed_runtime_materialize_saved_fallback_without_gateway(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        async with session.begin():
            report, original_snapshot, original_hash = await _create_v2_report(
                session,
                activity=False,
            )
            report_id = report.id

    async def forbidden_gateway(*_args):
        raise AssertionError("closed/missing-activity reconciliation cannot call Gateway")

    await run_once(
        settings=get_settings(),
        session_factory=session_factory,
        gateway_sender=forbidden_gateway,
        clock=lambda: _NOW,
    )
    async with session_factory() as session:
        report = await session.get(CompanyReportRecord, report_id)
        outbox = await session.scalar(select(CompanyCardNarrativeOutbox))
        job = await session.scalar(select(CompanyCardNarrativeJob))
        artifact = await session.get(CompanyCardNarrativeArtifact, job.artifact_id)
        assert report.normalized_snapshot == original_snapshot
        assert report.snapshot_hash == original_hash
        assert outbox.state == "processed" and outbox.generation_key == job.generation_key
        assert job.state == "fallback_finalized"
        assert job.validation_codes == ["primary_activity_unavailable"]
        assert artifact.binding_kind == "fallback"
        assert artifact.rendered_description == FALLBACK_DESCRIPTION


@pytest.mark.parametrize(
    ("limits", "expected_code"),
    [
        (NarrativeLimits(enabled=False, kill_switch=True), "feature_disabled"),
        (
            NarrativeLimits(
                enabled=True,
                kill_switch=True,
                daily_limit=1,
                monthly_limit=1,
                concurrency=1,
            ),
            "kill_switch_enabled",
        ),
    ],
)
async def test_disabled_or_kill_switched_reconciler_saves_fallback(engine, limits, expected_code):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        async with session.begin():
            report, _snapshot, _snapshot_hash = await _create_v2_report(session)
            report_id = report.id
    async with session_factory() as session:
        async with session.begin():
            lease = await claim_narrative_reconciliation(session, now=_NOW)
    async with session_factory() as session:
        async with session.begin():
            await reconcile_claimed_narrative_outbox(
                session,
                lease=lease,
                now=_NOW,
                limits=limits,
            )
    async with session_factory() as session:
        job = await session.scalar(
            select(CompanyCardNarrativeJob).where(
                CompanyCardNarrativeJob.report_id == report_id
            )
        )
        artifact = await session.get(CompanyCardNarrativeArtifact, job.artifact_id)
        assert job.state == "fallback_finalized"
        assert job.validation_codes == [expected_code]
        assert artifact.binding_kind == "fallback"


async def test_legacy_report_gets_exact_saved_fallback_and_never_h2_pin(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        async with session.begin():
            report, original_snapshot, original_hash = await _create_legacy_report(session)
            report_id = report.id

    async def forbidden_gateway(*_args):
        raise AssertionError("legacy report reconciliation cannot call Gateway")

    await run_once(
        settings=get_settings(),
        session_factory=session_factory,
        gateway_sender=forbidden_gateway,
        clock=lambda: _NOW,
    )
    async with session_factory() as session:
        report = await session.get(CompanyReportRecord, report_id)
        job = await session.scalar(select(CompanyCardNarrativeJob))
        artifact = await session.get(CompanyCardNarrativeArtifact, job.artifact_id)
        rendered_hash = __import__("hashlib").sha256(FALLBACK_DESCRIPTION.encode("utf-8")).hexdigest()
        expected_identity = identity_key(
            FallbackIdentityV1(
                generation_key=job.generation_key,
                fallback_catalog_version=FALLBACK_CATALOG_VERSION,
                fallback_profile_id=FALLBACK_PROFILE_ID,
                renderer_version=FALLBACK_RENDERER_VERSION,
                rendered_output_bytes_sha256=rendered_hash,
            )
        )
        assert report.normalized_snapshot == original_snapshot
        assert report.snapshot_hash == original_hash
        assert job.state == "fallback_finalized"
        assert artifact.binding_key == artifact.fallback_identity == expected_identity
        assert artifact.phrase_trace == [{
            "scalar_start": 0,
            "scalar_end": 691,
            "statement_id": FALLBACK_PROFILE_ID,
            "evidence_ids": [],
        }]
        assert await session.scalar(
            select(func.count(CompanyReportPresentationPin.generation))
        ) == 0
        assert await session.scalar(
            select(func.count(CompanyReportPresentationStagedPointer.id))
        ) == 0


async def test_exhausted_budget_saves_fallback_without_gateway(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    daily, monthly = narrative_budget_windows(_NOW)
    async with session_factory() as session:
        async with session.begin():
            report, _snapshot, _snapshot_hash = await _create_v2_report(session)
            report_id = report.id
            for kind, values in (("daily", daily), ("monthly", monthly)):
                _label, starts_at, ends_at = values
                session.add(
                    CompanyCardNarrativeBudgetWindow(
                        period_kind=kind,
                        period_start_local=starts_at.astimezone(ZoneInfo("Europe/Moscow")).date(),
                        starts_at_utc=starts_at,
                        ends_at_utc=ends_at,
                        reserved_count=0,
                        consumed_count=1,
                    )
                )

    async def forbidden_gateway(*_args):
        raise AssertionError("exhausted budget cannot call Gateway")

    await run_once(
        settings=_open_settings(limit=1),
        session_factory=session_factory,
        gateway_sender=forbidden_gateway,
        clock=lambda: _NOW,
    )
    async with session_factory() as session:
        job = await session.scalar(
            select(CompanyCardNarrativeJob).where(
                CompanyCardNarrativeJob.report_id == report_id
            )
        )
        artifact = await session.get(CompanyCardNarrativeArtifact, job.artifact_id)
        assert job.state == "fallback_finalized"
        assert job.validation_codes == ["daily_budget_exhausted"]
        assert artifact.binding_kind == "fallback"


async def test_expired_dispatching_job_is_fallback_finalized_without_gateway_replay(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = _open_settings()
    limits = NarrativeLimits(
        enabled=True,
        kill_switch=False,
        daily_limit=10,
        monthly_limit=10,
        concurrency=1,
    )
    async with session_factory() as session:
        async with session.begin():
            report, _snapshot, _snapshot_hash = await _create_v2_report(session)
            report_id = report.id
            await synchronize_narrative_runtime_control(
                session,
                enabled=True,
                kill_switch=False,
                daily_limit=10,
                monthly_limit=10,
                concurrency_limit=1,
                now=_NOW,
            )
    async with session_factory() as session:
        async with session.begin():
            outbox_lease = await claim_narrative_reconciliation(session, now=_NOW)
    async with session_factory() as session:
        async with session.begin():
            await reconcile_claimed_narrative_outbox(
                session,
                lease=outbox_lease,
                now=_NOW,
                limits=limits,
            )
    async with session_factory() as session:
        async with session.begin():
            claimed = await claim_narrative_job(session, now=_NOW, lease_seconds=30)
            lease = job_lease(claimed)
    dispatch_id = uuid4()
    async with session_factory() as session:
        async with session.begin():
            await prepare_narrative_dispatch(
                session,
                lease=lease,
                dispatch_id=dispatch_id,
                now=_NOW,
                timeout_seconds=20,
                max_output_tokens=600,
            )
            await mark_dispatching(
                session,
                lease=lease,
                dispatch_id=dispatch_id,
                now=_NOW,
            )

    calls = 0

    async def forbidden_gateway(*_args):
        nonlocal calls
        calls += 1
        raise AssertionError("expired marked dispatch must never be replayed")

    await run_once(
        settings=settings,
        session_factory=session_factory,
        gateway_sender=forbidden_gateway,
        clock=lambda: _NOW + timedelta(seconds=31),
    )
    assert calls == 0
    async with session_factory() as session:
        job = await session.scalar(
            select(CompanyCardNarrativeJob).where(
                CompanyCardNarrativeJob.report_id == report_id
            )
        )
        artifact = await session.get(CompanyCardNarrativeArtifact, job.artifact_id)
        assert job.state == "fallback_finalized"
        assert job.gateway_dispatch_id == dispatch_id
        assert job.fence_generation == lease.fence_generation + 1
        assert job.validation_codes == ["ambiguous_worker_death"]
        assert artifact.binding_kind == "fallback"


@pytest.mark.parametrize("corruption", ["changed_value", "extra_key"])
async def test_dispatch_rejects_corrupt_durable_generation_identity(
    engine,
    corruption,
):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    limits = NarrativeLimits(
        enabled=True,
        kill_switch=False,
        daily_limit=10,
        monthly_limit=10,
        concurrency=1,
    )
    async with session_factory() as session:
        async with session.begin():
            await _create_v2_report(session)
            await synchronize_narrative_runtime_control(
                session,
                enabled=True,
                kill_switch=False,
                daily_limit=10,
                monthly_limit=10,
                concurrency_limit=1,
                now=_NOW,
            )
    async with session_factory() as session:
        async with session.begin():
            outbox_lease = await claim_narrative_reconciliation(session, now=_NOW)
    async with session_factory() as session:
        async with session.begin():
            await reconcile_claimed_narrative_outbox(
                session,
                lease=outbox_lease,
                now=_NOW,
                limits=limits,
            )
            job = await session.scalar(select(CompanyCardNarrativeJob))
            assert job is not None
            assert job.generation_identity["identity_version"] == "GenerationIdentityV2"
            corrupted_identity = dict(job.generation_identity)
            if corruption == "changed_value":
                corrupted_identity["prompt_version"] = "corrupt_prompt_v1"
            else:
                corrupted_identity["unexpected_binding"] = "must_be_rejected_v1"
            job.generation_identity = corrupted_identity
    async with session_factory() as session:
        async with session.begin():
            claimed = await claim_narrative_job(
                session,
                now=_NOW,
                lease_seconds=30,
            )
            assert claimed is not None
            lease = job_lease(claimed)
    async with session_factory() as session:
        async with session.begin():
            with pytest.raises(
                NarrativePersistenceError,
                match="narrative dispatch generation changed",
            ):
                await prepare_narrative_dispatch(
                    session,
                    lease=lease,
                    dispatch_id=uuid4(),
                    now=_NOW,
                    timeout_seconds=20,
                    max_output_tokens=600,
                )


async def test_third_pre_dispatch_local_failure_finalizes_fallback_without_gateway(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = _open_settings()
    limits = NarrativeLimits(
        enabled=True,
        kill_switch=False,
        daily_limit=10,
        monthly_limit=10,
        concurrency=1,
    )
    async with session_factory() as session:
        async with session.begin():
            report, _snapshot, _snapshot_hash = await _create_v2_report(session)
            report_id = report.id
            await synchronize_narrative_runtime_control(
                session,
                enabled=True,
                kill_switch=False,
                daily_limit=10,
                monthly_limit=10,
                concurrency_limit=1,
                now=_NOW,
            )
    async with session_factory() as session:
        async with session.begin():
            outbox_lease = await claim_narrative_reconciliation(session, now=_NOW)
    async with session_factory() as session:
        async with session.begin():
            await reconcile_claimed_narrative_outbox(
                session,
                lease=outbox_lease,
                now=_NOW,
                limits=limits,
            )

    for attempt in range(3):
        async with session_factory() as session:
            async with session.begin():
                claimed = await claim_narrative_job(session, now=_NOW, lease_seconds=30)
                lease = job_lease(claimed)
        async with session_factory() as session:
            async with session.begin():
                await release_pre_dispatch_reservation(
                    session,
                    lease=lease,
                    failure_code="local_request_build_failed",
                    now=_NOW,
                )
        if attempt < 2:
            async with session_factory() as session:
                async with session.begin():
                    assert await requeue_pre_dispatch_failure(session, now=_NOW) == 1

    calls = 0

    async def forbidden_gateway(*_args):
        nonlocal calls
        calls += 1
        raise AssertionError("exhausted local attempts cannot call Gateway")

    await run_once(
        settings=settings,
        session_factory=session_factory,
        gateway_sender=forbidden_gateway,
        clock=lambda: _NOW,
    )
    assert calls == 0
    async with session_factory() as session:
        job = await session.scalar(
            select(CompanyCardNarrativeJob).where(
                CompanyCardNarrativeJob.report_id == report_id
            )
        )
        artifact = await session.get(CompanyCardNarrativeArtifact, job.artifact_id)
        reservation = await session.get(
            CompanyCardNarrativeBudgetReservation,
            job.generation_key,
        )
        assert job.state == "fallback_finalized"
        assert job.local_attempt_count == 3
        assert job.validation_codes == ["local_attempts_exhausted"]
        assert reservation.state == "released" and reservation.reservation_epoch == 3
        assert artifact.binding_kind == "fallback"


async def test_corrupt_snapshot_never_dispatches_and_closes_without_public_binding(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = _open_settings()
    limits = NarrativeLimits(
        enabled=True,
        kill_switch=False,
        daily_limit=10,
        monthly_limit=10,
        concurrency=1,
    )
    async with session_factory() as session:
        async with session.begin():
            report, _snapshot, _snapshot_hash = await _create_v2_report(session)
            report_id = report.id
            await synchronize_narrative_runtime_control(
                session,
                enabled=True,
                kill_switch=False,
                daily_limit=10,
                monthly_limit=10,
                concurrency_limit=1,
                now=_NOW,
            )
    async with session_factory() as session:
        async with session.begin():
            outbox_lease = await claim_narrative_reconciliation(session, now=_NOW)
    async with session_factory() as session:
        async with session.begin():
            await reconcile_claimed_narrative_outbox(
                session,
                lease=outbox_lease,
                now=_NOW,
                limits=limits,
            )
    async with session_factory() as session:
        async with session.begin():
            report = await session.get(CompanyReportRecord, report_id, with_for_update=True)
            corrupt = deepcopy(report.normalized_snapshot)
            corrupt["privacy_version"] = "corrupt-after-initialization"
            report.normalized_snapshot = corrupt

    calls = 0

    async def forbidden_gateway(*_args):
        nonlocal calls
        calls += 1
        raise AssertionError("corrupt snapshot cannot call Gateway")

    for _ in range(4):
        await run_once(
            settings=settings,
            session_factory=session_factory,
            gateway_sender=forbidden_gateway,
            clock=lambda: _NOW,
        )
    assert calls == 0
    async with session_factory() as session:
        job = await session.scalar(
            select(CompanyCardNarrativeJob).where(
                CompanyCardNarrativeJob.report_id == report_id
            )
        )
        assert job.state == "fallback_finalized"
        assert job.artifact_id is None
        assert job.validation_codes == ["invalid_report_snapshot"]
        assert await session.scalar(
            select(func.count(CompanyReportPresentationPin.generation))
        ) == 0
