from datetime import datetime, timezone

import pytest

from product_api.models import User
from product_api.settings import get_settings

pytestmark = pytest.mark.asyncio


async def test_admin_request_link_ok(async_client, mock_session, monkeypatch):
    sent = {}

    def fake_send_claims_admin_magic_link(_settings, to_email, link):
        sent["to_email"] = to_email
        sent["link"] = link

    from product_api.routers import admin_claims_auth as admin_claims_auth_router

    monkeypatch.setattr(
        admin_claims_auth_router,
        "send_claims_admin_magic_link",
        fake_send_claims_admin_magic_link,
    )

    resp = await async_client.post(
        "/admin/auth/request-link",
        json={"email": "claims-admin@example.com"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"
    assert isinstance(payload.get("token"), str)
    assert "token=" in payload["link"]
    assert sent["to_email"] == "claims-admin@example.com"
    assert mock_session.commit.await_count == 1


async def test_admin_request_link_non_whitelisted_email_returns_ok(async_client, mock_session, monkeypatch):
    sent = {"called": False}

    def fake_send_claims_admin_magic_link(_settings, to_email, link):
        sent["called"] = True

    from product_api.routers import admin_claims_auth as admin_claims_auth_router

    monkeypatch.setattr(
        admin_claims_auth_router,
        "send_claims_admin_magic_link",
        fake_send_claims_admin_magic_link,
    )

    resp = await async_client.post(
        "/admin/auth/request-link",
        json={"email": "outsider@example.com"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload == {"status": "ok"}
    assert sent["called"] is False
    assert mock_session.commit.await_count == 0


async def test_admin_confirm_ok_sets_cookie(async_client, mock_session, monkeypatch):
    async def fake_consume_claims_admin_auth_token(_session, _settings, *, token):
        assert token == "good-token"
        return "claims-admin@example.com"

    async def fake_get_or_create_claims_admin_user(_session, *, email):
        assert email == "claims-admin@example.com"
        return User(
            id=777,
            email=email,
            role=None,
            is_active=True,
            company_id=None,
            is_superadmin=False,
        )

    async def fake_create_claims_admin_session(_session, _settings, *, user_id):
        assert user_id == 777
        return "raw-session", datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)

    from product_api.routers import admin_claims_auth as admin_claims_auth_router

    monkeypatch.setattr(
        admin_claims_auth_router,
        "consume_claims_admin_auth_token",
        fake_consume_claims_admin_auth_token,
    )
    monkeypatch.setattr(
        admin_claims_auth_router,
        "get_or_create_claims_admin_user",
        fake_get_or_create_claims_admin_user,
    )
    monkeypatch.setattr(
        admin_claims_auth_router,
        "create_claims_admin_session",
        fake_create_claims_admin_session,
    )

    resp = await async_client.post(
        "/admin/auth/confirm",
        json={"token": "good-token"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    cookie = resp.headers.get("set-cookie")
    settings = get_settings()
    assert cookie is not None
    assert f"{settings.session_cookie_name}=raw-session" in cookie
    assert mock_session.commit.await_count == 1


async def test_admin_confirm_get_ok_sets_cookie(async_client, mock_session, monkeypatch):
    async def fake_consume_claims_admin_auth_token(_session, _settings, *, token):
        assert token == "good-token"
        return "claims-admin@example.com"

    async def fake_get_or_create_claims_admin_user(_session, *, email):
        assert email == "claims-admin@example.com"
        return User(
            id=778,
            email=email,
            role=None,
            is_active=True,
            company_id=None,
            is_superadmin=False,
        )

    async def fake_create_claims_admin_session(_session, _settings, *, user_id):
        assert user_id == 778
        return "raw-session-get", datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)

    from product_api.routers import admin_claims_auth as admin_claims_auth_router

    monkeypatch.setattr(
        admin_claims_auth_router,
        "consume_claims_admin_auth_token",
        fake_consume_claims_admin_auth_token,
    )
    monkeypatch.setattr(
        admin_claims_auth_router,
        "get_or_create_claims_admin_user",
        fake_get_or_create_claims_admin_user,
    )
    monkeypatch.setattr(
        admin_claims_auth_router,
        "create_claims_admin_session",
        fake_create_claims_admin_session,
    )

    resp = await async_client.get(
        "/admin/auth/confirm",
        params={"token": "good-token"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    cookie = resp.headers.get("set-cookie")
    settings = get_settings()
    assert cookie is not None
    assert f"{settings.session_cookie_name}=raw-session-get" in cookie
    assert mock_session.commit.await_count == 1


async def test_admin_confirm_invalid_token_returns_401(async_client, mock_session, monkeypatch):
    async def fake_consume_claims_admin_auth_token(_session, _settings, *, token):
        raise ValueError("invalid_or_expired_token")

    from product_api.routers import admin_claims_auth as admin_claims_auth_router

    monkeypatch.setattr(
        admin_claims_auth_router,
        "consume_claims_admin_auth_token",
        fake_consume_claims_admin_auth_token,
    )

    resp = await async_client.post(
        "/admin/auth/confirm",
        json={"token": "bad-token"},
    )

    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid or expired token"
    assert mock_session.commit.await_count == 0


async def test_admin_confirm_forbidden_email_returns_403(async_client, mock_session, monkeypatch):
    async def fake_consume_claims_admin_auth_token(_session, _settings, *, token):
        raise PermissionError("forbidden_admin_email")

    from product_api.routers import admin_claims_auth as admin_claims_auth_router

    monkeypatch.setattr(
        admin_claims_auth_router,
        "consume_claims_admin_auth_token",
        fake_consume_claims_admin_auth_token,
    )

    resp = await async_client.post(
        "/admin/auth/confirm",
        json={"token": "bad-token"},
    )

    assert resp.status_code == 403
    assert resp.json()["detail"] == "forbidden"
    assert mock_session.commit.await_count == 0


async def test_admin_confirm_inactive_user_returns_401(async_client, mock_session, monkeypatch):
    async def fake_consume_claims_admin_auth_token(_session, _settings, *, token):
        return "claims-admin@example.com"

    async def fake_get_or_create_claims_admin_user(_session, *, email):
        raise PermissionError("inactive_user")

    from product_api.routers import admin_claims_auth as admin_claims_auth_router

    monkeypatch.setattr(
        admin_claims_auth_router,
        "consume_claims_admin_auth_token",
        fake_consume_claims_admin_auth_token,
    )
    monkeypatch.setattr(
        admin_claims_auth_router,
        "get_or_create_claims_admin_user",
        fake_get_or_create_claims_admin_user,
    )

    resp = await async_client.post(
        "/admin/auth/confirm",
        json={"token": "good-token"},
    )

    assert resp.status_code == 401
    assert resp.json()["detail"] == "inactive user"
    assert mock_session.commit.await_count == 0
