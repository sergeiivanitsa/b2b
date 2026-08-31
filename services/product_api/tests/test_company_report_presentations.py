import asyncio
import httpx
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from types import SimpleNamespace
from uuid import UUID, uuid4
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from product_api.main import app
from product_api.routers import company_report_presentations as presentations_router
from product_api.company_reports import worker as report_worker
from product_api.company_reports.company_urls import CanonicalUrlBinding
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
from product_api.company_reports.company_card_v2.public_h2 import (
    PublicH2ProjectionBindingV1,
    build_public_h2,
)
from product_api.company_reports.company_card_v2.public_h2_models import PublicH2Narrative
from product_api.company_reports.company_card_v2.service import (
    _v3_generation_identity,
    build_active_public_h2_for_pin,
)
from product_api.company_reports.company_card_v2.writer import (
    build_company_card_v2_snapshot_outcome,
)
from product_api.company_reports.persistence.models import (
    CompanyCardNarrativeArtifact,
    CompanyCardNarrativeJob,
    CompanyReportH2LifecycleHead,
    CompanyReportJob,
    CompanyReportPresentation,
    CompanyReportPresentationAssignment,
    CompanyReportPresentationAssignmentJournal,
    CompanyReportPresentationPin,
    CompanyReportPresentationStagedPointer,
    CompanyReportRecord,
    CompanyReportSubject,
)
from product_api.company_reports.persistence.errors import CompanyReportJobStateConflictError
from product_api.company_reports.persistence.jobs import (
    claim_next_job,
    complete_claimed_company_card_v2_job,
    enqueue_company_report_job,
)
from product_api.company_reports.persistence.presentations import (
    PresentationAssignmentConflict,
    _plan_active_h2_pin_locked,
    append_presentation_pin,
    append_resolved_h2_pin,
    assign_pin_cas,
    create_or_reuse_h2_presentation,
    create_or_reuse_unresolved_h2_pin,
    stage_h2_pin,
)
from product_api.company_reports.persistence.v3 import (
    calculate_company_card_v2_snapshot_hash,
    company_card_v2_from_snapshot,
    company_card_v2_to_snapshot,
)
from product_api.company_reports.company_card_v2.finance import build_chart_facts
from product_api.company_reports.company_card_v2.models import ArbitrationBasisV1, CompanyCardCounterpartyCoreV1, CompanyCardV2SnapshotV2, FinanceBasisV1, NarrativeEvidenceV1
from product_api.company_reports.persistence.presentations import H2_PUBLICATION_POLICY_VERSION, H2_PUBLICATION_POLICY_V2
from product_api.providers.datanewton import (
    ARBITRATION_CASES_ENDPOINT,
    COUNTERPARTY_ENDPOINT,
    FINANCE_ENDPOINT,
    DataNewtonResult,
    calculate_response_hash,
)
from product_api.settings import get_settings


def _presentation_settings(
    *,
    rollout_generation: int = 1,
    presentations_enabled: bool = True,
    writer_enabled: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        company_card_v2_presentations_enabled=presentations_enabled,
        company_card_v2_writer_enabled=writer_enabled,
        company_card_v2_rollout_generation=rollout_generation,
        company_card_v2_allowlist_inns=["7701234567", "7801234567"],
        company_card_v2_percentage_basis_points=0,
        company_card_v2_arbitration_collection_enabled=False,
        company_card_v2_arbitration_mask_active_key_id=None,
    )


def _bind_presentation_route_session(monkeypatch, engine) -> None:
    async def _get_test_session():
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            yield session

    monkeypatch.setattr(presentations_router, "get_session", _get_test_session)


def _assert_lifecycle_headers(response) -> None:
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-robots-tag"] == "noindex,follow"


def _valid_v3(report_id, inn: str) -> tuple[dict, str, CompanyCardV2SnapshotV2]:
    basis = FinanceBasisV1()
    snapshot = CompanyCardV2SnapshotV2(report_id=str(report_id), subject_inn=inn, target_inn=inn, rollout_config_generation=1, generated_at=datetime(2026, 8, 24, tzinfo=timezone.utc), counterparty=CompanyCardCounterpartyCoreV1(inn=inn, full_name="Тест"), finance_basis=basis, arbitration_basis=ArbitrationBasisV1(), chart_facts=build_chart_facts(basis), evidence_version="evidence_v1", privacy_version="privacy_v1", narrative_evidence=NarrativeEvidenceV1(limitation_code="primary_activity_not_admitted"))
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


