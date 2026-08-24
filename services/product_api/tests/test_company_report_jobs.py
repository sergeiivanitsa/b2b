from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
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
from product_api.company_reports.company_card_v2.finance import build_chart_facts
from product_api.company_reports.company_card_v2.models import (
    ArbitrationBasisV1,
    CompanyCardCounterpartyCoreV1,
    CompanyCardV2SnapshotV2,
    FinanceBasisV1,
    NarrativeEvidenceV1,
)
from product_api.company_reports.persistence import (
    CompanyReportDataset,
    CompanyReportJob,
    CompanyReportJobFencingError,
    CompanyReportJobStateConflictError,
    CompanyReportProviderRequest,
    CompanyReportRecord,
    WriterDecision,
    claim_next_job,
    complete_claimed_job,
    complete_claimed_company_card_v2_job,
    enqueue_company_report_job,
    fail_owned_job,
    heartbeat_job,
    reconcile_expired_jobs,
)
from product_api.company_reports.persistence.models import CompanyCardNarrativeOutbox
from product_api.company_reports.persistence.narratives import insert_narrative_outbox

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


async def _enqueue_and_claim_company_card_v2(
    engine,
    *,
    identifier: str = "7701234567",
):
    decision = WriterDecision(
        writer_profile="company_card_v2_writer_v3",
        report_version="3",
        presentation_contract="company_public_h2_v1",
        rollout_generation=1,
    )
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        enqueued = await enqueue_company_report_job(
            session,
            identifier,
            decision=decision,
        )
        await session.commit()
        claimed = await claim_next_job(session, lease_seconds=60)
        assert claimed is not None
        assert claimed.report_id == enqueued.report_id
        await session.commit()
        return claimed


def _company_card_v2_snapshot(
    claimed,
    *,
    full_name: str = "Тестовое общество",
) -> CompanyCardV2SnapshotV2:
    finance_basis = FinanceBasisV1()
    return CompanyCardV2SnapshotV2(
        report_id=str(claimed.report_id),
        subject_inn=claimed.normalized_identifier,
        target_inn=claimed.normalized_identifier,
        generated_at=datetime(2026, 8, 25, tzinfo=UTC),
        rollout_config_generation=claimed.rollout_generation,
        counterparty=CompanyCardCounterpartyCoreV1(
            inn=claimed.normalized_identifier,
            full_name=full_name,
        ),
        finance_basis=finance_basis,
        arbitration_basis=ArbitrationBasisV1(),
        chart_facts=build_chart_facts(finance_basis),
        evidence_version="evidence_registry_v1",
        privacy_version="privacy_v1",
        narrative_evidence=NarrativeEvidenceV1(
            limitation_code="primary_activity_not_admitted",
        ),
    )


async def _company_card_v2_boundary_state(engine, *, job_id, report_id):
    async with AsyncSession(bind=engine) as session:
        job = await session.get(CompanyReportJob, job_id)
        report = await session.get(CompanyReportRecord, report_id)
        assert job is not None and report is not None
        return {
            "job": (
                job.state,
                job.finished_at,
                job.safe_failure_code,
                job.worker_token,
                job.fence_generation,
            ),
            "report": (
                report.lifecycle_status,
                report.generated_at,
                report.finished_at,
                deepcopy(report.normalized_snapshot),
                report.snapshot_hash,
                deepcopy(report.completeness_snapshot),
                deepcopy(report.freshness_snapshot),
                deepcopy(report.warnings_snapshot),
                deepcopy(report.safe_error_snapshot),
            ),
            "outbox": await session.scalar(
                select(func.count(CompanyCardNarrativeOutbox.id)).where(
                    CompanyCardNarrativeOutbox.report_id == report_id
                )
            ),
            "datasets": await session.scalar(
                select(func.count(CompanyReportDataset.id)).where(
                    CompanyReportDataset.report_id == report_id
                )
            ),
            "provider_requests": await session.scalar(
                select(func.count(CompanyReportProviderRequest.id)).where(
                    CompanyReportProviderRequest.report_id == report_id
                )
            ),
        }


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


