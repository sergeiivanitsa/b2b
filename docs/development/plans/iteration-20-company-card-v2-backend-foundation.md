# Итерация 20 — Company Card v2 backend foundation: implementation plan

ID: `20`

Slug: `company-card-v2-backend-foundation`

Статус плана: `approved_after_single_correction`

## 1. Constraints

- Работать только в feature worktree/branch и не менять `ROADMAP.md`.
- Не выполнять live/provider/FNS/Gateway/AI calls, deploy или production DB
  operation.
- Не добавлять dependencies.
- Реализовывать поведение вместе с тестами.
- H1, signals, scoring и Claims semantics являются compatibility surfaces, а
  не refactor targets.
- Commit/push допустимы только после всех проверок и независимого `READY`.

## 2. Exact changed-file manifest

### Documentation/state

```text
docs/development/DEVFLOW_STATE.yaml
docs/development/iterations/iteration-20-company-card-v2-backend-foundation.md
docs/development/plans/iteration-20-company-card-v2-backend-foundation.md
```

### Settings, provider and routes

```text
services/product_api/.env.example
services/product_api/src/product_api/settings.py
services/product_api/src/product_api/main.py
services/product_api/src/product_api/providers/datanewton/models.py
services/product_api/src/product_api/providers/datanewton/client.py
services/product_api/src/product_api/routers/company_reports.py
services/product_api/src/product_api/routers/company_report_presentations.py
```

### Company Card v2 domain

```text
services/product_api/src/product_api/company_reports/company_card_v2/__init__.py
services/product_api/src/product_api/company_reports/company_card_v2/models.py
services/product_api/src/product_api/company_reports/company_card_v2/decimal_transport.py
services/product_api/src/product_api/company_reports/company_card_v2/canonical_json.py
services/product_api/src/product_api/company_reports/company_card_v2/evidence.py
services/product_api/src/product_api/company_reports/company_card_v2/counterparty.py
services/product_api/src/product_api/company_reports/company_card_v2/finance.py
services/product_api/src/product_api/company_reports/company_card_v2/privacy.py
services/product_api/src/product_api/company_reports/company_card_v2/arbitration.py
services/product_api/src/product_api/company_reports/company_card_v2/public_h2_models.py
services/product_api/src/product_api/company_reports/company_card_v2/public_h2.py
services/product_api/src/product_api/company_reports/company_card_v2/service.py
```

### Persistence, lifecycle and compatibility

```text
services/product_api/src/product_api/company_reports/persistence/models.py
services/product_api/src/product_api/company_reports/persistence/jobs.py
services/product_api/src/product_api/company_reports/persistence/repository.py
services/product_api/src/product_api/company_reports/persistence/public_h1.py
services/product_api/src/product_api/company_reports/persistence/publications.py
services/product_api/src/product_api/company_reports/persistence/v3.py
services/product_api/src/product_api/company_reports/persistence/presentations.py
services/product_api/src/product_api/company_reports/persistence/__init__.py
services/product_api/src/product_api/company_reports/service.py
services/product_api/src/product_api/company_reports/worker.py
services/product_api/src/product_api/claims/company_report_handoff.py
services/product_api/alembic/versions/0016_company_card_v2_foundation.py
```

`aggregate.py`, H1 projection models, legacy normalizers, signals and scoring
не входят в manifest.

### Unit tests and synthetic fixtures

