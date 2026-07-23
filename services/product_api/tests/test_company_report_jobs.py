from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
import sys

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

TESTS_UNIT = Path(__file__).resolve().parents[1] / "tests_unit"
if str(TESTS_UNIT) not in sys.path:
    sys.path.append(str(TESTS_UNIT))

from company_report_orchestrator_test_helpers import successful_fake_provider
from product_api.company_reports import build_company_report
from product_api.company_reports.persistence import (
    CompanyReportDataset,
    CompanyReportJob,
    CompanyReportJobFencingError,
    CompanyReportProviderRequest,
    CompanyReportRecord,
    claim_next_job,
    complete_claimed_job,
    enqueue_company_report_job,
    fail_owned_job,
    heartbeat_job,
    reconcile_expired_jobs,
)

pytestmark = pytest.mark.asyncio


async def _require_jobs_table(engine) -> None:
    async with engine.connect() as connection:
        exists = await connection.scalar(
            text("SELECT to_regclass('company_report_jobs')")
        )
    if exists is None:
        pytest.skip("company_report_jobs migration is not applied")


async def _enqueue_and_claim(
    engine,
    *,
    identifier: str = "7700000000",
    lease_seconds: int = 60,
):
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        enqueued = await enqueue_company_report_job(session, identifier)
        await session.commit()
        claimed = await claim_next_job(session, lease_seconds=lease_seconds)
        assert claimed is not None
        assert claimed.job_id == enqueued.job_id
        await session.commit()
        return enqueued, claimed


async def _successful_report(claimed):
    provider = successful_fake_provider()
    report = await build_company_report(
        claimed.normalized_identifier,
        provider=provider,
        request_id=f"integration:{claimed.report_id}",
        report_id_factory=lambda: claimed.report_id,
    )
    assert len(provider.calls) == 3
    return report


async def _job_report_snapshot(engine, *, job_id, report_id):
    async with AsyncSession(bind=engine) as session:
        job = await session.get(CompanyReportJob, job_id)
        report = await session.get(CompanyReportRecord, report_id)
        assert job is not None and report is not None
        return (
            job.state,
            job.finished_at,
            job.safe_failure_code,
            job.heartbeat_at,
            job.lease_expires_at,
            report.lifecycle_status,
            report.generated_at,
            report.finished_at,
            deepcopy(report.safe_error_snapshot),
            deepcopy(report.normalized_snapshot),
            report.snapshot_hash,
        )


async def test_concurrent_enqueue_reuses_one_pending_report_and_job(engine):
    await _require_jobs_table(engine)

    async def enqueue_once():
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            result = await enqueue_company_report_job(session, "7700000000")
            await session.commit()
            return result

    first, second = await asyncio.gather(enqueue_once(), enqueue_once())

    assert first.report_id == second.report_id
    assert first.job_id == second.job_id
    assert {first.reused, second.reused} == {False, True}
    async with AsyncSession(bind=engine) as session:
        assert await session.scalar(select(func.count(CompanyReportRecord.id))) == 1
        assert await session.scalar(select(func.count(CompanyReportJob.id))) == 1


async def test_concurrent_claims_claim_each_job_once(engine):
    await _require_jobs_table(engine)
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        await enqueue_company_report_job(session, "7700000000")
        await enqueue_company_report_job(session, "770000000001")
        await session.commit()

    async def claim_once():
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            claimed = await claim_next_job(session, lease_seconds=60)
            await session.commit()
            return claimed

    first, second = await asyncio.gather(claim_once(), claim_once())

    assert first is not None and second is not None
    assert first.job_id != second.job_id
    assert first.report_id != second.report_id


