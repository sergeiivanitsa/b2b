# Iteration 25 baseline audit v1

Artifact ID: `company_card_v2_iteration_25_baseline_audit_v1`

Initial audit date: `2026-08-27`

Refresh date: `2026-08-28`

Initial audited repository base:
`886f207d945e35acc1a7e5c07dcff8c36e501bf6`

Refreshed implementation planning base:
`31b299ac88b5fac7d5c04082324fb122d63db7e7`

Refresh branch: `codex/iteration-25-company-card-v2-qa-rollout-refresh`

State: `REFRESHED PLANNING EVIDENCE — INDEPENDENT REVIEW APPROVED`

Initial planning-audit review: `APPROVED 2026-08-27` for the historical base
only. Refreshed plan review round 1: `CHANGES_REQUIRED 2026-08-28`.
Correction review: `CHANGES_REQUIRED 2026-08-28` because the proposed
iteration-25 rerun initially retained an iteration-24 `head == 0018`
assumption. Forward-head amendment reviews: `APPROVED 2026-08-28` by the
architecture and evidence reviewers, with no remaining actionable findings.

## 1. Audit boundary

This artifact records repository, GitHub Actions and local Stage 0 state used
to plan iteration 25. The refreshed audit did not call DataNewton, FNS,
Gateway runtime or paid AI, did not access a production or unknown database
and did not change a production flag, assignment or release. Docker was used
only by the reviewed iteration-20/24 runners, which create unique loopback-only
tmpfs PostgreSQL containers and remove their exact owned labels.

Current production database, runtime flags, secret registry and deployed
image state remain unknown. They may be inspected only by a separately
authorized read-only production preflight.

## 2. Lifecycle and prerequisite state

- Iterations 19–24 are merged into `origin/main`.
- PR `#150` (`604bf6deeea453187841bdf454f8dfc0c390d72d`) closed the
  iteration-20 presentation-create lifecycle/query contract debt.
- PR `#151` (`557244b69c5bf54bba6ae07bfd5a39638ff14f18`) reconciled that
  continuation into Roadmap and DevFlow.
- PR `#152` (`31b299ac88b5fac7d5c04082324fb122d63db7e7`) merged the
  iteration-24 PostgreSQL acceptance evidence and removed only that debt.
- The bounded delta from `886f207...` to `31b299ac...` contains those three
  squash merges. It changes no Gateway/Web tree, GitHub workflow, deploy tree
  or Alembic revision.
- The old dirty planning worktree remains untouched. This refresh was created
  as a new clean branch/worktree from exact `origin/main`.
- Iteration 25 must not absorb a later missing unit, component or contract
  matrix from iterations 20–24. Such a finding remains a separate prerequisite
  or continuation.

The historical 2026-08-27 Docker preflight failure remains part of the initial
audit chronology. It was superseded on 2026-08-28 by the clean Stage 0 runs
below; it did not touch a database.

## 3. Existing automated-test inventory

The repository already contains substantial lower-layer coverage:

| Surface | Audited inventory | Current CI use |
|---|---:|---|
| Product API unit | 126 files, 976 `test_*` functions | yes |
| Product API PostgreSQL integration | 37 files, 204 functions | no |
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

### 3.1. Refreshed Stage 0 execution

The exact refresh environment was Python `3.12.2`, Node `24.13.1`, npm
`11.8.0`, PowerShell `7.6.4`, Docker Engine `29.1.3` and local image
`postgres:16-alpine` ID
`sha256:23e88eb049fd5d54894d70100df61d38a49ed97909263f79d4ff4c30a5d5fca2`.
Inherited database/provider/AI variables and repository/Product `.env` files
were absent.

| Gate | Refreshed result |
|---|---|
| Frozen iteration-20 lifecycle/OpenAPI subset | `50 passed, 4 warnings in 1.41s` |
| Product API unit | `1524 passed, 4 warnings in 68.40s` |
| Gateway API | `31 passed, 29 warnings in 0.34s` |
| Web lint | exit `0` |
| Web unit/component | `50 files / 496 tests passed in 75.90s` |
| Web type-check + SPA/H2 build + manifest verify | exit `0` |
| H2 release tests | `34 passed in 20.70s` |
| nginx SEO routing contract | passed |
| Iteration-24 migration module | `2 passed, 24 warnings in 16.53s` |
| Iteration-24 affected nine-file integration suite | `79 passed, 22 warnings in 50.08s` |
| Iteration-20 PostgreSQL Targeted | `117 passed, 50 warnings in 67.85s`; failures/errors/skips `0/0/0` |
| Iteration-20 PostgreSQL Full | `290 passed, 165 warnings in 195.27s`; failures/errors/skips `0/0/0` |

