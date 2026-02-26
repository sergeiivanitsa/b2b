import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.models import Ledger, UserCreditLimit
from product_api.settings import get_settings

from .utils import create_company, create_session_cookie, create_user

pytestmark = pytest.mark.asyncio

OLD_WHOAMI_KEYS = {"id", "email", "role", "org_id", "company_id", "is_superadmin", "is_active"}
NEW_WHOAMI_KEYS = {
    "first_name",
    "last_name",
    "company_name",
    "remaining_credits",
    "company_pool_balance",
    "company_allocated_total",
    "company_unallocated_balance",
    "effective_credits",
}


async def _get_whoami(async_client, cookie: str):
    settings = get_settings()
    return await async_client.get(
        "/internal/whoami",
        cookies={settings.session_cookie_name: cookie},
    )


def _assert_whoami_contract(payload: dict):
    assert OLD_WHOAMI_KEYS <= set(payload.keys())
    assert NEW_WHOAMI_KEYS <= set(payload.keys())


async def test_whoami_profile_with_name_company_and_limit(async_client, engine):
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(session, "Whoami Rich Profile Co")
        user = await create_user(session, "named@whoami.test", "member", company.id)
        user.first_name = "Ivan"
        user.last_name = "Ivanov"
        session.add(
            Ledger(
                company_id=company.id,
                user_id=None,
                message_id=None,
                delta=100,
                reason="whoami_test_topup",
                idempotency_key="whoami-rich-topup",
            )
        )
        session.add(UserCreditLimit(company_id=company.id, user_id=user.id, remaining_credits=37))
        await session.commit()
        cookie = await create_session_cookie(session, user.id)

    response = await _get_whoami(async_client, cookie)
    assert response.status_code == 200
    payload = response.json()
    _assert_whoami_contract(payload)
    assert payload["email"] == "named@whoami.test"
    assert payload["first_name"] == "Ivan"
    assert payload["last_name"] == "Ivanov"
    assert payload["org_id"] == company.id
    assert payload["company_id"] == company.id
    assert payload["company_name"] == "Whoami Rich Profile Co"
    assert payload["remaining_credits"] == 37
    assert payload["company_pool_balance"] == 100
    assert payload["company_allocated_total"] == 37
    assert payload["company_unallocated_balance"] == 63
    assert payload["effective_credits"] == 37


async def test_whoami_profile_without_name_returns_null_names(async_client, engine):
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(session, "Whoami No Name Co")
        user = await create_user(session, "noname@whoami.test", "member", company.id)
        session.add(
            Ledger(
                company_id=company.id,
                user_id=None,
                message_id=None,
                delta=50,
                reason="whoami_test_topup",
                idempotency_key="whoami-noname-topup",
            )
        )
        session.add(UserCreditLimit(company_id=company.id, user_id=user.id, remaining_credits=11))
        await session.commit()
        cookie = await create_session_cookie(session, user.id)

    response = await _get_whoami(async_client, cookie)
    assert response.status_code == 200
    payload = response.json()
    _assert_whoami_contract(payload)
    assert payload["first_name"] is None
    assert payload["last_name"] is None
    assert payload["company_name"] == "Whoami No Name Co"
    assert payload["remaining_credits"] == 11
    assert payload["company_pool_balance"] == 50
    assert payload["company_allocated_total"] == 11
    assert payload["company_unallocated_balance"] == 39
    assert payload["effective_credits"] == 11


async def test_whoami_profile_without_limit_returns_zero_remaining_credits(async_client, engine):
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(session, "Whoami No Limit Co")
        user = await create_user(session, "nolimit@whoami.test", "member", company.id)
        user.first_name = "NoLimit"
        user.last_name = "User"
        session.add(
            Ledger(
                company_id=company.id,
                user_id=None,
                message_id=None,
                delta=120,
                reason="whoami_test_topup",
                idempotency_key="whoami-nolimit-topup",
            )
        )
        await session.commit()
        cookie = await create_session_cookie(session, user.id)

    response = await _get_whoami(async_client, cookie)
    assert response.status_code == 200
    payload = response.json()
    _assert_whoami_contract(payload)
    assert payload["first_name"] == "NoLimit"
    assert payload["last_name"] == "User"
    assert payload["company_name"] == "Whoami No Limit Co"
    assert payload["remaining_credits"] == 0
    assert payload["company_pool_balance"] == 120
    assert payload["company_allocated_total"] == 0
    assert payload["company_unallocated_balance"] == 120
    assert payload["effective_credits"] == 120


async def test_whoami_profile_uses_user_limit_by_user_id(async_client, engine):
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        user_company = await create_company(session, "Whoami User Limit Source Co")
        foreign_company = await create_company(session, "Foreign Company")
        user = await create_user(session, "userlimit@whoami.test", "member", user_company.id)
        user.first_name = "User"
        user.last_name = "Limit"
        session.add(
            Ledger(
                company_id=user_company.id,
                user_id=None,
                message_id=None,
                delta=20,
                reason="whoami_test_topup",
                idempotency_key="whoami-user-limit-source-topup",
            )
        )
        # Keep the limit row attached to another company_id to mirror real-world
        # data drift where whoami and admin previously disagreed.
        session.add(UserCreditLimit(company_id=foreign_company.id, user_id=user.id, remaining_credits=9))
        await session.commit()
        cookie = await create_session_cookie(session, user.id)

    response = await _get_whoami(async_client, cookie)
    assert response.status_code == 200
    payload = response.json()
    _assert_whoami_contract(payload)
    assert payload["company_name"] == "Whoami User Limit Source Co"
    assert payload["remaining_credits"] == 9
    assert payload["company_pool_balance"] == 20
    assert payload["company_allocated_total"] == 0
    assert payload["company_unallocated_balance"] == 20
    assert payload["effective_credits"] == 9


async def test_whoami_profile_without_company_returns_null_company_and_zero_credits(
    async_client,
    engine,
):
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        user = await create_user(session, "nocompany@whoami.test", role=None, company_id=None)
        user.first_name = "Solo"
        user.last_name = "User"
        await session.commit()
        cookie = await create_session_cookie(session, user.id)

    response = await _get_whoami(async_client, cookie)
    assert response.status_code == 200
    payload = response.json()
    _assert_whoami_contract(payload)
    assert payload["first_name"] == "Solo"
    assert payload["last_name"] == "User"
    assert payload["company_id"] is None
    assert payload["org_id"] is None
    assert payload["company_name"] is None
    assert payload["remaining_credits"] == 0
    assert payload["company_pool_balance"] == 0
    assert payload["company_allocated_total"] == 0
    assert payload["company_unallocated_balance"] == 0
    assert payload["effective_credits"] == 0
