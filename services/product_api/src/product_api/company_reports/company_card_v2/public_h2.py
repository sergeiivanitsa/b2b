from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext
from hashlib import sha256
from typing import Protocol
from zoneinfo import ZoneInfo

from product_api.company_reports.aggregate import CompanyReport

from .canonical_json import canonical_digest, canonical_json_bytes
from .finance import F5_ROWS, FORM_BY_CODE, build_finance_views
from .models import CompanyCardV2Snapshot, CompanyCardV2SnapshotV2
from .narrative.catalog import (
    FALLBACK_DESCRIPTION,
    FALLBACK_PROFILE_ID,
    FALLBACK_RENDERER_VERSION,
)
from .privacy import assert_public_boundary_safe
from .public_h2_models import (
    BLOCK_ORDER, COVERAGE_BLOCKS, CompanyPublicH2Response, PublicH2Action,
    PublicChartAxis, PublicChartInterval, PublicChartPoint, PublicF1, PublicF2,
    PublicF2Period, PublicF3, PublicF3Point, PublicF3SeriesSummary, PublicF4,
    PublicF5, PublicF5Cell, PublicF5Row, PublicFinanceMoney, PublicFinanceSegment,
    PublicH2Blocks, PublicH2Breadcrumb, PublicH2ClaimCta, PublicH2CoverageItem,
    PublicActivity, PublicH2Address, PublicH2Identity, PublicH2Limitation, PublicH2Narrative, PublicH2Requisites,
    PublicH2SourceItem,
)

_MOSCOW = ZoneInfo("Europe/Moscow")
EMPTY_CHART_FACTS_VERSION = "company_card_chart_facts_v1"
EMPTY_CHART_FACTS_HASH = canonical_digest({
    "version": EMPTY_CHART_FACTS_VERSION,
    "unit_policy": "datanewton_finance_thousand_rub_v2",
    "facts": [],
})


