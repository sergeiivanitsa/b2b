"""Durable write-side primitives for Company Card narrative work.

Public resolvers intentionally do not import this module.  Every worker
mutation is fenced, every clock value is supplied by the caller, and the
Gateway boundary is crossed only after :func:`mark_dispatching` commits.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from zoneinfo import ZoneInfo
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.company_reports.company_card_v2.narrative.catalog import (
    FALLBACK_CATALOG_VERSION,
    FALLBACK_DESCRIPTION,
    FALLBACK_PROFILE_ID,
    FALLBACK_RENDERER_VERSION,
)
from product_api.company_reports.company_card_v2.narrative.identity import (
    ArtifactIdentityV1,
    FallbackIdentityV1,
    GenerationIdentityV2,
    identity_key,
)

from .models import (
    CompanyCardNarrativeArtifact,
    CompanyCardNarrativeBudgetReservation,
    CompanyCardNarrativeBudgetWindow,
    CompanyCardNarrativeJob,
    CompanyCardNarrativeOutbox,
    CompanyCardNarrativeRuntimeControl,
    CompanyReportRecord,
)
from .presentations import append_resolved_h2_pin


_MOSCOW = ZoneInfo("Europe/Moscow")
_LEASED_STATES = {"leased", "dispatching", "dispatched", "validating", "rendered"}
_POST_DISPATCH_STATES = {"dispatching", "dispatched", "validating", "rendered"}
_LOCAL_FAILURE_CODES = {
    "local_report_validation_failed",
    "local_request_build_failed",
    "local_gateway_configuration_failed",
}


class NarrativePersistenceError(RuntimeError):
    pass


class NarrativeStaleOwnership(NarrativePersistenceError):
    pass


class NarrativeBudgetUnavailable(NarrativePersistenceError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class NarrativeJobLease:
    job_id: UUID
    report_id: UUID
    snapshot_hash: str
    generation_key: str
    lease_token: UUID
    fence_generation: int
    lease_expires_at: datetime


@dataclass(frozen=True)
class NarrativeArtifactDraft:
    artifact_identity: str
    resolved_model_version: str
    raw_model_output: str
    validated_render_plan_cjson: bytes
    validated_render_plan_bytes_sha256: str
    rendered_description: str
    statement_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    phrase_trace: tuple[dict[str, object], ...]
    validation_codes: tuple[str, ...]
    renderer_version: str
    rendered_output_bytes_sha256: str


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("narrative clock must be timezone-aware")
    return value.astimezone(UTC)


def narrative_budget_windows(
    now: datetime,
) -> tuple[tuple[str, datetime, datetime], tuple[str, datetime, datetime]]:
    """Return exact daily/monthly Moscow windows without wall-clock reads."""
    local = _aware_utc(now).astimezone(_MOSCOW)
    daily_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = daily_start.replace(day=1)
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return (
        (
            daily_start.date().isoformat(),
            daily_start.astimezone(UTC),
            (daily_start + timedelta(days=1)).astimezone(UTC),
        ),
        (
            month_start.date().isoformat(),
            month_start.astimezone(UTC),
            next_month.astimezone(UTC),
        ),
    )


async def insert_narrative_outbox(
    session: AsyncSession,
    *,
    report_id: UUID,
    snapshot_hash: str,
    now: datetime,
) -> CompanyCardNarrativeOutbox:
    """Idempotently append the report-finalization event in its transaction."""
    now = _aware_utc(now)
    statement = (
        postgresql_insert(CompanyCardNarrativeOutbox)
        .values(
            id=uuid4(),
            report_id=report_id,
            snapshot_hash=snapshot_hash,
            event_kind="initialize_narrative_v1",
            state="pending",
            available_at=now,
        )
        .on_conflict_do_nothing(constraint="uq_company_card_narrative_outbox_event")
        .returning(CompanyCardNarrativeOutbox.id)
    )
    inserted_id = await session.scalar(statement)
    if inserted_id is not None:
        row = await session.get(CompanyCardNarrativeOutbox, inserted_id)
        if row is None:  # pragma: no cover - database RETURNING invariant
            raise NarrativePersistenceError("inserted narrative outbox is unavailable")
        return row
    row = await session.scalar(
        select(CompanyCardNarrativeOutbox)
        .where(
            CompanyCardNarrativeOutbox.report_id == report_id,
            CompanyCardNarrativeOutbox.snapshot_hash == snapshot_hash,
            CompanyCardNarrativeOutbox.event_kind == "initialize_narrative_v1",
        )
        .with_for_update()
    )
    if row is None:  # pragma: no cover - unique conflict must expose a row
        raise NarrativePersistenceError("narrative outbox conflict is invalid")
    return row


async def synchronize_narrative_runtime_control(
    session: AsyncSession,
    *,
    enabled: bool,
    kill_switch: bool,
    daily_limit: int,
    monthly_limit: int,
    concurrency_limit: int,
    now: datetime,
) -> CompanyCardNarrativeRuntimeControl:
    if min(daily_limit, monthly_limit, concurrency_limit) < 0:
        raise ValueError("narrative runtime limits must be non-negative")
    if enabled and (kill_switch or not all((daily_limit, monthly_limit, concurrency_limit))):
        raise ValueError("enabled narrative runtime must be fully open")
    row = await session.get(CompanyCardNarrativeRuntimeControl, 1, with_for_update=True)
    if row is None:
        raise NarrativePersistenceError("narrative runtime control is missing")
    # Zero is the explicit fail-closed kill-switch state and may be applied
    # while an already-fenced lease drains.  Any positive cap, however, must
    # continue to account for every live lease already recorded in the
    # singleton.  This check and the database constraint protect against a
    # configuration rollout silently oversubscribing paid work.
    if concurrency_limit > 0 and concurrency_limit < row.leased_count:
        raise NarrativePersistenceError(
            "narrative concurrency limit is below active leases"
        )
    row.enabled = enabled
    row.kill_switch = kill_switch
    row.daily_limit = daily_limit
    row.monthly_limit = monthly_limit
    row.concurrency_limit = concurrency_limit
    row.updated_at = _aware_utc(now)
    await session.flush()
    return row


async def resolve_exact_narrative_binding(
    session: AsyncSession,
    *,
    report_id: UUID,
    snapshot_hash: str,
    generation_key: str,
) -> CompanyCardNarrativeArtifact | None:
    """SELECT-only exact artifact resolver; it never renders a fallback."""
    return await session.scalar(
        select(CompanyCardNarrativeArtifact).where(
            CompanyCardNarrativeArtifact.report_id == report_id,
            CompanyCardNarrativeArtifact.snapshot_hash == snapshot_hash,
            CompanyCardNarrativeArtifact.generation_key == generation_key,
        )
    )


async def initialize_narrative_generation(
    session: AsyncSession,
    *,
    report_id: UUID,
    snapshot_hash: str,
    generation_key: str,
    identity: GenerationIdentityV2,
    now: datetime,
) -> CompanyCardNarrativeJob:
    """Create the one exact V2 job for an immutable report generation."""
    if not isinstance(identity, GenerationIdentityV2):
        raise NarrativePersistenceError("narrative generation identity must be V2")
    identity_payload = asdict(identity)
    if (
        identity.report_id != str(report_id)
        or identity.snapshot_hash != snapshot_hash
        or identity_key(identity) != generation_key
    ):
        raise NarrativePersistenceError("narrative generation identity is invalid")
    report = await session.get(CompanyReportRecord, report_id, with_for_update=True)
    if (
        report is None
        or report.snapshot_hash != snapshot_hash
        or report.lifecycle_status not in {"complete", "partial"}
    ):
        raise NarrativePersistenceError("narrative report identity is invalid")
    row = await session.scalar(
        select(CompanyCardNarrativeJob)
        .where(CompanyCardNarrativeJob.generation_key == generation_key)
        .with_for_update()
    )
    if row is not None:
        if (
            row.report_id != report_id
            or row.snapshot_hash != snapshot_hash
            or row.identity_version != "GenerationIdentityV2"
            or row.generation_identity != identity_payload
        ):
            raise NarrativePersistenceError("narrative generation key conflicts")
        return row
    row = CompanyCardNarrativeJob(
        report_id=report_id,
        snapshot_hash=snapshot_hash,
        generation_key=generation_key,
        identity_version="GenerationIdentityV2",
        generation_identity=identity_payload,
        state="ready",
        available_at=_aware_utc(now),
    )
    session.add(row)
    await session.flush()
    return row


async def _window_rows(
    session: AsyncSession,
    *,
    now: datetime,
) -> tuple[CompanyCardNarrativeBudgetWindow, CompanyCardNarrativeBudgetWindow]:
    daily, monthly = narrative_budget_windows(now)
    result: list[CompanyCardNarrativeBudgetWindow] = []
    for kind, values in (("daily", daily), ("monthly", monthly)):
        _label, starts_at, ends_at = values
        local_date = starts_at.astimezone(_MOSCOW).date()
        row = await session.get(
            CompanyCardNarrativeBudgetWindow,
            (kind, local_date),
            with_for_update=True,
        )
        if row is None:
            row = CompanyCardNarrativeBudgetWindow(
                period_kind=kind,
                period_start_local=local_date,
                starts_at_utc=starts_at,
                ends_at_utc=ends_at,
                reserved_count=0,
                consumed_count=0,
            )
            session.add(row)
            await session.flush()
        elif row.starts_at_utc != starts_at or row.ends_at_utc != ends_at:
            raise NarrativePersistenceError("narrative budget window identity is invalid")
        result.append(row)
    return result[0], result[1]


async def reserve_or_rereserve_dispatch_credit(
    session: AsyncSession,
    *,
    generation_key: str,
    now: datetime,
) -> CompanyCardNarrativeBudgetReservation:
    """Reserve one credit under the singleton lock and both Moscow windows."""
    now = _aware_utc(now)
    control = await session.get(CompanyCardNarrativeRuntimeControl, 1, with_for_update=True)
    if control is None or not control.enabled or control.kill_switch:
        raise NarrativeBudgetUnavailable("narrative_runtime_closed")
    if not all((control.daily_limit, control.monthly_limit, control.concurrency_limit)):
        raise NarrativeBudgetUnavailable("narrative_runtime_closed")
    reservation = await session.get(
        CompanyCardNarrativeBudgetReservation,
        generation_key,
        with_for_update=True,
    )
    if reservation is not None and reservation.state == "reserved":
        return reservation
    if reservation is not None and reservation.state == "consumed":
        raise NarrativeBudgetUnavailable("dispatch_credit_consumed")
    if reservation is not None and reservation.reservation_epoch >= 3:
        raise NarrativeBudgetUnavailable("local_attempts_exhausted")
    job = await session.scalar(
        select(CompanyCardNarrativeJob)
        .where(CompanyCardNarrativeJob.generation_key == generation_key)
        .with_for_update()
    )
    if job is None or job.state not in {"ready", "pre_dispatch_failed"}:
        raise NarrativePersistenceError("narrative job is not reservable")

    daily, monthly = await _window_rows(session, now=now)
    if daily.reserved_count + daily.consumed_count >= control.daily_limit:
        raise NarrativeBudgetUnavailable("daily_budget_exhausted")
    if monthly.reserved_count + monthly.consumed_count >= control.monthly_limit:
        raise NarrativeBudgetUnavailable("monthly_budget_exhausted")
    daily.reserved_count += 1
    monthly.reserved_count += 1
    if reservation is None:
        reservation = CompanyCardNarrativeBudgetReservation(
            generation_key=generation_key,
            dispatch_credit=1,
            state="reserved",
            daily_period_kind="daily",
            daily_period_start_local=daily.period_start_local,
            monthly_period_kind="monthly",
            monthly_period_start_local=monthly.period_start_local,
            reservation_epoch=1,
            reserved_at=now,
        )
        session.add(reservation)
    else:
        reservation.state = "reserved"
        reservation.daily_period_kind = "daily"
        reservation.daily_period_start_local = daily.period_start_local
        reservation.monthly_period_kind = "monthly"
        reservation.monthly_period_start_local = monthly.period_start_local
        reservation.reservation_epoch += 1
        reservation.reserved_at = now
        reservation.release_code = None
        reservation.consumed_at = None
    if job.state == "pre_dispatch_failed":
        job.state = "ready"
        job.available_at = now
    await session.flush()
    return reservation


def job_lease(row: CompanyCardNarrativeJob) -> NarrativeJobLease:
    if row.state not in _LEASED_STATES or row.lease_token is None or row.lease_expires_at is None:
        raise NarrativeStaleOwnership("narrative job is not leased")
    return NarrativeJobLease(
        job_id=row.id,
        report_id=row.report_id,
        snapshot_hash=row.snapshot_hash,
        generation_key=row.generation_key,
        lease_token=row.lease_token,
        fence_generation=row.fence_generation,
        lease_expires_at=row.lease_expires_at,
    )


async def claim_narrative_job(
    session: AsyncSession,
    *,
    now: datetime,
    lease_seconds: int,
) -> CompanyCardNarrativeJob | None:
    now = _aware_utc(now)
    if lease_seconds <= 0:
        raise ValueError("narrative job lease must be positive")
    control = await session.get(CompanyCardNarrativeRuntimeControl, 1, with_for_update=True)
    if (
        control is None
        or not control.enabled
        or control.kill_switch
        or not all((control.daily_limit, control.monthly_limit, control.concurrency_limit))
        or control.leased_count >= control.concurrency_limit
    ):
        return None
    row = await session.scalar(
        select(CompanyCardNarrativeJob)
        .join(
            CompanyCardNarrativeBudgetReservation,
            CompanyCardNarrativeBudgetReservation.generation_key
            == CompanyCardNarrativeJob.generation_key,
        )
        .where(
            CompanyCardNarrativeJob.state == "ready",
            CompanyCardNarrativeJob.available_at <= now,
            CompanyCardNarrativeBudgetReservation.state == "reserved",
        )
        .order_by(CompanyCardNarrativeJob.available_at, CompanyCardNarrativeJob.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if row is None:
        return None
    row.state = "leased"
    row.lease_token = uuid4()
    row.lease_expires_at = now + timedelta(seconds=lease_seconds)
    row.fence_generation += 1
    control.leased_count += 1
    await session.flush()
    return row


async def _owned_job(
    session: AsyncSession,
    *,
    lease: NarrativeJobLease,
    now: datetime,
    states: set[str],
) -> CompanyCardNarrativeJob:
    row = await session.get(CompanyCardNarrativeJob, lease.job_id, with_for_update=True)
    if (
        row is None
        or row.report_id != lease.report_id
        or row.snapshot_hash != lease.snapshot_hash
        or row.generation_key != lease.generation_key
        or row.state not in states
        or row.lease_token != lease.lease_token
        or row.fence_generation != lease.fence_generation
        or row.lease_expires_at is None
        or row.lease_expires_at <= _aware_utc(now)
    ):
        raise NarrativeStaleOwnership("stale narrative job ownership")
    return row


async def heartbeat_narrative_job(
    session: AsyncSession,
    *,
    lease: NarrativeJobLease,
    now: datetime,
    lease_seconds: int,
) -> NarrativeJobLease:
    if lease_seconds <= 0:
        raise ValueError("narrative job lease must be positive")
    row = await _owned_job(session, lease=lease, now=now, states=_LEASED_STATES)
    row.lease_expires_at = _aware_utc(now) + timedelta(seconds=lease_seconds)
    await session.flush()
    return job_lease(row)


async def _locked_reservation_windows(
    session: AsyncSession,
    reservation: CompanyCardNarrativeBudgetReservation,
) -> tuple[CompanyCardNarrativeBudgetWindow, CompanyCardNarrativeBudgetWindow]:
    daily = await session.get(
        CompanyCardNarrativeBudgetWindow,
        (reservation.daily_period_kind, reservation.daily_period_start_local),
        with_for_update=True,
    )
    monthly = await session.get(
        CompanyCardNarrativeBudgetWindow,
        (reservation.monthly_period_kind, reservation.monthly_period_start_local),
        with_for_update=True,
    )
    if daily is None or monthly is None:
        raise NarrativePersistenceError("narrative reservation window is missing")
    return daily, monthly


async def _release_concurrency_slot(
    session: AsyncSession,
) -> CompanyCardNarrativeRuntimeControl:
    control = await session.get(CompanyCardNarrativeRuntimeControl, 1, with_for_update=True)
    if control is None or control.leased_count <= 0:
        raise NarrativePersistenceError("narrative concurrency counter is invalid")
    control.leased_count -= 1
    return control


async def mark_dispatching(
    session: AsyncSession,
    *,
    lease: NarrativeJobLease,
    dispatch_id: UUID,
    now: datetime,
) -> CompanyCardNarrativeJob:
    """Consume the credit and durably write the dispatch marker atomically."""
    now = _aware_utc(now)
    control = await session.get(CompanyCardNarrativeRuntimeControl, 1, with_for_update=True)
    if (
        control is None
        or not control.enabled
        or control.kill_switch
        or not all(
            (control.daily_limit, control.monthly_limit, control.concurrency_limit)
        )
        or control.leased_count <= 0
        or control.leased_count > control.concurrency_limit
    ):
        raise NarrativeBudgetUnavailable("narrative_runtime_closed")
    row = await _owned_job(session, lease=lease, now=now, states={"leased"})
    reservation = await session.get(
        CompanyCardNarrativeBudgetReservation,
        row.generation_key,
        with_for_update=True,
    )
    if reservation is None or reservation.state != "reserved":
        raise NarrativeBudgetUnavailable("dispatch_credit_unavailable")
    daily, monthly = await _locked_reservation_windows(session, reservation)
    if daily.reserved_count <= 0 or monthly.reserved_count <= 0:
        raise NarrativePersistenceError("narrative reserved counters are invalid")
    daily.reserved_count -= 1
    monthly.reserved_count -= 1
    daily.consumed_count += 1
    monthly.consumed_count += 1
    reservation.state = "consumed"
    reservation.consumed_at = now
    row.state = "dispatching"
    row.gateway_dispatch_id = dispatch_id
    row.dispatch_started_at = now
    await session.flush()
    return row


async def record_gateway_response(
    session: AsyncSession,
    *,
    lease: NarrativeJobLease,
    resolved_model_version: str,
    now: datetime,
) -> CompanyCardNarrativeJob:
    if not isinstance(resolved_model_version, str) or not resolved_model_version.strip() or len(resolved_model_version) > 255:
        raise NarrativePersistenceError("resolved narrative model is invalid")
    row = await _owned_job(session, lease=lease, now=now, states={"dispatching"})
    row.state = "dispatched"
    row.response_received_at = _aware_utc(now)
    row.resolved_model_version = resolved_model_version
    await session.flush()
    return row


async def mark_narrative_validating(
    session: AsyncSession,
    *,
    lease: NarrativeJobLease,
    now: datetime,
) -> CompanyCardNarrativeJob:
    row = await _owned_job(session, lease=lease, now=now, states={"dispatched"})
    row.state = "validating"
    await session.flush()
    return row


async def release_pre_dispatch_reservation(
    session: AsyncSession,
    *,
    lease: NarrativeJobLease,
    failure_code: str,
    now: datetime,
) -> CompanyCardNarrativeJob:
    """Release a provably local failure and consume one of three epochs."""
    if failure_code not in _LOCAL_FAILURE_CODES:
        raise NarrativePersistenceError("pre-dispatch failure code is not allowlisted")
    now = _aware_utc(now)
    row = await _owned_job(session, lease=lease, now=now, states={"leased"})
    if any(
        value is not None
        for value in (
            row.gateway_dispatch_id,
            row.dispatch_started_at,
            row.response_received_at,
            row.resolved_model_version,
        )
    ):
        raise NarrativePersistenceError("dispatch marker forbids local release")
    reservation = await session.get(
        CompanyCardNarrativeBudgetReservation,
        row.generation_key,
        with_for_update=True,
    )
    if reservation is None or reservation.state != "reserved":
        raise NarrativePersistenceError("only reserved narrative credit may be released")
    daily, monthly = await _locked_reservation_windows(session, reservation)
    if daily.reserved_count <= 0 or monthly.reserved_count <= 0:
        raise NarrativePersistenceError("narrative reserved counters are invalid")
    daily.reserved_count -= 1
    monthly.reserved_count -= 1
    reservation.state = "released"
    reservation.last_released_at = now
    reservation.release_code = failure_code
    row.local_attempt_count += 1
    row.state = "pre_dispatch_failed"
    row.lease_token = None
    row.lease_expires_at = None
    await _release_concurrency_slot(session)
    await session.flush()
    return row


async def _fallback_artifact(
    session: AsyncSession,
    *,
    job: CompanyCardNarrativeJob,
    now: datetime,
) -> CompanyCardNarrativeArtifact:
    rendered_hash = sha256(FALLBACK_DESCRIPTION.encode("utf-8")).hexdigest()
    fallback_identity = identity_key(
        FallbackIdentityV1(
            generation_key=job.generation_key,
            fallback_catalog_version=FALLBACK_CATALOG_VERSION,
            fallback_profile_id=FALLBACK_PROFILE_ID,
            renderer_version=FALLBACK_RENDERER_VERSION,
            rendered_output_bytes_sha256=rendered_hash,
        )
    )
    existing = await session.scalar(
        select(CompanyCardNarrativeArtifact)
        .where(CompanyCardNarrativeArtifact.generation_key == job.generation_key)
        .with_for_update()
    )
    if existing is not None:
        if (
            existing.report_id != job.report_id
            or existing.snapshot_hash != job.snapshot_hash
            or existing.binding_kind != "fallback"
            or existing.binding_key != fallback_identity
            or existing.fallback_identity != fallback_identity
            or existing.artifact_identity is not None
            or existing.resolved_model_version is not None
            or existing.raw_model_output is not None
            or existing.validated_render_plan_cjson is not None
            or existing.validated_render_plan_bytes_sha256 is not None
            or existing.rendered_description != FALLBACK_DESCRIPTION
            or existing.rendered_comments != []
            or existing.statement_ids != [FALLBACK_PROFILE_ID]
            or existing.evidence_ids != []
            or existing.validation_codes != []
            or existing.phrase_trace
            != [
                {
                    "scalar_start": 0,
                    "scalar_end": len(FALLBACK_DESCRIPTION),
                    "statement_id": FALLBACK_PROFILE_ID,
                    "evidence_ids": [],
                }
            ]
            or existing.renderer_version != FALLBACK_RENDERER_VERSION
            or existing.rendered_output_bytes_sha256 != rendered_hash
        ):
            raise NarrativePersistenceError("saved narrative fallback conflicts")
        return existing
    artifact = CompanyCardNarrativeArtifact(
        report_id=job.report_id,
        snapshot_hash=job.snapshot_hash,
        generation_key=job.generation_key,
        binding_kind="fallback",
        binding_key=fallback_identity,
        artifact_identity=None,
        fallback_identity=fallback_identity,
        resolved_model_version=None,
        raw_model_output=None,
        validated_render_plan_cjson=None,
        validated_render_plan_bytes_sha256=None,
        rendered_description=FALLBACK_DESCRIPTION,
        rendered_comments=[],
        statement_ids=[FALLBACK_PROFILE_ID],
        evidence_ids=[],
        phrase_trace=[
            {
                "scalar_start": 0,
                "scalar_end": len(FALLBACK_DESCRIPTION),
                "statement_id": FALLBACK_PROFILE_ID,
                "evidence_ids": [],
            }
        ],
        # The universal fallback artifact is content-identical for every
        # terminal reason. Operational failure codes stay on the job row.
        validation_codes=[],
        renderer_version=FALLBACK_RENDERER_VERSION,
        rendered_output_bytes_sha256=rendered_hash,
        created_at=_aware_utc(now),
    )
    session.add(artifact)
    await session.flush()
    return artifact


async def materialize_saved_fallback(
    session: AsyncSession,
    *,
    generation_key: str,
    validation_codes: tuple[str, ...],
    now: datetime,
) -> CompanyCardNarrativeArtifact:
    if any(not code or len(code) > 64 for code in validation_codes):
        raise NarrativePersistenceError("fallback validation code is invalid")
    job = await session.scalar(
        select(CompanyCardNarrativeJob)
        .where(CompanyCardNarrativeJob.generation_key == generation_key)
        .with_for_update()
    )
    if job is None:
        raise NarrativePersistenceError("fallback generation is missing")
    return await _fallback_artifact(
        session,
        job=job,
        now=now,
    )


async def _bind_artifact(
    session: AsyncSession,
    *,
    job: CompanyCardNarrativeJob,
    artifact: CompanyCardNarrativeArtifact,
    projection_digest: str | None,
) -> None:
    report = await session.get(CompanyReportRecord, job.report_id, with_for_update=True)
    if report is None or report.snapshot_hash != job.snapshot_hash:
        raise NarrativePersistenceError("artifact report identity is invalid")
    if report.report_version == "3":
        if projection_digest is None:
            raise NarrativePersistenceError("v3 artifact projection digest is required")
        await append_resolved_h2_pin(
            session,
            report=report,
            artifact=artifact,
            projection_digest=projection_digest,
        )
    elif report.report_version in {"1", "2"}:
        if projection_digest is not None:
            raise NarrativePersistenceError("legacy fallback cannot own an H2 pin")
    else:
        raise NarrativePersistenceError("artifact report version is invalid")


async def finalize_unleased_fallback(
    session: AsyncSession,
    *,
    generation_key: str,
    validation_code: str,
    projection_digest: str | None,
    now: datetime,
) -> CompanyCardNarrativeJob:
    job = await session.scalar(
        select(CompanyCardNarrativeJob)
        .where(CompanyCardNarrativeJob.generation_key == generation_key)
        .with_for_update()
    )
    if job is None:
        raise NarrativePersistenceError("fallback job is missing")
    if job.state == "fallback_finalized":
        if job.artifact_id is None:
            raise NarrativePersistenceError("finalized fallback artifact is missing")
        return job
    if job.state not in {"ready", "pre_dispatch_failed"} or job.lease_token is not None:
        raise NarrativePersistenceError("job is not eligible for pre-dispatch fallback")
    artifact = await _fallback_artifact(
        session,
        job=job,
        now=now,
    )
    await _bind_artifact(
        session,
        job=job,
        artifact=artifact,
        projection_digest=projection_digest,
    )
    job.state = "fallback_finalized"
    job.artifact_id = artifact.id
    job.validation_codes = [validation_code]
    job.lease_token = None
    job.lease_expires_at = None
    await session.flush()
    return job


async def finalize_fallback_after_dispatch(
    session: AsyncSession,
    *,
    lease: NarrativeJobLease,
    validation_code: str,
    projection_digest: str,
    now: datetime,
) -> CompanyCardNarrativeJob:
    current = await session.get(CompanyCardNarrativeJob, lease.job_id, with_for_update=True)
    if current is not None and current.state == "fallback_finalized":
        if current.artifact_id is None:
            raise NarrativePersistenceError("finalized fallback artifact is missing")
        return current
    job = await _owned_job(
        session,
        lease=lease,
        now=now,
        states=_POST_DISPATCH_STATES,
    )
    reservation = await session.get(
        CompanyCardNarrativeBudgetReservation,
        job.generation_key,
        with_for_update=True,
    )
    if reservation is None or reservation.state != "consumed":
        raise NarrativePersistenceError("post-dispatch fallback has no consumed credit")
    artifact = await _fallback_artifact(
        session,
        job=job,
        now=now,
    )
    await _bind_artifact(
        session,
        job=job,
        artifact=artifact,
        projection_digest=projection_digest,
    )
    job.state = "fallback_finalized"
    job.artifact_id = artifact.id
    job.validation_codes = [validation_code]
    job.lease_token = None
    job.lease_expires_at = None
    await _release_concurrency_slot(session)
    await session.flush()
    return job


def _validate_artifact_draft(job: CompanyCardNarrativeJob, draft: NarrativeArtifactDraft) -> None:
    if (
        not draft.resolved_model_version.strip()
        or len(draft.resolved_model_version) > 255
        or len(draft.raw_model_output.encode("utf-8")) > 16384
        or len(draft.validated_render_plan_cjson) > 16384
        or sha256(draft.validated_render_plan_cjson).hexdigest()
        != draft.validated_render_plan_bytes_sha256
        or sha256(draft.rendered_description.encode("utf-8")).hexdigest()
        != draft.rendered_output_bytes_sha256
        or draft.artifact_identity
        != identity_key(
            ArtifactIdentityV1(
                generation_key=job.generation_key,
                resolved_model_version=draft.resolved_model_version,
                validated_render_plan_bytes_sha256=draft.validated_render_plan_bytes_sha256,
                rendered_output_bytes_sha256=draft.rendered_output_bytes_sha256,
            )
        )
        or not draft.statement_ids
        or not draft.phrase_trace
    ):
        raise NarrativePersistenceError("narrative artifact draft is invalid")


async def finalize_narrative_artifact(
    session: AsyncSession,
    *,
    lease: NarrativeJobLease,
    draft: NarrativeArtifactDraft,
    projection_digest: str,
    now: datetime,
) -> CompanyCardNarrativeJob:
    current = await session.get(CompanyCardNarrativeJob, lease.job_id, with_for_update=True)
    if current is not None and current.state == "finalized":
        if current.artifact_id is None:
            raise NarrativePersistenceError("finalized narrative artifact is missing")
        return current
    job = await _owned_job(session, lease=lease, now=now, states={"validating", "rendered"})
    if job.resolved_model_version != draft.resolved_model_version:
        raise NarrativePersistenceError("resolved narrative model changed")
    reservation = await session.get(
        CompanyCardNarrativeBudgetReservation,
        job.generation_key,
        with_for_update=True,
    )
    if reservation is None or reservation.state != "consumed":
        raise NarrativePersistenceError("narrative artifact has no consumed credit")
    _validate_artifact_draft(job, draft)
    existing = await session.scalar(
        select(CompanyCardNarrativeArtifact)
        .where(CompanyCardNarrativeArtifact.generation_key == job.generation_key)
        .with_for_update()
    )
    if existing is None:
        artifact = CompanyCardNarrativeArtifact(
            report_id=job.report_id,
            snapshot_hash=job.snapshot_hash,
            generation_key=job.generation_key,
            binding_kind="artifact",
            binding_key=draft.artifact_identity,
            artifact_identity=draft.artifact_identity,
            fallback_identity=None,
            resolved_model_version=draft.resolved_model_version,
            raw_model_output=draft.raw_model_output,
            validated_render_plan_cjson=draft.validated_render_plan_cjson,
            validated_render_plan_bytes_sha256=draft.validated_render_plan_bytes_sha256,
            rendered_description=draft.rendered_description,
            rendered_comments=[],
            statement_ids=list(draft.statement_ids),
            evidence_ids=list(draft.evidence_ids),
            phrase_trace=[dict(item) for item in draft.phrase_trace],
            validation_codes=list(draft.validation_codes),
            renderer_version=draft.renderer_version,
            rendered_output_bytes_sha256=draft.rendered_output_bytes_sha256,
            created_at=_aware_utc(now),
        )
        session.add(artifact)
        await session.flush()
    else:
        artifact = existing
        if (
            artifact.binding_kind != "artifact"
            or artifact.binding_key != draft.artifact_identity
            or artifact.artifact_identity != draft.artifact_identity
            or artifact.report_id != job.report_id
            or artifact.snapshot_hash != job.snapshot_hash
            or artifact.resolved_model_version != draft.resolved_model_version
            or artifact.raw_model_output != draft.raw_model_output
            or bytes(artifact.validated_render_plan_cjson or b"")
            != draft.validated_render_plan_cjson
            or artifact.validated_render_plan_bytes_sha256
            != draft.validated_render_plan_bytes_sha256
            or artifact.rendered_description != draft.rendered_description
            or artifact.rendered_output_bytes_sha256
            != draft.rendered_output_bytes_sha256
        ):
            raise NarrativePersistenceError("narrative artifact conflicts")
    await _bind_artifact(
        session,
        job=job,
        artifact=artifact,
        projection_digest=projection_digest,
    )
    job.state = "finalized"
    job.artifact_id = artifact.id
    job.validation_codes = list(draft.validation_codes)
    job.lease_token = None
    job.lease_expires_at = None
    await _release_concurrency_slot(session)
    await session.flush()
    return job


async def select_expired_narrative_job(
    session: AsyncSession,
    *,
    now: datetime,
) -> CompanyCardNarrativeJob | None:
    return await session.scalar(
        select(CompanyCardNarrativeJob)
        .where(
            CompanyCardNarrativeJob.state.in_(_LEASED_STATES),
            CompanyCardNarrativeJob.lease_expires_at <= _aware_utc(now),
        )
        .order_by(CompanyCardNarrativeJob.lease_expires_at, CompanyCardNarrativeJob.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )


async def expire_pre_dispatch_job(
    session: AsyncSession,
    *,
    job: CompanyCardNarrativeJob,
    now: datetime,
) -> CompanyCardNarrativeJob:
    now = _aware_utc(now)
    if (
        job.state != "leased"
        or job.lease_expires_at is None
        or job.lease_expires_at > now
        or job.gateway_dispatch_id is not None
    ):
        raise NarrativePersistenceError("narrative pre-dispatch expiry is invalid")
    reservation = await session.get(
        CompanyCardNarrativeBudgetReservation,
        job.generation_key,
        with_for_update=True,
    )
    if reservation is None or reservation.state != "reserved":
        raise NarrativePersistenceError("expired narrative job has no reservation")
    daily, monthly = await _locked_reservation_windows(session, reservation)
    if daily.reserved_count <= 0 or monthly.reserved_count <= 0:
        raise NarrativePersistenceError("expired narrative counters are invalid")
    daily.reserved_count -= 1
    monthly.reserved_count -= 1
    reservation.state = "released"
    reservation.last_released_at = now
    reservation.release_code = "local_report_validation_failed"
    job.local_attempt_count += 1
    job.state = "pre_dispatch_failed"
    job.lease_token = None
    job.lease_expires_at = None
    job.fence_generation += 1
    await _release_concurrency_slot(session)
    await session.flush()
    return job


async def finalize_expired_post_dispatch_fallback(
    session: AsyncSession,
    *,
    job: CompanyCardNarrativeJob,
    validation_code: str,
    projection_digest: str,
    now: datetime,
) -> CompanyCardNarrativeJob:
    now = _aware_utc(now)
    if (
        job.state not in _POST_DISPATCH_STATES
        or job.lease_expires_at is None
        or job.lease_expires_at > now
        or job.gateway_dispatch_id is None
        or job.dispatch_started_at is None
    ):
        raise NarrativePersistenceError("narrative post-dispatch expiry is invalid")
    reservation = await session.get(
        CompanyCardNarrativeBudgetReservation,
        job.generation_key,
        with_for_update=True,
    )
    if reservation is None or reservation.state != "consumed":
        raise NarrativePersistenceError("expired dispatch has no consumed credit")
    artifact = await _fallback_artifact(
        session,
        job=job,
        now=now,
    )
    await _bind_artifact(
        session,
        job=job,
        artifact=artifact,
        projection_digest=projection_digest,
    )
    job.state = "fallback_finalized"
    job.artifact_id = artifact.id
    job.validation_codes = [validation_code]
    job.lease_token = None
    job.lease_expires_at = None
    job.fence_generation += 1
    await _release_concurrency_slot(session)
    await session.flush()
    return job


async def finalize_unpublishable_job(
    session: AsyncSession,
    *,
    job: CompanyCardNarrativeJob,
    validation_code: str,
    now: datetime,
) -> CompanyCardNarrativeJob:
    """Close integrity-corrupt work without creating a misleading binding.

    A universal fallback may only be pinned against a snapshot whose stored
    bytes still match its hash. If that invariant is broken after outbox
    initialization, the paid boundary remains closed and the public result
    stays deliberately unavailable.
    """
    now = _aware_utc(now)
    if job.state == "pre_dispatch_failed":
        if job.lease_token is not None or job.lease_expires_at is not None:
            raise NarrativePersistenceError("unpublishable pre-dispatch lease is invalid")
    elif job.state in _POST_DISPATCH_STATES:
        if job.lease_expires_at is None or job.lease_expires_at > now:
            raise NarrativePersistenceError("unpublishable dispatch is not expired")
        reservation = await session.get(
            CompanyCardNarrativeBudgetReservation,
            job.generation_key,
            with_for_update=True,
        )
        if reservation is None or reservation.state != "consumed":
            raise NarrativePersistenceError("unpublishable dispatch has no consumed credit")
        job.fence_generation += 1
        await _release_concurrency_slot(session)
    else:
        raise NarrativePersistenceError("job cannot be closed as unpublishable")
    job.state = "fallback_finalized"
    job.artifact_id = None
    job.validation_codes = [validation_code]
    job.lease_token = None
    job.lease_expires_at = None
    await session.flush()
    return job


__all__ = [
    "NarrativeArtifactDraft",
    "NarrativeBudgetUnavailable",
    "NarrativeJobLease",
    "NarrativePersistenceError",
    "NarrativeStaleOwnership",
    "claim_narrative_job",
    "expire_pre_dispatch_job",
    "finalize_expired_post_dispatch_fallback",
    "finalize_fallback_after_dispatch",
    "finalize_narrative_artifact",
    "finalize_unleased_fallback",
    "finalize_unpublishable_job",
    "heartbeat_narrative_job",
    "initialize_narrative_generation",
    "insert_narrative_outbox",
    "job_lease",
    "mark_dispatching",
    "mark_narrative_validating",
    "materialize_saved_fallback",
    "narrative_budget_windows",
    "record_gateway_response",
    "release_pre_dispatch_reservation",
    "reserve_or_rereserve_dispatch_credit",
    "resolve_exact_narrative_binding",
    "select_expired_narrative_job",
    "synchronize_narrative_runtime_control",
]
