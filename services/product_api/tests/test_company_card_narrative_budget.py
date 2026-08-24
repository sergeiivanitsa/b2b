from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.company_reports.company_card_v2.narrative.identity import (
    GenerationIdentityV2,
    identity_key,
)
from product_api.company_reports.company_card_v2.narrative import worker as narrative_worker
from product_api.company_reports.persistence.jobs import database_wall_clock
from product_api.company_reports.persistence.models import (
    CompanyCardNarrativeBudgetReservation,
    CompanyCardNarrativeBudgetWindow,
    CompanyCardNarrativeRuntimeControl,
    CompanyReportRecord,
    CompanyReportSubject,
)
from product_api.company_reports.persistence.narratives import (
    NarrativeBudgetUnavailable,
    NarrativeStaleOwnership,
    claim_narrative_job,
    initialize_narrative_generation,
    job_lease,
    mark_dispatching,
    narrative_budget_windows,
    release_pre_dispatch_reservation,
    reserve_or_rereserve_dispatch_credit,
)


_NOW = datetime(2026, 8, 24, 12, tzinfo=UTC)


def _identity(report_id, snapshot_hash: str):
    value = GenerationIdentityV2(
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
    return value, identity_key(value)


async def _job(
    session: AsyncSession,
    *,
    inn: str,
    snapshot_hash: str,
    now: datetime = _NOW,
) -> str:
    subject = CompanyReportSubject(
        normalized_identifier=inn, identifier_type="legal_entity_inn"
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
        normalized_snapshot={"report_version": "3"},
        snapshot_hash=snapshot_hash,
        warnings_snapshot=[],
        usable_for_public_page=False,
        usable_for_future_scoring=False,
    )
    session.add(report)
    await session.flush()
    identity, generation_key = _identity(report.id, snapshot_hash)
    await initialize_narrative_generation(
        session,
        report_id=report.id,
        snapshot_hash=snapshot_hash,
        generation_key=generation_key,
        identity=identity,
        now=now,
    )
    return generation_key


async def _open(
    session: AsyncSession,
    *,
    daily: int,
    monthly: int,
    concurrency: int,
) -> None:
    control = await session.get(CompanyCardNarrativeRuntimeControl, 1)
    assert control is not None
    control.enabled, control.kill_switch = True, False
    control.daily_limit = daily
    control.monthly_limit = monthly
    control.concurrency_limit = concurrency


def test_budget_windows_use_moscow_calendar_not_utc_calendar():
    daily, monthly = narrative_budget_windows(datetime(2026, 8, 31, 21, 30, tzinfo=UTC))

    assert daily[0] == "2026-09-01"
    assert daily[1] == datetime(2026, 8, 31, 21, tzinfo=UTC)
    assert daily[2] == datetime(2026, 9, 1, 21, tzinfo=UTC)
    assert monthly[0] == "2026-09-01"
    assert monthly[1] == daily[1]
    assert monthly[2] == datetime(2026, 9, 30, 21, tzinfo=UTC)


@pytest.mark.parametrize(
    ("daily", "monthly", "expected"),
    ((1, 2, "daily_budget_exhausted"), (2, 1, "monthly_budget_exhausted")),
)
@pytest.mark.asyncio
async def test_daily_and_monthly_limits_fail_closed(engine, daily, monthly, expected):
    async with AsyncSession(bind=engine) as session:
        first = await _job(session, inn="7701234501", snapshot_hash="1" * 64)
        second = await _job(session, inn="7701234502", snapshot_hash="2" * 64)
        await _open(session, daily=daily, monthly=monthly, concurrency=2)
        await reserve_or_rereserve_dispatch_credit(
            session, generation_key=first, now=_NOW
        )
        await session.commit()

    async with AsyncSession(bind=engine) as session:
        with pytest.raises(NarrativeBudgetUnavailable) as captured:
            await reserve_or_rereserve_dispatch_credit(
                session, generation_key=second, now=_NOW
            )
        assert captured.value.code == expected


@pytest.mark.asyncio
async def test_concurrent_last_credit_has_exactly_one_winner(engine):
    async with AsyncSession(bind=engine) as session:
        keys = (
            await _job(session, inn="7701234511", snapshot_hash="3" * 64),
            await _job(session, inn="7701234512", snapshot_hash="4" * 64),
        )
        await _open(session, daily=1, monthly=1, concurrency=2)
        await session.commit()

    async def contender(generation_key: str) -> str:
        async with AsyncSession(bind=engine) as session:
            try:
                async with session.begin():
                    await reserve_or_rereserve_dispatch_credit(
                        session, generation_key=generation_key, now=_NOW
                    )
                return "reserved"
            except NarrativeBudgetUnavailable as exc:
                return exc.code

    outcomes = await asyncio.gather(*(contender(key) for key in keys))
    assert sorted(outcomes) == ["daily_budget_exhausted", "reserved"]
    async with AsyncSession(bind=engine) as session:
        windows = (await session.scalars(select(CompanyCardNarrativeBudgetWindow))).all()
        assert len(windows) == 2
        assert all(window.reserved_count == 1 for window in windows)
        assert all(window.consumed_count == 0 for window in windows)


@pytest.mark.asyncio
async def test_two_sessions_ignore_divergent_host_clocks_for_db_authoritative_moscow_budget_and_lease_timeline(
    engine,
):
    host_behind = datetime(2026, 8, 31, 20, 30, tzinfo=UTC)
    host_ahead = datetime(2026, 8, 31, 21, 30, tzinfo=UTC)
    assert narrative_budget_windows(host_behind)[0][0] != narrative_budget_windows(host_ahead)[0][0]

    async with AsyncSession(bind=engine) as session:
        async with session.begin():
            database_now = await database_wall_clock(session)
            keys = (
                await _job(
                    session,
                    inn="7701234513",
                    snapshot_hash="a" * 64,
                    now=database_now,
                ),
                await _job(
                    session,
                    inn="7701234514",
                    snapshot_hash="b" * 64,
                    now=database_now,
                ),
            )
            await _open(session, daily=2, monthly=2, concurrency=2)

    async def reserve_and_claim(generation_key: str, host_now: datetime):
        # Each worker host has a different hypothetical wall clock, but that
        # value is evidence-only: the production path below keeps clock=None.
        host_windows = tuple(window[0] for window in narrative_budget_windows(host_now))
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            async with session.begin():
                now = await narrative_worker._transaction_now(session, None)
                await reserve_or_rereserve_dispatch_credit(
                    session,
                    generation_key=generation_key,
                    now=now,
                )
                claimed = await claim_narrative_job(
                    session,
                    now=now,
                    lease_seconds=60,
                )
                assert claimed is not None
                lease = job_lease(claimed)
                daily, monthly = narrative_budget_windows(now)
                return (
                    host_windows,
                    (daily[0], monthly[0]),
                    now,
                    lease.lease_expires_at,
                )

    outcomes = await asyncio.gather(
        reserve_and_claim(keys[0], host_behind),
        reserve_and_claim(keys[1], host_ahead),
    )

    assert outcomes[0][0] != outcomes[1][0]
    expected_windows = outcomes[0][1]
    assert all(windows == expected_windows for _host_windows, windows, _now, _expires_at in outcomes)
    for _host_windows, db_windows, db_now, lease_expires_at in outcomes:
        assert lease_expires_at == db_now + timedelta(seconds=60)
        assert db_windows == tuple(window[0] for window in narrative_budget_windows(db_now))


@pytest.mark.asyncio
async def test_released_credit_rebuckets_across_moscow_day_and_month(engine):
    before = datetime(2026, 8, 31, 20, 30, tzinfo=UTC)
    after = datetime(2026, 8, 31, 21, 30, tzinfo=UTC)
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        key = await _job(
            session, inn="7701234521", snapshot_hash="5" * 64, now=before
        )
        await _open(session, daily=2, monthly=2, concurrency=1)
        await reserve_or_rereserve_dispatch_credit(
            session, generation_key=key, now=before
        )
        await session.commit()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claimed = await claim_narrative_job(
            session, now=before, lease_seconds=60
        )
        assert claimed is not None
        lease = job_lease(claimed)
        await session.commit()
    async with AsyncSession(bind=engine) as session:
        await release_pre_dispatch_reservation(
            session,
            lease=lease,
            failure_code="local_request_build_failed",
            now=before,
        )
        await session.commit()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        reservation = await reserve_or_rereserve_dispatch_credit(
            session, generation_key=key, now=after
        )
        assert reservation.daily_period_start_local.isoformat() == "2026-09-01"
        assert reservation.monthly_period_start_local.isoformat() == "2026-09-01"
        await session.commit()
    async with AsyncSession(bind=engine) as session:
        windows = (await session.scalars(select(CompanyCardNarrativeBudgetWindow))).all()
        counts = {
            (row.period_kind, row.period_start_local.isoformat()): row.reserved_count
            for row in windows
        }
        assert counts[("daily", "2026-08-31")] == 0
        assert counts[("monthly", "2026-08-01")] == 0
        assert counts[("daily", "2026-09-01")] == 1
        assert counts[("monthly", "2026-09-01")] == 1


@pytest.mark.asyncio
async def test_consumed_credit_never_releases_or_rebuckets(engine):
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        key = await _job(session, inn="7701234531", snapshot_hash="6" * 64)
        await _open(session, daily=1, monthly=1, concurrency=1)
        await reserve_or_rereserve_dispatch_credit(
            session, generation_key=key, now=_NOW
        )
        await session.commit()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claimed = await claim_narrative_job(session, now=_NOW, lease_seconds=60)
        assert claimed is not None
        lease = job_lease(claimed)
        await mark_dispatching(
            session, lease=lease, dispatch_id=uuid4(), now=_NOW
        )
        await session.commit()

    async def rereserve() -> str:
        async with AsyncSession(bind=engine) as session:
            try:
                await reserve_or_rereserve_dispatch_credit(
                    session,
                    generation_key=key,
                    now=datetime(2026, 9, 2, 12, tzinfo=UTC),
                )
            except NarrativeBudgetUnavailable as exc:
                return exc.code
        return "unexpected"

    assert await asyncio.gather(rereserve(), rereserve()) == [
        "dispatch_credit_consumed",
        "dispatch_credit_consumed",
    ]
    async with AsyncSession(bind=engine) as session:
        with pytest.raises(NarrativeStaleOwnership):
            await release_pre_dispatch_reservation(
                session,
                lease=lease,
                failure_code="local_request_build_failed",
                now=_NOW,
            )
        await session.rollback()
        reservation = await session.get(CompanyCardNarrativeBudgetReservation, key)
        windows = (await session.scalars(select(CompanyCardNarrativeBudgetWindow))).all()
        assert reservation is not None and reservation.state == "consumed"
        assert all(window.reserved_count == 0 for window in windows)
        assert all(window.consumed_count == 1 for window in windows)
