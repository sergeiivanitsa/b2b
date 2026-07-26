# Iteration 12 — implementation plan

## 1. Changed-file manifest

| File | Change |
|---|---|
| `docs/development/iterations/iteration-12-seo-publishing.md` | Approved specification. |
| `docs/development/plans/iteration-12-seo-publishing.md` | This plan. |
| `services/product_api/alembic/versions/0014_company_report_publications.py` | Append-only control/publication/batch/item/journal schema. |
| `services/product_api/src/product_api/settings.py` | SEO hard gate, base URL, batch and sitemap validators. |
| `services/product_api/.env.example` | Safe disabled SEO defaults. |
| `services/product_api/src/product_api/company_reports/persistence/models.py` | Publication ORM models, checks, FKs and indexes. |
| `services/product_api/src/product_api/company_reports/persistence/publications.py` | Control, manifest, claim/cursor, publication and journal repository. |
| `services/product_api/src/product_api/company_reports/persistence/__init__.py` | Narrow exports. |
| `services/product_api/src/product_api/company_reports/seo.py` | Pure projection, policy, metadata, HTML/XML rendering. |
| `services/product_api/src/product_api/company_reports/seo_publish.py` | Manual CLI. |
| `services/product_api/src/product_api/routers/company_reports_public.py` | Anonymous SSR, robots and sitemap routes. |
| `services/product_api/src/product_api/main.py` | Router registration. |
| `services/product_api/tests_unit/test_company_report_seo.py` | Policy/render/privacy/metadata unit tests. |
| `services/product_api/tests_unit/test_company_report_publications.py` | Repository state/idempotency unit tests. |
| `services/product_api/tests_unit/test_company_report_seo_publish.py` | CLI tests. |
| `services/product_api/tests_unit/test_company_report_seo_settings.py` | Settings tests. |
| `services/product_api/tests_unit/test_company_report_public_routes.py` | Mocked HTTP contract tests. |
| `services/product_api/tests_unit/test_company_report_seo_crawl.py` | Crawl/canonical/sitemap consistency tests. |
| `services/product_api/tests/test_company_report_publications.py` | PostgreSQL race, manifest and replacement integration tests. |
| `services/product_api/tests/test_company_report_publications_migration.py` | Disposable PostgreSQL migration/schema/seed test. |
| `services/product_api/tests/conftest.py` | FK-safe cleanup for new tables. |
| `deploy/nginx/product_api.conf` | Auth-aware company routing and public SEO proxy routes. |
| `deploy/nginx/install_product_api_conf.sh` | Explicit human validate/install/rollback/reload handoff. |
| `deploy/nginx/test_product_api_conf.ps1` | Static nginx routing contract check. |

`deploy/nginx/pork.su.conf`, `.github/workflows/deploy_prod.yml`,
`docker-compose.product.yml`, Web UI, Gateway, authenticated CompanyReport API,
provider, normalizers, signals и scoring не меняются. Existing Product image
and `.env.product` wiring already carry Settings defaults; no service or deploy
action is added.

## 2. Stage 1 — migration and persistence

1. Add five ORM models and migration with the exact specification constraints.
2. Seed singleton control as `paused`; preserve all existing report tables/data.
3. Implement deterministic latest-finalized-per-subject selection excluding an
   already terminal identical report/hash/policy.
4. Materialize at most N batch items in one transaction before `running`.
5. Implement row-locked control/batch/item claim, pause/resume, terminal
   finalize, and PostgreSQL-identity generation-fenced publication upsert:
   conditional subject replacement is permitted only for a newer persisted
   batch generation; safe stale reread is a terminal no-op.
6. Store immutable `published_lastmod` only from report generated/finished time.
7. Keep journal reason/action allowlists and never persist raw/error text.

## 3. Stage 2 — pure SEO policy and rendering

1. Build typed allowlisted projection directly from immutable snapshot and
   verify stored hash.
2. Reuse existing evaluate/score functions only for the `insufficient_data`
   gate; do not change or persist their result.
3. Implement identity, finance/arbitration substantive predicates and explicit
   partial sufficiency.
4. Generate slug, actual-section metadata, canonical and robots
   deterministically.
