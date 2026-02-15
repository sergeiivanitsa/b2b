import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import AsyncSession as SAAsyncSession
from sqlalchemy.sql.elements import TextClause

from product_api.settings import get_settings

from .utils import create_company, create_invite, create_session_cookie, create_user

pytestmark = pytest.mark.asyncio


async def _make_superadmin_cookie(session: AsyncSession, email: str = "super@hardening.test") -> str:
    superadmin = await create_user(
        session,
        email,
        role=None,
        company_id=None,
        is_superadmin=True,
    )
    return await create_session_cookie(session, superadmin.id)


async def _make_regular_cookie(
    session: AsyncSession,
    company_name: str = "Regular Co",
    email: str = "member@hardening.test",
) -> tuple[int, str]:
    company = await create_company(session, company_name)
    user = await create_user(session, email, "member", company.id)
    cookie = await create_session_cookie(session, user.id)
    return company.id, cookie


async def _ledger_balance(session: AsyncSession, company_id: int) -> int:
    result = await session.execute(
        text("SELECT COALESCE(SUM(delta), 0) FROM ledger WHERE company_id = :cid"),
        {"cid": company_id},
    )
    return int(result.scalar_one())


async def _ledger_count_by_key(session: AsyncSession, key: str) -> int:
    result = await session.execute(
        text("SELECT COUNT(*) FROM ledger WHERE idempotency_key = :key"),
        {"key": key},
    )
    return int(result.scalar_one())


async def _ledger_row_by_key(session: AsyncSession, key: str):
    result = await session.execute(
        text(
            "SELECT id, company_id, delta, reason, idempotency_key "
            "FROM ledger WHERE idempotency_key = :key LIMIT 1"
        ),
        {"key": key},
    )
    return result.first()


