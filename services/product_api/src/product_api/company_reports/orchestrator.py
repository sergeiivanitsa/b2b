from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID, uuid4

from product_api.providers.datanewton import (
    ARBITRATION_CASES_ENDPOINT,
    COUNTERPARTY_ENDPOINT,
    FINANCE_ENDPOINT,
    DataNewtonError,
    DataNewtonIdentifierType,
    DataNewtonInvalidResponseError,
    DataNewtonNetworkError,
    DataNewtonNotFoundError,
    DataNewtonRateLimitError,
    DataNewtonServerError,
    DataNewtonUnsupportedIdentifierError,
    DataNewtonValidationError,
    DataNewtonAccessDeniedError,
    DataNewtonAuthenticationError,
    DataNewtonConfigurationError,
    DataNewtonDisabledError,
    DataNewtonResult,
    identify_identifier_type,
    normalize_identifier,
)

from .aggregate import (
    CompanyReport,
    CompanyReportCompleteness,
    CompanyReportStatus,
    DatasetReport,
    DatasetReportStatus,
    ReportFreshness,
    ReportWarning,
    SafeDatasetError,
)
from .errors import (
    CompanyReportInputError,
    CompanyReportNormalizationError,
    DatasetMismatchError,
    InvalidDatasetPayloadError,
)
from .models import (
    ArbitrationFacts,
    CounterpartyFacts,
    FinanceFacts,
    NormalizationWarning,
)
from .normalizers import normalize_arbitration, normalize_counterparty, normalize_finance
from .provider_protocol import CompanyReportProvider

REQUIRED_DATASETS: tuple[str, ...] = ("counterparty", "finance", "arbitration")
_ENDPOINTS = {
    "counterparty": COUNTERPARTY_ENDPOINT,
    "finance": FINANCE_ENDPOINT,
    "arbitration": ARBITRATION_CASES_ENDPOINT,
}

_ERROR_CLASSIFICATION: tuple[tuple[type[Exception], DatasetReportStatus, str, str], ...] = (
    (DataNewtonNotFoundError, DatasetReportStatus.NOT_FOUND, "dataset was not found", "dataset_not_found"),
    (DataNewtonAccessDeniedError, DatasetReportStatus.ACCESS_DENIED, "dataset access was denied", "dataset_access_denied"),
    (DataNewtonAuthenticationError, DatasetReportStatus.AUTHENTICATION_ERROR, "provider authentication failed", "dataset_authentication_error"),
    (DataNewtonRateLimitError, DatasetReportStatus.RATE_LIMITED, "provider rate limit was reached", "dataset_rate_limited"),
    (DataNewtonServerError, DatasetReportStatus.TEMPORARILY_UNAVAILABLE, "provider is temporarily unavailable", "dataset_temporarily_unavailable"),
    (DataNewtonNetworkError, DatasetReportStatus.TEMPORARILY_UNAVAILABLE, "provider is temporarily unavailable", "dataset_temporarily_unavailable"),
    (DataNewtonInvalidResponseError, DatasetReportStatus.INVALID_RESPONSE, "provider response was invalid", "dataset_invalid_response"),
    (DataNewtonDisabledError, DatasetReportStatus.DISABLED, "provider dataset is disabled", "dataset_disabled"),
    (DataNewtonConfigurationError, DatasetReportStatus.CONFIGURATION_ERROR, "provider configuration is invalid", "dataset_configuration_error"),
    (DataNewtonUnsupportedIdentifierError, DatasetReportStatus.NORMALIZATION_ERROR, "dataset normalization failed", "dataset_normalization_failed"),
    (DatasetMismatchError, DatasetReportStatus.NORMALIZATION_ERROR, "dataset normalization failed", "dataset_normalization_failed"),
    (InvalidDatasetPayloadError, DatasetReportStatus.NORMALIZATION_ERROR, "dataset normalization failed", "dataset_normalization_failed"),
    (CompanyReportNormalizationError, DatasetReportStatus.NORMALIZATION_ERROR, "dataset normalization failed", "dataset_normalization_failed"),
    (DataNewtonValidationError, DatasetReportStatus.NORMALIZATION_ERROR, "dataset normalization failed", "dataset_normalization_failed"),
)


@dataclass
class _DatasetOutcome:
    report: DatasetReport
    facts: Any | None = None


