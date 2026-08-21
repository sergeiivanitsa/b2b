import pytest

from company_report_orchestrator_test_helpers import successful_fake_provider
from product_api.company_reports import (
    CompanyReportStatus,
    DatasetReportStatus,
    build_company_report,
)
from product_api.providers.datanewton import DataNewtonAccessDeniedError


def _access_denied(dataset: str) -> DataNewtonAccessDeniedError:
    return DataNewtonAccessDeniedError(
        "unsafe provider body must not be copied",
        endpoint=f"/v1/{dataset}",
        dataset=dataset,
        status_code=403,
        attempts=1,
        request_id="partial-request",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failed_dataset", "expected_percent"),
    [("arbitration", 67), ("finance", 67), ("counterparty", 67)],
)
async def test_partial_reports_preserve_successful_facts(failed_dataset, expected_percent):
    provider = successful_fake_provider()
    provider.errors[failed_dataset] = _access_denied(failed_dataset)

    report = await build_company_report(
        "7700000000",
        provider=provider,
        request_id="partial-request",
    )

    assert report.status is CompanyReportStatus.PARTIAL
    assert report.report_version == "2"
    assert tuple(report.datasets) == ("counterparty", "finance", "arbitration")
    assert report.optional_datasets == {}
    assert report.completeness.percent == expected_percent
    assert report.datasets[failed_dataset].status is DatasetReportStatus.ACCESS_DENIED
    assert report.datasets[failed_dataset].error is not None
    assert report.datasets[failed_dataset].error.status_code == 403
    assert report.datasets[failed_dataset].error.message != str(provider.errors[failed_dataset])
    assert any(item.code == "report_partial" for item in report.warnings)


@pytest.mark.asyncio
@pytest.mark.parametrize("available", ["counterparty", "finance", "arbitration"])
async def test_only_one_available_dataset_sets_usability_flags(available):
    provider = successful_fake_provider()
    for dataset in ("counterparty", "finance", "arbitration"):
        if dataset != available:
            provider.errors[dataset] = _access_denied(dataset)

    report = await build_company_report("7700000000", provider=provider)

    assert report.status is CompanyReportStatus.PARTIAL
    assert report.completeness.available_count == 1
    assert report.usable_for_public_page is (available == "counterparty")
    assert report.usable_for_future_scoring is False
