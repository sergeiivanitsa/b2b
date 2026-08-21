from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import sys
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

TESTS_UNIT = Path(__file__).resolve().parents[1] / "tests_unit"
if str(TESTS_UNIT) not in sys.path:
    sys.path.append(str(TESTS_UNIT))

from company_report_signal_test_helpers import (
    complete_company_report,
    counterparty_facts,
)
from product_api.company_reports.persistence.models import (
    CompanyReportRecord,
    CompanyReportSubject,
)
from product_api.company_reports.persistence.serialization import (
    calculate_company_report_snapshot_hash,
    company_report_to_snapshot,
)

pytestmark = pytest.mark.asyncio


async def _require_jobs_table(engine) -> None:
    async with engine.connect() as connection:
        exists = await connection.scalar(
            text("SELECT to_regclass('company_report_jobs')")
        )
    if exists is None:
        pytest.skip("company_report_jobs migration is not applied")


async def test_public_client_can_enqueue_reuse_and_poll_status(
    engine,
    async_client,
):
    await _require_jobs_table(engine)

    first = await async_client.post(
        "/company-reports",
        json={"inn": "7700000000"},
    )
    second = await async_client.post(
        "/company-reports",
        json={"inn": "770-000-0000"},
    )
    status_response = await async_client.get(
        "/company-reports/7700000000/status"
    )
    pending_response = await async_client.get(
        "/company-reports/7700000000"
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["report_id"] == second.json()["report_id"]
    assert first.json()["reused"] is False
    assert second.json()["reused"] is True
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "pending"
    assert pending_response.status_code == 409
    assert pending_response.json()["detail"]["code"] == "report_pending"


async def test_public_company_report_api_validation_and_missing_status(
    engine,
    async_client,
):
    await _require_jobs_table(engine)

    missing = await async_client.get(
        "/company-reports/7812345678/status"
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "company_report_not_found"

    malformed = await async_client.post(
        "/company-reports",
        json={"inn": "7700000000", "extra": True},
    )
    assert malformed.status_code == 422


@pytest.mark.parametrize("report_version", ["1", "2"])
async def test_public_h1_reads_stored_v1_and_v2_without_writes(
    engine,
    async_client,
    report_version,
):
    await _require_jobs_table(engine)
    now = datetime(2026, 8, 20, tzinfo=timezone.utc)
    counterparty = counterparty_facts().model_copy(
        update={"inn": "0000000000", "full_name": "ООО Интеграция"}
    )
    report = complete_company_report(
        counterparty=counterparty,
        report_version=report_version,
    ).model_copy(
        update={"report_id": uuid4(), "generated_at": now}
    )
    snapshot = company_report_to_snapshot(report)
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        subject = CompanyReportSubject(
            normalized_identifier="0000000000",
            identifier_type="legal_entity_inn",
        )
        session.add(subject)
        await session.flush()
        session.add(
            CompanyReportRecord(
                id=report.report_id,
                subject_id=subject.id,
                report_version=report.report_version,
                lifecycle_status="complete",
                started_at=now,
                generated_at=now,
                finished_at=now,
                normalized_snapshot=snapshot,
                snapshot_hash=calculate_company_report_snapshot_hash(snapshot),
                completeness_snapshot={},
                freshness_snapshot={},
                warnings_snapshot=[],
                usable_for_public_page=True,
                usable_for_future_scoring=True,
                created_at=now,
            )
        )
        await session.commit()
    async with AsyncSession(bind=engine) as session:
        before = await session.scalar(select(func.count(CompanyReportRecord.id)))
        before_record = await session.get(CompanyReportRecord, report.report_id)
        assert before_record is not None
        before_snapshot = deepcopy(before_record.normalized_snapshot)
        before_hash = before_record.snapshot_hash
    response = await async_client.get("/company-reports/0000000000/public-h1")
    assert response.status_code == 200
    assert response.json()["report_id"] == str(report.report_id)
    assert response.json()["report_version"] == report_version
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-robots-tag"] == "noindex,follow"
    async with AsyncSession(bind=engine) as session:
        after = await session.scalar(select(func.count(CompanyReportRecord.id)))
        after_record = await session.get(CompanyReportRecord, report.report_id)
        assert after_record is not None
        assert after_record.normalized_snapshot == before_snapshot == snapshot
        assert (
            after_record.snapshot_hash
            == before_hash
            == calculate_company_report_snapshot_hash(snapshot)
        )
    assert after == before == 1


async def test_public_h1_pending_and_query_rejection_have_exact_headers(
    engine,
    async_client,
):
    await _require_jobs_table(engine)
    pending = await async_client.post("/company-reports", json={"inn": "7700000000"})
    assert pending.status_code == 202
    h1 = await async_client.get("/company-reports/7700000000/public-h1")
    assert h1.status_code == 409
    assert h1.json() == {
        "detail": {
            "code": "report_pending",
            "message": "company report is pending",
        }
    }
    query = await async_client.get("/company-reports/7700000000/public-h1?x=1")
    assert query.status_code == 422
    assert query.json()["detail"][0]["loc"] == ["query", "x"]
    for response in (h1, query):
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-robots-tag"] == "noindex,follow"
