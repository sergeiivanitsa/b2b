import json

import gateway_api.main as gateway_main

from .utils import sign_headers


def _structured_body():
    return {
        "messages": [
            {"role": "system", "content": "select ids"},
            {"role": "user", "content": "{}"},
        ],
        "model": None,
        "model_profile": "economy_text_structured_v1",
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "company_recovery_explanation_v1",
                "strict": True,
                "schema": {"type": "object", "additionalProperties": False},
            },
        },
        "max_output_tokens": 600,
        "stream": False,
        "timeout": 20,
        "metadata": None,
    }


def _signed_headers(body):
    raw = json.dumps(body, separators=(",", ":")).encode()
    headers = sign_headers("test-shared-secret", "POST", "/v1/chat", raw)
    headers["Content-Type"] = "application/json"
    return raw, headers


def test_signed_structured_request_resolves_profile_and_forwards_options(client, monkeypatch):
    received = {}

    async def fake_create(settings, model, messages, timeout, **kwargs):
        received.update(
            settings=settings,
            model=model,
            messages=messages,
            timeout=timeout,
            **kwargs,
        )
        return ("{}", {"total_tokens": 1})

    monkeypatch.setattr(gateway_main, "create_chat_completion", fake_create)
    body = _structured_body()
    raw, headers = _signed_headers(body)

    response = client.post("/v1/chat", headers=headers, data=raw)
    assert response.status_code == 200
    assert response.json() == {
        "text": "{}",
        "usage": {"total_tokens": 1},
        "raw": None,
        "model_profile": "economy_text_structured_v1",
        "resolved_model": "gpt-5.2",
    }
    assert received["model"] == "gpt-5.2"
    assert received["timeout"] == 20
    assert received["max_output_tokens"] == 600
    assert received["response_format"]["json_schema"]["schema"] == body["response_format"]["json_schema"]["schema"]


def test_structured_hybrid_and_unsigned_payloads_are_rejected(client):
    body = _structured_body()
    body["model"] = "gpt-5.2"
    raw, headers = _signed_headers(body)
    assert client.post("/v1/chat", headers=headers, data=raw).status_code == 422

    body = _structured_body()
    unsigned = client.post("/v1/chat", json=body)
    assert unsigned.status_code == 401


def test_structured_logging_does_not_include_metadata_values(client, monkeypatch, caplog):
    async def fake_create(*_args, **_kwargs):
        return ("{}", None)

    monkeypatch.setattr(gateway_main, "create_chat_completion", fake_create)
    body = _structured_body()
    raw, headers = _signed_headers(body)
    with caplog.at_level("INFO"):
        response = client.post("/v1/chat", headers=headers, data=raw)
    assert response.status_code == 200
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "model_profile=economy_text_structured_v1" in messages
    for field in ("company_id", "user_id", "conversation_id", "message_id"):
        assert field not in messages
