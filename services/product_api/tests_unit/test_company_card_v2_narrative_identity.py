from dataclasses import replace
from uuid import uuid4

import pytest

from product_api.company_reports.company_card_v2.narrative.catalog import (
    FALLBACK_CATALOG_VERSION,
    FALLBACK_PROFILE_ID,
    FALLBACK_RENDERER_VERSION,
)
from product_api.company_reports.company_card_v2.narrative.identity import (
    ArtifactIdentityV1,
    FallbackIdentityV1,
    GenerationIdentityV1,
    GenerationIdentityV2,
    identity_key,
)


def _generation_v1() -> GenerationIdentityV1:
    return GenerationIdentityV1(
        report_id=str(uuid4()),
        snapshot_hash="0" * 64,
        chart_facts_hash="1" * 64,
        evidence_registry_version="evidence_v1",
        statement_catalog_version="statement_v1",
        template_catalog_version="template_v1",
        prompt_version="prompt_v1",
        json_schema_version="schema_v1",
        policy_version="policy_v1",
        renderer_version="renderer_v1",
        gateway_profile_version="profile_v1",
        fallback_catalog_version=FALLBACK_CATALOG_VERSION,
    )


def _generation_v2() -> GenerationIdentityV2:
    base = _generation_v1()
    return GenerationIdentityV2(
        report_id=base.report_id,
        snapshot_hash=base.snapshot_hash,
        chart_facts_hash=base.chart_facts_hash,
        evidence_registry_version=base.evidence_registry_version,
        statement_catalog_version=base.statement_catalog_version,
        template_catalog_version=base.template_catalog_version,
        prompt_version=base.prompt_version,
        json_schema_version=base.json_schema_version,
        policy_version=base.policy_version,
        renderer_version=base.renderer_version,
        gateway_profile_version=base.gateway_profile_version,
        fallback_catalog_version=base.fallback_catalog_version,
        snapshot_schema_version="company_card_v2_snapshot_v2",
        narrative_evidence_schema_version="company_card_v2_narrative_evidence_v1",
        primary_activity_parser_version="company_card_v2_primary_activity_parser_v1",
        primary_activity_evidence_version="company_card_v2_okved_primary_activity_evidence_v1",
        insight_catalog_version="insight_v1",
        connector_catalog_version="connector_v1",
        input_schema_version="input_v1",
    )


def test_artifact_identity_changes_with_resolved_model_only():
    generation = _generation_v1()
    key = identity_key(generation)
    assert identity_key(ArtifactIdentityV1(key, "a", "2" * 64, "3" * 64)) != identity_key(ArtifactIdentityV1(key, "b", "2" * 64, "3" * 64))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("snapshot_hash", "A" * 64),
        ("chart_facts_hash", "0" * 63),
        ("prompt_version", "not a version"),
    ],
)
def test_generation_identity_rejects_noncanonical_hashes_and_versions(field, value):
    with pytest.raises(ValueError):
        replace(_generation_v1(), **{field: value})


def test_identity_version_is_a_literal_and_cannot_be_spoofed():
    values = {
        **_generation_v1().__dict__,
        "identity_version": "GenerationIdentityV2",
    }
    with pytest.raises(TypeError):
        GenerationIdentityV1(**values)


def test_generation_v2_validates_snapshot_and_evidence_version_tuple():
    with pytest.raises(ValueError, match="snapshot_schema_version"):
        replace(_generation_v2(), snapshot_schema_version="unknown_v1")
    with pytest.raises(ValueError, match="version tuple"):
        replace(
            _generation_v2(),
            narrative_evidence_schema_version="narrative_evidence_absent_v1",
        )


def test_artifact_and_fallback_identities_reject_spoofed_literals_and_hashes():
    generation_key = identity_key(_generation_v2())
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        ArtifactIdentityV1(generation_key, "model-v1", "A" * 64, "b" * 64)
    with pytest.raises(ValueError, match="fallback_catalog_version"):
        FallbackIdentityV1(
            generation_key,
            "fallback_other_v1",
            FALLBACK_PROFILE_ID,
            FALLBACK_RENDERER_VERSION,
            "c" * 64,
        )
    valid = FallbackIdentityV1(
        generation_key,
        FALLBACK_CATALOG_VERSION,
        FALLBACK_PROFILE_ID,
        FALLBACK_RENDERER_VERSION,
        "c" * 64,
    )
    assert len(identity_key(valid)) == 64


def test_v1_v2_artifact_and_fallback_identity_goldens_are_byte_exact() -> None:
    v1 = replace(
        _generation_v1(),
        report_id="00000000-0000-4000-8000-000000000001",
    )
    v2 = replace(
        _generation_v2(),
        report_id="00000000-0000-4000-8000-000000000001",
    )
    generation_key = identity_key(v2)
    artifact = ArtifactIdentityV1(generation_key, "model-v1", "2" * 64, "3" * 64)
    fallback = FallbackIdentityV1(
        generation_key,
        FALLBACK_CATALOG_VERSION,
        FALLBACK_PROFILE_ID,
        FALLBACK_RENDERER_VERSION,
        "c" * 64,
    )

    assert identity_key(v1) == "577e7403f8e351a568846a727eea7c6115765d226ee7474621b71720a38ff9d0"
    assert generation_key == "a0127badd3a9f7dba212ffa20cd385b69bee7b4157afe7b7259a9918795bbaad"
    assert identity_key(artifact) == "7f1ea091a9a78c3929f6f02f9d09908a3312c2fcfded19f4c675cf35806538d7"
    assert identity_key(fallback) == "165dab36e042944008f7ea06e743132f0bce951804ca8911cd7446418453ad66"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("connector_catalog_version", "connector_v2"),
        ("input_schema_version", "input_v2"),
        ("fallback_catalog_version", "company_card_h2_fallback_catalog_v2"),
    ],
)
def test_catalog_only_generation_upgrade_changes_generation_key(field: str, value: str) -> None:
    generation = _generation_v2()
    assert identity_key(replace(generation, **{field: value})) != identity_key(generation)


def test_resolved_model_change_keeps_generation_key_and_changes_only_artifact_identity() -> None:
    generation_key = identity_key(_generation_v2())
    first = ArtifactIdentityV1(generation_key, "model-v1", "2" * 64, "3" * 64)
    second = ArtifactIdentityV1(generation_key, "model-v2", "2" * 64, "3" * 64)

    assert first.generation_key == second.generation_key == generation_key
    assert identity_key(first) != identity_key(second)


@pytest.mark.parametrize(
    ("factory", "field", "value"),
    [
        (ArtifactIdentityV1, "generation_key", "0" * 63),
        (ArtifactIdentityV1, "resolved_model_version", " model"),
        (FallbackIdentityV1, "rendered_output_bytes_sha256", "F" * 64),
    ],
)
def test_artifact_and_fallback_identity_reject_noncanonical_spoof_values(factory, field, value) -> None:
    generation_key = identity_key(_generation_v2())
    if factory is ArtifactIdentityV1:
        values = {
            "generation_key": generation_key,
            "resolved_model_version": "model-v1",
            "validated_render_plan_bytes_sha256": "2" * 64,
            "rendered_output_bytes_sha256": "3" * 64,
        }
    else:
        values = {
            "generation_key": generation_key,
            "fallback_catalog_version": FALLBACK_CATALOG_VERSION,
            "fallback_profile_id": FALLBACK_PROFILE_ID,
            "renderer_version": FALLBACK_RENDERER_VERSION,
            "rendered_output_bytes_sha256": "c" * 64,
        }
    values[field] = value

    with pytest.raises(ValueError):
        factory(**values)
