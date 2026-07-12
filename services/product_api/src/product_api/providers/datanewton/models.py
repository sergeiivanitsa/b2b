from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .errors import DataNewtonValidationError

BATCH_CARDS_ENDPOINT = "/v1/batchCards"
MAX_BATCH_IDENTIFIERS = 5000
_NON_DIGIT_RE = re.compile(r"\D+")


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
    model_config = ConfigDict(extra="forbid")

    provider: Literal["datanewton"] = "datanewton"
    dataset: Literal["batch_cards"] = "batch_cards"
    endpoint: Literal["/v1/batchCards"] = BATCH_CARDS_ENDPOINT
    requested_identifiers: list[str]
    status_code: int
    attempts: int = Field(ge=1)
    duration_ms: float = Field(ge=0)
    request_id: str | None = None
    received_at: datetime
    raw_payload: dict[str, Any] = Field(repr=False)
    response_hash: str
    provider_limit_metadata: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)


def calculate_response_hash(raw_payload: dict[str, Any]) -> str:
    canonical_payload = json.dumps(
        raw_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical_payload).hexdigest()
