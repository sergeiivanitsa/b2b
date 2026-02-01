"""add usage_json to messages

Revision ID: 0008_message_usage
Revises: 0007_credits
Create Date: 2026-01-27 00:00:00

"""
from alembic import op
import sqlalchemy as sa

revision = "0008_message_usage"
down_revision = "0007_credits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("usage_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "usage_json")
