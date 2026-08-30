from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from shared.schemas import ChatResponse

from product_api.company_reports.company_card_v2.narrative.catalog import MODEL_PROFILE
from product_api.company_reports.company_card_v2.narrative.models import (
    NarrativeEvidenceEnvelope,
)
from product_api.company_reports.company_card_v2.narrative import worker
from product_api.company_reports.persistence.narratives import (
    NarrativeJobLease,
    NarrativePersistenceError,
    NarrativeStaleOwnership,
)
from product_api.gateway_client import GatewayError


NOW = datetime(2026, 8, 24, 12, tzinfo=UTC)
DISPATCH_ID = UUID("123e4567-e89b-12d3-a456-426614174000")


class _Context:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class _Session(_Context):
    def begin(self):
        return _Context()


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        company_card_v2_narrative_enabled=True,
        company_card_v2_narrative_kill_switch=False,
        company_card_v2_narrative_quota_mode="bounded",
        company_card_v2_narrative_daily_limit=1,
        company_card_v2_narrative_monthly_limit=1,
        company_card_v2_narrative_concurrency=1,
        company_card_v2_narrative_gateway_timeout_seconds=20,
        company_card_v2_narrative_max_output_tokens=600,
        company_report_worker_heartbeat_interval_seconds=10,
    )


def _lease() -> NarrativeJobLease:
    return NarrativeJobLease(
        job_id=uuid4(),
        report_id=uuid4(),
        snapshot_hash="a" * 64,
        generation_key="b" * 64,
        lease_token=uuid4(),
        fence_generation=1,
        lease_expires_at=NOW + timedelta(minutes=1),
    )


def _prepared(lease: NarrativeJobLease) -> SimpleNamespace:
    return SimpleNamespace(
        lease=lease,
        report=SimpleNamespace(generation_key=lease.generation_key),
        evidence=NarrativeEvidenceEnvelope(
            evidence_registry_version="company_card_v2_evidence_registry_v1",
            primary_activity_label="Разработка программного обеспечения",
        ),
        request=SimpleNamespace(gateway_dispatch_id=DISPATCH_ID),
    )


def _response(dispatch_id: UUID = DISPATCH_ID) -> ChatResponse:
    return ChatResponse(
        text="{}",
        model_profile=MODEL_PROFILE,
        resolved_model="gpt-test-v1",
        gateway_dispatch_id=dispatch_id,
    )


def _install_common(monkeypatch: pytest.MonkeyPatch) -> tuple[NarrativeJobLease, SimpleNamespace, list[tuple[str, object]]]:
    lease = _lease()
    prepared = _prepared(lease)
    events: list[tuple[str, object]] = []

    async def synchronize(_session, **_kwargs):
        events.append(("synchronize", None))

    async def claim_outbox(_session, **_kwargs):
        return None

    async def no_changes(_session, **_kwargs):
        return 0

    async def claim_job(_session, **_kwargs):
        return object()

    async def prepare(_session, **_kwargs):
        events.append(("prepare", None))
        return prepared

    async def mark(_session, **kwargs):
        events.append(("dispatching", kwargs["dispatch_id"]))

    async def record(_session, **_kwargs):
        events.append(("response_recorded", None))

    async def validating(_session, **_kwargs):
        events.append(("validating", None))

    async def finalize(_session, **_kwargs):
        events.append(("artifact", None))

    async def fallback(_session, **kwargs):
        events.append(("fallback", kwargs["validation_code"]))

    async def release(_session, **kwargs):
        events.append(("release", kwargs["failure_code"]))

    async def heartbeat(_lease, stop, _ownership_lost, **_kwargs):
        await stop.wait()

    monkeypatch.setattr(worker, "synchronize_narrative_runtime_control", synchronize)
    monkeypatch.setattr(worker, "claim_narrative_reconciliation", claim_outbox)
    monkeypatch.setattr(worker, "reconcile_expired_narrative_jobs", no_changes)
    monkeypatch.setattr(worker, "requeue_pre_dispatch_failure", no_changes)
    monkeypatch.setattr(worker, "claim_narrative_job", claim_job)
    monkeypatch.setattr(worker, "job_lease", lambda _row: lease)
    monkeypatch.setattr(worker, "prepare_narrative_dispatch", prepare)
    monkeypatch.setattr(worker, "mark_dispatching", mark)
    monkeypatch.setattr(worker, "record_gateway_response", record)
    monkeypatch.setattr(worker, "mark_narrative_validating", validating)
    monkeypatch.setattr(worker, "finalize_narrative_artifact", finalize)
    monkeypatch.setattr(worker, "finalize_fallback_after_dispatch", fallback)
    monkeypatch.setattr(worker, "release_pre_dispatch_reservation", release)
    monkeypatch.setattr(worker, "heartbeat_supervisor", heartbeat)
    monkeypatch.setattr(worker, "fallback_projection_digest", lambda _report: "c" * 64)
    monkeypatch.setattr(
        worker,
        "projection_digest_for_narrative",
        lambda _report, _narrative: "d" * 64,
    )
    monkeypatch.setattr(
        worker,
        "validate_gateway_artifact",
        lambda _context, _response: SimpleNamespace(
            draft=object(),
            public_narrative=object(),
        ),
    )
    return lease, prepared, events


