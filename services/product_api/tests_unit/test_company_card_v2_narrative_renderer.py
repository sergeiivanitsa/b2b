import json
from pathlib import Path

from product_api.company_reports.company_card_v2.narrative.catalog import (
    EVIDENCE_BY_STATEMENT,
    FALLBACK_PROFILE_ID,
    PUBLIC_STATEMENT_IDS,
)
from product_api.company_reports.company_card_v2.narrative.models import NarrativeEvidenceEnvelope
from product_api.company_reports.company_card_v2.narrative.renderer import render_fallback, render_narrative


def _evidence(label="Разработка программного обеспечения"):
    return NarrativeEvidenceEnvelope(
        evidence_registry_version="evidence_registry_v1",
        primary_activity_label=label,
    )


def test_renderer_is_deterministic_and_bounded():
    first = render_narrative(_evidence())
    assert first == render_narrative(_evidence())
    assert 400 <= len(first.description) <= 700
    assert first.comments == ()
    assert first.statement_ids == PUBLIC_STATEMENT_IDS
    assert first.render_digest == render_narrative(_evidence()).render_digest

    previous_end = -1
    for index, trace in enumerate(first.phrase_trace):
        assert trace.statement_id == first.statement_ids[index]
        assert trace.evidence_ids == EVIDENCE_BY_STATEMENT[trace.statement_id]
        assert first.description[trace.start:trace.end]
        assert trace.start == (0 if index == 0 else previous_end + 1)
        previous_end = trace.end
    assert previous_end == len(first.description)


def test_fallback_has_no_company_specific_label():
    rendered = render_fallback(_evidence())
    assert rendered.mode == "deterministic_fallback"
    assert "Разработка программного обеспечения" not in rendered.description


def test_fallback_matches_exact_691_scalar_golden_and_empty_grounding() -> None:
    path = Path(__file__).parent / "fixtures" / "company_card_v2" / "narrative_fallback_golden.json"
    golden = json.loads(path.read_text(encoding="utf-8"))
    rendered = render_fallback(_evidence())

    assert len(rendered.description) == 691
    assert rendered.model_dump(mode="json") == {
        key: value for key, value in golden.items() if key != "scalar_count"
    }
    assert rendered.comments == ()
    assert rendered.statement_ids == (FALLBACK_PROFILE_ID,)
    assert rendered.phrase_trace[0].evidence_ids == ()
    assert rendered.phrase_trace[0].start == 0
    assert rendered.phrase_trace[0].end == 691


def test_maximum_admitted_label_renders_exact_upper_boundary() -> None:
    rendered = render_narrative(_evidence("😀" * 128))
    assert len(rendered.description) == 691
    assert rendered == render_narrative(_evidence("😀" * 128))
