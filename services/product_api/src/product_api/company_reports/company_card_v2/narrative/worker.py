"""Separate durable Company Card narrative worker.

The Gateway sender is injected for tests.  Production crosses that boundary
only after the ``dispatching`` transaction has committed, and no code path in
this module retries a marked dispatch.
"""
from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import datetime
from types import FrameType
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from shared.schemas import ChatRequest, ChatResponse

from product_api.company_reports.persistence.narratives import (
    NarrativeJobLease,
    NarrativePersistenceError,
    NarrativeStaleOwnership,
    claim_narrative_job,
    finalize_fallback_after_dispatch,
    finalize_narrative_artifact,
    heartbeat_narrative_job,
    job_lease,
    mark_dispatching,
    mark_narrative_validating,
    record_gateway_response,
    release_pre_dispatch_reservation,
    synchronize_narrative_runtime_control,
)
from product_api.company_reports.persistence.jobs import database_wall_clock
from product_api.db.session import AsyncSessionMaker
from product_api.gateway_client import GatewayError, send_chat
from product_api.logging_config import configure_logging
from product_api.settings import Settings, get_settings

from .catalog import MODEL_PROFILE
from .service import (
    NarrativeLimits,
    NarrativeResponseValidationContextV1,
    PreparedNarrativeDispatch,
    claim_narrative_reconciliation,
    fallback_projection_digest,
    prepare_narrative_dispatch,
    projection_digest_for_narrative,
    reconcile_claimed_narrative_outbox,
    reconcile_expired_narrative_jobs,
    requeue_pre_dispatch_failure,
    validate_gateway_artifact,
)


class SessionFactory(Protocol):
    def __call__(self) -> AsyncSession: ...


GatewaySender = Callable[[Settings, ChatRequest], Awaitable[ChatResponse]]
Clock = Callable[[], datetime]
DispatchIdFactory = Callable[[], UUID]

logger = logging.getLogger(__name__)


async def _transaction_now(session: AsyncSession, clock: Clock | None) -> datetime:
    """Return one mutation time from this transaction's authoritative clock.

    Production intentionally leaves ``clock`` unset, so budget windows, leases
    and reconciliation all use the database wall clock observed within their
    own transaction.  A callable is retained solely as an explicit test seam.
    """
    if clock is not None:
        return clock()
    return await database_wall_clock(session)


def _limits(settings: Settings) -> NarrativeLimits:
    return NarrativeLimits(
        enabled=settings.company_card_v2_narrative_enabled,
        kill_switch=settings.company_card_v2_narrative_kill_switch,
        quota_mode=settings.company_card_v2_narrative_quota_mode,
        daily_limit=settings.company_card_v2_narrative_daily_limit,
        monthly_limit=settings.company_card_v2_narrative_monthly_limit,
        concurrency=settings.company_card_v2_narrative_concurrency,
    )


async def _finalize_post_dispatch_fallback(
    *,
    session_factory: SessionFactory,
    prepared: PreparedNarrativeDispatch,
    failure_code: str,
    clock: Clock | None,
) -> None:
    projection_digest = fallback_projection_digest(prepared.report)
    if projection_digest is None:
        raise NarrativePersistenceError("dispatched narrative report is not v3")
    async with session_factory() as session:
        async with session.begin():
            now = await _transaction_now(session, clock)
            await finalize_fallback_after_dispatch(
                session,
                lease=prepared.lease,
                validation_code=failure_code,
                projection_digest=projection_digest,
                now=now,
            )


