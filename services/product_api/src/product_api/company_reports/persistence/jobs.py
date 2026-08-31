from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import UUID, uuid4

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.company_reports.aggregate import CompanyReport, CURRENT_COMPANY_REPORT_VERSION
from product_api.company_reports.company_card_v2.models import CompanyCardV2Snapshot
from product_api.company_reports.ephemeral_evaluation import (
    evaluate_report_ephemerally,
)
from product_api.providers.datanewton import (
    DataNewtonIdentifierType,
    identify_identifier_type,
    normalize_identifier,
)

from .errors import (
    CompanyReportJobFencingError,
    CompanyReportJobNotFoundError,
    CompanyReportJobStateConflictError,
    CompanyReportPersistenceError,
)
from .models import (
    JOB_FAILED_STATE,
    JOB_QUEUED_STATE,
    JOB_RUNNING_STATE,
    JOB_SUCCEEDED_STATE,
    REPORT_FINAL_STATUSES,
    REPORT_PENDING_STATUS,
    CompanyReportJob,
    CompanyReportRecord,
    CompanyReportSubject,
)
from .repository import (
    finalize_company_card_v2_report,
    finalize_report,
    lock_or_create_subject_for_update,
)

REPORT_EXECUTION_FAILED_CODE = "report_execution_failed"
REPORT_EXECUTION_INTERRUPTED_CODE = "report_execution_interrupted"
REPORT_JOB_PRECONDITION_FAILED_CODE = "report_job_precondition_failed"
H1_WRITER_PROFILE = "h1_legacy_writer_v2"
H1_PRESENTATION_CONTRACT = "company_public_h1_v1"
H2_WRITER_PROFILE = "company_card_v2_writer_v3"
H2_PRESENTATION_CONTRACT = "company_public_h2_v1"

_SAFE_FAILURE_MESSAGES = {
    REPORT_EXECUTION_FAILED_CODE: "company report execution failed",
    REPORT_EXECUTION_INTERRUPTED_CODE: "company report execution was interrupted",
    REPORT_JOB_PRECONDITION_FAILED_CODE: "company report job precondition failed",
}


@dataclass(frozen=True)
class EnqueuedReportJob:
    report_id: UUID
    job_id: UUID
    subject_id: UUID
    lifecycle_status: str
    reused: bool


@dataclass(frozen=True)
class WriterDecision:
    writer_profile: str = H1_WRITER_PROFILE
    report_version: str = CURRENT_COMPANY_REPORT_VERSION
    presentation_contract: str = H1_PRESENTATION_CONTRACT
    rollout_generation: int = 0

    def __post_init__(self) -> None:
        h1 = (self.writer_profile, self.report_version, self.presentation_contract, self.rollout_generation) == (H1_WRITER_PROFILE, CURRENT_COMPANY_REPORT_VERSION, H1_PRESENTATION_CONTRACT, 0)
        h2 = self.writer_profile == H2_WRITER_PROFILE and self.report_version == "3" and self.presentation_contract == H2_PRESENTATION_CONTRACT and self.rollout_generation > 0
        if not (h1 or h2):
            raise ValueError("writer decision is invalid")


@dataclass(frozen=True)
class ClaimedReportJob:
    job_id: UUID
    report_id: UUID
    subject_id: UUID
    normalized_identifier: str
    worker_token: UUID
    claimed_at: datetime
    lease_expires_at: datetime
    writer_profile: str = H1_WRITER_PROFILE
    report_version: str = CURRENT_COMPANY_REPORT_VERSION
    presentation_contract: str = H1_PRESENTATION_CONTRACT
    rollout_generation: int = 0
    fence_generation: int = 0


@dataclass(frozen=True)
class CompletedReportJob:
    report_id: UUID
    lifecycle_status: str
    signals: object
    scoring: object


@dataclass(frozen=True)
class LatestFinalizedReportRecord:
    report_id: UUID
    subject_id: UUID
    lifecycle_status: str
    report_version: str
    started_at: datetime
    generated_at: datetime | None
    finished_at: datetime | None
    fresh_until: datetime | None
    normalized_snapshot: dict[str, object] | None
    snapshot_hash: str | None
    safe_error_snapshot: dict[str, object] | None
    usable_for_public_page: bool
    usable_for_future_scoring: bool
    created_at: datetime


