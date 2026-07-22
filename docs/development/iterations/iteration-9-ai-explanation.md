# Инженерная итерация 9 — AI-объяснение результата

## 1. Цель и границы

Итерация добавляет ephemeral AI-объяснение готовых `CompanyReport`,
`SignalEvaluationResult` и `ScoringResult`.

Структура результата:

1. общий вывод;
2. факторы в пользу взыскания;
3. основные риски;
4. срочность;
5. рекомендуемый следующий шаг;
6. ограничения и неполнота.

AI не пересчитывает и не изменяет score, level, confidence, direction,
strength, signals или факты. Machine score и explanation — разные контракты.

Нет persistence, миграций, backfill, API endpoint, router, UI, web search,
legal guarantee или claims generation.

## 2. Архитектура

```text
CompanyReport + SignalEvaluationResult + ScoringResult
  -> pure allowlisted envelope
  -> strict AI selection prompt
  -> Product Gateway client (HMAC)
  -> existing POST /v1/chat, structured profile mode
  -> strict JSON Schema model response
  -> parse + schema + grounding validation
  -> deterministic renderer
  -> ephemeral AIExplanationResult
```

Explanation code не импортируется orchestrator, persistence, normalizers,
signals или scoring и не вызывается ими автоматически.

## 3. Product explanation contracts

Все новые domain models immutable, `extra="forbid"` и детерминированно
сортируют collections.

### 3.1. Allowlisted input

`ExplanationInputEnvelope` содержит только:

- `CompanyReport.report_version`, status, completeness и dataset statuses;
- существующие safe report/scoring warning codes;
- signal `code`, category, direction, strength, confidence;
- scoring ruleset version, level, score points, confidence, reason signal codes;
- versioned deterministic `allowed_statement_catalog`.

Не включаются:

- `target_identifier`, название, адрес, менеджеры, реквизиты;
- provider metadata/error text;
- `raw_payload`, raw headers, API keys, auth/session data;
- internal transport errors;
- arbitrary normalized source fields.

Вход сериализуется canonical JSON. Для
`AI_EXPLANATION_MAX_INPUT_TOKENS` используется консервативный UTF-8 byte upper
bound: byte length canonical envelope не превышает budget. Это локальная
верхняя граница входа без новой tokenizer dependency, а не provider usage
accounting.

### 3.2. Strict model output

Модель получает strict JSON Schema `company_recovery_explanation_v1` и
возвращает только selection:

```json
{
  "output_schema_version": "1",
  "overall_conclusion_id": "...",
  "recovery_factor_ids": ["..."],
  "key_risk_ids": ["..."],
  "urgency_id": "...",
  "recommended_next_step_id": "...",
  "limitation_ids": ["..."]
}
```

Все IDs должны присутствовать в соответствующем разделе input catalog.
Массивы уникальны; factors/risks ограничены тремя, limitations — пятью
элементами. Additional keys запрещены. Свободный текст от модели не
допускается.

Product проверяет JSON, schema version, IDs, cardinality и grounding каждого
selected statement в текущих report/signals/scoring/warnings. Только затем
deterministic renderer создаёт шесть пользовательских разделов. Поэтому модель
не может добавить неподтверждённый факт.

### 3.3. Result

```python
class AIExplanation(FrozenDomainModel):
    output_schema_version: Literal["1"]
    overall_conclusion: str
    recovery_factors: list[str]
    key_risks: list[str]
    urgency: str
    recommended_next_step: str
    limitations: list[str]
    prompt_version: str
    model_profile: str
    resolved_model: str
    attempt_count: Literal[1, 2]

class AIExplanationStatus(StrEnum):
    OK = "ok"
    TRANSPORT_FAILURE = "transport_failure"
    INVALID_RESPONSE = "invalid_response"
    CONFIGURATION_ERROR = "configuration_error"

class AIExplanationResult(FrozenDomainModel):
    status: AIExplanationStatus
    explanation: AIExplanation | None
    failure: AIExplanationFailure | None
```

При `ok` задан только `explanation`; при любой ошибке задан только `failure`,
AI text отсутствует. Failure содержит лишь safe code, profile, prompt/schema
versions и retry flag.

## 4. Двухрежимный shared `ChatRequest` contract

`ChatRequest.model` и `metadata` становятся optional только на type level.
Pydantic `model_validator` требует ровно один из двух режимов.

### 4.1. Legacy chat mode

Сохраняет существующий contract:

```json
{
  "messages": [{"role": "user", "content": "..."}],
  "model": "gpt-5.2",
  "stream": false,
  "timeout": 30,
  "metadata": {
    "company_id": 1,
    "user_id": 1,
    "conversation_id": 1,
    "message_id": 1
  }
}
```

Инварианты:

- `model` non-empty и required semantically;
- `metadata` required;
- `model_profile is None`;
- `response_format is None`;
- `max_output_tokens is None`;
- current streaming behavior is unchanged.

Gateway сохраняет legacy `gpt-5.2` allowlist и existing metadata logging для
этого режима.

