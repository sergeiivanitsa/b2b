from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.company_reports.persistence.models import (
    CompanyCardNarrativeArtifact,
    CompanyReportRecord,
    CompanyReportSubject,
)
from product_api.company_reports.persistence.narratives import (
    initialize_narrative_generation,
    resolve_exact_narrative_binding,
)
from product_api.company_reports.company_card_v2.narrative.identity import (
    GenerationIdentityV2,
    identity_key,
)


pytestmark = pytest.mark.asyncio


async def test_exact_binding_resolver_never_selects_another_report_or_writes(engine):
    now = datetime(2026, 8, 24, tzinfo=UTC)
    snapshot_hash, binding_key = "c" * 64, "e" * 64
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        subject = CompanyReportSubject(normalized_identifier="7701234567", identifier_type="legal_entity_inn")
        session.add(subject); await session.flush()
        report = CompanyReportRecord(subject_id=subject.id, report_version="3", writer_profile="company_card_v2_writer_v3", presentation_contract="company_public_h2_v1", rollout_generation=1, lifecycle_status="complete", started_at=now, generated_at=now, normalized_snapshot={}, snapshot_hash=snapshot_hash, warnings_snapshot=[], usable_for_public_page=False, usable_for_future_scoring=False)
        session.add(report); await session.flush()
        identity = GenerationIdentityV2(
            report_id=str(report.id), snapshot_hash=snapshot_hash,
            chart_facts_hash="d" * 64, evidence_registry_version="evidence_v1",
            statement_catalog_version="statement_v1", template_catalog_version="template_v1",
            prompt_version="prompt_v1", json_schema_version="schema_v1",
            policy_version="policy_v1", renderer_version="renderer_v1",
            gateway_profile_version="gateway_v1", fallback_catalog_version="fallback_v1",
            snapshot_schema_version="company_card_v2_snapshot_v2",
            narrative_evidence_schema_version="evidence_schema_v1",
            primary_activity_parser_version="parser_v1",
            primary_activity_evidence_version="activity_evidence_v1",
            insight_catalog_version="insight_v1", connector_catalog_version="connector_v1",
            input_schema_version="input_v1",
        )
        generation_key = identity_key(identity)
        await initialize_narrative_generation(session, report_id=report.id, snapshot_hash=snapshot_hash, generation_key=generation_key, identity=identity, now=now)
        session.add(CompanyCardNarrativeArtifact(
            report_id=report.id, snapshot_hash=snapshot_hash,
            generation_key=generation_key, binding_kind="fallback",
            binding_key=binding_key, fallback_identity=binding_key,
            rendered_description="saved fallback", rendered_comments=[],
            statement_ids=["fallback_profile_any_v1"], evidence_ids=[],
            phrase_trace=[], validation_codes=[],
            renderer_version="company_card_h2_fallback_renderer_v1",
            rendered_output_bytes_sha256="f" * 64,
        ))
        await session.commit()

    async with AsyncSession(bind=engine) as session:
        found = await resolve_exact_narrative_binding(session, report_id=report.id, snapshot_hash=snapshot_hash, generation_key=generation_key)
        missing = await resolve_exact_narrative_binding(session, report_id=report.id, snapshot_hash="0" * 64, generation_key=generation_key)
        assert found is not None and found.binding_key == binding_key
        assert missing is None
