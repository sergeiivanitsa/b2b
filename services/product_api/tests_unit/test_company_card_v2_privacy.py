import pytest
from pydantic import ValidationError

from product_api.company_reports.company_card_v2.narrative.catalog import (
    FALLBACK_DESCRIPTION,
    FALLBACK_PROFILE_ID,
    FALLBACK_RENDERER_VERSION,
)
from product_api.company_reports.company_card_v2.narrative.renderer import render_fallback
from product_api.company_reports.company_card_v2.narrative.models import NarrativeEvidenceEnvelope
from product_api.company_reports.company_card_v2.privacy import PrivacyBoundaryError, assert_public_boundary_safe
from product_api.company_reports.company_card_v2.public_h2_models import PublicH2Narrative


@pytest.mark.parametrize("payload", [
    {"case_id": "x"}, {"opponent": {"value": "a" * 64}}, {"contact": "x"},
    {"X-Api-Key": "secret"}, {"body": "Bearer secret"}, {"href": "https://kad.arbitr.ru/card/x"},
])
def test_public_boundary_rejects_private_markers(payload: object) -> None:
    with pytest.raises(PrivacyBoundaryError):
        assert_public_boundary_safe(payload)


def test_public_projection_digest_is_not_a_private_token() -> None:
    assert_public_boundary_safe({"projection_digest": "a" * 64})


def test_public_narrative_shape_cannot_leak_raw_model_output_or_phrase_trace() -> None:
    rendered = render_fallback(
        NarrativeEvidenceEnvelope(
            evidence_registry_version="narrative_evidence_absent_v1",
            limitation_code="primary_activity_not_admitted",
        )
    )
    public = {
        "mode": "deterministic_fallback",
        "renderer_version": FALLBACK_RENDERER_VERSION,
        "description": FALLBACK_DESCRIPTION,
        "statement_ids": [FALLBACK_PROFILE_ID],
        "comments": [],
        "render_digest": rendered.render_digest,
    }
    PublicH2Narrative.model_validate(public)

    for forbidden in ("raw_model_output", "validated_render_plan_cjson", "phrase_trace"):
        with pytest.raises(ValidationError):
            PublicH2Narrative.model_validate({**public, forbidden: "secret"})
