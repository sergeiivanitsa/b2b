from __future__ import annotations

from datetime import timezone
from decimal import Decimal
from typing import Protocol
from zoneinfo import ZoneInfo

from .canonical_json import canonical_digest, canonical_json_bytes
from .models import CompanyCardV2Snapshot
from .privacy import assert_public_boundary_safe
from .public_h2_models import (
    BLOCK_ORDER, COVERAGE_BLOCKS, CompanyPublicH2Response, PublicH2Action,
    PublicChartAxis, PublicChartInterval, PublicChartPoint, PublicF1, PublicF2,
    PublicF2Period, PublicF3, PublicF3Point, PublicF3SeriesSummary, PublicF4,
    PublicF5, PublicF5Cell, PublicF5Row, PublicFinanceMoney, PublicFinanceSegment,
    PublicH2Blocks, PublicH2Breadcrumb, PublicH2ClaimCta, PublicH2CoverageItem,
    PublicH2Address, PublicH2Identity, PublicH2Limitation, PublicH2Narrative, PublicH2Requisites,
    PublicH2SourceItem,
)

_MOSCOW = ZoneInfo("Europe/Moscow")


class NarrativeBindingProtocol(Protocol):
    """Validated in-memory boundary owned by fixture/golden callers only."""

    @property
    def narrative(self) -> PublicH2Narrative: ...


