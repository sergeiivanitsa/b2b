from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from product_api.company_reports.models import (
    FinanceFacts,
    FinanceForm,
    FinancialIndicatorSeries,
    FinancialPeriod,
    NormalizationWarning,
)
from product_api.providers.datanewton import FINANCE_ENDPOINT, DataNewtonResult

from .common import (
    optional_string,
    parse_decimal,
    source_metadata,
    validate_result,
    warning,
)

_FORMS: tuple[tuple[str, FinanceForm], ...] = (
    ("balances", FinanceForm.BALANCE),
    ("fin_results", FinanceForm.FINANCIAL_RESULTS),
    ("money_flow", FinanceForm.CASH_FLOW),
)

_PERIOD_FIELDS: dict[tuple[FinanceForm, str], str] = {
    (FinanceForm.BALANCE, "1600"): "total_assets",
    (FinanceForm.BALANCE, "1100"): "non_current_assets",
    (FinanceForm.BALANCE, "1200"): "current_assets",
    (FinanceForm.BALANCE, "1210"): "inventories",
    (FinanceForm.BALANCE, "1230"): "accounts_receivable",
    (FinanceForm.BALANCE, "1250"): "cash_and_equivalents",
    (FinanceForm.BALANCE, "1300"): "equity",
    (FinanceForm.BALANCE, "1400"): "long_term_liabilities",
    (FinanceForm.BALANCE, "1500"): "short_term_liabilities",
    (FinanceForm.BALANCE, "1510"): "short_term_borrowings",
    (FinanceForm.BALANCE, "1520"): "accounts_payable",
    (FinanceForm.FINANCIAL_RESULTS, "2110"): "revenue",
    (FinanceForm.FINANCIAL_RESULTS, "2120"): "cost_of_sales",
    (FinanceForm.FINANCIAL_RESULTS, "2100"): "gross_profit",
    (FinanceForm.FINANCIAL_RESULTS, "2200"): "operating_profit",
    (FinanceForm.FINANCIAL_RESULTS, "2300"): "profit_before_tax",
    (FinanceForm.FINANCIAL_RESULTS, "2400"): "net_profit",
    (FinanceForm.CASH_FLOW, "4400"): "net_cash_flow",
    (FinanceForm.CASH_FLOW, "4450"): "cash_at_start",
    (FinanceForm.CASH_FLOW, "4500"): "cash_at_end",
}


@dataclass
class _Candidate:
    form: FinanceForm
    code: str
    name: str | None
    values: dict[int, Decimal | None]
    chosen_path: str
    source_paths: list[str]

    @property
    def rank(self) -> tuple[int, str]:
        return (_path_depth(self.chosen_path), self.chosen_path)


def normalize_finance(result: DataNewtonResult) -> FinanceFacts:
    payload = validate_result(
        result,
        expected_dataset="finance",
        expected_endpoint=FINANCE_ENDPOINT,
    )
    warnings: list[NormalizationWarning] = []
    candidates: dict[tuple[FinanceForm, str], _Candidate] = {}
    years: set[int] = set()
    okud: dict[FinanceForm, str | None] = {}

    for provider_name, form in _FORMS:
        form_payload = payload.get(provider_name)
        if form_payload is None:
            okud[form] = None
            continue
        if not isinstance(form_payload, dict):
            warnings.append(
                warning(
                    "finance_form_invalid",
                    f"$.{provider_name}",
                    "financial form must be an object",
                )
            )
            okud[form] = None
            continue
        okud[form] = optional_string(form_payload.get("okud"))
        _collect_declared_years(
            form_payload.get("years"),
            path=f"$.{provider_name}.years",
            years=years,
            warnings=warnings,
        )
        _walk_form(
            form_payload,
            form=form,
            path=f"$.{provider_name}",
            years=years,
            candidates=candidates,
            warnings=warnings,
        )

    series = [
        FinancialIndicatorSeries(
            form=candidate.form,
            code=candidate.code,
            name=candidate.name,
            values_by_year=dict(sorted(candidate.values.items())),
            source_paths=sorted(set(candidate.source_paths)),
        )
        for _, candidate in sorted(
            candidates.items(),
            key=lambda item: (_form_order(item[0][0]), item[0][1]),
        )
    ]
    sorted_years = sorted(years)
    lookup = {(item.form, item.code): item.values_by_year for item in series}
    periods = [_period(year, lookup) for year in sorted_years]
    source = source_metadata(result, warnings)
    return FinanceFacts(
        source=source,
        years=sorted_years,
        latest_year=sorted_years[-1] if sorted_years else None,
        balance_okud=okud.get(FinanceForm.BALANCE),
        financial_results_okud=okud.get(FinanceForm.FINANCIAL_RESULTS),
        cash_flow_okud=okud.get(FinanceForm.CASH_FLOW),
        indicators=series,
        periods=periods,
        warnings=source.warnings,
    )


