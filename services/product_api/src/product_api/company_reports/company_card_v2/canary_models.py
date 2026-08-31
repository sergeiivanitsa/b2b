"""Private immutable operator plan for one Company Card v2 canary.

The plan is deliberately separate from the public API and from the rollout
decision.  It binds the exact pre-activation database state which the canary
preparer is allowed to extend, without containing credentials or provider
payloads.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator

from product_api.company_reports.company_urls import parse_company_path
from .canonical_json import canonical_json_bytes


CANARY_PLAN_SCHEMA_VERSION = "company_card_v2_canary_plan_v1"
CANARY_RECEIPT_SCHEMA_VERSION = "company_card_v2_canary_receipt_v1"
MAX_CANARY_PLAN_BYTES = 65_536

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_INN = re.compile(r"^(?:[0-9]{10}|[0-9]{12})$")
_KEY_ID = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_RELEASE = re.compile(r"^[0-9a-f]{40}$")
_REVISION = re.compile(r"^[A-Za-z0-9_]{1,128}$")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")


class CanaryPlanError(ValueError):
    """A privacy-safe plan parsing failure."""

    code = "canary_plan_invalid"


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} redacted>"

    __str__ = __repr__


class CanaryExpectedAssignmentV1(_ClosedModel):
    generation: StrictInt = Field(ge=0)
    presentation_contract: Literal[
        "company_public_h1_v1", "company_public_h2_v1"
    ] | None
    pin_generation: StrictInt | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _closed_shape(self):
        if self.generation == 0 and (
            self.presentation_contract is not None
            or self.pin_generation is not None
        ):
            raise ValueError("assignment shape is invalid")
        if self.generation > 0 and (
            self.presentation_contract is None
            or self.pin_generation is None
        ):
            raise ValueError("assignment shape is invalid")
        return self


class CanaryH1RollbackV1(_ClosedModel):
    source_kind: Literal[
        "assignment_pin",
        "publication_pin",
        "active_publication",
        "latest_eligible_report",
    ]
    report_id: str
    snapshot_hash: str
    pin_generation: StrictInt = Field(gt=0)
    pin_exists: StrictBool
    publication_policy_version: Literal["publication_sufficiency_v1"]
    canonical_path: str
    published_lastmod: str

    @model_validator(mode="after")
    def _source_shape(self):
        if self.source_kind in {"assignment_pin", "publication_pin"}:
            if not self.pin_exists:
                raise ValueError("H1 pin source is invalid")
        elif self.pin_exists:
            raise ValueError("H1 report source is invalid")
        return self

    @field_validator("report_id")
    @classmethod
    def _report_id(cls, value: str) -> str:
        return _canonical_uuid(value, "report ID")

    @field_validator("snapshot_hash")
    @classmethod
    def _snapshot_hash(cls, value: str) -> str:
        if type(value) is not str or _DIGEST.fullmatch(value) is None:
            raise ValueError("snapshot hash is invalid")
        return value

    @field_validator("canonical_path")
    @classmethod
    def _canonical_path(cls, value: str) -> str:
        parsed = parse_company_path(value)
        if type(value) is not str or parsed is None or parsed.kind == "plain":
            raise ValueError("canonical path is invalid")
        return value

    @field_validator("published_lastmod")
    @classmethod
    def _published_lastmod(cls, value: str) -> str:
        if type(value) is not str or _UTC.fullmatch(value) is None:
            raise ValueError("published lastmod is invalid")
        return value


class CanaryExpectedH2V1(_ClosedModel):
    head_generation: StrictInt = Field(ge=0)
    head_report_id: str | None
    active_report_id: str | None
    active_job_state: Literal["queued", "running"] | None

    @field_validator("head_report_id", "active_report_id")
    @classmethod
    def _optional_uuid(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _canonical_uuid(value, "report ID")

    @model_validator(mode="after")
    def _closed_shape(self):
        if (self.head_generation == 0) != (self.head_report_id is None):
            raise ValueError("H2 head shape is invalid")
        if (self.active_report_id is None) != (self.active_job_state is None):
            raise ValueError("active H2 job shape is invalid")
        if (
            self.active_report_id is not None
            and self.head_report_id != self.active_report_id
        ):
            raise ValueError("active H2 job is not the lifecycle head")
        return self


class CompanyCardV2CanaryPlanV1(_ClosedModel):
    schema_version: Literal["company_card_v2_canary_plan_v1"]
    release_commit: str
    database_schema_revision: str
    rollout_generation: StrictInt = Field(gt=0)
    arbitration_mask_key_id: str
    target_subject_id: str
    target_inn: str
    expected_assignment: CanaryExpectedAssignmentV1
    h1_rollback: CanaryH1RollbackV1
    expected_h2: CanaryExpectedH2V1

    @field_validator("release_commit")
    @classmethod
    def _release(cls, value: str) -> str:
        if type(value) is not str or _RELEASE.fullmatch(value) is None:
            raise ValueError("release commit is invalid")
        return value

    @field_validator("database_schema_revision")
    @classmethod
    def _revision(cls, value: str) -> str:
        if type(value) is not str or _REVISION.fullmatch(value) is None:
            raise ValueError("database revision is invalid")
        return value

    @field_validator("arbitration_mask_key_id")
    @classmethod
    def _key_id(cls, value: str) -> str:
        if type(value) is not str or _KEY_ID.fullmatch(value) is None:
            raise ValueError("arbitration key ID is invalid")
        return value

    @field_validator("target_subject_id")
    @classmethod
    def _subject_id(cls, value: str) -> str:
        return _canonical_uuid(value, "subject ID")

    @field_validator("target_inn")
    @classmethod
    def _inn(cls, value: str) -> str:
        if type(value) is not str or _INN.fullmatch(value) is None:
            raise ValueError("target INN is invalid")
        return value

    @model_validator(mode="after")
    def _target_path(self):
        parsed = parse_company_path(self.h1_rollback.canonical_path)
        if parsed is None or parsed.kind == "plain" or parsed.inn != self.target_inn:
            raise ValueError("H1 rollback target is invalid")
        return self

    @property
    def subject_uuid(self) -> UUID:
        return UUID(self.target_subject_id)

    @property
    def h1_report_uuid(self) -> UUID:
        return UUID(self.h1_rollback.report_id)


class CompanyCardV2CanaryReceiptV1(_ClosedModel):
    """Durable pre-commit lineage emitted by an attempted prepare command.

    A commit failure may leave this receipt stale; every consuming command
    must therefore revalidate its exact database lineage.
    """

    schema_version: Literal["company_card_v2_canary_receipt_v1"]
    plan_digest: str
    target_subject_id: str
    head_generation: StrictInt = Field(gt=0)
    presentation_id: str
    report_id: str
    job_id: str

    @field_validator("plan_digest")
    @classmethod
    def _plan_digest(cls, value: str) -> str:
        if type(value) is not str or _DIGEST.fullmatch(value) is None:
            raise ValueError("plan digest is invalid")
        return value

    @field_validator(
        "target_subject_id", "presentation_id", "report_id", "job_id"
    )
    @classmethod
    def _uuid(cls, value: str) -> str:
        return _canonical_uuid(value, "receipt UUID")

    @property
    def subject_uuid(self) -> UUID:
        return UUID(self.target_subject_id)

    @property
    def presentation_uuid(self) -> UUID:
        return UUID(self.presentation_id)

    @property
    def report_uuid(self) -> UUID:
        return UUID(self.report_id)

    @property
    def job_uuid(self) -> UUID:
        return UUID(self.job_id)


def parse_canary_plan_bytes(raw: bytes) -> CompanyCardV2CanaryPlanV1:
    try:
        if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_CANARY_PLAN_BYTES:
            raise ValueError
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        plan = CompanyCardV2CanaryPlanV1.model_validate(parsed)
        if canonical_json_bytes(plan.model_dump(mode="json")) != raw:
            raise ValueError
        return plan
    except Exception as exc:
        raise CanaryPlanError("canary_plan_invalid") from exc


def load_canary_plan(path: Path) -> CompanyCardV2CanaryPlanV1:
    try:
        return parse_canary_plan_bytes(path.read_bytes())
    except CanaryPlanError:
        raise
    except Exception as exc:
        raise CanaryPlanError("canary_plan_invalid") from exc


def canary_plan_bytes(plan: CompanyCardV2CanaryPlanV1) -> bytes:
    return canonical_json_bytes(plan.model_dump(mode="json"))


def canary_plan_digest(plan: CompanyCardV2CanaryPlanV1) -> str:
    return sha256(canary_plan_bytes(plan)).hexdigest()


def parse_canary_receipt_bytes(raw: bytes) -> CompanyCardV2CanaryReceiptV1:
    try:
        if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_CANARY_PLAN_BYTES:
            raise ValueError
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        receipt = CompanyCardV2CanaryReceiptV1.model_validate(parsed)
        if canary_receipt_bytes(receipt) != raw:
            raise ValueError
        return receipt
    except Exception as exc:
        raise CanaryPlanError("canary_receipt_invalid") from exc


def canary_receipt_bytes(receipt: CompanyCardV2CanaryReceiptV1) -> bytes:
    return canonical_json_bytes(receipt.model_dump(mode="json"))


def _canonical_uuid(value: str, label: str) -> str:
    if type(value) is not str:
        raise ValueError(f"{label} is invalid")
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{label} is invalid") from exc
    if str(parsed) != value:
        raise ValueError(f"{label} is invalid")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


__all__ = [
    "CANARY_PLAN_SCHEMA_VERSION",
    "CANARY_RECEIPT_SCHEMA_VERSION",
    "CanaryExpectedAssignmentV1",
    "CanaryExpectedH2V1",
    "CanaryH1RollbackV1",
    "CanaryPlanError",
    "CompanyCardV2CanaryPlanV1",
    "CompanyCardV2CanaryReceiptV1",
    "canary_plan_bytes",
    "canary_plan_digest",
    "canary_receipt_bytes",
    "load_canary_plan",
    "parse_canary_plan_bytes",
    "parse_canary_receipt_bytes",
]
