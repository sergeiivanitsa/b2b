from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    CompanyCardNarrativeBudgetReservation,
    CompanyCardNarrativeJob,
    CompanyCardNarrativeOutbox,
)


class NarrativeOutboxOwnershipError(RuntimeError):
    """A stale reconciler attempted to mutate durable outbox work."""


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("narrative outbox clock must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class NarrativeOutboxLease:
    outbox_id: UUID
    report_id: UUID
    snapshot_hash: str
    lease_token: UUID
    fence_generation: int
    lease_expires_at: datetime


def outbox_lease(row: CompanyCardNarrativeOutbox) -> NarrativeOutboxLease:
    if row.state != "leased" or row.lease_token is None or row.lease_expires_at is None:
        raise NarrativeOutboxOwnershipError("narrative outbox is not leased")
    return NarrativeOutboxLease(
        outbox_id=row.id,
        report_id=row.report_id,
        snapshot_hash=row.snapshot_hash,
        lease_token=row.lease_token,
        fence_generation=row.fence_generation,
        lease_expires_at=row.lease_expires_at,
    )


async def claim_narrative_outbox(
    session: AsyncSession,
    *,
    now: datetime,
    lease_seconds: int = 60,
) -> CompanyCardNarrativeOutbox | None:
    """Lease pending work or reclaim one expired reconciler lease.

    The caller commits this transition before performing reconciliation. A
    third expired lease is terminalized instead of being replayed forever.
    """
    if lease_seconds <= 0:
        raise ValueError("narrative outbox lease must be positive")
    now = _aware_utc(now)

    exhausted = await session.scalar(
        select(CompanyCardNarrativeOutbox)
        .where(
            CompanyCardNarrativeOutbox.state == "leased",
            CompanyCardNarrativeOutbox.lease_expires_at <= now,
            CompanyCardNarrativeOutbox.attempt_count >= 3,
        )
        .order_by(CompanyCardNarrativeOutbox.available_at, CompanyCardNarrativeOutbox.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if exhausted is not None:
        exhausted.state = "terminal"
        exhausted.failure_code = "outbox_attempts_exhausted"
        exhausted.lease_token = None
        exhausted.lease_expires_at = None
        await session.flush()
        return None

    row = await session.scalar(
        select(CompanyCardNarrativeOutbox)
        .where(
            CompanyCardNarrativeOutbox.available_at <= now,
            or_(
                CompanyCardNarrativeOutbox.state == "pending",
                (
                    (CompanyCardNarrativeOutbox.state == "leased")
                    & (CompanyCardNarrativeOutbox.lease_expires_at <= now)
                    & (CompanyCardNarrativeOutbox.attempt_count < 3)
                ),
            ),
        )
        .order_by(CompanyCardNarrativeOutbox.available_at, CompanyCardNarrativeOutbox.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if row is None:
        return None
    row.state = "leased"
    row.attempt_count += 1
    row.lease_token = uuid4()
    row.lease_expires_at = now + timedelta(seconds=lease_seconds)
    row.fence_generation += 1
    await session.flush()
    return row


async def get_claimed_narrative_outbox(
    session: AsyncSession,
    *,
    lease: NarrativeOutboxLease,
    now: datetime,
) -> CompanyCardNarrativeOutbox:
    now = _aware_utc(now)
    row = await session.get(CompanyCardNarrativeOutbox, lease.outbox_id, with_for_update=True)
    if (
        row is None
        or row.state != "leased"
        or row.report_id != lease.report_id
        or row.snapshot_hash != lease.snapshot_hash
        or row.lease_token != lease.lease_token
        or row.fence_generation != lease.fence_generation
        or row.lease_expires_at is None
        or row.lease_expires_at <= now
    ):
        raise NarrativeOutboxOwnershipError("stale narrative outbox ownership")
    return row


async def heartbeat_narrative_outbox(
    session: AsyncSession,
    *,
    lease: NarrativeOutboxLease,
    now: datetime,
    lease_seconds: int = 60,
) -> NarrativeOutboxLease:
    if lease_seconds <= 0:
        raise ValueError("narrative outbox lease must be positive")
    now = _aware_utc(now)
    row = await get_claimed_narrative_outbox(session, lease=lease, now=now)
    row.lease_expires_at = now + timedelta(seconds=lease_seconds)
    await session.flush()
    return outbox_lease(row)


async def mark_narrative_outbox_processed(
    session: AsyncSession,
    *,
    lease: NarrativeOutboxLease,
    generation_key: str,
    now: datetime,
) -> CompanyCardNarrativeOutbox:
    now = _aware_utc(now)
    row = await get_claimed_narrative_outbox(session, lease=lease, now=now)
    job = await session.scalar(
        select(CompanyCardNarrativeJob).where(
            CompanyCardNarrativeJob.generation_key == generation_key,
            CompanyCardNarrativeJob.report_id == row.report_id,
            CompanyCardNarrativeJob.snapshot_hash == row.snapshot_hash,
        )
    )
    if job is None:
        raise NarrativeOutboxOwnershipError("outbox result is not durable")
    reservation = await session.get(
        CompanyCardNarrativeBudgetReservation,
        generation_key,
        with_for_update=True,
    )
    has_saved_result = (
        job.state in {"finalized", "fallback_finalized"}
        and job.artifact_id is not None
    )
    has_dispatch_work = (
        reservation is not None
        and reservation.state in {"reserved", "consumed"}
    )
    if not has_saved_result and not has_dispatch_work:
        raise NarrativeOutboxOwnershipError("outbox result is not durable")
    row.state = "processed"
    row.generation_key = generation_key
    row.processed_at = now
    row.failure_code = None
    row.lease_token = None
    row.lease_expires_at = None
    await session.flush()
    return row


async def mark_narrative_outbox_terminal(
    session: AsyncSession,
    *,
    lease: NarrativeOutboxLease,
    failure_code: str,
    now: datetime,
) -> CompanyCardNarrativeOutbox:
    if not failure_code or len(failure_code) > 64:
        raise ValueError("narrative outbox failure code is invalid")
    now = _aware_utc(now)
    row = await get_claimed_narrative_outbox(session, lease=lease, now=now)
    row.state = "terminal"
    row.failure_code = failure_code
    row.generation_key = None
    row.processed_at = None
    row.lease_token = None
    row.lease_expires_at = None
    await session.flush()
    return row


__all__ = [
    "NarrativeOutboxLease",
    "NarrativeOutboxOwnershipError",
    "claim_narrative_outbox",
    "get_claimed_narrative_outbox",
    "heartbeat_narrative_outbox",
    "mark_narrative_outbox_processed",
    "mark_narrative_outbox_terminal",
    "outbox_lease",
]
