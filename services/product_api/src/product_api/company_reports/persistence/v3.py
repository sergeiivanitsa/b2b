"""Strict serializer/parser for v3 snapshots; legacy serialization stays v1/v2-only."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import ValidationError

from product_api.company_reports.company_card_v2.canonical_json import canonical_digest
from product_api.company_reports.company_card_v2.models import (
    CompanyCardV2Snapshot,
    CompanyCardV2SnapshotV1,
    CompanyCardV2SnapshotV2,
    CompanyCardV2SnapshotV3,
)
from .errors import CompanyReportSnapshotError


CompanyCardV2SnapshotAny = (
    CompanyCardV2SnapshotV1 | CompanyCardV2SnapshotV2 | CompanyCardV2SnapshotV3
)


def company_card_v2_to_snapshot(snapshot: CompanyCardV2SnapshotAny) -> dict[str, Any]:
    if type(snapshot) not in {
        CompanyCardV2SnapshotV1,
        CompanyCardV2SnapshotV2,
        CompanyCardV2SnapshotV3,
    }:
        raise CompanyReportSnapshotError("company card v2 snapshot schema is invalid")
    data = snapshot.model_dump(mode="json")
    if data.get("report_version") != "3":
        raise CompanyReportSnapshotError("company card v2 snapshot version is invalid")
    # ``model_copy(update=...)`` deliberately skips Pydantic validation.  The
    # persistence boundary therefore reparses the emitted mapping and requires
    # the same exact runtime model and byte-equivalent re-emission before a
    # digest can be accepted.  This binds V1/V2/V3 to their discriminator and
    # closes other validation-bypass mutations without changing valid bytes.
    restored = company_card_v2_from_snapshot(data)
    if (
        type(restored) is not type(snapshot)
        or restored.model_dump(mode="json") != data
    ):
        raise CompanyReportSnapshotError("company card v2 snapshot schema is invalid")
    return data


def company_card_v2_from_snapshot(snapshot: object) -> CompanyCardV2SnapshotAny:
    if not isinstance(snapshot, dict) or snapshot.get("report_version") != "3" or type(snapshot.get("report_version")) is not str:
        raise CompanyReportSnapshotError("company card v2 snapshot version is invalid")
    try:
        # V1 is a frozen byte shape: a discriminator is only legal for the
        # explicitly new sub-schema, and no default field is materialized.
        if "snapshot_schema_version" not in snapshot:
            return CompanyCardV2SnapshotV1.model_validate(snapshot)
        if snapshot.get("snapshot_schema_version") == "company_card_v2_snapshot_v2":
            return CompanyCardV2SnapshotV2.model_validate(snapshot)
        if snapshot.get("snapshot_schema_version") == "company_card_v2_snapshot_v3":
            return CompanyCardV2SnapshotV3.model_validate(snapshot)
        raise CompanyReportSnapshotError("company card v2 snapshot schema is invalid")
    except ValidationError as exc:
        raise CompanyReportSnapshotError("company card v2 snapshot is invalid") from exc


def calculate_company_card_v2_snapshot_hash(snapshot: CompanyCardV2SnapshotAny | dict[str, Any]) -> str:
    payload = company_card_v2_to_snapshot(snapshot) if isinstance(
        snapshot,
        (CompanyCardV2SnapshotV1, CompanyCardV2SnapshotV2, CompanyCardV2SnapshotV3),
    ) else snapshot
    return canonical_digest(payload)


def validate_company_card_v2_finalization(
    snapshot: CompanyCardV2SnapshotAny,
    *,
    report_id: UUID,
    subject_inn: str,
    writer_profile: str,
    report_version: str,
    presentation_contract: str,
    rollout_config_generation: int,
) -> tuple[dict[str, Any], str]:
    """Validate the immutable v3 snapshot against its stored writer tuple.

    This remains persistence-neutral so the repository/worker can use one
    closed check before mutating a report.  The returned bytes-equivalent
    mapping and digest come from the same validated snapshot.
    """
    expected = (
        str(report_id), subject_inn, writer_profile, report_version,
        presentation_contract, rollout_config_generation,
    )
    observed = (
        snapshot.report_id, snapshot.subject_inn, snapshot.writer_profile,
        snapshot.report_version, snapshot.presentation_contract,
        snapshot.rollout_config_generation,
    )
    if observed != expected or snapshot.target_inn != subject_inn:
        raise CompanyReportSnapshotError("company card v2 snapshot writer decision is invalid")
    serialized = company_card_v2_to_snapshot(snapshot)
    return serialized, canonical_digest(serialized)


__all__ = [
    "calculate_company_card_v2_snapshot_hash",
    "company_card_v2_from_snapshot",
    "company_card_v2_to_snapshot",
    "validate_company_card_v2_finalization",
]
