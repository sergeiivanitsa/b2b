# Implementation plan — iteration 20 presentation lifecycle continuation

ID: `20`

Slug: `company-card-v2-backend-foundation`

Continuation key: `presentation-create-lifecycle-contract-v1`

Base commit: `886f207d945e35acc1a7e5c07dcff8c36e501bf6`

Intended branch:
`codex/iteration-20-presentation-create-lifecycle-continuation`

Статус плана:
`IMPLEMENTATION IN PROGRESS AFTER APPROVED REVIEWED PLAN`

Independent plan review: `APPROVED` after one Roadmap prerequisite correction

Owner planning authorization: `APPROVED` — 2026-08-27

Owner implementation approval: `APPROVED` — user command 2026-08-27

Production activation: `NOT AUTHORIZED`

## 1. Execution rules

- Работать только в clean continuation worktree от exact base.
- До code edits получить independent plan review и затем explicit owner
  implementation approval этого полного плана.
- Не переносить код из dirty root worktree.
- Сначала RED regressions, затем минимальная реализация.
- Не использовать live provider/FNS/Gateway/AI, production/unknown DB,
  deploy/config activation.
- Не создавать dependency или migration.
- Docker-based disposable PostgreSQL обязателен до readiness.
- Commit/push требуют отдельной owner command; merge выполняет человек.

## 2. Exact changed-file manifest

### 2.1. Planning/state

```text
docs/development/ROADMAP.md
docs/development/DEVFLOW_STATE.yaml
docs/development/evidence/iteration-20-company-card-v2/iteration-20-presentation-create-lifecycle-baseline-v1.md
docs/development/iterations/iteration-20-company-card-v2-presentation-create-lifecycle-continuation.md
docs/development/plans/iteration-20-company-card-v2-presentation-create-lifecycle-continuation.md
```

### 2.2. Production

```text
services/product_api/src/product_api/company_reports/schemas.py
services/product_api/src/product_api/company_reports/persistence/presentations.py
services/product_api/src/product_api/routers/company_report_presentations.py
services/product_api/src/product_api/company_reports/company_card_v2/service.py
```

The service file may change only the frozen no-subject error code literal.
The persistence file may add only a read-only exact lifecycle resolver and its
internal result/error types.

### 2.3. Tests

```text
services/product_api/tests_unit/test_company_report_presentations_api.py
services/product_api/tests/test_company_report_presentations.py
services/product_api/tests/test_company_report_public_h2_reads.py
```

No runner edit is expected: iteration-20 Targeted already owns both
PostgreSQL test files.

Any production/test path outside this manifest stops implementation for plan
re-review. Formatting-generated asset changes are forbidden.

## 3. Stage A — preflight and RED

1. Fetch `origin/main`; prove base remains exact or rebase/re-audit before any
   edit.
2. Record `git status`, HEAD and hash-locked source blobs.
3. Force worktree-local `PYTHONPATH`; fail if `product_api.__file__` resolves
   outside this worktree.
4. Add named RED tests:

```text
test_presentation_create_openapi_declares_exact_202_lifecycle
test_presentation_create_rejects_any_query_before_gate_or_db
test_presentation_routes_reject_version_profile_selector_headers
test_presentation_create_normalizes_before_cohort
test_presentation_create_returns_complete_frozen_lifecycle
test_presentation_status_ignores_current_rollout_flags
test_presentation_status_reads_only_exact_opaque_binding
test_presentation_status_rejects_corrupt_exact_tuple
test_public_h2_missing_subject_uses_frozen_not_found_code
```

5. Capture failures by contract reason. Do not weaken assertions to match
   current runtime.

## 4. Stage B — strict schemas and OpenAPI

In `company_reports/schemas.py`:

- add public strict create DTO with exactly `identifier: str`;
- add strict lifecycle DTO with seven exact fields and literals;
- document method-relative `reused`;
- keep `canonical_document_path` nullable but never synthesize it;
- reuse existing `StrictPublicModel`.

In route decorators:

- POST declares request model, `response_model`, `status_code=202`;
- GET declares the same `response_model`, `status_code=200`;
- no query/header selector is advertised as an input;
- error responses remain safe JSON.

Unit tests inspect OpenAPI component refs and
`additionalProperties: false`.

## 5. Stage C — exact lifecycle resolver

Add one read-only helper in `persistence/presentations.py`:

1. Select presentation by opaque UUID and its exact report/subject binding.
2. Distinguish missing presentation from corrupt tuple.
3. Validate literal contract, v3 writer/version, generation, lifecycle and
   normalized INN.
4. Return a frozen internal result containing only IDs, contract, lifecycle
   and normalized INN.
5. Never read head/assignment/staged/pin/latest/settings.
6. Never add/flush/commit/rollback or call providers.

