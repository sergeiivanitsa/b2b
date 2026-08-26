"""add the default-off Company Card v2 arbitration decision.

Revision ID: 0018_company_card_v2_arbitration
Revises: 0017_company_card_v2_ai_narrative
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0018_company_card_v2_arbitration"
down_revision = "0017_company_card_v2_ai_narrative"
branch_labels = None
depends_on = None


_ACTIVE_H2_LINEAGE_ERROR = "iteration24_active_h2_lineage_ambiguous"
_H2_PROFILE = "company_card_v2_writer_v3"
_H2_CONTRACT = "company_public_h2_v1"

_PENDING_H2_REPORT_EXISTS = sa.text(
    "SELECT EXISTS ("
    "SELECT 1 FROM company_reports "
    "WHERE lifecycle_status = 'pending' "
    "AND writer_profile = :profile "
    "AND report_version = '3' "
    "AND presentation_contract = :contract "
    "AND rollout_generation > 0"
    ")"
).bindparams(profile=_H2_PROFILE, contract=_H2_CONTRACT)

_ACTIVE_H2_JOB_EXISTS = sa.text(
    "SELECT EXISTS ("
    "SELECT 1 FROM company_report_jobs "
    "WHERE state IN ('queued', 'running') "
    "AND writer_profile = :profile "
    "AND presentation_contract = :contract "
    "AND rollout_generation > 0"
    ")"
).bindparams(profile=_H2_PROFILE, contract=_H2_CONTRACT)


def _guard_active_h2_lineage() -> None:
    """Refuse to guess an unfinalized pre-0018 H2 lineage."""

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "LOCK TABLE company_reports IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    bind.execute(
        sa.text(
            "LOCK TABLE company_report_jobs IN SHARE ROW EXCLUSIVE MODE"
        )
    )

    # These predicates deliberately do not join the tables. A missing or
    # mismatched counterpart must not hide either active side of the lineage.
    pending_report_exists = bool(
        bind.execute(_PENDING_H2_REPORT_EXISTS).scalar()
    )
    active_job_exists = bool(bind.execute(_ACTIVE_H2_JOB_EXISTS).scalar())
    if pending_report_exists or active_job_exists:
        raise RuntimeError(_ACTIVE_H2_LINEAGE_ERROR)


def upgrade() -> None:
    _guard_active_h2_lineage()

    for table in ("company_reports", "company_report_jobs"):
        op.add_column(
            table,
            sa.Column(
                "arbitration_collection_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
        op.add_column(
            table,
            sa.Column(
                "arbitration_mask_key_id",
                sa.String(32),
                nullable=True,
            ),
        )
        op.create_check_constraint(
            f"{table}_arbitration_decision",
            table,
            "arbitration_collection_enabled OR arbitration_mask_key_id IS NULL",
        )


def downgrade() -> None:
    for table in ("company_report_jobs", "company_reports"):
        op.drop_constraint(
            f"{table}_arbitration_decision",
            table,
            type_="check",
        )
        op.drop_column(table, "arbitration_mask_key_id")
        op.drop_column(table, "arbitration_collection_enabled")
