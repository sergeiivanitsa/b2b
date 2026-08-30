import json
from uuid import UUID

from product_api.company_reports.company_card_v2.narrative.models import NarrativeEvidenceEnvelope
from product_api.company_reports.company_card_v2.narrative.prompt import (
    build_narrative_gateway_body,
    narrative_json_schema,
)


DISPATCH_ID = UUID("123e4567-e89b-12d3-a456-426614174000")


def _facts(evidence: NarrativeEvidenceEnvelope) -> tuple[dict[str, object], str]:
    body = build_narrative_gateway_body(evidence, dispatch_id=DISPATCH_ID)
    content = body["messages"][0]["content"]
    assert isinstance(content, str)
    return json.loads(content), content


def test_gateway_body_contains_exact_privacy_safe_versions_and_admitted_activity():
    facts, content = _facts(NarrativeEvidenceEnvelope(
        evidence_registry_version="evidence_registry_v1",
        primary_activity_label="Разработка программного обеспечения",
    ))

    assert facts == {
        "allowed_evidence_ids": [
            "evidence_snapshot_identity_v1",
            "evidence_missing_semantics_policy_v1",
            "evidence_neutrality_policy_v1",
            "evidence_primary_activity_v1",
        ],
        "evidence_registry_version": "evidence_registry_v1",
        "input_schema_version": "company_card_narrative_input_v1",
        "insight_catalog_version": "company_card_narrative_insight_catalog_v1",
        "primary_activity_label": "Разработка программного обеспечения",
        "statement_catalog_version": "company_card_narrative_statement_catalog_v1",
        "template_catalog_version": "company_card_narrative_template_catalog_v1",
    }
    assert content == (
        '{"allowed_evidence_ids":["evidence_snapshot_identity_v1",'
        '"evidence_missing_semantics_policy_v1",'
        '"evidence_neutrality_policy_v1",'
        '"evidence_primary_activity_v1"],'
        '"evidence_registry_version":"evidence_registry_v1",'
        '"input_schema_version":"company_card_narrative_input_v1",'
        '"insight_catalog_version":"company_card_narrative_insight_catalog_v1",'
        '"primary_activity_label":"Разработка программного обеспечения",'
        '"statement_catalog_version":"company_card_narrative_statement_catalog_v1",'
        '"template_catalog_version":"company_card_narrative_template_catalog_v1"}'
    )
    assert "connector_catalog_version" not in facts
    for prohibited in ("report_id", "snapshot_hash", "chart_facts_hash", "primary_activity_code"):
        assert prohibited not in content


def test_gateway_body_is_canonical_and_emits_closed_unavailability_relation():
    evidence = NarrativeEvidenceEnvelope(
        evidence_registry_version="narrative_evidence_absent_v1",
        limitation_code="primary_activity_not_admitted",
    )

    facts, first = _facts(evidence)
    _repeat, second = _facts(evidence)

    assert first == second
    assert facts["limitation_code"] == "primary_activity_not_admitted"
    assert "primary_activity_label" not in facts
    assert facts["allowed_evidence_ids"] == [
        "evidence_snapshot_identity_v1",
        "evidence_missing_semantics_policy_v1",
        "evidence_neutrality_policy_v1",
    ]


def test_render_plan_schema_remains_recursively_closed_and_openai_compatible():
    schema = narrative_json_schema()["schema"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["output_schema_version"] == {
        "type": "string",
        "enum": ["company_card_narrative_render_plan_v1"],
    }
    description_plan = schema["properties"]["description_plan"]
    assert description_plan["additionalProperties"] is False
    for field in ("statement_ids", "connector_ids"):
        array = description_plan["properties"][field]
        assert array["minItems"] == array["maxItems"] == 3
        assert array["items"]["type"] == "string"
        assert len(array["items"]["enum"]) == 3
        assert "prefixItems" not in array
    assert schema["properties"]["chart_comments"]["items"] == {"type": "string"}


def test_every_object_schema_is_recursively_closed() -> None:
    root = narrative_json_schema()["schema"]
    object_nodes: list[dict[str, object]] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object":
                object_nodes.append(value)
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(root)

    assert len(object_nodes) == 2
    assert all(node.get("additionalProperties") is False for node in object_nodes)


def test_gateway_envelope_contains_no_forbidden_company_or_operational_identifiers() -> None:
    body = build_narrative_gateway_body(
        NarrativeEvidenceEnvelope(
            evidence_registry_version="evidence_registry_v1",
            primary_activity_label="Разработка программного обеспечения",
        ),
        dispatch_id=DISPATCH_ID,
    )
    content = body["messages"][0]["content"]
    assert isinstance(content, str)
    lowered = content.lower()

    for forbidden in (
        "inn",
        "ogrn",
        "kpp",
        "report_id",
        "subject_id",
        "company_id",
        "company_name",
        "address",
        "manager",
        "owner",
        "snapshot_hash",
        "chart_facts_hash",
        "primary_activity_code",
        "raw_payload",
        "api_key",
        "score",
        "verdict",
        "probability",
        "recommendation",
    ):
        assert forbidden not in lowered

    assert body["gateway_dispatch_id"] == str(DISPATCH_ID)
    assert type(body["timeout"]) is int
    assert type(body["max_output_tokens"]) is int