@dataclass(frozen=True)
class LegacySnapshotBinding:
    """Exact immutable record identity already loaded by the SELECT-only resolver."""

    report_id: str
    report_version: str
    inn: str
    lifecycle_status: str
    stored_snapshot_hash: str
    calculated_snapshot_hash: str


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
    finance_enabled: bool = False,
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
    # ``fixture_finance_views`` is retained only for frozen golden callers. A
    # saved v2 publication policy explicitly enables the same pure projection
    # at runtime; legacy/v1 callers never enter this branch.
    views = fixture_finance_views if fixture_finance_views is not None else (
        build_finance_views(snapshot.finance_basis) if finance_enabled else None
    )
    finance_blocks = _fixture_finance_blocks(views) if views is not None else {}
    finance_codes = {
        "finance_f1": frozenset(("1250", "1240", "1230", "1500")),
        "finance_f2": frozenset(("1300", "1400", "1500")),
        "finance_f3": frozenset(("2110", "1600")),
        "finance_f4": frozenset(("2110", "2100", "2200", "2400")),
        "finance_f5": frozenset(code for code, _label in F5_ROWS),
    }
    # Limitations belong only to source leaves used by the concrete public
    # view: correct source form and that view's selected calendar window.
    # A historical/wrong-form cell must never downgrade a current projection.
    finance_state_codes: dict[str, tuple[str, ...]] = {}
    finance_formula_codes: dict[str, tuple[str, ...]] = {}
    relevant_cells: dict[str, tuple[object, ...]] = {}
    if finance_enabled and views is not None:
        view_years = {
            "finance_f1": (() if views["F1"] is None else (views["F1"]["year"],)),
            "finance_f2": (() if views["F2"] is None else tuple(period["year"] for period in views["F2"]["periods"])),
            "finance_f3": (() if views["F3"] is None else tuple(point["year"] for point in views["F3"]["points"])),
            "finance_f4": (() if views["F4"] is None else (views["F4"]["year"],)),
            "finance_f5": (() if views["F5"] is None else tuple(views["F5"]["years"])),
        }
        for block, codes in finance_codes.items():
            if not view_years[block]:
                candidates = [
                    cell.year for cell in snapshot.finance_basis.cells
                    if cell.code in codes and cell.form == FORM_BY_CODE[cell.code]
                ]
                if candidates:
                    anchor = max(candidates)
                    view_years[block] = (anchor,) if block in {"finance_f1", "finance_f4"} else tuple(range(anchor - 6, anchor + 1))
            relevant_cells[block] = tuple(
                cell for cell in snapshot.finance_basis.cells
                if cell.code in codes
                and cell.form == FORM_BY_CODE[cell.code]
                and cell.year in view_years[block]
            )
            states = sorted({cell.state for cell in relevant_cells[block] if cell.state != "available_nonzero"})
            finance_state_codes[block] = tuple(f"finance_{state}" for state in states)
        if views["F1"] is not None and "receivables_collection_unassessed" in views["F1"].get("limitations", ()):
            finance_formula_codes["finance_f1"] = ("receivables_collection_unassessed",)
        for block, view in (("finance_f2", views["F2"]), ("finance_f4", views["F4"])):
            if view is None:
                continue
            raw = (
                tuple(code for period in view["periods"] for code in period.get("limitations", ()))
                if block == "finance_f2" else tuple(view.get("limitations", ()))
            )
            approved = tuple(sorted(set(raw) & {"finance_denominator_non_positive"}))
            if approved:
                finance_formula_codes[block] = approved
    stored_limitations = (*snapshot.limitations, *snapshot.arbitration_basis.limitations)
    if finance_enabled:
        # Rebuild finance limitations from the exact selected form/window
        # below. Carrying snapshot-wide finance rows here would let an old or
        # wrong-form leaf downgrade an unrelated current view.
        stored_limitations = tuple(
            item for item in stored_limitations
            if not (
                (item.field is not None and item.field.startswith("finance."))
                or item.code.startswith("finance_")
            )
        )
    limitations = [
        PublicH2Limitation(code=item.code, field_id=item.field, message="Данные недоступны в текущем подтверждённом контуре.")
        for item in stored_limitations
    ]
    if finance_enabled:
        seen_finance_fields: set[tuple[str, str]] = set()
        seen_finance_states: set[str] = set()
        for block, cells in relevant_cells.items():
            for cell in cells:
                if cell.state == "available_nonzero":
                    continue
                key = (cell.state, f"finance.{cell.form}.{cell.code}.{cell.year}")
                if key in seen_finance_fields:
                    continue
                seen_finance_fields.add(key)
                state_code = f"finance_{cell.state}"
                if state_code not in seen_finance_states:
                    seen_finance_states.add(state_code)
                    limitations.append(PublicH2Limitation(
                        code=state_code,
                        field_id=None,
                        message="Часть финансовых показателей не подтверждена в сохранённом снимке.",
                    ))
                limitations.append(PublicH2Limitation(
                    code=f"finance-{cell.state}-{cell.form}-{cell.code}-{cell.year}",
                    field_id=key[1],
                    message="Часть финансовых показателей не подтверждена в сохранённом снимке.",
                ))
        for code in sorted({code for codes in finance_formula_codes.values() for code in codes}):
            limitations.append(PublicH2Limitation(
                code=code,
                field_id=None,
                message="Расчёт финансового показателя ограничен сохранёнными исходными данными.",
            ))
    # Every unavailable leaf has an explicit linked limitation.  Do not reuse
    # private/provider text as a message.
    # Requisites are deliberately conservative: the available snapshot core
    # is public, but the complete requisites evidence family is not.
    limitations.append(PublicH2Limitation(code="requisites_partial", block_id="requisites", field_id=None, message="Часть реквизитов недоступна в текущем подтверждённом контуре."))
    for block in (*COVERAGE_BLOCKS[2:7], *COVERAGE_BLOCKS[7:12]):
        if block.startswith("finance_") and finance_blocks.get(block) is not None:
            continue
        if block.startswith("finance_") and finance_enabled:
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
            # F1's receivables-collection notice is an approved advisory, not
            # an incompleteness signal for an otherwise complete calculation.
            formula_codes = () if block == "finance_f1" else finance_formula_codes.get(block, ())
            codes = (*finance_state_codes.get(block, ()), *formula_codes)
            coverage.append(PublicH2CoverageItem(block_id=block, state="partial" if codes else "available", population_scope="not_applicable", limitation_codes=codes))
        elif block.startswith("finance_") and finance_enabled:
            coverage.append(PublicH2CoverageItem(block_id=block, state="missing", population_scope="not_applicable", limitation_codes=finance_state_codes.get(block, ())))
        else:
            coverage.append(PublicH2CoverageItem(block_id=block, state="gate_closed", population_scope="not_applicable", limitation_codes=(f"{block}_gate_closed",)))
    primary_activity = None
    if isinstance(snapshot, CompanyCardV2SnapshotV2) and snapshot.narrative_evidence.primary_activity is not None:
        admitted = snapshot.narrative_evidence.primary_activity
        primary_activity = PublicActivity(code=admitted.code, label=admitted.label, is_primary=True)
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
            requisites=PublicH2Requisites(address=(PublicH2Address(display=snapshot.counterparty.address, is_inaccuracy=snapshot.counterparty.address_inaccuracy) if snapshot.counterparty.address else None), primary_activity=primary_activity),
            **finance_blocks,
        ).model_dump(mode="json"),
        "coverage": [item.model_dump(mode="json") for item in coverage],
        "sources": [PublicH2SourceItem(dataset=dataset, received_at=checked_at, normalization_version="company_card_v2_v1", evidence_version=snapshot.evidence_version).model_dump(mode="json") for dataset in ("counterparty", "finance", "arbitration")],
        "limitations": [item.model_dump(mode="json") for item in limitations],
        "actions": [PublicH2Action(action_id="check_another_company", label="Проверить другую компанию", path="/").model_dump(mode="json"), PublicH2Action(action_id="prepare_claim", label="Подготовить претензию", path=f"/claims?report_id={snapshot.report_id}").model_dump(mode="json")],
        "breadcrumbs": [PublicH2Breadcrumb(label="Главная", path="/", current=False).model_dump(mode="json"), PublicH2Breadcrumb(label=name, path=canonical_path, current=True).model_dump(mode="json")],
        "primary_claim_cta": PublicH2ClaimCta(path=f"/claims?report_id={snapshot.report_id}").model_dump(mode="json"),
    }
    response = CompanyPublicH2Response(**payload, projection_digest=canonical_digest(payload))
    if len(canonical_json_bytes(response.model_dump(mode="json"))) > 524288:
        raise ValueError("public_projection_too_large")
    assert_public_boundary_safe(response.model_dump(mode="json"))
    return response


