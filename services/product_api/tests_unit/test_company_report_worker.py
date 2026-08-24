import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from company_report_orchestrator_test_helpers import successful_fake_provider
from company_report_signal_test_helpers import complete_company_report
from product_api.company_reports import worker
from product_api.company_reports.persistence import ClaimedReportJob
from product_api.providers.datanewton import (
    COUNTERPARTY_ENDPOINT,
    FINANCE_ENDPOINT,
    DataNewtonResult,
    calculate_response_hash,
)
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
async def test_v3_job_never_constructs_provider_while_default_off(monkeypatch):
    report = complete_company_report()
    claimed = _claimed(report).__class__(
        **{**_claimed(report).__dict__, "writer_profile": "company_card_v2_writer_v3", "report_version": "3", "presentation_contract": "company_public_h2_v1", "rollout_generation": 1}
    )
    fail = AsyncMock(return_value=False)
    monkeypatch.setattr(worker, "_try_fail_live_owned_job", fail)
    factory = lambda _settings: (_ for _ in ()).throw(AssertionError("provider must not be constructed"))
    assert await worker.run_one_claimed_job(claimed, get_settings(), session_factory=_SessionFactory(), client_factory=factory) is False
    fail.assert_awaited_once()


@pytest.mark.asyncio
async def test_v3_worker_requires_the_full_immutable_tuple_before_builder(monkeypatch):
    report = complete_company_report()
    claimed = _claimed(report).__class__(
        **{
            **_claimed(report).__dict__,
            "writer_profile": "company_card_v2_writer_v3",
            "report_version": "2",
            "presentation_contract": "company_public_h2_v1",
            "rollout_generation": 1,
        }
    )
    builder = AsyncMock()
    fail = AsyncMock(return_value=False)
    monkeypatch.setattr(worker, "_try_fail_live_owned_job", fail)
    settings = get_settings().model_copy(
        update={"company_card_v2_writer_enabled": True}
    )

    assert await worker.run_one_claimed_job(
        claimed,
        settings,
        session_factory=_SessionFactory(),
        v3_builder=builder,
    ) is False

    builder.assert_not_awaited()
    fail.assert_awaited_once()


@pytest.mark.asyncio
async def test_v3_worker_forwards_explicit_partial_outcome_and_commits(monkeypatch):
    report = complete_company_report()
    claimed = _claimed(report).__class__(
        **{
            **_claimed(report).__dict__,
            "writer_profile": "company_card_v2_writer_v3",
            "report_version": "3",
            "presentation_contract": "company_public_h2_v1",
            "rollout_generation": 1,
        }
    )
    outcome = SimpleNamespace(snapshot=object(), lifecycle_status="partial")
    builder = AsyncMock(return_value=outcome)
    complete = AsyncMock()
    monkeypatch.setattr(worker, "complete_claimed_company_card_v2_job", complete)
    sessions = _SessionFactory()
    settings = get_settings().model_copy(
        update={"company_card_v2_writer_enabled": True}
    )

    assert await worker.run_one_claimed_job(
        claimed,
        settings,
        session_factory=sessions,
        v3_builder=builder,
    ) is True

    builder.assert_awaited_once_with(claimed)
    complete.assert_awaited_once_with(
        sessions.sessions[-1],
        claimed=claimed,
        snapshot=outcome.snapshot,
        lifecycle_status="partial",
    )
    assert sessions.sessions[-1].commit.await_count == 1


@pytest.mark.asyncio
async def test_v3_completion_failure_rolls_back_before_owned_failure(monkeypatch):
    report = complete_company_report()
    claimed = _claimed(report).__class__(
        **{
            **_claimed(report).__dict__,
            "writer_profile": "company_card_v2_writer_v3",
            "report_version": "3",
            "presentation_contract": "company_public_h2_v1",
            "rollout_generation": 1,
        }
    )
    builder = AsyncMock(
        return_value=SimpleNamespace(snapshot=object(), lifecycle_status="complete")
    )
    complete = AsyncMock(side_effect=RuntimeError("outbox insert failed"))
    fail = AsyncMock(return_value=False)
    monkeypatch.setattr(worker, "complete_claimed_company_card_v2_job", complete)
    monkeypatch.setattr(worker, "_try_fail_live_owned_job", fail)
    sessions = _SessionFactory()
    settings = get_settings().model_copy(
        update={"company_card_v2_writer_enabled": True}
    )

    assert await worker.run_one_claimed_job(
        claimed,
        settings,
        session_factory=sessions,
        v3_builder=builder,
    ) is False

    assert sessions.sessions[-1].rollback.await_count == 1
    fail.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_worker_supplies_default_v3_builder_with_injected_clock(monkeypatch):
    report = complete_company_report()
    claimed = _claimed(report).__class__(
        **{
            **_claimed(report).__dict__,
            "writer_profile": "company_card_v2_writer_v3",
            "report_version": "3",
            "presentation_contract": "company_public_h2_v1",
            "rollout_generation": 1,
        }
    )
    shutdown = asyncio.Event()
    received: dict[str, object] = {}

    async def fake_run_one(*args, **kwargs):
        received["builder"] = kwargs["v3_builder"]
        shutdown.set()
        return True

    production = AsyncMock(return_value=object())
    monkeypatch.setattr(worker, "run_one_claimed_job", fake_run_one)
    monkeypatch.setattr(worker, "reconcile_expired_jobs", AsyncMock(return_value=0))
    monkeypatch.setattr(worker, "claim_next_job", AsyncMock(return_value=claimed))
    monkeypatch.setattr(worker, "_build_production_v3_outcome", production)
    clock = lambda: datetime(2026, 8, 25, tzinfo=timezone.utc)
    client_factory = lambda _settings: (_ for _ in ()).throw(
        AssertionError("adapter stub must not construct provider")
    )
    settings = get_settings()

    await worker.run_worker(
        settings,
        shutdown,
        session_factory=_SessionFactory(),
        client_factory=client_factory,
        clock=clock,
    )

    supplied = received["builder"]
    assert callable(supplied)
    await supplied(claimed)
    production.assert_awaited_once_with(
        claimed,
        settings=settings,
        client_factory=client_factory,
        clock=clock,
    )


