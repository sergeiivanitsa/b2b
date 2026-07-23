# Итерация 10 — Company Reports API: implementation plan

## 1. Scope summary

Реализовать в существующем Product API:

```http
POST /company-reports
GET  /company-reports/{inn}
GET  /company-reports/{inn}/status
```

Execution:

```text
HTTP enqueue
→ PostgreSQL durable job
→ separate worker
→ existing DataNewton/orchestrator
→ persistence finalization
→ ephemeral signals/scoring
```

AI остаётся explicit GET-only и ephemeral. Claims, UI, public API, Gateway и
scoring persistence не изменяются.

## 2. Exact change manifest

Documentation/state:

- `docs/development/iterations/iteration-10-company-reports-api.md`;
- `docs/development/plans/iteration-10-company-reports-api.md`;
- `docs/development/DEVFLOW_STATE.yaml`;
- `README.md` — worker/start/API notes.

Migration/persistence:

- new `services/product_api/alembic/versions/0013_company_report_jobs.py`;
- `company_reports/persistence/models.py` — `CompanyReportJob` и constants;
- `company_reports/persistence/errors.py` — typed job errors;
- new `company_reports/persistence/jobs.py` — enqueue, claim, heartbeat,
  terminal transitions, reconciliation, finalized-record query;
- `company_reports/persistence/repository.py` — shared concurrency-safe subject
  handling и backward-compatible safe failure code;
- `company_reports/persistence/__init__.py` — explicit exports.

Application/API:

- new `company_reports/schemas.py` — strict request/response/public projection;
- new `company_reports/service.py` — typed use cases;
- new `company_reports/worker.py` — CLI/loop/pipeline/shutdown;
- `company_reports/__init__.py` — intentional exports if needed;
- new `routers/company_reports.py` — routes/rate-limit/error mapping;
- `main.py` — include router only.

Configuration/deployment:

- `settings.py` — worker settings/validators;
- `services/product_api/.env.example` — worker defaults;
- `docker-compose.yml` — local worker process using same Product image;
- `docker-compose.product.yml` — production API и worker из одного exact image;
- `.github/workflows/deploy_prod.yml` — migration-before-worker rollout,
  recreate/inspect API и worker.

No nginx change is expected: existing `/api/` rewrite covers endpoints.
Dockerfile remains unchanged because Compose overrides `command`.

Tests:

- new unit:
  - `test_company_report_job_models.py`;
  - `test_company_report_jobs.py`;
  - `test_company_report_service.py`;
  - `test_company_report_api_schemas.py`;
  - `test_company_report_worker.py`;
  - `test_company_report_worker_settings.py`;
  - `test_company_reports_api.py`;
- update `test_company_report_migration.py`,
  `persistence_test_helpers.py`, unit `conftest.py` as needed;
- new PostgreSQL integration:
  - `tests/test_company_report_jobs.py`;
  - `tests/test_company_reports_api.py`;
  - `tests/test_company_report_jobs_migration.py`;
- update integration `conftest.py` cleanup and `tests/utils.py` only if needed.

## 3. Stage 1 — Migration и ORM

Create `0013_company_report_jobs.py` with:

- `down_revision = "0012_company_report_persistence"`;
- FKs `report_id → company_reports.id`, `subject_id →
  company_report_subjects.id`, both `ON DELETE CASCADE`;
- unique report constraint;
- state/attempt/state-shape checks;
- active-subject, queued-claim и running-lease partial indexes.

Downgrade drops only new indexes/table. Do not edit `0012`.

Add ORM constants:

```python
JOB_QUEUED_STATE = "queued"
JOB_RUNNING_STATE = "running"
JOB_SUCCEEDED_STATE = "succeeded"
JOB_FAILED_STATE = "failed"
```

`CompanyReportJob.__repr__` omits identifier, worker token and failure detail.

Tests verify metadata, constraints/indexes/FKs, privacy, migration chain and
absence of scoring/AI/provider payload columns.

## 4. Stage 2 — Transactional job repository

Create `persistence/jobs.py`.

Immutable service records:

- `EnqueuedReportJob`;
- `ClaimedReportJob`;
- `LatestFinalizedReportRecord`.

Typed errors:

- `CompanyReportJobStateConflictError`;
- `CompanyReportJobFencingError`;
- `CompanyReportJobNotFoundError`.

Messages are static and do not embed nested DB/provider exceptions.