def build_legacy_public_h2(
    snapshot: CompanyReport,
    *,
    snapshot_binding: LegacySnapshotBinding,
    narrative_binding: NarrativeBindingProtocol,
) -> CompanyPublicH2Response:
    """Project a frozen v1/v2 report without upgrading or deriving Card-v2 facts.

    The caller supplies the hash calculated from the exact stored JSON and the
    persisted record identity.  This pure adapter only accepts equality across
    those values and the strict legacy snapshot.  It performs no I/O, fallback
    rendering, finance/arbitration calculation, provider access, or mutation.
    """
    if not isinstance(snapshot, CompanyReport):
        raise ValueError("legacy snapshot binding is invalid")
    hashes_match = (
        snapshot_binding.stored_snapshot_hash
        == snapshot_binding.calculated_snapshot_hash
        and len(snapshot_binding.stored_snapshot_hash) == 64
        and all(character in "0123456789abcdef" for character in snapshot_binding.stored_snapshot_hash)
    )
    counterparty = snapshot.counterparty
    if (
        not hashes_match
        or snapshot.report_version not in {"1", "2"}
        or snapshot.report_version != snapshot_binding.report_version
        or str(snapshot.report_id) != snapshot_binding.report_id
        or snapshot.target_identifier != snapshot_binding.inn
        or getattr(snapshot.target_identifier_type, "value", snapshot.target_identifier_type)
        != "legal_entity_inn"
        or snapshot.status.value != snapshot_binding.lifecycle_status
        or snapshot_binding.lifecycle_status not in {"complete", "partial"}
        or counterparty is None
        or counterparty.inn != snapshot_binding.inn
        or not isinstance(counterparty.full_name, str)
        or not counterparty.full_name.strip()
    ):
        raise ValueError("legacy snapshot binding is invalid")

    narrative = _saved_fallback_narrative(narrative_binding)
    checked_at = _utc_z(snapshot.generated_at)
    checked_date = snapshot.generated_at.astimezone(_MOSCOW).date().isoformat()
    canonical_path = f"/company/{snapshot_binding.inn}-company"
    address = None
    if counterparty.address is not None and counterparty.address.line_address:
        address = PublicH2Address(
            display=counterparty.address.line_address,
            region=counterparty.address.region,
            is_inaccuracy=counterparty.address.is_inaccuracy,
        )

    limitations = _legacy_limitations()
    coverage = _legacy_coverage()
    sources = _legacy_sources(snapshot)
    payload = {
        "contract_version": "company_public_h2_v1",
        "report_id": snapshot_binding.report_id,
        "report_version": snapshot_binding.report_version,
        "chart_facts_version": EMPTY_CHART_FACTS_VERSION,
        "chart_facts_hash": EMPTY_CHART_FACTS_HASH,
        "snapshot_capability": "legacy_read_only",
        "projection_scope": "latest_unpublished",
        "canonical_path": canonical_path,
        "indexable": False,
        "checked_at": checked_at,
        "checked_date": checked_date,
        "checked_date_display": checked_date,
        "identity": PublicH2Identity(
            display_name=counterparty.full_name,
            legal_full_name=counterparty.full_name,
            short_name=counterparty.short_name,
            inn=counterparty.inn,
            ogrn=counterparty.ogrn,
            kpp=counterparty.kpp,
            registration_date=(
                counterparty.registration_date.isoformat()
                if counterparty.registration_date is not None
                else None
            ),
            dissolution_date=(
                counterparty.dissolved_date.isoformat()
                if counterparty.dissolved_date is not None
                else None
            ),
            status=None,
        ).model_dump(mode="json"),
        "narrative": narrative.model_dump(mode="json"),
        "block_order": BLOCK_ORDER,
        "blocks": PublicH2Blocks(
            requisites=PublicH2Requisites(address=address),
        ).model_dump(mode="json"),
        "coverage": [item.model_dump(mode="json") for item in coverage],
        "sources": [item.model_dump(mode="json") for item in sources],
        "limitations": [item.model_dump(mode="json") for item in limitations],
        "actions": [
            PublicH2Action(
                action_id="check_another_company",
                label="Проверить другую компанию",
                path="/",
            ).model_dump(mode="json"),
            PublicH2Action(
                action_id="prepare_claim",
                label="Подготовить претензию",
                path=f"/claims?report_id={snapshot_binding.report_id}",
            ).model_dump(mode="json"),
        ],
        "breadcrumbs": [
            PublicH2Breadcrumb(
                label="Главная", path="/", current=False
            ).model_dump(mode="json"),
            PublicH2Breadcrumb(
                label=counterparty.full_name,
                path=canonical_path,
                current=True,
            ).model_dump(mode="json"),
        ],
        "primary_claim_cta": PublicH2ClaimCta(
            path=f"/claims?report_id={snapshot_binding.report_id}"
        ).model_dump(mode="json"),
    }
    response = CompanyPublicH2Response(
        **payload, projection_digest=canonical_digest(payload)
    )
    if len(canonical_json_bytes(response.model_dump(mode="json"))) > 524288:
        raise ValueError("public_projection_too_large")
    assert_public_boundary_safe(response.model_dump(mode="json"))
    return response


