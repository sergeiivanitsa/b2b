"""add ledger message_id for chat credits

Revision ID: 0007_credits
Revises: 0006_chat_api_v1
Create Date: 2026-01-27 00:00:00

"""
from alembic import op
import sqlalchemy as sa

revision = "0007_credits"
down_revision = "0006_chat_api_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ledger",
        sa.Column("message_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_ledger_message_id_messages",
        "ledger",
        "messages",
        ["message_id"],
        ["id"],
    )
    op.create_index(
        "uq_ledger_message_id",
        "ledger",
        ["message_id"],
        unique=True,
        postgresql_where=sa.text("message_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_ledger_message_id", table_name="ledger")
    op.drop_constraint(
        "fk_ledger_message_id_messages",
        "ledger",
        type_="foreignkey",
    )
    op.drop_column("ledger", "message_id")
