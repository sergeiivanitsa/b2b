from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
import re
from typing import Annotated, Literal, TypeAlias
import unicodedata
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


# Iteration 24 is intentionally additive.  These V2 arbitration models do not
# widen or reinterpret any of the frozen V1 arbitration/snapshot classes above.
StrictZeroOrOne: TypeAlias = Annotated[int, Field(strict=True, ge=0, le=1)]
StrictCount1000: TypeAlias = Annotated[int, Field(strict=True, ge=0, le=1000)]
StrictConflictKeyCount: TypeAlias = Annotated[int, Field(strict=True, ge=0, le=500)]
StrictOpponentTokenCount: TypeAlias = Annotated[int, Field(strict=True, ge=0, le=20_000_000)]
StrictOpponentGroupCount: TypeAlias = Annotated[int, Field(strict=True, ge=0, le=20_000)]
StrictOpponentProbeCount: TypeAlias = Annotated[int, Field(strict=True, ge=0, le=20_001)]
StrictSignedInt64: TypeAlias = Annotated[int, Field(strict=True, ge=0, le=9_223_372_036_854_775_807)]
StrictBoolean: TypeAlias = Annotated[bool, Field(strict=True)]

ArbitrationCompletionReasonV2: TypeAlias = Literal[
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
]

ArbitrationLimitationCodeV2: TypeAlias = Literal[
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
]

