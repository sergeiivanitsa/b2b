"""Strict, deterministic ``company_public_h1_v1`` projection.

The module is deliberately pure: it accepts one immutable domain report and
returns an allowlisted DTO.  It performs no persistence, provider, scoring,
signal or explanation work.
"""
from __future__ import annotations

import html
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, TypeAlias
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .aggregate import CompanyReport, DatasetReportStatus
from .models import (
    ArbitrationCaseFacts,
    ArbitrationParty,
    ArbitrationResultType,
    ArbitrationStatus,
    CounterpartyBlockStatus,
    FinanceForm,
)
from .seo import canonical_path

_INN = re.compile(r"^(?:[0-9]{10}|[0-9]{12})$")
_KPP = re.compile(r"^[0-9]{9}$")
_OGRN = re.compile(r"^(?:[0-9]{13}|[0-9]{15})$")
_CURRENCY = re.compile(r"^[A-Z][A-Z0-9_-]{2,15}$")
_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_CANONICAL = re.compile(r"^/company/(?P<inn>[0-9]{10}(?:[0-9]{2})?)-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)$")
_MSK = ZoneInfo("Europe/Moscow")
_MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря")
_BANKRUPTCY_MESSAGES = {
    "debtor_intention": "Опубликовано намерение должника обратиться в суд с заявлением о банкротстве.",
    "creditor_intention": "Опубликовано намерение кредитора обратиться в суд с заявлением о банкротстве компании.",
    "unknown": "Тип публикации не классифицирован",
}
_BANKRUPTCY_DISCLAIMER = (
    "Наличие публикации не подтверждает, что заявление принято судом, возбуждено "
    "дело, компания признана банкротом или процедура продолжается сейчас."
)
_TAX_MESSAGES = {
    False: "Признак неоплаченной налоговой задолженности не установлен.",
    True: "Источник передал признак неоплаченной налоговой задолженности.",
}

PublicFinanceMetricId: TypeAlias = Literal[
    "total_assets", "non_current_assets", "current_assets", "inventories",
    "accounts_receivable", "cash_and_equivalents", "equity",
    "long_term_liabilities", "short_term_liabilities",
    "short_term_borrowings", "accounts_payable", "revenue", "cost_of_sales",
    "gross_profit", "operating_profit", "profit_before_tax", "net_profit",
    "net_cash_flow", "cash_at_start", "cash_at_end",
]
PublicBlockId: TypeAlias = Literal[
    "breadcrumbs", "identity_status", "known_summary", "in_page_navigation",
    "coverage_checked_at", "requisites", "finance", "arbitration",
    "bankruptcy", "tax", "management", "sources_limitations",
    "neutral_actions", "internal_links",
]
FactualBlockId: TypeAlias = Literal["requisites", "finance", "arbitration", "bankruptcy", "tax", "management"]
DatasetId: TypeAlias = Literal["counterparty", "finance", "arbitration", "bankruptcy", "tax_info"]
NormalizationVersion: TypeAlias = Literal[
    "counterparty_normalizer_v1", "finance_normalizer_v1",
    "arbitration_normalizer_v1", "arbitration_normalizer_v2",
]

_METRICS: tuple[PublicFinanceMetricId, ...] = (
    "total_assets", "non_current_assets", "current_assets", "inventories",
    "accounts_receivable", "cash_and_equivalents", "equity",
    "long_term_liabilities", "short_term_liabilities", "short_term_borrowings",
    "accounts_payable", "revenue", "cost_of_sales", "gross_profit",
    "operating_profit", "profit_before_tax", "net_profit", "net_cash_flow",
    "cash_at_start", "cash_at_end",
)
_SERIES: dict[tuple[FinanceForm, str], PublicFinanceMetricId] = {
    (FinanceForm.BALANCE, "1600"): "total_assets", (FinanceForm.BALANCE, "1100"): "non_current_assets",
    (FinanceForm.BALANCE, "1200"): "current_assets", (FinanceForm.BALANCE, "1210"): "inventories",
    (FinanceForm.BALANCE, "1230"): "accounts_receivable", (FinanceForm.BALANCE, "1250"): "cash_and_equivalents",
    (FinanceForm.BALANCE, "1300"): "equity", (FinanceForm.BALANCE, "1400"): "long_term_liabilities",
    (FinanceForm.BALANCE, "1500"): "short_term_liabilities", (FinanceForm.BALANCE, "1510"): "short_term_borrowings",
    (FinanceForm.BALANCE, "1520"): "accounts_payable", (FinanceForm.FINANCIAL_RESULTS, "2110"): "revenue",
    (FinanceForm.FINANCIAL_RESULTS, "2120"): "cost_of_sales", (FinanceForm.FINANCIAL_RESULTS, "2100"): "gross_profit",
    (FinanceForm.FINANCIAL_RESULTS, "2200"): "operating_profit", (FinanceForm.FINANCIAL_RESULTS, "2300"): "profit_before_tax",
    (FinanceForm.FINANCIAL_RESULTS, "2400"): "net_profit", (FinanceForm.CASH_FLOW, "4400"): "net_cash_flow",
    (FinanceForm.CASH_FLOW, "4450"): "cash_at_start", (FinanceForm.CASH_FLOW, "4500"): "cash_at_end",
}


def _safe_text(value: str, *, field: str) -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", value).split())
    if not normalized or any(unicodedata.category(char) == "Cc" for char in normalized):
        raise ValueError(f"unsafe {field}")
    return normalized


def _same_origin_absolute_path(value: str, *, field: str) -> str:
    normalized = _safe_text(value, field=field)
    if (
        not normalized.startswith("/")
        or normalized.startswith("//")
        or "\\" in normalized
        or any(char.isspace() for char in normalized)
    ):
        raise ValueError(f"{field} must be a same-origin absolute path")
    return normalized


def _display_legal_name(value: str) -> str:
    """Apply only the iteration-16-approved deterministic name typography."""
    normalized = _safe_text(value, field="legal name")
    if normalized.count('"') == 2:
        left, quoted, right = normalized.split('"')
        if quoted:
            normalized = f"{left}«{quoted}»{right}"
    return normalized


def _canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("decimal must be finite")
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in {"-0", ""} else rendered


def _validate_decimal(value: str | None) -> str | None:
    if value is not None:
        if not _DECIMAL.fullmatch(value) or _canonical_decimal(Decimal(value)) != value:
            raise ValueError("invalid canonical Decimal string")
    return value


class PublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicMoney(PublicModel):
    source_decimal: str
    source_unit: Literal["thousand_rub"]
    rub_decimal: str
    display_value: str
    unit_policy_version: str = Field(min_length=1)
    _source_decimal = field_validator("source_decimal")(_validate_decimal)
    _rub_decimal = field_validator("rub_decimal")(_validate_decimal)

    @field_validator("display_value", "unit_policy_version")
    @classmethod
    def _safe_strings(cls, value: str) -> str:
        return _safe_text(value, field="money string")