@pytest.mark.asyncio
async def test_production_v3_adapter_uses_injected_provider_and_clock_only():
    report = complete_company_report()
    claimed = _claimed(report).__class__(
        **{
            **_claimed(report).__dict__,
            "writer_profile": "company_card_v2_writer_v3",
            "report_version": "3",
            "presentation_contract": "company_public_h2_v1",
            "rollout_generation": 1,
        }
    )
    now = datetime(2026, 8, 25, 12, tzinfo=timezone.utc)
    calls = []

    class Provider:
        closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            self.closed = True

        async def fetch_counterparty(self, identifier, *, filters, request_id=None):
            calls.append(("counterparty", identifier, filters, request_id))
            payload = {
                "inn": identifier,
                "company": {
                    "company_names": {"short_name": "Тест"},
                    "okveds": [{
                        "code": "62.01",
                        "value": "Разработка программного обеспечения",
                        "main": True,
                        "mode": "new",
                    }],
                },
            }
            return DataNewtonResult(
                dataset="counterparty",
                endpoint=COUNTERPARTY_ENDPOINT,
                requested_identifier=identifier,
                request_parameters={"inn": identifier, "filters": "OKVED_BLOCK"},
                status_code=200,
                attempts=1,
                duration_ms=0,
                received_at=now,
                raw_payload=payload,
                response_hash=calculate_response_hash(payload),
            )

        async def fetch_finance(self, identifier, *, request_id=None):
            calls.append(("finance", identifier, request_id))
            payload = {}
            return DataNewtonResult(
                dataset="finance",
                endpoint=FINANCE_ENDPOINT,
                requested_identifier=identifier,
                request_parameters={"inn": identifier},
                status_code=200,
                attempts=1,
                duration_ms=0,
                received_at=now,
                raw_payload=payload,
                response_hash=calculate_response_hash(payload),
            )

    provider = Provider()
    outcome = await worker._build_production_v3_outcome(
        claimed,
        settings=get_settings(),
        client_factory=lambda _settings: provider,
        clock=lambda: now,
    )

    assert outcome.snapshot.generated_at == now
    assert outcome.lifecycle_status == "complete"
    assert provider.closed is True
    assert calls == [
        (
            "counterparty",
            claimed.normalized_identifier,
            ("OKVED_BLOCK",),
            f"company-report:{claimed.report_id}:counterparty",
        ),
        (
            "finance",
            claimed.normalized_identifier,
            f"company-report:{claimed.report_id}:finance",
        ),
    ]


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


@pytest.mark.asyncio
async def test_heartbeat_supervisor_passes_full_captured_claim_tuple(monkeypatch):
    report = complete_company_report()
    claimed = _claimed(report)
    heartbeat = AsyncMock()
    monkeypatch.setattr(worker, "heartbeat_job", heartbeat)
    stop = asyncio.Event()
    ownership_lost = asyncio.Event()

    class Settings:
        company_report_worker_heartbeat_interval_seconds = 0.001
        company_report_worker_lease_seconds = 60

    task = asyncio.create_task(
        worker.heartbeat_supervisor(
            claimed, Settings(), stop, ownership_lost, session_factory=_SessionFactory()
        )
    )
    for _ in range(50):
        if heartbeat.await_count:
            break
        await asyncio.sleep(0.002)
    stop.set()
    await task
    assert heartbeat.await_count >= 1
    assert heartbeat.await_args.kwargs["claimed"] == claimed