Targeted JUnit SHA-256 is
`a76e3a475d5904f892d553f6bb4ecf27679c6063c802f13dbb66b17960787137`;
Full JUnit SHA-256 is
`bf5d8f8eb779b218e75a9631b2c8d4a4a8f174d35a9c7dbb9e314c24cbe97c98`.
Both disposable label namespaces were empty before, between and after runs;
Docker remained available. The first sandboxed Web test attempt stopped before
test collection with local esbuild `spawn EPERM`; the same command passed once
that local subprocess was permitted. This is environment reconciliation, not a
waived test failure.

The iteration-24 counts above are exact point-in-time console results and show
no skips in those executions. Review nevertheless found that the current
runner enforces only pytest exit codes, which are also zero for an all-skipped
phase. It therefore requires a separate JUnit-based no-skip hardening
gate before the same phases can be implementation acceptance evidence. The
historical runner script remains unchanged and is not reused as that gate; the planned
iteration-25 runner/checker owns the distinct nonzero/zero-failure/error/skip
JUnit proof. Because `0019` becomes new `head`, its forward-compatible phase
will keep every old migration assertion but replace the old test's two generic
`head` aliases with explicit `0018`, then upgrade that roundtrip DB to verified
`0019/head` before the affected phase. Iteration-20 Targeted/Full were already
machine-reconciled from JUnit.

`npm ci --prefix services/web_ui` completed from the unchanged lockfile (Git
blob `9a667e6da9d188c6288593f085cbc8a4fd2b93c1`) and its 2026-08-28 online
advisory summary reported `16` findings: `2 low`, `1 moderate`, `12 high`, `1
critical`. This is a point-in-time registry observation, not an immutable
property of the lockfile. At `2026-08-28T12:48:05+10:00`,
`npm audit --json --package-lock-only --prefix services/web_ui` with npm
`11.8.0` against `https://registry.npmjs.org/` returned zero findings for the
same lock. No automatic audit fix or dependency change was made. The SPA main
chunk remained
`591.35 kB / 176.27 kB gzip`; the H2 entry remained
`307.79 kB / 92.11 kB gzip`. The existing Vite `>500 kB` warning remains a
baseline finding, not an invented performance budget.

### 3.2. Immutable base identities

Each file hash below is SHA-256 over its raw bytes in this refreshed Windows
working tree; checkout bytes, including line endings, are part of the identity:

| Surface | Path | SHA-256 |
|---|---|---|
| H1 Product JSON | `services/product_api/tests_unit/fixtures/company_reports/public_h1_v1_expected.json` | `bc3ad0398855883f6619b92b705a1466fe3fd3286192a9fdc501d91dba9238d9` |
| H1 Web published JSON | `services/web_ui/src/companyReport/fixtures/company-public-h1-published.json` | `5b5c61260400105da0350f21e278293c5eb542b3d0ded8354d03687dbc5a337f` |
| H1 Web latest-unpublished JSON | `services/web_ui/src/companyReport/fixtures/company-public-h1-latest-unpublished.json` | `e43b532e26a8b4ed8443a0ef4a1dc9d147d0ba0fa51ecd3b943135597986a372` |
| H1 Web SSR HTML | `services/web_ui/src/companyReport/fixtures/company-public-h1-published-ssr.html` | `da0168b7666a9f5090c6e2e71005082a96415fb504ba218388b1e986b047c8aa` |
| H2 public V1 | `services/product_api/tests_unit/fixtures/company_card_v2/public_h2_v1_expected.json` | `43aafa40f173153a5613b8f103e11fadedc8c0dde4b602625de27098a77b8d75` |
| H2 public V2 | `services/product_api/tests_unit/fixtures/company_card_v2/public_h2_v2_expected.json` | `e57002e89b54097abdb390b5b5148ab7ace1d5459ec8bc8dde34c71d9998d59f` |
| H2 public V3 | `services/product_api/tests_unit/fixtures/company_card_v2/public_h2_v3_expected.json` | `7a9f1ae937e818099c5826880bb3ffde9488f6ec2340ada0ac680593f1a14bfc` |
| H2 asset manifest | `services/product_api/src/product_api/company_reports/company_card_v2/public_h2_asset_manifest.json` | `97a76daefbb73e1b78935916516fa093f3db5027e09ea44f52df6f63ac18222b` |
| Iteration-22 matrix | `scripts/run-iteration22-company-public-h2-browser-matrix.mjs` | `f378deb4b53f68b61b0921bf5a6fd53fb6500c335f7c7137110d734390e5d412` |
| Iteration-22 probe | `scripts/iteration22-company-public-h2-browser-probe.mjs` | `d3b24d4f597250b7db6e0c7601a60c48c990bf9f2986224df3d4f7be9e283068` |
| Iteration-22 fixture server | `scripts/serve-iteration22-company-public-h2-fixture.py` | `f0b8a35f22d14df4ab68d43f6d9972ef4473798e25f0d2d9cdf1a1336a13795d` |

