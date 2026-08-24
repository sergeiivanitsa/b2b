from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal, ROUND_HALF_UP, localcontext

from .canonical_json import canonical_digest
from .models import ChartFactV1, ChartFactsV1, FinanceBasisV1, FinanceCellV1, LimitationV1

APPROVED_FINANCE_CELL_COUNT = 12
BALANCE_FORM = "balance"
FINANCIAL_RESULTS_FORM = "financial_results"
APPROVED_CODES = frozenset({"1210", "1230", "1240", "1250", "1300", "1400", "1500", "1600", "2100", "2110", "2200", "2400"})
F5_ROWS = (
    ("2110", "Продажи"), ("1600", "Всё имущество"), ("1250", "Деньги на счетах"),
    ("1240", "Финансовые вложения"), ("1230", "Долги покупателей"), ("1210", "Запасы"),
    ("1500", "Ближайшие обязательства"), ("1300", "Свои средства"), ("2400", "Чистая прибыль"),
)


def classify_finance_cell(*, form: str, code: str, year: int, lexemes: Iterable[str] | None, transport_valid: bool) -> FinanceCellV1:
    """Classify a closed finance leaf without turning absent/zero data into facts."""
    values = tuple(lexemes or ())
    if not values:
        return FinanceCellV1(form=form, code=code, year=year, state="missing")
    if not transport_valid:
        return FinanceCellV1(form=form, code=code, year=year, state="decimal_transport_lossy")
    from .decimal_transport import DecimalTransportError, parse_source_decimal
    try:
        parsed = tuple(parse_source_decimal(item).value for item in values)
    except DecimalTransportError:
        return FinanceCellV1(form=form, code=code, year=year, state="invalid")
    if any(value == 0 for value in parsed):
        # A provider zero is explicitly non-numeric even if duplicated with
        # a nonzero source leaf: its meaning has not passed evidence.
        return FinanceCellV1(form=form, code=code, year=year, state="zero_unverified")
    if len(set(parsed)) != 1:
        return FinanceCellV1(form=form, code=code, year=year, state="conflict")
    return FinanceCellV1(form=form, code=code, year=year, state="available_nonzero", value=parsed[0])


def build_chart_facts(basis: FinanceBasisV1) -> ChartFactsV1:
    """Create deterministic availability-only facts.

    Formula-specific F1–F5 geometry is deliberately null unless its closed
    inputs are present in the supplied basis. This function never invents a
    missing or provider-zero value.
    """
    facts: list[ChartFactV1] = []
    for cell in sorted(basis.cells, key=lambda item: (item.form, item.code, item.year)):
        limitations = () if cell.state == "available_nonzero" else (f"finance_{cell.state}",)
        facts.append(ChartFactV1(key=f"{cell.form}:{cell.code}:{cell.year}", value=cell.value, geometry=cell.value, limitation_codes=limitations))
    payload = {"version": "company_card_chart_facts_v1", "unit_policy": "datanewton_finance_thousand_rub_v2", "facts": [item.model_dump(mode="json") for item in facts]}
    return ChartFactsV1(facts=tuple(facts), hash=canonical_digest(payload))


def finance_limitations(basis: FinanceBasisV1) -> tuple[LimitationV1, ...]:
    return tuple(
        LimitationV1(code=f"finance_{cell.state}", field=f"finance.{cell.form}.{cell.code}.{cell.year}")
        for cell in basis.cells if cell.state != "available_nonzero"
    )


def build_finance_views(basis: FinanceBasisV1, *, anchor_year: int | None = None) -> dict[str, object]:
    """Produce all five closed finance views using Decimal-only arithmetic.

    The return is a pure internal Chart Facts representation. Values remain in
    source thousand-ruble units; missing/zero/conflict cells never participate
    in a calculation. ``anchor_year`` is injected by the writer, so the pure
    calculation never reads the wall clock.
    """
    cells = {(cell.code, cell.year): cell for cell in basis.cells if cell.code in APPROVED_CODES}
    years = sorted({year for _, year in cells})
    if anchor_year is None:
        anchor_year = max(years) if years else None
    if anchor_year is None:
        return {name: None for name in ("F1", "F2", "F3", "F4", "F5")}
    value = lambda code, year: _available(cells.get((code, year)))
    return {
        "F1": _f1(value, anchor_year),
        "F2": _f2(value, anchor_year),
        "F3": _f3(value, anchor_year),
        "F4": _f4(value, anchor_year),
        "F5": _f5(value, anchor_year),
    }


def _f1(value, year: int) -> dict[str, object] | None:
    required = {code: value(code, year) for code in ("1250", "1240", "1230", "1500")}
    if any(item is None for item in required.values()):
        return None
    available = required["1250"] + required["1240"] + required["1230"]
    difference = available - required["1500"]
    all_values = [*required.values(), difference]
    return {"view_id": "finance_f1_liquidity", "year": year, "values": required, "available_without_inventory": available, "difference": difference, "axis": _axis(all_values), "limitations": ("receivables_collection_unassessed",)}


