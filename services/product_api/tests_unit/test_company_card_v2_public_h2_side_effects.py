from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from sqlalchemy.sql import Select

from product_api.company_reports.company_card_v2 import service
from product_api.company_reports.company_card_v2.canonical_json import canonical_json_bytes
from product_api.company_reports.company_card_v2.narrative.catalog import (
    CONNECTOR_IDS,
    FALLBACK_CATALOG_VERSION,
    FALLBACK_DESCRIPTION,
    FALLBACK_PROFILE_ID,
    FALLBACK_RENDERER_VERSION,
    INTRO_TEMPLATE_ID,
    OUTPUT_SCHEMA_VERSION,
    RENDERER_VERSION,
    STATEMENT_IDS,
)
from product_api.company_reports.company_card_v2.narrative.identity import (
    ArtifactIdentityV1,
    FallbackIdentityV1,
    identity_key,
)
from product_api.company_reports.company_card_v2.narrative.models import (
    NarrativeEvidenceEnvelope,
)
from product_api.company_reports.company_card_v2.narrative.validation import (
    validate_render_plan,
)
from product_api.company_reports.company_card_v2.public_h2 import build_public_h2
from product_api.company_reports.company_card_v2.public_h2_models import (
    PublicH2Narrative,
)
from product_api.company_reports.company_card_v2.service import h2_cohort_selected
from product_api.company_reports.persistence.serialization import (
    calculate_company_report_snapshot_hash,
)
from product_api.company_reports.persistence.v3 import (
    calculate_company_card_v2_snapshot_hash,
    company_card_v2_from_snapshot,
)


_FIXTURES = Path(__file__).parent / "fixtures" / "company_reports"
_CARD_FIXTURES = Path(__file__).parent / "fixtures" / "company_card_v2"


def test_default_off_h2_cohort_prevents_any_selection_before_persistence() -> None:
    settings = type("Settings", (), {
        "company_card_v2_presentations_enabled": False,
        "company_card_v2_rollout_generation": 0,
        "company_card_v2_allowlist_inns": [],
        "company_card_v2_percentage_basis_points": 10_000,
    })()
    assert not h2_cohort_selected(inn="7701234567", settings=settings)


def test_public_resolver_import_does_not_load_narrative_runtime_service() -> None:
    source_root = str(Path(__file__).parents[1] / "src")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        (source_root, environment.get("PYTHONPATH", ""))
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import product_api.company_reports.company_card_v2.service; "
                "assert "
                "'product_api.company_reports.company_card_v2.narrative.service' "
                "not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert result.returncode == 0, result.stderr


class _ReadOnlySession:
    def __init__(self, values):
        self.values = iter(values)
        self.scalar_calls = 0
        self.get_calls = 0

    async def scalar(self, _statement):
        self.scalar_calls += 1
        return next(self.values)

    async def execute(self, _statement):
        raise AssertionError("public H2 resolver must not execute a write-capable path")

    async def get(self, _model, _key):
        self.get_calls += 1
        return None

    def add(self, _value):
        raise AssertionError("public H2 resolver must not add rows")

    async def flush(self):
        raise AssertionError("public H2 resolver must not flush")

    async def commit(self):
        raise AssertionError("public H2 resolver must not commit")


@pytest.mark.asyncio
async def test_unbound_v3_resolver_is_read_only_and_fails_closed() -> None:
    subject = type("Subject", (), {"id": "subject-id"})()
    session = _ReadOnlySession((subject, None, None, "v3-report-id"))

    with pytest.raises(service.PublicH2NotEligible) as caught:
        await service.resolve_public_h2(session, inn="7701234567")

    assert caught.value.code == "report_not_eligible"
    assert session.scalar_calls == 4
    assert session.get_calls == 1


class _V3SelectOnlySession:
    def __init__(self, presentation, job, artifact):
        self.scalar_values = iter((presentation, job))
        self.artifact = artifact
        self.select_count = 0

    async def scalar(self, statement):
        assert isinstance(statement, Select)
        self.select_count += 1
        return next(self.scalar_values)

    async def get(self, model, key):
        self.select_count += 1
        assert model.__name__ == "CompanyCardNarrativeArtifact"
        assert key == self.artifact.id
        return self.artifact

    async def execute(self, _statement):
        raise AssertionError("V3 H2 resolution must use SELECT-only reads")

    def add(self, _value):
        raise AssertionError("V3 H2 resolution must not add rows")

    async def flush(self):
        raise AssertionError("V3 H2 resolution must not flush")

    async def commit(self):
        raise AssertionError("V3 H2 resolution must not commit")

    async def rollback(self):
        raise AssertionError("V3 H2 resolution must not rollback")


