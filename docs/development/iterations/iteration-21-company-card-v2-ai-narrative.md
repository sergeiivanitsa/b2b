# Итерация 21 — Публичное AI-описание Company Card v2

ID: `21`

Slug: `company-card-v2-ai-narrative`

Public contract: `company_public_h2_v1`

Stored report version: `"3"`

New snapshot sub-schema: `company_card_v2_snapshot_v2`

Status: `approved_for_implementation`

Author: `DevFlow planner`

Planning date: `2026-08-24`

Base commit: `f4fe88e51f89a85cbd3c8881affbb8b0b87fbe6c`

Branch: `feat/iteration-21-company-card-v2-ai-narrative`

Review status: `CHANGES_REQUIRED; single correction applied; root blocker audit PASSED; no second plan review`

Production activation: `NOT AUTHORIZED`

## 1. Цель

Добавить к Company Card v2 сохранённое нейтральное описание длиной 400–700 Unicode scalar characters и инфраструктуру максимум для одного AI-dispatch на одну полную immutable generation identity.

AI возвращает только закрытый render plan. Публичный русский текст формируется локальным детерминированным renderer. Недоступность, ошибка или невалидный результат AI всегда дают универсальный deterministic fallback и не блокируют отчёт.

## 2. Нормативные источники

Приоритет:

1. `AGENTS.md`, Roadmap и `DEVFLOW_STATE.yaml`.
2. Итерации 19–20 и их утверждённые решения.
3. `okved-primary-activity-evidence-v1.md`.
4. `iteration-21-ai-narrative-budget-policy-v1.md`.
5. Существующие H1/v1/v2/v3, Gateway HMAC и structured-mode contracts.
6. Эта спецификация.

## 3. Scope

- Строгий parser единственной primary OKVED activity.
- Явное sub-versioning новых v3 snapshots без изменения старых bytes/hash.
- Default-off write-side v3 V2 builder с exact `OKVED_BLOCK` profile; он не
  вызывается из public read path и не запрашивает arbitration/contact/
  manager/owner datasets.
- Минимальный обезличенный narrative evidence envelope.
- Task-specific Gateway profile и strict JSON Schema.
- Allowlisted evidence, statement, connector и template IDs.
- Локальный deterministic renderer, grounding, double-render и hashes.
- Отдельные durable narrative jobs, artifacts, budget reservations/windows.
- Lease/fence/concurrency/one-dispatch state machines.
- Универсальный immutable fallback.
- Exact resolved H2 narrative binding и noindex staged pin.
- Side-effect-free Public H2 GET/HEAD resolution.
- Migration `0017`, unit/Gateway/PostgreSQL tests и disposable runbook.

## 4. Вне scope

- H2 assignment, indexable activation, production rollout или deploy.
- Frontend, SSR shell, charts и React.
- Live/paid OpenAI, DataNewton, FNS или production DB calls.
- Admin UI, ручная модерация, repair/second-AI call.
- Signals, scoring, verdict, probability, recommendations.
- Refresh/backfill provider data старых reports.
- Positive production budget/concurrency thresholds or model pricing.
- Additional OKVED activities, percentages, revenue share or effective date.
- Changes to H1 public contract or saved v1/v2/v3 bytes.

## 5. Compatibility and primary-activity persistence

### 5.0. Reachable write path

Iteration 20 intentionally shipped no runtime v3 provider builder. Iteration
21 adds `build_company_card_v2_snapshot_v2` behind the existing literal
`COMPANY_CARD_V2_WRITER_ENABLED=false` default. It runs only for the exact
stored tuple:

```text
writer_profile = company_card_v2_writer_v3
report_version = "3"
presentation_contract = company_public_h2_v1
rollout_config_generation > 0
```

The builder accepts an injected provider protocol and explicit clock. Its only
counterparty request is:

```text
endpoint = GET /v1/counterparty
filters = [OKVED_BLOCK]
source_profile_version = company_card_v2_counterparty_okved_primary_v1
```

It may request the already approved finance dataset to build the iteration-20
finance basis. It performs no arbitration request while that gate remains
closed and never requests `CONTACT_BLOCK`, `MANAGER_BLOCK`, `OWNER_BLOCK` or
`WORKERS_COUNT_BLOCK`. The provider client stays outside pure parsers.

Dataset results are bound to the exact target and normalized independently.
Counterparty/finance partial failure produces the existing explicit
complete/partial/failed semantics; no missing fact becomes zero. Only a
complete or partial immutable v3 V2 snapshot is finalized. Report finalization
and narrative outbox insertion then commit atomically. Unit/integration tests
use injected fakes only; no implementation test performs a live call.

### 5.1. Frozen old v3

Текущая точная v3 shape становится моделью `CompanyCardV2SnapshotV1`.

Parser dispatch:

```text
report_version != literal string "3" -> reject from v3 parser

report_version="3" and snapshot_schema_version absent
  -> validate only exact frozen CompanyCardV2SnapshotV1

report_version="3" and
snapshot_schema_version="company_card_v2_snapshot_v2"
  -> validate only exact CompanyCardV2SnapshotV2

any other/malformed/coerced discriminator -> reject
```

Для сохранённых V1 snapshots:

- bytes и snapshot hash не меняются;
- новые default fields не материализуются;
- snapshot не rewrite/backfill/refresh;
- H1 и v1/v2 parsers не меняются;
- public primary activity отсутствует;
- write-side reconciler сохраняет universal fallback artifact/binding без
  provider refresh и без изменения snapshot;
- пока saved binding отсутствует, public read возвращает
  `409 report_not_eligible`, а не синтезирует fallback;
