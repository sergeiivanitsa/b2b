# Технический план итерации 25 — QA и rollout Company Card v2

ID: 25

Slug: `company-card-v2-qa-rollout`

Specification:
`docs/development/iterations/iteration-25-company-card-v2-qa-rollout.md`

Initial planning-audit base:
`886f207d945e35acc1a7e5c07dcff8c36e501bf6`

Implementation planning base:
`31b299ac88b5fac7d5c04082324fb122d63db7e7`

Initial planning branch: `codex/iteration-25-company-card-v2-qa-rollout`

Refresh branch/worktree:
`codex/iteration-25-company-card-v2-qa-rollout-refresh`, created clean from
exact post-prerequisite `origin/main`; the initial draft was not rebased/reset.

Статус: `IMPLEMENTATION APPROVED — IN PROGRESS`

Initial planning-audit review: `APPROVED 2026-08-27` — reconciliation,
rollout/CAS and QA/CI scopes; this historical verdict is bound to
`886f207...` only.

Refreshed independent plan review round 1: `CHANGES_REQUIRED 2026-08-28`

Correction review: `CHANGES_REQUIRED 2026-08-28` — the first amendment tried
to rerun an iteration-24 migration phase whose stale `head == 0018` assumption
cannot hold after `0019`.

Forward-head amendment reviews: `APPROVED 2026-08-28` — architecture and
evidence reviewers reported no remaining actionable findings.

Owner implementation approval: `APPROVED` — user command 2026-08-28

Production activation: `NOT AUTHORIZED`

## 1. Execution rules

1. Merged prerequisites are closed through PR `#150–#152`; exact base
   identities, bounded delta and Stage 0 are refreshed. Do not execute this
   plan until the owner explicitly approves the now independently reviewed
   specification/plan. The historical iteration-24 runner script remains
   unchanged and is not reused as a gate. Iteration 25
   owns its new JUnit-enforced acceptance runner/checker and one explicitly
   scoped forward-head compatibility edit to the 0018 migration test; no old
   assertion is removed or weakened.
2. Work only in the intended feature worktree and preserve unrelated/user files.
3. Implement test-first in bounded stages; do not absorb iteration 20–24 gaps.
4. Never call live provider/FNS/Gateway/AI or a production database.
5. Keep every runtime/operation default off/zero.
6. Do not execute production seed, deploy, migration, assignment or flag change.
7. No public HTTP mutation surface is added.
8. Historical H1/H2 fixtures and iteration-22 CDP evidence are immutable unless
   a byte change is explicitly named as a new versioned artifact.
9. No dependency is added beyond the two approved dev-only browser-test
   packages. Any further dependency is a plan blocker.
10. Commit/push require a later separate owner command. Merge is human-only.

## 2. Expected changed-file manifest

The exact implementation diff is constrained to these surfaces. A needed path
outside the list requires an explicit scope audit before editing.

### 2.1. Docs and state

```text
README.md
.gitignore
docs/development/ROADMAP.md
docs/development/DEVFLOW_STATE.yaml
docs/development/decisions/iteration-25-planning-activation-boundary-v1.md
docs/development/evidence/iteration-25-company-card-v2/**
docs/development/iterations/iteration-25-company-card-v2-qa-rollout.md
docs/development/plans/iteration-25-company-card-v2-qa-rollout.md
docs/development/runbooks/company-card-v2-rollout.md
deploy/nginx/README.md
services/web_ui/README.md
services/product_api/.env.example
```

`docker-compose.yml` may change only to document default-off production-like
settings and only if it retains every false/zero default. No credential or
positive operation value is added.

### 2.2. Persistence and rollout runtime

```text
services/product_api/alembic/versions/0019_company_card_v2_rollout_control.py
services/product_api/src/product_api/company_reports/persistence/models.py
services/product_api/src/product_api/company_reports/persistence/presentations.py
services/product_api/src/product_api/company_reports/persistence/public_documents.py
services/product_api/src/product_api/company_reports/persistence/publications.py
services/product_api/src/product_api/company_reports/persistence/__init__.py
services/product_api/src/product_api/company_reports/company_card_v2/public_h2.py
services/product_api/src/product_api/company_reports/company_card_v2/service.py
services/product_api/src/product_api/company_reports/company_card_v2/narrative/service.py
services/product_api/src/product_api/company_reports/company_card_v2/rollout_models.py
services/product_api/src/product_api/company_reports/company_card_v2/rollout.py
services/product_api/src/product_api/company_reports/public_document_service.py
services/product_api/src/product_api/routers/company_reports_public.py
services/product_api/src/product_api/settings.py
services/product_api/Dockerfile
services/gateway_api/Dockerfile
docker-compose.product.yml
```

Add optional `PRODUCT_RELEASE_COMMIT`, accepted only as exact 40 lowercase hex
when present. Local/default-off runtime may omit it; rollout mutation requires
it and requires equality with the decision. `docker-compose.product.yml`
injects the exact deploy SHA into Product and both workers without changing a
feature default. No public control is added.

The existing presentation create/status router is read by cross-layer tests but
is not an iteration-25 edit surface. PR `#150` closed its frozen lifecycle/query
contract defect; iteration 25 only preserves that result as a regression gate.

### 2.3. Product tests and synthetic fixtures

Expected new/extended paths:

```text
services/product_api/tests_unit/test_company_card_v2_rollout_decision.py
services/product_api/tests_unit/test_company_card_v2_rollout_privacy.py
services/product_api/tests_unit/test_company_card_v2_public_h2_activation.py
services/product_api/tests_unit/test_company_report_public_assignment_sitemap.py
services/product_api/tests_unit/test_ci_network_guard.py
services/product_api/tests_unit/test_ci_junit_guard.py
services/product_api/tests_unit/conftest.py
services/product_api/tests/test_company_card_v2_rollout.py
services/product_api/tests/test_company_card_v2_rollout_migration.py
services/product_api/tests/test_company_card_v2_rollout_e2e.py
services/product_api/tests/test_company_report_iteration24_migration.py
services/product_api/tests/test_claims_company_report_handoff.py
services/product_api/tests/conftest.py
services/gateway_api/tests/conftest.py
services/product_api/tests/fixtures/company_card_v2_iteration25/**
shared/fixtures/company_card_v2_iteration25/**
tests_support/__init__.py
tests_support/network_guard.py
tests_support/junit_guard.py
scripts/run-iteration25-postgres-tests.ps1
scripts/seed-iteration25-company-card-v2-acceptance.py
scripts/check-iteration25-test-results.py
scripts/check-python-ci-lock.py
docs/development/evidence/iteration-25-company-card-v2/iteration-25-test-baseline-v1.json
```

Existing tests may be extended only when the new rollout behavior belongs
there. Historical goldens are not overwritten; active/staged/indexable outputs
receive new names.

### 2.4. Web/browser/performance

```text
services/web_ui/package.json
services/web_ui/package-lock.json
services/web_ui/playwright.config.ts
services/web_ui/e2e/companyCardV2/**
services/web_ui/src/companyPublicH2/CompanyPublicH2Page.css
services/web_ui/src/companyPublicH2/**/*.test.ts*
services/web_ui/scripts/company-public-h2-bundle-budget.mjs
services/web_ui/company-public-h2-bundle-budget.json
services/product_api/src/product_api/company_reports/company_card_v2/public_h2_asset_manifest.json
```

CSS changes are limited to a production-valid safe-area design token and any
layout reservation required by a failing real-browser test. Product UI facts,
copy, order and chart semantics do not change.

