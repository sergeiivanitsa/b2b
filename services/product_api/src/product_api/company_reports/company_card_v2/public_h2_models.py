"""Closed recursive public H2 DTOs for company_public_h2_v1."""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .canonical_json import canonical_json_bytes

_CODE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_INN = re.compile(r"^(?:[0-9]{10}|[0-9]{12})$")
_OGRN = re.compile(r"^(?:[0-9]{13}|[0-9]{15})$")
_KPP = re.compile(r"^[0-9]{9}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_PATH = re.compile(r"^/[A-Za-z0-9_./?=&-]{1,2047}$")
_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")
_ACTIVITY = re.compile(r"^[0-9.]{2,16}$")
CanonicalDecimal = Annotated[str, StringConstraints(pattern=_DECIMAL.pattern)]

BLOCK_ORDER = ("hero_status", "narrative", "in_page_navigation", "requisites", "finance_f1_liquidity", "finance_f2_funding", "finance_f3_growth", "finance_f4_profit_per_100", "finance_f5_yearly_table", "arbitration_a1_activity", "arbitration_a2_roles", "arbitration_a3_outcomes", "arbitration_a4_case_amounts", "arbitration_a5_opponents", "sources_limitations", "neutral_actions")
COVERAGE_BLOCKS = ("requisites", "narrative", "finance_f1", "finance_f2", "finance_f3", "finance_f4", "finance_f5", "arbitration_a1", "arbitration_a2", "arbitration_a3", "arbitration_a4", "arbitration_a5", "sources_limitations")


class PublicH2Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def _nfc_scalars(self) -> "PublicH2Model":
        _walk(self)
        return self


def _walk(value: object) -> None:
    if isinstance(value, str):
        if value != unicodedata.normalize("NFC", value) or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise ValueError("public strings must be NFC Unicode scalars")
    elif isinstance(value, PublicH2Model):
        for nested in value.__dict__.values():
            _walk(nested)
    elif isinstance(value, (tuple, list)):
        for nested in value:
            _walk(nested)


def _text(value: str, maximum: int = 2048) -> str:
    if not value.strip() or len(value) > maximum:
        raise ValueError("public text must be nonblank and bounded")
    return value


class PublicH2Status(PublicH2Model):
    state: Literal["active", "inactive", "other"]
    code: str
    label: str
    effective_date: str | None = None

    @model_validator(mode="after")
    def _valid(self) -> "PublicH2Status":
        if not _CODE.fullmatch(self.code) or (self.effective_date and not _DATE.fullmatch(self.effective_date)):
            raise ValueError("invalid status")
        _text(self.label)
        return self


class PublicH2Identity(PublicH2Model):
    display_name: str
    legal_full_name: str
    short_name: str | None = None
    inn: str
    ogrn: str | None = None
    kpp: str | None = None
    registration_date: str | None = None
    dissolution_date: str | None = None
    status: PublicH2Status | None = None

    @model_validator(mode="after")
    def _valid(self) -> "PublicH2Identity":
        if not _INN.fullmatch(self.inn) or (self.ogrn and not _OGRN.fullmatch(self.ogrn)) or (self.kpp and not _KPP.fullmatch(self.kpp)):
            raise ValueError("invalid public identity")
        if any(item and not _DATE.fullmatch(item) for item in (self.registration_date, self.dissolution_date)):
            raise ValueError("invalid identity date")
        _text(self.display_name); _text(self.legal_full_name)
        if self.short_name is not None:
            _text(self.short_name)
        return self


class PublicLabeledCode(PublicH2Model):
    code: str
    label: str
    @model_validator(mode="after")
    def _valid(self) -> "PublicLabeledCode":
        if not _CODE.fullmatch(self.code):
            raise ValueError("invalid code")
        _text(self.label)
        return self


class PublicH2Address(PublicH2Model):
    display: str
    region: str | None = None
    is_inaccuracy: bool | None = None
    @model_validator(mode="after")
    def _valid(self) -> "PublicH2Address":
        _text(self.display)
        if self.region:
            _text(self.region)
        return self


class PublicCharterCapital(PublicH2Model):
    source_decimal: CanonicalDecimal
    unit_id: str
    display_exact: str
    unit_policy_version: str
    @model_validator(mode="after")
    def _valid(self) -> "PublicCharterCapital":
        if not _CODE.fullmatch(self.unit_id) or not _CODE.fullmatch(self.unit_policy_version):
            raise ValueError("invalid charter capital")
        _text(self.display_exact)
        return self


class PublicTaxMode(PublicH2Model):
    mode_id: Literal["common_mode", "usn_sign", "ausn_sign", "envd_sign", "eshn_sign", "npd_sign", "psn_sign", "srp_sign"]
    label: str
    applies: Literal[True] = True
    effective_date: str | None = None


class PublicActivity(PublicH2Model):
    code: str
    label: str
    is_primary: bool
    @model_validator(mode="after")
    def _valid(self) -> "PublicActivity":
        if not _ACTIVITY.fullmatch(self.code):
            raise ValueError("invalid activity")
        _text(self.label)
        return self


class PublicManager(PublicH2Model):
    name: str
    role: str
    appointed_at: str | None = None
    is_inaccuracy: bool | None = None


class PublicOwner(PublicH2Model):
    display_name: str
    owner_type: Literal["person", "organization", "state"]
    share_percent_decimal: CanonicalDecimal | None = None
    share_display: str | None = None
    effective_date: str | None = None
    @model_validator(mode="after")
    def _valid(self) -> "PublicOwner":
        if (self.share_percent_decimal is None) != (self.share_display is None):
            raise ValueError("owner share fields must co-occur")
        _text(self.display_name)
        return self


class PublicEmployees(PublicH2Model):
    count: int = Field(ge=0, le=999999999)
    period: str
    effective_date: str | None = None


class PublicH2Requisites(PublicH2Model):
    legal_form: PublicLabeledCode | None = None
    address: PublicH2Address | None = None
    charter_capital: PublicCharterCapital | None = None
    tax_modes: tuple[PublicTaxMode, ...] = Field(default=(), max_length=8)
    primary_activity: PublicActivity | None = None
    additional_activities: tuple[PublicActivity, ...] = Field(default=(), max_length=20)
    managers: tuple[PublicManager, ...] = Field(default=(), max_length=20)
    owners: tuple[PublicOwner, ...] = Field(default=(), max_length=50)
    employees: PublicEmployees | None = None
    tax_authority: PublicLabeledCode | None = None
    @model_validator(mode="after")
    def _valid(self) -> "PublicH2Requisites":
        if any(item.is_primary for item in self.additional_activities) or tuple(sorted(self.tax_modes, key=lambda item: item.mode_id)) != self.tax_modes:
            raise ValueError("invalid requisites ordering")
        return self


class PublicH2ChartComment(PublicH2Model):
    chart_id: Literal["finance_f1_liquidity", "finance_f2_funding", "finance_f3_growth", "finance_f4_profit_per_100", "finance_f5_yearly_table", "arbitration_a1_activity", "arbitration_a2_roles", "arbitration_a3_outcomes", "arbitration_a4_case_amounts", "arbitration_a5_opponents"]
    text: str
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=8)
    @model_validator(mode="after")
    def _valid(self) -> "PublicH2ChartComment":
        if not 1 <= len(self.text) <= 280 or len(set(self.evidence_ids)) != len(self.evidence_ids) or not all(_CODE.fullmatch(item) for item in self.evidence_ids):
            raise ValueError("invalid chart comment")
        return self


