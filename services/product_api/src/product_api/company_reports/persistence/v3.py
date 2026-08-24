"""Strict serializer/parser for v3 snapshots; legacy serialization stays v1/v2-only."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import ValidationError

from product_api.company_reports.company_card_v2.canonical_json import canonical_digest
from product_api.company_reports.company_card_v2.models import CompanyCardV2Snapshot
from .errors import CompanyReportSnapshotError


def company_card_v2_to_snapshot(snapshot: CompanyCardV2Snapshot) -> dict[str, Any]:
    data = snapshot.model_dump(mode="json")
    if data.get("report_version") != "3":
        raise CompanyReportSnapshotError("company card v2 snapshot version is invalid")
    return data


def company_card_v2_from_snapshot(snapshot: object) -> CompanyCardV2Snapshot:
    if not isinstance(snapshot, dict) or snapshot.get("report_version") != "3" or type(snapshot.get("report_version")) is not str:
        raise CompanyReportSnapshotError("company card v2 snapshot version is invalid")
    try:
        return CompanyCardV2Snapshot.model_validate(snapshot)
    except ValidationError as exc:
        raise CompanyReportSnapshotError("company card v2 snapshot is invalid") from exc


def calculate_company_card_v2_snapshot_hash(snapshot: CompanyCardV2Snapshot | dict[str, Any]) -> str:
    payload = company_card_v2_to_snapshot(snapshot) if isinstance(snapshot, CompanyCardV2Snapshot) else snapshot
    return canonical_digest(payload)


def validate_company_card_v2_finalization(
    snapshot: CompanyCardV2Snapshot,
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