Playwright screenshot baselines live beside the new E2E suite in its generated
`*-snapshots` directory. `.tmp/iteration22-visual/`, new Playwright output,
traces, reports and PostgreSQL runner artifacts are gitignored.

### 2.5. CI and release tooling

```text
.github/actions/setup-python-ci/action.yml
.github/ci/playwright-font-inventory.sha256
.github/ci/python-bootstrap.lock
.github/ci/python-gateway-runtime.lock
.github/ci/python-product-runtime.lock
.github/ci/python-test.lock
.github/workflows/qa.yml
.github/workflows/product_api_unit_tests.yml
.github/workflows/deploy_prod.yml
.github/workflows/company_public_h2_seed_bundle.yml
deploy/nginx/company_public_h2_release.py
deploy/nginx/company_public_h2_seed.py
deploy/nginx/install_company_public_h2_assets.sh
deploy/nginx/seed_company_public_h2_assets.sh
deploy/nginx/test_company_public_h2_release.py
deploy/nginx/test_company_public_h2_seed.py
deploy/nginx/test_product_api_conf.ps1
deploy/product_api/worker_drain.py
deploy/product_api/test_worker_drain.py
deploy/web_ui/install_web_ui_release.sh
deploy/web_ui/test_install_web_ui_release.py
```

The old Product-only workflow is removed or reduced to a reusable/compatibility
wrapper only after `qa.yml` provides the same unit job. There must be one
unambiguous required `qa-required` status, not competing partial gates.

### 2.6. Explicitly unchanged semantics

```text
services/product_api/src/product_api/company_reports/public_h1.py
services/product_api/src/product_api/claims/**
services/product_api/src/product_api/providers/datanewton/**
services/gateway_api/src/**
shared CompanyReport/Claims domain contracts
historical migrations 0001..0018
historical iteration-22 browser scripts and visual evidence
```

Tests may read these surfaces. A required semantic edit is a blocker and needs
an approved plan amendment.

## 3. Dependency decision

Add exactly:

```text
devDependency: @playwright/test
devDependency: @axe-core/playwright
```

Rationale:

- the required gate needs portable pinned Chromium, touch/reduced-motion
  contexts, network interception, trace capture and deterministic screenshots;
- axe provides a repeatable browser accessibility scan while explicit
  keyboard/focus tests remain authoritative;
- both are test-only and the H2 production manifest closure will prove they are
  absent from entry/lazy assets.

Rejected alternative: extending raw CDP would require maintaining custom
Linux browser discovery, touch emulation, trace/visual diff and accessibility
infrastructure. The historical CDP harness stays unchanged as evidence.

No new production npm or Python dependency is allowed. Network blocking uses
existing mock transports, Playwright routing and standard-library socket
guards rather than adding `pytest-socket`.

The Stage 0 npm advisory summary is retained only as a dated external
observation; it is not a frozen dependency baseline. Future installs use
`npm ci --no-audit`, while a separate
`npm audit --json --package-lock-only --prefix services/web_ui` observation
records UTC, npm version, registry, exact base/candidate lock identities and
nonzero advisory package/severity details inline in evidence. Cross-time count
differences are not called an exact dependency delta without an immutable
advisory dataset. The deterministic checks are the lockfile package-graph
delta and proof that test-only packages do not enter the H2 or SPA production
closure. No automatic audit fix or broad dependency upgrade is authorized.

The shared test guard is installed by all three Python `conftest.py` files
before application/provider imports. It fails instead of deleting an inherited
paid/provider/SMTP/arbitration credential; mandatory application secrets must
equal closed test placeholders. It blocks DNS and socket connect outside a
suite-specific allowlist: unit/Gateway permit loopback only, while integration
adds only the runner-validated disposable PostgreSQL host/port. Wildcards,
public IPs and environment-expanded arbitrary hosts are rejected.

The four Python lock files pin the existing Product/Gateway runtime, combined
test and build-tool closures only; they do not add a project dependency. Every
entry is an exact version with hashes for the one supported Linux x86_64
CPython patch, and shared packages have identical pins/hashes across locks.
The implementation resolves and verifies those locks, the exact Python
base-image digest, the exact Playwright npm package/browser version, the
matching official Playwright container digest, the PostgreSQL service digest
and Action SHAs before recording them. This plan does not invent versions or
digests before compatibility verification.

## 4. Migration decision

One additive `0019` revision is required because the current schema permits
only noindex/canonical-null H2 pins and the journal cannot bind a rollout
decision.

Revision work:

1. add nullable `projection_scope` to presentation pins;
2. replace only the presentation-pin contract-shape check with the compatible
   legacy/staged/active shapes from the specification;
3. add the non-sensitive global rollout-decision binding table with primary/
   unique/composite identity constraints;
4. add nullable `decision_id`, `decision_digest`, `reason_code` to assignment
   journal;
5. add all-null/all-valid check, new-row uniqueness and composite FK to the
   global decision binding;
6. add assignment unique `(id, subject_id)` and replace only the journal's
   scalar assignment FK with `(assignment_id, subject_id)` → assignment
   `(id, subject_id)`, preserving `ON DELETE CASCADE`; validate all legacy
   pairs and fail without rewrite on any cross-subject mismatch;
7. leave all historical rows unchanged;
8. add no sitemap eligibility/materialized-index column or backfill;
9. implement a guarded downgrade that refuses data-losing removal when **any**
   pin has non-null `projection_scope`, any journal row has a new audit field or
   any global decision row exists. Before the guard it acquires
   `SHARE ROW EXCLUSIVE` locks in exact order:
   `company_card_v2_rollout_decisions`,
   `company_report_presentation_assignments`,
   `company_report_presentation_pins`,
   `company_report_presentation_assignment_journal`; the same PostgreSQL
   transactional-DDL transaction holds them through all drops.

No table is dropped, no snapshot/pin is rewritten and no production migration
is executed in this iteration.

## 5. Stage 0 — prerequisite and immutable baseline

This stage was completed on `2026-08-28` before any production-code edit and
is the comparison baseline during implementation. Its historical commands are
recorded below; future gated prerequisite re-verification runs through the new
iteration-25 JUnit-enforced runner rather than reusing the old runner as proof.

1. Record external closure: iteration-20 PR `#150/#151` and iteration-24 PR
   `#152`; do not rename those continuations as iteration-25 code.
2. Confirm the new clean branch/worktree at exact
   `31b299ac88b5fac7d5c04082324fb122d63db7e7`, preserve the old draft and record
   bounded delta `886f207...31b299ac`.
3. Record SHA-256 for:
   - H1 Product/Web JSON and HTML goldens;
   - existing H2 V1/V2/V3 public fixtures;
   - current H2 asset manifest;
   - iteration-22 CDP scripts;
   - migrations through `0018`.
4. Run the current mandatory lower-layer suites before behavior changes.
5. In an identical disposable environment, record origin/main integration,
   Web build and release baselines.
6. Record existing skips by exact node ID/reason. Setup/DB unavailability and
   relevant Company Card/Claims skips are blockers; unrelated accepted skips
   require an exact committed allowlist rather than a count-only waiver.
7. Before, between and after PostgreSQL runners, require empty iteration-20 and
   iteration-24 owned-label queries. Never auto-delete an unknown leftover.

The refreshed evidence records `50` frozen lifecycle tests, `1524` Product
unit, `31` Gateway, `496` Web, `34` release, iteration-24 `2 + 79` and
iteration-20 `117 + 290` as passing, with zero PostgreSQL skips/failures/errors.

