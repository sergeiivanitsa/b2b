"""link claim drafts to trusted company report handoffs

Revision ID: 0015_claims_company_report_handoff
Revises: 0014_company_report_publications
Create Date: 2026-07-26 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_claims_company_report_handoff"
down_revision = "0014_company_report_publications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "claims",
        sa.Column(
            "source_company_report_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("company_reports.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "claims",
        sa.Column("handoff_idempotency_key_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_claims_source_company_report_id", "claims", ["source_company_report_id"]
    )
    op.create_unique_constraint(
        "uq_claims_handoff_idempotency_key_hash",
        "claims",
        ["handoff_idempotency_key_hash"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_claims_handoff_idempotency_key_hash", "claims", type_="unique"
    )
    op.drop_index("ix_claims_source_company_report_id", table_name="claims")
    op.drop_column("claims", "handoff_idempotency_key_hash")
    op.drop_column("claims", "source_company_report_id")
