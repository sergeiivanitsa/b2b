import json

import gateway_api.main as gateway_main
from gateway_api.openai_client import OpenAIError

from .utils import sign_headers


def _chat_body():
    return {
        "messages": [{"role": "user", "content": "hi"}],
        "model": "gpt-5.2",
        "stream": False,
        "metadata": {
            "company_id": 1,
            "user_id": 1,
            "conversation_id": 1,
            "message_id": 1,
        },
    }


def test_contract_non_stream(client, monkeypatch):
    async def fake_create_chat(_settings, _model, _messages, _timeout):
        return ("ok", {"total_tokens": 1})

    monkeypatch.setattr(gateway_main, "create_chat_completion", fake_create_chat)

    body = _chat_body()
    raw = json.dumps(body, separators=(",", ":")).encode()
    headers = sign_headers("test-shared-secret", "POST", "/v1/chat", raw)
    headers["Content-Type"] = "application/json"

    resp = client.post("/v1/chat", headers=headers, data=raw)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["text"] == "ok"
    assert payload["usage"]["total_tokens"] == 1


def test_contract_error_normalization(client, monkeypatch):
    async def fake_create_chat(_settings, _model, _messages, _timeout):
        raise OpenAIError(
            status_code=429,
            message="rate limit",
            code="rate_limit",
            retryable=True,
            err_type="rate_limit_error",
        )

    monkeypatch.setattr(gateway_main, "create_chat_completion", fake_create_chat)

    body = _chat_body()
    raw = json.dumps(body, separators=(",", ":")).encode()
    headers = sign_headers("test-shared-secret", "POST", "/v1/chat", raw)
    headers["Content-Type"] = "application/json"

    resp = client.post("/v1/chat", headers=headers, data=raw)
    assert resp.status_code == 429
    payload = resp.json()
    assert payload["error"]["code"] == "rate_limit"
    assert payload["error"]["type"] == "rate_limit_error"
    assert payload["error"]["retryable"] is True
