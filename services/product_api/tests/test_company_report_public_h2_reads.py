from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.company_reports.company_card_v2.narrative.catalog import (
    FALLBACK_CATALOG_VERSION,
    FALLBACK_DESCRIPTION,
    FALLBACK_PROFILE_ID,
    FALLBACK_RENDERER_VERSION,
)
from product_api.company_reports.company_card_v2.narrative.identity import (
    FallbackIdentityV1,
    identity_key,
)
from product_api.company_reports.company_card_v2.public_h2 import build_public_h2
from product_api.company_reports.company_card_v2.public_h2_models import (
    PublicH2Narrative,
)
from product_api.company_reports.company_card_v2.service import (
    PublicH2Invalid,
    PublicH2NotEligible,
    _legacy_generation_identity,
    _v3_generation_identity,
    resolve_public_h2,
)
from product_api.company_reports.persistence.models import (
    CompanyCardNarrativeArtifact,
    CompanyCardNarrativeJob,
    CompanyCardNarrativeOutbox,
    CompanyReportDataset,
    CompanyReportH2LifecycleHead,
    CompanyReportJob,
    CompanyReportPresentation,
    CompanyReportPresentationAssignment,
    CompanyReportPresentationPin,
    CompanyReportPresentationStagedPointer,
    CompanyReportProviderRequest,
    CompanyReportRecord,
    CompanyReportSubject,
)
from product_api.company_reports.persistence.serialization import (
    calculate_company_report_snapshot_hash,
)
from product_api.company_reports.persistence.v3 import (
    calculate_company_card_v2_snapshot_hash,
    company_card_v2_from_snapshot,
)
from product_api.providers.datanewton import DataNewtonClient
from product_api.routers import company_reports as company_reports_router


pytestmark = pytest.mark.asyncio
_FIXTURES = Path(__file__).parents[1] / "tests_unit" / "fixtures" / "company_reports"
_CARD_FIXTURES = Path(__file__).parents[1] / "tests_unit" / "fixtures" / "company_card_v2"


def _legacy_snapshot(*, report_id: str, generated_at: str, version: str = "2"):
    raw = json.loads(
        (_FIXTURES / (
            "snapshot_v1_legacy.json" if version == "1" else "snapshot_v2_exact.json"
        )).read_text(encoding="utf-8")
    )
    source = raw["counterparty"]["source"]
    source["received_at"] = generated_at
    raw.update({
        "report_id": report_id,
        "generated_at": generated_at,
        "target_identifier": "7701234567",
    })
    raw["counterparty"].update({
        "inn": "7701234567",
        "full_name": "Тестовое общество",
        "short_name": "Тест",
        "address": {"line_address": "г. Москва", "is_inaccuracy": False},
    })
    raw["datasets"]["counterparty"]["source"] = dict(source)
    raw["freshness"]["generated_at"] = generated_at
    return raw