### 4.1. Atomic create-or-reuse

Repository does not commit internally:

1. Normalize INN before transaction.
2. Concurrency-safe subject insert/reselect.
3. `SELECT subject FOR UPDATE`.
4. Select subject pending report.
5. Existing pending accepts only matching queued/running job and returns reused.
6. No pending creates report UUID, pending record and queued job, then flush.
7. Caller commits.

Use PostgreSQL conflict-safe insertion/savepoint; never continue an aborted
transaction after plain `IntegrityError`.

### 4.2. Claim/heartbeat/transitions

`claim_next_job()`:

- deterministic order;
- `FOR UPDATE SKIP LOCKED`;
- validate report/subject;
- precondition failure atomically fails queued job/pending report;
- otherwise assigns UUID token, timestamps, lease, attempt 1;
- commit before provider call.

`heartbeat_job()` conditionally updates by job/state/token and extends lease
using database time only while the prior lease is still live; zero rows means
fencing error. Expired lease cannot be extended.

Terminal success owns one transaction:

1. lock job/report;
2. obtain fresh PostgreSQL wall clock after lock;
3. assert running/token/live lease;
4. call `finalize_report`;
5. `evaluate_signals`;
6. `score_signals`;
7. set succeeded/finished;
8. commit.

Signals/scoring are returned only for tests/diagnostics and not persisted.

Failure functions cover queued precondition, owned running failure and expired
running reconciliation. All update job and pending report in one transaction,
store only allowlisted code and never raw exception.

All claim/heartbeat/terminal/reconciliation lease decisions use only
PostgreSQL current wall clock evaluated after the relevant row lock. A shared
helper uses `clock_timestamp()`, not Python time, `now()` or
`CURRENT_TIMESTAMP`. Claim derives all claim timestamps from one DB timestamp.
Heartbeat uses a conditional update requiring `running`, matching token and
`lease_expires_at > db_clock`, and derives the new lease from the same
timestamp. Terminal success and owned failure recheck a live lease after lock;
stale owners mutate nothing. Fixed lock order is job then report.

Add latest finalized query including `complete`, `partial`, `failed`, ordered
by `created_at DESC, id DESC`. Existing query contracts remain unchanged.

Tests cover repeat enqueue, new enqueue after final/failed, invalid invariants,
transition matrix, stale token, expired lease, reconciliation idempotency,
immutable finalization and old safe-error JSON.

## 5. Stage 3 — Public schemas и projection

Create strict models:

- `CompanyReportCreateRequest`;
- `CompanyReportAcceptedResponse`;
- `CompanyReportStatusResponse`;
- `CompanyReportSafeFailureResponse`;
- `CompanyReportPublicSnapshot`;
- `CompanyReportResponse`;
- safe dataset/warning/source-time projections.

All use `extra="forbid"`.

Identifier helper uses existing normalization/type detection and permits only
10/12-digit INN. No checksum rules are invented.

Projection begins only from deserialized immutable `CompanyReport` and
allowlists normalized facts/status/timing. It must not unrestricted-recursively
dump persistence JSON. Forbidden tests cover case-insensitively:

```text
raw_payload
headers
authorization
api_key
apikey
provider_limit_metadata
request_id
endpoint
response_hash
worker_token
lease_expires_at
safe_error_type
```

Missing stays null and Decimal serialization remains exact.

## 6. Stage 4 — Application service

Create typed safe errors for invalid identifier, not found, pending, state
conflict, persistence unavailable and internal evaluation/snapshot failure.

`create_or_reuse_company_report()`:

- validates INN;
- delegates atomic repository transaction;
- returns report ID/status/reused;
- never creates provider or evaluates domain/AI.

`get_company_report_status()`:

- validates INN;
- reads latest persistence lifecycle;
- maps none to not found;
- does not import/call provider, scoring or explanation.

`get_latest_company_report()`:

1. validate INN;
2. load latest finalized record;
3. if none, return 409 for existing pending, otherwise 404;
4. valid snapshot: deserialize, preserve pre-call representation/hash,
   evaluate signals, score signals, optionally explicit AI, build projection
   and assert no mutation;
5. infrastructure-failed without snapshot: null domain outputs and safe failure;
6. corrupt snapshot/evaluation maps to safe 500.

Pending plus older finalized returns that finalized result. AI failure remains
HTTP 200 response data.

