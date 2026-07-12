from datetime import datetime, timezone
from uuid import UUID

import pytest

from company_report_orchestrator_test_helpers import successful_fake_provider
from product_api.company_reports import (
    CompanyReportStatus,
    build_company_report,
)


@pytest.mark.asyncio
async def test_all_datasets_success_and_request_contract():
    provider = successful_fake_provider()
    generated = datetime(2026, 2, 1, 12, tzinfo=timezone.utc)
    report_id = UUID("00000000-0000-4000-8000-000000000001")

    report = await build_company_report(
        "000-000-0000",
        provider=provider,
        request_id="report-request",
        arbitration_limit=37,
        clock=lambda: generated,
        report_id_factory=lambda: report_id,
    )

    assert report.status is CompanyReportStatus.COMPLETE
    assert report.completeness.available_count == 3
    assert report.completeness.percent == 100
    assert report.completeness.ratio == 1
    assert report.usable_for_public_page is True
    assert report.usable_for_future_scoring is True
    assert report.counterparty is not None
    assert report.finance is not None
    assert report.arbitration is not None
    assert report.arbitration.cases[0].company_roles
    assert report.report_id == report_id
    assert report.target_identifier == "0000000000"
    assert report.target_identifier_type.value == "legal_entity_inn"
    assert report.freshness.oldest_received_at is not None
    assert report.freshness.newest_received_at is not None
    assert set(report.freshness.datasets_received_at) == {
        "counterparty",
        "finance",
        "arbitration",
    }

    assert [call["dataset"] for call in provider.calls] == [
        "counterparty",
        "finance",
        "arbitration",
    ]
    assert all(call["identifier"] == "0000000000" for call in provider.calls)
    assert provider.calls[2]["limit"] == 37
    assert {call["request_id"] for call in provider.calls} == {
        "report-request:counterparty",
        "report-request:finance",
        "report-request:arbitration",
    }


@pytest.mark.asyncio
async def test_three_delayed_calls_are_concurrent():
    provider = successful_fake_provider(delay=0.08)
    started = __import__("time").perf_counter()

    await build_company_report("7700000000", provider=provider)

    elapsed = __import__("time").perf_counter() - started
    assert elapsed < 0.2
