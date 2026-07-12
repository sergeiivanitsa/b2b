from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.company_reports.aggregate import (
    CompanyReport,
    DatasetReportStatus,
)
from product_api.company_reports.models import (
    ArbitrationFacts,
    CounterpartyFacts,
    FinanceFacts,
)
from product_api.providers.datanewton import (
    DataNewtonIdentifierType,
    identify_identifier_type,
    normalize_identifier,
)

from .errors import (
    CompanyReportNotFoundError,
    CompanyReportPersistenceError,
    CompanyReportSnapshotError,
    CompanyReportStateConflictError,
    PendingCompanyReportAlreadyExistsError,
)
from .models import (
    CompanyReportDataset,
    CompanyReportProviderRequest,
    CompanyReportRecord,
    CompanyReportSubject,
    REPORT_PENDING_STATUS,
)
from .serialization import (
    calculate_company_report_snapshot_hash,
    company_report_from_snapshot,
    company_report_to_snapshot,
)


@dataclass(frozen=True)
class SafePersistenceError:
    error_type: str
    message: str
    retryable: bool = False
    request_id: str | None = None
    failed_at: datetime | None = None


@dataclass(frozen=True)
class ReportRunStatusRecord:
    report_id: UUID
    lifecycle_status: str
    report_version: str
    started_at: datetime
    generated_at: datetime | None
    finished_at: datetime | None
    fresh_until: datetime | None


SubjectRecord = CompanyReportSubject
PendingReportRecord = CompanyReportRecord
StoredReportRecord = CompanyReportRecord


async def get_or_create_subject(
    session: AsyncSession,
    identifier: str,
) -> SubjectRecord:
    normalized, identifier_type = _normalize_identifier(identifier)
    result = await session.execute(
        select(CompanyReportSubject).where(
            CompanyReportSubject.normalized_identifier == normalized
        )
    )
    subject = result.scalar_one_or_none()
    if subject is not None:
        return subject
    subject = CompanyReportSubject(
        normalized_identifier=normalized,
        identifier_type=identifier_type.value,
    )
    session.add(subject)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise CompanyReportPersistenceError("subject creation conflicted") from exc
    return subject


