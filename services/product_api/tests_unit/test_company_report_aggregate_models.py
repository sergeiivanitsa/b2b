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
    REQUIRED_DATASETS,
    ReportFreshness,
    SafeDatasetError,
    SourceMetadata,
    build_company_report,
)


_GENERATED_AT = datetime(2026, 1, 10, tzinfo=timezone.utc)
_OPTIONAL_RECEIVED_AT = {
    "tax_info": datetime(2025, 1, 1, tzinfo=timezone.utc),
    "bankruptcy": datetime(2026, 1, 9, tzinfo=timezone.utc),
}


def _optional_dataset_reports(state: str) -> dict[str, DatasetReport]:
    if state == "empty":
        return {}

    if state == "available":
        return {
            dataset: DatasetReport(
                dataset=dataset,
                status=DatasetReportStatus.AVAILABLE,
                source=SourceMetadata(
                    provider="datanewton",
                    dataset=dataset,
                    endpoint=f"/v1/{dataset.replace('_', '-')}",
                    response_hash="0" * 64,
                    received_at=received_at,
                    request_id=f"optional-matrix:{dataset}",
                ),
            )
            for dataset, received_at in _OPTIONAL_RECEIVED_AT.items()
        }

    status = {
        "not_found": DatasetReportStatus.NOT_FOUND,
        "failed": DatasetReportStatus.UNEXPECTED_ERROR,
    }[state]
    return {
        dataset: DatasetReport(
            dataset=dataset,
            status=status,
            error=SafeDatasetError(
                error_type="SyntheticOptionalDatasetError",
                message=(
                    "optional dataset was not found"
                    if state == "not_found"
                    else "optional dataset failed"
                ),
            ),
        )
        for dataset in _OPTIONAL_RECEIVED_AT
    }


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
    assert report.report_version == "2"
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


@pytest.mark.parametrize(
    ("optional_state", "required_available_count"),
    [
        (optional_state, required_available_count)
        for optional_state in ("empty", "available", "not_found", "failed")
        for required_available_count in range(4)
    ],
)
@pytest.mark.asyncio
async def test_optional_dataset_state_does_not_change_required_lifecycle_matrix(
    optional_state,
    required_available_count,
):
    provider = successful_fake_provider()
    provider.errors.update(
        {
            dataset: RuntimeError(f"synthetic unavailable {dataset}")
            for dataset in REQUIRED_DATASETS[required_available_count:]
        }
    )
    required_only = await build_company_report(
        "7700000000",
        provider=provider,
        request_id=(
            f"optional-matrix:{optional_state}:{required_available_count}"
        ),
        clock=lambda: _GENERATED_AT,
        report_id_factory=uuid4,
    )
    optional_datasets = _optional_dataset_reports(optional_state)

    report = CompanyReport.model_validate(
        {
            **required_only.model_dump(),
            "optional_datasets": optional_datasets,
        }
    )

    expected_status = (
        CompanyReportStatus.FAILED
        if required_available_count == 0
        else CompanyReportStatus.COMPLETE
        if required_available_count == 3
        else CompanyReportStatus.PARTIAL
    )
    assert report.status is expected_status
    assert report.status is required_only.status
    assert report.completeness == required_only.completeness
    assert report.completeness.required_datasets == REQUIRED_DATASETS
    assert report.completeness.required_count == 3
    assert report.completeness.available_count == required_available_count
    assert report.completeness.ratio == (
        Decimal(required_available_count) / Decimal(3)
    )
    assert report.freshness == required_only.freshness
    assert (
        report.freshness.oldest_received_at
        == required_only.freshness.oldest_received_at
    )
    assert (
        report.freshness.newest_received_at
        == required_only.freshness.newest_received_at
    )
    assert (
        report.freshness.age_seconds_at_generation
        == required_only.freshness.age_seconds_at_generation
    )
    assert set(report.freshness.datasets_received_at) == set(
        REQUIRED_DATASETS[:required_available_count]
    )
    assert not (
        set(report.freshness.datasets_received_at) & set(optional_datasets)
    )
    assert report.warnings == required_only.warnings
    assert report.usable_for_public_page is (required_available_count >= 1)
    assert report.usable_for_future_scoring is (required_available_count >= 2)
    assert (
        report.usable_for_public_page
        is required_only.usable_for_public_page
    )
    assert (
        report.usable_for_future_scoring
        is required_only.usable_for_future_scoring
    )

    expected_optional_keys = (
        set() if optional_state == "empty" else set(_OPTIONAL_RECEIVED_AT)
    )
    assert set(report.optional_datasets) == expected_optional_keys
    if optional_state == "empty":
        return

    expected_optional_status = {
        "available": DatasetReportStatus.AVAILABLE,
        "not_found": DatasetReportStatus.NOT_FOUND,
        "failed": DatasetReportStatus.UNEXPECTED_ERROR,
    }[optional_state]
    for dataset, optional_report in report.optional_datasets.items():
        assert optional_report.status is expected_optional_status
        if optional_state == "available":
            assert optional_report.source is not None
            assert (
                optional_report.source.received_at
                == _OPTIONAL_RECEIVED_AT[dataset]
            )
            assert optional_report.error is None
        else:
            assert optional_report.source is None
            assert optional_report.error is not None