- unresolved active/staged pin остаётся неeligible и не переосмысливается.

### 5.2. New v3 sub-schema

Новый writer после итерации 21 пишет только:

```text
report_version = "3"
snapshot_schema_version = "company_card_v2_snapshot_v2"
```

Это сохраняет существующий report/pin/public-H2 version axis, но явно создаёт новую snapshot generation.

`CompanyCardV2SnapshotV2` содержит versioned:

```text
narrative_evidence:
  schema_version
  primary_activity_parser_version
  primary_activity_evidence_version
  source_profile_version
  primary_activity | null
  limitation_code | null
```

`primary_activity` содержит только:

```text
code
label
is_primary = true
```

Никаких additional activities, `mode`, effective date, percentage или revenue-share полей в public DTO нет. Opaque `mode="new"` проверяется parser-ом, но публично и в Gateway input не выводится.

Snapshot schema/parser/evidence versions входят в generation identity.

### 5.3. Strict admission rule

Activity доступна, только если одновременно:

1. result связан с exact target INN;
2. был явно запрошен `OKVED_BLOCK`;
3. dataset успешно получен;
4. `$.company.okveds` — array из `1..100` строгих объектов; evidence cohort
   содержит допустимый случай из `45` строк;
5. каждый объект содержит только exact `code`, `value`, `main`, `mode`;
6. `main` — literal boolean;
7. ровно одна строка имеет `main=true`;
8. после нормализации каждый row занимает не более `2048` UTF-8 bytes в
   `CJSON_company_public_h2_cjson_v1`, весь normalized array — не более
   `65536` bytes; равная граница принимается, `+1` отвергается;
9. выбранный code соответствует
   `^[0-9]{2}(?:\.[0-9]{1,2}){0,2}$`, `2..8` Unicode scalars/ASCII bytes;
10. выбранный label после общей text normalization содержит `1..128`
    Unicode scalars и не более `512` UTF-8 bytes;
11. `mode` каждой строки — строка `1..16` scalars, а у primary row равен
    opaque literal `"new"`;
12. другая строка с primary code и иным normalized label/mode или с primary
    normalized label и иным code отвергает весь activity block.

Полностью одинаковая non-primary duplicate выбранной строки допустима:
единственной primary остаётся строка с literal `main=true`. Duplicate/conflict
между исключительно additional rows не влияет на выбор и не сохраняется;
это необходимо для наблюдавшегося evidence case `45 rows / 43 unique codes`.
Любое иное нарушение даёт `primary_activity=null` и closed limitation
`primary_activity_not_admitted`. Запрещены first-row, fuzzy, name-based и
secondary-row fallbacks.

## 6. AI input privacy contract

Gateway получает только:

```text
input_schema_version
evidence_registry_version
insight_catalog_version
statement_catalog_version
template_catalog_version
allowed evidence IDs
neutral availability/limitation relations
approved primary-activity label, when admitted
closed render-plan schema
```

Запрещены:

- INN, OGRN, KPP, report/subject/company identifiers;
- company name, address, manager/owner or party data;
- raw values, amounts, percentages and chart numbers;
- raw/provider payload, headers, errors or URLs;
- signals, scoring, verdict, probability or recommendations;
- auth/session/API keys.

Primary OKVED code остаётся в snapshot/public requisites, но Gateway получает только approved label and evidence ID.

Prompt, schema body, evidence label, model output and rendered text не логируются.

## 7. Render-plan contract

Task-specific identifiers:

```text
model_profile = company_card_narrative_structured_v1
json_schema_name = company_card_narrative_render_plan_v1
output_schema_version = company_card_narrative_render_plan_v1
```

Model output:

```json
{
  "output_schema_version": "company_card_narrative_render_plan_v1",
  "description_plan": {
    "intro_template_id": "allowlisted-id",
    "statement_ids": ["allowlisted-id"],
    "connector_ids": ["allowlisted-id"]
  },
  "chart_comments": []
}
```

Runtime schema фиксирует единственный допустимый description plan:

```text
intro_template_id = intro_snapshot_scope_v1
statement_ids = [
  statement_primary_activity_v1,
  statement_missing_is_unknown_v1,
  statement_neutrality_and_immutability_v1
]
connector_ids = [
  connector_intro_activity_v1,
  connector_activity_missing_v1,
  connector_missing_neutrality_v1
]
chart_comments = []
```

Каждый object рекурсивно имеет `additionalProperties=false`; runtime arrays
имеют exact `minItems=maxItems`, positional `const` IDs и deterministic order.
Model не возвращает prose, labels, amounts, percentages или другие numbers.

Normative catalogs:

```text
input_schema_version =
  company_card_narrative_input_v1
insight_catalog_version =
  company_card_narrative_insight_catalog_v1
statement_catalog_version =
  company_card_narrative_statement_catalog_v1
template_catalog_version =
  company_card_narrative_template_catalog_v1
connector_catalog_version =
  company_card_narrative_connector_catalog_v1

intro_snapshot_scope_v1 =
  "Описание сформировано по сохранённому снимку отчёта и использует только сведения, прошедшие проверки источника, единиц и публичной приватности."

statement_primary_activity_v1 =
  "Основной вид деятельности в допущенных исходных данных обозначен как «{primary_activity_label}»."

statement_missing_is_unknown_v1 =
  "Отсутствующее значение, неполный набор или закрытый раздел не превращаются в ноль, отрицательный факт либо положительный вывод о компании."

statement_neutrality_and_immutability_v1 =
  "Текст не содержит оценки надёжности, вероятности результата, совета, прогноза или неподтверждённой рекомендации. Последующее изменение источника требует новой генерации и не меняет уже опубликованный снимок."

connector_intro_activity_v1 = " "
connector_activity_missing_v1 = " "
connector_missing_neutrality_v1 = " "
```