async def test_heartbeat_waiting_on_job_lock_uses_fresh_clock_and_is_fenced(engine):
    await _require_jobs_table(engine)
    _, claimed = await _enqueue_and_claim(engine, lease_seconds=1)
    before = await _job_report_snapshot(
        engine,
        job_id=claimed.job_id,
        report_id=claimed.report_id,
    )

    blocker = AsyncSession(bind=engine, expire_on_commit=False)
    await blocker.execute(
        select(CompanyReportJob)
        .where(CompanyReportJob.id == claimed.job_id)
        .with_for_update()
    )
    heartbeat_started = asyncio.Event()

    async def late_heartbeat():
        async with AsyncSession(bind=engine) as session:
            heartbeat_started.set()
            try:
                await heartbeat_job(
                    session,
                    job_id=claimed.job_id,
                    worker_token=claimed.worker_token,
                    lease_seconds=60,
                )
            except Exception as exc:
                await session.rollback()
                return exc
            await session.commit()
            return None

    heartbeat_task = asyncio.create_task(late_heartbeat())
    await heartbeat_started.wait()
    await asyncio.sleep(1.25)
    await blocker.commit()
    await blocker.close()
    heartbeat_error = await asyncio.wait_for(heartbeat_task, timeout=5)

    assert isinstance(heartbeat_error, CompanyReportJobFencingError)
    after = await _job_report_snapshot(
        engine,
        job_id=claimed.job_id,
        report_id=claimed.report_id,
    )
    assert after == before


async def test_heartbeat_and_reconciliation_have_one_winner_without_mixed_state(
    engine,
):
    await _require_jobs_table(engine)
    _, claimed = await _enqueue_and_claim(engine)
    async with AsyncSession(bind=engine) as session:
        await session.execute(
            update(CompanyReportJob)
            .where(CompanyReportJob.id == claimed.job_id)
            .values(lease_expires_at=text("clock_timestamp() - interval '1 second'"))
        )
        await session.commit()

    reconciler = AsyncSession(bind=engine, expire_on_commit=False)
    assert await reconcile_expired_jobs(reconciler) == 1
    heartbeat_started = asyncio.Event()

    async def blocked_heartbeat():
        async with AsyncSession(bind=engine) as session:
            heartbeat_started.set()
            try:
                await heartbeat_job(
                    session,
                    job_id=claimed.job_id,
                    worker_token=claimed.worker_token,
                    lease_seconds=60,
                )
            except Exception as exc:
                await session.rollback()
                return exc
            await session.commit()
            return None

    heartbeat_task = asyncio.create_task(blocked_heartbeat())
    await heartbeat_started.wait()
    await asyncio.sleep(0.1)
    assert heartbeat_task.done() is False
    await reconciler.commit()
    await reconciler.close()
    heartbeat_error = await asyncio.wait_for(heartbeat_task, timeout=5)

    assert isinstance(heartbeat_error, CompanyReportJobFencingError)
    async with AsyncSession(bind=engine) as session:
        job = await session.get(CompanyReportJob, claimed.job_id)
        report = await session.get(CompanyReportRecord, claimed.report_id)
        assert job is not None
        assert report is not None
        assert job.state == "failed"
        assert job.safe_failure_code == "report_execution_interrupted"
        assert report.lifecycle_status == "failed"
        assert report.safe_error_snapshot == {
            "code": "report_execution_interrupted"
        }
        assert job.finished_at == report.finished_at


async def test_stale_complete_and_fail_after_reconciliation_leave_rows_unchanged(
    engine,
):
    await _require_jobs_table(engine)
    _, claimed = await _enqueue_and_claim(engine)
    report_result = await _successful_report(claimed)
    async with AsyncSession(bind=engine) as session:
        await session.execute(
            update(CompanyReportJob)
            .where(CompanyReportJob.id == claimed.job_id)
            .values(lease_expires_at=text("clock_timestamp() - interval '1 second'"))
        )
        await session.commit()
        assert await reconcile_expired_jobs(session) == 1
        await session.commit()

    before = await _job_report_snapshot(
        engine,
        job_id=claimed.job_id,
        report_id=claimed.report_id,
    )
    async with AsyncSession(bind=engine) as session:
        with pytest.raises(CompanyReportJobFencingError):
            await complete_claimed_job(
                session,
                claimed=claimed,
                report=report_result,
            )
        await session.rollback()
    async with AsyncSession(bind=engine) as session:
        with pytest.raises(CompanyReportJobFencingError):
            await fail_owned_job(session, claimed=claimed)
        await session.rollback()

    after = await _job_report_snapshot(
        engine,
        job_id=claimed.job_id,
        report_id=claimed.report_id,
    )
    assert after == before


