from decimal import Decimal

from product_api.company_reports.company_card_v2.finance import (
    APPROVED_CODES,
    F5_ROWS,
    FORM_BY_CODE,
    build_finance_views,
    classify_finance_cell,
)
from product_api.company_reports.company_card_v2.models import FinanceBasisV1, FinanceCellV1


def test_all_twelve_approved_codes_are_closed_and_f5_has_fixed_nine_rows() -> None:
    assert len(APPROVED_CODES) == 12
    assert len(F5_ROWS) == 9
    cells = tuple(
        FinanceCellV1(form=FORM_BY_CODE[code], code=code, year=year, state="available_nonzero", value=Decimal("10"))
        for year in range(2019, 2026)
        for code in APPROVED_CODES
    )
    views = build_finance_views(FinanceBasisV1(cells=cells), anchor_year=2025)
    assert set(views) == {"F1", "F2", "F3", "F4", "F5"}
    assert len(views["F2"]["periods"]) == len(views["F3"]["points"]) == 7
    assert len(views["F5"]["rows"]) == 9


def test_zero_is_not_numeric_and_conflict_never_enters_finance_views() -> None:
    zero = classify_finance_cell(form="balance", code="1250", year=2025, lexemes=("0",), transport_valid=True)
    conflict = classify_finance_cell(form="balance", code="1240", year=2025, lexemes=("1", "2"), transport_valid=True)
    assert zero.state == "zero_unverified" and zero.value is None
    assert conflict.state == "conflict" and conflict.value is None
    views = build_finance_views(FinanceBasisV1(cells=(zero, conflict)), anchor_year=2025)
    assert views["F1"] is None
