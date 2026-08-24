# Итерация 21 — Company Card v2 AI narrative: implementation plan

ID: `21`

Slug: `company-card-v2-ai-narrative`

Specification: `docs/development/iterations/iteration-21-company-card-v2-ai-narrative.md`

Status: `approved_for_implementation`

Author: `DevFlow planner`

Planning date: `2026-08-24`

Base commit: `f4fe88e51f89a85cbd3c8881affbb8b0b87fbe6c`

Branch: `feat/iteration-21-company-card-v2-ai-narrative`

Review status: `CHANGES_REQUIRED; single correction applied; root blocker audit PASSED; no second plan review`

## 1. Execution rules

- Implement test-first in the iteration-21 worktree.
- Preserve unrelated/user changes.
- No network/live/paid/provider/FNS/production DB/deploy/frontend work.
- Do not modify Roadmap.
- No new dependencies.
- Implementer does not commit/push; DevFlow root may do so only after checks and `VERDICT: READY`.
- Any need for positive production limits, a second AI call, H2 assignment or broader OKVED semantics is a blocker.

## 2. Exact changed-file manifest

### Docs/state/config

```text
README.md
docs/development/DEVFLOW_STATE.yaml
docs/development/iterations/iteration-21-company-card-v2-ai-narrative.md
docs/development/plans/iteration-21-company-card-v2-ai-narrative.md
docs/development/evidence/iteration-21-company-card-v2/okved-primary-activity-evidence-v1.md
docs/development/decisions/iteration-21-ai-narrative-budget-policy-v1.md
docker-compose.yml
docker-compose.product.yml
services/product_api/.env.example
services/gateway_api/.env.example
```

### Shared/Gateway

```text
shared/constants.py
shared/schemas.py
services/gateway_api/src/gateway_api/settings.py
services/gateway_api/src/gateway_api/main.py
services/gateway_api/src/gateway_api/openai_client.py
services/gateway_api/tests/test_contract.py
services/gateway_api/tests/test_structured_contract.py
services/gateway_api/tests/test_company_card_narrative_contract.py
```

### Product domain/transport

```text
services/product_api/src/product_api/settings.py
services/product_api/src/product_api/gateway_client.py
services/product_api/src/product_api/company_reports/worker.py
services/product_api/src/product_api/company_reports/company_card_v2/__init__.py
services/product_api/src/product_api/company_reports/company_card_v2/models.py
services/product_api/src/product_api/company_reports/company_card_v2/primary_activity.py
services/product_api/src/product_api/company_reports/company_card_v2/writer.py
services/product_api/src/product_api/company_reports/company_card_v2/public_h2_models.py
services/product_api/src/product_api/company_reports/company_card_v2/public_h2.py
services/product_api/src/product_api/company_reports/company_card_v2/service.py
services/product_api/src/product_api/company_reports/company_card_v2/narrative/__init__.py
services/product_api/src/product_api/company_reports/company_card_v2/narrative/models.py
services/product_api/src/product_api/company_reports/company_card_v2/narrative/identity.py
services/product_api/src/product_api/company_reports/company_card_v2/narrative/catalog.py
services/product_api/src/product_api/company_reports/company_card_v2/narrative/prompt.py
services/product_api/src/product_api/company_reports/company_card_v2/narrative/validation.py
services/product_api/src/product_api/company_reports/company_card_v2/narrative/renderer.py
services/product_api/src/product_api/company_reports/company_card_v2/narrative/service.py
services/product_api/src/product_api/company_reports/company_card_v2/narrative/worker.py
services/product_api/src/product_api/company_reports/company_card_v2/public_h2_ssr_adapter.py
services/product_api/src/product_api/claims/company_report_handoff.py
services/product_api/src/product_api/routers/company_reports_public.py
```

### Persistence/migration

```text
services/product_api/src/product_api/company_reports/persistence/models.py
services/product_api/src/product_api/company_reports/persistence/v3.py
services/product_api/src/product_api/company_reports/persistence/jobs.py
services/product_api/src/product_api/company_reports/persistence/presentations.py
services/product_api/src/product_api/company_reports/persistence/narratives.py
services/product_api/src/product_api/company_reports/persistence/narrative_outbox.py
services/product_api/src/product_api/company_reports/persistence/__init__.py
services/product_api/alembic/versions/0017_company_card_v2_ai_narrative.py
```