class PublicH2Narrative(PublicH2Model):
    mode: Literal["artifact", "deterministic_fallback"]
    renderer_version: str
    description: str
    statement_ids: tuple[str, ...] = Field(min_length=1, max_length=16)
    comments: tuple[PublicH2ChartComment, ...] = Field(default=(), max_length=2)
    render_digest: str
    @model_validator(mode="after")
    def _valid(self) -> "PublicH2Narrative":
        if not _CODE.fullmatch(self.renderer_version) or not 400 <= len(self.description) <= 700 or len(set(self.statement_ids)) != len(self.statement_ids) or not all(_CODE.fullmatch(item) for item in self.statement_ids) or not _DIGEST.fullmatch(self.render_digest):
            raise ValueError("invalid narrative")
        return self


class PublicH2Limitation(PublicH2Model):
    code: str
    block_id: str | None = None
    field_id: str | None = None
    message: str
    @model_validator(mode="after")
    def _valid(self) -> "PublicH2Limitation":
        if not _CODE.fullmatch(self.code) or self.block_id not in {*COVERAGE_BLOCKS, None} or (self.field_id and not _CODE.fullmatch(self.field_id)):
            raise ValueError("invalid limitation")
        _text(self.message, 512)
        return self


class PublicH2CoverageItem(PublicH2Model):
    block_id: str
    state: Literal["available", "available_empty", "partial", "missing", "not_requested", "failed", "conflict", "gate_closed", "legacy_unavailable"]
    population_scope: Literal["not_applicable", "complete_collection", "returned_slice"]
    total: int | None = Field(default=None, ge=0)
    returned: int | None = Field(default=None, ge=0)
    eligible: int | None = Field(default=None, ge=0)
    limitation_codes: tuple[str, ...] = Field(default=(), max_length=16)
    @model_validator(mode="after")
    def _valid(self) -> "PublicH2CoverageItem":
        if self.block_id not in COVERAGE_BLOCKS or len(set(self.limitation_codes)) != len(self.limitation_codes) or not all(_CODE.fullmatch(item) for item in self.limitation_codes):
            raise ValueError("invalid coverage")
        if self.state != "available" and not self.limitation_codes:
            raise ValueError("unavailable coverage requires limitation")
        return self


