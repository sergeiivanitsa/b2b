from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.company_reports.persistence.models import (
    CompanyCardNarrativeBudgetReservation,
    CompanyCardNarrativeBudgetWindow,
    CompanyCardNarrativeJob,
    CompanyCardNarrativeRuntimeControl,
    CompanyReportRecord,
    CompanyReportSubject,
)
from product_api.company_reports.persistence.narratives import (
    NarrativeBudgetUnavailable,
    NarrativePersistenceError,
    NarrativeStaleOwnership,
    claim_narrative_job,
    heartbeat_narrative_job,
    initialize_narrative_generation,
    job_lease,
    mark_dispatching,
    release_pre_dispatch_reservation,
    reserve_or_rereserve_dispatch_credit,
    synchronize_narrative_runtime_control,
)
from product_api.company_reports.company_card_v2.narrative.identity import (
    GenerationIdentityV2,
    identity_key,
)


pytestmark = pytest.mark.asyncio
_NOW = datetime(2026, 8, 24, 12, tzinfo=UTC)
_HASH = "a" * 64


def _identity(report_id, snapshot_hash=_HASH):
    identity = GenerationIdentityV2(
        report_id=str(report_id), snapshot_hash=snapshot_hash,
        chart_facts_hash="b" * 64, evidence_registry_version="evidence_v1",
        statement_catalog_version="statement_v1", template_catalog_version="template_v1",
        prompt_version="prompt_v1", json_schema_version="schema_v1",
        policy_version="policy_v1", renderer_version="renderer_v1",
        gateway_profile_version="gateway_v1", fallback_catalog_version="fallback_v1",
        snapshot_schema_version="company_card_v2_snapshot_v2",
        narrative_evidence_schema_version="evidence_schema_v1",
        primary_activity_parser_version="parser_v1",
        primary_activity_evidence_version="activity_evidence_v1",
        insight_catalog_version="insight_v1", connector_catalog_version="connector_v1",
        input_schema_version="input_v1",
    )
    return identity, identity_key(identity)


async def _report(
    session: AsyncSession,
    *,
    inn: str = "7701234567",
    snapshot_hash: str = _HASH,
):
    subject = CompanyReportSubject(normalized_identifier=inn, identifier_type="legal_entity_inn")
    session.add(subject)
    await session.flush()
    report = CompanyReportRecord(
        subject_id=subject.id, report_version="3", writer_profile="company_card_v2_writer_v3",
        presentation_contract="company_public_h2_v1", rollout_generation=1, lifecycle_status="complete",
        started_at=_NOW, generated_at=_NOW, normalized_snapshot={"report_version": "3"},
        snapshot_hash=snapshot_hash, warnings_snapshot=[], usable_for_public_page=False,
        usable_for_future_scoring=False,
    )
    session.add(report)
    await session.flush()
    return report


async def _ready_job(
    session: AsyncSession,
    *,
    inn: str,
    snapshot_hash: str,
) -> str:
    report = await _report(session, inn=inn, snapshot_hash=snapshot_hash)
    identity, generation_key = _identity(report.id, snapshot_hash)
    await initialize_narrative_generation(
        session,
        report_id=report.id,
        snapshot_hash=snapshot_hash,
        generation_key=generation_key,
        identity=identity,
        now=_NOW,
    )
    return generation_key


async def test_closed_runtime_control_cannot_claim_ready_narrative_job(engine):
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        report = await _report(session)
        identity, generation_key = _identity(report.id)
        await initialize_narrative_generation(
            session, report_id=report.id, snapshot_hash=_HASH, generation_key=generation_key,
            identity=identity, now=_NOW,
        )
        await session.commit()

    async with AsyncSession(bind=engine) as session:
        assert await claim_narrative_job(session, now=_NOW, lease_seconds=30) is None


async def test_claim_then_dispatch_requires_exact_fenced_ownership(engine):
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        report = await _report(session)
        identity, generation_key = _identity(report.id)
        await initialize_narrative_generation(
            session, report_id=report.id, snapshot_hash=_HASH, generation_key=generation_key,
            identity=identity, now=_NOW,
        )
        control = await session.get(CompanyCardNarrativeRuntimeControl, 1)
        assert control is not None
        control.enabled, control.kill_switch = True, False
        control.daily_limit = control.monthly_limit = control.concurrency_limit = 1
        await reserve_or_rereserve_dispatch_credit(
            session, generation_key=generation_key, now=_NOW,
        )
        await session.commit()

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claimed = await claim_narrative_job(session, now=_NOW, lease_seconds=30)
        assert claimed is not None
        dispatched = await mark_dispatching(
            session, lease=job_lease(claimed),
            dispatch_id=uuid4(), now=_NOW,
        )
        assert dispatched.state == "dispatching"
        assert dispatched.gateway_dispatch_id is not None


