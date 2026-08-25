# Итерация 22 — Company Card v2 page shell: implementation plan

ID: 22
Slug: company-card-v2-page-shell
Specification:
docs/development/iterations/iteration-22-company-card-v2-page-shell.md
Base commit: 5fa69e7
Branch: feat/iteration-22-company-card-v2-page-shell
Status: approved_after_single_correction
Production activation: NOT AUTHORIZED

## 1. Execution rules

- Implement test-first in the iteration-22 worktree.
- Preserve unrelated/user files.
- Do not modify ROADMAP.md.
- Do not call network, provider, FNS, Gateway, AI or production DB.
- Do not activate H2 assignment or positive rollout settings.
- Do not add dependencies.
- Do not modify H1 DTO, render_public_h1_html or H1 golden bytes.
- Do not implement F1–F5/A1–A5 chart renderers.
- Implementer does not commit or push.
- Any need for schema migration, H2 assignment, Claims changes or new factual
  semantics is a blocker.

## 2. Exact changed-file manifest

### 2.1. Docs and state

    README.md
    docs/development/DEVFLOW_STATE.yaml
    docs/development/iterations/iteration-22-company-card-v2-page-shell.md
    docs/development/plans/iteration-22-company-card-v2-page-shell.md

ROADMAP.md remains unchanged.

### 2.2. Product API runtime

    services/product_api/pyproject.toml
    services/product_api/src/product_api/main.py
    services/product_api/src/product_api/routers/company_reports_public.py
    services/product_api/src/product_api/company_reports/public_h1_service.py
    services/product_api/src/product_api/company_reports/public_document_service.py
    services/product_api/src/product_api/company_reports/persistence/public_documents.py
    services/product_api/src/product_api/company_reports/company_card_v2/public_h2.py
    services/product_api/src/product_api/company_reports/company_card_v2/public_h2_models.py
    services/product_api/src/product_api/company_reports/company_card_v2/public_h2_ssr_adapter.py
    services/product_api/src/product_api/company_reports/company_card_v2/service.py
    services/product_api/src/product_api/company_reports/company_card_v2/public_h2_document.py
    services/product_api/src/product_api/company_reports/company_card_v2/public_h2_asset_manifest.py
    services/product_api/src/product_api/company_reports/company_card_v2/public_h2_asset_manifest.json

