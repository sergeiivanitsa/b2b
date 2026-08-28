# Iteration 25 QA evidence v1

Artifact ID: `company_card_v2_iteration_25_qa_evidence_v1`

Evidence date: `2026-08-28`

Branch: `codex/iteration-25-company-card-v2-qa-rollout-refresh`

Candidate base commit: `31b299ac88b5fac7d5c04082324fb122d63db7e7`

State: `PASS — LOCAL CANDIDATE QA COMPLETE; NON-PRODUCTION / NOT AN ATTESTATION`

This file describes the implementation candidate in the shared dirty worktree
based on the commit above. It is not a `qa-required` attestation and does not
claim a final implementation commit before one exists. `PASS` here means the
recorded local/disposable candidate checks completed; it is not a GitHub
`qa-required` attestation, release authorization or production approval.

## 1. Boundary

All recorded commands used repository, disposable temp roots, loopback
listeners and runner-owned Docker containers only. No production/unknown DB,
SSH target, provider, Gateway paid operation, OpenAI/AI operation, assignment,
positive flag, H2 production seed, production migration or deploy was used.
No raw identifier, secret, DB dump or production screenshot is stored here.

Production authorization remains absent. P1 is
`PARTIAL / INSUFFICIENT`; P2–P9 are `UNSET/STOP`. Repository examples keep
provider/presentations/writer/arbitration collection/narrative disabled,
narrative kill-switched with zero credits/concurrency, rollout generation and
percentage at zero, allowlist empty, and P8 key variables truly unset.

## 2. Frozen CI/release identities

| Surface | Exact identity |
|---|---|
| CPython | `3.12.11`, Linux x86_64 manylinux2014 locks |
| Node build | `22.17.1` |
| Playwright container Node | `24.18.1` |
| PostgreSQL | `postgres:16.9-alpine@sha256:b441677c946de564fe88ae4245ba80fe84a69485b22bf560e9c7c3710cd5e21d` |
| Playwright amd64 | `mcr.microsoft.com/playwright:v1.62.1-noble@sha256:c091b21d9fae78c76e85cd4356431e9b018402f172a214fc7d7a5e9a7e29d8ac` |
| Playwright OCI index | `sha256:dcc5531e97840b9b5e794f2814476b21571c5124a3fca2267d73041f56e7580e` |
| Playwright package / Chromium | `1.62.1`; revision `1234`; `151.0.7922.34` |
| Normalized font inventory | `705c330e71882ba9b680add251004054dcdc680b5c646e814b5b5ea2b6b341b3` |
| Python base | `python:3.12.11-slim-bookworm@sha256:c00fc7b44d844b6da22861ec24af43968a5200eac4ec607b4725d585165d6b49` |
| Docker Buildx | `v0.25.0` |
| BuildKit | `moby/buildkit:v0.23.2@sha256:e39f6119f134b4811af19fd5c20f495a6a264a85c1b6920daf569b23009dd42c` |

The tracked font-inventory file SHA-256 is
`0182aceb33fb643f8ee8522357511b18c44a10f4f9252231d20093e0dee2fad1`.
The candidate Product H2 manifest SHA-256 is
`3b9f28de6c4c61087de887cf9a9c217fb933a3fa8714acb6b50b3722aca93b12`;
the npm lock SHA-256 is
`d3995d2c7f9f0a02d1cb8f73dc41285717e6b9eeda9a96cc6edb573743af982f`.

## 3. Completed checks