def _walk_form(
    value: object,
    *,
    form: FinanceForm,
    path: str,
    years: set[int],
    candidates: dict[tuple[FinanceForm, str], _Candidate],
    warnings: list[NormalizationWarning],
) -> None:
    if isinstance(value, dict):
        if "code" in value and isinstance(value.get("sum"), dict):
            _collect_indicator(
                value,
                form=form,
                path=path,
                years=years,
                candidates=candidates,
                warnings=warnings,
            )
        for key in sorted(value):
            _walk_form(
                value[key],
                form=form,
                path=f"{path}.{key}",
                years=years,
                candidates=candidates,
                warnings=warnings,
            )
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk_form(
                item,
                form=form,
                path=f"{path}[{index}]",
                years=years,
                candidates=candidates,
                warnings=warnings,
            )


def _collect_indicator(
    value: dict[str, Any],
    *,
    form: FinanceForm,
    path: str,
    years: set[int],
    candidates: dict[tuple[FinanceForm, str], _Candidate],
    warnings: list[NormalizationWarning],
) -> None:
    code = optional_string(value.get("code"))
    if not code:
        warnings.append(
            warning(
                "finance_indicator_missing_code",
                path,
                "financial indicator without a code was skipped",
            )
        )
        return
    raw_sum = value["sum"]
    values: dict[int, Decimal | None] = {}
    for raw_year, raw_value in sorted(raw_sum.items(), key=lambda item: str(item[0])):
        year = _parse_year(raw_year)
        if year is None:
            warnings.append(
                warning(
                    "finance_invalid_year",
                    f"{path}.sum",
                    "financial period key could not be parsed",
                )
            )
            continue
        years.add(year)
        values[year] = parse_decimal(
            raw_value,
            path=f"{path}.sum.{year}",
            warnings=warnings,
        )

    candidate = _Candidate(
        form=form,
        code=code,
        name=optional_string(value.get("name")),
        values=values,
        chosen_path=path,
        source_paths=[path],
    )
    key = (form, code)
    existing = candidates.get(key)
    if existing is None:
        candidates[key] = candidate
        return
    all_paths = sorted(set([*existing.source_paths, path]))
    if existing.name == candidate.name and existing.values == candidate.values:
        existing.source_paths = all_paths
        return

    warnings.append(
        warning(
            "finance_duplicate_conflict",
            path,
            "duplicate financial indicator has conflicting metadata or values",
        )
    )
    if candidate.rank < existing.rank:
        candidate.source_paths = all_paths
        candidates[key] = candidate
    else:
        existing.source_paths = all_paths


def _collect_declared_years(
    value: object,
    *,
    path: str,
    years: set[int],
    warnings: list[NormalizationWarning],
) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        warnings.append(
            warning("finance_years_invalid", path, "years field must be an array")
        )
        return
    for item in value:
        year = _parse_year(item)
        if year is None:
            warnings.append(
                warning(
                    "finance_invalid_year",
                    path,
                    "financial period value could not be parsed",
                )
            )
        else:
            years.add(year)


def _parse_year(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _period(
    year: int,
    lookup: dict[tuple[FinanceForm, str], dict[int, Decimal | None]],
) -> FinancialPeriod:
    values: dict[str, object] = {"year": year}
    for indicator_key, field_name in _PERIOD_FIELDS.items():
        values[field_name] = lookup.get(indicator_key, {}).get(year)
    return FinancialPeriod(**values)


def _path_depth(path: str) -> int:
    return path.count(".") + path.count("[")


def _form_order(form: FinanceForm) -> int:
    return {
        FinanceForm.BALANCE: 0,
        FinanceForm.FINANCIAL_RESULTS: 1,
        FinanceForm.CASH_FLOW: 2,
    }[form]
