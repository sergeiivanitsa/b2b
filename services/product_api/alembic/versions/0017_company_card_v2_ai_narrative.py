"""create default-off Company Card v2 narrative infrastructure.

Revision ID: 0017_company_card_v2_ai_narrative
Revises: 0016_company_card_v2_foundation
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0017_company_card_v2_ai_narrative"
down_revision = "0016_company_card_v2_foundation"
branch_labels = None
depends_on = None


_HEX64 = "^[0-9a-f]{64}$"
_PIN_SHAPE_0017 = (
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
_PIN_SHAPE_0016 = (
    "(presentation_contract = 'company_public_h1_v1' AND indexable = true "
    "AND publication_policy_version IS NOT NULL AND canonical_path IS NOT NULL "
    "AND published_lastmod IS NOT NULL AND projection_digest IS NULL "
    "AND narrative_binding_status IS NULL AND narrative_binding_kind IS NULL "
    "AND narrative_binding_key IS NULL AND chart_facts_version IS NULL "
    "AND chart_facts_hash IS NULL AND evidence_registry_version IS NULL) "
    "OR (presentation_contract = 'company_public_h2_v1' AND indexable = false "
    "AND canonical_path IS NULL AND published_lastmod IS NULL "
    "AND projection_digest IS NULL AND chart_facts_version IS NOT NULL "
    "AND chart_facts_hash IS NOT NULL AND evidence_registry_version IS NOT NULL "
    "AND publication_policy_version IS NOT NULL "
    "AND narrative_binding_status = 'unresolved' "
    "AND narrative_binding_kind IS NULL AND narrative_binding_key IS NULL)"
)


def _hex(name: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(f"{name} ~ '{_HEX64}'", name=f"{name}_hex")


def upgrade() -> None:
    _create_runtime_control()
    _create_budget_windows()
    _create_jobs()
    _create_outbox()
    _create_reservations()
    _create_artifacts()
    _expand_h2_pin_contract()
    _validate_existing_h2_pins()
    _backfill_legacy_outbox()


def _create_runtime_control() -> None:
    op.create_table(
        "company_card_narrative_runtime_control",
        sa.Column("singleton_id", sa.SmallInteger(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("kill_switch", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("daily_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("monthly_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("concurrency_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("leased_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("singleton_id = 1", name="company_card_narrative_runtime_singleton"),
        sa.CheckConstraint(
            "daily_limit >= 0 AND monthly_limit >= 0 AND concurrency_limit >= 0 "
            "AND leased_count >= 0 AND (concurrency_limit = 0 OR concurrency_limit >= leased_count)",
            name="company_card_narrative_runtime_nonnegative",
        ),
    )
    op.execute(sa.text("INSERT INTO company_card_narrative_runtime_control (singleton_id) VALUES (1)"))


def _create_budget_windows() -> None:
    op.create_table(
        "company_card_narrative_budget_windows",
        sa.Column("period_kind", sa.String(7), primary_key=True),
        sa.Column("period_start_local", sa.Date(), primary_key=True),
        sa.Column("starts_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reserved_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consumed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("period_kind IN ('daily', 'monthly')", name="company_card_narrative_window_kind"),
        sa.CheckConstraint(
            "starts_at_utc < ends_at_utc AND reserved_count >= 0 AND consumed_count >= 0",
            name="company_card_narrative_window_shape",
        ),
    )


def _create_jobs() -> None:
    lease_states = "'leased', 'dispatching', 'dispatched', 'validating', 'rendered'"
    pre_dispatch_states = "'ready', 'leased', 'pre_dispatch_failed'"
    dispatched_states = (
        "'dispatching', 'dispatched', 'validating', 'rendered', 'finalized', "
        "'ambiguous_timeout', 'invalid_output'"
    )
    op.create_table(
        "company_card_narrative_jobs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("report_id", sa.Uuid(as_uuid=True), sa.ForeignKey("company_reports.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("snapshot_hash", sa.CHAR(64), nullable=False),
        sa.Column("generation_key", sa.CHAR(64), nullable=False, unique=True),
        sa.Column("identity_version", sa.String(32), nullable=False),
        sa.Column("generation_identity", postgresql.JSONB(), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_token", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fence_generation", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("local_attempt_count", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("gateway_dispatch_id", sa.Uuid(as_uuid=True), nullable=True, unique=True),
        sa.Column("dispatch_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_model_version", sa.String(255), nullable=True),
        sa.Column("validation_codes", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("artifact_id", sa.Uuid(as_uuid=True), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        _hex("snapshot_hash"),
        _hex("generation_key"),
        sa.CheckConstraint(
            "identity_version IN ('GenerationIdentityV1', 'GenerationIdentityV2')",
            name="company_card_narrative_job_identity",
        ),
        sa.CheckConstraint(
            "state IN ('ready', 'leased', 'dispatching', 'dispatched', 'validating', 'rendered', "
            "'finalized', 'pre_dispatch_failed', 'ambiguous_timeout', 'invalid_output', 'fallback_finalized')",
            name="company_card_narrative_job_state",
        ),
        sa.CheckConstraint(
            "fence_generation >= 0 AND local_attempt_count BETWEEN 0 AND 3",
            name="company_card_narrative_job_attempts",
        ),
        sa.CheckConstraint(
            f"(state IN ({lease_states}) AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) "
            f"OR (state NOT IN ({lease_states}) AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name="company_card_narrative_job_lease_shape",
        ),
        sa.CheckConstraint(
            f"(state IN ({pre_dispatch_states}) AND gateway_dispatch_id IS NULL AND dispatch_started_at IS NULL "
            "AND resolved_model_version IS NULL AND response_received_at IS NULL) OR "
            f"(state IN ({dispatched_states}) AND gateway_dispatch_id IS NOT NULL AND dispatch_started_at IS NOT NULL) OR "
            "(state = 'fallback_finalized' AND ((gateway_dispatch_id IS NULL AND dispatch_started_at IS NULL "
            "AND resolved_model_version IS NULL AND response_received_at IS NULL) OR "
            "(gateway_dispatch_id IS NOT NULL AND dispatch_started_at IS NOT NULL)))",
            name="company_card_narrative_job_dispatch_shape",
        ),
    )
    op.create_index(
        "ix_company_card_narrative_jobs_ready_selection",
        "company_card_narrative_jobs",
        ["state", "available_at", "id"],
    )
    op.create_index(
        "ix_company_card_narrative_jobs_expired_selection",
        "company_card_narrative_jobs",
        ["state", "lease_expires_at", "id"],
    )


def _create_outbox() -> None:
    op.create_table(
        "company_card_narrative_outbox",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("report_id", sa.Uuid(as_uuid=True), sa.ForeignKey("company_reports.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("snapshot_hash", sa.CHAR(64), nullable=False),
        sa.Column("event_kind", sa.String(48), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_token", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fence_generation", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("attempt_count", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("failure_code", sa.String(64), nullable=True),
        sa.Column(
            "generation_key",
            sa.CHAR(64),
            sa.ForeignKey("company_card_narrative_jobs.generation_key", deferrable=True, initially="DEFERRED"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        _hex("snapshot_hash"),
        sa.CheckConstraint("event_kind = 'initialize_narrative_v1'", name="company_card_narrative_outbox_kind"),
        sa.CheckConstraint("state IN ('pending', 'leased', 'processed', 'terminal')", name="company_card_narrative_outbox_state"),
        sa.CheckConstraint(
            "fence_generation >= 0 AND attempt_count BETWEEN 0 AND 3",
            name="company_card_narrative_outbox_attempts",
        ),
        sa.CheckConstraint(
            "(state = 'leased' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
            "(state <> 'leased' AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name="company_card_narrative_outbox_lease_shape",
        ),
        sa.CheckConstraint(
            "(state = 'processed' AND processed_at IS NOT NULL AND generation_key IS NOT NULL AND failure_code IS NULL) OR "
            "(state = 'terminal' AND processed_at IS NULL AND generation_key IS NULL AND failure_code IS NOT NULL) OR "
            "(state IN ('pending', 'leased') AND processed_at IS NULL AND generation_key IS NULL AND failure_code IS NULL)",
            name="company_card_narrative_outbox_terminal_shape",
        ),
        sa.UniqueConstraint("report_id", "snapshot_hash", "event_kind", name="uq_company_card_narrative_outbox_event"),
    )
    op.create_index(
        "ix_company_card_narrative_outbox_pending_selection",
        "company_card_narrative_outbox",
        ["state", "available_at", "lease_expires_at", "id"],
    )


def _create_reservations() -> None:
    op.create_table(
        "company_card_narrative_budget_reservations",
        sa.Column("generation_key", sa.CHAR(64), sa.ForeignKey("company_card_narrative_jobs.generation_key", ondelete="RESTRICT"), primary_key=True),
        sa.Column("dispatch_credit", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("state", sa.String(10), nullable=False),
        sa.Column("daily_period_kind", sa.String(7), nullable=False, server_default="daily"),
        sa.Column("daily_period_start_local", sa.Date(), nullable=False),
        sa.Column("monthly_period_kind", sa.String(7), nullable=False, server_default="monthly"),
        sa.Column("monthly_period_start_local", sa.Date(), nullable=False),
        sa.Column("reservation_epoch", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("release_code", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(
            ["daily_period_kind", "daily_period_start_local"],
            ["company_card_narrative_budget_windows.period_kind", "company_card_narrative_budget_windows.period_start_local"],
            name="fk_company_card_narrative_reservation_daily_window",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["monthly_period_kind", "monthly_period_start_local"],
            ["company_card_narrative_budget_windows.period_kind", "company_card_narrative_budget_windows.period_start_local"],
            name="fk_company_card_narrative_reservation_monthly_window",
            ondelete="RESTRICT",
        ),
        _hex("generation_key"),
        sa.CheckConstraint(
            "dispatch_credit = 1 AND state IN ('reserved', 'released', 'consumed') "
            "AND daily_period_kind = 'daily' AND monthly_period_kind = 'monthly' "
            "AND reservation_epoch BETWEEN 1 AND 3",
            name="company_card_narrative_reservation_shape",
        ),
        sa.CheckConstraint(
            "(state = 'consumed') = (consumed_at IS NOT NULL)",
            name="company_card_narrative_reservation_consumed_shape",
        ),
    )


def _create_artifacts() -> None:
    op.create_table(
        "company_card_narrative_artifacts",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("report_id", sa.Uuid(as_uuid=True), sa.ForeignKey("company_reports.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("snapshot_hash", sa.CHAR(64), nullable=False),
        sa.Column("generation_key", sa.CHAR(64), sa.ForeignKey("company_card_narrative_jobs.generation_key", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("binding_kind", sa.String(8), nullable=False),
        sa.Column("binding_key", sa.CHAR(64), nullable=False),
        sa.Column("artifact_identity", sa.CHAR(64), nullable=True),
        sa.Column("fallback_identity", sa.CHAR(64), nullable=True),
        sa.Column("resolved_model_version", sa.String(255), nullable=True),
        sa.Column("raw_model_output", sa.Text(), nullable=True),
        sa.Column("validated_render_plan_cjson", sa.LargeBinary(), nullable=True),
        sa.Column("validated_render_plan_bytes_sha256", sa.CHAR(64), nullable=True),
        sa.Column("rendered_description", sa.Text(), nullable=False),
        sa.Column("rendered_comments", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("statement_ids", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB(), nullable=False),
        sa.Column("phrase_trace", postgresql.JSONB(), nullable=False),
        sa.Column("validation_codes", postgresql.JSONB(), nullable=False),
        sa.Column("renderer_version", sa.String(96), nullable=False),
        sa.Column("rendered_output_bytes_sha256", sa.CHAR(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        _hex("snapshot_hash"),
        _hex("generation_key"),
        _hex("binding_key"),
        _hex("rendered_output_bytes_sha256"),
        sa.CheckConstraint("artifact_identity IS NULL OR artifact_identity ~ '^[0-9a-f]{64}$'", name="company_card_narrative_artifact_identity_hex"),
        sa.CheckConstraint("fallback_identity IS NULL OR fallback_identity ~ '^[0-9a-f]{64}$'", name="company_card_narrative_fallback_identity_hex"),
        sa.CheckConstraint("validated_render_plan_bytes_sha256 IS NULL OR validated_render_plan_bytes_sha256 ~ '^[0-9a-f]{64}$'", name="company_card_narrative_artifact_plan_hash_hex"),
        sa.CheckConstraint("binding_kind IN ('artifact', 'fallback')", name="company_card_narrative_artifact_kind"),
        sa.CheckConstraint("raw_model_output IS NULL OR octet_length(raw_model_output) <= 16384", name="company_card_narrative_artifact_raw_bound"),
        sa.CheckConstraint("validated_render_plan_cjson IS NULL OR octet_length(validated_render_plan_cjson) <= 16384", name="company_card_narrative_artifact_plan_bound"),
        sa.CheckConstraint("rendered_comments = '[]'::jsonb", name="company_card_narrative_artifact_comments_empty"),
        sa.CheckConstraint(
            "(binding_kind = 'artifact' AND binding_key = artifact_identity AND artifact_identity IS NOT NULL "
            "AND fallback_identity IS NULL AND resolved_model_version IS NOT NULL "
            "AND validated_render_plan_cjson IS NOT NULL AND validated_render_plan_bytes_sha256 IS NOT NULL) OR "
            "(binding_kind = 'fallback' AND binding_key = fallback_identity AND artifact_identity IS NULL "
            "AND fallback_identity IS NOT NULL AND resolved_model_version IS NULL AND raw_model_output IS NULL "
            "AND validated_render_plan_cjson IS NULL AND validated_render_plan_bytes_sha256 IS NULL "
            "AND renderer_version = 'company_card_h2_fallback_renderer_v1')",
            name="company_card_narrative_artifact_identity_shape",
        ),
        sa.UniqueConstraint("binding_kind", "binding_key", name="uq_company_card_narrative_artifact_binding"),
    )
    op.create_index(
        "ix_company_card_narrative_artifacts_exact_lookup",
        "company_card_narrative_artifacts",
        ["report_id", "snapshot_hash", "generation_key"],
    )
    op.create_foreign_key(
        "fk_company_card_narrative_job_artifact",
        "company_card_narrative_jobs",
        "company_card_narrative_artifacts",
        ["artifact_id"],
        ["id"],
        deferrable=True,
        initially="DEFERRED",
    )


def _expand_h2_pin_contract() -> None:
    op.drop_constraint("company_report_presentation_pins_contract_shape", "company_report_presentation_pins", type_="check")
    op.create_check_constraint("company_report_presentation_pins_contract_shape", "company_report_presentation_pins", _PIN_SHAPE_0017)
    op.create_foreign_key(
        "fk_company_report_h2_pin_narrative_binding",
        "company_report_presentation_pins",
        "company_card_narrative_artifacts",
        ["narrative_binding_kind", "narrative_binding_key"],
        ["binding_kind", "binding_key"],
        deferrable=True,
        initially="DEFERRED",
    )


def _validate_existing_h2_pins() -> None:
    """Fail closed before adding migration metadata for historical reports."""
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT p.report_id, p.snapshot_hash AS pin_snapshot_hash, p.chart_facts_hash, "
        "p.narrative_binding_status, p.narrative_binding_kind, p.narrative_binding_key, "
        "r.report_version, r.lifecycle_status, r.writer_profile, r.presentation_contract, "
        "r.rollout_generation, r.snapshot_hash AS report_snapshot_hash, r.normalized_snapshot "
        "FROM company_report_presentation_pins p "
        "JOIN company_reports r ON r.id = p.report_id AND r.subject_id = p.subject_id "
        "WHERE p.presentation_contract = 'company_public_h2_v1'"
    )).mappings().all()
    for row in rows:
        if (
            row["narrative_binding_status"] != "unresolved"
            or row["narrative_binding_kind"] is not None
            or row["narrative_binding_key"] is not None
            or row["report_version"] != "3"
            or row["lifecycle_status"] not in {"complete", "partial"}
            or row["writer_profile"] != "company_card_v2_writer_v3"
            or row["presentation_contract"] != "company_public_h2_v1"
            or not isinstance(row["rollout_generation"], int)
            or row["rollout_generation"] <= 0
            or not _is_hex64(row["pin_snapshot_hash"])
            or row["pin_snapshot_hash"] != row["report_snapshot_hash"]
            or not _is_hex64(row["chart_facts_hash"])
            or not _snapshot_hash_matches(row["normalized_snapshot"], row["report_version"], row["report_snapshot_hash"])
        ):
            raise RuntimeError("cannot migrate corrupt H2 presentation pin")


def _backfill_legacy_outbox() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT r.id, r.report_version, r.snapshot_hash, r.normalized_snapshot, "
        "COALESCE(r.finished_at, r.generated_at, r.updated_at, r.created_at) AS available_at "
        "FROM company_reports r "
        "WHERE r.lifecycle_status IN ('complete', 'partial') "
        "AND r.report_version IN ('1', '2', '3') "
        "AND r.normalized_snapshot IS NOT NULL AND r.snapshot_hash IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM company_report_presentation_pins p "
        "WHERE p.report_id = r.id AND p.presentation_contract = 'company_public_h2_v1' "
        "AND p.narrative_binding_status = 'resolved')"
    )).mappings().all()
    table = sa.table(
        "company_card_narrative_outbox",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("report_id", sa.Uuid(as_uuid=True)),
        sa.column("snapshot_hash", sa.String(64)),
        sa.column("event_kind", sa.String(48)),
        sa.column("state", sa.String(16)),
        sa.column("available_at", sa.DateTime(timezone=True)),
    )
    for row in rows:
        if not _snapshot_hash_matches(row["normalized_snapshot"], row["report_version"], row["snapshot_hash"]):
            raise RuntimeError("cannot backfill corrupt company report snapshot")
        bind.execute(postgresql.insert(table).values(
            id=uuid4(),
            report_id=row["id"],
            snapshot_hash=row["snapshot_hash"],
            event_kind="initialize_narrative_v1",
            state="pending",
            available_at=row["available_at"],
        ).on_conflict_do_nothing(constraint="uq_company_card_narrative_outbox_event"))


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _snapshot_hash_matches(snapshot: object, report_version: object, expected_hash: object) -> bool:
    if not isinstance(snapshot, dict) or not isinstance(report_version, str) or snapshot.get("report_version") != report_version:
        return False
    if not _is_hex64(expected_hash):
        return False
    try:
        serialized = _company_card_v2_cjson(snapshot) if report_version == "3" else json.dumps(
            snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
        )
    except (TypeError, ValueError):
        return False
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest() == expected_hash


def _company_card_v2_cjson(value: object) -> str:
    """Frozen 0017 copy of the v3 canonical JSON hash profile."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        raise ValueError("float is not canonical")
    if isinstance(value, str):
        normalized = unicodedata.normalize("NFC", value)
        if any(0xD800 <= ord(character) <= 0xDFFF for character in normalized):
            raise ValueError("surrogate is not canonical")
        return _company_card_v2_quote(normalized)
    if isinstance(value, dict):
        normalized: dict[str, object] = {}
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ValueError("non-string key is not canonical")
            clean_key = unicodedata.normalize("NFC", key)
            if clean_key in normalized:
                raise ValueError("duplicate normalized key")
            normalized[clean_key] = nested
        return "{" + ",".join(
            _company_card_v2_quote(key) + ":" + _company_card_v2_cjson(normalized[key])
            for key in sorted(normalized)
        ) + "}"
    if isinstance(value, list):
        return "[" + ",".join(_company_card_v2_cjson(item) for item in value) + "]"
    raise ValueError("value is not canonical")