async def heartbeat_supervisor(
    lease: NarrativeJobLease,
    stop_event: asyncio.Event,
    ownership_lost: asyncio.Event,
    *,
    session_factory: SessionFactory,
    clock: Clock | None,
    lease_seconds: int,
    heartbeat_interval_seconds: float,
) -> None:
    """Extend one exact fenced lease until processing is complete.

    The supervisor never changes the dispatch identity and never calls the
    Gateway.  A stale fence is terminal for this process; transient database
    failures are logged and retried until either the lease is fenced elsewhere
    or the owner finishes.
    """
    if lease_seconds <= 0 or heartbeat_interval_seconds <= 0:
        raise ValueError("narrative heartbeat timing must be positive")
    if heartbeat_interval_seconds >= lease_seconds:
        raise ValueError("narrative heartbeat interval must be below lease")
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=heartbeat_interval_seconds
            )
            return
        except TimeoutError:
            pass

        async with session_factory() as session:
            try:
                async with session.begin():
                    now = await _transaction_now(session, clock)
                    await heartbeat_narrative_job(
                        session,
                        lease=lease,
                        now=now,
                        lease_seconds=lease_seconds,
                    )
            except NarrativeStaleOwnership:
                ownership_lost.set()
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("company card narrative heartbeat failed")


async def run_once(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory = AsyncSessionMaker,
    gateway_sender: GatewaySender = send_chat,
    clock: Clock | None = None,
    dispatch_id_factory: DispatchIdFactory = uuid4,
    lease_seconds: int = 60,
) -> int:
    """Run bounded reconciliation and at most one paid dispatch."""
    settings = settings or get_settings()
    limits = _limits(settings)
    changed = 0

    # Runtime controls and the durable outbox lease commit before work begins.
    async with session_factory() as session:
        async with session.begin():
            now = await _transaction_now(session, clock)
            await synchronize_narrative_runtime_control(
                session,
                enabled=limits.enabled,
                kill_switch=limits.kill_switch,
                quota_mode=limits.quota_mode,
                daily_limit=limits.daily_limit,
                monthly_limit=limits.monthly_limit,
                concurrency_limit=limits.concurrency,
                now=now,
            )
            outbox = await claim_narrative_reconciliation(
                session,
                now=now,
                lease_seconds=lease_seconds,
            )
    if outbox is not None:
        async with session_factory() as session:
            async with session.begin():
                now = await _transaction_now(session, clock)
                changed += await reconcile_claimed_narrative_outbox(
                    session,
                    lease=outbox,
                    now=now,
                    limits=limits,
                )

    # Expired marked work becomes fallback; expired unmarked work releases its
    # credit.  Neither branch crosses the Gateway boundary.
    async with session_factory() as session:
        async with session.begin():
            now = await _transaction_now(session, clock)
            changed += await reconcile_expired_narrative_jobs(session, now=now)
    async with session_factory() as session:
        async with session.begin():
            now = await _transaction_now(session, clock)
            changed += await requeue_pre_dispatch_failure(session, now=now)

    # Claim and commit the concurrency slot before local preparation.
    async with session_factory() as session:
        async with session.begin():
            now = await _transaction_now(session, clock)
            claimed = await claim_narrative_job(
                session,
                now=now,
                lease_seconds=lease_seconds,
            )
            lease = None if claimed is None else job_lease(claimed)
    if lease is None:
        return changed
    changed += 1

    heartbeat_stop = asyncio.Event()
    ownership_lost = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        heartbeat_supervisor(
            lease,
            heartbeat_stop,
            ownership_lost,
            session_factory=session_factory,
            clock=clock,
            lease_seconds=lease_seconds,
            heartbeat_interval_seconds=min(
                settings.company_report_worker_heartbeat_interval_seconds,
                lease_seconds / 2,
            ),
        )
    )
    try:
        return await _run_claimed_dispatch(
            settings=settings,
            session_factory=session_factory,
            gateway_sender=gateway_sender,
            clock=clock,
            dispatch_id_factory=dispatch_id_factory,
            lease=lease,
            ownership_lost=ownership_lost,
            changed=changed,
        )
    finally:
        heartbeat_stop.set()
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task


