"""Privacy-minimal task-specific gateway request construction."""
from __future__ import annotations

from uuid import UUID

from shared.constants import COMPANY_CARD_NARRATIVE_MODEL_PROFILE, COMPANY_CARD_NARRATIVE_OUTPUT_SCHEMA_NAME

from .catalog import INPUT_SCHEMA_VERSION, OUTPUT_SCHEMA_VERSION
from .catalog import INSIGHT_CATALOG_VERSION, STATEMENT_CATALOG_VERSION, TEMPLATE_CATALOG_VERSION
from ..canonical_json import canonical_json_bytes
from .models import NarrativeEvidenceEnvelope


def narrative_json_schema() -> dict[str, object]:
    return {
        "name": COMPANY_CARD_NARRATIVE_OUTPUT_SCHEMA_NAME,
        "strict": True,
        "schema": {
            "type": "object", "additionalProperties": False,
            "required": ["output_schema_version", "description_plan", "chart_comments"],
            "properties": {
                "output_schema_version": {"const": OUTPUT_SCHEMA_VERSION},
                "description_plan": {
                    "type": "object", "additionalProperties": False,
                    "required": ["intro_template_id", "statement_ids", "connector_ids"],
                    "properties": {
                        "intro_template_id": {"const": "intro_snapshot_scope_v1"},
                        "statement_ids": {"type": "array", "minItems": 3, "maxItems": 3, "prefixItems": [{"const": "statement_primary_activity_v1"}, {"const": "statement_missing_is_unknown_v1"}, {"const": "statement_neutrality_and_immutability_v1"}], "items": False},
                        "connector_ids": {"type": "array", "minItems": 3, "maxItems": 3, "prefixItems": [{"const": "connector_intro_activity_v1"}, {"const": "connector_activity_missing_v1"}, {"const": "connector_missing_neutrality_v1"}], "items": False},
                    },
                },
                "chart_comments": {"type": "array", "minItems": 0, "maxItems": 0},
            },
        },
    }


def build_narrative_gateway_body(evidence: NarrativeEvidenceEnvelope, *, dispatch_id: UUID) -> dict[str, object]:
    facts: dict[str, object] = {
        "input_schema_version": INPUT_SCHEMA_VERSION,
        "evidence_registry_version": evidence.evidence_registry_version,
        "insight_catalog_version": INSIGHT_CATALOG_VERSION,
        "statement_catalog_version": STATEMENT_CATALOG_VERSION,
        "template_catalog_version": TEMPLATE_CATALOG_VERSION,
        "allowed_evidence_ids": [
            "evidence_snapshot_identity_v1",
            "evidence_missing_semantics_policy_v1",
            "evidence_neutrality_policy_v1",
        ],
    }
    if evidence.primary_activity_label is not None:
        facts["primary_activity_label"] = evidence.primary_activity_label
        facts["allowed_evidence_ids"] = [*facts["allowed_evidence_ids"], "evidence_primary_activity_v1"]
    else:
        facts["limitation_code"] = evidence.limitation_code
    return {
        "messages": [{"role": "user", "content": canonical_json_bytes(facts).decode("utf-8")}],
        "stream": False, "timeout": 20, "model_profile": COMPANY_CARD_NARRATIVE_MODEL_PROFILE,
        "response_format": {"type": "json_schema", "json_schema": narrative_json_schema()},
        "max_output_tokens": 600, "gateway_dispatch_id": str(dispatch_id),
    }
