"""add explicit bounded or unlimited Company Card narrative quota mode.

Revision ID: 0020_company_card_narrative_quota_mode
Revises: 0019_company_card_v2_rollout_control
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0020_company_card_narrative_quota_mode"
down_revision = "0019_company_card_v2_rollout_control"
branch_labels = None
depends_on = None


_QUOTA_SHAPE = (
    "quota_mode IN ('bounded', 'unlimited') "
    "AND (quota_mode = 'bounded' OR (daily_limit = 0 AND monthly_limit = 0)) "
    "AND (NOT enabled OR (NOT kill_switch AND concurrency_limit > 0 "
    "AND ((quota_mode = 'bounded' AND daily_limit > 0 AND monthly_limit > 0) "
    "OR quota_mode = 'unlimited')))"
)


def upgrade() -> None:
    op.add_column(
        "company_card_narrative_runtime_control",
        sa.Column(
            "quota_mode",
            sa.String(16),
            nullable=False,
            server_default="bounded",
        ),
    )
    op.create_check_constraint(
        "company_card_narrative_runtime_quota_shape",
        "company_card_narrative_runtime_control",
        _QUOTA_SHAPE,
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "LOCK TABLE company_card_narrative_runtime_control "
            "IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    unlimited = bind.execute(
        sa.text(
            "SELECT EXISTS ("
            "SELECT 1 FROM company_card_narrative_runtime_control "
            "WHERE quota_mode <> 'bounded'"
            ")"
        )
    ).scalar()
    if unlimited:
        raise RuntimeError("refuse to discard unlimited narrative quota mode")
    op.drop_constraint(
        "company_card_narrative_runtime_quota_shape",
        "company_card_narrative_runtime_control",
        type_="check",
    )
    op.drop_column("company_card_narrative_runtime_control", "quota_mode")
