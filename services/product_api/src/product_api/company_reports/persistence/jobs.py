from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Any, Callable, Literal
from uuid import UUID, uuid4

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.company_reports.aggregate import CompanyReport, CURRENT_COMPANY_REPORT_VERSION
from product_api.company_reports.company_card_v2.models import (
    CompanyCardV2SnapshotV2,
    CompanyCardV2SnapshotV3,
)
from product_api.company_reports.company_urls import (
    CanonicalUrlBinding,
    legacy_h2_binding,
    parse_company_path,
)
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
    CompanyReportStateConflictError,
)
from .models import (
    JOB_FAILED_STATE,
    JOB_QUEUED_STATE,
    JOB_RUNNING_STATE,
    JOB_SUCCEEDED_STATE,
    REPORT_FINAL_STATUSES,
    REPORT_PENDING_STATUS,
    CompanyCardNarrativeOutbox,
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
_ARBITRATION_MASK_KEY_ID = re.compile(r"[a-z][a-z0-9_]{0,31}")

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
    arbitration_collection_enabled: bool = False
    arbitration_mask_key_id: str | None = None

    def __post_init__(self) -> None:
        if (
            type(self.writer_profile) is not str
            or type(self.report_version) is not str
            or type(self.presentation_contract) is not str
            or type(self.rollout_generation) is not int
        ):
            raise ValueError("writer decision scalar types are invalid")
        if type(self.arbitration_collection_enabled) is not bool:
            raise ValueError("writer arbitration decision is invalid")
        if (
            self.arbitration_mask_key_id is not None
            and (
                type(self.arbitration_mask_key_id) is not str
                or _ARBITRATION_MASK_KEY_ID.fullmatch(self.arbitration_mask_key_id)
                is None
            )
        ):
            raise ValueError("writer arbitration key id is invalid")
        if not self.arbitration_collection_enabled and self.arbitration_mask_key_id is not None:
            raise ValueError("disabled writer arbitration decision cannot carry a key id")
        h1 = (self.writer_profile, self.report_version, self.presentation_contract, self.rollout_generation) == (H1_WRITER_PROFILE, CURRENT_COMPANY_REPORT_VERSION, H1_PRESENTATION_CONTRACT, 0)
        h2 = self.writer_profile == H2_WRITER_PROFILE and self.report_version == "3" and self.presentation_contract == H2_PRESENTATION_CONTRACT and self.rollout_generation > 0
        if not (h1 or h2) or (h1 and self.arbitration_collection_enabled):
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
    arbitration_collection_enabled: bool = False
    arbitration_mask_key_id: str | None = None
    fence_generation: int = 0

    def __post_init__(self) -> None:
        if type(self.fence_generation) is not int:
            raise ValueError("claim fence generation is invalid")
        WriterDecision(
            writer_profile=self.writer_profile,
            report_version=self.report_version,
            presentation_contract=self.presentation_contract,
            rollout_generation=self.rollout_generation,
            arbitration_collection_enabled=self.arbitration_collection_enabled,
            arbitration_mask_key_id=self.arbitration_mask_key_id,
        )


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
        arbitration_collection_enabled=decision.arbitration_collection_enabled,
        arbitration_mask_key_id=decision.arbitration_mask_key_id,
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
        arbitration_collection_enabled=decision.arbitration_collection_enabled,
        arbitration_mask_key_id=decision.arbitration_mask_key_id,
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

    if job.attempt_count != 0 or (job.fence_generation or 0) != 0:
        # Iteration 20 has one claim only.  A mutated/replayed queued row is
        # terminally invalid rather than a reclaim opportunity.
        await _fail_queued_precondition(session, job=job, report=report, finished_at=db_time)
        return None

    worker_token = token_factory()
    job.state = JOB_RUNNING_STATE
    job.worker_token = worker_token
    # This is a one-claim lifecycle, not a reclaim counter. A queued job is
    # exactly fence 0; its sole successful claim atomically sets fence 1.
    job.fence_generation = 1
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
        writer_profile=_row_writer_profile(job),
        report_version=report.report_version,
        presentation_contract=_row_presentation_contract(job),
        rollout_generation=0 if job.rollout_generation is None else job.rollout_generation,
        arbitration_collection_enabled=_row_arbitration_enabled(job),
        arbitration_mask_key_id=job.arbitration_mask_key_id,
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
    if claimed is None:
        try:
            exact_legacy_h1 = (
                _row_writer_profile(job) == H1_WRITER_PROFILE
                and _row_presentation_contract(job)
                == H1_PRESENTATION_CONTRACT
                and (0 if job.rollout_generation is None else job.rollout_generation)
                == 0
                and not _row_arbitration_enabled(job)
                and job.arbitration_mask_key_id is None
            )
        except ValueError:
            exact_legacy_h1 = False
        if not exact_legacy_h1:
            raise CompanyReportJobStateConflictError(
                "non-H1 heartbeat requires the immutable claim decision"
            )
        _assert_live_owner(job, worker_token=worker_token, db_time=db_time)
        report = await _lock_report(session, job.report_id)
        if (
            report is None
            or report.lifecycle_status != REPORT_PENDING_STATUS
            or not _has_immutable_job_binding(job, report)
        ):
            raise CompanyReportJobStateConflictError(
                "H1 heartbeat report decision does not match the job"
            )
    if claimed is not None:
        _assert_claim_matches(job, claimed)
        report = await _lock_report(session, claimed.report_id)
        if report is None:
            raise CompanyReportJobStateConflictError(
                "company report job decision does not match the claim"
            )
        _assert_report_matches_claim(report, claimed)
        if not _job_matches_decision(
            job,
            report,
            WriterDecision(
                writer_profile=claimed.writer_profile,
                report_version=claimed.report_version,
                presentation_contract=claimed.presentation_contract,
                rollout_generation=claimed.rollout_generation,
                arbitration_collection_enabled=claimed.arbitration_collection_enabled,
                arbitration_mask_key_id=claimed.arbitration_mask_key_id,
            ),
        ):
            raise CompanyReportJobStateConflictError("company report job decision does not match the claim")
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
    _assert_report_matches_claim(stored_report, claimed)
    if (
        claimed.writer_profile != H1_WRITER_PROFILE
        or claimed.presentation_contract != H1_PRESENTATION_CONTRACT
        or claimed.report_version not in {"1", "2"}
        or claimed.rollout_generation != 0
        or not _valid_stored_job_decision(job, stored_report)
    ):
        raise CompanyReportJobStateConflictError("H1 completion decision does not match the claim")
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
    snapshot: CompanyCardV2SnapshotV2 | CompanyCardV2SnapshotV3,
    lifecycle_status: Literal["complete", "partial"] = "complete",
    canonical_url_binding: CanonicalUrlBinding | None = None,
) -> CompletedReportJob:
    """Finalize one V2 snapshot and its durable narrative event atomically.

    The caller owns the surrounding transaction.  In particular, an outbox
    insertion failure must escape this function so that the caller rolls the
    report, job and outbox transition back together.
    """
    binding = canonical_url_binding or legacy_h2_binding(claimed.normalized_identifier)
    if type(binding) is not CanonicalUrlBinding:
        raise CompanyReportJobStateConflictError(
            "company card v2 URL binding is invalid"
        )
    parsed_binding = parse_company_path(binding.canonical_path)
    if (
        parsed_binding is None
        or parsed_binding.kind == "plain"
        or parsed_binding.inn != claimed.normalized_identifier
        or parsed_binding.form_token != binding.form_token
        or parsed_binding.name_slug != binding.name_slug
    ):
        raise CompanyReportJobStateConflictError(
            "company card v2 URL binding is invalid"
        )
    if not _snapshot_matches_claim_decision(snapshot, claimed):
        raise CompanyReportJobStateConflictError(
            "company card v2 completion snapshot decision is invalid"
        )
    if lifecycle_status not in {"complete", "partial"}:
        raise ValueError("company card v2 lifecycle status is invalid")
    # Enqueue owns the stable subject row before it inspects an active job.
    # Use the same subject -> job -> report order here so finalization cannot
    # deadlock with a concurrent request for a newer report.
    subject = await session.get(
        CompanyReportSubject,
        claimed.subject_id,
        with_for_update=True,
    )
    job = await _lock_job(session, claimed.job_id)
    record = await _lock_report(session, claimed.report_id)
    db_time = await database_wall_clock(session)
    if subject is None or job is None or record is None:
        raise CompanyReportJobNotFoundError("company card v2 job was not found")
    if subject.normalized_identifier != claimed.normalized_identifier:
        raise CompanyReportJobStateConflictError(
            "company card v2 subject does not match the claim"
        )
    _assert_claim_matches(job, claimed)
    _assert_report_matches_claim(record, claimed)
    if claimed.writer_profile != H2_WRITER_PROFILE or not _valid_stored_job_decision(job, record):
        raise CompanyReportJobStateConflictError("company card v2 writer decision does not match")
    if job.state == JOB_SUCCEEDED_STATE:
        return await _reuse_exact_company_card_v2_completion(
            session,
            claimed=claimed,
            job=job,
            record=record,
            snapshot=snapshot,
            lifecycle_status=lifecycle_status,
            canonical_url_binding=binding,
            db_time=db_time,
        )
    _assert_live_owner(job, worker_token=claimed.worker_token, db_time=db_time)
    if record.lifecycle_status != REPORT_PENDING_STATUS:
        raise CompanyReportJobStateConflictError(
            "company card v2 report is already finalized"
        )
    finalized = await finalize_company_card_v2_report(
        session,
        snapshot,
        report_id=claimed.report_id,
        subject_id=claimed.subject_id,
        finished_at=db_time,
        arbitration_collection_enabled=claimed.arbitration_collection_enabled,
        arbitration_mask_key_id=claimed.arbitration_mask_key_id,
    )
    # The finalization repository validates the immutable snapshot and owns
    # its legacy-compatible default.  V2 writer outcome supplies the explicit
    # complete/partial result for independently normalized datasets.
    finalized.lifecycle_status = lifecycle_status
    if finalized.snapshot_hash is None:
        raise CompanyReportJobStateConflictError(
            "finalized company card v2 snapshot hash is missing"
        )
    # Pin, report and outbox share the caller transaction.  The read path is
    # deliberately SELECT-only; only a fenced writer may establish v2 policy.
    from .presentations import create_or_reuse_unresolved_h2_pin
    await create_or_reuse_unresolved_h2_pin(
        session,
        report=finalized,
        canonical_path=binding.canonical_path,
    )
    # ``narratives`` imports presentation helpers that depend on this module;
    # defer this narrow write-side dependency until jobs has initialized.
    from .narratives import insert_narrative_outbox

    await insert_narrative_outbox(
        session,
        report_id=finalized.id,
        snapshot_hash=finalized.snapshot_hash,
        now=db_time,
    )
    job.state, job.finished_at, job.safe_failure_code, job.updated_at = JOB_SUCCEEDED_STATE, db_time, None, db_time
    await session.flush()
    return CompletedReportJob(report_id=finalized.id, lifecycle_status=finalized.lifecycle_status, signals=None, scoring=None)


