"""Closed recursive public H2 DTOs for company_public_h2_v1."""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationInfo, model_validator

from .canonical_json import canonical_digest, canonical_json_bytes

_CODE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_INN = re.compile(r"^(?:[0-9]{10}|[0-9]{12})$")
_OGRN = re.compile(r"^(?:[0-9]{13}|[0-9]{15})$")
_KPP = re.compile(r"^[0-9]{9}$")
_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_PATH = re.compile(r"^/[A-Za-z0-9_./?=&-]{1,2047}$")
_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")
_ACTIVITY = re.compile(r"^[0-9.]{2,16}$")
_CASE_PUBLIC_ID = re.compile(r"^case_([0-9]{6})$")
_OPPONENT_PUBLIC_ID = re.compile(r"^opponent_([0-9]{6})$")
_FIRST_NUMBER = re.compile(r"^(?:(?:А|A)[0-9]{1,3}|СИП)-[0-9]{1,12}/[0-9]{4}$")
CanonicalDecimal = Annotated[str, StringConstraints(pattern=_DECIMAL.pattern)]

BLOCK_ORDER = ("hero_status", "narrative", "in_page_navigation", "requisites", "finance_f1_liquidity", "finance_f2_funding", "finance_f3_growth", "finance_f4_profit_per_100", "finance_f5_yearly_table", "arbitration_a1_activity", "arbitration_a2_roles", "arbitration_a3_outcomes", "arbitration_a4_case_amounts", "arbitration_a5_opponents", "sources_limitations", "neutral_actions")
COVERAGE_BLOCKS = ("requisites", "narrative", "finance_f1", "finance_f2", "finance_f3", "finance_f4", "finance_f5", "arbitration_a1", "arbitration_a2", "arbitration_a3", "arbitration_a4", "arbitration_a5", "sources_limitations")
_ARBITRATION_BLOCKS = COVERAGE_BLOCKS[7:12]
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
_ARBITRATION_COMPLETION_PRECEDENCE = (
    "operation_gate_closed",
    "evidence_gate_closed",
    "privacy_key_unavailable",
    "provider_error",
    "provider_binding_invalid",
    "lexical_transport_invalid",
    "envelope_invalid",
    "malformed_rows",
    "duplicate_conflict",
    "oversized_case",
    "storage_cap_exhausted",
    "opponent_group_cap_exhausted",
    "source_total_exceeds_cap",
    "complete",
)
_ARBITRATION_COMPLETION_REASONS = set(_ARBITRATION_COMPLETION_PRECEDENCE)
_ARBITRATION_LIMITATION_CODES = {
    *(_ARBITRATION_COMPLETION_REASONS - {"complete"}),
    "arbitration_calendar_unverified",
    "arbitration_unknown_year",
    "arbitration_date_invalid",
    "arbitration_date_inversion",
    "arbitration_year_conflict",
    "arbitration_first_number_unavailable",
    "arbitration_first_number_identity_collision",
    "arbitration_amount_missing",
    "arbitration_amount_invalid",
    "arbitration_currency_missing",
    "arbitration_currency_unidentified",
    "arbitration_currency_invalid",
    "arbitration_public_projection_cap_exhausted",
}
_ARBITRATION_CAP_CODE = "arbitration_public_projection_cap_exhausted"
_ARBITRATION_SOURCE_NORMALIZATION = "company_card_arbitration_normalization_v2"
_ARBITRATION_SOURCE_EVIDENCE = "datanewton_arbitration_registry_v2"
_MAX_ARBITRATION_ROWS = 1_000
_MAX_SOURCE_TOTAL = (1 << 63) - 1
_ARBITRATION_A1_LIMITATIONS = {
    "arbitration_calendar_unverified",
    "arbitration_unknown_year",
}
_ARBITRATION_A4_LIMITATIONS = {
    "arbitration_amount_missing",
    "arbitration_amount_invalid",
    "arbitration_currency_missing",
    "arbitration_currency_unidentified",
    "arbitration_currency_invalid",
}
_ARBITRATION_LIMITATION_PRECEDENCE = (
    *_ARBITRATION_COMPLETION_PRECEDENCE[:-1],
    "arbitration_calendar_unverified",
    "arbitration_unknown_year",
    "arbitration_date_invalid",
    "arbitration_date_inversion",
    "arbitration_year_conflict",
    "arbitration_first_number_unavailable",
    "arbitration_first_number_identity_collision",
    "arbitration_amount_missing",
    "arbitration_amount_invalid",
    "arbitration_currency_missing",
    "arbitration_currency_unidentified",
    "arbitration_currency_invalid",
)
ARBITRATION_PUBLIC_LIMITATION_MESSAGES = {
    "operation_gate_closed": "Сбор арбитражных данных отключён операционным ограничением.",
    "evidence_gate_closed": "Арбитражные данные недоступны до подтверждения evidence gate.",
    "privacy_key_unavailable": "Арбитражные данные недоступны из-за закрытого privacy-контура.",
    "provider_error": "Подтверждённый источник арбитражных данных временно недоступен.",
    "provider_binding_invalid": "Ответ источника не прошёл проверку привязки к отчёту.",
    "lexical_transport_invalid": "Числовой транспорт ответа источника не подтверждён.",
    "envelope_invalid": "Структура ответа источника не прошла проверку.",
    "malformed_rows": "Часть строк источника не прошла проверку структуры.",
    "duplicate_conflict": "Конфликтующие дубликаты дел исключены из представления.",
    "oversized_case": "Строка дела превысила допустимый безопасный размер.",
    "storage_cap_exhausted": "Сохранён безопасный префикс данных в пределах лимита.",
    "opponent_group_cap_exhausted": "Группировка скрытых сторон недоступна из-за лимита приватности.",
    "source_total_exceeds_cap": "Источник сообщает больше дел, чем возвращено в подтверждённом срезе.",
    "arbitration_calendar_unverified": "Календарная полнота арбитражных данных не подтверждена.",
    "arbitration_unknown_year": "Для части дел год не подтверждён.",
    "arbitration_date_invalid": "Для части дел дата не прошла строгую проверку.",
    "arbitration_date_inversion": "Для части дел порядок дат не подтверждён.",
    "arbitration_year_conflict": "Для части дел год не согласуется с датой начала.",
    "arbitration_first_number_unavailable": "Для части дел безопасный номер не опубликован.",
    "arbitration_first_number_identity_collision": "Номер дела скрыт из-за совпадения с приватным идентификатором.",
    "arbitration_amount_missing": "Для части дел цена иска отсутствует.",
    "arbitration_amount_invalid": "Для части дел цена иска не прошла точную числовую проверку.",
    "arbitration_currency_missing": "Для части дел валюта цены иска отсутствует.",
    "arbitration_currency_unidentified": "Для части дел валюта цены иска не идентифицирована как рубль.",
    "arbitration_currency_invalid": "Для части дел значение валюты некорректно.",
    _ARBITRATION_CAP_CODE: "Арбитражные представления не опубликованы из-за предельного размера ответа.",
}


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
        if self.state not in {"available", "available_empty", "missing"} and not self.limitation_codes:
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
        with localcontext() as context:
            # A public DTO must not inherit a caller's ambient Decimal
            # precision while checking a 40-digit source value.
            context.prec = 128
            context.rounding = ROUND_HALF_UP
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


def _in_axis(value: Decimal, axis: "PublicChartAxis") -> bool:
    return Decimal(axis.axis_min_decimal) <= value <= Decimal(axis.axis_max_decimal)


_EXACT_DECIMAL_PRECISION = 128
_DERIVED_QUANTUM = Decimal("0.000001")
_F5_LABELS = (
    "Продажи", "Всё имущество", "Деньги на счетах", "Финансовые вложения",
    "Долги покупателей", "Запасы", "Ближайшие обязательства", "Свои средства",
    "Чистая прибыль",
)


def _money_source(value: "PublicFinanceMoney") -> Decimal:
    return Decimal(value.source_thousand_decimal)


def _exact_axis(values: tuple[Decimal, ...]) -> tuple[Decimal, Decimal]:
    return min(Decimal("0"), *values), max(Decimal("0"), *values)


def _axis_pair(axis: "PublicChartAxis") -> tuple[Decimal, Decimal]:
    return Decimal(axis.axis_min_decimal), Decimal(axis.axis_max_decimal)


def _derived_ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 34
        context.rounding = ROUND_HALF_UP
        return (numerator / denominator * Decimal("100")).quantize(
            _DERIVED_QUANTUM,
            rounding=ROUND_HALF_UP,
        )