class PublicH2SourceItem(PublicH2Model):
    dataset: Literal["counterparty", "finance", "arbitration"]
    received_at: str
    effective_at: str | None = None
    period: str | None = None
    normalization_version: str
    evidence_version: str
    @model_validator(mode="after")
    def _valid(self) -> "PublicH2SourceItem":
        if not _UTC.fullmatch(self.received_at) or (self.effective_at and not _DATE.fullmatch(self.effective_at)) or not _CODE.fullmatch(self.normalization_version) or not _CODE.fullmatch(self.evidence_version):
            raise ValueError("invalid source")
        return self


class PublicFinanceMoney(PublicH2Model):
    source_thousand_decimal: CanonicalDecimal
    rub_decimal: CanonicalDecimal
    million_decimal: CanonicalDecimal
    display_exact: str
    display_compact: str
    unit_id: Literal["RUB"] = "RUB"
    unit_policy_version: Literal["datanewton_finance_thousand_rub_v2"] = "datanewton_finance_thousand_rub_v2"
    @model_validator(mode="after")
    def _valid(self) -> "PublicFinanceMoney":
        source = Decimal(self.source_thousand_decimal)
        if Decimal(self.rub_decimal) != source * Decimal("1000") or Decimal(self.million_decimal) != source / Decimal("1000"):
            raise ValueError("finance money units do not agree")
        _text(self.display_exact); _text(self.display_compact)
        return self


class PublicCaseAmount(PublicH2Model):
    source_decimal: CanonicalDecimal
    source_currency_id: str
    display_exact: str


class PublicChartAxis(PublicH2Model):
    axis_min_decimal: CanonicalDecimal
    axis_max_decimal: CanonicalDecimal
    @model_validator(mode="after")
    def _valid(self) -> "PublicChartAxis":
        if Decimal(self.axis_min_decimal) > 0 or Decimal(self.axis_max_decimal) < 0 or Decimal(self.axis_min_decimal) > Decimal(self.axis_max_decimal):
            raise ValueError("axis must contain zero and be ordered")
        return self


