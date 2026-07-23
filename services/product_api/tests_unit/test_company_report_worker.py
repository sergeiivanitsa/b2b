from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from company_report_orchestrator_test_helpers import successful_fake_provider
from company_report_signal_test_helpers import complete_company_report
from product_api.company_reports import worker
from product_api.company_reports.persistence import ClaimedReportJob
from product_api.settings import get_settings

class _Session:
    def __init__(self):
        self.commit = AsyncMock()
        self.rollback = AsyncMock()


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        return None


class _SessionFactory:
    def __init__(self):
        self.sessions = []

    def __call__(self):
        session = _Session()
        self.sessions.append(session)
        return _SessionContext(session)


class _Client:
    def __init__(self):
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True


class _ProviderClient(_Client):
    def __init__(self, provider):
        super().__init__()
        self._provider = provider

    async def fetch_counterparty(self, *args, **kwargs):
        return await self._provider.fetch_counterparty(*args, **kwargs)

    async def fetch_finance(self, *args, **kwargs):
        return await self._provider.fetch_finance(*args, **kwargs)

    async def fetch_arbitration_cases(self, *args, **kwargs):
        return await self._provider.fetch_arbitration_cases(*args, **kwargs)


def _claimed(report):
    now = datetime.now(timezone.utc)
    return ClaimedReportJob(
        job_id=uuid4(),
        report_id=report.report_id,
        subject_id=uuid4(),
        normalized_identifier=report.target_identifier,
        worker_token=uuid4(),
        claimed_at=now,
        lease_expires_at=now + timedelta(seconds=60),
    )


@pytest.mark.asyncio
async def test_run_one_calls_orchestrator_once_closes_provider_and_finalizes(
    monkeypatch,
):
    report = complete_company_report()
    claimed = _claimed(report)
    client = _Client()
    builder = AsyncMock(return_value=report)
    complete = AsyncMock()
    monkeypatch.setattr(worker, "complete_claimed_job", complete)
    session_factory = _SessionFactory()

    succeeded = await worker.run_one_claimed_job(
        claimed,
        get_settings(),
        session_factory=session_factory,
        client_factory=lambda _settings: client,
        report_builder=builder,
    )

    assert succeeded is True
    assert client.closed is True
    builder.assert_awaited_once()
    call = builder.await_args
    assert call.args == (claimed.normalized_identifier,)
    assert call.kwargs["request_id"] == f"company-report:{claimed.report_id}"
    assert call.kwargs["report_id_factory"]() == claimed.report_id
    complete.assert_awaited_once()
    assert session_factory.sessions[-1].commit.await_count == 1


@pytest.mark.asyncio
async def test_run_one_does_not_retry_unexpected_failure(monkeypatch):
    report = complete_company_report()
    claimed = _claimed(report)
    builder = AsyncMock(side_effect=RuntimeError("private failure"))
    fail = AsyncMock()
    monkeypatch.setattr(worker, "fail_owned_job", fail)
    session_factory = _SessionFactory()

    succeeded = await worker.run_one_claimed_job(
        claimed,
        get_settings(),
        session_factory=session_factory,
        client_factory=lambda _settings: _Client(),
        report_builder=builder,
    )

    assert succeeded is False
    builder.assert_awaited_once()
    fail.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_pipeline_calls_each_dataset_exactly_once(monkeypatch):
    seed = complete_company_report()
    claimed = _claimed(seed)
    provider = successful_fake_provider()
    client = _ProviderClient(provider)
    complete = AsyncMock()
    monkeypatch.setattr(worker, "complete_claimed_job", complete)

    succeeded = await worker.run_one_claimed_job(
        claimed,
        get_settings(),
        session_factory=_SessionFactory(),
        client_factory=lambda _settings: client,
    )

    assert succeeded is True
    assert len(provider.calls) == 3
    assert {call["dataset"] for call in provider.calls} == {
        "counterparty",
        "finance",
        "arbitration",
    }
    assert all(
        call["request_id"].startswith(f"company-report:{claimed.report_id}:")
        for call in provider.calls
    )


@pytest.mark.asyncio
async def test_worker_stops_without_claiming_when_shutdown_is_already_set(
    monkeypatch,
):
    shutdown = __import__("asyncio").Event()
    shutdown.set()
    claim = AsyncMock(side_effect=AssertionError("must not claim"))
    monkeypatch.setattr(worker, "claim_next_job", claim)

    await worker.run_worker(
        get_settings(),
        shutdown,
        session_factory=_SessionFactory(),
    )

    claim.assert_not_awaited()


def test_worker_has_no_explanation_or_gateway_dependency():
    source = Path(worker.__file__).read_text(encoding="utf-8")
    assert "explain_scoring_result" not in source
    assert "gateway_client" not in source