def _f2(value, anchor: int) -> dict[str, object]:
    periods: list[dict[str, object]] = []
    for year in range(anchor - 6, anchor + 1):
        equity, long_debt, short_debt = value("1300", year), value("1400", year), value("1500", year)
        if None in (equity, long_debt, short_debt):
            periods.append({"year": year, "state": "gap", "equity": None, "long_liabilities": None, "short_liabilities": None, "debt": None, "denominator": None, "equity_share": None, "debt_share": None, "mode": "unavailable", "axis": None})
            continue
        debt = long_debt + short_debt
        denominator = equity + debt
        if denominator <= 0:
            periods.append({"year": year, "state": "denominator_unavailable", "equity": equity, "long_liabilities": long_debt, "short_liabilities": short_debt, "debt": debt, "denominator": denominator, "equity_share": None, "debt_share": None, "mode": "unavailable", "axis": None, "limitations": ("finance_denominator_non_positive",)})
            continue
        equity_share, debt_share = _shares(equity, debt, denominator)
        signed = equity_share < 0 or debt_share < 0
        periods.append({"year": year, "state": "available", "equity": equity, "long_liabilities": long_debt, "short_liabilities": short_debt, "debt": debt, "denominator": denominator, "equity_share": equity_share, "debt_share": debt_share, "mode": "diverging_signed" if signed else "stacked_100", "axis": _axis([equity_share, debt_share])})
    return {"view_id": "finance_f2_funding", "anchor_year": anchor, "window_start_year": anchor - 6, "periods": tuple(periods)}


def _f3(value, anchor: int) -> dict[str, object]:
    points: list[dict[str, object]] = []
    sequences = {"revenue": [], "assets": []}
    for year in range(anchor - 6, anchor + 1):
        revenue, assets = value("2110", year), value("1600", year)
        sequences["revenue"].append((year, revenue)); sequences["assets"].append((year, assets))
        points.append({"year": year, "revenue": revenue, "assets": assets, "revenue_yoy": _yoy(value("2110", year - 1), revenue), "assets_yoy": _yoy(value("1600", year - 1), assets)})
    return {"view_id": "finance_f3_growth", "anchor_year": anchor, "window_start_year": anchor - 6, "points": tuple(points), "revenue_summary": _series_summary(sequences["revenue"]), "assets_summary": _series_summary(sequences["assets"])}


def _f4(value, year: int) -> dict[str, object] | None:
    revenue, gross, operating, net = (value(code, year) for code in ("2110", "2100", "2200", "2400"))
    if None in (revenue, gross, operating, net):
        return None
    result: dict[str, object] = {"view_id": "finance_f4_profit_per_100", "year": year, "revenue": revenue, "gross": gross, "operating": operating, "net": net}
    if revenue <= 0:
        result.update({"mode": "denominator_unavailable", "revenue_per_100": None, "gross_per_100": None, "operating_per_100": None, "net_per_100": None, "axis": None, "limitations": ("finance_denominator_non_positive",)})
    else:
        ratios = [_ratio(gross, revenue), _ratio(operating, revenue), _ratio(net, revenue)]
        result.update({"mode": "per_100", "revenue_per_100": Decimal("100"), "gross_per_100": ratios[0], "operating_per_100": ratios[1], "net_per_100": ratios[2], "axis": _axis([Decimal("100"), *ratios])})
    return result


def _f5(value, anchor: int) -> dict[str, object]:
    years = tuple(range(anchor - 6, anchor + 1))
    rows = []
    for code, label in F5_ROWS:
        cells = tuple({"year": year, "value": value(code, year), "yoy": _yoy(value(code, year - 1), value(code, year))} for year in years)
        rows.append({"metric_id": code, "label": label, "cells": cells})
    return {"view_id": "finance_f5_yearly_table", "anchor_year": anchor, "years": years, "rows": tuple(rows)}


def _available(cell: FinanceCellV1 | None) -> Decimal | None:
    return cell.value if cell is not None and cell.state == "available_nonzero" else None


def _ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 34
        context.rounding = ROUND_HALF_UP
        return (numerator / denominator * Decimal("100")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _shares(equity: Decimal, debt: Decimal, denominator: Decimal) -> tuple[Decimal, Decimal]:
    with localcontext() as context:
        context.prec = 34
        context.rounding = ROUND_HALF_UP
        unrounded = (
            equity / denominator * Decimal("100"),
            debt / denominator * Decimal("100"),
        )
        shares = [item.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP) for item in unrounded]
        residual = Decimal("100") - sum(shares, Decimal("0"))
        # Allocate the quantisation residual to the greatest absolute
        # remainder; the documented deterministic tie order is equity, debt.
        winner = max(range(2), key=lambda index: (abs(unrounded[index] - shares[index]), -index))
        shares[winner] += residual
        return shares[0], shares[1]


def _yoy(previous: Decimal | None, current: Decimal | None) -> Decimal | None:
    if previous is None or current is None or previous <= 0:
        return None
    return _ratio(current - previous, previous)


def _series_summary(values: list[tuple[int, Decimal | None]]) -> dict[str, object]:
    available = [(year, number) for year, number in values if number is not None]
    if len(available) < 2:
        return {"comparison_start_year": None, "comparison_end_year": None, "multiple": None, "change": None, "axis": _axis([number for _, number in available]) if available else None}
    (first_year, first), (last_year, last) = available[0], available[-1]
    multiple = (last / first).quantize(Decimal("0.000001")) if first > 0 and last > 0 else None
    return {"comparison_start_year": first_year, "comparison_end_year": last_year, "multiple": multiple, "change": last - first, "axis": _axis([number for _, number in available])}


def _axis(values: Iterable[Decimal]) -> tuple[Decimal, Decimal]:
    values = tuple(values)
    return min(Decimal("0"), *values), max(Decimal("0"), *values)


__all__ = ["APPROVED_CODES", "APPROVED_FINANCE_CELL_COUNT", "F5_ROWS", "build_chart_facts", "build_finance_views", "classify_finance_cell", "finance_limitations"]
