from __future__ import annotations

INPUT_SCHEMA_VERSION = "company_card_narrative_input_v1"
INSIGHT_CATALOG_VERSION = "company_card_narrative_insight_catalog_v1"
STATEMENT_CATALOG_VERSION = "company_card_narrative_statement_catalog_v1"
TEMPLATE_CATALOG_VERSION = "company_card_narrative_template_catalog_v1"
CONNECTOR_CATALOG_VERSION = "company_card_narrative_connector_catalog_v1"
RENDERER_VERSION = "company_card_narrative_renderer_v1"
FALLBACK_CATALOG_VERSION = "company_card_h2_fallback_catalog_v1"
FALLBACK_RENDERER_VERSION = "company_card_h2_fallback_renderer_v1"
FALLBACK_PROFILE_ID = "fallback_profile_any_v1"
FALLBACK_DESCRIPTION = "Карточка построена по зафиксированному снимку отчёта и отражает только факты, прошедшие проверку контракта. Деятельность и реквизиты показываются лишь при подтверждённом источнике; неизвестные значения не заменяются выводом. Финансовые показатели доступны после проверки единиц и исходных строк; закрытый или неполный раздел содержит ограничение. Арбитражные сведения зависят от подтверждённой выборки и правил приватности; неполная коллекция не означает отсутствия дел. Для скрытых данных применяется безопасное ограничение, а не догадка. Текст не содержит оценки надёжности, вероятности результата, рекомендации или интерпретации за пределами подтверждённых фактов и указанных ограничений."
OUTPUT_SCHEMA_VERSION = "company_card_narrative_render_plan_v1"
MODEL_PROFILE = "company_card_narrative_structured_v1"
PROMPT_VERSION = "company_card_narrative_prompt_v1"
POLICY_VERSION = "company_card_narrative_policy_v1"
GATEWAY_PROFILE_VERSION = MODEL_PROFILE
NARRATIVE_EVIDENCE_ABSENT = "narrative_evidence_absent_v1"
NOT_APPLICABLE = "not_applicable_v1"
LEGACY_SNAPSHOT_VERSIONS = {
    "1": "company_report_snapshot_v1_legacy",
    "2": "company_report_snapshot_v2_legacy",
}
FROZEN_V3_SNAPSHOT_VERSION = "company_card_v2_snapshot_v1"

INTRO = "Описание сформировано по сохранённому снимку отчёта и использует только сведения, прошедшие проверки источника, единиц и публичной приватности."
PRIMARY = "Основной вид деятельности в допущенных исходных данных обозначен как «{primary_activity_label}»."
MISSING = "Отсутствующее значение, неполный набор или закрытый раздел не превращаются в ноль, отрицательный факт либо положительный вывод о компании."
NEUTRAL = "Текст не содержит оценки надёжности, вероятности результата, совета, прогноза или неподтверждённой рекомендации. Последующее изменение источника требует новой генерации и не меняет уже опубликованный снимок."

INTRO_TEMPLATE_ID = "intro_snapshot_scope_v1"
STATEMENT_IDS = (
    "statement_primary_activity_v1", "statement_missing_is_unknown_v1",
    "statement_neutrality_and_immutability_v1",
)
CONNECTOR_IDS = (
    "connector_intro_activity_v1", "connector_activity_missing_v1",
    "connector_missing_neutrality_v1",
)
PUBLIC_STATEMENT_IDS = ("statement_snapshot_scope_v1",) + STATEMENT_IDS
EVIDENCE_BY_STATEMENT = {
    "statement_snapshot_scope_v1": ("evidence_snapshot_identity_v1",),
    "statement_primary_activity_v1": ("evidence_primary_activity_v1",),
    "statement_missing_is_unknown_v1": ("evidence_missing_semantics_policy_v1",),
    "statement_neutrality_and_immutability_v1": ("evidence_neutrality_policy_v1",),
}
