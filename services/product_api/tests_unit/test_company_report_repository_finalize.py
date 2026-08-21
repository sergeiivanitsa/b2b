from datetime import datetime, timedelta, timezone

import pytest

from company_report_orchestrator_test_helpers import successful_fake_provider
from persistence_test_helpers import FakeAsyncSession
from product_api.company_reports import build_company_report
from product_api.company_reports.persistence import (
    CompanyReportSnapshotError,
    CompanyReportStateConflictError,
    SafePersistenceError,
    create_pending_report,
    finalize_report,
    get_company_report,
    mark_report_failed,
)


@pytest.mark.asyncio
async def test_finalize_stores_report_datasets_and_provider_journal_atomically():
    session = FakeAsyncSession()
    pending = await create_pending_report(session, identifier="0000000000")
    report = await build_company_report("0000000000", provider=successful_fake_provider())
    report = report.model_copy(update={"report_id": pending.id})

    stored = await finalize_report(
        session,
        report,
        fresh_until=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    assert stored.lifecycle_status == report.status.value
    assert stored.report_version == report.report_version == "2"
    assert stored.normalized_snapshot is not None
    assert stored.snapshot_hash is not None
    assert len(session.datasets) == 3
    assert len(session.journals) == 3
    assert all(journal.cost_amount is None for journal in session.journals)
    assert all(journal.billing_units is None for journal in session.journals)
    assert session.commit_count == 0
    loaded = await get_company_report(session, pending.id)
    assert loaded == report


@pytest.mark.asyncio
async def test_finalize_same_hash_is_idempotent_and_changed_hash_conflicts():
    session = FakeAsyncSession()
    pending = await create_pending_report(session, identifier="0000000000")
    report = (await build_company_report("0000000000", provider=successful_fake_provider())).model_copy(
        update={"report_id": pending.id}
    )

    await finalize_report(session, report)
    dataset_count = len(session.datasets)
    journal_count = len(session.journals)
    same = await finalize_report(session, report)
    assert same.id == pending.id
    assert len(session.datasets) == dataset_count
    assert len(session.journals) == journal_count

    changed = report.model_copy(update={"usable_for_public_page": False})
    with pytest.raises(CompanyReportStateConflictError):
        await finalize_report(session, changed)


@pytest.mark.asyncio
async def test_mark_report_failed_stores_only_safe_error_without_snapshot():
    session = FakeAsyncSession()
    pending = await create_pending_report(session, identifier="0000000000")

    failed = await mark_report_failed(
        session,
        report_id=pending.id,
        safe_error=SafePersistenceError(
            error_type="DataNewtonAccessDeniedError",
            message="provider access was denied",
            retryable=False,
            request_id="safe-request",
        ),
    )

    assert failed.lifecycle_status == "failed"
    assert failed.normalized_snapshot is None
    assert failed.safe_error_snapshot == {
        "error_type": "DataNewtonAccessDeniedError",
        "message": "provider access was denied",
        "retryable": False,
        "request_id": "safe-request",
        "failed_at": failed.finished_at.isoformat(),
    }
    assert await get_company_report(session, pending.id) is None
