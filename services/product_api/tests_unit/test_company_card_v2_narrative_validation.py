from __future__ import annotations

import json
from pathlib import Path

import pytest

from product_api.company_reports.company_card_v2.narrative.models import NarrativeEvidenceEnvelope
from product_api.company_reports.company_card_v2.narrative.renderer import render_narrative
from product_api.company_reports.company_card_v2.narrative.validation import (
    NarrativeValidationError,
    normalize_text,
    validate_render_plan,
)


FIXTURES = Path(__file__).parent / "fixtures" / "company_card_v2"


def _plan() -> dict[str, object]:
    return json.loads((FIXTURES / "narrative_render_plan_valid.json").read_text(encoding="utf-8"))


def _evidence() -> NarrativeEvidenceEnvelope:
    return NarrativeEvidenceEnvelope(
        evidence_registry_version="evidence_registry_v1",
        primary_activity_label="Разработка программного обеспечения",
    )


def test_normalization_order_is_nfc_then_newlines_trim_and_unicode_whitespace_collapse() -> None:
    assert normalize_text(" \u212b\r\n\tX\u00a0Y ") == "Å X Y"
    assert normalize_text(" e\u0301\r lone\r\nline ") == "é lone line"


@pytest.mark.parametrize(
    "value",
    [
        "bad\x00",
        "bad\x01",
        "bad\x7f",
        "bad\x85",
        "bad\u202a",
        "bad\u202e",
        "bad\ud800",
    ],
)
def test_normalization_rejects_nul_controls_bidi_and_unpaired_surrogates(value: str) -> None:
    with pytest.raises(NarrativeValidationError, match="unsafe text"):
        normalize_text(value)


def test_exact_runtime_render_plan_validates_and_double_render_is_identical() -> None:
    rendered = validate_render_plan(_plan(), _evidence())
    assert rendered == render_narrative(_evidence())
    assert rendered.comments == ()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.__setitem__("unknown", True),
        lambda value: value.__setitem__("chart_comments", [{"chart_id": "finance_f1_liquidity"}]),
        lambda value: value["description_plan"].__setitem__("statement_ids", []),
        lambda value: value["description_plan"].__setitem__("statement_ids", ["statement_primary_activity_v1"] * 3),
        lambda value: value["description_plan"].__setitem__("connector_ids", ["unknown_v1"] * 3),
    ],
)
def test_runtime_plan_rejects_extra_chart_duplicate_and_unknown_ids(mutation) -> None:
    value = _plan()
    mutation(value)

    with pytest.raises(NarrativeValidationError, match="render plan is invalid"):
        validate_render_plan(value, _evidence())


def test_runtime_plan_cannot_assert_activity_without_admitted_evidence() -> None:
    evidence = NarrativeEvidenceEnvelope(
        evidence_registry_version="narrative_evidence_absent_v1",
        limitation_code="primary_activity_not_admitted",
    )

    with pytest.raises(NarrativeValidationError, match="activity evidence is unavailable"):
        validate_render_plan(_plan(), evidence)


def test_double_render_byte_mismatch_is_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = render_narrative(_evidence())
    calls = 0

    def nondeterministic(_evidence_value):
        nonlocal calls
        calls += 1
        if calls == 1:
            return baseline
        return baseline.model_copy(update={"description": "X" + baseline.description[1:]})

    monkeypatch.setattr(
        "product_api.company_reports.company_card_v2.narrative.validation.render_narrative",
        nondeterministic,
    )

    with pytest.raises(NarrativeValidationError, match="nondeterministic"):
        validate_render_plan(_plan(), _evidence())
