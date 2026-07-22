import json

import pytest
import httpx

from product_api import settings as settings_module
from product_api.company_reports.explanation import AIExplanationStatus, explain_scoring_result
from product_api.company_reports.explanation.validation import build_input_envelope
from product_api.company_reports.scoring import score_signals
from product_api.company_reports.signals import evaluate_signals
from product_api.gateway_client import GatewayError
from product_api import gateway_client
from shared.schemas import ChatMessage, ChatMetadata, ChatRequest, ChatResponse

from company_report_signal_test_helpers import complete_company_report


def _inputs():
    report = complete_company_report()
    signals = evaluate_signals(report)
    return report, signals, score_signals(signals)


def _settings():
    return settings_module.get_settings().model_copy(update={"ai_explanation_enabled": True})


def _selection(report, signals, scoring):
    catalog = build_input_envelope(report, signals, scoring).allowed_statement_catalog
    return json.dumps({
        "output_schema_version": "1",
        "overall_conclusion_id": catalog.overall_conclusions[0].id,
        "recovery_factor_ids": [item.id for item in catalog.recovery_factors[:3]],
        "key_risk_ids": [item.id for item in catalog.key_risks[:3]],
        "urgency_id": catalog.urgencies[0].id,
        "recommended_next_step_id": catalog.recommended_next_steps[0].id,
        "limitation_ids": [item.id for item in catalog.limitations[:5]],
    })


@pytest.mark.asyncio
async def test_service_builds_structured_payload_and_succeeds(monkeypatch):
    report, signals, scoring = _inputs()
    seen = []

    async def fake_send(_settings, payload):
        seen.append(payload)
        return ChatResponse(
            text=_selection(report, signals, scoring),
            model_profile="economy_text_structured_v1",
            resolved_model="gpt-5.2",
        )

    monkeypatch.setattr("product_api.company_reports.explanation.service.send_chat", fake_send)
    result = await explain_scoring_result(_settings(), report, signals, scoring)
    assert result.status is AIExplanationStatus.OK
    assert seen[0].model is None and seen[0].metadata is None
    assert seen[0].timeout == 20 and seen[0].stream is False


@pytest.mark.asyncio
async def test_service_retries_only_safe_transport_or_invalid_output(monkeypatch):
    report, signals, scoring = _inputs()
    calls = 0

    async def fake_send(_settings, _payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            return ChatResponse(text="not-json", model_profile="economy_text_structured_v1", resolved_model="gpt-5.2")
        return ChatResponse(text=_selection(report, signals, scoring), model_profile="economy_text_structured_v1", resolved_model="gpt-5.2")

    monkeypatch.setattr("product_api.company_reports.explanation.service.send_chat", fake_send)
    result = await explain_scoring_result(_settings(), report, signals, scoring)
    assert result.status is AIExplanationStatus.OK and result.explanation.attempt_count == 2
    assert calls == 2

    async def fail_send(_settings, _payload):
        raise GatewayError("auth", retryable=False)

    monkeypatch.setattr("product_api.company_reports.explanation.service.send_chat", fail_send)
    result = await explain_scoring_result(_settings(), report, signals, scoring)
    assert result.status is AIExplanationStatus.TRANSPORT_FAILURE
    assert result.failure.retry_attempted is False


@pytest.mark.asyncio
async def test_service_never_retries_gateway_http_errors_but_retries_local_transport(monkeypatch):
    report, signals, scoring = _inputs()
    calls = 0

    async def rate_limited(_settings, _payload):
        nonlocal calls
        calls += 1
        raise GatewayError("rate limit", status_code=429, retryable=True)

    monkeypatch.setattr("product_api.company_reports.explanation.service.send_chat", rate_limited)
    result = await explain_scoring_result(_settings(), report, signals, scoring)
    assert result.status is AIExplanationStatus.TRANSPORT_FAILURE
    assert result.failure.retry_attempted is False
    assert calls == 1

    async def local_transport_then_success(_settings, _payload):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise GatewayError("network", retryable=True, is_transport_failure=True)
        return ChatResponse(
            text=_selection(report, signals, scoring),
            model_profile="economy_text_structured_v1",
            resolved_model="gpt-5.2",
        )

    monkeypatch.setattr(
        "product_api.company_reports.explanation.service.send_chat", local_transport_then_success
    )
    result = await explain_scoring_result(_settings(), report, signals, scoring)
    assert result.status is AIExplanationStatus.OK
    assert result.explanation.attempt_count == 2
    assert calls == 3


@pytest.mark.asyncio
async def test_inconsistent_input_is_local_configuration_error_without_gateway_call(monkeypatch):
    report, signals, scoring = _inputs()
    calls = 0

    async def unexpected_gateway(_settings, _payload):
        nonlocal calls
        calls += 1
        raise AssertionError("gateway must not be called")

    monkeypatch.setattr("product_api.company_reports.explanation.service.send_chat", unexpected_gateway)
    result = await explain_scoring_result(
        _settings(), report, signals, scoring.model_copy(update={"reasons": []})
    )
    assert result.status is AIExplanationStatus.CONFIGURATION_ERROR
    assert result.failure.safe_code == "invalid_local_explanation_input"
    assert calls == 0


@pytest.mark.asyncio
async def test_service_rejects_audit_mismatch_without_retry(monkeypatch):
    report, signals, scoring = _inputs()
    calls = 0

    async def fake_send(_settings, _payload):
        nonlocal calls
        calls += 1
        return ChatResponse(text="{}", model_profile="wrong", resolved_model="gpt-5.2")

    monkeypatch.setattr("product_api.company_reports.explanation.service.send_chat", fake_send)
    result = await explain_scoring_result(_settings(), report, signals, scoring)
    assert result.status is AIExplanationStatus.CONFIGURATION_ERROR
    assert result.failure.safe_code == "gateway_contract_mismatch"
    assert calls == 1


@pytest.mark.asyncio
async def test_gateway_client_uses_payload_timeout_then_legacy_fallback(monkeypatch):
    timeouts = []

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"text": "ok"}

    class Client:
        def __init__(self, *, timeout):
            timeouts.append(timeout)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(gateway_client.httpx, "AsyncClient", Client)
    settings = _settings()
    payload = ChatRequest(
        messages=[ChatMessage(role="user", content="legacy")],
        model="gpt-5.2",
        metadata=ChatMetadata(company_id=1, user_id=1, conversation_id=1, message_id=1),
        timeout=None,
    )
    await gateway_client.send_chat(settings, payload)
    payload = payload.model_copy(update={"timeout": 7})
    await gateway_client.send_chat(settings, payload)
    assert timeouts == [settings.gateway_timeout_seconds, 7]


@pytest.mark.asyncio
async def test_gateway_client_marks_only_local_httpx_failure_as_transport(monkeypatch):
    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            raise httpx.ConnectError("offline", request=httpx.Request("POST", "http://gateway"))

    monkeypatch.setattr(gateway_client.httpx, "AsyncClient", Client)
    payload = ChatRequest(
        messages=[ChatMessage(role="user", content="legacy")],
        model="gpt-5.2",
        metadata=ChatMetadata(company_id=1, user_id=1, conversation_id=1, message_id=1),
    )
    with pytest.raises(GatewayError) as raised:
        await gateway_client.send_chat(_settings(), payload)
    assert raised.value.is_transport_failure is True