class PublicChartInterval(PublicH2Model):
    start_ratio_decimal: CanonicalDecimal
    end_ratio_decimal: CanonicalDecimal


class PublicChartPoint(PublicH2Model):
    ratio_decimal: CanonicalDecimal


class PublicDetailScope(PublicH2Model):
    population_scope: Literal["complete_collection", "returned_slice"]
    source_total: int | None = Field(default=None, ge=0)
    rows_received: int = Field(ge=0)
    eligible_total: int = Field(ge=0)
    shown: int = Field(ge=0, le=20)
    cap: Literal[20] = 20
    label: str
    @model_validator(mode="after")
    def _valid(self) -> "PublicDetailScope":
        if self.shown != min(self.eligible_total, 20):
            raise ValueError("invalid shown count")
        _text(self.label)
        return self


class PublicFinanceSegment(PublicH2Model):
    metric_id: Literal["1250", "1240", "1230", "1500"]
    value: PublicFinanceMoney
    geometry: PublicChartInterval


class PublicF1(PublicH2Model):
    view_id: Literal["finance_f1_liquidity"] = "finance_f1_liquidity"
    year: int = Field(ge=1900, le=2100)
    cash_1250: PublicFinanceMoney
    investments_1240: PublicFinanceMoney
    receivables_1230: PublicFinanceMoney
    short_liabilities_1500: PublicFinanceMoney
    available_without_inventory: PublicFinanceMoney
    difference: PublicFinanceMoney
    axis: PublicChartAxis
    segments: tuple[PublicFinanceSegment, PublicFinanceSegment, PublicFinanceSegment, PublicFinanceSegment]
    @model_validator(mode="after")
    def _valid(self) -> "PublicF1":
        if tuple(item.metric_id for item in self.segments) != ("1250", "1240", "1230", "1500"):
            raise ValueError("F1 segments are fixed")
        available = sum((Decimal(item.source_thousand_decimal) for item in (self.cash_1250, self.investments_1240, self.receivables_1230)), Decimal("0"))
        if Decimal(self.available_without_inventory.source_thousand_decimal) != available or Decimal(self.difference.source_thousand_decimal) != available - Decimal(self.short_liabilities_1500.source_thousand_decimal):
            raise ValueError("F1 arithmetic mismatch")
        return self


class PublicF2Period(PublicH2Model):
    year: int = Field(ge=1900, le=2100)
    state: Literal["available", "gap", "denominator_unavailable"]
    equity_1300: PublicFinanceMoney | None = None
    long_liabilities_1400: PublicFinanceMoney | None = None
    short_liabilities_1500: PublicFinanceMoney | None = None
    debt: PublicFinanceMoney | None = None
    denominator: PublicFinanceMoney | None = None
    equity_share_decimal: CanonicalDecimal | None = None
    debt_share_decimal: CanonicalDecimal | None = None
    mode: Literal["stacked_100", "diverging_signed", "unavailable"]
    axis: PublicChartAxis | None = None
    geometry_by_metric: tuple[PublicChartInterval | None, PublicChartInterval | None]
    @model_validator(mode="after")
    def _valid(self) -> "PublicF2Period":
        money = (self.equity_1300, self.long_liabilities_1400, self.short_liabilities_1500, self.debt, self.denominator)
        derived = (self.equity_share_decimal, self.debt_share_decimal, self.axis, *self.geometry_by_metric)
        if self.state == "gap" and (any(item is not None for item in money) or self.mode != "unavailable" or any(item is not None for item in derived)):
            raise ValueError("F2 gap cannot infer values")
        if self.state == "denominator_unavailable" and (any(item is None for item in money) or self.mode != "unavailable" or any(item is not None for item in derived)):
            raise ValueError("F2 denominator shape mismatch")
        if self.state == "available" and (any(item is None for item in money) or self.mode == "unavailable" or any(item is None for item in derived)):
            raise ValueError("F2 available shape mismatch")
        return self


