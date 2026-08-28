"""add the default-off Company Card v2 rollout control plane.

Revision ID: 0019_company_card_v2_rollout_control
Revises: 0018_company_card_v2_arbitration
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0019_company_card_v2_rollout_control"
down_revision = "0018_company_card_v2_arbitration"
branch_labels = None
depends_on = None


_PIN_SHAPE_0018 = (
    "(presentation_contract = 'company_public_h1_v1' "
    "AND indexable = true AND publication_policy_version IS NOT NULL "
    "AND canonical_path IS NOT NULL AND published_lastmod IS NOT NULL "
    "AND projection_digest IS NULL "
    "AND narrative_binding_status IS NULL AND narrative_binding_kind IS NULL "
    "AND narrative_binding_key IS NULL AND chart_facts_version IS NULL "
    "AND chart_facts_hash IS NULL AND evidence_registry_version IS NULL) "
    "OR (presentation_contract = 'company_public_h2_v1' "
    "AND indexable = false AND canonical_path IS NULL AND published_lastmod IS NULL "
    "AND chart_facts_version IS NOT NULL AND chart_facts_hash IS NOT NULL "
    "AND evidence_registry_version IS NOT NULL AND publication_policy_version IS NOT NULL "
    "AND ((projection_digest IS NULL AND narrative_binding_status = 'unresolved' "
    "AND narrative_binding_kind IS NULL AND narrative_binding_key IS NULL) "
    "OR (projection_digest ~ '^[0-9a-f]{64}$' AND narrative_binding_status = 'resolved' "
    "AND narrative_binding_kind IN ('artifact', 'fallback') "
    "AND narrative_binding_key ~ '^[0-9a-f]{64}$')))"
)

_PIN_SHAPE_0019 = (
    "(presentation_contract = 'company_public_h1_v1' "
    "AND projection_scope IS NULL "
    "AND indexable = true AND publication_policy_version IS NOT NULL "
    "AND canonical_path IS NOT NULL AND published_lastmod IS NOT NULL "
    "AND projection_digest IS NULL "
    "AND narrative_binding_status IS NULL AND narrative_binding_kind IS NULL "
    "AND narrative_binding_key IS NULL AND chart_facts_version IS NULL "
    "AND chart_facts_hash IS NULL AND evidence_registry_version IS NULL) "
    "OR (presentation_contract = 'company_public_h2_v1' "
    "AND (projection_scope IS NULL OR projection_scope IN "
    "('staged_publication', 'active_publication')) "
    "AND chart_facts_version IS NOT NULL AND chart_facts_hash IS NOT NULL "
    "AND evidence_registry_version IS NOT NULL AND publication_policy_version IS NOT NULL "
    "AND ((projection_digest IS NULL AND narrative_binding_status = 'unresolved' "
    "AND narrative_binding_kind IS NULL AND narrative_binding_key IS NULL "
    "AND (projection_scope IS NULL OR projection_scope = 'staged_publication') "
    "AND indexable = false AND canonical_path IS NULL AND published_lastmod IS NULL) "
    "OR (projection_digest ~ '^[0-9a-f]{64}$' "
    "AND narrative_binding_status = 'resolved' "
    "AND narrative_binding_kind IN ('artifact', 'fallback') "
    "AND narrative_binding_key ~ '^[0-9a-f]{64}$' "
    "AND (((projection_scope IS NULL OR projection_scope = 'staged_publication') "
    "AND indexable = false AND canonical_path IS NULL AND published_lastmod IS NULL) "
    "OR (projection_scope = 'active_publication' "
    "AND publication_policy_version = 'company_public_h2_publication_v3' "
    "AND canonical_path IS NOT NULL AND published_lastmod IS NOT NULL)))))"
)

_DECISION_SHAPE = (
    "schema_version = 'company_card_v2_rollout_decision_v1' "
    "AND decision_digest ~ '^[0-9a-f]{64}$' "
    "AND release_commit ~ '^[0-9a-f]{40}$' "
    "AND target_count BETWEEN 1 AND 1000 "
    "AND ((action = 'activate' AND stage IN ('allowlist', 'percentage', 'ga') "
    "AND target_contract = 'company_public_h2_v1' "
    "AND (stage <> 'ga' OR h2_indexable = true)) "
    "OR (action = 'rollback' AND stage = 'emergency_rollback' "
    "AND target_contract = 'company_public_h1_v1' AND h2_indexable = false))"
)

_JOURNAL_AUDIT_SHAPE = (
    "(decision_id IS NULL AND decision_digest IS NULL AND reason_code IS NULL) "
    "OR (decision_id IS NOT NULL AND decision_digest IS NOT NULL "
    "AND reason_code IS NOT NULL AND decision_digest ~ '^[0-9a-f]{64}$' "
    "AND reason_code IN ('activate_allowlist', 'activate_percentage', "
    "'activate_ga', 'rollback_emergency_rollback'))"
)

_LEGACY_ASSIGNMENT_FK = (
    "fk_company_report_presentation_assignment_journal_assignment_id_"
    "company_report_presentation_assignments"
)
_NEW_ASSIGNMENT_FK = "fk_company_report_presentation_journal_assignment_subject"
_DOWNGRADE_REFUSAL = "iteration25_rollout_control_data_present"


def upgrade() -> None:
    op.add_column(
        "company_report_presentation_pins",
        sa.Column("projection_scope", sa.String(32), nullable=True),
    )
    op.drop_constraint(
        "company_report_presentation_pins_contract_shape",
        "company_report_presentation_pins",
        type_="check",
    )
    op.create_check_constraint(
        "company_report_presentation_pins_contract_shape",
        "company_report_presentation_pins",
        _PIN_SHAPE_0019,
    )

    op.create_table(
        "company_card_v2_rollout_decisions",
        sa.Column("decision_id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("decision_digest", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("release_commit", sa.String(40), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("target_contract", sa.String(64), nullable=False),
        sa.Column("h2_indexable", sa.Boolean(), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "decision_digest",
            name="uq_company_card_v2_rollout_decision_digest",
        ),
        sa.UniqueConstraint(
            "decision_id",
            "decision_digest",
            name="uq_company_card_v2_rollout_decision_identity",
        ),
        sa.CheckConstraint(
            _DECISION_SHAPE,
            name="company_card_v2_rollout_decision_shape",
        ),
    )

    op.add_column(
        "company_report_presentation_assignment_journal",
        sa.Column("decision_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "company_report_presentation_assignment_journal",
        sa.Column("decision_digest", sa.String(64), nullable=True),
    )
    op.add_column(
        "company_report_presentation_assignment_journal",
        sa.Column("reason_code", sa.String(64), nullable=True),
    )
    op.create_check_constraint(
        "company_report_presentation_assignment_journal_audit_shape",
        "company_report_presentation_assignment_journal",
        _JOURNAL_AUDIT_SHAPE,
    )
    op.create_unique_constraint(
        "uq_company_report_pin_journal_assignment_decision",
        "company_report_presentation_assignment_journal",
        ["assignment_id", "decision_digest"],
    )
    op.create_foreign_key(
        "fk_company_report_presentation_journal_decision",
        "company_report_presentation_assignment_journal",
        "company_card_v2_rollout_decisions",
        ["decision_id", "decision_digest"],
        ["decision_id", "decision_digest"],
        ondelete="RESTRICT",
    )

    _replace_assignment_foreign_key()


def _replace_assignment_foreign_key() -> None:
    bind = op.get_bind()
    mismatch = bind.execute(
        sa.text(
            "SELECT EXISTS ("
            "SELECT 1 FROM company_report_presentation_assignment_journal j "
            "JOIN company_report_presentation_assignments a ON a.id = j.assignment_id "
            "WHERE a.subject_id <> j.subject_id"
            ")"
        )
    ).scalar()
    if mismatch:
        raise RuntimeError("iteration25_legacy_assignment_subject_mismatch")

    op.create_unique_constraint(
        "uq_company_report_presentation_assignment_id_subject",
        "company_report_presentation_assignments",
        ["id", "subject_id"],
    )
    op.drop_constraint(
        op.f(_LEGACY_ASSIGNMENT_FK),
        "company_report_presentation_assignment_journal",
        type_="foreignkey",
    )
    op.create_foreign_key(
        _NEW_ASSIGNMENT_FK,
        "company_report_presentation_assignment_journal",
        "company_report_presentation_assignments",
        ["assignment_id", "subject_id"],
        ["id", "subject_id"],
        ondelete="CASCADE",
    )


def _guard_downgrade() -> None:
    bind = op.get_bind()
    for table in (
        "company_card_v2_rollout_decisions",
        "company_report_presentation_assignments",
        "company_report_presentation_pins",
        "company_report_presentation_assignment_journal",
    ):
        bind.execute(sa.text(f"LOCK TABLE {table} IN SHARE ROW EXCLUSIVE MODE"))

    unsafe = (
        bool(
            bind.execute(
                sa.text(
                    "SELECT EXISTS (SELECT 1 FROM company_report_presentation_pins "
                    "WHERE projection_scope IS NOT NULL)"
                )
            ).scalar()
        )
        or bool(
            bind.execute(
                sa.text(
                    "SELECT EXISTS ("
                    "SELECT 1 FROM company_report_presentation_assignment_journal "
                    "WHERE decision_id IS NOT NULL OR decision_digest IS NOT NULL "
                    "OR reason_code IS NOT NULL)"
                )
            ).scalar()
        )
        or bool(
            bind.execute(
                sa.text(
                    "SELECT EXISTS (SELECT 1 FROM company_card_v2_rollout_decisions)"
                )
            ).scalar()
        )
    )
    if unsafe:
        raise RuntimeError(_DOWNGRADE_REFUSAL)


def downgrade() -> None:
    # Alembic executes this function inside PostgreSQL transactional DDL.  The
    # deterministic locks are deliberately acquired before every guard query
    # and remain held until all constraint/column/table drops commit.
    _guard_downgrade()

    op.drop_constraint(
        _NEW_ASSIGNMENT_FK,
        "company_report_presentation_assignment_journal",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f(_LEGACY_ASSIGNMENT_FK),
        "company_report_presentation_assignment_journal",
        "company_report_presentation_assignments",
        ["assignment_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "uq_company_report_presentation_assignment_id_subject",
        "company_report_presentation_assignments",
        type_="unique",
    )

    op.drop_constraint(
        "fk_company_report_presentation_journal_decision",
        "company_report_presentation_assignment_journal",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_company_report_pin_journal_assignment_decision",
        "company_report_presentation_assignment_journal",
        type_="unique",
    )
    op.drop_constraint(
        "company_report_presentation_assignment_journal_audit_shape",
        "company_report_presentation_assignment_journal",
        type_="check",
    )
    for column in ("reason_code", "decision_digest", "decision_id"):
        op.drop_column("company_report_presentation_assignment_journal", column)

    op.drop_table("company_card_v2_rollout_decisions")

    op.drop_constraint(
        "company_report_presentation_pins_contract_shape",
        "company_report_presentation_pins",
        type_="check",
    )
    op.create_check_constraint(
        "company_report_presentation_pins_contract_shape",
        "company_report_presentation_pins",
        _PIN_SHAPE_0018,
    )
    op.drop_column("company_report_presentation_pins", "projection_scope")
