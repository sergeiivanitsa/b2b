from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from product_api.company_reports.company_card_v2.narrative import catalog


FIXTURES = Path(__file__).parent / "fixtures" / "company_card_v2"


def test_runtime_catalog_versions_and_fixed_render_plan_ids_are_exact() -> None:
    assert catalog.INPUT_SCHEMA_VERSION == "company_card_narrative_input_v1"
    assert catalog.INSIGHT_CATALOG_VERSION == "company_card_narrative_insight_catalog_v1"
    assert catalog.STATEMENT_CATALOG_VERSION == "company_card_narrative_statement_catalog_v1"
    assert catalog.TEMPLATE_CATALOG_VERSION == "company_card_narrative_template_catalog_v1"
    assert catalog.CONNECTOR_CATALOG_VERSION == "company_card_narrative_connector_catalog_v1"
    assert catalog.OUTPUT_SCHEMA_VERSION == "company_card_narrative_render_plan_v1"
    assert catalog.MODEL_PROFILE == "company_card_narrative_structured_v1"
    assert catalog.INTRO_TEMPLATE_ID == "intro_snapshot_scope_v1"
    assert catalog.STATEMENT_IDS == (
        "statement_primary_activity_v1",
        "statement_missing_is_unknown_v1",
        "statement_neutrality_and_immutability_v1",
    )
    assert catalog.CONNECTOR_IDS == (
        "connector_intro_activity_v1",
        "connector_activity_missing_v1",
        "connector_missing_neutrality_v1",
    )


def test_normative_russian_catalog_wording_is_byte_exact() -> None:
    assert catalog.INTRO == (
        "Описание сформировано по сохранённому снимку отчёта и использует только сведения, "
        "прошедшие проверки источника, единиц и публичной приватности."
    )
    assert catalog.PRIMARY == (
        "Основной вид деятельности в допущенных исходных данных обозначен как "
        "«{primary_activity_label}»."
    )
    assert catalog.MISSING == (
        "Отсутствующее значение, неполный набор или закрытый раздел не превращаются в ноль, "
        "отрицательный факт либо положительный вывод о компании."
    )
    assert catalog.NEUTRAL == (
        "Текст не содержит оценки надёжности, вероятности результата, совета, прогноза или "
        "неподтверждённой рекомендации. Последующее изменение источника требует новой "
        "генерации и не меняет уже опубликованный снимок."
    )


def test_statement_to_evidence_allowlist_and_public_order_are_closed() -> None:
    assert catalog.PUBLIC_STATEMENT_IDS == (
        "statement_snapshot_scope_v1",
        "statement_primary_activity_v1",
        "statement_missing_is_unknown_v1",
        "statement_neutrality_and_immutability_v1",
    )
    assert catalog.EVIDENCE_BY_STATEMENT == {
        "statement_snapshot_scope_v1": ("evidence_snapshot_identity_v1",),
        "statement_primary_activity_v1": ("evidence_primary_activity_v1",),
        "statement_missing_is_unknown_v1": ("evidence_missing_semantics_policy_v1",),
        "statement_neutrality_and_immutability_v1": ("evidence_neutrality_policy_v1",),
    }


def test_universal_fallback_is_exact_691_scalar_golden() -> None:
    golden = json.loads((FIXTURES / "narrative_fallback_golden.json").read_text(encoding="utf-8"))

    assert catalog.FALLBACK_DESCRIPTION == golden["description"]
    assert len(catalog.FALLBACK_DESCRIPTION) == golden["scalar_count"] == 691
    assert sha256(catalog.FALLBACK_DESCRIPTION.encode("utf-8")).hexdigest() == golden["render_digest"]
    assert catalog.FALLBACK_PROFILE_ID == "fallback_profile_any_v1"
    assert catalog.FALLBACK_CATALOG_VERSION == "company_card_h2_fallback_catalog_v1"
    assert catalog.FALLBACK_RENDERER_VERSION == "company_card_h2_fallback_renderer_v1"
