import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from product_api import gateway_client
from product_api.gateway_client import GatewayError
from shared.constants import (
    COMPANY_CARD_NARRATIVE_MODEL_PROFILE,
    COMPANY_CARD_NARRATIVE_OUTPUT_SCHEMA_NAME,
)
from shared.schemas import ChatMessage, ChatMetadata, ChatRequest


def _payload(dispatch_id):
    return ChatRequest(
        messages=[ChatMessage(role="user", content="{}")],
        model_profile=COMPANY_CARD_NARRATIVE_MODEL_PROFILE,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": COMPANY_CARD_NARRATIVE_OUTPUT_SCHEMA_NAME,
                "strict": True,
                "schema": {"type": "object"},
            },
        },
        timeout=20,
        max_output_tokens=600,
        gateway_dispatch_id=dispatch_id,
    )


class _Response:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_narrative_serializes_canonical_dispatch_id_signs_body_and_requires_echo(
    monkeypatch,
):
    dispatch_id = uuid4()
    observed = {}

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, *, content, headers):
            observed["body"] = json.loads(content)
            observed["headers"] = headers
            return _Response(
                {
                    "text": "{}",
                    "model_profile": COMPANY_CARD_NARRATIVE_MODEL_PROFILE,
                    "resolved_model": "gateway-model",
                    "gateway_dispatch_id": str(dispatch_id),
                }
            )

    monkeypatch.setattr(gateway_client.httpx, "AsyncClient", Client)
    settings = SimpleNamespace(
        gateway_url="http://gateway",
        gateway_shared_secret="test-secret",
        gateway_timeout_seconds=30,
    )
    response = await gateway_client.send_chat(settings, _payload(dispatch_id))
    assert response.gateway_dispatch_id == dispatch_id
    assert observed["body"]["gateway_dispatch_id"] == str(dispatch_id)
    assert observed["headers"]["X-Gateway-Dispatch-ID"] == str(dispatch_id)
    assert observed["headers"]["X-Body-SHA256"] == gateway_client._body_sha256(
        json.dumps(
            observed["body"], separators=(",", ":"), ensure_ascii=False
        ).encode()
    )


@pytest.mark.asyncio
async def test_narrative_gateway_echo_mismatch_is_terminal(monkeypatch):
    dispatch_id = uuid4()

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return _Response(
                {
                    "text": "{}",
                    "model_profile": COMPANY_CARD_NARRATIVE_MODEL_PROFILE,
                    "resolved_model": "gateway-model",
                    "gateway_dispatch_id": str(uuid4()),
                }
            )

    monkeypatch.setattr(gateway_client.httpx, "AsyncClient", Client)
    settings = SimpleNamespace(
        gateway_url="http://gateway",
        gateway_shared_secret="test-secret",
        gateway_timeout_seconds=30,
    )
    with pytest.raises(GatewayError, match="dispatch id mismatch") as raised:
        await gateway_client.send_chat(settings, _payload(dispatch_id))
    assert raised.value.code == "gateway_dispatch_id_mismatch"
    assert raised.value.retryable is False


@pytest.mark.asyncio
async def test_narrative_request_cap_is_checked_before_transport(monkeypatch):
    class UnexpectedClient:
        def __init__(self, **_kwargs):
            raise AssertionError("oversized narrative must not open transport")

    monkeypatch.setattr(gateway_client.httpx, "AsyncClient", UnexpectedClient)
    settings = SimpleNamespace(
        gateway_url="http://gateway",
        gateway_shared_secret="test-secret",
        gateway_timeout_seconds=30,
    )
    payload = ChatRequest(
        messages=[ChatMessage(role="user", content="x" * 32768)],
        model_profile=COMPANY_CARD_NARRATIVE_MODEL_PROFILE,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": COMPANY_CARD_NARRATIVE_OUTPUT_SCHEMA_NAME,
                "strict": True,
                "schema": {"type": "object"},
            },
        },
        timeout=20,
        max_output_tokens=600,
        gateway_dispatch_id=uuid4(),
    )

    with pytest.raises(GatewayError, match="request is too large") as raised:
        await gateway_client.send_chat(settings, payload)
    assert raised.value.code == "request_too_large"
    assert raised.value.is_transport_failure is False


@pytest.mark.asyncio
async def test_legacy_request_larger_than_narrative_cap_is_unchanged(monkeypatch):
    observed = {}

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, *, content, headers):
            observed["body"] = json.loads(content)
            observed["headers"] = headers
            return _Response({"text": "ok"})

    monkeypatch.setattr(gateway_client.httpx, "AsyncClient", Client)
    settings = SimpleNamespace(
        gateway_url="http://gateway",
        gateway_shared_secret="test-secret",
        gateway_timeout_seconds=30,
    )
    payload = ChatRequest(
        messages=[ChatMessage(role="user", content="x" * 40000)],
        model="gpt-5.2",
        metadata=ChatMetadata(
            company_id=1,
            user_id=2,
            conversation_id=3,
            message_id=4,
        ),
    )

    response = await gateway_client.send_chat(settings, payload)

    assert response.text == "ok"
    assert len(observed["body"]["messages"][0]["content"]) == 40000
    assert "gateway_dispatch_id" not in observed["body"]
    assert "X-Gateway-Dispatch-ID" not in observed["headers"]


@pytest.mark.asyncio
async def test_narrative_gateway_rejects_noncanonical_dispatch_echo(monkeypatch):
    dispatch_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return _Response(
                {
                    "text": "{}",
                    "model_profile": COMPANY_CARD_NARRATIVE_MODEL_PROFILE,
                    "resolved_model": "gateway-model",
                    "gateway_dispatch_id": str(dispatch_id).upper(),
                }
            )

    monkeypatch.setattr(gateway_client.httpx, "AsyncClient", Client)
    settings = SimpleNamespace(
        gateway_url="http://gateway",
        gateway_shared_secret="test-secret",
        gateway_timeout_seconds=30,
    )
    with pytest.raises(GatewayError, match="response contract failure"):
        await gateway_client.send_chat(settings, _payload(dispatch_id))
