from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.auth import utcnow

from .utils import create_company, create_invite

pytestmark = pytest.mark.asyncio


async def test_invite_ttl_expired(async_client, engine):
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(session, "InviteCo")
        expired_at = utcnow() - timedelta(seconds=30)
        raw_token, _invite = await create_invite(
            session,
            company_id=company.id,
            email="expired@invite.test",
            role="user",
            expires_at=expired_at,
        )

    resp = await async_client.post("/invites/accept", json={"token": raw_token})
    assert resp.status_code == 401
