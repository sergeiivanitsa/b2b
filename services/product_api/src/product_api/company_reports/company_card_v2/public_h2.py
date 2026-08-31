from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext
from hashlib import sha256
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

from product_api.company_reports.aggregate import CompanyReport
from product_api.company_reports.company_urls import parse_company_path

from .canonical_json import canonical_digest, canonical_json_bytes
from .finance import F5_ROWS, FORM_BY_CODE, build_finance_views
from .models import (
    ArbitrationBasisV2,
    CompanyCardV2Snapshot,
    CompanyCardV2SnapshotV2,
    CompanyCardV2SnapshotV3,
    SanitizedArbitrationCaseV2,
)
from .narrative.catalog import (
    FALLBACK_DESCRIPTION,
    FALLBACK_PROFILE_ID,
    FALLBACK_RENDERER_VERSION,
)
from .privacy import assert_public_boundary_safe
from .public_h2_models import (
    ARBITRATION_PUBLIC_LIMITATION_MESSAGES, BLOCK_ORDER, COVERAGE_BLOCKS,
    CompanyPublicH2Response, PublicH2Action,
    PublicChartAxis, PublicChartInterval, PublicChartPoint, PublicF1, PublicF2,
    PublicF2Period, PublicF3, PublicF3Point, PublicF3SeriesSummary, PublicF4,
    PublicF5, PublicF5Cell, PublicF5Row, PublicFinanceMoney, PublicFinanceSegment,
    PublicH2Blocks, PublicH2Breadcrumb, PublicH2ClaimCta, PublicH2CoverageItem,
    PublicActivity, PublicH2Address, PublicH2Identity, PublicH2Limitation, PublicH2Narrative, PublicH2Requisites,
    PublicH2SourceItem, PublicArbitrationSummary, PublicSafeCaseDetail,
    PublicCaseAmount, PublicDetailScope, PublicRoleDetail, PublicA1YearBucket,
    PublicA1, PublicCountBar, PublicA2, PublicA3, PublicA4CaseGeometry,
    PublicA4CurrencyGroup, PublicA4, PublicA5OpponentGroup, PublicA5,
)