def _utc_z(value) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_public_h2(
    snapshot: CompanyCardV2Snapshot,
    *,
    narrative_binding: NarrativeBindingProtocol,
    fixture_finance_views: dict[str, object] | None = None,
) -> CompanyPublicH2Response:
    """Build only from an already validated, injected narrative binding.

    Iteration 20 has no artifact generation, storage, or runtime fallback.
    Callers that cannot supply this in-memory binding must keep the H2 pin
    unresolved and return ``report_not_eligible`` instead.
    """
    narrative = narrative_binding.narrative
    if not isinstance(narrative, PublicH2Narrative):
        raise ValueError("narrative binding is not validated")
    checked_at = _utc_z(snapshot.generated_at)
    checked_date = snapshot.generated_at.astimezone(_MOSCOW).date().isoformat()
    name = snapshot.counterparty.full_name or snapshot.counterparty.short_name or snapshot.subject_inn
    canonical_path = f"/company/{snapshot.subject_inn}-company"
    finance_blocks = _fixture_finance_blocks(fixture_finance_views) if fixture_finance_views is not None else {}
    limitations = [
        PublicH2Limitation(code=item.code, field_id=item.field, message="Данные недоступны в текущем подтверждённом контуре.")
        for item in (*snapshot.limitations, *snapshot.arbitration_basis.limitations)
    ]
    # Every unavailable leaf has an explicit linked limitation.  Do not reuse
    # private/provider text as a message.
    # Requisites are deliberately conservative: the available snapshot core
    # is public, but the complete requisites evidence family is not.
    limitations.append(PublicH2Limitation(code="requisites_partial", block_id="requisites", field_id=None, message="Часть реквизитов недоступна в текущем подтверждённом контуре."))
    for block in (*COVERAGE_BLOCKS[2:7], *COVERAGE_BLOCKS[7:12]):
        if block.startswith("finance_") and finance_blocks.get(block) is not None:
            continue
        code = f"{block}_gate_closed"
        limitations.append(PublicH2Limitation(code=code, block_id=block, field_id=None, message="Раздел недоступен до закрытия обязательного evidence gate."))
    # Deduplicate deterministically without accepting conflicting text.
    unique: dict[str, PublicH2Limitation] = {}
    for limitation in limitations:
        unique.setdefault(limitation.code, limitation)
    limitations = sorted(unique.values(), key=lambda item: (COVERAGE_BLOCKS.index(item.block_id) if item.block_id in COVERAGE_BLOCKS else 99, item.field_id or "", item.code))
    coverage = []
    for block in COVERAGE_BLOCKS:
        if block == "requisites":
            coverage.append(PublicH2CoverageItem(block_id=block, state="partial", population_scope="not_applicable", limitation_codes=("requisites_partial",)))
        elif block == "narrative":
            coverage.append(PublicH2CoverageItem(block_id=block, state="available", population_scope="not_applicable", limitation_codes=()))
        elif block == "sources_limitations":
            coverage.append(PublicH2CoverageItem(block_id=block, state="available", population_scope="not_applicable", limitation_codes=()))
        elif block.startswith("finance_") and finance_blocks.get(block) is not None:
            coverage.append(PublicH2CoverageItem(block_id=block, state="available", population_scope="not_applicable", limitation_codes=()))
        else:
            coverage.append(PublicH2CoverageItem(block_id=block, state="gate_closed", population_scope="not_applicable", limitation_codes=(f"{block}_gate_closed",)))
    payload = {
        "contract_version": "company_public_h2_v1", "report_id": snapshot.report_id, "report_version": "3",
        "chart_facts_version": snapshot.chart_facts.version, "chart_facts_hash": snapshot.chart_facts.hash,
        "snapshot_capability": "card_v2", "projection_scope": "latest_unpublished", "canonical_path": canonical_path,
        "indexable": False, "checked_at": checked_at, "checked_date": checked_date, "checked_date_display": checked_date,
        "identity": PublicH2Identity(display_name=name, legal_full_name=name, short_name=snapshot.counterparty.short_name,
            inn=snapshot.counterparty.inn, ogrn=snapshot.counterparty.ogrn, kpp=snapshot.counterparty.kpp,
            registration_date=snapshot.counterparty.registration_date.isoformat() if snapshot.counterparty.registration_date else None,
            dissolution_date=snapshot.counterparty.dissolution_date.isoformat() if snapshot.counterparty.dissolution_date else None).model_dump(mode="json"),
        "narrative": narrative.model_dump(mode="json"), "block_order": BLOCK_ORDER,
        "blocks": PublicH2Blocks(
            requisites=PublicH2Requisites(address=(PublicH2Address(display=snapshot.counterparty.address, is_inaccuracy=snapshot.counterparty.address_inaccuracy) if snapshot.counterparty.address else None)),
            **finance_blocks,
        ).model_dump(mode="json"),
        "coverage": [item.model_dump(mode="json") for item in coverage],
        "sources": [PublicH2SourceItem(dataset=dataset, received_at=checked_at, normalization_version="company_card_v2_v1", evidence_version=snapshot.evidence_version).model_dump(mode="json") for dataset in ("counterparty", "finance", "arbitration")],
        "limitations": [item.model_dump(mode="json") for item in limitations],
        "actions": [PublicH2Action(action_id="check_another_company", label="Проверить другую компанию", path="/company").model_dump(mode="json"), PublicH2Action(action_id="prepare_claim", label="Подготовить претензию", path=f"/claims?report_id={snapshot.report_id}").model_dump(mode="json")],
        "breadcrumbs": [PublicH2Breadcrumb(label="Компании", path="/company", current=False).model_dump(mode="json"), PublicH2Breadcrumb(label=name, path=canonical_path, current=True).model_dump(mode="json")],
        "primary_claim_cta": PublicH2ClaimCta(path=f"/claims?report_id={snapshot.report_id}").model_dump(mode="json"),
    }
    response = CompanyPublicH2Response(**payload, projection_digest=canonical_digest(payload))
    if len(canonical_json_bytes(response.model_dump(mode="json"))) > 524288:
        raise ValueError("public_projection_too_large")
    assert_public_boundary_safe(response.model_dump(mode="json"))
    return response


def _decimal(value: Decimal) -> str:
    rendered = format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else format(value, "f")
    return "0" if rendered in {"", "-0"} else rendered


def _money(value: Decimal) -> PublicFinanceMoney:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("fixture finance values must be finite Decimal")
    source = _decimal(value)
    rub = _decimal(value * Decimal("1000"))
    million = _decimal(value / Decimal("1000"))
    return PublicFinanceMoney(
        source_thousand_decimal=source,
        rub_decimal=rub,
        million_decimal=million,
        display_exact=f"{rub} ₽",
        display_compact=f"{million} млн ₽",
    )


