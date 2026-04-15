"""add preview_header_json to claims

Revision ID: 0011_claims_preview_header_json
Revises: 0010_claims_core
Create Date: 2026-04-15 10:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0011_claims_preview_header_json"
down_revision = "0010_claims_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("claims", sa.Column("preview_header_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("claims", "preview_header_json")
