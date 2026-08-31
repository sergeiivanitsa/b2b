"""Strict serializer/parser for v3 snapshots; legacy serialization stays v1/v2-only."""
from __future__ import annotations

from typing import Any

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


__all__ = ["calculate_company_card_v2_snapshot_hash", "company_card_v2_from_snapshot", "company_card_v2_to_snapshot"]
