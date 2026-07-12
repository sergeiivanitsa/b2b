from datetime import datetime, timezone

import pytest

from persistence_test_helpers import FakeAsyncSession
from product_api.company_reports.persistence import (
    create_pending_report,
    get_latest_run_status_by_identifier,
    get_or_create_subject,
)


@pytest.mark.asyncio
async def test_pending_creation_normalizes_subject_and_is_idempotent():
    session = FakeAsyncSession()

    first = await create_pending_report(
        session,
        identifier="000-000-0000",
        request_id="pending-request",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    second = await create_pending_report(
        session,
        identifier="0000000000",
        request_id="another-request",
    )

    assert first.id == second.id
    assert len(session.subjects) == 1
    assert len(session.reports) == 1
    assert first.lifecycle_status == "pending"
    assert first.normalized_snapshot is None
    assert first.safe_error_snapshot is None
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_different_subjects_can_have_pending_and_status_query_sees_pending():
    session = FakeAsyncSession()
    first = await create_pending_report(session, identifier="0000000000")
    second = await create_pending_report(session, identifier="111111111111")

    status = await get_latest_run_status_by_identifier(session, "000-000-0000")

    assert first.subject_id != second.subject_id
    assert status is not None
    assert status.lifecycle_status == "pending"
    assert status.report_id == first.id


@pytest.mark.asyncio
async def test_get_or_create_subject_returns_existing_record():
    session = FakeAsyncSession()
    first = await get_or_create_subject(session, "0000000000000")
    second = await get_or_create_subject(session, "000-000-0000-000")

    assert first.id == second.id
    assert first.identifier_type == "ogrn"