При label длиной `1..128` этот exact plan рендерит `564..691` scalars.
Implementer не добавляет и не редактирует business prose.

Catalog relations are exact:

```text
intro_snapshot_scope_v1
  -> public statement_id: statement_snapshot_scope_v1
  -> evidence_ids: [evidence_snapshot_identity_v1]

statement_primary_activity_v1
  -> evidence_ids: [evidence_primary_activity_v1]

statement_missing_is_unknown_v1
  -> evidence_ids: [evidence_missing_semantics_policy_v1]

statement_neutrality_and_immutability_v1
  -> evidence_ids: [evidence_neutrality_policy_v1]

insight catalog:
  primary_activity_available_v1
    requires evidence_primary_activity_v1
    permits statement_primary_activity_v1

public statement_ids, in rendered order:
  [statement_snapshot_scope_v1,
   statement_primary_activity_v1,
   statement_missing_is_unknown_v1,
   statement_neutrality_and_immutability_v1]
```

`evidence_snapshot_identity_v1` and `evidence_primary_activity_v1` are bound to
the exact report/snapshot. The two policy evidence IDs are bound to the exact
`policy_version` and contain no company fact. Phrase trace uses these mappings
and exact half-open scalar ranges. No renderer branch may invent a different
statement/evidence relation.

Runtime catalog не содержит visible chart bindings, поэтому runtime `chart_comments` обязан быть `[]`. Общий validator допускает 0–2 comments только в sanitized pure fixtures с injected visible-chart registry. Третий, duplicate, hidden или unsupported chart reference отвергается.

Fixture-only comment schema:

```text
chart_comments: array, 0..2
item: exact object, additionalProperties=false
  chart_id: exact member injected visible-chart registry
  comment_template_id: exact member injected comment catalog
  evidence_ids: 1..8 unique allowlisted IDs
```

Каждый `comment_template_id` отображается ровно в один allowlisted statement и
рендерит один comment `1..280` scalars. `chart_id` должен принадлежать exact
same-report/snapshot Chart Facts, быть public-visible и supported. Duplicate
`chart_id`, hidden reference, zero/multiple statement mapping или evidence из
другого snapshot отвергаются.

## 8. Validation and deterministic renderer

Перед artifact publication Product проверяет:

1. exact recursive schema;
2. output/schema/context versions;
3. allowlisted IDs и cardinality;
4. statement-to-evidence grounding;
5. exact same report/snapshot/chart/evidence identity;
6. provider dataset/request/success/target gates, unit gates и privacy gates;
7. отсутствие hidden chart references;
8. runtime comments count `0`;
9. rendered description length `400..700`;
10. comment length `1..280` в fixture-only tests;
11. два независимых render pass дают одинаковые UTF-8 bytes;
12. stored render hash равен повторному hash;
13. raw model text не пересекает public/log/telemetry boundary;
14. никакой выбранный ID не допускает score, verdict, probability, advice,
    unsupported comparison или неподтверждённое отсутствие;
15. каждый fixture comment содержит ровно один allowlisted statement.

Единая normalization function применяется к admitted label, catalog fragments,
model string leaves до schema rejection и rendered output строго в порядке:

1. reject unpaired surrogate, NUL, bidi override и C0/C1 controls кроме
   `TAB/LF/CR`;
2. Unicode NFC;
3. заменить `CRLF` и lone `CR` на `LF`;
4. удалить leading/trailing Unicode `White_Space`;
5. каждую максимальную последовательность Unicode `White_Space` заменить
   одним ASCII space;
6. считать Unicode scalar values и UTF-8 bytes итоговой строки.

Границы `399/400/700/701`, `127/128/129` label scalars и exact byte
boundary/`+1` обязательны.

Любая ошибка завершает generation fallback-ом без repair или второго AI call.

Public requisites получают ровно одну `primary_activity` только из admitted V2 evidence. Renderer может утверждать лишь, что label является основной деятельностью согласно допущенным source data.

## 9. Immutable identities

Iteration-19 `GenerationIdentityV1` не изменяется ни полями, ни literal, ни
формулой:

```text
GenerationIdentityV1:
  identity_version = "GenerationIdentityV1"
  report_id
  snapshot_hash
  chart_facts_hash
  evidence_registry_version
  statement_catalog_version
  template_catalog_version
  prompt_version
  json_schema_version
  policy_version
  renderer_version
  gateway_profile_version
  fallback_catalog_version
```

```text
generation_key_v1 =
  SHA256(UTF8(CJSON_company_public_h2_cjson_v1(GenerationIdentityV1)))
```

Iteration 21 вводит новый, не совместимый по bytes, явно названный
`GenerationIdentityV2`. Он содержит все exact V1 fields без переименования и
дополнительно:

```text
identity_version = "GenerationIdentityV2"
snapshot_schema_version
narrative_evidence_schema_version
primary_activity_parser_version
primary_activity_evidence_version
insight_catalog_version
connector_catalog_version
input_schema_version
```

```text
generation_key_v2 =
  SHA256(UTF8(CJSON_company_public_h2_cjson_v1(GenerationIdentityV2)))
```

Все iteration-21 generations используют V2. Для legacy snapshots identity-only
sentinels равны:

```text
snapshot_schema_version:
  company_report_snapshot_v1_legacy |
  company_report_snapshot_v2_legacy |
  company_card_v2_snapshot_v1 |
  company_card_v2_snapshot_v2
narrative_evidence_schema_version = narrative_evidence_absent_v1
primary_activity_parser_version = not_applicable_v1
primary_activity_evidence_version = not_applicable_v1
```

