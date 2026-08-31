from decimal import Decimal

import pytest

from product_api.company_reports.company_card_v2.decimal_transport import DecimalTransportError, parse_source_decimal
from product_api.company_reports.company_card_v2.finance import classify_finance_cell
from product_api.company_reports.company_card_v2.finance import build_finance_views
from product_api.company_reports.company_card_v2.models import FinanceBasisV1, FinanceCellV1


def test_decimal_transport_is_lexical_and_normalizes_negative_zero() -> None:
    assert parse_source_decimal("-0.000").value == Decimal("0")
    assert parse_source_decimal("273325.0").lexeme == "273325"
    assert parse_source_decimal("-12.3400").lexeme == "-12.34"


@pytest.mark.parametrize("value", [1, 1.0, True, "1e2", "+1", "01", " 1", "1,0"])
def test_decimal_transport_rejects_lossy_forms(value: object) -> None:
    with pytest.raises(DecimalTransportError):
        parse_source_decimal(value)


def test_provider_zero_has_no_numeric_fact() -> None:
    fact = classify_finance_cell(form="0710001", code="1600", year=2025, lexemes=["0"], transport_valid=True)
    assert fact.state == "zero_unverified"
    assert fact.value is None


def test_finance_views_keep_deterministic_seven_year_window_and_signed_ratio() -> None:
    cells = []
    for year in range(2019, 2026):
        for code, value in (("1300", "10"), ("1400", "5"), ("1500", "5"), ("1600", "10"), ("2110", "20"), ("2100", "-2"), ("2200", "3"), ("2400", "4")):
            cells.append(FinanceCellV1(form="x", code=code, year=year, state="available_nonzero", value=Decimal(value)))
    views = build_finance_views(FinanceBasisV1(cells=tuple(cells)), anchor_year=2025)
    assert len(views["F2"]["periods"]) == 7
    assert views["F4"]["gross_per_100"] == Decimal("-10.000000")
    assert len(views["F5"]["years"]) == 7
    assert len(views["F5"]["rows"]) == 9


def test_finance_denominator_and_missing_are_unavailable_not_zero() -> None:
    cells = tuple(FinanceCellV1(form="x", code=code, year=2025, state="available_nonzero", value=Decimal("-1")) for code in ("1300", "1400", "1500"))
    views = build_finance_views(FinanceBasisV1(cells=cells), anchor_year=2025)
    assert views["F2"]["periods"][-1]["state"] == "denominator_unavailable"
    assert views["F1"] is None