```text
services/product_api/tests_unit/test_datanewton_provider_lexical_transport.py
services/product_api/tests_unit/test_company_report_persistence_serialization.py
services/product_api/tests_unit/test_company_report_repository_queries.py
services/product_api/tests_unit/test_company_report_jobs.py
services/product_api/tests_unit/test_company_report_worker.py
services/product_api/tests_unit/test_company_report_public_h1_service.py
services/product_api/tests_unit/test_company_report_publications.py
services/product_api/tests_unit/test_company_reports_api.py
services/product_api/tests_unit/test_claims_company_report_handoff.py
services/product_api/tests_unit/test_company_card_v2_decimal_transport.py
services/product_api/tests_unit/test_company_card_v2_canonical_json.py
services/product_api/tests_unit/test_company_card_v2_counterparty.py
services/product_api/tests_unit/test_company_card_v2_finance.py
services/product_api/tests_unit/test_company_card_v2_arbitration.py
services/product_api/tests_unit/test_company_card_v2_privacy.py
services/product_api/tests_unit/test_company_card_v2_serialization.py
services/product_api/tests_unit/test_company_card_v2_public_h2.py
services/product_api/tests_unit/test_company_card_v2_presentations.py
services/product_api/tests_unit/test_company_card_v2_public_h2_side_effects.py
services/product_api/tests_unit/fixtures/company_reports/snapshot_v2_exact.json
services/product_api/tests_unit/fixtures/company_card_v2/*
```

Existing `snapshot_v1_legacy.json` remains byte-for-byte unchanged.

### PostgreSQL integration/runbook

```text
services/product_api/tests/test_company_card_v2_migration.py
services/product_api/tests/test_company_report_presentations.py
services/product_api/tests/test_company_report_public_h2_reads.py
services/product_api/tests/test_company_report_publications.py
services/product_api/tests/test_company_report_publications_migration.py
services/product_api/tests/test_company_reports_api.py
services/product_api/tests/test_company_report_public_h1_reads.py
services/product_api/tests/test_claims_company_report_handoff.py
scripts/run-iteration20-postgres-tests.ps1
```

Any expansion outside this manifest stops implementation for scope review.

## 3. Stage A — compatibility locks

Record branch/base/diff, v1 fixture and H1 golden hashes, current Alembic head
and targeted H1/jobs/Claims baseline. Add failing tests that lock permanent H1
POST-v2 behavior, v3 exclusion from H1 queries, exact v1/v2 parser behavior
and default-off H2 before production edits.

## 4. Stage B — lexical Decimal transport

Extend provider result additively with an in-memory lexical manifest and
validity flag. Parse exact response bytes with stdlib JSON callbacks, reject
duplicate keys/nonfinite constants, escape JSON pointers and verify topology;
do not persist/log the manifest or break legacy consumers on failure.

Implement pure `company_card_source_decimal_v1`. Test integer/fraction/string,
signed and negative-zero behavior, exact 96/97 digit, 32/33 fractional and
128/129 byte boundaries, all forbidden lexical forms, float/bool rejection,
pointer mismatch and the complete source-bytes → Decimal → snapshot → Chart
Facts → DTO chain.

## 5. Stage C — strict v3 models/serialization

Add frozen `extra=forbid` snapshot, counterparty, finance/arbitration basis,
Chart Facts and limitation models. Implement separate v3 serializer/parser/
hash functions; do not widen the legacy parser. Verify discriminator,
round-trip/fixed hash, cross-parser rejection, nested mutation, Chart Facts
hash, forbidden keys and privacy markers.

## 6. Stage D — counterparty parser

Build a v3-local observed-shape parser with two outputs: approved core and safe
gate metadata. Validate exact paths/types and caps, discard personal IDs at the
boundary, preserve approved address behavior, and emit limitations for hidden
sections. Test unknown/invalid/missing/empty shapes, contacts prohibition and
absence of every deferred leaf from public DTO.

## 7. Stage E — finance basis and Chart Facts

Index exact form/code/year leaves from the lexical manifest, classify the six
closed cell states, collapse identical nonzero duplicates and mark conflicts.
Convert only policy-v2 nonzero Decimal inputs. Build F1–F5 with deterministic
windows and pure Decimal math; persist/hash basis and Chart Facts separately.

Cover all twelve codes, missing/zero/nonzero/conflict, signs, sparse series,
positive/zero/negative denominators, seven-year F5, no current-time anchor,
precision/sign preservation and the rule that any required provider zero
creates limitation/null geometry rather than public zero.

## 8. Stage F — arbitration foundation

Ship a gate-closed evidence registry and prove the network callback is never
constructed/invoked. With synthetic verified registry and in-memory pages,
implement pagination caps, drift/non-progress, row/canonical-byte limits,
sanitization, deterministic dedup/conflict removal, counters/reasons, roles,
dates, HMAC masking and public ordinal helpers.

