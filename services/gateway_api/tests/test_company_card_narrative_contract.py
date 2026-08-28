import json
import uuid

import pytest
from pydantic import ValidationError

from gateway_api import main as gateway_main
from gateway_api.openai_client import OpenAIError, create_chat_completion
from gateway_api.settings import Settings
from shared.constants import COMPANY_CARD_NARRATIVE_MODEL_PROFILE, COMPANY_CARD_NARRATIVE_OUTPUT_SCHEMA_NAME
from tests.utils import sign_headers


def _body(dispatch_id: str):
    return {"messages": [{"role": "user", "content": "{}"}], "stream": False, "timeout": 20, "model_profile": COMPANY_CARD_NARRATIVE_MODEL_PROFILE, "max_output_tokens": 600, "gateway_dispatch_id": dispatch_id, "response_format": {"type": "json_schema", "json_schema": {"name": COMPANY_CARD_NARRATIVE_OUTPUT_SCHEMA_NAME, "strict": True, "schema": {"type": "object"}}}}


def test_narrative_is_closed_before_openai_when_disabled(client, monkeypatch):
    dispatch = str(uuid.uuid4())
    body = _body(dispatch)
    raw = json.dumps(body, separators=(",", ":")).encode()
    headers = sign_headers(gateway_main.settings.gateway_shared_secret, "POST", "/v1/chat", raw)
    headers.update({"Content-Type": "application/json", "X-Gateway-Dispatch-ID": dispatch})
    monkeypatch.setattr(gateway_main.settings, "company_card_narrative_gateway_enabled", False)
    response = client.post("/v1/chat", content=raw, headers=headers)
    assert response.status_code == 503


def test_enabled_narrative_forwards_exact_profile_options_and_dispatch_id(client, monkeypatch):
    dispatch = str(uuid.uuid4())
    body = _body(dispatch)
    raw = json.dumps(body, separators=(",", ":")).encode()
    headers = sign_headers(gateway_main.settings.gateway_shared_secret, "POST", "/v1/chat", raw)
    headers["Content-Type"] = "application/json"
    headers["X-Gateway-Dispatch-ID"] = dispatch
    received = {}

    async def fake_create(settings, model, messages, timeout, **kwargs):
        received.update(model=model, messages=messages, timeout=timeout, **kwargs)
        return ("{}", {"total_tokens": 1})

    monkeypatch.setattr(gateway_main.settings, "company_card_narrative_gateway_enabled", True)
    monkeypatch.setattr(gateway_main.settings, "company_card_narrative_model", "narrative-test-model")
    monkeypatch.setattr(gateway_main, "create_chat_completion", fake_create)

    response = client.post("/v1/chat", data=raw, headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "text": "{}",
        "usage": {"total_tokens": 1},
        "raw": None,
        "model_profile": COMPANY_CARD_NARRATIVE_MODEL_PROFILE,
        "resolved_model": "narrative-test-model",
        "gateway_dispatch_id": dispatch,
    }
    assert received["model"] == "narrative-test-model"
    assert received["timeout"] == 20
    assert received["max_output_tokens"] == 600
    assert received["response_format"]["json_schema"]["name"] == COMPANY_CARD_NARRATIVE_OUTPUT_SCHEMA_NAME