def _company_card_v2_quote(value: str) -> str:
    pieces = ['"']
    for character in value:
        codepoint = ord(character)
        if character == '"':
            pieces.append('\\\"')
        elif character == "\\":
            pieces.append("\\\\")
        elif codepoint <= 0x1F:
            pieces.append(f"\\u{codepoint:04x}")
        else:
            pieces.append(character)
    pieces.append('"')
    return "".join(pieces)


def downgrade() -> None:
    bind = op.get_bind()
    populated_tables = (
        "company_card_narrative_outbox",
        "company_card_narrative_budget_windows",
        "company_card_narrative_budget_reservations",
        "company_card_narrative_jobs",
        "company_card_narrative_artifacts",
    )
    if any(bind.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar() for table in populated_tables):
        raise RuntimeError("refuse to discard narrative data")
    if bind.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM company_card_narrative_runtime_control "
        "WHERE enabled OR NOT kill_switch OR daily_limit <> 0 OR monthly_limit <> 0 "
        "OR concurrency_limit <> 0 OR leased_count <> 0)"
    )).scalar():
        raise RuntimeError("refuse to discard narrative runtime control")
    if bind.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM company_report_presentation_pins "
        "WHERE presentation_contract = 'company_public_h2_v1' AND narrative_binding_status = 'resolved')"
    )).scalar():
        raise RuntimeError("refuse to discard resolved narrative pins")
    op.drop_constraint("fk_company_report_h2_pin_narrative_binding", "company_report_presentation_pins", type_="foreignkey")
    op.drop_constraint("company_report_presentation_pins_contract_shape", "company_report_presentation_pins", type_="check")
    op.create_check_constraint("company_report_presentation_pins_contract_shape", "company_report_presentation_pins", _PIN_SHAPE_0016)
    op.drop_constraint("fk_company_card_narrative_job_artifact", "company_card_narrative_jobs", type_="foreignkey")
    for table in (
        "company_card_narrative_budget_reservations",
        "company_card_narrative_outbox",
        "company_card_narrative_artifacts",
        "company_card_narrative_jobs",
        "company_card_narrative_budget_windows",
        "company_card_narrative_runtime_control",
    ):
        op.drop_table(table)
