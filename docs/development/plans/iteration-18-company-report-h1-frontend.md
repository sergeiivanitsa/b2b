# Итерация 18 — Frontend H1: implementation plan

ID: `18`
Slug: `company-report-h1-frontend`
Contract: `company_public_h1_v1`
Branch: `feat/iteration-18-company-report-h1-frontend`
Base commit: `c5f20fdedbc068fb9462cf230d512d510d6c294a`
Статус плана: `approved_after_single_correction`

Specification:

```text
docs/development/iterations/iteration-18-company-report-h1-frontend.md
```

## 1. Implementation decisions

1. Единственный factual endpoint страницы —
   `GET /company-reports/{inn}/public-h1`.
2. Legacy create/status остаются только lifecycle boundary; legacy latest/AI
   page не вызывает.
3. Runtime parser выполняется вручную без dependency и reconstructs новый
   allowlisted object.
4. `company_public_h1_v1` является closed versioned contract: extra keys и
   unknown values fail closed.
5. Current merged backend gates валидируются на root; reserved leaf types
   тестируются detached и не получают reachable runtime components.
6. Overall complete/partial status не вычисляется из coverage.
7. Renderer использует только DTO fields и fixed presentation registries.
8. SPA company fallback получает synchronous path-scoped noindex до React.
9. Existing public router production file, Claims, backend, package/lock,
   Roadmap и deploy не меняются.
10. CSS меняется только в `.company-report-*`; landing styles неизменны.

## 2. Exact manifest

### 2.1. Documentation/state

| File | Change |
|---|---|
| `docs/development/iterations/iteration-18-company-report-h1-frontend.md` | Reviewed specification. |
| `docs/development/plans/iteration-18-company-report-h1-frontend.md` | Reviewed implementation plan. |
| `docs/development/DEVFLOW_STATE.yaml` | Только iteration-18 DevFlow transitions. |

### 2.2. Production frontend

| File | Change |
|---|---|
| `services/web_ui/index.html` | Strict company-path-only synchronous lang/noindex bootstrap. |
| `services/web_ui/src/companyReport/companyReportTypes.ts` | H1 topology, reserved DTO и lifecycle types; legacy score/AI page types удалить. |
| `services/web_ui/src/companyReport/companyReportApi.ts` | `getCompanyPublicH1`; parse unknown; сохранить create/status. |
| `services/web_ui/src/companyReport/companyReportPresentation.ts` | Route/error classification, fixed labels, string-only dates, safe head manager. |
| `services/web_ui/src/companyReport/companyReportH1Contract.ts` | Новый strict parser/reconstructor и safe contract error. |
| `services/web_ui/src/components/company-report/CompanyReportContent.tsx` | State shell, focus/live behavior, manifest dispatcher и safe parity attributes. |
| `services/web_ui/src/components/company-report/CompanyReportH1Blocks.tsx` | Только reachable current-runtime H1 blocks. |
| `services/web_ui/src/pages/CompanyReportPage.tsx` | Public-H1 lifecycle, canonical navigation, one-create flow, polling/abort/meta; AI удалить. |
| `services/web_ui/src/index.css` | Scoped H1 responsive/a11y styles. |

### 2.3. Safe fixtures

```text
services/web_ui/src/companyReport/fixtures/company-public-h1-published.json
services/web_ui/src/companyReport/fixtures/company-public-h1-published-ssr.html
services/web_ui/src/companyReport/fixtures/company-public-h1-latest-unpublished.json
```

Fixtures читаются test-only через Vite `?raw` + `JSON.parse` или `node:fs`:
`tsconfig.app.json` не меняется и не требует `resolveJsonModule`.

### 2.4. Tests

```text
services/web_ui/src/companyReport/companyReportApi.test.ts
services/web_ui/src/companyReport/companyReportPresentation.test.ts
services/web_ui/src/companyReport/companyReportH1Contract.test.ts
services/web_ui/src/components/company-report/CompanyReportContent.test.tsx
services/web_ui/src/components/company-report/CompanyReportH1Blocks.test.tsx
services/web_ui/src/pages/CompanyReportPage.test.tsx
services/web_ui/src/router/PublicCompanyReportFlow.test.tsx
```