def test_narrative_rejects_header_dispatch_mismatch_before_openai(client, monkeypatch):
    body_dispatch, header_dispatch = str(uuid.uuid4()), str(uuid.uuid4())
    body = _body(body_dispatch)
    raw = json.dumps(body, separators=(",", ":")).encode()
    headers = sign_headers(gateway_main.settings.gateway_shared_secret, "POST", "/v1/chat", raw)
    headers["Content-Type"] = "application/json"
    headers["X-Gateway-Dispatch-ID"] = header_dispatch

    async def unexpected_call(*_args, **_kwargs):
        raise AssertionError("narrative mismatch must not call OpenAI")

    monkeypatch.setattr(gateway_main.settings, "company_card_narrative_gateway_enabled", True)
    monkeypatch.setattr(gateway_main.settings, "company_card_narrative_model", "narrative-test-model")
    monkeypatch.setattr(gateway_main, "create_chat_completion", unexpected_call)

    response = client.post("/v1/chat", data=raw, headers=headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "narrative dispatch id mismatch"


def test_narrative_rejects_non_narrative_schema_before_openai(client, monkeypatch):
    dispatch = str(uuid.uuid4())
    body = _body(dispatch)
    body["response_format"]["json_schema"]["name"] = "other_schema"
    raw = json.dumps(body, separators=(",", ":")).encode()
    headers = sign_headers(gateway_main.settings.gateway_shared_secret, "POST", "/v1/chat", raw)
    headers["Content-Type"] = "application/json"
    headers["X-Gateway-Dispatch-ID"] = dispatch

    async def unexpected_call(*_args, **_kwargs):
        raise AssertionError("unsupported narrative schema must not call OpenAI")

    monkeypatch.setattr(gateway_main.settings, "company_card_narrative_gateway_enabled", True)
    monkeypatch.setattr(gateway_main.settings, "company_card_narrative_model", "narrative-test-model")
    monkeypatch.setattr(gateway_main, "create_chat_completion", unexpected_call)

    response = client.post("/v1/chat", data=raw, headers=headers)

    assert response.status_code == 422


@pytest.mark.parametrize(("timeout", "tokens"), [(1, 1), (20, 600)])
def test_narrative_option_boundaries_reach_openai(client, monkeypatch, timeout, tokens):
    dispatch = str(uuid.uuid4())
    body = _body(dispatch)
    body["timeout"], body["max_output_tokens"] = timeout, tokens
    raw = json.dumps(body, separators=(",", ":")).encode()
    headers = sign_headers(gateway_main.settings.gateway_shared_secret, "POST", "/v1/chat", raw)
    headers.update({"Content-Type": "application/json", "X-Gateway-Dispatch-ID": dispatch})
    received = {}

    async def fake_create(*_args, **kwargs):
        received.update(kwargs)
        return ("{}", None)

    monkeypatch.setattr(gateway_main.settings, "company_card_narrative_gateway_enabled", True)
    monkeypatch.setattr(gateway_main.settings, "company_card_narrative_model", "narrative-test-model")
    monkeypatch.setattr(gateway_main, "create_chat_completion", fake_create)
    assert client.post("/v1/chat", data=raw, headers=headers).status_code == 200
    assert received["max_output_tokens"] == tokens


@pytest.mark.parametrize(("field", "value"), [("timeout", 21), ("max_output_tokens", 601)])
def test_narrative_rejects_out_of_bound_options_before_openai(client, monkeypatch, field, value):
    dispatch = str(uuid.uuid4())
    body = _body(dispatch)
    body[field] = value
    raw = json.dumps(body, separators=(",", ":")).encode()
    headers = sign_headers(gateway_main.settings.gateway_shared_secret, "POST", "/v1/chat", raw)
    headers.update({"Content-Type": "application/json", "X-Gateway-Dispatch-ID": dispatch})

    async def unexpected_call(*_args, **_kwargs):
        raise AssertionError("invalid narrative request must not call OpenAI")

    monkeypatch.setattr(gateway_main.settings, "company_card_narrative_gateway_enabled", True)
    monkeypatch.setattr(gateway_main.settings, "company_card_narrative_model", "narrative-test-model")
    monkeypatch.setattr(gateway_main, "create_chat_completion", unexpected_call)
    assert client.post("/v1/chat", data=raw, headers=headers).status_code == 422


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("timeout", "20"),
        ("timeout", 20.0),
        ("timeout", True),
        ("max_output_tokens", "600"),
        ("max_output_tokens", 600.0),
        ("max_output_tokens", True),
    ],
)
def test_narrative_rejects_noninteger_wire_limits_before_openai(
    client, monkeypatch, field, value
):
    dispatch = str(uuid.uuid4())
    body = _body(dispatch)
    body[field] = value
    raw = json.dumps(body, separators=(",", ":")).encode()
    headers = sign_headers(
        gateway_main.settings.gateway_shared_secret, "POST", "/v1/chat", raw
    )
    headers.update(
        {"Content-Type": "application/json", "X-Gateway-Dispatch-ID": dispatch}
    )

    async def unexpected_call(*_args, **_kwargs):
        raise AssertionError("noninteger narrative limits must not call OpenAI")

    monkeypatch.setattr(
        gateway_main.settings, "company_card_narrative_gateway_enabled", True
    )
    monkeypatch.setattr(
        gateway_main.settings, "company_card_narrative_model", "narrative-test-model"
    )
    monkeypatch.setattr(gateway_main, "create_chat_completion", unexpected_call)
    assert client.post("/v1/chat", data=raw, headers=headers).status_code == 422