_URL_PIPELINE_NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
_URL_PIPELINE_MASK_SECRET = b"iteration-26-url-pipeline-mask-key"


def _url_pipeline_result(
    *,
    inn: str,
    dataset: str,
    endpoint: str,
    payload: dict[str, object],
    request_parameters: dict[str, object],
    request_id: str | None,
    lexical_number_lexemes: dict[str, str] | None = None,
) -> DataNewtonResult:
    return DataNewtonResult(
        dataset=dataset,
        endpoint=endpoint,
        requested_identifier=inn,
        request_parameters=request_parameters,
        status_code=200,
        attempts=1,
        duration_ms=1,
        request_id=request_id,
        received_at=_URL_PIPELINE_NOW,
        raw_payload=payload,
        lexical_transport_valid=True,
        lexical_number_lexemes=lexical_number_lexemes or {},
        response_hash=calculate_response_hash(payload),
    )


class _UrlPipelineProvider:
    def __init__(self, inn: str) -> None:
        self.inn = inn

    async def fetch_counterparty(self, identifier, *, filters, request_id=None):
        assert identifier == self.inn
        payload = {
            "inn": self.inn,
            "company": {
                "company_names": {
                    "short_name": "ООО Ромашка",
                    "full_name": "Общество с ограниченной ответственностью Ромашка",
                },
                "opf": "ООО",
                "okveds": [],
            },
        }
        return _url_pipeline_result(
            inn=self.inn,
            dataset="counterparty",
            endpoint=COUNTERPARTY_ENDPOINT,
            payload=payload,
            request_parameters={"inn": self.inn, "filters": filters},
            request_id=request_id,
        )

    async def fetch_finance(self, identifier, *, request_id=None):
        assert identifier == self.inn
        return _url_pipeline_result(
            inn=self.inn,
            dataset="finance",
            endpoint=FINANCE_ENDPOINT,
            payload={},
            request_parameters={"inn": self.inn},
            request_id=request_id,
        )

    async def fetch_arbitration_cases(
        self,
        identifier,
        *,
        company_role,
        offset,
        limit,
        request_id,
    ):
        assert identifier == self.inn
        payload = {"total_cases": 0, "offset": 0, "limit": 1000}
        return _url_pipeline_result(
            inn=self.inn,
            dataset="arbitration_cases",
            endpoint=ARBITRATION_CASES_ENDPOINT,
            payload=payload,
            request_parameters={
                "inn": self.inn,
                "company_role": company_role,
                "offset": offset,
                "limit": limit,
            },
            request_id=request_id,
            lexical_number_lexemes={
                "/total_cases": "0",
                "/offset": "0",
                "/limit": "1000",
            },
        )


async def _store_url_pipeline_fallback_artifact(
    session: AsyncSession,
    *,
    report: CompanyReportRecord,
) -> tuple[CompanyCardNarrativeArtifact, PublicH2Narrative]:
    snapshot = company_card_v2_from_snapshot(report.normalized_snapshot)
    generation_identity = _v3_generation_identity(record=report, snapshot=snapshot)
    generation_key = identity_key(generation_identity)
    render_digest = sha256(FALLBACK_DESCRIPTION.encode("utf-8")).hexdigest()
    fallback_identity = identity_key(
        FallbackIdentityV1(
            generation_key=generation_key,
            fallback_catalog_version=FALLBACK_CATALOG_VERSION,
            fallback_profile_id=FALLBACK_PROFILE_ID,
            renderer_version=FALLBACK_RENDERER_VERSION,
            rendered_output_bytes_sha256=render_digest,
        )
    )
    job = CompanyCardNarrativeJob(
        report_id=report.id,
        snapshot_hash=report.snapshot_hash,
        generation_key=generation_key,
        identity_version="GenerationIdentityV2",
        generation_identity=asdict(generation_identity),
        state="fallback_finalized",
        available_at=_URL_PIPELINE_NOW,
        validation_codes=["feature_disabled"],
    )
    session.add(job)
    await session.flush()
    artifact = CompanyCardNarrativeArtifact(
        report_id=report.id,
        snapshot_hash=report.snapshot_hash,
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
        rendered_output_bytes_sha256=render_digest,
    )
    session.add(artifact)
    await session.flush()
    job.artifact_id = artifact.id
    narrative = PublicH2Narrative(
        mode="deterministic_fallback",
        renderer_version=FALLBACK_RENDERER_VERSION,
        description=FALLBACK_DESCRIPTION,
        statement_ids=(FALLBACK_PROFILE_ID,),
        comments=(),
        render_digest=render_digest,
    )
    await session.flush()
    return artifact, narrative


