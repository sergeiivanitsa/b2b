import json

import pytest

from company_report_orchestrator_test_helpers import successful_fake_provider
from persistence_test_helpers import FakeAsyncSession
from product_api.company_reports import build_company_report
from product_api.company_reports.persistence import (
    SafePersistenceError,
    company_report_to_snapshot,
    create_pending_report,
    finalize_report,
    mark_report_failed,
)


@pytest.mark.asyncio
async def test_snapshots_and_errors_have_no_raw_or_secret_markers():
    session = FakeAsyncSession()
    pending = await create_pending_report(session, identifier="0000000000")
    report = (await build_company_report("0000000000", provider=successful_fake_provider())).model_copy(
        update={"report_id": pending.id}
    )
    await finalize_report(session, report)
    snapshot_text = json.dumps(report.normalized_snapshot if hasattr(report, "normalized_snapshot") else company_report_to_snapshot(report), ensure_ascii=False)
    assert "raw_payload" not in snapshot_text
    assert "DATANEWTON_API_KEY" not in snapshot_text
    assert "api-secret" not in snapshot_text
    assert "0000000000" in snapshot_text
    assert "0000000000" not in repr(session.reports[0])

    failed_pending = await create_pending_report(session, identifier="111111111111")
    await mark_report_failed(
        session,
        report_id=failed_pending.id,
        safe_error=SafePersistenceError(
            error_type="provider_error",
            message="safe error",
            request_id="request-safe",
        ),
    )
    assert "raw response" not in json.dumps(session.reports[-1].safe_error_snapshot)
    assert "api-secret" not in json.dumps(session.reports[-1].safe_error_snapshot)
