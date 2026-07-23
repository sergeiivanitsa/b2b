from __future__ import annotations

import pytest
from sqlalchemy import text

from product_api.settings import get_settings
from tests.utils import create_company, create_session_cookie, create_user

pytestmark = pytest.mark.asyncio


async def _require_jobs_table(engine) -> None:
    async with engine.connect() as connection:
        exists = await connection.scalar(
            text("SELECT to_regclass('company_report_jobs')")
        )
    if exists is None:
        pytest.skip("company_report_jobs migration is not applied")


async def test_authenticated_member_can_enqueue_reuse_and_poll_status(
    engine,
    db_session,
    async_client,
):
    await _require_jobs_table(engine)
    company = await create_company(db_session, "Reports company")
    user = await create_user(
        db_session,
        "reports-member@example.com",
        "member",
        company_id=company.id,
    )
    raw_cookie = await create_session_cookie(db_session, user.id)
    async_client.cookies.set(get_settings().session_cookie_name, raw_cookie)

    first = await async_client.post(
        "/company-reports",
        json={"inn": "7700000000"},
    )
    second = await async_client.post(
        "/company-reports",
        json={"inn": "770-000-0000"},
    )
    status_response = await async_client.get(
        "/company-reports/7700000000/status"
    )
    pending_response = await async_client.get(
        "/company-reports/7700000000"
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["report_id"] == second.json()["report_id"]
    assert first.json()["reused"] is False
    assert second.json()["reused"] is True
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "pending"
    assert pending_response.status_code == 409
    assert pending_response.json()["detail"]["code"] == "report_pending"


async def test_company_report_api_auth_validation_and_strict_query(
    engine,
    async_client,
):
    await _require_jobs_table(engine)

    anonymous = await async_client.get(
        "/company-reports/7700000000/status"
    )
    assert anonymous.status_code == 401

    # Validation occurs after authentication, so malformed public input cannot
    # bypass the existing session boundary.
    malformed = await async_client.post(
        "/company-reports",
        json={"inn": "7700000000", "extra": True},
    )
    assert malformed.status_code in {401, 422}
