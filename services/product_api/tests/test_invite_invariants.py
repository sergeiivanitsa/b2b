import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.settings import get_settings

from .utils import create_company, create_invite, create_session_cookie, create_user

pytestmark = pytest.mark.asyncio


async def test_company_invite_reject_user_with_company(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company_a = await create_company(session, "CompanyA")
        company_b = await create_company(session, "CompanyB")
        admin = await create_user(session, "admin@a.test", "admin", company_a.id)
        cookie = await create_session_cookie(session, admin.id)
        await create_user(session, "member@b.test", "member", company_b.id)

    resp = await async_client.post(
        "/company/invites",
        json={"email": "member@b.test"},
        cookies={settings.session_cookie_name: cookie},
    )
    assert resp.status_code == 409


async def test_company_invite_reject_active_invite_other_org(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company_a = await create_company(session, "CompanyA")
        company_b = await create_company(session, "CompanyB")
        admin = await create_user(session, "admin@a.test", "admin", company_a.id)
        cookie = await create_session_cookie(session, admin.id)
        await create_invite(session, company_b.id, "pending@org.test")

    resp = await async_client.post(
        "/company/invites",
        json={"email": "pending@org.test"},
        cookies={settings.session_cookie_name: cookie},
    )
    assert resp.status_code == 409


async def test_invite_accept_reject_existing_user_with_company(async_client, engine):
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(session, "InviteCo")
        raw_token, _invite = await create_invite(
            session,
            company.id,
            "existing@org.test",
        )
        await create_user(session, "existing@org.test", "member", company.id)

    resp = await async_client.post("/invites/accept", json={"token": raw_token})
    assert resp.status_code == 409