Sentinels не записываются в old snapshot и не меняют его bytes/hash.
`resolved_model_version` намеренно отсутствует в V1/V2 generation identity.

AI artifact identity:

```text
ArtifactIdentityV1:
  identity_version = "ArtifactIdentityV1"
  generation_key
  resolved_model_version
  validated_render_plan_bytes_sha256
  rendered_output_bytes_sha256

artifact_identity =
  SHA256(UTF8(CJSON_company_public_h2_cjson_v1(ArtifactIdentityV1)))
```

Это exact iteration-19 `ArtifactIdentityV1`; он не переопределяется и может
ссылаться на V1 либо V2 generation key. Изменение resolved model при
неизменном generation key создаёт другой artifact identity.

Fallback использует exact iteration-19:

```text
company_card_h2_fallback_catalog_v1
fallback_profile_any_v1
company_card_h2_fallback_renderer_v1
FallbackIdentityV1
```

и exact 691-scalar literal из iteration 19. `binding_key` равен artifact
identity либо fallback identity. Изменение любого V2 field, включая
connector/input/fallback catalog, создаёт новый generation key и не заменяет
существующий binding.

## 10. Durable data model

Migration `0017_company_card_v2_ai_narrative` добавляет:

```text
company_card_narrative_outbox
company_card_narrative_runtime_control
company_card_narrative_budget_windows
company_card_narrative_budget_reservations
company_card_narrative_jobs
company_card_narrative_artifacts
```

Exact SQL contract:

```text
company_card_narrative_outbox
  id UUID PK
  report_id UUID NOT NULL FK company_reports(id) ON DELETE RESTRICT
  snapshot_hash CHAR(64) NOT NULL CHECK lowercase hex
  event_kind VARCHAR(48) NOT NULL CHECK = 'initialize_narrative_v1'
  state VARCHAR(16) NOT NULL CHECK IN
    ('pending','leased','processed','terminal')
  available_at TIMESTAMPTZ NOT NULL
  lease_token UUID NULL
  lease_expires_at TIMESTAMPTZ NULL
  fence_generation BIGINT NOT NULL DEFAULT 0 CHECK >= 0
  attempt_count SMALLINT NOT NULL DEFAULT 0 CHECK BETWEEN 0 AND 3
  failure_code VARCHAR(64) NULL
  generation_key CHAR(64) NULL
    FK company_card_narrative_jobs(generation_key) DEFERRABLE INITIALLY DEFERRED
  created_at TIMESTAMPTZ NOT NULL
  updated_at TIMESTAMPTZ NOT NULL
  processed_at TIMESTAMPTZ NULL
  UNIQUE(report_id,snapshot_hash,event_kind)
  leased shape requires token+expiry; other states require both NULL;
  processed requires processed_at+generation_key and null failure_code;
  terminal requires failure_code and null generation_key;
  pending/leased require processed_at+generation_key+failure_code all NULL

company_card_narrative_runtime_control
  singleton_id SMALLINT PK CHECK = 1
  enabled BOOLEAN NOT NULL DEFAULT FALSE
  kill_switch BOOLEAN NOT NULL DEFAULT TRUE
  daily_limit INTEGER NOT NULL DEFAULT 0 CHECK >= 0
  monthly_limit INTEGER NOT NULL DEFAULT 0 CHECK >= 0
  concurrency_limit INTEGER NOT NULL DEFAULT 0 CHECK >= 0
  leased_count INTEGER NOT NULL DEFAULT 0 CHECK >= 0
  updated_at TIMESTAMPTZ NOT NULL

company_card_narrative_budget_windows
  period_kind VARCHAR(7) NOT NULL CHECK IN ('daily','monthly')
  period_start_local DATE NOT NULL
  starts_at_utc TIMESTAMPTZ NOT NULL
  ends_at_utc TIMESTAMPTZ NOT NULL CHECK starts_at_utc < ends_at_utc
  reserved_count INTEGER NOT NULL DEFAULT 0 CHECK >= 0
  consumed_count INTEGER NOT NULL DEFAULT 0 CHECK >= 0
  PRIMARY KEY(period_kind,period_start_local)

company_card_narrative_jobs
  id UUID PK
  report_id UUID NOT NULL FK company_reports(id) ON DELETE RESTRICT
  snapshot_hash CHAR(64) NOT NULL CHECK lowercase hex
  generation_key CHAR(64) NOT NULL UNIQUE CHECK lowercase hex
  identity_version VARCHAR(32) NOT NULL CHECK IN
    ('GenerationIdentityV1','GenerationIdentityV2')
  generation_identity JSONB NOT NULL
  state VARCHAR(24) NOT NULL CHECK IN
    ('ready','leased','dispatching','dispatched','validating','rendered',
     'finalized','pre_dispatch_failed','ambiguous_timeout',
     'invalid_output','fallback_finalized')
  available_at TIMESTAMPTZ NOT NULL
  lease_token UUID NULL
  lease_expires_at TIMESTAMPTZ NULL
  fence_generation BIGINT NOT NULL DEFAULT 0 CHECK >= 0
  local_attempt_count SMALLINT NOT NULL DEFAULT 0 CHECK BETWEEN 0 AND 3
  gateway_dispatch_id UUID NULL UNIQUE
  dispatch_started_at TIMESTAMPTZ NULL
  response_received_at TIMESTAMPTZ NULL
  resolved_model_version VARCHAR(255) NULL
  validation_codes JSONB NOT NULL DEFAULT '[]'
  artifact_id UUID NULL
  created_at TIMESTAMPTZ NOT NULL
  updated_at TIMESTAMPTZ NOT NULL
  artifact_id is UNIQUE when non-null;
  states dispatching/dispatched/validating/rendered/finalized/
    ambiguous_timeout/invalid_output require dispatch id/start;
  states ready/leased/pre_dispatch_failed require dispatch id/start/model/
    response all NULL;
  fallback_finalized permits null dispatch fields only for pre-dispatch
    fallback and otherwise requires dispatch id/start;
  states leased/dispatching/dispatched/validating/rendered require
    lease token+expiry; every other state requires both NULL

company_card_narrative_budget_reservations
  generation_key CHAR(64) PK
    FK company_card_narrative_jobs(generation_key) ON DELETE RESTRICT
  dispatch_credit SMALLINT NOT NULL CHECK = 1
  state VARCHAR(10) NOT NULL CHECK IN ('reserved','released','consumed')
  daily_period_kind VARCHAR(7) NOT NULL CHECK = 'daily'
  daily_period_start_local DATE NOT NULL
  monthly_period_kind VARCHAR(7) NOT NULL CHECK = 'monthly'
  monthly_period_start_local DATE NOT NULL
  reservation_epoch SMALLINT NOT NULL DEFAULT 1 CHECK BETWEEN 1 AND 3
  reserved_at TIMESTAMPTZ NOT NULL
  last_released_at TIMESTAMPTZ NULL
  consumed_at TIMESTAMPTZ NULL
  release_code VARCHAR(64) NULL
  FK daily pair -> budget_windows
  FK monthly pair -> budget_windows
  consumed iff consumed_at non-null; non-consumed requires consumed_at null

company_card_narrative_artifacts
  id UUID PK
  report_id UUID NOT NULL FK company_reports(id) ON DELETE RESTRICT
  snapshot_hash CHAR(64) NOT NULL CHECK lowercase hex
  generation_key CHAR(64) NOT NULL UNIQUE
    FK company_card_narrative_jobs(generation_key) ON DELETE RESTRICT
  binding_kind VARCHAR(8) NOT NULL CHECK IN ('artifact','fallback')
  binding_key CHAR(64) NOT NULL CHECK lowercase hex
  artifact_identity CHAR(64) NULL
  fallback_identity CHAR(64) NULL
  resolved_model_version VARCHAR(255) NULL
  raw_model_output TEXT NULL CHECK octet_length <= 16384
  validated_render_plan_cjson BYTEA NULL CHECK octet_length <= 16384
  validated_render_plan_bytes_sha256 CHAR(64) NULL
  rendered_description TEXT NOT NULL
  rendered_comments JSONB NOT NULL DEFAULT '[]'
  statement_ids JSONB NOT NULL
  evidence_ids JSONB NOT NULL
  phrase_trace JSONB NOT NULL
  validation_codes JSONB NOT NULL
  renderer_version VARCHAR(96) NOT NULL
  rendered_output_bytes_sha256 CHAR(64) NOT NULL
  created_at TIMESTAMPTZ NOT NULL
  UNIQUE(binding_kind,binding_key)
  artifact kind requires artifact identity/model/plan hashes and null fallback id;
  fallback kind requires fallback identity, null model/raw/plan/artifact id,
  exact fallback renderer and comments='[]'
```