Explicitly unchanged:

    services/product_api/src/product_api/company_reports/public_h1.py
    services/product_api/src/product_api/claims/**
    services/product_api/alembic/versions/**

### 2.3. Product tests and fixtures

    services/product_api/tests_unit/test_company_card_v2_public_h2.py
    services/product_api/tests_unit/test_company_card_v2_canonical_json.py
    services/product_api/tests_unit/test_company_card_v2_public_h2_ssr_adapter.py
    services/product_api/tests_unit/test_company_card_v2_public_h2_document.py
    services/product_api/tests_unit/test_company_card_v2_public_h2_asset_manifest.py
    services/product_api/tests_unit/test_company_report_public_document_service.py
    services/product_api/tests_unit/test_company_report_public_document_persistence.py
    services/product_api/tests_unit/test_company_report_public_routes.py
    services/product_api/tests_unit/fixtures/company_card_v2/public_h2_v1_expected.json
    services/product_api/tests_unit/fixtures/company_card_v2/public_h2_v2_expected.json
    services/product_api/tests_unit/fixtures/company_card_v2/public_h2_v3_expected.json
    services/product_api/tests/test_company_report_public_h2_reads.py
    services/product_api/tests/test_company_report_public_documents.py

Existing H1 fixtures remain read-only.

### 2.4. Shared cross-language fixtures

    shared/fixtures/company_public_h2_cjson_v1.json

The existing Product canonical vectors remain and are byte-compared with this
shared fixture.

### 2.5. Dedicated H2 frontend

    services/web_ui/package.json
    services/web_ui/vite.company-public-h2.config.ts
    services/web_ui/scripts/company-public-h2-manifest.mjs
    services/web_ui/src/companyPublicH2/main.tsx
    services/web_ui/src/companyPublicH2/bootstrap.tsx
    services/web_ui/src/companyPublicH2/strictJson.ts
    services/web_ui/src/companyPublicH2/canonicalJson.ts
    services/web_ui/src/companyPublicH2/contract.ts
    services/web_ui/src/companyPublicH2/presentation.ts
    services/web_ui/src/companyPublicH2/CompanyPublicH2Page.tsx
    services/web_ui/src/companyPublicH2/CompanyPublicH2Page.css
    services/web_ui/src/companyPublicH2/strictJson.test.ts
    services/web_ui/src/companyPublicH2/canonicalJson.test.ts
    services/web_ui/src/companyPublicH2/contract.test.ts
    services/web_ui/src/companyPublicH2/bootstrap.test.tsx
    services/web_ui/src/companyPublicH2/CompanyPublicH2Page.test.tsx
    services/web_ui/src/companyPublicH2/assetManifest.test.ts
    services/web_ui/src/companyPublicH2/fixtures/public-h2-v3-shell.json
    services/web_ui/src/companyPublicH2/fixtures/public-h2-v3-shell.ssr.html

Must not change or import:

    services/web_ui/index.html
    services/web_ui/src/main.tsx
    services/web_ui/src/App.tsx
    services/web_ui/src/index.css
    services/web_ui/src/auth/**

### 2.6. Existing landing navigation

    services/web_ui/src/pages/CompanyLandingPage.tsx
    services/web_ui/src/pages/CompanyLandingPage.test.tsx
    services/web_ui/src/router/PublicCompanyReportFlow.test.tsx

### 2.7. Deploy and verification

    .github/workflows/deploy_prod.yml
    deploy/nginx/product_api.conf
    deploy/nginx/pork.su.conf
    deploy/nginx/test_product_api_conf.ps1
    deploy/nginx/install_company_public_h2_assets.sh
    deploy/nginx/test_company_public_h2_release.py
    deploy/nginx/README.md
    scripts/run-iteration22-postgres-tests.ps1
    scripts/serve-iteration22-company-public-h2-fixture.py

Any additional path requires explicit root scope audit before it is changed.

## 3. Dependency and migration decision

No dependency is added. No Alembic migration is created.

Reasons:

- page shell uses existing React/Vite;
- strict parsing and hashing use browser/Node standard APIs;
- backend rendering uses Python standard library and current Pydantic models;
- current DB schema already contains assignment/pin/report bindings;
- iteration 22 must not enable H2 assignment.

## 4. Stage 0 — Baseline and immutable fences

Before behavior changes:

1. Record git status and base.
2. Hash H1 fixtures and deterministic H1 renderer output.
3. Run targeted existing H1/H2 tests.
4. Record current H2 action-path defect /company.
5. Assert H2 settings defaults are off.
6. Assert assign_pin_cas rejects H2.
7. Assert no H2 frontend entry exists.

Baseline commands:

    python -m pytest services/product_api/tests_unit/test_company_report_public_routes.py services/product_api/tests_unit/test_company_card_v2_public_h2.py services/product_api/tests_unit/test_company_card_v2_public_h2_ssr_adapter.py -q
    npm run test --prefix services/web_ui -- src/pages/CompanyReportPage.test.tsx src/router/PublicCompanyReportFlow.test.tsx

Record SHA-256 for:

    services/product_api/tests_unit/fixtures/company_reports/public_h1_v1_expected.json
    services/web_ui/src/companyReport/fixtures/company-public-h1-published.json
    services/web_ui/src/companyReport/fixtures/company-public-h1-published-ssr.html

The same hashes are required after implementation.

## 5. Stage 1 — Correct H2 navigation cross-bindings

Update both build_public_h2 and build_legacy_public_h2:

    check_another_company.path = "/"
    breadcrumbs[0] = Главная, "/", current=false
    prepare_claim.path = "/claims?report_id={report_id}"
    primary_claim_cta.path = same exact Claims path

Strengthen CompanyPublicH2Response validation:

- exact action order, labels and paths;
- exact breadcrumb order/current flags;
- second breadcrumb label/path equals identity/canonical;
- both Claims paths equal each other;
- both Claims paths bind exact root UUID;
- canonical path binds identity INN;
- no external or request-controlled alias.

Regenerate only H2 expected DTOs/digests.

Tests:

- cross-report UUID;
- presentation UUID used as Claims ID;
- /company first action;
- external or query-bearing action;
- swapped actions;
- stale breadcrumb;
- wrong canonical INN;
- old staged pin digest fails closed without mutation.

## 6. Stage 2 — Shared TypeScript parsing and canonical JSON

strictJson.ts exposes:

    StrictJsonError
    StrictJsonInteger
    StrictJsonValue
    parseStrictJson(raw)

Integer representation:

    type StrictJsonInteger = {
      readonly kind: "integer"
      readonly token: string
      readonly value: bigint
    }

Parser requirements:

- recursive descent over raw text;
- integer grammar `0|-?[1-9][0-9]*`;
- reject negative zero, float, exponent, plus and leading zero;
- preserve the exact accepted decimal token;
- construct BigInt only after grammar and byte/depth bounds pass;
- never parse an integer through JSON.parse or Number;
- duplicate raw key rejection;
- duplicate-after-NFC rejection;
- unpaired raw/escaped surrogate rejection;
- JSON controls/escape validation;
- input byte, collection and depth bounds.

canonicalJson.ts exposes CanonicalJsonError, canonicalJsonBytes and
canonicalProjectionDigest over StrictJsonValue.

Requirements mirror Python:

- NFC strings/keys;
- Unicode-scalar key order;
- preserved arrays;
- exact control escaping;
- emit StrictJsonInteger.token byte-for-byte;
- remove projection_digest entirely before hash;
- lowercase SHA-256;
- no Number.isSafeInteger profile restriction and no Number round trip.

contract.ts exposes:

    CompanyPublicH2ContractError
    ParsedCompanyPublicH2
    parseCompanyPublicH2

ParsedCompanyPublicH2 retains both:

- canonicalSource: the validated StrictJsonValue used for digest;
- dto: the typed React presentation DTO.

Full recursive validation covers every leaf in public_h2_models.py, including
currently unrendered F1–F5/A1–A5. Integer bounds are compared as BigInt. A leaf
may become JavaScript number only after its exact schema bound is validated
and that schema bound itself lies within the safe-integer interval. Unbounded
or wider leaves retain an integer wrapper/token; rendering uses the token.
Digest canonicalization always uses canonicalSource and never the converted
presentation DTO.

Tests use shared Python/TypeScript vectors for:

- 9007199254740991;
- 9007199254740992;
- 123456789012345678901234567890;
- negative large integer;
- NFC equivalence and collision;
- Cyrillic;
- `<`, `>` and `&`;
- U+2028/U+2029;
- controls, slash, backslash and quotes;
- nested key ordering;
- Decimal strings;
- surrogate;
- float/exponent;
- caps equality and plus one;
- digest exclusion/insertion.

The 2^53 and larger vectors must round-trip token-exact and produce the same
canonical bytes and SHA-256 as Python. No dependency is added.

## 7. Stage 3 — Asset build and pinned manifest

vite.company-public-h2.config.ts writes only:

    services/web_ui/dist-company-public-h2/

Configuration:

- input is src/companyPublicH2/main.tsx;
- output directory is separate from SPA dist;
- React is bundled instead of shared with SPA chunks;
- JS/CSS/chunk basenames begin company-public-h2.;
- content hashes are present;
- no HTML entry is derived from index.html;
- no Auth/Router/Webvisor imports.

package.json build order:

    tsc -b
    vite build
    vite build --config vite.company-public-h2.config.ts
    node scripts/company-public-h2-manifest.mjs --verify

The explicit authoring command:

    npm run build:company-public-h2-manifest

is the only command that writes:

    services/product_api/src/product_api/company_reports/company_card_v2/
      public_h2_asset_manifest.json

company-public-h2-manifest.mjs:

1. reads only the isolated output;
2. walks the exact Vite entry graph;
3. validates same-origin prefixed content-hashed names;
4. computes SHA-256 for every referenced byte file;
5. emits deterministic UTF-8/LF/sorted manifest bytes in author mode;
6. in verify mode requires byte-identical tracked manifest and exact file set;
7. scans JS/CSS for mc.yandex, webvisor, ym(, /internal/whoami,
   AuthProvider, /company-reports/ and /company-report-presentations;
8. prepares a release artifact containing only the tracked manifest and its
   referenced assets.

pyproject.toml declares the manifest as Product package data.

public_h2_asset_manifest.py defines strict frozen models and:

    load_public_h2_asset_manifest
    validate_public_h2_asset_manifest
    public_h2_asset_manifest_sha256
    asset_integrity_attribute

Loading uses importlib.resources and exact packaged bytes. Product lifespan
validates schema, contract, CJSON profile and deterministic identity before
traffic. The loaded object is injected into SSR rendering. Product never
reads web dist, host manifest-set or nginx asset bytes.

Tests cover package inclusion, BOM/non-UTF-8, unknown fields, wrong versions,
external/traversal paths, missing/duplicate/extra assets, bad hash, ordering,
JS/CSS mismatch, exact digest identity and startup failure/success.

## 8. Stage 4 — One joined assignment-aware document selection

Create persistence/public_documents.py with:

    PublicDocumentAssignmentRow
    get_public_document_assignment_row(session, inn)

The helper issues one SELECT with:

    subject
    LEFT JOIN assignment
    LEFT JOIN exact pin on subject/contract/pin_generation
    LEFT JOIN exact report on pin.report_id/subject

No second assignment read is allowed.

Create public_document_service.py with:

    PublicDocumentKind
    ResolvedPublicDocument
    PublicDocumentInvalid
    resolve_public_document(session, inn)

Algorithm:

1. read PublicDocumentAssignmentRow once;
2. no assignment → call existing resolve_public_h1;
3. exact H1 assignment → validate and build only its joined pin/report;
4. exact H2 assignment → reproduce only its joined pin/report and exact saved
   narrative/digest;
5. unknown, absent joined member or tuple mismatch → PublicDocumentInvalid;
6. never consult staged pointer, lifecycle head, legacy H2 preview, active H1
   publication or latest H1 after an assignment is present.

public_h1_service.py adds pure:

    validate_assigned_public_h1(subject, assignment, pin, report)

It validates exact tuple, H1 pin publication fields, snapshot identity/hash,
canonical INN, generated/published time and builds through existing
build_public_h1. It does not call resolve_public_h1.

public_h2_ssr_adapter.py exposes:

    resolve_exact_assigned_public_h2(
        session,
        *,
        subject,
        assignment,
        pin,
        report,
    )

It may read exact presentation/narrative artifacts required by that pin, but
may not re-read assignment or choose another pin/report.

Tests:

- joined statement shape and one assignment SELECT;
- no assignment + staged pointer → ordinary canonical H1;
- no assignment + lifecycle head → ordinary canonical H1;
- no assignment + legacy preview → ordinary canonical H1;
- exact H1 assignment whose report differs from active publication/latest
  report → exact assigned H1;
- corrupt exact H1 pin/report/snapshot/canonical/time → 500, no fallback;
- mocked assignment change after joined SELECT cannot alter the captured row;
- exact injected H2 assignment;
- corrupt/cross-subject H2 binding;
- SELECT-only document behavior;
- render_public_h1_html output remains byte-identical for the same H1 DTO.

assign_pin_cas remains unchanged and continues rejecting H2.

## 9. Stage 5 — H2 SSR renderer

public_h2_document.py exposes:

    render_public_h2_body(dto)
    render_public_h2_document(dto, manifest, nonce, robots)
    render_public_h2_error_document(title, message)
    public_h2_security_headers(nonce, robots)

Requirements:

- escape every visible string with html.escape;
- render shell-owned sections in contract order;
- visible exact report ID;
- exact Claims cross-binding;
- no chart facts interpretation;
- one state script from script_safe_json_bytes;
- one external stylesheet and module script from manifest;
- matching nonce and CSP;
- SRI generated from manifest SHA-256;
- deterministic output for fixed DTO/manifest/nonce;
- no Webvisor/analytics;
- no raw/private fields.

Create a sanitized fixed SSR fixture with deterministic test nonce and test
manifest. Backend test requires exact renderer equality. Frontend bootstrap
test consumes the same fixture.

Negative cases:

- malicious identity/narrative/limitation;
- </script>;
- controls/U+2028/U+2029;
- unpaired surrogate;
- state cap plus one;
- manifest mismatch;
- incorrect CTA path;
- incorrect root DOM attributes.

## 10. Stage 6 — Public route selector and HTTP behavior

Refactor public_company_page into an api_route supporting GET and HEAD.

Routing algorithm:

1. reject query with 422;
2. parse plain/canonical key;
3. call resolve_public_document once;
4. use ordinary H1 resolution only when the joined row has no assignment;
5. use exact assigned H1 or exact assigned H2 when assignment exists;
6. never call generic resolve_public_h2;
7. redirect a plain key to the selected DTO’s exact canonical path;
8. return controlled 404 only for an unassigned ordinary-H1 not-found result;
9. redirect a wrong canonical slug to the selected exact canonical path;
10. render unchanged render_public_h1_html for selected H1;
11. render the new document for selected H2;
12. preserve assigned corruption/lifecycle errors without cross-contract
    fallback.

Tests assert:

- H1 SSR body and renderer golden equal baseline bytes;
- assigned H1 differing from active/latest selects assigned report;
- corrupt/changed assigned H1 returns safe 500;
- no assignment + staged old-digest H2 returns canonical H1;
- generic `/company-reports/{inn}/public-h2` + the staged old digest retains its
  existing fail-closed 500 behavior;
- exact assigned old-digest H2 returns canonical safe 500 with no H1 fallback;
- the three preceding cases use independent fixtures;
- plain existing H1 redirects canonical;
- plain missing H1 returns controlled 404;
- plain exact H2 redirects canonical;
- canonical H1 and H2 return 200;
- wrong slug returns 301;
- query returns 422;
- HEAD has GET status/headers and empty body;
- current H2 pin indexable=false produces noindex meta/header;
- structurally complete H2 head/canonical/text is present despite noindex;
- pending/failed/not-eligible return 409;
- corruption returns 500;
- SQL unavailable returns 503;
- selected errors contain no state/assets/factual root;
- no DB writes/provider/Gateway/AI calls.

Sitemap remains H1-only. indexable=true H2 persistence and sitemap behavior
remain iteration-25 scope.

## 11. Stage 7 — React bootstrap and page components

bootstrapCompanyPublicH2:

- receives Document and injected crypto in tests;
- reads state text once;
- checks exactly one state node and byte cap;
- parses and validates once;
- verifies digest;
- checks SSR root contract, report ID and current canonical pathname;
- mounts only after success;
- never imports or uses fetch;
- leaves server head unchanged;
- writes only fixed enhancement-failure text on failure.

Tests spy on fetch, XMLHttpRequest, navigator.sendBeacon, document.title and
canonical/robots nodes. Network counts remain zero.

CompanyPublicH2Page renders:

- breadcrumbs;
- hero/status/date/report ID;
- artifact/fallback narrative;
- anchor navigation;
- requisites;
- finance/arbitration coverage shells;
- sources;
- limitations;
- neutral actions;
- one responsive CTA;
- one mobile/tablet inert reserver;
- live region.

All links use regular anchors.

Before/after takeover parity compares ordered section IDs, ordered
data-h2-field map, visible text, report ID, both Claims hrefs and
coverage/limitation associations.

## 12. Stage 8 — Responsive CSS and accessibility

Use H2-scoped class names only.

CSS contract:

    @media (min-width: 1200px)
    @media (min-width: 768px) and (max-width: 1199px)
    @media (max-width: 767px)
    @media (prefers-reduced-motion: reduce)
    env(safe-area-inset-bottom)

Component/source tests cover:

- one focusable CTA;
- inert reserver has no anchor/button;
- CTA labels/copy/states;
- action order;
- headings and landmarks;
- aria-current;
- limitation IDs;
- focusable anchor destinations;
- live region;
- fallback label;
- long strings;
- no chart SVG/canvas/chart-library markup.

## 13. Stage 9 — Full document navigation from landing

Change CompanyLandingPage.openCompany from React navigate to same-origin full
navigation:

    window.location.assign("/company/{validated-inn}")

This permits Product API/nginx to select H1 or H2 before an app mounts.

Tests:

- valid INN invokes one full navigation;
- double submit remains fenced;
- invalid input does not navigate;
- no auth state is stored;
- target remains /company/{inn}.

Do not change Claims backlinks or H1 page lifecycle.

## 14. Stage 10 — Nginx, CI deploy and durable manifest history

Make product_api.conf and pork.su.conf express the same canonical config.

Locations:

    plain /company/{inn}
      -> Product API
      -> only 404 intercepted to @company_h1_spa

    canonical /company/{inn}-{slug}
      -> Product API
      -> no intercept or fallback

    /assets/company-public-h2.*
      -> /var/lib/pork/company-public-h2/v1/assets/
      -> immutable cache

Stable layout:

    /var/lib/pork/company-public-h2/v1/assets/{basename}
    /var/lib/pork/company-public-h2/v1/manifests/sha256/{digest}.json
    /var/lib/pork/company-public-h2/v1/manifest-set.json
    /var/lib/pork/company-public-h2/v1/.install.lock

manifest-set.json uses company_public_h2_manifest_set_v1 and contains exact
current plus two distinct predecessor digests, newest first.

install_company_public_h2_assets.sh:

- resolves and validates explicit source/target paths;
- takes an exclusive lock;
- verifies candidate manifest identity and every source asset;
- reads predecessors only from the existing stable manifest-set and immutable
  manifest directory;
- verifies all existing manifest digests and referenced asset hashes;
- copies assets and manifest with same-directory temp, fsync and atomic rename;
- refuses a mismatched existing basename;
- forms `[candidate, old-current, old-previous]`;
- refuses missing/malformed history or fewer than two valid predecessors;
- verifies all three retained manifests and all referenced stored assets;
- fetches every referenced URL through loopback nginx and hashes response
  bytes;
- atomically replaces manifest-set.json and fsyncs its parent;
- repeats complete stored and reachability validation;
- never deletes assets/manifests, changes flags or reloads nginx.

An idempotent candidate revalidates without rotation. A new/empty host fails.
Initial or DR seeding is explicitly deferred to an authorized iteration-25
runbook.

test_product_api_conf.ps1 asserts exact 10/12 digit patterns, plain-only 404
fallback, canonical no fallback, H2 asset rule precedence, no
User-Agent/cookie/header routing, preserved non-404 errors and stable storage
outside dist.

deploy_prod.yml static order:

1. build SPA and isolated H2 output;
2. verify tracked Product manifest and exact Vite graph;
3. package/upload current H2 release artifact;
4. extract candidate Product image manifest offline and compute its digest;
5. run installer on the existing RU stable store;
6. require host current digest equal candidate Product digest;
7. require all current-plus-two manifest/hash/loopback checks pass;
8. only then replace Product API;
9. run nonactive compatibility smoke;
10. publish SPA without touching stable H2 root;
11. validate nginx and unchanged default-off settings.

test_company_public_h2_release.py uses temporary stores and a local fixture
server to cover:

- successful rotation retaining exactly current plus two;
- idempotent verification;
- atomic pointer replacement;
- missing pointer/new host rejection;
- one-predecessor rejection;
- missing immutable manifest;
- missing/mismatched asset;
- mismatched Product/candidate digest;
- unreachable asset;
- workflow ordering proving install/history/reachability gates precede Product
  replacement;
- absence of deletion and H2 activation commands.

Update README/deploy README with asset-first and rollback order. No workflow is
executed in this DevFlow.

## 15. Stage 11 — Disposable PostgreSQL coverage

Add run-iteration22-postgres-tests.ps1 following iteration-21 safeguards:

- already-local postgres:16-alpine;
- --pull=never;
- loopback dynamic port;
- tmpfs and generated credentials;
- reject repository .env;
- clear all H2/provider/AI activation env;
- verify imported Product package belongs to current worktree;
- exact labeled-container cleanup;
- JUnit tests greater than zero, failures/errors/skips equal zero.

Targeted integration suite:

    services/product_api/tests/test_company_report_public_h1_reads.py
    services/product_api/tests/test_company_report_public_h2_reads.py
    services/product_api/tests/test_company_report_public_documents.py
    services/product_api/tests/test_company_report_presentations.py
    services/product_api/tests/test_claims_company_report_handoff.py

Required assertions:

- unassigned staged old-digest H2 remains canonical H1;
- the same staged old digest fails closed through generic public-h2;
- exact assigned old-digest H2 returns 500 without H1 fallback;
- exact assigned H1 differing from active/latest selects its exact pin/report;
- corrupt or changed assigned H1 fails closed;
- injected exact H2 assignment selects H2 noindex;
- assignment corruption never falls back;
- report ID/Claims binding;
- H1 renderer bytes unchanged;
- no DML from canonical GET/HEAD;
- no H2 activation rows created.

## 16. Stage 12 — Real-browser visual matrix

Build assets and start only the synthetic local fixture server:

    npm run build --prefix services/web_ui
    python scripts/serve-iteration22-company-public-h2-fixture.py

The server uses checked-in sanitized DTOs and Product SSR renderer, serves
built content-addressed assets, uses no DB/network/provider/Gateway and
provides fallback, artifact, sparse/partial and long-content profiles.

Capture ignored evidence under:

    .tmp/iteration22-visual/

Viewport matrix:

| Width | Required checks |
|---:|---|
| 320 | stacked fixed CTA, safe area, no horizontal scroll |
| 390 | mobile wireframe composition and long content |
| 768 | horizontal tablet CTA |
| 1024 | tablet composition |
| 1199 | final fixed-bar width |
| 1200 | first sticky-rail width |
| 1440 | full desktop grid and 320px rail |

For each viewport record:

- screenshot;
- document/body scrollWidth no greater than clientWidth;
- CTA and content bounding boxes do not overlap;
- action/CTA targets;
- fixed/sticky computed styles;
- one focusable primary CTA;
- inert reserver has no focusable descendant;
- keyboard anchor navigation;
- touch target minimum;
- 200% zoom observation;
- reduced-motion observation;
- network log with zero factual/auth/provider/Gateway/AI requests.

Profiles:

    saved artifact
    deterministic fallback
    missing/gate-closed
    partial with long limitations
    long company/address/source strings

No chart art is expected. Evidence remains ignored and is summarized for
review; no production browser or URL is used.

## 17. Required verification commands

Targeted Product unit:

    python -m pytest services/product_api/tests_unit/test_company_card_v2_public_h2.py services/product_api/tests_unit/test_company_card_v2_canonical_json.py services/product_api/tests_unit/test_company_card_v2_public_h2_ssr_adapter.py services/product_api/tests_unit/test_company_card_v2_public_h2_document.py services/product_api/tests_unit/test_company_card_v2_public_h2_asset_manifest.py services/product_api/tests_unit/test_company_report_public_document_persistence.py services/product_api/tests_unit/test_company_report_public_document_service.py services/product_api/tests_unit/test_company_report_public_routes.py -q

Targeted frontend:

    npm run test --prefix services/web_ui -- src/companyPublicH2 src/pages/CompanyLandingPage.test.tsx src/router/PublicCompanyReportFlow.test.tsx

Nginx:

    powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\nginx\test_product_api_conf.ps1

Deployment/retention static and temporary-store contract:

    python deploy/nginx/test_company_public_h2_release.py

Disposable PostgreSQL:

    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-iteration22-postgres-tests.ps1 -Mode Targeted
    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-iteration22-postgres-tests.ps1 -Mode Full

Repository-required checks:

    python -m pytest services/product_api/tests_unit -q
    python -m pytest services/gateway_api/tests -q
    npm run lint --prefix services/web_ui
    npm run test --prefix services/web_ui
    npm run build --prefix services/web_ui

With disposable PostgreSQL:

    python -m pytest services/product_api/tests -q

Additional applicable checks:

    python -m compileall services/product_api/src/product_api shared
    git diff --check
    git status --short --branch

No Python lint/type-check command is configured or claimed.

## 18. Evidence required for review

Reviewer receives:

- approved spec and plan;
- complete diff and exact changed-file manifest comparison;
- before/after H1 fixture hashes and deterministic body equality;
- H2 action/cross-binding matrix;
- joined assignment-aware exact H1/H2 selection matrix;
- staged/head/legacy non-displacement evidence;
- SELECT-only query evidence;
- SSR/embedded/client ordered field parity;
- XSS/surrogate/size matrix;
- shared Python/TypeScript CJSON results;
- built asset manifest and recomputed hashes;
- banned bundle marker scan;
- nginx config and routing results;
- deploy workflow static-contract results;
- targeted/full JUnit counts;
- real-browser screenshots and measurements;
- exact command exit codes;
- confirmation of no network/provider/AI/production calls;
- confirmation of no migration/dependency/H2 assignment.
- compiled SQL/equivalent query-count evidence for the single joined
  assignment/pin/report SELECT;
- assigned-H1-versus-active/latest matrix and corrupt-H1 fail-closed evidence;
- three independent old-digest endpoint/assignment results;
- token-exact BigInt vectors for 2^53-1, 2^53 and larger integers;
- Product packaged-manifest digest;
- before/after host manifest-set and immutable current-plus-two manifests;
- stored-byte and loopback-response hashes for every retained asset;
- new/incomplete-host pre-replacement failure;
- workflow ordering evidence showing no Product replacement before all asset
  and history gates.

## 19. Rollback

- H1 document remains intact throughout.
- Revert server document selector to H1-only if necessary.
- Do not delete v3 reports, narrative artifacts, pins or H2 assets.
- Content-addressed assets remain harmless while unreferenced.
- Existing H2 staged pins remain immutable.
- Product operation remains H1 through absent/H1 assignment and default-off
  H2 create/writer settings.
- Product rollback may reference only one of the two verified predecessor
  manifests retained in the stable host set.
- Assets and immutable manifests are not deleted during rollback.
- A host without the complete current-plus-two set is not a rollback target
  until a separately authorized iteration-25 seed procedure succeeds.

Production assignment and rollback rehearsal belong to iteration 25.

## 20. Completion gate

Iteration may move to ready_for_merge only when:

- independent plan review findings are closed by the single allowed correction;
- all implementation stages are complete;
- no additional scope was introduced;
- H1 hashes and behavior remain exact;
- action and Claims bindings pass;
- one joined assignment-aware SELECT selects exact H1/H2 binding;
- assigned H1 differs safely from active/latest and corruption fails closed;
- all three old-digest isolation scenarios pass;
- TypeScript CJSON is token-exact for arbitrary valid integers;
- no H2 assignment can be created;
- every H2 response remains noindex in iteration 22;
- Product-pinned manifest and isolated Vite output match;
- atomic current-plus-two host retention and reachability checks pass;
- new/incomplete host fails before Product replacement;
- workflow static order prevents Product-first deployment;
- all required commands pass;
- visual matrix evidence is complete;
- privacy/secret scan is clean;
- git diff --check is clean;
- independent code reviewer returns VERDICT: READY.

## 21. Recovery implementation plan

Recovery plan review: `VERDICT: APPROVED` (2026-08-25). No blocking or
substantial findings; the optional candidate-image manifest evidence remains
inside Stage R7 verification.

### 21.1. Recovery rule and state ownership

This is a fresh DevFlow continuation after a blocked implementation
correction. The preserved uncommitted branch diff is the implementation
baseline. The principal inventories it, records `blocked -> planning`, stores
this plan and submits it to independent plan review. It never resets or cleans
the preserved implementation, changes ROADMAP or starts iteration 23.

Generated `.tmp`, `dist*`, coverage, JUnit and `node_modules`/junction paths
are evidence only and must not enter the commit.

### 21.2. R1 — Close landing navigation regression

Files:

- `services/web_ui/src/router/PublicCompanyReportFlow.test.tsx`;
- `services/web_ui/src/pages/CompanyLandingPage.test.tsx`;
- `services/web_ui/src/pages/companyLandingNavigation.ts`;
- `services/web_ui/src/pages/CompanyLandingPage.tsx` only for a test seam.

Replace the obsolete SPA-takeover assertion with exactly one full-document
handoff to `/company/{validated-inn}`. Prove double-submit fencing, invalid-INN
rejection, no H1 factual GET/create/status call, and no auth/storage mutation.
Preserve direct legacy/canonical H1 SPA coverage.

### 21.3. R2 — Complete recursive TypeScript validation

Files:

- `services/web_ui/src/companyPublicH2/contract.ts`;
- add `contractSchema.ts`, `contractSemantics.ts`, `contract.test.ts`;
- add `shared/fixtures/company_public_h2_contract_v1_cases.json`;
- update Python public-H2 contract tests to consume the shared corpus.

Replace `KNOWN_NESTED_FIELDS` and traversal-only validation with closed
validators for every Python public-H2 model. Validate exact keys, types,
nullability, literals, bounds, tuple/array shapes, order, identifiers,
dates/UTC, Decimal arithmetic and every Python semantic/cross-binding rule.
Retain arbitrary-size numeric tokens and compare integer bounds with `BigInt`.
Construct an immutable typed presentation DTO only after validation; keep the
strict source separately for digest. Verify digest last.

The shared corpus contains a complete sanitized DTO with F1-F5/A1-A5 and
mutations for every model family. Semantic mutations get recomputed digests;
Python and TypeScript must agree on accept/reject outcomes.

### 21.4. R3 — Shared SSR fixture and shell parity

Files:

- add `shared/fixtures/company_public_h2_ssr_v1.json` and `.html`;
- `services/product_api/src/product_api/company_reports/company_card_v2/public_h2_document.py`;
- `services/product_api/tests_unit/test_company_card_v2_public_h2_document.py`;
- `services/web_ui/src/companyPublicH2/CompanyPublicH2Page.tsx`;
- `services/web_ui/src/companyPublicH2/bootstrap.tsx`;
- add `CompanyPublicH2Page.test.tsx`, `bootstrap.test.tsx`,
  `assetManifest.test.ts`.

Use fixed shell IDs `hero-status`, `narrative`, `requisites`, `finance`,
`arbitration`, `sources-limitations`, `neutral-actions`. Stop deriving anchors
from chart-level `block_order`. Render the complete factual surface from
specification section 21.3, all F/A coverage rows and their limitation links.
Use one unavailable-status fallback and identical SSR/React action order,
classes and hrefs; both lower action buttons retain the approved orange accent.

Generate a sanitized golden from fixed DTO, manifest, nonce and robots.
Backend requires byte-exact fixture equality. Frontend loads that same HTML,
records ordered parity surfaces, takes over and compares them after commit.
Bootstrap tests inject Document/crypto, prove zero fetch/XHR/beacon and prove
head preservation. Failure leaves SSR facts intact and changes only fixed
enhancement status text.

Product startup passes the already validated immutable asset manifest into
the renderer/request dependency. Per-request package rereads are removed and
covered by tests. Approved 409/503 error classes are preserved.

### 21.5. R4 — Responsive CTA and accessibility

Files:

- `services/web_ui/src/companyPublicH2/CompanyPublicH2Page.css`;
- `services/web_ui/src/companyPublicH2/CompanyPublicH2Page.tsx`;
- R3 component/bootstrap tests.

Implement mobile one-column stacked fixed CTA through 767px, horizontal fixed
tablet CTA at 768-1199px and 320px sticky rail from 1200px. Add same-layout
inert reserver, safe-area padding, 44px minimum targets, exact hover/active/
disabled/focus states, wrapping, scroll margins, focus/announcement behavior
and reduced-motion handling. Source/component tests prove breakpoint rules;
browser measurements prove computed layout and non-overlap.

### 21.6. R5 — Assignment-aware unit and integration matrices

Files:

- existing `persistence/public_documents.py`, `public_document_service.py`,
  `public_h1_service.py`, `public_h2_ssr_adapter.py`;
- add `tests_unit/test_company_report_public_document_persistence.py`;
- add `tests_unit/test_company_report_public_document_service.py`;
- update `tests_unit/test_company_report_public_documents.py`;
- add `tests/test_company_report_public_documents.py`;
- update affected route/read tests only for the matrix.

Compile/inspect the joined statement and prove one assignment-aware SELECT and
no second assignment read. Cover captured-row concurrency, exact assigned H1
versus active/latest, every corrupt H1 tuple/snapshot/path/time case, injected
exact H2, corrupt/cross-subject H2, and three independent old-digest fixtures.
Record canonical GET/HEAD SQL and reject DML; compare persistence row counts;
preserve exact H1 renderer bytes. Update stale H1 integration query-count
expectations caused by the intentional joined selector without weakening the
no-DML assertion.

### 21.7. R6 — Independent disposable PostgreSQL runner

Replace `scripts/run-iteration22-postgres-tests.ps1` with an iteration-22
container, labels, JUnit directory and credentials. It must not invoke an
earlier runner. Targeted mode runs exactly the five planned integration files;
Full runs all Product integration tests. Both independently validate import
path, fresh JUnit, nonzero test count and zero failures/errors/skips, and clean
only the exact matching labeled container.

### 21.8. R7 — Executable temporary-store release verification

Files:

- add `deploy/nginx/company_public_h2_release.py` as dependency-free testable
  release-decision core, or an equivalently shared testable core;
- update `install_company_public_h2_assets.sh` to use the same decisions while
  preserving lock/fsync/atomic/loopback safeguards;
- replace `test_company_public_h2_release.py` with executable temporary-store
  tests;
- update deploy workflow/docs only where invocation/order changes.

Seed a temporary three-manifest store and loopback asset server. Execute four
rotations and validate exact history, immutable identities, stored/response
hashes after each. Cover idempotency, pre-pointer failure preserving bytes,
immutable collision, fresh/one-predecessor/malformed history, missing/mismatch
manifest or asset, candidate/Product mismatch and unreachable asset. Parse
workflow stage order and prove every gate precedes Product replacement. Tests
must exercise release logic, not only search source strings, and never touch
production paths/processes/network.

### 21.9. R8 — Synthetic real-browser matrix

Extend `scripts/serve-iteration22-company-public-h2-fixture.py` for saved
artifact, deterministic fallback, gate-closed, partial/long-limitations and
long-string profiles. Build isolated assets and use only loopback.

For all five profiles at 320, 390, 768, 1024, 1199, 1200 and 1440 capture
ignored screenshots and measurements under `.tmp/iteration22-visual/`. Verify
scroll width, no overlap, hrefs, fixed/sticky/stacked computed layout, one
focusable primary CTA, inert reserver, minimum target size and zero forbidden
requests. At 390/1024/1440 also exercise keyboard anchors, 200% zoom and
reduced motion. Confirm no chart SVG/canvas. All 35 cells must pass.

### 21.10. Recovery changed-file manifest

Allowed paths are the preserved iteration-22 manifest plus:

- `deploy/nginx/company_public_h2_release.py` and executable release tests;
- both iteration-22 docs and `DEVFLOW_STATE.yaml`;
- independent iteration-22 PostgreSQL runner and real public-document
  integration test;
- public-document persistence/service unit tests;
- shared contract/SSR fixtures;
- TypeScript contract schema/semantics/tests;
- React page/bootstrap/asset-manifest tests;
- affected landing/router tests.

The existing `.github/workflows/deploy_prod.yml`, nginx configs/docs/tests,
Product H2 models/builder/manifest/renderer/selector/routes/startup/tests,
isolated Vite config/script, frontend H2 code and shared CJSON fixture remain
within the already approved iteration-22 manifest. Any other path requires an
explicit scope justification. `.tmp`, `dist*`, node_modules, JUnit,
screenshots, caches, `.env`, secrets and raw provider data are forbidden from
staged content.

### 21.11. Verification order

Record exact command, exit code and concise result.

Targeted Product:

    python -m pytest services/product_api/tests_unit/test_company_card_v2_public_h2.py services/product_api/tests_unit/test_company_card_v2_canonical_json.py services/product_api/tests_unit/test_company_card_v2_public_h2_ssr_adapter.py services/product_api/tests_unit/test_company_card_v2_public_h2_document.py services/product_api/tests_unit/test_company_card_v2_public_h2_asset_manifest.py services/product_api/tests_unit/test_company_report_public_document_persistence.py services/product_api/tests_unit/test_company_report_public_document_service.py services/product_api/tests_unit/test_company_report_public_documents.py services/product_api/tests_unit/test_company_report_public_routes.py -q

Targeted frontend:

    npm run test --prefix services/web_ui -- src/companyPublicH2 src/pages/CompanyLandingPage.test.tsx src/router/PublicCompanyReportFlow.test.tsx

Nginx and release:

    powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\nginx\test_product_api_conf.ps1
    python deploy/nginx/test_company_public_h2_release.py

Disposable PostgreSQL:

    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-iteration22-postgres-tests.ps1 -Mode Targeted
    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-iteration22-postgres-tests.ps1 -Mode Full

Repository regressions:

    python -m pytest services/product_api/tests_unit -q
    python -m pytest services/gateway_api/tests -q
    npm run lint --prefix services/web_ui
    npm run test --prefix services/web_ui
    npm run build --prefix services/web_ui

Additional:

    python -m compileall services/product_api/src/product_api shared
    git diff --check
    git status --short --branch

Browser fixture:

    npm run build --prefix services/web_ui
    python scripts/serve-iteration22-company-public-h2-fixture.py

The browser matrix is executed only against the loopback fixture server.

### 21.12. Final gate

Do not enter code review until all recovery stages and targeted checks pass.
Do not move to `ready_for_merge`, commit or push unless targeted and full
checks, both PostgreSQL modes, executable release suite and all 35 browser
cells pass; full diff/staged/privacy audits are clean; generated paths are not
staged; and independent code review has no blocking or substantial finding.

## 22. Blocker-only continuation implementation plan

Continuation-2 plan review: `VERDICT: APPROVED` (2026-08-25), with no
blocking, substantial or optional findings.

### 22.1. Recovery exception and execution rule

This is a new human-authorized DevFlow continuation for iteration 22. The
dirty worktree is an accepted preflight exception for this run only. Inventory
and preserve it; never reset, clean, discard, rewrite or recreate the branch.
Section 22 is independently reviewed before implementation.

Implement only C1-C5. Closed landing, security, startup manifest, CTA and
nginx behavior are regression-only. Do not start iteration 23 or introduce
charts, activation, production deploy execution, live provider/Gateway/AI,
production database, migration or dependency work.

### 22.2. Exact continuation file manifest

Docs/state:

    docs/development/DEVFLOW_STATE.yaml
    docs/development/iterations/iteration-22-company-card-v2-page-shell.md
    docs/development/plans/iteration-22-company-card-v2-page-shell.md

Shared fixtures:

    shared/fixtures/company_public_h2_contract_v1.json
    shared/fixtures/company_public_h2_contract_v1_cases.json
    shared/fixtures/company_public_h2_ssr_v1.json
    shared/fixtures/company_public_h2_ssr_v1.html

Contract and parity:

    services/product_api/src/product_api/company_reports/company_card_v2/public_h2_models.py
    services/product_api/src/product_api/company_reports/company_card_v2/public_h2_document.py
    services/product_api/tests_unit/test_company_card_v2_public_h2_contract_parity.py
    services/product_api/tests_unit/test_company_card_v2_public_h2_document.py
    services/web_ui/src/companyPublicH2/strictJson.ts
    services/web_ui/src/companyPublicH2/strictJson.test.ts
    services/web_ui/src/companyPublicH2/canonicalJson.ts
    services/web_ui/src/companyPublicH2/canonicalJson.test.ts
    services/web_ui/src/companyPublicH2/contract.ts
    services/web_ui/src/companyPublicH2/contractSchema.ts
    services/web_ui/src/companyPublicH2/contractSemantics.ts
    services/web_ui/src/companyPublicH2/contract.test.ts
    services/web_ui/src/companyPublicH2/presentation.ts
    services/web_ui/src/companyPublicH2/CompanyPublicH2Page.tsx
    services/web_ui/src/companyPublicH2/CompanyPublicH2Page.test.tsx
    services/web_ui/src/companyPublicH2/bootstrap.tsx
    services/web_ui/src/companyPublicH2/bootstrap.test.tsx

Public-document matrix and narrowly demonstrated fixes:

    services/product_api/src/product_api/company_reports/persistence/public_documents.py
    services/product_api/src/product_api/company_reports/public_document_service.py
    services/product_api/src/product_api/company_reports/public_h1_service.py
    services/product_api/src/product_api/company_reports/company_card_v2/public_h2_ssr_adapter.py
    services/product_api/src/product_api/company_reports/company_card_v2/service.py
    services/product_api/src/product_api/routers/company_reports_public.py
    services/product_api/tests_unit/test_company_report_public_document_persistence.py
    services/product_api/tests_unit/test_company_report_public_document_service.py
    services/product_api/tests_unit/test_company_report_public_documents.py
    services/product_api/tests/test_company_report_public_documents.py

Release implementation/tests/order:

    deploy/nginx/company_public_h2_release.py
    deploy/nginx/install_company_public_h2_assets.sh
    deploy/nginx/test_company_public_h2_release.py
    .github/workflows/deploy_prod.yml

Browser fixture/harness:

    scripts/serve-iteration22-company-public-h2-fixture.py
    scripts/run-iteration22-company-public-h2-browser-matrix.mjs
    scripts/iteration22-company-public-h2-browser-probe.mjs

Existing runner, Product startup/manifest, nginx configs/tests, CSS, landing,
router and package files are regression-only unless a required check exposes a
direct continuation defect. The dedicated HTML/CSS may receive only a proven
overflow/accessibility correction. ROADMAP, migrations, Claims, auth, SPA root
and dependencies are unchanged. Any additional path requires a new scope
decision. `.tmp`, `dist*`, screenshots, JUnit, caches, node_modules, `.env`,
secrets and raw data are never staged.

### 22.3. C0 — Inventory and blocker reproduction

Record branch/base, all paths and diff stat without cleaning. Reproduce
TS2352, incomplete F/A corpus, absent successful takeover parity, empty-DB
integration matrix, helper-only/zero-test release evidence, invalid fixture
profiles and absent 35-cell harness. Record H1 fixture/renderer hashes and the
green closed regressions. Confirm the fixture imports `shared` and Product
from this worktree and capture the current 320px overflow baseline.

### 22.4. C1 — Dense schema/corpus parity and TypeScript build

Implement one robust strict integer discriminator shared by parser,
canonicalization, contract and presentation; raw JSON cannot spoof it.
Preserve generic CJSON normalization while public-H2 rejects non-NFC DTO
scalars. Split full canonical bytes/cap from projection digest bytes.

Implement all Python public-H2 structural validators/types in
`contractSchema.ts`, exact existing semantics in `contractSemantics.ts`, and
ordered parse/schema/semantics/cap/digest in `contract.ts`. Decimal operations
use BigInt scale alignment. Do not add semantics absent from Python.

Create a dense DTO and shared JSON-pointer corpus with raw patch values,
closed constraint IDs and recomputed digests. Python uses strict JSON;
TypeScript uses strict token trees. Both prove identical IDs/outcomes with zero
skips and cover every common/F/A/root family plus legal null/boundary and
adjacent rejects. Large cap boundaries are generated in tests. Add Python
canonical-path/INN binding. Fix TS2352 through actual narrowing.

Required before C2:

    npm run build --prefix services/web_ui
    npm run test --prefix services/web_ui -- src/companyPublicH2/strictJson.test.ts src/companyPublicH2/canonicalJson.test.ts src/companyPublicH2/contract.test.ts
    python -m pytest services/product_api/tests_unit/test_company_card_v2_public_h2_contract_parity.py services/product_api/tests_unit/test_company_card_v2_canonical_json.py -q

### 22.5. C2 — Byte fixture and successful takeover parity

Generate exact SSR bytes from the dense DTO with fixed manifest/nonce/robots.
Tests compare exact `.html` bytes and never rewrite fixtures. Render fixed
sections, approved facts and all coverage/count/scope/limitation targets
without chart art.

Use a shared ordered parity collector. Bootstrap loads exact fixture HTML,
captures head/SSR vector, installs throwing network spies, validates state,
commits React synchronously, compares React vector/text/head exactly and marks
enhancement after success. Restore SSR on mismatch/error. React returns direct
children. Test fixed missing status, bindings, zero network and schema/
semantic/digest failure preservation. Add target focus/live announcement.

Required before C3:

    python -m pytest services/product_api/tests_unit/test_company_card_v2_public_h2_document.py -q
    npm run test --prefix services/web_ui -- src/companyPublicH2/CompanyPublicH2Page.test.tsx src/companyPublicH2/bootstrap.test.tsx
    npm run build --prefix services/web_ui

### 22.6. C3 — Real PostgreSQL public-document matrix

Unit persistence captures/compiles the actual SQLAlchemy `Select`, proves one
execute and exact joins. Service units cover captured-row/no-reread, complete
unknown/incomplete/mismatch, H2 statuses and exact-H2 SQLAlchemy 503.

Replace empty-DB smoke with committed fixtures for assigned H1 versus active/
latest, valid injected H2, representable corruption and three independent old-
digest cases. Override generic route session/cohort at its actual import point;
seed and request sessions are separate.

Around each endpoint call, classify SQL, prove one assignment joined SELECT
and no reread, reject DML/DDL and compare every Product table count plus exact
relevant row bytes before/after. Verify H1 bytes, H2 noindex/report/Claims and
no activation. Production assignment stays closed.

Required before C4:

    python -m pytest services/product_api/tests_unit/test_company_report_public_document_persistence.py services/product_api/tests_unit/test_company_report_public_document_service.py services/product_api/tests_unit/test_company_report_public_documents.py -q
    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-iteration22-postgres-tests.ps1 -Mode Targeted

### 22.7. C4 — Shared actual installer path

Move strict manifest/source/history parsing, identity comparison, collision-
safe immutable copy, rotation, stored/loopback verification, failure injection,
fsync and atomic pointer replacement into one importable installer/CLI. Shell
keeps resolved-path/host guard and lock, then delegates; remove duplicated
`mv -n` copy/rotation decisions.

Tests use a temporary source/store and `ThreadingHTTPServer`, invoking the same
install path four times. Validate exact history/stored/response hashes after
each rotation/idempotency and every specified failure with pointer preservation.
Manifest parsing mirrors Product exact keys/media type/source graph. Execute
via pytest explicitly; direct zero-test Python execution is not evidence.

Workflow builds the candidate Product image, extracts its packaged manifest
and compares identity before install; all release gates precede migration/up.
Tests prove complete step order. No workflow/host is executed.

Required before C5:

    python -m pytest deploy/nginx/test_company_public_h2_release.py -q -p no:cacheprovider

### 22.8. C5 — Valid profiles and executable 35-cell matrix

Fix fixture imports to the current worktree. Build five profiles via model
dump, consistent mutation, digest recomputation and full Python revalidation;
prove all digest-match, TypeScript-parse and differ observably.

Provide a no-download local-browser matrix using CDP or the supported Codex
browser client plus checked-in pure probe. It starts/stops only its own
loopback processes/profile, blocks non-loopback traffic and executes exact
5x7 widths. The fixture server logs every request by matrix run; allow only
HTML, content-addressed assets and an explicitly served/favicon data URL.
Per-cell PNG/JSON and aggregate evidence enforce takeover/head, layout/
overflow/overlap, links, focus/reserver/44px, coverage/limitations, no chart
art, network and console rules. Fix the proven 320px overflow without changing
the approved CTA contract. At 390/1024/1440 also verify keyboard anchors, 200%
zoom and deterministic reduced motion. Exact aggregate: 35 executed/passed,
zero failed/skipped.

Required before review:

    npm run build --prefix services/web_ui
    node scripts/run-iteration22-company-public-h2-browser-matrix.mjs

### 22.9. Final verification order

Blocker-targeted:

    python -m pytest services/product_api/tests_unit/test_company_card_v2_public_h2_contract_parity.py services/product_api/tests_unit/test_company_card_v2_canonical_json.py services/product_api/tests_unit/test_company_card_v2_public_h2_document.py services/product_api/tests_unit/test_company_report_public_document_persistence.py services/product_api/tests_unit/test_company_report_public_document_service.py services/product_api/tests_unit/test_company_report_public_documents.py -q
    npm run test --prefix services/web_ui -- src/companyPublicH2/strictJson.test.ts src/companyPublicH2/canonicalJson.test.ts src/companyPublicH2/contract.test.ts src/companyPublicH2/CompanyPublicH2Page.test.tsx src/companyPublicH2/bootstrap.test.tsx
    npm run build --prefix services/web_ui
    python -m pytest deploy/nginx/test_company_public_h2_release.py -q -p no:cacheprovider
    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-iteration22-postgres-tests.ps1 -Mode Targeted
    node scripts/run-iteration22-company-public-h2-browser-matrix.mjs

Closed regressions:

    npm run test --prefix services/web_ui -- src/pages/CompanyLandingPage.test.tsx src/router/PublicCompanyReportFlow.test.tsx
    powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\nginx\test_product_api_conf.ps1

Repository-required:

    python -m pytest services/product_api/tests_unit -q
    python -m pytest services/gateway_api/tests -q
    npm run lint --prefix services/web_ui
    npm run test --prefix services/web_ui
    npm run build --prefix services/web_ui
    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-iteration22-postgres-tests.ps1 -Mode Full
    python -m compileall services/product_api/src/product_api shared
    git diff --check
    git status --short --branch

### 22.10. Review and final gate

Do not enter code review until C1-C5 and targeted commands pass. Reviewer gets
corpus coverage, parity/head/network vectors, SQL/no-DML/row/H1 evidence,
installer rotation/failure/hash evidence, 35-cell JSON/screenshots, full check
results and changed/privacy/staged audits. Do not move to `ready_for_merge`,
commit or push unless all targeted/full checks, both PostgreSQL modes, release,
browser matrix and `git diff --check` pass and review has no blocking or
substantial finding.
