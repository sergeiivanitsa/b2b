from decimal import Decimal, getcontext

import pytest

from product_api.company_reports.company_card_v2.finance import FORM_BY_CODE, build_finance_views
from product_api.company_reports.company_card_v2.models import FinanceBasisV1, FinanceCellV1
from product_api.company_reports.company_card_v2.public_h2 import _money
from product_api.company_reports.persistence.presentations import (
    H2_PUBLICATION_POLICY_V1,
    H2_PUBLICATION_POLICY_V2,
    H2_PUBLICATION_POLICY_V3,
    H2_PUBLICATION_POLICY_VERSIONS,
)


def _cell(code: str, year: int, value: str, *, form: str | None = None) -> FinanceCellV1:
    return FinanceCellV1(
        form=form or FORM_BY_CODE[code],
        code=code,
        year=year,
        state="available_nonzero",
        value=Decimal(value),
    )


def _complete_basis() -> FinanceBasisV1:
    return FinanceBasisV1(cells=tuple(
        _cell(code, year, str((year - 2018) * 10 + index + 1))
        for year in range(2019, 2026)
        for index, code in enumerate(sorted(FORM_BY_CODE))
    ))


def test_finance_policy_uses_exact_forms_and_independent_view_anchors() -> None:
    cells = list(_complete_basis().cells)
    # A newer wrong-form value is not an eligible F1 source.  F5 may still
    # anchor independently on a different, valid retained row.
    cells.append(_cell("1250", 2026, "999", form="financial_results"))
    cells.append(_cell("2110", 2026, "999"))
    views = build_finance_views(FinanceBasisV1(cells=tuple(cells)))

    assert views["F1"]["year"] == 2025
    assert views["F3"]["anchor_year"] == 2025
    assert views["F5"]["anchor_year"] == 2026


def test_finance_geometry_and_provider_zero_are_not_interpolated() -> None:
    views = build_finance_views(_complete_basis(), anchor_year=2025)
    f1 = views["F1"]
    assert f1 is not None
    assert f1["axis"][1] == max(
        f1["available_without_inventory"],
        f1["difference"],
        f1["values"]["1250"] + f1["values"]["1240"],
    )
    f2 = views["F2"]
    assert f2 is not None
    assert all(
        period["axis"] == (Decimal("0"), Decimal("100"))
        for period in f2["periods"]
        if period["mode"] == "stacked_100"
    )

    zero_basis = FinanceBasisV1(cells=tuple(
        FinanceCellV1(form=cell.form, code=cell.code, year=cell.year, state="zero_unverified")
        if (cell.code, cell.year) == ("1250", 2025) else cell
        for cell in _complete_basis().cells
    ))
    assert build_finance_views(zero_basis, anchor_year=2025)["F1"]["year"] == 2024


def test_money_formatter_preserves_three_million_decimals_and_context() -> None:
    huge_source = "123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456"
    original = getcontext().prec
    try:
        getcontext().prec = 8
        formatted = _money(Decimal("273325"))
        huge = _money(Decimal(huge_source))
    finally:
        getcontext().prec = original
    assert formatted.display_exact == "273,325 млн ₽"
    assert formatted.display_compact == "273,3 млн ₽"
    assert huge.source_thousand_decimal == huge_source
    assert huge.rub_decimal == f"{huge_source}000"
    assert huge.million_decimal == f"{huge_source[:-3]}.{huge_source[-3:]}"
    assert huge.display_exact == f"{huge_source[:-3]},{huge_source[-3:]} млн ₽"
    assert huge.display_compact == f"{huge_source[:-3]},5 млн ₽"
    assert _money(Decimal("-10")).display_exact == "−0,010 млн ₽"


def test_saved_publication_policy_is_an_explicit_closed_set() -> None:
    assert H2_PUBLICATION_POLICY_V1 in H2_PUBLICATION_POLICY_VERSIONS
    assert H2_PUBLICATION_POLICY_V2 in H2_PUBLICATION_POLICY_VERSIONS
    assert H2_PUBLICATION_POLICY_V3 in H2_PUBLICATION_POLICY_VERSIONS
    assert len(H2_PUBLICATION_POLICY_VERSIONS) == 3
