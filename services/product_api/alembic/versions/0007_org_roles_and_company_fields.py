"""org roles and company fields

Revision ID: 0007_org_roles_and_company_fields
Revises: 0006_chat_api_v1
Create Date: 2026-02-14 00:00:00

"""
from alembic import op
import sqlalchemy as sa

revision = "0007_org_roles_and_company_fields"
down_revision = "0006_chat_api_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_superadmin", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.alter_column(
        "users",
        "role",
        existing_type=sa.String(length=32),
        nullable=True,
        server_default=None,
    )

    op.add_column("companies", sa.Column("inn", sa.String(length=16), nullable=True))
    op.add_column("companies", sa.Column("phone", sa.String(length=32), nullable=True))
    op.add_column(
        "companies",
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'legacy'"),
            nullable=False,
        ),
    )
    op.execute(sa.text("UPDATE companies SET status = 'legacy' WHERE status IS NULL"))

    op.execute(
        sa.text(
            "UPDATE users SET is_superadmin = true, role = NULL, company_id = NULL "
            "WHERE role = 'superadmin'"
        )
    )
    op.execute(sa.text("UPDATE users SET role = 'admin' WHERE role = 'company_admin'"))
    op.execute(
        sa.text(
            "UPDATE users SET role = 'member' "
            "WHERE role = 'user' AND company_id IS NOT NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE users SET role = NULL "
            "WHERE role = 'user' AND company_id IS NULL"
        )
    )

    op.create_check_constraint(
        "role_company_consistency",
        "users",
        "(company_id IS NULL AND role IS NULL) OR "
        "(company_id IS NOT NULL AND role IN ('owner','admin','member'))",
    )
    op.create_check_constraint(
        "superadmin_consistency",
        "users",
        "is_superadmin = false OR (company_id IS NULL AND role IS NULL)",
    )

    op.execute(
        sa.text(
            "UPDATE invites SET used_at = now() "
            "WHERE used_at IS NULL AND expires_at <= now()"
        )
    )
    op.execute(
        sa.text(
            "WITH ranked AS ("
            "    SELECT id, ROW_NUMBER() OVER (PARTITION BY email ORDER BY created_at DESC, id DESC) AS rn "
            "    FROM invites "
            "    WHERE used_at IS NULL"
            ") "
            "UPDATE invites SET used_at = now() "
            "WHERE id IN (SELECT id FROM ranked WHERE rn > 1)"
        )
    )
    op.create_index(
        "ix_invites_active_email",
        "invites",
        ["email"],
        unique=True,
        postgresql_where=sa.text("used_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_invites_active_email", table_name="invites")
    op.drop_constraint("ck_users_superadmin_consistency", "users", type_="check")
    op.drop_constraint("ck_users_role_company_consistency", "users", type_="check")

    op.execute(
        sa.text("UPDATE users SET role = 'superadmin' WHERE is_superadmin = true")
    )
    op.execute(sa.text("UPDATE users SET role = 'company_admin' WHERE role = 'admin'"))
    op.execute(sa.text("UPDATE users SET role = 'user' WHERE role = 'member'"))
    op.execute(sa.text("UPDATE users SET role = 'user' WHERE role IS NULL"))

    op.alter_column(
        "users",
        "role",
        existing_type=sa.String(length=32),
        nullable=False,
        server_default=sa.text("'user'"),
    )
    op.drop_column("users", "is_superadmin")

    op.drop_column("companies", "status")
    op.drop_column("companies", "phone")
    op.drop_column("companies", "inn")
