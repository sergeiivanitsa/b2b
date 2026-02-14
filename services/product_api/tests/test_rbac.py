import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.settings import get_settings

from .utils import create_company, create_session_cookie, create_user

pytestmark = pytest.mark.asyncio


async def test_rbac_roles(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(session, "RBAC Co")
        superadmin = await create_user(
            session,
            "super@rbac.test",
            None,
            None,
            is_superadmin=True,
        )
        company_admin = await create_user(
            session, "admin@rbac.test", "admin", company.id
        )
        user = await create_user(session, "user@rbac.test", "member", company.id)

        super_cookie = await create_session_cookie(session, superadmin.id)
        admin_cookie = await create_session_cookie(session, company_admin.id)
        user_cookie = await create_session_cookie(session, user.id)

    cookies_user = {settings.session_cookie_name: user_cookie}
    cookies_admin = {settings.session_cookie_name: admin_cookie}
    cookies_super = {settings.session_cookie_name: super_cookie}

    resp = await async_client.post(
        "/admin/companies",
        json={"name": "DeniedCo"},
        cookies=cookies_user,
    )
    assert resp.status_code == 403

    resp = await async_client.post(
        "/admin/companies",
        json={"name": "DeniedCo"},
        cookies=cookies_admin,
    )
    assert resp.status_code == 403

    resp = await async_client.post(
        "/admin/companies",
        json={"name": "AllowedCo"},
        cookies=cookies_super,
    )
    assert resp.status_code == 200

    resp = await async_client.get("/company/users", cookies=cookies_admin)
    assert resp.status_code == 200
