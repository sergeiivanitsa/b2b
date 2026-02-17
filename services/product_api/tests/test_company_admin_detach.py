import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.models import Ledger, Session, User, UserCreditLimit
from product_api.settings import get_settings

from .utils import create_company, create_session_cookie, create_user

pytestmark = pytest.mark.asyncio


async def _make_company_users(session: AsyncSession):
    company = await create_company(session, "Detach Co")
    owner = await create_user(session, "owner@detach.test", "owner", company.id)
    admin = await create_user(session, "admin@detach.test", "admin", company.id)
    admin2 = await create_user(session, "admin2@detach.test", "admin", company.id)
    member = await create_user(session, "member@detach.test", "member", company.id)

    owner_cookie = await create_session_cookie(session, owner.id)
    admin_cookie = await create_session_cookie(session, admin.id)
    member_cookie = await create_session_cookie(session, member.id)
    return company, owner, admin, admin2, member, owner_cookie, admin_cookie, member_cookie


async def test_detach_owner_success_user_hidden_from_stats_and_history_kept(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company, owner, _admin, _admin2, member, owner_cookie, _admin_cookie, _member_cookie = await _make_company_users(session)

        member_limit = UserCreditLimit(
            company_id=company.id,
            user_id=member.id,
            remaining_credits=7,
        )
        ledger_entry = Ledger(
            company_id=company.id,
            user_id=member.id,
            message_id=None,
            delta=-2,
            reason="chat_message",
            idempotency_key="detach-member-chat-1",
        )
        session.add_all([member_limit, ledger_entry])
        await session.commit()
        ledger_id = ledger_entry.id

    detach_resp = await async_client.post(
        f"/company/users/{member.id}/detach",
        cookies={settings.session_cookie_name: owner_cookie},
    )
    assert detach_resp.status_code == 200
    payload = detach_resp.json()
    assert payload["status"] == "ok"
    assert payload["released_limit"] == 7
    assert payload["user"]["id"] == member.id
    assert payload["user"]["company_id"] is None
    assert payload["user"]["is_active"] is False

    stats_resp = await async_client.get(
        "/company/users/stats",
        cookies={settings.session_cookie_name: owner_cookie},
    )
    assert stats_resp.status_code == 200
    emails = [item["email"] for item in stats_resp.json()["users"]]
    assert member.email not in emails

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        user = await session.get(User, member.id)
        assert user is not None
        assert user.company_id is None
        assert user.role == "member"
        assert user.is_active is False
        assert user.joined_company_at is None

        limit_result = await session.execute(
            select(UserCreditLimit).where(UserCreditLimit.user_id == member.id)
        )
        assert limit_result.scalar_one_or_none() is None

        sessions_result = await session.execute(
            select(Session).where(Session.user_id == member.id)
        )
        assert sessions_result.scalars().first() is None

        ledger_result = await session.execute(select(Ledger).where(Ledger.id == ledger_id))
        assert ledger_result.scalar_one_or_none() is not None


async def test_detach_email_can_be_invited_to_another_company(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company_a = await create_company(session, "Detach A")
        company_b = await create_company(session, "Detach B")
        owner_a = await create_user(session, "owner@a.detach.test", "owner", company_a.id)
        owner_b = await create_user(session, "owner@b.detach.test", "owner", company_b.id)
        member_a = await create_user(session, "member@cross.detach.test", "member", company_a.id)
        owner_a_cookie = await create_session_cookie(session, owner_a.id)
        owner_b_cookie = await create_session_cookie(session, owner_b.id)

    detach_resp = await async_client.post(
        f"/company/users/{member_a.id}/detach",
        cookies={settings.session_cookie_name: owner_a_cookie},
    )
    assert detach_resp.status_code == 200

    invite_resp = await async_client.post(
        "/company/invites",
        json={"email": member_a.email, "first_name": "Ivan", "last_name": "Detached"},
        cookies={settings.session_cookie_name: owner_b_cookie},
    )
    assert invite_resp.status_code == 200


async def test_detach_admin_can_detach_member(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        _company, _owner, _admin, _admin2, member, _owner_cookie, admin_cookie, _member_cookie = await _make_company_users(session)

    resp = await async_client.post(
        f"/company/users/{member.id}/detach",
        cookies={settings.session_cookie_name: admin_cookie},
    )
    assert resp.status_code == 200


async def test_detach_admin_cannot_detach_owner_or_admin(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        _company, owner, _admin, admin2, _member, _owner_cookie, admin_cookie, _member_cookie = await _make_company_users(session)

    owner_resp = await async_client.post(
        f"/company/users/{owner.id}/detach",
        cookies={settings.session_cookie_name: admin_cookie},
    )
    assert owner_resp.status_code == 403

    admin_resp = await async_client.post(
        f"/company/users/{admin2.id}/detach",
        cookies={settings.session_cookie_name: admin_cookie},
    )
    assert admin_resp.status_code == 403


async def test_detach_member_forbidden(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        _company, owner, _admin, _admin2, _member, _owner_cookie, _admin_cookie, member_cookie = await _make_company_users(session)

    resp = await async_client.post(
        f"/company/users/{owner.id}/detach",
        cookies={settings.session_cookie_name: member_cookie},
    )
    assert resp.status_code == 403


async def test_detach_self_forbidden(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        _company, owner, _admin, _admin2, _member, owner_cookie, _admin_cookie, _member_cookie = await _make_company_users(session)

    resp = await async_client.post(
        f"/company/users/{owner.id}/detach",
        cookies={settings.session_cookie_name: owner_cookie},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "cannot detach self"