No wildcard expansion. Explicitly unchanged:

```text
services/web_ui/package.json
services/web_ui/package-lock.json
services/web_ui/tsconfig*.json
services/web_ui/vite.config.ts
services/web_ui/src/router/AppRouter.tsx
services/web_ui/src/claims/*
services/web_ui/src/auth/*
services/web_ui/src/lib/api.ts
services/product_api/*
services/gateway_api/*
shared/*
deploy/*
.github/workflows/*
docker-compose*.yml
docs/development/ROADMAP.md
```

## 3. Stage A — Contract boundary and fixtures

### 3.1. Types and numeric boundary

In `companyReportTypes.ts`:

1. Keep `CompanyReportAccepted` and `CompanyReportLifecycle`.
2. Add root/current/reserved iteration-17 DTO types.
3. UUID, ISO timestamps/dates and only the following exact Decimal fields
   remain strings:
   - `source_decimal`;
   - `rub_decimal`;
   - `exact_percent`;
   - `exact_decimal`;
   - reserved `share_percent_decimal`.
4. Backend `display_value` strings remain strings and are never reformatted.
5. Years/counts/limit/offset use TypeScript `number`.
6. Runtime parser accepts these numeric fields only with
   `Number.isSafeInteger`; counts/offset require non-negative values and limit
   requires positive value.
7. Remove legacy `CompanyReportResponse` from page-facing imports.
8. Reserved topology remains structurally exact despite disabled root emission.

Negative tests include numeric strings, fractions, `NaN`, infinities, unsafe
integers, negative count/offset and zero/negative limit. Exact Decimal negative
tests include exponent notation, leading plus, trailing decimal point,
non-canonical leading zeros, `NaN`, `Infinity` and whitespace.

### 3.2. Parser and mirrored invariants

Create `companyReportH1Contract.ts` in this order:

1. Recursive exact-key object guard.
2. Array/string/boolean/null and safe-integer guards.
3. UUID, ASCII identifier, ISO date, UTC timestamp, canonical Decimal and
   same-origin path grammar.
4. Closed enum/catalog guards.
5. Current and detached reserved leaf parsers.
6. Requisites/finance/arbitration parsers.
7. Coverage/source/limitation/action/breadcrumb parsers.
8. Exact root relationships.
9. Current-runtime disabled gates.
10. Recursive forbidden-surface audit.
11. Return newly allocated readonly DTO.

Implement and table-test:

```text
previous_year == current_year - 1

FinanceBlock.metrics.length >= 1
current root FinanceBlock.unit_policy_version == null
every current root FinanceMetric.money == null
every current root FinanceMetric.yoy != null

currency =~ ^[A-Z][A-Z0-9_-]{2,15}$
claim display == exact_decimal with "." changed to "," + " " + currency
case claim role is plaintiff/respondent
case claim role == attributed_role
aggregate claim role is plaintiff/respondent

sum(role_counts) + unattributed == normalized
normalized + malformed == returned
sum(status_counts) == normalized
sum(result_counts) == normalized

every coverage limitation code has exact present catalog limitation
coverage exact six-item order/dataset mapping
sources unique and in precedence order
optional coverage exact not_requested/null slice/exact code order

current status fields == null
current legal_form == null
current optional blocks == null
current internal_links == []
current exact block_order
exact two actions and labels/paths
exact two breadcrumbs and relationships
latest_unpublished implies indexable false
```

Date/display policy:

- do not convert `checked_at` to Moscow;
- validate UTC/ISO grammar;
- validate `checked_date_display` against `checked_date` using only string
  components and approved Russian month catalog;
- preserve all three server fields.

Decimal display policy:

- never use JavaScript Number;
- pure decimal-string validation confirms approved signed one-decimal
  `ROUND_HALF_UP` relationship for YoY;
- claim amount display relation is exact string validation;
- validators return original server exact/display strings and never create
  replacement facts.

`CompanyReportContractError` exposes only
`company_public_h1_contract_mismatch`, never raw payload/reason.

Additional tests cover:

- valid v1/v2 and published/latest;
- missing/extra nested fields;
- malformed UUID/INN/KPP/OGRN/path/date/timestamp/Decimal;
- unknown contract/block/dataset/state/metric/role/action/version/limitation;
- exact coverage/source/action/breadcrumb order and root relationships;
- status/legal-form/money/optional blocks/internal links rejected at root;
- detached money/tax/bankruptcy/manager/owner/link topology accepted by their
  dedicated leaf parsers/types.

### 3.3. Fixtures

Use only synthetic values derived through merged iteration-17 DTO/builder.

Published pair:

```text
exact JSON DTO
→ merged render_public_h1_html(dto)
→ deterministic checked-in HTML
```

Latest-unpublished JSON is regenerated/copied against the merged backend
golden. Before check-in:

- both JSON files pass frontend parser;
- SSR root attributes/factual values match published JSON;
- fixture search excludes forbidden/contact/PII keys and production values;
- no raw provider payload.

Stage completion: parser matrix green, fixtures traceable, no dependency diff.

## 4. Stage B — API boundary

Update `companyReportApi.ts`:

```text
getCompanyPublicH1(inn, signal):
  apiFetchJson<unknown>("/company-reports/{inn}/public-h1")
  → parseCompanyPublicH1
  → CompanyPublicH1Response
```

Retain `getCompanyReportStatus` and `createCompanyReport`. Delete page-facing
legacy latest/`include_ai_explanation` helper.

API tests:

- exact `/public-h1` path without query;
- AbortSignal forwarding;
- malformed 200 becomes safe contract mismatch;
- create/status URLs and bodies unchanged;
- no auth wrapper or external URL.

Stage completion: no factual JSON reaches renderer without strict parser.

## 5. Stage C — Presentation policy

Refactor `companyReportPresentation.ts`:

1. Preserve strict plain/canonical parser; reject non-empty company-route
   query string, while safe in-page hashes remain client-only.
2. Validate returned path for same INN.
3. Add exact block, coverage, dataset, finance metric and arbitration
   role/status/result label registries.
4. Add `displayIsoDate` through string slicing only.
5. Preserve `checked_date_display`, YoY and amount `display_value` verbatim.
6. Add typed HTTP/detail-code error classification.
7. Distinguish retryable read/status errors from terminal H1 errors.
8. Add exact shared head constants:

   ```text
   HEAD_OWNER_ATTRIBUTE = "data-company-report-head-owner"
   HEAD_OWNER_VALUE = "company-report-h1-v1"
   HEAD_KIND_ATTRIBUTE = "data-company-report-head-kind"
   ```

9. Head manager owns only nodes with this exact owner value.
10. SPA always keeps owned robots at `noindex,follow`; it never promotes index.
11. After parsed DTO it owns one canonical link and safe dynamic title.
12. Route-scoped lang becomes `ru`; cleanup restores previous lang/title and
    removes only owned nodes.

Do not infer lifecycle status from coverage.

Tests cover every mapping, string-only dates, browser timezone independence,
query rejection, metadata transitions and cleanup. Head tests begin with the
real bootstrap-created node and prove exactly one owned robots/canonical node,
adoption without duplication, published SPA remaining noindex, error/noindex
states, cleanup of only owned nodes, no stale company metadata on `/`, and no
telemetry invocation.

## 6. Stage D — Route lifecycle

Rewrite `CompanyReportPage.tsx` around discriminated states:

```text
loading_h1 | pending | content | terminal_error |
retryable_error | contract_error | invalid_route
```

State contains only current route identity, parsed H1 DTO, safe error and
pending stage. AI/scoring/legacy report state is removed.

### 6.1. Load algorithm

```text
loadH1(inn, kind)
  success:
    if pathname != dto.canonical_path: replace navigate
    retain and render same dto
  exact 409 report_pending:
    enter read-only pending/poll for plain or canonical
  plain + exact 404 company_report_not_found:
    create once, then poll
  otherwise:
    terminal or retryable safe state; never legacy fallback
```

Canonical wrong slug is normalized. Canonical 404/terminal 409 never POST.
Any non-empty query is invalid locally and makes zero H1/create calls.

