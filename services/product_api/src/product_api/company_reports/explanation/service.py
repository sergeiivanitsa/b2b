from __future__ import annotations

from product_api.company_reports.aggregate import CompanyReport
from product_api.company_reports.scoring.models import ScoringResult
from product_api.company_reports.signals.models import SignalEvaluationResult
from product_api.gateway_client import GatewayError, send_chat
from product_api.settings import Settings
from shared.constants import AI_EXPLANATION_OUTPUT_SCHEMA_VERSION
from shared.schemas import ChatRequest

from .models import AIExplanationFailure, AIExplanationResult, AIExplanationStatus
from .prompt import build_explanation_messages, explanation_response_format
from .validation import (
    ExplanationValidationError,
    build_input_envelope,
    parse_selection,
    render_selection,
    validate_input_budget,
)


def _failure(
    status: AIExplanationStatus,
    safe_code: str,
    settings: Settings,
    *,
    retry_attempted: bool,
) -> AIExplanationResult:
    return AIExplanationResult(
        status=status,
        failure=AIExplanationFailure(
            safe_code=safe_code,
            model_profile=settings.ai_explanation_model_profile,
            prompt_version=settings.ai_explanation_prompt_version,
            output_schema_version=AI_EXPLANATION_OUTPUT_SCHEMA_VERSION,
            retry_attempted=retry_attempted,
        ),
    )


async def explain_scoring_result(
    settings: Settings,
    report: CompanyReport,
    signal_evaluation: SignalEvaluationResult,
    scoring: ScoringResult,
) -> AIExplanationResult:
    """Request at most two strict selections and render only catalog text locally."""

    if not settings.ai_explanation_enabled:
        return _failure(
            AIExplanationStatus.CONFIGURATION_ERROR,
            "explanation_disabled",
            settings,
            retry_attempted=False,
        )
    try:
        envelope = build_input_envelope(report, signal_evaluation, scoring)
        validate_input_budget(envelope, settings.ai_explanation_max_input_tokens)
        payload = ChatRequest(
            messages=build_explanation_messages(envelope),
            model=None,
            model_profile=settings.ai_explanation_model_profile,
            response_format=explanation_response_format(envelope.allowed_statement_catalog),
            max_output_tokens=settings.ai_explanation_max_output_tokens,
            stream=False,
            timeout=settings.ai_explanation_timeout_seconds,
            metadata=None,
        )
    except (ExplanationValidationError, ValueError):
        return _failure(
            AIExplanationStatus.CONFIGURATION_ERROR,
            "invalid_local_explanation_input",
            settings,
            retry_attempted=False,
        )

    retried = False
    for attempt in (1, 2):
        try:
            response = await send_chat(settings, payload)
        except GatewayError as exc:
            if exc.is_transport_failure and attempt == 1:
                retried = True
                continue
            return _failure(
                AIExplanationStatus.TRANSPORT_FAILURE,
                "gateway_transport_failure"
                if exc.is_transport_failure
                else "gateway_request_failure",
                settings,
                retry_attempted=retried,
            )
        if (
            response.model_profile != settings.ai_explanation_model_profile
            or not response.resolved_model
        ):
            return _failure(
                AIExplanationStatus.CONFIGURATION_ERROR,
                "gateway_contract_mismatch",
                settings,
                retry_attempted=retried,
            )
        try:
            selection = parse_selection(response.text)
            explanation = render_selection(
                selection,
                envelope.allowed_statement_catalog,
                prompt_version=settings.ai_explanation_prompt_version,
                model_profile=settings.ai_explanation_model_profile,
                resolved_model=response.resolved_model,
                attempt_count=attempt,
            )
        except ExplanationValidationError:
            if attempt == 1:
                retried = True
                continue
            return _failure(
                AIExplanationStatus.INVALID_RESPONSE,
                "invalid_model_selection",
                settings,
                retry_attempted=retried,
            )
        return AIExplanationResult(status=AIExplanationStatus.OK, explanation=explanation)
    raise AssertionError("explanation retry loop exceeded its fixed bound")