async def _store_legacy_report(
    engine,
    *,
    report_id: str = "00000000-0000-4000-8000-000000000001",
    generated_at: str = "2026-08-24T12:00:00Z",
    with_fallback: bool,
) -> tuple[UUID, str]:
    raw = _legacy_snapshot(report_id=report_id, generated_at=generated_at)
    snapshot_hash = calculate_company_report_snapshot_hash(raw)
    now = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        subject = await session.scalar(select(CompanyReportSubject).where(
            CompanyReportSubject.normalized_identifier == "7701234567"
        ))
        if subject is None:
            subject = CompanyReportSubject(
                normalized_identifier="7701234567",
                identifier_type="legal_entity_inn",
            )
            session.add(subject)
            await session.flush()
        record = CompanyReportRecord(
            id=UUID(report_id),
            subject_id=subject.id,
            report_version="2",
            writer_profile="h1_legacy_writer_v2",
            presentation_contract="company_public_h1_v1",
            rollout_generation=0,
            lifecycle_status="partial",
            started_at=now,
            generated_at=now,
            finished_at=now,
            normalized_snapshot=raw,
            snapshot_hash=snapshot_hash,
            warnings_snapshot=[],
            usable_for_public_page=True,
            usable_for_future_scoring=False,
        )
        session.add(record)
        await session.flush()
        if not with_fallback:
            session.add(CompanyCardNarrativeOutbox(
                report_id=record.id,
                snapshot_hash=snapshot_hash,
                event_kind="initialize_narrative_v1",
                state="pending",
                available_at=now,
            ))
            await session.commit()
            return record.id, snapshot_hash

        generation_identity = _legacy_generation_identity(record=record)
        generation_key = identity_key(generation_identity)
        digest = sha256(FALLBACK_DESCRIPTION.encode("utf-8")).hexdigest()
        fallback_identity = identity_key(FallbackIdentityV1(
            generation_key=generation_key,
            fallback_catalog_version=FALLBACK_CATALOG_VERSION,
            fallback_profile_id=FALLBACK_PROFILE_ID,
            renderer_version=FALLBACK_RENDERER_VERSION,
            rendered_output_bytes_sha256=digest,
        ))
        job = CompanyCardNarrativeJob(
            report_id=record.id,
            snapshot_hash=snapshot_hash,
            generation_key=generation_key,
            identity_version="GenerationIdentityV2",
            generation_identity=asdict(generation_identity),
            state="fallback_finalized",
            available_at=now,
            validation_codes=["legacy_snapshot"],
        )
        session.add(job)
        await session.flush()
        artifact = CompanyCardNarrativeArtifact(
            report_id=record.id,
            snapshot_hash=snapshot_hash,
            generation_key=generation_key,
            binding_kind="fallback",
            binding_key=fallback_identity,
            fallback_identity=fallback_identity,
            rendered_description=FALLBACK_DESCRIPTION,
            rendered_comments=[],
            statement_ids=[FALLBACK_PROFILE_ID],
            evidence_ids=[],
            phrase_trace=[{
                "scalar_start": 0,
                "scalar_end": len(FALLBACK_DESCRIPTION),
                "statement_id": FALLBACK_PROFILE_ID,
                "evidence_ids": [],
            }],
            validation_codes=[],
            renderer_version=FALLBACK_RENDERER_VERSION,
            rendered_output_bytes_sha256=digest,
        )
        session.add(artifact)
        await session.flush()
        job.artifact_id = artifact.id
        session.add(CompanyCardNarrativeOutbox(
            report_id=record.id,
            snapshot_hash=snapshot_hash,
            event_kind="initialize_narrative_v1",
            state="processed",
            available_at=now,
            generation_key=generation_key,
            processed_at=now,
        ))
        await session.commit()
        return record.id, snapshot_hash


