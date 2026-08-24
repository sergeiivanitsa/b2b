from __future__ import annotations

from hashlib import sha256

from .catalog import EVIDENCE_BY_STATEMENT, FALLBACK_DESCRIPTION, FALLBACK_PROFILE_ID, FALLBACK_RENDERER_VERSION, INTRO, MISSING, NEUTRAL, PRIMARY, PUBLIC_STATEMENT_IDS, RENDERER_VERSION
from .models import NarrativeEvidenceEnvelope, PhraseTrace, RenderedNarrative


def render_narrative(evidence: NarrativeEvidenceEnvelope, *, mode: str = "artifact") -> RenderedNarrative:
    if evidence.primary_activity_label is None:
        # A stable universal fallback contains no company-specific fact.
        label = "сведения об основном виде деятельности недоступны"
    else:
        label = evidence.primary_activity_label
    fragments = (INTRO, PRIMARY.format(primary_activity_label=label), MISSING, NEUTRAL)
    description = " ".join(fragments)
    traces: list[PhraseTrace] = []
    offset = 0
    for text, statement_id in zip(fragments, PUBLIC_STATEMENT_IDS):
        end = offset + len(text)
        traces.append(PhraseTrace(statement_id=statement_id, evidence_ids=EVIDENCE_BY_STATEMENT[statement_id], start=offset, end=end))
        offset = end + 1
    digest = sha256(description.encode("utf-8")).hexdigest()
    return RenderedNarrative(mode=mode, description=description, statement_ids=PUBLIC_STATEMENT_IDS, phrase_trace=tuple(traces), render_digest=digest)


def render_fallback(evidence: NarrativeEvidenceEnvelope) -> RenderedNarrative:
    del evidence
    description = FALLBACK_DESCRIPTION
    digest = sha256(description.encode("utf-8")).hexdigest()
    return RenderedNarrative(mode="deterministic_fallback", description=description, statement_ids=(FALLBACK_PROFILE_ID,), phrase_trace=(PhraseTrace(statement_id=FALLBACK_PROFILE_ID, evidence_ids=(), start=0, end=len(description)),), render_digest=digest)
