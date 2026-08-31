"""Closed, public-only ``company_public_h2_v1`` transport models."""
from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_CODE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_INN = re.compile(r"^(?:[0-9]{10}|[0-9]{12})$")
_PATH = re.compile(r"^/[A-Za-z0-9_./?=&-]{1,2047}$")


class PublicH2Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def _nfc_and_scalar_strings(self) -> "PublicH2Model":
        for value in self.__dict__.values():
            _validate_strings(value)
        return self


def _validate_strings(value: object) -> None:
    if isinstance(value, str):
        if value != unicodedata.normalize("NFC", value) or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise ValueError("public strings must be NFC Unicode scalars")
    elif isinstance(value, PublicH2Model):
        for nested in value.__dict__.values():
            _validate_strings(nested)
    elif isinstance(value, (tuple, list)):
        for nested in value:
            _validate_strings(nested)
    elif isinstance(value, dict):
        normalized: set[str] = set()
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ValueError("public object keys must be strings")
            nfc = unicodedata.normalize("NFC", key)
            if nfc != key or nfc in normalized:
                raise ValueError("public object keys must be unique NFC strings")
            normalized.add(nfc)
            _validate_strings(nested)


class PublicH2Limitation(PublicH2Model):
    code: str
    block_id: str | None = None
    field_id: str | None = None
    message: str

    @model_validator(mode="after")
    def _valid(self) -> "PublicH2Limitation":
        if not _CODE.fullmatch(self.code) or not self.message.strip() or len(self.message) > 512:
            raise ValueError("invalid public limitation")
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
    status: None = None

    @model_validator(mode="after")
    def _identity(self) -> "PublicH2Identity":
        if not _INN.fullmatch(self.inn) or not self.display_name.strip() or not self.legal_full_name.strip():
            raise ValueError("invalid public identity")
        if self.ogrn is not None and not re.fullmatch(r"(?:[0-9]{13}|[0-9]{15})", self.ogrn):
            raise ValueError("invalid OGRN")
        if self.kpp is not None and not re.fullmatch(r"[0-9]{9}", self.kpp):
            raise ValueError("invalid KPP")
        return self


class PublicH2Requisites(PublicH2Model):
    legal_form: None = None
    address: str | None = None
    address_inaccuracy: bool | None = None
    charter_capital: None = None
    tax_modes: tuple[()] = ()
    primary_activity: None = None
    additional_activities: tuple[()] = ()
    managers: tuple[()] = ()
    owners: tuple[()] = ()
    employees: None = None
    tax_authority: None = None


class PublicH2Narrative(PublicH2Model):
    mode: Literal["artifact", "deterministic_fallback"]
    renderer_version: str
    description: str
    statement_ids: tuple[str, ...]
    comments: tuple[()] = ()
    render_digest: str

    @model_validator(mode="after")
    def _narrative(self) -> "PublicH2Narrative":
        if not _CODE.fullmatch(self.renderer_version) or not 400 <= len(self.description) <= 700:
            raise ValueError("invalid public narrative")
        if not 1 <= len(self.statement_ids) <= 16 or len(set(self.statement_ids)) != len(self.statement_ids) or not _DIGEST.fullmatch(self.render_digest):
            raise ValueError("invalid public narrative binding")
        return self


class PublicH2CoverageItem(PublicH2Model):
    block_id: str
    state: Literal["available", "available_empty", "partial", "missing", "not_requested", "failed", "conflict"]
    population_scope: Literal["not_applicable", "complete_collection", "returned_slice"]
    total: int | None = Field(default=None, ge=0)
    returned: int | None = Field(default=None, ge=0)
    eligible: int | None = Field(default=None, ge=0)
    limitation_codes: tuple[str, ...] = ()


class PublicH2SourceItem(PublicH2Model):
    dataset: Literal["counterparty", "finance", "arbitration"]
    received_at: str
    effective_at: str | None = None
    period: str | None = None
    normalization_version: str
    evidence_version: str


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
    finance_f1: None = None
    finance_f2: None = None
    finance_f3: None = None
    finance_f4: None = None
    finance_f5: None = None
    arbitration_a1: None = None
    arbitration_a2: None = None
    arbitration_a3: None = None
    arbitration_a4: None = None
    arbitration_a5: None = None


BLOCK_ORDER = (
    "hero_status", "narrative", "in_page_navigation", "requisites",
    "finance_f1_liquidity", "finance_f2_funding", "finance_f3_growth",
    "finance_f4_profit_per_100", "finance_f5_yearly_table",
    "arbitration_a1_activity", "arbitration_a2_roles", "arbitration_a3_outcomes",
    "arbitration_a4_case_amounts", "arbitration_a5_opponents", "sources_limitations",
    "neutral_actions",
)
COVERAGE_BLOCKS = (
    "requisites", "narrative", "finance_f1", "finance_f2", "finance_f3", "finance_f4", "finance_f5",
    "arbitration_a1", "arbitration_a2", "arbitration_a3", "arbitration_a4", "arbitration_a5", "sources_limitations",
)


class CompanyPublicH2Response(PublicH2Model):
    contract_version: Literal["company_public_h2_v1"] = "company_public_h2_v1"
    projection_digest: str
    report_id: str
    report_version: Literal["1", "2", "3"]
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
    limitations: tuple[PublicH2Limitation, ...] = ()
    actions: tuple[PublicH2Action, PublicH2Action]
    breadcrumbs: tuple[PublicH2Breadcrumb, PublicH2Breadcrumb]
    primary_claim_cta: PublicH2ClaimCta

    @model_validator(mode="after")
    def _closed_contract(self) -> "CompanyPublicH2Response":
        if not _DIGEST.fullmatch(self.projection_digest) or not _PATH.fullmatch(self.canonical_path):
            raise ValueError("invalid public projection digest or path")
        if self.block_order != BLOCK_ORDER or tuple(item.block_id for item in self.coverage) != COVERAGE_BLOCKS:
            raise ValueError("invalid H2 block or coverage order")
        if len(self.sources) not in {1, 2, 3} or tuple(item.dataset for item in self.sources) != ("counterparty", "finance", "arbitration")[:len(self.sources)]:
            raise ValueError("invalid H2 source order")
        if (self.report_version == "3") != (self.snapshot_capability == "card_v2"):
            raise ValueError("invalid snapshot capability")
        if self.report_version in {"1", "2"} and self.indexable:
            raise ValueError("legacy H2 preview is never indexable")
        if tuple(item.action_id for item in self.actions) != ("check_another_company", "prepare_claim"):
            raise ValueError("invalid H2 action order")
        if self.breadcrumbs[0].current or not self.breadcrumbs[1].current:
            raise ValueError("invalid H2 breadcrumbs")
        return self


__all__ = ["BLOCK_ORDER", "COVERAGE_BLOCKS", "CompanyPublicH2Response", "PublicH2Action", "PublicH2Blocks", "PublicH2Breadcrumb", "PublicH2ClaimCta", "PublicH2CoverageItem", "PublicH2Identity", "PublicH2Limitation", "PublicH2Narrative", "PublicH2Requisites", "PublicH2SourceItem"]
