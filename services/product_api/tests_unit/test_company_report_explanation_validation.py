import json
from datetime import date

import pytest

from product_api.company_reports.explanation.validation import (
    ExplanationValidationError,
    build_input_envelope,
    parse_selection,
    render_selection,
    validate_input_budget,
)
from product_api.company_reports import DatasetReportStatus
from product_api.company_reports.scoring import score_signals
from product_api.company_reports.signals import evaluate_signals

from company_report_signal_test_helpers import (
    company_report,
    complete_company_report,
    counterparty_facts,
)


def _inputs():
    report = complete_company_report(report_version="2")
    signals = evaluate_signals(report)
    return report, signals, score_signals(signals)


def _valid_selection(envelope):
    catalog = envelope.allowed_statement_catalog
    return {
        "output_schema_version": "1",
        "overall_conclusion_id": catalog.overall_conclusions[0].id,
        "recovery_factor_ids": [item.id for item in catalog.recovery_factors[:3]],
        "key_risk_ids": [item.id for item in catalog.key_risks[:3]],
        "urgency_id": catalog.urgencies[0].id,
        "recommended_next_step_id": catalog.recommended_next_steps[0].id,
        "limitation_ids": [item.id for item in catalog.limitations[:5]],
    }


def test_allowlisted_envelope_and_renderer_reject_ungrounded_ids():
    report, signals, scoring = _inputs()
    envelope = build_input_envelope(report, signals, scoring)
    dumped = json.dumps(envelope.model_dump(mode="json"), sort_keys=True)
    assert report.target_identifier not in dumped
    assert "raw_payload" not in dumped

    selection = parse_selection(json.dumps(_valid_selection(envelope)))
    rendered = render_selection(
        selection,
        envelope.allowed_statement_catalog,
        prompt_version="v1",
        model_profile="economy_text_structured_v1",
        resolved_model="gpt-5.2",
        attempt_count=1,
    )
    assert rendered.overall_conclusion == envelope.allowed_statement_catalog.overall_conclusions[0].text

    invalid = _valid_selection(envelope)
    invalid["overall_conclusion_id"] = "invented"
    with pytest.raises(ExplanationValidationError):
        render_selection(
            parse_selection(json.dumps(invalid)), envelope.allowed_statement_catalog,
            prompt_version="v1", model_profile="economy_text_structured_v1",
            resolved_model="gpt-5.2", attempt_count=1,
        )


@pytest.mark.parametrize("payload", ["not-json", '{"output_schema_version":"2"}', '{"unexpected":true}'])
def test_invalid_model_json_or_schema_is_rejected(payload):
    with pytest.raises(ExplanationValidationError):
        parse_selection(payload)


def test_input_budget_uses_utf8_byte_upper_bound():
    report, signals, scoring = _inputs()
    envelope = build_input_envelope(report, signals, scoring)
    with pytest.raises(ExplanationValidationError):
        validate_input_budget(envelope, 1)


def test_consistency_validation_accepts_partial_failed_mixed_and_status_conflict_paths():
    reports = [
        company_report(),
        company_report(counterparty_status=DatasetReportStatus.DISABLED),
        complete_company_report(),
        complete_company_report(
            counterparty=counterparty_facts(dissolved_date=date(2025, 1, 1))
        ),
    ]
    scoring_results = []
    for report in reports:
        signals = evaluate_signals(report)
        scoring = score_signals(signals)
        scoring_results.append(scoring)
        envelope = build_input_envelope(report, signals, scoring)
        assert envelope.scoring.reason_signal_codes == sorted(
            signal.code for signal in signals.signals
        )
    assert any(warning.code.value == "mixed_directions" for warning in scoring_results[2].warnings)
    assert any(warning.code.value == "status_conflict" for warning in scoring_results[3].warnings)


def test_consistency_validation_rejects_mixed_snapshots():
    report, signals, scoring = _inputs()
    with pytest.raises(ExplanationValidationError):
        build_input_envelope(report, signals, scoring.model_copy(update={"reasons": []}))
    with pytest.raises(ExplanationValidationError):
        build_input_envelope(
            report,
            signals,
            scoring.model_copy(update={"signal_ruleset_version": "unexpected"}),
        )

    partial_report = company_report()
    partial_signals = evaluate_signals(partial_report)
    partial_scoring = score_signals(partial_signals)
    with pytest.raises(ExplanationValidationError):
        build_input_envelope(
            partial_report,
            partial_signals,
            partial_scoring.model_copy(
                update={
                    "domain_breakdown": [
                        item.model_copy(update={"suppressed_rule_codes": []})
                        for item in partial_scoring.domain_breakdown
                    ]
                }
            ),
        )

    datasets = dict(report.datasets)
    datasets["finance"] = datasets["finance"].model_copy(
        update={"status": DatasetReportStatus.DISABLED}
    )
    with pytest.raises(ExplanationValidationError):
        build_input_envelope(report.model_copy(update={"datasets": datasets}), signals, scoring)

    partial_datasets = dict(partial_report.datasets)
    partial_datasets["finance"] = partial_datasets["finance"].model_copy(
        update={"status": DatasetReportStatus.AVAILABLE}
    )
    with pytest.raises(ExplanationValidationError):
        build_input_envelope(
            partial_report.model_copy(update={"datasets": partial_datasets}),
            partial_signals,
            partial_scoring,
        )
