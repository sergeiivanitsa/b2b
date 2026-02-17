"""company admin profiles and user limits

Revision ID: 0009_company_admin_profiles_and_limits
Revises: 6f1f71f5ea36
Create Date: 2026-02-16 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = "0009_company_admin_profiles_and_limits"
down_revision = "6f1f71f5ea36"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("first_name", sa.String(length=120), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(length=120), nullable=True))
    op.add_column("users", sa.Column("joined_company_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("invites", sa.Column("first_name", sa.String(length=120), nullable=True))
    op.add_column("invites", sa.Column("last_name", sa.String(length=120), nullable=True))

    op.create_table(
        "user_credit_limits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("remaining_credits", sa.Integer(), server_default=sa.text("0"), nullable=False),
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
        sa.UniqueConstraint("user_id", name="uq_user_credit_limits_user_id"),
        sa.CheckConstraint(
            "remaining_credits >= 0",
            name="ck_user_credit_limits_remaining_credits_non_negative",
        ),
    )
    op.create_index(
        "ix_user_credit_limits_company_id",
        "user_credit_limits",
        ["company_id"],
    )

    op.execute(
        sa.text(
            "UPDATE users "
            "SET joined_company_at = created_at "
            "WHERE company_id IS NOT NULL AND joined_company_at IS NULL"
        )
    )

    # Seed strategy for a no-surprise rollout:
    # assign the entire positive company pool to owner, everyone else gets 0.
    op.execute(
        sa.text(
            "WITH company_balances AS ("
            "    SELECT c.id AS company_id, GREATEST(COALESCE(SUM(l.delta), 0), 0) AS pool_balance "
            "    FROM companies c "
            "    LEFT JOIN ledger l ON l.company_id = c.id "
            "    GROUP BY c.id"
            "), "
            "owner_candidates AS ("
            "    SELECT u.company_id, MIN(u.id) AS owner_user_id "
            "    FROM users u "
            "    WHERE u.company_id IS NOT NULL AND u.role = 'owner' "
            "    GROUP BY u.company_id"
            "), "
            "members AS ("
            "    SELECT u.id AS user_id, u.company_id "
            "    FROM users u "
            "    WHERE u.company_id IS NOT NULL AND u.role IN ('owner', 'admin', 'member')"
            "), "
            "seed_rows AS ("
            "    SELECT "
            "        m.company_id, "
            "        m.user_id, "
            "        CASE "
            "            WHEN oc.owner_user_id IS NOT NULL AND m.user_id = oc.owner_user_id "
            "                THEN COALESCE(cb.pool_balance, 0) "
            "            ELSE 0 "
            "        END AS remaining_credits "
            "    FROM members m "
            "    LEFT JOIN company_balances cb ON cb.company_id = m.company_id "
            "    LEFT JOIN owner_candidates oc ON oc.company_id = m.company_id"
            ") "
            "INSERT INTO user_credit_limits (company_id, user_id, remaining_credits, created_at, updated_at) "
            "SELECT company_id, user_id, remaining_credits, now(), now() "
            "FROM seed_rows "
            "ON CONFLICT (user_id) DO NOTHING"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_user_credit_limits_company_id", table_name="user_credit_limits")
    op.drop_table("user_credit_limits")

    op.drop_column("invites", "last_name")
    op.drop_column("invites", "first_name")

    op.drop_column("users", "joined_company_at")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
