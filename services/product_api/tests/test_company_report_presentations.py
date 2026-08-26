import asyncio
import httpx
from datetime import datetime, timezone
from hashlib import sha256
from uuid import uuid4
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.main import app
from product_api.company_reports.persistence.models import (
    CompanyCardNarrativeArtifact,
    CompanyCardNarrativeJob,
    CompanyReportPresentation,
    CompanyReportPresentationAssignment,
    CompanyReportPresentationAssignmentJournal,
    CompanyReportPresentationPin,
    CompanyReportPresentationStagedPointer,
    CompanyReportRecord,
    CompanyReportSubject,
)
from product_api.company_reports.persistence.presentations import (
    PresentationAssignmentConflict,
    append_presentation_pin,
    append_resolved_h2_pin,
    assign_pin_cas,
    create_or_reuse_unresolved_h2_pin,
    stage_h2_pin,
)
from product_api.company_reports.persistence.v3 import calculate_company_card_v2_snapshot_hash, company_card_v2_to_snapshot
from product_api.company_reports.company_card_v2.finance import build_chart_facts
from product_api.company_reports.company_card_v2.models import ArbitrationBasisV1, CompanyCardCounterpartyCoreV1, CompanyCardV2Snapshot, FinanceBasisV1
from product_api.company_reports.persistence.presentations import H2_PUBLICATION_POLICY_VERSION, H2_PUBLICATION_POLICY_V2


def _valid_v3(report_id, inn: str) -> tuple[dict, str, CompanyCardV2Snapshot]:
    basis = FinanceBasisV1()
    snapshot = CompanyCardV2Snapshot(report_id=str(report_id), subject_inn=inn, target_inn=inn, rollout_config_generation=1, generated_at=datetime(2026, 8, 24, tzinfo=timezone.utc), counterparty=CompanyCardCounterpartyCoreV1(inn=inn, full_name="Тест"), finance_basis=basis, arbitration_basis=ArbitrationBasisV1(), chart_facts=build_chart_facts(basis), evidence_version="evidence_v1", privacy_version="privacy_v1")
    raw = company_card_v2_to_snapshot(snapshot)
    return raw, calculate_company_card_v2_snapshot_hash(snapshot), snapshot


async def _store_v3_report(session: AsyncSession, *, inn: str = "7701234567"):
    now = datetime(2026, 8, 25, tzinfo=timezone.utc)
    subject = CompanyReportSubject(
        normalized_identifier=inn,
        identifier_type="legal_entity_inn",
    )
    session.add(subject)
    await session.flush()
    report_id = uuid4()
    raw, snapshot_hash, snapshot = _valid_v3(report_id, inn)
    report = CompanyReportRecord(
        id=report_id,
        subject_id=subject.id,
        report_version="3",
        writer_profile="company_card_v2_writer_v3",
        presentation_contract="company_public_h2_v1",
        rollout_generation=1,
        lifecycle_status="complete",
        started_at=now,
        generated_at=snapshot.generated_at,
        finished_at=now,
        normalized_snapshot=raw,
        snapshot_hash=snapshot_hash,
        completeness_snapshot={},
        freshness_snapshot={},
        warnings_snapshot=[],
        usable_for_public_page=False,
        usable_for_future_scoring=False,
    )
    session.add(report)
    await session.flush()
    session.add(
        CompanyReportPresentation(
            subject_id=subject.id,
            report_id=report.id,
            presentation_contract="company_public_h2_v1",
            rollout_generation=1,
        )
    )
    await session.flush()
    await create_or_reuse_unresolved_h2_pin(session, report=report)
    return subject, report, snapshot


async def _store_unpinned_v3_reports(
    session: AsyncSession,
    *,
    inn: str = "7701234567",
    count: int = 2,
) -> tuple[CompanyReportSubject, list[CompanyReportRecord]]:
    now = datetime(2026, 8, 25, tzinfo=timezone.utc)
    subject = CompanyReportSubject(
        normalized_identifier=inn,
        identifier_type="legal_entity_inn",
    )
    session.add(subject)
    await session.flush()
    reports: list[CompanyReportRecord] = []
    for _ in range(count):
        report_id = uuid4()
        raw, snapshot_hash, snapshot = _valid_v3(report_id, inn)
        report = CompanyReportRecord(
            id=report_id,
            subject_id=subject.id,
            report_version="3",
            writer_profile="company_card_v2_writer_v3",
            presentation_contract="company_public_h2_v1",
            rollout_generation=1,
            lifecycle_status="complete",
            started_at=now,
            generated_at=snapshot.generated_at,
            finished_at=now,
            normalized_snapshot=raw,
            snapshot_hash=snapshot_hash,
            completeness_snapshot={},
            freshness_snapshot={},
            warnings_snapshot=[],
            usable_for_public_page=False,
            usable_for_future_scoring=False,
        )
        session.add(report)
        await session.flush()
        session.add(
            CompanyReportPresentation(
                subject_id=subject.id,
                report_id=report.id,
                presentation_contract="company_public_h2_v1",
                rollout_generation=1,
            )
        )
        reports.append(report)
    await session.flush()
    return subject, reports


