import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.models import UserCreditLimit
from product_api.settings import get_settings

from .utils import create_company, create_session_cookie, create_user

pytestmark = pytest.mark.asyncio

OLD_WHOAMI_KEYS = {"id", "email", "role", "org_id", "company_id", "is_superadmin", "is_active"}
NEW_WHOAMI_KEYS = {"first_name", "last_name", "company_name", "remaining_credits"}


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


async def test_whoami_profile_without_name_returns_null_names(async_client, engine):
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(session, "Whoami No Name Co")
        user = await create_user(session, "noname@whoami.test", "member", company.id)
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


async def test_whoami_profile_without_limit_returns_zero_remaining_credits(async_client, engine):
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(session, "Whoami No Limit Co")
        user = await create_user(session, "nolimit@whoami.test", "member", company.id)
        user.first_name = "NoLimit"
        user.last_name = "User"
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
