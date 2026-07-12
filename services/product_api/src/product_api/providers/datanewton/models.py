from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .errors import DataNewtonValidationError

BATCH_CARDS_ENDPOINT = "/v1/batchCards"
TAX_INFO_ENDPOINT = "/v1/taxInfo"
ARBITRATION_CASES_ENDPOINT = "/v1/arbitration-cases"
FSSP_ENDPOINT = "/v1/fssp"
BANKRUPTCY_ENDPOINT = "/v1/bankruptcy"
MAX_BATCH_IDENTIFIERS = 5000
_NON_DIGIT_RE = re.compile(r"\D+")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class DataNewtonIdentifierType(StrEnum):
    LEGAL_ENTITY_INN = "legal_entity_inn"
    INDIVIDUAL_ENTREPRENEUR_INN = "individual_entrepreneur_inn"
    OGRN = "ogrn"
    OGRNIP = "ogrnip"


_IDENTIFIER_TYPES_BY_LENGTH = {
    10: DataNewtonIdentifierType.LEGAL_ENTITY_INN,
    12: DataNewtonIdentifierType.INDIVIDUAL_ENTREPRENEUR_INN,
    13: DataNewtonIdentifierType.OGRN,
    15: DataNewtonIdentifierType.OGRNIP,
}


def normalize_identifier(value: str) -> str:
    """Normalize an INN/OGRN format without validating its checksum."""
    if not isinstance(value, str):
        raise DataNewtonValidationError(
            "identifier must be a string",
            endpoint=BATCH_CARDS_ENDPOINT,
        )
    normalized = _NON_DIGIT_RE.sub("", value)
    if not normalized:
        raise DataNewtonValidationError(
            "identifier must not be empty",
            endpoint=BATCH_CARDS_ENDPOINT,
        )
    if len(normalized) not in _IDENTIFIER_TYPES_BY_LENGTH:
        raise DataNewtonValidationError(
            "identifier must contain 10, 12, 13, or 15 digits",
            endpoint=BATCH_CARDS_ENDPOINT,
        )
    return normalized


def identify_identifier_type(value: str) -> DataNewtonIdentifierType:
    normalized = normalize_identifier(value)
    return _IDENTIFIER_TYPES_BY_LENGTH[len(normalized)]


def identifier_query_parameter(identifier_type: DataNewtonIdentifierType) -> str:
    if identifier_type in {
        DataNewtonIdentifierType.LEGAL_ENTITY_INN,
        DataNewtonIdentifierType.INDIVIDUAL_ENTREPRENEUR_INN,
    }:
        return "inn"
    return "ogrn"


class SingleIdentifierRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: str

    @field_validator("identifier")
    @classmethod
    def _normalize_identifier(cls, value: str) -> str:
        return normalize_identifier(value)

    @property
    def identifier_type(self) -> DataNewtonIdentifierType:
        return identify_identifier_type(self.identifier)

    def identifier_query_params(self) -> dict[str, str]:
        return {identifier_query_parameter(self.identifier_type): self.identifier}


class TaxInfoRequest(SingleIdentifierRequest):
    pass


class ArbitrationCasesRequest(SingleIdentifierRequest):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=1000)
    company_role: str | None = None
    status: int | None = None
    start_date: str | None = None
    end_date: str | None = None
    updated_at_from: str | None = None
    need_document: bool | None = None

    @field_validator("start_date", "end_date", "updated_at_from")
    @classmethod
    def _validate_iso_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _ISO_DATE_RE.fullmatch(value):
            raise ValueError("date must use YYYY-MM-DD format")
        try:
            date.fromisoformat(value)
        except ValueError:
            raise ValueError("date must be a valid ISO calendar date") from None
        return value

    def query_params(self) -> dict[str, str | int | bool]:
        params: dict[str, str | int | bool] = {
            **self.identifier_query_params(),
            "offset": self.offset,
            "limit": self.limit,
        }
        for name in (
            "company_role",
            "status",
            "start_date",
            "end_date",
            "updated_at_from",
            "need_document",
        ):
            value = getattr(self, name)
            if value is not None:
                params[name] = value
        return params


class FsspRequest(SingleIdentifierRequest):
    limit: int = Field(default=100, ge=0, le=1000)
    offset: int = Field(default=0, ge=0)
    sort: str | None = None
    order: str | None = None
    filter: dict[str, object] | None = None

    @field_validator("filter")
    @classmethod
    def _require_json_filter(
        cls, value: dict[str, object] | None
    ) -> dict[str, object] | None:
        if value is None:
            return None
        try:
            json.dumps(value, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError):
            raise ValueError("filter must contain JSON-compatible values") from None
        return value

    def body(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            **self.identifier_query_params(),
            "limit": self.limit,
            "offset": self.offset,
        }
        for name in ("sort", "order", "filter"):
            value = getattr(self, name)
            if value is not None:
                body[name] = value
        return body


class BankruptcyRequest(SingleIdentifierRequest):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=1000)

    def query_params(self) -> dict[str, str | int]:
        return {
            **self.identifier_query_params(),
            "offset": self.offset,
            "limit": self.limit,
        }


class BatchCardsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_inns_or_ogrns: list[str] = Field(min_length=1, max_length=MAX_BATCH_IDENTIFIERS)

    @field_validator("source_inns_or_ogrns", mode="before")
    @classmethod
    def _validate_collection(cls, value: object) -> object:
        if not isinstance(value, list):
            raise ValueError("source_inns_or_ogrns must be a list")
        if not 1 <= len(value) <= MAX_BATCH_IDENTIFIERS:
            raise ValueError(
                f"source_inns_or_ogrns must contain between 1 and {MAX_BATCH_IDENTIFIERS} items"
            )
        return value

    @field_validator("source_inns_or_ogrns")
    @classmethod
    def _normalize_and_deduplicate(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            identifier = normalize_identifier(value)
            if identifier not in seen:
                normalized.append(identifier)
                seen.add(identifier)
        if not normalized:
            raise ValueError("source_inns_or_ogrns must not be empty after deduplication")
        return normalized


class DataNewtonResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["datanewton"] = "datanewton"
    dataset: str
    endpoint: str
    requested_identifier: str | None = Field(default=None, repr=False)
    requested_identifiers: list[str] = Field(default_factory=list, repr=False)
    request_parameters: dict[str, Any] = Field(default_factory=dict, repr=False)
    request_body: dict[str, Any] | None = Field(default=None, repr=False)
    status_code: int
    attempts: int = Field(ge=1)
    duration_ms: float = Field(ge=0)
    request_id: str | None = None
    received_at: datetime
    raw_payload: dict[str, Any] = Field(repr=False)
    response_hash: str
    provider_limit_metadata: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)

    @field_validator("received_at")
    @classmethod
    def _require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("received_at must be timezone-aware")
        return value.astimezone(timezone.utc)


def calculate_response_hash(raw_payload: dict[str, Any]) -> str:
    canonical_payload = json.dumps(
        raw_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical_payload).hexdigest()
