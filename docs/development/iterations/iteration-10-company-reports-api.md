# Итерация 10 — Интеграция CompanyReport с Product API

## 1. Статус и назначение

ID: `10`
Slug: `company-reports-api`
Ветка: `feat/iteration-10-company-reports-api`

Итерация подключает существующие DataNewton provider, normalizers,
CompanyReport orchestrator, persistence, signals, scoring и AI explanation к
существующему Product API.

Используется существующая схема доступа:

```text
browser/client
→ nginx /api/*
→ strip /api
→ Product API
```

Добавляются только внутренние endpoints:

```http
POST /company-reports
GET  /company-reports/{inn}
GET  /company-reports/{inn}/status
```

Асинхронное выполнение реализуется как durable PostgreSQL queue с отдельным
управляемым worker process из того же Product API image/codebase. Celery,
Redis, RabbitMQ и другой внешний broker не используются.

## 2. Утверждённая архитектура

```text
POST /company-reports
→ atomic transaction: pending report + queued job
→ 202 Accepted

separate CompanyReport worker
→ claim queued job
→ DataNewton provider
→ existing concurrent normalizers/orchestrator
→ persistence finalization
→ ephemeral signals
→ ephemeral scoring
→ job succeeded

GET /company-reports/{inn}/status
→ persistence lifecycle only

GET /company-reports/{inn}
→ latest finalized immutable snapshot
→ ephemeral signals
→ ephemeral scoring
→ optional explicit AI explanation
```

API-процесс не создаёт `BackgroundTasks`, `asyncio.create_task()` или другой
in-process fire-and-forget flow. Provider не вызывается из HTTP request
lifecycle.

Система гарантирует:

- атомарное создание pending report и queued job;
- не более одного pending report на subject;
- ровно один job на report;
- не более одного active job (`queued` или `running`) на subject;
- fenced claim worker-а;
- отсутствие автоматического replay прерванного `running` job;
- отсутствие скрытых provider-вызовов из POST, GET, status и reconciliation;
- immutable finalized snapshots;
- отсутствие persistence для signals, scoring и AI explanation.

Система не заявляет distributed/external exactly-once для DataNewton. Если
worker потерян после начала внешнего запроса, результат внешней операции
считается неизвестным. Истёкший `running` job переводится в `failed` без
provider replay. Новый запуск возможен только новым явным POST после failed
lifecycle.

## 3. Persistence contract

### 3.1. Таблица `company_report_jobs`

Добавляется append-only migration:

```text
revision: 0013_company_report_jobs
down_revision: 0012_company_report_persistence
```

| Column | Type | Contract |
|---|---|---|
| `id` | UUID PK | внутренний job id |
| `report_id` | UUID FK, unique, not null | один job на report |
| `subject_id` | UUID FK, not null | subject для active-job uniqueness |
| `state` | varchar(16), not null | `queued`, `running`, `succeeded`, `failed` |
| `worker_token` | UUID nullable | fencing token, обязателен для running |
| `attempt_count` | integer not null default 0 | только `0` или `1` |
| `claimed_at` | timestamptz nullable | момент claim |
| `heartbeat_at` | timestamptz nullable | последний heartbeat |
| `lease_expires_at` | timestamptz nullable | срок running lease |
| `finished_at` | timestamptz nullable | terminal transition |
| `safe_failure_code` | varchar(64) nullable | безопасный статический code |
| `created_at` | timestamptz not null | server default |
| `updated_at` | timestamptz not null | server default/application update |

Обязательные constraints и indexes:

- unique constraint на `report_id`;
- check `state IN ('queued','running','succeeded','failed')`;
- check `attempt_count IN (0,1)`;
- state-shape check:
  - `queued`: attempt 0, claim/lease/worker/failure/finished fields null;
  - `running`: attempt 1, worker/claim/heartbeat/lease present,
    failure/finished null;
  - `succeeded`: attempt 1, retained claim fields и `finished_at` present,
    failure null;
  - `failed`: `finished_at` и `safe_failure_code` present; разрешены failed до
    claim и failed после running;