Before `navigate(dto.canonical_path, {replace:true})`, retain optional parsed DTO
in a component-local ref keyed by exact `{inn, canonical_path}`. The route
effect consumes it once after replace and enters content without a second H1
request. It clears the ref on mismatch, cross-INN navigation, error and
unmount. It never writes DTO to history/session/local storage.

Tests prove plain success and wrong-slug canonical success each make one H1
request across replace, retained DTO is consumed once, wrong INN/path cannot
consume it, and remount without ref safely performs an ordinary read.

### 6.2. Poll

- POST 202 enters pending regardless of `reused`.
- Poll at existing `STATUS_POLL_INTERVAL_MS`.
- At most one request is in flight.
- Pending title changes are visual; live region announces only semantic state.
- Any terminal lifecycle triggers a final public-H1 read; H1 classifies final
  public result.
- Status failure never directly creates another run.

### 6.3. Races

Tests use fake timers/delayed promises and production-like `<StrictMode>`:

- plain exact 404 creates once under effect replay;
- stale success/404/pending cannot change DOM/URL or start stale POST;
- one poll in flight; unmount aborts it;
- delayed final H1 survives poll cleanup;
- navigation aborts old work;
- canonical replace works;
- terminal errors never POST;
- explicit retry repeats only the classified current operation.

### 6.4. Head/bootstrap authority

`index.html` adds a minimal inline bootstrap before Yandex telemetry. It uses
the exact shared owner/kind literals documented in specification and:

- runs only for strict company pathname;
- route-scoped sets `lang=ru`;
- creates/adopts exactly one owned robots meta;
- removes only duplicate owned robots;
- sets `noindex,follow`;
- performs no network, logging or telemetry call.

React adopts the same node. Every company SPA state remains noindex. Parsed DTO
adds one owned canonical and safe title, but does not promote indexability.
Cleanup removes only owned nodes and restores prior title/lang.

Backend SSR and sitemap remain the only indexability authority. Initial HTTP
`X-Robots-Tag` for SPA fallback is documented as an existing server/deploy
boundary, not claimed by this implementation.

## 7. Stage E — H1 renderer

### 7.1. Component split

`CompanyReportContent.tsx` owns state shells, focus target, safe root parity
attributes and exhaustive block dispatcher.

`CompanyReportH1Blocks.tsx` owns reachable blocks:

- breadcrumbs;
- identity/status hero;
- known summary;
- in-page navigation;
- coverage/date;
- requisites;
- finance YoY;
- arbitration;
- sources/limitations;
- neutral actions.

No tax/bankruptcy/management/internal-link runtime branches are implemented.

### 7.2. Rendering rules

1. Iterate backend `block_order`, never locale-sort it.
2. Render only exact typed fields; no generic object traversal.
3. Link limitations with stable IDs/`aria-describedby`.
4. Use fixed Russian labels from specification.
5. Preserve numeric zero/false and distinguish them from null.
6. Keep backend display strings verbatim.
7. Never use `dangerouslySetInnerHTML` or hidden serialized JSON.

Explicitly remove legacy technical eyebrow, dataset internals, signals,
machine scoring, AI section/button, unknown finance-unit label, absolute
finance table, overall status badge and new-report button for terminal report.

### 7.3. Claims action

Render parsed backend action path. Test verifies exact displayed root UUID and
absence of company context/raw data in query/storage.

Stage completion: both DTO fixtures render; only server facts/fixed labels are
visible; prohibitions pass recursively.

## 8. Stage F — CSS, a11y and responsive

Replace only legacy `.company-report-*` styles:

- content max-width, `min-width:0`, responsive hero/facts/actions;
- definition grids collapse on tablet/mobile;
- long tokens wrap;
- native controls >= 44px and visible focus;
- scrollable dense region labelled/focusable when necessary;
- no color-only status;
- restrained live/busy states;
- mobile full-width actions;
- reduced-motion rule;
- `.company-entry-*` unchanged.

### 8.1. Reproducible real-browser QA

Use the tracked published fixture containing long name/address and exactly ten
selected cases, plus the latest-unpublished fixture.

No Playwright/Cypress/dependency/config file is added. Use:

- temporary OS directory outside repository;
- temporary Python standard-library allowlist JSON server bound only to
  `127.0.0.1`;
