from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from types import FrameType
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from product_api.company_reports.orchestrator import build_company_report
from product_api.company_reports.persistence import (
    ClaimedReportJob,
    CompanyReportJobFencingError,
    REPORT_EXECUTION_FAILED_CODE,
    claim_next_job,
    complete_claimed_job,
    complete_claimed_company_card_v2_job,
    fail_owned_job,
    heartbeat_job,
    reconcile_expired_jobs,
)
from product_api.db.session import AsyncSessionMaker
from product_api.company_reports.scoring import score_signals
from product_api.company_reports.signals import evaluate_signals
from product_api.logging_config import configure_logging
from product_api.providers.datanewton import DataNewtonClient
from product_api.settings import Settings, get_settings

logger = logging.getLogger(__name__)

SessionFactory = async_sessionmaker[AsyncSession]
ClientFactory = Callable[[Settings], Any]
ReportBuilder = Callable[..., Any]
V3Builder = Callable[[ClaimedReportJob], Any]
Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _is_exact_v3_claim(claimed: ClaimedReportJob) -> bool:
    return (
        claimed.writer_profile == "company_card_v2_writer_v3"
        and claimed.report_version == "3"
        and claimed.presentation_contract == "company_public_h2_v1"
        and claimed.rollout_generation > 0
    )


async def _build_production_v3_outcome(
    claimed: ClaimedReportJob,
    *,
    settings: Settings,
    client_factory: ClientFactory,
    clock: Clock,
) -> object:
    """Open the provider only for the enabled, exact V3 write path.

    The writer owns the narrow provider protocol and receives both the client
    and an explicit timestamp.  Importing it lazily avoids making any public
    path or default-off worker cycle construct a provider client.
    """
    from product_api.company_reports.company_card_v2.writer import (
        build_company_card_v2_snapshot_v2_outcome,
    )

    client = client_factory(settings)
    async with client:
        return await build_company_card_v2_snapshot_v2_outcome(
            provider=client,
            report_id=claimed.report_id,
            subject_inn=claimed.normalized_identifier,
            target_inn=claimed.normalized_identifier,
            writer_profile=claimed.writer_profile,
            report_version=claimed.report_version,
            presentation_contract=claimed.presentation_contract,
            rollout_config_generation=claimed.rollout_generation,
            now=clock(),
            request_id=f"company-report:{claimed.report_id}",
        )