async def _store_narrative_artifact(
    session: AsyncSession,
    *,
    report: CompanyReportRecord,
    binding_kind: str,
) -> CompanyCardNarrativeArtifact:
    now = datetime(2026, 8, 25, tzinfo=timezone.utc)
    generation_key = sha256(
        f"presentation-boundary-generation:{binding_kind}".encode("ascii")
    ).hexdigest()
    binding_key = sha256(
        f"presentation-boundary-binding:{binding_kind}".encode("ascii")
    ).hexdigest()
    description = f"Сохранённое описание: {binding_kind}."
    render_digest = sha256(description.encode("utf-8")).hexdigest()
    is_ai = binding_kind == "artifact"
    plan_bytes = b"{}" if is_ai else None
    job = CompanyCardNarrativeJob(
        report_id=report.id,
        snapshot_hash=report.snapshot_hash,
        generation_key=generation_key,
        identity_version="GenerationIdentityV1",
        generation_identity={"identity_version": "GenerationIdentityV1"},
        state="finalized" if is_ai else "fallback_finalized",
        available_at=now,
        gateway_dispatch_id=uuid4() if is_ai else None,
        dispatch_started_at=now if is_ai else None,
        response_received_at=now if is_ai else None,
        resolved_model_version="narrative-test-model-v1" if is_ai else None,
        validation_codes=[] if is_ai else ["feature_disabled"],
    )
    session.add(job)
    await session.flush()
    artifact = CompanyCardNarrativeArtifact(
        report_id=report.id,
        snapshot_hash=report.snapshot_hash,
        generation_key=generation_key,
        binding_kind=binding_kind,
        binding_key=binding_key,
        artifact_identity=binding_key if is_ai else None,
        fallback_identity=None if is_ai else binding_key,
        resolved_model_version="narrative-test-model-v1" if is_ai else None,
        raw_model_output="{}" if is_ai else None,
        validated_render_plan_cjson=plan_bytes,
        validated_render_plan_bytes_sha256=(
            sha256(plan_bytes).hexdigest() if plan_bytes is not None else None
        ),
        rendered_description=description,
        rendered_comments=[],
        statement_ids=["presentation_boundary_statement"],
        evidence_ids=[],
        phrase_trace=[],
        validation_codes=[],
        renderer_version=(
            "company_card_h2_renderer_v1"
            if is_ai
            else "company_card_h2_fallback_renderer_v1"
        ),
        rendered_output_bytes_sha256=render_digest,
    )
    session.add(artifact)
    await session.flush()
    job.artifact_id = artifact.id
    await session.flush()
    return artifact


async def test_presentation_create_is_default_off_without_db_side_effect(async_client) -> None:
    response = await async_client.post("/company-report-presentations", json={"identifier": "7701234567"})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "company_public_h2_disabled"