def _axis(value: tuple[Decimal, Decimal]) -> PublicChartAxis:
    return PublicChartAxis(axis_min_decimal=_decimal(value[0]), axis_max_decimal=_decimal(value[1]))


def _interval(start: Decimal, end: Decimal) -> PublicChartInterval:
    return PublicChartInterval(start_ratio_decimal=_decimal(start), end_ratio_decimal=_decimal(end))


def _fixture_finance_blocks(views: dict[str, object]) -> dict[str, object]:
    """Convert explicit fixture facts to strict public DTOs.

    This is a pure golden-test seam. Runtime H2 resolution never supplies this
    argument and therefore keeps all finance blocks closed until their evidence
    gate is product-approved.
    """
    required = {"F1", "F2", "F3", "F4", "F5"}
    if set(views) != required:
        raise ValueError("fixture finance views must contain exactly F1..F5")
    return {
        "finance_f1": _f1(views["F1"]),
        "finance_f2": _f2(views["F2"]),
        "finance_f3": _f3(views["F3"]),
        "finance_f4": _f4(views["F4"]),
        "finance_f5": _f5(views["F5"]),
    }


def _mapping(value: object, *, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} fixture is invalid")
    return value


def _f1(value: object) -> PublicF1 | None:
    if value is None:
        return None
    item = _mapping(value, label="F1")
    values = _mapping(item.get("values"), label="F1 values")
    cash, investments, receivables, liabilities = (values.get(code) for code in ("1250", "1240", "1230", "1500"))
    if not all(isinstance(number, Decimal) for number in (cash, investments, receivables, liabilities)):
        raise ValueError("F1 money is invalid")
    running_cash = cash
    running_investments = cash + investments
    running_receivables = running_investments + receivables
    return PublicF1(
        year=item["year"],
        cash_1250=_money(cash), investments_1240=_money(investments),
        receivables_1230=_money(receivables), short_liabilities_1500=_money(liabilities),
        available_without_inventory=_money(item["available_without_inventory"]),
        difference=_money(item["difference"]), axis=_axis(item["axis"]),
        segments=(
            PublicFinanceSegment(metric_id="1250", value=_money(cash), geometry=_interval(Decimal("0"), running_cash)),
            PublicFinanceSegment(metric_id="1240", value=_money(investments), geometry=_interval(running_cash, running_investments)),
            PublicFinanceSegment(metric_id="1230", value=_money(receivables), geometry=_interval(running_investments, running_receivables)),
            PublicFinanceSegment(metric_id="1500", value=_money(liabilities), geometry=_interval(Decimal("0"), liabilities)),
        ),
    )


def _f2(value: object) -> PublicF2:
    item = _mapping(value, label="F2")
    periods: list[PublicF2Period] = []
    for raw in item["periods"]:
        period = _mapping(raw, label="F2 period")
        if period["state"] == "gap":
            periods.append(PublicF2Period(year=period["year"], state="gap", mode="unavailable", geometry_by_metric=(None, None)))
            continue
        money = {key: _money(period[key]) for key in ("equity", "long_liabilities", "short_liabilities", "debt", "denominator")}
        if period["state"] == "denominator_unavailable":
            periods.append(PublicF2Period(
                year=period["year"], state="denominator_unavailable", mode="unavailable",
                equity_1300=money["equity"], long_liabilities_1400=money["long_liabilities"],
                short_liabilities_1500=money["short_liabilities"], debt=money["debt"], denominator=money["denominator"],
                geometry_by_metric=(None, None),
            ))
            continue
        equity_share, debt_share = period["equity_share"], period["debt_share"]
        signed = period["mode"] == "diverging_signed"
        geometries = (
            _interval(Decimal("0"), equity_share),
            _interval(Decimal("0"), debt_share) if signed else _interval(equity_share, Decimal("100")),
        )
        periods.append(PublicF2Period(
            year=period["year"], state="available", mode=period["mode"],
            equity_1300=money["equity"], long_liabilities_1400=money["long_liabilities"],
            short_liabilities_1500=money["short_liabilities"], debt=money["debt"], denominator=money["denominator"],
            equity_share_decimal=_decimal(equity_share), debt_share_decimal=_decimal(debt_share),
            axis=_axis(period["axis"]), geometry_by_metric=geometries,
        ))
    return PublicF2(anchor_year=item["anchor_year"], window_start_year=item["window_start_year"], periods=tuple(periods))