Mandatory boundaries include 999/1000/1001 rows, equality/one-byte-over basis
and case caps, early/mid-page stops with later-row non-selection, identical/
conflicting duplicates, equal amount/different keys, all role sets,
missing/rotated keys, date cases and exact HMAC/order goldens. Public tests
always assert null A1–A5 and no private markers.

Add the exact alias matrix: later update; equal update/later start; equal dates/
normalized Unicode-scalar name; final internal-case-identity tie; null dates;
decomposed/precomposed equivalence; and no alias for natural/unknown. Add the
visible-number matrix: shipped gate closed; synthetic exact path open;
missing/blank/invalid; case_id-only; id-only; and proof that dedup identity is
never substituted or found at a public boundary.

## 9. Stage G — closed H2 DTO/digest

Implement strict leaf models rather than dictionaries: scalar/NFC/path rules,
exact cardinality/order, money/geometry invariants, capability matrix,
canonical JSON, digest, byte caps and recursive privacy scan. Builder accepts
only a validated narrative-binding protocol and never generates prose.

Golden fixtures cover legacy v1/v2 noindex, full/sparse/signed v3, null
arbitration, zero-unverified finance, Unicode/CJSON, unknown fields, cardinality
and ordering, exact size boundaries, digest removal/insertion and no-float/
canonical-Decimal rules.

## 10. Stage H — migration

Create only `0016_company_card_v2_foundation` after revision `0015`. Add
profile/contract/generation columns to reports/jobs and job fence generation;
backfill exact v1/v2 legacy rows before non-null/check constraints and abort on
unsupported historical versions. Retain one-active-job-per-subject.

Create immutable presentation, pin, staged-pointer, assignment and assignment-
journal tables with composite FKs, discriminated H1/H2 checks, positive
generations and append-only uniqueness. Create no H2 assignment/activation.

Import existing valid active H1 publications into immutable H1 pin generations
equal to their batch generation, preserving exact report/hash/policy/path/
indexability/lastmod. Paused/disabled rows remain but are not imported. A
corrupt active snapshot/hash/identity/path aborts the whole upgrade; the failed
upgrade leaves revision and legacy rows unchanged. Re-upgrade from 0015
recreates the same pin identities and no assignment/H2 row.

Migration tests use separate disposable databases for: valid active import;
paused/disabled preservation without import; atomic failure of corrupt active
hash/identity/path with unchanged revision and legacy rows; absence of H2/
assignment rows; downgrade legacy-row preservation; deterministic re-upgrade;
and runtime mirroring of a post-upgrade H1 publication.

Disposable migration tests upgrade seeded `0015` v1/v2/pending rows to `0016`,
inspect types/constraints/FKs/indexes/backfill, reject invalid combinations,
downgrade to `0015`, verify legacy rows survive, and upgrade again. No unknown
or production DB is used.

## 11. Stage I — jobs/worker/presentation lifecycle

Refactor job internals around an immutable writer decision while retaining the
H1 wrapper signature. H1 supplies constant v2; H2 supplies server cohort.
Reuse compares all decision fields; claim/heartbeat/finalization compare the
full fence. Existing H1 builder/signals/scoring run only for H1. H2 uses only
an injected v3 builder selected from stored profile; unknown profile fails
without provider work. Runtime H2 remains off.

Presentation creation stores one opaque exact report binding; status joins by
presentation ID and never queries latest/cohort. Cover the flag-flip and mixed-
job matrices.

## 12. Stage J — H1 query compatibility

Change selection predicates only: H1 finalized/status/publication fallback
remain v1/v2 H1-only, v3-only history is not eligible, an H1 POST can create a
new v2 run for a v3-only subject, and the active H1 pin remains first choice.
H1 DTO/golden/header output must remain unchanged.