def _saved_fallback_narrative(
    narrative_binding: NarrativeBindingProtocol,
) -> PublicH2Narrative:
    narrative = narrative_binding.narrative
    expected_digest = sha256(FALLBACK_DESCRIPTION.encode("utf-8")).hexdigest()
    if (
        not isinstance(narrative, PublicH2Narrative)
        or narrative.mode != "deterministic_fallback"
        or narrative.renderer_version != FALLBACK_RENDERER_VERSION
        or narrative.description != FALLBACK_DESCRIPTION
        or narrative.statement_ids != (FALLBACK_PROFILE_ID,)
        or narrative.comments != ()
        or narrative.render_digest != expected_digest
    ):
        raise ValueError("saved fallback binding is invalid")
    return narrative


def _legacy_limitations() -> tuple[PublicH2Limitation, ...]:
    limitations = [
        PublicH2Limitation(
            code="requisites_partial",
            block_id="requisites",
            field_id=None,
            message="Часть реквизитов недоступна в текущем подтверждённом контуре.",
        )
    ]
    for block in (*COVERAGE_BLOCKS[2:7], *COVERAGE_BLOCKS[7:12]):
        limitations.append(PublicH2Limitation(
            code=f"{block}_gate_closed",
            block_id=block,
            field_id=None,
            message="Раздел недоступен до закрытия обязательного evidence gate.",
        ))
    return tuple(limitations)


