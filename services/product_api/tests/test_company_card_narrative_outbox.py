from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.company_reports.company_card_v2.finance import build_chart_facts
from product_api.company_reports.company_card_v2.models import (
    ArbitrationBasisV1,
    CompanyCardCounterpartyCoreV1,
    CompanyCardV2SnapshotV2,
    FinanceBasisV1,
    NarrativeEvidenceV1,
)
from product_api.company_reports.persistence import (
    WriterDecision,
    claim_next_job,
    complete_claimed_company_card_v2_job,
    enqueue_company_report_job,
)
from product_api.company_reports.persistence.models import (
    CompanyCardNarrativeJob,
    CompanyCardNarrativeOutbox,
    CompanyReportJob,
    CompanyReportRecord,
    CompanyReportSubject,
)
from product_api.company_reports.persistence.narrative_outbox import (
    NarrativeOutboxOwnershipError,
    claim_narrative_outbox,
    heartbeat_narrative_outbox,
    mark_narrative_outbox_processed,
    outbox_lease,
)
from product_api.company_reports.persistence.narratives import insert_narrative_outbox


pytestmark = pytest.mark.asyncio


def _v2_snapshot(claimed) -> CompanyCardV2SnapshotV2:
    basis = FinanceBasisV1()
    return CompanyCardV2SnapshotV2(
        report_id=str(claimed.report_id),
        subject_inn=claimed.normalized_identifier,
        target_inn=claimed.normalized_identifier,
        generated_at=datetime(2026, 8, 25, tzinfo=UTC),
        rollout_config_generation=claimed.rollout_generation,
        counterparty=CompanyCardCounterpartyCoreV1(
            inn=claimed.normalized_identifier,
            full_name="Тестовое общество",
        ),
        finance_basis=basis,
        arbitration_basis=ArbitrationBasisV1(),
        chart_facts=build_chart_facts(basis),
        evidence_version="evidence_registry_v1",
        privacy_version="privacy_v1",
        narrative_evidence=NarrativeEvidenceV1(
            limitation_code="primary_activity_not_admitted",
        ),
    )


async def _enqueue_and_claim_v2(engine):
    decision = WriterDecision(
        writer_profile="company_card_v2_writer_v3",
        report_version="3",
        presentation_contract="company_public_h2_v1",
        rollout_generation=1,
    )
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        enqueued = await enqueue_company_report_job(
            session,
            "7701234567",
            decision=decision,
        )
        await session.commit()
        claimed = await claim_next_job(session, lease_seconds=60)
        assert claimed is not None
        assert claimed.report_id == enqueued.report_id
        await session.commit()
        return claimed


async def test_v2_completion_atomically_finalizes_partial_report_and_pending_outbox(engine):
    claimed = await _enqueue_and_claim_v2(engine)

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        completed = await complete_claimed_company_card_v2_job(
            session,
            claimed=claimed,
            snapshot=_v2_snapshot(claimed),
            lifecycle_status="partial",
        )
        await session.commit()

    assert completed.lifecycle_status == "partial"
    async with AsyncSession(bind=engine) as session:
        report = await session.get(CompanyReportRecord, claimed.report_id)
        job = await session.get(CompanyReportJob, claimed.job_id)
        outbox = await session.scalar(select(CompanyCardNarrativeOutbox).where(
            CompanyCardNarrativeOutbox.report_id == claimed.report_id,
        ))
        assert report is not None and report.lifecycle_status == "partial"
        assert job is not None and job.state == "succeeded"
        assert outbox is not None
        assert (
            outbox.snapshot_hash,
            outbox.event_kind,
            outbox.state,
            outbox.generation_key,
        ) == (report.snapshot_hash, "initialize_narrative_v1", "pending", None)


async def test_v2_completion_outbox_error_rolls_back_report_and_job(engine, monkeypatch):
    claimed = await _enqueue_and_claim_v2(engine)

    async def failing_outbox(*_args, **_kwargs):
        raise RuntimeError("forced outbox insert failure")

    from product_api.company_reports.persistence import narratives

    monkeypatch.setattr(narratives, "insert_narrative_outbox", failing_outbox)
    async with AsyncSession(bind=engine) as session:
        with pytest.raises(RuntimeError, match="forced outbox insert failure"):
            await complete_claimed_company_card_v2_job(
                session,
                claimed=claimed,
                snapshot=_v2_snapshot(claimed),
            )
        await session.rollback()

    async with AsyncSession(bind=engine) as session:
        report = await session.get(CompanyReportRecord, claimed.report_id)
        job = await session.get(CompanyReportJob, claimed.job_id)
        outbox_count = await session.scalar(select(func.count(
            CompanyCardNarrativeOutbox.id,
        )).where(CompanyCardNarrativeOutbox.report_id == claimed.report_id))
        assert report is not None and report.lifecycle_status == "pending"
        assert job is not None and job.state == "running"
        assert outbox_count == 0