def _v3_saved_result(kind: str):
    raw = json.loads(
        (_CARD_FIXTURES / "snapshot_v3_complete.json").read_text(encoding="utf-8")
    )
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
    record = SimpleNamespace(
        id=report_id,
        subject_id="subject-id",
        report_version="3",
        writer_profile="company_card_v2_writer_v3",
        presentation_contract="company_public_h2_v1",
        rollout_generation=1,
        lifecycle_status="complete",
        generated_at=snapshot.generated_at,
        normalized_snapshot=raw,
        snapshot_hash=snapshot_hash,
    )
    generation_identity = service._v3_generation_identity(
        record=record,
        snapshot=snapshot,
    )
    generation_key = identity_key(generation_identity)
    artifact_id = uuid4()
    now = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)

    if kind == "fallback":
        rendered_digest = sha256(FALLBACK_DESCRIPTION.encode("utf-8")).hexdigest()
        binding_key = identity_key(FallbackIdentityV1(
            generation_key=generation_key,
            fallback_catalog_version=FALLBACK_CATALOG_VERSION,
            fallback_profile_id=FALLBACK_PROFILE_ID,
            renderer_version=FALLBACK_RENDERER_VERSION,
            rendered_output_bytes_sha256=rendered_digest,
        ))
        narrative = PublicH2Narrative(
            mode="deterministic_fallback",
            renderer_version=FALLBACK_RENDERER_VERSION,
            description=FALLBACK_DESCRIPTION,
            statement_ids=(FALLBACK_PROFILE_ID,),
            comments=(),
            render_digest=rendered_digest,
        )
        artifact = SimpleNamespace(
            id=artifact_id,
            report_id=report_id,
            snapshot_hash=snapshot_hash,
            generation_key=generation_key,
            binding_kind="fallback",
            binding_key=binding_key,
            artifact_identity=None,
            fallback_identity=binding_key,
            resolved_model_version=None,
            raw_model_output=None,
            validated_render_plan_cjson=None,
            validated_render_plan_bytes_sha256=None,
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
            rendered_output_bytes_sha256=rendered_digest,
        )
        job_state = "fallback_finalized"
        job_validation_codes = ["feature_disabled"]
        job_model = None
        dispatch_id = dispatch_started_at = response_received_at = None
    else:
        plan = {
            "output_schema_version": OUTPUT_SCHEMA_VERSION,
            "description_plan": {
                "intro_template_id": INTRO_TEMPLATE_ID,
                "statement_ids": list(STATEMENT_IDS),
                "connector_ids": list(CONNECTOR_IDS),
            },
            "chart_comments": [],
        }
        plan_bytes = canonical_json_bytes(plan)
        plan_hash = sha256(plan_bytes).hexdigest()
        evidence = NarrativeEvidenceEnvelope(
            evidence_registry_version=snapshot.evidence_version,
            primary_activity_label=(
                snapshot.narrative_evidence.primary_activity.label
            ),
        )
        rendered = validate_render_plan(plan, evidence)
        rendered_digest = sha256(rendered.description.encode("utf-8")).hexdigest()
        resolved_model = "gpt-test-exact-v1"
        binding_key = identity_key(ArtifactIdentityV1(
            generation_key=generation_key,
            resolved_model_version=resolved_model,
            validated_render_plan_bytes_sha256=plan_hash,
            rendered_output_bytes_sha256=rendered_digest,
        ))
        phrase_trace = [{
            "scalar_start": trace.start,
            "scalar_end": trace.end,
            "statement_id": trace.statement_id,
            "evidence_ids": list(trace.evidence_ids),
        } for trace in rendered.phrase_trace]
        evidence_ids = []
        for trace in rendered.phrase_trace:
            for evidence_id in trace.evidence_ids:
                if evidence_id not in evidence_ids:
                    evidence_ids.append(evidence_id)
        narrative = PublicH2Narrative(
            mode="artifact",
            renderer_version=RENDERER_VERSION,
            description=rendered.description,
            statement_ids=rendered.statement_ids,
            comments=(),
            render_digest=rendered_digest,
        )
        artifact = SimpleNamespace(
            id=artifact_id,
            report_id=report_id,
            snapshot_hash=snapshot_hash,
            generation_key=generation_key,
            binding_kind="artifact",
            binding_key=binding_key,
            artifact_identity=binding_key,
            fallback_identity=None,
            resolved_model_version=resolved_model,
            raw_model_output=plan_bytes.decode("utf-8"),
            validated_render_plan_cjson=plan_bytes,
            validated_render_plan_bytes_sha256=plan_hash,
            rendered_description=rendered.description,
            rendered_comments=[],
            statement_ids=list(rendered.statement_ids),
            evidence_ids=evidence_ids,
            phrase_trace=phrase_trace,
            validation_codes=[],
            renderer_version=RENDERER_VERSION,
            rendered_output_bytes_sha256=rendered_digest,
        )
        job_state = "finalized"
        job_validation_codes = []
        job_model = resolved_model
        dispatch_id = uuid4()
        dispatch_started_at = response_received_at = now

    projection = build_public_h2(
        snapshot,
        narrative_binding=SimpleNamespace(narrative=narrative),
    )
    job = SimpleNamespace(
        id=uuid4(),
        report_id=report_id,
        snapshot_hash=snapshot_hash,
        generation_key=generation_key,
        identity_version="GenerationIdentityV2",
        generation_identity=asdict(generation_identity),
        state=job_state,
        artifact_id=artifact_id,
        lease_token=None,
        lease_expires_at=None,
        gateway_dispatch_id=dispatch_id,
        dispatch_started_at=dispatch_started_at,
        response_received_at=response_received_at,
        resolved_model_version=job_model,
        validation_codes=job_validation_codes,
    )
    pin = SimpleNamespace(
        subject_id="subject-id",
        report_id=report_id,
        presentation_contract="company_public_h2_v1",
        generation=1,
        snapshot_hash=snapshot_hash,
        chart_facts_version=snapshot.chart_facts.version,
        chart_facts_hash=snapshot.chart_facts.hash,
        evidence_registry_version=snapshot.evidence_version,
        publication_policy_version="company_public_h2_publication_v1",
        canonical_path=None,
        indexable=False,
        published_lastmod=None,
        projection_digest=projection.projection_digest,
        narrative_binding_status="resolved",
        narrative_binding_kind=kind,
        narrative_binding_key=binding_key,
    )
    presentation = SimpleNamespace(
        subject_id="subject-id",
        report_id=report_id,
        presentation_contract="company_public_h2_v1",
        rollout_generation=1,
    )
    return record, snapshot, pin, presentation, job, artifact


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ("artifact", "fallback"))
async def test_resolved_v3_saved_result_is_exact_select_only_and_immutable(kind: str) -> None:
    record, _snapshot, pin, presentation, job, artifact = _v3_saved_result(kind)
    before = deepcopy(record.normalized_snapshot)
    session = _V3SelectOnlySession(presentation, job, artifact)

    response = await service._resolve_exact_v3(
        session,
        record,
        pin=pin,
        expected_subject_id="subject-id",
        expected_inn="7701234567",
    )

    assert response.narrative.mode == (
        "artifact" if kind == "artifact" else "deterministic_fallback"
    )
    assert response.projection_digest == pin.projection_digest
    assert record.normalized_snapshot == before
    assert session.select_count == 3