def _legacy_coverage() -> tuple[PublicH2CoverageItem, ...]:
    coverage: list[PublicH2CoverageItem] = []
    for block in COVERAGE_BLOCKS:
        if block == "requisites":
            coverage.append(PublicH2CoverageItem(
                block_id=block,
                state="partial",
                population_scope="not_applicable",
                limitation_codes=("requisites_partial",),
            ))
        elif block in {"narrative", "sources_limitations"}:
            coverage.append(PublicH2CoverageItem(
                block_id=block,
                state="available",
                population_scope="not_applicable",
                limitation_codes=(),
            ))
        else:
            coverage.append(PublicH2CoverageItem(
                block_id=block,
                state="gate_closed",
                population_scope="not_applicable",
                limitation_codes=(f"{block}_gate_closed",),
            ))
    return tuple(coverage)


def _legacy_sources(snapshot: CompanyReport) -> tuple[PublicH2SourceItem, ...]:
    """Expose only the contiguous, exact source prefix present in the snapshot."""
    result: list[PublicH2SourceItem] = []
    for dataset in ("counterparty", "finance", "arbitration"):
        dataset_report = snapshot.datasets[dataset]
        if dataset_report.status.value != "available":
            break
        source = dataset_report.source
        if source is None or source.dataset != dataset:
            raise ValueError("legacy snapshot binding is invalid")
        result.append(PublicH2SourceItem(
            dataset=dataset,
            received_at=_utc_z(source.received_at),
            normalization_version="company_card_v2_v1",
            evidence_version="evidence_v1",
        ))
    if not result:
        raise ValueError("legacy snapshot binding is invalid")
    return tuple(result)


def _decimal(value: Decimal) -> str:
    rendered = format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else format(value, "f")
    return "0" if rendered in {"", "-0"} else rendered


def _money(value: Decimal) -> PublicFinanceMoney:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("fixture finance values must be finite Decimal")
    with localcontext() as context:
        context.prec = 128
        context.rounding = ROUND_HALF_UP
        source = _decimal(value)
        rub = _decimal(value * Decimal("1000"))
        # Exact public money intentionally keeps thousandth-million precision
        # for integral source units: 10 -> 0,010; 273325 -> 273,325.
        million_value = value / Decimal("1000")
        million = _decimal(million_value)
        exact_million = format(million_value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP), "f") if value == value.to_integral_value() else million
        compact = million_value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    def shown(number: Decimal | str) -> str:
        rendered = _decimal(number) if isinstance(number, Decimal) else number
        return rendered.replace("-", "−", 1).replace(".", ",")
    return PublicFinanceMoney(
        source_thousand_decimal=source,
        rub_decimal=rub,
        million_decimal=million,
        # Source units are thousands of roubles.  Preserve exact decimal
        # million precision separately from the one-decimal compact label.
        display_exact=f"{shown(exact_million)} млн ₽",
        display_compact=f"{shown(compact)} млн ₽",
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


def _f2(value: object) -> PublicF2 | None:
    if value is None:
        return None
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


def _f3(value: object) -> PublicF3 | None:
    if value is None:
        return None
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


def _f5(value: object) -> PublicF5 | None:
    if value is None:
        return None
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


__all__ = [
    "EMPTY_CHART_FACTS_HASH",
    "EMPTY_CHART_FACTS_VERSION",
    "LegacySnapshotBinding",
    "NarrativeBindingProtocol",
    "build_legacy_public_h2",
    "build_public_h2",
]
