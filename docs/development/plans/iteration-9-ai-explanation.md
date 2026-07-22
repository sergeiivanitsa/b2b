# Инженерная итерация 9 — AI-объяснение: implementation plan

## 1. Change manifest

| Surface | Files | Responsibility |
|---|---|---|
| Shared contracts | `shared/schemas.py`, `shared/constants.py` | Two-mode `ChatRequest`, strict format models, safe response audit fields, stable names. |
| Product config/transport | `services/product_api/src/product_api/settings.py`, `gateway_client.py`, `.env.example` | Explanation settings, payload timeout propagation, safe typed Gateway error. |
| Explanation domain | New `services/product_api/src/product_api/company_reports/explanation/{__init__.py,models.py,catalog.py,prompt.py,validation.py,service.py}` | Allowlist, strict schema, grounding, renderer, retry/failure logic. |
| Product exports | `services/product_api/src/product_api/company_reports/__init__.py` | Explicit explanation exports only. |
| Gateway | `services/gateway_api/src/gateway_api/{settings.py,main.py,openai_client.py}`, `.env.example` | Profile resolver, mode branch, no structured metadata logging, strict upstream request and timeout. |
| Tests | New Product explanation test modules; extend `services/gateway_api/tests/test_contract.py`; add `services/gateway_api/tests/test_structured_contract.py` | Unit and mocked contract coverage. |
| Docs | `docs/development/iterations/iteration-9-ai-explanation.md`, `docs/development/plans/iteration-9-ai-explanation.md` | Approved iteration artifacts. |

No Alembic file, persistence file, router, Product API endpoint or UI file is
changed.

## 2. Exact file contracts

### `shared/schemas.py`

Add:

- `JsonSchemaDefinition`;
- `JsonSchemaResponseFormat`;
- `ChatRequest.model: str | None`;
- `ChatRequest.metadata: ChatMetadata | None`;
- optional `model_profile`, `response_format`, `max_output_tokens`;
- cross-field mode validator;
- optional `ChatResponse.model_profile` and `ChatResponse.resolved_model`.

The validator admits exactly these two modes:

- legacy: non-empty `model`, required `metadata`, and no structured fields;
- structured: `model=None`, `metadata=None`, non-empty `model_profile`, strict
  `response_format`, positive `max_output_tokens`, `stream=False`.

Tests must reject hybrid, missing legacy metadata, missing structured
profile/schema/output cap, structured metadata, structured streaming and
structured direct model.

### `shared/constants.py`

Add profile and output schema/version constants. Do not place actual model names
in explanation domain constants.

### Product settings and client

`settings.py` adds and validates:

```text
AI_EXPLANATION_ENABLED=false
AI_EXPLANATION_MODEL_PROFILE=economy_text_structured_v1
AI_EXPLANATION_PROMPT_VERSION=v1
AI_EXPLANATION_MAX_INPUT_TOKENS=4096
AI_EXPLANATION_MAX_OUTPUT_TOKENS=600
AI_EXPLANATION_TIMEOUT_SECONDS=20
```

All budgets and timeouts are positive. Profile and prompt version are non-empty
and version matches `[A-Za-z0-9_.-]{1,32}`.

`gateway_client.py` uses:

```python
timeout_seconds = payload.timeout or settings.gateway_timeout_seconds
```

for the Product-to-Gateway `httpx.AsyncClient`. It parses only safe Gateway
normalized error attributes and keeps existing callers source-compatible.

### Explanation package

- `models.py`: immutable input/result/failure contracts.
- `catalog.py`: versioned selections and renderer templates backed only by
  existing signal/scoring/completeness conditions.
- `prompt.py`: canonical messages and strict JSON Schema.
- `validation.py`: allowlisted projection, input bound,
  parse/schema/grounding/audit validation and renderer.
- `service.py`: creates structured-mode `ChatRequest` with `model=None`,
  metadata absent, profile/schema/output cap, `stream=False`,
  `timeout=settings.ai_explanation_timeout_seconds`; executes retry policy.
- `__init__.py`: explicitly exports explanation types and
  `explain_scoring_result`.

After every successful transport response, Product requires matching
`model_profile` and a non-empty `resolved_model`. Missing or mismatched audit
metadata returns `configuration_error` / `gateway_contract_mismatch` without
retry or explanation text.

### Gateway

