import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.models import Company, User
from product_api.settings import get_settings

from .utils import create_company, create_invite, create_session_cookie, create_user

pytestmark = pytest.mark.asyncio


async def test_onboarding_create_org_ok(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        user = await create_user(session, "new@org.test", None, None)
        user_id = user.id
        cookie = await create_session_cookie(session, user.id)

    resp = await async_client.post(
        "/onboarding/create-org",
        json={"inn": "1234567890", "phone": "+79991234567"},
        cookies={settings.session_cookie_name: cookie},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["role"] == "owner"
    org_id = payload["org_id"]

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        db_user = await session.get(User, user_id)
        assert db_user is not None
        assert db_user.company_id == org_id
        assert db_user.role == "owner"

        company = await session.get(Company, org_id)
        assert company is not None
        assert company.inn == "1234567890"
        assert company.phone == "+79991234567"
        assert company.status == "active"


async def test_onboarding_reject_existing_org(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(session, "ExistingCo")
        user = await create_user(session, "member@org.test", "member", company.id)
        cookie = await create_session_cookie(session, user.id)

    resp = await async_client.post(
        "/onboarding/create-org",
        json={"inn": "2345678901", "phone": "+79991230000"},
        cookies={settings.session_cookie_name: cookie},
    )
    assert resp.status_code == 409


async def test_onboarding_reject_existing_inn(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        await create_company(
            session,
            "InnCo",
            inn="3456789012",
            phone="+79990001122",
            status="active",
        )
        user = await create_user(session, "new-inn@org.test", None, None)
        cookie = await create_session_cookie(session, user.id)

    resp = await async_client.post(
        "/onboarding/create-org",
        json={"inn": "3456789012", "phone": "+79990002233"},
        cookies={settings.session_cookie_name: cookie},
    )
    assert resp.status_code == 409


async def test_onboarding_reject_pending_invite(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(session, "InviteCo")
        await create_invite(session, company.id, "invited@org.test")
        user = await create_user(session, "invited@org.test", None, None)
        cookie = await create_session_cookie(session, user.id)

    resp = await async_client.post(
        "/onboarding/create-org",
        json={"inn": "4567890123", "phone": "+79995556677"},
        cookies={settings.session_cookie_name: cookie},
    )
    assert resp.status_code == 409
