import httpx
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.main import app
from product_api.company_reports.persistence.models import CompanyReportRecord, CompanyReportSubject
from product_api.company_reports.persistence.presentations import PresentationAssignmentConflict, append_presentation_pin, assign_pin_cas, stage_h2_pin


async def test_presentation_create_is_default_off_without_db_side_effect(async_client) -> None:
    response = await async_client.post("/company-report-presentations", json={"identifier": "7701234567"})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "company_public_h2_disabled"


async def test_internal_pin_stage_and_assignment_are_exact_and_immutable(engine) -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        subject = CompanyReportSubject(normalized_identifier="7701234567", identifier_type="legal_entity_inn")
        session.add(subject); await session.flush()
        report = CompanyReportRecord(id=uuid4(), subject_id=subject.id, report_version="3", writer_profile="company_card_v2_writer_v3", presentation_contract="company_public_h2_v1", rollout_generation=1, lifecycle_status="complete", started_at=now, generated_at=now, finished_at=now, normalized_snapshot={"report_version": "3"}, snapshot_hash="a" * 64, completeness_snapshot={}, freshness_snapshot={}, warnings_snapshot=[], usable_for_public_page=False, usable_for_future_scoring=False)
        session.add(report); await session.flush()
        pin = await append_presentation_pin(session, subject_id=subject.id, report=report, contract="company_public_h2_v1", generation=1)
        assert await append_presentation_pin(session, subject_id=subject.id, report=report, contract="company_public_h2_v1", generation=1) is pin
        staged = await stage_h2_pin(session, subject_id=subject.id, pin=pin, expected_generation=1)
        assignment = await assign_pin_cas(session, subject_id=subject.id, pin=pin, expected_generation=1)
        assert staged.pin_id == assignment.pin_id == pin.id
        with pytest.raises(PresentationAssignmentConflict):
            await assign_pin_cas(session, subject_id=subject.id, pin=pin, expected_generation=1)