@pytest.mark.asyncio
async def test_exact_unresolved_v3_pin_remains_409_without_artifact_lookup() -> None:
    record, _snapshot, pin, presentation, job, artifact = _v3_saved_result("fallback")
    pin.narrative_binding_status = "unresolved"
    pin.narrative_binding_kind = None
    pin.narrative_binding_key = None
    pin.projection_digest = None
    session = _V3SelectOnlySession(presentation, job, artifact)

    with pytest.raises(service.PublicH2NotEligible) as caught:
        await service._resolve_exact_v3(
            session,
            record,
            pin=pin,
            expected_subject_id="subject-id",
            expected_inn="7701234567",
        )

    assert caught.value.code == "report_not_eligible"
    assert session.select_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "corruption"),
    (
        ("fallback", "pin_projection_digest"),
        ("fallback", "pin_chart_hash"),
        ("fallback", "fallback_identity"),
        ("fallback", "fallback_phrase_trace"),
        ("artifact", "generation_identity"),
        ("artifact", "artifact_identity"),
        ("artifact", "plan_hash"),
        ("artifact", "catalog_phrase_trace"),
        ("artifact", "job_state"),
        ("artifact", "job_model"),
    ),
)
async def test_resolved_v3_corruption_matrix_is_terminal_500(
    kind: str,
    corruption: str,
) -> None:
    record, _snapshot, pin, presentation, job, artifact = _v3_saved_result(kind)
    if corruption == "pin_projection_digest":
        pin.projection_digest = "f" * 64
    elif corruption == "pin_chart_hash":
        pin.chart_facts_hash = "f" * 64
    elif corruption == "fallback_identity":
        artifact.fallback_identity = "f" * 64
    elif corruption == "fallback_phrase_trace":
        artifact.phrase_trace[0]["scalar_end"] -= 1
    elif corruption == "generation_identity":
        job.generation_identity = {**job.generation_identity, "prompt_version": "stale"}
    elif corruption == "artifact_identity":
        artifact.artifact_identity = "f" * 64
    elif corruption == "plan_hash":
        artifact.validated_render_plan_bytes_sha256 = "f" * 64
    elif corruption == "catalog_phrase_trace":
        artifact.phrase_trace[0]["evidence_ids"] = ["unsupported_evidence"]
    elif corruption == "job_state":
        job.state = "validating"
    elif corruption == "job_model":
        job.resolved_model_version = "stale-model"
    session = _V3SelectOnlySession(presentation, job, artifact)

    with pytest.raises(service.PublicH2Invalid) as caught:
        await service._resolve_exact_v3(
            session,
            record,
            pin=pin,
            expected_subject_id="subject-id",
            expected_inn="7701234567",
        )

    assert caught.value.code == "public_projection_invalid"


