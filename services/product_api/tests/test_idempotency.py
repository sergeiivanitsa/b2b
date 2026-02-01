import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.schemas import ChatResponse

import product_api.main as product_main
from product_api.models import Ledger
from product_api.settings import get_settings

from .utils import add_credits, create_company, create_session_cookie, create_user

pytestmark = pytest.mark.asyncio


async def test_chat_idempotent_ledger(async_client, engine, monkeypatch):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(session, "IdemCo")
        user = await create_user(session, "user@idem.test", "user", company.id)
        await add_credits(session, company.id, 2, reason="seed")
        cookie = await create_session_cookie(session, user.id)

    async def fake_send_chat(_settings, _payload):
        return ChatResponse(text="ok", usage=None)

    monkeypatch.setattr(product_main, "send_chat", fake_send_chat)

    cookies = {settings.session_cookie_name: cookie}
    client_message_id = "idem-1"

    resp = await async_client.post(
        "/v1/chat",
        json={"client_message_id": client_message_id, "content": "hi"},
        cookies=cookies,
    )
    assert resp.status_code == 200
    data = resp.json()
    user_message_id = data["user_message_id"]

    count_stmt = select(func.count()).select_from(Ledger).where(
        Ledger.message_id == user_message_id
    )
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        count1 = (await session.execute(count_stmt)).scalar_one()

    resp2 = await async_client.post(
        "/v1/chat",
        json={
            "conversation_id": data["conversation_id"],
            "client_message_id": client_message_id,
            "content": "hi",
        },
        cookies=cookies,
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["user_message_id"] == user_message_id

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        count2 = (await session.execute(count_stmt)).scalar_one()
    assert count1 == 1
    assert count2 == 1
