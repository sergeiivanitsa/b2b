import pytest
from fastapi import HTTPException

from product_api.claims.admin_auth import (
    consume_claims_admin_auth_token,
    is_claims_admin_email,
    require_claims_admin,
)
from product_api.models import User
from product_api.settings import get_settings

pytestmark = pytest.mark.asyncio


async def test_require_claims_admin_allows_whitelisted_email():
    settings = get_settings().model_copy(
        update={"claims_admin_emails": ["claims-admin@example.com"]}
    )
    user = User(
        id=1,
        email="claims-admin@example.com",
        role=None,
        is_active=True,
        is_superadmin=False,
        company_id=None,
    )

    result = await require_claims_admin(current_user=user, settings=settings)

    assert result.id == 1


async def test_require_claims_admin_rejects_non_whitelisted_email():
    settings = get_settings().model_copy(
        update={"claims_admin_emails": ["claims-admin@example.com"]}
    )
    user = User(
        id=2,
        email="superadmin@example.com",
        role=None,
        is_active=True,
        is_superadmin=True,
        company_id=None,
    )

    with pytest.raises(HTTPException) as exc:
        await require_claims_admin(current_user=user, settings=settings)

    assert exc.value.status_code == 403
    assert exc.value.detail == "forbidden"


async def test_consume_claims_admin_auth_token_requires_whitelist(mock_session, make_result):
    settings = get_settings().model_copy(
        update={"claims_admin_emails": ["claims-admin@example.com"]}
    )
    mock_session.execute.return_value = make_result(("outsider@example.com",))

    with pytest.raises(PermissionError, match="forbidden_admin_email"):
        await consume_claims_admin_auth_token(
            mock_session,
            settings,
            token="raw-token",
        )


async def test_is_claims_admin_email_normalizes_value():
    settings = get_settings().model_copy(
        update={"claims_admin_emails": ["claims-admin@example.com"]}
    )
    assert is_claims_admin_email(settings, "CLAIMS-ADMIN@EXAMPLE.COM")
    assert not is_claims_admin_email(settings, "other@example.com")
