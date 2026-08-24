from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

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
    unit_policy: Literal["datanewton_finance_thousand_rub_v2"] = "datanewton_finance_thousand_rub_v2"
    facts: tuple[ChartFactV1, ...] = ()
    hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _facts_are_ordered(self) -> "ChartFactsV1":
        if tuple(item.key for item in self.facts) != tuple(sorted(item.key for item in self.facts)):
            raise ValueError("chart facts must have deterministic key order")
        if len({item.key for item in self.facts}) != len(self.facts):
            raise ValueError("chart facts must have unique keys")
        return self


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


class ArbitrationPageManifestV1(V2Model):
    """Safe page provenance; it deliberately contains no URL or raw content."""

    offset: int = Field(ge=0)
    limit: Literal[100] = 100
    returned_count: int = Field(ge=0, le=100)
    accepted_count: int = Field(ge=0, le=100)
    page_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _accepted_is_bounded_by_returned(self) -> "ArbitrationPageManifestV1":
        if self.accepted_count > self.returned_count:
            raise ValueError("accepted page rows cannot exceed returned rows")
        return self


class ArbitrationCollectionCountersV1(V2Model):
    pages_requested: int = Field(default=0, ge=0, le=10)
    pages_accepted: int = Field(default=0, ge=0, le=10)
    rows_observed: int = Field(default=0, ge=0, le=1000)
    rows_shape_valid: int = Field(default=0, ge=0, le=1000)
    malformed_count: int = Field(default=0, ge=0, le=1000)
    oversized_case_count: int = Field(default=0, ge=0, le=1000)
    duplicate_identical_count: int = Field(default=0, ge=0, le=1000)
    duplicate_conflict_row_count: int = Field(default=0, ge=0, le=1000)
    duplicate_conflict_key_count: int = Field(default=0, ge=0, le=1000)
    unique_case_count: int = Field(default=0, ge=0, le=1000)
    masked_natural_count: int = Field(default=0, ge=0, le=1000)
    masked_unknown_count: int = Field(default=0, ge=0, le=1000)

    @model_validator(mode="after")
    def _counter_invariants(self) -> "ArbitrationCollectionCountersV1":
        if self.pages_accepted > self.pages_requested or self.rows_shape_valid > self.rows_observed:
            raise ValueError("arbitration counters are inconsistent")
        if self.malformed_count > self.rows_observed or self.unique_case_count > self.rows_shape_valid:
            raise ValueError("arbitration counters are inconsistent")
        return self


_ARBITRATION_COMPLETION_REASONS = (
    "privacy_key_unavailable", "envelope_gate_closed", "envelope_invalid",
    "provider_error", "total_drift", "offset_drift", "duplicate_conflict",
    "oversized_case", "storage_cap_exhausted", "case_cap_exhausted",
    "max_pages_exhausted", "non_progress", "complete",
)


class ArbitrationBasisV1(V2Model):
    shape_version: str | None = Field(default=None, min_length=1, max_length=96)
    source_total: int | None = Field(default=None, ge=0)
    page_manifest: tuple[ArbitrationPageManifestV1, ...] = ()
    counters: ArbitrationCollectionCountersV1 = Field(default_factory=ArbitrationCollectionCountersV1)
    completion_reasons: tuple[Literal[
        "privacy_key_unavailable", "envelope_gate_closed", "envelope_invalid",
        "provider_error", "total_drift", "offset_drift", "duplicate_conflict",
        "oversized_case", "storage_cap_exhausted", "case_cap_exhausted",
        "max_pages_exhausted", "non_progress", "complete",
    ], ...] = ("envelope_gate_closed",)
    collection_complete: bool = False
    calendar_complete: bool = False
    calendar_scope: Literal["unverified", "all_time", "bounded_interval"] = "unverified"
    unknown_year_count: int = Field(default=0, ge=0, le=1000)
    zero_years_proven: bool = False
    mask_algorithm_version: Literal["opponent_hmac_sha256_v1"] | None = None
    mask_key_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,31}$")
    cases: tuple[PrivateArbitrationCaseV1, ...] = ()
    limitations: tuple[LimitationV1, ...] = ()

    @model_validator(mode="after")
    def _collection_metadata_is_coherent(self) -> "ArbitrationBasisV1":
        reasons = self.completion_reasons
        if not reasons or len(set(reasons)) != len(reasons):
            raise ValueError("arbitration completion reasons must be nonempty and unique")
        if tuple(sorted(reasons, key=_ARBITRATION_COMPLETION_REASONS.index)) != reasons:
            raise ValueError("arbitration completion reasons must have fixed precedence")
        if self.collection_complete != (reasons == ("complete",)):
            raise ValueError("arbitration collection completeness is inconsistent")
        if self.collection_complete and self.source_total is None:
            raise ValueError("complete arbitration collection requires source total")
        if self.calendar_scope == "unverified" and self.calendar_complete:
            raise ValueError("unverified calendar cannot be complete")
        if self.zero_years_proven and not (self.collection_complete and self.calendar_complete and self.unknown_year_count == 0):
            raise ValueError("zero years require complete collection and calendar evidence")
        if (self.mask_algorithm_version is None) != (self.mask_key_id is None):
            raise ValueError("arbitration mask metadata must be paired")
        if self.counters.unique_case_count != len(self.cases):
            raise ValueError("arbitration unique case count must match cases")
        if len(self.page_manifest) != self.counters.pages_accepted:
            raise ValueError("arbitration page manifest must match accepted pages")
        return self