async def test_health_smoke_200(async_client):
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_rbac_matrix_for_admin_superadmin_endpoints(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        _company_id, regular_cookie = await _make_regular_cookie(session)
        super_cookie = await _make_superadmin_cookie(session)

    anon = await async_client.get("/superadmin/orgs")
    assert anon.status_code == 401

    regular = await async_client.get(
        "/superadmin/orgs",
        cookies={settings.session_cookie_name: regular_cookie},
    )
    assert regular.status_code == 403

    superadmin = await async_client.get(
        "/superadmin/orgs",
        cookies={settings.session_cookie_name: super_cookie},
    )
    assert superadmin.status_code == 200


async def test_superadmin_orgs_contract_fields(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        super_cookie = await _make_superadmin_cookie(session)
        await create_company(
            session,
            "Org One",
            inn="1234567890",
            phone="+79990001122",
            status="active",
        )

    resp = await async_client.get(
        "/superadmin/orgs",
        cookies={settings.session_cookie_name: super_cookie},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert "orgs" in payload
    assert len(payload["orgs"]) == 1
    org = payload["orgs"][0]
    assert {"id", "name", "inn", "phone", "status", "created_at"} <= set(org.keys())
    assert org["name"] == "Org One"
    assert org["inn"] == "1234567890"
    assert org["status"] == "active"


async def test_superadmin_patch_org_invalid_status_400(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        super_cookie = await _make_superadmin_cookie(session)
        company = await create_company(session, "Patch Org")

    resp = await async_client.patch(
        f"/superadmin/orgs/{company.id}",
        json={"status": "disabled"},
        cookies={settings.session_cookie_name: super_cookie},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid status"


async def test_superadmin_patch_org_not_found_404(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        super_cookie = await _make_superadmin_cookie(session)

    resp = await async_client.patch(
        "/superadmin/orgs/999999",
        json={"status": "active"},
        cookies={settings.session_cookie_name: super_cookie},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "company not found"


async def test_superadmin_patch_org_success_200_and_persisted(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        super_cookie = await _make_superadmin_cookie(session)
        company = await create_company(session, "Patch Org", status="pending")
        company_id = company.id

    resp = await async_client.patch(
        f"/superadmin/orgs/{company_id}",
        json={"status": "blocked"},
        cookies={settings.session_cookie_name: super_cookie},
    )
    assert resp.status_code == 200
    assert resp.json()["org"]["status"] == "blocked"

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        db_row = await session.execute(
            text("SELECT status FROM companies WHERE id = :id"),
            {"id": company_id},
        )
        assert db_row.scalar_one() == "blocked"


async def test_admin_company_admins_missing_company_404_not_500(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        super_cookie = await _make_superadmin_cookie(session)

    resp = await async_client.post(
        "/admin/companies/999999/admins",
        json={"email": "new-admin@org.test"},
        cookies={settings.session_cookie_name: super_cookie},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "company not found"


async def test_admin_company_admins_conflict_active_invite_409(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(session, "Invite Co")
        super_cookie = await _make_superadmin_cookie(session)
        await create_invite(session, company.id, "taken-admin@org.test", role="admin")

    resp = await async_client.post(
        f"/admin/companies/{company.id}/admins",
        json={"email": "taken-admin@org.test"},
        cookies={settings.session_cookie_name: super_cookie},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "active invite already exists"


async def test_admin_company_credits_missing_company_404_not_500(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        super_cookie = await _make_superadmin_cookie(session)

    resp = await async_client.post(
        "/admin/companies/999999/credits",
        json={"amount": 10, "reason": "seed"},
        cookies={settings.session_cookie_name: super_cookie},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "company not found"


async def test_admin_company_credits_amount_zero_400(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(session, "Credits Co")
        super_cookie = await _make_superadmin_cookie(session)

    resp = await async_client.post(
        f"/admin/companies/{company.id}/credits",
        json={"amount": 0, "reason": "noop"},
        cookies={settings.session_cookie_name: super_cookie},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "amount must not be zero"


async def test_admin_company_credits_negative_amount_current_behavior(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(session, "Credits Co")
        super_cookie = await _make_superadmin_cookie(session)

    resp = await async_client.post(
        f"/admin/companies/{company.id}/credits",
        json={"amount": -5, "reason": "adjustment"},
        cookies={settings.session_cookie_name: super_cookie},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"
    assert isinstance(payload["id"], int)


async def test_admin_company_credits_idempotency_duplicate_409(async_client, engine):
    settings = get_settings()
    key = "credits-dup-key-1"
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(session, "Credits Co")
        super_cookie = await _make_superadmin_cookie(session)
        balance_before = await _ledger_balance(session, company.id)

    first = await async_client.post(
        f"/admin/companies/{company.id}/credits",
        json={"amount": 11, "reason": "seed", "idempotency_key": key},
        cookies={settings.session_cookie_name: super_cookie},
    )
    assert first.status_code == 200

    second = await async_client.post(
        f"/admin/companies/{company.id}/credits",
        json={"amount": 11, "reason": "seed", "idempotency_key": key},
        cookies={settings.session_cookie_name: super_cookie},
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "duplicate idempotency_key"

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        key_rows = await _ledger_count_by_key(session, key)
        balance_after = await _ledger_balance(session, company.id)
    assert key_rows == 1
    assert balance_after - balance_before == 11


async def test_admin_company_credits_same_key_different_payload_409_and_data_unchanged(async_client, engine):
    settings = get_settings()
    key = "credits-dup-key-2"
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(session, "Credits Co")
        super_cookie = await _make_superadmin_cookie(session)
        balance_before = await _ledger_balance(session, company.id)

    first = await async_client.post(
        f"/admin/companies/{company.id}/credits",
        json={"amount": 7, "reason": "seed", "idempotency_key": key},
        cookies={settings.session_cookie_name: super_cookie},
    )
    assert first.status_code == 200

    second = await async_client.post(
        f"/admin/companies/{company.id}/credits",
        json={"amount": 999, "reason": "other reason", "idempotency_key": key},
        cookies={settings.session_cookie_name: super_cookie},
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "duplicate idempotency_key"

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        key_rows = await _ledger_count_by_key(session, key)
        row = await _ledger_row_by_key(session, key)
        balance_after = await _ledger_balance(session, company.id)

    assert key_rows == 1
    assert row is not None
    assert row[2] == 7
    assert row[3] == "seed"
    assert balance_after - balance_before == 7


async def test_internal_db_ping_requires_superadmin(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        _company_id, regular_cookie = await _make_regular_cookie(session)
        super_cookie = await _make_superadmin_cookie(session)

    anon = await async_client.get("/internal/db-ping")
    assert anon.status_code == 401

    regular = await async_client.get(
        "/internal/db-ping",
        cookies={settings.session_cookie_name: regular_cookie},
    )
    assert regular.status_code == 403

    superadmin = await async_client.get(
        "/internal/db-ping",
        cookies={settings.session_cookie_name: super_cookie},
    )
    assert superadmin.status_code == 200
    assert superadmin.json() == {"status": "ok"}


async def test_internal_db_ping_db_down_returns_503_only_for_superadmin(async_client, engine, monkeypatch):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        _company_id, regular_cookie = await _make_regular_cookie(session)
        super_cookie = await _make_superadmin_cookie(session)

    original_execute = SAAsyncSession.execute

    async def execute_with_db_down_on_ping(self, statement, *args, **kwargs):
        if isinstance(statement, TextClause) and statement.text.strip().upper() == "SELECT 1":
            raise RuntimeError("db unavailable")
        return await original_execute(self, statement, *args, **kwargs)

    monkeypatch.setattr(SAAsyncSession, "execute", execute_with_db_down_on_ping)

    anon = await async_client.get("/internal/db-ping")
    assert anon.status_code == 401

    regular = await async_client.get(
        "/internal/db-ping",
        cookies={settings.session_cookie_name: regular_cookie},
    )
    assert regular.status_code == 403

    superadmin = await async_client.get(
        "/internal/db-ping",
        cookies={settings.session_cookie_name: super_cookie},
    )
    assert superadmin.status_code == 503
    assert superadmin.json()["detail"] == "db unavailable"


async def test_internal_whoami_auth_and_contract(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        _company_id, regular_cookie = await _make_regular_cookie(session)

    anon = await async_client.get("/internal/whoami")
    assert anon.status_code == 401

    auth = await async_client.get(
        "/internal/whoami",
        cookies={settings.session_cookie_name: regular_cookie},
    )
    assert auth.status_code == 200
    payload = auth.json()
    assert {"id", "email", "role", "org_id", "company_id", "is_superadmin", "is_active"} <= set(
        payload.keys()
    )