### Unit tests/fixtures

```text
services/product_api/tests_unit/test_company_card_v2_primary_activity.py
services/product_api/tests_unit/test_company_card_v2_writer.py
services/product_api/tests_unit/test_company_card_v2_narrative_models.py
services/product_api/tests_unit/test_company_card_v2_narrative_identity.py
services/product_api/tests_unit/test_company_card_v2_narrative_catalog.py
services/product_api/tests_unit/test_company_card_v2_narrative_prompt.py
services/product_api/tests_unit/test_company_card_v2_narrative_validation.py
services/product_api/tests_unit/test_company_card_v2_narrative_renderer.py
services/product_api/tests_unit/test_company_card_v2_narrative_service.py
services/product_api/tests_unit/test_company_card_v2_narrative_jobs.py
services/product_api/tests_unit/test_company_card_v2_narrative_worker.py
services/product_api/tests_unit/test_company_card_v2_public_h2.py
services/product_api/tests_unit/test_company_card_v2_public_h2_side_effects.py
services/product_api/tests_unit/test_company_card_v2_serialization.py
services/product_api/tests_unit/test_company_card_v2_presentations.py
services/product_api/tests_unit/test_company_card_v2_privacy.py
services/product_api/tests_unit/test_company_report_persistence_models.py
services/product_api/tests_unit/test_company_report_persistence_serialization.py
services/product_api/tests_unit/test_company_report_worker.py
services/product_api/tests_unit/test_company_report_worker_settings.py
services/product_api/tests_unit/test_gateway_client.py
services/product_api/tests_unit/test_claims_company_report_handoff.py
services/product_api/tests_unit/test_company_card_v2_narrative_outbox.py
services/product_api/tests_unit/test_company_card_v2_public_h2_ssr_adapter.py
services/product_api/tests_unit/fixtures/company_card_v2/snapshot_v3_narrative_v2.json
services/product_api/tests_unit/fixtures/company_card_v2/narrative_render_plan_valid.json
services/product_api/tests_unit/fixtures/company_card_v2/narrative_fallback_golden.json
```

Existing v1/v2/v3 snapshot and public-H2 goldens are read-only and must not be rewritten.

### PostgreSQL tests/runbook

```text
services/product_api/tests/conftest.py
services/product_api/tests/test_company_card_narrative_migration.py
services/product_api/tests/test_company_card_narrative_jobs.py
services/product_api/tests/test_company_card_narrative_budget.py
services/product_api/tests/test_company_card_narrative_artifacts.py
services/product_api/tests/test_company_card_narrative_outbox.py
services/product_api/tests/test_company_card_narrative_reconciler.py
services/product_api/tests/test_company_report_presentations.py
services/product_api/tests/test_company_report_public_h2_reads.py
services/product_api/tests/test_company_report_jobs.py
scripts/run-iteration21-postgres-tests.ps1
```

Any additional path requires plan-review scope approval.

## 3. Dependency choices

No package is added.

- Pydantic: existing strict/frozen models and JSON Schema.
- SQLAlchemy/PostgreSQL: transactions, row locks, constraints and concurrency.
- `zoneinfo`: Europe/Moscow windows.
- `hashlib`, `json`, `unicodedata`: identities and renderer verification.
- Existing `httpx`/HMAC Gateway client.
- Existing canonical H2 JSON implementation.

A scheduler, tokenizer, distributed-lock package, price library or second validation model is unnecessary.

## 4. Stage 0 — Baseline and immutable goldens

Before production changes:

1. Record branch/base/status.
2. Hash existing v1/v2/v3 snapshot and public-H2 fixtures.
3. Run current v3 serialization, H1, presentation, job and Gateway structured tests.
4. Add regression assertions that old v3 has no new discriminator/default field and retains exact hash.
5. Confirm Alembic head is `0016_company_card_v2_foundation`.

## 5. Stage 1 — RED compatibility and primary-activity tests

Add failing tests for:

- exact legacy v3 dispatch with discriminator absent;
- new v3 V2 discriminator;
- unknown/missing/coerced cross-shapes;
- new writer refusing V1 output;
- old snapshots receiving no refresh;
- exact `OKVED_BLOCK` request/success/target binding;
- one `main=true`, exact `"new"`, code/label bounds;
- zero/two primary rows, unknown mode, malformed/extra row keys;
- exact array bounds `0/1/45/100/101`;
- exact normalized row `2048/2049` and aggregate `65536/65537` UTF-8 bytes;
- code grammar and `1/128/129` label scalar boundaries;
- duplicate selected row identical case, selected code/label conflicts and
  allowed duplicates exclusively among additional rows;
- additional rows never stored/public;
- no effective date/percentage/revenue claim;
- public primary activity only from V2 admitted evidence.

Then implement `primary_activity.py`, frozen V1/V2 snapshot models and strict
parser dispatch in `persistence/v3.py`.

Implement the shipped, default-off `writer.py` only after RED tests prove:

- exact stored H2 writer/version/contract/generation tuple is mandatory;
- disabled writer performs zero provider calls;
- enabled write path calls counterparty exactly once with
  `filters=("OKVED_BLOCK",)` and records
  `company_card_v2_counterparty_okved_primary_v1`;
- finance may be requested through the existing approved parser, but
  arbitration and contact/manager/owner/workers profiles are never requested;
- exact target/result binding and per-dataset partial failure semantics;
- no public GET/HEAD/SSR/crawler path can import or invoke the writer;
- completion stores only V2, then report plus outbox commit atomically;
- injected fake provider/clock are used; network is forbidden.

Add Claims handoff RED tests before implementation:

- old v3 V1 handoff output remains byte-equivalent;
- new discriminated V2 handoff succeeds;
- malformed V1/V2 cross-shapes fail closed;
- `narrative_evidence`, activity label/code and narrative artifact never enter
  Claims payload, prompt, storage or logs;
- repeated handoff remains idempotent.

## 6. Stage 2 — Pure narrative contracts

Implement:

- byte-exact inherited `GenerationIdentityV1` and `ArtifactIdentityV1`;
- new `GenerationIdentityV2` with snapshot/evidence/insight/connector/input
  versions;
- CJSON hashing;
- minimal privacy-safe evidence envelope;
- versioned catalogs;
- strict recursive output schema;
- grounding validator;
- deterministic renderer;
- exact universal fallback.

RED tests cover:

- unknown/extra/duplicate/excess IDs;
- prose/numeric model fields;
- missing evidence;
- label bounds/NFC/surrogates;
- 399/400/700/701 description lengths;
- zero/one/two fixture comments;
- three/duplicate/hidden runtime chart comments;
- double-render byte mismatch;
- render/artifact/fallback hash mismatch;
- permutations and repeatability;
- privacy scanner over prompt and captured Gateway payload.
- exact normalization order NFC→CR/LF→trim→whitespace collapse→scalar count;
- C0/C1, surrogate, NUL and bidi rejection;
- full same-report/snapshot, provider, unit, privacy and unsupported-comparison
  matrix;
- every fixture comment maps to exactly one allowlisted statement;
- exact Russian catalog strings and fixed runtime plan;
- exact 691-scalar named fallback mapping, empty evidence/comments and phrase
  trace;
- connector/input/fallback catalog-only upgrade creates a new generation;
- resolved-model-only change keeps generation key but changes
  `ArtifactIdentityV1`.

Runtime catalog fixture must prove `comments == []`.

## 7. Stage 3 — Task-specific Gateway profile

Extend shared constants/schema and Gateway resolution.

Tests first:

- signed narrative profile accepted;
- exact schema name/profile/options forwarded;
- metadata/direct model/stream/hybrid rejected;
- wrong profile/schema rejected;
- timeout and output cap forwarded;
- exact `1/20/21` timeout, `1/600/601` token, `32768/32769` request-byte and
  `16384/16385` response-byte boundaries;
- profile disabled returns closed error before OpenAI client;
- enabled plus blank/missing narrative model fails settings validation;
- matching profile/nonempty resolved model returned;
- canonical dispatch UUID stored before call, present identically in
  `X-Gateway-Dispatch-ID` and body, covered by body hash/HMAC and echoed;
