import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.models import Invite, User
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


async def test_company_invite_saves_profile_fields_and_list_returns_them(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(session, "CompanyA")
        admin = await create_user(session, "admin@a.test", "admin", company.id)
        cookie = await create_session_cookie(session, admin.id)

    create_resp = await async_client.post(
        "/company/invites",
        json={
            "email": "new.member@org.test",
            "first_name": "  Ivan  ",
            "last_name": "  Ivanov  ",
        },
        cookies={settings.session_cookie_name: cookie},
    )
    assert create_resp.status_code == 200

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        result = await session.execute(
            select(Invite).where(Invite.email == "new.member@org.test")
        )
        invite = result.scalar_one_or_none()
        assert invite is not None
        assert invite.first_name == "Ivan"
        assert invite.last_name == "Ivanov"

    list_resp = await async_client.get(
        "/company/invites",
        cookies={settings.session_cookie_name: cookie},
    )
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert "invites" in payload
    by_email = {item["email"]: item for item in payload["invites"]}
    assert "new.member@org.test" in by_email
    assert by_email["new.member@org.test"]["first_name"] == "Ivan"
    assert by_email["new.member@org.test"]["last_name"] == "Ivanov"


async def test_invite_accept_creates_user_with_profile_and_joined_company_at(async_client, engine):
    settings = get_settings()
    email = "accept.new@org.test"
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(session, "CompanyA")
        admin = await create_user(session, "admin@a.test", "admin", company.id)
        cookie = await create_session_cookie(session, admin.id)

    create_resp = await async_client.post(
        "/company/invites",
        json={
            "email": email,
            "first_name": "Petr",
            "last_name": "Petrov",
        },
        cookies={settings.session_cookie_name: cookie},
    )
    assert create_resp.status_code == 200
    token = create_resp.json().get("token")
    assert isinstance(token, str) and token

    accept_resp = await async_client.post("/invites/accept", json={"token": token})
    assert accept_resp.status_code == 200

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.company_id == company.id
        assert user.role == "member"
        assert user.first_name == "Petr"
        assert user.last_name == "Petrov"
        assert user.joined_company_at is not None


async def test_invite_accept_updates_existing_user_without_company_profile(async_client, engine):
    settings = get_settings()
    email = "accept.existing@org.test"
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(session, "CompanyA")
        admin = await create_user(session, "admin@a.test", "admin", company.id)
        cookie = await create_session_cookie(session, admin.id)
        existing = await create_user(session, email, None, None)
        existing.first_name = "Old"
        existing.last_name = "Name"
        await session.commit()

    create_resp = await async_client.post(
        "/company/invites",
        json={
            "email": email,
            "first_name": "New",
            "last_name": "Profile",
        },
        cookies={settings.session_cookie_name: cookie},
    )
    assert create_resp.status_code == 200
    token = create_resp.json().get("token")
    assert isinstance(token, str) and token

    accept_resp = await async_client.post("/invites/accept", json={"token": token})
    assert accept_resp.status_code == 200

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.company_id == company.id
        assert user.role == "member"
        assert user.is_active is True
        assert user.first_name == "New"
        assert user.last_name == "Profile"
        assert user.joined_company_at is not None
