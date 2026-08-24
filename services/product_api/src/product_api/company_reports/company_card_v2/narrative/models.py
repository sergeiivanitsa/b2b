from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .catalog import (CONNECTOR_IDS, INTRO_TEMPLATE_ID, OUTPUT_SCHEMA_VERSION, STATEMENT_IDS)


class NarrativeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DescriptionPlan(NarrativeModel):
    intro_template_id: Literal["intro_snapshot_scope_v1"]
    statement_ids: tuple[Literal["statement_primary_activity_v1", "statement_missing_is_unknown_v1", "statement_neutrality_and_immutability_v1"], Literal["statement_primary_activity_v1", "statement_missing_is_unknown_v1", "statement_neutrality_and_immutability_v1"], Literal["statement_primary_activity_v1", "statement_missing_is_unknown_v1", "statement_neutrality_and_immutability_v1"]]
    connector_ids: tuple[Literal["connector_intro_activity_v1", "connector_activity_missing_v1", "connector_missing_neutrality_v1"], Literal["connector_intro_activity_v1", "connector_activity_missing_v1", "connector_missing_neutrality_v1"], Literal["connector_intro_activity_v1", "connector_activity_missing_v1", "connector_missing_neutrality_v1"]]

    @model_validator(mode="after")
    def _fixed_plan(self) -> "DescriptionPlan":
        if self.intro_template_id != INTRO_TEMPLATE_ID or self.statement_ids != STATEMENT_IDS or self.connector_ids != CONNECTOR_IDS:
            raise ValueError("render plan is not allowlisted")
        return self


class RenderPlan(NarrativeModel):
    output_schema_version: Literal["company_card_narrative_render_plan_v1"]
    description_plan: DescriptionPlan
    chart_comments: tuple[()] = ()


class NarrativeEvidenceEnvelope(NarrativeModel):
    evidence_registry_version: str = Field(min_length=1, max_length=128)
    primary_activity_label: str | None = Field(default=None, min_length=1, max_length=128)
    limitation_code: Literal["primary_activity_not_admitted"] | None = None

    @model_validator(mode="after")
    def _closed(self) -> "NarrativeEvidenceEnvelope":
        if (self.primary_activity_label is None) == (self.limitation_code is None):
            raise ValueError("narrative evidence result is required")
        return self


class PhraseTrace(NarrativeModel):
    statement_id: str
    evidence_ids: tuple[str, ...]
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class RenderedNarrative(NarrativeModel):
    mode: Literal["artifact", "deterministic_fallback"]
    description: str = Field(min_length=400, max_length=700)
    statement_ids: tuple[str, ...]
    phrase_trace: tuple[PhraseTrace, ...]
    render_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    comments: tuple[()] = ()