- missing/malformed/header-body/response dispatch mismatch is terminal without
  retry;
- ordinary request ID remains separately propagated;
- logs contain request ID/profile only;
- no prompt, schema body, activity label, output or metadata log;
- HMAC rejection identical to existing modes;
- legacy chat and iteration-9 profile unchanged.

All OpenAI calls are mocked.

## 8. Stage 4 — Migration and repositories

Create `0017` tables/checks/FKs/indexes.

Repository APIs:

```text
Pre-lease identity-guarded:
  insert_narrative_outbox(report_id,snapshot_hash)
  claim_narrative_outbox(outbox_id,expected_state)
  initialize_narrative_generation(full GenerationIdentityV2)
  reserve_or_rereserve_dispatch_credit(generation_key,clock)
  release_pre_dispatch_reservation(generation_key,failure_code,clock)
  claim_narrative_job(generation_key,clock)

Leased/fenced:
  heartbeat_narrative_job(job_id,generation_key,lease_token,fence)
  mark_dispatching(job_id,generation_key,lease_token,fence,dispatch_id)
  record_gateway_response(job_id,generation_key,lease_token,fence,...)
  finalize_narrative_artifact(job_id,generation_key,lease_token,fence,...)
  finalize_fallback_after_dispatch(job_id,generation_key,lease_token,fence,...)

System reconciler:
  reconcile_pending_outbox(...)
  reconcile_expired_narrative_jobs(...)

Read-only:
  resolve_exact_narrative_binding(...)
```

Pre-lease APIs never accept optional/fake leases. Worker mutations always
require all four ownership values. Clock is explicit through `NarrativeClock`;
production uses DB UTC and tests inject fixed UTC.

Migration tests first:

- clean 0016 upgrade;
- complete columns/checks/FKs/unique indexes;
- exact table contract from specification, including outbox state-shape checks;
- no old snapshot/pin mutation;
- old V1/V2/V3 hash equality;
- corrupt old H2 pin atomic abort;
- clean downgrade/re-upgrade;
- populated-0017 downgrade refusal;
- duplicate generation/binding/dispatch ID rejection;
- migration-created legacy outbox idempotency;
- final report plus outbox atomic commit;
- simulated process death immediately after commit, followed by reconciler
  creation of exactly one saved fallback/binding;
- no synthesized fallback while migration/reconciler backlog is unprocessed.

## 9. Stage 5 — Budget and one-dispatch concurrency

PostgreSQL tests first:

- N concurrent reservations for one generation → one job/reservation;
- different generations racing at daily last credit → one winner;
- daily pass/monthly exhaustion and inverse;
- exact Moscow day/month boundaries with injected clock;
- reserved release decrements both old-window counters;
- exact `released→reserved` increments only recomputed current windows;
- daily-only, monthly-only and simultaneous day/month crossing rebucket
  matrices;
- consumed credit never releases;
- usage/price/model response cannot alter counters;
- default-zero/kill-switch/concurrency fail closed;
- cross-process concurrency cap through locked control row;
- stale lease/fence cannot dispatch;
- two pre-dispatch local failures/reschedules then success still produce one
  reservation row, three epochs and exactly one paid dispatch;
- third pre-dispatch failure is terminal fallback;
- dispatching commit observed before mocked Gateway call;
- timeout/death/lost response gives no second call;
- `gateway_dispatch_id` unique;
- one generation crosses Gateway boundary at most once.

## 10. Stage 6 — Worker and finalization

Implement the separate command:

```text
python -m product_api.company_reports.company_card_v2.narrative.worker
```

Add default-off compose service.

The existing CompanyReport worker:

1. finalizes an eligible report and inserts unique narrative outbox in the
   same transaction;
2. commits both or neither;
3. performs no Gateway/provider call in that transaction.

Reconciler:

1. claims durable outbox with its own lease/fence;
2. validates exact frozen snapshot/hash without rewriting it;
3. materializes a saved fallback immediately for legacy/missing-activity/
   disabled/kill-switch/budget-exhausted cases;