@pytest.mark.parametrize("lifecycle_status", ("complete", "partial"))
async def test_company_card_v2_completion_commits_snapshot_job_and_one_outbox(
    engine,
    lifecycle_status: str,
):
    claimed = await _enqueue_and_claim_company_card_v2(engine)
    before = await _company_card_v2_boundary_state(
        engine,
        job_id=claimed.job_id,
        report_id=claimed.report_id,
    )
    assert before["job"][0] == "running"
    assert before["report"][0] == "pending"
    assert before["report"][3:7] == (None, None, None, None)
    assert before["outbox"] == before["datasets"] == before["provider_requests"] == 0

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        completed = await complete_claimed_company_card_v2_job(
            session,
            claimed=claimed,
            snapshot=_company_card_v2_snapshot(claimed),
            lifecycle_status=lifecycle_status,
        )
        await session.commit()

    assert completed.lifecycle_status == lifecycle_status
    assert completed.signals is None
    assert completed.scoring is None
    after = await _company_card_v2_boundary_state(
        engine,
        job_id=claimed.job_id,
        report_id=claimed.report_id,
    )
    assert after["job"][0] == "succeeded"
    assert after["job"][1] == after["report"][2]
    assert after["job"][2] is None
    assert after["report"][0] == lifecycle_status
    assert after["report"][3]["snapshot_schema_version"] == (
        "company_card_v2_snapshot_v2"
    )
    assert after["report"][4] is not None
    assert after["report"][5] == {"contract": "company_public_h2_v1"}
    assert after["report"][6] == {
        "generated_at": "2026-08-25T00:00:00+00:00"
    }
    assert after["report"][7:] == ([], None)
    assert after["outbox"] == 1
    # V3 finalization stays outside the H1 provider-journal and signal/scoring
    # persistence path.  Its only derivative write is the durable outbox row.
    assert after["datasets"] == after["provider_requests"] == 0

    async with AsyncSession(bind=engine) as session:
        outbox = await session.scalar(
            select(CompanyCardNarrativeOutbox).where(
                CompanyCardNarrativeOutbox.report_id == claimed.report_id
            )
        )
        assert outbox is not None
        assert (
            outbox.snapshot_hash,
            outbox.event_kind,
            outbox.state,
            outbox.generation_key,
            outbox.attempt_count,
            outbox.fence_generation,
        ) == (
            after["report"][4],
            "initialize_narrative_v1",
            "pending",
            None,
            0,
            0,
        )


async def test_company_card_v2_outbox_failure_rolls_back_all_completion_writes(
    engine,
    monkeypatch,
):
    claimed = await _enqueue_and_claim_company_card_v2(engine)
    before = await _company_card_v2_boundary_state(
        engine,
        job_id=claimed.job_id,
        report_id=claimed.report_id,
    )

    async def fail_outbox(*_args, **_kwargs):
        raise RuntimeError("forced narrative outbox failure")

    from product_api.company_reports.persistence import narratives

    monkeypatch.setattr(narratives, "insert_narrative_outbox", fail_outbox)
    async with AsyncSession(bind=engine) as session:
        with pytest.raises(RuntimeError, match="forced narrative outbox failure"):
            await complete_claimed_company_card_v2_job(
                session,
                claimed=claimed,
                snapshot=_company_card_v2_snapshot(claimed),
                lifecycle_status="partial",
            )
        await session.rollback()

    after = await _company_card_v2_boundary_state(
        engine,
        job_id=claimed.job_id,
        report_id=claimed.report_id,
    )
    assert after == before
    assert after["job"][0] == "running"
    assert after["report"][0] == "pending"
    assert after["outbox"] == 0


async def test_company_card_v2_repeated_completion_is_fenced_and_outbox_is_idempotent(
    engine,
):
    claimed = await _enqueue_and_claim_company_card_v2(engine)
    original = _company_card_v2_snapshot(claimed)
    async with AsyncSession(bind=engine) as session:
        await complete_claimed_company_card_v2_job(
            session,
            claimed=claimed,
            snapshot=original,
            lifecycle_status="complete",
        )
        await session.commit()

    committed = await _company_card_v2_boundary_state(
        engine,
        job_id=claimed.job_id,
        report_id=claimed.report_id,
    )
    async with AsyncSession(bind=engine) as session:
        with pytest.raises(
            (CompanyReportJobFencingError, CompanyReportJobStateConflictError)
        ):
            await complete_claimed_company_card_v2_job(
                session,
                claimed=claimed,
                snapshot=_company_card_v2_snapshot(
                    claimed,
                    full_name="Запрещённая замена снимка",
                ),
                lifecycle_status="partial",
            )
        await session.rollback()

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        report = await session.get(CompanyReportRecord, claimed.report_id)
        assert report is not None and report.snapshot_hash is not None
        first = await insert_narrative_outbox(
            session,
            report_id=report.id,
            snapshot_hash=report.snapshot_hash,
            now=datetime(2026, 8, 25, 1, tzinfo=UTC),
        )
        second = await insert_narrative_outbox(
            session,
            report_id=report.id,
            snapshot_hash=report.snapshot_hash,
            now=datetime(2026, 8, 25, 2, tzinfo=UTC),
        )
        assert first.id == second.id
        await session.commit()

    after = await _company_card_v2_boundary_state(
        engine,
        job_id=claimed.job_id,
        report_id=claimed.report_id,
    )
    assert after == committed
    assert after["outbox"] == 1
    assert after["report"][0] == "complete"
    assert after["report"][3]["counterparty"]["full_name"] == "Тестовое общество"


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
        stored = await session.get(CompanyReportRecord, first.report_id)
        assert stored is not None and stored.report_version == "2"


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