- existing Vite `DEV_API_PROXY_TARGET`;
- two explicit verified-free loopback ports;
- hidden processes with retained PIDs;
- bounded 30-second readiness/stop waits.

The mock serves only exact H1 GET paths with
`Content-Type: application/json`, returns 404 otherwise, performs no POST and
has no external network behavior.

Start, viewport, keyboard/focus/overflow/screenshot and `finally` cleanup steps
are exactly those in specification § 12.1.

Acceptance:

- 1440×1000, 768×1024 and 390×844 checked;
- long values and all ten cases readable;
- document/body overflow assertions true;
- headings/landmarks/lang correct;
- exactly one owned robots and one content canonical;
- complete keyboard/focus pass;
- screenshots inspected from OS temp only;
- exact mock/Vite PIDs stopped;
- ports released;
- unique temp directory removed;
- pre/post git status identical;
- no tracked or untracked QA artifact.

## 9. Stage G — parity and regression

### 9.1. Published semantic SSR/API/SPA parity

Read raw published JSON and SSR HTML. Assert equal:

- root contract/report/version/scope/canonical/indexable attributes;
- ordered block IDs;
- checked date fields;
- identity/requisites/finance/arbitration facts;
- backend display strings;
- fixed backend messages;
- coverage, sources, limitations, actions and breadcrumbs.

Parity is semantic, not literal DOM text parity. Friendly local Russian labels
may differ from technical SSR field labels. SPA robots intentionally remain
`noindex,follow`; this is not a parity failure because indexability authority
belongs to the published backend SSR/sitemap. Frontend-only scope does not
claim visual/hydration parity for a direct published hard-load.

### 9.2. Latest unpublished

Assert parser/SPA equality for identity/path/date/order/facts, noindex, zero
create for existing projection and no SSR parity claim.

### 9.3. Regression

Run unchanged tests for public AppRouter route, landing/INN form,
companyReturnTarget, Claims handoff/backlink and Claim step 2.

## 10. Detailed test matrix

| Surface | Required cases |
|---|---|
| Root parser | v1/v2, published/latest, missing/extra, forbidden/unknown, disabled gates |
| Reserved types | detached money/tax/bankruptcy/manager/owner/link |
| Identifiers | ASCII INN/KPP/OGRN, UUID, same-INN canonical |
| Safe integers | Years/counts/limit/offset safe integer, fractional/unsafe/string/negative cases |
| Decimal strings | Exact canonical strings, no Number conversion, approved display relationship |
| Finance invariants | Adjacent years, non-empty facts, current money/unit null, every metric YoY non-null |
| Arbitration invariants | Currency/display/role match and all four sum equations |
| Coverage references | Every code resolves to exact present catalog limitation |
| Root contract | Exact blocks/order/actions/breadcrumbs/optional gates |
| Backend policy | No Moscow conversion or fact/display regeneration |
| Coverage | exact six/order/mapping, seven states, nullable/zero counts |
| Sources | unique fixed order and honest normalization version |
| Limitations | exact catalog/message/association/stable IDs |
| API | public-h1 only, signal, malformed success, create/status regression |
| Canonical | success/wrong slug, pending poll, 404/terminal no create |
| Plain | existing success, exact 404 one create, pending/final, terminal no create |
| Race | StrictMode, stale route, unmount, one poll, delayed final read |
| Retained navigation | One H1 read across plain/canonical replace |
| Content | H1/requisites/YoY/arbitration/sources/actions/zeros |
| Prohibitions | no legacy/raw/contact/score/verdict/signals/AI |
| Head ownership | One shared owned robots, one canonical, no stale/foreign mutation |
| A11y | headings, landmarks, focus, busy/live, described limitations, keyboard |
| Responsive | long values/no document overflow at 1440/768/390 |
| Browser QA | Loopback fixtures, 1440/768/390, keyboard/focus/overflow, exact cleanup |
| Parity | published semantic SSR/API/SPA; latest API/SPA only |
| Regression | landing, public route, return target and Claims |

## 11. Verification commands

Run from repository root.

Targeted H1:

