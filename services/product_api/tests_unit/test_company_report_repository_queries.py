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
from product_api.company_reports.persistence.models import CompanyReportRecord


class _QueryCaptureSession:
    def __init__(self, record):
        self.record = record
        self.statements = []
        self.calls = 0

    async def execute(self, statement):
        self.statements.append(statement)
        self.calls += 1
        value = None if self.calls == 1 else self.record
        return type("Result", (), {"scalar_one_or_none": lambda _self: value})()


def _h1_record(*, lifecycle: str = "complete") -> CompanyReportRecord:
    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    return CompanyReportRecord(
        subject_id=__import__("uuid").uuid4(), report_version="2", lifecycle_status=lifecycle,
        writer_profile="h1_legacy_writer_v2", presentation_contract="company_public_h1_v1",
        rollout_generation=0, started_at=now, generated_at=now, warnings_snapshot=[],
        usable_for_public_page=False, usable_for_future_scoring=False,
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


@pytest.mark.asyncio
@pytest.mark.parametrize("lifecycle", ["pending", "failed", "complete"], ids=["pending", "failed", "finalized"])
async def test_h1_status_ignores_newer_v3_shadow(lifecycle):
    session = _QueryCaptureSession(_h1_record())
    status = await get_latest_run_status_by_identifier(session, "0000000000")
    sql = str(session.statements[-1])
    params = session.statements[-1].compile().params
    assert status is not None and status.report_version == "2"
    assert "h1_legacy_writer_v2" in params.values() and "company_public_h1_v1" in params.values()
    assert "report_version IN" in sql


@pytest.mark.asyncio
async def test_h1_status_ignores_newer_v3_pending():
    await test_h1_status_ignores_newer_v3_shadow("pending")


@pytest.mark.asyncio
async def test_h1_status_ignores_newer_v3_failed():
    await test_h1_status_ignores_newer_v3_shadow("failed")


@pytest.mark.asyncio
async def test_h1_status_ignores_newer_v3_finalized():
    await test_h1_status_ignores_newer_v3_shadow("complete")


@pytest.mark.asyncio
async def test_latest_equal_generated_at_uses_id_not_created_at():
    session = _QueryCaptureSession(_h1_record())
    await get_latest_report_by_identifier(session, "0000000000")
    sql = str(session.statements[-1])
    order_by = sql.split("ORDER BY", 1)[1]
    assert "generated_at DESC NULLS LAST" in order_by and "company_reports.id DESC" in order_by
    assert "created_at" not in order_by
