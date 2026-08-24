MODEL_GPT_5_2 = "gpt-5.2"

# A profile is a stable Product-to-Gateway contract.  It deliberately is not
# an OpenAI model name: model resolution remains confined to gateway_api.
AI_EXPLANATION_MODEL_PROFILE = "economy_text_structured_v1"
AI_EXPLANATION_OUTPUT_SCHEMA_NAME = "company_recovery_explanation_v1"
AI_EXPLANATION_OUTPUT_SCHEMA_VERSION = "1"

# Iteration 21 is intentionally a separate, default-off structured contract.
COMPANY_CARD_NARRATIVE_MODEL_PROFILE = "company_card_narrative_structured_v1"
COMPANY_CARD_NARRATIVE_OUTPUT_SCHEMA_NAME = "company_card_narrative_render_plan_v1"
COMPANY_CARD_NARRATIVE_MAX_TIMEOUT_SECONDS = 20
COMPANY_CARD_NARRATIVE_MAX_OUTPUT_TOKENS = 600
COMPANY_CARD_NARRATIVE_MAX_REQUEST_BYTES = 32768
COMPANY_CARD_NARRATIVE_MAX_RESPONSE_BYTES = 16384