Baseline commands:

```powershell
$repo = (Resolve-Path '.').Path
$env:PYTHONDONTWRITEBYTECODE = '1'
Remove-Item Env:PYTEST_ADDOPTS -ErrorAction SilentlyContinue

$env:PYTHONPATH = "$repo\services\product_api\src$([IO.Path]::PathSeparator)$repo"
python -m pytest services/product_api/tests_unit/test_company_report_presentations_api.py services/product_api/tests_unit/test_company_card_v2_presentations.py -q -ra -p no:cacheprovider
python -m pytest services/product_api/tests_unit -q -ra -p no:cacheprovider

$env:PYTHONPATH = "$repo\services\gateway_api\src$([IO.Path]::PathSeparator)$repo"
python -m pytest services/gateway_api/tests -q -ra -p no:cacheprovider

npm ci --prefix services/web_ui
npm run lint --prefix services/web_ui
npm run test --prefix services/web_ui
npm run build --prefix services/web_ui
python -m pytest deploy/nginx -q -ra -p no:cacheprovider
pwsh -File deploy/nginx/test_product_api_conf.ps1

powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-iteration24-postgres-tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-iteration20-postgres-tests.ps1 -Mode Targeted
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-iteration20-postgres-tests.ps1 -Mode Full
```

The refreshed full integration baseline used this three-runner composition;
it never ran direct pytest with an inherited/default `DATABASE_URL`.
Iteration-20 Full intentionally
excludes the separately accepted iteration-24 migration module. The exact-base
iteration-24 console summaries recorded `2 passed` and `79 passed`, but exit
`0` or console-substring matching is not an executable no-skip gate. Before
either phase is treated as acceptance evidence, make one forward-head
compatibility change: both generic `upgrade(config, "head")` calls in
`test_company_report_iteration24_migration.py` target its frozen `REVISION`
(`0018`) instead, while every guard/default/roundtrip/row assertion stays
unchanged; update only the stale module comment to describe the explicit
handoff. The new iteration-25 runner executes that exact-0018 phase, then
explicitly upgrades its roundtrip database `0018 -> 0019/head`, verifies exact
revision `0019`, and only then starts the affected integration phase.
The compatibility subphase creates only
`i24_guard_<12hex>`/`i24_roundtrip_<12hex>` databases owned by matching
`i24u<12hex>` inside the new runner's uniquely named, loopback-only,
`com.b2b.iteration25.disposable=true` container because the preserved test
validates that frozen identity shape. It never invokes the old runner, accepts
an external URL or adopts the old iteration-24 ownership label.

Each pytest phase writes a distinct JUnit XML under a unique runner-owned
temporary directory. After pytest exit `0`, the checker rejects missing, stale
or malformed XML, requires more than zero `//testcase` nodes, and requires zero
`//failure`, `//error` and `//skipped` nodes. It prints validated per-phase counts and
removes only its owned temporary directory in `finally`. Synthetic parser tests
cover clean, zero-test, skipped, failed, errored and malformed XML. The two
iteration-20 JUnit files likewise show nonzero tests and zero failures/errors/
skips. Historical `2/79` are not frozen into the runner because legitimate
test growth is allowed. The old iteration-24 runner script is not modified or
reused as the executable gate.

## 6. Stage 1 — RED decision, pin and CAS matrix

Before implementation, add failing tests for:

- strict decision schema, duplicate keys, Unicode/surrogate/size/path issues;
- canonical decision bytes/digest and no sensitive repr/log output;
- exact action/stage/nullability/target-field matrix, 1 MiB/1,000-target caps,
  strict INN/subject uniqueness/order and deterministic stop/resume ordinals;
- allowlist sort/unique and frozen percentage bucket vectors;
- release/config mismatch and missing production fields;
- legacy null pin scope versus new staged/active scope;
- preserved iteration-24 exact-0018 migration assertions plus explicit
  iteration-25 `0018 -> 0019/head` handoff before its affected suite;
- staged-pointer write/read rejection of active scope or any indexable pin;
- active noindex/indexable H2 pin append without staged mutation;
- H2 policy/snapshot/artifact/chart/evidence/Claims/canonical corruption;
- target pin generation independent from assignment generation;
- concurrent absent-assignment inserts serialized by subject lock;
- global decision-ID/digest/release/action binding, advisory-lock contention
  and same-ID/different-digest races across different subjects;
- assignment `(id, subject_id)` composite identity and cross-subject journal
  rejection at the database boundary;
- exact NUL-byte advisory-key vector and session-lock lifecycle on a dedicated
  one-invocation `NullPool` physical connection: same-connection binding and
  every target, PID/`pg_locks` guard before each mutation, normal completion,
  binding/target exception, cancellation, repeated cancellation/SIGTERM,
  unlock/invalidate/close failure, physical-driver termination and successful
  retry;
- explicit SQLAlchemy transaction ownership: acquisition commit preserves the
  session lock; every binding/target guard is the first statement inside its
  own connection-owned transaction; no outer/implicit transaction exists
  between targets or around final unlock;
- durable-prefix regression: target N remains committed after target N+1
  rolls back, while `connection.in_transaction() == false` between them;
- real-PostgreSQL termination of the recorded lock-owner PID between targets:
  no next mutation, `rollout_lock_lost`, PID/lock disappearance and immediate
  same-decision reacquire/resume from the durable prefix;
- absent/current/stale CAS, applied-current replay success, superseded replay
  conflict and different-decision behavior;
- H1 → H2 → H1 journal order and exact rollback pin;
- concurrent activation/rollback races;
- guarded-downgrade lock order and concurrent writer versus guard/DDL race;
- sitemap H1/H2 uniqueness and corrupt-assignment fail-closed, including late
  corruption, valid/invalid rows around chunk boundaries, bounded validation
  windows and repeatable-read before/after views;
- immutable row hashes unchanged across the full sequence;
- inherited credential rejection and deny-non-loopback guard escape tests via
  raw socket, DNS, stdlib HTTP and HTTPX; exact loopback/disposable-PostgreSQL
  positive cases remain suite-specific;
- iteration-25 JUnit guard clean/nonzero success plus zero-test, skipped,
  failed, errored, missing, stale and malformed XML; runner-owned temporary
  cleanup is exact and fail-closed.

RED tests must fail for the missing behavior, not because a fixture silently
skips or because Docker is absent.

## 7. Stage 2 — migration and model compatibility

Implement `0019` and model metadata together.

Tests cover:

1. fresh `upgrade head`;
2. `0018 -> 0019` with representative historical H1 and H2 pins/journal;
3. preserved iteration-24 guard/default/roundtrip assertions at explicit
   `0018`, then exact `0019/head` on the same roundtrip DB before affected tests;
4. exact old-row bytes/values after upgrade;
5. every allowed and forbidden pin shape;
6. all-null/all-valid decision fields and invalid partial combinations;
7. global decision primary/unique/composite binding and journal FK;
8. assignment `(id, subject_id)` unique, journal composite FK and rejection of
   a legacy or new assignment-A/subject-B mixture;
9. decision digest uniqueness per assignment;
10. empty/legacy downgrade-reupgrade;
11. downgrade refusal after any new staged/active non-null scope, audited
    transition or global decision binding;
12. deterministic table locks held across guard and transactional DDL, with a
    real concurrent-writer race proving no new-schema data is silently lost;
13. model/migration constraint-name parity.

Do not autogenerate or edit `0018`.

## 8. Stage 3 — explicit projection binding and immutable active pins