def _summary(value: object, metric_id: str) -> PublicF3SeriesSummary:
    item = _mapping(value, label="F3 summary")
    change = item["change"]
    return PublicF3SeriesSummary(
        metric_id=metric_id, comparison_start_year=item["comparison_start_year"],
        comparison_end_year=item["comparison_end_year"],
        multiple_decimal=_decimal(item["multiple"]) if item["multiple"] is not None else None,
        change=_money(change) if change is not None else None,
        axis=_axis(item["axis"]) if item["axis"] is not None else None,
    )


def _f3(value: object) -> PublicF3:
    item = _mapping(value, label="F3")
    points = []
    for raw in item["points"]:
        point = _mapping(raw, label="F3 point")
        revenue, assets = point["revenue"], point["assets"]
        points.append(PublicF3Point(
            year=point["year"], revenue_2110=_money(revenue) if revenue is not None else None,
            assets_1600=_money(assets) if assets is not None else None,
            revenue_yoy_decimal=_decimal(point["revenue_yoy"]) if point["revenue_yoy"] is not None else None,
            assets_yoy_decimal=_decimal(point["assets_yoy"]) if point["assets_yoy"] is not None else None,
            geometry_by_metric=(
                PublicChartPoint(ratio_decimal=_decimal(revenue)) if revenue is not None else None,
                PublicChartPoint(ratio_decimal=_decimal(assets)) if assets is not None else None,
            ),
        ))
    return PublicF3(
        anchor_year=item["anchor_year"], window_start_year=item["window_start_year"], points=tuple(points),
        revenue_summary=_summary(item["revenue_summary"], "revenue_2110"),
        assets_summary=_summary(item["assets_summary"], "assets_1600"),
    )


def _f4(value: object) -> PublicF4 | None:
    if value is None:
        return None
    item = _mapping(value, label="F4")
    ratio_keys = ("revenue_per_100", "gross_per_100", "operating_per_100", "net_per_100")
    ratios = tuple(item[key] for key in ratio_keys)
    geometry = tuple(_interval(Decimal("0"), ratio) if ratio is not None else None for ratio in ratios)
    return PublicF4(
        year=item["year"], revenue_2110=_money(item["revenue"]), gross_2100=_money(item["gross"]),
        operating_2200=_money(item["operating"]), net_2400=_money(item["net"]), mode=item["mode"],
        revenue_per_100_decimal=_decimal(ratios[0]) if ratios[0] is not None else None,
        gross_per_100_decimal=_decimal(ratios[1]) if ratios[1] is not None else None,
        operating_per_100_decimal=_decimal(ratios[2]) if ratios[2] is not None else None,
        net_per_100_decimal=_decimal(ratios[3]) if ratios[3] is not None else None,
        axis=_axis(item["axis"]) if item["axis"] is not None else None,
        geometry_by_metric=geometry,
    )


def _f5(value: object) -> PublicF5:
    item = _mapping(value, label="F5")
    rows = []
    for raw in item["rows"]:
        row = _mapping(raw, label="F5 row")
        rows.append(PublicF5Row(
            metric_id=row["metric_id"], label=row["label"],
            cells=tuple(PublicF5Cell(
                year=cell["year"], value=_money(cell["value"]) if cell["value"] is not None else None,
                yoy_decimal=_decimal(cell["yoy"]) if cell["yoy"] is not None else None,
            ) for cell in row["cells"]),
        ))
    return PublicF5(anchor_year=item["anchor_year"], years=tuple(item["years"]), rows=tuple(rows))


__all__ = ["NarrativeBindingProtocol", "build_public_h2"]