`company_card_narrative_jobs.artifact_id` получает deferred unique FK на artifacts
после создания обеих таблиц. Resolved H2 pin получает composite nullable FK
`(narrative_binding_kind,narrative_binding_key)` на artifact unique pair.

### Runtime control

Singleton row сериализует cross-process reservation and claim decisions.

### Budget window

Key:

```text
(period_kind, moscow_period_start_date)
```

Stores exact UTC start/end and current reserved-or-consumed credits. Daily and monthly rows are locked in fixed daily→monthly order.

### Reservation

Одна row на generation key:

```text
dispatch_credit = 1
state = reserved | released | consumed
daily window identity
monthly window identity
reserved/released/consumed timestamps
```

Provider usage, token counts, prices and model cost никогда не меняют credit/counters.

### Job

Хранит полный generation tuple, state, lease token/expiry, fence, local attempts, dispatch markers, response/validation metadata и artifact reference.

### Artifact

Private immutable row:

```text
generation_key
binding_kind = artifact | fallback
binding_key
artifact_identity | fallback_identity
bounded raw model output
validated render plan
rendered description/comments
statement/evidence IDs
validation codes
resolved model version | null
rendered bytes hash
created_at
```

Raw output доступен только repository/worker path и никогда не сериализуется в Public H2.

## 11. Job, dispatch and budget state machines

Outbox создаётся в той же database transaction, которая переводит report в
finalized `complete|partial`. Report commit без outbox commit невозможен.
После commit отдельный reconciler claim-ит outbox и идемпотентно создаёт job
либо сохранённый fallback artifact/binding. Crash между report commit и
reconciler invocation оставляет durable `pending` outbox.

Generation states:

```text
ready -> leased -> dispatching -> dispatched
      -> validating -> rendered -> finalized

ready/leased -> pre_dispatch_failed -> ready
ready/leased -> fallback_finalized
dispatching/dispatched/validating/rendered
         -> ambiguous_timeout | invalid_output
         -> fallback_finalized
```

`pre_dispatch_failed -> ready` через exact release/re-reserve разрешён только
при:

- no dispatch marker/id/model/response;
- closed pre-dispatch failure code;
- exact lease/fence;
- `local_attempt_count < 3`.

Перед external call worker одной committed transaction:

1. сверяет kill switch/config/lease/fence;
2. переводит reservation `reserved→consumed`;
3. записывает unique `gateway_dispatch_id`;
4. записывает `dispatch_started_at`;
5. переводит job в `dispatching`;
6. commit.

Только затем выполняется HMAC Gateway call. После этого автоматический retry запрещён для timeout, worker death, lost response, Gateway error, invalid/schema/policy response или stale ownership.

Expired `dispatching` является ambiguous terminal work и получает fallback. Stale lease/fence не может dispatch, validate, finalize artifact или pin.

Mutation APIs разделены без optional lease arguments:

```text
Pre-lease, identity-guarded and row-locked:
  insert_narrative_outbox(report_id,snapshot_hash)
  initialize_generation(GenerationIdentityV2)
  reserve_or_rereserve_credit(generation_key,clock)
  release_pre_dispatch_credit(generation_key,failure_code,clock)
  claim_outbox(...)
  claim_narrative_job(...)

Leased/fenced, always requiring
job_id + generation_key + lease_token + fence_generation:
  heartbeat_job(...)
  mark_dispatching(...)
  record_gateway_response(...)
  mark_validating(...)
  finalize_ai_artifact(...)
  finalize_fallback_after_dispatch(...)
```

Expired-lease reconciliation is a separate system mutation which locks the
exact row, verifies expired timestamp/state/fence and increments the fence.
It never accepts or imitates a worker token.

## 12. Budget and concurrency policy

Moscow windows:

```text
daily   = [local 00:00, next local 00:00)
monthly = [first local day 00:00, next month local 00:00)
```

Configuration defaults:

```text
COMPANY_CARD_AI_NARRATIVE_ENABLED=false
COMPANY_CARD_AI_NARRATIVE_KILL_SWITCH=true
COMPANY_CARD_AI_NARRATIVE_DAILY_DISPATCH_CREDITS=0
COMPANY_CARD_AI_NARRATIVE_MONTHLY_DISPATCH_CREDITS=0
COMPANY_CARD_AI_NARRATIVE_WORKER_CONCURRENCY=0
```

Kill switch открыт только при literal `false`. AI enablement требует
`enabled=true`, `kill_switch=false` и все три values positive; иначе startup
fails closed. Никакие positive production values эта итерация не задаёт.

Reservation transaction locks runtime control plus daily/monthly rows, checks both limits, increments both and inserts one unique reservation. Definitive pre-dispatch release decrements both atomically. Dispatch/fallback после dispatch credit не возвращают.

Exact reschedule semantics:

1. definitive pre-dispatch failure is allowed only with all dispatch fields
   null and allowlisted local failure code;
2. one transaction locks control, reservation and its daily/monthly windows in
   deterministic order, decrements both `reserved_count`, sets
   `state=released`, increments job `local_attempt_count` and records release;
3. if count is `1` or `2`, a later reservation transaction recomputes
   Europe/Moscow day/month from injected current UTC clock, locks the new
   windows, checks current limits, increments their `reserved_count`, updates
   both reservation FKs, increments `reservation_epoch` and performs exact
   `released→reserved`;
4. if Moscow day or month changed, no counter is transferred by arithmetic:
   old window remains decremented and new window is incremented exactly once;
5. count `3`, limit exhaustion or closed controls finalizes saved fallback;
6. `reserved→consumed` atomically decrements both reserved counters and
   increments both consumed counters; `consumed` is terminal and never
   released/re-reserved.

Два local failures/reschedules, в том числе через simultaneous Moscow
day/month boundary, затем success используют одну reservation row, три
reservation epochs и ровно один consumed dispatch credit.

Concurrency slot занят только job states `leased`, `dispatching`,
`dispatched`, `validating` и `rendered`. Claim одной transaction блокирует
runtime control, требует `leased_count < concurrency_limit`, переводит exact
`ready→leased` и увеличивает `leased_count` на один. Любой переход из этого
множества в `ready`, `finalized`, `pre_dispatch_failed`,
`ambiguous_timeout`, `invalid_output` или `fallback_finalized` уменьшает
counter ровно один раз в той же transaction. Expired-lease reconciler делает
тот же decrement под lock; повторный reconciliation idempotent. DB/application
checks запрещают negative count и count выше positive configured limit.

Fallback and public reads consume zero credits.

## 13. Generation and public binding

Report finalization и outbox insertion выполняются одной transaction.
Narrative initialization и external work выполняются позже reconciler/worker.

- New V2 snapshot with admitted activity and open budget/config creates one reservation/job.
- Missing activity, disabled feature, closed kill switch or exhausted budget
  materializes and saves fallback on the reconciler write path without Gateway.
- Old v1/v2/frozen-v3 reports are never provider-refreshed; migration-created
  outbox rows cause write-side materialization of the universal fallback.
- Public reads never synthesize pending/latest-unpublished fallback.
- Successful/terminal generation creates one immutable artifact or fallback binding.
- For exact report version `"3"` only, a resolved noindex H2 pin and staged
  pointer may be created atomically for that exact report/hash/artifact.
- Legacy report versions `"1"|"2"` cannot own H2 pins. Their safe
  `latest_unpublished` preview joins the saved fallback artifact directly by
  exact `report_id + snapshot_hash + generation_key` and remains
  `indexable=false`; no pointer or assignment is created.
- No H2 assignment is created or changed.
- A later artifact cannot replace an existing resolved pin; republish requires a new explicit generation.
- Active/staged unresolved iteration-20 pins remain terminally ineligible rather than being silently reinterpreted.

