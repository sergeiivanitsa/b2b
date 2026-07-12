from decimal import Decimal

import pytest

from company_report_orchestrator_test_helpers import successful_fake_provider
from product_api.company_reports import build_company_report
from product_api.providers.datanewton import DataNewtonAccessDeniedError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("available_count", "expected_ratio", "expected_percent"),
    [(0, Decimal("0"), 0), (1, Decimal("0.3333333333333333333333333333"), 33), (2, Decimal("0.6666666666666666666666666667"), 67), (3, Decimal("1"), 100)],
)
async def test_completeness_uses_decimal_and_half_up_percent(
    available_count, expected_ratio, expected_percent
):
    provider = successful_fake_provider()
    for dataset in ("counterparty", "finance", "arbitration")[: 3 - available_count]:
        provider.errors[dataset] = DataNewtonAccessDeniedError(
            "safe", endpoint=f"/v1/{dataset}", status_code=403, attempts=1
        )

    report = await build_company_report("7700000000", provider=provider)

    assert report.completeness.available_count == available_count
    assert report.completeness.ratio == expected_ratio
    assert report.completeness.percent == expected_percent
    assert set(report.completeness.missing_datasets) == set(
        report.completeness.unavailable_datasets
    )
