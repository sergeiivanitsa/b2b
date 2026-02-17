from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.models import Ledger, UserCreditLimit
from product_api.settings import get_settings

from .utils import add_credits, create_company, create_session_cookie, create_user

pytestmark = pytest.mark.asyncio


async def _make_company_team(session: AsyncSession):
    company = await create_company(session, "Summary Co", inn="1234567890", phone="+79990000000", status="active")
    owner = await create_user(session, "owner@summary.test", "owner", company.id)
    admin = await create_user(session, "admin@summary.test", "admin", company.id)
    member = await create_user(session, "member@summary.test", "member", company.id)

    owner_cookie = await create_session_cookie(session, owner.id)
    admin_cookie = await create_session_cookie(session, admin.id)
    member_cookie = await create_session_cookie(session, member.id)

    return company, owner, admin, member, owner_cookie, admin_cookie, member_cookie


async def test_company_summary_rbac_owner_admin_allowed_member_forbidden(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        _company, _owner, _admin, _member, owner_cookie, admin_cookie, member_cookie = await _make_company_team(session)

    owner_resp = await async_client.get(
        "/company/summary",
        cookies={settings.session_cookie_name: owner_cookie},
    )
    assert owner_resp.status_code == 200

    admin_resp = await async_client.get(
        "/company/summary",
        cookies={settings.session_cookie_name: admin_cookie},
    )
    assert admin_resp.status_code == 200

    member_resp = await async_client.get(
        "/company/summary",
        cookies={settings.session_cookie_name: member_cookie},
    )
    assert member_resp.status_code == 403


async def test_company_users_stats_rbac_owner_admin_allowed_member_forbidden(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        _company, _owner, _admin, _member, owner_cookie, admin_cookie, member_cookie = await _make_company_team(session)

    owner_resp = await async_client.get(
        "/company/users/stats",
        cookies={settings.session_cookie_name: owner_cookie},
    )
    assert owner_resp.status_code == 200

    admin_resp = await async_client.get(
        "/company/users/stats",
        cookies={settings.session_cookie_name: admin_cookie},
    )
    assert admin_resp.status_code == 200

    member_resp = await async_client.get(
        "/company/users/stats",
        cookies={settings.session_cookie_name: member_cookie},
    )
    assert member_resp.status_code == 403


async def test_company_summary_contract_and_math(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company, owner, admin, member, owner_cookie, _admin_cookie, _member_cookie = await _make_company_team(session)
        await add_credits(session, company.id, 120, reason="seed")
        await add_credits(session, company.id, -20, reason="adjust")

        session.add_all(
            [
                UserCreditLimit(company_id=company.id, user_id=owner.id, remaining_credits=70),
                UserCreditLimit(company_id=company.id, user_id=admin.id, remaining_credits=20),
                UserCreditLimit(company_id=company.id, user_id=member.id, remaining_credits=5),
            ]
        )
        await session.commit()

    resp = await async_client.get(
        "/company/summary",
        cookies={settings.session_cookie_name: owner_cookie},
    )
    assert resp.status_code == 200
    payload = resp.json()

    assert {"company", "credits", "users"} <= set(payload.keys())
    assert {"id", "name", "inn", "phone", "status"} <= set(payload["company"].keys())
    assert payload["company"]["id"] == company.id
    assert payload["company"]["status"] == "active"

    assert payload["credits"]["pool_balance"] == 100
    assert payload["credits"]["allocated_total"] == 95
    assert payload["credits"]["unallocated_balance"] == 5

    assert payload["users"]["total"] == 3
    assert payload["users"]["active"] == 3


async def test_company_users_stats_contract_and_spent_all_time(async_client, engine):
    settings = get_settings()
    owner_joined = datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc)
    member_joined = datetime(2026, 2, 2, 10, 0, tzinfo=timezone.utc)

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company, owner, admin, member, _owner_cookie, admin_cookie, _member_cookie = await _make_company_team(session)

        owner.first_name = "Ivan"
        owner.last_name = "Ivanov"
        owner.joined_company_at = owner_joined
        member.first_name = "Petr"
        member.last_name = "Petrov"
        member.joined_company_at = member_joined

        session.add_all(
            [
                UserCreditLimit(company_id=company.id, user_id=owner.id, remaining_credits=15),
                UserCreditLimit(company_id=company.id, user_id=member.id, remaining_credits=2),
            ]
        )
        session.add_all(
            [
                Ledger(
                    company_id=company.id,
                    user_id=owner.id,
                    message_id=None,
                    delta=-3,
                    reason="chat_message",
                    idempotency_key="stats-owner-chat-1",
                ),
                Ledger(
                    company_id=company.id,
                    user_id=owner.id,
                    message_id=None,
                    delta=-2,
                    reason="chat_message",
                    idempotency_key="stats-owner-chat-2",
                ),
                Ledger(
                    company_id=company.id,
                    user_id=owner.id,
                    message_id=None,
                    delta=-7,
                    reason="manual_adjustment",
                    idempotency_key="stats-owner-other-1",
                ),
                Ledger(
                    company_id=company.id,
                    user_id=member.id,
                    message_id=None,
                    delta=-4,
                    reason="chat_message",
                    idempotency_key="stats-member-chat-1",
                ),
                Ledger(
                    company_id=company.id,
                    user_id=member.id,
                    message_id=None,
                    delta=9,
                    reason="bonus",
                    idempotency_key="stats-member-other-1",
                ),
            ]
        )
        await session.commit()

    resp = await async_client.get(
        "/company/users/stats",
        cookies={settings.session_cookie_name: admin_cookie},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert "users" in payload
    assert len(payload["users"]) == 3

    users_by_email = {item["email"]: item for item in payload["users"]}

    owner_row = users_by_email["owner@summary.test"]
    assert owner_row["first_name"] == "Ivan"
    assert owner_row["last_name"] == "Ivanov"
    assert owner_row["role"] == "owner"
    assert owner_row["remaining_credits"] == 15
    assert owner_row["spent_all_time"] == 5
    assert owner_row["joined_company_at"].startswith("2026-02-01T10:00:00")

    member_row = users_by_email["member@summary.test"]
    assert member_row["first_name"] == "Petr"
    assert member_row["last_name"] == "Petrov"
    assert member_row["role"] == "member"
    assert member_row["remaining_credits"] == 2
    assert member_row["spent_all_time"] == 4
    assert member_row["joined_company_at"].startswith("2026-02-02T10:00:00")

    admin_row = users_by_email["admin@summary.test"]
    assert admin_row["role"] == "admin"
    assert admin_row["remaining_credits"] == 0
    assert admin_row["spent_all_time"] == 0
    assert admin_row["joined_company_at"] is not None