async def _store_resolved_v3_fallback(
    engine,
    *,
    publication_policy_version: str = "company_public_h2_publication_v1",
) -> tuple[UUID, str]:
    arbitration_enabled = (
        publication_policy_version == "company_public_h2_publication_v3"
    )
    fixture_name = (
        "snapshot_v3_arbitration_v3.json"
        if arbitration_enabled
        else "snapshot_v3_complete.json"
    )
    raw = json.loads(
        (_CARD_FIXTURES / fixture_name).read_text(encoding="utf-8")
    )
    if not arbitration_enabled:
        raw["snapshot_schema_version"] = "company_card_v2_snapshot_v2"
    raw["narrative_evidence"] = {
        "schema_version": "company_card_v2_narrative_evidence_v1",
        "primary_activity_parser_version": "company_card_v2_primary_activity_parser_v1",
        "primary_activity_evidence_version": "company_card_v2_okved_primary_activity_evidence_v1",
        "source_profile_version": "company_card_v2_counterparty_okved_primary_v1",
        "primary_activity": {
            "code": "62.01",
            "label": "Разработка компьютерного программного обеспечения",
            "is_primary": True,
        },
        "limitation_code": None,
    }
    snapshot = company_card_v2_from_snapshot(raw)
    report_id = UUID(snapshot.report_id)
    snapshot_hash = calculate_company_card_v2_snapshot_hash(snapshot)
    now = snapshot.generated_at
    fallback_digest = sha256(FALLBACK_DESCRIPTION.encode("utf-8")).hexdigest()
    fallback_narrative = PublicH2Narrative(
        mode="deterministic_fallback",
        renderer_version=FALLBACK_RENDERER_VERSION,
        description=FALLBACK_DESCRIPTION,
        statement_ids=(FALLBACK_PROFILE_ID,),
        comments=(),
        render_digest=fallback_digest,
    )

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        subject = CompanyReportSubject(
            normalized_identifier=snapshot.subject_inn,
            identifier_type="legal_entity_inn",
        )
        session.add(subject)
        await session.flush()
        record = CompanyReportRecord(
            id=report_id,
            subject_id=subject.id,
            report_version="3",
            writer_profile="company_card_v2_writer_v3",
            presentation_contract="company_public_h2_v1",
            rollout_generation=snapshot.rollout_config_generation,
            arbitration_collection_enabled=arbitration_enabled,
            arbitration_mask_key_id=(
                snapshot.arbitration_basis.mask_key_id
                if arbitration_enabled
                else None
            ),
            lifecycle_status="complete",
            started_at=now,
            generated_at=now,
            finished_at=now,
            normalized_snapshot=raw,
            snapshot_hash=snapshot_hash,
            warnings_snapshot=[],
            usable_for_public_page=False,
            usable_for_future_scoring=False,
        )
        session.add(record)
        await session.flush()
        presentation = CompanyReportPresentation(
            subject_id=subject.id,
            report_id=record.id,
            presentation_contract="company_public_h2_v1",
            rollout_generation=snapshot.rollout_config_generation,
        )
        session.add(presentation)
        await session.flush()

        generation_identity = _v3_generation_identity(
            record=record,
            snapshot=snapshot,
        )
        generation_key = identity_key(generation_identity)
        fallback_identity = identity_key(FallbackIdentityV1(
            generation_key=generation_key,
            fallback_catalog_version=FALLBACK_CATALOG_VERSION,
            fallback_profile_id=FALLBACK_PROFILE_ID,
            renderer_version=FALLBACK_RENDERER_VERSION,
            rendered_output_bytes_sha256=fallback_digest,
        ))
        job = CompanyCardNarrativeJob(
            report_id=record.id,
            snapshot_hash=snapshot_hash,
            generation_key=generation_key,
            identity_version="GenerationIdentityV2",
            generation_identity=asdict(generation_identity),
            state="fallback_finalized",
            available_at=now,
            validation_codes=["feature_disabled"],
        )
        session.add(job)
        await session.flush()
        artifact = CompanyCardNarrativeArtifact(
            report_id=record.id,
            snapshot_hash=snapshot_hash,
            generation_key=generation_key,
            binding_kind="fallback",
            binding_key=fallback_identity,
            fallback_identity=fallback_identity,
            rendered_description=FALLBACK_DESCRIPTION,
            rendered_comments=[],
            statement_ids=[FALLBACK_PROFILE_ID],
            evidence_ids=[],
            phrase_trace=[{
                "scalar_start": 0,
                "scalar_end": len(FALLBACK_DESCRIPTION),
                "statement_id": FALLBACK_PROFILE_ID,
                "evidence_ids": [],
            }],
            validation_codes=[],
            renderer_version=FALLBACK_RENDERER_VERSION,
            rendered_output_bytes_sha256=fallback_digest,
        )
        session.add(artifact)
        await session.flush()
        job.artifact_id = artifact.id
        projection = build_public_h2(
            snapshot,
            narrative_binding=SimpleNamespace(narrative=fallback_narrative),
            finance_enabled=publication_policy_version
            in {
                "company_public_h2_publication_v2",
                "company_public_h2_publication_v3",
            },
            arbitration_enabled=arbitration_enabled,
        )
        pin = CompanyReportPresentationPin(
            subject_id=subject.id,
            report_id=record.id,
            presentation_contract="company_public_h2_v1",
            generation=1,
            snapshot_hash=snapshot_hash,
            chart_facts_version=snapshot.chart_facts.version,
            chart_facts_hash=snapshot.chart_facts.hash,
            evidence_registry_version=snapshot.evidence_version,
            publication_policy_version=publication_policy_version,
            canonical_path=None,
            indexable=False,
            published_lastmod=None,
            projection_digest=projection.projection_digest,
            narrative_binding_status="resolved",
            narrative_binding_kind="fallback",
            narrative_binding_key=fallback_identity,
        )
        session.add(pin)
        await session.flush()
        session.add(CompanyReportPresentationStagedPointer(
            subject_id=subject.id,
            presentation_contract="company_public_h2_v1",
            generation=pin.generation,
        ))
        await session.commit()
        return record.id, snapshot_hash