class _LegacySelectOnlySession:
    def __init__(self, scalar_values, get_values=()):
        self.scalar_values = iter(scalar_values)
        self.get_values = iter(get_values)
        self.select_count = 0

    async def scalar(self, statement):
        assert isinstance(statement, Select)
        self.select_count += 1
        return next(self.scalar_values)

    async def get(self, _model, _key):
        self.select_count += 1
        return next(self.get_values)

    async def execute(self, _statement):
        raise AssertionError("legacy H2 resolution must use the scalar SELECT path")

    def add(self, _value):
        raise AssertionError("legacy H2 resolution must not add rows")

    async def flush(self):
        raise AssertionError("legacy H2 resolution must not flush")

    async def commit(self):
        raise AssertionError("legacy H2 resolution must not commit")

    async def rollback(self):
        raise AssertionError("legacy H2 resolution must not rollback")


def _legacy_record(version: str = "1"):
    raw = json.loads(
        (_FIXTURES / (
            "snapshot_v1_legacy.json" if version == "1" else "snapshot_v2_exact.json"
        )).read_text(encoding="utf-8")
    )
    report_id = "00000000-0000-4000-8000-000000000001"
    generated_at = "2026-08-24T12:00:00Z"
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
    return SimpleNamespace(
        id=report_id,
        subject_id="subject-id",
        report_version=version,
        writer_profile="h1_legacy_writer_v2",
        presentation_contract="company_public_h1_v1",
        rollout_generation=0,
        lifecycle_status=raw["status"],
        generated_at=datetime.fromisoformat(raw["generated_at"].replace("Z", "+00:00")),
        normalized_snapshot=raw,
        snapshot_hash=calculate_company_report_snapshot_hash(raw),
    )


def _saved_fallback(record):
    generation_identity = service._legacy_generation_identity(record=record)
    generation_key = identity_key(generation_identity)
    rendered_digest = sha256(FALLBACK_DESCRIPTION.encode("utf-8")).hexdigest()
    fallback_identity = identity_key(FallbackIdentityV1(
        generation_key=generation_key,
        fallback_catalog_version=FALLBACK_CATALOG_VERSION,
        fallback_profile_id=FALLBACK_PROFILE_ID,
        renderer_version=FALLBACK_RENDERER_VERSION,
        rendered_output_bytes_sha256=rendered_digest,
    ))
    artifact_id = uuid4()
    artifact = SimpleNamespace(
        id=artifact_id,
        report_id=record.id,
        snapshot_hash=record.snapshot_hash,
        generation_key=generation_key,
        binding_kind="fallback",
        binding_key=fallback_identity,
        artifact_identity=None,
        fallback_identity=fallback_identity,
        resolved_model_version=None,
        raw_model_output=None,
        validated_render_plan_cjson=None,
        validated_render_plan_bytes_sha256=None,
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
        rendered_output_bytes_sha256=rendered_digest,
    )
    job = SimpleNamespace(
        report_id=record.id,
        snapshot_hash=record.snapshot_hash,
        generation_key=generation_key,
        identity_version="GenerationIdentityV2",
        generation_identity=asdict(generation_identity),
        state="fallback_finalized",
        artifact_id=artifact_id,
        lease_token=None,
        lease_expires_at=None,
        validation_codes=["legacy_snapshot"],
        gateway_dispatch_id=None,
        dispatch_started_at=None,
        response_received_at=None,
        resolved_model_version=None,
    )
    outbox = SimpleNamespace(
        report_id=record.id,
        snapshot_hash=record.snapshot_hash,
        event_kind="initialize_narrative_v1",
        state="processed",
        generation_key=generation_key,
        processed_at=record.generated_at,
        failure_code=None,
        lease_token=None,
        lease_expires_at=None,
    )
    return outbox, job, artifact