4. otherwise creates exact V2 generation/job/reservation idempotently;
5. marks outbox processed only after durable artifact or job exists.

Narrative worker:

1. claims under durable concurrency control;
2. validates exact report/snapshot identity;
3. writes committed `dispatching` before call;
4. performs one Gateway call;
5. validates/renders twice;
6. stores AI artifact or fallback;
7. appends resolved noindex H2 pin/staged pointer atomically;
8. never creates assignment.

Tests cover report-commit crash gap, shutdown, lease expiry, stale response,
worker restart, corrupt snapshot, invalid response, dispatch-ID mismatch and
idempotent finalization. Before/after database assertions prove snapshot JSON
and hashes, signals rows and scoring rows are byte/value unchanged. Phrase
trace is verified against rendered scalar spans, statement IDs and evidence
IDs.

## 11. Stage 7 — Public resolver and pins

Modify H2 builder/resolver to accept an exact validated binding context.

Matrices:

- old v1/v2/frozen-v3 with valid saved fallback → exact fallback;
- v1/v2 fallback is an exact direct artifact join for noindex
  `latest_unpublished` preview and never creates an H2 pin;
- v3 artifact/fallback uses an exact resolved H2 pin and may stage that pin;
- finalized report with migration outbox/job pending but no saved binding →
  `409 report_not_eligible`;
- missing/unpinned/unresolved v3 binding → `409 report_not_eligible`;
- selected v1/v2 report without exact saved fallback → `409 report_not_eligible`;
- stale unavailable unbound candidate → `409 report_not_eligible`;
- resolved artifact pin → exact stored narrative;
- resolved fallback pin → exact fallback;
- unresolved active/staged pin → `report_not_eligible`;
- binding report/snapshot/chart/generation mismatch → terminal invalid;
- bound stale/invalid artifact, missing FK, corrupt render/projection hash →
  `500 public_projection_invalid`;
- newer unbound report never replaces exact head/pin;
- GET, HEAD, SSR adapter and crawler User-Agent use identical selection;
- HEAD has same status/headers and empty body;
- repeated GET/HEAD/SSR/crawler performs only SELECT;
- no reservation, job, worker, Gateway, provider, signals or scoring call;
- assignment table remains unchanged/empty for H2.

`assign_pin_cas` continues rejecting H2. Iteration 25 owns H2 assignment.

No public path calls fallback renderer. Fallback rendering and binding are
write-side operations only.

## 12. PostgreSQL runbook

`scripts/run-iteration21-postgres-tests.ps1` follows iteration-20 safeguards:

- already-local `postgres:16-alpine`;
- `--pull=never`;
- loopback dynamic port;
- tmpfs, no persistent volume;
- generated credentials;
- reject root/Product `.env`;
- clear `OPENAI_API_KEY`, DataNewton and all Company Card AI/H2 activation env;
- assert narrative gateway disabled, model unset, limits/concurrency zero and
  kill switch true inside the test process;
- verify imported `product_api` belongs to current worktree;
- exact container ID/labels before cleanup;
- JUnit requires tests > 0 and zero failure/error/skip.

Targeted mode includes migration, jobs, budget, artifacts, pins, public-H2 reads and affected CompanyReport jobs. Full mode runs all Product integration tests.

No live provider/Gateway/OpenAI request is permitted.

## 13. Required verification commands

Targeted pure/unit:

```powershell
python -m pytest services/product_api/tests_unit/test_company_card_v2_primary_activity.py services/product_api/tests_unit/test_company_card_v2_narrative_models.py services/product_api/tests_unit/test_company_card_v2_narrative_identity.py services/product_api/tests_unit/test_company_card_v2_narrative_catalog.py services/product_api/tests_unit/test_company_card_v2_narrative_prompt.py services/product_api/tests_unit/test_company_card_v2_narrative_validation.py services/product_api/tests_unit/test_company_card_v2_narrative_renderer.py services/product_api/tests_unit/test_company_card_v2_narrative_service.py services/product_api/tests_unit/test_company_card_v2_narrative_jobs.py services/product_api/tests_unit/test_company_card_v2_narrative_worker.py services/product_api/tests_unit/test_company_card_v2_public_h2.py services/product_api/tests_unit/test_company_card_v2_public_h2_side_effects.py -q
```