| Gate | Exact local result |
|---|---|
| Product unit | `1626 passed, 4 warnings in 35.36s` (root-owned final run after crawler linkage, sitemap and manifest/golden corrections) |
| Gateway | `31 passed, 29 warnings in 0.31s` (root-owned final targeted run) |
| Web lint | exit `0` in `10.68s` |
| Web Vitest | `52` files / `503` tests passed; Vitest `21.81s`, wall `23.77s` |
| Web build | exit `0` in `16.11s`; TypeScript, SPA, H2 and Product-manifest verification clean |
| Web bundle contract | exact eager/lazy closure and budget verification passed |
| Release/nginx/seed/drain/Web tooling | `95 passed in 20.52s`; `deploy/nginx=42`, `deploy/product_api=39`, `deploy/web_ui=14`; failures/errors/skips `0/0/0` |
| Python lock graph | `{"bootstrap":3,"gateway":23,"product":32,"test":38}` |
| Workflow/action YAML parse | four workflow files plus the composite action parsed to mapping roots |
| Product/Gateway Compose parse | both `docker compose ... config --no-interpolate --quiet` commands exited `0` |
| nginx routing contract | `nginx product API SEO routing contract passed` |
| diff whitespace | `git diff --check` exited `0`; Windows emitted informational CRLF conversion notices only |

Python regression commands:

```powershell
python -m pytest services/product_api/tests_unit -q
python -m pytest services/gateway_api/tests -q
```

Web regression commands:

```powershell
npm run lint --prefix services/web_ui
npm run test --prefix services/web_ui
npm run build --prefix services/web_ui
npm run check:company-public-h2-bundle --prefix services/web_ui
```

Tooling command:

```powershell
python -m pytest deploy/nginx deploy/product_api deploy/web_ui -q -ra -p no:cacheprovider
```

The exact `95`-test breakdown was independently enumerated with
`--collect-only`: `42 + 39 + 14`. It supersedes the earlier 91-test snapshot.

The lock checker rejects noncanonical headers, markers, sdists/unhashed or
unpinned rows, duplicate/unsorted rows, cross-lock version/hash drift, and any
change to the audited Product/Gateway/test closures. Release installed-package
manifests must equal bootstrap + the one service closure + its exact local
wheel, with no other service/test package.

## 4. PostgreSQL acceptance

The final frozen-tree serialized runner command exited `0`:

```powershell
pwsh -NoProfile -File scripts/run-iteration25-postgres-tests.ps1 -Mode PostgresFull
```

It used
`postgres:16.9-alpine@sha256:b441677c946de564fe88ae4245ba80fe84a69485b22bf560e9c7c3710cd5e21d`
with `--platform linux/amd64 --pull=never`. The runner first exercised the
preserved iteration-24 contract at exact `0018`, upgraded the same roundtrip
database to verified exact head `0019`, and only then ran the affected-head
suite.

| Phase | Pytest/JUnit result | Duration | JUnit file | JUnit SHA-256 |
|---|---:|---:|---|---|
| `exact-0018` | tests/failures/errors/skips `2/0/0/0` | `9.31s` | `exact-0018.xml` | `e59bd1d7af50e8d51ba3828aedd9893c28602df1e4f1f3f0c88c7ba08aa5ba70` |
| `affected-head` | tests/failures/errors/skips `313/0/0/0` | `234.95s` | `affected-head.xml` | `a56bf6aa68d1815e1cb63df0d758073c444e17b4138e4d731b5045c8458b632d` |

The strict checker reported clean nonzero JUnit for both phases. Runner
status was `PASS ... junit=clean ... cleanup=confirmed`; after exact-ID cleanup,
`docker ps -aq --no-trunc --filter
label=com.b2b.iteration25.disposable=true` was empty. The runner also scoped
every owned container by exact run ID and role; no external PostgreSQL URL or
repository `.env` was accepted.

Independent review found and closed an earlier H1→H2→H1 evidence gap. The
accepted node hashes full subject-scoped report, pin and narrative-artifact
JSON rows in deterministic primary-key order, proves all three collections
nonempty and requires byte equality before/after while only assignment/journal
may grow. Its targeted proof was `1 passed in 5.30s`; the final affected-head
JUnit above includes that strengthened node.

## 5. Browser, accessibility, visual and performance acceptance

The exact baseline-update command was:

