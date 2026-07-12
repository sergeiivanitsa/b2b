import pytest

from company_report_orchestrator_test_helpers import successful_fake_provider
from product_api.company_reports import (
    CompanyReportInputError,
    CompanyReportStatus,
    DatasetReportStatus,
    build_company_report,
)
from product_api.providers.datanewton import (
    DataNewtonAccessDeniedError,
    DataNewtonAuthenticationError,
    DataNewtonConfigurationError,
    DataNewtonDisabledError,
    DataNewtonInvalidResponseError,
    DataNewtonNetworkError,
    DataNewtonNotFoundError,
    DataNewtonRateLimitError,
    DataNewtonServerError,
)


def _provider_error(error_type):
    return error_type(
        "provider body contains a secret and must not be exposed",
        endpoint="/v1/synthetic",
        status_code=403 if error_type is DataNewtonAccessDeniedError else 500,
        retryable=error_type in {DataNewtonRateLimitError, DataNewtonServerError, DataNewtonNetworkError},
        attempts=2,
        request_id="safe-request",
        dataset="finance",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_type", "status"),
    [
        (DataNewtonNotFoundError, DatasetReportStatus.NOT_FOUND),
        (DataNewtonAccessDeniedError, DatasetReportStatus.ACCESS_DENIED),
        (DataNewtonAuthenticationError, DatasetReportStatus.AUTHENTICATION_ERROR),
        (DataNewtonRateLimitError, DatasetReportStatus.RATE_LIMITED),
        (DataNewtonServerError, DatasetReportStatus.TEMPORARILY_UNAVAILABLE),
        (DataNewtonNetworkError, DatasetReportStatus.TEMPORARILY_UNAVAILABLE),
        (DataNewtonInvalidResponseError, DatasetReportStatus.INVALID_RESPONSE),
        (DataNewtonDisabledError, DatasetReportStatus.DISABLED),
        (DataNewtonConfigurationError, DatasetReportStatus.CONFIGURATION_ERROR),
    ],
)
async def test_provider_error_mapping(error_type, status):
    provider = successful_fake_provider()
    provider.errors["finance"] = _provider_error(error_type)

    report = await build_company_report("7700000000", provider=provider)
    dataset = report.datasets["finance"]

    assert dataset.status is status
    assert dataset.error is not None
    assert dataset.error.error_type == error_type.__name__
    assert "provider body" not in dataset.error.message
    assert dataset.error.endpoint == "/v1/synthetic"
    assert report.datasets["counterparty"].status is DatasetReportStatus.AVAILABLE
    assert report.datasets["arbitration"].status is DatasetReportStatus.AVAILABLE


@pytest.mark.asyncio
async def test_unexpected_error_is_safe_and_other_calls_complete():
    provider = successful_fake_provider()
    provider.errors["finance"] = RuntimeError("identifier and raw response must not escape")

    report = await build_company_report("7700000000", provider=provider)

    assert report.datasets["finance"].status is DatasetReportStatus.UNEXPECTED_ERROR
    assert report.datasets["finance"].error is not None
    assert report.datasets["finance"].error.message == "unexpected provider error"
    assert report.completeness.available_count == 2
    assert len(provider.calls) == 3


@pytest.mark.asyncio
async def test_normalization_error_isolated_to_one_dataset():
    provider = successful_fake_provider()
    provider.results["finance"] = provider.results["counterparty"]

    report = await build_company_report("7700000000", provider=provider)

    assert report.datasets["finance"].status is DatasetReportStatus.NORMALIZATION_ERROR
    assert report.datasets["finance"].error is not None
    assert report.datasets["finance"].error.message == "dataset normalization failed"
    assert report.datasets["counterparty"].status is DatasetReportStatus.AVAILABLE
    assert report.datasets["arbitration"].status is DatasetReportStatus.AVAILABLE


@pytest.mark.asyncio
async def test_all_fail_sets_failed_status_empty_freshness_and_warning():
    provider = successful_fake_provider()
    for dataset in ("counterparty", "finance", "arbitration"):
        provider.errors[dataset] = RuntimeError("unsafe")

    report = await build_company_report("7700000000", provider=provider)

    assert report.status is CompanyReportStatus.FAILED
    assert report.completeness.percent == 0
    assert report.usable_for_public_page is False
    assert report.usable_for_future_scoring is False
    assert report.freshness.oldest_received_at is None
    assert report.freshness.newest_received_at is None
    assert report.freshness.datasets_received_at == {}
    assert report.freshness.age_seconds_at_generation is None
    assert any(item.code == "report_failed" for item in report.warnings)


@pytest.mark.asyncio
@pytest.mark.parametrize("identifier", ["", "abc", "123", "1234567890123456"])
async def test_invalid_identifier_is_rejected_before_provider_calls(identifier):
    provider = successful_fake_provider()

    with pytest.raises(CompanyReportInputError):
        await build_company_report(identifier, provider=provider)

    assert provider.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, 1001, True, "100"])
async def test_invalid_arbitration_limit_is_rejected_before_provider_calls(limit):
    provider = successful_fake_provider()

    with pytest.raises(CompanyReportInputError):
        await build_company_report("7700000000", provider=provider, arbitration_limit=limit)

    assert provider.calls == []