async def test_form_first_binding_survives_writer_worker_job_and_h2_pin_lifecycle(
    engine,
) -> None:
    inn = "7701234567"
    expected_path = f"/company/ooo-romashka-{inn}"
    mask_key_id = "active_2026"
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        _presentation, enqueued, _head = await create_or_reuse_h2_presentation(
            session,
            identifier=inn,
            rollout_generation=1,
            arbitration_collection_enabled=True,
            arbitration_mask_key_id=mask_key_id,
        )
        await session.commit()
        claimed = await claim_next_job(session, lease_seconds=60)
        assert claimed is not None and claimed.report_id == enqueued.report_id
        await session.commit()

    provider = _UrlPipelineProvider(inn)

    async def build_outcome(current):
        assert current == claimed
        return await build_company_card_v2_snapshot_outcome(
            provider=provider,
            report_id=current.report_id,
            subject_inn=current.normalized_identifier,
            target_inn=current.normalized_identifier,
            writer_profile=current.writer_profile,
            report_version=current.report_version,
            presentation_contract=current.presentation_contract,
            rollout_config_generation=current.rollout_generation,
            now=_URL_PIPELINE_NOW,
            arbitration_enabled=True,
            arbitration_operation_enabled=True,
            arbitration_key_id=mask_key_id,
            arbitration_key_secret=_URL_PIPELINE_MASK_SECRET,
            request_id=f"company-report:{current.report_id}",
        )

    settings = get_settings().model_copy(
        update={"company_card_v2_writer_enabled": True}
    )
    assert await report_worker.run_one_claimed_job(
        claimed,
        settings,
        session_factory=session_factory,
        v3_builder=build_outcome,
    ) is True
    # A terminal worker retry must reuse the exact writer binding and pin.
    assert await report_worker.run_one_claimed_job(
        claimed,
        settings,
        session_factory=session_factory,
        v3_builder=build_outcome,
    ) is True

    async with session_factory() as session:
        report = await session.get(CompanyReportRecord, claimed.report_id)
        subject = await session.get(CompanyReportSubject, claimed.subject_id)
        assert report is not None and subject is not None
        unresolved = list((await session.scalars(select(CompanyReportPresentationPin).where(
            CompanyReportPresentationPin.report_id == report.id,
            CompanyReportPresentationPin.narrative_binding_status == "unresolved",
        ))).all())
        assert len(unresolved) == 1
        assert unresolved[0].canonical_path == expected_path

        exact_outcome = await build_outcome(claimed)
        with pytest.raises(
            CompanyReportJobStateConflictError,
            match="completed pin lineage is invalid",
        ):
            await complete_claimed_company_card_v2_job(
                session,
                claimed=claimed,
                snapshot=exact_outcome.snapshot,
                lifecycle_status=exact_outcome.lifecycle_status,
                canonical_url_binding=CanonicalUrlBinding(
                    f"/company/ao-romashka-{inn}",
                    "ao",
                    "romashka",
                ),
            )
        await session.rollback()

    async with session_factory() as session:
        report = await session.get(CompanyReportRecord, claimed.report_id)
        assert report is not None
        snapshot = company_card_v2_from_snapshot(report.normalized_snapshot)
        artifact, narrative = await _store_url_pipeline_fallback_artifact(
            session,
            report=report,
        )
        staged_projection = build_public_h2(
            snapshot,
            narrative_binding=SimpleNamespace(narrative=narrative),
            projection_binding=PublicH2ProjectionBindingV1(
                projection_scope="staged_publication",
                canonical_path=expected_path,
                indexable=False,
                published_lastmod=None,
            ),
            finance_enabled=True,
            arbitration_enabled=True,
        )
        resolved, staged = await append_resolved_h2_pin(
            session,
            report=report,
            artifact=artifact,
            projection_digest=staged_projection.projection_digest,
        )
        assert resolved.canonical_path == expected_path
        assert staged.generation == resolved.generation

        active_projection = await build_active_public_h2_for_pin(
            session,
            record=report,
            source_pin=resolved,
            expected_subject_id=report.subject_id,
            expected_inn=inn,
            canonical_path=expected_path,
            indexable=False,
            published_lastmod=report.generated_at,
        )
        subject = await session.get(
            CompanyReportSubject,
            report.subject_id,
            with_for_update=True,
        )
        pins = list((await session.scalars(
            select(CompanyReportPresentationPin)
            .where(CompanyReportPresentationPin.subject_id == report.subject_id)
            .order_by(CompanyReportPresentationPin.generation)
            .with_for_update()
        )).all())
        assert subject is not None and report.generated_at is not None
        active = await _plan_active_h2_pin_locked(
            session,
            subject=subject,
            pins=pins,
            report=report,
            source_pin=resolved,
            expected_generation=resolved.generation + 1,
            projection_digest=active_projection.projection_digest,
            canonical_path=expected_path,
            indexable=False,
            published_lastmod=report.generated_at,
        )
        session.add(active)
        await session.flush()
        await session.commit()

    async with session_factory() as session:
        lifecycle = tuple((await session.execute(
            select(
                CompanyReportPresentationPin.generation,
                CompanyReportPresentationPin.canonical_path,
                CompanyReportPresentationPin.narrative_binding_status,
                CompanyReportPresentationPin.projection_scope,
            )
            .where(CompanyReportPresentationPin.report_id == claimed.report_id)
            .order_by(CompanyReportPresentationPin.generation)
        )).all())
        assert lifecycle == (
            (1, expected_path, "unresolved", "staged_publication"),
            (2, expected_path, "resolved", "staged_publication"),
            (3, expected_path, "resolved", "active_publication"),
        )