def _derived_shares(
    equity: Decimal,
    debt: Decimal,
    denominator: Decimal,
) -> tuple[Decimal, Decimal]:
    with localcontext() as context:
        context.prec = 34
        context.rounding = ROUND_HALF_UP
        unrounded = (
            equity / denominator * Decimal("100"),
            debt / denominator * Decimal("100"),
        )
        shares = [
            value.quantize(_DERIVED_QUANTUM, rounding=ROUND_HALF_UP)
            for value in unrounded
        ]
        residual = Decimal("100") - sum(shares, Decimal("0"))
        winner = max(
            range(2),
            key=lambda index: (abs(unrounded[index] - shares[index]), -index),
        )
        shares[winner] += residual
        return shares[0], shares[1]


def _derived_yoy(previous: Decimal | None, current: Decimal | None) -> Decimal | None:
    if previous is None or current is None or previous <= 0:
        return None
    return _derived_ratio(current - previous, previous)


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
        with localcontext() as context:
            context.prec = _EXACT_DECIMAL_PRECISION
            context.rounding = ROUND_HALF_UP
            cash = _money_source(self.cash_1250)
            investments = _money_source(self.investments_1240)
            receivables = _money_source(self.receivables_1230)
            liabilities = _money_source(self.short_liabilities_1500)
            cash_and_investments = cash + investments
            available = cash_and_investments + receivables
            difference = available - liabilities
        if (
            _money_source(self.available_without_inventory) != available
            or _money_source(self.difference) != difference
        ):
            raise ValueError("F1 arithmetic mismatch")
        expected = (
            (Decimal("0"), cash),
            (cash, cash_and_investments),
            (cash_and_investments, available),
            (Decimal("0"), liabilities),
        )
        for segment, endpoints in zip(self.segments, expected):
            actual = (Decimal(segment.geometry.start_ratio_decimal), Decimal(segment.geometry.end_ratio_decimal))
            if actual != endpoints:
                raise ValueError("F1 geometry mismatch")
            if not all(_in_axis(endpoint, self.axis) for endpoint in actual):
                raise ValueError("F1 geometry outside axis")
        if not all(_in_axis(endpoint, self.axis) for endpoint in (*expected[2], *expected[3], Decimal(self.difference.source_thousand_decimal))):
            raise ValueError("F1 endpoint outside axis")
        expected_axis = _exact_axis((
            cash, investments, receivables, liabilities,
            cash_and_investments, available, difference,
        ))
        if _axis_pair(self.axis) != expected_axis:
            raise ValueError("F1 axis mismatch")
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
        if self.state in {"available", "denominator_unavailable"}:
            assert all(item is not None for item in money)
            equity = _money_source(self.equity_1300)
            long_debt = _money_source(self.long_liabilities_1400)
            short_debt = _money_source(self.short_liabilities_1500)
            with localcontext() as context:
                context.prec = _EXACT_DECIMAL_PRECISION
                context.rounding = ROUND_HALF_UP
                expected_debt = long_debt + short_debt
                expected_denominator = equity + expected_debt
            if (
                _money_source(self.debt) != expected_debt
                or _money_source(self.denominator) != expected_denominator
            ):
                raise ValueError("F2 source arithmetic mismatch")
            if self.state == "denominator_unavailable":
                if expected_denominator > 0:
                    raise ValueError("F2 unavailable denominator must be non-positive")
                return self

            if expected_denominator <= 0:
                raise ValueError("F2 available denominator must be positive")
            assert self.axis is not None
            actual_shares = (
                Decimal(self.equity_share_decimal),
                Decimal(self.debt_share_decimal),
            )
            expected_shares = _derived_shares(equity, expected_debt, expected_denominator)
            if actual_shares != expected_shares:
                raise ValueError("F2 share arithmetic mismatch")
            expected_mode = (
                "diverging_signed"
                if any(value < 0 for value in expected_shares)
                else "stacked_100"
            )
            if self.mode != expected_mode:
                raise ValueError("F2 mode mismatch")
            first, second = self.geometry_by_metric
            assert first is not None and second is not None
            first_interval = (Decimal(first.start_ratio_decimal), Decimal(first.end_ratio_decimal))
            second_interval = (Decimal(second.start_ratio_decimal), Decimal(second.end_ratio_decimal))
            if self.mode == "stacked_100":
                expected_axis = (Decimal("0"), Decimal("100"))
                expected_intervals = (
                    (Decimal("0"), expected_shares[0]),
                    (expected_shares[0], Decimal("100")),
                )
            else:
                expected_axis = _exact_axis(expected_shares)
                expected_intervals = (
                    (Decimal("0"), expected_shares[0]),
                    (Decimal("0"), expected_shares[1]),
                )
            if _axis_pair(self.axis) != expected_axis:
                raise ValueError("F2 axis mismatch")
            if (first_interval, second_interval) != expected_intervals:
                raise ValueError("F2 geometry mismatch")
            if not all(_in_axis(endpoint, self.axis) for endpoint in (*first_interval, *second_interval)):
                raise ValueError("F2 geometry outside axis")
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
        series = (
            (
                self.revenue_summary,
                tuple(point.revenue_2110 for point in self.points),
                tuple(point.revenue_yoy_decimal for point in self.points),
                tuple(point.geometry_by_metric[0] for point in self.points),
            ),
            (
                self.assets_summary,
                tuple(point.assets_1600 for point in self.points),
                tuple(point.assets_yoy_decimal for point in self.points),
                tuple(point.geometry_by_metric[1] for point in self.points),
            ),
        )
        for summary, monies, yoy_values, geometries in series:
            decimals = tuple(_money_source(item) if item is not None else None for item in monies)
            for index, (money, value, yoy, geometry) in enumerate(
                zip(monies, decimals, yoy_values, geometries)
            ):
                if (money is None) != (geometry is None):
                    raise ValueError("F3 gap geometry mismatch")
                if money is not None:
                    assert value is not None and geometry is not None
                    if Decimal(geometry.ratio_decimal) != value:
                        raise ValueError("F3 point geometry mismatch")
                previous = decimals[index - 1] if index > 0 else None
                expected_yoy = _derived_yoy(previous, value)
                actual_yoy = Decimal(yoy) if yoy is not None else None
                if actual_yoy != expected_yoy:
                    raise ValueError("F3 YoY mismatch")

            available = tuple(
                (point.year, value)
                for point, value in zip(self.points, decimals)
                if value is not None
            )
            if not available:
                if any(value is not None for value in (
                    summary.comparison_start_year,
                    summary.comparison_end_year,
                    summary.multiple_decimal,
                    summary.change,
                    summary.axis,
                )):
                    raise ValueError("F3 empty summary mismatch")
                continue
            expected_axis = _exact_axis(tuple(value for _, value in available))
            if summary.axis is None or _axis_pair(summary.axis) != expected_axis:
                raise ValueError("F3 series axis mismatch")
            if len(available) < 2:
                if any(value is not None for value in (
                    summary.comparison_start_year,
                    summary.comparison_end_year,
                    summary.multiple_decimal,
                    summary.change,
                )):
                    raise ValueError("F3 single-point summary mismatch")
                continue
            first_year, first = available[0]
            last_year, last = available[-1]
            with localcontext() as context:
                context.prec = _EXACT_DECIMAL_PRECISION
                context.rounding = ROUND_HALF_UP
                expected_change = last - first
            expected_multiple: Decimal | None = None
            if first > 0 and last > 0:
                with localcontext() as context:
                    context.prec = 34
                    context.rounding = ROUND_HALF_UP
                    expected_multiple = (last / first).quantize(
                        _DERIVED_QUANTUM,
                        rounding=ROUND_HALF_UP,
                    )
            if (
                summary.comparison_start_year != first_year
                or summary.comparison_end_year != last_year
                or (Decimal(summary.multiple_decimal) if summary.multiple_decimal is not None else None)
                != expected_multiple
                or summary.change is None
                or _money_source(summary.change) != expected_change
            ):
                raise ValueError("F3 summary mismatch")
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
        if (
            (self.mode == "per_100" and not all(item is not None for item in derived))
            or (self.mode == "denominator_unavailable" and any(item is not None for item in derived))
        ):
            raise ValueError("F4 denominator shape mismatch")
        revenue = _money_source(self.revenue_2110)
        source_values = (
            _money_source(self.gross_2100),
            _money_source(self.operating_2200),
            _money_source(self.net_2400),
        )
        if self.mode == "denominator_unavailable":
            if revenue > 0:
                raise ValueError("F4 unavailable denominator must be non-positive")
            return self
        if revenue <= 0:
            raise ValueError("F4 per-100 denominator must be positive")
        if self.mode == "per_100":
            assert self.axis is not None
            expected_values = (
                Decimal("100"),
                *tuple(_derived_ratio(value, revenue) for value in source_values),
            )
            actual_values = (
                Decimal(self.revenue_per_100_decimal),
                Decimal(self.gross_per_100_decimal),
                Decimal(self.operating_per_100_decimal),
                Decimal(self.net_per_100_decimal),
            )
            if actual_values != expected_values:
                raise ValueError("F4 ratio arithmetic mismatch")
            if _axis_pair(self.axis) != _exact_axis(expected_values):
                raise ValueError("F4 axis mismatch")
            if any(not _in_axis(value, self.axis) for value in actual_values):
                raise ValueError("F4 geometry outside axis")
            for interval, value in zip(self.geometry_by_metric, actual_values):
                assert interval is not None
                if Decimal(interval.start_ratio_decimal) != 0 or Decimal(interval.end_ratio_decimal) != value:
                    raise ValueError("F4 geometry mismatch")
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
        if (
            self.years != tuple(range(self.anchor_year - 6, self.anchor_year + 1))
            or tuple(row.metric_id for row in self.rows) != ids
            or tuple(row.label for row in self.rows) != _F5_LABELS
            or any(tuple(cell.year for cell in row.cells) != self.years for row in self.rows)
        ):
            raise ValueError("F5 shape mismatch")
        for row in self.rows:
            values = tuple(
                _money_source(cell.value) if cell.value is not None else None
                for cell in row.cells
            )
            for index, cell in enumerate(row.cells):
                expected = _derived_yoy(values[index - 1] if index > 0 else None, values[index])
                actual = Decimal(cell.yoy_decimal) if cell.yoy_decimal is not None else None
                if actual != expected:
                    raise ValueError("F5 YoY mismatch")
        return self


