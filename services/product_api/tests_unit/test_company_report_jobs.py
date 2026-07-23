from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from product_api.company_reports.persistence import jobs
from product_api.company_reports.persistence.errors import (
    CompanyReportJobFencingError,
    CompanyReportJobStateConflictError,
)
from product_api.company_reports.persistence.models import (
    CompanyReportJob,
    CompanyReportRecord,
    CompanyReportSubject,
)

pytestmark = pytest.mark.asyncio


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _Scalars:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _Scalars(self._values)


def _session():
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.get_bind.return_value.dialect.name = "postgresql"
    return session


async def test_enqueue_creates_pending_report_and_queued_job_without_commit(monkeypatch):
    session = _session()
    persistence_events = []
    session.add.side_effect = lambda value: persistence_events.append(
        ("add", type(value))
    )
    session.flush.side_effect = lambda: persistence_events.append(("flush", None))
    subject = CompanyReportSubject(
        id=uuid4(),
        normalized_identifier="7700000000",
        identifier_type="legal_entity_inn",
    )
    monkeypatch.setattr(
        jobs,
        "lock_or_create_subject_for_update",
        AsyncMock(return_value=subject),
    )
    db_time = datetime(2026, 7, 23, tzinfo=timezone.utc)
    monkeypatch.setattr(
        jobs,
        "database_wall_clock",
        AsyncMock(return_value=db_time),
    )
    session.execute.side_effect = [_ScalarResult(None), _ScalarResult(None)]
    report_id = uuid4()
    job_id = uuid4()

    result = await jobs.enqueue_company_report_job(
        session,
        "770-000-0000",
        report_id_factory=lambda: report_id,
        job_id_factory=lambda: job_id,
    )

    assert result.report_id == report_id
    assert result.job_id == job_id
    assert result.reused is False
    added_report = next(
        value for value in session.add.call_args_list
        if isinstance(value.args[0], CompanyReportRecord)
    ).args[0]
    added_job = next(
        value for value in session.add.call_args_list
        if isinstance(value.args[0], CompanyReportJob)
    ).args[0]
    assert added_report.lifecycle_status == "pending"
    assert added_report.started_at == db_time
    assert added_job.state == "queued"
    assert added_job.attempt_count == 0
    assert persistence_events == [
        ("add", CompanyReportRecord),
        ("flush", None),
        ("add", CompanyReportJob),
        ("flush", None),
    ]


async def test_enqueue_reuses_only_matching_active_job(monkeypatch):
    session = _session()
    subject = CompanyReportSubject(
        id=uuid4(),
        normalized_identifier="7700000000",
        identifier_type="legal_entity_inn",
    )
    report = CompanyReportRecord(
        id=uuid4(),
        subject_id=subject.id,
        report_version="1",
        lifecycle_status="pending",
        started_at=datetime.now(timezone.utc),
        warnings_snapshot=[],
        usable_for_public_page=False,
        usable_for_future_scoring=False,
    )
    job = CompanyReportJob(
        id=uuid4(),
        report_id=report.id,
        subject_id=subject.id,
        state="running",
        worker_token=uuid4(),
        attempt_count=1,
        claimed_at=datetime.now(timezone.utc),
        heartbeat_at=datetime.now(timezone.utc),
        lease_expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
    )
    monkeypatch.setattr(
        jobs,
        "lock_or_create_subject_for_update",
        AsyncMock(return_value=subject),
    )
    session.execute.return_value = _ScalarResult(job)
    lock_report = AsyncMock(return_value=report)
    monkeypatch.setattr(jobs, "_lock_report", lock_report)

    result = await jobs.enqueue_company_report_job(session, "7700000000")

    assert result.reused is True
    assert result.report_id == report.id
    assert result.job_id == job.id
    lock_report.assert_awaited_once_with(session, report.id)
    session.flush.assert_not_awaited()

    job.subject_id = uuid4()
    with pytest.raises(CompanyReportJobStateConflictError):
        await jobs.enqueue_company_report_job(session, "7700000000")


async def test_enqueue_rejects_pending_report_without_active_job(monkeypatch):
    session = _session()
    subject = CompanyReportSubject(
        id=uuid4(),
        normalized_identifier="7700000000",
        identifier_type="legal_entity_inn",
    )
    report = CompanyReportRecord(
        id=uuid4(),
        subject_id=subject.id,
        report_version="1",
        lifecycle_status="pending",
        started_at=datetime.now(timezone.utc),
        warnings_snapshot=[],
        usable_for_public_page=False,
        usable_for_future_scoring=False,
    )
    monkeypatch.setattr(
        jobs,
        "lock_or_create_subject_for_update",
        AsyncMock(return_value=subject),
    )
    session.execute.side_effect = [_ScalarResult(None), _ScalarResult(report)]

    with pytest.raises(
        CompanyReportJobStateConflictError,
        match="pending report does not have a matching active job",
    ):
        await jobs.enqueue_company_report_job(session, "7700000000")

    session.add.assert_not_called()
    session.flush.assert_not_awaited()


