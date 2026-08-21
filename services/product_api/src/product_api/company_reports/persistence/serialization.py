from __future__ import annotations

import hashlib
import json
from typing import Any, TypeAlias

from pydantic import ValidationError

from product_api.company_reports.aggregate import CompanyReport, CURRENT_COMPANY_REPORT_VERSION

from .errors import CompanyReportSnapshotError

SerializedCompanyReport: TypeAlias = dict[str, Any]


def company_report_to_snapshot(report: CompanyReport) -> SerializedCompanyReport:
    try:
        snapshot = report.model_dump(
            mode="json",
            # Preserve the exact absence of default-valued keys in historical
            # raw v1 JSON. Persisted v1 snapshots that already contain those
            # keys keep them because model validation records them as set.
            exclude_unset=report.report_version == "1",
        )
        if report.report_version == "1":
            # v1 snapshots are immutable.  Pydantic necessarily materializes
            # defaults from the shared in-memory domain model, so remove every
            # additive v2 field recursively before serializing/hashing v1.
            _strip_v2_fields_from_v1(snapshot)
        elif report.report_version != CURRENT_COMPANY_REPORT_VERSION:
            raise CompanyReportSnapshotError("company report version is invalid")
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
        _require_raw_report_version(snapshot)
        _assert_safe_snapshot(snapshot)
        report = CompanyReport.model_validate(snapshot)
        if report.report_version != snapshot["report_version"]:
            raise CompanyReportSnapshotError("company report snapshot version is invalid")
        return report
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
    forbidden = {
        "raw_payload", "raw_headers", "request_headers", "response_headers",
        "authorization", "api_key", "token", "secret", "result_status",
        "result_status_code", "provider_status_code", "http_status_code",
    }
    if any(_contains_key(snapshot, key) for key in forbidden):
        raise CompanyReportSnapshotError("company report snapshot contains forbidden data")


def _require_raw_report_version(snapshot: dict[str, Any]) -> None:
    """Reject absent/coerced discriminators before Pydantic can apply defaults."""
    value = snapshot.get("report_version")
    if "report_version" not in snapshot or type(value) is not str or value not in {"1", "2"}:
        raise CompanyReportSnapshotError("company report snapshot version is invalid")
    if value == "2" and any(key not in snapshot for key in ("optional_datasets", "tax_info", "bankruptcy")):
        raise CompanyReportSnapshotError("company report v2 snapshot is incomplete")
    if value == "1" and _contains_v2_fields(snapshot):
        raise CompanyReportSnapshotError("company report v1 snapshot contains v2 fields")


def _contains_v2_fields(snapshot: SerializedCompanyReport) -> bool:
    if any(key in snapshot for key in ("optional_datasets", "tax_info", "bankruptcy")):
        return True
    arbitration = snapshot.get("arbitration")
    if not isinstance(arbitration, dict):
        return False
    if "malformed_entry_count" in arbitration:
        return True
    cases = arbitration.get("cases")
    v2_case_fields = {
        "applicants", "creditors", "debtors", "interested_persons",
        "third_parties", "other_parties", "party_collections_valid",
    }
    return isinstance(cases, list) and any(
        isinstance(case, dict) and not v2_case_fields.isdisjoint(case)
        for case in cases
    )


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False


def _strip_v2_fields_from_v1(snapshot: SerializedCompanyReport) -> None:
    for key in ("optional_datasets", "tax_info", "bankruptcy"):
        snapshot.pop(key, None)
    arbitration = snapshot.get("arbitration")
    if not isinstance(arbitration, dict):
        return
    arbitration.pop("malformed_entry_count", None)
    cases = arbitration.get("cases")
    if not isinstance(cases, list):
        return
    v2_case_fields = (
        "applicants", "creditors", "debtors", "interested_persons",
        "third_parties", "other_parties", "party_collections_valid",
    )
    for case in cases:
        if isinstance(case, dict):
            for key in v2_case_fields:
                case.pop(key, None)