async def _run_claimed_dispatch(
    *,
    settings: Settings,
    session_factory: SessionFactory,
    gateway_sender: GatewaySender,
    clock: Clock | None,
    dispatch_id_factory: DispatchIdFactory,
    lease: NarrativeJobLease,
    ownership_lost: asyncio.Event,
    changed: int,
) -> int:
    dispatch_id = dispatch_id_factory()
    try:
        async with session_factory() as session:
            async with session.begin():
                now = await _transaction_now(session, clock)
                prepared = await prepare_narrative_dispatch(
                    session,
                    lease=lease,
                    dispatch_id=dispatch_id,
                    now=now,
                    timeout_seconds=settings.company_card_v2_narrative_gateway_timeout_seconds,
                    max_output_tokens=settings.company_card_v2_narrative_max_output_tokens,
                )
                await mark_dispatching(
                    session,
                    lease=lease,
                    dispatch_id=dispatch_id,
                    now=now,
                )
    except NarrativeStaleOwnership:
        return changed
    except (NarrativePersistenceError, ValueError):
        # The marker was not committed, so this is a provably local failure.
        try:
            async with session_factory() as session:
                async with session.begin():
                    now = await _transaction_now(session, clock)
                    await release_pre_dispatch_reservation(
                        session,
                        lease=lease,
                        failure_code="local_report_validation_failed",
                        now=now,
                    )
        except NarrativeStaleOwnership:
            pass
        return changed

    # Exactly one call for this generation. No loop, retry wrapper or repair
    # call is permitted after the committed dispatch marker.
    if ownership_lost.is_set():
        return changed
    try:
        response = await gateway_sender(settings, prepared.request)
    except asyncio.CancelledError:
        await asyncio.shield(
            _finalize_post_dispatch_fallback(
                session_factory=session_factory,
                prepared=prepared,
                failure_code="ambiguous_worker_shutdown",
                clock=clock,
            )
        )
        raise
    except (TimeoutError, asyncio.TimeoutError):
        await _finalize_post_dispatch_fallback(
            session_factory=session_factory,
            prepared=prepared,
            failure_code="ambiguous_timeout",
            clock=clock,
        )
        return changed
    except GatewayError:
        await _finalize_post_dispatch_fallback(
            session_factory=session_factory,
            prepared=prepared,
            failure_code="gateway_error_after_dispatch",
            clock=clock,
        )
        return changed
    except Exception:
        await _finalize_post_dispatch_fallback(
            session_factory=session_factory,
            prepared=prepared,
            failure_code="gateway_contract_failure",
            clock=clock,
        )
        return changed

    if (
        not isinstance(response, ChatResponse)
        or response.gateway_dispatch_id != dispatch_id
    ):
        await _finalize_post_dispatch_fallback(
            session_factory=session_factory,
            prepared=prepared,
            failure_code="gateway_dispatch_id_mismatch",
            clock=clock,
        )
        return changed
    if (
        response.model_profile != MODEL_PROFILE
        or not isinstance(response.resolved_model, str)
        or not response.resolved_model.strip()
    ):
        await _finalize_post_dispatch_fallback(
            session_factory=session_factory,
            prepared=prepared,
            failure_code="gateway_response_identity_mismatch",
            clock=clock,
        )
        return changed

    try:
        async with session_factory() as session:
            async with session.begin():
                now = await _transaction_now(session, clock)
                await record_gateway_response(
                    session,
                    lease=lease,
                    resolved_model_version=response.resolved_model,
                    now=now,
                )
                await mark_narrative_validating(
                    session,
                    lease=lease,
                    now=now,
                )
        validation_context = NarrativeResponseValidationContextV1(
            gateway_dispatch_id=prepared.request.gateway_dispatch_id,
            generation_key=prepared.report.generation_key,
            evidence=prepared.evidence,
        )
        validated = validate_gateway_artifact(validation_context, response)
        projection_digest = projection_digest_for_narrative(
            prepared.report,
            validated.public_narrative,
        )
    except NarrativeStaleOwnership:
        # An expired reconciler already won. The stale response is discarded.
        return changed
    except Exception:
        await _finalize_post_dispatch_fallback(
            session_factory=session_factory,
            prepared=prepared,
            failure_code="invalid_output",
            clock=clock,
        )
        return changed

    try:
        async with session_factory() as session:
            async with session.begin():
                now = await _transaction_now(session, clock)
                await finalize_narrative_artifact(
                    session,
                    lease=lease,
                    draft=validated.draft,
                    projection_digest=projection_digest,
                    now=now,
                )
    except NarrativeStaleOwnership:
        # Fenced stale output cannot overwrite the winner.
        return changed
    return changed


