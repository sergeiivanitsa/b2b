from datetime import datetime, timedelta, timezone

import pytest

from company_report_orchestrator_test_helpers import successful_fake_provider
from persistence_test_helpers import FakeAsyncSession
from product_api.company_reports import build_company_report
from product_api.company_reports.persistence import (
    create_pending_report,
    finalize_report,
    get_fresh_report_by_identifier,
    get_latest_report_by_identifier,
    get_latest_run_status_by_identifier,
)


@pytest.mark.asyncio
async def test_latest_and_fresh_queries_exclude_pending_and_expired_reports():
    session = FakeAsyncSession()
    pending = await create_pending_report(session, identifier="0000000000")
    assert await get_latest_report_by_identifier(session, "0000000000") is None
    assert (await get_latest_run_status_by_identifier(session, "0000000000")).lifecycle_status == "pending"

    report = (await build_company_report("0000000000", provider=successful_fake_provider())).model_copy(
        update={"report_id": pending.id}
    )
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    report = report.model_copy(update={"generated_at": now})
    await finalize_report(session, report, fresh_until=now + timedelta(hours=1))

    assert await get_latest_report_by_identifier(session, "000-000-0000") == report
    assert await get_fresh_report_by_identifier(session, "0000000000", now=now) == report
    assert await get_fresh_report_by_identifier(
        session, "0000000000", now=now + timedelta(hours=2)
    ) is None


@pytest.mark.asyncio
async def test_public_page_unusable_report_is_not_fresh():
    session = FakeAsyncSession()
    pending = await create_pending_report(session, identifier="0000000000")
    report = (await build_company_report("0000000000", provider=successful_fake_provider())).model_copy(
        update={"report_id": pending.id, "usable_for_public_page": False}
    )
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    await finalize_report(session, report, fresh_until=now + timedelta(hours=1))

    assert await get_fresh_report_by_identifier(session, "0000000000", now=now) is None
