from __future__ import annotations

import json

from shared.constants import (
    AI_EXPLANATION_OUTPUT_SCHEMA_NAME,
    AI_EXPLANATION_OUTPUT_SCHEMA_VERSION,
)
from shared.schemas import ChatMessage, JsonSchemaDefinition, JsonSchemaResponseFormat

from .models import AllowedStatementCatalog, ExplanationInputEnvelope


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def explanation_response_format(catalog: AllowedStatementCatalog) -> JsonSchemaResponseFormat:
    def ids(statements):
        return [statement.id for statement in statements]

    def selected_id_schema(statements):
        statement_ids = ids(statements)
        if not statement_ids:
            raise ValueError("required scalar catalog section is empty")
        return {"type": "string", "enum": statement_ids}

    def selected_ids_schema(statements, maximum: int):
        statement_ids = ids(statements)
        if not statement_ids:
            return {
                "type": "array",
                "items": {"type": "string"},
                "uniqueItems": True,
                "maxItems": 0,
            }
        return {
            "type": "array",
            "items": {"type": "string", "enum": statement_ids},
            "uniqueItems": True,
            "maxItems": maximum,
        }

    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "output_schema_version",
            "overall_conclusion_id",
            "recovery_factor_ids",
            "key_risk_ids",
            "urgency_id",
            "recommended_next_step_id",
            "limitation_ids",
        ],
        "properties": {
            "output_schema_version": {"type": "string", "const": AI_EXPLANATION_OUTPUT_SCHEMA_VERSION},
            "overall_conclusion_id": selected_id_schema(catalog.overall_conclusions),
            "recovery_factor_ids": selected_ids_schema(catalog.recovery_factors, 3),
            "key_risk_ids": selected_ids_schema(catalog.key_risks, 3),
            "urgency_id": selected_id_schema(catalog.urgencies),
            "recommended_next_step_id": selected_id_schema(catalog.recommended_next_steps),
            "limitation_ids": selected_ids_schema(catalog.limitations, 5),
        },
    }
    return JsonSchemaResponseFormat(
        type="json_schema",
        json_schema=JsonSchemaDefinition(
            name=AI_EXPLANATION_OUTPUT_SCHEMA_NAME,
            strict=True,
            schema=schema,
        ),
    )


def build_explanation_messages(envelope: ExplanationInputEnvelope) -> list[ChatMessage]:
    return [
        ChatMessage(
            role="system",
            content=(
                "Select only IDs from the supplied allowed_statement_catalog. "
                "Return only the required JSON object; do not add text or facts."
            ),
        ),
        ChatMessage(role="user", content=canonical_json(envelope.model_dump(mode="json"))),
    ]
