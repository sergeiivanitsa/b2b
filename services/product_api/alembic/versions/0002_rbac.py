"""add rbac fields

Revision ID: 0002_rbac
Revises: 0001_initial
Create Date: 2026-01-26 00:00:00

"""
from alembic import op
import sqlalchemy as sa

revision = "0002_rbac"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=32), server_default=sa.text("'user'"), nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.alter_column("users", "company_id", existing_type=sa.Integer(), nullable=True)
    op.create_unique_constraint(None, "users", ["email"])


def downgrade() -> None:
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.alter_column("users", "company_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("users", "is_active")
    op.drop_column("users", "role")