async def test_concurrent_unresolved_v2_pins_serialize_subject_generations(
    engine,
) -> None:
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        subject, reports = await _store_unpinned_v3_reports(session)
        subject_id = subject.id
        expected = {
            report.id: report.snapshot_hash
            for report in reports
        }
        await session.commit()

    started = [asyncio.Event(), asyncio.Event()]

    async def pin_once(index: int, report_id):
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            report = await session.get(CompanyReportRecord, report_id)
            assert report is not None
            started[index].set()
            pin = await create_or_reuse_unresolved_h2_pin(session, report=report)
            await session.commit()
            return pin

    tasks = [
        asyncio.create_task(pin_once(index, report_id))
        for index, report_id in enumerate(expected)
    ]
    await asyncio.gather(*(event.wait() for event in started))
    first, second = await asyncio.wait_for(asyncio.gather(*tasks), timeout=5)

    assert {first.generation, second.generation} == {1, 2}
    assert {first.report_id, second.report_id} == set(expected)

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        pins = list(
            (
                await session.scalars(
                    select(CompanyReportPresentationPin)
                    .where(
                        CompanyReportPresentationPin.subject_id == subject_id,
                        CompanyReportPresentationPin.presentation_contract
                        == "company_public_h2_v1",
                    )
                    .order_by(CompanyReportPresentationPin.generation)
                )
            ).all()
        )
        assert [pin.generation for pin in pins] == [1, 2]
        assert {pin.report_id for pin in pins} == set(expected)
        for pin in pins:
            report = await session.get(CompanyReportRecord, pin.report_id)
            assert report is not None
            snapshot = _valid_v3(report.id, subject.normalized_identifier)[2]
            assert (
                pin.snapshot_hash,
                pin.chart_facts_version,
                pin.chart_facts_hash,
                pin.evidence_registry_version,
                pin.publication_policy_version,
                pin.indexable,
                pin.projection_digest,
                pin.narrative_binding_status,
                pin.narrative_binding_kind,
                pin.narrative_binding_key,
            ) == (
                expected[pin.report_id],
                snapshot.chart_facts.version,
                snapshot.chart_facts.hash,
                snapshot.evidence_version,
                H2_PUBLICATION_POLICY_V2,
                False,
                None,
                "unresolved",
                None,
                None,
            )

        retried = []
        for report_id in expected:
            report = await session.get(CompanyReportRecord, report_id)
            assert report is not None
            retried.append(
                await create_or_reuse_unresolved_h2_pin(session, report=report)
            )
        await session.commit()
        assert {pin.generation for pin in retried} == {1, 2}
        assert await session.scalar(
            select(func.count()).select_from(CompanyReportPresentationPin)
        ) == 2

    corrupted_report_id = next(iter(expected))
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        report = await session.get(CompanyReportRecord, corrupted_report_id)
        assert report is not None
        pin = await session.scalar(
            select(CompanyReportPresentationPin)
            .where(
                CompanyReportPresentationPin.subject_id == subject_id,
                CompanyReportPresentationPin.report_id == corrupted_report_id,
            )
            .with_for_update()
        )
        assert pin is not None
        pin.publication_policy_version = H2_PUBLICATION_POLICY_VERSION
        await session.flush()
        with pytest.raises(
            PresentationAssignmentConflict,
            match="mixed policy or identity",
        ):
            await create_or_reuse_unresolved_h2_pin(session, report=report)
        await session.rollback()

    async with AsyncSession(bind=engine) as session:
        pins = list(
            (
                await session.scalars(
                    select(CompanyReportPresentationPin)
                    .where(
                        CompanyReportPresentationPin.subject_id == subject_id,
                        CompanyReportPresentationPin.presentation_contract
                        == "company_public_h2_v1",
                    )
                    .order_by(CompanyReportPresentationPin.generation)
                )
            ).all()
        )
        assert [pin.generation for pin in pins] == [1, 2]
        assert {
            pin.publication_policy_version for pin in pins
        } == {H2_PUBLICATION_POLICY_V2}


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
        assert (
            pin.indexable,
            pin.projection_digest,
            pin.narrative_binding_status,
            pin.narrative_binding_kind,
            pin.narrative_binding_key,
        ) == (False, None, "unresolved", None, None)
        # H2 pins are deliberately unresolved/noindex in iteration 20. No
        # assignment or journal mutation is allowed before a later narrative
        # activation iteration.
        with pytest.raises(PresentationAssignmentConflict, match="unresolved H2 pin"):
            await assign_pin_cas(session, subject_id=subject.id, pin=pin, expected_generation=1)
        assert await session.scalar(
            select(func.count()).select_from(CompanyReportPresentationAssignment)
        ) == 0
        assert await session.scalar(
            select(func.count()).select_from(
                CompanyReportPresentationAssignmentJournal
            )
        ) == 0


