import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from company_report_orchestrator_test_helpers import successful_fake_provider
from company_report_signal_test_helpers import complete_company_report
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


@pytest.mark.parametrize("version", [None, 1, True, "0", "3"])
def test_raw_report_version_is_required_before_model_defaults(version):
    raw = {"report_version": version} if version is not None else {}
    with pytest.raises(CompanyReportSnapshotError, match="version"):
        company_report_from_snapshot(raw)


def test_fixed_legacy_v1_fixture_has_exact_hash_and_is_never_rewritten():
    path = Path(__file__).parent / "fixtures" / "company_reports" / "snapshot_v1_legacy.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    original = copy.deepcopy(raw)

    restored = company_report_from_snapshot(raw)

    assert raw == original
    assert company_report_to_snapshot(restored) == original
    assert calculate_company_report_snapshot_hash(raw) == "1845706ccdeae18f7bfa1fbceb0ed11ffa75afa6cb82d16e914749d6118d3c3d"
    assert calculate_company_report_snapshot_hash(company_report_to_snapshot(restored)) == calculate_company_report_snapshot_hash(raw)


def test_v1_recursive_serializer_omits_every_v2_only_arbitration_field():
    snapshot = company_report_to_snapshot(complete_company_report(report_version="1"))
    assert "optional_datasets" not in snapshot
    assert "malformed_entry_count" not in snapshot["arbitration"]
    for case in snapshot["arbitration"]["cases"]:
        for field in ("applicants", "creditors", "debtors", "interested_persons", "third_parties", "other_parties", "party_collections_valid"):
            assert field not in case
    assert company_report_to_snapshot(company_report_from_snapshot(snapshot)) == snapshot


def test_v1_raw_snapshot_rejects_v2_only_fields_instead_of_silently_rewriting():
    path = Path(__file__).parent / "fixtures" / "company_reports" / "snapshot_v1_legacy.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["optional_datasets"] = {}
    with pytest.raises(CompanyReportSnapshotError, match="v2 fields"):
        company_report_from_snapshot(raw)


def test_fixed_legacy_v2_fixture_never_acquires_company_card_narrative_fields() -> None:
    path = Path(__file__).parent / "fixtures" / "company_reports" / "snapshot_v2_exact.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    original = copy.deepcopy(raw)

    emitted = company_report_to_snapshot(company_report_from_snapshot(raw))
    wire = json.dumps(emitted, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    assert raw == original
    assert calculate_company_report_snapshot_hash(emitted) == "d29a97aedc4a24bc13047f3304d5e3e20fd1e9833d113190e5dd044b37b39e58"
    assert "snapshot_schema_version" not in wire
    assert "narrative_evidence" not in wire
    assert "primary_activity" not in wire
    assert company_report_to_snapshot(company_report_from_snapshot(emitted)) == emitted