async def run_forever(
    *,
    poll_seconds: float = 1.0,
) -> None:
    """Compatibility entry point for an intentionally unbounded worker."""
    if poll_seconds <= 0:
        raise ValueError("narrative worker poll interval must be positive")
    shutdown_event = asyncio.Event()
    await run_worker(
        get_settings(),
        shutdown_event,
        poll_seconds=poll_seconds,
    )


async def _wait_interruptibly(
    shutdown_event: asyncio.Event,
    seconds: float,
) -> None:
    try:
        await asyncio.wait_for(shutdown_event.wait(), timeout=seconds)
    except TimeoutError:
        return


async def run_worker(
    settings: Settings,
    shutdown_event: asyncio.Event,
    *,
    session_factory: SessionFactory = AsyncSessionMaker,
    gateway_sender: GatewaySender = send_chat,
    clock: Clock | None = None,
    dispatch_id_factory: DispatchIdFactory = uuid4,
    poll_seconds: float | None = None,
) -> None:
    """Run until shutdown, allowing one in-flight job a bounded grace period."""
    poll_seconds = (
        settings.company_report_worker_poll_interval_seconds
        if poll_seconds is None
        else poll_seconds
    )
    if poll_seconds <= 0:
        raise ValueError("narrative worker poll interval must be positive")

    while not shutdown_event.is_set():
        current = asyncio.create_task(
            run_once(
                settings=settings,
                session_factory=session_factory,
                gateway_sender=gateway_sender,
                clock=clock,
                dispatch_id_factory=dispatch_id_factory,
                lease_seconds=settings.company_report_worker_lease_seconds,
            )
        )
        shutdown_wait = asyncio.create_task(shutdown_event.wait())
        done, _ = await asyncio.wait(
            {current, shutdown_wait}, return_when=asyncio.FIRST_COMPLETED
        )
        if current in done:
            shutdown_wait.cancel()
            with suppress(asyncio.CancelledError):
                await shutdown_wait
            try:
                changed = await current
            except Exception:
                logger.error("company card narrative worker cycle failed")
                changed = 0
            if changed == 0:
                await _wait_interruptibly(shutdown_event, poll_seconds)
            continue

        try:
            await asyncio.wait_for(
                asyncio.shield(current),
                timeout=settings.company_report_worker_shutdown_grace_seconds,
            )
        except TimeoutError:
            current.cancel()
            with suppress(asyncio.CancelledError):
                await current
        finally:
            shutdown_wait.cancel()
            with suppress(asyncio.CancelledError):
                await shutdown_wait
        return


def install_signal_handlers(
    loop: asyncio.AbstractEventLoop,
    shutdown_event: asyncio.Event,
) -> Callable[[], None]:
    registered_loop_signals: list[signal.Signals] = []
    previous_handlers: dict[
        signal.Signals,
        signal.Handlers | Callable[[int, FrameType | None], None],
    ] = {}

    def request_shutdown(*_: object) -> None:
        shutdown_event.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, request_shutdown)
            registered_loop_signals.append(signum)
        except (NotImplementedError, RuntimeError):
            try:
                previous_handlers[signum] = signal.getsignal(signum)
                signal.signal(signum, request_shutdown)
            except (ValueError, OSError, RuntimeError):
                continue

    def cleanup() -> None:
        for signum in registered_loop_signals:
            with suppress(NotImplementedError, RuntimeError):
                loop.remove_signal_handler(signum)
        for signum, handler in previous_handlers.items():
            with suppress(ValueError, OSError, RuntimeError):
                signal.signal(signum, handler)

    return cleanup


async def _async_main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    shutdown_event = asyncio.Event()
    cleanup = install_signal_handlers(asyncio.get_running_loop(), shutdown_event)
    try:
        await run_worker(settings, shutdown_event)
    finally:
        cleanup()


def main() -> None:
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()


__all__ = [
    "heartbeat_supervisor",
    "install_signal_handlers",
    "main",
    "run_forever",
    "run_once",
    "run_worker",
]