class PublicPercentChange(PublicModel):
    exact_percent: str
    display_value: str
    current_year: int
    previous_year: int
    formula_version: Literal["finance_yoy_v1"]
    _exact = field_validator("exact_percent")(_validate_decimal)

    @model_validator(mode="after")
    def _adjacent(self) -> "PublicPercentChange":
        if self.previous_year != self.current_year - 1:
            raise ValueError("YoY periods must be adjacent")
        expected = Decimal(self.exact_percent).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        display = f"{expected:+.1f}".replace(".", ",") + "%"
        if self.display_value != display:
            raise ValueError("invalid percent display")
        return self


class CompanyPublicIdentity(PublicModel):
    legal_full_name: str = Field(min_length=1)
    legal_short_name: str | None = None
    display_name: str = Field(min_length=1)
    inn: str
    status_code: str | None = None
    status_label: str | None = None
    status_effective_at: date | None = None

    @field_validator("inn")
    @classmethod
    def _valid_inn(cls, value: str) -> str:
        if not _INN.fullmatch(value):
            raise ValueError("invalid INN")
        return value

    @field_validator("legal_full_name", "display_name")
    @classmethod
    def _safe_required_name(cls, value: str) -> str:
        return _safe_text(value, field="public name")

    @field_validator("legal_short_name")
    @classmethod
    def _safe_optional_name(cls, value: str | None) -> str | None:
        return _safe_text(value, field="public short name") if value is not None else None

    @field_validator("status_code", "status_label")
    @classmethod
    def _safe_optional_status(cls, value: str | None) -> str | None:
        return _safe_text(value, field="public status") if value is not None else None


class PublicRegion(PublicModel):
    code: str | None = None
    name: str | None = None

    @field_validator("code", "name")
    @classmethod
    def _safe_region(cls, value: str | None) -> str | None:
        return _safe_text(value, field="region") if value is not None else None


class PublicAddress(PublicModel):
    display_line: str = Field(min_length=1)
    postal_code: str | None = None
    country: str | None = None
    region: str | None = None
    city: str | None = None
    street: str | None = None
    house: str | None = None
    office: str | None = None
    is_inaccuracy: bool | None = None

    @field_validator("display_line", "postal_code", "country", "region", "city", "street", "house", "office")
    @classmethod
    def _safe_component(cls, value: str | None) -> str | None:
        return _safe_text(value, field="address component") if value is not None else None


class RequisitesBlock(PublicModel):
    legal_form: str | None = None
    ogrn_or_ogrnip: str | None = None
    kpp: str | None = None
    registration_date: date | None = None
    dissolved_date: date | None = None
    region: PublicRegion | None = None
    legal_address: PublicAddress | None = None

    @field_validator("kpp")
    @classmethod
    def _valid_kpp(cls, value: str | None) -> str | None:
        if value is not None and not _KPP.fullmatch(value):
            raise ValueError("invalid KPP")
        return value

    @field_validator("ogrn_or_ogrnip")
    @classmethod
    def _valid_ogrn(cls, value: str | None) -> str | None:
        if value is not None and not _OGRN.fullmatch(value):
            raise ValueError("invalid OGRN")
        return value

    @field_validator("legal_form")
    @classmethod
    def _safe_optional_legal_form(cls, value: str | None) -> str | None:
        return _safe_text(value, field="legal form") if value is not None else None


class FinanceMetric(PublicModel):
    metric_id: PublicFinanceMetricId
    year: int
    money: PublicMoney | None = None
    yoy: PublicPercentChange | None = None


class FinanceBlock(PublicModel):
    unit_policy_version: str | None = None
    metrics: list[FinanceMetric] = Field(min_length=1)

    @model_validator(mode="after")
    def _has_public_fact(self) -> "FinanceBlock":
        if not any(metric.money is not None or metric.yoy is not None for metric in self.metrics):
            raise ValueError("finance block must contain a public fact")
        return self


class ArbitrationRoleCounts(PublicModel):
    plaintiff: int = Field(ge=0); respondent: int = Field(ge=0); applicant: int = Field(ge=0)
    creditor: int = Field(ge=0); debtor: int = Field(ge=0); other: int = Field(ge=0)


class ArbitrationStatusCounts(PublicModel):
    open: int = Field(ge=0); completed: int = Field(ge=0); unknown: int = Field(ge=0)


class ArbitrationResultCounts(PublicModel):
    satisfied_full: int = Field(ge=0); refused: int = Field(ge=0); returned: int = Field(ge=0)
    undefined: int = Field(ge=0); other: int = Field(ge=0)


class ArbitrationClaimAmount(PublicModel):
    role: Literal["plaintiff", "respondent"]
    currency: str
    exact_decimal: str
    display_value: str
    _exact = field_validator("exact_decimal")(_validate_decimal)

    @model_validator(mode="after")
    def _shape(self) -> "ArbitrationClaimAmount":
        if not _CURRENCY.fullmatch(self.currency):
            raise ValueError("invalid currency")
        expected = f"{self.exact_decimal.replace('.', ',')} {self.currency}"
        if self.display_value != expected:
            raise ValueError("invalid amount display")
        return self


class PublicArbitrationCase(PublicModel):
    case_number: str = Field(min_length=1)
    date_start: date | None = None
    date_update: date | None = None
    attributed_role: Literal["plaintiff", "respondent", "applicant", "creditor", "debtor", "other", "unattributed"]
    claim_amount: ArbitrationClaimAmount | None = None

    @model_validator(mode="after")
    def _amount_matches_role(self) -> "PublicArbitrationCase":
        if self.claim_amount is None:
            return self
        if self.attributed_role not in {"plaintiff", "respondent"}:
            raise ValueError("claim amount is unavailable for the attributed role")
        if self.claim_amount.role != self.attributed_role:
            raise ValueError("claim amount role does not match the attributed role")
        return self


class ArbitrationBlock(PublicModel):
    total_cases: int = Field(ge=0); returned_cases: int = Field(ge=0)
    normalized_case_count: int = Field(ge=0); malformed_count: int = Field(ge=0)
    limit: int = Field(ge=1); offset: int = Field(ge=0)
    role_counts: ArbitrationRoleCounts
    unattributed_count: int = Field(ge=0)
    status_counts: ArbitrationStatusCounts
    result_counts: ArbitrationResultCounts
    claim_amounts: list[ArbitrationClaimAmount] = Field(default_factory=list)
    selected_cases: list[PublicArbitrationCase] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def _counts(self) -> "ArbitrationBlock":
        role_total = sum(self.role_counts.model_dump().values())
        if role_total + self.unattributed_count != self.normalized_case_count:
            raise ValueError("arbitration role invariant failed")
        if self.normalized_case_count + self.malformed_count != self.returned_cases:
            raise ValueError("arbitration returned invariant failed")
        if sum(self.status_counts.model_dump().values()) != self.normalized_case_count:
            raise ValueError("arbitration status invariant failed")
        if sum(self.result_counts.model_dump().values()) != self.normalized_case_count:
            raise ValueError("arbitration result invariant failed")
        return self


class BankruptcyTypedCounts(PublicModel):
    debtor_intention: int = Field(ge=0); creditor_intention: int = Field(ge=0); unknown: int = Field(ge=0)


