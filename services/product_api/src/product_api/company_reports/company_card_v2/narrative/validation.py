from __future__ import annotations

import unicodedata
from hashlib import sha256

from .models import NarrativeEvidenceEnvelope, RenderPlan, RenderedNarrative
from .renderer import render_narrative


class NarrativeValidationError(ValueError):
    pass


def normalize_text(value: object) -> str:
    if not isinstance(value, str) or any(0xD800 <= ord(c) <= 0xDFFF or c == "\0" or 0x202A <= ord(c) <= 0x202E or (ord(c) < 32 and c not in "\t\n\r") or 0x7F <= ord(c) <= 0x9F for c in value):
        raise NarrativeValidationError("unsafe text")
    value = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    return " ".join(value.split())


def validate_render_plan(value: object, evidence: NarrativeEvidenceEnvelope) -> RenderedNarrative:
    try:
        plan = RenderPlan.model_validate(value)
    except Exception as exc:
        raise NarrativeValidationError("render plan is invalid") from exc
    if evidence.primary_activity_label is None:
        raise NarrativeValidationError("activity evidence is unavailable")
    first = render_narrative(evidence)
    second = render_narrative(evidence)
    if first.description.encode() != second.description.encode() or first.render_digest != sha256(first.description.encode()).hexdigest():
        raise NarrativeValidationError("renderer is nondeterministic")
    return first
