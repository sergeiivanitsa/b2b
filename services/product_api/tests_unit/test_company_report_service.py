from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from company_report_signal_test_helpers import complete_company_report
from product_api.company_reports import service
from product_api.company_reports.persistence import (
    EnqueuedReportJob,
    LatestFinalizedReportRecord,
    ReportRunStatusRecord,
    calculate_company_report_snapshot_hash,
    company_report_to_snapshot,
)
from product_api.settings import get_settings

pytestmark = pytest.mark.asyncio


def _session():
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _finalized_record(report):
    snapshot = company_report_to_snapshot(report)
    now = datetime(2026, 7, 23, tzinfo=timezone.utc)
    return LatestFinalizedReportRecord(
        report_id=report.report_id,
        subject_id=uuid4(),
        lifecycle_status=report.status.value,
        report_version=report.report_version,
        started_at=now,
        generated_at=report.generated_at,
        finished_at=now,
        fresh_until=None,
        normalized_snapshot=snapshot,
        snapshot_hash=calculate_company_report_snapshot_hash(snapshot),
        safe_error_snapshot=None,
        usable_for_public_page=report.usable_for_public_page,
        usable_for_future_scoring=report.usable_for_future_scoring,
        created_at=now,
    )


async def test_create_is_enqueue_only_and_commits_atomic_pair(monkeypatch):
    session = _session()
    enqueued = EnqueuedReportJob(
        report_id=uuid4(),
        job_id=uuid4(),
        subject_id=uuid4(),
        lifecycle_status="pending",
        reused=False,
    )
    enqueue = AsyncMock(return_value=enqueued)
    monkeypatch.setattr(service, "enqueue_company_report_job", enqueue)

    response = await service.create_or_reuse_company_report(
        session,
        inn="770-000-0000",
    )

    assert response.report_id == enqueued.report_id
    assert response.status == "pending"
    assert response.reused is False
    enqueue.assert_awaited_once_with(session, "7700000000")
    session.commit.assert_awaited_once()


async def test_status_is_persistence_only(monkeypatch):
    session = _session()
    now = datetime(2026, 7, 23, tzinfo=timezone.utc)
    persisted = ReportRunStatusRecord(
        report_id=uuid4(),
        lifecycle_status="pending",
        report_version="1",
        started_at=now,
        generated_at=None,
        finished_at=None,
        fresh_until=None,
    )
    monkeypatch.setattr(
        service,
        "get_latest_run_status_by_identifier",
        AsyncMock(return_value=persisted),
    )
    monkeypatch.setattr(
        service,
        "evaluate_signals",
        MagicMock(side_effect=AssertionError("must not run")),
    )

    response = await service.get_company_report_status(
        session,
        inn="7700000000",
    )

    assert response.report_id == persisted.report_id
    assert response.status == "pending"


async def test_latest_report_evaluates_ephemerally_without_mutating_snapshot(
    monkeypatch,
):
    session = _session()
    report = complete_company_report(report_version="2")
    finalized = _finalized_record(report)
    original = deepcopy(finalized.normalized_snapshot)
    monkeypatch.setattr(
        service,
        "get_latest_finalized_report_record",
        AsyncMock(return_value=finalized),
    )
    monkeypatch.setattr(
        service,
        "get_latest_run_status_by_identifier",
        AsyncMock(return_value=None),
    )
    explain = AsyncMock(side_effect=AssertionError("AI is opt-in only"))
    monkeypatch.setattr(service, "explain_scoring_result", explain)

    response = await service.get_latest_company_report(
        session,
        inn=report.target_identifier,
        settings=get_settings(),
    )

    assert response.report_id == report.report_id
    assert response.report is not None
    assert response.signals is not None
    assert response.scoring is not None
    assert response.ai_explanation is None
    assert finalized.normalized_snapshot == original
    explain.assert_not_awaited()


async def test_latest_report_adds_canonical_path_from_matching_safe_identity(
    monkeypatch,
):
    session = _session()
    base_report = complete_company_report()
    report = base_report.model_copy(
        update={
            "counterparty": base_report.counterparty.model_copy(
                update={
                    "inn": "0000000000",
                    "legal_form": "ООО",
                    "short_name": "ООО Вектор",
                    "full_name": "Полное имя не используется",
                }
            )
        }
    )
    finalized = _finalized_record(report)
    monkeypatch.setattr(service, "get_latest_finalized_report_record", AsyncMock(return_value=finalized))
    monkeypatch.setattr(service, "get_latest_run_status_by_identifier", AsyncMock(return_value=None))

    response = await service.get_latest_company_report(
        session,
        inn=report.target_identifier,
        settings=get_settings(),
    )

    assert response.canonical_path == "/company/ooo-vektor-0000000000"


async def test_latest_report_has_no_canonical_path_without_matching_identity_or_for_failed_report(
    monkeypatch,
):
    session = _session()
    base_report = complete_company_report()
    report = base_report.model_copy(
        update={
            "counterparty": base_report.counterparty.model_copy(
                update={"inn": "7700000000", "short_name": None, "full_name": None}
            )
        }
    )
    finalized = _finalized_record(report)
    monkeypatch.setattr(service, "get_latest_finalized_report_record", AsyncMock(return_value=finalized))
    monkeypatch.setattr(service, "get_latest_run_status_by_identifier", AsyncMock(return_value=None))

    response = await service.get_latest_company_report(
        session,
        inn=report.target_identifier,
        settings=get_settings(),
    )

    assert response.canonical_path is None


async def test_pending_does_not_hide_older_finalized_report(monkeypatch):
    session = _session()
    report = complete_company_report()
    finalized = _finalized_record(report)
    now = datetime.now(timezone.utc)
    pending = ReportRunStatusRecord(
        report_id=uuid4(),
        lifecycle_status="pending",
        report_version="1",
        started_at=now,
        generated_at=None,
        finished_at=None,
        fresh_until=None,
    )
    monkeypatch.setattr(
        service,
        "get_latest_finalized_report_record",
        AsyncMock(return_value=finalized),
    )
    monkeypatch.setattr(
        service,
        "get_latest_run_status_by_identifier",
        AsyncMock(return_value=pending),
    )

    response = await service.get_latest_company_report(
        session,
        inn=report.target_identifier,
        settings=get_settings(),
    )

    assert response.report_id == finalized.report_id


async def test_infrastructure_failed_record_exposes_only_allowlisted_failure(
    monkeypatch,
):
    session = _session()
    now = datetime.now(timezone.utc)
    failed = LatestFinalizedReportRecord(
        report_id=uuid4(),
        subject_id=uuid4(),
        lifecycle_status="failed",
        report_version="1",
        started_at=now,
        generated_at=None,
        finished_at=now,
        fresh_until=None,
        normalized_snapshot=None,
        snapshot_hash=None,
        safe_error_snapshot={
            "code": "report_execution_interrupted",
            "message": "raw exception must not escape",
            "request_id": "private-request",
        },
        usable_for_public_page=False,
        usable_for_future_scoring=False,
        created_at=now,
    )
    monkeypatch.setattr(
        service,
        "get_latest_finalized_report_record",
        AsyncMock(return_value=failed),
    )
    monkeypatch.setattr(
        service,
        "get_latest_run_status_by_identifier",
        AsyncMock(return_value=None),
    )

    response = await service.get_latest_company_report(
        session,
        inn="7700000000",
        settings=get_settings(),
    )

    assert response.report is None
    assert response.signals is None
    assert response.scoring is None
    assert response.failure is not None
    assert response.failure.code == "report_execution_interrupted"
    assert response.canonical_path is None
    assert "raw exception" not in response.model_dump_json()