async def enqueue_company_report_job(
    session: AsyncSession,
    identifier: str,
    *,
    report_id_factory: Callable[[], UUID] = uuid4,
    job_id_factory: Callable[[], UUID] = uuid4,
    decision: WriterDecision = WriterDecision(),
) -> EnqueuedReportJob:
    """Create a pending report and queued job, or return the matching active pair.

    The caller owns the transaction and must commit or roll it back.
    """

    normalized, _ = _normalize_inn(identifier)
    subject = await lock_or_create_subject_for_update(session, normalized)

    active_result = await session.execute(
        select(CompanyReportJob)
        .where(
            CompanyReportJob.subject_id == subject.id,
            CompanyReportJob.state.in_((JOB_QUEUED_STATE, JOB_RUNNING_STATE)),
        )
        .order_by(CompanyReportJob.created_at, CompanyReportJob.id)
        .limit(1)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    job = active_result.scalar_one_or_none()
    if job is not None:
        report = await _lock_report(session, job.report_id)
        if (
            job.subject_id != subject.id
            or job.state not in {JOB_QUEUED_STATE, JOB_RUNNING_STATE}
            or report is None
            or report.subject_id != subject.id
            or report.lifecycle_status != REPORT_PENDING_STATUS
        ):
            raise CompanyReportJobStateConflictError(
                "active job does not have a matching pending report"
            )
        if not _job_matches_decision(job, report, decision):
            raise CompanyReportJobStateConflictError("report writer profile conflict")
        return EnqueuedReportJob(
            report_id=report.id,
            job_id=job.id,
            subject_id=subject.id,
            lifecycle_status=report.lifecycle_status,
            reused=True,
        )

    pending_result = await session.execute(
        select(CompanyReportRecord)
        .where(
            CompanyReportRecord.subject_id == subject.id,
            CompanyReportRecord.lifecycle_status == REPORT_PENDING_STATUS,
        )
        .order_by(desc(CompanyReportRecord.created_at), desc(CompanyReportRecord.id))
        .limit(1)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if pending_result.scalar_one_or_none() is not None:
        raise CompanyReportJobStateConflictError(
            "pending report does not have a matching active job"
        )

    db_time = await database_wall_clock(session)
    report_id = report_id_factory()
    job_id = job_id_factory()
    report = CompanyReportRecord(
        id=report_id,
        subject_id=subject.id,
        report_version=decision.report_version,
        writer_profile=decision.writer_profile,
        presentation_contract=decision.presentation_contract,
        rollout_generation=decision.rollout_generation,
        lifecycle_status=REPORT_PENDING_STATUS,
        request_id=f"company-report:{report_id}",
        started_at=db_time,
        warnings_snapshot=[],
        usable_for_public_page=False,
        usable_for_future_scoring=False,
    )
    job = CompanyReportJob(
        id=job_id,
        report_id=report_id,
        subject_id=subject.id,
        state=JOB_QUEUED_STATE,
        writer_profile=decision.writer_profile,
        presentation_contract=decision.presentation_contract,
        rollout_generation=decision.rollout_generation,
        fence_generation=0,
        attempt_count=0,
    )
    session.add(report)
    await session.flush()
    session.add(job)
    await session.flush()
    return EnqueuedReportJob(
        report_id=report_id,
        job_id=job_id,
        subject_id=subject.id,
        lifecycle_status=REPORT_PENDING_STATUS,
        reused=False,
    )


async def claim_next_job(
    session: AsyncSession,
    *,
    lease_seconds: int,
    token_factory: Callable[[], UUID] = uuid4,
) -> ClaimedReportJob | None:
    _require_positive_lease(lease_seconds)
    result = await session.execute(
        select(CompanyReportJob)
        .where(CompanyReportJob.state == JOB_QUEUED_STATE)
        .order_by(CompanyReportJob.created_at, CompanyReportJob.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = result.scalar_one_or_none()
    if job is None:
        return None

    report = await _lock_report(session, job.report_id)
    subject = await _get_subject(session, job.subject_id)
    db_time = await database_wall_clock(session)
    if (
        report is None
        or subject is None
        or report.subject_id != job.subject_id
        or report.lifecycle_status != REPORT_PENDING_STATUS
        or not _valid_stored_job_decision(job, report)
    ):
        await _fail_queued_precondition(
            session,
            job=job,
            report=report,
            finished_at=db_time,
        )
        return None

    worker_token = token_factory()
    job.state = JOB_RUNNING_STATE
    job.worker_token = worker_token
    # A lease token alone is not a fence: a reclaimed job must invalidate every
    # earlier claimant even if a stale worker still has its token in memory.
    # The generation is persisted and copied into ``ClaimedReportJob`` below.
    job.fence_generation = (job.fence_generation or 0) + 1
    job.attempt_count = 1
    job.claimed_at = db_time
    job.heartbeat_at = db_time
    job.lease_expires_at = db_time + timedelta(seconds=lease_seconds)
    job.updated_at = db_time
    await session.flush()
    return ClaimedReportJob(
        job_id=job.id,
        report_id=job.report_id,
        subject_id=job.subject_id,
        normalized_identifier=subject.normalized_identifier,
        worker_token=worker_token,
        claimed_at=db_time,
        lease_expires_at=job.lease_expires_at,
        writer_profile=job.writer_profile or H1_WRITER_PROFILE,
        report_version=report.report_version,
        presentation_contract=job.presentation_contract or H1_PRESENTATION_CONTRACT,
        rollout_generation=0 if job.rollout_generation is None else job.rollout_generation,
        fence_generation=0 if job.fence_generation is None else job.fence_generation,
    )


async def heartbeat_job(
    session: AsyncSession,
    *,
    job_id: UUID,
    worker_token: UUID,
    lease_seconds: int,
    claimed: ClaimedReportJob | None = None,
) -> datetime:
    """Extend a live lease from a fresh DB wall clock read after the job lock."""

    _require_positive_lease(lease_seconds)
    job = await _lock_job(session, job_id)
    if job is None:
        raise CompanyReportJobNotFoundError("company report job was not found")
    db_time = await database_wall_clock(session)
    if claimed is not None:
        _assert_claim_matches(job, claimed)
    _assert_live_owner(job, worker_token=worker_token, db_time=db_time)
    job.heartbeat_at = db_time
    job.lease_expires_at = db_time + timedelta(seconds=lease_seconds)
    job.updated_at = db_time
    await session.flush()
    return job.lease_expires_at


async def complete_claimed_job(
    session: AsyncSession,
    *,
    claimed: ClaimedReportJob,
    report: CompanyReport,
    signal_evaluator: Callable[[CompanyReport], Any] | None = None,
    scoring_evaluator: Callable[[Any], Any] | None = None,
    fresh_until: datetime | None = None,
) -> CompletedReportJob:
    job = await _lock_job(session, claimed.job_id)
    if job is None:
        raise CompanyReportJobNotFoundError("company report job was not found")
    stored_report = await _lock_report(session, claimed.report_id)
    db_time = await database_wall_clock(session)
    _assert_claim_matches(job, claimed)
    _assert_live_owner(job, worker_token=claimed.worker_token, db_time=db_time)
    if stored_report is None:
        raise CompanyReportJobStateConflictError("company report was not found")
    if (
        stored_report.id != report.report_id
        or stored_report.subject_id != claimed.subject_id
        or stored_report.lifecycle_status != REPORT_PENDING_STATUS
    ):
        raise CompanyReportJobStateConflictError(
            "company report does not match the claimed job"
        )

    finalized = await finalize_report(
        session,
        report,
        fresh_until=fresh_until,
        finished_at=db_time,
    )
    if signal_evaluator is None and scoring_evaluator is None:
        signals, scoring = evaluate_report_ephemerally(report)
    elif signal_evaluator is not None and scoring_evaluator is not None:
        signals = signal_evaluator(report)
        scoring = scoring_evaluator(signals)
    else:
        raise ValueError("signal and scoring evaluators must be provided together")
    job.state = JOB_SUCCEEDED_STATE
    job.finished_at = db_time
    job.safe_failure_code = None
    job.updated_at = db_time
    await session.flush()
    return CompletedReportJob(
        report_id=finalized.id,
        lifecycle_status=finalized.lifecycle_status,
        signals=signals,
        scoring=scoring,
    )


async def complete_claimed_company_card_v2_job(
    session: AsyncSession,
    *,
    claimed: ClaimedReportJob,
    snapshot: CompanyCardV2Snapshot,
) -> CompletedReportJob:
    """Finalize an injected v3 artifact without provider/signals/scoring."""
    job = await _lock_job(session, claimed.job_id)
    record = await _lock_report(session, claimed.report_id)
    db_time = await database_wall_clock(session)
    if job is None or record is None:
        raise CompanyReportJobNotFoundError("company card v2 job was not found")
    _assert_claim_matches(job, claimed)
    _assert_live_owner(job, worker_token=claimed.worker_token, db_time=db_time)
    if claimed.writer_profile != H2_WRITER_PROFILE or not _valid_stored_job_decision(job, record):
        raise CompanyReportJobStateConflictError("company card v2 writer decision does not match")
    finalized = await finalize_company_card_v2_report(
        session, snapshot, report_id=claimed.report_id, subject_id=claimed.subject_id, finished_at=db_time
    )
    job.state, job.finished_at, job.safe_failure_code, job.updated_at = JOB_SUCCEEDED_STATE, db_time, None, db_time
    await session.flush()
    return CompletedReportJob(report_id=finalized.id, lifecycle_status=finalized.lifecycle_status, signals=None, scoring=None)


async def fail_owned_job(
    session: AsyncSession,
    *,
    claimed: ClaimedReportJob,
    safe_failure_code: str = REPORT_EXECUTION_FAILED_CODE,
) -> None:
    _validate_safe_failure_code(safe_failure_code)
    job = await _lock_job(session, claimed.job_id)
    if job is None:
        raise CompanyReportJobNotFoundError("company report job was not found")
    report = await _lock_report(session, claimed.report_id)
    db_time = await database_wall_clock(session)
    _assert_claim_matches(job, claimed)
    _assert_live_owner(job, worker_token=claimed.worker_token, db_time=db_time)
    if (
        report is None
        or report.subject_id != claimed.subject_id
        or report.lifecycle_status != REPORT_PENDING_STATUS
    ):
        raise CompanyReportJobStateConflictError(
            "company report does not match the claimed job"
        )
    _set_report_failed(report, safe_failure_code=safe_failure_code, finished_at=db_time)
    _set_job_failed(job, safe_failure_code=safe_failure_code, finished_at=db_time)
    await session.flush()


async def reconcile_expired_jobs(
    session: AsyncSession,
    *,
    limit: int = 100,
) -> int:
    if limit <= 0:
        raise ValueError("reconciliation limit must be positive")
    candidates_result = await session.execute(
        select(CompanyReportJob)
        .where(
            CompanyReportJob.state == JOB_RUNNING_STATE,
            CompanyReportJob.lease_expires_at <= func.clock_timestamp(),
        )
        .order_by(CompanyReportJob.lease_expires_at, CompanyReportJob.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    candidates = list(candidates_result.scalars().all())
    reconciled = 0
    for job in candidates:
        report = await _lock_report(session, job.report_id)
        db_time = await database_wall_clock(session)
        if (
            job.state != JOB_RUNNING_STATE
            or job.lease_expires_at is None
            or _as_utc(job.lease_expires_at) > db_time
        ):
            continue
        if (
            report is None
            or report.subject_id != job.subject_id
            or report.lifecycle_status != REPORT_PENDING_STATUS
        ):
            raise CompanyReportJobStateConflictError(
                "expired job does not match a pending report"
            )
        _set_report_failed(
            report,
            safe_failure_code=REPORT_EXECUTION_INTERRUPTED_CODE,
            finished_at=db_time,
        )
        _set_job_failed(
            job,
            safe_failure_code=REPORT_EXECUTION_INTERRUPTED_CODE,
            finished_at=db_time,
        )
        reconciled += 1
    if reconciled:
        await session.flush()
    return reconciled


async def get_latest_finalized_report_record(
    session: AsyncSession,
    identifier: str,
) -> LatestFinalizedReportRecord | None:
    normalized, _ = _normalize_inn(identifier)
    result = await session.execute(
        select(CompanyReportRecord)
        .join(
            CompanyReportSubject,
            CompanyReportSubject.id == CompanyReportRecord.subject_id,
        )
        .where(
            CompanyReportSubject.normalized_identifier == normalized,
            CompanyReportRecord.lifecycle_status.in_(REPORT_FINAL_STATUSES),
            # Legacy public/status callers are H1-only.  In particular, do not
            # let a newer v3/H2 artifact hide an eligible v1/v2 report.
            CompanyReportRecord.writer_profile == H1_WRITER_PROFILE,
            CompanyReportRecord.presentation_contract == H1_PRESENTATION_CONTRACT,
            CompanyReportRecord.report_version.in_(("1", "2")),
            CompanyReportRecord.rollout_generation == 0,
        )
        .order_by(
            desc(CompanyReportRecord.created_at),
            desc(CompanyReportRecord.id),
        )
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if record is None:
        return None
    return LatestFinalizedReportRecord(
        report_id=record.id,
        subject_id=record.subject_id,
        lifecycle_status=record.lifecycle_status,
        report_version=record.report_version,
        started_at=_as_utc(record.started_at),
        generated_at=_as_utc(record.generated_at) if record.generated_at else None,
        finished_at=_as_utc(record.finished_at) if record.finished_at else None,
        fresh_until=_as_utc(record.fresh_until) if record.fresh_until else None,
        normalized_snapshot=deepcopy(record.normalized_snapshot),
        snapshot_hash=record.snapshot_hash,
        safe_error_snapshot=deepcopy(record.safe_error_snapshot),
        usable_for_public_page=record.usable_for_public_page,
        usable_for_future_scoring=record.usable_for_future_scoring,
        created_at=_as_utc(record.created_at),
    )


async def database_wall_clock(session: AsyncSession) -> datetime:
    result = await session.execute(select(func.clock_timestamp()))
    value = result.scalar_one()
    if not isinstance(value, datetime):
        raise CompanyReportPersistenceError("database wall clock is unavailable")
    return _as_utc(value)


async def _get_subject(
    session: AsyncSession,
    subject_id: UUID,
) -> CompanyReportSubject | None:
    result = await session.execute(
        select(CompanyReportSubject).where(CompanyReportSubject.id == subject_id)
    )
    return result.scalar_one_or_none()


async def _lock_job(
    session: AsyncSession,
    job_id: UUID,
) -> CompanyReportJob | None:
    result = await session.execute(
        select(CompanyReportJob)
        .where(CompanyReportJob.id == job_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def _lock_report(
    session: AsyncSession,
    report_id: UUID,
) -> CompanyReportRecord | None:
    result = await session.execute(
        select(CompanyReportRecord)
        .where(CompanyReportRecord.id == report_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def _fail_queued_precondition(
    session: AsyncSession,
    *,
    job: CompanyReportJob,
    report: CompanyReportRecord | None,
    finished_at: datetime,
) -> None:
    if job.state != JOB_QUEUED_STATE or job.attempt_count != 0:
        raise CompanyReportJobStateConflictError(
            "queued company report job has invalid state"
        )
    if report is not None and report.lifecycle_status == REPORT_PENDING_STATUS:
        _set_report_failed(
            report,
            safe_failure_code=REPORT_JOB_PRECONDITION_FAILED_CODE,
            finished_at=finished_at,
        )
    _set_job_failed(
        job,
        safe_failure_code=REPORT_JOB_PRECONDITION_FAILED_CODE,
        finished_at=finished_at,
    )
    await session.flush()


def _set_report_failed(
    report: CompanyReportRecord,
    *,
    safe_failure_code: str,
    finished_at: datetime,
) -> None:
    _validate_safe_failure_code(safe_failure_code)
    report.lifecycle_status = JOB_FAILED_STATE
    report.generated_at = None
    report.finished_at = finished_at
    report.fresh_until = None
    report.normalized_snapshot = None
    report.snapshot_hash = None
    report.completeness_snapshot = None
    report.freshness_snapshot = None
    report.warnings_snapshot = []
    report.safe_error_snapshot = {"code": safe_failure_code}
    report.usable_for_public_page = False
    report.usable_for_future_scoring = False
    report.updated_at = finished_at


def _set_job_failed(
    job: CompanyReportJob,
    *,
    safe_failure_code: str,
    finished_at: datetime,
) -> None:
    _validate_safe_failure_code(safe_failure_code)
    job.state = JOB_FAILED_STATE
    job.finished_at = finished_at
    job.safe_failure_code = safe_failure_code
    job.updated_at = finished_at


def _assert_claim_matches(
    job: CompanyReportJob,
    claimed: ClaimedReportJob,
) -> None:
    if (
        job.id != claimed.job_id
        or job.report_id != claimed.report_id
        or job.subject_id != claimed.subject_id
        or (job.writer_profile or H1_WRITER_PROFILE) != claimed.writer_profile
        or (job.presentation_contract or H1_PRESENTATION_CONTRACT) != claimed.presentation_contract
        or (0 if job.rollout_generation is None else job.rollout_generation) != claimed.rollout_generation
        or (0 if job.fence_generation is None else job.fence_generation) != claimed.fence_generation
    ):
        raise CompanyReportJobStateConflictError(
            "company report job does not match the claim"
        )


def _assert_live_owner(
    job: CompanyReportJob,
    *,
    worker_token: UUID,
    db_time: datetime,
) -> None:
    if (
        job.state != JOB_RUNNING_STATE
        or job.worker_token != worker_token
        or job.lease_expires_at is None
        or _as_utc(job.lease_expires_at) <= db_time
    ):
        raise CompanyReportJobFencingError("company report job ownership was lost")


def _normalize_inn(
    identifier: str,
) -> tuple[str, DataNewtonIdentifierType]:
    try:
        normalized = normalize_identifier(identifier)
        identifier_type = identify_identifier_type(normalized)
    except Exception as exc:
        raise CompanyReportPersistenceError("identifier is invalid") from exc
    if identifier_type not in {
        DataNewtonIdentifierType.LEGAL_ENTITY_INN,
        DataNewtonIdentifierType.INDIVIDUAL_ENTREPRENEUR_INN,
    }:
        raise CompanyReportPersistenceError("identifier is not an INN")
    return normalized, identifier_type


def _job_matches_decision(
    job: CompanyReportJob,
    report: CompanyReportRecord,
    decision: WriterDecision,
) -> bool:
    # SQLAlchemy column defaults are applied on flush, while existing unit
    # callers construct legacy model objects in memory. Treat only absent
    # in-memory metadata as the immutable H1 default; persisted v3 never
    # receives this compatibility normalization.
    job_profile = job.writer_profile or H1_WRITER_PROFILE
    record_profile = report.writer_profile or H1_WRITER_PROFILE
    job_contract = job.presentation_contract or H1_PRESENTATION_CONTRACT
    record_contract = report.presentation_contract or H1_PRESENTATION_CONTRACT
    job_generation = 0 if job.rollout_generation is None else job.rollout_generation
    record_generation = 0 if report.rollout_generation is None else report.rollout_generation
    return (
        job_profile == record_profile == decision.writer_profile
        and job_contract == record_contract == decision.presentation_contract
        and job_generation == record_generation == decision.rollout_generation
        and report.report_version == decision.report_version
    )


def _validate_safe_failure_code(value: str) -> None:
    if value not in _SAFE_FAILURE_MESSAGES:
        raise ValueError("safe failure code is not allowed")


def _valid_stored_job_decision(job: CompanyReportJob, report: CompanyReportRecord) -> bool:
    try:
        decision = WriterDecision(
            writer_profile=job.writer_profile or H1_WRITER_PROFILE,
            report_version=report.report_version,
            presentation_contract=job.presentation_contract or H1_PRESENTATION_CONTRACT,
            rollout_generation=0 if job.rollout_generation is None else job.rollout_generation,
        )
    except ValueError:
        return False
    return _job_matches_decision(job, report, decision)


def _require_positive_lease(value: int) -> None:
    if value <= 0:
        raise ValueError("lease seconds must be positive")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = [
    "ClaimedReportJob",
    "CompletedReportJob",
    "EnqueuedReportJob",
    "H1_PRESENTATION_CONTRACT",
    "H1_WRITER_PROFILE",
    "H2_PRESENTATION_CONTRACT",
    "H2_WRITER_PROFILE",
    "LatestFinalizedReportRecord",
    "REPORT_EXECUTION_FAILED_CODE",
    "REPORT_EXECUTION_INTERRUPTED_CODE",
    "REPORT_JOB_PRECONDITION_FAILED_CODE",
    "WriterDecision",
    "claim_next_job",
    "complete_claimed_job",
    "complete_claimed_company_card_v2_job",
    "database_wall_clock",
    "enqueue_company_report_job",
    "fail_owned_job",
    "get_latest_finalized_report_record",
    "heartbeat_job",
    "reconcile_expired_jobs",
]
