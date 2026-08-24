import httpx
from datetime import datetime, timezone
from uuid import uuid4
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.main import app
from product_api.company_reports.persistence.models import CompanyReportRecord, CompanyReportSubject
from product_api.company_reports.persistence.presentations import PresentationAssignmentConflict, append_presentation_pin, assign_pin_cas, stage_h2_pin
from product_api.company_reports.persistence.v3 import calculate_company_card_v2_snapshot_hash, company_card_v2_to_snapshot
from product_api.company_reports.company_card_v2.finance import build_chart_facts
from product_api.company_reports.company_card_v2.models import ArbitrationBasisV1, CompanyCardCounterpartyCoreV1, CompanyCardV2Snapshot, FinanceBasisV1
from product_api.company_reports.persistence.presentations import H2_PUBLICATION_POLICY_VERSION


def _valid_v3(report_id, inn: str) -> tuple[dict, str, CompanyCardV2Snapshot]:
    basis = FinanceBasisV1()
    snapshot = CompanyCardV2Snapshot(report_id=str(report_id), subject_inn=inn, target_inn=inn, rollout_config_generation=1, generated_at=datetime(2026, 8, 24, tzinfo=timezone.utc), counterparty=CompanyCardCounterpartyCoreV1(inn=inn, full_name="Тест"), finance_basis=basis, arbitration_basis=ArbitrationBasisV1(), chart_facts=build_chart_facts(basis), evidence_version="evidence_v1", privacy_version="privacy_v1")
    raw = company_card_v2_to_snapshot(snapshot)
    return raw, calculate_company_card_v2_snapshot_hash(snapshot), snapshot


async def test_presentation_create_is_default_off_without_db_side_effect(async_client) -> None:
    response = await async_client.post("/company-report-presentations", json={"identifier": "7701234567"})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "company_public_h2_disabled"


async def test_internal_pin_stage_and_assignment_are_exact_and_immutable(engine) -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        subject = CompanyReportSubject(normalized_identifier="7701234567", identifier_type="legal_entity_inn")
        session.add(subject); await session.flush()
        report_id = uuid4(); raw, snapshot_hash, snapshot = _valid_v3(report_id, subject.normalized_identifier)
        report = CompanyReportRecord(id=report_id, subject_id=subject.id, report_version="3", writer_profile="company_card_v2_writer_v3", presentation_contract="company_public_h2_v1", rollout_generation=1, lifecycle_status="complete", started_at=now, generated_at=now, finished_at=now, normalized_snapshot=raw, snapshot_hash=snapshot_hash, completeness_snapshot={}, freshness_snapshot={}, warnings_snapshot=[], usable_for_public_page=False, usable_for_future_scoring=False)
        session.add(report); await session.flush()
        h2_identity = {
            "chart_facts_version": snapshot.chart_facts.version,
            "chart_facts_hash": snapshot.chart_facts.hash,
            "evidence_registry_version": snapshot.evidence_version,
            "publication_policy_version": H2_PUBLICATION_POLICY_VERSION,
        }
        pin = await append_presentation_pin(session, subject_id=subject.id, report=report, contract="company_public_h2_v1", generation=1, **h2_identity)
        assert await append_presentation_pin(session, subject_id=subject.id, report=report, contract="company_public_h2_v1", generation=1, **h2_identity) is pin
        staged = await stage_h2_pin(session, subject_id=subject.id, pin=pin, expected_generation=1)
        assert (staged.subject_id, staged.presentation_contract, staged.generation) == (
            pin.subject_id,
            pin.presentation_contract,
            pin.generation,
        )
        # H2 pins are deliberately unresolved/noindex in iteration 20. No
        # assignment or journal mutation is allowed before a later narrative
        # activation iteration.
        with pytest.raises(PresentationAssignmentConflict, match="unresolved H2 pin"):
            await assign_pin_cas(session, subject_id=subject.id, pin=pin, expected_generation=1)


async def test_h2_pin_database_shape_rejects_missing_evidence_and_cross_subject_report(engine) -> None:
    """PostgreSQL checks/FKs, rather than helper validation, enforce the pin boundary."""
    now = datetime.now(timezone.utc)
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        first = CompanyReportSubject(normalized_identifier="7701234567", identifier_type="legal_entity_inn")
        second = CompanyReportSubject(normalized_identifier="7701234568", identifier_type="legal_entity_inn")
        session.add_all((first, second)); await session.flush()
        report = CompanyReportRecord(
            id=uuid4(), subject_id=first.id, report_version="3",
            writer_profile="company_card_v2_writer_v3", presentation_contract="company_public_h2_v1",
            rollout_generation=1, lifecycle_status="complete", started_at=now,
            generated_at=now, finished_at=now, normalized_snapshot={"report_version": "3"},
            snapshot_hash="a" * 64, completeness_snapshot={}, freshness_snapshot={},
            warnings_snapshot=[], usable_for_public_page=False, usable_for_future_scoring=False,
        )
        session.add(report); await session.flush()
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(text(
                    "INSERT INTO company_report_presentation_pins "
                    "(subject_id, report_id, presentation_contract, generation, snapshot_hash, indexable, narrative_binding_status) "
                    "VALUES (:subject, :report, 'company_public_h2_v1', 1, :hash, false, 'unresolved')"
                ), {"subject": first.id, "report": report.id, "hash": "a" * 64})
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(text(
                    "INSERT INTO company_report_presentation_pins "
                    "(subject_id, report_id, presentation_contract, generation, snapshot_hash, chart_facts_version, chart_facts_hash, evidence_registry_version, publication_policy_version, indexable, narrative_binding_status) "
                    "VALUES (:subject, :report, 'company_public_h2_v1', 1, :hash, 'chart_facts_v2', :chart_hash, 'evidence_registry_v1', 'company_public_h2_v1', false, 'unresolved')"
                ), {"subject": second.id, "report": report.id, "hash": "a" * 64, "chart_hash": "b" * 64})