class PublicBankruptcyPublication(PublicModel):
    safe_reference: str | None = None
    publication_date: date | None = None
    kind: Literal["debtor_intention", "creditor_intention", "unknown"]
    message: str
    participant_role: Literal["debtor", "creditor", "other", "unknown"]

    @field_validator("safe_reference")
    @classmethod
    def _safe_reference_value(cls, value: str | None) -> str | None:
        return _safe_text(value, field="bankruptcy reference") if value is not None else None

    @model_validator(mode="after")
    def _message_catalog(self) -> "PublicBankruptcyPublication":
        if self.message != _BANKRUPTCY_MESSAGES[self.kind]:
            raise ValueError("bankruptcy message does not match the approved kind catalog")
        return self


class BankruptcyBlock(PublicModel):
    total: int = Field(ge=0); returned: int = Field(ge=0); limit: int = Field(ge=1); offset: int = Field(ge=0)
    typed_counts: BankruptcyTypedCounts
    publications: list[PublicBankruptcyPublication] = Field(default_factory=list)
    disclaimer: str

    @field_validator("disclaimer")
    @classmethod
    def _disclaimer_catalog(cls, value: str) -> str:
        if value != _BANKRUPTCY_DISCLAIMER:
            raise ValueError("bankruptcy disclaimer is outside the approved catalog")
        return value


class PublicTaxRecord(PublicModel):
    record_type: str
    document_date: date | None = None
    period: str | None = None
    amount: PublicMoney | None = None

    @field_validator("record_type")
    @classmethod
    def _safe_record_type(cls, value: str) -> str:
        return _safe_text(value, field="tax record type")


