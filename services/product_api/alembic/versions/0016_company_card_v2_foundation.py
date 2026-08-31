"""create default-off Company Card v2 persistence foundation

Revision ID: 0016_company_card_v2_foundation
Revises: 0015_claims_company_report_handoff
Create Date: 2026-08-24 00:00:00
"""
import hashlib
import json
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "0016_company_card_v2_foundation"
down_revision = "0015_claims_company_report_handoff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing rows are always H1/v2; add nullable columns, backfill, then lock.
    for table in ("company_reports", "company_report_jobs"):
        op.add_column(table, sa.Column("writer_profile", sa.String(length=64), nullable=True))
        op.add_column(table, sa.Column("presentation_contract", sa.String(length=64), nullable=True))
        op.add_column(table, sa.Column("rollout_generation", sa.BigInteger(), nullable=True))
        op.execute(sa.text(f"UPDATE {table} SET writer_profile='h1_legacy_writer_v2', presentation_contract='company_public_h1_v1', rollout_generation=0 WHERE writer_profile IS NULL OR presentation_contract IS NULL OR rollout_generation IS NULL"))
        op.alter_column(table, "writer_profile", nullable=False, server_default="h1_legacy_writer_v2")
        op.alter_column(table, "presentation_contract", nullable=False, server_default="company_public_h1_v1")
        op.alter_column(table, "rollout_generation", nullable=False, server_default="0")
    op.add_column("company_report_jobs", sa.Column("fence_generation", sa.BigInteger(), nullable=False, server_default="0"))
    op.create_check_constraint("company_reports_profile_contract", "company_reports", "(writer_profile = 'h1_legacy_writer_v2' AND presentation_contract = 'company_public_h1_v1' AND report_version IN ('1','2') AND rollout_generation = 0) OR (writer_profile = 'company_card_v2_writer_v3' AND presentation_contract = 'company_public_h2_v1' AND report_version = '3' AND rollout_generation > 0)")
    op.create_check_constraint("company_report_jobs_profile_contract", "company_report_jobs", "(writer_profile = 'h1_legacy_writer_v2' AND presentation_contract = 'company_public_h1_v1' AND rollout_generation = 0) OR (writer_profile = 'company_card_v2_writer_v3' AND presentation_contract = 'company_public_h2_v1' AND rollout_generation > 0)")
    op.create_check_constraint("company_report_jobs_fence_generation", "company_report_jobs", "fence_generation >= 0")
    op.create_table(
        "company_report_presentations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("subject_id", sa.Uuid(as_uuid=True), sa.ForeignKey("company_report_subjects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("report_id", sa.Uuid(as_uuid=True), sa.ForeignKey("company_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("presentation_contract", sa.String(length=64), nullable=False),
        sa.Column("rollout_generation", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("presentation_contract = 'company_public_h2_v1' AND rollout_generation > 0", name="company_report_presentations_h2_only"),
        sa.UniqueConstraint("report_id", "presentation_contract", name="uq_company_report_presentations_report_contract"),
    )
    op.create_table(
        "company_report_presentation_pins",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("subject_id", sa.Uuid(as_uuid=True), sa.ForeignKey("company_report_subjects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("report_id", sa.Uuid(as_uuid=True), sa.ForeignKey("company_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("presentation_contract", sa.String(length=64), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("presentation_contract IN ('company_public_h1_v1', 'company_public_h2_v1')", name="company_report_presentation_pins_contract"),
        sa.CheckConstraint("generation > 0", name="company_report_presentation_pins_generation"),
        sa.UniqueConstraint("subject_id", "presentation_contract", "generation", name="uq_company_report_presentation_pins_generation"),
    )
    op.create_table(
        "company_report_presentation_staged_pointers",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("subject_id", sa.Uuid(as_uuid=True), sa.ForeignKey("company_report_subjects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pin_id", sa.Uuid(as_uuid=True), sa.ForeignKey("company_report_presentation_pins.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("expected_generation", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("expected_generation > 0", name="company_report_presentation_staged_generation"),
        sa.UniqueConstraint("subject_id", name="uq_company_report_presentation_staged_subject"),
    )
    op.create_table(
        "company_report_presentation_assignments",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("subject_id", sa.Uuid(as_uuid=True), sa.ForeignKey("company_report_subjects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pin_id", sa.Uuid(as_uuid=True), sa.ForeignKey("company_report_presentation_pins.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("generation > 0", name="company_report_presentation_assignment_generation"),
        sa.UniqueConstraint("subject_id", name="uq_company_report_presentation_assignment_subject"),
    )
    op.create_table(
        "company_report_presentation_assignment_journal",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", sa.Uuid(as_uuid=True), sa.ForeignKey("company_report_presentation_assignments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pin_id", sa.Uuid(as_uuid=True), sa.ForeignKey("company_report_presentation_pins.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("assignment_id", "generation", name="uq_company_report_presentation_assignment_journal_generation"),
    )
    _import_valid_active_h1_pins()


def _import_valid_active_h1_pins() -> None:
    """Import only verifiable active H1 publications, atomically or not at all."""
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT p.subject_id, p.report_id, p.snapshot_hash AS publication_hash, p.batch_generation, "
        "r.report_version, r.writer_profile, r.presentation_contract, r.rollout_generation, r.normalized_snapshot, r.snapshot_hash AS report_hash "
        "FROM company_report_publications p JOIN company_reports r ON r.id=p.report_id "
        "WHERE p.status='active'"
    )).mappings().all()
    inserts: list[dict[str, object]] = []
    for row in rows:
        snapshot = row["normalized_snapshot"]
        if (
            row["report_version"] not in {"1", "2"}
            or row["writer_profile"] != "h1_legacy_writer_v2"
            or row["presentation_contract"] != "company_public_h1_v1"
            or row["rollout_generation"] != 0
            or not isinstance(snapshot, dict)
            or not isinstance(row["report_hash"], str)
            or row["publication_hash"] != row["report_hash"]
            or snapshot.get("report_version") != row["report_version"]
            or str(snapshot.get("report_id")) != str(row["report_id"])
        ):
            raise RuntimeError("cannot import corrupt active H1 publication")
        digest = hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
        if digest != row["report_hash"]:
            raise RuntimeError("cannot import active H1 publication with invalid snapshot hash")
        inserts.append({
            "id": uuid4(), "subject_id": row["subject_id"], "report_id": row["report_id"],
            "presentation_contract": "company_public_h1_v1", "generation": row["batch_generation"],
            "snapshot_hash": row["report_hash"],
        })
    if inserts:
        bind.execute(sa.table("company_report_presentation_pins",
            sa.column("id"), sa.column("subject_id"), sa.column("report_id"), sa.column("presentation_contract"), sa.column("generation"), sa.column("snapshot_hash")
        ).insert(), inserts)


def downgrade() -> None:
    op.drop_table("company_report_presentation_assignment_journal")
    op.drop_table("company_report_presentation_assignments")
    op.drop_table("company_report_presentation_staged_pointers")
    op.drop_table("company_report_presentation_pins")
    op.drop_table("company_report_presentations")
    op.drop_constraint("company_report_jobs_fence_generation", "company_report_jobs", type_="check")
    op.drop_constraint("company_report_jobs_profile_contract", "company_report_jobs", type_="check")
    op.drop_constraint("company_reports_profile_contract", "company_reports", type_="check")
    op.drop_column("company_report_jobs", "fence_generation")
    for table in ("company_report_jobs", "company_reports"):
        op.drop_column(table, "rollout_generation")
        op.drop_column(table, "presentation_contract")
        op.drop_column(table, "writer_profile")
