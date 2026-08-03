from __future__ import annotations

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def _require_jobs_table(engine) -> None:
    async with engine.connect() as connection:
        exists = await connection.scalar(
            text("SELECT to_regclass('company_report_jobs')")
        )
    if exists is None:
        pytest.skip("company_report_jobs migration is not applied")


async def test_public_client_can_enqueue_reuse_and_poll_status(
    engine,
    async_client,
):
    await _require_jobs_table(engine)

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


async def test_public_company_report_api_validation_and_missing_status(
    engine,
    async_client,
):
    await _require_jobs_table(engine)

    missing = await async_client.get(
        "/company-reports/7812345678/status"
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "company_report_not_found"

    malformed = await async_client.post(
        "/company-reports",
        json={"inn": "7700000000", "extra": True},
    )
    assert malformed.status_code == 422
