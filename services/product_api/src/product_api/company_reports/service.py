from __future__ import annotations

from copy import deepcopy

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.company_reports.explanation import (
    AIExplanationFailure,
    AIExplanationResult,
    AIExplanationStatus,
    explain_scoring_result,
)
from product_api.company_reports.persistence import (
    CompanyReportJobStateConflictError,
    CompanyReportPersistenceError,
    CompanyReportSnapshotError,
    calculate_company_report_snapshot_hash,
    company_report_from_snapshot,
    enqueue_company_report_job,
    get_latest_finalized_report_record,
    get_latest_run_status_by_identifier,
)
from product_api.company_reports.scoring import score_signals
from product_api.company_reports.signals import evaluate_signals
from product_api.providers.datanewton import (
    DataNewtonIdentifierType,
    identify_identifier_type,
    normalize_identifier,
)
from product_api.settings import Settings

from .seo import SeoPolicyError, canonical_path
from .schemas import (
    CompanyReportAcceptedResponse,
    CompanyReportResponse,
    CompanyReportSafeFailureResponse,
    CompanyReportStatusResponse,
    assert_public_payload_is_safe,
    build_public_signals,
    build_public_snapshot,
)


class CompanyReportServiceError(RuntimeError):
    code = "company_report_internal_error"
    safe_message = "company report request failed"


class InvalidCompanyReportIdentifierError(CompanyReportServiceError):
    code = "invalid_inn"
    safe_message = "invalid INN"


class CompanyReportServiceNotFoundError(CompanyReportServiceError):
    code = "company_report_not_found"
    safe_message = "company report not found"


class CompanyReportPendingError(CompanyReportServiceError):
    code = "report_pending"
    safe_message = "company report is pending"


class CompanyReportServiceStateConflictError(CompanyReportServiceError):
    code = "report_state_conflict"
    safe_message = "company report state conflict"


class CompanyReportServiceUnavailableError(CompanyReportServiceError):
    code = "company_report_unavailable"
    safe_message = "company report service is unavailable"


class CompanyReportServiceInternalError(CompanyReportServiceError):
    code = "company_report_internal_error"
    safe_message = "company report processing failed"


async def create_or_reuse_company_report(
    session: AsyncSession,
    *,
    inn: str,
) -> CompanyReportAcceptedResponse:
    normalized = validate_company_report_inn(inn)
    try:
        enqueued = await enqueue_company_report_job(session, normalized)
        await session.commit()
    except CompanyReportJobStateConflictError as exc:
        await session.rollback()
        raise CompanyReportServiceStateConflictError(
            CompanyReportServiceStateConflictError.safe_message
        ) from exc
    except CompanyReportPersistenceError as exc:
        await session.rollback()
        raise CompanyReportServiceUnavailableError(
            CompanyReportServiceUnavailableError.safe_message
        ) from exc
    except SQLAlchemyError as exc:
        await session.rollback()
        raise CompanyReportServiceUnavailableError(
            CompanyReportServiceUnavailableError.safe_message
        ) from exc
    return CompanyReportAcceptedResponse(
        report_id=enqueued.report_id,
        status="pending",
        reused=enqueued.reused,
    )


async def get_company_report_status(
    session: AsyncSession,
    *,
    inn: str,
) -> CompanyReportStatusResponse:
    normalized = validate_company_report_inn(inn)
    try:
        record = await get_latest_run_status_by_identifier(session, normalized)
    except CompanyReportPersistenceError as exc:
        raise CompanyReportServiceUnavailableError(
            CompanyReportServiceUnavailableError.safe_message
        ) from exc
    except SQLAlchemyError as exc:
        raise CompanyReportServiceUnavailableError(
            CompanyReportServiceUnavailableError.safe_message
        ) from exc
    if record is None:
        raise CompanyReportServiceNotFoundError(
            CompanyReportServiceNotFoundError.safe_message
        )
    return CompanyReportStatusResponse(
        report_id=record.report_id,
        status=record.lifecycle_status,
        started_at=record.started_at,
        generated_at=record.generated_at,
        finished_at=record.finished_at,
        fresh_until=record.fresh_until,
    )