Introduce a frozen internal value object, for example
`PublicH2ProjectionBindingV1`, containing only:

```text
projection_scope
canonical_path
indexable
published_lastmod
```

Refactor the pure public-H2 builder to consume that explicit binding while
retaining its current default only for frozen unit fixture callers. It may not
read Settings, DB, current time or request state.

The narrative service may change only to calculate a newly finalized pin's
projection digest with the explicit staged binding. Prompt, catalogs, budget,
dispatch, validation, fallback text and artifact identity remain byte-stable.

Resolution rules:

- legacy `projection_scope=null` H2 pins reproduce their exact stored digest
  and historical `latest_unpublished` behavior;
- new staged pins build `staged_publication/noindex`;
- new active pins build `active_publication` with exact pin canonical/
  indexability/lastmod;
- stored projection digest must match the rebuilt complete DTO;
- no fallback between candidate scopes is allowed for a new non-null scope.

Both `stage_h2_pin` and staged/latest resolution enforce the staged noindex
shape. They admit only legacy-null or `staged_publication` H2 pins with
`indexable=false` and null canonical/lastmod, and reject active scope even when
that active pin is noindex. PostgreSQL tests inject forged active/indexable
pointers directly and prove the read fence still fails closed.

Add `append_active_h2_pin`:

1. accept only the already subject-locked target-command context owned by the
   rollout transaction; never acquire a pin before the subject;
2. load/lock all command pins in deterministic contract/generation order and
   validate the exact resolved staged/historical predecessor and report;
3. build the active DTO with explicit binding;
4. apply noindex/indexability predicate;
5. append `max(generation)+1` with exact new digest;
6. return an exact existing row only for byte-identical idempotency;
7. reject a conflicting active binding; never update a pin.

New active noindex and active indexable outputs get new JSON/HTML goldens. Old
goldens remain byte-identical.

## 9. Stage 4 — general assignment CAS and journal

Replace the current H1-only semantics with one immutable per-target command
whose fields exactly match specification section 8: decision binding, subject/
INN, expected assignment/current pin identity and the action-specific source
H2, expected active H2/digest and exact H1 rollback/target generations. Keep a
compatibility wrapper only if existing callers need it and prove identical H1
behavior; no helper may rediscover “latest”.

Implementation order inside one transaction follows specification section 10.
Additional requirements:

- lock the stable subject row before reading/inserting assignment so two first
  assignments cannot race past a missing-row `FOR UPDATE`;
- use the single lock order subject → assignment/journal → pins ordered by
  contract/generation → report/artifact; active-pin append and CAS share this
  transaction/context and never take the reverse order;
- H2 target requires exact decision release/generation and validated H1
  rollback pin before mutation;
- H1 rollback target is caller-selected, not “latest”;
- absent assignment uses expected current generation `0` and creates generation `1`;
- existing assignment advances `current+1` only;
- load the decision journal before expected-generation validation: same digest
  + exact result still current returns idempotent success despite the now-stale
  original expectation; a later assignment returns `decision_superseded`;
- same digest + different journal result is corruption/conflict;
- a later decision naming the already assigned exact pin returns
  `already_target` without assignment/journal growth;
- journal is appended before commit and covered by composite FKs;
- journal assignment identity is covered by `(assignment_id, subject_id)` →
  assignment `(id, subject_id)`, in addition to the exact subject/pin FK;
- no raw decision object enters ORM repr or structured log.

Remove the unconditional H2 rejection only after all RED cases pass.

After full read-only validation and before binding/target transactions, derive
the signed 64-bit key from the specification's exact NUL-byte vector. Create a
one-invocation async engine with `NullPool`, acquire exactly one physical
connection and use a connection-owned acquisition transaction to record its
backend PID and call nonblocking `pg_try_advisory_lock(key)`. Commit/exit that
transaction before binding; the session lock persists and
`connection.in_transaction()` must then be false. Contention reports
`decision_in_progress`.

The same connection performs the binding insert-or-compare and every ordered
target transaction through bound sessions; use of the shared engine, a second
target connection, reconnect/recheckout or automatic retry is forbidden. Each
binding/target unit is owned by its own `connection.begin()` context. Its
PID/exact-`pg_locks` guard is the first statement inside that transaction; the
bound ORM session uses `expire_on_commit=false`, flushes/closes without
`commit()`, does not own/extend the transaction and materializes its closed
outcome before exit so no later lazy load triggers autobegin.
After normal commit or handled rollback the context must exit and assert
`connection.in_transaction() == false` before any stop check/next target; no
interstitial query may trigger autobegin. Disconnect/query error, invalidation,
PID change or lock absence yields `rollout_lock_lost` before any next mutation.
A killed backend during a target leaves only the transaction's atomic
committed-or-rolled-back result, resolved by the durable journal on a later
exact-decision resume. A real-PostgreSQL regression commits target N, rolls
back N+1 and proves N remains durable plus the between-target no-transaction
invariant.

Install/restore a controlled SIGTERM handler around the batch. SIGTERM or task
cancellation first closes target admission. Await current transaction cleanup,
then await an idempotent cleanup task under `asyncio.shield`; repeated signals/
cancellation cannot cancel it. `finally` requires
`pg_advisory_unlock(key) = true`, closes the physical connection and disposes
the `NullPool` engine within a finite tested technical timeout. The unlock
query owns and exits its own explicit transaction; no implicit transaction is
left for close. Any uncertain unlock/close or timeout invokes the non-awaitable
asyncpg driver `terminate()` fallback before propagating cancellation or
SIGTERM exit `143`. Tests prove PID/lock disappearance and immediate
same-decision retry for every path.
Targets are strictly sorted/unique, the complete file and cohort membership
are prevalidated, and the first new failure stops the batch. Resume accepts
only the exact same global binding.

## 10. Stage 5 — operator-only rollout CLI

Implement a module CLI, with no web router registration:

```powershell
python -m product_api.company_reports.company_card_v2.rollout validate --decision-file <path>
python -m product_api.company_reports.company_card_v2.rollout plan --decision-file <path>
python -m product_api.company_reports.company_card_v2.rollout apply --decision-file <path> --confirm-digest <sha256>
python -m product_api.company_reports.company_card_v2.rollout rollback --decision-file <path> --confirm-digest <sha256>
python -m product_api.company_reports.company_card_v2.rollout status --decision-file <path>
```

Rules:

- `validate/plan/status` are read-only;
- decision `action` is only `activate|rollback`; CLI mode is not serialized as
  an action. Enforce the closed action/stage/nullability table, 1 MiB/1,000
  target technical caps, exact target field sets, strict INN order/uniqueness
  and `targets.length <= maximum_batch_size`;
- `apply/rollback` refuse TTY-free accidental execution unless the exact
  digest is supplied; no generic `--force` exists;
- decision SHA must equal the checked-out/reported release SHA;
- `PRODUCT_RELEASE_COMMIT` must be present, exact and equal to the decision for
  mutation; its absence is allowed only for read-only/local operation;
- activation live config must equal decision generation/allowlist/percentage;
- rollback/emergency rollback must work with presentation/writer flags closed
  and generation/allowlist/percentage reset; it validates only release/tool,
  authorization, exact current assignment, H1 pin and CAS fence;
- each target is exact and bounded by required `maximum_batch_size`;
- allowlist/percentage/GA membership is recomputed with the frozen bucket rule
  before mutation; a nonmember or out-of-order/duplicate target rejects the
  complete decision;