For v3, public GET/HEAD selects exact assignment → staged pin → lifecycle head.
For legacy v1/v2 only when no v3 lifecycle exists, it selects the existing
deterministic latest compatible report and requires its exact saved fallback
artifact. Both paths validate report, snapshot, hashes and saved binding and
render only a persisted artifact. GET, HEAD, the iteration-21 SSR projection
adapter and crawler User-Agent requests execute the same SELECT-only resolver
and never enqueue, write, reserve, refresh or call Gateway/provider. Iteration
22 owns the page shell; iteration 25 owns assignment/production activation.

Saved fallback maps exactly to `company_public_h2_v1`:

```text
mode = "deterministic_fallback"
renderer_version = "company_card_h2_fallback_renderer_v1"
description = exact iteration-19 691-scalar fallback_profile_any_v1 literal
statement_ids = ["fallback_profile_any_v1"]
comments = []
render_digest =
  e54d792c1b9543a6ed38f507532c74b33febd800f9a8efcf5115c9247eb6c4dd

private artifact:
  evidence_ids = []
  phrase_trace = [{
    scalar_start: 0,
    scalar_end: 691,
    statement_id: "fallback_profile_any_v1",
    evidence_ids: []
  }]
```

Saved AI artifact maps with `mode="artifact"`,
`renderer_version="company_card_narrative_renderer_v1"`, exact stored
description/statement IDs, runtime `comments=[]` and digest of exact normalized
UTF-8 description bytes. Every rendered phrase has an immutable scalar range,
one statement ID and its exact evidence IDs. Narrative artifacts never update
snapshot, signals or scoring.

For both iteration-21 artifact kinds,
`rendered_output_bytes = UTF8(normalized_description)` because runtime comments
are exactly empty. `render_digest` and
`rendered_output_bytes_sha256` are the lowercase SHA-256 of those exact bytes.
`validated_render_plan_bytes` are the exact
`CJSON_company_public_h2_cjson_v1` bytes of the recursively validated plan.
Later non-empty chart comments require a new renderer/artifact contract version.

## 14. Gateway contract

Existing `/v1/chat` and HMAC canonical signing remain.

Gateway adds a separate profile-to-model setting for
`company_card_narrative_structured_v1`. Product never sends an external model
name and never owns `OPENAI_API_KEY`.

Exact defaults:

```text
Gateway:
  COMPANY_CARD_NARRATIVE_GATEWAY_ENABLED=false
  COMPANY_CARD_NARRATIVE_MODEL_PROFILE=company_card_narrative_structured_v1
  COMPANY_CARD_NARRATIVE_MODEL=<unset>
  COMPANY_CARD_NARRATIVE_TIMEOUT_SECONDS=20
  COMPANY_CARD_NARRATIVE_MAX_OUTPUT_TOKENS=600

Product:
  COMPANY_CARD_AI_NARRATIVE_ENABLED=false
  COMPANY_CARD_AI_NARRATIVE_KILL_SWITCH=true
  COMPANY_CARD_AI_NARRATIVE_DAILY_DISPATCH_CREDITS=0
  COMPANY_CARD_AI_NARRATIVE_MONTHLY_DISPATCH_CREDITS=0
  COMPANY_CARD_AI_NARRATIVE_WORKER_CONCURRENCY=0
  COMPANY_CARD_AI_NARRATIVE_GATEWAY_TIMEOUT_SECONDS=20
  COMPANY_CARD_AI_NARRATIVE_MAX_OUTPUT_TOKENS=600
```

Narrative request is rejected before provider call when gateway profile is
disabled. `enabled=true` with missing/blank narrative model fails Gateway
settings validation at startup. Narrative timeout must be integer `1..20`,
`max_output_tokens` integer `1..600`, serialized request body at most `32768`
bytes and returned `text` at most `16384` UTF-8 bytes. Existing legacy and
iteration-9 defaults/limits remain unchanged.

Immediately before dispatch Product generates canonical lowercase hyphenated
UUID text and stores it as `gateway_dispatch_id`. Exact request contract:

```text
header:
  X-Gateway-Dispatch-ID: <canonical UUID>
body:
  gateway_dispatch_id: <same canonical UUID>
  model_profile: company_card_narrative_structured_v1
  model: null/omitted
  metadata: null/omitted
  stream: false
  timeout: integer 1..20
  max_output_tokens: integer 1..600
  response_format.json_schema.name:
    company_card_narrative_render_plan_v1
```

`gateway_dispatch_id` is included in the serialized body before
`X-Body-SHA256` and HMAC calculation, so existing canonical HMAC signs it via
the body hash. Gateway verifies HMAC first, then requires exact
header/body equality. Success response contains:

```text
gateway_dispatch_id: exact request UUID
model_profile: company_card_narrative_structured_v1
resolved_model: nonempty Gateway-resolved string
text: bounded structured output
```

Product requires stored/request-header/request-body/response IDs to be
identical. Missing/malformed/mismatched echo is terminal
`gateway_dispatch_id_mismatch`: consumed credit, saved fallback, no retry.
`ChatRequest.gateway_dispatch_id` and `ChatResponse.gateway_dispatch_id` are
optional for backward compatibility but required by this profile.

Gateway requires:

- structured mode, no metadata, no stream;
- exact profile and schema name;
- strict response format;
- bounded output cap and timeout;
- request ID/gateway dispatch ID propagation.

Success returns matching profile and nonempty resolved model. Profile/schema mismatch, missing audit metadata or auth failure is terminal fallback with no retry.

Legacy chat and iteration-9 explanation profile remain source/behavior compatible.

## 15. Failure matrix

