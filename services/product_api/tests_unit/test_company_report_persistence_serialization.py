import copy
import json
from datetime import datetime, timezone

import pytest

from company_report_orchestrator_test_helpers import successful_fake_provider
from product_api.company_reports import build_company_report
from product_api.company_reports.persistence import (
    CompanyReportSnapshotError,
    calculate_company_report_snapshot_hash,
    company_report_from_snapshot,
    company_report_to_snapshot,
)


@pytest.mark.asyncio
async def test_company_report_snapshot_round_trip_is_deterministic_and_non_mutating():
    report = await build_company_report(
        "0000000000",
        provider=successful_fake_provider(),
        clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    before = copy.deepcopy(report.model_dump(mode="json"))

    snapshot = company_report_to_snapshot(report)
    restored = company_report_from_snapshot(snapshot)
    reordered = {key: snapshot[key] for key in reversed(snapshot)}

    assert restored == report
    assert calculate_company_report_snapshot_hash(report) == calculate_company_report_snapshot_hash(reordered)
    assert before == report.model_dump(mode="json")
    assert "raw_payload" not in json.dumps(snapshot, ensure_ascii=False)
    assert "api-secret" not in json.dumps(snapshot, ensure_ascii=False)


def test_different_snapshot_has_different_hash_and_forbidden_raw_is_rejected():
    payload = {"report_version": "1", "value": "a"}
    changed = {"report_version": "1", "value": "b"}

    assert calculate_company_report_snapshot_hash(payload) != calculate_company_report_snapshot_hash(changed)
    with pytest.raises(CompanyReportSnapshotError):
        company_report_from_snapshot({"raw_payload": {"secret": True}})