ARBITRATION_COMPLETION_PRECEDENCE_V2: tuple[str, ...] = (
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

ARBITRATION_LIMITATION_PRECEDENCE_V2: tuple[str, ...] = (
    *ARBITRATION_COMPLETION_PRECEDENCE_V2[:-1],
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
ARBITRATION_CASE_LIMITATION_CODES_V2 = frozenset(
    ARBITRATION_LIMITATION_PRECEDENCE_V2[
        ARBITRATION_LIMITATION_PRECEDENCE_V2.index("arbitration_unknown_year"):
    ]
)

_FIRST_NUMBER_V2 = re.compile(r"(?:(?:А|A)[0-9]{1,3}|СИП)-[0-9]{1,12}/[0-9]{4}$")


def _is_safe_case_id_v2(value: str) -> bool:
    unsafe_scalar = any(
        ord(char) <= 0x1F
        or 0x7F <= ord(char) <= 0x9F
        or 0xD800 <= ord(char) <= 0xDFFF
        or 0x202A <= ord(char) <= 0x202E
        or 0x2066 <= ord(char) <= 0x2069
        for char in value
    )
    return (
        value == unicodedata.normalize("NFC", value)
        and 1 <= len(value) <= 256
        and not unsafe_scalar
        and len(value.encode("utf-8")) <= 1024
        and value == value.strip()
    )


class ArbitrationBasisLimitationV2(V2Model):
    code: ArbitrationLimitationCodeV2


class ArbitrationPageManifestV2(V2Model):
    offset: Literal[0] = 0
    limit: Literal[1000] = 1000
    returned_count: StrictCount1000
    accepted_count: StrictCount1000
    response_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("offset", "limit", mode="before")
    @classmethod
    def _strict_fixed_integers(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("arbitration page offset/limit must be exact integers")
        return value

    @model_validator(mode="after")
    def _accepted_does_not_exceed_returned(self) -> "ArbitrationPageManifestV2":
        if self.accepted_count > self.returned_count:
            raise ValueError("accepted arbitration rows exceed returned rows")
        return self


class ArbitrationCollectionCountersV2(V2Model):
    pages_requested: StrictZeroOrOne = 0
    pages_accepted: StrictZeroOrOne = 0
    rows_observed: StrictCount1000 = 0
    rows_processed: StrictCount1000 = 0
    rows_shape_valid: StrictCount1000 = 0
    malformed_count: StrictCount1000 = 0
    oversized_case_count: StrictZeroOrOne = 0
    storage_cap_rejected_count: StrictZeroOrOne = 0
    duplicate_identical_count: StrictCount1000 = 0
    duplicate_conflict_row_count: StrictCount1000 = 0
    duplicate_conflict_key_count: StrictConflictKeyCount = 0
    unique_case_count: StrictCount1000 = 0
    opponent_token_count: StrictOpponentTokenCount = 0
    opponent_group_count: StrictOpponentGroupCount = 0
    opponent_group_probe_count: StrictOpponentProbeCount = 0

    @model_validator(mode="after")
    def _closed_counter_invariants(self) -> "ArbitrationCollectionCountersV2":
        if self.pages_accepted > self.pages_requested:
            raise ValueError("accepted pages exceed requested pages")
        row_fields = (
            self.rows_observed,
            self.rows_processed,
            self.rows_shape_valid,
            self.malformed_count,
            self.oversized_case_count,
            self.storage_cap_rejected_count,
            self.duplicate_identical_count,
            self.duplicate_conflict_row_count,
            self.unique_case_count,
        )
        if self.pages_accepted == 0 and any(row_fields) or self.pages_accepted == 0 and any((self.opponent_token_count, self.opponent_group_count, self.opponent_group_probe_count)):
            raise ValueError("unaccepted arbitration page cannot own row counters")
        if self.pages_accepted == 1:
            if self.rows_processed > self.rows_observed:
                raise ValueError("processed rows exceed observed rows")
            if self.malformed_count != self.rows_processed - self.rows_shape_valid:
                raise ValueError("malformed arbitration counter is inconsistent")
            if self.rows_shape_valid != (
                self.unique_case_count
                + self.duplicate_identical_count
                + self.duplicate_conflict_row_count
                + self.oversized_case_count
                + self.storage_cap_rejected_count
            ):
                raise ValueError("arbitration row classification does not conserve rows")
        if self.duplicate_conflict_row_count < 2 * self.duplicate_conflict_key_count:
            raise ValueError("conflicting arbitration keys require at least two rows")
        if (self.duplicate_conflict_row_count == 0) != (self.duplicate_conflict_key_count == 0):
            raise ValueError("arbitration conflict row/key zero states must be paired")
        if self.oversized_case_count + self.storage_cap_rejected_count > 1:
            raise ValueError("only one arbitration storage boundary may stop collection")
        if self.rows_processed < self.rows_observed and self.oversized_case_count + self.storage_cap_rejected_count != 1:
            raise ValueError("short arbitration prefix requires one storage boundary")
        if self.opponent_group_probe_count == 20_001:
            if self.opponent_token_count or self.opponent_group_count:
                raise ValueError("opponent overflow must atomically scrub retained tokens")
        else:
            if self.opponent_group_probe_count != self.opponent_group_count:
                raise ValueError("opponent probe and retained group counts must match")
            if self.opponent_group_count > self.opponent_token_count or ((self.opponent_group_count == 0) != (self.opponent_token_count == 0)):
                raise ValueError("retained opponent token/group counts are inconsistent")
        return self


class PrivateOpponentTokenV2(V2Model):
    algorithm_version: Literal["opponent_hmac_sha256_v1"] = "opponent_hmac_sha256_v1"
    key_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    value: str = Field(pattern=r"^[0-9a-f]{64}$")


class SanitizedArbitrationCaseV2(V2Model):
    case_id: str
    first_number: str | None = None
    year: Annotated[int, Field(strict=True, ge=1900, le=2100)] | None = None
    role: Literal["plaintiff", "respondent", "other", "unattributed"]
    outcome: Literal["won", "lost", "returned", "unknown"]
    date_start: date | None = None
    date_update: date | None = None
    duration_days: Annotated[int, Field(strict=True, ge=0)] | None = None
    amount_state: Literal["available", "missing", "invalid"]
    amount: Decimal | None = None
    currency_state: Literal["rub", "missing", "unidentified", "invalid"]
    opponent_tokens: tuple[PrivateOpponentTokenV2, ...] = ()
    limitations: tuple[ArbitrationLimitationCodeV2, ...] = ()

    @field_validator("case_id")
    @classmethod
    def _safe_private_case_key(cls, value: str) -> str:
        if not _is_safe_case_id_v2(value):
            raise ValueError("case_id is outside the closed arbitration identity grammar")
        return value

    @field_validator("first_number")
    @classmethod
    def _safe_display_number(cls, value: str | None) -> str | None:
        if value is not None:
            if any(0xD800 <= ord(char) <= 0xDFFF for char in value) or (
                value != unicodedata.normalize("NFC", value)
                or value != value.strip()
                or len(value) > 22
                or len(value.encode("utf-8")) > 32
                or _FIRST_NUMBER_V2.fullmatch(value) is None
            ):
                raise ValueError("first_number is outside the closed display grammar")
        return value

    @field_validator("amount", mode="before")
    @classmethod
    def _exact_decimal_only(cls, value: object) -> object:
        if isinstance(value, str):
            from .decimal_transport import DecimalTransportError, parse_source_decimal

            try:
                parsed = parse_source_decimal(value)
            except DecimalTransportError as exc:
                raise ValueError("arbitration amount wire decimal is invalid") from exc
            if parsed.lexeme != value:
                raise ValueError("arbitration amount wire decimal is not canonical")
            value = parsed.value
        if value is not None and not isinstance(value, Decimal):
            raise ValueError("arbitration amount must be an exact Decimal or canonical wire decimal")
        if isinstance(value, Decimal) and not value.is_finite():
            raise ValueError("arbitration amount must be finite")
        if isinstance(value, Decimal):
            from .decimal_transport import parse_source_decimal

            value = Decimal(parse_source_decimal(value).lexeme)
        return value

    @field_validator("date_start", "date_update", mode="before")
    @classmethod
    def _strict_iso_wire_date(cls, value: object) -> object:
        if value is None or type(value) is date:
            return value
        if not isinstance(value, str):
            raise ValueError("arbitration dates must be exact ISO dates")
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("arbitration date is invalid") from exc
        if parsed.isoformat() != value:
            raise ValueError("arbitration date is not canonical ISO")
        return parsed

    @model_validator(mode="after")
    def _closed_case_pairings(self) -> "SanitizedArbitrationCaseV2":
        if self.year is not None and self.date_start is not None and self.year != self.date_start.year:
            raise ValueError("verified arbitration year disagrees with start date")
        expected_duration = (
            (self.date_update - self.date_start).days
            if self.date_start is not None and self.date_update is not None and self.date_update >= self.date_start
            else None
        )
        if self.duration_days != expected_duration:
            raise ValueError("arbitration duration is not the exact safe date delta")
        limitation_set = set(self.limitations)
        if limitation_set - ARBITRATION_CASE_LIMITATION_CODES_V2:
            raise ValueError("arbitration case owns a non-case limitation")
        first_number_codes = limitation_set & {
            "arbitration_first_number_unavailable",
            "arbitration_first_number_identity_collision",
        }
        if (self.first_number is None and len(first_number_codes) != 1) or (self.first_number is not None and first_number_codes):
            raise ValueError("arbitration first-number value/limitation pairing is invalid")
        has_unknown_year = "arbitration_unknown_year" in limitation_set
        if (self.year is None) != has_unknown_year:
            raise ValueError("arbitration year value/limitation pairing is invalid")
        if "arbitration_year_conflict" in limitation_set and self.year is not None:
            raise ValueError("conflicting arbitration year must be unavailable")
        has_inversion = "arbitration_date_inversion" in limitation_set
        actual_inversion = self.date_start is not None and self.date_update is not None and self.date_update < self.date_start
        if has_inversion != actual_inversion:
            raise ValueError("arbitration date inversion limitation is inconsistent")
        if (
            "arbitration_date_invalid" in limitation_set
            and self.date_start is not None
            and self.date_update is not None
        ):
            raise ValueError("arbitration invalid-date limitation lacks a missing date")
        if (
            "arbitration_year_conflict" in limitation_set
            and self.date_start is None
        ):
            raise ValueError("arbitration year-conflict limitation lacks a start date")
        amount_codes = limitation_set & {"arbitration_amount_missing", "arbitration_amount_invalid"}
        expected_amount_code = None if self.amount_state == "available" else f"arbitration_amount_{self.amount_state}"
        if (self.amount_state == "available") != (self.amount is not None) or amount_codes != ({expected_amount_code} if expected_amount_code else set()):
            raise ValueError("arbitration amount state/value/limitation pairing is invalid")
        currency_codes = limitation_set & {
            "arbitration_currency_missing",
            "arbitration_currency_unidentified",
            "arbitration_currency_invalid",
        }
        expected_currency_code = None if self.currency_state == "rub" else f"arbitration_currency_{self.currency_state}"
        if currency_codes != ({expected_currency_code} if expected_currency_code else set()):
            raise ValueError("arbitration currency state/limitation pairing is invalid")
        if len(limitation_set) != len(self.limitations) or tuple(sorted(self.limitations, key=ARBITRATION_LIMITATION_PRECEDENCE_V2.index)) != self.limitations:
            raise ValueError("arbitration case limitations must be ordered and unique")
        token_keys = tuple((token.value, token.algorithm_version, token.key_id) for token in self.opponent_tokens)
        if token_keys != tuple(sorted(set(token_keys))):
            raise ValueError("arbitration opponent tokens must be ordered and unique")
        if self.role in {"other", "unattributed"} and (
            self.outcome != "unknown" or self.opponent_tokens
        ):
            raise ValueError(
                "non-party arbitration role cannot carry outcome or opponent facts"
            )
        return self


class ArbitrationBasisV2(V2Model):
    basis_version: Literal["company_card_arbitration_basis_v2"] = "company_card_arbitration_basis_v2"
    normalization_version: Literal["company_card_arbitration_normalization_v2"] = "company_card_arbitration_normalization_v2"
    registry_version: Literal["datanewton_arbitration_registry_v2"] = "datanewton_arbitration_registry_v2"
    contract_binding: Literal["datanewton_arbitration_openapi_v1_2026_08_26"] = "datanewton_arbitration_openapi_v1_2026_08_26"
    openapi_sha256: Literal["2c3d34ab00a35e58e07f7c3dea32b605b9e61d112a92a1654fd54e415ef851d2"] = "2c3d34ab00a35e58e07f7c3dea32b605b9e61d112a92a1654fd54e415ef851d2"
    runtime_dataset: Literal["arbitration_cases"] = "arbitration_cases"
    endpoint: Literal["GET /v1/arbitration-cases"] = "GET /v1/arbitration-cases"
    identity_policy: Literal["arbitration_case_identity_case_id_only_v1"] = "arbitration_case_identity_case_id_only_v1"
    target_policy: Literal["arbitration_target_exact_inn_v1"] = "arbitration_target_exact_inn_v1"
    collection_policy: Literal["datanewton_arbitration_single_page_1000_v1"] = "datanewton_arbitration_single_page_1000_v1"
    storage_budget_policy: Literal["arbitration_basis_metadata_reserve_v1"] = "arbitration_basis_metadata_reserve_v1"
    outcome_policy: Literal["arbitration_party_result_narrow_v1"] = "arbitration_party_result_narrow_v1"
    currency_policy: Literal["arbitration_rubles_only_v1"] = "arbitration_rubles_only_v1"
    privacy_policy: Literal["arbitration_opponents_all_masked_v1"] = "arbitration_opponents_all_masked_v1"
    source_total: StrictSignedInt64 | None = None
    page_manifest: tuple[ArbitrationPageManifestV2, ...] = ()
    provider_received_at: datetime | None = None
    counters: ArbitrationCollectionCountersV2 = Field(default_factory=ArbitrationCollectionCountersV2)
    completion_reasons: tuple[ArbitrationCompletionReasonV2, ...]
    collection_complete: StrictBoolean = False
    calendar_complete: Literal[False] = False
    calendar_scope: Literal["unverified"] = "unverified"
    unknown_year_count: StrictCount1000 = 0
    zero_years_proven: Literal[False] = False
    mask_algorithm_version: Literal["opponent_hmac_sha256_v1"] | None = None
    mask_key_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,31}$")
    sanitized_cases: tuple[SanitizedArbitrationCaseV2, ...] = ()
    limitations: tuple[ArbitrationBasisLimitationV2, ...] = ()

    @field_validator("provider_received_at", mode="before")
    @classmethod
    def _bound_receipt_uses_z(cls, value: object) -> object:
        if value is not None:
            if not isinstance(value, (str, datetime)):
                raise ValueError("arbitration provider_received_at must be an exact timestamp")
            if isinstance(value, str) and not value.endswith("Z"):
                raise ValueError("arbitration provider_received_at must use UTC Z notation")
        return value

    @field_validator("calendar_complete", "zero_years_proven", mode="before")
    @classmethod
    def _strict_fixed_false(cls, value: object) -> object:
        if type(value) is not bool or value:
            raise ValueError("arbitration calendar booleans are fixed false")
        return value

    @model_validator(mode="after")
    def _closed_basis_invariants(self) -> "ArbitrationBasisV2":
        if not self.completion_reasons or len(set(self.completion_reasons)) != len(self.completion_reasons):
            raise ValueError("arbitration completion reasons must be nonempty and unique")
        if tuple(sorted(self.completion_reasons, key=ARBITRATION_COMPLETION_PRECEDENCE_V2.index)) != self.completion_reasons:
            raise ValueError("arbitration completion reasons have invalid precedence")
        if self.collection_complete != (self.completion_reasons == ("complete",)):
            raise ValueError("arbitration collection completeness is inconsistent")
        if self.provider_received_at is not None and (
            self.provider_received_at.tzinfo is None or self.provider_received_at.utcoffset() != timedelta(0)
        ):
            raise ValueError("arbitration provider receipt must be UTC")
        if self.counters.pages_accepted == 0:
            if self.source_total is not None or self.page_manifest:
                raise ValueError("unaccepted arbitration result cannot own source metadata")
            if len(self.completion_reasons) != 1 or self.completion_reasons[0] not in {
                "operation_gate_closed",
                "evidence_gate_closed",
                "privacy_key_unavailable",
                "provider_error",
                "provider_binding_invalid",
                "lexical_transport_invalid",
                "envelope_invalid",
            }:
                raise ValueError("unaccepted arbitration result has an invalid lifecycle reason")
        else:
            if self.source_total is None or len(self.page_manifest) != 1:
                raise ValueError("accepted arbitration page requires exact source metadata")
            if any(reason in {
                "operation_gate_closed", "evidence_gate_closed", "privacy_key_unavailable",
                "provider_error", "provider_binding_invalid", "lexical_transport_invalid", "envelope_invalid",
            } for reason in self.completion_reasons):
                raise ValueError("accepted arbitration page cannot own a pre-result reason")
            manifest = self.page_manifest[0]
            if manifest.returned_count != self.counters.rows_observed or manifest.accepted_count != self.counters.unique_case_count:
                raise ValueError("arbitration manifest does not match exact counters")
            if self.source_total <= 1000:
                if self.counters.rows_observed != self.source_total:
                    raise ValueError("bounded arbitration population must equal returned rows")
            elif self.counters.rows_observed == 0:
                raise ValueError("capped arbitration population requires a nonempty returned slice")
        if self.counters.unique_case_count != len(self.sanitized_cases):
            raise ValueError("arbitration unique case counter must match retained cases")
        if self.unknown_year_count != sum(case.year is None for case in self.sanitized_cases):
            raise ValueError("arbitration unknown-year counter must match cases")
        case_keys = tuple(case.case_id for case in self.sanitized_cases)
        case_key_set = set(case_keys)
        if case_keys != tuple(sorted(case_keys)) or len(case_key_set) != len(case_keys):
            raise ValueError("sanitized arbitration cases must be ordered and unique")
        if any(
            case.first_number is not None and case.first_number in case_key_set
            for case in self.sanitized_cases
        ):
            raise ValueError(
                "arbitration first-number identity collision must be suppressed"
            )
        if (self.mask_algorithm_version is None) != (self.mask_key_id is None):
            raise ValueError("arbitration mask metadata must be paired")
        first_reason = self.completion_reasons[0]
        zero_call_reasons = {"operation_gate_closed", "evidence_gate_closed", "privacy_key_unavailable"}
        bound_receipt_reasons = {"lexical_transport_invalid", "envelope_invalid"}
        if first_reason in zero_call_reasons:
            if self.counters.pages_requested != 0 or self.mask_key_id is not None or self.provider_received_at is not None:
                raise ValueError("arbitration preflight lifecycle metadata is inconsistent")
        else:
            if self.counters.pages_requested != 1 or self.mask_key_id is None:
                raise ValueError("attempted arbitration lifecycle requires resolved key metadata")
        if first_reason in bound_receipt_reasons or self.counters.pages_accepted == 1:
            if self.provider_received_at is None:
                raise ValueError("bound arbitration result requires provider receipt time")
        elif self.provider_received_at is not None:
            raise ValueError("unbound arbitration result cannot own provider receipt time")
        tokens = tuple(token for case in self.sanitized_cases for token in case.opponent_tokens)
        if self.mask_key_id is None and tokens:
            raise ValueError("arbitration tokens require resolved mask metadata")
        if any(token.algorithm_version != self.mask_algorithm_version or token.key_id != self.mask_key_id for token in tokens):
            raise ValueError("arbitration tokens must bind the effective basis key")
        if self.counters.opponent_token_count != len(tokens) or self.counters.opponent_group_count != len({token.value for token in tokens}):
            raise ValueError("arbitration opponent counters must match retained tokens")
        limitation_codes = tuple(item.code for item in self.limitations)
        if len(set(limitation_codes)) != len(limitation_codes) or tuple(sorted(limitation_codes, key=ARBITRATION_LIMITATION_PRECEDENCE_V2.index)) != limitation_codes:
            raise ValueError("arbitration basis limitations must be ordered and unique")
        limitation_set = set(limitation_codes)
        if "arbitration_calendar_unverified" not in limitation_set:
            raise ValueError("arbitration basis requires the fixed calendar limitation")
        if any(reason != "complete" and reason not in limitation_set for reason in self.completion_reasons):
            raise ValueError("arbitration completion reasons must be represented as limitations")
        if any(set(case.limitations) - limitation_set for case in self.sanitized_cases):
            raise ValueError("arbitration basis must cover every retained case limitation")
        expected_limitations = {
            "arbitration_calendar_unverified",
            *(reason for reason in self.completion_reasons if reason != "complete"),
            *(code for case in self.sanitized_cases for code in case.limitations),
        }
        if limitation_set != expected_limitations:
            raise ValueError("arbitration basis limitations are not the exact derived set")
        identity_population_fully_retained = (
            self.counters.rows_processed == self.counters.rows_observed
            and self.counters.malformed_count == 0
            and self.counters.oversized_case_count == 0
            and self.counters.storage_cap_rejected_count == 0
            and self.counters.duplicate_conflict_row_count == 0
            and self.counters.rows_observed
            == self.counters.unique_case_count
            + self.counters.duplicate_identical_count
        )
        if (
            identity_population_fully_retained
            and "arbitration_first_number_identity_collision" in limitation_set
            and not any(
                _FIRST_NUMBER_V2.fullmatch(case.case_id) is not None
                for case in self.sanitized_cases
            )
        ):
            raise ValueError(
                "arbitration identity-collision limitation lacks a case-id witness"
            )
        if (self.unknown_year_count > 0) != ("arbitration_unknown_year" in limitation_set):
            raise ValueError("arbitration unknown-year limitation is inconsistent")
        reason_flags = {
            "malformed_rows": self.counters.malformed_count > 0,
            "duplicate_conflict": self.counters.duplicate_conflict_key_count > 0,
            "oversized_case": self.counters.oversized_case_count == 1,
            "storage_cap_exhausted": self.counters.storage_cap_rejected_count == 1,
            "opponent_group_cap_exhausted": self.counters.opponent_group_probe_count == 20_001,
            "source_total_exceeds_cap": self.source_total is not None and self.source_total > 1000,
        }
        if any((reason in self.completion_reasons) != active for reason, active in reason_flags.items()):
            raise ValueError("arbitration completion reasons do not match exact counters")
        from .canonical_json import canonical_json_bytes

        if len(canonical_json_bytes(self.model_dump(mode="json"))) > 8_388_608:
            raise ValueError("arbitration basis exceeds the CJSON storage cap")
        return self


class ArbitrationNamedCountV1(V2Model):
    key: Literal["plaintiff", "respondent", "other", "unattributed", "won", "lost", "returned", "unknown"]
    count: StrictCount1000


class ArbitrationYearRoleFactV1(V2Model):
    year: Annotated[int, Field(strict=True, ge=1900, le=2100)]
    plaintiff: StrictCount1000 = 0
    respondent: StrictCount1000 = 0
    other: StrictCount1000 = 0
    unattributed: StrictCount1000 = 0


class ArbitrationChartFactsV1(V2Model):
    version: Literal["company_card_arbitration_chart_facts_v1"] = "company_card_arbitration_chart_facts_v1"
    collection_state: Literal["gate_closed", "failed", "partial", "complete"]
    source_total: StrictSignedInt64 | None = None
    rows_observed: StrictCount1000 | None = None
    unique_case_count: StrictCount1000 | None = None
    unknown_year_count: StrictCount1000 | None = None
    role_counts: tuple[ArbitrationNamedCountV1, ...] = ()
    outcome_counts: tuple[ArbitrationNamedCountV1, ...] = ()
    year_role_facts: tuple[ArbitrationYearRoleFactV1, ...] = ()
    rub_amount_case_count: StrictCount1000 | None = None
    opponent_group_count: StrictOpponentGroupCount | None = None
    cases_without_safe_opponent: StrictCount1000 | None = None
    multi_opponent_case_count: StrictCount1000 | None = None
    limitation_codes: tuple[ArbitrationLimitationCodeV2, ...] = ()

    @model_validator(mode="after")
    def _facts_are_closed(self) -> "ArbitrationChartFactsV1":
        core_aggregate_scalars = (
            self.rows_observed,
            self.unique_case_count,
            self.unknown_year_count,
            self.rub_amount_case_count,
        )
        opponent_aggregate_scalars = (
            self.opponent_group_count,
            self.cases_without_safe_opponent,
            self.multi_opponent_case_count,
        )
        if self.collection_state in {"gate_closed", "failed"}:
            if self.source_total is not None or any(value is not None for value in (*core_aggregate_scalars, *opponent_aggregate_scalars)) or self.role_counts or self.outcome_counts or self.year_role_facts:
                raise ValueError("failed arbitration facts cannot own aggregates")
        elif self.source_total is None or any(value is None for value in core_aggregate_scalars):
            raise ValueError("admitted arbitration facts require exact aggregate counts")
        opponent_failed = "opponent_group_cap_exhausted" in self.limitation_codes
        if self.collection_state in {"partial", "complete"} and (
            opponent_failed != all(value is None for value in opponent_aggregate_scalars)
            or (not opponent_failed and any(value is None for value in opponent_aggregate_scalars))
        ):
            raise ValueError("arbitration opponent facts do not match the privacy-cap state")
        role_order = ("plaintiff", "respondent", "other", "unattributed")
        outcome_order = ("won", "lost", "returned", "unknown")
        if self.collection_state in {"partial", "complete"}:
            if tuple(item.key for item in self.role_counts) != role_order or tuple(item.key for item in self.outcome_counts) != outcome_order:
                raise ValueError("arbitration aggregate facts use a fixed key order")
            if sum(item.count for item in self.role_counts) != self.unique_case_count or sum(item.count for item in self.outcome_counts) != self.unique_case_count:
                raise ValueError("arbitration aggregate facts do not conserve cases")
            years = tuple(item.year for item in self.year_role_facts)
            if years != tuple(sorted(set(years))):
                raise ValueError("arbitration year facts must be ordered and unique")
        if len(set(self.limitation_codes)) != len(self.limitation_codes) or tuple(sorted(self.limitation_codes, key=ARBITRATION_LIMITATION_PRECEDENCE_V2.index)) != self.limitation_codes:
            raise ValueError("arbitration fact limitations must be ordered and unique")
        return self


class CompanyCardV2SnapshotV3(CompanyCardV2SnapshotV2):
    snapshot_schema_version: Literal["company_card_v2_snapshot_v3"] = "company_card_v2_snapshot_v3"
    arbitration_basis: ArbitrationBasisV2
    arbitration_chart_facts: ArbitrationChartFactsV1
    arbitration_chart_facts_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _arbitration_derivative_is_exact(self) -> "CompanyCardV2SnapshotV3":
        from .arbitration_v2 import build_arbitration_chart_facts, arbitration_chart_facts_hash

        expected = build_arbitration_chart_facts(self.arbitration_basis)
        if self.arbitration_chart_facts != expected:
            raise ValueError("snapshot arbitration facts do not match arbitration basis")
        if self.arbitration_chart_facts_hash != arbitration_chart_facts_hash(expected):
            raise ValueError("snapshot arbitration facts hash is invalid")
        return self


# Backward compatible import name for callers that construct the frozen v1
# shape.  Parsers below explicitly dispatch V1/V2 and never infer a shape.
CompanyCardV2Snapshot = CompanyCardV2SnapshotV1


__all__ = [
    "ArbitrationBasisV1", "ArbitrationCollectionCountersV1", "ArbitrationPageManifestV1",
    "ChartFactV1", "ChartFactsV1", "CompanyCardCounterpartyCoreV1",
    "CompanyCardV2Snapshot", "CompanyCardV2SnapshotV1", "CompanyCardV2SnapshotV2",
    "CompanyCardV2SnapshotV3", "ArbitrationBasisV2", "ArbitrationBasisLimitationV2",
    "ArbitrationChartFactsV1", "ArbitrationCollectionCountersV2", "ArbitrationPageManifestV2",
    "ArbitrationNamedCountV1", "ArbitrationYearRoleFactV1", "PrivateOpponentTokenV2",
    "SanitizedArbitrationCaseV2", "ARBITRATION_COMPLETION_PRECEDENCE_V2",
    "ARBITRATION_LIMITATION_PRECEDENCE_V2", "ARBITRATION_CASE_LIMITATION_CODES_V2",
    "ArbitrationCompletionReasonV2",
    "ArbitrationLimitationCodeV2",
    "NarrativeEvidenceV1", "PrimaryActivitySnapshotV1", "FinanceBasisV1", "FinanceCellV1", "InternalCaseIdentityV1",
    "LimitationV1", "PrivateArbitrationCaseV1", "PrivateOpponentTokenV1",
]
