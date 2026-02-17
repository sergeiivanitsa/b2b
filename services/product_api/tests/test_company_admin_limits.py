import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.models import Ledger, UserCreditLimit
from product_api.settings import get_settings

from .utils import add_credits, create_company, create_session_cookie, create_user

pytestmark = pytest.mark.asyncio


async def _make_company_users(session: AsyncSession):
    company = await create_company(session, "Limits Co")
    owner = await create_user(session, "owner@limits.test", "owner", company.id)
    admin = await create_user(session, "admin@limits.test", "admin", company.id)
    admin2 = await create_user(session, "admin2@limits.test", "admin", company.id)
    member = await create_user(session, "member@limits.test", "member", company.id)

    owner_cookie = await create_session_cookie(session, owner.id)
    admin_cookie = await create_session_cookie(session, admin.id)
    member_cookie = await create_session_cookie(session, member.id)
    return company, owner, admin, admin2, member, owner_cookie, admin_cookie, member_cookie


async def test_patch_user_limit_allocate_success(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company, owner, _admin, _admin2, member, owner_cookie, _admin_cookie, _member_cookie = await _make_company_users(session)
        await add_credits(session, company.id, 10, reason="seed")
        session.add_all(
            [
                UserCreditLimit(company_id=company.id, user_id=owner.id, remaining_credits=4),
                UserCreditLimit(company_id=company.id, user_id=member.id, remaining_credits=2),
            ]
        )
        await session.commit()

    resp = await async_client.patch(
        f"/company/users/{member.id}/limit",
        json={"delta": 3, "reason": "allocate"},
        cookies={settings.session_cookie_name: owner_cookie},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"
    assert payload["user"]["remaining_credits"] == 5
    assert payload["credits"]["pool_balance"] == 10
    assert payload["credits"]["allocated_total"] == 9
    assert payload["credits"]["unallocated_balance"] == 1


async def test_patch_user_limit_deallocate_success(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company, owner, _admin, _admin2, member, owner_cookie, _admin_cookie, _member_cookie = await _make_company_users(session)
        await add_credits(session, company.id, 10, reason="seed")
        session.add_all(
            [
                UserCreditLimit(company_id=company.id, user_id=owner.id, remaining_credits=4),
                UserCreditLimit(company_id=company.id, user_id=member.id, remaining_credits=5),
            ]
        )
        await session.commit()

    resp = await async_client.patch(
        f"/company/users/{member.id}/limit",
        json={"delta": -2, "reason": "deallocate"},
        cookies={settings.session_cookie_name: owner_cookie},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["user"]["remaining_credits"] == 3
    assert payload["credits"]["allocated_total"] == 7


async def test_patch_user_limit_reject_below_zero(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company, _owner, _admin, _admin2, member, _owner_cookie, admin_cookie, _member_cookie = await _make_company_users(session)
        await add_credits(session, company.id, 10, reason="seed")
        session.add(UserCreditLimit(company_id=company.id, user_id=member.id, remaining_credits=1))
        await session.commit()

    resp = await async_client.patch(
        f"/company/users/{member.id}/limit",
        json={"delta": -2, "reason": "deallocate"},
        cookies={settings.session_cookie_name: admin_cookie},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "limit cannot be negative"


async def test_patch_user_limit_reject_exceeds_pool(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company, owner, _admin, _admin2, member, owner_cookie, _admin_cookie, _member_cookie = await _make_company_users(session)
        await add_credits(session, company.id, 3, reason="seed")
        session.add_all(
            [
                UserCreditLimit(company_id=company.id, user_id=owner.id, remaining_credits=1),
                UserCreditLimit(company_id=company.id, user_id=member.id, remaining_credits=2),
            ]
        )
        await session.commit()

    resp = await async_client.patch(
        f"/company/users/{member.id}/limit",
        json={"delta": 1, "reason": "allocate"},
        cookies={settings.session_cookie_name: owner_cookie},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "allocation exceeds company pool balance"


async def test_patch_user_limit_member_forbidden(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company, owner, _admin, _admin2, member, _owner_cookie, _admin_cookie, member_cookie = await _make_company_users(session)
        await add_credits(session, company.id, 10, reason="seed")
        session.add(UserCreditLimit(company_id=company.id, user_id=owner.id, remaining_credits=2))
        await session.commit()

    resp = await async_client.patch(
        f"/company/users/{owner.id}/limit",
        json={"delta": 1, "reason": "allocate"},
        cookies={settings.session_cookie_name: member_cookie},
    )
    assert resp.status_code == 403


async def test_patch_user_limit_admin_cannot_manage_owner_or_admin(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company, owner, _admin, admin2, _member, _owner_cookie, admin_cookie, _member_cookie = await _make_company_users(session)
        await add_credits(session, company.id, 20, reason="seed")
        session.add(UserCreditLimit(company_id=company.id, user_id=owner.id, remaining_credits=5))
        session.add(UserCreditLimit(company_id=company.id, user_id=admin2.id, remaining_credits=5))
        await session.commit()

    owner_resp = await async_client.patch(
        f"/company/users/{owner.id}/limit",
        json={"delta": 1, "reason": "allocate"},
        cookies={settings.session_cookie_name: admin_cookie},
    )
    assert owner_resp.status_code == 403

    admin_resp = await async_client.patch(
        f"/company/users/{admin2.id}/limit",
        json={"delta": 1, "reason": "allocate"},
        cookies={settings.session_cookie_name: admin_cookie},
    )
    assert admin_resp.status_code == 403


async def test_company_credits_locked_for_company_admin(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company, _owner, admin, _admin2, _member, _owner_cookie, admin_cookie, _member_cookie = await _make_company_users(session)

    resp = await async_client.post(
        "/company/credits",
        json={"amount": 10, "reason": "manual", "user_id": None},
        cookies={settings.session_cookie_name: admin_cookie},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "company pool can only be changed by superadmin"

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        result = await session.execute(
            select(Ledger).where(
                Ledger.company_id == company.id,
                Ledger.reason == "manual",
            )
        )
        assert result.scalars().first() is None