`settings.py` provides configured profile and actual model. The profile must
match the shared `economy_text_structured_v1` constant; the default actual model
is the only model already supported by the current Gateway, `gpt-5.2`.

`main.py` explicitly dispatches legacy vs structured mode:

- legacy retains direct-model check, metadata log and existing behavior;
- structured resolves profile, excludes metadata logging, logs only request ID
  and profile, passes payload timeout/schema/output cap, and returns safe audit
  fields.

`openai_client.py` accepts optional structured settings. Only structured
requests add `response_format` and `max_completion_tokens`; all calls use
supplied timeout when present.

## 3. Stages

### Stage 0 — approved contracts

Add specification and plan; confirm no persistence/API/UI scope.

### Stage 1 — shared two-mode contract

Implement strict legacy/structured validator and response audit fields.
Preserve all existing chat tests.

### Stage 2 — Product pure explanation domain

Implement allowlist, catalog, strict selection schema, grounding validator and
deterministic renderer. Ensure no raw payload or mutable input.

### Stage 3 — Gateway structured extension

Implement profile resolution and `/v1/chat` structured branch. Preserve legacy
HMAC and logging behavior; structured requests never log metadata.

### Stage 4 — timeout, audit and retry service

Implement explicit timeout propagation, structured request construction, safe
Gateway classification, audit mismatch rejection and retry ceiling.

### Stage 5 — verification

Run tests, diff inspection and independent review.

## 4. Required tests

Product tests:

- two-mode `ChatRequest` construction through explanation service;
- input allowlist excludes identifier, provider/raw/error/auth data;
- deterministic canonical prompt/schema/catalog/rendering;
- malformed JSON, extra keys, wrong version, unknown/duplicate/excess IDs and
  ungrounded selections;
- complete/partial/failed/`insufficient_data`, mixed-direction and
  status-conflict inputs;
- Product `httpx` timeout equals `payload.timeout`; legacy fallback uses gateway
  settings timeout;
- one call success, transport retry, invalid-output retry, no third call;
- no retry for configuration/auth/local validation/audit mismatch;
- missing/mismatched `model_profile` or empty `resolved_model` yields
  `configuration_error`, `gateway_contract_mismatch`, no explanation and no
  retry;
- immutable report/signals/scoring and no persisted result.

Gateway tests:

- signed legacy request retains required metadata, direct `gpt-5.2` behavior
  and legacy metadata log;
- signed structured request has `model=None`, metadata absent,
  profile/schema/output cap, and resolves configured actual model;
- hybrid or invalid structured payload fails validation;
- structured request forwards `response_format`, `max_completion_tokens` and
  payload timeout to mocked `create_chat_completion`;
- legacy request still forwards its timeout unchanged;
- structured success returns matching profile/non-empty resolved model;
- structured logging contains request ID/profile only and contains no
  company/user/conversation/message values;
- HMAC rejection applies equally to legacy and structured paths;
- mocked OpenAI boundary only; no real network call.

## 5. Verification commands

Targeted Product explanation:

```text
python -m pytest services/product_api/tests_unit/test_company_report_explanation_models.py services/product_api/tests_unit/test_company_report_explanation_catalog.py services/product_api/tests_unit/test_company_report_explanation_prompt.py services/product_api/tests_unit/test_company_report_explanation_validation.py services/product_api/tests_unit/test_company_report_explanation_service.py -q
```

Targeted Gateway:

```text
python -m pytest services/gateway_api/tests/test_contract.py services/gateway_api/tests/test_structured_contract.py -q
```

Full affected regressions:

```text
python -m pytest services/product_api/tests_unit -q
python -m pytest services/gateway_api/tests -q
python -m compileall -q services/product_api/src/product_api/company_reports services/gateway_api/src/gateway_api shared
git diff --check
```

No UI command is required because UI is intentionally outside this iteration.
Product integration tests requiring PostgreSQL are not applicable because the
plan prohibits persistence/router changes. Python lint/type-check commands are
not configured in this repository.

## 6. Definition of done

- Corrected specification and plan close all mandatory reviewer findings.
- Only the approved scope is implemented.
- Machine score and AI explanation remain separate entities.
- No migration, persistence, Product API endpoint or frontend change exists.
- Targeted and affected regression checks pass without paid requests.
- Full diff passes independent code review without blockers.
- State moves to `ready_for_merge` only after review and checks.
- Main DevFlow agent performs commit/push; merge remains manual.