async def test_outbox_is_idempotent_and_claim_transitions_to_a_fenced_lease(engine):
    now, snapshot_hash = datetime(2026, 8, 24, tzinfo=UTC), "1" * 64
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        subject = CompanyReportSubject(normalized_identifier="7701234567", identifier_type="legal_entity_inn")
        session.add(subject); await session.flush()
        report = CompanyReportRecord(subject_id=subject.id, report_version="3", writer_profile="company_card_v2_writer_v3", presentation_contract="company_public_h2_v1", rollout_generation=1, lifecycle_status="complete", started_at=now, generated_at=now, normalized_snapshot={}, snapshot_hash=snapshot_hash, warnings_snapshot=[], usable_for_public_page=False, usable_for_future_scoring=False)
        session.add(report); await session.flush()
        first = await insert_narrative_outbox(session, report_id=report.id, snapshot_hash=snapshot_hash, now=now)
        second = await insert_narrative_outbox(session, report_id=report.id, snapshot_hash=snapshot_hash, now=now)
        assert first.id == second.id
        await session.commit()

    async with AsyncSession(bind=engine) as session:
        claimed = await claim_narrative_outbox(session, now=now)
        assert claimed is not None
        assert claimed.state == "leased"
        assert claimed.lease_token is not None and claimed.lease_expires_at is not None
        assert claimed.fence_generation == 1 and claimed.attempt_count == 1
        assert await session.scalar(select(func.count(CompanyCardNarrativeOutbox.id))) == 1


async def test_expired_outbox_lease_is_refenced_and_stale_heartbeat_is_rejected(engine):
    now, snapshot_hash = datetime(2026, 8, 24, tzinfo=UTC), "2" * 64
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        subject = CompanyReportSubject(normalized_identifier="7701234567", identifier_type="legal_entity_inn")
        session.add(subject)
        await session.flush()
        report = CompanyReportRecord(
            subject_id=subject.id, report_version="3",
            writer_profile="company_card_v2_writer_v3",
            presentation_contract="company_public_h2_v1", rollout_generation=1,
            lifecycle_status="complete", started_at=now, generated_at=now,
            normalized_snapshot={}, snapshot_hash=snapshot_hash,
            warnings_snapshot=[], usable_for_public_page=False,
            usable_for_future_scoring=False,
        )
        session.add(report)
        await session.flush()
        await insert_narrative_outbox(
            session, report_id=report.id, snapshot_hash=snapshot_hash, now=now,
        )
        await session.commit()

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        first = await claim_narrative_outbox(session, now=now, lease_seconds=30)
        stale = outbox_lease(first)
        await session.commit()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        second = await claim_narrative_outbox(
            session, now=now + timedelta(seconds=31), lease_seconds=30,
        )
        winner = outbox_lease(second)
        await session.commit()
    assert winner.lease_token != stale.lease_token
    assert winner.fence_generation == stale.fence_generation + 1
    async with AsyncSession(bind=engine) as session:
        with pytest.raises(NarrativeOutboxOwnershipError, match="stale narrative outbox ownership"):
            await heartbeat_narrative_outbox(
                session,
                lease=stale,
                now=now + timedelta(seconds=31),
            )


async def test_outbox_cannot_be_processed_for_a_bare_job_without_result_or_reservation(engine):
    now, snapshot_hash, generation_key = (
        datetime(2026, 8, 24, tzinfo=UTC),
        "3" * 64,
        "4" * 64,
    )
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        subject = CompanyReportSubject(
            normalized_identifier="7701234567",
            identifier_type="legal_entity_inn",
        )
        session.add(subject)
        await session.flush()
        report = CompanyReportRecord(
            subject_id=subject.id,
            report_version="3",
            writer_profile="company_card_v2_writer_v3",
            presentation_contract="company_public_h2_v1",
            rollout_generation=1,
            lifecycle_status="complete",
            started_at=now,
            generated_at=now,
            normalized_snapshot={},
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
            now=now,
        )
        session.add(
            CompanyCardNarrativeJob(
                report_id=report.id,
                snapshot_hash=snapshot_hash,
                generation_key=generation_key,
                identity_version="GenerationIdentityV2",
                generation_identity={},
                state="ready",
                available_at=now,
            )
        )
        await session.commit()

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claimed = await claim_narrative_outbox(session, now=now)
        lease = outbox_lease(claimed)
        await session.commit()

    async with AsyncSession(bind=engine) as session:
        with pytest.raises(
            NarrativeOutboxOwnershipError,
            match="outbox result is not durable",
        ):
            await mark_narrative_outbox_processed(
                session,
                lease=lease,
                generation_key=generation_key,
                now=now,
            )