In H1 publication batching, filter v1/v2 profile/contract-compatible rows in
SQL before per-subject latest selection and order by generated time then ID.
Mirror each successful active H1 publication to the same immutable pin
generation in the same transaction; exact retry is idempotent and conflict
rolls back publication/journal changes. Test newer-v3/older-v2, v3-only,
v2/v1 ordering, new generation, retry and mirroring conflict.

## 13. Stage K — H2 GET/HEAD

Implement request order: query rejection, INN, Accept/rate limit, default-off
cohort, exact stored binding/pin/report, hashes/narrative/DTO/digest, one
serialization. Disabled returns before DB. HEAD reuses exact selection and
drops only the body.

Instrument sessions and patch provider/worker/queue/signals/scoring/AI to fail
if touched. Test the full HTTP/error/header matrix and attempts to select facts
through query/header/cookie/language. Reads may issue SELECTs only and no DML or
session mutation.

Resolver precedence is exact active H2, exact staged H2, then independently
validated latest H1-compatible v1/v2 legacy preview. It never selects global
latest v3. Exact H2 corruption is terminal; a corrupt legacy candidate may be
skipped for an older independently valid v1/v2. API tests cover v1-only,
v2-over-v1, unpinned-v3-over-v2, exact-v3-over-v2, corrupt exact-H2, corrupt
newest-v2/valid-v1, and v3-only. Assert report/version, legacy capability/
scope/noindex, HEAD parity and zero external/write side effects.

## 14. Stage L — pins and assignment foundation

Implement append H1/H2 pin, staged pointer, exact assignment resolution and
internal CAS. Pins are immutable; exact repeats are idempotent and changed
payload creates a new generation. Staged pointer is H2-only. CAS validates the
exact pin/report/hash and stale expected generation conflicts. No route exposes
CAS and no production assignment is created. PostgreSQL tests cover
concurrency, uniqueness and composite FK behavior.

## 15. Stage M — Claims/privacy

Implement separate `validate_private_arbitration_basis` and
`assert_public_boundary_safe` policies. The former path-allows only exact
internal case identity/full HMAC shapes; the latter receives private taint
values before discard and scans DTO, JSON, headers, captured logs and Claims.
Never weaken the public scanner because the private basis allows HMAC.

Dispatch Claims exact-report parsing by raw snapshot version. Cover exact
v1/v2/v3, pending/failed, hash/identity mismatch, copied snapshot, hidden v3
facts and unchanged idempotency. Scan snapshots, DTO/JSON, HEAD headers,
captured logs and Claims prefill for raw/private/secret/contact markers.

## 16. Disposable PostgreSQL

Create the iteration-20 runbook with iteration-17 safety properties: local
`postgres:16-alpine`, `--pull=never`, loopback dynamic port, tmpfs/no volume,
unique name/labels, exact cleanup target, generated credentials, `.env`
rejection, external services/H2 activation forced off, worktree import proof,
JUnit required with tests > 0 and zero failure/error/skip.

Targeted mode runs the new migration/presentation/public-H2 tests plus affected
H1 publication/migration, API/read and Claims handoff integration tests. Full mode runs all Product
API integration tests. Evidence is confined to ignored
`.tmp/iteration20-postgres/{targeted,full}.xml`.

## 17. Verification

Targeted unit matrix includes every new v2 module plus affected provider,
persistence/jobs/worker, H1 API/service and Claims tests. Mandatory final
commands:

```powershell
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

No Python lint/type-check is claimed because none is configured.

## 18. Rollback, dependencies and review gate

Before activation rollback is configuration-only because H2 flags stay false.
No production migration/downgrade is authorized. Disposable/local downgrade
removes only iteration-20 schema after proving legacy rows survive.

No dependency is needed: stdlib JSON/Decimal/hash/HMAC, existing Pydantic,
SQLAlchemy/Alembic and pytest/httpx cover the scope.

Review must reject any visible deferred counterparty fact, numeric provider
zero, populated A1–A5, flag bypass of evidence, float truth, v3 shadowing H1,
read-path provider/AI/queue/write, assignment activation route, iteration 21+
work, Roadmap/deploy/production DB change, missing privacy scan or missing
disposable PostgreSQL proof.