class CompanyCardV2SnapshotV1(V2Model):
    report_version: Literal["3"] = "3"
    writer_profile: Literal["company_card_v2_writer_v3"] = "company_card_v2_writer_v3"
    presentation_contract: Literal["company_public_h2_v1"] = "company_public_h2_v1"
    # This is the complete immutable H2 writer decision.  It intentionally
    # mirrors the decision persisted with the report/job without importing the
    # persistence layer into the pure Company Card domain.
    rollout_config_generation: int = Field(gt=0)
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

    @field_validator("generated_at", mode="before")
    @classmethod
    def _require_utc_z_wire_timestamp(cls, value: object) -> object:
        # A stored snapshot is a wire artifact.  Do not silently accept an
        # offset-equivalent spelling such as ``+00:00`` and then rewrite it
        # when hashing/serializing the snapshot.
        if isinstance(value, str) and not value.endswith("Z"):
            raise ValueError("snapshot generated_at must use UTC Z notation")
        return value

    @model_validator(mode="after")
    def _same_subject(self) -> "CompanyCardV2SnapshotV1":
        if not (self.subject_inn == self.target_inn == self.counterparty.inn):
            raise ValueError("snapshot subject, target and counterparty INN must match")
        try:
            parsed_report_id = UUID(self.report_id)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("snapshot report_id must be a canonical UUID") from exc
        if str(parsed_report_id) != self.report_id:
            raise ValueError("snapshot report_id must be a canonical UUID")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() != timedelta(0):
            raise ValueError("snapshot generated_at must be UTC")
        if self.finance_basis.unit_policy != "datanewton_finance_thousand_rub_v2" or self.chart_facts.unit_policy != self.finance_basis.unit_policy:
            raise ValueError("snapshot finance policy identity is invalid")
        # Chart Facts are an immutable derivative of the exact finance basis.
        # Recompute at the model boundary so a stale/mutated hash cannot enter
        # a snapshot, pin or public projection later in the lifecycle.
        from .finance import build_chart_facts

        if self.chart_facts != build_chart_facts(self.finance_basis):
            raise ValueError("snapshot chart facts do not match finance basis")
        return self


class NarrativeEvidenceV1(V2Model):
    """Only the one approved primary-activity fact may enter a v2 snapshot."""
    schema_version: Literal["company_card_v2_narrative_evidence_v1"] = "company_card_v2_narrative_evidence_v1"
    primary_activity_parser_version: Literal["company_card_v2_primary_activity_parser_v1"] = "company_card_v2_primary_activity_parser_v1"
    primary_activity_evidence_version: Literal["company_card_v2_okved_primary_activity_evidence_v1"] = "company_card_v2_okved_primary_activity_evidence_v1"
    source_profile_version: Literal["company_card_v2_counterparty_okved_primary_v1"] = "company_card_v2_counterparty_okved_primary_v1"
    primary_activity: "PrimaryActivitySnapshotV1 | None" = None
    limitation_code: Literal["primary_activity_not_admitted"] | None = None

    @model_validator(mode="after")
    def _closed_shape(self) -> "NarrativeEvidenceV1":
        if (self.primary_activity is None) == (self.limitation_code is None):
            raise ValueError("narrative evidence must contain exactly one result")
        return self


class PrimaryActivitySnapshotV1(V2Model):
    code: str = Field(pattern=r"^[0-9]{2}(?:\.[0-9]{1,2}){0,2}$", min_length=2, max_length=8)
    label: str = Field(min_length=1, max_length=128)
    is_primary: Literal[True] = True

    @field_validator("label")
    @classmethod
    def _admitted_label_is_normalized(cls, value: str) -> str:
        import unicodedata
        if value != " ".join(unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n").split()):
            raise ValueError("primary activity label must be normalized")
        if len(value.encode("utf-8")) > 512 or any(ord(c) == 0 or 0xD800 <= ord(c) <= 0xDFFF or 0x202A <= ord(c) <= 0x202E or (ord(c) < 32 and c not in "\t\n\r") or 0x7F <= ord(c) <= 0x9F for c in value):
            raise ValueError("primary activity label is unsafe")
        return value


class CompanyCardV2SnapshotV2(CompanyCardV2SnapshotV1):
    snapshot_schema_version: Literal["company_card_v2_snapshot_v2"] = "company_card_v2_snapshot_v2"
    narrative_evidence: NarrativeEvidenceV1


# Backward compatible import name for callers that construct the frozen v1
# shape.  Parsers below explicitly dispatch V1/V2 and never infer a shape.
CompanyCardV2Snapshot = CompanyCardV2SnapshotV1


__all__ = [
    "ArbitrationBasisV1", "ArbitrationCollectionCountersV1", "ArbitrationPageManifestV1",
    "ChartFactV1", "ChartFactsV1", "CompanyCardCounterpartyCoreV1",
    "CompanyCardV2Snapshot", "CompanyCardV2SnapshotV1", "CompanyCardV2SnapshotV2",
    "NarrativeEvidenceV1", "PrimaryActivitySnapshotV1", "FinanceBasisV1", "FinanceCellV1", "InternalCaseIdentityV1",
    "LimitationV1", "PrivateArbitrationCaseV1", "PrivateOpponentTokenV1",
]