class TaxBlock(PublicModel):
    unpaid_debt_indicator: bool
    message: str
    as_of_date: date | None = None
    records: list[PublicTaxRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def _message_catalog(self) -> "TaxBlock":
        if self.message != _TAX_MESSAGES[self.unpaid_debt_indicator]:
            raise ValueError("tax message does not match the approved boolean catalog")
        return self


class PublicManager(PublicModel):
    name: str = Field(min_length=1)
    role: str
    appointed_at: date | None = None
    is_inaccuracy: bool | None = None

    @field_validator("name", "role")
    @classmethod
    def _safe_manager_string(cls, value: str) -> str:
        return _safe_text(value, field="manager string")


class PublicOwner(PublicModel):
    name_or_org: str = Field(min_length=1)
    owner_type: Literal["person", "organization"]
    organization_inn: str | None = None
    organization_ogrn: str | None = None
    share_percent_decimal: str | None = None
    share_display: str | None = None
    ownership_effective_at: date | None = None
    _share = field_validator("share_percent_decimal")(_validate_decimal)

    @field_validator("name_or_org")
    @classmethod
    def _safe_owner_name(cls, value: str) -> str:
        return _safe_text(value, field="owner name")

    @model_validator(mode="after")
    def _identifiers(self) -> "PublicOwner":
        if self.organization_inn is not None and not _INN.fullmatch(self.organization_inn):
            raise ValueError("invalid owner INN")
        if self.organization_ogrn is not None and not _OGRN.fullmatch(self.organization_ogrn):
            raise ValueError("invalid owner OGRN")
        return self


class ManagementBlock(PublicModel):
    managers: list[PublicManager] = Field(default_factory=list)
    owners: list[PublicOwner] = Field(default_factory=list)

    @model_validator(mode="after")
    def _non_empty(self) -> "ManagementBlock":
        if not self.managers and not self.owners:
            raise ValueError("management block must contain a manager or owner")
        return self


LimitationCode: TypeAlias = Literal[
    "address_not_requested", "address_marked_inaccurate", "legal_form_mapping_unknown",
    "identity_status_mapping_unknown", "identity_status_conflict",
    "finance_unit_evidence_not_passed", "finance_series_conflict",
    "finance_dataset_not_found", "finance_dataset_failed", "arbitration_identity_conflict",
    "arbitration_target_identity_incomplete", "arbitration_unknown_currency",
    "arbitration_partial_slice", "arbitration_malformed_records",
    "legacy_arbitration_role_detail_unavailable", "arbitration_dataset_not_found",
    "arbitration_dataset_failed", "tax_schema_gate_not_passed",
    "tax_operational_gate_not_passed", "bankruptcy_schema_gate_not_passed",
    "bankruptcy_operational_gate_not_passed", "management_privacy_gate_not_passed",
    "management_schema_gate_not_passed", "management_operational_gate_not_passed",
]


class PublicCoverageItem(PublicModel):
    block_id: FactualBlockId
    dataset: DatasetId
    state: Literal["available", "available_empty", "not_found", "not_requested", "partial", "failed", "conflict"]
    total: int | None = Field(default=None, ge=0); returned: int | None = Field(default=None, ge=0)
    limit: int | None = Field(default=None, ge=0); offset: int | None = Field(default=None, ge=0)
    limitation_codes: list[LimitationCode] = Field(default_factory=list)


class PublicSourceItem(PublicModel):
    dataset: DatasetId
    received_at: datetime
    effective_at: date | None = None
    period: str | None = None
    normalization_version: NormalizationVersion

    @field_validator("received_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("source time must be aware")
        return value.astimezone(timezone.utc)


class PublicLimitation(PublicModel):
    code: LimitationCode
    block_id: PublicBlockId | None = None
    field_id: Literal["identity.status_label", "requisites.legal_address", "requisites.legal_form", "finance.metrics.money", "finance.metrics.yoy", "arbitration.selected_cases.attributed_role", "arbitration.claim_amounts"] | None = None
    message: str = Field(min_length=1)

    @field_validator("message")
    @classmethod
    def _safe_message(cls, value: str) -> str:
        return _safe_text(value, field="limitation message")


class PublicAction(PublicModel):
    action_id: Literal["check_another_company", "prepare_claim"]
    label: Literal["Проверить другую компанию", "Подготовить претензию"]
    path: str


class PublicBreadcrumb(PublicModel):
    label: str = Field(min_length=1)
    path: str


class PublicInternalLink(PublicModel):
    label: str
    path: str
    relation: str

    @field_validator("label", "relation")
    @classmethod
    def _safe_link_string(cls, value: str) -> str:
        return _safe_text(value, field="internal link string")

    @field_validator("path")
    @classmethod
    def _same_origin_path(cls, value: str) -> str:
        return _same_origin_absolute_path(value, field="internal link path")


class CompanyPublicH1Blocks(PublicModel):
    requisites: RequisitesBlock | None
    finance: FinanceBlock | None
    arbitration: ArbitrationBlock | None
    bankruptcy: BankruptcyBlock | None
    tax: TaxBlock | None
    management: ManagementBlock | None


_COVERAGE_ORDER = ("requisites", "finance", "arbitration", "bankruptcy", "tax", "management")
_SOURCE_ORDER = ("counterparty", "finance", "arbitration", "tax_info", "bankruptcy")
_OPTIONAL_GATE_CODES: dict[str, tuple[LimitationCode, ...]] = {
    "bankruptcy": (
        "bankruptcy_schema_gate_not_passed",
        "bankruptcy_operational_gate_not_passed",
    ),
    "tax": ("tax_schema_gate_not_passed", "tax_operational_gate_not_passed"),
    "management": (
        "management_privacy_gate_not_passed",
        "management_schema_gate_not_passed",
        "management_operational_gate_not_passed",
    ),
}


class CompanyPublicH1Response(PublicModel):
    contract_version: Literal["company_public_h1_v1"] = "company_public_h1_v1"
    report_id: UUID
    report_version: Literal["1", "2"]
    projection_scope: Literal["published", "latest_unpublished"]
    canonical_path: str
    indexable: bool
    checked_at: datetime
    checked_date: date
    checked_date_display: str
    identity: CompanyPublicIdentity
    block_order: list[PublicBlockId]
    blocks: CompanyPublicH1Blocks
    coverage: list[PublicCoverageItem] = Field(min_length=6, max_length=6)
    sources: list[PublicSourceItem]
    limitations: list[PublicLimitation]
    actions: list[PublicAction] = Field(min_length=2, max_length=2)
    breadcrumbs: list[PublicBreadcrumb] = Field(min_length=2, max_length=2)
    internal_links: list[PublicInternalLink] = Field(default_factory=list)

    @model_validator(mode="after")
    def _contract(self) -> "CompanyPublicH1Response":
        if self.checked_at.tzinfo is None or self.checked_at.utcoffset() is None:
            raise ValueError("checked_at must be aware")
        if self.checked_at.utcoffset() != timezone.utc.utcoffset(self.checked_at):
            raise ValueError("checked_at must be UTC")
        canonical = _CANONICAL.fullmatch(self.canonical_path)
        if canonical is None or canonical.group("inn") != self.identity.inn:
            raise ValueError("canonical path does not match identity")
        if tuple(item.block_id for item in self.coverage) != _COVERAGE_ORDER:
            raise ValueError("coverage order is invalid")
        expected_datasets = ("counterparty", "finance", "arbitration", "bankruptcy", "tax_info", "counterparty")
        if tuple(item.dataset for item in self.coverage) != expected_datasets or self.coverage[0].state != "available":
            raise ValueError("coverage mapping is invalid")
        if tuple(item.dataset for item in self.sources) != tuple(name for name in _SOURCE_ORDER if name in {source.dataset for source in self.sources}):
            raise ValueError("source order is invalid")
        for source in self.sources:
            expected = f"{source.dataset}_normalizer_v1"
            if source.dataset == "arbitration" and self.report_version == "2":
                expected = "arbitration_normalizer_v2"
            if source.normalization_version != expected:
                raise ValueError("source normalization version is dishonest")
        if self.projection_scope == "latest_unpublished" and self.indexable:
            raise ValueError("unpublished projection cannot be indexable")
        expected_date = self.checked_at.astimezone(_MSK)
        if self.checked_date != expected_date.date() or self.checked_date_display != f"{expected_date.day} {_MONTHS[expected_date.month - 1]} {expected_date.year} года":
            raise ValueError("checked date policy is invalid")
        if (
            self.identity.status_code is not None
            or self.identity.status_label is not None
            or self.identity.status_effective_at is not None
        ):
            raise ValueError("public status catalog/effective date is not evidence-enabled")
        if self.blocks.requisites is None:
            raise ValueError("requisites must be present after the identity gate")
        if self.blocks.requisites.legal_form is not None:
            raise ValueError("legal form catalog is not evidence-enabled")
        if self.blocks.bankruptcy is not None or self.blocks.tax is not None or self.blocks.management is not None or self.internal_links:
            raise ValueError("disabled H1 blocks must be absent")
        if self.blocks.finance is not None:
            if self.blocks.finance.unit_policy_version is not None or any(
                metric.money is not None for metric in self.blocks.finance.metrics
            ):
                raise ValueError("finance money gate is disabled")
            if any(metric.yoy is None for metric in self.blocks.finance.metrics):
                raise ValueError("finance metrics require an enabled public fact")
        coverage_by_block = {item.block_id: item for item in self.coverage}
        for block_id, limitation_codes in _OPTIONAL_GATE_CODES.items():
            item = coverage_by_block[block_id]
            if (
                item.state != "not_requested"
                or any(
                    value is not None
                    for value in (item.total, item.returned, item.limit, item.offset)
                )
                or tuple(item.limitation_codes) != limitation_codes
            ):
                raise ValueError("disabled H1 coverage gate is invalid")
        factual = ["requisites"]
        if self.blocks.finance is not None:
            factual.append("finance")
        if self.blocks.arbitration is not None:
            factual.append("arbitration")
        expected_order: list[str] = ["breadcrumbs", "identity_status", "known_summary"]
        if len(factual) >= 2:
            expected_order.append("in_page_navigation")
        expected_order.extend(["coverage_checked_at", *factual, "sources_limitations", "neutral_actions"])
        if self.block_order != expected_order:
            raise ValueError("block order is invalid")
        expected_actions = ("check_another_company", "prepare_claim")
        if tuple(item.action_id for item in self.actions) != expected_actions or self.actions[0].label != "Проверить другую компанию" or self.actions[0].path != "/" or self.actions[1].label != "Подготовить претензию" or self.actions[1].path != f"/claims?report_id={self.report_id}":
            raise ValueError("actions are invalid")
        if self.breadcrumbs[0] != PublicBreadcrumb(label="Главная", path="/") or self.breadcrumbs[1].label != self.identity.display_name or self.breadcrumbs[1].path != self.canonical_path:
            raise ValueError("breadcrumbs are invalid")
        for limitation in self.limitations:
            if (
                limitation.block_id,
                limitation.field_id,
                limitation.message,
            ) != _LIMITATIONS[limitation.code]:
                raise ValueError("limitation does not match the fixed catalog")
        expected_limitations = sorted(
            self.limitations,
            key=lambda item: (item.block_id or "", item.field_id or "", item.code),
        )
        if self.limitations != expected_limitations or len({(i.block_id, i.field_id, i.code) for i in self.limitations}) != len(self.limitations):
            raise ValueError("limitations are not deterministically ordered")
        limitation_codes = {item.code for item in self.limitations}
        if any(code not in limitation_codes for coverage in self.coverage for code in coverage.limitation_codes):
            raise ValueError("coverage references a missing limitation")
        return self


_LIMITATIONS: dict[LimitationCode, tuple[str, str | None, str]] = {
    "address_not_requested": ("requisites", "requisites.legal_address", "Юридический адрес не запрашивался в сохранённом отчёте."),
    "address_marked_inaccurate": ("requisites", "requisites.legal_address", "Источник пометил юридический адрес как недостоверный."),
    "legal_form_mapping_unknown": ("requisites", "requisites.legal_form", "Организационно-правовая форма не отображена: значение отсутствует в утверждённом справочнике."),
    "identity_status_mapping_unknown": ("identity_status", "identity.status_label", "Статус компании не отображён: значение отсутствует в утверждённом справочнике."),
    "identity_status_conflict": ("identity_status", "identity.status_label", "Статус компании не отображён из-за противоречивых сохранённых сведений."),
    "finance_unit_evidence_not_passed": ("finance", "finance.metrics.money", "Денежные значения не показаны: единица источника не подтверждена сохранёнными доказательствами."),
    "finance_series_conflict": ("finance", "finance.metrics.yoy", "Изменение показателя не рассчитано из-за неоднозначного сопоставления периодов."),
    "finance_dataset_not_found": ("finance", None, "Финансовые сведения не найдены в области ответа источника; нулевые значения не предполагаются."),
    "finance_dataset_failed": ("finance", None, "Финансовые сведения недоступны из-за ошибки получения или нормализации."),
    "arbitration_identity_conflict": ("arbitration", "arbitration.selected_cases.attributed_role", "Роль компании в отдельных делах не определена из-за противоречивых идентификаторов."),
    "arbitration_target_identity_incomplete": ("arbitration", "arbitration.selected_cases.attributed_role", "Роль компании в отдельных делах не определена из-за неполных идентификаторов."),
    "arbitration_unknown_currency": ("arbitration", "arbitration.claim_amounts", "Часть сумм требований не показана: валюта источника не распознана."),
    "arbitration_partial_slice": ("arbitration", None, "Показана только сохранённая часть арбитражных сведений."),
    "arbitration_malformed_records": ("arbitration", None, "Часть арбитражных записей пропущена из-за некорректной структуры."),
    "legacy_arbitration_role_detail_unavailable": ("arbitration", "arbitration.selected_cases.attributed_role", "Для отчёта версии 1 детализация роли по отдельным делам недоступна."),
    "arbitration_dataset_not_found": ("arbitration", None, "Арбитражные сведения не найдены в области ответа источника; отсутствие дел не предполагается."),
    "arbitration_dataset_failed": ("arbitration", None, "Арбитражные сведения недоступны из-за ошибки получения или нормализации."),
    "tax_schema_gate_not_passed": ("tax", None, "Налоговые сведения не запрашивались: схема источника не подтверждена."),
    "tax_operational_gate_not_passed": ("tax", None, "Дополнительный запрос налоговых сведений не активирован."),
    "bankruptcy_schema_gate_not_passed": ("bankruptcy", None, "Сведения о банкротных публикациях не запрашивались: схема источника не подтверждена."),
    "bankruptcy_operational_gate_not_passed": ("bankruptcy", None, "Дополнительный запрос банкротных публикаций не активирован."),
    "management_privacy_gate_not_passed": ("management", None, "Персональные сведения о руководителях не публикуются без утверждённой privacy policy."),
    "management_schema_gate_not_passed": ("management", None, "Сведения о владельцах не публикуются: схема и семантика долей не подтверждены."),
    "management_operational_gate_not_passed": ("management", None, "Дополнительные блоки руководителей и владельцев не запрашивались."),
}


def canonical_json(value: PublicModel) -> bytes:
    return json.dumps(value.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _limitation(code: LimitationCode) -> PublicLimitation:
    block, field, message = _LIMITATIONS[code]
    return PublicLimitation(code=code, block_id=block, field_id=field, message=message)


def _identity(report: CompanyReport) -> tuple[CompanyPublicIdentity, list[PublicLimitation]]:
    dataset = report.datasets.get("counterparty")
    cp = report.counterparty
    if dataset is None or dataset.status is not DatasetReportStatus.AVAILABLE or cp is None or cp.inn != report.target_identifier or not _INN.fullmatch(cp.inn or ""):
        raise ValueError("public counterparty identity is unavailable")
    full_raw = cp.full_name or (cp.names.full_name if cp.names else None)
    short_raw = cp.short_name or (cp.names.short_name if cp.names else None)
    if not full_raw:
        raise ValueError("public legal name is unavailable")
    full = _display_legal_name(full_raw)
    short = _display_legal_name(short_raw) if short_raw else None
    limitations: list[PublicLimitation] = []
    # No reviewed production status dictionary exists in the repository.
    status_values = [value for value in (cp.status_code, cp.status_text, cp.status.code if cp.status else None, cp.status.text if cp.status else None) if value]
    if status_values:
        limitations.append(_limitation("identity_status_mapping_unknown"))
    if cp.status and cp.status.is_active is not None and cp.is_active is not None and cp.status.is_active != cp.is_active:
        limitations = [item for item in limitations if item.code != "identity_status_mapping_unknown"]
        limitations.append(_limitation("identity_status_conflict"))
    return CompanyPublicIdentity(legal_full_name=full, legal_short_name=short, display_name=short or full, inn=cp.inn), limitations


def _requisites(report: CompanyReport) -> tuple[RequisitesBlock, list[PublicLimitation]]:
    cp = report.counterparty
    assert cp is not None
    limitations: list[PublicLimitation] = []
    legal_form = None
    if cp.legal_form:
        limitations.append(_limitation("legal_form_mapping_unknown"))
    ogrn = cp.ogrn if cp.ogrn and _OGRN.fullmatch(cp.ogrn) else None
    if ogrn is not None and ((len(cp.inn or "") == 10) != (len(ogrn) == 13)):
        ogrn = None
    kpp = cp.kpp if len(cp.inn or "") == 10 and cp.kpp and _KPP.fullmatch(cp.kpp) else None
    address = None
    address_state = cp.block_statuses.get("address")
    if address_state is CounterpartyBlockStatus.AVAILABLE and cp.address and cp.address.line_address:
        source = cp.address
        address = PublicAddress(display_line=_safe_text(source.line_address, field="address"), postal_code=source.zip_code, country=source.country, region=source.region, city=source.city, street=source.street, house=source.house, office=source.office, is_inaccuracy=source.is_inaccuracy)
        if source.is_inaccuracy:
            limitations.append(_limitation("address_marked_inaccurate"))
    elif address_state in {None, CounterpartyBlockStatus.NOT_REQUESTED}:
        limitations.append(_limitation("address_not_requested"))
    region = PublicRegion(code=cp.address.region_code, name=cp.address.region) if address_state is CounterpartyBlockStatus.AVAILABLE and cp.address and (cp.address.region_code or cp.address.region) else None
    return RequisitesBlock(legal_form=legal_form, ogrn_or_ogrnip=ogrn, kpp=kpp, registration_date=cp.registration_date, dissolved_date=cp.dissolved_date, region=region, legal_address=address), limitations


def _finance(report: CompanyReport) -> tuple[FinanceBlock | None, list[PublicLimitation]]:
    if report.finance is None:
        return None, []
    grouped: dict[PublicFinanceMetricId, list] = defaultdict(list)
    has_amount = False
    for series in report.finance.indicators:
        metric = _SERIES.get((series.form, series.code))
        if metric is not None:
            grouped[metric].append(series)
            has_amount = has_amount or any(value is not None for value in series.values_by_year.values())
    has_amount = has_amount or any(
        value is not None
        for period in report.finance.periods
        for field, value in period.model_dump(mode="python").items()
        if field != "year"
    )
    limitations: list[PublicLimitation] = []
    if has_amount:
        limitations.append(_limitation("finance_unit_evidence_not_passed"))
    metrics: list[FinanceMetric] = []
    for metric_id in _METRICS:
        candidates = grouped.get(metric_id, [])
        if len(candidates) > 1:
            limitations.append(_limitation("finance_series_conflict"))
            continue
        if not candidates:
            continue
        values = candidates[0].values_by_year
        for year in sorted(values, reverse=True):
            current, previous = values[year], values.get(year - 1)
            if current is None or previous is None or previous == 0:
                continue
            exact = (current - previous) / abs(previous) * Decimal("100")
            exact_string = _canonical_decimal(exact)
            display_value = f"{exact.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP):+.1f}".replace(".", ",") + "%"
            metrics.append(FinanceMetric(metric_id=metric_id, year=year, money=None, yoy=PublicPercentChange(exact_percent=exact_string, display_value=display_value, current_year=year, previous_year=year - 1, formula_version="finance_yoy_v1")))
    return (FinanceBlock(unit_policy_version=None, metrics=metrics) if metrics else None), limitations


def _party_match(party: ArbitrationParty, inn: str, ogrn: str | None) -> Literal["match", "conflict", "incomplete", "none"]:
    pin = party.inn if party.inn and _INN.fullmatch(party.inn) else None
    pogrn = party.ogrn if party.ogrn and _OGRN.fullmatch(party.ogrn) else None
    if party.inn and pin is None or party.ogrn and pogrn is None:
        return "none"
    if pin and pogrn:
        if ogrn is None:
            return "incomplete" if pin == inn else "none"
        if pin == inn and pogrn == ogrn:
            return "match"
        return "conflict" if pin == inn or pogrn == ogrn else "none"
    if pin:
        return "match" if pin == inn else "none"
    if pogrn:
        return "match" if ogrn is not None and pogrn == ogrn else "none"
    return "none"


def _case_role(case: ArbitrationCaseFacts, *, inn: str, ogrn: str | None, report_version: str) -> tuple[str, set[LimitationCode]]:
    collections = (
        ("plaintiff", case.plaintiffs), ("respondent", case.respondents), ("applicant", case.applicants),
        ("creditor", case.creditors), ("debtor", case.debtors),
        ("other", case.third_parties + case.interested_persons + case.other_parties),
    )
    matches: list[str] = []
    outcomes: set[str] = set()
    for role, parties in collections:
        results = {_party_match(party, inn, ogrn) for party in parties}
        outcomes.update(results)
        if "match" in results:
            matches.append(role)
    limitations: set[LimitationCode] = set()
    if "conflict" in outcomes:
        limitations.add("arbitration_identity_conflict")
    if "incomplete" in outcomes:
        limitations.add("arbitration_target_identity_incomplete")
    if report_version == "1" and not any(parties for _, parties in collections):
        limitations.add("legacy_arbitration_role_detail_unavailable")
    if limitations.intersection(
        {"arbitration_identity_conflict", "arbitration_target_identity_incomplete"}
    ):
        return "unattributed", limitations
    if len(matches) == 1:
        return matches[0], limitations
    if len(matches) > 1:
        return "other", limitations
    return "unattributed", limitations


def _case_sort_key(item: PublicArbitrationCase) -> tuple[tuple[int, int], tuple[int, int], str]:
    updated = (0, -item.date_update.toordinal()) if item.date_update else (1, 0)
    started = (0, -item.date_start.toordinal()) if item.date_start else (1, 0)
    return updated, started, item.case_number


def _arbitration(report: CompanyReport) -> tuple[ArbitrationBlock | None, list[PublicLimitation]]:
    facts = report.arbitration
    if facts is None:
        return None, []
    if facts.total_cases < 0:
        raise ValueError("arbitration total_cases must be non-negative")
    if facts.limit <= 0:
        raise ValueError("arbitration limit must be positive")
    if facts.offset < 0:
        raise ValueError("arbitration offset must be non-negative")
    cp = report.counterparty
    target_ogrn = cp.ogrn if cp and cp.ogrn and _OGRN.fullmatch(cp.ogrn) else None
    limitations: set[LimitationCode] = set()
    valid: list[tuple[ArbitrationCaseFacts, str]] = []
    malformed = facts.malformed_entry_count
    for case in facts.cases:
        if not case.party_collections_valid:
            malformed += 1
            continue
        case_number = None
        internal_id = None
        if case.case_number is not None:
            try:
                case_number = _safe_text(case.case_number, field="case number")
            except ValueError:
                pass
        if case.internal_id is not None:
            try:
                internal_id = _safe_text(case.internal_id, field="arbitration internal id")
            except ValueError:
                pass
        if case_number is None and internal_id is None:
            malformed += 1
            continue
        role, role_limitations = _case_role(case, inn=report.target_identifier, ogrn=target_ogrn, report_version=report.report_version)
        limitations.update(role_limitations)
        valid.append(
            (
                case.model_copy(
                    update={"case_number": case_number, "internal_id": internal_id}
                ),
                role,
            )
        )
    returned = facts.returned_cases
    if len(valid) + malformed != returned:
        raise ValueError("arbitration raw returned invariant failed")
    if malformed:
        limitations.add("arbitration_malformed_records")
    if not facts.is_complete or facts.offset > 0 or returned < facts.total_cases:
        limitations.add("arbitration_partial_slice")

    role_counts = Counter(role for _, role in valid if role != "unattributed")
    unattributed = sum(role == "unattributed" for _, role in valid)
    status_counts = Counter(case.normalized_status.value for case, _ in valid)
    result_counts = Counter(case.normalized_result_type.value for case, _ in valid)
    totals: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    selected: list[PublicArbitrationCase] = []
    for case, role in valid:
        amount_dto = None
        if case.claim_amount is not None and role in {"plaintiff", "respondent"}:
            currency = case.currency or ""
            if not _CURRENCY.fullmatch(currency):
                limitations.add("arbitration_unknown_currency")
            else:
                totals[(role, currency)] += case.claim_amount
                exact = _canonical_decimal(case.claim_amount)
                amount_dto = ArbitrationClaimAmount(role=role, currency=currency, exact_decimal=exact, display_value=f"{exact.replace('.', ',')} {currency}")
        if case.case_number is not None:
            selected.append(PublicArbitrationCase(case_number=case.case_number, date_start=case.date_start, date_update=case.date_update, attributed_role=role, claim_amount=amount_dto))
    selected.sort(key=_case_sort_key)
    amounts = []
    for role in ("plaintiff", "respondent"):
        for currency in sorted(currency for total_role, currency in totals if total_role == role):
            exact = _canonical_decimal(totals[(role, currency)])
            amounts.append(ArbitrationClaimAmount(role=role, currency=currency, exact_decimal=exact, display_value=f"{exact.replace('.', ',')} {currency}"))
    block = ArbitrationBlock(
        total_cases=facts.total_cases, returned_cases=returned,
        normalized_case_count=len(valid), malformed_count=malformed,
        limit=facts.limit, offset=facts.offset,
        role_counts=ArbitrationRoleCounts(plaintiff=role_counts["plaintiff"], respondent=role_counts["respondent"], applicant=role_counts["applicant"], creditor=role_counts["creditor"], debtor=role_counts["debtor"], other=role_counts["other"]),
        unattributed_count=unattributed,
        status_counts=ArbitrationStatusCounts(open=status_counts[ArbitrationStatus.OPEN.value], completed=status_counts[ArbitrationStatus.COMPLETED.value], unknown=status_counts[ArbitrationStatus.UNKNOWN.value]),
        result_counts=ArbitrationResultCounts(satisfied_full=result_counts[ArbitrationResultType.SATISFIED_FULL.value], refused=result_counts[ArbitrationResultType.REFUSED.value], returned=result_counts[ArbitrationResultType.RETURNED.value], undefined=result_counts[ArbitrationResultType.UNDEFINED.value], other=result_counts[ArbitrationResultType.OTHER.value]),
        claim_amounts=amounts, selected_cases=selected[:10],
    )
    return block, [_limitation(code) for code in limitations]


def _dataset_state(status: DatasetReportStatus) -> Literal["available", "not_found", "failed"]:
    if status is DatasetReportStatus.AVAILABLE:
        return "available"
    if status is DatasetReportStatus.NOT_FOUND:
        return "not_found"
    return "failed"


def build_public_h1(report: CompanyReport, *, projection_scope: Literal["published", "latest_unpublished"], persisted_canonical_path: str | None = None, persisted_indexable: bool = False) -> CompanyPublicH1Response:
    if report.status.value not in {"complete", "partial"}:
        raise ValueError("report is not finalized")
    identity, limitations = _identity(report)
    requisites, requisites_limitations = _requisites(report)
    limitations.extend(requisites_limitations)
    path = persisted_canonical_path if projection_scope == "published" else canonical_path(identity.inn, identity.display_name)
    if path is None or _CANONICAL.fullmatch(path) is None or not path.startswith(f"/company/{identity.inn}-"):
        raise ValueError("canonical path unavailable")
    finance, finance_limitations = _finance(report)
    arbitration, arbitration_limitations = _arbitration(report)
    limitations.extend(finance_limitations); limitations.extend(arbitration_limitations)

    finance_state = _dataset_state(report.datasets["finance"].status)
    arbitration_state = _dataset_state(report.datasets["arbitration"].status)
    finance_codes: list[LimitationCode] = [item.code for item in finance_limitations]
    arbitration_codes: list[LimitationCode] = [item.code for item in arbitration_limitations]
    if finance_state == "not_found":
        finance_codes.append("finance_dataset_not_found"); limitations.append(_limitation("finance_dataset_not_found"))
    elif finance_state == "failed":
        finance_codes.append("finance_dataset_failed"); limitations.append(_limitation("finance_dataset_failed"))
    if arbitration_state == "not_found":
        arbitration_codes.append("arbitration_dataset_not_found"); limitations.append(_limitation("arbitration_dataset_not_found"))
    elif arbitration_state == "failed":
        arbitration_codes.append("arbitration_dataset_failed"); limitations.append(_limitation("arbitration_dataset_failed"))
    if arbitration_state == "available" and arbitration is not None:
        if arbitration.total_cases == 0 and arbitration.returned_cases == 0:
            arbitration_state = "available_empty"
        elif "arbitration_partial_slice" in arbitration_codes or "arbitration_malformed_records" in arbitration_codes:
            arbitration_state = "partial"

    optional_codes: tuple[LimitationCode, ...] = (
        "tax_schema_gate_not_passed", "tax_operational_gate_not_passed",
        "bankruptcy_schema_gate_not_passed", "bankruptcy_operational_gate_not_passed",
        "management_privacy_gate_not_passed", "management_schema_gate_not_passed",
        "management_operational_gate_not_passed",
    )
    limitations.extend(_limitation(code) for code in optional_codes)
    coverage = [
        PublicCoverageItem(block_id="requisites", dataset="counterparty", state="available", limitation_codes=[item.code for item in requisites_limitations]),
        PublicCoverageItem(block_id="finance", dataset="finance", state=finance_state, limitation_codes=sorted(set(finance_codes))),
        PublicCoverageItem(block_id="arbitration", dataset="arbitration", state=arbitration_state, total=arbitration.total_cases if arbitration else None, returned=arbitration.returned_cases if arbitration else None, limit=arbitration.limit if arbitration else None, offset=arbitration.offset if arbitration else None, limitation_codes=sorted(set(arbitration_codes))),
        PublicCoverageItem(block_id="bankruptcy", dataset="bankruptcy", state="not_requested", limitation_codes=["bankruptcy_schema_gate_not_passed", "bankruptcy_operational_gate_not_passed"]),
        PublicCoverageItem(block_id="tax", dataset="tax_info", state="not_requested", limitation_codes=["tax_schema_gate_not_passed", "tax_operational_gate_not_passed"]),
        PublicCoverageItem(block_id="management", dataset="counterparty", state="not_requested", limitation_codes=["management_privacy_gate_not_passed", "management_schema_gate_not_passed", "management_operational_gate_not_passed"]),
    ]
    limitations = sorted({(item.block_id, item.field_id, item.code): item for item in limitations}.values(), key=lambda item: (item.block_id, item.field_id or "", item.code))
    sources = []
    for name in ("counterparty", "finance", "arbitration"):
        dataset = report.datasets[name]
        if dataset.status is DatasetReportStatus.AVAILABLE and dataset.source:
            normalizer: NormalizationVersion = f"{name}_normalizer_v{'2' if name == 'arbitration' and report.report_version == '2' else '1'}"  # type: ignore[assignment]
            sources.append(PublicSourceItem(dataset=name, received_at=dataset.source.received_at, normalization_version=normalizer))
    checked_at = report.generated_at.astimezone(timezone.utc)
    checked = checked_at.astimezone(_MSK)
    factual = [name for name, block in (("requisites", requisites), ("finance", finance), ("arbitration", arbitration)) if block is not None]
    order: list[PublicBlockId] = ["breadcrumbs", "identity_status", "known_summary"]
    if len(factual) >= 2:
        order.append("in_page_navigation")
    order.extend(["coverage_checked_at", *factual, "sources_limitations", "neutral_actions"])
    dto = CompanyPublicH1Response(
        report_id=report.report_id, report_version=report.report_version, projection_scope=projection_scope,
        canonical_path=path, indexable=bool(projection_scope == "published" and persisted_indexable),
        checked_at=checked_at, checked_date=checked.date(), checked_date_display=f"{checked.day} {_MONTHS[checked.month - 1]} {checked.year} года",
        identity=identity, block_order=order,
        blocks=CompanyPublicH1Blocks(requisites=requisites, finance=finance, arbitration=arbitration, bankruptcy=None, tax=None, management=None),
        coverage=coverage, sources=sources, limitations=limitations,
        actions=[PublicAction(action_id="check_another_company", label="Проверить другую компанию", path="/"), PublicAction(action_id="prepare_claim", label="Подготовить претензию", path=f"/claims?report_id={report.report_id}")],
        breadcrumbs=[PublicBreadcrumb(label="Главная", path="/"), PublicBreadcrumb(label=identity.display_name, path=path)], internal_links=[],
    )
    return dto


def _public_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _public_field(field: str, value: object) -> str:
    esc = html.escape
    return (
        f'<li data-field="{esc(field, quote=True)}">'
        f'<span class="field-label">{esc(field)}</span>: '
        f'<span class="field-value">{esc(_public_scalar(value))}</span></li>'
    )


def _public_value_fields(value: object, *, prefix: str) -> str:
    if isinstance(value, dict):
        return "".join(
            _public_value_fields(child, prefix=f"{prefix}.{key}" if prefix else key)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return "".join(
            _public_value_fields(child, prefix=f"{prefix}.{index}")
            for index, child in enumerate(value)
        )
    return _public_field(prefix, value)


def _public_section(section_id: str, title: str, rows: str) -> str:
    return (
        f'<section id="{html.escape(section_id, quote=True)}">'
        f"<h2>{html.escape(title)}</h2><ul>{rows}</ul></section>"
    )


def render_public_h1_html(dto: CompanyPublicH1Response) -> str:
    """Render the complete allowlisted DTO as deterministic, escaped HTML."""
    esc = html.escape
    attrs = " ".join(
        (
            f'data-contract-version="{esc(dto.contract_version, quote=True)}"',
            f'data-report-id="{esc(str(dto.report_id), quote=True)}"',
            f'data-report-version="{esc(dto.report_version, quote=True)}"',
            f'data-projection-scope="{esc(dto.projection_scope, quote=True)}"',
            f'data-canonical-path="{esc(dto.canonical_path, quote=True)}"',
            f'data-indexable="{_public_scalar(dto.indexable)}"',
            f'data-block-order="{esc(",".join(dto.block_order), quote=True)}"',
        )
    )

    breadcrumb_items = "".join(
        (
            "<li>"
            f'<a href="{esc(item.path, quote=True)}">{esc(item.label)}</a>'
            "<ul>"
            + _public_value_fields(
                item.model_dump(mode="json", exclude_none=True),
                prefix=f"breadcrumbs.{index}",
            )
            + "</ul></li>"
        )
        for index, item in enumerate(dto.breadcrumbs)
    )
    breadcrumbs = (
        '<nav id="breadcrumbs" aria-label="Хлебные крошки">'
        f"<ol>{breadcrumb_items}</ol></nav>"
    )

    identity_dump = dto.identity.model_dump(mode="json", exclude_none=True)
    status_dump = {
        key: identity_dump[key]
        for key in ("status_code", "status_label", "status_effective_at")
        if key in identity_dump
    }
    status_rows = _public_value_fields(status_dump, prefix="identity")
    if not status_rows:
        status_rows = '<li data-field="identity.status">Статус не отображён</li>'
    identity_status = _public_section("identity-status", "Статус", status_rows)

    summary_dump = {
        key: identity_dump[key]
        for key in ("legal_full_name", "legal_short_name", "display_name", "inn")
        if key in identity_dump
    }
    summary_rows = _public_value_fields(summary_dump, prefix="identity")
    known_summary = (
        f'<section id="known-summary"><h1>{esc(dto.identity.display_name)}</h1>'
        f"<ul>{summary_rows}</ul></section>"
    )

    factual_blocks = [
        block_id
        for block_id in ("requisites", "finance", "arbitration")
        if getattr(dto.blocks, block_id) is not None
    ]
    in_page_navigation = (
        '<nav id="in-page-navigation" aria-label="Разделы">'
        + "".join(
            f'<a href="#{esc(block_id, quote=True)}">{esc(block_id)}</a>'
            for block_id in factual_blocks
        )
        + "</nav>"
    )

    serialized = dto.model_dump(mode="json")
    checked_rows = _public_value_fields(
        {
            "checked_at": serialized["checked_at"],
            "checked_date": serialized["checked_date"],
            "checked_date_display": serialized["checked_date_display"],
        },
        prefix="",
    )
    coverage_rows = checked_rows + _public_value_fields(
        [item.model_dump(mode="json", exclude_none=True) for item in dto.coverage],
        prefix="coverage",
    )
    coverage = _public_section("coverage-checked-at", "Покрытие", coverage_rows)

    requisites = ""
    if dto.blocks.requisites is not None:
        requisites = _public_section(
            "requisites",
            "Реквизиты",
            _public_value_fields(
                dto.blocks.requisites.model_dump(mode="json", exclude_none=True),
                prefix="requisites",
            ),
        )

    finance = ""
    if dto.blocks.finance is not None:
        finance = _public_section(
            "finance",
            "Финансы",
            _public_value_fields(
                dto.blocks.finance.model_dump(mode="json", exclude_none=True),
                prefix="finance",
            ),
        )

    arbitration = ""
    if dto.blocks.arbitration is not None:
        arbitration = _public_section(
            "arbitration",
            "Арбитраж",
            _public_value_fields(
                dto.blocks.arbitration.model_dump(mode="json", exclude_none=True),
                prefix="arbitration",
            ),
        )

    sources_rows = _public_value_fields(
        [item.model_dump(mode="json", exclude_none=True) for item in dto.sources],
        prefix="sources",
    )
    limitations_rows = _public_value_fields(
        [item.model_dump(mode="json", exclude_none=True) for item in dto.limitations],
        prefix="limitations",
    )
    sources_limitations = (
        '<section id="sources-limitations">'
        + _public_section("sources", "Источники", sources_rows)
        + _public_section("limitations", "Ограничения", limitations_rows)
        + "</section>"
    )

    action_items = "".join(
        (
            "<li>"
            f'<a data-action-id="{esc(item.action_id, quote=True)}" '
            f'href="{esc(item.path, quote=True)}">{esc(item.label)}</a>'
            "<ul>"
            + _public_value_fields(
                item.model_dump(mode="json", exclude_none=True),
                prefix=f"actions.{index}",
            )
            + "</ul></li>"
        )
        for index, item in enumerate(dto.actions)
    )
    neutral_actions = (
        '<nav id="neutral-actions" aria-label="Действия">'
        f"<ul>{action_items}</ul></nav>"
    )

    fragments = {
        "breadcrumbs": breadcrumbs,
        "identity_status": identity_status,
        "known_summary": known_summary,
        "in_page_navigation": in_page_navigation,
        "coverage_checked_at": coverage,
        "requisites": requisites,
        "finance": finance,
        "arbitration": arbitration,
        "bankruptcy": "",
        "tax": "",
        "management": "",
        "sources_limitations": sources_limitations,
        "neutral_actions": neutral_actions,
        "internal_links": "",
    }
    body = "".join(fragments[block_id] for block_id in dto.block_order)
    return (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        f"<title>{esc(dto.identity.display_name)}</title></head><body>"
        f"<main {attrs}>{body}</main></body></html>"
    )


__all__ = [name for name in globals() if name.startswith("Public") or name.startswith("CompanyPublic") or name in {"ArbitrationBlock", "ArbitrationClaimAmount", "ArbitrationRoleCounts", "ArbitrationStatusCounts", "ArbitrationResultCounts", "BankruptcyBlock", "BankruptcyTypedCounts", "FinanceBlock", "FinanceMetric", "ManagementBlock", "RequisitesBlock", "TaxBlock", "build_public_h1", "canonical_json", "render_public_h1_html"}]
