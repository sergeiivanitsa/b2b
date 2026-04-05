import pytest

from product_api.claims import gateway_adapter
from product_api.settings import get_settings
from shared.constants import MODEL_GPT_5_2
from shared.schemas import ChatMessage, ChatResponse

pytestmark = pytest.mark.asyncio


async def test_request_claim_extraction_uses_chat_contract(monkeypatch):
    captured = {}

    async def fake_send_chat(_settings, payload):
        captured["payload"] = payload
        return ChatResponse(text='{"case_type":"supply"}')

    monkeypatch.setattr(gateway_adapter, "send_chat", fake_send_chat)

    response_text = await gateway_adapter.request_claim_extraction(
        get_settings(),
        claim_id=77,
        messages=[
            ChatMessage(role="system", content="system"),
            ChatMessage(role="user", content="user"),
        ],
    )

    assert response_text == '{"case_type":"supply"}'
    payload = captured["payload"]
    assert payload.model == MODEL_GPT_5_2
    assert payload.stream is False
    assert payload.metadata.company_id == 77
    assert payload.metadata.user_id == 77
    assert payload.metadata.conversation_id == 77
    assert payload.metadata.message_id == 77