### 4.2. Structured profile mode

Используется только Iteration 9:

```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "model": null,
  "model_profile": "economy_text_structured_v1",
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "company_recovery_explanation_v1",
      "strict": true,
      "schema": {}
    }
  },
  "max_output_tokens": 600,
  "stream": false,
  "timeout": 20,
  "metadata": null
}
```

Инварианты:

- `model is None`;
- `model_profile` non-empty and required;
- `response_format` required and is strict JSON Schema;
- `max_output_tokens` positive and required;
- `stream is False`;
- `metadata is None`;
- no third/hybrid mode is valid.

Product explanation never knows or sends an external model name. Gateway alone
resolves profile to configured actual model.

## 5. Privacy and Gateway behavior

`POST /v1/chat` remains the sole endpoint and HMAC protection is unchanged.

`gateway_api.main` branches after validated `ChatRequest`:

1. Legacy mode: validate existing direct model; log existing
   company/user/conversation/message metadata; call current plain/stream
   behavior.
2. Structured mode: validate profile; resolve actual model exclusively through
   Gateway `AI_EXPLANATION_MODEL`; do not read or log metadata; log only request
   ID and model profile; pass strict response format and output token cap to
   OpenAI client.

Gateway structured response returns:

```json
{
  "text": "{...}",
  "usage": {},
  "model_profile": "economy_text_structured_v1",
  "resolved_model": "configured-model"
}
```

`model_profile` и non-empty `resolved_model` обязательны в successful structured
responses. Legacy response remains compatible; those fields optional/absent.

No prompt, envelope, schema body, model output, raw header, key or upstream
response body is logged.

## 6. Configuration, prompt, budgets and timeout

Product settings:

```text
AI_EXPLANATION_ENABLED=false
AI_EXPLANATION_MODEL_PROFILE=economy_text_structured_v1
AI_EXPLANATION_PROMPT_VERSION=v1
AI_EXPLANATION_MAX_INPUT_TOKENS=4096
AI_EXPLANATION_MAX_OUTPUT_TOKENS=600
AI_EXPLANATION_TIMEOUT_SECONDS=20
```

All budgets/timeouts are positive. Prompt version matches
`[A-Za-z0-9_.-]{1,32}`.

Gateway settings:

```text
AI_EXPLANATION_MODEL_PROFILE=economy_text_structured_v1
AI_EXPLANATION_MODEL=gpt-5.2
```

The configured profile value is normalized to and must equal the shared
constant `economy_text_structured_v1`. The profile is the default economy text
profile. Deployment config selects its cheapest available
strict-structured-output-capable text model; Product domain remains independent
of that model name. The repository default remains the only model currently
supported by Gateway, `gpt-5.2`.

Per-call timeout flow is mandatory:

```text
Product explanation service
  -> ChatRequest.timeout = AI_EXPLANATION_TIMEOUT_SECONDS
  -> gateway_client httpx timeout = payload.timeout
     (otherwise existing settings.gateway_timeout_seconds)
  -> Gateway passes payload.timeout to create_chat_completion
  -> OpenAI client uses that timeout
```

Structured OpenAI request includes `response_format` and
`max_completion_tokens`. Legacy request shape remains unchanged.

## 7. Audit metadata validation

After a successful structured Gateway response, Product validates:

- `response.model_profile == requested model_profile`;
- `response.resolved_model` is non-empty.

A missing/mismatched profile or missing model is terminal:

```text
status: configuration_error
safe_code: gateway_contract_mismatch
explanation: null
retry: no
```

Successful `AIExplanation` keeps prompt version, schema version, requested
profile and resolved model as ephemeral audit metadata only. Nothing is
persisted.

## 8. Retry/failure semantics

One explanation invocation makes one primary AI call and no more than one
retry.

Retry once only for:

- safe transport failure;
- non-JSON response;
- JSON/schema/grounding validation failure.

No retry for:

- invalid local input/version/budget/configuration;
- HMAC/auth/contract failure;
- `gateway_contract_mismatch`;
- non-transport Gateway failure.

Terminal failures return typed safe `AIExplanationResult` without AI text.
Report, signals and scoring stay independently usable.

## 9. Compatibility and acceptance

- No migration, DB model, serializer, snapshot, lifecycle or API/router/UI
  change.
- Existing legacy `/v1/chat` clients retain required semantic `model` and
  `metadata`.
- Structured mode has no metadata and cannot emit legacy metadata logs.
- Existing Product rule forbidding `OPENAI_API_KEY` remains.
- Tests use mocks only; no paid OpenAI calls.

Acceptance requires:

- only allowlisted data reaches the prompt;
- strict schema and grounding are enforced;
- final text is renderer-derived only;
- machine score fields remain unchanged;
- profile/model audit metadata is checked;
- timeout flows Product -> Gateway -> OpenAI;
- one primary call and at most one permitted retry;
- legacy and structured HMAC paths both pass;
- no metadata logging in structured mode;
- no persistence/API/UI/migration changes;
- affected Product and Gateway suites plus `git diff --check` pass.