async def get_latest_company_report(
    session: AsyncSession,
    *,
    inn: str,
    settings: Settings,
    include_ai_explanation: bool = False,
) -> CompanyReportResponse:
    normalized = validate_company_report_inn(inn)
    try:
        finalized = await get_latest_finalized_report_record(session, normalized)
        latest_run = await get_latest_run_status_by_identifier(session, normalized)
    except CompanyReportPersistenceError as exc:
        raise CompanyReportServiceUnavailableError(
            CompanyReportServiceUnavailableError.safe_message
        ) from exc
    except SQLAlchemyError as exc:
        raise CompanyReportServiceUnavailableError(
            CompanyReportServiceUnavailableError.safe_message
        ) from exc

    if finalized is None:
        if latest_run is not None and latest_run.lifecycle_status == "pending":
            raise CompanyReportPendingError(CompanyReportPendingError.safe_message)
        raise CompanyReportServiceNotFoundError(
            CompanyReportServiceNotFoundError.safe_message
        )

    if finalized.normalized_snapshot is None:
        if finalized.lifecycle_status != "failed":
            raise CompanyReportServiceInternalError(
                CompanyReportServiceInternalError.safe_message
            )
        response = CompanyReportResponse(
            report_id=finalized.report_id,
            status="failed",
            started_at=finalized.started_at,
            generated_at=finalized.generated_at,
            finished_at=finalized.finished_at,
            fresh_until=finalized.fresh_until,
            report=None,
            signals=None,
            scoring=None,
            ai_explanation=None,
            failure=_safe_infrastructure_failure(finalized.safe_error_snapshot),
            canonical_path=None,
        )
        assert_public_payload_is_safe(response.model_dump(mode="json"))
        return response

    snapshot_before = deepcopy(finalized.normalized_snapshot)
    hash_before = calculate_company_report_snapshot_hash(snapshot_before)
    if finalized.snapshot_hash is not None and finalized.snapshot_hash != hash_before:
        raise CompanyReportServiceInternalError(
            CompanyReportServiceInternalError.safe_message
        )
    try:
        report = company_report_from_snapshot(snapshot_before)
        if (
            report.report_id != finalized.report_id
            or report.report_version != finalized.report_version
            or report.status.value != finalized.lifecycle_status
        ):
            raise CompanyReportSnapshotError(
                "snapshot lifecycle identity does not match"
            )
        signals = evaluate_signals(report)
        scoring = score_signals(signals)
        public_report = build_public_snapshot(report)
        public_signals = build_public_signals(signals)
    except (CompanyReportSnapshotError, TypeError, ValueError) as exc:
        raise CompanyReportServiceInternalError(
            CompanyReportServiceInternalError.safe_message
        ) from exc
    except Exception as exc:
        raise CompanyReportServiceInternalError(
            CompanyReportServiceInternalError.safe_message
        ) from exc

    if finalized.normalized_snapshot != snapshot_before:
        raise CompanyReportServiceInternalError(
            CompanyReportServiceInternalError.safe_message
        )
    if calculate_company_report_snapshot_hash(snapshot_before) != hash_before:
        raise CompanyReportServiceInternalError(
            CompanyReportServiceInternalError.safe_message
        )

    ai_result = None
    if include_ai_explanation:
        try:
            ai_result = await explain_scoring_result(
                settings,
                report,
                signals,
                scoring,
            )
        except Exception:
            ai_result = _unexpected_ai_failure(settings)

    response = CompanyReportResponse(
        report_id=finalized.report_id,
        status=finalized.lifecycle_status,
        started_at=finalized.started_at,
        generated_at=finalized.generated_at,
        finished_at=finalized.finished_at,
        fresh_until=finalized.fresh_until,
        report=public_report,
        signals=public_signals,
        scoring=scoring,
        ai_explanation=ai_result,
        failure=None,
        canonical_path=_canonical_path_for_report(report, normalized),
    )
    assert_public_payload_is_safe(response.model_dump(mode="json"))
    return response


def _canonical_path_for_report(report: object, inn: str) -> str | None:
    """Build an ephemeral canonical path from safe final counterparty facts."""
    if not hasattr(report, "status") or getattr(report.status, "value", None) == "failed":
        return None
    counterparty = getattr(report, "counterparty", None)
    if counterparty is None or getattr(counterparty, "inn", None) != inn:
        return None
    name = getattr(counterparty, "short_name", None) or getattr(counterparty, "full_name", None)
    if not isinstance(name, str) or not name.strip():
        return None
    try:
        return canonical_path(inn, name.strip())
    except SeoPolicyError:
        return None


def validate_company_report_inn(value: str) -> str:
    try:
        normalized = normalize_identifier(value)
        identifier_type = identify_identifier_type(normalized)
    except Exception as exc:
        raise InvalidCompanyReportIdentifierError(
            InvalidCompanyReportIdentifierError.safe_message
        ) from exc
    if identifier_type not in {
        DataNewtonIdentifierType.LEGAL_ENTITY_INN,
        DataNewtonIdentifierType.INDIVIDUAL_ENTREPRENEUR_INN,
    }:
        raise InvalidCompanyReportIdentifierError(
            InvalidCompanyReportIdentifierError.safe_message
        )
    return normalized


_FAILURE_DETAILS = {
    "report_execution_failed": (
        "company report execution failed",
        True,
    ),
    "report_execution_interrupted": (
        "company report execution was interrupted",
        True,
    ),
    "report_job_precondition_failed": (
        "company report job precondition failed",
        False,
    ),
}


def _safe_infrastructure_failure(
    snapshot: dict[str, object] | None,
) -> CompanyReportSafeFailureResponse:
    code_value = snapshot.get("code") if snapshot is not None else None
    code = code_value if isinstance(code_value, str) else "report_execution_failed"
    if code not in _FAILURE_DETAILS:
        code = "report_execution_failed"
    message, retryable = _FAILURE_DETAILS[code]
    return CompanyReportSafeFailureResponse(
        code=code,
        message=message,
        retryable=retryable,
    )


def _unexpected_ai_failure(settings: Settings) -> AIExplanationResult:
    return AIExplanationResult(
        status=AIExplanationStatus.CONFIGURATION_ERROR,
        failure=AIExplanationFailure(
            safe_code="explanation_unavailable",
            model_profile=settings.ai_explanation_model_profile,
            prompt_version=settings.ai_explanation_prompt_version,
            output_schema_version="1",
            retry_attempted=False,
        ),
    )


__all__ = [
    "CompanyReportPendingError",
    "CompanyReportServiceError",
    "CompanyReportServiceInternalError",
    "CompanyReportServiceNotFoundError",
    "CompanyReportServiceStateConflictError",
    "CompanyReportServiceUnavailableError",
    "InvalidCompanyReportIdentifierError",
    "create_or_reuse_company_report",
    "get_company_report_status",
    "get_latest_company_report",
    "validate_company_report_inn",
]