async def _reuse_exact_company_card_v2_completion(
    session: AsyncSession,
    *,
    claimed: ClaimedReportJob,
    job: CompanyReportJob,
    record: CompanyReportRecord,
    snapshot: CompanyCardV2SnapshotV2 | CompanyCardV2SnapshotV3,
    lifecycle_status: Literal["complete", "partial"],
    db_time: datetime,
    canonical_url_binding: CanonicalUrlBinding | None = None,
) -> CompletedReportJob:
    """Return a committed V3 boundary only when every durable row is exact.

    This path is deliberately read-only.  In particular, a historical terminal
    report without its unresolved v2 predecessor is corruption and must never
    be backfilled by a retry.
    """
    if (
        record.lifecycle_status not in {"complete", "partial"}
        or record.lifecycle_status != lifecycle_status
        or record.snapshot_hash is None
        or record.finished_at is None
        or job.finished_at is None
        or _as_utc(record.finished_at) != _as_utc(job.finished_at)
        or job.safe_failure_code is not None
        or job.attempt_count != 1
        or (job.fence_generation or 0) != 1
    ):
        raise CompanyReportJobStateConflictError(
            "company card v2 completed boundary is not exact"
        )
    try:
        finalized = await finalize_company_card_v2_report(
            session,
            snapshot,
            report_id=record.id,
            subject_id=record.subject_id,
            finished_at=record.finished_at or db_time,
            arbitration_collection_enabled=claimed.arbitration_collection_enabled,
            arbitration_mask_key_id=claimed.arbitration_mask_key_id,
        )
    except CompanyReportStateConflictError as exc:
        raise CompanyReportJobStateConflictError(
            "company card v2 completion retry does not match the stored snapshot"
        ) from exc
    if finalized.snapshot_hash != record.snapshot_hash:
        raise CompanyReportJobStateConflictError(
            "company card v2 completion retry hash is not exact"
        )

    from .presentations import (
        H2_PUBLICATION_POLICY_V2,
        H2_PUBLICATION_POLICY_V3,
        PresentationAssignmentConflict,
        require_existing_unresolved_h2_pin,
    )

    try:
        if canonical_url_binding is None:
            pin = await require_existing_unresolved_h2_pin(session, report=record)
        else:
            pin = await require_existing_unresolved_h2_pin(
                session,
                report=record,
                canonical_path=canonical_url_binding.canonical_path,
            )
    except PresentationAssignmentConflict as exc:
        raise CompanyReportJobStateConflictError(
            "company card v2 completed pin lineage is invalid"
        ) from exc
    expected_policy = (
        H2_PUBLICATION_POLICY_V3
        if claimed.arbitration_collection_enabled
        else H2_PUBLICATION_POLICY_V2
    )
    if pin.publication_policy_version != expected_policy:
        raise CompanyReportJobStateConflictError(
            "company card v2 completed pin policy is invalid"
        )

    outboxes = list(
        (
            await session.scalars(
                select(CompanyCardNarrativeOutbox).where(
                    CompanyCardNarrativeOutbox.report_id == record.id,
                    CompanyCardNarrativeOutbox.event_kind
                    == "initialize_narrative_v1",
                )
            )
        ).all()
    )
    if len(outboxes) != 1 or outboxes[0].snapshot_hash != record.snapshot_hash:
        raise CompanyReportJobStateConflictError(
            "company card v2 completed narrative outbox is not exact"
        )
    return CompletedReportJob(
        report_id=record.id,
        lifecycle_status=record.lifecycle_status,
        signals=None,
        scoring=None,
    )


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
    _assert_report_matches_claim(report, claimed)
    _assert_live_owner(job, worker_token=claimed.worker_token, db_time=db_time)
    if report is not None and not _valid_stored_job_decision(job, report):
        raise CompanyReportJobStateConflictError("company report job decision does not match the claim")
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
            or not _has_immutable_job_binding(job, report)
            or job.attempt_count != 1
            or (job.fence_generation or 0) != 1
            or job.worker_token is None
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
            CompanyReportRecord.generated_at.desc().nullslast(),
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
    if type(claimed.fence_generation) is not int or claimed.fence_generation != 1:
        raise CompanyReportJobStateConflictError(
            "company report claim fence is invalid"
        )
    try:
        WriterDecision(
            writer_profile=claimed.writer_profile,
            report_version=claimed.report_version,
            presentation_contract=claimed.presentation_contract,
            rollout_generation=claimed.rollout_generation,
            arbitration_collection_enabled=claimed.arbitration_collection_enabled,
            arbitration_mask_key_id=claimed.arbitration_mask_key_id,
        )
    except ValueError as exc:
        raise CompanyReportJobStateConflictError(
            "company report claim decision is invalid"
        ) from exc
    try:
        job_arbitration_enabled = _row_arbitration_enabled(job)
    except ValueError as exc:
        raise CompanyReportJobStateConflictError(
            "company report job decision is invalid"
        ) from exc
    if (
        job.id != claimed.job_id
        or job.report_id != claimed.report_id
        or job.subject_id != claimed.subject_id
        or job.worker_token != claimed.worker_token
        or _row_writer_profile(job) != claimed.writer_profile
        or _row_presentation_contract(job) != claimed.presentation_contract
        or (0 if job.rollout_generation is None else job.rollout_generation) != claimed.rollout_generation
        or job_arbitration_enabled != claimed.arbitration_collection_enabled
        or job.arbitration_mask_key_id != claimed.arbitration_mask_key_id
        or (0 if job.fence_generation is None else job.fence_generation) != claimed.fence_generation
    ):
        raise CompanyReportJobStateConflictError(
            "company report job does not match the claim"
        )