async def build_company_report(
    identifier: str,
    *,
    provider: CompanyReportProvider,
    request_id: str | None = None,
    arbitration_limit: int = 100,
    clock: Callable[[], datetime] | None = None,
    report_id_factory: Callable[[], UUID] | None = None,
) -> CompanyReport:
    normalized_identifier = _normalize_report_identifier(identifier)
    identifier_type = identify_identifier_type(normalized_identifier)
    _validate_arbitration_limit(arbitration_limit)

    report_id = (report_id_factory or uuid4)()
    base_request_id = request_id or f"report:{report_id}"

    tasks = (
        _run_dataset(
            dataset="counterparty",
            request_id=f"{base_request_id}:counterparty",
            fetch=lambda: provider.fetch_counterparty(
                normalized_identifier,
                request_id=f"{base_request_id}:counterparty",
            ),
            normalize=normalize_counterparty,
            expected_endpoint=COUNTERPARTY_ENDPOINT,
        ),
        _run_dataset(
            dataset="finance",
            request_id=f"{base_request_id}:finance",
            fetch=lambda: provider.fetch_finance(
                normalized_identifier,
                request_id=f"{base_request_id}:finance",
            ),
            normalize=normalize_finance,
            expected_endpoint=FINANCE_ENDPOINT,
        ),
        _run_dataset(
            dataset="arbitration",
            request_id=f"{base_request_id}:arbitration",
            fetch=lambda: provider.fetch_arbitration_cases(
                normalized_identifier,
                offset=0,
                limit=arbitration_limit,
                request_id=f"{base_request_id}:arbitration",
            ),
            normalize=lambda result: normalize_arbitration(
                result,
                target_identifier=normalized_identifier,
            ),
            expected_endpoint=ARBITRATION_CASES_ENDPOINT,
        ),
    )
    outcomes = dict(zip(REQUIRED_DATASETS, await asyncio.gather(*tasks), strict=True))
    dataset_reports = {
        dataset: outcome.report for dataset, outcome in outcomes.items()
    }

    generated_at = _as_utc((clock or _utc_now)())
    completeness = _build_completeness(dataset_reports)
    status = _build_status(completeness.available_count)
    freshness = _build_freshness(dataset_reports, generated_at)
    warnings = _build_report_warnings(dataset_reports, status, completeness)

    counterparty = _available_fact(outcomes["counterparty"], CounterpartyFacts)
    finance = _available_fact(outcomes["finance"], FinanceFacts)
    arbitration = _available_fact(outcomes["arbitration"], ArbitrationFacts)
    return CompanyReport(
        report_id=report_id,
        generated_at=generated_at,
        target_identifier=normalized_identifier,
        target_identifier_type=identifier_type,
        status=status,
        counterparty=counterparty,
        finance=finance,
        arbitration=arbitration,
        datasets=dataset_reports,
        completeness=completeness,
        freshness=freshness,
        warnings=warnings,
        usable_for_public_page=completeness.identity_available,
        usable_for_future_scoring=(
            completeness.identity_available
            and (completeness.financial_data_available or completeness.arbitration_data_available)
        ),
    )


async def _run_dataset(
    *,
    dataset: str,
    request_id: str,
    fetch: Callable[[], Awaitable[DataNewtonResult]],
    normalize: Callable[[DataNewtonResult], Any],
    expected_endpoint: str,
) -> _DatasetOutcome:
    started = time.perf_counter()
    result: DataNewtonResult | None = None
    try:
        result = await fetch()
        if not isinstance(result, DataNewtonResult):
            raise CompanyReportNormalizationError(
                "provider returned an invalid result object",
                dataset=dataset,
                endpoint=expected_endpoint,
            )
        facts = normalize(result)
        duration_ms = _duration_ms(started)
        fact_warnings = [
            _report_warning(item, dataset) for item in getattr(facts, "warnings", [])
        ]
        return _DatasetOutcome(
            report=DatasetReport(
                dataset=dataset,
                status=DatasetReportStatus.AVAILABLE,
                source=facts.source,
                duration_ms=duration_ms,
                attempts=result.attempts,
                warnings=fact_warnings,
            ),
            facts=facts,
        )
    except Exception as exc:
        duration_ms = _duration_ms(started)
        status, safe_message, warning_code = _classify_exception(exc)
        safe_error = _safe_dataset_error(
            exc,
            safe_message=safe_message,
            request_id=request_id,
            endpoint=expected_endpoint,
            attempts=result.attempts if result is not None else None,
        )
        return _DatasetOutcome(
            report=DatasetReport(
                dataset=dataset,
                status=status,
                error=safe_error,
                duration_ms=duration_ms,
                attempts=safe_error.attempts,
                warnings=[
                    ReportWarning(code=warning_code, dataset=dataset, message=safe_message)
                ],
            )
        )