async def run_one_claimed_job(
    claimed: ClaimedReportJob,
    settings: Settings,
    *,
    session_factory: SessionFactory = AsyncSessionMaker,
    client_factory: ClientFactory = DataNewtonClient,
    report_builder: ReportBuilder = build_company_report,
    v3_builder: V3Builder | None = None,
) -> bool:
    """Execute one claimed job without retrying or replaying the pipeline."""

    heartbeat_stop = asyncio.Event()
    ownership_lost = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        heartbeat_supervisor(
            claimed,
            settings,
            heartbeat_stop,
            ownership_lost,
            session_factory=session_factory,
        )
    )
    try:
        # The shipped worker keeps V3 disabled until the setting and the full
        # immutable writer tuple are both present.  This branch is the only
        # write-side provider boundary for Company Card V2.
        if claimed.writer_profile != "h1_legacy_writer_v2":
            if (
                not _is_exact_v3_claim(claimed)
                or not settings.company_card_v2_writer_enabled
                or v3_builder is None
            ):
                return await _try_fail_live_owned_job(claimed, session_factory=session_factory)
            outcome = await v3_builder(claimed)
            snapshot = getattr(outcome, "snapshot", None)
            lifecycle_status = getattr(outcome, "lifecycle_status", None)
            if snapshot is None or lifecycle_status not in {"complete", "partial"}:
                raise RuntimeError("company card v2 builder outcome is invalid")
            if ownership_lost.is_set():
                return False
            async with session_factory() as session:
                try:
                    await complete_claimed_company_card_v2_job(
                        session,
                        claimed=claimed,
                        snapshot=snapshot,
                        lifecycle_status=lifecycle_status,
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise
            return True
        client = client_factory(settings)
        async with client:
            report = await report_builder(
                claimed.normalized_identifier,
                provider=client,
                request_id=f"company-report:{claimed.report_id}",
                report_id_factory=lambda: claimed.report_id,
            )
        if ownership_lost.is_set():
            return False
        async with session_factory() as session:
            try:
                await complete_claimed_job(
                    session,
                    claimed=claimed,
                    report=report,
                    signal_evaluator=evaluate_signals,
                    scoring_evaluator=score_signals,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        return True
    except asyncio.CancelledError:
        await _try_fail_live_owned_job(
            claimed,
            session_factory=session_factory,
        )
        raise
    except CompanyReportJobFencingError:
        return False
    except Exception:
        logger.error("company report worker execution failed")
        return await _try_fail_live_owned_job(
            claimed,
            session_factory=session_factory,
        )
    finally:
        heartbeat_stop.set()
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task


async def heartbeat_supervisor(
    claimed: ClaimedReportJob,
    settings: Settings,
    stop_event: asyncio.Event,
    ownership_lost: asyncio.Event,
    *,
    session_factory: SessionFactory = AsyncSessionMaker,
) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=settings.company_report_worker_heartbeat_interval_seconds,
            )
            return
        except TimeoutError:
            pass

        async with session_factory() as session:
            try:
                await heartbeat_job(
                    session,
                    job_id=claimed.job_id,
                    worker_token=claimed.worker_token,
                    lease_seconds=settings.company_report_worker_lease_seconds,
                    # Every runtime heartbeat carries the immutable claim
                    # tuple, so persistence can reject a profile/version/
                    # contract/generation/fence mutation before extending a
                    # lease. The optional public argument remains solely for
                    # legacy direct callers outside this worker.
                    claimed=claimed,
                )
                await session.commit()
            except CompanyReportJobFencingError:
                await session.rollback()
                ownership_lost.set()
                return
            except Exception:
                await session.rollback()
                logger.error("company report worker heartbeat failed")


async def run_worker(
    settings: Settings,
    shutdown_event: asyncio.Event,
    *,
    session_factory: SessionFactory = AsyncSessionMaker,
    client_factory: ClientFactory = DataNewtonClient,
    report_builder: ReportBuilder = build_company_report,
    v3_builder: V3Builder | None = None,
    clock: Clock = _utc_now,
) -> None:
    if v3_builder is None:
        async def production_v3_builder(claimed: ClaimedReportJob) -> object:
            return await _build_production_v3_outcome(
                claimed,
                settings=settings,
                client_factory=client_factory,
                clock=clock,
            )

        v3_builder = production_v3_builder

    while not shutdown_event.is_set():
        claimed: ClaimedReportJob | None = None
        async with session_factory() as session:
            try:
                await reconcile_expired_jobs(session)
                claimed = await claim_next_job(
                    session,
                    lease_seconds=settings.company_report_worker_lease_seconds,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                logger.error("company report worker persistence cycle failed")

        if claimed is None:
            await _wait_interruptibly(
                shutdown_event,
                settings.company_report_worker_poll_interval_seconds,
            )
            continue

        current = asyncio.create_task(
            run_one_claimed_job(
                claimed,
                settings,
                session_factory=session_factory,
                client_factory=client_factory,
                report_builder=report_builder,
                v3_builder=v3_builder,
            )
        )
        shutdown_wait = asyncio.create_task(shutdown_event.wait())
        done, _ = await asyncio.wait(
            {current, shutdown_wait},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if current in done:
            shutdown_wait.cancel()
            with suppress(asyncio.CancelledError):
                await shutdown_wait
            await current
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


async def _try_fail_live_owned_job(
    claimed: ClaimedReportJob,
    *,
    session_factory: SessionFactory,
) -> bool:
    async with session_factory() as session:
        try:
            await fail_owned_job(
                session,
                claimed=claimed,
                safe_failure_code=REPORT_EXECUTION_FAILED_CODE,
            )
            await session.commit()
            return False
        except CompanyReportJobFencingError:
            await session.rollback()
            return False
        except Exception:
            await session.rollback()
            logger.error("company report worker failure finalization failed")
            return False


async def _wait_interruptibly(
    shutdown_event: asyncio.Event,
    seconds: float,
) -> None:
    try:
        await asyncio.wait_for(shutdown_event.wait(), timeout=seconds)
    except TimeoutError:
        return


async def _async_main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    shutdown_event = asyncio.Event()
    cleanup = install_signal_handlers(
        asyncio.get_running_loop(),
        shutdown_event,
    )
    try:
        await run_worker(settings, shutdown_event)
    finally:
        cleanup()


def main() -> None:
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()


__all__ = [
    "_build_production_v3_outcome",
    "heartbeat_supervisor",
    "install_signal_handlers",
    "main",
    "run_one_claimed_job",
    "run_worker",
]
