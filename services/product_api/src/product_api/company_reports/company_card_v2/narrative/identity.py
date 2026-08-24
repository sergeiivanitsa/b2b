from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import re
from typing import Literal
from uuid import UUID

from ..canonical_json import canonical_json_bytes
from .catalog import (
    FALLBACK_CATALOG_VERSION,
    FALLBACK_PROFILE_ID,
    FALLBACK_RENDERER_VERSION,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$")
_SNAPSHOT_SCHEMA_VERSIONS = frozenset(
    {
        "company_report_snapshot_v1_legacy",
        "company_report_snapshot_v2_legacy",
        "company_card_v2_snapshot_v1",
        "company_card_v2_snapshot_v2",
    }
)


def _require_sha256(name: str, value: object) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{name} must be lowercase SHA-256")


def _require_version(name: str, value: object, *, maximum: int = 96) -> None:
    if (
        not isinstance(value, str)
        or len(value) > maximum
        or _VERSION.fullmatch(value) is None
    ):
        raise ValueError(f"{name} must be a canonical version")


def _require_report_id(value: object) -> None:
    if not isinstance(value, str):
        raise ValueError("report_id must be a canonical UUID")
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("report_id must be a canonical UUID") from exc
    if str(parsed) != value:
        raise ValueError("report_id must be a canonical UUID")


@dataclass(frozen=True)
class GenerationIdentityV1:
    report_id: str
    snapshot_hash: str
    chart_facts_hash: str
    evidence_registry_version: str
    statement_catalog_version: str
    template_catalog_version: str
    prompt_version: str
    json_schema_version: str
    policy_version: str
    renderer_version: str
    gateway_profile_version: str
    fallback_catalog_version: str
    identity_version: Literal["GenerationIdentityV1"] = field(
        default="GenerationIdentityV1", init=False
    )

    def __post_init__(self) -> None:
        _require_report_id(self.report_id)
        _require_sha256("snapshot_hash", self.snapshot_hash)
        _require_sha256("chart_facts_hash", self.chart_facts_hash)
        for name in (
            "evidence_registry_version",
            "statement_catalog_version",
            "template_catalog_version",
            "prompt_version",
            "json_schema_version",
            "policy_version",
            "renderer_version",
            "gateway_profile_version",
            "fallback_catalog_version",
        ):
            _require_version(name, getattr(self, name))


@dataclass(frozen=True)
class GenerationIdentityV2:
    report_id: str
    snapshot_hash: str
    chart_facts_hash: str
    evidence_registry_version: str
    statement_catalog_version: str
    template_catalog_version: str
    prompt_version: str
    json_schema_version: str
    policy_version: str
    renderer_version: str
    gateway_profile_version: str
    fallback_catalog_version: str
    snapshot_schema_version: str
    narrative_evidence_schema_version: str
    primary_activity_parser_version: str
    primary_activity_evidence_version: str
    insight_catalog_version: str
    connector_catalog_version: str
    input_schema_version: str
    identity_version: Literal["GenerationIdentityV2"] = field(
        default="GenerationIdentityV2", init=False
    )

    def __post_init__(self) -> None:
        _require_report_id(self.report_id)
        _require_sha256("snapshot_hash", self.snapshot_hash)
        _require_sha256("chart_facts_hash", self.chart_facts_hash)
        for name in (
            "evidence_registry_version",
            "statement_catalog_version",
            "template_catalog_version",
            "prompt_version",
            "json_schema_version",
            "policy_version",
            "renderer_version",
            "gateway_profile_version",
            "fallback_catalog_version",
            "snapshot_schema_version",
            "narrative_evidence_schema_version",
            "primary_activity_parser_version",
            "primary_activity_evidence_version",
            "insight_catalog_version",
            "connector_catalog_version",
            "input_schema_version",
        ):
            _require_version(name, getattr(self, name))
        if self.snapshot_schema_version not in _SNAPSHOT_SCHEMA_VERSIONS:
            raise ValueError("snapshot_schema_version is not supported")
        absent = self.narrative_evidence_schema_version == "narrative_evidence_absent_v1"
        if absent != (
            self.primary_activity_parser_version == "not_applicable_v1"
            and self.primary_activity_evidence_version == "not_applicable_v1"
        ):
            raise ValueError("narrative evidence version tuple is inconsistent")


@dataclass(frozen=True)
class ArtifactIdentityV1:
    generation_key: str
    resolved_model_version: str
    validated_render_plan_bytes_sha256: str
    rendered_output_bytes_sha256: str
    identity_version: Literal["ArtifactIdentityV1"] = field(
        default="ArtifactIdentityV1", init=False
    )

    def __post_init__(self) -> None:
        _require_sha256("generation_key", self.generation_key)
        _require_version(
            "resolved_model_version", self.resolved_model_version, maximum=255
        )
        _require_sha256(
            "validated_render_plan_bytes_sha256",
            self.validated_render_plan_bytes_sha256,
        )
        _require_sha256(
            "rendered_output_bytes_sha256", self.rendered_output_bytes_sha256
        )


@dataclass(frozen=True)
class FallbackIdentityV1:
    generation_key: str
    fallback_catalog_version: str
    fallback_profile_id: str
    renderer_version: str
    rendered_output_bytes_sha256: str
    identity_version: Literal["FallbackIdentityV1"] = field(
        default="FallbackIdentityV1", init=False
    )

    def __post_init__(self) -> None:
        _require_sha256("generation_key", self.generation_key)
        _require_sha256(
            "rendered_output_bytes_sha256", self.rendered_output_bytes_sha256
        )
        if self.fallback_catalog_version != FALLBACK_CATALOG_VERSION:
            raise ValueError("fallback_catalog_version is not supported")
        if self.fallback_profile_id != FALLBACK_PROFILE_ID:
            raise ValueError("fallback_profile_id is not supported")
        if self.renderer_version != FALLBACK_RENDERER_VERSION:
            raise ValueError("fallback renderer_version is not supported")


def identity_key(identity: GenerationIdentityV1 | GenerationIdentityV2 | ArtifactIdentityV1 | FallbackIdentityV1) -> str:
    if type(identity) not in {
        GenerationIdentityV1,
        GenerationIdentityV2,
        ArtifactIdentityV1,
        FallbackIdentityV1,
    }:
        raise TypeError("unsupported narrative identity")
    return sha256(canonical_json_bytes(asdict(identity))).hexdigest()
