from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from product_api.company_reports.aggregate import CompanyReport
from product_api.company_reports.explanation import AIExplanationResult
from product_api.company_reports.scoring import ScoringResult
from product_api.company_reports.signals import SignalEvaluationResult


class StrictPublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CompanyReportCreateRequest(StrictPublicModel):
    inn: str


class CompanyReportGetQuery(StrictPublicModel):
    include_ai_explanation: bool = False


class CompanyReportAcceptedResponse(StrictPublicModel):
    report_id: UUID
    status: Literal["pending"]
    reused: bool


class CompanyReportStatusResponse(StrictPublicModel):
    report_id: UUID
    status: Literal["pending", "complete", "partial", "failed"]
    started_at: datetime
    generated_at: datetime | None = None
    finished_at: datetime | None = None
    fresh_until: datetime | None = None


class CompanyReportSafeFailureResponse(StrictPublicModel):
    code: str
    message: str
    retryable: bool


class CompanyReportPublicWarning(StrictPublicModel):
    code: str
    dataset: str | None = None
    path: str | None = None
    message: str


class CompanyReportPublicSourceTime(StrictPublicModel):
    dataset: str
    received_at: datetime


class CompanyReportPublicDatasetFailure(StrictPublicModel):
    code: str
    message: str
    retryable: bool


class CompanyReportPublicDataset(StrictPublicModel):
    dataset: str
    status: str
    source_time: CompanyReportPublicSourceTime | None = None
    duration_ms: float | None = Field(default=None, ge=0)
    attempts: int | None = Field(default=None, ge=0)
    warnings: list[CompanyReportPublicWarning] = Field(default_factory=list)
    failure: CompanyReportPublicDatasetFailure | None = None


class CompanyReportPublicCompleteness(StrictPublicModel):
    required_datasets: tuple[str, ...]
    available_datasets: list[str] = Field(default_factory=list)
    missing_datasets: list[str] = Field(default_factory=list)
    unavailable_datasets: list[str] = Field(default_factory=list)
    available_count: int = Field(ge=0)
    required_count: int = Field(ge=1)
    ratio: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    percent: int = Field(ge=0, le=100)
    identity_available: bool
    financial_data_available: bool
    arbitration_data_available: bool


class CompanyReportPublicFreshness(StrictPublicModel):
    oldest_received_at: datetime | None = None
    newest_received_at: datetime | None = None
    datasets_received_at: dict[str, datetime] = Field(default_factory=dict)
    generated_at: datetime
    age_seconds_at_generation: Decimal | None = None
    warnings: list[CompanyReportPublicWarning] = Field(default_factory=list)


class CompanyReportPublicSnapshot(StrictPublicModel):
    report_version: Literal["1", "2"]
    status: Literal["complete", "partial", "failed"]
    counterparty: dict[str, Any] | None = None
    finance: dict[str, Any] | None = None
    arbitration: dict[str, Any] | None = None
    datasets: dict[str, CompanyReportPublicDataset]
    completeness: CompanyReportPublicCompleteness
    freshness: CompanyReportPublicFreshness
    warnings: list[CompanyReportPublicWarning] = Field(default_factory=list)
    usable_for_public_page: bool
    usable_for_future_scoring: bool


class CompanyReportPublicSignalSource(StrictPublicModel):
    dataset: str
    received_at: datetime


class CompanyReportPublicSignal(StrictPublicModel):
    code: str
    category: str
    direction: str
    strength: str
    confidence: str
    period: dict[str, Any]
    factual_basis: dict[str, Any]
    sources: list[CompanyReportPublicSignalSource] = Field(default_factory=list)
    warnings: list[CompanyReportPublicWarning] = Field(default_factory=list)


class CompanyReportPublicSignalWarning(StrictPublicModel):
    code: str
    rule_code: str | None = None
    dataset: str | None = None
    message: str
    evaluation_basis: dict[str, Any]


class CompanyReportPublicSignals(StrictPublicModel):
    ruleset_version: Literal["1"]
    signals: list[CompanyReportPublicSignal] = Field(default_factory=list)
    warnings: list[CompanyReportPublicSignalWarning] = Field(default_factory=list)


class CompanyReportResponse(StrictPublicModel):
    report_id: UUID
    status: Literal["complete", "partial", "failed"]
    started_at: datetime
    generated_at: datetime | None = None
    finished_at: datetime | None = None
    fresh_until: datetime | None = None
    report: CompanyReportPublicSnapshot | None = None
    signals: CompanyReportPublicSignals | None = None
    scoring: ScoringResult | None = None
    ai_explanation: AIExplanationResult | None = None
    failure: CompanyReportSafeFailureResponse | None = None
    canonical_path: str | None = None


_FACT_EXCLUDED_KEYS = {
    "source",
    "warnings",
    "raw_role",
    "raw_status",
    "raw_result_type",
    "internal_id",
    "requested_filters",
    "source_paths",
}
_FORBIDDEN_PUBLIC_KEYS = {
    "raw_payload",
    "headers",
    "authorization",
    "api_key",
    "apikey",
    "provider_limit_metadata",
    "request_id",
    "endpoint",
    "response_hash",
    "worker_token",
    "lease_expires_at",
    "safe_error_type",
}
_DATASET_FAILURE_MESSAGES = {
    "not_found": "dataset was not found",
    "access_denied": "dataset access was denied",
    "authentication_error": "dataset authentication failed",
    "rate_limited": "dataset rate limit was reached",
    "temporarily_unavailable": "dataset is temporarily unavailable",
    "invalid_response": "dataset response was invalid",
    "normalization_error": "dataset normalization failed",
    "disabled": "dataset is disabled",
    "configuration_error": "dataset configuration is invalid",
    "unexpected_error": "dataset is unavailable",
}


