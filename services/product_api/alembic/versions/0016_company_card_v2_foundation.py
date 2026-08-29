"""create default-off Company Card v2 persistence foundation

Revision ID: 0016_company_card_v2_foundation
Revises: 0015_claims_company_report_handoff
"""
import hashlib
import json
import re
from unicodedata import normalize

from alembic import op
import sqlalchemy as sa


revision = "0016_company_card_v2_foundation"
down_revision = "0015_claims_company_report_handoff"
branch_labels = None
depends_on = None

H1_PROFILE = "h1_legacy_writer_v2"
H1_CONTRACT = "company_public_h1_v1"
H1_PUBLICATION_POLICY_VERSION = "publication_sufficiency_v1"
_H1_SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
# Frozen copy of the H1 canonical slug transform at revision 0016.  A
# migration must validate historical bytes against its own immutable contract,
# not import a mutable application helper from a later release.
_H1_TRANSLIT = str.maketrans({
    "а":"a", "б":"b", "в":"v", "г":"g", "д":"d", "е":"e", "ё":"e", "ж":"zh", "з":"z", "и":"i", "й":"i", "к":"k", "л":"l", "м":"m", "н":"n", "о":"o", "п":"p", "р":"r", "с":"s", "т":"t", "у":"u", "ф":"f", "х":"h", "ц":"c", "ч":"ch", "ш":"sh", "щ":"sh", "ъ":"", "ы":"y", "ь":"", "э":"e", "ю":"yu", "я":"ya",
})


def upgrade() -> None:
    bind = op.get_bind()
    # 0015 has only historical H1 reports. Unknown history must abort instead
    # of being silently re-labelled as H1 by the compatibility backfill.
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM company_reports WHERE report_version NOT IN ('1', '2'))")).scalar():
        raise RuntimeError("cannot backfill unknown company report version")
    for table in ("company_reports", "company_report_jobs"):
        op.add_column(table, sa.Column("writer_profile", sa.String(64), nullable=True))
        op.add_column(table, sa.Column("presentation_contract", sa.String(64), nullable=True))
        op.add_column(table, sa.Column("rollout_generation", sa.BigInteger(), nullable=True))
        op.execute(sa.text(
            f"UPDATE {table} SET writer_profile=:profile, presentation_contract=:contract, rollout_generation=0 "
            "WHERE writer_profile IS NULL OR presentation_contract IS NULL OR rollout_generation IS NULL"
        ).bindparams(profile=H1_PROFILE, contract=H1_CONTRACT))
        op.alter_column(table, "writer_profile", nullable=False, server_default=H1_PROFILE)
        op.alter_column(table, "presentation_contract", nullable=False, server_default=H1_CONTRACT)
        op.alter_column(table, "rollout_generation", nullable=False, server_default="0")
    op.add_column("company_report_jobs", sa.Column("fence_generation", sa.BigInteger(), nullable=False, server_default="0"))
    # Historical 0013 jobs already encode whether the only allowed worker
    # attempt happened.  Preserve that fencing generation before adding the
    # stricter 0016 shape constraint; leaving the new column at its default
    # would reject every valid running, succeeded, or attempted-failed row.
    op.execute(sa.text(
        "UPDATE company_report_jobs SET fence_generation = attempt_count "
        "WHERE fence_generation <> attempt_count"
    ))
    op.create_check_constraint("company_reports_profile_contract", "company_reports", "(writer_profile = 'h1_legacy_writer_v2' AND presentation_contract = 'company_public_h1_v1' AND report_version IN ('1','2') AND rollout_generation = 0) OR (writer_profile = 'company_card_v2_writer_v3' AND presentation_contract = 'company_public_h2_v1' AND report_version = '3' AND rollout_generation > 0)")
    op.create_check_constraint("company_report_jobs_profile_contract", "company_report_jobs", "(writer_profile = 'h1_legacy_writer_v2' AND presentation_contract = 'company_public_h1_v1' AND rollout_generation = 0) OR (writer_profile = 'company_card_v2_writer_v3' AND presentation_contract = 'company_public_h2_v1' AND rollout_generation > 0)")
    op.create_check_constraint("company_report_jobs_fence_generation", "company_report_jobs", "fence_generation >= 0")
    op.create_check_constraint("company_report_jobs_fence_shape", "company_report_jobs", "(state = 'queued' AND fence_generation = 0) OR (state IN ('running', 'succeeded') AND attempt_count = 1 AND fence_generation = 1) OR (state = 'failed' AND ((attempt_count = 0 AND fence_generation = 0) OR (attempt_count = 1 AND fence_generation = 1)))")
    # The redundant pair is a deliberate FK target for all public bindings.
    # A report UUID alone cannot prove that the binding has the same subject.
    op.create_unique_constraint("uq_company_reports_id_subject", "company_reports", ["id", "subject_id"])
    _create_presentation_tables()
    _import_valid_active_h1_pins()