class PublicF2(PublicH2Model):
    view_id: Literal["finance_f2_funding"] = "finance_f2_funding"
    anchor_year: int = Field(ge=1900, le=2100)
    window_start_year: int
    periods: tuple[PublicF2Period, PublicF2Period, PublicF2Period, PublicF2Period, PublicF2Period, PublicF2Period, PublicF2Period]
    @model_validator(mode="after")
    def _valid(self) -> "PublicF2":
        if self.window_start_year != self.anchor_year - 6 or tuple(row.year for row in self.periods) != tuple(range(self.window_start_year, self.anchor_year + 1)):
            raise ValueError("F2 periods must be seven ascending years")
        return self


class PublicF3Point(PublicH2Model):
    year: int = Field(ge=1900, le=2100)
    revenue_2110: PublicFinanceMoney | None = None
    assets_1600: PublicFinanceMoney | None = None
    revenue_yoy_decimal: CanonicalDecimal | None = None
    assets_yoy_decimal: CanonicalDecimal | None = None
    geometry_by_metric: tuple[PublicChartPoint | None, PublicChartPoint | None]


class PublicF3SeriesSummary(PublicH2Model):
    metric_id: Literal["revenue_2110", "assets_1600"]
    comparison_start_year: int | None = Field(default=None, ge=1900, le=2100)
    comparison_end_year: int | None = Field(default=None, ge=1900, le=2100)
    multiple_decimal: CanonicalDecimal | None = None
    change: PublicFinanceMoney | None = None
    axis: PublicChartAxis | None = None


class PublicF3(PublicH2Model):
    view_id: Literal["finance_f3_growth"] = "finance_f3_growth"
    anchor_year: int = Field(ge=1900, le=2100)
    window_start_year: int
    points: tuple[PublicF3Point, PublicF3Point, PublicF3Point, PublicF3Point, PublicF3Point, PublicF3Point, PublicF3Point]
    revenue_summary: PublicF3SeriesSummary
    assets_summary: PublicF3SeriesSummary
    @model_validator(mode="after")
    def _valid(self) -> "PublicF3":
        if self.window_start_year != self.anchor_year - 6 or tuple(row.year for row in self.points) != tuple(range(self.window_start_year, self.anchor_year + 1)) or self.revenue_summary.metric_id != "revenue_2110" or self.assets_summary.metric_id != "assets_1600":
            raise ValueError("F3 shape mismatch")
        return self


class PublicF4(PublicH2Model):
    view_id: Literal["finance_f4_profit_per_100"] = "finance_f4_profit_per_100"
    year: int = Field(ge=1900, le=2100)
    revenue_2110: PublicFinanceMoney
    gross_2100: PublicFinanceMoney
    operating_2200: PublicFinanceMoney
    net_2400: PublicFinanceMoney
    revenue_per_100_decimal: Literal["100"] | None = None
    gross_per_100_decimal: CanonicalDecimal | None = None
    operating_per_100_decimal: CanonicalDecimal | None = None
    net_per_100_decimal: CanonicalDecimal | None = None
    mode: Literal["per_100", "denominator_unavailable"]
    axis: PublicChartAxis | None = None
    geometry_by_metric: tuple[PublicChartInterval | None, PublicChartInterval | None, PublicChartInterval | None, PublicChartInterval | None]
    @model_validator(mode="after")
    def _valid(self) -> "PublicF4":
        derived = (self.revenue_per_100_decimal, self.gross_per_100_decimal, self.operating_per_100_decimal, self.net_per_100_decimal, self.axis, *self.geometry_by_metric)
        if (self.mode == "per_100") != all(item is not None for item in derived):
            raise ValueError("F4 denominator shape mismatch")
        return self


class PublicF5Cell(PublicH2Model):
    year: int = Field(ge=1900, le=2100)
    value: PublicFinanceMoney | None = None
    yoy_decimal: CanonicalDecimal | None = None


