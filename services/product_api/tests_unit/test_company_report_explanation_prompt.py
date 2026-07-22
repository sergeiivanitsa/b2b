from product_api.company_reports.explanation.prompt import (
    build_explanation_messages,
    canonical_json,
    explanation_response_format,
)
from product_api.company_reports.explanation.models import (
    AllowedStatementCatalog,
    CatalogStatement,
)
from product_api.company_reports.explanation.validation import parse_selection, render_selection
from product_api.company_reports.explanation.validation import build_input_envelope
from product_api.company_reports.scoring import score_signals
from product_api.company_reports.signals import evaluate_signals

from company_report_signal_test_helpers import complete_company_report


def test_prompt_is_canonical_strict_and_allowlisted():
    report = complete_company_report()
    envelope = build_input_envelope(report, evaluate_signals(report), score_signals(evaluate_signals(report)))
    messages = build_explanation_messages(envelope)
    response_format = explanation_response_format(envelope.allowed_statement_catalog)

    assert messages[1].content == canonical_json(envelope.model_dump(mode="json"))
    assert report.target_identifier not in messages[1].content
    schema = response_format.json_schema.schema_
    assert schema["additionalProperties"] is False
    assert schema["properties"]["recovery_factor_ids"]["maxItems"] == 3
    assert schema["properties"]["overall_conclusion_id"]["enum"] == [
        envelope.allowed_statement_catalog.overall_conclusions[0].id
    ]


def test_empty_selectable_sections_never_emit_an_empty_enum_and_ground_empty_arrays():
    catalog = AllowedStatementCatalog(
        overall_conclusions=[CatalogStatement(id="overall", text="Overall.")],
        urgencies=[CatalogStatement(id="urgency", text="Urgency.")],
        recommended_next_steps=[CatalogStatement(id="next", text="Next.")],
    )
    schema = explanation_response_format(catalog).json_schema.schema_

    def assert_no_empty_enum(value):
        if isinstance(value, dict):
            if "enum" in value:
                assert value["enum"]
            for nested in value.values():
                assert_no_empty_enum(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_no_empty_enum(nested)

    assert_no_empty_enum(schema)
    for field in ("recovery_factor_ids", "key_risk_ids", "limitation_ids"):
        assert schema["properties"][field]["maxItems"] == 0
    selection = parse_selection(
        '{"output_schema_version":"1","overall_conclusion_id":"overall",'
        '"recovery_factor_ids":[],"key_risk_ids":[],"urgency_id":"urgency",'
        '"recommended_next_step_id":"next","limitation_ids":[]}'
    )
    rendered = render_selection(
        selection, catalog, prompt_version="v1", model_profile="economy_text_structured_v1",
        resolved_model="gpt-5.2", attempt_count=1,
    )
    assert rendered.recovery_factors == rendered.key_risks == rendered.limitations == []