The 20 migration files through `0018`, including the historical merge-head
revision, have refreshed-working-tree aggregate SHA-256
`e59c274144846827a57dca6063e452179bcf96a74a57a5414a784ced9df90a58`.
Paths use repository-relative `/` separators and are sorted by their UTF-8 byte
sequence. For each file the hash receives `UTF8(path) + 0x00 + raw working-tree
bytes + 0x00`. The previously recorded `1d0ac464...` is the result for ASCII
backslash/zero separators and does not satisfy this NUL-byte algorithm.

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

Historical iteration-23/24 runs remain evidence for one exact pre-migration
failure mode:

- [iteration 23 deploy run #148](https://github.com/sergeiivanitsa/b2b/actions/runs/33023177576);
- [iteration 24 deploy run #149](https://github.com/sergeiivanitsa/b2b/actions/runs/33032702531).

Those two runs built the Web UI and candidate Product image, uploaded the H2
package and stopped at:

```text
stable root missing or symlinked; seed runbook required
```

They did not reach report-worker stop, Alembic, Product replacement, US deploy
or SPA replacement. This does not prove the current production database state,
which remains unknown.

The refreshed PR `#150–#152` main runs all passed the only configured Product
unit job and all failed the automatic production workflow:

| PR | Main Product unit | Automatic deploy |
|---|---|---|
| `#150` | [run `33067512591`](https://github.com/sergeiivanitsa/b2b/actions/runs/33067512591), `1524 passed` | [run `33067512575`](https://github.com/sergeiivanitsa/b2b/actions/runs/33067512575), failed |
| `#151` | [run `33069727446`](https://github.com/sergeiivanitsa/b2b/actions/runs/33069727446), `1524 passed` | [run `33069727527`](https://github.com/sergeiivanitsa/b2b/actions/runs/33069727527), failed |
| `#152` | [run `33130746907`](https://github.com/sergeiivanitsa/b2b/actions/runs/33130746907), `1524 passed` | [run `33130746922`](https://github.com/sergeiivanitsa/b2b/actions/runs/33130746922), failed |

For all three deploy runs the public job state shows Web build/H2 upload
success, `Deploy RU` failure and skipped US/SPA deploys. Public log download
returned `403`, so this evidence does not assign the historical stable-root
message to these newer runs and does not claim whether they reached Alembic or
process replacement.

The active default-branch ruleset currently requires strict
`product_api_unit_tests` only, requires `0` approving reviews and enables
review-thread resolution. GitHub reports no configured environments. This is
insufficient P1 evidence: `qa-required`, a protected production environment,
required production reviewers and exact release/window/drain values remain
absent or unset.

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
- immutable release SHA/window/drain timeout; current main requires only the
  Product unit status, while a protected production environment and required
  production reviewers are absent;
- DataNewton operation mode;
- AI model, positive credits/concurrency, monetary ceiling and paid smoke;
- arbitration mask active key ID, immutable secret-version binding and old-key retention;
- initial/DR asset seed authority and retained release/image set;
- final indexability/GA decision.

No implementation plan may manufacture these values.