- read-only `plan` computes source pin, active projection digest and the exact
  expected active identity: an existing byte-identical reusable generation or,
  when absent, the exact next generation; `apply` rechecks and performs that
  reuse/append plus assignment CAS in the same transaction;
- no target causes report generation, provider, AI or fallback synthesis;
- output is JSON with decision ID/digest, counts and target ordinal by closed
  outcome only; it never emits an INN, subject/report UUID, URL or decision body
  and has no detailed-identifier output mode;
- processing stops at the first new failure; the explicit completed prefix is
  safe to resume only under the same global decision binding/advisory lock.

Use dependency injection for session/config/release identity so unit tests
never read a real environment or production DB.

## 11. Stage 6 — canonical, sitemap and crawler parity

Extend the assignment-aware public-document read without adding a second
assignment selection.

1. Canonical H2 validates exact active pin scope/digest and emits index/noindex
   from the pin.
2. Staged/latest preview routes remain noindex and cannot enter sitemap.
3. Sitemap uses an assignment overlay: no assignment keeps the current valid
   H1 publication; assigned H1 uses its exact pin; assigned indexable H2 uses
   its exact pin; assigned noindex/corrupt H2 suppresses H1 and emits no row.
4. Active H2 suppresses the H1 sitemap row. The control plane completely
   forbids indexable-H1 → noindex-H2 rather than accepting a generic warning.
5. Missing/corrupt H2 assignment fails closed everywhere; it never scans H1 or latest.
6. Wrong slug, query, HEAD, robots and error paths remain read-only/noindex.

Replace the current Python-side full-publication materialization with one
bounded full-validation pipeline. Each sitemap request opens one read-only
`REPEATABLE READ` transaction. A SQL assignment overlay controls precedence
and selects at most one complete candidate dependency tuple per subject:

- no assignment selects the current H1 publication/report/subject tuple;
- any assignment selects only its exact assignment/pin/report and required H2
  presentation/job/artifact tuple;
- assignment presence suppresses H1 before validation, including when its H2
  tuple is missing, noindex or corrupt.

Stream candidates in keyset windows of at most `100`, ordered by
`(normalized_inn, coalesce(selected_canonical_path, ''), subject_id)`. Do not
use `.all()`, unbounded retention, SQL `OFFSET` over candidates or a persisted
eligibility bit. Every tuple, including assigned noindex, passes the same full
pure H1/H2 validation used by canonical resolution without calling that
resolver again or performing another selection. Structurally valid SQL rows
with invalid snapshot bytes/hash/model, time/canonical, projection,
presentation/job/artifact, Claims or privacy lineage are excluded fail closed.

The index scans the finite candidate stream and retains only one integer
eligible count. Chunk N scans the same logical stream from its start, skips
exactly `(N - 1) * chunk_size` validated eligible rows and retains at most the
one output chunk. This intentionally makes index/deep/out-of-range work
`O(candidate_count)` while memory remains bounded by one validation window,
one validation state and one output chunk. Empty/out-of-range pages are stable;
storage/system failure returns a safe error without partial XML. In one fixed
snapshot count/chunk have identical selection, validation and order. A
concurrent assignment/rollback yields one complete before-view and becomes
visible only to a later request. The no-assignment result set/order/lastmod is
byte-equivalent to current valid H1.

Tests instrument SQL/DML/provider/Gateway/worker calls and prove:

- the document assignment tuple is one joined selection;
- a legacy/default active H1 publication remains in sitemap when assignment is absent;
- every candidate fetch is at most `100`; retained candidates do not grow with
  large synthetic N; index retains only a count and chunk retains at most the
  frozen output size;
- interleaved corrupt/noindex rows immediately before, on and after chunk
  boundaries leave no holes or duplicates; concatenated chunks equal the full
  canonical-valid sorted set;
- a row corrupted after successful activation is excluded on the next sitemap
  read, proving there is no stale eligibility cache;
- alternate internal window sizes and insertion orders produce identical XML;
- a PostgreSQL concurrency barrier proves repeatable-read before-view and
  next-request committed after-view semantics;
- sitemap does not independently pick a different report/pin;
- GET/HEAD/crawler reads create zero writes/external calls;
- H1 bytes are unchanged before and after an unrelated H2 staged pin.

## 12. Stage 7 — merged prerequisite re-verification

This stage contains no route implementation. First implement the new
iteration-25 runner/checker against the Stage 1 parser tests, without editing
the old runner script. Apply only the scoped old-test compatibility edit above,
run its preserved migration assertions at explicit `0018`, upgrade that
roundtrip DB to verified `0019/head`, then run the affected phase. Accept only
nonzero per-phase JUnit counts with zero failure/error/skip; console summaries
alone are diagnostic.

PR `#150/#151` already closed and reconciled the iteration-20 debt before
iteration-25 code. Re-run the frozen contract tests here after migration/CAS
changes to prove the complete lifecycle and selector rejection remain green.
Any regression stops iteration 25; the old iteration-24 runner script and
router remain outside this edit scope.

## 13. Stage 8 — acceptance registry and PostgreSQL seeder

Create the five sanitized profiles from the specification as closed public/
persistence fixtures, not provider raw.

The seeder:

- accepts only a runner-owned database URL and generated database name;
- verifies schema at `0019`;
- creates exact subject, H1, v3 H2, narrative, pin, assignment/journal rows
  through production persistence helpers where possible;
- uses deterministic UUIDs/timestamps/Decimals only inside fixtures;
- calculates every snapshot/chart/projection digest with production code;
- refuses unknown profile IDs and external URLs;
- prints only profile IDs and aggregate counts;
- never imports Settings credentials or provider clients.

Add a fixture manifest recording expected public facts and forbidden tokens.
Run repository-wide scans ensuring no real СКС identifier/name/raw payload is
present.

## 14. Stage 9 — Playwright E2E and visual matrix

Add package scripts:

```text
test:e2e
test:e2e:update-snapshots
test:e2e:ci
```

CI runs inside the digest-pinned official Playwright Linux container whose tag
matches the exact `@playwright/test` version and bundled Chromium revision in
`package-lock.json`. It does not run `playwright install --with-deps`, `apt` or
any browser/channel download. Startup asserts the expected Playwright/browser
revision and the SHA-256 of a normalized `fc-list` font inventory against
`.github/ci/playwright-font-inventory.sha256`; normalization fixes `LC_ALL=C`,
emits file/family/style/index fields, LF endings and bytewise sort. The config fixes locale,
timezone, color scheme, reduced-motion defaults, device scale factor, retries
and one worker for visual stability.

Harness sequence:

1. start disposable PostgreSQL and migrate to head;
2. seed profiles;
3. install the same deny-network guard, then start Product API bound to
   loopback with only disposable PostgreSQL + loopback allowed and all
   operation flags off;
4. serve built immutable H2 assets through a loopback same-origin fixture
   proxy; no production-only test route is added;
5. before navigation, route and hold the exact H2 entry-module response while
   CSS/font/static requests continue; abort every non-loopback request;
6. after response commit, prove the untouched SSR marker and canonical factual
   fallback, await `document.fonts.ready`, require Layout Shift observer
   support, record `post_font_start = performance.now()`, and arm a buffered
   observer before releasing the entry module;
7. release the module, await explicit harness-observed hydration takeover and
   the terminal lazy success/error marker without sleeps, then run the remaining
   core/interaction/failure matrix;
8. after the terminal marker, await two stable `requestAnimationFrame`
   boundaries, merge the observer callback buffer with `takeRecords()`, then
   disconnect and assert every positive entry whose `startTime >=
   post_font_start`, including entries with `hadRecentInput=true`; earlier
   buffered entries are diagnostic only;