Do not alter create/reuse persistence or model constraints.

## 6. Stage D — create/status router

### Create order

1. Strict body parse.
2. Reject any query and named selector headers.
3. Normalize/validate INN.
4. Evaluate cohort on normalized INN.
5. Check writer availability.
6. Enter DB generator.
7. Call existing atomic create/reuse helper.
8. Validate returned presentation/enqueued tuple.
9. Build strict lifecycle before commit.
10. Commit and return `202`.

On conflict/unavailability, rollback and return only safe closed errors.
Disabled/invalid/selector cases do not enter DB.

### Status order

1. Reject query and selector headers.
2. Enter DB without checking current feature/writer/cohort flags.
3. Resolve exact opaque binding.
4. Build strict lifecycle with `reused=true`.
5. Return `200`.

Both paths use one response/header helper. All route-owned responses have
`no-store`, `nosniff`, `noindex,follow`.

## 7. Stage E — public-H2 literal

Change only `PublicH2NotFound.code` to `company_report_not_found`.

Add one enabled-cohort no-subject PostgreSQL route regression with:

- `404`;
- exact code;
- no-store/nosniff/noindex;
- unchanged table counts/no provider calls.

No other public-H2 selection or message changes.

## 8. Stage F — unit and PostgreSQL matrix

### Unit/ASGI/OpenAPI

- exact/extra/missing/invalid request body;
- single/repeated/blank query;
- both named headers, case-insensitive and empty value;
- selector rejection precedes settings/DB;
- normalized identifier passed to cohort and persistence;
- exact seven-key create/status bodies;
- deprecated `status` absent;
- POST first/reuse and GET `reused` semantics;
- canonical path remains null;
- public read path uses stored normalized INN;
- headers on success and route-owned errors;
- OpenAPI exact request/response/status schemas;
- fake corrupt/missing/unavailable sessions are safe and read-only;
- auth/cookie/locale/unknown header invariance.

### Disposable PostgreSQL

- first create produces one subject/report/job/presentation/head,
  `head_generation=1`, `reused=false`;
- exact retry returns same IDs, `reused=true`, counts and head generation
  unchanged;
- incompatible H1 active job gives 409 and zero H2 partial state;
- pending/complete/partial/failed exact status;
- after settings flag/allowlist/percentage/generation/writer flip, status by
  existing ID remains 200 and exact;
- after a newer explicit H2 lifecycle/head, old presentation ID still returns
  old report;
- missing presentation 404;
- corrupt tuple fails closed and never falls back;
- query/header attempts create no rows;
- no-subject public-H2 code is frozen.

Use transaction-safe fixture cleanup only. Do not weaken DB constraints to
manufacture corrupt state; test application validation with legal setup plus
controlled unit doubles where DB constraints intentionally forbid corruption.

## 9. Verification

Run from repository root with worktree-local imports:

```powershell
$env:PYTHONPATH = (Resolve-Path 'services/product_api/src').Path
python -m pytest services/product_api/tests_unit/test_company_report_presentations_api.py services/product_api/tests_unit/test_company_card_v2_presentations.py -q
python -m pytest services/product_api/tests_unit -q
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-iteration20-postgres-tests.ps1 -Mode Targeted
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-iteration20-postgres-tests.ps1 -Mode Full
python -m pytest services/gateway_api/tests -q
npm run lint --prefix services/web_ui
npm run test --prefix services/web_ui
npm run build --prefix services/web_ui
python -m compileall services/product_api/src/product_api
git diff --check
```

Additional static gates:

- YAML parse for `DEVFLOW_STATE.yaml`;
- OpenAPI exact schema probe;
- changed-file manifest;
- no migration/settings/default/dependency change;
- no secrets, `.env`, raw payload, logs, caches or temporary evidence;
- no first-party lifecycle consumer drift;
- `git status --short --branch`.

No PostgreSQL runner may fall back to `DATABASE_URL` from `.env` or an unknown
host. Docker absence is a blocker, not a skip.

Iteration-24 PostgreSQL runner remains separate:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-iteration24-postgres-tests.ps1
```

Passing iteration-20 runners does not close iteration-24 debt.

## 10. Review and state transition

Before code:

- independent plan review must return `VERDICT: APPROVED`;
- owner must explicitly approve this reviewed plan.

After code:

- independent code review receives spec, plan, full diff and exact results;
- blocker findings are fixed and affected matrices rerun;
- ID 20 remains historically `merged`; its state block records continuation
  readiness without erasing old merge metadata;
- commit/push only after separate owner command;
- human merge is followed by docs-only reconciliation with exact merge commit.

Iteration 25 remains blocked until:

1. this continuation is merged and reconciled;
2. iteration-24 disposable PostgreSQL acceptance is closed independently;
3. iteration-25 own exact-base spec/plan are approved.