Tests cover complete/partial/two failed forms, pending semantics, deterministic
ephemeral evaluation, old snapshots, immutability, AI default off/explicit on
and absence of provider calls.

## 7. Stage 5 — Durable worker

Create testable functions:

- `run_worker(settings, shutdown_event, ...)`;
- `run_one_claimed_job(...)`;
- heartbeat supervisor;
- signal registration wrapper;
- `main()`.

Factories are injectable in tests.

Loop:

1. reconcile expired running jobs;
2. claim at most one queued job;
3. interruptibly wait poll interval if none;
4. execute claimed job;
5. stop claiming after shutdown.

Pipeline constructs/closes DataNewton client, calls `build_company_report` once
with pending ID and deterministic request ID, heartbeats concurrently, and
finishes through success/failure repository transaction. No AI import/call and
no worker replay.

SIGTERM/SIGINT handling must be cross-platform safe. Queued jobs remain queued.
Graceful cancellation safely fails a live owned job when possible; hard kill is
handled later by reconciliation without replay.

Tests cover call order, exactly three dataset calls, provider-owned transport
retry ceiling, no worker retry, partial/all-dataset domain failure, unexpected
exception, heartbeat/fencing/reconciliation, shutdown, no AI and no network.

## 8. Stage 6 — Router и HTTP wiring

Create `routers/company_reports.py`, include it in `main.py`.

All routes depend on:

```python
require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_MEMBER)
```

Tests cover 401, 403, member and superadmin.

Create report-specific limiter instances from existing limiter/config/settings.
POST and AI-enabled GET use expensive buckets; ordinary GET/status use read
buckets. Do not share state with chat/Claims limiters.

A single mapping converts typed service errors to exact
400/404/409/500/503 bodies. Unexpected errors log no identifier/provider/raw
message and return safe 500.

- POST: `202`;
- status: `200`;
- GET: `200`, explicit bool query;
- strict model/query failures: `422`;
- no `BackgroundTasks`;
- routes do not import provider/orchestrator directly.

## 9. Stage 7 — Configuration, local deployment и docs

Add settings/defaults/cross-field validators:

- poll/lease/heartbeat positive;
- heartbeat strictly less than lease;
- shutdown grace nonnegative.

Add `.env.example` values.

Add `company_report_worker` to Compose:

```yaml
command:
  - python
  - -m
  - product_api.company_reports.worker
restart: unless-stopped
```

Use same Product build/image/settings, depend on healthy PostgreSQL, expose no
port, never commit DataNewton secret.

README documents migration, API+worker start, worker command, no automatic
replay, status polling and explicit AI opt-in.

## 10. Stage 8 — Production compose и deploy workflow

Update `docker-compose.product.yml` so both services reuse one exact image:

```yaml
services:
  product_api:
    image: b2b-product-api:${PRODUCT_IMAGE_TAG:-local}
    build:
      context: .
      dockerfile: services/product_api/Dockerfile
    env_file:
      - .env.product

  company_report_worker:
    image: b2b-product-api:${PRODUCT_IMAGE_TAG:-local}
    env_file:
      - .env.product
    restart: unless-stopped
    stop_grace_period: 40s
    command:
      - python
      - -m
      - product_api.company_reports.worker
```

Worker has no build section and no port. Product API image is built once from
the deployed checkout; API, Alembic migration container and worker use this
same image/tag.

Update `.github/workflows/deploy_prod.yml`:

1. Resolve deployed commit and export it as `PRODUCT_IMAGE_TAG`.
2. Gracefully stop old worker if present.
3. Build Product image once.
4. Run `alembic upgrade head` from that exact image.
5. Only after successful migration recreate/start API and worker.
6. Verify API health.
7. Verify worker exists, is running and not restarting.
8. Verify API/worker image IDs are identical and correspond to deployed tag.

Migration failure must prevent recreation/start of the new worker. Worker is
never built separately.

## 11. Stage 9 — Disposable PostgreSQL migration verification

Create `services/product_api/tests/test_company_report_jobs_migration.py`.
Using a dedicated test PostgreSQL admin URL, the test:

1. Creates a uniquely named disposable database.
2. Refuses production-like, unknown or not-test-created targets.
3. Runs Alembic upgrade through `0013_company_report_jobs`.
4. Inspects exact columns/nullability, FKs, unique/check constraints, partial
   indexes and ORM metadata.