9. upload bounded failure-only report/trace/screenshots;
10. terminate processes and delete only runner-owned temp state.

Assertions port the historical CDP semantics and add:

- full F1–F5/A1–A5 visible/text/chart parity;
- touch contexts and pointer semantics;
- non-zero safe-area token portrait/landscape;
- lazy chunk request timing and deterministic failure;
- layout-shift observer;
- axe scan and exact keyboard focus order;
- JS-disabled complete/partial documents;
- canonical/wrong-slug/robots/sitemap/crawler/Claims paths;
- no service worker, Webvisor, telemetry or second factual GET from the Company
  Card document.

For Claims links, intercept the exact loopback main-frame document request to
`/claims?report_id=...` before the destination response commits. Assert full
document navigation, method and exact pinned report ID, then terminate that
navigation. Do not load generic SPA `index.html` or claim that its existing
site-wide Yandex Metrika/Webvisor behavior belongs to Company Card.

Do not delete or repurpose `scripts/run-iteration22-*`.

## 15. Stage 10 — safe-area, accessibility and lazy layout corrections

Only after a failing E2E proves need:

1. expose a CSS design token whose production default is
   `env(safe-area-inset-bottom, 0px)`;
2. allow the harness to override that token with a non-zero value;
3. reserve stable chart/error/fallback dimensions through hydration/lazy load;
4. correct focus/target/overflow issues without changing facts/copy/order;
5. update only new iteration-25 screenshots and the generated H2 manifest.

Every CSS change must pass existing component/geometry tests and explain its
asset byte delta.

## 16. Stage 11 — bundle and layout-shift gate

Create a deterministic budget file from the pinned base build with:

- manifest identity;
- each asset raw/gzip bytes;
- eager entry closure and lazy finance/arbitration closures;
- approved file-level delta/rationale fields.

The checker fails on:

- unknown/missing/duplicate asset;
- lazy chunk reachable from eager closure;
- positive eager delta without an explicit reviewed budget update;
- test dependency string/module in production graph;
- mismatch between Product manifest and built bytes.

This is named a **post-font zero-shift gate**, not a full CLS-window metric. The
entry module stays held until the SSR assertion and `document.fonts.ready`
succeed. The harness then requires observer support, records the monotonic
`post_font_start`, and installs the buffered observer before release. Missing
Layout Shift API support is a failure, never an empty pass. Buffered entries
with `startTime < post_font_start` are retained only as diagnostics. After
explicit hydration/lazy terminal signals, two stable animation frames and a
final `takeRecords()` drain precede disconnect/assert. Every positive
post-cutoff entry fails, regardless of `hadRecentInput`, and reports its value,
flag and DOM sources. LCP/timing remain artifacts only.

## 17. Stage 12 — privacy-safe status and observability

Use existing logging/metrics facilities only; do not add an observability SDK.

Add closed server/operator events for:

- plan eligibility counts;
- activation/rollback success, stale CAS and invalid lineage;
- H2 public projection safe error class;
- asset missing/hash mismatch;
- AI/provider gate state and fallback/budget outcome as existing aggregate codes.

Tests capture logs/JSON/status output and recursively reject identifiers,
company/URL/DOM/narrative/amount/case/opponent/HMAC/key material. Browser network
assertions prove client telemetry remains zero for the Company Card document
through the intercepted Claims navigation boundary; they make no assertion
about a separately loaded generic Claims SPA.

Dashboard queries, SLOs and alerts are documented as P4 placeholders with STOP
semantics; no fake production monitor is claimed.

## 18. Stage 13 — initial/DR asset seed tooling

Keep normal install fail-closed on an absent stable root. Add a distinct seed
tool and wrapper; normal deploy must never call seed implicitly.

Seed input is exactly three prebuilt release directories/packages, each with
its Product manifest and complete assets. The manual seed-bundle workflow:

1. accepts the three full reviewed commit SHAs and manifest SHA-256 values from
   specification section 20.1;
2. checks out each SHA in an isolated directory;
3. runs `npm ci` and the dedicated build;
4. verifies built graph against that commit's tracked Product manifest;
5. packages all three manifests/assets plus a canonical inventory and hashes;
6. uploads a bounded non-secret artifact; it does not connect to production.

Seed tests in temp roots cover:

- correct oldest→newest current+2 initialization;
- wrong commit/manifest/source graph/hash;
- duplicate/collision/symlink/permissions/nonempty root;
- interruption at every pre-pointer phase;
- idempotent verify but non-idempotent accidental reseed;
- DR restore to a fresh root and exact loopback serving;
- select each retained manifest without deleting another.

Production execution remains P5 and separate authorization.

## 19. Stage 14 — atomic Web release and deploy workflow

### 19.1. Testable Web installer

Move destructive live-directory replacement out of inline workflow into a
strict script that:

- accepts exact release archive, SHA and approved root;
- extracts into a new SHA-named directory;
- verifies required files/hashes;
- fsyncs and atomically swaps a stable symlink/pointer;
- retains current + two predecessors;
- never follows/deletes an unapproved path;
- restores the previous pointer on failed post-switch smoke.

Unit tests use temp roots and verify every resolved path before any recursive
operation.

### 19.2. Manual exact-SHA deploy

Change `deploy_prod.yml` to manual only. Use the protected `production`
environment and exact lowercase 40-hex input. The workflow calls/reuses the QA
workflow with that value as its required `release_sha`, proves the commit is
reachable from protected `main` and refuses a mismatch. It consumes only the
QA-built SHA-named release artifacts and canonical QA attestation whose
verified SHA equals the dispatch input; it never rebuilds from caller/default
branch state. This permits an explicitly approved older-main release that
contains the compatible iteration-25 QA contract, without permitting an
arbitrary unmerged commit. Emergency rollback to a pre-contract release uses
only the separately recorded compatible image/pointers, not an unverified
rebuild of an old checkout.

Before QA/artifact use, fetch protected/default `main` and require all of:

- dispatch `github.ref == refs/heads/main`;
- workflow SHA/ref equals the fetched main head and names that head's exact
  `.github/workflows/deploy_prod.yml` blob;
- repository owner/name is the expected protected repository, not a fork;
- P1 supplies current external evidence that main requires `qa-required` and
  the `production` environment has the approved required reviewers.

These GitHub settings are not inferred from YAML. A stale/missing rule export,
wrong workflow ref or absent reviewer protection stops before artifact download.

Retain the whole-deploy mutex exactly as `group: prod-deploy` with
`cancel-in-progress: false`. A second manual run queues and cannot concurrently
touch asset/SPA pointers, the database or service images.

Deploy ordering:

1. download and reverify the Product, Gateway, SPA and H2 artifacts built once
   by reusable QA for the exact SHA;
2. read-only RU/US preflight and record compatible previous image/pointers;
3. install/verify H2 assets before DB/process replacement;
4. require successful drain/stop of report and narrative workers;
5. run Alembic upgrade head against the explicit approved DB only;
6. recreate RU Product and both workers from exact image, verify health/image;
7. recreate US Gateway from exact SHA image, verify health/image;
8. atomically switch SPA, reload nginx and smoke canonical/API/auth boundaries;
9. leave all H2 assignment/positive flags unchanged/off.

Failure after a replacement invokes the recorded compatible rollback for code/
pointers; schema remains additive. Any unsafe rollback condition stops and
reports exact phase rather than continuing mixed-version deployment.