- unique partial index на `subject_id WHERE state IN ('queued','running')`;
- claim index `(state, created_at, id)` для `state='queued'`;
- reconciliation index `(state, lease_expires_at)` для `state='running'`.

Job не содержит provider payload, headers, API keys, auth metadata, AI data,
scoring или arbitrary exception text.

### 3.2. Job lifecycle

Разрешены только переходы:

```text
queued → running → succeeded
queued → failed
running → failed
```

Запрещены `running → queued`, любые переходы из terminal state, повторный claim
и автоматический retry/replay.

`job.state=succeeded` означает, что application pipeline завершён. Финальный
`CompanyReport.lifecycle_status` при этом может быть `complete`, `partial` или
`failed`: orchestrator-level failed snapshot является корректным результатом
выполненного flow.

`job.state=failed` означает infrastructure/lifecycle/worker failure без
пригодного finalized snapshot.

### 3.3. Report lifecycle и atomic enqueue

Сохраняется существующий lifecycle:

```text
pending → complete
pending → partial
pending → failed
```

Finalized snapshot не заменяется и не мутируется. При worker/reconciliation
failure используется существующий `safe_error_snapshot`, расширенный
обратно совместимым безопасным `code`. API не возвращает сохранённые
`error_type`, raw message, request ID или exception context.

POST выполняет одну транзакцию:

1. Нормализует и валидирует ИНН.
2. Concurrency-safe создаёт или получает subject.
3. Блокирует subject row `FOR UPDATE`.
4. Ищет pending report.
5. Если pending существует, проверяет matching job в `queued` или `running` и
   возвращает существующий report с `reused=true`.
6. Если pending отсутствует, создаёт pending report и queued job, flush/commit
   обеих записей атомарно и возвращает `reused=false`.

Subject creation корректно обрабатывает concurrent insert через PostgreSQL
`ON CONFLICT DO NOTHING` или эквивалентный savepoint/reselect. Нельзя
продолжать transaction-aborted session после plain `IntegrityError`.

Pending без active job, active job без matching pending report или
несовпадающие subject/report дают typed state conflict, а не новый job.

## 4. Worker contract

### 4.1. Entry point и settings

Worker запускается отдельным процессом:

```text
python -m product_api.company_reports.worker
```

Он использует existing `Settings`, `AsyncSessionMaker`, `DataNewtonClient` и
CompanyReport domain modules. FastAPI app и AI explanation не запускаются.

Настройки:

```text
COMPANY_REPORT_WORKER_POLL_INTERVAL_SECONDS=1
COMPANY_REPORT_WORKER_LEASE_SECONDS=60
COMPANY_REPORT_WORKER_HEARTBEAT_INTERVAL_SECONDS=10
COMPANY_REPORT_WORKER_SHUTDOWN_GRACE_SECONDS=30
```

Poll, lease и heartbeat строго положительны, heartbeat меньше lease, shutdown
grace неотрицателен. Настройки не влияют на pure-domain logic.

### 4.2. Claim

Каждый claim выполняется короткой транзакцией:

1. Reconcile expired running jobs.
2. Выбрать первый queued job по `(created_at, id)` через
   `SELECT ... FOR UPDATE SKIP LOCKED`.
3. Проверить matching pending report и subject.
4. При нарушении precondition выполнить `queued → failed` без provider.
5. Иначе создать `worker_token`, установить `running`, `attempt_count=1`,
   claim/heartbeat/lease timestamps и commit до provider call.

Heartbeat и terminal mutations требуют совпадающий `worker_token`, ожидаемый
state и ещё живой lease.

### 4.3. Execution pipeline и provider-call ceiling

Для claimed job worker:

1. Загружает normalized subject identifier.
2. Создаёт и гарантированно закрывает `DataNewtonClient(settings)`.
3. Вызывает `build_company_report()` ровно один раз.
4. Передаёт pending UUID через `report_id_factory`.
5. Использует deterministic base request ID `company-report:{report_id}`.
6. В terminal transaction блокирует job/report, проверяет state/token/lease,
   вызывает `finalize_report`, `evaluate_signals`, `score_signals`, не
   сохраняет signals/scoring, переводит job в `succeeded` и commit.

Worker никогда не вызывает AI.

Для одного нового job:

- orchestrator вызывает каждый из трёх dataset methods ровно один раз;
- transport attempts ограничены existing контрактом
  `1 + DATANEWTON_RETRY_COUNT` только для разрешённых retry-классов;
- worker retry отсутствует;
- interrupted running job не replay;
- repeated POST, GET, status и reconciliation provider не вызывают.

Application/persistence/scoring exception, не преобразованный orchestrator,
переводит pending report и owned job в `failed` с allowlisted safe code. Raw
exception не сохраняется.

### 4.4. Database wall clock, heartbeat и fencing

Все lease-решения — claim, heartbeat, terminal success, owned failure и
reconciliation — используют только актуальный PostgreSQL wall clock после
получения необходимой row lock. Python clock, `now()` и
`CURRENT_TIMESTAMP`, фиксированные началом транзакции, для fencing запрещены.
Используется `clock_timestamp()` либо эквивалентный current wall-clock
expression.

Claim после lock получает один DB timestamp и использует его для
`claimed_at`, `heartbeat_at` и `lease_expires_at`.

Heartbeat выполняет atomic conditional update с единым DB-time basis:

```text
job id matches
state = running
worker_token matches
lease_expires_at > current DB wall clock
```

Новые heartbeat и lease строятся от того же timestamp. Zero updated rows
означает fencing loss. Истёкший lease никогда не продлевается и не
«воскрешается».

Terminal success и owned failure:

1. Блокируют job.
2. После lock получают новый `clock_timestamp()`.
3. Проверяют `running`, matching token и
   `lease_expires_at > db_time`.
4. Только затем блокируют/мутируют report и job.

Stale/expired owner не может финализировать report, пометить его failed или
изменить job. Terminal timestamps передаются в persistence явно из DB clock.

### 4.5. Reconciliation

Reconciliation выбирает running candidates через
`FOR UPDATE SKIP LOCKED`. После получения lock DB wall clock читается заново и
expiry повторно проверяется:

```text
state = running
lease_expires_at <= current DB wall clock
```

В одной транзакции job и связанный pending report переводятся в `failed` с
code `report_execution_interrupted`. Provider не вызывается, replay/requeue
нет, finalized report не изменяется.

Heartbeat и reconciliation — взаимоисключающие fenced mutations: в гонке
ровно одна сторона выигрывает. Inconsistent queued job может перейти в failed
с code `report_job_precondition_failed` без provider.

### 4.6. Graceful shutdown

На SIGTERM/SIGINT worker:

- перестаёт claim новые jobs;
- оставляет queued jobs queued;
- продолжает heartbeat текущего job;
- ждёт current job не более shutdown grace;
- при управляемой отмене пытается завершить current job как failed;
- после hard kill expired running job завершает reconciliation без replay.

## 5. HTTP access и rate limiting

Endpoints требуют существующую cookie session и:

```python
require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_MEMBER)
```

Active company members и superadmin разрешены. Anonymous/inactive получают
existing `401`, authenticated user без роли — `403`. CompanyReport subjects
не связываются с tenant `companies` и Claims.

Используются existing `RateLimiter`, `RateLimitConfig` и значения
`RATE_LIMIT_COMPANY_RPM`, `RATE_LIMIT_USER_RPM`, `RATE_LIMIT_IP_RPM`.
Report buckets отделены от chat buckets. POST и AI-enabled GET считаются
expensive; обычный GET и status — read. 429 сохраняет existing safe body:

```json
{"detail":{"code":"rate_limited","message":"rate limit"}}
```

## 6. HTTP contracts

Все новые request/response models используют `extra="forbid"`.

### 6.1. `POST /company-reports`

Request:

```json
{"inn":"7700000000"}
```

Разрешены только 10-digit legal-entity INN и 12-digit entrepreneur INN.
ОГРН/ОГРНИП запрещены. Checksum не добавляется, поскольку current provider
contract её не определяет.

Успех: `202 Accepted`.

```json
{
  "report_id":"00000000-0000-0000-0000-000000000000",
  "status":"pending",
  "reused":false
}
```

Повторный POST при queued/running возвращает тот же `report_id`,
`status="pending"`, `reused=true`. После finalized report новый явный POST
создаёт новый report/job. POST не вызывает provider, normalizers,
orchestrator, signals, scoring или AI и не возвращает job/worker/provider
details.

### 6.2. `GET /company-reports/{inn}/status`

Успех: `200 OK`.

```json
{
  "report_id":"00000000-0000-0000-0000-000000000000",
  "status":"pending",
  "started_at":"2026-07-23T00:00:00Z",
  "generated_at":null,
  "finished_at":null,
  "fresh_until":null
}
```

Endpoint возвращает latest run по `(created_at, id)` со status `pending`,
`complete`, `partial` или `failed`. Он читает только persistence lifecycle и
не вызывает provider, normalizers, signals, scoring или AI; job state, lease и
internal failure не возвращаются.

### 6.3. `GET /company-reports/{inn}`

Query:

```text
include_ai_explanation=false
```

Endpoint выбирает latest finalized record (`complete`, `partial`, `failed`) по
`(created_at, id)`. Pending не заменяет более старый finalized report. Если
finalized report отсутствует, но pending существует, возвращается
`409 report_pending`.

Response содержит:

- report/lifecycle timestamps;
- safe public CompanyReport projection;
- ephemeral signals и scoring;
- optional ephemeral AI explanation;
- safe failure либо `null`.

Projection включает normalized facts, dataset status/timing/safe warnings,
completeness, freshness, report warnings и usability flags. Она исключает
`raw_payload`, headers, provider limit metadata, keys/auth, provider request
IDs, endpoints, response hashes, raw/internal errors и job/worker fields.
`Decimal` сохраняет точность, missing остаётся `null`.

Snapshot-based failed CompanyReport вычисляет signals/scoring и получает
безопасный `insufficient_data`. Infrastructure-failed record без snapshot
возвращает `report`, `signals`, `scoring`, `ai_explanation` как `null`, а
`failure` содержит только allowlisted code/static message/retryable.

Stored snapshot, hash и ORM record не мутируются.

### 6.4. Explicit AI explanation

Только `GET /company-reports/{inn}?include_ai_explanation=true` может вызвать
existing `explain_scoring_result()`.

- default `false`;
- POST/status/worker AI не вызывают;
- вызов возможен только при snapshot/signals/scoring;
- максимум primary + один допустимый retry по итерации 9;
- result ephemeral;
- AI failure не меняет HTTP 200, report, signals, score, level/confidence;
- disabled AI не вызывает Gateway;
- tests используют mocks.

## 7. Typed errors и HTTP mapping

| Condition | HTTP | Safe code |
|---|---:|---|
| invalid/non-INN identifier | 400 | `invalid_inn` |
| no report/run | 404 | `company_report_not_found` |
| only pending report for GET | 409 | `report_pending` |
| pending/job invariant conflict | 409 | `report_state_conflict` |
| invalid body/query/extra field | 422 | FastAPI validation contract |
| report rate limit | 429 | `rate_limited` |
| DB temporarily unavailable | 503 | `company_report_unavailable` |
| corrupt snapshot/evaluation/internal failure | 500 | `company_report_internal_error` |

Error body:

```json
{"detail":{"code":"company_report_not_found","message":"company report not found"}}
```

Provider errors не становятся synchronous HTTP errors. HTTP/logging не
включают raw exception/provider message, headers, API key или auth data.

## 8. Production deployment

`docker-compose.product.yml` определяет `product_api` и
`company_report_worker`, использующие один exact image:

```text
b2b-product-api:${PRODUCT_IMAGE_TAG}
```

Production workflow устанавливает `PRODUCT_IMAGE_TAG` равным deployed Git
commit SHA, собирает image один раз и использует его для migration container,
API и worker. Worker не имеет собственного build или port, использует тот же
`.env.product`, `restart: unless-stopped`, `stop_grace_period: 40s` и command:

```text
python -m product_api.company_reports.worker
```

RU deploy выполняет:

1. Определяет exact commit/image tag.
2. Gracefully останавливает старый worker, если он существует.
3. Собирает Product image один раз.
4. Выполняет Alembic upgrade из этого image.
5. Только после успешной migration recreates API и worker.
6. Проверяет API health, running/non-restarting worker и одинаковый image ID у
   API/worker.

При migration failure новый worker не запускается. Local `docker-compose.yml`
также использует один shared Product image для API и worker.

## 9. Migration execution verification

Отдельный PostgreSQL integration test создаёт только собственную disposable
test database, выполняет Alembic upgrade до `0013_company_report_jobs`,
проверяет columns, nullability, FKs, unique/check constraints и partial
indexes, затем downgrade до `0012_company_report_persistence`.

После downgrade новая таблица/indexes отсутствуют, четыре существующие
CompanyReport tables сохранены, Alembic version равна
`0012_company_report_persistence`. Test отказывается работать с production,
unknown или не им созданной database и удаляет только generated database в
`finally`.

Real PostgreSQL race tests обязаны доказать:

- late heartbeat не продлевает expired lease;
- heartbeat/reconciliation имеют ровно одного winner;
- stale worker после reconciliation не может finalize или fail report.

## 10. Совместимость, безопасность и out of scope

- Existing CompanyReport v1 snapshots/hashes неизменны.
- Existing persistence queries сохраняют поведение; API использует новые
  explicit finalized-record queries.
- Old failed records без safe `code` получают conservative static fallback.
- Нет backfill, scoring/AI persistence columns.
- Migration append-only; `0012` не меняется.
- Claims routers/services/tables не меняются.
- Existing nginx generic `/api/` уже покрывает endpoints.
- Worker logs содержат только report/job IDs, state и safe codes.
- Real DataNewton/OpenAI tests запрещены.

Out of scope: внешний/public API, новый Gateway, API keys,
`/api/public/company-reports`, frontend/company page, SEO, Claims handoff,
payment, Celery/Redis/RabbitMQ, worker replay, scoring/AI persistence, новые
provider datasets/fields.

## 11. Критерии приёмки

- POST атомарно создаёт pending report и queued job.
- Concurrent POST возвращают один report/job.
- Claim использует `FOR UPDATE SKIP LOCKED` и fencing.
- Expired running job не replay/requeue; reconciliation не вызывает provider.
- Late heartbeat не возрождает expired lease, а stale worker не мутирует
  report/job.
- Worker выполняет approved pipeline и никогда AI.
- Provider-call ceiling проверен tests.
- GET/status не создают provider calls.
- AI только explicit opt-in.
- Complete, partial, snapshot-failed и infrastructure-failed ответы безопасны.
- Missing/partial не превращаются в zero.
- Raw payload, headers, secrets и internal errors отсутствуют в API/job.
- Unit, PostgreSQL integration, migration checks, compileall и
  `git diff --check` проходят.
- Disposable PostgreSQL Alembic upgrade/inspect/downgrade test проходит.
- Production deploy запускает API и worker из одного exact commit-tagged image
  только после successful migration.
- Claims regression suite проходит.
