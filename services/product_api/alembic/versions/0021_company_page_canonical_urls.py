"""admit deterministic form-first company-page canonical URLs.

Revision ID: 0021_company_page_canonical_urls
Revises: 0020_company_card_narrative_quota_mode
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0021_company_page_canonical_urls"
down_revision = "0020_company_card_narrative_quota_mode"
branch_labels = None
depends_on = None


_LEGACY_PATH = "canonical_path ~ '^/company/([0-9]{10}|[0-9]{12})-[a-z0-9]+(-[a-z0-9]+)*$'"
_V2_PATH = "canonical_path ~ '^/company/(ooo|ao|oao|zao|pao|ip)-[a-z0-9]+(-[a-z0-9]+)*-([0-9]{10}|[0-9]{12})$'"
_VALID_PATH = f"({_LEGACY_PATH} OR {_V2_PATH})"
_H2_BINDING_GUARD_FUNCTION = "company_report_h2_pin_url_binding_guard_v1"
_H2_BINDING_GUARD_TRIGGER = "trg_company_report_h2_pin_url_binding_guard_v1"

_H2_BINDING_GUARD_SQL = f"""
CREATE FUNCTION {_H2_BINDING_GUARD_FUNCTION}()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    subject_inn text;
    historical_fallback text;
    predecessor_count bigint;
    matching_count bigint;
BEGIN
    IF NEW.presentation_contract <> 'company_public_h2_v1' THEN
        RETURN NEW;
    END IF;

    SELECT normalized_identifier
    INTO subject_inn
    FROM company_report_subjects
    WHERE id = NEW.subject_id;
    IF subject_inn IS NULL THEN
        RAISE EXCEPTION 'company public H2 pin subject is missing'
            USING ERRCODE = '23514';
    END IF;
    historical_fallback := '/company/' || subject_inn || '-company';

    IF NEW.canonical_path IS NULL OR NOT (
        NEW.canonical_path ~ ('^/company/' || subject_inn || '-[a-z0-9]+(-[a-z0-9]+)*$')
        OR NEW.canonical_path ~ ('^/company/(ooo|ao|oao|zao|pao|ip)-[a-z0-9]+(-[a-z0-9]+)*-' || subject_inn || '$')
    ) THEN
        RAISE EXCEPTION 'new company public H2 pin requires a valid subject-bound canonical path'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.narrative_binding_status = 'unresolved' THEN
        RETURN NEW;
    END IF;

    IF NEW.projection_scope IS NULL OR NEW.projection_scope = 'staged_publication' THEN
        SELECT
            count(*),
            count(*) FILTER (WHERE
                COALESCE(p.canonical_path, historical_fallback) = NEW.canonical_path
                AND p.snapshot_hash = NEW.snapshot_hash
                AND p.chart_facts_version = NEW.chart_facts_version
                AND p.chart_facts_hash = NEW.chart_facts_hash
                AND p.evidence_registry_version = NEW.evidence_registry_version
                AND p.publication_policy_version = NEW.publication_policy_version
            )
        INTO predecessor_count, matching_count
        FROM company_report_presentation_pins AS p
        WHERE p.subject_id = NEW.subject_id
          AND p.report_id = NEW.report_id
          AND p.presentation_contract = 'company_public_h2_v1'
          AND p.generation < NEW.generation
          AND (p.projection_scope IS NULL OR p.projection_scope = 'staged_publication')
          AND p.narrative_binding_status = 'unresolved';
        IF predecessor_count <> 1 OR matching_count <> 1 THEN
            RAISE EXCEPTION 'resolved company public H2 pin binding differs from predecessor'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.projection_scope = 'active_publication' THEN
        SELECT
            count(*),
            count(*) FILTER (WHERE
                p.report_id = NEW.report_id
                AND p.generation < NEW.generation
                AND (p.projection_scope IS NULL OR p.projection_scope = 'staged_publication')
                AND p.narrative_binding_status = 'resolved'
                AND COALESCE(p.canonical_path, historical_fallback) = NEW.canonical_path
                AND p.snapshot_hash = NEW.snapshot_hash
                AND p.chart_facts_version = NEW.chart_facts_version
                AND p.chart_facts_hash = NEW.chart_facts_hash
                AND p.evidence_registry_version = NEW.evidence_registry_version
                AND p.publication_policy_version = NEW.publication_policy_version
                AND p.narrative_binding_kind = NEW.narrative_binding_kind
                AND p.narrative_binding_key = NEW.narrative_binding_key
            )
        INTO predecessor_count, matching_count
        FROM company_report_presentation_staged_pointers AS sp
        JOIN company_report_presentation_pins AS p
          ON p.subject_id = sp.subject_id
         AND p.presentation_contract = sp.presentation_contract
         AND p.generation = sp.generation
        WHERE sp.subject_id = NEW.subject_id
          AND sp.presentation_contract = 'company_public_h2_v1';
        IF predecessor_count <> 1 OR matching_count <> 1 THEN
            RAISE EXCEPTION 'active company public H2 pin binding differs from staged predecessor'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;

    RAISE EXCEPTION 'company public H2 pin lifecycle is invalid'
        USING ERRCODE = '23514';
