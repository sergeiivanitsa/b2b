from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FrozenDomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NormalizationWarning(FrozenDomainModel):
    code: str
    path: str
    message: str


class SourceMetadata(FrozenDomainModel):
    provider: Literal["datanewton"]
    dataset: str
    endpoint: str
    response_hash: str
    received_at: datetime
    request_id: str | None = None
    status_code: int | None = None
    attempts: int | None = Field(default=None, ge=0)
    duration_ms: float | None = Field(default=None, ge=0)
    provider_limit_metadata: dict[str, Any] | None = None
    warnings: list[NormalizationWarning] = Field(default_factory=list)


class CounterpartyBlockStatus(StrEnum):
    AVAILABLE = "available"
    AVAILABLE_EMPTY = "available_empty"
    NOT_REQUESTED = "not_requested"
    INVALID = "invalid"


class CompanyNames(FrozenDomainModel):
    short_name: str | None = Field(default=None, repr=False)
    full_name: str | None = Field(default=None, repr=False)


class CompanyStatus(FrozenDomainModel):
    is_active: bool | None = None
    code: str | None = None
    text: str | None = None


class CompanyAddress(FrozenDomainModel):
    line_address: str | None = Field(default=None, repr=False)
    country: str | None = Field(default=None, repr=False)
    region: str | None = Field(default=None, repr=False)
    region_code: str | None = Field(default=None, repr=False)
    city: str | None = Field(default=None, repr=False)
    street: str | None = Field(default=None, repr=False)
    house: str | None = Field(default=None, repr=False)
    office: str | None = Field(default=None, repr=False)
    zip_code: str | None = Field(default=None, repr=False)
    is_inaccuracy: bool | None = None


class CompanyManager(FrozenDomainModel):
    full_name: str | None = Field(default=None, repr=False)
    position: str | None = None
    innfl: str | None = Field(default=None, repr=False)
    appointed_at: date | None = None
    is_inaccuracy: bool | None = None


class TaxModeInfo(FrozenDomainModel):
    common_mode: bool | None = None
    usn_sign: bool | None = None
    ausn_sign: bool | None = None
    envd_sign: bool | None = None
    eshn_sign: bool | None = None
    npd_sign: bool | None = None
    psn_sign: bool | None = None
    srp_sign: bool | None = None
    publication_date: date | None = None


class CounterpartyFacts(FrozenDomainModel):
    source: SourceMetadata
    inn: str | None = Field(default=None, repr=False)
    ogrn: str | None = Field(default=None, repr=False)
    kpp: str | None = Field(default=None, repr=False)
    short_name: str | None = Field(default=None, repr=False)
    full_name: str | None = Field(default=None, repr=False)
    names: CompanyNames | None = Field(default=None, repr=False)
    legal_form: str | None = None
    is_active: bool | None = None
    status_code: str | None = None
    status_text: str | None = None
    status: CompanyStatus | None = None
    registration_date: date | None = None
    dissolved_date: date | None = None
    years_from_registration: int | None = None
    charter_capital: Decimal | None = Field(default=None, repr=False)
    address: CompanyAddress | None = Field(default=None, repr=False)
    managers: list[CompanyManager] = Field(default_factory=list, repr=False)
    tax_modes: TaxModeInfo | None = None
    requested_filters: list[str] = Field(default_factory=list)
    block_statuses: dict[str, CounterpartyBlockStatus] = Field(default_factory=dict)
    warnings: list[NormalizationWarning] = Field(default_factory=list)


class FinanceForm(StrEnum):
    BALANCE = "balance"
    FINANCIAL_RESULTS = "financial_results"
    CASH_FLOW = "cash_flow"


class FinancialIndicatorSeries(FrozenDomainModel):
    form: FinanceForm
    code: str
    name: str | None = None
    values_by_year: dict[int, Decimal | None] = Field(default_factory=dict, repr=False)
    source_paths: list[str] = Field(default_factory=list)


class FinancialPeriod(FrozenDomainModel):
    year: int
    total_assets: Decimal | None = Field(default=None, repr=False)
    non_current_assets: Decimal | None = Field(default=None, repr=False)
    current_assets: Decimal | None = Field(default=None, repr=False)
    inventories: Decimal | None = Field(default=None, repr=False)
    accounts_receivable: Decimal | None = Field(default=None, repr=False)
    cash_and_equivalents: Decimal | None = Field(default=None, repr=False)
    equity: Decimal | None = Field(default=None, repr=False)
    long_term_liabilities: Decimal | None = Field(default=None, repr=False)
    short_term_liabilities: Decimal | None = Field(default=None, repr=False)
    short_term_borrowings: Decimal | None = Field(default=None, repr=False)
    accounts_payable: Decimal | None = Field(default=None, repr=False)
    revenue: Decimal | None = Field(default=None, repr=False)
    cost_of_sales: Decimal | None = Field(default=None, repr=False)
    gross_profit: Decimal | None = Field(default=None, repr=False)
    operating_profit: Decimal | None = Field(default=None, repr=False)
    profit_before_tax: Decimal | None = Field(default=None, repr=False)
    net_profit: Decimal | None = Field(default=None, repr=False)
    net_cash_flow: Decimal | None = Field(default=None, repr=False)
    cash_at_start: Decimal | None = Field(default=None, repr=False)
    cash_at_end: Decimal | None = Field(default=None, repr=False)


class FinanceFacts(FrozenDomainModel):
    source: SourceMetadata
    years: list[int] = Field(default_factory=list)
    latest_year: int | None = None
    balance_okud: str | None = None
    financial_results_okud: str | None = None
    cash_flow_okud: str | None = None
    indicators: list[FinancialIndicatorSeries] = Field(default_factory=list, repr=False)
    periods: list[FinancialPeriod] = Field(default_factory=list, repr=False)
    unit: Literal["provider_units_unknown"] = "provider_units_unknown"
    warnings: list[NormalizationWarning] = Field(default_factory=list)


