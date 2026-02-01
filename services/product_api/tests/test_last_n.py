import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.schemas import ChatResponse

import product_api.main as product_main
from product_api.settings import get_settings

from .utils import (
    add_credits,
    add_message,
    create_company,
    create_conversation,
    create_session_cookie,
    create_user,
    utc_at,
)

pytestmark = pytest.mark.asyncio


async def test_last_n_trimming(async_client, engine, monkeypatch):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(session, "TrimCo")
        user = await create_user(session, "user@trim.test", "user", company.id)
        await add_credits(session, company.id, 5, reason="seed")
        cookie = await create_session_cookie(session, user.id)
        conversation = await create_conversation(session, company.id, user.id)

        await add_message(session, conversation.id, "user", "m1", created_at=utc_at(-10))
        await add_message(session, conversation.id, "user", "m2", created_at=utc_at(-9))
        await add_message(session, conversation.id, "user", "m3", created_at=utc_at(-8))
        await add_message(session, conversation.id, "user", "m4", created_at=utc_at(-7))
        await add_message(session, conversation.id, "user", "m5", created_at=utc_at(-6))

    monkeypatch.setattr(product_main.settings, "chat_context_limit", 3)
    captured = {}

    async def fake_send_chat(_settings, request_payload):
        captured["messages"] = [m.content for m in request_payload.messages]
        return ChatResponse(text="ok", usage=None)

    monkeypatch.setattr(product_main, "send_chat", fake_send_chat)

    cookies = {settings.session_cookie_name: cookie}
    resp = await async_client.post(
        "/v1/chat",
        json={
            "conversation_id": conversation.id,
            "client_message_id": "trim-1",
            "content": "m6",
        },
        cookies=cookies,
    )
    assert resp.status_code == 200
    assert captured["messages"] == ["m4", "m5", "m6"]
