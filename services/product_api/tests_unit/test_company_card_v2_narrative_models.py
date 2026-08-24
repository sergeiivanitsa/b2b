import pytest
from pydantic import ValidationError

from product_api.company_reports.company_card_v2.narrative.catalog import (
    CONNECTOR_IDS,
    INTRO_TEMPLATE_ID,
    OUTPUT_SCHEMA_VERSION,
    STATEMENT_IDS,
)
from product_api.company_reports.company_card_v2.narrative.models import (
    NarrativeEvidenceEnvelope,
    PhraseTrace,
    RenderPlan,
    RenderedNarrative,
)


def test_evidence_envelope_is_privacy_minimal_and_requires_registry_version():
    evidence = NarrativeEvidenceEnvelope(
        evidence_registry_version="evidence_registry_v1",
        primary_activity_label="Разработка программного обеспечения",
    )

    assert evidence.model_dump() == {
        "evidence_registry_version": "evidence_registry_v1",
        "primary_activity_label": "Разработка программного обеспечения",
        "limitation_code": None,
    }
    with pytest.raises(ValidationError):
        NarrativeEvidenceEnvelope(primary_activity_label="Разработка программного обеспечения")
    with pytest.raises(ValidationError):
        NarrativeEvidenceEnvelope(
            evidence_registry_version="evidence_registry_v1",
            primary_activity_label="Разработка программного обеспечения",
            report_id="forbidden",
        )


def test_evidence_envelope_requires_one_admitted_activity_or_closed_limitation():
    unavailable = NarrativeEvidenceEnvelope(
        evidence_registry_version="narrative_evidence_absent_v1",
        limitation_code="primary_activity_not_admitted",
    )

    assert unavailable.primary_activity_label is None
    with pytest.raises(ValidationError):
        NarrativeEvidenceEnvelope(evidence_registry_version="evidence_registry_v1")
    with pytest.raises(ValidationError):
        NarrativeEvidenceEnvelope(
            evidence_registry_version="evidence_registry_v1",
            limitation_code="unexpected",
        )


def _valid_plan() -> dict[str, object]:
    return {
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "description_plan": {
            "intro_template_id": INTRO_TEMPLATE_ID,
            "statement_ids": list(STATEMENT_IDS),
            "connector_ids": list(CONNECTOR_IDS),
        },
        "chart_comments": [],
    }


def test_render_plan_accepts_only_the_exact_runtime_allowlist() -> None:
    plan = RenderPlan.model_validate(_valid_plan())

    assert plan.output_schema_version == OUTPUT_SCHEMA_VERSION
    assert plan.description_plan.statement_ids == STATEMENT_IDS
    assert plan.description_plan.connector_ids == CONNECTOR_IDS
    assert plan.chart_comments == ()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.__setitem__("prose", "model-authored prose"),
        lambda value: value.__setitem__("score", 1),
        lambda value: value.__setitem__("output_schema_version", "unknown_v1"),
        lambda value: value["description_plan"].__setitem__("intro_template_id", "unknown_v1"),
        lambda value: value["description_plan"].__setitem__("extra", True),
        lambda value: value["description_plan"].__setitem__("statement_ids", [*STATEMENT_IDS, STATEMENT_IDS[-1]]),
        lambda value: value["description_plan"].__setitem__("statement_ids", [STATEMENT_IDS[1], STATEMENT_IDS[0], STATEMENT_IDS[2]]),
        lambda value: value["description_plan"].__setitem__("connector_ids", [*CONNECTOR_IDS[:-1], "unknown_v1"]),
        lambda value: value.__setitem__("chart_comments", [{"chart_id": "finance_f1_liquidity"}]),
    ],
)
def test_render_plan_rejects_unknown_extra_duplicate_excess_and_model_prose(mutate) -> None:
    value = _valid_plan()
    mutate(value)

    with pytest.raises(ValidationError):
        RenderPlan.model_validate(value)


@pytest.mark.parametrize(
    "label",
    ["", "x" * 129],
)
def test_evidence_label_has_closed_scalar_cardinality(label: str) -> None:
    with pytest.raises(ValidationError):
        NarrativeEvidenceEnvelope(
            evidence_registry_version="evidence_registry_v1",
            primary_activity_label=label,
        )


def test_evidence_label_exact_128_scalar_boundary_is_accepted() -> None:
    evidence = NarrativeEvidenceEnvelope(
        evidence_registry_version="evidence_registry_v1",
        primary_activity_label="😀" * 128,
    )
    assert len(evidence.primary_activity_label or "") == 128


@pytest.mark.parametrize("length", [400, 700])
def test_rendered_description_accepts_exact_scalar_boundaries(length: int) -> None:
    value = RenderedNarrative(
        mode="artifact",
        description="я" * length,
        statement_ids=("fixture_statement_v1",),
        phrase_trace=(
            PhraseTrace(
                statement_id="fixture_statement_v1",
                evidence_ids=("fixture_evidence_v1",),
                start=0,
                end=length,
            ),
        ),
        render_digest="a" * 64,
    )
    assert len(value.description) == length


@pytest.mark.parametrize("length", [399, 701])
def test_rendered_description_rejects_outside_scalar_boundaries(length: int) -> None:
    with pytest.raises(ValidationError):
        RenderedNarrative(
            mode="artifact",
            description="я" * length,
            statement_ids=("fixture_statement_v1",),
            phrase_trace=(
                PhraseTrace(
                    statement_id="fixture_statement_v1",
                    evidence_ids=("fixture_evidence_v1",),
                    start=0,
                    end=length,
                ),
            ),
            render_digest="a" * 64,
        )