class TaxInfoFacts(FrozenDomainModel):
    """Provider-neutral future-gated facts; no iteration-17 normalizer creates these."""

    source: SourceMetadata
    has_unpaid_debts: bool | None = None
    as_of_date: date | None = None
    records: list[str] = Field(default_factory=list)
    warnings: list[NormalizationWarning] = Field(default_factory=list)


class BankruptcyFacts(FrozenDomainModel):
    """Provider-neutral future-gated facts; no iteration-17 normalizer creates these."""

    source: SourceMetadata
    total: int | None = Field(default=None, ge=0)
    returned: int | None = Field(default=None, ge=0)
    limit: int | None = Field(default=None, ge=0)
    offset: int | None = Field(default=None, ge=0)
    publications: list[str] = Field(default_factory=list)
    warnings: list[NormalizationWarning] = Field(default_factory=list)


class ArbitrationRole(StrEnum):
    PLAINTIFF = "plaintiff"
    RESPONDENT = "respondent"
    APPLICANT = "applicant"
    CREDITOR = "creditor"
    DEBTOR = "debtor"
    THIRD_PARTY = "third_party"
    INTERESTED_PERSON = "interested_person"
    OTHER = "other"
    UNKNOWN = "unknown"


class ArbitrationStatus(StrEnum):
    OPEN = "open"
    COMPLETED = "completed"
    UNKNOWN = "unknown"


class ArbitrationResultType(StrEnum):
    SATISFIED_FULL = "satisfied_full"
    REFUSED = "refused"
    RETURNED = "returned"
    UNDEFINED = "undefined"
    OTHER = "other"


class ArbitrationParty(FrozenDomainModel):
    name: str | None = Field(default=None, repr=False)
    normalized_name: str | None = Field(default=None, repr=False)
    inn: str | None = Field(default=None, repr=False)
    ogrn: str | None = Field(default=None, repr=False)
    raw_role: str | None = None


class ArbitrationDocumentSummary(FrozenDomainModel):
    document_type: str | None = None
    creation_date: date | None = None
    instance_id: str | None = Field(default=None, repr=False)
    instance_name: str | None = Field(default=None, repr=False)
    instance_number: str | None = Field(default=None, repr=False)


class ArbitrationCaseFacts(FrozenDomainModel):
    internal_id: str | None = Field(default=None, repr=False)
    case_number: str | None = Field(default=None, repr=False)
    date_start: date | None = None
    date_update: date | None = None
    updated_at: date | datetime | None = None
    last_document_date: date | None = None
    year: int | None = None
    claim_amount: Decimal | None = Field(default=None, repr=False)
    currency: str | None = None
    raw_status: int | str | None = None
    normalized_status: ArbitrationStatus
    raw_result_type: str | None = None
    normalized_result_type: ArbitrationResultType
    dispute_code: int | str | None = None
    company_roles: list[ArbitrationRole] = Field(default_factory=list)
    plaintiffs: list[ArbitrationParty] = Field(default_factory=list, repr=False)
    respondents: list[ArbitrationParty] = Field(default_factory=list, repr=False)
    applicants: list[ArbitrationParty] = Field(default_factory=list, repr=False)
    creditors: list[ArbitrationParty] = Field(default_factory=list, repr=False)
    debtors: list[ArbitrationParty] = Field(default_factory=list, repr=False)
    interested_persons: list[ArbitrationParty] = Field(default_factory=list, repr=False)
    third_parties: list[ArbitrationParty] = Field(default_factory=list, repr=False)
    other_parties: list[ArbitrationParty] = Field(default_factory=list, repr=False)
    party_collections_valid: bool = True
    documents: list[ArbitrationDocumentSummary] = Field(default_factory=list, repr=False)
    document_count: int = 0
    document_types: list[str] = Field(default_factory=list)
    latest_document_date: date | None = None
    kad_arbitr_link: str | None = Field(default=None, repr=False)


class RoleSummary(FrozenDomainModel):
    plaintiff_count: int = 0
    respondent_count: int = 0
    applicant_count: int = 0
    creditor_count: int = 0
    debtor_count: int = 0
    other_count: int = 0
    unknown_count: int = 0


class StatusSummary(FrozenDomainModel):
    open_count: int = 0
    completed_count: int = 0
    unknown_count: int = 0


class ResultSummary(FrozenDomainModel):
    satisfied_full_count: int = 0
    refused_count: int = 0
    returned_count: int = 0
    undefined_count: int = 0
    other_count: int = 0


class ArbitrationClaimAmounts(FrozenDomainModel):
    plaintiff: Decimal = Field(default=Decimal("0"), repr=False)
    respondent: Decimal = Field(default=Decimal("0"), repr=False)


class ArbitrationFacts(FrozenDomainModel):
    source: SourceMetadata
    total_cases: int
    returned_cases: int
    offset: int
    limit: int
    is_complete: bool
    cases: list[ArbitrationCaseFacts] = Field(default_factory=list, repr=False)
    role_summary: RoleSummary
    status_summary: StatusSummary
    result_summary: ResultSummary
    claim_amount_as_plaintiff: Decimal | None = Field(default=None, repr=False)
    claim_amount_as_respondent: Decimal | None = Field(default=None, repr=False)
    claim_amounts_by_currency: dict[str, ArbitrationClaimAmounts] = Field(
        default_factory=dict,
        repr=False,
    )
    malformed_entry_count: int = Field(default=0, ge=0)
    warnings: list[NormalizationWarning] = Field(default_factory=list)
