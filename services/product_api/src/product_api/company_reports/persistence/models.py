from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    BigInteger,
    CHAR,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Identity,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

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
        # ``id`` is the physical primary key, while this exact pair is the
        # parent key used by public bindings.  Keeping the subject in the
        # referenced key prevents a pin/presentation for subject A from being
        # pointed at a report owned by subject B.
        UniqueConstraint("id", "subject_id", name="uq_company_reports_id_subject"),
        CheckConstraint(
            "lifecycle_status IN ('pending', 'complete', 'partial', 'failed')",
            name="company_report_lifecycle_status",
        ),
        CheckConstraint(
            "arbitration_collection_enabled OR arbitration_mask_key_id IS NULL",
            name="company_reports_arbitration_decision",
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
    arbitration_collection_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    arbitration_mask_key_id: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
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
            "arbitration_collection_enabled OR arbitration_mask_key_id IS NULL",
            name="company_report_jobs_arbitration_decision",
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
        CheckConstraint(
            "(state = 'queued' AND fence_generation = 0) OR "
            "(state IN ('running', 'succeeded') AND attempt_count = 1 AND fence_generation = 1) OR "
            "(state = 'failed' AND ((attempt_count = 0 AND fence_generation = 0) OR (attempt_count = 1 AND fence_generation = 1)))",
            name="company_report_job_fence_shape",
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
    arbitration_collection_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    arbitration_mask_key_id: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
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
    __table_args__ = (
        UniqueConstraint("report_id", "presentation_contract", name="uq_company_report_presentations_report_contract"),
        UniqueConstraint("id", "subject_id", "report_id", "presentation_contract", "rollout_generation", name="uq_company_report_presentations_exact_binding"),
        CheckConstraint("presentation_contract = 'company_public_h2_v1' AND rollout_generation > 0", name="company_report_presentations_h2_shape"),
        ForeignKeyConstraint(
            ["report_id", "subject_id"],
            ["company_reports.id", "company_reports.subject_id"],
            name="fk_company_report_presentations_report_subject",
            ondelete="CASCADE",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    subject_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_report_subjects.id", ondelete="CASCADE"), nullable=False)
    report_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    presentation_contract: Mapped[str] = mapped_column(String(64), nullable=False)
    rollout_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CompanyReportH2LifecycleHead(Base):
    """Durable H2 public lifecycle selector; it is not a generic latest row."""
    __tablename__ = "company_report_h2_lifecycle_heads"
    __table_args__ = (
        ForeignKeyConstraint(
            ["presentation_id", "subject_id", "report_id", "presentation_contract", "rollout_generation"],
            [
                "company_report_presentations.id",
                "company_report_presentations.subject_id",
                "company_report_presentations.report_id",
                "company_report_presentations.presentation_contract",
                "company_report_presentations.rollout_generation",
            ],
            name="fk_company_report_h2_head_presentation_binding",
            ondelete="RESTRICT",
        ),
        CheckConstraint("presentation_contract = 'company_public_h2_v1'", name="company_report_h2_head_contract"),
        CheckConstraint("rollout_generation > 0 AND head_generation > 0", name="company_report_h2_head_generation"),
    )
    subject_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_report_subjects.id", ondelete="CASCADE"), primary_key=True)
    presentation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    report_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    presentation_contract: Mapped[str] = mapped_column(String(64), nullable=False)
    rollout_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    head_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CompanyReportPresentationPin(Base):
    __tablename__ = "company_report_presentation_pins"
    __table_args__ = (
        # A pin is an immutable public binding, not an opaque row selected by
        # a surrogate identifier.  Every pointer below carries this exact
        # identity, which makes cross-subject bindings impossible at the DB
        # boundary as well as in the CAS helper.
        CheckConstraint("generation > 0", name="company_report_presentation_pins_generation"),
        CheckConstraint(
            "(presentation_contract = 'company_public_h1_v1' "
            "AND indexable = true AND publication_policy_version IS NOT NULL "
            "AND canonical_path IS NOT NULL AND published_lastmod IS NOT NULL "
            "AND projection_digest IS NULL "
            "AND narrative_binding_status IS NULL AND narrative_binding_kind IS NULL "
            "AND narrative_binding_key IS NULL AND chart_facts_version IS NULL "
            "AND chart_facts_hash IS NULL AND evidence_registry_version IS NULL) "
            "OR (presentation_contract = 'company_public_h2_v1' "
            "AND indexable = false AND canonical_path IS NULL AND published_lastmod IS NULL "
            "AND chart_facts_version IS NOT NULL "
            "AND chart_facts_hash IS NOT NULL AND evidence_registry_version IS NOT NULL "
            "AND publication_policy_version IS NOT NULL "
            "AND ((projection_digest IS NULL AND narrative_binding_status = 'unresolved' "
            "AND narrative_binding_kind IS NULL AND narrative_binding_key IS NULL) "
            "OR (projection_digest ~ '^[0-9a-f]{64}$' "
            "AND narrative_binding_status = 'resolved' "
            "AND narrative_binding_kind IN ('artifact', 'fallback') "
            "AND narrative_binding_key ~ '^[0-9a-f]{64}$')))",
            name="company_report_presentation_pins_contract_shape",
        ),
        ForeignKeyConstraint(
            ["report_id", "subject_id"],
            ["company_reports.id", "company_reports.subject_id"],
            name="fk_company_report_presentation_pins_report_subject",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["narrative_binding_kind", "narrative_binding_key"],
            [
                "company_card_narrative_artifacts.binding_kind",
                "company_card_narrative_artifacts.binding_key",
            ],
            name="fk_company_report_h2_pin_narrative_binding",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    subject_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_report_subjects.id", ondelete="CASCADE"), primary_key=True)
    report_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    presentation_contract: Mapped[str] = mapped_column(String(64), primary_key=True)
    generation: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    chart_facts_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chart_facts_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_registry_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    publication_policy_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    canonical_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    indexable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    published_lastmod: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    projection_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    narrative_binding_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    narrative_binding_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    narrative_binding_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CompanyReportPresentationStagedPointer(Base):
    __tablename__ = "company_report_presentation_staged_pointers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["subject_id", "presentation_contract", "generation"],
            [
                "company_report_presentation_pins.subject_id",
                "company_report_presentation_pins.presentation_contract",
                "company_report_presentation_pins.generation",
            ],
            name="fk_company_report_presentation_staged_pin",
            ondelete="RESTRICT",
        ),
        CheckConstraint("generation > 0", name="company_report_presentation_staged_generation"),
        UniqueConstraint("subject_id", name="uq_company_report_presentation_staged_subject"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    subject_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_report_subjects.id", ondelete="CASCADE"), nullable=False)
    presentation_contract: Mapped[str] = mapped_column(String(64), nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CompanyReportPresentationAssignment(Base):
    __tablename__ = "company_report_presentation_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["subject_id", "presentation_contract", "pin_generation"],
            [
                "company_report_presentation_pins.subject_id",
                "company_report_presentation_pins.presentation_contract",
                "company_report_presentation_pins.generation",
            ],
            name="fk_company_report_presentation_assignment_pin",
            ondelete="RESTRICT",
        ),
        CheckConstraint("generation > 0 AND pin_generation > 0", name="company_report_presentation_assignment_generation"),
        UniqueConstraint("subject_id", name="uq_company_report_presentation_assignment_subject"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    subject_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_report_subjects.id", ondelete="CASCADE"), nullable=False)
    presentation_contract: Mapped[str] = mapped_column(String(64), nullable=False)
    pin_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CompanyReportPresentationAssignmentJournal(Base):
    __tablename__ = "company_report_presentation_assignment_journal"
    __table_args__ = (
        ForeignKeyConstraint(
            ["subject_id", "presentation_contract", "pin_generation"],
            [
                "company_report_presentation_pins.subject_id",
                "company_report_presentation_pins.presentation_contract",
                "company_report_presentation_pins.generation",
            ],
            name="fk_company_report_presentation_journal_pin",
            ondelete="RESTRICT",
        ),
        CheckConstraint("generation > 0 AND pin_generation > 0", name="company_report_presentation_assignment_journal_generation"),
        UniqueConstraint("assignment_id", "generation", name="uq_company_report_pin_journal_assignment_generation"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    assignment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_report_presentation_assignments.id", ondelete="CASCADE"), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_report_subjects.id", ondelete="CASCADE"), nullable=False)
    presentation_contract: Mapped[str] = mapped_column(String(64), nullable=False)
    pin_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
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


# Narrative records are intentionally separate from immutable report snapshots.
class CompanyCardNarrativeOutbox(Base):
    __tablename__ = "company_card_narrative_outbox"
    __table_args__ = (
        CheckConstraint("snapshot_hash ~ '^[0-9a-f]{64}$'", name="snapshot_hash_hex"),
        CheckConstraint("event_kind = 'initialize_narrative_v1'", name="company_card_narrative_outbox_kind"),
        CheckConstraint("state IN ('pending', 'leased', 'processed', 'terminal')", name="company_card_narrative_outbox_state"),
        CheckConstraint("fence_generation >= 0 AND attempt_count BETWEEN 0 AND 3", name="company_card_narrative_outbox_attempts"),
        CheckConstraint(
            "(state = 'leased' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
            "(state <> 'leased' AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name="company_card_narrative_outbox_lease_shape",
        ),
        CheckConstraint(
            "(state = 'processed' AND processed_at IS NOT NULL AND generation_key IS NOT NULL AND failure_code IS NULL) OR "
            "(state = 'terminal' AND processed_at IS NULL AND generation_key IS NULL AND failure_code IS NOT NULL) OR "
            "(state IN ('pending', 'leased') AND processed_at IS NULL AND generation_key IS NULL AND failure_code IS NULL)",
            name="company_card_narrative_outbox_terminal_shape",
        ),
        UniqueConstraint("report_id", "snapshot_hash", "event_kind", name="uq_company_card_narrative_outbox_event"),
        Index(
            "ix_company_card_narrative_outbox_pending_selection",
            "state",
            "available_at",
            "lease_expires_at",
            "id",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    report_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_reports.id", ondelete="RESTRICT"), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    event_kind: Mapped[str] = mapped_column(String(48), nullable=False, default="initialize_narrative_v1")
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    lease_token: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fence_generation: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    attempt_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    failure_code: Mapped[str | None] = mapped_column(String(64))
    generation_key: Mapped[str | None] = mapped_column(CHAR(64), ForeignKey("company_card_narrative_jobs.generation_key", deferrable=True, initially="DEFERRED"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CompanyCardNarrativeRuntimeControl(Base):
    __tablename__ = "company_card_narrative_runtime_control"
    __table_args__ = (
        CheckConstraint("singleton_id = 1", name="company_card_narrative_runtime_singleton"),
        CheckConstraint(
            "daily_limit >= 0 AND monthly_limit >= 0 AND concurrency_limit >= 0 "
            "AND leased_count >= 0 AND (concurrency_limit = 0 OR concurrency_limit >= leased_count)",
            name="company_card_narrative_runtime_nonnegative",
        ),
    )
    singleton_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    kill_switch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    daily_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    monthly_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    concurrency_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    leased_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CompanyCardNarrativeBudgetWindow(Base):
    __tablename__ = "company_card_narrative_budget_windows"
    __table_args__ = (
        CheckConstraint("period_kind IN ('daily', 'monthly')", name="company_card_narrative_window_kind"),
        CheckConstraint(
            "starts_at_utc < ends_at_utc AND reserved_count >= 0 AND consumed_count >= 0",
            name="company_card_narrative_window_shape",
        ),
    )
    period_kind: Mapped[str] = mapped_column(String(7), primary_key=True)
    period_start_local: Mapped[date] = mapped_column(Date, primary_key=True)
    starts_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reserved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consumed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class CompanyCardNarrativeBudgetReservation(Base):
    __tablename__ = "company_card_narrative_budget_reservations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["daily_period_kind", "daily_period_start_local"],
            ["company_card_narrative_budget_windows.period_kind", "company_card_narrative_budget_windows.period_start_local"],
            name="fk_company_card_narrative_reservation_daily_window",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["monthly_period_kind", "monthly_period_start_local"],
            ["company_card_narrative_budget_windows.period_kind", "company_card_narrative_budget_windows.period_start_local"],
            name="fk_company_card_narrative_reservation_monthly_window",
            ondelete="RESTRICT",
        ),
        CheckConstraint("generation_key ~ '^[0-9a-f]{64}$'", name="generation_key_hex"),
        CheckConstraint(
            "dispatch_credit = 1 AND state IN ('reserved', 'released', 'consumed') "
            "AND daily_period_kind = 'daily' AND monthly_period_kind = 'monthly' "
            "AND reservation_epoch BETWEEN 1 AND 3",
            name="company_card_narrative_reservation_shape",
        ),
        CheckConstraint(
            "(state = 'consumed') = (consumed_at IS NOT NULL)",
            name="company_card_narrative_reservation_consumed_shape",
        ),
    )
    generation_key: Mapped[str] = mapped_column(CHAR(64), ForeignKey("company_card_narrative_jobs.generation_key", ondelete="RESTRICT"), primary_key=True)
    dispatch_credit: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    state: Mapped[str] = mapped_column(String(10), nullable=False)
    daily_period_kind: Mapped[str] = mapped_column(String(7), nullable=False)
    daily_period_start_local: Mapped[date] = mapped_column(Date, nullable=False)
    monthly_period_kind: Mapped[str] = mapped_column(String(7), nullable=False)
    monthly_period_start_local: Mapped[date] = mapped_column(Date, nullable=False)
    reservation_epoch: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    release_code: Mapped[str | None] = mapped_column(String(64))


class CompanyCardNarrativeJob(Base):
    __tablename__ = "company_card_narrative_jobs"
    __table_args__ = (
        CheckConstraint("snapshot_hash ~ '^[0-9a-f]{64}$'", name="snapshot_hash_hex"),
        CheckConstraint("generation_key ~ '^[0-9a-f]{64}$'", name="generation_key_hex"),
        CheckConstraint(
            "identity_version IN ('GenerationIdentityV1', 'GenerationIdentityV2')",
            name="company_card_narrative_job_identity",
        ),
        CheckConstraint(
            "state IN ('ready', 'leased', 'dispatching', 'dispatched', 'validating', 'rendered', "
            "'finalized', 'pre_dispatch_failed', 'ambiguous_timeout', 'invalid_output', 'fallback_finalized')",
            name="company_card_narrative_job_state",
        ),
        CheckConstraint(
            "fence_generation >= 0 AND local_attempt_count BETWEEN 0 AND 3",
            name="company_card_narrative_job_attempts",
        ),
        CheckConstraint(
            "(state IN ('leased', 'dispatching', 'dispatched', 'validating', 'rendered') "
            "AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
            "(state NOT IN ('leased', 'dispatching', 'dispatched', 'validating', 'rendered') "
            "AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name="company_card_narrative_job_lease_shape",
        ),
        CheckConstraint(
            "(state IN ('ready', 'leased', 'pre_dispatch_failed') "
            "AND gateway_dispatch_id IS NULL AND dispatch_started_at IS NULL "
            "AND resolved_model_version IS NULL AND response_received_at IS NULL) OR "
            "(state IN ('dispatching', 'dispatched', 'validating', 'rendered', 'finalized', 'ambiguous_timeout', 'invalid_output') "
            "AND gateway_dispatch_id IS NOT NULL AND dispatch_started_at IS NOT NULL) OR "
            "(state = 'fallback_finalized' AND ((gateway_dispatch_id IS NULL AND dispatch_started_at IS NULL "
            "AND resolved_model_version IS NULL AND response_received_at IS NULL) OR "
            "(gateway_dispatch_id IS NOT NULL AND dispatch_started_at IS NOT NULL)))",
            name="company_card_narrative_job_dispatch_shape",
        ),
        Index(
            "ix_company_card_narrative_jobs_ready_selection",
            "state",
            "available_at",
            "id",
        ),
        Index(
            "ix_company_card_narrative_jobs_expired_selection",
            "state",
            "lease_expires_at",
            "id",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    report_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_reports.id", ondelete="RESTRICT"), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    generation_key: Mapped[str] = mapped_column(CHAR(64), nullable=False, unique=True)
    identity_version: Mapped[str] = mapped_column(String(32), nullable=False)
    generation_identity: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="ready")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    lease_token: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fence_generation: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    local_attempt_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    gateway_dispatch_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), unique=True)
    dispatch_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_model_version: Mapped[str | None] = mapped_column(String(255))
    validation_codes: Mapped[list[object]] = mapped_column(JSONB, nullable=False, default=list)
    artifact_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "company_card_narrative_artifacts.id",
            name="fk_company_card_narrative_job_artifact",
            deferrable=True,
            initially="DEFERRED",
        ),
        unique=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CompanyCardNarrativeArtifact(Base):
    __tablename__ = "company_card_narrative_artifacts"
    __table_args__ = (
        CheckConstraint("snapshot_hash ~ '^[0-9a-f]{64}$'", name="snapshot_hash_hex"),
        CheckConstraint("generation_key ~ '^[0-9a-f]{64}$'", name="generation_key_hex"),
        CheckConstraint("binding_key ~ '^[0-9a-f]{64}$'", name="binding_key_hex"),
        CheckConstraint("rendered_output_bytes_sha256 ~ '^[0-9a-f]{64}$'", name="rendered_output_bytes_sha256_hex"),
        CheckConstraint("artifact_identity IS NULL OR artifact_identity ~ '^[0-9a-f]{64}$'", name="company_card_narrative_artifact_identity_hex"),
        CheckConstraint("fallback_identity IS NULL OR fallback_identity ~ '^[0-9a-f]{64}$'", name="company_card_narrative_fallback_identity_hex"),
        CheckConstraint("validated_render_plan_bytes_sha256 IS NULL OR validated_render_plan_bytes_sha256 ~ '^[0-9a-f]{64}$'", name="company_card_narrative_artifact_plan_hash_hex"),
        CheckConstraint("binding_kind IN ('artifact', 'fallback')", name="company_card_narrative_artifact_kind"),
        CheckConstraint("raw_model_output IS NULL OR octet_length(raw_model_output) <= 16384", name="company_card_narrative_artifact_raw_bound"),
        CheckConstraint("validated_render_plan_cjson IS NULL OR octet_length(validated_render_plan_cjson) <= 16384", name="company_card_narrative_artifact_plan_bound"),
        CheckConstraint("rendered_comments = '[]'::jsonb", name="company_card_narrative_artifact_comments_empty"),
        CheckConstraint(
            "(binding_kind = 'artifact' AND binding_key = artifact_identity AND artifact_identity IS NOT NULL "
            "AND fallback_identity IS NULL AND resolved_model_version IS NOT NULL "
            "AND validated_render_plan_cjson IS NOT NULL AND validated_render_plan_bytes_sha256 IS NOT NULL) OR "
            "(binding_kind = 'fallback' AND binding_key = fallback_identity AND artifact_identity IS NULL "
            "AND fallback_identity IS NOT NULL AND resolved_model_version IS NULL AND raw_model_output IS NULL "
            "AND validated_render_plan_cjson IS NULL AND validated_render_plan_bytes_sha256 IS NULL "
            "AND renderer_version = 'company_card_h2_fallback_renderer_v1')",
            name="company_card_narrative_artifact_identity_shape",
        ),
        UniqueConstraint("binding_kind", "binding_key", name="uq_company_card_narrative_artifact_binding"),
        Index(
            "ix_company_card_narrative_artifacts_exact_lookup",
            "report_id",
            "snapshot_hash",
            "generation_key",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    report_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_reports.id", ondelete="RESTRICT"), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    generation_key: Mapped[str] = mapped_column(CHAR(64), ForeignKey("company_card_narrative_jobs.generation_key", ondelete="RESTRICT"), nullable=False, unique=True)
    binding_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    binding_key: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    artifact_identity: Mapped[str | None] = mapped_column(CHAR(64))
    fallback_identity: Mapped[str | None] = mapped_column(CHAR(64))
    resolved_model_version: Mapped[str | None] = mapped_column(String(255))
    raw_model_output: Mapped[str | None] = mapped_column(Text)
    validated_render_plan_cjson: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    validated_render_plan_bytes_sha256: Mapped[str | None] = mapped_column(CHAR(64))
    rendered_description: Mapped[str] = mapped_column(Text, nullable=False)
    rendered_comments: Mapped[list[object]] = mapped_column(JSONB, nullable=False, default=list)
    statement_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    phrase_trace: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    validation_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    renderer_version: Mapped[str] = mapped_column(String(96), nullable=False)
    rendered_output_bytes_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
