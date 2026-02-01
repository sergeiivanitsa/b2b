"""add chat api v1 message fields

Revision ID: 0006_chat_api_v1
Revises: 0005_superadmin_api
Create Date: 2026-01-27 00:00:00

"""
from alembic import op
import sqlalchemy as sa

revision = "0006_chat_api_v1"
down_revision = "0005_superadmin_api"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("parent_message_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("client_message_id", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_messages_parent_message_id_messages",
        "messages",
        "messages",
        ["parent_message_id"],
        ["id"],
    )
    op.create_index(
        "ix_messages_parent_message_id",
        "messages",
        ["parent_message_id"],
    )
    op.create_index(
        "uq_messages_conversation_client_message_id",
        "messages",
        ["conversation_id", "client_message_id"],
        unique=True,
        postgresql_where=sa.text("client_message_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_messages_conversation_client_message_id", table_name="messages")
    op.drop_index("ix_messages_parent_message_id", table_name="messages")
    op.drop_constraint(
        "fk_messages_parent_message_id_messages",
        "messages",
        type_="foreignkey",
    )
    op.drop_column("messages", "client_message_id")
    op.drop_column("messages", "parent_message_id")
