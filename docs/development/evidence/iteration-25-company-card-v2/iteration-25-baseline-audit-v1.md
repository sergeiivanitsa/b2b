# Iteration 25 baseline audit v1

Artifact ID: `company_card_v2_iteration_25_baseline_audit_v1`

Audit date: `2026-08-27`

Audited repository base: `886f207d945e35acc1a7e5c07dcff8c36e501bf6`

Implementation base: NOT ESTABLISHED — this evidence must be regenerated from
the exact post-prerequisite `origin/main`.

Planning branch: `codex/iteration-25-company-card-v2-qa-rollout`

State: `REVIEWED PLANNING EVIDENCE — NO RUNTIME OR PRODUCTION ACTION`

Planning-audit review: `APPROVED 2026-08-27`; implementation still requires
regenerated evidence and repeat review on the exact post-prerequisite base.

## 1. Audit boundary

This artifact records repository and GitHub Actions state used to plan
iteration 25. The audit was read-only. It did not call DataNewton, FNS,
Gateway or paid AI, did not start Docker, did not access a production
database and did not change a production flag, assignment or release.

Current production database, runtime flags, secret registry and deployed
image state remain unknown. They may be inspected only by a separately
authorized read-only production preflight.

## 2. Lifecycle and prerequisite state

- Iterations 19–24 are merged into `origin/main`.
- Iteration 24 is recorded as merged with one acceptance debt: its exact
  disposable PostgreSQL runner has not passed after merge because the local
  Docker Desktop daemon is unavailable.
- The runner is `scripts/run-iteration24-postgres-tests.ps1`. It owns a
  loopback-only tmpfs PostgreSQL container, refuses inherited database URLs,
  never pulls an image and cannot fall back to another database.
- Iteration 25 planning may continue, but no production-code change may begin
  until that runner succeeds and its result is reconciled into Roadmap and
  `DEVFLOW_STATE.yaml`.

Independent static contract review also confirmed a separate iteration-20
debt on the merged base: the presentation-create route accepts query input and
does not return the frozen complete `PresentationLifecycle`. It must be fixed
and merged as an iteration-20 continuation. This planning branch is then left
untouched; a new clean implementation branch/worktree must start at the exact
new `origin/main`, regenerate this evidence and repeat bounded delta audit plus
plan review before iteration-25 code. No automatic rebase/reset is authorized;
the debt is not rollout scope.
- Iteration 25 must not absorb a missing unit, component or contract matrix
  from iterations 20–24. Such a finding is a separate prerequisite or
  continuation.

Local Docker preflight on 2026-08-27 failed before container creation because
`dockerDesktopLinuxEngine` was unavailable. No database was touched.

## 3. Existing automated-test inventory

The repository already contains substantial lower-layer coverage:

| Surface | Audited inventory | Current CI use |
|---|---:|---|
| Product API unit | 125 files, 967 `test_*` functions | yes |
| Product API PostgreSQL integration | 37 files, 198 functions | no |
| Gateway API | 4 files, 22 functions | no |
| Web UI | 50 files, 342 `it/test` cases | no |
| H2 Web UI subset | 13 files, 107 tests | no |
| H1 company-report Web UI subset | 3 files, 42 tests | no |
| H2 release/nginx | strict release CLI tests and nginx contract checks | deploy build only; tests no |

`npm run build --prefix services/web_ui` already performs TypeScript checking,
the SPA build, the dedicated H2 build and tracked H2 manifest verification.
The tracked H2 manifest has one entry JS, one CSS and three lazy JS chunks.

Current CI is only `.github/workflows/product_api_unit_tests.yml`: Python
3.12, editable Product API test install and the Product API unit suite. It
does not run Gateway, PostgreSQL integration, frontend lint/test, real-browser,
release, nginx, no-skip, bundle or layout-shift gates.

Both Python projects declare dependency floors with `>=`, and the repository
has no Python lock/hashed constraints surface. Therefore the current editable
CI install can resolve a different transitive environment over time; exact
Python/action versions alone do not make its result reproducible.

## 4. Existing real-browser evidence

Iteration 22 supplied a no-download raw-CDP harness:

- `scripts/run-iteration22-company-public-h2-browser-matrix.mjs`;
- `scripts/iteration22-company-public-h2-browser-probe.mjs`;
- `scripts/serve-iteration22-company-public-h2-fixture.py`.

It exercises five sanitized profiles at the required seven widths
`320/390/768/1024/1199/1200/1440`, records 35 screenshots and JSON results,
checks factual SSR before takeover, SSR/React parity, overflow/overlap, CTA
placement, keyboard behavior, selected 200% zoom and reduced-motion cases,
loopback-only network and console/runtime errors.

It remains useful historical evidence and a source of assertion semantics, but
it is not sufficient as the iteration-25 gate because it:

- discovers only Windows Chrome/Edge and is not attached to package scripts or CI;
- uses an in-memory fixture server rather than PostgreSQL → Product API → HTTP;
- has no real touch context or non-zero safe-area scenario;
- asserts that lazy chart art is absent and therefore does not cover F1–F5/A1–A5;
- has no large-N, lazy-chunk-failure, crawler/robots/wrong-slug matrix;
- captures PNG files without a deterministic golden comparison;
- does not measure layout shifts or initial/lazy bundle closure.

The historical harness must not be rewritten to make past evidence mean
something new. Iteration 25 should create a new harness and may reuse its pure
assertion ideas.