async def test_two_local_reschedules_use_three_epochs_and_one_consumed_dispatch(engine):
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        report = await _report(session)
        identity, generation_key = _identity(report.id)
        await initialize_narrative_generation(
            session,
            report_id=report.id,
            snapshot_hash=_HASH,
            generation_key=generation_key,
            identity=identity,
            now=_NOW,
        )
        control = await session.get(CompanyCardNarrativeRuntimeControl, 1)
        control.enabled, control.kill_switch = True, False
        control.daily_limit = control.monthly_limit = 3
        control.concurrency_limit = 1
        await reserve_or_rereserve_dispatch_credit(
            session,
            generation_key=generation_key,
            now=_NOW,
        )
        await session.commit()

    for failure_number in range(2):
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            claimed = await claim_narrative_job(session, now=_NOW, lease_seconds=30)
            assert claimed is not None
            lease = job_lease(claimed)
            await session.commit()
        async with AsyncSession(bind=engine) as session:
            await release_pre_dispatch_reservation(
                session,
                lease=lease,
                failure_code="local_request_build_failed",
                now=_NOW,
            )
            await session.commit()
        async with AsyncSession(bind=engine) as session:
            reservation = await reserve_or_rereserve_dispatch_credit(
                session,
                generation_key=generation_key,
                now=_NOW,
            )
            assert reservation.reservation_epoch == failure_number + 2
            await session.commit()

    dispatch_id = uuid4()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claimed = await claim_narrative_job(session, now=_NOW, lease_seconds=30)
        assert claimed is not None
        await mark_dispatching(
            session,
            lease=job_lease(claimed),
            dispatch_id=dispatch_id,
            now=_NOW,
        )
        await session.commit()

    async with AsyncSession(bind=engine) as session:
        job = await session.scalar(
            select(CompanyCardNarrativeJob).where(
                CompanyCardNarrativeJob.generation_key == generation_key
            )
        )
        reservation = await session.get(
            CompanyCardNarrativeBudgetReservation,
            generation_key,
        )
        windows = (
            await session.scalars(select(CompanyCardNarrativeBudgetWindow))
        ).all()
        assert job.local_attempt_count == 2
        assert job.state == "dispatching" and job.gateway_dispatch_id == dispatch_id
        assert reservation.reservation_epoch == 3 and reservation.state == "consumed"
        assert all(window.reserved_count == 0 for window in windows)
        assert all(window.consumed_count == 1 for window in windows)


async def test_concurrent_claim_has_one_winner_and_stale_fence_cannot_heartbeat(engine):
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        report = await _report(session)
        identity, generation_key = _identity(report.id)
        await initialize_narrative_generation(
            session,
            report_id=report.id,
            snapshot_hash=_HASH,
            generation_key=generation_key,
            identity=identity,
            now=_NOW,
        )
        control = await session.get(CompanyCardNarrativeRuntimeControl, 1)
        control.enabled, control.kill_switch = True, False
        control.daily_limit = control.monthly_limit = 2
        control.concurrency_limit = 1
        await reserve_or_rereserve_dispatch_credit(
            session,
            generation_key=generation_key,
            now=_NOW,
        )
        await session.commit()

    async def contender():
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            async with session.begin():
                row = await claim_narrative_job(session, now=_NOW, lease_seconds=30)
                return None if row is None else job_lease(row)

    leases = await asyncio.gather(contender(), contender())
    winners = [lease for lease in leases if lease is not None]
    assert len(winners) == 1
    stale = replace(winners[0], fence_generation=winners[0].fence_generation + 1)
    async with AsyncSession(bind=engine) as session:
        with pytest.raises(NarrativeStaleOwnership, match="stale narrative job ownership"):
            await heartbeat_narrative_job(
                session,
                lease=stale,
                now=_NOW,
                lease_seconds=30,
            )


async def test_positive_runtime_cap_cannot_drop_below_active_leases_but_zero_closes(engine):
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        keys = [
            await _ready_job(
                session,
                inn=f"77012345{index:02d}",
                snapshot_hash=str(index) * 64,
            )
            for index in (1, 2)
        ]
        control = await session.get(CompanyCardNarrativeRuntimeControl, 1)
        control.enabled, control.kill_switch = True, False
        control.daily_limit = control.monthly_limit = 10
        control.concurrency_limit = 2
        for key in keys:
            await reserve_or_rereserve_dispatch_credit(
                session, generation_key=key, now=_NOW
            )
        await session.commit()

    for _ in range(2):
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            claimed = await claim_narrative_job(
                session, now=_NOW, lease_seconds=30
            )
            assert claimed is not None
            await session.commit()

    async with AsyncSession(bind=engine) as session:
        with pytest.raises(
            NarrativePersistenceError,
            match="below active leases",
        ):
            await synchronize_narrative_runtime_control(
                session,
                enabled=False,
                kill_switch=True,
                daily_limit=10,
                monthly_limit=10,
                concurrency_limit=1,
                now=_NOW,
            )
        await session.rollback()
        closed = await synchronize_narrative_runtime_control(
            session,
            enabled=False,
            kill_switch=True,
            daily_limit=0,
            monthly_limit=0,
            concurrency_limit=0,
            now=_NOW,
        )
        assert closed.concurrency_limit == 0 and closed.leased_count == 2
        await session.commit()


async def test_mark_dispatching_rechecks_closed_runtime_without_consuming_credit(engine):
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        generation_key = await _ready_job(
            session, inn="7701234599", snapshot_hash="9" * 64
        )
        control = await session.get(CompanyCardNarrativeRuntimeControl, 1)
        control.enabled, control.kill_switch = True, False
        control.daily_limit = control.monthly_limit = control.concurrency_limit = 1
        await reserve_or_rereserve_dispatch_credit(
            session, generation_key=generation_key, now=_NOW
        )
        await session.commit()

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claimed = await claim_narrative_job(session, now=_NOW, lease_seconds=30)
        assert claimed is not None
        lease = job_lease(claimed)
        await session.commit()

    async with AsyncSession(bind=engine) as session:
        await synchronize_narrative_runtime_control(
            session,
            enabled=False,
            kill_switch=True,
            daily_limit=0,
            monthly_limit=0,
            concurrency_limit=0,
            now=_NOW,
        )
        await session.commit()

    async with AsyncSession(bind=engine) as session:
        with pytest.raises(
            NarrativeBudgetUnavailable, match="narrative_runtime_closed"
        ):
            await mark_dispatching(
                session, lease=lease, dispatch_id=uuid4(), now=_NOW
            )
        await session.rollback()
        reservation = await session.get(
            CompanyCardNarrativeBudgetReservation, generation_key
        )
        assert reservation is not None and reservation.state == "reserved"