def _create_presentation_tables() -> None:
    op.create_table(
        "company_report_presentations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("subject_id", sa.Uuid(as_uuid=True), sa.ForeignKey("company_report_subjects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("report_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("presentation_contract", sa.String(64), nullable=False),
        sa.Column("rollout_generation", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["report_id", "subject_id"], ["company_reports.id", "company_reports.subject_id"], name="fk_company_report_presentations_report_subject", ondelete="CASCADE"),
        sa.CheckConstraint("presentation_contract = 'company_public_h2_v1' AND rollout_generation > 0", name="company_report_presentations_h2_only"),
        sa.UniqueConstraint("report_id", "presentation_contract", name="uq_company_report_presentations_report_contract"),
        sa.UniqueConstraint("id", "subject_id", "report_id", "presentation_contract", "rollout_generation", name="uq_company_report_presentations_exact_binding"),
    )
    op.create_table(
        "company_report_presentation_pins",
        sa.Column("subject_id", sa.Uuid(as_uuid=True), sa.ForeignKey("company_report_subjects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("report_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("presentation_contract", sa.String(64), primary_key=True),
        sa.Column("generation", sa.BigInteger(), primary_key=True),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("chart_facts_version", sa.String(64), nullable=True),
        sa.Column("chart_facts_hash", sa.String(64), nullable=True),
        sa.Column("evidence_registry_version", sa.String(64), nullable=True),
        sa.Column("publication_policy_version", sa.String(64), nullable=True),
        sa.Column("canonical_path", sa.String(2048), nullable=True),
        sa.Column("indexable", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("published_lastmod", sa.DateTime(timezone=True), nullable=True),
        sa.Column("projection_digest", sa.String(64), nullable=True),
        sa.Column("narrative_binding_status", sa.String(16), nullable=True),
        sa.Column("narrative_binding_kind", sa.String(64), nullable=True),
        sa.Column("narrative_binding_key", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["report_id", "subject_id"], ["company_reports.id", "company_reports.subject_id"], name="fk_company_report_presentation_pins_report_subject", ondelete="CASCADE"),
        sa.CheckConstraint("generation > 0", name="company_report_presentation_pins_generation"),
        sa.CheckConstraint("(presentation_contract = 'company_public_h1_v1' AND indexable = true AND publication_policy_version IS NOT NULL AND canonical_path IS NOT NULL AND published_lastmod IS NOT NULL AND projection_digest IS NULL AND narrative_binding_status IS NULL AND narrative_binding_kind IS NULL AND narrative_binding_key IS NULL AND chart_facts_version IS NULL AND chart_facts_hash IS NULL AND evidence_registry_version IS NULL) OR (presentation_contract = 'company_public_h2_v1' AND indexable = false AND canonical_path IS NULL AND published_lastmod IS NULL AND projection_digest IS NULL AND chart_facts_version IS NOT NULL AND chart_facts_hash IS NOT NULL AND evidence_registry_version IS NOT NULL AND publication_policy_version IS NOT NULL AND narrative_binding_status = 'unresolved' AND narrative_binding_kind IS NULL AND narrative_binding_key IS NULL)", name="company_report_presentation_pins_contract_shape"),
    )
    op.create_table(
        "company_report_h2_lifecycle_heads",
        sa.Column("subject_id", sa.Uuid(as_uuid=True), sa.ForeignKey("company_report_subjects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("presentation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("report_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("presentation_contract", sa.String(64), nullable=False),
        sa.Column("rollout_generation", sa.BigInteger(), nullable=False),
        sa.Column("head_generation", sa.BigInteger(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["presentation_id", "subject_id", "report_id", "presentation_contract", "rollout_generation"], ["company_report_presentations.id", "company_report_presentations.subject_id", "company_report_presentations.report_id", "company_report_presentations.presentation_contract", "company_report_presentations.rollout_generation"], name="fk_company_report_h2_head_presentation_binding", ondelete="RESTRICT"),
        sa.CheckConstraint("presentation_contract = 'company_public_h2_v1'", name="company_report_h2_head_contract"),
        sa.CheckConstraint("rollout_generation > 0 AND head_generation > 0", name="company_report_h2_head_generation"),
    )
    _create_pin_reference_tables()


def _create_pin_reference_tables() -> None:
    pin_columns = ["company_report_presentation_pins.subject_id", "company_report_presentation_pins.presentation_contract", "company_report_presentation_pins.generation"]
    op.create_table(
        "company_report_presentation_staged_pointers",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("subject_id", sa.Uuid(as_uuid=True), sa.ForeignKey("company_report_subjects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("presentation_contract", sa.String(64), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["subject_id", "presentation_contract", "generation"], pin_columns, name="fk_company_report_presentation_staged_pin", ondelete="RESTRICT"),
        sa.CheckConstraint("generation > 0", name="company_report_presentation_staged_generation"),
        sa.UniqueConstraint("subject_id", name="uq_company_report_presentation_staged_subject"),
    )
    op.create_table(
        "company_report_presentation_assignments",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("subject_id", sa.Uuid(as_uuid=True), sa.ForeignKey("company_report_subjects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("presentation_contract", sa.String(64), nullable=False),
        sa.Column("pin_generation", sa.BigInteger(), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["subject_id", "presentation_contract", "pin_generation"], pin_columns, name="fk_company_report_presentation_assignment_pin", ondelete="RESTRICT"),
        sa.CheckConstraint("generation > 0 AND pin_generation > 0", name="company_report_presentation_assignment_generation"),
        sa.UniqueConstraint("subject_id", name="uq_company_report_presentation_assignment_subject"),
    )
    op.create_table(
        "company_report_presentation_assignment_journal",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", sa.Uuid(as_uuid=True), sa.ForeignKey("company_report_presentation_assignments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject_id", sa.Uuid(as_uuid=True), sa.ForeignKey("company_report_subjects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("presentation_contract", sa.String(64), nullable=False),
        sa.Column("pin_generation", sa.BigInteger(), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["subject_id", "presentation_contract", "pin_generation"], pin_columns, name="fk_company_report_presentation_journal_pin", ondelete="RESTRICT"),
        sa.CheckConstraint("generation > 0 AND pin_generation > 0", name="company_report_presentation_assignment_journal_generation"),
        sa.UniqueConstraint("assignment_id", "generation", name="uq_company_report_pin_journal_assignment_generation"),
    )


def _import_valid_active_h1_pins() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT p.subject_id, p.report_id, p.snapshot_hash AS publication_hash, p.batch_generation, p.policy_version, p.canonical_slug, p.canonical_path, p.indexable, p.published_lastmod, r.subject_id AS report_subject_id, r.report_version, r.lifecycle_status, r.generated_at, r.writer_profile, r.presentation_contract, r.rollout_generation, r.normalized_snapshot, r.snapshot_hash AS report_hash, s.normalized_identifier AS subject_inn FROM company_report_publications p JOIN company_reports r ON r.id=p.report_id JOIN company_report_subjects s ON s.id=p.subject_id WHERE p.status='active'"
    )).mappings().all()
    inserts: list[dict[str, object]] = []
    for row in rows:
        snapshot = row["normalized_snapshot"]
        subject_inn = row["subject_inn"]
        counterparty = snapshot.get("counterparty") if isinstance(snapshot, dict) else None
        canonical_name = _h1_counterparty_name(counterparty)
        canonical_slug = row["canonical_slug"]
        expected_path = _h1_canonical_path(subject_inn, canonical_name) if isinstance(subject_inn, str) and canonical_name is not None else None
        if (row["subject_id"] != row["report_subject_id"] or not isinstance(subject_inn, str) or not subject_inn.isascii() or not subject_inn.isdigit() or len(subject_inn) not in {10, 12} or row["report_version"] not in {"1", "2"} or row["lifecycle_status"] not in {"complete", "partial"} or row["writer_profile"] != H1_PROFILE or row["presentation_contract"] != H1_CONTRACT or row["rollout_generation"] != 0 or not isinstance(snapshot, dict) or not isinstance(row["report_hash"], str) or len(row["report_hash"]) != 64 or any(char not in "0123456789abcdef" for char in row["report_hash"].lower()) or row["publication_hash"] != row["report_hash"] or snapshot.get("report_version") != row["report_version"] or str(snapshot.get("report_id")) != str(row["report_id"]) or snapshot.get("target_identifier") != subject_inn or not isinstance(counterparty, dict) or counterparty.get("inn") != subject_inn or row["policy_version"] != H1_PUBLICATION_POLICY_VERSION or not isinstance(canonical_slug, str) or _H1_SLUG_RE.fullmatch(canonical_slug) is None or len(canonical_slug) > 200 or row["canonical_path"] != expected_path or row["canonical_path"] != f"/company/{subject_inn}-{canonical_slug}" or row["batch_generation"] is None or row["batch_generation"] <= 0 or row["indexable"] is not True or row["published_lastmod"] is None or row["generated_at"] is None or row["published_lastmod"] != row["generated_at"]):
            raise RuntimeError("cannot import corrupt active H1 publication")
        digest = hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
        if digest != row["report_hash"]:
            raise RuntimeError("cannot import active H1 publication with invalid snapshot hash")
        inserts.append({"subject_id": row["subject_id"], "report_id": row["report_id"], "presentation_contract": H1_CONTRACT, "generation": row["batch_generation"], "snapshot_hash": row["report_hash"], "publication_policy_version": row["policy_version"], "canonical_path": row["canonical_path"], "indexable": True, "published_lastmod": row["published_lastmod"]})
    if inserts:
        bind.execute(sa.table("company_report_presentation_pins", sa.column("subject_id"), sa.column("report_id"), sa.column("presentation_contract"), sa.column("generation"), sa.column("snapshot_hash"), sa.column("publication_policy_version"), sa.column("canonical_path"), sa.column("indexable"), sa.column("published_lastmod")).insert(), inserts)


def _h1_counterparty_name(counterparty: object) -> str | None:
    if not isinstance(counterparty, dict):
        return None
    for key in ("short_name", "full_name"):
        value = counterparty.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _h1_canonical_path(inn: str, name: str) -> str | None:
    value = normalize("NFKD", name.lower().translate(_H1_TRANSLIT))
    value = "".join(char for char in value if not ("\u0300" <= char <= "\u036f"))
    value = "".join(char if char.isascii() and char.isalnum() else "-" for char in value)
    slug = re.sub(r"-+", "-", value).strip("-")[:200].rstrip("-")
    return f"/company/{inn}-{slug}" if slug and _H1_SLUG_RE.fullmatch(slug) else None


def downgrade() -> None:
    op.drop_table("company_report_h2_lifecycle_heads")
    op.drop_table("company_report_presentation_assignment_journal")
    op.drop_table("company_report_presentation_assignments")
    op.drop_table("company_report_presentation_staged_pointers")
    op.drop_table("company_report_presentation_pins")
    op.drop_table("company_report_presentations")
    op.drop_constraint("company_report_jobs_fence_shape", "company_report_jobs", type_="check")
    op.drop_constraint("company_report_jobs_fence_generation", "company_report_jobs", type_="check")
    op.drop_constraint("company_report_jobs_profile_contract", "company_report_jobs", type_="check")
    op.drop_constraint("company_reports_profile_contract", "company_reports", type_="check")
    op.drop_constraint("uq_company_reports_id_subject", "company_reports", type_="unique")
    op.drop_column("company_report_jobs", "fence_generation")
    for table in ("company_report_jobs", "company_reports"):
        op.drop_column(table, "rollout_generation")
        op.drop_column(table, "presentation_contract")
        op.drop_column(table, "writer_profile")
