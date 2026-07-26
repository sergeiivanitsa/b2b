"""add controlled public company report publications

Revision ID: 0014_company_report_publications
Revises: 0013_company_report_jobs
Create Date: 2026-07-24 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_company_report_publications"
down_revision = "0013_company_report_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)
    op.create_table(
        "company_report_publication_control",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("id = 1", name="company_report_publication_control_singleton"),
        sa.CheckConstraint("state IN ('paused', 'active')", name="company_report_publication_control_state"),
    )
    op.execute("INSERT INTO company_report_publication_control (id, state, policy_version) VALUES (1, 'paused', 'publication_sufficiency_v1')")
    op.create_table(
        "company_report_publications",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("subject_id", uuid, sa.ForeignKey("company_report_subjects.id"), nullable=False),
        sa.Column("report_id", uuid, sa.ForeignKey("company_reports.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("canonical_slug", sa.String(200), nullable=False),
        sa.Column("canonical_path", sa.String(240), nullable=False),
        sa.Column("snapshot_hash", sa.String(64)),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("batch_generation", sa.BigInteger(), nullable=False),
        sa.Column("indexable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sufficiency_status", sa.String(64), nullable=False),
        sa.Column("published_lastmod", sa.DateTime(timezone=True)),
        sa.Column("published_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True)),
        sa.Column("audited_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("subject_id", name="uq_company_report_publications_subject_id"),
        sa.UniqueConstraint("report_id", name="uq_company_report_publications_report_id"),
        sa.UniqueConstraint("canonical_path", name="uq_company_report_publications_canonical_path"),
        sa.CheckConstraint("status IN ('active', 'paused', 'disabled')", name="company_report_publication_status"),
        sa.CheckConstraint("canonical_path ~ '^/company/([0-9]{10}|[0-9]{12})-[a-z0-9]+(-[a-z0-9]+)*$'", name="company_report_publication_path"),
        sa.CheckConstraint("(status = 'active' AND snapshot_hash IS NOT NULL AND published_lastmod IS NOT NULL) OR status != 'active'", name="company_report_publication_active_shape"),
        sa.CheckConstraint("status = 'active' OR indexable = false", name="company_report_publication_inactive_noindex"),
        sa.CheckConstraint("batch_generation > 0", name="company_report_publication_batch_generation"),
    )
    op.create_index("ix_company_report_publications_sitemap", "company_report_publications", ["status", "indexable", "canonical_path"])
    op.create_table(
        "company_report_publication_batches",
        sa.Column("id", uuid, primary_key=True), sa.Column("generation", sa.BigInteger(), sa.Identity(always=True), nullable=False), sa.Column("state", sa.String(16), nullable=False),
        sa.Column("requested_limit", sa.Integer(), nullable=False), sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("next_ordinal", sa.Integer(), nullable=False, server_default=sa.text("0")), sa.Column("claimed_ordinal", sa.Integer()),
        sa.Column("policy_version", sa.String(64), nullable=False), sa.Column("safe_failure_code", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("state IN ('running', 'paused', 'completed', 'failed')", name="company_report_publication_batch_state"),
        sa.CheckConstraint("requested_limit >= 1", name="company_report_publication_batch_requested_limit"),
        sa.CheckConstraint("candidate_count >= 0 AND candidate_count <= requested_limit", name="company_report_publication_batch_candidate_count"),
        sa.CheckConstraint("next_ordinal >= 0 AND next_ordinal <= candidate_count", name="company_report_publication_batch_cursor"),
        sa.CheckConstraint("(candidate_count = 0 AND state = 'completed' AND next_ordinal = 0 AND claimed_ordinal IS NULL) OR candidate_count > 0", name="company_report_publication_batch_empty_shape"),
        sa.UniqueConstraint("generation", name="uq_company_report_publication_batches_generation"),
    )
    op.create_table(
        "company_report_publication_batch_items",
        sa.Column("id", uuid, primary_key=True), sa.Column("batch_id", uuid, sa.ForeignKey("company_report_publication_batches.id"), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False), sa.Column("subject_id", uuid, sa.ForeignKey("company_report_subjects.id"), nullable=False),
        sa.Column("report_id", uuid, sa.ForeignKey("company_reports.id"), nullable=False), sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False), sa.Column("state", sa.String(16), nullable=False),
        sa.Column("claim_token", uuid), sa.Column("claimed_at", sa.DateTime(timezone=True)), sa.Column("finished_at", sa.DateTime(timezone=True)), sa.Column("reason_code", sa.String(64)),
        sa.UniqueConstraint("batch_id", "ordinal", name="uq_company_report_publication_batch_item_ordinal"),
        sa.CheckConstraint("state IN ('pending', 'claimed', 'published', 'skipped', 'disabled', 'failed')", name="company_report_publication_batch_item_state"),
        sa.CheckConstraint("(state = 'pending' AND claim_token IS NULL AND claimed_at IS NULL AND finished_at IS NULL AND reason_code IS NULL) OR (state = 'claimed' AND claim_token IS NOT NULL AND claimed_at IS NOT NULL AND finished_at IS NULL AND reason_code IS NULL) OR (state IN ('published', 'skipped', 'disabled', 'failed') AND claim_token IS NOT NULL AND claimed_at IS NOT NULL AND finished_at IS NOT NULL AND reason_code IS NOT NULL)", name="company_report_publication_batch_item_shape"),
        sa.CheckConstraint("reason_code IS NULL OR reason_code IN ('sufficient', 'invalid_report', 'report_not_finalized', 'report_not_usable', 'invalid_or_private_snapshot', 'insufficient_scoring', 'thin_content', 'partial_insufficient', 'safe_policy_error', 'state_conflict', 'superseded_by_newer_batch')", name="company_report_publication_batch_item_reason"),
    )
    op.create_foreign_key(
        "fk_company_report_publications_batch_generation",
        "company_report_publications",
        "company_report_publication_batches",
        ["batch_generation"],
        ["generation"],
    )
    op.create_index("ix_company_report_publication_batch_item_claim", "company_report_publication_batch_items", ["batch_id", "state", "ordinal"])
    op.create_table(
        "company_report_publication_journal",
        sa.Column("id", uuid, primary_key=True), sa.Column("batch_id", uuid, sa.ForeignKey("company_report_publication_batches.id"), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False), sa.Column("subject_id", uuid, sa.ForeignKey("company_report_subjects.id"), nullable=False),
        sa.Column("report_id", uuid, sa.ForeignKey("company_reports.id"), nullable=False), sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False), sa.Column("action", sa.String(16), nullable=False), sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("batch_id", "ordinal", "action", name="uq_company_report_publication_journal_action"),
        sa.UniqueConstraint("report_id", "snapshot_hash", "policy_version", "action", name="uq_company_report_publication_journal_terminal"),
        sa.CheckConstraint("action IN ('published', 'skipped', 'disabled', 'failed')", name="company_report_publication_journal_action_value"),
        sa.CheckConstraint("reason_code IN ('sufficient', 'invalid_report', 'report_not_finalized', 'report_not_usable', 'invalid_or_private_snapshot', 'insufficient_scoring', 'thin_content', 'partial_insufficient', 'safe_policy_error', 'state_conflict', 'superseded_by_newer_batch')", name="company_report_publication_journal_reason"),
    )


def downgrade() -> None:
    op.drop_table("company_report_publication_journal")
    op.drop_index("ix_company_report_publication_batch_item_claim", table_name="company_report_publication_batch_items")
    op.drop_table("company_report_publication_batch_items")
    op.drop_constraint(
        "fk_company_report_publications_batch_generation",
        "company_report_publications",
        type_="foreignkey",
    )
    op.drop_table("company_report_publication_batches")
    op.drop_index("ix_company_report_publications_sitemap", table_name="company_report_publications")
    op.drop_table("company_report_publications")
    op.drop_table("company_report_publication_control")
