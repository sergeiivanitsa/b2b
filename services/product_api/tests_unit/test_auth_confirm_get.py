import pytest

from product_api.settings import get_settings

pytestmark = pytest.mark.asyncio


async def test_auth_confirm_get_ok(async_client, mock_session, make_result):
    mock_session.execute.side_effect = [
        make_result((1, "user@example.com")),
        make_result((42, True)),
    ]

    resp = await async_client.get("/auth/confirm", params={"token": "raw-token"})

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    cookie = resp.headers.get("set-cookie")
    settings = get_settings()
    assert cookie is not None
    assert f"{settings.session_cookie_name}=" in cookie


async def test_auth_confirm_get_invalid(async_client, mock_session, make_result):
    mock_session.execute.return_value = make_result(None)

    resp = await async_client.get("/auth/confirm", params={"token": "bad-token"})

    assert resp.status_code == 401