class PublicArbitrationSummary(PublicH2Model):
    source_total: int | None = Field(default=None, ge=0, le=_MAX_SOURCE_TOTAL)
    rows_observed: int = Field(ge=0, le=_MAX_ARBITRATION_ROWS)
    unique_case_count: int = Field(ge=0, le=_MAX_ARBITRATION_ROWS)
    malformed_count: int = Field(ge=0, le=_MAX_ARBITRATION_ROWS)
    duplicate_identical_count: int = Field(ge=0, le=_MAX_ARBITRATION_ROWS)
    duplicate_conflict_count: int = Field(ge=0, le=_MAX_ARBITRATION_ROWS)
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


def _arbitration_values(response: "CompanyPublicH2Response") -> tuple[object | None, ...]:
    return tuple(getattr(response.blocks, block) for block in _ARBITRATION_BLOCKS)


def _arbitration_coverage(
    response: "CompanyPublicH2Response",
) -> tuple[PublicH2CoverageItem, ...]:
    by_id = {item.block_id: item for item in response.coverage}
    return tuple(by_id[block] for block in _ARBITRATION_BLOCKS)


def _arbitration_limitations(
    response: "CompanyPublicH2Response",
) -> tuple[PublicH2Limitation, ...]:
    return tuple(
        item for item in response.limitations
        if item.code in _ARBITRATION_LIMITATION_CODES
    )


def _is_arbitration_linked_limitation(item: PublicH2Limitation) -> bool:
    return (
        item.block_id in _ARBITRATION_BLOCKS
        or item.code.startswith("arbitration_")
        or item.code == "opponent_group_cap_exhausted"
    )


def _validate_arbitration_limitation_catalog(
    response: "CompanyPublicH2Response",
) -> None:
    if (
        any(
            _is_arbitration_linked_limitation(item)
            and item.code not in _ARBITRATION_LIMITATION_CODES
            for item in response.limitations
        )
        or any(
            code not in _ARBITRATION_LIMITATION_CODES
            for item in _arbitration_coverage(response)
            for code in item.limitation_codes
        )
    ):
        raise ValueError("unknown policy-v3 arbitration limitation")
    if any(
        item.message != ARBITRATION_PUBLIC_LIMITATION_MESSAGES[item.code]
        for item in _arbitration_limitations(response)
    ):
        raise ValueError("invalid policy-v3 arbitration limitation message")


def _valid_frozen_source_prefix(response: "CompanyPublicH2Response") -> bool:
    if len(response.sources) < 2:
        return False
    counterparty, finance = response.sources[:2]
    return (
        counterparty.dataset == "counterparty"
        and finance.dataset == "finance"
        and counterparty.received_at == response.checked_at
        and finance.received_at == response.checked_at
        and counterparty.effective_at is None
        and finance.effective_at is None
        and counterparty.period is None
        and finance.period is None
        and counterparty.normalization_version == "company_card_v2_v1"
        and finance.normalization_version == "company_card_v2_v1"
        and counterparty.evidence_version == finance.evidence_version
    )


def _is_exact_bound_arbitration_source(item: PublicH2SourceItem) -> bool:
    return (
        item.dataset == "arbitration"
        and item.effective_at is None
        and item.period is None
        and item.normalization_version == _ARBITRATION_SOURCE_NORMALIZATION
        and item.evidence_version == _ARBITRATION_SOURCE_EVIDENCE
    )


def _v3_semantic_signal(response: "CompanyPublicH2Response") -> bool:
    coverage = _arbitration_coverage(response)
    if any(
        code in _ARBITRATION_LIMITATION_CODES
        for item in coverage
        for code in item.limitation_codes
    ) or any(
        item.code in _ARBITRATION_LIMITATION_CODES
        for item in response.limitations
    ):
        return True
    arbitration_sources = tuple(
        item for item in response.sources if item.dataset == "arbitration"
    )
    if any(
        item.normalization_version == _ARBITRATION_SOURCE_NORMALIZATION
        or item.evidence_version == _ARBITRATION_SOURCE_EVIDENCE
        for item in arbitration_sources
    ):
        return True
    for block in _arbitration_values(response):
        if block is None:
            continue
        dumped = block.model_dump(mode="json")
        stack: list[object] = [dumped]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
            elif isinstance(value, str) and (
                _CASE_PUBLIC_ID.fullmatch(value)
                or _OPPONENT_PUBLIC_ID.fullmatch(value)
            ):
                return True
    return False