| Condition | Dispatch credit | Result |
|---|---:|---|
| Old v1/v2/v3 snapshot | 0 | write-side saved universal fallback |
| V2 activity unavailable | 0 | write-side saved universal fallback |
| Feature/kill switch closed | 0 | write-side saved universal fallback |
| Daily/monthly exhausted | 0 | write-side saved universal fallback |
| Definitive pre-dispatch lease loss | released | bounded local reschedule |
| Local attempts exhausted | 0 | fallback finalized |
| Dispatch marker committed, timeout/death/lost response | 1 | ambiguous fallback, no retry |
| Gateway HTTP/auth/profile error after dispatch | 1 | fallback, no retry |
| Invalid JSON/schema/IDs/grounding/privacy | 1 | fallback, no second call |
| Render mismatch/length/hash mismatch | 1 | fallback |
| Stale lease/fence finalization | unchanged | rejected, winner remains |
| Corrupt artifact/pin/hash on read | 0 | fail closed, no fallback to another report |

Exact public read matrix:

| Saved state selected by exact resolver | HTTP result |
|---|---|
| report lifecycle still pending | `409 report_pending` |
| report lifecycle failed, no older exact projection | `409 report_failed` |
| finalized report, outbox/job pending but no binding | `409 report_not_eligible` |
| finalized v3 report, missing/unpinned/unresolved binding | `409 report_not_eligible` |
| selected legacy v1/v2 report with exact saved fallback artifact | `200`, exact noindex legacy preview |
| selected legacy v1/v2 report without exact saved fallback artifact | `409 report_not_eligible` |
| stale/unavailable unbound AI candidate | ignore candidate; `409 report_not_eligible` |
| valid saved AI binding | `200`, exact artifact |
| valid saved fallback binding | `200`, exact fallback |
| active/staged unresolved iteration-20 pin | `409 report_not_eligible` |
| bound artifact has stale version, invalid status or hash mismatch | `500 public_projection_invalid` |
| bound key/FK/report/snapshot missing or mismatched | `500 public_projection_invalid` |
| malformed DTO, comments or digest | `500 public_projection_invalid` |

Missing/stale/invalid Gateway output selects and saves fallback on the write
path before binding. Read-time corruption never falls back to a different
artifact/report and never repairs data.

## 16. Privacy, logging and telemetry

Allowed logs/metrics:

- job UUID;
- closed state transition;
- safe failure/validation code;
- model profile;
- aggregate reservation/dispatch/fallback counters;
- daily/monthly utilization without report/company identity.

Forbidden:

- prompt/envelope/schema body;
- activity label;
- raw/model/rendered output;
- report/company identifiers and hashes;
- resolved model in logs;
- usage payload, headers, HMAC material or secrets.

Artifacts are private; Public H2 exposes only rendered text, statement/evidence IDs allowed by public DTO, renderer version and render digest.

## 17. Migration and rollback

`0017`:

- follows `0016_company_card_v2_foundation`;
- creates narrative/control/budget tables and constraints;
- expands H2 pin check to allow old `unresolved` shape or exact `resolved` noindex artifact/fallback shape;
- adds composite nullable FK from resolved pin binding kind/key to artifact;
- does not update snapshot JSON, hashes, H1 pins or unresolved H2 pins;
- inserts idempotent pending outbox rows for finalized eligible legacy
  v1/v2/v3 reports which have no resolved narrative binding; this is local
  migration metadata, not provider refresh;
- new report writer inserts outbox atomically with final report state;
- aborts atomically on corrupt existing rows;
- supports clean `0016→0017→0016→0017`;
- refuses downgrade when 0017 narrative data/resolved pins exist.

Runtime rollback:

1. set kill switch true/feature false;
2. stop narrative worker;
3. release only proven pre-dispatch reservations;
4. retain consumed reservations, jobs, artifacts, pins and snapshots;
5. reads continue only with valid saved pinned text/fallback; unbound reports
   remain `report_not_eligible`;
6. H1 remains production/default rollback path.

## 18. Acceptance criteria

Iteration is ready only when:

- old v1/v2/v3 fixtures and hashes remain exact;
- new V2 sub-schema is explicit and new-writer-only;
- exactly one admitted primary activity can appear;
- Gateway input passes privacy scan;
- model emits only a recursively strict render plan;
- runtime comments are zero;
- double-render and immutable identities pass;
- reservation/concurrency races produce one credit and one dispatch maximum;
- crash after report/outbox commit and before initialization is recovered by
  reconciler without losing or duplicating generation;
- two pre-dispatch releases/reschedules then success consume exactly one
  dispatch, including Moscow day/month rebucketing;
- ambiguous states never retry;
- public GET/HEAD/SSR adapter/crawler perform zero writes, enqueue, reservation,
  Gateway and provider calls;
- resolved pins are exact and assignment remains untouched;
- V1 identity/fallback goldens remain byte-exact; V2 connector/input/model
  identity tests pass;
- Claims v3 handoff accepts V1/V2 discriminated snapshots without exposing
  narrative evidence or changing old Claims output;
- migration/corruption/downgrade matrices pass;
- Product unit, disposable PostgreSQL, Gateway, web regression commands and `git diff --check` pass;
- independent review has no blocker.

## 19. Risks and open questions

Risks are closed by contract:

- report-to-narrative crash gap — atomic durable outbox plus reconciler;
- double spend — locked windows, unique reservation and committed dispatch;
- cross-window accounting — explicit release and re-reserve rebucketing;
- privacy/prose drift — minimal envelope, exact catalogs and closed schema;
- old-record drift — frozen parsers, identity V2 and no snapshot rewrite;
- read-side side effects — saved-result-only resolver and contract guards.

Open questions: `none`. Positive production limits, resolved model selection,
provider fields, H2 assignment and production activation are intentionally not
decisions of iteration 21.
