"""add durable company report jobs

Revision ID: 0013_company_report_jobs
Revises: 0012_company_report_persistence
Create Date: 2026-07-23 00:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0013_company_report_jobs"
down_revision = "0012_company_report_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid_type = sa.Uuid(as_uuid=True)

    op.create_table(
        "company_report_jobs",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "report_id",
            uuid_type,
            sa.ForeignKey("company_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subject_id",
            uuid_type,
            sa.ForeignKey("company_report_subjects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("worker_token", uuid_type, nullable=True),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("safe_failure_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "report_id",
            name="uq_company_report_jobs_report_id",
        ),
        sa.CheckConstraint(
            "state IN ('queued', 'running', 'succeeded', 'failed')",
            name="company_report_job_state",
        ),
        sa.CheckConstraint(
            "attempt_count IN (0, 1)",
            name="company_report_job_attempt_count",
        ),
        sa.CheckConstraint(
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
    )
    op.create_index(
        "uq_company_report_jobs_active_subject",
        "company_report_jobs",
        ["subject_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('queued', 'running')"),
    )
    op.create_index(
        "ix_company_report_jobs_queued_claim",
        "company_report_jobs",
        ["state", "created_at", "id"],
        unique=False,
        postgresql_where=sa.text("state = 'queued'"),
    )
    op.create_index(
        "ix_company_report_jobs_running_lease",
        "company_report_jobs",
        ["state", "lease_expires_at"],
        unique=False,
        postgresql_where=sa.text("state = 'running'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_company_report_jobs_running_lease",
        table_name="company_report_jobs",
    )
    op.drop_index(
        "ix_company_report_jobs_queued_claim",
        table_name="company_report_jobs",
    )
    op.drop_index(
        "uq_company_report_jobs_active_subject",
        table_name="company_report_jobs",
    )
    op.drop_table("company_report_jobs")