async def create_pending_report(
    session: AsyncSession,
    *,
    identifier: str,
    report_id: UUID | None = None,
    report_version: str = "1",
    request_id: str | None = None,
    started_at: datetime | None = None,
    fresh_until: datetime | None = None,
) -> PendingReportRecord:
    subject = await get_or_create_subject(session, identifier)
    result = await session.execute(
        select(CompanyReportRecord)
        .where(
            CompanyReportRecord.subject_id == subject.id,
            CompanyReportRecord.lifecycle_status == REPORT_PENDING_STATUS,
        )
        .order_by(desc(CompanyReportRecord.created_at), desc(CompanyReportRecord.id))
        .limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    record = CompanyReportRecord(
        id=report_id or uuid4(),
        subject_id=subject.id,
        report_version=report_version,
        lifecycle_status=REPORT_PENDING_STATUS,
        request_id=request_id,
        started_at=_as_utc(started_at or _utc_now()),
        fresh_until=_as_utc(fresh_until) if fresh_until is not None else None,
        warnings_snapshot=[],
        usable_for_public_page=False,
        usable_for_future_scoring=False,
    )
    session.add(record)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise PendingCompanyReportAlreadyExistsError(
            "a pending report already exists for this subject"
        ) from exc
    return record


async def finalize_report(
    session: AsyncSession,
    report: CompanyReport,
    *,
    fresh_until: datetime | None = None,
) -> StoredReportRecord:
    snapshot = company_report_to_snapshot(report)
    snapshot_hash = calculate_company_report_snapshot_hash(snapshot)
    record = await _get_report_for_update(session, report.report_id)
    if record is None:
        raise CompanyReportNotFoundError("company report was not found")

    subject = await _get_subject(session, record.subject_id)
    if subject is None or subject.normalized_identifier != report.target_identifier:
        raise CompanyReportStateConflictError("company report subject does not match")
    if record.report_version != report.report_version:
        raise CompanyReportStateConflictError("company report version does not match")

    if record.lifecycle_status != REPORT_PENDING_STATUS:
        if record.snapshot_hash == snapshot_hash:
            return record
        raise CompanyReportStateConflictError("finalized company report cannot be replaced")

    record.lifecycle_status = report.status.value
    record.generated_at = _as_utc(report.generated_at)
    record.finished_at = _utc_now()
    record.fresh_until = _as_utc(fresh_until) if fresh_until is not None else None
    record.normalized_snapshot = snapshot
    record.snapshot_hash = snapshot_hash
    record.completeness_snapshot = report.completeness.model_dump(mode="json")
    record.freshness_snapshot = report.freshness.model_dump(mode="json")
    record.warnings_snapshot = report.warnings and [
        item.model_dump(mode="json") for item in report.warnings
    ] or []
    record.safe_error_snapshot = None
    record.usable_for_public_page = report.usable_for_public_page
    record.usable_for_future_scoring = report.usable_for_future_scoring

    await _create_dataset_and_journal_records(session, record, report)
    await session.flush()
    return record


async def mark_report_failed(
    session: AsyncSession,
    *,
    report_id: UUID,
    safe_error: SafePersistenceError,
    finished_at: datetime | None = None,
) -> StoredReportRecord:
    record = await _get_report_for_update(session, report_id)
    if record is None:
        raise CompanyReportNotFoundError("company report was not found")
    if record.lifecycle_status != REPORT_PENDING_STATUS:
        raise CompanyReportStateConflictError("company report is already finalized")

    failed_at = _as_utc(finished_at or safe_error.failed_at or _utc_now())
    record.lifecycle_status = "failed"
    record.finished_at = failed_at
    record.normalized_snapshot = None
    record.snapshot_hash = None
    record.completeness_snapshot = None
    record.freshness_snapshot = None
    record.warnings_snapshot = []
    record.safe_error_snapshot = {
        "error_type": safe_error.error_type,
        "message": safe_error.message,
        "retryable": safe_error.retryable,
        "request_id": safe_error.request_id,
        "failed_at": failed_at.isoformat(),
    }
    record.usable_for_public_page = False
    record.usable_for_future_scoring = False
    await session.flush()
    return record


async def get_report_record(
    session: AsyncSession,
    report_id: UUID,
) -> StoredReportRecord | None:
    result = await session.execute(
        select(CompanyReportRecord).where(CompanyReportRecord.id == report_id)
    )
    return result.scalar_one_or_none()


async def get_company_report(
    session: AsyncSession,
    report_id: UUID,
) -> CompanyReport | None:
    record = await get_report_record(session, report_id)
    if record is None or record.normalized_snapshot is None:
        return None
    try:
        return company_report_from_snapshot(record.normalized_snapshot)
    except CompanyReportSnapshotError:
        return None


async def get_latest_report_by_identifier(
    session: AsyncSession,
    identifier: str,
) -> CompanyReport | None:
    normalized, _ = _normalize_identifier(identifier)
    result = await session.execute(
        select(CompanyReportRecord)
        .join(CompanyReportSubject, CompanyReportSubject.id == CompanyReportRecord.subject_id)
        .where(
            CompanyReportSubject.normalized_identifier == normalized,
            CompanyReportRecord.lifecycle_status.in_(("complete", "partial")),
            CompanyReportRecord.normalized_snapshot.is_not(None),
        )
        .order_by(
            desc(CompanyReportRecord.generated_at),
            desc(CompanyReportRecord.created_at),
            desc(CompanyReportRecord.id),
        )
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if record is None or record.normalized_snapshot is None:
        return None
    try:
        return company_report_from_snapshot(record.normalized_snapshot)
    except CompanyReportSnapshotError:
        return None


async def get_latest_run_status_by_identifier(
    session: AsyncSession,
    identifier: str,
) -> ReportRunStatusRecord | None:
    normalized, _ = _normalize_identifier(identifier)
    result = await session.execute(
        select(CompanyReportRecord)
        .join(CompanyReportSubject, CompanyReportSubject.id == CompanyReportRecord.subject_id)
        .where(CompanyReportSubject.normalized_identifier == normalized)
        .order_by(
            desc(CompanyReportRecord.created_at),
            desc(CompanyReportRecord.id),
        )
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if record is None:
        return None
    return ReportRunStatusRecord(
        report_id=record.id,
        lifecycle_status=record.lifecycle_status,
        report_version=record.report_version,
        started_at=record.started_at,
        generated_at=record.generated_at,
        finished_at=record.finished_at,
        fresh_until=record.fresh_until,
    )


async def get_fresh_report_by_identifier(
    session: AsyncSession,
    identifier: str,
    *,
    now: datetime,
) -> CompanyReport | None:
    normalized, _ = _normalize_identifier(identifier)
    current_time = _as_utc(now)
    result = await session.execute(
        select(CompanyReportRecord)
        .join(CompanyReportSubject, CompanyReportSubject.id == CompanyReportRecord.subject_id)
        .where(
            CompanyReportSubject.normalized_identifier == normalized,
            CompanyReportRecord.lifecycle_status.in_(("complete", "partial")),
            CompanyReportRecord.normalized_snapshot.is_not(None),
            CompanyReportRecord.fresh_until.is_not(None),
            CompanyReportRecord.fresh_until > current_time,
            CompanyReportRecord.usable_for_public_page.is_(True),
        )
        .order_by(
            desc(CompanyReportRecord.generated_at),
            desc(CompanyReportRecord.created_at),
            desc(CompanyReportRecord.id),
        )
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if record is None or record.normalized_snapshot is None:
        return None
    try:
        return company_report_from_snapshot(record.normalized_snapshot)
    except CompanyReportSnapshotError:
        return None


async def _create_dataset_and_journal_records(
    session: AsyncSession,
    report_record: CompanyReportRecord,
    report: CompanyReport,
) -> None:
    facts_by_dataset: dict[str, Any] = {
        "counterparty": report.counterparty,
        "finance": report.finance,
        "arbitration": report.arbitration,
    }
    for dataset, dataset_report in report.datasets.items():
        facts = facts_by_dataset.get(dataset)
        if dataset_report.status is DatasetReportStatus.AVAILABLE:
            if facts is None or dataset_report.source is None or dataset_report.error is not None:
                raise CompanyReportSnapshotError("available dataset snapshot is incomplete")
            normalized_snapshot = facts.model_dump(mode="json")
            source = dataset_report.source
            source_metadata = source.model_dump(mode="json")
            safe_error = None
            response_hash = source.response_hash
            received_at = source.received_at
            provider = source.provider
            endpoint = source.endpoint
            request_id = source.request_id
            http_status_code = source.status_code
            attempts = source.attempts if source.attempts is not None else dataset_report.attempts
            duration_ms = source.duration_ms if source.duration_ms is not None else dataset_report.duration_ms
            retryable = None
            provider_limit_metadata = source.provider_limit_metadata
            request_executed = True
            request_outcome = "success"
            safe_error_type = None
            safe_error_message = None
        else:
            if facts is not None or dataset_report.error is None:
                raise CompanyReportSnapshotError("error dataset snapshot is incomplete")
            normalized_snapshot = None
            source_metadata = None
            safe_error = dataset_report.error.model_dump(mode="json")
            response_hash = None
            received_at = None
            provider = "datanewton"
            endpoint = dataset_report.error.endpoint
            request_id = dataset_report.error.request_id
            http_status_code = dataset_report.error.status_code
            attempts = dataset_report.error.attempts
            duration_ms = dataset_report.duration_ms
            retryable = dataset_report.error.retryable
            provider_limit_metadata = None
            request_executed = dataset_report.status not in {
                DatasetReportStatus.DISABLED,
                DatasetReportStatus.CONFIGURATION_ERROR,
            }
            request_outcome = "error" if request_executed else "not_executed"
            safe_error_type = dataset_report.error.error_type
            safe_error_message = dataset_report.error.message

        dataset_record = CompanyReportDataset(
            id=uuid4(),
            report_id=report_record.id,
            dataset=dataset,
            status=dataset_report.status.value,
            normalized_snapshot=normalized_snapshot,
            source_metadata=source_metadata,
            safe_error=safe_error,
            warnings_snapshot=[item.model_dump(mode="json") for item in dataset_report.warnings],
            response_hash=response_hash,
            received_at=received_at,
            attempts=attempts,
            duration_ms=duration_ms,
        )
        session.add(dataset_record)
        session.add(
            CompanyReportProviderRequest(
                report_id=report_record.id,
                dataset_record_id=dataset_record.id,
                provider=provider,
                dataset=dataset,
                endpoint=endpoint,
                request_id=request_id,
                request_executed=request_executed,
                request_outcome=request_outcome,
                dataset_status=dataset_report.status.value,
                http_status_code=http_status_code,
                attempts=attempts,
                duration_ms=duration_ms,
                retryable=retryable,
                response_hash=response_hash,
                received_at=received_at,
                provider_limit_metadata=provider_limit_metadata,
                safe_error_type=safe_error_type,
                safe_error_message=safe_error_message,
                billing_units=None,
                cost_amount=None,
                cost_currency=None,
                billing_metadata=None,
            )
        )


async def _get_report_for_update(
    session: AsyncSession,
    report_id: UUID,
) -> CompanyReportRecord | None:
    result = await session.execute(
        select(CompanyReportRecord)
        .where(CompanyReportRecord.id == report_id)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def _get_subject(
    session: AsyncSession,
    subject_id: UUID,
) -> CompanyReportSubject | None:
    result = await session.execute(
        select(CompanyReportSubject).where(CompanyReportSubject.id == subject_id)
    )
    return result.scalar_one_or_none()


def _normalize_identifier(identifier: str) -> tuple[str, DataNewtonIdentifierType]:
    try:
        normalized = normalize_identifier(identifier)
        return normalized, identify_identifier_type(normalized)
    except Exception as exc:
        raise CompanyReportPersistenceError("identifier is invalid") from exc


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