async def _read_state(engine, report_id: UUID):
    async with AsyncSession(bind=engine) as session:
        record = await session.get(CompanyReportRecord, report_id)
        counts = []
        for model in (
            CompanyCardNarrativeOutbox,
            CompanyCardNarrativeJob,
            CompanyCardNarrativeArtifact,
            CompanyReportPresentationPin,
            CompanyReportPresentation,
            CompanyReportH2LifecycleHead,
            CompanyReportPresentationAssignment,
            CompanyReportPresentationStagedPointer,
        ):
            counts.append(await session.scalar(select(func.count()).select_from(model)))
        return deepcopy(record.normalized_snapshot), record.snapshot_hash, counts


async def _company_report_table_counts(engine) -> dict[str, int]:
    models = (
        CompanyReportSubject,
        CompanyReportRecord,
        CompanyReportJob,
        CompanyReportDataset,
        CompanyReportProviderRequest,
        CompanyReportPresentation,
        CompanyReportH2LifecycleHead,
        CompanyReportPresentationPin,
        CompanyReportPresentationStagedPointer,
        CompanyReportPresentationAssignment,
        CompanyCardNarrativeOutbox,
        CompanyCardNarrativeJob,
        CompanyCardNarrativeArtifact,
    )
    async with AsyncSession(bind=engine) as session:
        return {
            model.__tablename__: int(
                await session.scalar(select(func.count()).select_from(model)) or 0
            )
            for model in models
        }


async def test_public_h2_disabled_get_and_head_are_no_store(async_client) -> None:
    get_response = await async_client.get("/company-reports/7701234567/public-h2")
    head_response = await async_client.head("/company-reports/7701234567/public-h2")
    assert get_response.status_code == head_response.status_code == 404
    assert get_response.json()["detail"]["code"] == "company_public_h2_disabled"
    assert head_response.content == b""
    assert get_response.headers["cache-control"] == "no-store"


async def test_public_h2_enabled_no_subject_uses_frozen_not_found_code_without_writes(
    async_client,
    engine,
    monkeypatch,
) -> None:
    async def override_session():
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            yield session

    async def provider_call_forbidden(*_args, **_kwargs):
        raise AssertionError("public H2 no-subject read must not call a provider")

    for method_name in (
        "fetch_batch_cards",
        "fetch_counterparty",
        "fetch_finance",
        "fetch_tax_info",
        "fetch_arbitration_cases",
        "fetch_fssp",
        "fetch_bankruptcy",
    ):
        monkeypatch.setattr(
            DataNewtonClient, method_name, provider_call_forbidden
        )

    before = await _company_report_table_counts(engine)
    statements: list[str] = []

    def capture_statements(
        _conn, _cursor, statement, _parameters, _context, _executemany
    ) -> None:
        statements.append(statement)

    monkeypatch.setattr(
        company_reports_router, "h2_cohort_selected", lambda **_kwargs: True
    )
    monkeypatch.setattr(company_reports_router, "get_session", override_session)
    event.listen(engine.sync_engine, "before_cursor_execute", capture_statements)
    try:
        response = await async_client.get(
            "/company-reports/7701234567/public-h2"
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture_statements)

    after = await _company_report_table_counts(engine)
    assert response.status_code == 404
    assert response.json() == {
        "detail": {
            "code": "company_report_not_found",
            "message": "company card v2 was not found",
        }
    }
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-robots-tag"] == "noindex,follow"
    assert before == after
    assert statements
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)


async def test_legacy_saved_fallback_read_is_repeatable_and_executes_only_selects(engine) -> None:
    report_id, _ = await _store_legacy_report(engine, with_fallback=True)
    before = await _read_state(engine, report_id)
    statements: list[str] = []

    def capture_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", capture_selects)
    try:
        async with AsyncSession(bind=engine) as session:
            first = await resolve_public_h2(session, inn="7701234567")
            second = await resolve_public_h2(session, inn="7701234567")
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture_selects)

    after = await _read_state(engine, report_id)
    assert first == second
    assert first.report_version == "2"
    assert first.snapshot_capability == "legacy_read_only"
    assert first.projection_scope == "latest_unpublished"
    assert first.indexable is False
    assert first.narrative.mode == "deterministic_fallback"
    assert before == after
    assert statements
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)


