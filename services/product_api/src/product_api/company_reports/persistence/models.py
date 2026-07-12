from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from product_api.db.base import Base

REPORT_PENDING_STATUS = "pending"
REPORT_FINAL_STATUSES = ("complete", "partial", "failed")
DATASET_STATUSES = (
    "available",
    "not_found",
    "access_denied",
    "authentication_error",
    "rate_limited",
    "temporarily_unavailable",
    "invalid_response",
    "normalization_error",
    "disabled",
    "configuration_error",
    "unexpected_error",
)
REQUEST_OUTCOMES = ("success", "error", "not_executed")


class CompanyReportSubject(Base):
    __tablename__ = "company_report_subjects"
    __table_args__ = (
        CheckConstraint(
            "length(normalized_identifier) IN (10, 12, 13, 15)",
            name="company_report_subject_identifier_length",
        ),
        Index("ix_company_report_subjects_normalized_identifier", "normalized_identifier"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    normalized_identifier: Mapped[str] = mapped_column(
        String(15), nullable=False, unique=True
    )
    identifier_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<CompanyReportSubject id={self.id!s} identifier_type={self.identifier_type!r}>"


class CompanyReportRecord(Base):
    __tablename__ = "company_reports"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_status IN ('pending', 'complete', 'partial', 'failed')",
            name="company_report_lifecycle_status",
        ),
        Index("ix_company_reports_subject_id", "subject_id"),
        Index("ix_company_reports_lifecycle_status", "lifecycle_status"),
        Index("ix_company_reports_generated_at", "generated_at"),
        Index("ix_company_reports_created_at", "created_at"),
        Index("ix_company_reports_request_id", "request_id"),
        Index(
            "ix_company_reports_subject_generated_created",
            "subject_id",
            "generated_at",
            "created_at",
        ),
        Index(
            "uq_company_reports_pending_subject",
            "subject_id",
            unique=True,
            postgresql_where=text("lifecycle_status = 'pending'"),
            sqlite_where=text("lifecycle_status = 'pending'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    subject_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("company_report_subjects.id", ondelete="CASCADE"),
        nullable=False,
    )
    report_version: Mapped[str] = mapped_column(String(16), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(16), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fresh_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    normalized_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    completeness_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    freshness_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    warnings_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    safe_error_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    usable_for_public_page: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    usable_for_future_scoring: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<CompanyReportRecord id={self.id!s} status={self.lifecycle_status!r}>"


class CompanyReportDataset(Base):
    __tablename__ = "company_report_datasets"
    __table_args__ = (
        UniqueConstraint(
            "report_id",
            "dataset",
            name="uq_company_report_datasets_report_id_dataset",
        ),
        CheckConstraint(
            "status IN ('available', 'not_found', 'access_denied', 'authentication_error', "
            "'rate_limited', 'temporarily_unavailable', 'invalid_response', "
            "'normalization_error', 'disabled', 'configuration_error', 'unexpected_error')",
            name="company_report_dataset_status",
        ),
        Index("ix_company_report_datasets_report_id", "report_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    report_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("company_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    dataset: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    normalized_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    source_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    safe_error: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    warnings_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    response_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<CompanyReportDataset id={self.id!s} dataset={self.dataset!r} status={self.status!r}>"


class CompanyReportProviderRequest(Base):
    __tablename__ = "company_report_provider_requests"
    __table_args__ = (
        CheckConstraint(
            "request_outcome IN ('success', 'error', 'not_executed')",
            name="company_report_provider_request_outcome",
        ),
        Index("ix_company_report_provider_requests_report_id", "report_id"),
        Index("ix_company_report_provider_requests_dataset", "dataset"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    report_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("company_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    dataset_record_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("company_report_datasets.id", ondelete="SET NULL"),
        nullable=True,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_executed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    request_outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    dataset_status: Mapped[str] = mapped_column(String(32), nullable=False)
    http_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(nullable=True)
    retryable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    response_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_limit_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    safe_error_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    safe_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_units: Mapped[Any | None] = mapped_column(Numeric, nullable=True)
    cost_amount: Mapped[Any | None] = mapped_column(Numeric, nullable=True)
    cost_currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    billing_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<CompanyReportProviderRequest id={self.id!s} dataset={self.dataset!r} outcome={self.request_outcome!r}>"