```powershell
pwsh -NoProfile -File scripts/run-iteration25-postgres-tests.ps1 -Mode BrowserE2E -ReleaseArtifactRoot 'C:\GPT\.worktrees\iteration-25-company-card-v2-qa-rollout-refresh\.release\artifacts' -PlaywrightImage 'mcr.microsoft.com/playwright:v1.62.1-noble@sha256:c091b21d9fae78c76e85cd4356431e9b018402f172a214fc7d7a5e9a7e29d8ac' -FontInventory 'C:\GPT\.worktrees\iteration-25-company-card-v2-qa-rollout-refresh\.github\ci\playwright-font-inventory.sha256' -ReleaseSha '31b299ac88b5fac7d5c04082324fb122d63db7e7' -UpdateSnapshots
```

The distinct strict comparison used the same command without
`-UpdateSnapshots`. Both consumed canonical disposable release-manifest
SHA-256 `3678b52145aa94d854660ef7f7f9a7b0828f0c079295c8741b9863644637196c`.

| Browser phase | tests/failures/errors/skips | Duration | JUnit SHA-256 | Cleanup |
|---|---:|---:|---|---|
| baseline update | `97/0/0/0` | `7.8m` | `5c86694e603bc5efc657e5aa0f81e80133cd4f12c432dca32a6bc4d40aea842b` | confirmed |
| strict compare | `97/0/0/0` | `7.8m` | `9c851296b946a59a922a9d337447de385b2f74d2ed0c7ffb4e7792e9600b6e2f` | confirmed |

The 97-test closed matrix was: `28` core visual cells (four profiles × seven
widths), `7` lazy-failure widths, `12` keyboard/focus, `8` real-touch, `12`
200% reflow, `10` reduced-motion, `2` nonzero safe-area, `4` JavaScript-off,
`2` axe/semantic and `1` canonical/crawler/Claims test, plus `11` fail-closed
manifest/proxy/relay/stack contract tests. All `35` core/lazy cells returned an
empty post-font layout-shift ledger. Four axe scans (SSR and enhanced at mobile
and desktop) had zero violations; no allowlist or rule disable was used.

Exactly 28 full-page PNG baselines were produced (four profiles × seven
widths), all byte-distinct and visually reviewed with no clipping, empty tail
or external data. Their reproducible inventory identity is SHA-256
`ae6e06947267b0c7cc265a22df3288f02790c06a31ebbecf9e50e296d80609e6`
over bytewise filename-sorted ASCII records
`name<TAB>lower_sha256<LF>`.

The bundle gate fixed the eager closure to entry `BpRKylUz` plus CSS
`CJwgWpoy` (`314,079` raw / `93,549` gzip approved bound), finance lazy closure
to shared `CWjjw1Pe` + `yIMa9GAq`, and arbitration lazy closure to shared
`CWjjw1Pe` + `DD5Vc9W2`. The reviewed generated H2 Vite manifest SHA-256
recorded by the canonical budget file's `manifest_sha256` field is
`e4800328189d5ed619932898edfce0635cb183b98a036482f3e5bd3a678e19c6`;
the tracked `company-public-h2-bundle-budget.json` file SHA-256 is
`dd60be22ea3b6dfcac81cc2a616d5fabbf25d368d29184944e8868048f79653a`.
Navigation/resource timing diagnostics were attached for all 28 visual cells;
they are diagnostic only and are not promoted to an SLO without P4.

The browser contract is fail-closed: the runner creates an absolute JSON
profile manifest and an explicit IPv4-loopback base URL, holds PostgreSQL,
Product and the same-origin proxy, and runs Playwright in the pinned container.
There is no external/default E2E URL and the workflow does not install or
rebuild inside the browser job.

## 6. CI and release result

`.github/workflows/qa.yml` resolves one lowercase 40-hex SHA, checks out that
same SHA in every consumer, builds Product/Gateway OCI plus SPA/H2/Playwright
runtime once, and makes browser/release/attestation jobs consume the SHA-bound
checksummed graph. `qa-required` rejects failure, cancellation or skip and
emits a canonical attestation that binds all six job conclusions and the
release-manifest digest. This local document is not that GitHub attestation.

All recorded local QA gates are green and independent browser/Web review
reported no blocker. Production remains STOP because P1 is insufficient and
P2–P9 remain unset; only a future protected GitHub run can emit the canonical
`qa-required` attestation for a committed release SHA.