def _exact_decimal(value: Decimal) -> str:
    if value == 0:
        return "0"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _expected_percentages(
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
    return tuple(_exact_decimal(value) for value in rounded)  # type: ignore[return-value]


def _public_id_ordinal(value: str, pattern: re.Pattern[str], maximum: int) -> int:
    matched = pattern.fullmatch(value)
    if matched is None:
        raise ValueError("invalid policy-v3 public ordinal")
    ordinal = int(matched.group(1))
    if not 1 <= ordinal <= maximum:
        raise ValueError("invalid policy-v3 public ordinal")
    return ordinal


def _policy_v3_date(raw: str | None) -> date | None:
    if raw is None:
        return None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("invalid policy-v3 case date") from exc
    if parsed.isoformat() != raw:
        raise ValueError("invalid policy-v3 case date")
    return parsed


def _policy_v3_decimal(raw: str) -> Decimal:
    if raw == "-0":
        raise ValueError("negative zero is invalid in policy-v3 decimal")
    return Decimal(raw)


def _detail_order_key(value: PublicSafeCaseDetail) -> tuple[object, ...]:
    def descending_date(raw: str | None) -> tuple[int, int]:
        parsed = _policy_v3_date(raw)
        if parsed is None:
            return (1, 0)
        return (0, -parsed.toordinal())

    return (
        value.year is None,
        -(value.year or 0),
        *descending_date(value.start_date),
        *descending_date(value.update_date),
        value.case_public_id,
    )


def _validate_case_detail(value: PublicSafeCaseDetail) -> None:
    _public_id_ordinal(value.case_public_id, _CASE_PUBLIC_ID, 1000)
    if value.case_number is not None and _FIRST_NUMBER.fullmatch(value.case_number) is None:
        raise ValueError("invalid policy-v3 public case number")
    if value.result_detail is not None or value.instance_count is not None:
        raise ValueError("deferred policy-v3 case detail is non-null")
    if value.courts or value.opponents or value.public_case_url is not None:
        raise ValueError("private policy-v3 case detail escaped")
    if value.amount is not None:
        _policy_v3_decimal(value.amount.source_decimal)
        expected_display = (
            value.amount.source_decimal.replace("-", "−").replace(".", ",") + " ₽"
        )
        if (
            value.amount.source_currency_id != "RUB"
            or value.amount.display_exact != expected_display
        ):
            raise ValueError("invalid policy-v3 RUB amount")
    start = _policy_v3_date(value.start_date)
    update = _policy_v3_date(value.update_date)
    if value.year is not None and start is not None and value.year != start.year:
        raise ValueError("invalid policy-v3 year/date pairing")
    if value.role in {"other", "unattributed"} and value.outcome != "unknown":
        raise ValueError("invalid policy-v3 role/outcome pairing")
    expected_days = (
        (update - start).days
        if start is not None and update is not None and update >= start
        else None
    )
    if value.days_to_last_update != expected_days:
        raise ValueError("invalid policy-v3 safe duration")


def _validate_case_sequence(values: tuple[PublicSafeCaseDetail, ...]) -> None:
    if len({item.case_public_id for item in values}) != len(values):
        raise ValueError("duplicate policy-v3 case detail")
    for item in values:
        _validate_case_detail(item)
    if values != tuple(sorted(values, key=_detail_order_key)):
        raise ValueError("policy-v3 case details are not ordered")


def _a4_detail_order_key(value: PublicSafeCaseDetail) -> tuple[object, ...]:
    if value.amount is None:
        raise ValueError("policy-v3 A4 detail lacks an amount")
    amount = _policy_v3_decimal(value.amount.source_decimal)
    if value.update_date is None:
        update_key = (1, 0)
    else:
        try:
            update = date.fromisoformat(value.update_date)
        except ValueError as exc:
            raise ValueError("invalid policy-v3 case date") from exc
        if update.isoformat() != value.update_date:
            raise ValueError("invalid policy-v3 case date")
        update_key = (0, -update.toordinal())
    return (
        amount.copy_abs().copy_negate(),
        amount.copy_negate(),
        value.year is None,
        -(value.year or 0),
        *update_key,
        value.case_public_id,
    )


def _validate_a4_case_sequence(
    values: tuple[PublicSafeCaseDetail, ...],
) -> None:
    if len({item.case_public_id for item in values}) != len(values):
        raise ValueError("duplicate policy-v3 A4 case detail")
    for item in values:
        _validate_case_detail(item)
    if values != tuple(sorted(values, key=_a4_detail_order_key)):
        raise ValueError("policy-v3 A4 case details are not ordered")


def _validate_scope(
    scope: PublicDetailScope,
    *,
    population_scope: str,
    source_total: int | None,
    rows_received: int,
    eligible_total: int,
    noun: Literal["дел", "сторон"],
) -> None:
    shown = min(eligible_total, 20)
    if (
        scope.population_scope != population_scope
        or scope.source_total != source_total
        or scope.rows_received != rows_received
        or scope.eligible_total != eligible_total
        or scope.shown != shown
        or scope.cap != 20
        or scope.label != f"показано {shown} из {eligible_total} {noun}"
    ):
        raise ValueError("invalid policy-v3 detail scope")


def _validate_summary(
    summary: PublicArbitrationSummary,
    *,
    coverage: tuple[PublicH2CoverageItem, ...],
) -> tuple[str, int | None, int, int]:
    a1 = coverage[0]
    if (
        summary.calendar_complete
        or summary.calendar_scope != "unverified"
        or summary.calendar_start_year is not None
        or summary.calendar_end_year is not None
        or summary.calendar_evidence_version is not None
        or summary.zero_years_proven
    ):
        raise ValueError("invalid policy-v3 unverified calendar")
    if (summary.observed_start_year is None) != (summary.observed_end_year is None):
        raise ValueError("invalid policy-v3 observed year bounds")
    if (
        summary.observed_start_year is not None
        and summary.observed_start_year > summary.observed_end_year
    ):
        raise ValueError("invalid policy-v3 observed year bounds")
    if (summary.observed_start_year is None) != (
        summary.unique_case_count == summary.unknown_year_count
    ):
        raise ValueError("policy-v3 observed bounds disagree with known population")
    if summary.unknown_year_count > summary.unique_case_count:
        raise ValueError("invalid policy-v3 unknown-year count")
    if (
        summary.malformed_count > summary.rows_observed
        or summary.unique_case_count > summary.rows_observed
        or summary.duplicate_identical_count > summary.rows_observed
        or summary.duplicate_conflict_count > summary.rows_observed // 2
        or summary.malformed_count
        + summary.unique_case_count
        + summary.duplicate_identical_count
        + 2 * summary.duplicate_conflict_count
        > summary.rows_observed
    ):
        raise ValueError("invalid policy-v3 public counters")
    if summary.completion_reason not in _ARBITRATION_COMPLETION_REASONS:
        raise ValueError("invalid policy-v3 completion reason")
    if summary.collection_complete != (summary.completion_reason == "complete"):
        raise ValueError("invalid policy-v3 collection completeness")
    if summary.collection_complete and (
        summary.malformed_count != 0
        or summary.duplicate_conflict_count != 0
        or summary.unique_case_count + summary.duplicate_identical_count
        != summary.rows_observed
    ):
        raise ValueError("complete policy-v3 counters do not conserve rows")
    if (
        summary.source_total is None
        or summary.source_total < summary.rows_observed
        or (
            summary.source_total <= _MAX_ARBITRATION_ROWS
            and summary.rows_observed != summary.source_total
        )
        or (
            summary.source_total > _MAX_ARBITRATION_ROWS
            and summary.rows_observed == 0
        )
        or (
            summary.collection_complete
            and summary.source_total != summary.rows_observed
        )
    ):
        raise ValueError("invalid policy-v3 source population")
    population_scope = (
        "complete_collection" if summary.collection_complete else "returned_slice"
    )
    if (
        a1.population_scope != population_scope
        or a1.total != summary.source_total
        or a1.returned != summary.rows_observed
        or a1.eligible != summary.unique_case_count
    ):
        raise ValueError("policy-v3 summary and coverage disagree")
    return population_scope, summary.source_total, summary.rows_observed, summary.unique_case_count


def _validate_policy_v3_views(response: "CompanyPublicH2Response") -> None:
    coverage = _arbitration_coverage(response)
    a1, a2, a3, a4, a5 = _arbitration_values(response)
    if not isinstance(a1, PublicA1) or not isinstance(a2, PublicA2) or not isinstance(a3, PublicA3) or not isinstance(a4, PublicA4):
        raise ValueError("policy-v3 admitted collection requires A1-A4")
    overflow = (
        a5 is None
        and coverage[4].state == "failed"
        and coverage[4].population_scope == "returned_slice"
        and coverage[4].eligible is None
        and coverage[4].limitation_codes == ("opponent_group_cap_exhausted",)
    )
    if a5 is None and not overflow:
        raise ValueError("policy-v3 A5 is missing")
    if a5 is not None and not isinstance(a5, PublicA5):
        raise ValueError("invalid policy-v3 A5")

    summaries = [a1.summary, a2.summary, a3.summary, a4.summary]
    if isinstance(a5, PublicA5):
        summaries.append(a5.summary)
    if any(summary != summaries[0] for summary in summaries[1:]):
        raise ValueError("policy-v3 summaries disagree")
    population_scope, source_total, rows_received, denominator = _validate_summary(
        summaries[0], coverage=coverage,
    )
    if any(
        item.population_scope != population_scope
        or item.total != source_total
        or item.returned != rows_received
        for item in coverage[:4]
    ):
        raise ValueError("policy-v3 coverage evidence disagrees")
    if coverage[1].eligible != denominator or coverage[2].eligible != denominator:
        raise ValueError("policy-v3 A1-A3 denominators disagree")
    if overflow and (
        coverage[4].total != source_total
        or coverage[4].returned != rows_received
    ):
        raise ValueError("policy-v3 A5 overflow evidence disagrees")

    case_fingerprints: dict[str, dict[str, object]] = {}
    visible_case_details: dict[str, PublicSafeCaseDetail] = {}
    def remember(
        values: tuple[PublicSafeCaseDetail, ...],
        *,
        a4_order: bool = False,
    ) -> None:
        if a4_order:
            _validate_a4_case_sequence(values)
        else:
            _validate_case_sequence(values)
        for item in values:
            _public_id_ordinal(
                item.case_public_id,
                _CASE_PUBLIC_ID,
                denominator,
            )
            dumped = item.model_dump(mode="json")
            previous = case_fingerprints.setdefault(item.case_public_id, dumped)
            if previous != dumped:
                raise ValueError("policy-v3 case detail changed across views")
            visible_case_details.setdefault(item.case_public_id, item)

    known_years = tuple(bucket.year for bucket in a1.buckets if bucket.year is not None)
    if known_years != tuple(sorted(set(known_years))) or len(known_years) > 10:
        raise ValueError("policy-v3 A1 years are not ordered")
    unknown_buckets = tuple(bucket for bucket in a1.buckets if bucket.year is None)
    if len(unknown_buckets) > 1 or (unknown_buckets and a1.buckets[-1] is not unknown_buckets[0]):
        raise ValueError("policy-v3 A1 unknown year bucket is invalid")
    if a1.displayed_start_year != (known_years[0] if known_years else None) or a1.displayed_end_year != (known_years[-1] if known_years else None):
        raise ValueError("policy-v3 A1 displayed bounds are invalid")
    if a1.all_time_case_count != denominator:
        raise ValueError("policy-v3 A1 all-time count is invalid")
    if (denominator == 0) != (not a1.buckets):
        raise ValueError("policy-v3 A1 empty population is invalid")
    role_order = ("plaintiff", "respondent", "other", "unattributed")
    displayed_total = 0
    displayed_role_counts = {role: 0 for role in role_order}
    for bucket in a1.buckets:
        counts = (
            bucket.plaintiff_count,
            bucket.respondent_count,
            bucket.other_count,
            bucket.unattributed_count,
        )
        if bucket.total_count == 0 or bucket.total_count != sum(counts):
            raise ValueError("policy-v3 A1 bucket does not conserve cases")
        displayed_total += bucket.total_count
        for role, count in zip(role_order, counts, strict=True):
            displayed_role_counts[role] += count
        if tuple(item.role for item in bucket.role_details) != role_order:
            raise ValueError("policy-v3 A1 role order is invalid")
        for role, count, detail in zip(role_order, counts, bucket.role_details, strict=True):
            _validate_scope(
                detail.scope,
                population_scope=population_scope,
                source_total=source_total,
                rows_received=rows_received,
                eligible_total=count,
                noun="дел",
            )
            if len(detail.cases) != detail.scope.shown or any(
                item.role != role or item.year != bucket.year for item in detail.cases
            ):
                raise ValueError("policy-v3 A1 details disagree")
            remember(detail.cases)
    if displayed_total > denominator:
        raise ValueError("policy-v3 A1 displayed population is too large")
    if unknown_buckets and unknown_buckets[0].total_count != summaries[0].unknown_year_count:
        raise ValueError("policy-v3 A1 unknown-year count disagrees")
    if not unknown_buckets and summaries[0].unknown_year_count:
        raise ValueError("policy-v3 A1 unknown-year bucket is missing")
    known_population = denominator - summaries[0].unknown_year_count
    if bool(known_years) != (known_population > 0):
        raise ValueError("policy-v3 A1 observed bounds are invalid")
    if known_years:
        displayed_known_population = displayed_total - (
            unknown_buckets[0].total_count if unknown_buckets else 0
        )
        if (
            summaries[0].observed_end_year != known_years[-1]
            or summaries[0].observed_start_year is None
            or (
                displayed_known_population == known_population
                and summaries[0].observed_start_year != known_years[0]
            )
            or (
                displayed_known_population < known_population
                and (
                    len(known_years) != 10
                    or summaries[0].observed_start_year >= known_years[0]
                )
            )
        ):
            raise ValueError("policy-v3 A1 observed bounds are invalid")

    for view, expected_order, category_field in (
        (a2, role_order, "role"),
        (a3, ("won", "lost", "returned", "unknown"), "outcome"),
    ):
        if view.denominator != denominator or tuple(bar.category_id for bar in view.bars) != expected_order:
            raise ValueError("policy-v3 count-bar order is invalid")
        counts = tuple(bar.count for bar in view.bars)
        if sum(counts) != denominator or tuple(bar.percent_decimal for bar in view.bars) != _expected_percentages(counts, denominator):
            raise ValueError("policy-v3 count bars do not reconcile")
        for bar in view.bars:
            _validate_scope(
                bar.scope,
                population_scope=population_scope,
                source_total=source_total,
                rows_received=rows_received,
                eligible_total=bar.count,
                noun="дел",
            )
            if len(bar.cases) != bar.scope.shown or any(
                getattr(item, category_field) != bar.category_id for item in bar.cases
            ):
                raise ValueError("policy-v3 count-bar details disagree")
            remember(bar.cases)

    a2_role_counts = {bar.category_id: bar.count for bar in a2.bars}
    undisplayed_a1_cases = denominator - displayed_total
    if any(
        not (
            displayed_role_counts[role]
            <= a2_role_counts[role]
            <= displayed_role_counts[role] + undisplayed_a1_cases
        )
        for role in role_order
    ):
        raise ValueError("policy-v3 A1 and A2 role totals disagree")
    a3_outcome_counts = {bar.category_id: bar.count for bar in a3.bars}
    nonparty_case_count = (
        a2_role_counts["other"] + a2_role_counts["unattributed"]
    )
    if a3_outcome_counts["unknown"] < nonparty_case_count:
        raise ValueError("policy-v3 role and outcome totals disagree")

    if len(a4.currency_groups) > 1:
        raise ValueError("policy-v3 A4 has more than one currency")
    if a4.missing_amount_count > denominator or a4.missing_currency_count > denominator:
        raise ValueError("policy-v3 A4 missing counters are invalid")
    a4_eligible = coverage[3].eligible
    if a4_eligible is None:
        raise ValueError("policy-v3 A4 eligible count is missing")
    if (
        a4_eligible > denominator
        or a4_eligible + a4.missing_amount_count > denominator
        or a4_eligible + a4.missing_currency_count > denominator
    ):
        raise ValueError("policy-v3 A4 counters exceed case population")
    if not a4.currency_groups:
        if a4_eligible != 0:
            raise ValueError("policy-v3 A4 group is missing")
    else:
        if a4_eligible == 0:
            raise ValueError("policy-v3 A4 group is unexpected")
        group = a4.currency_groups[0]
        if group.source_currency_id != "RUB" or group.display_currency != "₽":
            raise ValueError("policy-v3 A4 currency is invalid")
        _validate_scope(
            group.scope,
            population_scope=population_scope,
            source_total=source_total,
            rows_received=rows_received,
            eligible_total=a4_eligible,
            noun="дел",
        )
        if len(group.cases) != group.scope.shown or len(group.case_geometries) != len(group.cases):
            raise ValueError("policy-v3 A4 detail cardinality is invalid")
        remember(group.cases, a4_order=True)
        amounts = tuple(
            _policy_v3_decimal(item.amount.source_decimal)
            for item in group.cases
            if item.amount is not None
        )
        if len(amounts) != len(group.cases):
            raise ValueError("policy-v3 A4 case lacks a RUB amount")
        expected_axis = (min((Decimal("0"), *amounts)), max((Decimal("0"), *amounts)))
        if (
            _policy_v3_decimal(group.axis.axis_min_decimal),
            _policy_v3_decimal(group.axis.axis_max_decimal),
        ) != expected_axis:
            raise ValueError("policy-v3 A4 axis is invalid")
        for detail, geometry in zip(group.cases, group.case_geometries, strict=True):
            if (
                geometry.case_public_id != detail.case_public_id
                or _policy_v3_decimal(geometry.geometry.start_ratio_decimal) != 0
                or _policy_v3_decimal(geometry.geometry.end_ratio_decimal)
                != _policy_v3_decimal(detail.amount.source_decimal)  # type: ignore[union-attr]
            ):
                raise ValueError("policy-v3 A4 geometry is invalid")

    if overflow:
        if summaries[0].collection_complete:
            raise ValueError("policy-v3 opponent overflow cannot be complete")
    else:
        assert isinstance(a5, PublicA5)
        a5_eligible = coverage[4].eligible
        if a5_eligible is None:
            raise ValueError("policy-v3 A5 eligible count is missing")
        if a5_eligible > 20_000:
            raise ValueError("policy-v3 A5 eligible count exceeds registry cap")
        _validate_scope(
            a5.scope,
            population_scope=population_scope,
            source_total=source_total,
            rows_received=rows_received,
            eligible_total=a5_eligible,
            noun="сторон",
        )
        cases_with_safe_opponent = denominator - a5.cases_without_safe_opponent
        if (
            len(a5.groups) != a5.scope.shown
            or a5.cases_without_safe_opponent > denominator
            or a5.cases_without_safe_opponent < nonparty_case_count
            or a5.multi_opponent_case_count > cases_with_safe_opponent
            or (a5_eligible == 0) != (
                a5.cases_without_safe_opponent == denominator
            )
        ):
            raise ValueError("policy-v3 A5 counters are invalid")
        group_keys = tuple((-group.case_count, group.opponent_public_id) for group in a5.groups)
        if group_keys != tuple(sorted(group_keys)) or len({group.opponent_public_id for group in a5.groups}) != len(a5.groups):
            raise ValueError("policy-v3 A5 group order is invalid")
        visible_memberships: dict[str, int] = {}
        for group in a5.groups:
            ordinal = _public_id_ordinal(
                group.opponent_public_id,
                _OPPONENT_PUBLIC_ID,
                a5_eligible,
            )
            if (
                group.display_kind != "masked_unknown"
                or group.display_name != f"Сторона скрыта {ordinal}"
                or group.case_count == 0
                or group.case_count > cases_with_safe_opponent
                or any(
                    item.role not in {"plaintiff", "respondent"}
                    for item in group.cases
                )
            ):
                raise ValueError("policy-v3 opponent is not fully masked")
            _validate_scope(
                group.case_scope,
                population_scope=population_scope,
                source_total=source_total,
                rows_received=rows_received,
                eligible_total=group.case_count,
                noun="дел",
            )
            if len(group.cases) != group.case_scope.shown:
                raise ValueError("policy-v3 A5 case scope disagrees")
            remember(group.cases)
            for item in group.cases:
                visible_memberships[item.case_public_id] = (
                    visible_memberships.get(item.case_public_id, 0) + 1
                )
        visible_safe_cases = len(visible_memberships)
        visible_multi_cases = sum(
            count >= 2 for count in visible_memberships.values()
        )
        total_memberships = sum(group.case_count for group in a5.groups)
        if (
            a5.cases_without_safe_opponent
            > denominator - visible_safe_cases
            or a5.multi_opponent_case_count < visible_multi_cases
            or total_memberships
            > cases_with_safe_opponent
            + a5.multi_opponent_case_count * (len(a5.groups) - 1)
            or (
                a5_eligible <= 20
                and total_memberships
                < cases_with_safe_opponent + a5.multi_opponent_case_count
            )
        ):
            raise ValueError("policy-v3 A5 counters are invalid")
        all_memberships_visible = (
            a5_eligible <= 20
            and all(group.case_count <= 20 for group in a5.groups)
        )
        if all_memberships_visible and (
            a5.cases_without_safe_opponent
            != denominator - visible_safe_cases
            or a5.multi_opponent_case_count != visible_multi_cases
        ):
            raise ValueError("policy-v3 A5 visible memberships disagree")

    visible_case_ids = set(case_fingerprints)
    visible_amount_case_ids = {
        case_id
        for case_id, detail in case_fingerprints.items()
        if detail["amount"] is not None
    }
    if (
        a4_eligible < len(visible_amount_case_ids)
        or denominator - a4_eligible
        < len(visible_case_ids - visible_amount_case_ids)
        or (
            len(visible_case_ids) == denominator
            and a4_eligible != len(visible_amount_case_ids)
        )
    ):
        raise ValueError("policy-v3 A4 visible population disagrees")

    for bucket in a1.buckets:
        counts = (
            bucket.plaintiff_count,
            bucket.respondent_count,
            bucket.other_count,
            bucket.unattributed_count,
        )
        for role, count, detail in zip(
            role_order, counts, bucket.role_details, strict=True,
        ):
            matching = tuple(sorted(
                (
                    case
                    for case in visible_case_details.values()
                    if case.year == bucket.year and case.role == role
                ),
                key=_detail_order_key,
            ))
            expected = tuple(
                item.case_public_id for item in matching[:min(count, 20)]
            )
            actual = tuple(item.case_public_id for item in detail.cases)
            if len(matching) > count or actual != expected:
                raise ValueError("policy-v3 A1 visible membership disagrees")
    for view, category_field in ((a2, "role"), (a3, "outcome")):
        for bar in view.bars:
            matching = tuple(sorted(
                (
                    case
                    for case in visible_case_details.values()
                    if getattr(case, category_field) == bar.category_id
                ),
                key=_detail_order_key,
            ))
            expected = tuple(
                item.case_public_id for item in matching[:min(bar.count, 20)]
            )
            actual = tuple(item.case_public_id for item in bar.cases)
            if len(matching) > bar.count or actual != expected:
                raise ValueError("policy-v3 count-bar visible membership disagrees")
    visible_amount_details = tuple(sorted(
        (
            case
            for case in visible_case_details.values()
            if case.amount is not None
        ),
        key=_a4_detail_order_key,
    ))
    expected_a4 = tuple(
        item.case_public_id
        for item in visible_amount_details[:min(a4_eligible, 20)]
    )
    actual_a4 = (
        tuple(
            item.case_public_id
            for item in a4.currency_groups[0].cases
        )
        if a4.currency_groups
        else ()
    )
    if actual_a4 != expected_a4:
        raise ValueError("policy-v3 A4 visible membership disagrees")

    emitted_codes = {
        item.code for item in _arbitration_limitations(response)
    }
    if len(visible_case_ids) == denominator:
        if (
            "arbitration_date_invalid" in emitted_codes
            and all(
                item.start_date is not None and item.update_date is not None
                for item in visible_case_details.values()
            )
        ):
            raise ValueError(
                "policy-v3 invalid-date limitation lacks a visible candidate"
            )
        if (
            "arbitration_year_conflict" in emitted_codes
            and not any(
                item.year is None and item.start_date is not None
                for item in visible_case_details.values()
            )
        ):
            raise ValueError(
                "policy-v3 year-conflict limitation lacks a visible candidate"
            )
        if (
            "arbitration_date_inversion" in emitted_codes
            and not any(
                item.start_date is not None
                and item.update_date is not None
                and item.start_date > item.update_date
                for item in visible_case_details.values()
            )
        ):
            raise ValueError(
                "policy-v3 date-inversion limitation lacks a visible candidate"
            )
    first_number_codes = emitted_codes & {
        "arbitration_first_number_unavailable",
        "arbitration_first_number_identity_collision",
    }
    visible_hidden_number_count = sum(
        item.case_number is None for item in visible_case_details.values()
    )
    undisplayed_case_count = denominator - len(visible_case_ids)
    if (
        visible_hidden_number_count + undisplayed_case_count
        < len(first_number_codes)
    ):
        raise ValueError(
            "policy-v3 first-number limitation population is impossible"
        )
    for detail in case_fingerprints.values():
        year = detail["year"]
        if year is None:
            if summaries[0].unknown_year_count == 0:
                raise ValueError("policy-v3 visible unknown year disagrees")
        elif (
            summaries[0].observed_start_year is None
            or summaries[0].observed_end_year is None
            or year < summaries[0].observed_start_year
            or year > summaries[0].observed_end_year
        ):
            raise ValueError("policy-v3 visible year is outside observed bounds")
        elif year not in known_years and (
            len(known_years) != 10 or year > known_years[0]
        ):
            raise ValueError("policy-v3 visible year contradicts A1 top years")
        start = _policy_v3_date(detail["start_date"])  # type: ignore[arg-type]
        update = _policy_v3_date(detail["update_date"])  # type: ignore[arg-type]
        if (
            start is not None
            and update is not None
            and start > update
            and "arbitration_date_inversion" not in emitted_codes
        ):
            raise ValueError("policy-v3 visible date inversion is unexplained")
        if (
            detail["case_number"] is None
            and not emitted_codes & {
                "arbitration_first_number_unavailable",
                "arbitration_first_number_identity_collision",
            }
        ):
            raise ValueError("policy-v3 hidden case number is unexplained")

    expected_states: tuple[str, ...]
    if summaries[0].collection_complete:
        expected_states = (
            ("available_empty",) * 5
            if denominator == 0
            else (
                "available",
                "available",
                "available",
                "available" if a4_eligible == denominator else "partial",
                "available" if isinstance(a5, PublicA5) and coverage[4].eligible else "available_empty",
            )
        )
    else:
        expected_states = ("partial", "partial", "partial", "partial", "failed" if overflow else "partial")
    if tuple(item.state for item in coverage) != expected_states:
        raise ValueError("policy-v3 coverage states are invalid")


def _validate_cap_fallback(response: "CompanyPublicH2Response") -> None:
    coverage = _arbitration_coverage(response)
    if any(_arbitration_values(response)):
        raise ValueError("policy-v3 projection-cap fallback retained a block")
    if any(
        item.state != "failed"
        or item.limitation_codes != (_ARBITRATION_CAP_CODE,)
        for item in coverage
    ):
        raise ValueError("invalid policy-v3 projection-cap fallback")
    limitations = _arbitration_limitations(response)
    if (
        len(limitations) != 1
        or limitations[0].code != _ARBITRATION_CAP_CODE
        or limitations[0].block_id is not None
        or limitations[0].field_id is not None
    ):
        raise ValueError("invalid policy-v3 projection-cap limitation")
    first = coverage[0]
    if (
        first.population_scope not in {"complete_collection", "returned_slice"}
        or first.total is None
        or first.returned is None
        or first.returned > _MAX_ARBITRATION_ROWS
        or first.total > _MAX_SOURCE_TOTAL
        or first.total < first.returned
        or (
            first.total <= _MAX_ARBITRATION_ROWS
            and first.returned != first.total
        )
        or (
            first.total > _MAX_ARBITRATION_ROWS
            and first.returned == 0
        )
        or (
            first.population_scope == "complete_collection"
            and first.total != first.returned
        )
    ):
        raise ValueError("invalid policy-v3 projection-cap evidence")
    if any(
        item.population_scope != first.population_scope
        or item.total != first.total
        or item.returned != first.returned
        for item in coverage[1:]
    ):
        raise ValueError("projection-cap fallback changed common evidence")
    if (
        first.eligible is None
        or first.eligible > _MAX_ARBITRATION_ROWS
        or first.eligible > first.returned
        or coverage[1].eligible != first.eligible
        or coverage[2].eligible != first.eligible
    ):
        raise ValueError("projection-cap fallback lost A1-A3 counts")
    if (
        coverage[3].eligible is None
        or coverage[3].eligible > _MAX_ARBITRATION_ROWS
        or coverage[3].eligible > first.eligible
    ):
        raise ValueError("projection-cap fallback has invalid A4 count")
    if coverage[4].eligible is None:
        if coverage[4].population_scope != "returned_slice":
            raise ValueError("projection-cap fallback has invalid A5 count")
    elif (
        coverage[4].eligible > 20_000
        or (coverage[4].eligible > 0 and first.eligible == 0)
    ):
        raise ValueError("projection-cap fallback has invalid A5 count")


def _validate_source_less_v3(response: "CompanyPublicH2Response") -> None:
    _validate_arbitration_limitation_catalog(response)
    if len(response.sources) != 2 or not _valid_frozen_source_prefix(response):
        raise ValueError("invalid source-less policy-v3 source prefix")
    if any(_arbitration_values(response)):
        raise ValueError("source-less policy-v3 response owns arbitration facts")
    coverage = _arbitration_coverage(response)
    reasons = {code for item in coverage for code in item.limitation_codes}
    if len(reasons) != 1:
        raise ValueError("source-less policy-v3 reasons disagree")
    reason = next(iter(reasons))
    expected_state = _ARBITRATION_PRE_RESULT_REASONS.get(reason)
    if expected_state is None or any(
        item.state != expected_state
        or item.population_scope != "not_applicable"
        or item.total is not None
        or item.returned is not None
        or item.eligible is not None
        or item.limitation_codes != (reason,)
        for item in coverage
    ):
        raise ValueError("invalid source-less policy-v3 coverage")
    limitations = _arbitration_limitations(response)
    if (
        len(limitations) != 1
        or limitations[0].code != reason
        or limitations[0].block_id is not None
        or limitations[0].field_id is not None
    ):
        raise ValueError("invalid source-less policy-v3 limitation")


def _validate_bound_v3(response: "CompanyPublicH2Response") -> None:
    _validate_arbitration_limitation_catalog(response)
    if len(response.sources) != 3 or not _valid_frozen_source_prefix(response):
        raise ValueError("invalid bound policy-v3 source prefix")
    source = response.sources[2]
    if not _is_exact_bound_arbitration_source(source):
        raise ValueError("invalid bound policy-v3 source")
    coverage = _arbitration_coverage(response)
    if all(value is None for value in _arbitration_values(response)):
        if all(item.limitation_codes == (_ARBITRATION_CAP_CODE,) for item in coverage):
            _validate_cap_fallback(response)
            return
        reasons = {code for item in coverage for code in item.limitation_codes}
        if len(reasons) != 1 or next(iter(reasons)) not in _ARBITRATION_BOUND_FAILURE_REASONS:
            raise ValueError("invalid bound policy-v3 failure reason")
        reason = next(iter(reasons))
        if any(
            item.state != "failed"
            or item.population_scope != "not_applicable"
            or item.total is not None
            or item.returned is not None
            or item.eligible is not None
            or item.limitation_codes != (reason,)
            for item in coverage
        ):
            raise ValueError("invalid bound policy-v3 failed coverage")
        limitations = _arbitration_limitations(response)
        if (
            len(limitations) != 1
            or limitations[0].code != reason
            or limitations[0].block_id is not None
            or limitations[0].field_id is not None
        ):
            raise ValueError("invalid bound policy-v3 failed limitation")
        return
    _validate_policy_v3_views(response)
    referenced = {
        code for item in coverage for code in item.limitation_codes
        if code in _ARBITRATION_LIMITATION_CODES
    }
    emitted = {item.code for item in _arbitration_limitations(response)}
    if emitted != referenced or _ARBITRATION_CAP_CODE in emitted:
        raise ValueError("policy-v3 arbitration limitations are not exact")
    a1 = response.blocks.arbitration_a1
    a4 = response.blocks.arbitration_a4
    assert isinstance(a1, PublicA1) and isinstance(a4, PublicA4)
    summary = a1.summary
    a4_eligible = coverage[3].eligible
    assert a4_eligible is not None

    arbitration_items = _arbitration_limitations(response)
    expected_root_order = tuple(sorted(
        emitted,
        key=lambda code: (
            0 if code in _ARBITRATION_A1_LIMITATIONS else
            1 if code in _ARBITRATION_A4_LIMITATIONS else
            2,
            code,
        ),
    ))
    if tuple(item.code for item in arbitration_items) != expected_root_order:
        raise ValueError("policy-v3 arbitration limitation order is invalid")

    def limitation_blocks(code: str) -> tuple[str, ...]:
        if code in _ARBITRATION_A1_LIMITATIONS:
            return ("arbitration_a1",)
        if code in _ARBITRATION_A4_LIMITATIONS:
            return ("arbitration_a4",)
        return _ARBITRATION_BLOCKS

    overflow = response.blocks.arbitration_a5 is None
    for coverage_item in coverage:
        expected_codes = tuple(
            code
            for code in _ARBITRATION_LIMITATION_PRECEDENCE
            if code in emitted and coverage_item.block_id in limitation_blocks(code)
        )
        if overflow and coverage_item.block_id == "arbitration_a5":
            expected_codes = ("opponent_group_cap_exhausted",)
        if coverage_item.limitation_codes != expected_codes:
            raise ValueError("policy-v3 arbitration coverage linkage is invalid")

    def require_exact(code: str, condition: bool) -> None:
        if (code in emitted) != condition:
            raise ValueError("policy-v3 inferred limitation semantics disagree")

    require_exact("arbitration_calendar_unverified", True)
    require_exact(
        "arbitration_unknown_year",
        summary.unknown_year_count > 0,
    )
    require_exact(
        "arbitration_amount_missing",
        a4.missing_amount_count > 0,
    )
    require_exact(
        "arbitration_currency_missing",
        a4.missing_currency_count > 0,
    )
    if bool(emitted & _ARBITRATION_A4_LIMITATIONS) != (
        a4_eligible < summary.unique_case_count
    ):
        raise ValueError("policy-v3 inferred limitation semantics disagree")
    if (
        a4_eligible
        + a4.missing_amount_count
        + int("arbitration_amount_invalid" in emitted)
        > summary.unique_case_count
        or a4_eligible
        + a4.missing_currency_count
        + int("arbitration_currency_unidentified" in emitted)
        + int("arbitration_currency_invalid" in emitted)
        > summary.unique_case_count
    ):
        raise ValueError("policy-v3 A4 limitation population is invalid")
    require_exact("malformed_rows", summary.malformed_count > 0)
    require_exact(
        "duplicate_conflict",
        summary.duplicate_conflict_count > 0,
    )
    require_exact(
        "source_total_exceeds_cap",
        summary.source_total is not None
        and summary.source_total > _MAX_ARBITRATION_ROWS,
    )
    require_exact(
        "opponent_group_cap_exhausted",
        response.blocks.arbitration_a5 is None,
    )
    if {"oversized_case", "storage_cap_exhausted"} <= emitted:
        raise ValueError("policy-v3 storage boundary limitations conflict")
    boundary_row_count = int(bool(
        emitted & {"oversized_case", "storage_cap_exhausted"}
    ))
    classified_row_minimum = (
        summary.malformed_count
        + summary.unique_case_count
        + summary.duplicate_identical_count
        + 2 * summary.duplicate_conflict_count
        + boundary_row_count
    )
    if (
        classified_row_minimum > summary.rows_observed
        or (
            summary.duplicate_conflict_count == 0
            and boundary_row_count == 0
            and classified_row_minimum != summary.rows_observed
        )
    ):
        raise ValueError("policy-v3 public row classification is invalid")
    if summary.completion_reason in {
        *_ARBITRATION_PRE_RESULT_REASONS,
        *_ARBITRATION_BOUND_FAILURE_REASONS,
    }:
        raise ValueError("invalid admitted policy-v3 completion reason")
    collection_codes = _ARBITRATION_COMPLETION_REASONS - {"complete"}
    if summary.collection_complete:
        if emitted & collection_codes:
            raise ValueError("policy-v3 inferred limitation semantics disagree")
    else:
        ordered_emitted = tuple(
            code
            for code in _ARBITRATION_COMPLETION_PRECEDENCE[:-1]
            if code in emitted
        )
        if (
            not ordered_emitted
            or summary.completion_reason != ordered_emitted[0]
        ):
            raise ValueError("policy-v3 completion precedence disagrees")
    for item in arbitration_items:
        expected_block = (
            "arbitration_a1"
            if item.code in _ARBITRATION_A1_LIMITATIONS
            else "arbitration_a4"
            if item.code in _ARBITRATION_A4_LIMITATIONS
            else None
        )
        if item.block_id != expected_block or item.field_id is not None:
            raise ValueError("policy-v3 arbitration limitation linkage is invalid")


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
    def _valid(self, info: ValidationInfo) -> "CompanyPublicH2Response":
        if not _DIGEST.fullmatch(self.projection_digest) or not _DIGEST.fullmatch(self.chart_facts_hash) or not _UUID.fullmatch(self.report_id) or not _PATH.fullmatch(self.canonical_path) or not _UTC.fullmatch(self.checked_at) or not _DATE.fullmatch(self.checked_date):
            raise ValueError("invalid public root")
        if not re.fullmatch(rf"/company/{re.escape(self.identity.inn)}-[a-z0-9]+(?:-[a-z0-9]+)*", self.canonical_path):
            raise ValueError("canonical path does not bind identity INN")
        if self.block_order != BLOCK_ORDER or tuple(item.block_id for item in self.coverage) != COVERAGE_BLOCKS:
            raise ValueError("invalid block or coverage order")
        if len(self.sources) not in {1, 2, 3} or tuple(item.dataset for item in self.sources) != ("counterparty", "finance", "arbitration")[:len(self.sources)]:
            raise ValueError("invalid source order")
        if (self.report_version == "3") != (self.snapshot_capability == "card_v2") or (self.report_version in {"1", "2"} and self.indexable) or (self.indexable and self.projection_scope != "active_publication"):
            raise ValueError("invalid version/indexability")
        if (
            tuple(item.action_id for item in self.actions) != ("check_another_company", "prepare_claim")
            or self.actions[0].label != "Проверить другую компанию"
            or self.actions[0].path != "/"
            or self.actions[1].label != "Подготовить претензию"
            or self.breadcrumbs[0].label != "Главная"
            or self.breadcrumbs[0].path != "/"
            or self.breadcrumbs[0].current
            or not self.breadcrumbs[1].current
            or self.breadcrumbs[1].label != self.identity.display_name
            or self.breadcrumbs[1].path != self.canonical_path
        ):
            raise ValueError("invalid navigation")
        expected_claim = f"/claims?report_id={self.report_id}"
        if self.actions[1].path != expected_claim or self.primary_claim_cta.path != expected_claim:
            raise ValueError("invalid Claims cross-binding")
        known = {item.code for item in self.limitations}
        if len(known) != len(self.limitations) or any(code not in known for item in self.coverage for code in item.limitation_codes):
            raise ValueError("invalid coverage limitation link")
        pairs = (("finance_f1", self.blocks.finance_f1), ("finance_f2", self.blocks.finance_f2), ("finance_f3", self.blocks.finance_f3), ("finance_f4", self.blocks.finance_f4), ("finance_f5", self.blocks.finance_f5), ("arbitration_a1", self.blocks.arbitration_a1), ("arbitration_a2", self.blocks.arbitration_a2), ("arbitration_a3", self.blocks.arbitration_a3), ("arbitration_a4", self.blocks.arbitration_a4), ("arbitration_a5", self.blocks.arbitration_a5))
        for block, value in pairs:
            state = next(item.state for item in self.coverage if item.block_id == block)
            if (state in {"available", "available_empty", "partial"}) != (value is not None):
                raise ValueError("coverage and block disagree")
        arbitration_sources = tuple(
            item for item in self.sources if item.dataset == "arbitration"
        )
        exact_bound = (
            len(arbitration_sources) == 1
            and _is_exact_bound_arbitration_source(arbitration_sources[0])
        )
        no_arbitration_source = not arbitration_sources
        if exact_bound:
            if self.report_version != "3" or self.snapshot_capability != "card_v2":
                raise ValueError("invalid policy-v3 branch discriminator")
            _validate_bound_v3(self)
        elif (
            self.report_version == "3"
            and self.snapshot_capability == "card_v2"
            and no_arbitration_source
            and all(value is None for value in _arbitration_values(self))
        ):
            _validate_source_less_v3(self)
        elif _v3_semantic_signal(self):
            raise ValueError("invalid policy-v3 branch discriminator")
        skip_size_cap = bool(
            info.context and info.context.get("skip_public_h2_size_cap") is True
        )
        if not skip_size_cap and len(canonical_json_bytes(self.model_dump(mode="json"))) > 524288:
            raise ValueError("public_projection_too_large")
        return self


def parse_public_h2_json(raw: str | bytes) -> CompanyPublicH2Response:
    """Parse one public H2 wire document without JSON or Pydantic coercion.

    The browser boundary retains JSON integer tokens, while Python naturally
    represents integer JSON tokens as ``int``. Floats are not part of the
    public profile: decimal leaves are strings. Duplicate keys are rejected
    before Pydantic sees a mapping, and the model dump equality check makes
    every declared field explicit even where an in-process constructor has a
    convenience default.
    """
    if isinstance(raw, bytes):
        if len(raw) > 786_432:
            raise ValueError("public H2 state exceeds byte limit")
        try:
            text = raw.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise ValueError("public H2 state must be UTF-8") from exc
    elif isinstance(raw, str):
        if len(raw.encode("utf-8")) > 786_432:
            raise ValueError("public H2 state exceeds byte limit")
        text = raw
    else:
        raise TypeError("public H2 state must be str or bytes")

    def reject_float(value: str) -> object:
        raise ValueError(f"public H2 JSON float is forbidden: {value}")

    def strict_integer(value: str) -> int:
        if re.fullmatch(r"(?:0|-?[1-9][0-9]*)", value) is None:
            raise ValueError(f"public H2 JSON integer is invalid: {value}")
        return int(value)

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate public H2 JSON key: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(
            text,
            object_pairs_hook=pairs,
            parse_int=strict_integer,
            parse_float=reject_float,
            parse_constant=reject_float,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid public H2 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("public H2 root must be an object")
    dto = CompanyPublicH2Response.model_validate(value)

    def exact(left: object, right: object) -> bool:
        if type(left) is not type(right):
            return False
        if isinstance(left, dict):
            return set(left) == set(right) and all(exact(item, right[key]) for key, item in left.items())
        if isinstance(left, list):
            return len(left) == len(right) and all(exact(a, b) for a, b in zip(left, right))
        return left == right

    if not exact(dto.model_dump(mode="json"), value):
        raise ValueError("public H2 JSON must explicitly match the closed DTO")
    expected = canonical_digest({key: item for key, item in value.items() if key != "projection_digest"})
    if value.get("projection_digest") != expected:
        raise ValueError("projection digest")
    return dto


__all__ = [name for name in globals() if name.startswith("Public") or name in {"BLOCK_ORDER", "COVERAGE_BLOCKS", "CanonicalDecimal", "CompanyPublicH2Response", "parse_public_h2_json"}]
