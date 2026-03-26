"""add claims core schema

Revision ID: 0010_claims_core
Revises: 0009_company_admin_profiles_and_limits
Create Date: 2026-02-16 12:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0010_claims_core"
down_revision = "0009_company_admin_profiles_and_limits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'draft'")),
        sa.Column(
            "generation_state",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'insufficient_data'"),
        ),
        sa.Column("price_rub", sa.Integer(), nullable=False),
        sa.Column("edit_token_hash", sa.String(length=64), nullable=False),
        sa.Column("client_email", sa.String(length=320), nullable=True),
        sa.Column("client_phone", sa.String(length=32), nullable=True),
        sa.Column("case_type", sa.String(length=32), nullable=True),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("normalized_data_json", sa.JSON(), nullable=True),
        sa.Column("generation_notes_json", sa.JSON(), nullable=True),
        sa.Column("allowed_blocks_json", sa.JSON(), nullable=True),
        sa.Column("blocked_blocks_json", sa.JSON(), nullable=True),
        sa.Column("risk_flags_json", sa.JSON(), nullable=True),
        sa.Column("generated_preview_text", sa.Text(), nullable=True),
        sa.Column("generated_full_text", sa.Text(), nullable=True),
        sa.Column("final_text", sa.Text(), nullable=True),
        sa.Column("summary_for_admin", sa.Text(), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'preview_ready', 'paid', 'in_review', 'sent')",
            name="ck_claims_status",
        ),
        sa.CheckConstraint(
            "generation_state IN ('ready', 'manual_review_required', 'insufficient_data')",
            name="ck_claims_generation_state",
        ),
        sa.CheckConstraint(
            "price_rub >= 0",
            name="ck_claims_price_rub_non_negative",
        ),
        sa.CheckConstraint(
            "case_type IS NULL OR case_type IN ('supply', 'contract_work', 'services')",
            name="ck_claims_case_type",
        ),
        sa.UniqueConstraint("edit_token_hash", name="uq_claims_edit_token_hash"),
    )
    op.create_index("ix_claims_status", "claims", ["status"])
    op.create_index("ix_claims_generation_state", "claims", ["generation_state"])
    op.create_index("ix_claims_created_at", "claims", ["created_at"])

    op.create_table(
        "claim_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("claim_id", sa.Integer(), sa.ForeignKey("claims.id"), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("file_role", sa.String(length=32), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_claim_files_claim_id", "claim_files", ["claim_id"])

    op.create_table(
        "claim_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("claim_id", sa.Integer(), sa.ForeignKey("claims.id"), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_claim_events_claim_id", "claim_events", ["claim_id"])


def downgrade() -> None:
    op.drop_index("ix_claim_events_claim_id", table_name="claim_events")
    op.drop_table("claim_events")

    op.drop_index("ix_claim_files_claim_id", table_name="claim_files")
    op.drop_table("claim_files")

    op.drop_index("ix_claims_created_at", table_name="claims")
    op.drop_index("ix_claims_generation_state", table_name="claims")
    op.drop_index("ix_claims_status", table_name="claims")
    op.drop_table("claims")