async def test_claim_uses_one_database_time_for_all_lease_fields(monkeypatch):
    session = _session()
    subject_id = uuid4()
    report_id = uuid4()
    job = CompanyReportJob(
        id=uuid4(),
        report_id=report_id,
        subject_id=subject_id,
        state="queued",
        attempt_count=0,
    )
    report = CompanyReportRecord(
        id=report_id,
        subject_id=subject_id,
        report_version="1",
        lifecycle_status="pending",
        started_at=datetime.now(timezone.utc),
        warnings_snapshot=[],
        usable_for_public_page=False,
        usable_for_future_scoring=False,
    )
    subject = CompanyReportSubject(
        id=subject_id,
        normalized_identifier="7700000000",
        identifier_type="legal_entity_inn",
    )
    session.execute.return_value = _ScalarResult(job)
    monkeypatch.setattr(jobs, "_lock_report", AsyncMock(return_value=report))
    monkeypatch.setattr(jobs, "_get_subject", AsyncMock(return_value=subject))
    db_time = datetime(2026, 7, 23, 1, 2, 3, tzinfo=timezone.utc)
    monkeypatch.setattr(
        jobs,
        "database_wall_clock",
        AsyncMock(return_value=db_time),
    )
    token = uuid4()

    claimed = await jobs.claim_next_job(
        session,
        lease_seconds=60,
        token_factory=lambda: token,
    )

    assert claimed is not None
    assert job.state == "running"
    assert job.claimed_at == job.heartbeat_at == db_time
    assert job.lease_expires_at == db_time + timedelta(seconds=60)
    assert claimed.worker_token == token


async def test_heartbeat_cannot_extend_expired_or_stale_lease(monkeypatch):
    session = _session()
    events = []
    token = uuid4()
    db_time = datetime(2026, 7, 23, tzinfo=timezone.utc)
    job = CompanyReportJob(
        id=uuid4(),
        report_id=uuid4(),
        subject_id=uuid4(),
        state="running",
        worker_token=token,
        attempt_count=1,
        claimed_at=db_time - timedelta(seconds=60),
        heartbeat_at=db_time - timedelta(seconds=60),
        lease_expires_at=db_time,
    )
    lock_job = AsyncMock(
        side_effect=lambda *_args, **_kwargs: events.append("lock") or job
    )
    monkeypatch.setattr(jobs, "_lock_job", lock_job)
    monkeypatch.setattr(
        jobs,
        "database_wall_clock",
        AsyncMock(side_effect=lambda *_args, **_kwargs: events.append("clock") or db_time),
    )

    with pytest.raises(CompanyReportJobFencingError):
        await jobs.heartbeat_job(
            session,
            job_id=job.id,
            worker_token=token,
            lease_seconds=60,
        )
    assert events == ["lock", "clock"]
    assert job.lease_expires_at == db_time
    session.flush.assert_not_awaited()


async def test_reconciliation_is_idempotent_and_never_requeues(monkeypatch):
    session = _session()
    db_time = datetime(2026, 7, 23, tzinfo=timezone.utc)
    job = CompanyReportJob(
        id=uuid4(),
        report_id=uuid4(),
        subject_id=uuid4(),
        state="running",
        worker_token=uuid4(),
        attempt_count=1,
        claimed_at=db_time - timedelta(seconds=120),
        heartbeat_at=db_time - timedelta(seconds=120),
        lease_expires_at=db_time - timedelta(seconds=60),
    )
    report = CompanyReportRecord(
        id=job.report_id,
        subject_id=job.subject_id,
        report_version="1",
        lifecycle_status="pending",
        started_at=db_time - timedelta(seconds=120),
        warnings_snapshot=[],
        usable_for_public_page=False,
        usable_for_future_scoring=False,
    )
    session.execute.return_value = _ScalarsResult([job])
    monkeypatch.setattr(jobs, "_lock_report", AsyncMock(return_value=report))
    monkeypatch.setattr(
        jobs,
        "database_wall_clock",
        AsyncMock(return_value=db_time),
    )

    assert await jobs.reconcile_expired_jobs(session) == 1
    assert job.state == "failed"
    assert job.safe_failure_code == "report_execution_interrupted"
    assert report.lifecycle_status == "failed"

    session.execute.return_value = _ScalarsResult([])
    assert await jobs.reconcile_expired_jobs(session) == 0