5. Runs downgrade to `0012_company_report_persistence`.
6. Verifies only the new table/indexes were removed, the four existing
   CompanyReport tables remain and Alembic version is `0012`.
7. Force-closes connections and drops only its generated database in `finally`.

The integration cleanup fixture includes, in FK-safe order:

```text
company_report_jobs
company_report_provider_requests
company_report_datasets
company_reports
company_report_subjects
```

## 12. Test matrix

Real PostgreSQL integration:

- concurrent enqueue for same INN → one subject/pending/job and same report ID;
- concurrent claims → one claim per job;
- active-job uniqueness;
- fencing/reconciliation;
- late heartbeat cannot revive an expired lease;
- heartbeat/reconciliation race has exactly one winner;
- stale worker cannot finalize or fail after reconciliation;
- stale finalizer cannot replace failed report;
- new POST after failed creates new report/job.

API:

- auth and new/reused POST;
- 400 invalid/OGRN;
- 422 malformed/extra/query;
- 404/409/429/safe 500/503;
- status invokes no domain/provider/AI;
- GET invokes no provider and does not mutate;
- complete/partial/failed and safe completeness/freshness/warnings;
- AI default off, explicit on and non-fatal failure;
- forbidden fields absent.

Regression/privacy:

- persistence serialization/hash;
- signals/scoring/explanation;
- Claims endpoints;
- mocks only, no DataNewton/OpenAI.

## 13. Verification commands

Targeted:

```text
python -m pytest services/product_api/tests_unit/test_company_report_job_models.py services/product_api/tests_unit/test_company_report_jobs.py services/product_api/tests_unit/test_company_report_service.py services/product_api/tests_unit/test_company_report_api_schemas.py services/product_api/tests_unit/test_company_report_worker.py services/product_api/tests_unit/test_company_report_worker_settings.py services/product_api/tests_unit/test_company_reports_api.py services/product_api/tests_unit/test_company_report_migration.py -q
```

CompanyReport regression:

```text
python -m pytest services/product_api/tests_unit/test_company_report_repository_pending.py services/product_api/tests_unit/test_company_report_repository_finalize.py services/product_api/tests_unit/test_company_report_repository_queries.py services/product_api/tests_unit/test_company_report_persistence_serialization.py services/product_api/tests_unit/test_company_report_privacy.py services/product_api/tests_unit/test_company_report_signal_evaluation.py services/product_api/tests_unit/test_company_report_scoring_evaluation.py services/product_api/tests_unit/test_company_report_explanation_service.py -q
```

Full unit:

```text
python -m pytest services/product_api/tests_unit -q
```

Targeted PostgreSQL integration:

```text
python -m pytest services/product_api/tests/test_company_report_jobs.py services/product_api/tests/test_company_reports_api.py -q
```

Required disposable PostgreSQL Alembic execution:

```text
python -m pytest services/product_api/tests/test_company_report_jobs_migration.py -q
```

Full PostgreSQL integration when available/migrated:

```text
python -m pytest services/product_api/tests -q
```

Migration head from `services/product_api`:

```text
alembic -c alembic.ini heads
```

Compile/diff:

```text
python -m compileall -q services/product_api/src/product_api services/product_api/alembic/versions
git diff --check
```

Gateway/UI checks are not applicable because those surfaces are unchanged.
Python lint/type-check commands are not configured.

`alembic -c alembic.ini heads` may be used as supplementary inspection, but it
does not replace the disposable upgrade/inspect/downgrade test.

## 14. Definition of done

- Approved durable migration/worker contract implemented.
- No in-process background execution or competing pending/active job.
- No automatic replay of running jobs.
- Late heartbeat cannot revive expired work and stale ownership cannot mutate
  report/job.
- Provider-call ceiling tested.
- Status is persistence-only.
- GET recomputes immutable ephemeral signals/scoring.
- AI explicit-only, ephemeral and non-fatal.
- No secrets/raw provider/internal errors leave persistence/API.
- Claims/Gateway/UI/nginx behavior unchanged.
- API and worker deploy from one exact commit-tagged image after successful
  migration; workflow inspects worker running and image equality.
- Disposable PostgreSQL Alembic upgrade/inspect/downgrade passes.
- Targeted, full unit, applicable integration, compileall and diff checks pass.
- Independent code review has no unresolved blocking/substantial finding.
- State becomes `ready_for_merge` only after checks.