async def test_successful_completion_atomically_persists_report_and_job(engine):
    await _require_jobs_table(engine)
    _, claimed = await _enqueue_and_claim(engine)
    report_result = await _successful_report(claimed)

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        completed = await complete_claimed_job(
            session,
            claimed=claimed,
            report=report_result,
        )
        await session.commit()

    assert completed.report_id == claimed.report_id
    assert completed.lifecycle_status == "complete"
    async with AsyncSession(bind=engine) as session:
        job = await session.get(CompanyReportJob, claimed.job_id)
        report = await session.get(CompanyReportRecord, claimed.report_id)
        dataset_count = await session.scalar(
            select(func.count(CompanyReportDataset.id)).where(
                CompanyReportDataset.report_id == claimed.report_id
            )
        )
        journal_count = await session.scalar(
            select(func.count(CompanyReportProviderRequest.id)).where(
                CompanyReportProviderRequest.report_id == claimed.report_id
            )
        )
        assert job is not None
        assert report is not None
        assert job.state == "succeeded"
        assert job.finished_at == report.finished_at
        assert report.lifecycle_status == "complete"
        assert report.normalized_snapshot is not None
        assert report.snapshot_hash is not None
        assert dataset_count == 3
        assert journal_count == 3


async def test_repeated_enqueue_during_terminal_transition_does_not_deadlock(engine):
    await _require_jobs_table(engine)
    first, claimed = await _enqueue_and_claim(engine)
    report_result = await _successful_report(claimed)

    terminal = AsyncSession(bind=engine, expire_on_commit=False)
    await terminal.execute(
        select(CompanyReportJob)
        .where(CompanyReportJob.id == claimed.job_id)
        .with_for_update()
    )
    enqueue_started = asyncio.Event()

    async def repeated_enqueue():
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            enqueue_started.set()
            result = await enqueue_company_report_job(
                session,
                claimed.normalized_identifier,
            )
            await session.commit()
            return result

    enqueue_task = asyncio.create_task(repeated_enqueue())
    await enqueue_started.wait()
    await asyncio.sleep(0.1)
    assert enqueue_task.done() is False

    await complete_claimed_job(
        terminal,
        claimed=claimed,
        report=report_result,
    )
    await terminal.commit()
    await terminal.close()
    second = await asyncio.wait_for(enqueue_task, timeout=5)

    assert second.reused is False
    assert second.report_id != first.report_id
    assert second.job_id != first.job_id

    async with AsyncSession(bind=engine) as session:
        first_job = await session.get(CompanyReportJob, first.job_id)
        first_report = await session.get(CompanyReportRecord, first.report_id)
        second_job = await session.get(CompanyReportJob, second.job_id)
        second_report = await session.get(CompanyReportRecord, second.report_id)
        assert first_job is not None and first_job.state == "succeeded"
        assert first_report is not None and first_report.lifecycle_status == "complete"
        assert second_job is not None and second_job.state == "queued"
        assert second_report is not None
        assert second_report.lifecycle_status == "pending"


async def test_new_explicit_enqueue_after_failed_creates_new_report(engine):
    await _require_jobs_table(engine)
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        first = await enqueue_company_report_job(session, "7700000000")
        await session.commit()
        claimed = await claim_next_job(session, lease_seconds=60)
        assert claimed is not None
        await session.commit()
        await fail_owned_job(session, claimed=claimed)
        await session.commit()

        second = await enqueue_company_report_job(session, "7700000000")
        await session.commit()

    assert second.report_id != first.report_id
    assert second.job_id != first.job_id
    assert second.reused is False