Static workflow tests assert no `push: main`, no `origin/main` deployment, no
`|| true` around worker stop, one SHA everywhere, exact protected-main ancestry,
trusted current-main workflow ref, external protection STOP gates, the
non-cancelling `prod-deploy` mutex and `qa-required` dependency.

### 19.3. Testable worker drain

Move worker shutdown/predicate logic out of inline SSH into a strict adapter-
driven tool. P1 provides the deadline, which preflight must prove is not shorter
than configured shutdown grace and provider/Gateway timeout bounds. The tool:

1. records exact old report/narrative container and image IDs plus DB clock;
2. disables their restart policy and sends only `SIGTERM`, so claim/dispatch
   admission closes without a later automatic `SIGKILL`;
3. polls exact process IDs and aggregate DB predicates without printing job,
   report, subject or dispatch identifiers;
4. allows report `queued|succeeded|failed`, outbox
   `pending|processed|terminal`, narrative terminal/unleased states and
   reservation `released|consumed`; it requires report `running=0`, outbox
   `leased=0`, narrative active leased-state count `0`, runtime
   `leased_count=0` and reservation `reserved=0`;
5. requires committed-dispatch rows to be fenced terminal with consumed credit,
   no lease and exact fallback/artifact invariants; they are never retried;
6. repeats a stable snapshot before returning `drained`.

An expired lease may be handled only by the exact old compatible bounded
reconciler after both worker processes are gone and with provider/Gateway
network disabled. If no such path is available, or the deadline/process/state
predicate fails, the workflow stops before Alembic and does not escalate the
signal. Recovery uses the recorded old identities and a separately inspected
incident path.

Disposable tests cover idle, queued/pending, graceful completion, report lease
expiry, pre-dispatch reservation release, cancellation after the durable AI
dispatch marker, terminal ambiguous fallback, changing counts, a live process
at deadline and proof that Alembic/recreate were never invoked on failure.

## 20. Stage 15 — CI workflow

Create `.github/workflows/qa.yml` as both `pull_request` and `workflow_call`.
`workflow_call` requires one lowercase 40-hex `release_sha`; a PR run resolves
the same single value from `github.event.pull_request.head.sha`. A first
`resolve-release` job validates the value and emits it once. Every later job:

- checks out `needs.resolve-release.outputs.release_sha` explicitly and fails
  unless `git rev-parse HEAD` is byte-equal;
- includes the full SHA in every cache key, artifact name and result manifest;
- uses no cache restore-prefix that can cross a release SHA;
- never substitutes `github.sha`, a merge ref, default branch or caller HEAD;
- consumes only artifacts whose embedded SHA and checksum manifest match.

Resolve/pin all Action SHAs, exact runtime patches, the Docker BuildKit/buildx
tool image, the official Playwright container digest and the one PostgreSQL
image digest during implementation.

### Shared Python environment contract

Every Python-bearing job in QA, seed-bundle and deploy uses the checked-in
`.github/actions/setup-python-ci/action.yml`; a static workflow test rejects a
direct unconstrained `pip install`. The action selects one exact CPython patch
with an Action pinned by commit SHA, then runs this logical sequence:

```text
python -m pip install --no-deps --only-binary=:all: --require-hashes -r .github/ci/python-bootstrap.lock
assert exact pip/setuptools/wheel versions
python -m pip install --no-deps --only-binary=:all: --require-hashes -r .github/ci/python-test.lock
python -m pip install --no-deps --no-build-isolation -e services/product_api -e services/gateway_api
python -m pip check
python scripts/check-python-ci-lock.py --strict-environment
```

`python-bootstrap.lock` pins and hashes `pip`, `setuptools` and `wheel`.
`python-test.lock` contains the complete transitive Product, Gateway and test
closure with exact versions and accepted wheel hashes for the declared
platform; because `--no-deps` is used, pip performs no resolution. The checker
parses both `pyproject.toml` files, proves every declared requirement is
represented, rejects an sdist/unhashed/unpinned/extra distribution and permits
only the two exact local editable projects from the verified checkout. Lock
headers record Python/platform and the digest/version of the isolated resolver
used to regenerate them. A lock change is reviewed with its dependency diff;
it does not silently change dependency floors in either project.

`python-product-runtime.lock` and `python-gateway-runtime.lock` are strict
service-specific subsets of the tested closure. The checker requires every
shared distribution to use the same version and wheel hashes in all applicable
locks and rejects test-only, Product-only or Gateway-only leakage into the
wrong runtime image.

### Reproducible release-image contract

Both Dockerfiles replace floating `python:3.12-slim` and online editable
installs with a literal exact-patch base reference including its immutable
`sha256` digest. The sole `release-build` job:

1. uses the shared locked environment to build non-editable Product and Gateway
   project wheels from the verified checkout with `--no-deps` and
   `--no-build-isolation`, and records their SHA-256 values;
2. materializes separate Product/Gateway wheelhouses from the bootstrap plus
   matching runtime lock using `--require-hashes --only-binary=:all: --no-deps`;
3. verifies the wheelhouse inventory and then builds with `--network=none`;
   Dockerfiles use `--no-index --find-links`, `--no-deps` and the hashed locks,
   and never invoke a resolver, `pip --upgrade` or editable install;
4. copies only the exact local service wheel and required `shared` source,
   runs `pip check`, and emits a canonical installed-distribution manifest;
5. audits that manifest against the service runtime/bootstrap locks and local
   wheel hash, including absence of test/other-service packages;
6. smokes Product API, report/narrative worker entry points and Gateway in
   disposable/offline mode before accepting the OCI image digests;
7. writes base digest, lock/wheelhouse/local-wheel hashes, installed manifest,
   image config/OCI digest and release SHA into the release manifest.

The job also builds the SPA/H2 assets exactly once. It uploads SHA-named OCI
archives and Web/H2 packages plus the canonical release manifest. Browser,
release-contract and deploy jobs only verify and consume those artifacts; they
do not rebuild them. A double-build reproducibility check in disposable state
must produce the same installed manifests and OCI digests before the images
are eligible for `qa-attestation.json`; the pinned builder normalizes source/
OCI timestamps from the exact commit and emits provenance separately so wall
clock/run IDs cannot perturb the image digest.

### `python-unit-contract`

```powershell
python -m pytest services/product_api/tests_unit -q -ra --junitxml=...
python -m pytest services/gateway_api/tests -q -ra --junitxml=...
```

Fail before tests if any paid/provider/SMTP/arbitration key is nonempty or any
mandatory secret differs from its closed test placeholder; conftests may not
silently `pop` inherited credentials. The pre-import shared guard denies DNS/
socket escape, MockTransport remains mandatory, and negative tests prove raw
socket/stdlib/HTTPX cannot bypass it.

### `postgres-full`

Use one digest-pinned PostgreSQL 16 service and runner-created guard/roundtrip/
suite DBs. `browser-e2e-visual` uses that identical image digest. Run migration
contract, full `services/product_api/tests` and the JUnit checker. It fails
every skip/setup error/new failure; an unrelated origin/main failure is
accepted only when its exact node ID and normalized signature match the
reviewed baseline JSON. Never use repository `.env` or a public DB port.
The integration network guard allows only the runner-validated PostgreSQL
service endpoint plus loopback and rejects every other host/port.

### `web-static`

```powershell
npm ci --prefix services/web_ui
npm run lint --prefix services/web_ui
npm run test --prefix services/web_ui
```

### `release-build`

After the unit/static jobs succeed, run the sole immutable artifact producer:

```powershell
npm ci --prefix services/web_ui
npm run build --prefix services/web_ui
npm run check:company-public-h2-bundle --prefix services/web_ui
```

Then execute the offline service-image contract above and upload the exact
release artifacts/manifests. All later consumers depend on this job.

### `browser-e2e-visual`

Run in the matching digest-pinned official Playwright container, assert the
package/browser revision and committed font-inventory hash, connect to the
same digest-pinned PostgreSQL service, run the E2E harness with one visual
worker against the downloaded H2 release artifact and upload only SHA-named
failure artifacts. No OS/browser install or application rebuild runs inside
the job.

### `release-contract`

Download/reverify the sole producer's Product/Gateway OCI archives, SPA/H2
packages and canonical release manifest. Run image environment/smoke, nginx
release/seed/Web installer, mandatory
`deploy/product_api/test_worker_drain.py`, and exact workflow-order assertions
without a rebuild, then promote the same artifact identities to the
aggregator/deploy.

### `qa-required`

Require success from every job for the exact checked-out SHA. Cancelled/skipped
job is failure. Emit `verified_release_sha`, exact release artifact names and
hashes, and a canonical `qa-attestation.json` binding job conclusions, lock/
container digests, workflow run/attempt and release manifests to that SHA.
Deploy requires byte equality between dispatch input, this output, attestation,
artifact names/manifests and checked-out commit. Do not let deploy use the old
Product-only status.

## 21. Stage 16 — runbook and production decision gates

Create one runbook with exact commands and STOP conditions for:

1. separately authorized read-only DB/schema/job/assignment/asset/image/config preflight;
2. backup/restore verification;
3. seed verify and DR restore;
4. manual exact-SHA default-off deploy;
5. redacted effective-config verification after process recreation;
6. H2 precreation and staged/noindex smoke;
7. decision file creation, offline storage, digest approval and dry-run;
8. allowlist/percentage/indexable activation;
9. observation and abort decision;
10. H2 → H1 CAS rollback, then optional code-pointer rollback;
11. post-rollback canonical/sitemap/Claims/provider/AI/key-retention checks.

P8 commands use aggregate counts only. Secret deletion is eligible only after
zero nonterminal report job/lease/retry/outbox/reservation reference and proof
that every terminal stored masked projection verifies without secret bytes.
Reads, pin validation, rollback and rehearsal consume stored masked facts plus
nonsecret provenance and never reopen a retired secret. Deletion retains an
immutable key-ID/KMS-version tombstone; any read-time secret dependency is STOP,
not a reason to infer indefinite retention.

All P1–P9 values remain placeholders marked `UNSET/STOP`. The runbook may show
synthetic examples but never a real company, host secret, positive budget or
made-up threshold.

## 22. Stage 17 — targeted verification

Run after each owning stage:

```powershell
python -m pytest services/product_api/tests_unit/test_company_card_v2_rollout_decision.py services/product_api/tests_unit/test_company_card_v2_rollout_privacy.py -q -ra
python -m pytest services/product_api/tests_unit/test_company_card_v2_public_h2_activation.py services/product_api/tests_unit/test_company_report_public_assignment_sitemap.py -q -ra
pwsh -File scripts/run-iteration25-postgres-tests.ps1
npm run test --prefix services/web_ui -- src/companyPublicH2
npm run test:e2e:ci --prefix services/web_ui
python -m pytest deploy/nginx deploy/product_api deploy/web_ui -q -ra
pwsh -File deploy/nginx/test_product_api_conf.ps1
```

The PostgreSQL and browser runners must show owned loopback targets before work
and clean them in `finally`. They must never select an inherited URL on failure.

## 23. Stage 18 — complete regression and static checks

Mandatory final commands from repository root:

```powershell
python -m pytest services/product_api/tests_unit -q -ra
pwsh -File scripts/run-iteration25-postgres-tests.ps1
python -m pytest services/gateway_api/tests -q -ra
npm run lint --prefix services/web_ui
npm run test --prefix services/web_ui
npm run build --prefix services/web_ui
npm run test:e2e:ci --prefix services/web_ui
python -m pytest deploy/nginx deploy/product_api deploy/web_ui -q -ra
pwsh -File deploy/nginx/test_product_api_conf.ps1
git diff --check
```

Also run repository scans for:

- provider/Gateway/AI network entry from read/browser paths;
- forbidden production identifiers/raw payload/secrets;
- Webvisor/telemetry/service-worker code in H2 graph;
- untracked browser/DB/build artifacts;
- changed H1/historical fixture hashes;
- floating CI actions/images/runtimes;
- automatic production trigger or mixed SHA.

Do not claim Python lint/type-check; none is configured.

## 24. Baseline-failure policy

- A new failure, skip, setup error or timeout on an affected Company Card,
  Claims, release or browser surface is a blocker.
- An unrelated origin/main failure may be reported only when the exact node ID,
  normalized failure signature and environment match head; a count is
  insufficient.
- No baseline waiver may cover a migration, fixture setup, DB availability,
  network escape, privacy, assignment, canonical, Claims or browser gate.
- Unrelated fixes are not bundled; open a separate continuation.

## 25. Evidence outputs

After implementation, create/update:

```text
docs/development/evidence/iteration-25-company-card-v2/iteration-25-qa-evidence-v1.md
docs/development/evidence/iteration-25-company-card-v2/iteration-25-rollout-rehearsal-v1.md
```

They record:

- exact commit, runtime/browser/DB versions and commands;
- pass/fail/skip counts and JUnit artifact identities;
- profile/viewport/interaction matrix result;
- bundle/post-font zero-shift/visual baseline identities;
- H1/H2 immutable hash and CAS/rollback evidence;
- seed/DR/deploy rehearsal against temp/loopback state;
- baseline failures/limitations;
- confirmation that no live provider/AI/production action occurred.

No raw screenshots with production data, DB dumps, decision files, secrets or
unredacted logs are committed.

## 26. Independent review

After all checks, assign a reviewer who did not implement the change. Provide:

- Roadmap, AGENTS, proposed/approved decision register;
- full specification and plan;
- complete diff and migration;
- exact test/evidence outputs;
- baseline failure reconciliation;
- production authorization matrix P1–P9.

Reviewer must explicitly examine:

1. iteration-24 prerequisite closure and scope ownership;
2. legacy H1/H2 compatibility;
3. pin scope/digest immutability and indexability;
4. CAS/idempotency/race/rollback semantics;
5. sitemap/canonical/Claims parity;
6. browser/visual/a11y/performance determinism;
7. privacy/network/paid-call absence;
8. migration/down guard;
9. asset seed/DR/deploy exact-SHA and rollback;
10. off defaults and absence of production authorization.

Only `VERDICT: READY` with no blocker permits the owner to request commit/push.
It still does not authorize merge or production action.

## 27. Stop conditions

Stop implementation and return for direction if any of these occurs:

- iteration-20/24 accepted prerequisite behavior cannot be reproduced or
  regresses;
- a required old unit/component/contract gap is discovered;
- H1 byte/semantic compatibility requires change;
- indexable H2 cannot be represented additively without rewriting pins;
- rollback needs migration downgrade or implicit latest selection;
- a public assignment endpoint or browser-selected cohort becomes necessary;
- a third production/test dependency becomes necessary;
- deterministic visual/post-font zero-shift gate requires hiding factual content;
- seed needs deleting/replacing an existing root;
- production values/credentials are needed to complete default-off QA;
- any command would touch production without a new explicit authorization.