@pytest.mark.asyncio
async def test_local_pre_dispatch_failure_releases_credit_and_never_calls_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    _lease_value, _prepared_value, events = _install_common(monkeypatch)
    calls = 0

    async def failed_prepare(*_args, **_kwargs):
        raise NarrativePersistenceError("local invalid snapshot")

    async def forbidden_gateway(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("gateway must not be called")

    monkeypatch.setattr(worker, "prepare_narrative_dispatch", failed_prepare)
    changed = await worker.run_once(
        settings=_settings(),
        session_factory=_Session,
        gateway_sender=forbidden_gateway,
        clock=lambda: NOW,
        dispatch_id_factory=lambda: DISPATCH_ID,
    )

    assert changed == 1
    assert calls == 0
    assert ("release", "local_report_validation_failed") in events
    assert not any(name == "dispatching" for name, _value in events)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (TimeoutError("timeout"), "ambiguous_timeout"),
        (
            GatewayError(
                "insufficient quota",
                status_code=429,
                code="insufficient_quota",
            ),
            "gateway_error_after_dispatch",
        ),
        (
            GatewayError("upstream unavailable", status_code=503, retryable=True),
            "gateway_error_after_dispatch",
        ),
        (RuntimeError("contract"), "gateway_contract_failure"),
    ],
)
async def test_post_dispatch_failure_materializes_fallback_without_retry(monkeypatch: pytest.MonkeyPatch, failure: Exception, code: str) -> None:
    _lease_value, _prepared_value, events = _install_common(monkeypatch)
    calls = 0

    async def gateway(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise failure

    changed = await worker.run_once(
        settings=_settings(),
        session_factory=_Session,
        gateway_sender=gateway,
        clock=lambda: NOW,
        dispatch_id_factory=lambda: DISPATCH_ID,
    )

    assert changed == 1
    assert calls == 1
    assert events.index(("dispatching", DISPATCH_ID)) < events.index(("fallback", code))


@pytest.mark.asyncio
async def test_cancelled_dispatch_is_shielded_to_saved_fallback_and_reraised(monkeypatch: pytest.MonkeyPatch) -> None:
    _lease_value, _prepared_value, events = _install_common(monkeypatch)

    async def cancelled(*_args, **_kwargs):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await worker.run_once(
            settings=_settings(),
            session_factory=_Session,
            gateway_sender=cancelled,
            clock=lambda: NOW,
            dispatch_id_factory=lambda: DISPATCH_ID,
        )

    assert ("fallback", "ambiguous_worker_shutdown") in events


@pytest.mark.asyncio
async def test_dispatch_echo_mismatch_is_terminal_fallback_and_never_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    _lease_value, _prepared_value, events = _install_common(monkeypatch)
    calls = 0

    async def gateway(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return _response(UUID("123e4567-e89b-12d3-a456-426614174001"))

    await worker.run_once(
        settings=_settings(),
        session_factory=_Session,
        gateway_sender=gateway,
        clock=lambda: NOW,
        dispatch_id_factory=lambda: DISPATCH_ID,
    )

    assert calls == 1
    assert ("fallback", "gateway_dispatch_id_mismatch") in events
    assert not any(name in {"response_recorded", "validating", "artifact"} for name, _value in events)


@pytest.mark.asyncio
async def test_invalid_gateway_output_is_terminal_fallback_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _lease_value, _prepared_value, events = _install_common(monkeypatch)
    calls = 0

    async def gateway(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return _response()

    def invalid(*_args, **_kwargs):
        raise ValueError("invalid render plan")

    monkeypatch.setattr(worker, "validate_gateway_artifact", invalid)
    changed = await worker.run_once(
        settings=_settings(),
        session_factory=_Session,
        gateway_sender=gateway,
        clock=lambda: NOW,
        dispatch_id_factory=lambda: DISPATCH_ID,
    )

    assert changed == 1
    assert calls == 1
    assert ("fallback", "invalid_output") in events
    assert not any(name == "artifact" for name, _value in events)


def test_worker_maps_explicit_unlimited_settings_to_dispatchable_limits() -> None:
    settings = _settings()
    settings.company_card_v2_narrative_quota_mode = "unlimited"
    settings.company_card_v2_narrative_daily_limit = 0
    settings.company_card_v2_narrative_monthly_limit = 0

    limits = worker._limits(settings)

    assert limits.quota_mode == "unlimited"
    assert limits.permits_dispatch()


@pytest.mark.asyncio
async def test_success_crosses_gateway_once_after_dispatch_marker_and_finalizes(monkeypatch: pytest.MonkeyPatch) -> None:
    _lease_value, _prepared_value, events = _install_common(monkeypatch)
    calls = 0

    async def gateway(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        events.append(("gateway", None))
        return _response()

    changed = await worker.run_once(
        settings=_settings(),
        session_factory=_Session,
        gateway_sender=gateway,
        clock=lambda: NOW,
        dispatch_id_factory=lambda: DISPATCH_ID,
    )

    assert changed == 1
    assert calls == 1
    assert [name for name, _value in events if name in {"dispatching", "gateway", "response_recorded", "validating", "artifact"}] == [
        "dispatching",
        "gateway",
        "response_recorded",
        "validating",
        "artifact",
    ]


@pytest.mark.asyncio
async def test_default_worker_clock_is_database_authoritative_and_clock_is_explicit_test_seam(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _lease_value, _prepared_value, _events = _install_common(monkeypatch)
    database_clock_calls = 0

    async def database_clock(_session) -> datetime:
        nonlocal database_clock_calls
        database_clock_calls += 1
        return NOW

    monkeypatch.setattr(worker, "database_wall_clock", database_clock)

    async def gateway(*_args, **_kwargs):
        return _response()

    await worker.run_once(
        settings=_settings(),
        session_factory=_Session,
        gateway_sender=gateway,
        dispatch_id_factory=lambda: DISPATCH_ID,
    )

    assert database_clock_calls > 0
    assert await worker._transaction_now(_Session(), lambda: NOW + timedelta(days=1)) == (
        NOW + timedelta(days=1)
    )
    assert database_clock_calls > 0


@pytest.mark.asyncio
async def test_runtime_heartbeat_extends_exact_fenced_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    lease = _lease()
    calls: list[dict[str, object]] = []

    async def heartbeat(_session, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(worker, "heartbeat_narrative_job", heartbeat)
    stop = asyncio.Event()
    ownership_lost = asyncio.Event()
    task = asyncio.create_task(
        worker.heartbeat_supervisor(
            lease,
            stop,
            ownership_lost,
            session_factory=_Session,
            clock=lambda: NOW,
            lease_seconds=60,
            heartbeat_interval_seconds=0.001,
        )
    )
    for _ in range(50):
        if calls:
            break
        await asyncio.sleep(0.002)
    stop.set()
    await task

    assert calls and calls[0]["lease"] == lease
    assert calls[0]["lease_seconds"] == 60
    assert ownership_lost.is_set() is False


@pytest.mark.asyncio
async def test_runtime_heartbeat_stops_after_stale_fence(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    async def stale(_session, **_kwargs):
        nonlocal calls
        calls += 1
        raise NarrativeStaleOwnership("stale")

    monkeypatch.setattr(worker, "heartbeat_narrative_job", stale)
    ownership_lost = asyncio.Event()
    await asyncio.wait_for(
        worker.heartbeat_supervisor(
            _lease(),
            asyncio.Event(),
            ownership_lost,
            session_factory=_Session,
            clock=lambda: NOW,
            lease_seconds=60,
            heartbeat_interval_seconds=0.001,
        ),
        timeout=0.1,
    )
    assert calls == 1
    assert ownership_lost.is_set()


def _runtime_settings(*, grace: float) -> SimpleNamespace:
    return SimpleNamespace(
        company_report_worker_poll_interval_seconds=0.001,
        company_report_worker_lease_seconds=60,
        company_report_worker_shutdown_grace_seconds=grace,
    )


@pytest.mark.asyncio
async def test_runtime_worker_stops_without_new_cycle_when_shutdown_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    async def forbidden(**_kwargs):
        nonlocal calls
        calls += 1

    monkeypatch.setattr(worker, "run_once", forbidden)
    shutdown = asyncio.Event()
    shutdown.set()
    await worker.run_worker(_runtime_settings(grace=0), shutdown)
    assert calls == 0


@pytest.mark.asyncio
async def test_runtime_worker_allows_inflight_cycle_to_finish_during_grace(monkeypatch: pytest.MonkeyPatch) -> None:
    shutdown = asyncio.Event()
    started = asyncio.Event()
    finished = asyncio.Event()

    async def cycle(**_kwargs):
        started.set()
        await asyncio.sleep(0.005)
        finished.set()
        return 1

    monkeypatch.setattr(worker, "run_once", cycle)
    task = asyncio.create_task(
        worker.run_worker(_runtime_settings(grace=0.1), shutdown)
    )
    await started.wait()
    shutdown.set()
    await asyncio.wait_for(task, timeout=0.2)
    assert finished.is_set()


@pytest.mark.asyncio
async def test_runtime_worker_cancels_inflight_cycle_after_grace(monkeypatch: pytest.MonkeyPatch) -> None:
    shutdown = asyncio.Event()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def cycle(**_kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(worker, "run_once", cycle)
    task = asyncio.create_task(worker.run_worker(_runtime_settings(grace=0), shutdown))
    await started.wait()
    shutdown.set()
    await asyncio.wait_for(task, timeout=0.2)
    assert cancelled.is_set()