def _assert_report_matches_claim(
    report: CompanyReportRecord | None,
    claimed: ClaimedReportJob,
) -> None:
    try:
        report_arbitration_enabled = (
            None if report is None else _row_arbitration_enabled(report)
        )
    except ValueError as exc:
        raise CompanyReportJobStateConflictError(
            "company report decision is invalid"
        ) from exc
    if (
        report is None
        or report.id != claimed.report_id
        or report.subject_id != claimed.subject_id
        or report.report_version != claimed.report_version
        or _row_writer_profile(report) != claimed.writer_profile
        or _row_presentation_contract(report)
        != claimed.presentation_contract
        or (0 if report.rollout_generation is None else report.rollout_generation)
        != claimed.rollout_generation
        or report_arbitration_enabled != claimed.arbitration_collection_enabled
        or report.arbitration_mask_key_id != claimed.arbitration_mask_key_id
    ):
        raise CompanyReportJobStateConflictError(
            "company report does not match the claim"
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
        or job.attempt_count != 1
        or (job.fence_generation or 0) != 1
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
    job_profile = _row_writer_profile(job)
    record_profile = _row_writer_profile(report)
    job_contract = _row_presentation_contract(job)
    record_contract = _row_presentation_contract(report)
    job_generation = 0 if job.rollout_generation is None else job.rollout_generation
    record_generation = 0 if report.rollout_generation is None else report.rollout_generation
    if (
        type(job_profile) is not str
        or type(record_profile) is not str
        or type(job_contract) is not str
        or type(record_contract) is not str
        or type(job_generation) is not int
        or type(record_generation) is not int
        or type(report.report_version) is not str
        or (
            report.arbitration_mask_key_id is not None
            and type(report.arbitration_mask_key_id) is not str
        )
    ):
        return False
    try:
        job_arbitration_enabled = _row_arbitration_enabled(job)
        report_arbitration_enabled = _row_arbitration_enabled(report)
    except ValueError:
        return False
    return (
        job_profile == record_profile == decision.writer_profile
        and job_contract == record_contract == decision.presentation_contract
        and job_generation == record_generation == decision.rollout_generation
        and report.report_version == decision.report_version
        and job_arbitration_enabled
        == report_arbitration_enabled
        == decision.arbitration_collection_enabled
        and job.arbitration_mask_key_id
        == report.arbitration_mask_key_id
        == decision.arbitration_mask_key_id
    )


def _snapshot_matches_claim_decision(
    snapshot: object,
    claimed: ClaimedReportJob,
) -> bool:
    if claimed.arbitration_collection_enabled:
        if type(snapshot) is not CompanyCardV2SnapshotV3:
            return False
        effective_key_id = snapshot.arbitration_basis.mask_key_id
        return (
            effective_key_id is None
            or effective_key_id == claimed.arbitration_mask_key_id
        )
    return (
        type(snapshot) is CompanyCardV2SnapshotV2
        and claimed.arbitration_mask_key_id is None
    )


def _validate_safe_failure_code(value: str) -> None:
    if value not in _SAFE_FAILURE_MESSAGES:
        raise ValueError("safe failure code is not allowed")


def _valid_stored_job_decision(job: CompanyReportJob, report: CompanyReportRecord) -> bool:
    try:
        decision = WriterDecision(
            writer_profile=_row_writer_profile(job),
            report_version=report.report_version,
            presentation_contract=_row_presentation_contract(job),
            rollout_generation=0 if job.rollout_generation is None else job.rollout_generation,
            arbitration_collection_enabled=_row_arbitration_enabled(job),
            arbitration_mask_key_id=job.arbitration_mask_key_id,
        )
    except ValueError:
        return False
    return _job_matches_decision(job, report, decision)


def _has_immutable_job_binding(job: CompanyReportJob, report: CompanyReportRecord) -> bool:
    """Validate a stored tuple before terminal reconciliation.

    An old H1/v1 pending row is not eligible for a new writer claim, but an
    already-owned, expired row must still be terminally failed rather than
    left running forever.  This deliberately does not broaden `WriterDecision`
    or the enqueue/claim path.
    """
    job_profile = _row_writer_profile(job)
    report_profile = _row_writer_profile(report)
    job_contract = _row_presentation_contract(job)
    report_contract = _row_presentation_contract(report)
    job_generation = 0 if job.rollout_generation is None else job.rollout_generation
    report_generation = 0 if report.rollout_generation is None else report.rollout_generation
    if (
        type(job_profile) is not str
        or type(report_profile) is not str
        or type(job_contract) is not str
        or type(report_contract) is not str
        or type(job_generation) is not int
        or type(report_generation) is not int
        or type(report.report_version) is not str
        or (
            job.arbitration_mask_key_id is not None
            and type(job.arbitration_mask_key_id) is not str
        )
        or (
            report.arbitration_mask_key_id is not None
            and type(report.arbitration_mask_key_id) is not str
        )
    ):
        return False
    try:
        job_arbitration_enabled = _row_arbitration_enabled(job)
        report_arbitration_enabled = _row_arbitration_enabled(report)
    except ValueError:
        return False
    if (
        job.subject_id != report.subject_id
        or job_profile != report_profile
        or job_contract != report_contract
        or job_generation != report_generation
        or job_arbitration_enabled != report_arbitration_enabled
        or job.arbitration_mask_key_id != report.arbitration_mask_key_id
    ):
        return False
    if (
        job_profile == H1_WRITER_PROFILE
        and job_contract == H1_PRESENTATION_CONTRACT
        and job_generation == 0
        and report.report_version in {"1", "2"}
    ):
        return not job_arbitration_enabled and job.arbitration_mask_key_id is None
    try:
        WriterDecision(
            writer_profile=job_profile,
            report_version=report.report_version,
            presentation_contract=job_contract,
            rollout_generation=job_generation,
            arbitration_collection_enabled=job_arbitration_enabled,
            arbitration_mask_key_id=job.arbitration_mask_key_id,
        )
    except ValueError:
        return False
    return True


def _row_writer_profile(
    row: CompanyReportJob | CompanyReportRecord,
) -> object:
    """Default only an unflushed ORM ``None``; persisted falsy values are corrupt."""

    return H1_WRITER_PROFILE if row.writer_profile is None else row.writer_profile


def _row_presentation_contract(
    row: CompanyReportJob | CompanyReportRecord,
) -> object:
    """Default only an unflushed ORM ``None``; persisted falsy values are corrupt."""

    return (
        H1_PRESENTATION_CONTRACT
        if row.presentation_contract is None
        else row.presentation_contract
    )


def _row_arbitration_enabled(
    row: CompanyReportJob | CompanyReportRecord,
) -> bool:
    """Normalize only an unflushed ORM default; persisted columns are NOT NULL."""
    value = row.arbitration_collection_enabled
    if value is None:
        return False
    if type(value) is not bool:
        raise ValueError("stored arbitration decision is invalid")
    return value


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