async def test_presentation_create_is_default_off_without_db_side_effect(async_client) -> None:
    response = await async_client.post("/company-report-presentations", json={"identifier": "7701234567"})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "company_public_h2_disabled"


async def test_rejected_presentation_selectors_create_no_postgresql_rows(
    async_client,
    engine,
    monkeypatch,
) -> None:
    _bind_presentation_route_session(monkeypatch, engine)
    monkeypatch.setattr(
        presentations_router,
        "get_settings",
        lambda: _presentation_settings(),
    )

    attempts = (
        ("?unknown=", {}, "presentation_query_forbidden"),
        (
            "?report_version=3&report_version=2",
            {},
            "presentation_query_forbidden",
        ),
        ("", {"X-Report-Version": ""}, "presentation_selector_forbidden"),
        (
            "",
            {"X-Writer-Profile": "company_card_v2_writer_v3"},
            "presentation_selector_forbidden",
        ),
    )
    for suffix, headers, expected_code in attempts:
        response = await async_client.post(
            f"/company-report-presentations{suffix}",
            json={"identifier": "7701234567"},
            headers=headers,
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == expected_code
        _assert_lifecycle_headers(response)

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        for model in (
            CompanyReportSubject,
            CompanyReportRecord,
            CompanyReportJob,
            CompanyReportPresentation,
            CompanyReportH2LifecycleHead,
        ):
            assert await session.scalar(
                select(func.count()).select_from(model)
            ) == 0


async def test_presentation_create_reuses_exact_binding_and_status_ignores_flag_flip(
    async_client,
    engine,
    monkeypatch,
) -> None:
    _bind_presentation_route_session(monkeypatch, engine)
    monkeypatch.setattr(
        presentations_router,
        "get_settings",
        lambda: _presentation_settings(),
    )

    first = await async_client.post(
        "/company-report-presentations",
        json={"identifier": "770 123 45 67"},
    )
    second = await async_client.post(
        "/company-report-presentations",
        json={"identifier": "7701234567"},
    )

    assert first.status_code == second.status_code == 202
    expected_keys = {
        "presentation_id",
        "presentation_contract",
        "report_id",
        "lifecycle_status",
        "public_read_path",
        "canonical_document_path",
        "reused",
    }
    assert set(first.json()) == set(second.json()) == expected_keys
    assert first.json() == {
        "presentation_id": second.json()["presentation_id"],
        "presentation_contract": "company_public_h2_v1",
        "report_id": second.json()["report_id"],
        "lifecycle_status": "pending",
        "public_read_path": "/company-reports/7701234567/public-h2",
        "canonical_document_path": None,
        "reused": False,
    }
    assert second.json()["reused"] is True
    _assert_lifecycle_headers(first)
    _assert_lifecycle_headers(second)

    presentation_id = UUID(first.json()["presentation_id"])
    report_id = UUID(first.json()["report_id"])
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        assert await session.scalar(
            select(func.count()).select_from(CompanyReportSubject)
        ) == 1
        assert await session.scalar(
            select(func.count()).select_from(CompanyReportRecord)
        ) == 1
        assert await session.scalar(
            select(func.count()).select_from(CompanyReportPresentation)
        ) == 1
        assert await session.scalar(
            select(func.count()).select_from(CompanyReportJob)
        ) == 1
        head = await session.scalar(select(CompanyReportH2LifecycleHead))
        assert head is not None
        assert head.presentation_id == presentation_id
        assert head.report_id == report_id
        assert head.head_generation == 1

    def _status_must_not_read_settings():
        raise AssertionError("presentation status must not re-resolve rollout settings")

    monkeypatch.setattr(
        presentations_router,
        "get_settings",
        _status_must_not_read_settings,
    )
    status_response = await async_client.get(
        f"/company-report-presentations/{presentation_id}/status"
    )

    assert status_response.status_code == 200
    assert status_response.json() == {
        **first.json(),
        "reused": True,
    }
    _assert_lifecycle_headers(status_response)


async def test_presentation_status_returns_exact_lifecycle_and_safe_missing(
    async_client,
    engine,
    monkeypatch,
) -> None:
    _bind_presentation_route_session(monkeypatch, engine)
    monkeypatch.setattr(
        presentations_router,
        "get_settings",
        lambda: _presentation_settings(),
    )
    created = await async_client.post(
        "/company-report-presentations",
        json={"identifier": "7701234567"},
    )
    assert created.status_code == 202
    presentation_id = UUID(created.json()["presentation_id"])
    report_id = UUID(created.json()["report_id"])

    def _status_must_not_read_settings():
        raise AssertionError("presentation status must not re-resolve rollout settings")

    monkeypatch.setattr(
        presentations_router,
        "get_settings",
        _status_must_not_read_settings,
    )
    for lifecycle_status in ("pending", "complete", "partial", "failed"):
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            report = await session.get(CompanyReportRecord, report_id)
            assert report is not None
            report.lifecycle_status = lifecycle_status
            await session.commit()
        response = await async_client.get(
            f"/company-report-presentations/{presentation_id}/status"
        )
        assert response.status_code == 200
        assert response.json()["lifecycle_status"] == lifecycle_status
        assert response.json()["report_id"] == str(report_id)
        assert response.json()["reused"] is True
        assert "status" not in response.json()

    missing = await async_client.get(
        f"/company-report-presentations/{uuid4()}/status"
    )
    assert missing.status_code == 404
    assert missing.json() == {
        "detail": {
            "code": "presentation_not_found",
            "message": "presentation was not found",
        }
    }
    _assert_lifecycle_headers(missing)


async def test_old_presentation_status_stays_bound_after_new_h2_head(
    async_client,
    engine,
    monkeypatch,
) -> None:
    _bind_presentation_route_session(monkeypatch, engine)
    monkeypatch.setattr(
        presentations_router,
        "get_settings",
        lambda: _presentation_settings(rollout_generation=1),
    )
    first = await async_client.post(
        "/company-report-presentations",
        json={"identifier": "7701234567"},
    )
    assert first.status_code == 202
    first_presentation_id = UUID(first.json()["presentation_id"])
    first_report_id = UUID(first.json()["report_id"])

    now = datetime(2026, 8, 27, 12, tzinfo=timezone.utc)
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        report = await session.get(CompanyReportRecord, first_report_id)
        job = await session.scalar(
            select(CompanyReportJob).where(
                CompanyReportJob.report_id == first_report_id
            )
        )
        assert report is not None and job is not None
        report.lifecycle_status = "failed"
        report.finished_at = now
        job.state = "failed"
        job.finished_at = now
        job.safe_failure_code = "report_execution_failed"
        await session.commit()

    monkeypatch.setattr(
        presentations_router,
        "get_settings",
        lambda: _presentation_settings(rollout_generation=2),
    )
    second = await async_client.post(
        "/company-report-presentations",
        json={"identifier": "7701234567"},
    )
    assert second.status_code == 202
    assert second.json()["presentation_id"] != str(first_presentation_id)
    assert second.json()["report_id"] != str(first_report_id)
    second_report_id = UUID(second.json()["report_id"])

    def _status_must_not_read_settings():
        raise AssertionError("presentation status must not re-resolve rollout settings")

    monkeypatch.setattr(
        presentations_router,
        "get_settings",
        _status_must_not_read_settings,
    )
    old_status = await async_client.get(
        f"/company-report-presentations/{first_presentation_id}/status"
    )
    new_status = await async_client.get(
        f"/company-report-presentations/{second.json()['presentation_id']}/status"
    )
    assert old_status.status_code == new_status.status_code == 200
    assert old_status.json()["report_id"] == str(first_report_id)
    assert old_status.json()["lifecycle_status"] == "failed"
    assert new_status.json()["report_id"] == second.json()["report_id"]
    assert new_status.json()["lifecycle_status"] == "pending"
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        head = await session.scalar(select(CompanyReportH2LifecycleHead))
        assert head is not None
        assert head.presentation_id == UUID(second.json()["presentation_id"])
        assert head.report_id == second_report_id
        assert head.head_generation == 2

        old_presentation = await session.get(
            CompanyReportPresentation,
            first_presentation_id,
        )
        assert old_presentation is not None
        old_presentation.rollout_generation = 999
        await session.commit()

    corrupt_old_status = await async_client.get(
        f"/company-report-presentations/{first_presentation_id}/status"
    )
    assert corrupt_old_status.status_code == 500
    assert corrupt_old_status.json() == {
        "detail": {
            "code": "presentation_invalid",
            "message": "presentation binding is invalid",
        }
    }
    assert str(second_report_id) not in corrupt_old_status.text
    _assert_lifecycle_headers(corrupt_old_status)


async def test_incompatible_h1_job_leaves_no_h2_presentation_or_head(
    async_client,
    engine,
    monkeypatch,
) -> None:
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        await enqueue_company_report_job(session, "7801234567")
        await session.commit()

    _bind_presentation_route_session(monkeypatch, engine)
    monkeypatch.setattr(
        presentations_router,
        "get_settings",
        lambda: _presentation_settings(),
    )
    response = await async_client.post(
        "/company-report-presentations",
        json={"identifier": "7801234567"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "report_writer_profile_conflict"
    _assert_lifecycle_headers(response)

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        assert await session.scalar(
            select(func.count()).select_from(CompanyReportPresentation)
        ) == 0
        assert await session.scalar(
            select(func.count()).select_from(CompanyReportH2LifecycleHead)
        ) == 0


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
        canonical_path = f"/company/ooo-test-{subject.normalized_identifier}"
        pin = await append_presentation_pin(
            session,
            subject_id=subject.id,
            report=report,
            contract="company_public_h2_v1",
            generation=1,
            canonical_path=canonical_path,
            **h2_identity,
        )
        assert await append_presentation_pin(
            session,
            subject_id=subject.id,
            report=report,
            contract="company_public_h2_v1",
            generation=1,
            canonical_path=canonical_path,
            **h2_identity,
        ) is pin
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
