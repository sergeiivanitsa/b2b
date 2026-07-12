from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from company_report_orchestrator_test_helpers import successful_fake_provider
from product_api.company_reports import (
    CompanyReport,
    CompanyReportCompleteness,
    CompanyReportStatus,
    DatasetReport,
    DatasetReportStatus,
    ReportFreshness,
    SafeDatasetError,
    build_company_report,
)


@pytest.mark.asyncio
async def test_aggregate_models_are_frozen_and_json_serializable():
    report = await build_company_report(
        "7700000000",
        provider=successful_fake_provider(),
        request_id="aggregate-test",
        clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        report_id_factory=lambda: uuid4(),
    )

    assert isinstance(report, CompanyReport)
    assert report.report_version == "1"
    assert report.status is CompanyReportStatus.COMPLETE
    assert report.model_dump(mode="json")["report_id"]
    with pytest.raises(ValidationError):
        report.status = CompanyReportStatus.FAILED


def test_dataset_report_validates_source_and_error_invariants():
    with pytest.raises(ValidationError):
        DatasetReport(dataset="finance", status=DatasetReportStatus.AVAILABLE)

    with pytest.raises(ValidationError):
        DatasetReport(
            dataset="finance",
            status=DatasetReportStatus.ACCESS_DENIED,
            source=object(),
            error=SafeDatasetError(error_type="x", message="safe"),
        )


def test_completeness_ratio_and_freshness_are_typed():
    completeness = CompanyReportCompleteness(
        required_datasets=("counterparty", "finance", "arbitration"),
        available_datasets=["counterparty"],
        missing_datasets=["finance", "arbitration"],
        unavailable_datasets=["finance", "arbitration"],
        available_count=1,
        required_count=3,
        ratio=Decimal("0.3333333333333333333333333333"),
        percent=33,
        identity_available=True,
        financial_data_available=False,
        arbitration_data_available=False,
    )
    freshness = ReportFreshness(
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        age_seconds_at_generation=Decimal("2.5"),
    )

    assert completeness.ratio == Decimal("0.3333333333333333333333333333")
    assert freshness.age_seconds_at_generation == Decimal("2.5")
