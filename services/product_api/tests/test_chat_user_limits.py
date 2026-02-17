import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.schemas import ChatResponse

import product_api.main as product_main
from product_api.models import Ledger, UserCreditLimit
from product_api.settings import get_settings

from .utils import add_credits, create_company, create_session_cookie, create_user

pytestmark = pytest.mark.asyncio


async def test_chat_debits_pool_and_user_limit(async_client, engine, monkeypatch):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(session, "ChatLimitCo")
        user = await create_user(session, "user@chat-limit.test", "member", company.id)
        await add_credits(session, company.id, 2, reason="seed")
        session.add(
            UserCreditLimit(
                company_id=company.id,
                user_id=user.id,
                remaining_credits=2,
            )
        )
        await session.commit()
        cookie = await create_session_cookie(session, user.id)

    async def fake_send_chat(_settings, _payload):
        return ChatResponse(text="ok", usage=None)

    monkeypatch.setattr(product_main, "send_chat", fake_send_chat)

    resp = await async_client.post(
        "/v1/chat",
        json={"client_message_id": "chat-limit-1", "content": "hello"},
        cookies={settings.session_cookie_name: cookie},
    )
    assert resp.status_code == 200

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        pool_balance = (
            await session.execute(
                select(func.coalesce(func.sum(Ledger.delta), 0)).where(
                    Ledger.company_id == company.id
                )
            )
        ).scalar_one()
        assert int(pool_balance) == 1

        user_limit = (
            await session.execute(
                select(UserCreditLimit).where(UserCreditLimit.user_id == user.id)
            )
        ).scalar_one()
        assert user_limit.remaining_credits == 1

        chat_ledger_count = (
            await session.execute(
                select(func.count())
                .select_from(Ledger)
                .where(
                    Ledger.company_id == company.id,
                    Ledger.user_id == user.id,
                    Ledger.reason == "chat_message",
                )
            )
        ).scalar_one()
        assert int(chat_ledger_count) == 1


async def test_chat_rejects_when_company_pool_insufficient(async_client, engine, monkeypatch):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(session, "NoPoolCo")
        user = await create_user(session, "user@nopool.test", "member", company.id)
        session.add(
            UserCreditLimit(
                company_id=company.id,
                user_id=user.id,
                remaining_credits=3,
            )
        )
        await session.commit()
        cookie = await create_session_cookie(session, user.id)

    async def fake_send_chat(_settings, _payload):
        return ChatResponse(text="ok", usage=None)

    monkeypatch.setattr(product_main, "send_chat", fake_send_chat)

    resp = await async_client.post(
        "/v1/chat",
        json={"client_message_id": "no-pool-1", "content": "hello"},
        cookies={settings.session_cookie_name: cookie},
    )
    assert resp.status_code == 402
    assert resp.json()["detail"]["code"] == "insufficient_company_credits"

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        user_limit = (
            await session.execute(
                select(UserCreditLimit).where(UserCreditLimit.user_id == user.id)
            )
        ).scalar_one()
        assert user_limit.remaining_credits == 3

        chat_ledger_count = (
            await session.execute(
                select(func.count())
                .select_from(Ledger)
                .where(
                    Ledger.company_id == company.id,
                    Ledger.reason == "chat_message",
                )
            )
        ).scalar_one()
        assert int(chat_ledger_count) == 0


async def test_chat_rejects_when_user_limit_insufficient(async_client, engine, monkeypatch):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(session, "NoUserLimitCo")
        user = await create_user(session, "user@nolimit.test", "member", company.id)
        await add_credits(session, company.id, 2, reason="seed")
        session.add(
            UserCreditLimit(
                company_id=company.id,
                user_id=user.id,
                remaining_credits=0,
            )
        )
        await session.commit()
        cookie = await create_session_cookie(session, user.id)

    async def fake_send_chat(_settings, _payload):
        return ChatResponse(text="ok", usage=None)

    monkeypatch.setattr(product_main, "send_chat", fake_send_chat)

    resp = await async_client.post(
        "/v1/chat",
        json={"client_message_id": "no-user-limit-1", "content": "hello"},
        cookies={settings.session_cookie_name: cookie},
    )
    assert resp.status_code == 402
    assert resp.json()["detail"]["code"] == "insufficient_user_credits"

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        pool_balance = (
            await session.execute(
                select(func.coalesce(func.sum(Ledger.delta), 0)).where(
                    Ledger.company_id == company.id
                )
            )
        ).scalar_one()
        assert int(pool_balance) == 2


async def test_chat_rejects_when_user_limit_row_missing(async_client, engine, monkeypatch):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(session, "MissingUserLimitRowCo")
        user = await create_user(session, "user@missing-limit.test", "member", company.id)
        await add_credits(session, company.id, 2, reason="seed")
        cookie = await create_session_cookie(session, user.id)

    async def fake_send_chat(_settings, _payload):
        return ChatResponse(text="ok", usage=None)

    monkeypatch.setattr(product_main, "send_chat", fake_send_chat)

    resp = await async_client.post(
        "/v1/chat",
        json={"client_message_id": "missing-user-limit-1", "content": "hello"},
        cookies={settings.session_cookie_name: cookie},
    )
    assert resp.status_code == 402
    assert resp.json()["detail"]["code"] == "insufficient_user_credits"

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        pool_balance = (
            await session.execute(
                select(func.coalesce(func.sum(Ledger.delta), 0)).where(
                    Ledger.company_id == company.id
                )
            )
        ).scalar_one()
        assert int(pool_balance) == 2
