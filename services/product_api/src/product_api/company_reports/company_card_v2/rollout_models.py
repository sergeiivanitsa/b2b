"""Closed, privacy-safe operator contract for Company Card v2 rollout.

This module is deliberately pure: it reads no settings, environment, clock,
network or database state.  Parsing also proves the exact canonical JSON bytes
that are later bound by the database journal.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    ValidationError,
    field_validator,
    model_validator,
)

from .canonical_json import CanonicalJsonError, canonical_json_bytes


SCHEMA_VERSION = "company_card_v2_rollout_decision_v1"
H1_PRESENTATION_CONTRACT = "company_public_h1_v1"
H2_PRESENTATION_CONTRACT = "company_public_h2_v1"
MAX_DECISION_BYTES = 1_048_576
MAX_TARGETS = 1_000
ROLLOUT_DECISION_LOCK_DOMAIN = b"company-card-v2-rollout-decision-v1\x00"

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_INN = re.compile(r"^(?:[0-9]{10}|[0-9]{12})$")
_SAFE_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")

PositiveInt = Annotated[StrictInt, Field(gt=0)]
NonNegativeInt = Annotated[StrictInt, Field(ge=0)]
BasisPoints = Annotated[StrictInt, Field(ge=0, le=10_000)]
BatchSize = Annotated[StrictInt, Field(ge=1, le=MAX_TARGETS)]


class RolloutDecisionError(ValueError):
    """Closed validation failure; the message never contains target values."""

    code = "rollout_decision_invalid"


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} redacted>"

    __str__ = __repr__


class _TargetCommon(_ClosedModel):
    subject_id: str = Field(repr=False)
    inn: str = Field(repr=False)
    expected_assignment_generation: NonNegativeInt
    expected_current_contract: Literal[
        "company_public_h1_v1", "company_public_h2_v1"
    ] | None
    expected_current_pin_generation: PositiveInt | None

    @field_validator("subject_id")
    @classmethod
    def _canonical_subject_id(cls, value: str) -> str:
        if type(value) is not str:
            raise ValueError("subject ID must be a canonical UUID")
        try:
            parsed = UUID(value)
        except (ValueError, AttributeError) as exc:
            raise ValueError("subject ID must be a canonical UUID") from exc
        if str(parsed) != value:
            raise ValueError("subject ID must be a canonical UUID")
        return value

    @field_validator("inn")
    @classmethod
    def _normalized_inn(cls, value: str) -> str:
        if type(value) is not str or _INN.fullmatch(value) is None:
            raise ValueError("target INN is invalid")
        return value

    @model_validator(mode="after")
    def _current_shape(self):
        absent = self.expected_assignment_generation == 0
        if absent != (
            self.expected_current_contract is None
            and self.expected_current_pin_generation is None
        ):
            raise ValueError("expected current assignment shape is invalid")
        if not absent and (
            self.expected_current_contract is None
            or self.expected_current_pin_generation is None
        ):
            raise ValueError("expected current assignment shape is invalid")
        return self

    @property
    def subject_uuid(self) -> UUID:
        return UUID(self.subject_id)


class CompanyCardV2ActivateTargetV1(_TargetCommon):
    source_h2_pin_generation: PositiveInt
    expected_active_h2_pin_generation: PositiveInt
    expected_active_projection_digest: str
    h1_rollback_pin_generation: PositiveInt

    @field_validator("expected_active_projection_digest")
    @classmethod
    def _projection_digest(cls, value: str) -> str:
        if type(value) is not str or _HEX64.fullmatch(value) is None:
            raise ValueError("active projection digest is invalid")
        return value


class CompanyCardV2RollbackTargetV1(_TargetCommon):
    h1_target_pin_generation: PositiveInt

    @model_validator(mode="after")
    def _rollback_current_is_h2(self):
        if self.expected_current_contract != H2_PRESENTATION_CONTRACT:
            raise ValueError("rollback requires an exact current H2 assignment")
        return self


RolloutTargetV1 = CompanyCardV2ActivateTargetV1 | CompanyCardV2RollbackTargetV1


class CompanyCardV2RolloutDecisionV1(_ClosedModel):
    schema_version: Literal["company_card_v2_rollout_decision_v1"]
    decision_id: str
    authorization_reference: str = Field(repr=False)
    release_commit: str
    rollout_generation: PositiveInt | None
    action: Literal["activate", "rollback"]
    stage: Literal["allowlist", "percentage", "ga", "emergency_rollback"]
    target_contract: Literal[
        "company_public_h1_v1", "company_public_h2_v1"
    ]
    h2_indexable: StrictBool
    allowlist_inns: tuple[str, ...] | None = Field(repr=False)
    percentage_basis_points: BasisPoints | None
    maximum_batch_size: BatchSize
    observation_window_seconds: PositiveInt | None
    abort_policy_reference: str | None = Field(repr=False)
    targets: tuple[RolloutTargetV1, ...] = Field(repr=False)

    @field_validator("decision_id")
    @classmethod
    def _canonical_decision_id(cls, value: str) -> str:
        if type(value) is not str:
            raise ValueError("decision ID must be a canonical UUID")
        try:
            parsed = UUID(value)
        except (ValueError, AttributeError) as exc:
            raise ValueError("decision ID must be a canonical UUID") from exc
        if str(parsed) != value:
            raise ValueError("decision ID must be a canonical UUID")
        return value

    @field_validator("authorization_reference", "abort_policy_reference")
    @classmethod
    def _safe_reference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if type(value) is not str or _SAFE_REFERENCE.fullmatch(value) is None:
            raise ValueError("authorization reference is invalid")
        return value

    @field_validator("release_commit")
    @classmethod
    def _release_commit(cls, value: str) -> str:
        if type(value) is not str or _HEX40.fullmatch(value) is None:
            raise ValueError("release commit must be exact lowercase hex")
        return value

    @field_validator("allowlist_inns")
    @classmethod
    def _allowlist(cls, value: tuple[str, ...] | None):
        if value is None:
            return None
        if len(value) > MAX_TARGETS or any(
            type(inn) is not str or _INN.fullmatch(inn) is None for inn in value
        ):
            raise ValueError("allowlist is invalid")
        if tuple(sorted(set(value))) != value:
            raise ValueError("allowlist must be sorted and unique")
        return value

    @model_validator(mode="after")
    def _closed_matrix(self):
        if not 1 <= len(self.targets) <= MAX_TARGETS:
            raise ValueError("decision target count is invalid")
        if len(self.targets) > self.maximum_batch_size:
            raise ValueError("decision exceeds maximum batch size")
        if tuple(target.inn for target in self.targets) != tuple(
            sorted(target.inn for target in self.targets)
        ):
            raise ValueError("targets must be ordered by INN")
        if len({target.inn for target in self.targets}) != len(self.targets) or len(
            {target.subject_id for target in self.targets}
        ) != len(self.targets):
            raise ValueError("targets must have unique INNs and subjects")

        if self.action == "activate":
            self._validate_activate()
        else:
            self._validate_rollback()
        return self

    def _validate_activate(self) -> None:
        if (
            self.stage not in {"allowlist", "percentage", "ga"}
            or self.target_contract != H2_PRESENTATION_CONTRACT
            or self.rollout_generation is None
            or self.allowlist_inns is None
            or self.percentage_basis_points is None
            or self.observation_window_seconds is None
            or self.abort_policy_reference is None
            or not all(
                isinstance(target, CompanyCardV2ActivateTargetV1)
                for target in self.targets
            )
        ):
            raise ValueError("activate decision shape is invalid")

        if self.stage == "allowlist":
            valid_stage = (
                len(self.allowlist_inns) > 0
                and self.percentage_basis_points == 0
                and all(target.inn in self.allowlist_inns for target in self.targets)
            )
        elif self.stage == "percentage":
            valid_stage = 1 <= self.percentage_basis_points <= 9_999 and all(
                target.inn in self.allowlist_inns
                or cohort_bucket(target.inn) < self.percentage_basis_points
                for target in self.targets
            )
        else:
            valid_stage = (
                self.percentage_basis_points == 10_000 and self.h2_indexable
            )
        if not valid_stage:
            raise ValueError("activate stage/cohort shape is invalid")

    def _validate_rollback(self) -> None:
        if (
            self.stage != "emergency_rollback"
            or self.target_contract != H1_PRESENTATION_CONTRACT
            or self.h2_indexable
            or self.rollout_generation is not None
            or self.allowlist_inns is not None
            or self.percentage_basis_points is not None
            or self.observation_window_seconds is not None
            or self.abort_policy_reference is not None
            or not all(
                isinstance(target, CompanyCardV2RollbackTargetV1)
                for target in self.targets
            )
        ):
            raise ValueError("rollback decision shape is invalid")

    @property
    def decision_uuid(self) -> UUID:
        return UUID(self.decision_id)

    @property
    def reason_code(self) -> str:
        return f"{self.action}_{self.stage}"


@dataclass(frozen=True, repr=False)
class ParsedRolloutDecisionV1:
    decision: CompanyCardV2RolloutDecisionV1
    canonical_bytes: bytes
    decision_digest: str

    def __repr__(self) -> str:
        return (
            "<ParsedRolloutDecisionV1 "
            f"decision_id={self.decision.decision_id!r} "
            f"decision_digest={self.decision_digest!r}>"
        )


def cohort_bucket(inn: str) -> int:
    if type(inn) is not str or _INN.fullmatch(inn) is None:
        raise RolloutDecisionError("target INN is invalid")
    digest = hashlib.sha256(
        ("company-card-v2-cohort-v1\x00" + inn).encode("ascii")
    ).digest()
    return int.from_bytes(digest[:8], "big") % 10_000


def rollout_advisory_lock_key(decision_id: str) -> int:
    try:
        canonical_id = str(UUID(decision_id))
    except (ValueError, AttributeError) as exc:
        raise RolloutDecisionError("decision ID must be a canonical UUID") from exc
    if canonical_id != decision_id:
        raise RolloutDecisionError("decision ID must be a canonical UUID")
    digest = hashlib.sha256(
        ROLLOUT_DECISION_LOCK_DOMAIN + decision_id.encode("ascii")
    ).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def parse_rollout_decision(raw: bytes | str) -> ParsedRolloutDecisionV1:
    if isinstance(raw, str):
        try:
            encoded = raw.encode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise RolloutDecisionError("decision is not valid UTF-8") from exc
    elif isinstance(raw, bytes):
        encoded = raw
    else:
        raise RolloutDecisionError("decision input type is invalid")
    if len(encoded) > MAX_DECISION_BYTES:
        raise RolloutDecisionError("decision exceeds the technical size cap")
    if encoded.startswith(b"\xef\xbb\xbf"):
        raise RolloutDecisionError("UTF-8 BOM is forbidden")
    try:
        text = encoded.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise RolloutDecisionError("decision is not valid UTF-8") from exc

    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_float=_reject_json_number,
            parse_constant=_reject_json_number,
        )
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise RolloutDecisionError("decision JSON is invalid") from exc
    if type(value) is not dict:
        raise RolloutDecisionError("decision root must be an object")

    action = value.get("action")
    raw_targets = value.get("targets")
    if type(raw_targets) is not list:
        raise RolloutDecisionError("decision targets must be an array")
    target_type = (
        CompanyCardV2ActivateTargetV1
        if action == "activate"
        else CompanyCardV2RollbackTargetV1
        if action == "rollback"
        else None
    )
    if target_type is None:
        raise RolloutDecisionError("decision action is invalid")
    try:
        parsed_targets = tuple(target_type.model_validate(item) for item in raw_targets)
        candidate = dict(value)
        candidate["allowlist_inns"] = (
            None
            if candidate.get("allowlist_inns") is None
            else tuple(candidate["allowlist_inns"])
        )
        candidate["targets"] = parsed_targets
        decision = CompanyCardV2RolloutDecisionV1.model_validate(candidate)
        canonical = canonical_json_bytes(decision.model_dump(mode="json"))
    except (ValidationError, ValueError, TypeError, CanonicalJsonError) as exc:
        raise RolloutDecisionError("decision contract is invalid") from exc
    if canonical != encoded:
        raise RolloutDecisionError("decision bytes are not canonical JSON")
    return ParsedRolloutDecisionV1(
        decision=decision,
        canonical_bytes=canonical,
        decision_digest=hashlib.sha256(canonical).hexdigest(),
    )


def load_rollout_decision(path: str | Path) -> ParsedRolloutDecisionV1:
    candidate = Path(path)
    if not candidate.is_absolute() or candidate.is_symlink() or not candidate.is_file():
        raise RolloutDecisionError("decision path must be an absolute regular file")
    try:
        if candidate.stat().st_size > MAX_DECISION_BYTES:
            raise RolloutDecisionError("decision exceeds the technical size cap")
        raw = candidate.read_bytes()
    except RolloutDecisionError:
        raise
    except OSError as exc:
        raise RolloutDecisionError("decision file cannot be read") from exc
    return parse_rollout_decision(raw)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_json_number(value: str) -> object:
    raise ValueError("non-integer JSON number is forbidden")


__all__ = [
    "H1_PRESENTATION_CONTRACT",
    "H2_PRESENTATION_CONTRACT",
    "MAX_DECISION_BYTES",
    "MAX_TARGETS",
    "SCHEMA_VERSION",
    "CompanyCardV2ActivateTargetV1",
    "CompanyCardV2RollbackTargetV1",
    "CompanyCardV2RolloutDecisionV1",
    "ParsedRolloutDecisionV1",
    "RolloutDecisionError",
    "cohort_bucket",
    "load_rollout_decision",
    "parse_rollout_decision",
    "rollout_advisory_lock_key",
]