class PublicF5Row(PublicH2Model):
    metric_id: Literal["2110", "1600", "1250", "1240", "1230", "1210", "1500", "1300", "2400"]
    label: str
    cells: tuple[PublicF5Cell, PublicF5Cell, PublicF5Cell, PublicF5Cell, PublicF5Cell, PublicF5Cell, PublicF5Cell]


class PublicF5(PublicH2Model):
    view_id: Literal["finance_f5_yearly_table"] = "finance_f5_yearly_table"
    anchor_year: int = Field(ge=1900, le=2100)
    years: tuple[int, int, int, int, int, int, int]
    rows: tuple[PublicF5Row, PublicF5Row, PublicF5Row, PublicF5Row, PublicF5Row, PublicF5Row, PublicF5Row, PublicF5Row, PublicF5Row]
    @model_validator(mode="after")
    def _valid(self) -> "PublicF5":
        ids = ("2110", "1600", "1250", "1240", "1230", "1210", "1500", "1300", "2400")
        if self.years != tuple(range(self.anchor_year - 6, self.anchor_year + 1)) or tuple(row.metric_id for row in self.rows) != ids or any(tuple(cell.year for cell in row.cells) != self.years for row in self.rows):
            raise ValueError("F5 shape mismatch")
        return self


class PublicArbitrationSummary(PublicH2Model):
    source_total: int | None = Field(default=None, ge=0)
    rows_observed: int = Field(ge=0)
    unique_case_count: int = Field(ge=0)
    malformed_count: int = Field(ge=0)
    duplicate_identical_count: int = Field(ge=0)
    duplicate_conflict_count: int = Field(ge=0)
    collection_complete: bool
    completion_reason: str
    calendar_complete: bool
    calendar_scope: Literal["unverified", "all_time", "bounded_interval"]
    calendar_start_year: int | None = Field(default=None, ge=1900, le=2100)
    calendar_end_year: int | None = Field(default=None, ge=1900, le=2100)
    calendar_evidence_version: str | None = None
    observed_start_year: int | None = Field(default=None, ge=1900, le=2100)
    observed_end_year: int | None = Field(default=None, ge=1900, le=2100)
    unknown_year_count: int = Field(ge=0)
    zero_years_proven: bool


class PublicSafeOpponent(PublicH2Model):
    opponent_public_id: str
    display_name: str
    display_kind: Literal["legal", "state", "masked_natural", "masked_unknown"]


class PublicSafeCaseDetail(PublicH2Model):
    case_public_id: str
    case_number: str | None = None
    year: int | None = Field(default=None, ge=1900, le=2100)
    role: Literal["plaintiff", "respondent", "other", "unattributed"]
    outcome: Literal["won", "lost", "returned", "unknown"]
    result_detail: str | None = None
    amount: PublicCaseAmount | None = None
    start_date: str | None = None
    update_date: str | None = None
    days_to_last_update: int | None = Field(default=None, ge=0)
    instance_count: int | None = Field(default=None, ge=0)
    courts: tuple[str, ...] = Field(default=(), max_length=10)
    opponents: tuple[PublicSafeOpponent, ...] = Field(default=(), max_length=20)
    public_case_url: str | None = None


class PublicRoleDetail(PublicH2Model):
    role: Literal["plaintiff", "respondent", "other", "unattributed"]
    scope: PublicDetailScope
    cases: tuple[PublicSafeCaseDetail, ...] = Field(default=(), max_length=20)


class PublicA1YearBucket(PublicH2Model):
    year: int | None = Field(default=None, ge=1900, le=2100)
    plaintiff_count: int = Field(ge=0)
    respondent_count: int = Field(ge=0)
    other_count: int = Field(ge=0)
    unattributed_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    role_details: tuple[PublicRoleDetail, PublicRoleDetail, PublicRoleDetail, PublicRoleDetail]


class PublicA1(PublicH2Model):
    view_id: Literal["arbitration_a1_activity"] = "arbitration_a1_activity"
    summary: PublicArbitrationSummary
    displayed_start_year: int | None = Field(default=None, ge=1900, le=2100)
    displayed_end_year: int | None = Field(default=None, ge=1900, le=2100)
    buckets: tuple[PublicA1YearBucket, ...] = Field(default=(), max_length=11)
    all_time_case_count: int = Field(ge=0)


