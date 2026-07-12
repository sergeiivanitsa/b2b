"""add persistent company report storage

Revision ID: 0012_company_report_persistence
Revises: 0011_claims_preview_header_json
Create Date: 2026-07-12 00:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0012_company_report_persistence"
down_revision = "0011_claims_preview_header_json"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid_type = sa.Uuid(as_uuid=True)

    op.create_table(
        "company_report_subjects",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("normalized_identifier", sa.String(length=15), nullable=False),
        sa.Column("identifier_type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("normalized_identifier", name="uq_company_report_subjects_normalized_identifier"),
        sa.CheckConstraint(
            "length(normalized_identifier) IN (10, 12, 13, 15)",
            name="company_report_subject_identifier_length",
        ),
    )
    op.create_index(
        "ix_company_report_subjects_normalized_identifier",
        "company_report_subjects",
        ["normalized_identifier"],
        unique=False,
    )

    op.create_table(
        "company_reports",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "subject_id",
            uuid_type,
            sa.ForeignKey("company_report_subjects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("report_version", sa.String(length=16), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=16), nullable=False),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fresh_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("normalized_snapshot", sa.JSON(), nullable=True),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column("completeness_snapshot", sa.JSON(), nullable=True),
        sa.Column("freshness_snapshot", sa.JSON(), nullable=True),
        sa.Column("warnings_snapshot", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("safe_error_snapshot", sa.JSON(), nullable=True),
        sa.Column("usable_for_public_page", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("usable_for_future_scoring", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "lifecycle_status IN ('pending', 'complete', 'partial', 'failed')",
            name="company_report_lifecycle_status",
        ),
    )
    for name, columns in (
        ("ix_company_reports_subject_id", ["subject_id"]),
        ("ix_company_reports_lifecycle_status", ["lifecycle_status"]),
        ("ix_company_reports_generated_at", ["generated_at"]),
        ("ix_company_reports_created_at", ["created_at"]),
        ("ix_company_reports_request_id", ["request_id"]),
        (
            "ix_company_reports_subject_generated_created",
            ["subject_id", "generated_at", "created_at"],
        ),
    ):
        op.create_index(name, "company_reports", columns, unique=False)
    op.create_index(
        "uq_company_reports_pending_subject",
        "company_reports",
        ["subject_id"],
        unique=True,
        postgresql_where=sa.text("lifecycle_status = 'pending'"),
    )

    op.create_table(
        "company_report_datasets",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "report_id",
            uuid_type,
            sa.ForeignKey("company_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dataset", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("normalized_snapshot", sa.JSON(), nullable=True),
        sa.Column("source_metadata", sa.JSON(), nullable=True),
        sa.Column("safe_error", sa.JSON(), nullable=True),
        sa.Column("warnings_snapshot", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("response_hash", sa.String(length=64), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("report_id", "dataset", name="uq_company_report_datasets_report_id_dataset"),
        sa.CheckConstraint(
            "status IN ('available', 'not_found', 'access_denied', 'authentication_error', "
            "'rate_limited', 'temporarily_unavailable', 'invalid_response', "
            "'normalization_error', 'disabled', 'configuration_error', 'unexpected_error')",
            name="company_report_dataset_status",
        ),
    )
    op.create_index("ix_company_report_datasets_report_id", "company_report_datasets", ["report_id"])

    op.create_table(
        "company_report_provider_requests",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "report_id",
            uuid_type,
            sa.ForeignKey("company_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dataset_record_id",
            uuid_type,
            sa.ForeignKey("company_report_datasets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("dataset", sa.String(length=64), nullable=False),
        sa.Column("endpoint", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("request_executed", sa.Boolean(), nullable=False),
        sa.Column("request_outcome", sa.String(length=32), nullable=False),
        sa.Column("dataset_status", sa.String(length=32), nullable=False),
        sa.Column("http_status_code", sa.Integer(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=True),
        sa.Column("response_hash", sa.String(length=64), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_limit_metadata", sa.JSON(), nullable=True),
        sa.Column("safe_error_type", sa.String(length=128), nullable=True),
        sa.Column("safe_error_message", sa.Text(), nullable=True),
        sa.Column("billing_units", sa.Numeric(), nullable=True),
        sa.Column("cost_amount", sa.Numeric(), nullable=True),
        sa.Column("cost_currency", sa.String(length=16), nullable=True),
        sa.Column("billing_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "request_outcome IN ('success', 'error', 'not_executed')",
            name="company_report_provider_request_outcome",
        ),
    )
    op.create_index(
        "ix_company_report_provider_requests_report_id",
        "company_report_provider_requests",
        ["report_id"],
    )
    op.create_index(
        "ix_company_report_provider_requests_dataset",
        "company_report_provider_requests",
        ["dataset"],
    )


def downgrade() -> None:
    op.drop_index("ix_company_report_provider_requests_dataset", table_name="company_report_provider_requests")
    op.drop_index("ix_company_report_provider_requests_report_id", table_name="company_report_provider_requests")
    op.drop_table("company_report_provider_requests")
    op.drop_index("ix_company_report_datasets_report_id", table_name="company_report_datasets")
    op.drop_table("company_report_datasets")
    op.drop_index("uq_company_reports_pending_subject", table_name="company_reports")
    op.drop_index("ix_company_reports_subject_generated_created", table_name="company_reports")
    op.drop_index("ix_company_reports_request_id", table_name="company_reports")
    op.drop_index("ix_company_reports_created_at", table_name="company_reports")
    op.drop_index("ix_company_reports_generated_at", table_name="company_reports")
    op.drop_index("ix_company_reports_lifecycle_status", table_name="company_reports")
    op.drop_index("ix_company_reports_subject_id", table_name="company_reports")
    op.drop_table("company_reports")
    op.drop_index("ix_company_report_subjects_normalized_identifier", table_name="company_report_subjects")
    op.drop_table("company_report_subjects")