```text
npm run test --prefix services/web_ui -- --run src/companyReport/companyReportH1Contract.test.ts src/companyReport/companyReportApi.test.ts src/companyReport/companyReportPresentation.test.ts src/components/company-report/CompanyReportH1Blocks.test.tsx src/components/company-report/CompanyReportContent.test.tsx src/pages/CompanyReportPage.test.tsx src/router/PublicCompanyReportFlow.test.tsx src/router/AppRouter.companyPage.test.tsx
```

Entry/Claims regression:

```text
npm run test --prefix services/web_ui -- --run src/components/company-report/CompanyReportInnForm.test.tsx src/pages/CompanyLandingPage.test.tsx src/auth/companyReturnTarget.test.ts src/claims/companyReportHandoff.test.ts src/pages/ClaimStep2Page.test.tsx
```

Required gates:

```text
npm run lint --prefix services/web_ui
npm run test --prefix services/web_ui
npm run build --prefix services/web_ui
python -m pytest services/product_api/tests_unit -q
git diff --check
git status --short
```

Product API unit is a touched-contract regression. PostgreSQL integration,
Alembic and Python lint/type-check do not apply because backend/schema do not
change and such Python lint commands are not configured.

## 12. Security/privacy audit

Before review:

1. Compare exact paths with manifest.
2. Search diff/fixtures for forbidden/contact/PII terms.
3. Exclude `.env`, token, auth file, probe, log, cache and temporary evidence.
4. Prove page has no legacy AI/scoring read.
5. Prove parser reconstructs allowlisted object and errors do not stringify
   payload.
6. Search protected Decimal paths for `Number`, unary plus, `parseInt`,
   `parseFloat` and locale numeric formatting; ordinary safe-integer fields are
   explicitly allowed as numbers.
7. Prove unsafe/fractional/negative integer matrix rejects.
8. Prove date code never derives Moscow date from `checked_at`.
9. Prove no external/cross-INN action or canonical survives parser.
10. Prove head manager touches only exact owned nodes and emits no telemetry.
11. Prove package/lock, backend, deploy and QA helpers/artifacts are absent from
    diff.

## 13. Migration, rollback and residual boundaries

Migration: not applicable. No DB/schema/snapshot/publication mutation.

Rollback before deployment: revert one iteration-18 frontend/docs commit; no
data cleanup. Backend H1 and immutable v1/v2 snapshots remain compatible.

Residual boundaries recorded, not hidden:

- direct published hard-load remains standalone iteration-17 SSR and is not
  hydrated/styled by this frontend-only iteration;
- path-scoped HTML noindex protects SPA fallback body, while HTTP
  `X-Robots-Tag` remains backend/nginx responsibility outside this diff;
- no automated layout/a11y browser plugin is added, so real-browser QA evidence
  is mandatory.

## 14. Independent review focus

Reviewer must answer:

1. Does client activate a disabled backend gate?
2. Is overall status inferred from coverage?
3. Can canonical/terminal state create a report?
4. Can existing report trigger refresh/provider work?
5. Does any H1 fact use legacy latest/scoring/AI?
6. Are backend date/Decimal display strings preserved?
7. Does company SPA start noindex and latest remain noindex?
8. Does path-scoped bootstrap leave non-company routes alone?
9. Does Claims use displayed report ID?
10. Are block/coverage/source/limitation orders exact?
11. Are contacts/raw/internal data absent?
12. Does diff stay inside exact manifest?

## 15. Completion gates

Independent plan review returned `CHANGES_REQUIRED`; the single allowed
correction pass closed its four mandatory findings. Root verification approved
the corrected plan without a second independent review.

Code review begins
only when parser, fixture parity, lifecycle/race, responsive/a11y, targeted and
full checks are green and scope audit is clean. Iteration becomes
`ready_for_merge` only after independent code review returns `VERDICT: READY`.
Merge remains manual.

Additional completion gates:

- safe/lossless integer negative matrix passes;
- exact mirrored invariant table passes;
- backend-authoritative date/display strings are never regenerated;
- plain and canonical replace retain parsed DTO with one H1 read;
- SPA never promotes indexability;
- one shared head-owner contract and cleanup matrix pass;
- reproducible real-browser QA completes with no residual process, port,
  screenshot, helper or repository artifact.
