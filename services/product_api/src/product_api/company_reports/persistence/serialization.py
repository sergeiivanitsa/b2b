from __future__ import annotations

import hashlib
import json
from typing import Any, TypeAlias

from pydantic import ValidationError

from product_api.company_reports.aggregate import CompanyReport

from .errors import CompanyReportSnapshotError

SerializedCompanyReport: TypeAlias = dict[str, Any]


def company_report_to_snapshot(report: CompanyReport) -> SerializedCompanyReport:
    try:
        snapshot = report.model_dump(mode="json")
        _assert_safe_snapshot(snapshot)
        json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return snapshot
    except CompanyReportSnapshotError:
        raise
    except (TypeError, ValueError) as exc:
        raise CompanyReportSnapshotError("company report snapshot is not serializable") from exc


def company_report_from_snapshot(snapshot: object) -> CompanyReport:
    if not isinstance(snapshot, dict):
        raise CompanyReportSnapshotError("company report snapshot must be an object")
    try:
        _assert_safe_snapshot(snapshot)
        return CompanyReport.model_validate(snapshot)
    except CompanyReportSnapshotError:
        raise
    except (ValidationError, TypeError, ValueError) as exc:
        raise CompanyReportSnapshotError("company report snapshot is invalid") from exc


def calculate_company_report_snapshot_hash(
    snapshot_or_report: SerializedCompanyReport | CompanyReport,
) -> str:
    snapshot = (
        company_report_to_snapshot(snapshot_or_report)
        if isinstance(snapshot_or_report, CompanyReport)
        else snapshot_or_report
    )
    try:
        canonical = json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CompanyReportSnapshotError("company report snapshot is not hashable") from exc
    return hashlib.sha256(canonical).hexdigest()


def _assert_safe_snapshot(snapshot: object) -> None:
    if _contains_key(snapshot, "raw_payload"):
        raise CompanyReportSnapshotError("company report snapshot contains forbidden data")


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False