class PublicCountBar(PublicH2Model):
    category_id: Literal["plaintiff", "respondent", "other", "unattributed", "won", "lost", "returned", "unknown"]
    count: int = Field(ge=0)
    percent_decimal: CanonicalDecimal | None = None
    scope: PublicDetailScope
    cases: tuple[PublicSafeCaseDetail, ...] = Field(default=(), max_length=20)


class PublicA2(PublicH2Model):
    view_id: Literal["arbitration_a2_roles"] = "arbitration_a2_roles"
    summary: PublicArbitrationSummary
    denominator: int = Field(ge=0)
    bars: tuple[PublicCountBar, PublicCountBar, PublicCountBar, PublicCountBar]


class PublicA3(PublicH2Model):
    view_id: Literal["arbitration_a3_outcomes"] = "arbitration_a3_outcomes"
    summary: PublicArbitrationSummary
    denominator: int = Field(ge=0)
    bars: tuple[PublicCountBar, PublicCountBar, PublicCountBar, PublicCountBar]


class PublicA4CaseGeometry(PublicH2Model):
    case_public_id: str
    geometry: PublicChartInterval


class PublicA4CurrencyGroup(PublicH2Model):
    source_currency_id: str
    display_currency: str
    axis: PublicChartAxis
    case_geometries: tuple[PublicA4CaseGeometry, ...] = Field(default=(), max_length=20)
    scope: PublicDetailScope
    cases: tuple[PublicSafeCaseDetail, ...] = Field(default=(), max_length=20)


class PublicA4(PublicH2Model):
    view_id: Literal["arbitration_a4_case_amounts"] = "arbitration_a4_case_amounts"
    summary: PublicArbitrationSummary
    currency_groups: tuple[PublicA4CurrencyGroup, ...] = Field(default=(), max_length=16)
    missing_amount_count: int = Field(ge=0)
    missing_currency_count: int = Field(ge=0)


class PublicA5OpponentGroup(PublicH2Model):
    opponent_public_id: str
    display_name: str
    display_kind: Literal["legal", "state", "masked_natural", "masked_unknown"]
    case_count: int = Field(ge=1)
    case_scope: PublicDetailScope
    cases: tuple[PublicSafeCaseDetail, ...] = Field(default=(), max_length=20)


class PublicA5(PublicH2Model):
    view_id: Literal["arbitration_a5_opponents"] = "arbitration_a5_opponents"
    summary: PublicArbitrationSummary
    scope: PublicDetailScope
    groups: tuple[PublicA5OpponentGroup, ...] = Field(default=(), max_length=20)
    cases_without_safe_opponent: int = Field(ge=0)
    multi_opponent_case_count: int = Field(ge=0)


class PublicH2Action(PublicH2Model):
    action_id: Literal["check_another_company", "prepare_claim"]
    label: str
    path: str


class PublicH2Breadcrumb(PublicH2Model):
    label: str
    path: str
    current: bool


class PublicH2ClaimCta(PublicH2Model):
    action_id: Literal["prepare_claim"] = "prepare_claim"
    heading: Literal["Вам задолжали?"] = "Вам задолжали?"
    desktop_copy: Literal["Запустите процесс взыскания прямо сейчас: создайте досудебную претензию онлайн!"] = "Запустите процесс взыскания прямо сейчас: создайте досудебную претензию онлайн!"
    button_label: Literal["Создать претензию"] = "Создать претензию"
    path: str


class PublicH2Blocks(PublicH2Model):
    requisites: PublicH2Requisites
    finance_f1: PublicF1 | None = None
    finance_f2: PublicF2 | None = None
    finance_f3: PublicF3 | None = None
    finance_f4: PublicF4 | None = None
    finance_f5: PublicF5 | None = None
    arbitration_a1: PublicA1 | None = None
    arbitration_a2: PublicA2 | None = None
    arbitration_a3: PublicA3 | None = None
    arbitration_a4: PublicA4 | None = None
    arbitration_a5: PublicA5 | None = None