END;
$$
"""

_PIN_SHAPE_0020 = (
    "(presentation_contract = 'company_public_h1_v1' AND projection_scope IS NULL "
    "AND indexable = true AND publication_policy_version IS NOT NULL "
    "AND canonical_path IS NOT NULL AND published_lastmod IS NOT NULL "
    "AND projection_digest IS NULL AND narrative_binding_status IS NULL "
    "AND narrative_binding_kind IS NULL AND narrative_binding_key IS NULL "
    "AND chart_facts_version IS NULL AND chart_facts_hash IS NULL "
    "AND evidence_registry_version IS NULL) "
    "OR (presentation_contract = 'company_public_h2_v1' "
    "AND (projection_scope IS NULL OR projection_scope IN ('staged_publication', 'active_publication')) "
    "AND chart_facts_version IS NOT NULL AND chart_facts_hash IS NOT NULL "
    "AND evidence_registry_version IS NOT NULL AND publication_policy_version IS NOT NULL "
    "AND ((projection_digest IS NULL AND narrative_binding_status = 'unresolved' "
    "AND narrative_binding_kind IS NULL AND narrative_binding_key IS NULL "
    "AND (projection_scope IS NULL OR projection_scope = 'staged_publication') "
    "AND indexable = false AND canonical_path IS NULL AND published_lastmod IS NULL) "
    "OR (projection_digest ~ '^[0-9a-f]{64}$' AND narrative_binding_status = 'resolved' "
    "AND narrative_binding_kind IN ('artifact', 'fallback') "
    "AND narrative_binding_key ~ '^[0-9a-f]{64}$' "
    "AND (((projection_scope IS NULL OR projection_scope = 'staged_publication') "
    "AND indexable = false AND canonical_path IS NULL AND published_lastmod IS NULL) "
    "OR (projection_scope = 'active_publication' "
    "AND publication_policy_version = 'company_public_h2_publication_v3' "
    "AND canonical_path IS NOT NULL AND published_lastmod IS NOT NULL)))))"
)

_PIN_SHAPE_0021 = (
    "(presentation_contract = 'company_public_h1_v1' AND projection_scope IS NULL "
    "AND indexable = true AND publication_policy_version IS NOT NULL "
    f"AND canonical_path IS NOT NULL AND {_VALID_PATH} AND published_lastmod IS NOT NULL "
    "AND projection_digest IS NULL AND narrative_binding_status IS NULL "
    "AND narrative_binding_kind IS NULL AND narrative_binding_key IS NULL "
    "AND chart_facts_version IS NULL AND chart_facts_hash IS NULL "
    "AND evidence_registry_version IS NULL) "
    "OR (presentation_contract = 'company_public_h2_v1' "
    "AND (projection_scope IS NULL OR projection_scope IN ('staged_publication', 'active_publication')) "
    "AND chart_facts_version IS NOT NULL AND chart_facts_hash IS NOT NULL "
    "AND evidence_registry_version IS NOT NULL AND publication_policy_version IS NOT NULL "
    "AND ((projection_digest IS NULL AND narrative_binding_status = 'unresolved' "
    "AND narrative_binding_kind IS NULL AND narrative_binding_key IS NULL "
    "AND (projection_scope IS NULL OR projection_scope = 'staged_publication') "
    f"AND indexable = false AND (canonical_path IS NULL OR {_VALID_PATH}) "
    "AND published_lastmod IS NULL) "
    "OR (projection_digest ~ '^[0-9a-f]{64}$' AND narrative_binding_status = 'resolved' "
    "AND narrative_binding_kind IN ('artifact', 'fallback') "
    "AND narrative_binding_key ~ '^[0-9a-f]{64}$' "
    "AND (((projection_scope IS NULL OR projection_scope = 'staged_publication') "
    f"AND indexable = false AND (canonical_path IS NULL OR {_VALID_PATH}) "
    "AND published_lastmod IS NULL) "
    "OR (projection_scope = 'active_publication' "
    "AND publication_policy_version = 'company_public_h2_publication_v3' "
    f"AND canonical_path IS NOT NULL AND {_VALID_PATH} "
    "AND published_lastmod IS NOT NULL)))))"
)


def upgrade() -> None:
    op.drop_constraint(
        "company_report_publication_path",
        "company_report_publications",
        type_="check",
    )
    op.create_check_constraint(
        "company_report_publication_path",
        "company_report_publications",
        _VALID_PATH,
    )
    op.drop_constraint(
        "company_report_presentation_pins_contract_shape",
        "company_report_presentation_pins",
        type_="check",
    )
    op.create_check_constraint(
        "company_report_presentation_pins_contract_shape",
        "company_report_presentation_pins",
        _PIN_SHAPE_0021,
    )
    op.execute(_H2_BINDING_GUARD_SQL)
    op.execute(
        f"CREATE TRIGGER {_H2_BINDING_GUARD_TRIGGER} "
        "BEFORE INSERT ON company_report_presentation_pins "
        f"FOR EACH ROW EXECUTE FUNCTION {_H2_BINDING_GUARD_FUNCTION}()"
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "LOCK TABLE company_report_publications, company_report_presentation_pins "
            "IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    incompatible = bind.execute(
        sa.text(
            "SELECT EXISTS ("
            "SELECT 1 FROM company_report_publications WHERE " + _V2_PATH +
            " UNION ALL SELECT 1 FROM company_report_presentation_pins "
            "WHERE (presentation_contract = 'company_public_h1_v1' AND " + _V2_PATH + ") "
            "OR (presentation_contract = 'company_public_h2_v1' AND ("
            "((projection_scope IS NULL OR projection_scope = 'staged_publication') "
            "AND canonical_path IS NOT NULL) OR " + _V2_PATH + ")) LIMIT 1)"
        )
    ).scalar()
    if incompatible:
        raise RuntimeError("refuse to discard company-page canonical URL bindings")

    op.execute(
        f"DROP TRIGGER {_H2_BINDING_GUARD_TRIGGER} "
        "ON company_report_presentation_pins"
    )
    op.execute(f"DROP FUNCTION {_H2_BINDING_GUARD_FUNCTION}()")

    op.drop_constraint(
        "company_report_presentation_pins_contract_shape",
        "company_report_presentation_pins",
        type_="check",
    )
    op.create_check_constraint(
        "company_report_presentation_pins_contract_shape",
        "company_report_presentation_pins",
        _PIN_SHAPE_0020,
    )
    op.drop_constraint(
        "company_report_publication_path",
        "company_report_publications",
        type_="check",
    )
    op.create_check_constraint(
        "company_report_publication_path",
        "company_report_publications",
        _LEGACY_PATH,
    )