@pytest.mark.parametrize(("size", "status"), [(16384, 200), (16385, 502)])
def test_narrative_response_byte_cap(client, monkeypatch, size, status):
    dispatch = str(uuid.uuid4())
    body = _body(dispatch)
    raw = json.dumps(body, separators=(",", ":")).encode()
    headers = sign_headers(gateway_main.settings.gateway_shared_secret, "POST", "/v1/chat", raw)
    headers.update({"Content-Type": "application/json", "X-Gateway-Dispatch-ID": dispatch})

    async def fake_create(*_args, **_kwargs):
        return ("x" * size, None)

    monkeypatch.setattr(gateway_main.settings, "company_card_narrative_gateway_enabled", True)
    monkeypatch.setattr(gateway_main.settings, "company_card_narrative_model", "narrative-test-model")
    monkeypatch.setattr(gateway_main, "create_chat_completion", fake_create)
    assert client.post("/v1/chat", data=raw, headers=headers).status_code == status


@pytest.mark.parametrize(("size", "status"), [(32768, 200), (32769, 413)])
def test_narrative_request_byte_cap(client, monkeypatch, size, status):
    dispatch = str(uuid.uuid4())
    body = _body(dispatch)
    body["messages"][0]["content"] = ""
    base = json.dumps(body, separators=(",", ":")).encode()
    body["messages"][0]["content"] = "x" * (size - len(base))
    raw = json.dumps(body, separators=(",", ":")).encode()
    assert len(raw) == size
    headers = sign_headers(gateway_main.settings.gateway_shared_secret, "POST", "/v1/chat", raw)
    headers.update({"Content-Type": "application/json", "X-Gateway-Dispatch-ID": dispatch})

    async def fake_create(*_args, **_kwargs):
        return ("{}", None)

    monkeypatch.setattr(gateway_main.settings, "company_card_narrative_gateway_enabled", True)
    monkeypatch.setattr(gateway_main.settings, "company_card_narrative_model", "narrative-test-model")
    monkeypatch.setattr(gateway_main, "create_chat_completion", fake_create)
    assert client.post("/v1/chat", data=raw, headers=headers).status_code == status


def test_enabled_gateway_rejects_blank_narrative_model():
    with pytest.raises(ValidationError, match="requires a model"):
        Settings(GATEWAY_SHARED_SECRET="test", COMPANY_CARD_NARRATIVE_GATEWAY_ENABLED=True, COMPANY_CARD_NARRATIVE_MODEL="   ")


def test_disabled_gateway_normalizes_blank_narrative_model_to_unset():
    settings = Settings(
        GATEWAY_SHARED_SECRET="test",
        COMPANY_CARD_NARRATIVE_GATEWAY_ENABLED=False,
        COMPANY_CARD_NARRATIVE_MODEL="   ",
    )
    assert settings.company_card_narrative_model is None


@pytest.mark.asyncio
async def test_paid_boundary_rejects_unset_model_before_network():
    settings = Settings(
        GATEWAY_SHARED_SECRET="test",
        OPENAI_API_KEY="not-used",
    )
    with pytest.raises(OpenAIError) as caught:
        await create_chat_completion(settings, None, [])
    assert caught.value.code == "missing_model"


def test_narrative_dispatch_id_must_be_lowercase_canonical_uuid(client):
    dispatch = "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"
    body = _body(dispatch)
    raw = json.dumps(body, separators=(",", ":")).encode()
    headers = sign_headers(gateway_main.settings.gateway_shared_secret, "POST", "/v1/chat", raw)
    headers.update({"Content-Type": "application/json", "X-Gateway-Dispatch-ID": dispatch})
    assert client.post("/v1/chat", data=raw, headers=headers).status_code == 422