def _normalize_report_identifier(identifier: str) -> str:
    try:
        return normalize_identifier(identifier)
    except Exception as exc:
        raise CompanyReportInputError("identifier is invalid") from exc


def _validate_arbitration_limit(limit: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise CompanyReportInputError("arbitration_limit must be between 1 and 1000")


def _classify_exception(
    exc: Exception,
) -> tuple[DatasetReportStatus, str, str]:
    for exception_type, status, message, warning_code in _ERROR_CLASSIFICATION:
        if isinstance(exc, exception_type):
            return status, message, warning_code
    return (
        DatasetReportStatus.UNEXPECTED_ERROR,
        "unexpected provider error",
        "dataset_unexpected_error",
    )


def _safe_dataset_error(
    exc: Exception,
    *,
    safe_message: str,
    request_id: str,
    endpoint: str,
    attempts: int | None,
) -> SafeDatasetError:
    if isinstance(exc, DataNewtonError):
        return SafeDatasetError(
            error_type=type(exc).__name__,
            message=safe_message,
            status_code=exc.status_code,
            retryable=exc.retryable,
            attempts=max(exc.attempts, 0),
            request_id=exc.request_id or request_id,
            endpoint=exc.endpoint or endpoint,
        )
    error_endpoint = getattr(exc, "endpoint", None) or endpoint
    return SafeDatasetError(
        error_type=type(exc).__name__,
        message=safe_message,
        status_code=getattr(exc, "status_code", None),
        retryable=bool(getattr(exc, "retryable", False)),
        attempts=attempts,
        request_id=getattr(exc, "request_id", None) or request_id,
        endpoint=error_endpoint,
    )


def _build_status(available_count: int) -> CompanyReportStatus:
    if available_count == len(REQUIRED_DATASETS):
        return CompanyReportStatus.COMPLETE
    if available_count:
        return CompanyReportStatus.PARTIAL
    return CompanyReportStatus.FAILED


def _build_completeness(
    dataset_reports: dict[str, DatasetReport],
) -> CompanyReportCompleteness:
    available = [
        dataset
        for dataset in REQUIRED_DATASETS
        if dataset_reports[dataset].status is DatasetReportStatus.AVAILABLE
    ]
    unavailable = [dataset for dataset in REQUIRED_DATASETS if dataset not in available]
    required_count = len(REQUIRED_DATASETS)
    available_count = len(available)
    ratio = Decimal(available_count) / Decimal(required_count)
    percent = int((ratio * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return CompanyReportCompleteness(
        required_datasets=REQUIRED_DATASETS,
        available_datasets=available,
        missing_datasets=list(unavailable),
        unavailable_datasets=list(unavailable),
        available_count=available_count,
        required_count=required_count,
        ratio=ratio,
        percent=percent,
        identity_available=dataset_reports["counterparty"].status
        is DatasetReportStatus.AVAILABLE,
        financial_data_available=dataset_reports["finance"].status
        is DatasetReportStatus.AVAILABLE,
        arbitration_data_available=dataset_reports["arbitration"].status
        is DatasetReportStatus.AVAILABLE,
    )


def _build_freshness(
    dataset_reports: dict[str, DatasetReport],
    generated_at: datetime,
) -> ReportFreshness:
    received = {
        dataset: report.source.received_at
        for dataset, report in dataset_reports.items()
        if report.status is DatasetReportStatus.AVAILABLE and report.source is not None
    }
    if not received:
        return ReportFreshness(generated_at=generated_at)
    oldest = min(received.values())
    newest = max(received.values())
    age_seconds = max(Decimal("0"), Decimal(str((generated_at - oldest).total_seconds())))
    return ReportFreshness(
        oldest_received_at=oldest,
        newest_received_at=newest,
        datasets_received_at=received,
        generated_at=generated_at,
        age_seconds_at_generation=age_seconds,
    )


def _build_report_warnings(
    dataset_reports: dict[str, DatasetReport],
    status: CompanyReportStatus,
    completeness: CompanyReportCompleteness,
) -> list[ReportWarning]:
    warnings: list[ReportWarning] = []
    seen: set[tuple[str, str | None, str]] = set()
    for dataset in REQUIRED_DATASETS:
        report = dataset_reports[dataset]
        if report.status is DatasetReportStatus.AVAILABLE:
            for item in report.warnings:
                key = (item.code, item.dataset, item.message)
                if key not in seen:
                    warnings.append(item)
                    seen.add(key)
        if report.status is not DatasetReportStatus.AVAILABLE:
            warnings.append(
                ReportWarning(
                    code=_warning_code_for_status(report.status),
                    dataset=dataset,
                    message=_message_for_status(report.status),
                )
            )
    if status is CompanyReportStatus.PARTIAL:
        warnings.append(ReportWarning(code="report_partial", message="report has unavailable datasets"))
    elif status is CompanyReportStatus.FAILED:
        warnings.append(ReportWarning(code="report_failed", message="no required dataset is available"))
    if not completeness.identity_available:
        warnings.append(ReportWarning(code="identity_unavailable", dataset="counterparty", message="identity data is unavailable"))
    if not completeness.financial_data_available:
        warnings.append(ReportWarning(code="financial_data_unavailable", dataset="finance", message="financial data is unavailable"))
    if not completeness.arbitration_data_available:
        warnings.append(ReportWarning(code="arbitration_data_unavailable", dataset="arbitration", message="arbitration data is unavailable"))
    return warnings


def _warning_code_for_status(status: DatasetReportStatus) -> str:
    return {
        DatasetReportStatus.NOT_FOUND: "dataset_not_found",
        DatasetReportStatus.ACCESS_DENIED: "dataset_access_denied",
        DatasetReportStatus.AUTHENTICATION_ERROR: "dataset_authentication_error",
        DatasetReportStatus.RATE_LIMITED: "dataset_rate_limited",
        DatasetReportStatus.TEMPORARILY_UNAVAILABLE: "dataset_temporarily_unavailable",
        DatasetReportStatus.INVALID_RESPONSE: "dataset_invalid_response",
        DatasetReportStatus.NORMALIZATION_ERROR: "dataset_normalization_failed",
        DatasetReportStatus.DISABLED: "dataset_disabled",
        DatasetReportStatus.CONFIGURATION_ERROR: "dataset_configuration_error",
        DatasetReportStatus.UNEXPECTED_ERROR: "dataset_unexpected_error",
        DatasetReportStatus.AVAILABLE: "",
    }[status]


def _message_for_status(status: DatasetReportStatus) -> str:
    return {
        DatasetReportStatus.NOT_FOUND: "dataset was not found",
        DatasetReportStatus.ACCESS_DENIED: "dataset access was denied",
        DatasetReportStatus.AUTHENTICATION_ERROR: "provider authentication failed",
        DatasetReportStatus.RATE_LIMITED: "provider rate limit was reached",
        DatasetReportStatus.TEMPORARILY_UNAVAILABLE: "provider is temporarily unavailable",
        DatasetReportStatus.INVALID_RESPONSE: "provider response was invalid",
        DatasetReportStatus.NORMALIZATION_ERROR: "dataset normalization failed",
        DatasetReportStatus.DISABLED: "provider dataset is disabled",
        DatasetReportStatus.CONFIGURATION_ERROR: "provider configuration is invalid",
        DatasetReportStatus.UNEXPECTED_ERROR: "unexpected provider error",
        DatasetReportStatus.AVAILABLE: "",
    }[status]


def _report_warning(item: NormalizationWarning, dataset: str) -> ReportWarning:
    return ReportWarning(code=item.code, dataset=dataset, message=item.message)


def _available_fact(outcome: _DatasetOutcome, expected_type: type[Any]) -> Any:
    if outcome.report.status is not DatasetReportStatus.AVAILABLE:
        return None
    if isinstance(outcome.facts, expected_type):
        return outcome.facts
    return None


def _duration_ms(started: float) -> float:
    return max(0.0, (time.perf_counter() - started) * 1000)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