@pytest.mark.asyncio
async def test_legacy_resolver_repeats_select_only_without_mutating_snapshot() -> None:
    record = _legacy_record("1")
    outbox, job, artifact = _saved_fallback(record)
    subject = SimpleNamespace(id="subject-id")
    session = _LegacySelectOnlySession(
        (
            subject, None, None, None, record, outbox, job,
            subject, None, None, None, record, outbox, job,
        ),
        get_values=(None, artifact, None, artifact),
    )
    before = deepcopy(record.normalized_snapshot)

    first = await service.resolve_public_h2(session, inn="7701234567")
    second = await service.resolve_public_h2(session, inn="7701234567")

    assert first == second
    assert first.projection_scope == "latest_unpublished"
    assert first.snapshot_capability == "legacy_read_only"
    assert first.narrative.mode == "deterministic_fallback"
    assert record.normalized_snapshot == before
    assert session.select_count == 18


@pytest.mark.asyncio
async def test_legacy_missing_binding_is_409_but_corrupt_binding_or_snapshot_is_500() -> None:
    record = _legacy_record("2")
    missing = _LegacySelectOnlySession((None,))
    with pytest.raises(service.PublicH2NotEligible) as caught:
        await service._legacy_preview(missing, record, "7701234567")
    assert caught.value.code == "report_not_eligible"

    pending_outbox, _job, _artifact = _saved_fallback(record)
    pending_outbox.state = "pending"
    pending_outbox.generation_key = None
    pending_outbox.processed_at = None
    pending = _LegacySelectOnlySession((pending_outbox,))
    with pytest.raises(service.PublicH2NotEligible) as caught:
        await service._legacy_preview(pending, record, "7701234567")
    assert caught.value.code == "report_not_eligible"

    outbox, job, corrupt_artifact = _saved_fallback(record)
    corrupt_artifact.rendered_description += "x"
    corrupt = _LegacySelectOnlySession(
        (outbox, job),
        get_values=(corrupt_artifact,),
    )
    with pytest.raises(service.PublicH2Invalid) as caught:
        await service._legacy_preview(corrupt, record, "7701234567")
    assert caught.value.code == "public_projection_invalid"

    processed_outbox, _job, _artifact = _saved_fallback(record)
    missing_job = _LegacySelectOnlySession((processed_outbox, None))
    with pytest.raises(service.PublicH2Invalid) as caught:
        await service._legacy_preview(missing_job, record, "7701234567")
    assert caught.value.code == "public_projection_invalid"

    corrupt_record = _legacy_record("2")
    corrupt_record.snapshot_hash = "f" * 64
    no_query = _LegacySelectOnlySession(())
    with pytest.raises(service.PublicH2Invalid) as caught:
        await service._legacy_preview(no_query, corrupt_record, "7701234567")
    assert caught.value.code == "public_projection_invalid"
    assert no_query.select_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corruption",
    ("generation_identity", "state", "artifact_id", "lease"),
)
async def test_legacy_processed_saved_result_job_corruption_is_500(
    corruption: str,
) -> None:
    record = _legacy_record("1")
    outbox, job, artifact = _saved_fallback(record)
    if corruption == "generation_identity":
        job.generation_identity = {
            **job.generation_identity,
            "snapshot_schema_version": "stale",
        }
    elif corruption == "state":
        job.state = "ready"
    elif corruption == "artifact_id":
        job.artifact_id = uuid4()
    else:
        job.lease_token = uuid4()
    session = _LegacySelectOnlySession(
        (outbox, job),
        get_values=(artifact,),
    )

    with pytest.raises(service.PublicH2Invalid) as caught:
        await service._legacy_preview(session, record, "7701234567")

    assert caught.value.code == "public_projection_invalid"
