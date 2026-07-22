import pytest

from product_api.company_reports.explanation.models import AIExplanationResult, AIExplanationStatus, ExplanationSelection
from product_api.company_reports.explanation.prompt import explanation_response_format
from product_api.company_reports.explanation.validation import build_input_envelope
from product_api.company_reports.scoring import score_signals
from product_api.company_reports.signals import evaluate_signals
from shared.schemas import ChatMessage, ChatMetadata, ChatRequest

from company_report_signal_test_helpers import complete_company_report


def test_selection_rejects_duplicate_and_excess_ids():
    with pytest.raises(ValueError):
        ExplanationSelection(
            output_schema_version="1",
            overall_conclusion_id="overall",
            recovery_factor_ids=["one", "one"],
            key_risk_ids=[],
            urgency_id="urgency",
            recommended_next_step_id="next",
            limitation_ids=[],
        )
    with pytest.raises(ValueError):
        ExplanationSelection(
            output_schema_version="1",
            overall_conclusion_id="overall",
            recovery_factor_ids=["1", "2", "3", "4"],
            key_risk_ids=[],
            urgency_id="urgency",
            recommended_next_step_id="next",
            limitation_ids=[],
        )


def test_result_requires_matching_failure_or_explanation():
    with pytest.raises(ValueError):
        AIExplanationResult(status=AIExplanationStatus.OK)


def test_chat_request_admits_only_legacy_or_structured_mode():
    with pytest.raises(ValueError):
        ChatRequest(messages=[ChatMessage(role="user", content="x")], model="gpt-5.2")

    report = complete_company_report()
    signals = evaluate_signals(report)
    envelope = build_input_envelope(report, signals, score_signals(signals))
    structured = ChatRequest(
        messages=[ChatMessage(role="user", content="x")],
        model=None,
        model_profile="economy_text_structured_v1",
        response_format=explanation_response_format(envelope.allowed_statement_catalog),
        max_output_tokens=1,
        stream=False,
        metadata=None,
    )
    assert structured.model is None
    with pytest.raises(ValueError):
        ChatRequest(
            messages=structured.messages,
            model=None,
            model_profile=structured.model_profile,
            response_format=structured.response_format,
            max_output_tokens=structured.max_output_tokens,
            metadata=ChatMetadata(company_id=1, user_id=1, conversation_id=1, message_id=1),
        )