def build_public_snapshot(report: CompanyReport) -> CompanyReportPublicSnapshot:
    facts = {
        "counterparty": report.counterparty,
        "finance": report.finance,
        "arbitration": report.arbitration,
    }
    datasets: dict[str, CompanyReportPublicDataset] = {}
    for dataset_name in sorted(report.datasets):
        dataset = report.datasets[dataset_name]
        source_time = (
            CompanyReportPublicSourceTime(
                dataset=dataset_name,
                received_at=dataset.source.received_at,
            )
            if dataset.source is not None
            else None
        )
        failure = None
        if dataset.error is not None:
            failure = CompanyReportPublicDatasetFailure(
                code=dataset.status.value,
                message=_DATASET_FAILURE_MESSAGES.get(
                    dataset.status.value,
                    "dataset is unavailable",
                ),
                retryable=dataset.error.retryable,
            )
        datasets[dataset_name] = CompanyReportPublicDataset(
            dataset=dataset_name,
            status=dataset.status.value,
            source_time=source_time,
            duration_ms=dataset.duration_ms,
            attempts=dataset.attempts,
            warnings=[
                CompanyReportPublicWarning(
                    code=warning.code,
                    dataset=warning.dataset,
                    message=warning.message,
                )
                for warning in dataset.warnings
            ],
            failure=failure,
        )

    snapshot = CompanyReportPublicSnapshot(
        report_version=report.report_version,
        status=report.status.value,
        counterparty=_safe_fact_payload(facts["counterparty"]),
        finance=_safe_fact_payload(facts["finance"]),
        arbitration=_safe_fact_payload(facts["arbitration"]),
        datasets=datasets,
        completeness=CompanyReportPublicCompleteness.model_validate(
            report.completeness.model_dump(mode="python")
        ),
        freshness=CompanyReportPublicFreshness(
            oldest_received_at=report.freshness.oldest_received_at,
            newest_received_at=report.freshness.newest_received_at,
            datasets_received_at=dict(report.freshness.datasets_received_at),
            generated_at=report.freshness.generated_at,
            age_seconds_at_generation=report.freshness.age_seconds_at_generation,
            warnings=[
                CompanyReportPublicWarning(
                    code=warning.code,
                    dataset=warning.dataset,
                    message=warning.message,
                )
                for warning in report.freshness.warnings
            ],
        ),
        warnings=[
            CompanyReportPublicWarning(
                code=warning.code,
                dataset=warning.dataset,
                message=warning.message,
            )
            for warning in report.warnings
        ],
        usable_for_public_page=report.usable_for_public_page,
        usable_for_future_scoring=report.usable_for_future_scoring,
    )
    assert_public_payload_is_safe(snapshot.model_dump(mode="json"))
    return snapshot


def build_public_signals(
    evaluation: SignalEvaluationResult,
) -> CompanyReportPublicSignals:
    public = CompanyReportPublicSignals(
        ruleset_version=evaluation.ruleset_version,
        signals=[
            CompanyReportPublicSignal(
                code=signal.code,
                category=signal.category.value,
                direction=signal.direction.value,
                strength=signal.strength.value,
                confidence=signal.confidence.value,
                period=signal.period.model_dump(mode="json"),
                factual_basis=signal.factual_basis.model_dump(mode="json"),
                sources=[
                    CompanyReportPublicSignalSource(
                        dataset=source.dataset,
                        received_at=source.received_at,
                    )
                    for source in signal.source
                ],
                warnings=[
                    CompanyReportPublicWarning(
                        code=warning.code,
                        dataset=warning.dataset,
                        message=warning.message,
                    )
                    for warning in signal.warnings
                ],
            )
            for signal in evaluation.signals
        ],
        warnings=[
            CompanyReportPublicSignalWarning(
                code=warning.code,
                rule_code=warning.rule_code,
                dataset=warning.dataset,
                message=warning.message,
                evaluation_basis=warning.evaluation_basis.model_dump(mode="json"),
            )
            for warning in evaluation.warnings
        ],
    )
    assert_public_payload_is_safe(public.model_dump(mode="json"))
    return public


def assert_public_payload_is_safe(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower() in _FORBIDDEN_PUBLIC_KEYS:
                raise ValueError("public payload contains a forbidden field")
            assert_public_payload_is_safe(nested)
    elif isinstance(value, list):
        for nested in value:
            assert_public_payload_is_safe(nested)


def _safe_fact_payload(value: object) -> dict[str, Any] | None:
    if value is None:
        return None
    if not hasattr(value, "model_dump"):
        raise TypeError("public company fact is not a domain model")
    payload = value.model_dump(mode="json")
    safe = _strip_excluded_fact_keys(payload)
    if not isinstance(safe, dict):
        raise TypeError("public company fact payload is invalid")
    assert_public_payload_is_safe(safe)
    return safe


def _strip_excluded_fact_keys(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _strip_excluded_fact_keys(nested)
            for key, nested in value.items()
            if str(key).lower() not in _FACT_EXCLUDED_KEYS
        }
    if isinstance(value, list):
        return [_strip_excluded_fact_keys(nested) for nested in value]
    if isinstance(value, (str, int, bool, float, Decimal, date, datetime)) or value is None:
        return value
    return str(value)


__all__ = [
    "CompanyReportAcceptedResponse",
    "CompanyReportCreateRequest",
    "CompanyReportGetQuery",
    "CompanyReportPublicDataset",
    "CompanyReportPublicSnapshot",
    "CompanyReportPublicSourceTime",
    "CompanyReportPublicWarning",
    "CompanyReportResponse",
    "CompanyReportSafeFailureResponse",
    "CompanyReportStatusResponse",
    "assert_public_payload_is_safe",
    "build_public_signals",
    "build_public_snapshot",
]