The generic SPA `index.html` loads Yandex Metrika with Webvisor, including the
Claims destination. Therefore a Company Card zero-telemetry test can prove the
exact full-navigation request but must intercept before loading the unrelated
destination SPA unless telemetry scope is separately changed.

## 5. Browser-tool decision input

| Option | Benefits | Costs/risks |
|---|---|---|
| Extend raw CDP | no browser-test dependency; preserves the existing style | bespoke Linux discovery, touch, tracing, network interception and visual diff; browser/fonts remain weakly pinned |
| Playwright Test | lock-bound browser revision, portable Chromium, touch/reduced-motion emulation, network interception, traces and screenshot comparisons | dev-only npm dependency, browser download/cache and committed visual baselines |

The audit recommends dev-only `@playwright/test` for the new cross-layer gate.
`@axe-core/playwright` may be added as a second dev-only dependency for a
repeatable automated accessibility scan; it does not replace keyboard/touch
checks. Neither package is allowed into the production H2 bundle.

## 6. Deployment and release audit

`.github/workflows/deploy_prod.yml` currently runs automatically for every
push to `main`. It does not wait for the missing QA matrix and has no manual
production environment approval.

Safety gaps found in the current workflow:

1. RU uses the workflow SHA while US resets to then-current `origin/main`, so
   a queued deployment can mix releases.
2. Product report-worker stop errors are ignored and the narrative worker is
   not drained, stopped or verified.
3. The live SPA directory is cleared and refilled non-atomically, without a
   retained previous pointer.
4. There is no complete cross-service automatic rollback after a later phase
   fails.
5. The deploy job builds Web UI but does not run lint, tests, browser or
   release-contract gates.
6. Product and Gateway Dockerfiles use floating `python:3.12-slim`, online
   `pip --upgrade` and unconstrained editable installs, so a tested host
   environment does not prove the dependencies in a deployed image.
7. Worker shutdown ignores report-worker failure, omits the narrative worker
   and has no lifecycle/lease/reservation predicate before Alembic.

The H2 asset installer itself is deliberately strict: it verifies the
candidate Product manifest, source graph, stored bytes, loopback HTTPS/SNI
responses and an immutable `current + two predecessors` manifest set before
migration or Product replacement. A fresh or incomplete stable root fails
closed until a separately authorized seed procedure is performed.

No initial/DR seed command or rehearsal evidence exists. Asset retention also
does not by itself prove that matching Product/Gateway/Web images are retained.

## 7. Recent GitHub Actions evidence

The two most recent merged Company Card runs had successful Product API unit
jobs and failed production deployment jobs:

- [iteration 23 deploy run #148](https://github.com/sergeiivanitsa/b2b/actions/runs/33023177576);
- [iteration 24 deploy run #149](https://github.com/sergeiivanitsa/b2b/actions/runs/33032702531).

Both deployment runs built the Web UI and candidate Product image, uploaded
the H2 package and then stopped at the same pre-migration release gate:

```text
stable root missing or symlinked; seed runbook required
```

The workflow did not reach report-worker stop, Alembic, Product replacement,
US deployment or SPA replacement. Therefore these runs did not apply
migration `0018`. This does **not** prove the production database is still at
the prior revision: a manual change is possible, so its state remains unknown.

The iteration-24 deploy log recorded the following non-gating baseline:

```text
SPA main chunk: 591.35 kB minified / 176.27 kB gzip
H2 entry chunk: 307.79 kB minified / 92.11 kB gzip
Vite: existing >500 kB warning
npm audit: 16 existing findings (2 low, 1 moderate, 12 high, 1 critical)
```

These are baseline observations, not invented iteration-25 budgets and not an
authorization to expand scope into unrelated dependency remediation. Any new
test dependency must be attributed and must not enter the production bundle.

## 8. Rollout-control findings

Existing strong controls:

- all H2 writer/presentation, arbitration and AI runtime defaults are off;
- rollout generation, allowlist and basis points are validated fail-closed;
- non-allowlisted cohort selection uses the frozen sticky SHA-256 bucket;
- immutable H1/H2 pins, staged H2 pointer and assignment journal already exist;
- canonical document selection is server-authoritative and one joined read;
- H2 reads do not invoke provider, Gateway, AI or writes;
- H2 assets are content-addressed and Product validates its packaged manifest.

Missing iteration-25 controls:

- `assign_pin_cas` intentionally rejects H2 and incorrectly couples target pin
  generation to assignment generation for a general switch/rollback API;
- H2 pins are currently resolved but staged/noindex only;
- there is no operator-only dry-run/apply/rollback tool, decision digest or
  privacy-safe status summary;
- closing a runtime flag does not revert durable H2 assignments;
- sitemap reads only active H1 publication rows and currently materializes the
  complete publication set before index/chunk slicing;
- there is no separately tested H2 indexability predicate;
- there is no global rehearsal of H1 → H2 → H1 canonical and Claims continuity.

## 9. Open activation inputs

The following are intentionally `UNSET` and block production action, not
default-off implementation or disposable rehearsal:

- production rollout generation, allowlist and percentage ladder;
- maximum batch size, observation windows, SLO/abort thresholds;
- production database backup/restore and migration approval;
- immutable release SHA/window/drain timeout plus current protected-main status
  and protected-environment required-reviewer evidence;
- DataNewton operation mode;
- AI model, positive credits/concurrency, monetary ceiling and paid smoke;
- arbitration mask active key ID, immutable secret-version binding and old-key retention;
- initial/DR asset seed authority and retained release/image set;
- final indexability/GA decision.

No implementation plan may manufacture these values.