_MOSCOW = ZoneInfo("Europe/Moscow")
EMPTY_CHART_FACTS_VERSION = "company_card_chart_facts_v1"
EMPTY_CHART_FACTS_HASH = canonical_digest({
    "version": EMPTY_CHART_FACTS_VERSION,
    "unit_policy": "datanewton_finance_thousand_rub_v2",
    "facts": [],
})
_ARBITRATION_BLOCK_IDS = tuple(f"arbitration_a{index}" for index in range(1, 6))
_ARBITRATION_CAP_CODE = "arbitration_public_projection_cap_exhausted"
_ARBITRATION_PRE_RESULT_REASONS = {
    "operation_gate_closed": "gate_closed",
    "evidence_gate_closed": "gate_closed",
    "privacy_key_unavailable": "failed",
    "provider_error": "failed",
    "provider_binding_invalid": "failed",
}
_ARBITRATION_BOUND_FAILURE_REASONS = {
    "lexical_transport_invalid",
    "envelope_invalid",
}
_ARBITRATION_COLLECTION_CODES = {
    "malformed_rows",
    "duplicate_conflict",
    "oversized_case",
    "storage_cap_exhausted",
    "source_total_exceeds_cap",
}
_ARBITRATION_AMOUNT_CODES = {
    "arbitration_amount_missing",
    "arbitration_amount_invalid",
    "arbitration_currency_missing",
    "arbitration_currency_unidentified",
    "arbitration_currency_invalid",
}
_ARBITRATION_A1_CODES = {
    "arbitration_calendar_unverified",
    "arbitration_unknown_year",
}
_ARBITRATION_DETAIL_CODES = {
    "arbitration_date_invalid",
    "arbitration_date_inversion",
    "arbitration_year_conflict",
    "arbitration_first_number_unavailable",
    "arbitration_first_number_identity_collision",
}
_ARBITRATION_MESSAGES = ARBITRATION_PUBLIC_LIMITATION_MESSAGES
_NON_ARBITRATION_FIXED_LIMITATION_MESSAGES = frozenset({
    "Данные недоступны в текущем подтверждённом контуре.",
    "Часть финансовых показателей не подтверждена в сохранённом снимке.",
    "Расчёт финансового показателя ограничен сохранёнными исходными данными.",
    "Часть реквизитов недоступна в текущем подтверждённом контуре.",
    "Раздел недоступен до закрытия обязательного evidence gate.",
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


@dataclass(frozen=True)
class PublicH2ProjectionBindingV1:
    """Explicit, immutable publication coordinates for one H2 projection.

    The value is supplied by the already selected persistence boundary.  It
    deliberately contains no settings, request state or clock dependency.
    ``published_lastmod`` is not part of the public DTO, but validating it
    here prevents an active projection from being built without the exact
    immutable publication timestamp that must be persisted beside the pin.
    """

    projection_scope: Literal[
        "active_publication", "staged_publication", "latest_unpublished"
    ]
    canonical_path: str
    indexable: bool
    published_lastmod: datetime | None

    def __post_init__(self) -> None:
        if type(self.indexable) is not bool:
            raise TypeError("public H2 indexability must be an exact boolean")
        if (
            not isinstance(self.canonical_path, str)
            or (parsed := parse_company_path(self.canonical_path)) is None
            or parsed.kind == "plain"
        ):
            raise ValueError("public H2 canonical path is invalid")
        if self.projection_scope == "active_publication":
            if (
                self.published_lastmod is None
                or self.published_lastmod.tzinfo is None
                or self.published_lastmod.utcoffset() is None
            ):
                raise ValueError("active public H2 lastmod is invalid")
        elif self.projection_scope in {
            "staged_publication",
            "latest_unpublished",
        }:
            if self.indexable or self.published_lastmod is not None:
                raise ValueError("non-active public H2 binding must be noindex")
        else:  # pragma: no cover - the annotation is not a runtime boundary
            raise ValueError("public H2 projection scope is invalid")


@dataclass(frozen=True)
class _ArbitrationProjection:
    blocks: dict[str, object | None]
    coverage: dict[str, PublicH2CoverageItem]
    limitations: tuple[PublicH2Limitation, ...]
    source: PublicH2SourceItem | None


def _utc_z(value) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_public_h2(
    snapshot: (
        CompanyCardV2Snapshot
        | CompanyCardV2SnapshotV2
        | CompanyCardV2SnapshotV3
    ),
    *,
    narrative_binding: NarrativeBindingProtocol,
    projection_binding: PublicH2ProjectionBindingV1 | None = None,
    fixture_finance_views: dict[str, object] | None = None,
    finance_enabled: bool = False,
    arbitration_enabled: bool = False,
) -> CompanyPublicH2Response:
    """Build only from an already validated, injected narrative binding.

    Iteration 20 has no artifact generation, storage, or runtime fallback.
    Callers that cannot supply this in-memory binding must keep the H2 pin
    unresolved and return ``report_not_eligible`` instead.
    """
    narrative = narrative_binding.narrative
    if not isinstance(narrative, PublicH2Narrative):
        raise ValueError("narrative binding is not validated")
    if (
        arbitration_enabled != (type(snapshot) is CompanyCardV2SnapshotV3)
        or (arbitration_enabled and not finance_enabled)
    ):
        raise ValueError("arbitration publication policy does not match snapshot")
    checked_at = _utc_z(snapshot.generated_at)
    checked_date = snapshot.generated_at.astimezone(_MOSCOW).date().isoformat()
    name = snapshot.counterparty.full_name or snapshot.counterparty.short_name or snapshot.subject_inn
    default_canonical_path = f"/company/{snapshot.subject_inn}-company"
    projection_binding = projection_binding or PublicH2ProjectionBindingV1(
        projection_scope="latest_unpublished",
        canonical_path=default_canonical_path,
        indexable=False,
        published_lastmod=None,
    )
    if type(projection_binding) is not PublicH2ProjectionBindingV1:
        raise TypeError("public H2 projection binding is invalid")
    canonical_path = projection_binding.canonical_path
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
    stored_limitations = (
        tuple(snapshot.limitations)
        if arbitration_enabled
        else (*snapshot.limitations, *snapshot.arbitration_basis.limitations)
    )
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
    for block in (
        *COVERAGE_BLOCKS[2:7],
        *(() if arbitration_enabled else COVERAGE_BLOCKS[7:12]),
    ):
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
    arbitration_projection = (
        _build_arbitration_projection(snapshot)
        if arbitration_enabled and type(snapshot) is CompanyCardV2SnapshotV3
        else None
    )
    if arbitration_projection is not None:
        limitations.extend(arbitration_projection.limitations)
        unique = {}
        for limitation in limitations:
            unique.setdefault(limitation.code, limitation)
        limitations = sorted(
            unique.values(),
            key=lambda item: (
                COVERAGE_BLOCKS.index(item.block_id)
                if item.block_id in COVERAGE_BLOCKS else 99,
                item.field_id or "",
                item.code,
            ),
        )
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
        elif arbitration_projection is not None and block in _ARBITRATION_BLOCK_IDS:
            coverage.append(arbitration_projection.coverage[block])
        else:
            coverage.append(PublicH2CoverageItem(block_id=block, state="gate_closed", population_scope="not_applicable", limitation_codes=(f"{block}_gate_closed",)))
    primary_activity = None
    if isinstance(snapshot, CompanyCardV2SnapshotV2) and snapshot.narrative_evidence.primary_activity is not None:
        admitted = snapshot.narrative_evidence.primary_activity
        primary_activity = PublicActivity(code=admitted.code, label=admitted.label, is_primary=True)
    payload = {
        "contract_version": "company_public_h2_v1", "report_id": snapshot.report_id, "report_version": "3",
        "chart_facts_version": snapshot.chart_facts.version, "chart_facts_hash": snapshot.chart_facts.hash,
        "snapshot_capability": "card_v2", "projection_scope": projection_binding.projection_scope, "canonical_path": canonical_path,
        "indexable": projection_binding.indexable, "checked_at": checked_at, "checked_date": checked_date, "checked_date_display": checked_date,
        "identity": PublicH2Identity(display_name=name, legal_full_name=name, short_name=snapshot.counterparty.short_name,
            inn=snapshot.counterparty.inn, ogrn=snapshot.counterparty.ogrn, kpp=snapshot.counterparty.kpp,
            registration_date=snapshot.counterparty.registration_date.isoformat() if snapshot.counterparty.registration_date else None,
            dissolution_date=snapshot.counterparty.dissolution_date.isoformat() if snapshot.counterparty.dissolution_date else None).model_dump(mode="json"),
        "narrative": narrative.model_dump(mode="json"), "block_order": BLOCK_ORDER,
        "blocks": PublicH2Blocks(
            requisites=PublicH2Requisites(address=(PublicH2Address(display=snapshot.counterparty.address, is_inaccuracy=snapshot.counterparty.address_inaccuracy) if snapshot.counterparty.address else None), primary_activity=primary_activity),
            **finance_blocks,
            **(arbitration_projection.blocks if arbitration_projection is not None else {}),
        ).model_dump(mode="json"),
        "coverage": [item.model_dump(mode="json") for item in coverage],
        "sources": [
            item.model_dump(mode="json")
            for item in (
                PublicH2SourceItem(dataset="counterparty", received_at=checked_at, normalization_version="company_card_v2_v1", evidence_version=snapshot.evidence_version),
                PublicH2SourceItem(dataset="finance", received_at=checked_at, normalization_version="company_card_v2_v1", evidence_version=snapshot.evidence_version),
                *(
                    (arbitration_projection.source,)
                    if arbitration_projection is not None and arbitration_projection.source is not None
                    else (() if arbitration_projection is not None else (
                        PublicH2SourceItem(dataset="arbitration", received_at=checked_at, normalization_version="company_card_v2_v1", evidence_version=snapshot.evidence_version),
                    ))
                ),
            )
        ],
        "limitations": [item.model_dump(mode="json") for item in limitations],
        "actions": [PublicH2Action(action_id="check_another_company", label="Проверить другую компанию", path="/").model_dump(mode="json"), PublicH2Action(action_id="prepare_claim", label="Подготовить претензию", path=f"/claims?report_id={snapshot.report_id}").model_dump(mode="json")],
        "breadcrumbs": [PublicH2Breadcrumb(label="Главная", path="/", current=False).model_dump(mode="json"), PublicH2Breadcrumb(label=name, path=canonical_path, current=True).model_dump(mode="json")],
        "primary_claim_cta": PublicH2ClaimCta(path=f"/claims?report_id={snapshot.report_id}").model_dump(mode="json"),
    }
    response = _finalize_public_h2_payload(
        payload,
        bound_arbitration=(
            arbitration_projection is not None
            and arbitration_projection.source is not None
        ),
    )
    if arbitration_projection is None:
        assert_public_boundary_safe(response.model_dump(mode="json"))
    else:
        _assert_policy_v3_projection_safe(response, snapshot)
    return response


def rebind_public_h2_projection(
    response: CompanyPublicH2Response,
    *,
    projection_binding: PublicH2ProjectionBindingV1,
) -> CompanyPublicH2Response:
    """Rebind one fully validated DTO without reopening saved/private inputs.

    Rollout planning first validates the exact staged pin through the normal
    saved-result boundary.  Only the public projection coordinates then
    change.  Re-validating and re-digesting the complete DTO makes this pure
    transformation byte-equivalent to rebuilding from the same snapshot and
    narrative with the explicit binding.
    """
    if type(response) is not CompanyPublicH2Response:
        raise TypeError("public H2 response is invalid")
    if type(projection_binding) is not PublicH2ProjectionBindingV1:
        raise TypeError("public H2 projection binding is invalid")
    payload = response.model_dump(mode="json")
    payload.pop("projection_digest", None)
    payload["projection_scope"] = projection_binding.projection_scope
    payload["canonical_path"] = projection_binding.canonical_path
    payload["indexable"] = projection_binding.indexable
    breadcrumbs = [dict(item) for item in payload["breadcrumbs"]]
    breadcrumbs[1]["path"] = projection_binding.canonical_path
    payload["breadcrumbs"] = breadcrumbs
    rebound = CompanyPublicH2Response.model_validate(
        {**payload, "projection_digest": canonical_digest(payload)}
    )
    return rebound


def _provider_utc_z(value) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="auto").replace(
        "+00:00", "Z"
    )


def _case_public_ids(
    report_id: str,
    cases: tuple[SanitizedArbitrationCaseV2, ...],
) -> dict[str, str]:
    ordered = sorted(
        cases,
        key=lambda case: canonical_json_bytes(
            {
                "identity_version": "CasePublicOrderIdentityV1",
                "report_id": report_id.lower(),
                "case_key": case.case_id,
            }
        ),
    )
    if len(ordered) > 1000 or len({case.case_id for case in ordered}) != len(ordered):
        raise ValueError("invalid policy-v3 case ordinal population")
    return {
        case.case_id: f"case_{index:06d}"
        for index, case in enumerate(ordered, start=1)
    }


def _opponent_public_ids(
    report_id: str,
    basis: ArbitrationBasisV2,
) -> dict[str, str]:
    values = {
        token.value
        for case in basis.sanitized_cases
        for token in case.opponent_tokens
    }
    ordered = sorted(
        values,
        key=lambda value: canonical_json_bytes(
            {
                "identity_version": "OpponentPublicOrderIdentityV1",
                "report_id": report_id.lower(),
                "display_kind": "masked_unknown",
                "private_identity_kind": "masked_hmac",
                "private_identity_value": value,
            }
        ),
    )
    if len(ordered) > 20_000:
        raise ValueError("invalid policy-v3 opponent ordinal population")
    return {
        value: f"opponent_{index:06d}"
        for index, value in enumerate(ordered, start=1)
    }


def _case_detail_order(
    case: SanitizedArbitrationCaseV2,
    *,
    case_ids: dict[str, str],
) -> tuple[object, ...]:
    def descending(value: date | None) -> tuple[int, int]:
        return (1, 0) if value is None else (0, -value.toordinal())

    return (
        case.year is None,
        -(case.year or 0),
        *descending(case.date_start),
        *descending(case.date_update),
        case_ids[case.case_id],
    )


def _rub_case_amount(case: SanitizedArbitrationCaseV2) -> PublicCaseAmount | None:
    if (
        case.amount_state != "available"
        or case.currency_state != "rub"
        or case.amount is None
    ):
        return None
    source = _decimal(case.amount)
    return PublicCaseAmount(
        source_decimal=source,
        source_currency_id="RUB",
        display_exact=source.replace("-", "−").replace(".", ",") + " ₽",
    )


def _case_detail(
    case: SanitizedArbitrationCaseV2,
    *,
    case_public_id: str,
    private_case_ids: frozenset[str],
) -> PublicSafeCaseDetail:
    return PublicSafeCaseDetail(
        case_public_id=case_public_id,
        case_number=(
            None if case.first_number in private_case_ids else case.first_number
        ),
        year=case.year,
        role=case.role,
        outcome=case.outcome,
        result_detail=None,
        amount=_rub_case_amount(case),
        start_date=case.date_start.isoformat() if case.date_start is not None else None,
        update_date=case.date_update.isoformat() if case.date_update is not None else None,
        days_to_last_update=case.duration_days,
        instance_count=None,
        courts=(),
        opponents=(),
        public_case_url=None,
    )


def _ordered_details(
    cases: tuple[SanitizedArbitrationCaseV2, ...] | list[SanitizedArbitrationCaseV2],
    *,
    case_ids: dict[str, str],
    private_case_ids: frozenset[str],
) -> tuple[PublicSafeCaseDetail, ...]:
    return tuple(
        _case_detail(
            case,
            case_public_id=case_ids[case.case_id],
            private_case_ids=private_case_ids,
        )
        for case in sorted(
            cases,
            key=lambda item: _case_detail_order(item, case_ids=case_ids),
        )[:20]
    )


def _detail_scope(
    *,
    population_scope: str,
    source_total: int | None,
    rows_received: int,
    eligible_total: int,
    noun: str,
) -> PublicDetailScope:
    shown = min(eligible_total, 20)
    return PublicDetailScope(
        population_scope=population_scope,  # type: ignore[arg-type]
        source_total=source_total,
        rows_received=rows_received,
        eligible_total=eligible_total,
        shown=shown,
        cap=20,
        label=f"показано {shown} из {eligible_total} {noun}",
    )


def _arbitration_summary(basis: ArbitrationBasisV2) -> PublicArbitrationSummary:
    observed_years = tuple(
        case.year for case in basis.sanitized_cases if case.year is not None
    )
    counters = basis.counters
    return PublicArbitrationSummary(
        source_total=basis.source_total,
        rows_observed=counters.rows_observed,
        unique_case_count=counters.unique_case_count,
        malformed_count=counters.malformed_count,
        duplicate_identical_count=counters.duplicate_identical_count,
        duplicate_conflict_count=counters.duplicate_conflict_key_count,
        collection_complete=basis.collection_complete,
        completion_reason=basis.completion_reasons[0],
        calendar_complete=False,
        calendar_scope="unverified",
        calendar_start_year=None,
        calendar_end_year=None,
        calendar_evidence_version=None,
        observed_start_year=min(observed_years) if observed_years else None,
        observed_end_year=max(observed_years) if observed_years else None,
        unknown_year_count=basis.unknown_year_count,
        zero_years_proven=False,
    )


def _arbitration_percentages(
    counts: tuple[int, int, int, int],
    denominator: int,
) -> tuple[str | None, str | None, str | None, str | None]:
    if denominator == 0:
        return (None, None, None, None)
    quantum = Decimal("0.000001")
    with localcontext() as context:
        context.prec = 34
        context.rounding = ROUND_HALF_UP
        unrounded = tuple(
            Decimal(count) / Decimal(denominator) * Decimal("100")
            for count in counts
        )
        rounded = [
            value.quantize(quantum, rounding=ROUND_HALF_UP)
            for value in unrounded
        ]
        residual = Decimal("100") - sum(rounded, Decimal("0"))
        winner = max(
            range(4),
            key=lambda index: (abs(unrounded[index] - rounded[index]), -index),
        )
        rounded[winner] += residual
    return tuple(_decimal(value) for value in rounded)  # type: ignore[return-value]


def _arbitration_views(
    snapshot: CompanyCardV2SnapshotV3,
) -> tuple[dict[str, object | None], dict[str, int | None]]:
    basis = snapshot.arbitration_basis
    cases = basis.sanitized_cases
    case_ids = _case_public_ids(snapshot.report_id, cases)
    opponent_ids = _opponent_public_ids(snapshot.report_id, basis)
    private_case_ids = frozenset(case.case_id for case in cases)
    summary = _arbitration_summary(basis)
    population_scope = (
        "complete_collection" if basis.collection_complete else "returned_slice"
    )
    source_total = basis.source_total
    rows_received = basis.counters.rows_observed

    known_years = sorted({case.year for case in cases if case.year is not None})[-10:]
    bucket_years: list[int | None] = list(known_years)
    if any(case.year is None for case in cases):
        bucket_years.append(None)
    role_order = ("plaintiff", "respondent", "other", "unattributed")
    buckets: list[PublicA1YearBucket] = []
    for year in bucket_years:
        bucket_cases = tuple(case for case in cases if case.year == year)
        counts = {role: sum(case.role == role for case in bucket_cases) for role in role_order}
        details = tuple(
            PublicRoleDetail(
                role=role,  # type: ignore[arg-type]
                scope=_detail_scope(
                    population_scope=population_scope,
                    source_total=source_total,
                    rows_received=rows_received,
                    eligible_total=counts[role],
                    noun="дел",
                ),
                cases=_ordered_details(
                    tuple(case for case in bucket_cases if case.role == role),
                    case_ids=case_ids,
                    private_case_ids=private_case_ids,
                ),
            )
            for role in role_order
        )
        buckets.append(
            PublicA1YearBucket(
                year=year,
                plaintiff_count=counts["plaintiff"],
                respondent_count=counts["respondent"],
                other_count=counts["other"],
                unattributed_count=counts["unattributed"],
                total_count=len(bucket_cases),
                role_details=details,  # type: ignore[arg-type]
            )
        )
    a1 = PublicA1(
        summary=summary,
        displayed_start_year=known_years[0] if known_years else None,
        displayed_end_year=known_years[-1] if known_years else None,
        buckets=tuple(buckets),
        all_time_case_count=len(cases),
    )

    def count_bars(
        categories: tuple[str, str, str, str],
        attribute: str,
    ) -> tuple[PublicCountBar, PublicCountBar, PublicCountBar, PublicCountBar]:
        counts = tuple(sum(getattr(case, attribute) == category for case in cases) for category in categories)
        percentages = _arbitration_percentages(counts, len(cases))
        return tuple(
            PublicCountBar(
                category_id=category,  # type: ignore[arg-type]
                count=count,
                percent_decimal=percent,
                scope=_detail_scope(
                    population_scope=population_scope,
                    source_total=source_total,
                    rows_received=rows_received,
                    eligible_total=count,
                    noun="дел",
                ),
                cases=_ordered_details(
                    tuple(case for case in cases if getattr(case, attribute) == category),
                    case_ids=case_ids,
                    private_case_ids=private_case_ids,
                ),
            )
            for category, count, percent in zip(categories, counts, percentages, strict=True)
        )  # type: ignore[return-value]

    a2 = PublicA2(
        summary=summary,
        denominator=len(cases),
        bars=count_bars(role_order, "role"),
    )
    a3 = PublicA3(
        summary=summary,
        denominator=len(cases),
        bars=count_bars(("won", "lost", "returned", "unknown"), "outcome"),
    )

    rub_cases = tuple(
        case for case in cases
        if case.amount_state == "available"
        and case.currency_state == "rub"
        and case.amount is not None
    )
    top_rub_cases = tuple(sorted(
        rub_cases,
        key=lambda case: (
            case.amount.copy_abs().copy_negate(),  # type: ignore[union-attr]
            case.amount.copy_negate(),  # type: ignore[union-attr]
            case.year is None,
            -(case.year or 0),
            case.date_update is None,
            -(case.date_update.toordinal() if case.date_update is not None else 0),
            case_ids[case.case_id],
        ),
    )[:20])
    a4_groups: tuple[PublicA4CurrencyGroup, ...] = ()
    if rub_cases:
        details = tuple(
            _case_detail(
                case,
                case_public_id=case_ids[case.case_id],
                private_case_ids=private_case_ids,
            )
            for case in top_rub_cases
        )
        amounts = tuple(case.amount for case in top_rub_cases)
        axis = PublicChartAxis(
            axis_min_decimal=_decimal(min((Decimal("0"), *amounts))),
            axis_max_decimal=_decimal(max((Decimal("0"), *amounts))),
        )
        a4_groups = (
            PublicA4CurrencyGroup(
                source_currency_id="RUB",
                display_currency="₽",
                axis=axis,
                case_geometries=tuple(
                    PublicA4CaseGeometry(
                        case_public_id=case_ids[case.case_id],
                        geometry=_interval(Decimal("0"), case.amount),  # type: ignore[arg-type]
                    )
                    for case in top_rub_cases
                ),
                scope=_detail_scope(
                    population_scope=population_scope,
                    source_total=source_total,
                    rows_received=rows_received,
                    eligible_total=len(rub_cases),
                    noun="дел",
                ),
                cases=details,
            ),
        )
    a4 = PublicA4(
        summary=summary,
        currency_groups=a4_groups,
        missing_amount_count=sum(case.amount_state == "missing" for case in cases),
        missing_currency_count=sum(case.currency_state == "missing" for case in cases),
    )

    overflow = basis.counters.opponent_group_probe_count == 20_001
    a5: PublicA5 | None = None
    if not overflow:
        cases_by_opponent: dict[str, list[SanitizedArbitrationCaseV2]] = {
            value: [] for value in opponent_ids
        }
        for case in cases:
            for token in case.opponent_tokens:
                cases_by_opponent[token.value].append(case)
        ordered_groups = sorted(
            cases_by_opponent.items(),
            key=lambda item: (-len(item[1]), opponent_ids[item[0]]),
        )[:20]
        groups = tuple(
            PublicA5OpponentGroup(
                opponent_public_id=opponent_ids[value],
                display_name=f"Сторона скрыта {int(opponent_ids[value].split('_')[1])}",
                display_kind="masked_unknown",
                case_count=len(group_cases),
                case_scope=_detail_scope(
                    population_scope=population_scope,
                    source_total=source_total,
                    rows_received=rows_received,
                    eligible_total=len(group_cases),
                    noun="дел",
                ),
                cases=_ordered_details(
                    tuple(group_cases),
                    case_ids=case_ids,
                    private_case_ids=private_case_ids,
                ),
            )
            for value, group_cases in ordered_groups
        )
        a5 = PublicA5(
            summary=summary,
            scope=_detail_scope(
                population_scope=population_scope,
                source_total=source_total,
                rows_received=rows_received,
                eligible_total=len(opponent_ids),
                noun="сторон",
            ),
            groups=groups,
            cases_without_safe_opponent=sum(not case.opponent_tokens for case in cases),
            multi_opponent_case_count=sum(len(case.opponent_tokens) > 1 for case in cases),
        )
    return (
        {
            "arbitration_a1": a1,
            "arbitration_a2": a2,
            "arbitration_a3": a3,
            "arbitration_a4": a4,
            "arbitration_a5": a5,
        },
        {
            "arbitration_a1": len(cases),
            "arbitration_a2": len(cases),
            "arbitration_a3": len(cases),
            "arbitration_a4": len(rub_cases),
            "arbitration_a5": None if overflow else len(opponent_ids),
        },
    )


def _limitation_blocks(code: str) -> tuple[str, ...]:
    if code in _ARBITRATION_COLLECTION_CODES or code in _ARBITRATION_DETAIL_CODES:
        return _ARBITRATION_BLOCK_IDS
    if code in _ARBITRATION_A1_CODES:
        return ("arbitration_a1",)
    if code in _ARBITRATION_AMOUNT_CODES:
        return ("arbitration_a4",)
    if code == "opponent_group_cap_exhausted":
        return _ARBITRATION_BLOCK_IDS
    return _ARBITRATION_BLOCK_IDS


def _admitted_arbitration_limitations(
    basis: ArbitrationBasisV2,
) -> tuple[tuple[PublicH2Limitation, ...], dict[str, tuple[str, ...]]]:
    by_block: dict[str, list[str]] = {block: [] for block in _ARBITRATION_BLOCK_IDS}
    limitations: list[PublicH2Limitation] = []
    for item in basis.limitations:
        code = item.code
        blocks = _limitation_blocks(code)
        for block in blocks:
            by_block[block].append(code)
        limitations.append(
            PublicH2Limitation(
                code=code,
                block_id=blocks[0] if len(blocks) == 1 else None,
                field_id=None,
                message=_ARBITRATION_MESSAGES[code],
            )
        )
    return tuple(limitations), {
        block: tuple(codes) for block, codes in by_block.items()
    }


def _build_arbitration_projection(
    snapshot: CompanyCardV2SnapshotV3,
) -> _ArbitrationProjection:
    basis = snapshot.arbitration_basis
    facts = snapshot.arbitration_chart_facts
    first_reason = basis.completion_reasons[0]
    source = (
        PublicH2SourceItem(
            dataset="arbitration",
            received_at=_provider_utc_z(basis.provider_received_at),
            effective_at=None,
            period=None,
            normalization_version="company_card_arbitration_normalization_v2",
            evidence_version="datanewton_arbitration_registry_v2",
        )
        if basis.provider_received_at is not None else None
    )
    if facts.collection_state in {"gate_closed", "failed"}:
        if source is None:
            expected_state = _ARBITRATION_PRE_RESULT_REASONS.get(first_reason)
            if expected_state is None:
                raise ValueError("source-less policy-v3 failure reason is invalid")
        else:
            if first_reason not in _ARBITRATION_BOUND_FAILURE_REASONS:
                raise ValueError("bound policy-v3 failure reason is invalid")
            expected_state = "failed"
        limitation = PublicH2Limitation(
            code=first_reason,
            block_id=None,
            field_id=None,
            message=_ARBITRATION_MESSAGES[first_reason],
        )
        return _ArbitrationProjection(
            blocks={block: None for block in _ARBITRATION_BLOCK_IDS},
            coverage={
                block: PublicH2CoverageItem(
                    block_id=block,
                    state=expected_state,  # type: ignore[arg-type]
                    population_scope="not_applicable",
                    total=None,
                    returned=None,
                    eligible=None,
                    limitation_codes=(first_reason,),
                )
                for block in _ARBITRATION_BLOCK_IDS
            },
            limitations=(limitation,),
            source=source,
        )
    if source is None:
        raise ValueError("admitted policy-v3 collection lacks a bound source")

    blocks, eligible = _arbitration_views(snapshot)
    limitations, codes_by_block = _admitted_arbitration_limitations(basis)
    population_scope = (
        "complete_collection" if basis.collection_complete else "returned_slice"
    )
    coverage: dict[str, PublicH2CoverageItem] = {}
    for block in _ARBITRATION_BLOCK_IDS:
        block_value = blocks[block]
        block_eligible = eligible[block]
        if block == "arbitration_a5" and block_value is None:
            state = "failed"
            limitation_codes = ("opponent_group_cap_exhausted",)
        elif not basis.collection_complete:
            state = "partial"
            limitation_codes = codes_by_block[block]
        elif basis.counters.unique_case_count == 0:
            state = "available_empty"
            limitation_codes = codes_by_block[block]
        elif block == "arbitration_a4" and block_eligible != basis.counters.unique_case_count:
            state = "partial"
            limitation_codes = codes_by_block[block]
        elif block == "arbitration_a5" and block_eligible == 0:
            state = "available_empty"
            limitation_codes = codes_by_block[block]
        else:
            state = "available"
            limitation_codes = codes_by_block[block]
        coverage[block] = PublicH2CoverageItem(
            block_id=block,
            state=state,  # type: ignore[arg-type]
            population_scope=population_scope,
            total=basis.source_total,
            returned=basis.counters.rows_observed,
            eligible=block_eligible,
            limitation_codes=limitation_codes,
        )
    return _ArbitrationProjection(
        blocks=blocks,
        coverage=coverage,
        limitations=limitations,
        source=source,
    )


def _finalize_public_h2_payload(
    payload: dict[str, object],
    *,
    bound_arbitration: bool,
) -> CompanyPublicH2Response:
    candidate_payload = {
        **payload,
        "projection_digest": canonical_digest(payload),
    }
    candidate = CompanyPublicH2Response.model_validate(
        candidate_payload,
        context={"skip_public_h2_size_cap": True},
    )
    if len(canonical_json_bytes(candidate.model_dump(mode="json"))) <= 524_288:
        return candidate
    if not bound_arbitration:
        raise ValueError("public_projection_too_large")

    blocks = dict(candidate_payload["blocks"])  # type: ignore[arg-type]
    for block in _ARBITRATION_BLOCK_IDS:
        blocks[block] = None
    coverage = []
    for item in candidate_payload["coverage"]:  # type: ignore[union-attr]
        copied = dict(item)
        if copied["block_id"] in _ARBITRATION_BLOCK_IDS:
            copied["state"] = "failed"
            copied["limitation_codes"] = [_ARBITRATION_CAP_CODE]
        coverage.append(copied)
    limitations = [
        item for item in candidate_payload["limitations"]  # type: ignore[union-attr]
        if item["code"] not in _ARBITRATION_MESSAGES
    ]
    limitations.append(
        PublicH2Limitation(
            code=_ARBITRATION_CAP_CODE,
            block_id=None,
            field_id=None,
            message=_ARBITRATION_MESSAGES[_ARBITRATION_CAP_CODE],
        ).model_dump(mode="json")
    )
    fallback_payload = {
        **payload,
        "blocks": blocks,
        "coverage": coverage,
        "limitations": limitations,
    }
    return CompanyPublicH2Response(
        **fallback_payload,
        projection_digest=canonical_digest(fallback_payload),
    )


def _assert_policy_v3_projection_safe(
    response: CompanyPublicH2Response,
    snapshot: CompanyCardV2SnapshotV3,
) -> None:
    payload = response.model_dump(mode="json")
    non_arbitration = dict(payload)
    non_arbitration_blocks = dict(non_arbitration["blocks"])
    for block in _ARBITRATION_BLOCK_IDS:
        non_arbitration_blocks[block] = None
    non_arbitration["blocks"] = non_arbitration_blocks
    assert_public_boundary_safe(non_arbitration)

    private_values = {
        snapshot.arbitration_basis.mask_key_id,
        *(case.case_id for case in snapshot.arbitration_basis.sanitized_cases),
        *(
            token.value
            for case in snapshot.arbitration_basis.sanitized_cases
            for token in case.opponent_tokens
        ),
    }
    private_values.discard(None)
    _assert_no_private_arbitration_identity_at_public_sinks(
        {
            "blocks": {
                block: payload["blocks"][block]
                for block in _ARBITRATION_BLOCK_IDS
            },
            "limitations": payload["limitations"],
        },
        private_values=frozenset(private_values),
    )


_PRIVATE_ARBITRATION_IDENTITY_SINKS = frozenset({
    "case_number",
    "message",
    "result_detail",
    "courts",
    "opponents",
    "public_case_url",
})


def _assert_no_private_arbitration_identity_at_public_sinks(
    payload: object,
    *,
    private_values: frozenset[str],
) -> None:
    """Reject private identity only where the public contract can carry identity.

    Semantic enum/fact fields and report-scoped generated IDs are intentionally
    not compared by value: a private identifier may legitimately equal such a
    closed-contract token without that token becoming an identity disclosure.
    """

    stack: list[tuple[object, bool, tuple[str | int, ...]]] = [
        (payload, False, ())
    ]
    while stack:
        value, identity_sink, path = stack.pop()
        if isinstance(value, dict):
            fixed_limitation_message = (
                len(path) == 2
                and path[0] == "limitations"
                and type(path[1]) is int
                and _is_fixed_public_limitation(value)
            )
            stack.extend(
                (
                    nested,
                    (
                        False
                        if fixed_limitation_message and key == "message"
                        else identity_sink
                        or key in _PRIVATE_ARBITRATION_IDENTITY_SINKS
                    ),
                    (*path, key),
                )
                for key, nested in value.items()
            )
        elif isinstance(value, (list, tuple)):
            stack.extend(
                (nested, identity_sink, (*path, index))
                for index, nested in enumerate(value)
            )
        elif identity_sink and isinstance(value, str) and value in private_values:
            raise ValueError("private arbitration identity reached public projection")


def _is_fixed_public_limitation(value: dict[object, object]) -> bool:
    code = value.get("code")
    message = value.get("message")
    if not isinstance(code, str) or not isinstance(message, str):
        return False
    arbitration_message = _ARBITRATION_MESSAGES.get(code)
    if arbitration_message is not None:
        return message == arbitration_message
    return message in _NON_ARBITRATION_FIXED_LIMITATION_MESSAGES


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
    "PublicH2ProjectionBindingV1",
    "build_legacy_public_h2",
    "build_public_h2",
    "rebind_public_h2_projection",
]
