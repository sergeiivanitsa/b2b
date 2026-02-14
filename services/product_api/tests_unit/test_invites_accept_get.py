from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from product_api.routers import invites as invites_router
from product_api.settings import get_settings

pytestmark = pytest.mark.asyncio


async def test_invite_accept_get_ok(async_client, mock_session, make_result, monkeypatch):
    mock_session.execute.side_effect = [
        make_result((1, 10, "user@example.com", "member")),
    ]

    existing = SimpleNamespace(
        id=123,
        company_id=None,
        role=None,
        is_active=False,
        is_superadmin=False,
    )
    monkeypatch.setattr(
        invites_router,
        "get_user_by_email",
        AsyncMock(return_value=existing),
    )
    monkeypatch.setattr(invites_router, "write_audit_log", AsyncMock())

    resp = await async_client.get("/invites/accept", params={"token": "raw-token"})

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    cookie = resp.headers.get("set-cookie")
    settings = get_settings()
    assert cookie is not None
    assert f"{settings.session_cookie_name}=" in cookie


async def test_invite_accept_get_invalid(async_client, mock_session, make_result):
    mock_session.execute.return_value = make_result(None)

    resp = await async_client.get("/invites/accept", params={"token": "bad-token"})

    assert resp.status_code == 401