5. Render escaped semantic HTML and XML without template dependency, JSON state,
   JSON-LD, AI or SPA script.
6. Assert forbidden keys recursively and preserve exact decimal strings,
   missing and unknown units.

## 4. Stage 3 — routes and nginx

1. Add exact anonymous routes:
   - `GET /company/{company_key}`;
   - `GET /robots.txt`;
   - `GET /sitemaps/index.xml`;
   - `GET /sitemaps/{chunk}.xml`.
2. Reject query parameters and invalid grammar before repository lookup.
3. Implement exact `200/301/404/500/503` and matching robots headers/meta.
4. Keep GET read-only and sitemap filtered through the same policy.
5. Add nginx internal auth subrequest: only `401` reaches SSR; `2xx` reaches
   SPA; other states do not.
6. Add explicit manual install script and static PowerShell contract test.

## 5. Stage 4 — CLI

1. Add `control resume|pause` with hard-gate and singleton row locking.
2. Add bounded `run --limit N`.
3. Add `batch pause|resume --batch-id`.
4. Process immutable ordinal manifest with claim token and cursor.
5. Handle concurrency/unique conflicts by conditional update and exact reread.
6. Prove no provider, AI, job enqueue, browser or network call.

## 6. Stage 5 — tests

| Surface | Required cases |
|---|---|
| Policy | Complete/partial eligible; partial insufficient; both usable flags; status/requisites-only thin; finance/arbitration substantive; failed/pending; insufficient scoring. |
| Privacy/render | Forbidden keys absent; exact decimals; missing/unit/currency; escaping; deterministic metadata and no JSON-LD. |
| HTTP | Anonymous exact page; wrong slug redirect; query/invalid/missing/pending/failed 404; infra 503; corruption 500; legacy 200 noindex; no writes. |
| Sitemap/crawl | Same policy, canonical-only, chunks, deterministic order, immutable lastmod, noindex exclusion, no URL combinations. |
| Persistence | Schema constraints, paused seed, one subject/canonical, bounded immutable manifest, journal policy key, same/new hash/policy replacement. |
| Concurrency | Run/resume/pause races, ordinal at-most-once, unique conflict reread, no post-pause claim, limit never exceeded. |
| CLI | Hard gate/control, limit bounds, global and batch pause/resume, completed rerun, no external/domain-generation calls. |
| Nginx | Auth 2xx SPA, only 401 SSR, failure isolation, no User-Agent branch, source-of-truth and public locations. |
| Regression | Existing authenticated CompanyReport API/page, Claims, Gateway unchanged. |

## 7. Verification commands

Targeted unit and crawl:

```text
python -m pytest services/product_api/tests_unit/test_company_report_seo.py services/product_api/tests_unit/test_company_report_publications.py services/product_api/tests_unit/test_company_report_seo_publish.py services/product_api/tests_unit/test_company_report_seo_settings.py services/product_api/tests_unit/test_company_report_public_routes.py services/product_api/tests_unit/test_company_report_seo_crawl.py -q
```

Targeted PostgreSQL when available:

```text
python -m pytest services/product_api/tests/test_company_report_publications.py services/product_api/tests/test_company_report_publications_migration.py -q
```

Nginx contract:

```text
powershell -ExecutionPolicy Bypass -File deploy/nginx/test_product_api_conf.ps1
```

Repository-required checks from `C:\GPT`:

```text
python -m pytest services/product_api/tests_unit -q
python -m pytest services/gateway_api/tests -q
npm run lint --prefix services/web_ui
npm run test --prefix services/web_ui
npm run build --prefix services/web_ui
python -m pytest services/product_api/tests -q
git diff --check
```

Full Product API integration requires available migrated PostgreSQL. No Python
lint/type-check command exists. No production migration, nginx installation,
rollout activation, batch run, sitemap submission or network call belongs to
the implementation workflow.

## 8. Completion gate

- Spec/plan reviewer findings are closed.
- Targeted SEO/crawl and all applicable regression checks pass.
- Migration remains append-only and initial control remains paused.
- Diff contains no secrets, raw payload or unrelated changes.
- Independent code review has no blocking/substantial finding.
- State becomes `ready_for_merge` only after verification.