class CompanyPublicH2Response(PublicH2Model):
    contract_version: Literal["company_public_h2_v1"] = "company_public_h2_v1"
    projection_digest: str
    report_id: str
    report_version: Literal["1", "2", "3"]
    chart_facts_version: Literal["company_card_chart_facts_v1"]
    chart_facts_hash: str
    snapshot_capability: Literal["legacy_read_only", "card_v2"]
    projection_scope: Literal["active_publication", "staged_publication", "latest_unpublished"]
    canonical_path: str
    indexable: bool
    checked_at: str
    checked_date: str
    checked_date_display: str
    identity: PublicH2Identity
    narrative: PublicH2Narrative
    block_order: tuple[str, ...]
    blocks: PublicH2Blocks
    coverage: tuple[PublicH2CoverageItem, ...]
    sources: tuple[PublicH2SourceItem, ...]
    limitations: tuple[PublicH2Limitation, ...] = Field(default=(), max_length=128)
    actions: tuple[PublicH2Action, PublicH2Action]
    breadcrumbs: tuple[PublicH2Breadcrumb, PublicH2Breadcrumb]
    primary_claim_cta: PublicH2ClaimCta
    @model_validator(mode="after")
    def _valid(self) -> "CompanyPublicH2Response":
        if not _DIGEST.fullmatch(self.projection_digest) or not _DIGEST.fullmatch(self.chart_facts_hash) or not _UUID.fullmatch(self.report_id) or not _PATH.fullmatch(self.canonical_path) or not _UTC.fullmatch(self.checked_at) or not _DATE.fullmatch(self.checked_date):
            raise ValueError("invalid public root")
        if self.block_order != BLOCK_ORDER or tuple(item.block_id for item in self.coverage) != COVERAGE_BLOCKS:
            raise ValueError("invalid block or coverage order")
        if len(self.sources) not in {1, 2, 3} or tuple(item.dataset for item in self.sources) != ("counterparty", "finance", "arbitration")[:len(self.sources)]:
            raise ValueError("invalid source order")
        if (self.report_version == "3") != (self.snapshot_capability == "card_v2") or (self.report_version in {"1", "2"} and self.indexable) or (self.indexable and self.projection_scope != "active_publication"):
            raise ValueError("invalid version/indexability")
        if tuple(item.action_id for item in self.actions) != ("check_another_company", "prepare_claim") or self.breadcrumbs[0].current or not self.breadcrumbs[1].current:
            raise ValueError("invalid navigation")
        known = {item.code for item in self.limitations}
        if len(known) != len(self.limitations) or any(code not in known for item in self.coverage for code in item.limitation_codes):
            raise ValueError("invalid coverage limitation link")
        pairs = (("finance_f1", self.blocks.finance_f1), ("finance_f2", self.blocks.finance_f2), ("finance_f3", self.blocks.finance_f3), ("finance_f4", self.blocks.finance_f4), ("finance_f5", self.blocks.finance_f5), ("arbitration_a1", self.blocks.arbitration_a1), ("arbitration_a2", self.blocks.arbitration_a2), ("arbitration_a3", self.blocks.arbitration_a3), ("arbitration_a4", self.blocks.arbitration_a4), ("arbitration_a5", self.blocks.arbitration_a5))
        for block, value in pairs:
            if (next(item.state for item in self.coverage if item.block_id == block) == "available") != (value is not None):
                raise ValueError("coverage and block disagree")
        if len(canonical_json_bytes(self.model_dump(mode="json"))) > 524288:
            raise ValueError("public_projection_too_large")
        return self


__all__ = [name for name in globals() if name.startswith("Public") or name in {"BLOCK_ORDER", "COVERAGE_BLOCKS", "CanonicalDecimal", "CompanyPublicH2Response"}]