async def test_resolved_v3_saved_fallback_recomputes_exact_pin_with_selects_only(engine) -> None:
    report_id, _ = await _store_resolved_v3_fallback(engine)
    before = await _read_state(engine, report_id)
    statements: list[str] = []

    def capture_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", capture_selects)
    try:
        async with AsyncSession(bind=engine) as session:
            first = await resolve_public_h2(session, inn="7701234567")
            second = await resolve_public_h2(session, inn="7701234567")
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture_selects)

    after = await _read_state(engine, report_id)
    assert first == second
    assert first.report_version == "3"
    assert first.snapshot_capability == "card_v2"
    assert first.indexable is False
    assert first.narrative.mode == "deterministic_fallback"
    assert before == after
    assert statements
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)


@pytest.mark.parametrize(
    "corruption",
    ("pin_projection_digest", "generation_identity", "phrase_trace"),
)
async def test_resolved_v3_saved_result_corruption_is_terminal_500(
    engine,
    corruption: str,
) -> None:
    report_id, _ = await _store_resolved_v3_fallback(engine)
    async with AsyncSession(bind=engine) as session:
        if corruption == "pin_projection_digest":
            pin = await session.scalar(select(CompanyReportPresentationPin).where(
                CompanyReportPresentationPin.report_id == report_id
            ))
            pin.projection_digest = "f" * 64
        elif corruption == "generation_identity":
            job = await session.scalar(select(CompanyCardNarrativeJob).where(
                CompanyCardNarrativeJob.report_id == report_id
            ))
            job.generation_identity = {
                **job.generation_identity,
                "prompt_version": "stale",
            }
        else:
            artifact = await session.scalar(select(CompanyCardNarrativeArtifact).where(
                CompanyCardNarrativeArtifact.report_id == report_id
            ))
            artifact.phrase_trace = [{
                **artifact.phrase_trace[0],
                "scalar_end": len(FALLBACK_DESCRIPTION) - 1,
            }]
        await session.commit()

    async with AsyncSession(bind=engine) as session:
        with pytest.raises(PublicH2Invalid) as caught:
            await resolve_public_h2(session, inn="7701234567")
    assert caught.value.code == "public_projection_invalid"


async def test_legacy_missing_binding_is_409(engine) -> None:
    await _store_legacy_report(engine, with_fallback=False)
    async with AsyncSession(bind=engine) as session:
        with pytest.raises(PublicH2NotEligible) as caught:
            await resolve_public_h2(session, inn="7701234567")
    assert caught.value.code == "report_not_eligible"


async def test_legacy_corrupt_saved_binding_is_500(engine) -> None:
    report_id, _ = await _store_legacy_report(
        engine,
        with_fallback=True,
    )
    async with AsyncSession(bind=engine) as session:
        artifact = await session.scalar(select(CompanyCardNarrativeArtifact).where(
            CompanyCardNarrativeArtifact.report_id == report_id
        ))
        artifact.rendered_description = artifact.rendered_description + "x"
        await session.commit()
    async with AsyncSession(bind=engine) as session:
        with pytest.raises(PublicH2Invalid) as caught:
            await resolve_public_h2(session, inn="7701234567")
    assert caught.value.code == "public_projection_invalid"


@pytest.mark.parametrize(
    "corruption",
    ("generation_identity", "job_state", "artifact_reference"),
)
async def test_legacy_processed_saved_result_job_corruption_is_500(
    engine,
    corruption: str,
) -> None:
    report_id, _ = await _store_legacy_report(engine, with_fallback=True)
    async with AsyncSession(bind=engine) as session:
        job = await session.scalar(select(CompanyCardNarrativeJob).where(
            CompanyCardNarrativeJob.report_id == report_id
        ))
        if corruption == "generation_identity":
            job.generation_identity = {
                **job.generation_identity,
                "snapshot_schema_version": "stale",
            }
        elif corruption == "job_state":
            job.state = "ready"
        else:
            job.artifact_id = None
        await session.commit()

    async with AsyncSession(bind=engine) as session:
        with pytest.raises(PublicH2Invalid) as caught:
            await resolve_public_h2(session, inn="7701234567")
    assert caught.value.code == "public_projection_invalid"
