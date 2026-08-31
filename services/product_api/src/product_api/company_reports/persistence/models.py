from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Identity,
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
JOB_QUEUED_STATE = "queued"
JOB_RUNNING_STATE = "running"
JOB_SUCCEEDED_STATE = "succeeded"
JOB_FAILED_STATE = "failed"
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
PUBLICATION_POLICY_VERSION = "publication_sufficiency_v1"


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
    writer_profile: Mapped[str] = mapped_column(String(64), nullable=False, default="h1_legacy_writer_v2", server_default=text("'h1_legacy_writer_v2'"))
    presentation_contract: Mapped[str] = mapped_column(String(64), nullable=False, default="company_public_h1_v1", server_default=text("'company_public_h1_v1'"))
    rollout_generation: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
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


class CompanyReportJob(Base):
    __tablename__ = "company_report_jobs"
    __table_args__ = (
        UniqueConstraint(
            "report_id",
            name="uq_company_report_jobs_report_id",
        ),
        CheckConstraint(
            "state IN ('queued', 'running', 'succeeded', 'failed')",
            name="company_report_job_state",
        ),
        CheckConstraint(
            "attempt_count IN (0, 1)",
            name="company_report_job_attempt_count",
        ),
        CheckConstraint(
            "("
            "state = 'queued' AND attempt_count = 0 "
            "AND worker_token IS NULL AND claimed_at IS NULL "
            "AND heartbeat_at IS NULL AND lease_expires_at IS NULL "
            "AND finished_at IS NULL AND safe_failure_code IS NULL"
            ") OR ("
            "state = 'running' AND attempt_count = 1 "
            "AND worker_token IS NOT NULL AND claimed_at IS NOT NULL "
            "AND heartbeat_at IS NOT NULL AND lease_expires_at IS NOT NULL "
            "AND finished_at IS NULL AND safe_failure_code IS NULL"
            ") OR ("
            "state = 'succeeded' AND attempt_count = 1 "
            "AND worker_token IS NOT NULL AND claimed_at IS NOT NULL "
            "AND heartbeat_at IS NOT NULL AND lease_expires_at IS NOT NULL "
            "AND finished_at IS NOT NULL AND safe_failure_code IS NULL"
            ") OR ("
            "state = 'failed' AND finished_at IS NOT NULL "
            "AND safe_failure_code IS NOT NULL AND ("
            "  (attempt_count = 0 AND worker_token IS NULL "
            "   AND claimed_at IS NULL AND heartbeat_at IS NULL "
            "   AND lease_expires_at IS NULL)"
            "  OR "
            "  (attempt_count = 1 AND worker_token IS NOT NULL "
            "   AND claimed_at IS NOT NULL AND heartbeat_at IS NOT NULL "
            "   AND lease_expires_at IS NOT NULL)"
            ")"
            ")",
            name="company_report_job_state_shape",
        ),
        Index(
            "uq_company_report_jobs_active_subject",
            "subject_id",
            unique=True,
            postgresql_where=text("state IN ('queued', 'running')"),
        ),
        Index(
            "ix_company_report_jobs_queued_claim",
            "state",
            "created_at",
            "id",
            postgresql_where=text("state = 'queued'"),
        ),
        Index(
            "ix_company_report_jobs_running_lease",
            "state",
            "lease_expires_at",
            postgresql_where=text("state = 'running'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    report_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("company_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    subject_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("company_report_subjects.id", ondelete="CASCADE"),
        nullable=False,
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    writer_profile: Mapped[str] = mapped_column(String(64), nullable=False, default="h1_legacy_writer_v2", server_default=text("'h1_legacy_writer_v2'"))
    presentation_contract: Mapped[str] = mapped_column(String(64), nullable=False, default="company_public_h1_v1", server_default=text("'company_public_h1_v1'"))
    rollout_generation: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    fence_generation: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    worker_token: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    safe_failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<CompanyReportJob id={self.id!s} "
            f"state={self.state!r} attempt_count={self.attempt_count}>"
        )


class CompanyReportPresentation(Base):
    __tablename__ = "company_report_presentations"
    __table_args__ = (UniqueConstraint("report_id", "presentation_contract", name="uq_company_report_presentations_report_contract"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    subject_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_report_subjects.id", ondelete="CASCADE"), nullable=False)
    report_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_reports.id", ondelete="CASCADE"), nullable=False)
    presentation_contract: Mapped[str] = mapped_column(String(64), nullable=False)
    rollout_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CompanyReportPresentationPin(Base):
    __tablename__ = "company_report_presentation_pins"
    __table_args__ = (UniqueConstraint("subject_id", "presentation_contract", "generation", name="uq_company_report_presentation_pins_generation"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    subject_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_report_subjects.id", ondelete="CASCADE"), nullable=False)
    report_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_reports.id", ondelete="CASCADE"), nullable=False)
    presentation_contract: Mapped[str] = mapped_column(String(64), nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CompanyReportPresentationStagedPointer(Base):
    __tablename__ = "company_report_presentation_staged_pointers"
    __table_args__ = (UniqueConstraint("subject_id", name="uq_company_report_presentation_staged_subject"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    subject_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_report_subjects.id", ondelete="CASCADE"), nullable=False)
    pin_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_report_presentation_pins.id", ondelete="RESTRICT"), nullable=False)
    expected_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CompanyReportPresentationAssignment(Base):
    __tablename__ = "company_report_presentation_assignments"
    __table_args__ = (UniqueConstraint("subject_id", name="uq_company_report_presentation_assignment_subject"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    subject_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_report_subjects.id", ondelete="CASCADE"), nullable=False)
    pin_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_report_presentation_pins.id", ondelete="RESTRICT"), nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CompanyReportPresentationAssignmentJournal(Base):
    __tablename__ = "company_report_presentation_assignment_journal"
    __table_args__ = (UniqueConstraint("assignment_id", "generation", name="uq_company_report_presentation_assignment_journal_generation"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    assignment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_report_presentation_assignments.id", ondelete="CASCADE"), nullable=False)
    pin_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_report_presentation_pins.id", ondelete="RESTRICT"), nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


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


class CompanyReportPublicationControl(Base):
    __tablename__ = "company_report_publication_control"
    __table_args__ = (
        CheckConstraint("id = 1", name="company_report_publication_control_singleton"),
        CheckConstraint("state IN ('paused', 'active')", name="company_report_publication_control_state"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="paused")
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CompanyReportPublication(Base):
    __tablename__ = "company_report_publications"
    __table_args__ = (
        UniqueConstraint("subject_id", name="uq_company_report_publications_subject_id"),
        UniqueConstraint("report_id", name="uq_company_report_publications_report_id"),
        UniqueConstraint("canonical_path", name="uq_company_report_publications_canonical_path"),
        CheckConstraint("status IN ('active', 'paused', 'disabled')", name="company_report_publication_status"),
        CheckConstraint("canonical_path ~ '^/company/([0-9]{10}|[0-9]{12})-[a-z0-9]+(-[a-z0-9]+)*$'", name="company_report_publication_path"),
        CheckConstraint("(status = 'active' AND snapshot_hash IS NOT NULL AND published_lastmod IS NOT NULL) OR status != 'active'", name="company_report_publication_active_shape"),
        CheckConstraint("status = 'active' OR indexable = false", name="company_report_publication_inactive_noindex"),
        CheckConstraint("batch_generation > 0", name="company_report_publication_batch_generation"),
        Index("ix_company_report_publications_sitemap", "status", "indexable", "canonical_path"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    subject_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_report_subjects.id"), nullable=False)
    report_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_reports.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    canonical_slug: Mapped[str] = mapped_column(String(200), nullable=False)
    canonical_path: Mapped[str] = mapped_column(String(240), nullable=False)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    batch_generation: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("company_report_publication_batches.generation"),
        nullable=False,
    )
    indexable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    sufficiency_status: Mapped[str] = mapped_column(String(64), nullable=False)
    published_lastmod: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    audited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CompanyReportPublicationBatch(Base):
    __tablename__ = "company_report_publication_batches"
    __table_args__ = (
        CheckConstraint("state IN ('running', 'paused', 'completed', 'failed')", name="company_report_publication_batch_state"),
        CheckConstraint("requested_limit >= 1", name="company_report_publication_batch_requested_limit"),
        CheckConstraint("candidate_count >= 0 AND candidate_count <= requested_limit", name="company_report_publication_batch_candidate_count"),
        CheckConstraint("next_ordinal >= 0 AND next_ordinal <= candidate_count", name="company_report_publication_batch_cursor"),
        CheckConstraint("(candidate_count = 0 AND state = 'completed' AND next_ordinal = 0 AND claimed_ordinal IS NULL) OR candidate_count > 0", name="company_report_publication_batch_empty_shape"),
        UniqueConstraint("generation", name="uq_company_report_publication_batches_generation"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    generation: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), nullable=False
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    next_ordinal: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    claimed_ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    safe_failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CompanyReportPublicationBatchItem(Base):
    __tablename__ = "company_report_publication_batch_items"
    __table_args__ = (
        UniqueConstraint("batch_id", "ordinal", name="uq_company_report_publication_batch_item_ordinal"),
        CheckConstraint("state IN ('pending', 'claimed', 'published', 'skipped', 'disabled', 'failed')", name="company_report_publication_batch_item_state"),
        CheckConstraint("(state = 'pending' AND claim_token IS NULL AND claimed_at IS NULL AND finished_at IS NULL AND reason_code IS NULL) OR (state = 'claimed' AND claim_token IS NOT NULL AND claimed_at IS NOT NULL AND finished_at IS NULL AND reason_code IS NULL) OR (state IN ('published', 'skipped', 'disabled', 'failed') AND claim_token IS NOT NULL AND claimed_at IS NOT NULL AND finished_at IS NOT NULL AND reason_code IS NOT NULL)", name="company_report_publication_batch_item_shape"),
        CheckConstraint("reason_code IS NULL OR reason_code IN ('sufficient', 'invalid_report', 'report_not_finalized', 'report_not_usable', 'invalid_or_private_snapshot', 'insufficient_scoring', 'thin_content', 'partial_insufficient', 'safe_policy_error', 'state_conflict', 'superseded_by_newer_batch')", name="company_report_publication_batch_item_reason"),
        Index("ix_company_report_publication_batch_item_claim", "batch_id", "state", "ordinal"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_report_publication_batches.id"), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    subject_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_report_subjects.id"), nullable=False)
    report_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_reports.id"), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    claim_token: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CompanyReportPublicationJournal(Base):
    __tablename__ = "company_report_publication_journal"
    __table_args__ = (
        UniqueConstraint("batch_id", "ordinal", "action", name="uq_company_report_publication_journal_action"),
        UniqueConstraint("report_id", "snapshot_hash", "policy_version", "action", name="uq_company_report_publication_journal_terminal"),
        CheckConstraint("action IN ('published', 'skipped', 'disabled', 'failed')", name="company_report_publication_journal_action_value"),
        CheckConstraint("reason_code IN ('sufficient', 'invalid_report', 'report_not_finalized', 'report_not_usable', 'invalid_or_private_snapshot', 'insufficient_scoring', 'thin_content', 'partial_insufficient', 'safe_policy_error', 'state_conflict', 'superseded_by_newer_batch')", name="company_report_publication_journal_reason"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_report_publication_batches.id"), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    subject_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_report_subjects.id"), nullable=False)
    report_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_reports.id"), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


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
