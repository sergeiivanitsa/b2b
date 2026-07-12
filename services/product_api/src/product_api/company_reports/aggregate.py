from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from product_api.providers.datanewton import DataNewtonIdentifierType

from .models import (
    ArbitrationFacts,
    CounterpartyFacts,
    FinanceFacts,
    FrozenDomainModel,
    SourceMetadata,
)


class CompanyReportStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class DatasetReportStatus(StrEnum):
    AVAILABLE = "available"
    NOT_FOUND = "not_found"
    ACCESS_DENIED = "access_denied"
    AUTHENTICATION_ERROR = "authentication_error"
    RATE_LIMITED = "rate_limited"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    INVALID_RESPONSE = "invalid_response"
    NORMALIZATION_ERROR = "normalization_error"
    DISABLED = "disabled"
    CONFIGURATION_ERROR = "configuration_error"
    UNEXPECTED_ERROR = "unexpected_error"


class ReportWarning(FrozenDomainModel):
    code: str
    dataset: str | None = None
    message: str


class SafeDatasetError(FrozenDomainModel):
    error_type: str
    message: str
    status_code: int | None = None
    retryable: bool = False
    attempts: int | None = Field(default=None, ge=0)
    request_id: str | None = None
    endpoint: str | None = None


class DatasetReport(FrozenDomainModel):
    dataset: str
    status: DatasetReportStatus
    source: SourceMetadata | None = None
    error: SafeDatasetError | None = None
    duration_ms: float | None = Field(default=None, ge=0)
    attempts: int | None = Field(default=None, ge=0)
    warnings: list[ReportWarning] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_status_payload(self) -> DatasetReport:
        if self.status is DatasetReportStatus.AVAILABLE:
            if self.source is None or self.error is not None:
                raise ValueError("available dataset must have source and no error")
        elif self.error is None or self.source is not None:
            raise ValueError("unavailable dataset must have error and no source")
        return self


class CompanyReportCompleteness(FrozenDomainModel):
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


class ReportFreshness(FrozenDomainModel):
    oldest_received_at: datetime | None = None
    newest_received_at: datetime | None = None
    datasets_received_at: dict[str, datetime] = Field(default_factory=dict)
    generated_at: datetime
    age_seconds_at_generation: Decimal | None = None
    warnings: list[ReportWarning] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def _generated_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value.astimezone(timezone.utc)


class CompanyReport(FrozenDomainModel):
    report_id: UUID
    report_version: Literal["1"] = "1"
    generated_at: datetime
    target_identifier: str = Field(repr=False)
    target_identifier_type: DataNewtonIdentifierType
    status: CompanyReportStatus
    counterparty: CounterpartyFacts | None = None
    finance: FinanceFacts | None = None
    arbitration: ArbitrationFacts | None = None
    datasets: dict[str, DatasetReport]
    completeness: CompanyReportCompleteness
    freshness: ReportFreshness
    warnings: list[ReportWarning] = Field(default_factory=list)
    usable_for_public_page: bool
    usable_for_future_scoring: bool

    @field_validator("generated_at")
    @classmethod
    def _generated_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _status_matches_datasets(self) -> CompanyReport:
        available = sum(
            dataset.status is DatasetReportStatus.AVAILABLE
            for dataset in self.datasets.values()
        )
        if self.status is CompanyReportStatus.COMPLETE and available != 3:
            raise ValueError("complete report must have all required datasets available")
        if self.status is CompanyReportStatus.FAILED and available != 0:
            raise ValueError("failed report must have no available datasets")
        if self.status is CompanyReportStatus.PARTIAL and available not in range(1, 3):
            raise ValueError("partial report must have one or two available datasets")
        return self