@pytest.mark.parametrize("binding_kind", ("artifact", "fallback"))
async def test_resolved_h2_pin_accepts_exact_saved_narrative_composite_binding(
    engine,
    binding_kind: str,
) -> None:
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        subject, report, snapshot = await _store_v3_report(session)
        artifact = await _store_narrative_artifact(
            session,
            report=report,
            binding_kind=binding_kind,
        )
        projection_digest = sha256(
            f"presentation-projection:{binding_kind}".encode("ascii")
        ).hexdigest()
        pin, staged = await append_resolved_h2_pin(
            session,
            report=report,
            artifact=artifact,
            projection_digest=projection_digest,
        )
        await session.commit()

        assert (
            pin.subject_id,
            pin.report_id,
            pin.snapshot_hash,
            pin.chart_facts_version,
            pin.chart_facts_hash,
            pin.evidence_registry_version,
            pin.publication_policy_version,
            pin.indexable,
            pin.projection_digest,
            pin.narrative_binding_status,
            pin.narrative_binding_kind,
            pin.narrative_binding_key,
        ) == (
            subject.id,
            report.id,
            report.snapshot_hash,
            snapshot.chart_facts.version,
            snapshot.chart_facts.hash,
            snapshot.evidence_version,
            H2_PUBLICATION_POLICY_V2,
            False,
            projection_digest,
            "resolved",
            binding_kind,
            artifact.binding_key,
        )
        assert (
            staged.subject_id,
            staged.presentation_contract,
            staged.generation,
        ) == (subject.id, "company_public_h2_v1", pin.generation)

        # Narrative resolution still does not authorize publication assignment.
        with pytest.raises(PresentationAssignmentConflict):
            await assign_pin_cas(
                session,
                subject_id=subject.id,
                pin=pin,
                expected_generation=pin.generation,
            )
        assert await session.scalar(
            select(func.count()).select_from(CompanyReportPresentationAssignment)
        ) == 0
        assert await session.scalar(
            select(func.count()).select_from(
                CompanyReportPresentationAssignmentJournal
            )
        ) == 0


async def test_resolved_h2_pin_rejects_corrupt_artifact_identity_without_side_effects(
    engine,
) -> None:
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        subject, report, _snapshot = await _store_v3_report(session)
        artifact = await _store_narrative_artifact(
            session,
            report=report,
            binding_kind="fallback",
        )
        artifact_id = artifact.id
        original_binding_key = artifact.binding_key
        await session.commit()

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        report = await session.get(CompanyReportRecord, report.id)
        artifact = await session.get(CompanyCardNarrativeArtifact, artifact_id)
        assert report is not None and artifact is not None
        artifact.binding_key = "0" * 64
        with pytest.raises(
            PresentationAssignmentConflict,
            match="resolved H2 pin identity is invalid",
        ):
            await append_resolved_h2_pin(
                session,
                report=report,
                artifact=artifact,
                projection_digest="1" * 64,
            )
        await session.rollback()

    async with AsyncSession(bind=engine) as session:
        artifact = await session.get(CompanyCardNarrativeArtifact, artifact_id)
        assert artifact is not None and artifact.binding_key == original_binding_key
        assert await session.scalar(
            select(func.count()).select_from(CompanyReportPresentationPin)
        ) == 1
        assert await session.scalar(
            select(func.count()).select_from(
                CompanyReportPresentationStagedPointer
            )
        ) == 0
        assert await session.scalar(
            select(func.count()).select_from(CompanyReportPresentationAssignment)
        ) == 0


async def test_resolved_h2_pin_database_rejects_missing_narrative_binding(
    engine,
) -> None:
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        subject, report, snapshot = await _store_v3_report(session)
        subject_id, report_id = subject.id, report.id
        snapshot_hash = report.snapshot_hash
        await session.commit()

    async with AsyncSession(bind=engine) as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    "INSERT INTO company_report_presentation_pins "
                    "(subject_id, report_id, presentation_contract, generation, "
                    "snapshot_hash, chart_facts_version, chart_facts_hash, "
                    "evidence_registry_version, publication_policy_version, "
                    "indexable, projection_digest, narrative_binding_status, "
                    "narrative_binding_kind, narrative_binding_key) "
                    "VALUES (:subject_id, :report_id, 'company_public_h2_v1', 1, "
                    ":snapshot_hash, :chart_version, :chart_hash, :evidence_version, "
                    ":policy_version, false, :projection_digest, 'resolved', "
                    "'fallback', :missing_binding_key)"
                ),
                {
                    "subject_id": subject_id,
                    "report_id": report_id,
                    "snapshot_hash": snapshot_hash,
                    "chart_version": snapshot.chart_facts.version,
                    "chart_hash": snapshot.chart_facts.hash,
                    "evidence_version": snapshot.evidence_version,
                    "policy_version": H2_PUBLICATION_POLICY_VERSION,
                    "projection_digest": "2" * 64,
                    "missing_binding_key": "3" * 64,
                },
            )
            # The composite FK is intentionally deferred so the narrative job
            # and artifact can be finalized atomically.  Force its boundary in
            # this test to prove a pin cannot survive without its exact row.
            await session.execute(
                text(
                    "SET CONSTRAINTS "
                    "fk_company_report_h2_pin_narrative_binding IMMEDIATE"
                )
            )
        await session.rollback()

    async with AsyncSession(bind=engine) as session:
        assert await session.scalar(
            select(func.count()).select_from(CompanyReportPresentationPin)
        ) == 1
        assert await session.scalar(
            select(func.count()).select_from(CompanyReportPresentationAssignment)
        ) == 0


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
