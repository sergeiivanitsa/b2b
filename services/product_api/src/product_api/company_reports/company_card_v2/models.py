from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from product_api.company_reports.models import FrozenDomainModel


class V2Model(FrozenDomainModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LimitationV1(V2Model):
    code: str = Field(min_length=1, max_length=96)
    field: str = Field(min_length=1, max_length=160)


class CompanyCardCounterpartyCoreV1(V2Model):
    inn: str = Field(pattern=r"^[0-9]{10}$|^[0-9]{12}$")
    ogrn: str | None = Field(default=None, pattern=r"^[0-9]{13}$|^[0-9]{15}$")
    kpp: str | None = Field(default=None, pattern=r"^[0-9]{9}$")
    short_name: str | None = Field(default=None, max_length=512)
    full_name: str | None = Field(default=None, max_length=1024)
    registration_date: date | None = None
    dissolution_date: date | None = None
    address: str | None = Field(default=None, max_length=2048)
    address_inaccuracy: bool | None = None


class FinanceCellV1(V2Model):
    form: str
    code: str
    year: int
    state: Literal["available_nonzero", "zero_unverified", "missing", "conflict", "decimal_transport_lossy", "invalid"]
    value: Decimal | None = None

    @model_validator(mode="after")
    def _numeric_only_for_nonzero(self) -> "FinanceCellV1":
        if self.state == "available_nonzero":
            if self.value is None or self.value == 0:
                raise ValueError("available_nonzero requires a nonzero value")
        elif self.value is not None:
            raise ValueError("non-numeric finance states must not own a value")
        return self


class FinanceBasisV1(V2Model):
    unit_policy: Literal["datanewton_finance_thousand_rub_v2"] = "datanewton_finance_thousand_rub_v2"
    cells: tuple[FinanceCellV1, ...] = ()


class ChartFactV1(V2Model):
    key: str
    value: Decimal | None = None
    geometry: Decimal | None = None
    limitation_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _no_zero_geometry(self) -> "ChartFactV1":
        if self.geometry is not None and not self.geometry.is_finite():
            raise ValueError("chart geometry must be finite")
        return self


class ChartFactsV1(V2Model):
    version: Literal["company_card_chart_facts_v1"] = "company_card_chart_facts_v1"
    facts: tuple[ChartFactV1, ...] = ()
    hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class InternalCaseIdentityV1(V2Model):
    source_kind: Literal["case_id", "id"]
    value: str = Field(min_length=1, max_length=256)


class PrivateOpponentTokenV1(V2Model):
    algorithm_version: Literal["hmac_sha256_v1"] = "hmac_sha256_v1"
    key_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    value: str = Field(pattern=r"^[0-9a-f]{64}$")


class PrivateArbitrationCaseV1(V2Model):
    identity: InternalCaseIdentityV1
    roles: tuple[str, ...] = ()
    started_at: date | None = None
    updated_at: date | None = None
    opponent: PrivateOpponentTokenV1 | None = None
    amount: Decimal | None = None


class ArbitrationBasisV1(V2Model):
    cases: tuple[PrivateArbitrationCaseV1, ...] = ()
    limitations: tuple[LimitationV1, ...] = ()


class CompanyCardV2Snapshot(V2Model):
    report_version: Literal["3"] = "3"
    writer_profile: Literal["company_card_v2_writer_v3"] = "company_card_v2_writer_v3"
    presentation_contract: Literal["company_public_h2_v1"] = "company_public_h2_v1"
    report_id: str
    subject_inn: str = Field(pattern=r"^[0-9]{10}$|^[0-9]{12}$")
    target_inn: str = Field(pattern=r"^[0-9]{10}$|^[0-9]{12}$")
    generated_at: datetime
    counterparty: CompanyCardCounterpartyCoreV1
    finance_basis: FinanceBasisV1
    arbitration_basis: ArbitrationBasisV1
    chart_facts: ChartFactsV1
    evidence_version: str = Field(min_length=1, max_length=96)
    privacy_version: str = Field(min_length=1, max_length=96)
    limitations: tuple[LimitationV1, ...] = ()

    @model_validator(mode="after")
    def _same_subject(self) -> "CompanyCardV2Snapshot":
        if not (self.subject_inn == self.target_inn == self.counterparty.inn):
            raise ValueError("snapshot subject, target and counterparty INN must match")
        return self


__all__ = [
    "ArbitrationBasisV1", "ChartFactV1", "ChartFactsV1", "CompanyCardCounterpartyCoreV1",
    "CompanyCardV2Snapshot", "FinanceBasisV1", "FinanceCellV1", "InternalCaseIdentityV1",
    "LimitationV1", "PrivateArbitrationCaseV1", "PrivateOpponentTokenV1",
]