Targeted Gateway:

```powershell
python -m pytest services/gateway_api/tests/test_contract.py services/gateway_api/tests/test_structured_contract.py services/gateway_api/tests/test_company_card_narrative_contract.py -q
```

Disposable PostgreSQL:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-iteration21-postgres-tests.ps1 -Mode Targeted
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-iteration21-postgres-tests.ps1 -Mode Full
```

Exact repository checks from `AGENTS.md`:

```powershell
python -m pytest services/product_api/tests_unit -q
python -m pytest services/gateway_api/tests -q
npm run lint --prefix services/web_ui
npm run test --prefix services/web_ui
npm run build --prefix services/web_ui
```

With a disposable PostgreSQL URL available:

```powershell
python -m pytest services/product_api/tests -q
```

Additional applicable checks:

```powershell
python -m compileall services/product_api/src/product_api services/gateway_api/src/gateway_api shared
git diff --check
git status --short --branch
```

No Python lint/type-check command is configured or claimed. Web source remains unchanged, but repository-prescribed web regressions still run.

## 14. Review evidence

Code reviewer receives:

- approved spec/plan;
- full diff and exact manifest comparison;
- immutable old-fixture hash report;
- exact V1/V2/artifact/fallback identity goldens and privacy matrices;
- exact catalog wording and 691-scalar golden;
- outbox atomicity/crash-recovery evidence;
- reservation/dispatch concurrency evidence;
- Moscow window rebucketing and two-reschedule/one-dispatch evidence;
- GET/HEAD/SSR/crawler zero-side-effect query/call evidence;
- migration clean/corrupt/downgrade report;
- Targeted/Full JUnit counts;
- exact command/exit-code results;
- confirmation of zero network/paid calls;
- confirmation H2 assignments remain unchanged.

## 15. Rollback and completion

Operational rollback is flag-only and non-destructive:

```text
enabled=false
kill_switch=true
worker stopped
daily/monthly/concurrency defaults=0
```

Do not delete or rewrite reservations, artifacts, pins or snapshots. Consumed credits stay consumed. H1 remains the production resolver.

Iteration may move to `ready_for_merge` only after all checks pass, `git diff --check` is clean, secret/raw scans are clean, and independent code review returns `VERDICT: READY`. Merge and production activation remain manual.

## 16. Risks, open questions and correction self-audit

Risks are closed by the specification and test gates. Open questions:
`none`. If implementation discovers a need to choose a positive production
threshold/model, add provider fields, mutate immutable v3, synthesize fallback
on read, create H2 assignment or call a live service, it stops as a blocker.

Correction mapping:

1. durable report→narrative outbox and crash test — specification §§10–11,
   plan stages 4 and 6;
2. released/reserved rebucketing and counters — specification §12, plan
   stage 5;
3. exact inherited V1 plus complete V2 tuple — specification §9, plan
   stage 2;
4. exact dispatch header/body/HMAC/echo — specification §14, plan stage 3;
5. default-off gateway, missing model and caps — specification §§12,14,
   plan stage 3;
6. OKVED bounds, duplicates and 45-row case — specification §5.3, plan
   stage 1;
7. exact fallback public mapping and trace — specification §13, plan
   stages 2 and 7;
8. pre-lease versus leased/fenced APIs — specification §11, plan stage 4;
9. saved-result-only HTTP/error matrix — specification §§13,15, plan
   stage 7;
10. two-reschedule/one-dispatch, resolved-model identity, 691 scalar,
    catalog-upgrade and normalization goldens — plan stages 2 and 5;
11. full validation/comment/privacy matrix — specification §§7–8, plan
    stage 2;
12. Claims V1/V2 handoff and snapshot/signals/scoring immutability — plan
    stages 1 and 6;
13. exact catalogs/public wording and SQL schema — specification §§7,10;
14. GET/HEAD/SSR/crawler guards and iteration-25 boundary — specification
    §13, plan stage 7;
15. no live/paid calls, no dependency, default-off rollback — plan §§1,3,
    12,15.
