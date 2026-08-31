# Итерация 20 — Backend и данные Company Card v2

ID: `20`

Slug: `company-card-v2-backend-foundation`

Scope version: `narrowed_fail_closed_v1`

Public contract: `company_public_h2_v1`

Snapshot writer version: `3`

Статус спецификации: `approved_after_single_correction`

Production activation: `NOT AUTHORIZED`

## 1. Цель

Реализовать default-off backend foundation Company Card v2 без открытия
незакрытых evidence gates и без изменения production-default H1. Отдельный
H2/v3-контур должен:

- строго и раздельно читать immutable snapshots `1`, `2` и `3`;
- сохранять v3 без выдачи его за v2;
- оставить H1 writer/API, signals, scoring, publication и Claims semantics
  совместимыми;
- добавить fenced v3 writer, presentation lifecycle, immutable Chart Facts,
  H2 pins и assignment foundation без activation route;
- публиковать только закрытый `company_public_h2_v1` DTO;
- допускать finance numeric facts только после lossless lexical Decimal
  transport и только для явных ненулевых значений;
- реализовать strict observed-shape counterparty parser, но публично оставлять
  только уже утверждённые core identity/address;
- реализовать fixture-only arbitration bounds, dedup, exact-INN role и masking,
  блокируя provider call до сети;
- доказать поведение unit- и disposable-PostgreSQL-тестами.

H1 остаётся production resolver и rollback path. Итерация не является rollout.

## 2. Нормативные источники

При конфликте применяются по приоритету:

1. `decisions/iteration-20-owner-scope-decision-v1.md`;
2. `evidence/iteration-19-company-card-v2/iteration-20-gate-readiness-v3.md`;
3. закрытые leaf-level contracts разделов 26–31 iteration 19;
4. architecture/privacy ADR iteration 19;
5. evidence v2/v3;
6. существующие H1/v1/v2 runtime contracts и tests.

Утверждённая матрица:

```text
company_card_v2_feature_default = off
company_card_v2_writer_default = off
production_provider_operation = disabled
production_publication = disabled

finance_unit_policy = datanewton_finance_thousand_rub_v2
finance_nonzero = available only after lexical transport verification
finance_zero = zero_unverified, never numeric/public input
finance_missing = missing, never zero

counterparty_new_fields = parser-only, public hidden
arbitration_provider_envelope = gate_closed
arbitration_a1_a5 = public null/gate_closed
```

## 3. Scope

1. Separate strict v1/v2/v3 snapshot readers and serializers.
2. Permanent H1/v2 writer decision and default-off H2/v3 decision.
3. One-active-job-per-subject fencing across mixed H1 and H2 jobs.
4. Immutable presentation identity bound to exact subject/report/contract.
5. Immutable v3 snapshot, snapshot hash, Chart Facts version/hash and
   evidence/privacy versions.
6. H2 pin/staged-pointer/assignment/CAS persistence foundation without public
   mutation or activation.
7. Closed `company_public_h2_v1` models and canonical digest.
8. `GET` and `HEAD /company-reports/{inn}/public-h2` with no read-side effects.
9. Exact lexical Decimal ingestion and finance nonzero-only policy.
10. Strict observed-shape counterparty parser with public core-only projection.
11. Fixture-only arbitration algorithms and privacy primitives.
12. Claims exact-report compatibility for versions 1, 2 and 3.
13. Migration and compatibility tests on disposable PostgreSQL.

## 4. Вне scope

- live DataNewton, FNS, Gateway или AI calls;
- production DB migration, deploy, backfill, refresh или activation;
- frontend, SSR shell, chart UI и iteration 21+;
- AI narrative generation/reservation/fallback implementation;
- provider-zero finance publication;
- visible status/form/capital/tax/activity/manager/owner/worker/tax-authority
  leaves из нового observed shape;
- public arbitration totals, calendar zeroes, outcome, amount, currency,
  opponent, case number, court, instance или KAD facts;
- изменения H1 DTO/facts, signals, scoring, SEO policy или Claims semantics;
- `ROADMAP.md`, dependencies, deploy и nginx.

## 5. Version and writer compatibility

```text
H1:
  writer_profile = h1_legacy_writer_v2
  presentation_contract = company_public_h1_v1
  writable_report_version = 2
  compatible_read_versions = {1,2}
  rollout_config_generation = 0

H2:
  writer_profile = company_card_v2_writer_v3
  presentation_contract = company_public_h2_v1
  writable_report_version = 3
  snapshot_capability = card_v2
  rollout_config_generation > 0
```

Legacy endpoints remain H1-only. `POST /company-reports` always creates or
reuses H1/v2 work and never consults H2 configuration. H1 latest/status/public
queries explicitly select compatible v1/v2 H1 records; a newer v3 record or
H2 assignment cannot shadow an H1 pin or eligible v1/v2 report.

Legacy `company_report_from_snapshot` stays strict for `1|2`. A dedicated v3
parser first checks the raw literal discriminator `3`; neither parser coerces,
upgrades or downgrades another version. V3 never enters H1 signals/scoring.

## 6. Configuration and lifecycle

Fail-closed defaults:

```text
COMPANY_CARD_V2_PRESENTATIONS_ENABLED=false
COMPANY_CARD_V2_WRITER_ENABLED=false
COMPANY_CARD_V2_ROLLOUT_GENERATION=0
COMPANY_CARD_V2_ALLOWLIST_INNS=[]
COMPANY_CARD_V2_PERCENTAGE_BASIS_POINTS=0
```

Malformed settings fail startup. Enabled H2 requires a positive generation.
Cohort choice is server-only and deterministic; body, query, header, cookie or
URL cannot choose version/profile/assignment. Disabled H2 returns
`company_public_h2_disabled` before DB access.

The internal H2 lifecycle is exposed only as:

```http
POST /company-report-presentations
GET  /company-report-presentations/{presentation_id}/status
```

Create accepts exactly `{"identifier":"<INN>"}`. Status resolves only the
immutable presentation ID binding and never re-resolves cohort/latest.

After the endpoint-specific decision, enqueue locks the subject and reuses an
active job only when profile, version, contract and rollout generation all
match. Otherwise it returns `report_writer_profile_conflict`. Claim,
heartbeat and finalization fence on job/report/subject/profile/version/
contract/generation plus lease token and fence generation.

The default v3 worker path is unreachable. Tests use injected fixture builders
only; no extended live provider profile is enabled.

## 7. Immutable v3 snapshot

`CompanyCardV2Snapshot` is a strict frozen model containing exact v3 identity,
generated time, target, approved counterparty core, finance basis, arbitration
basis, Chart Facts, hashes, evidence/privacy versions and closed limitations.

Required invariants:

- record/report/subject/target/counterparty INN equality;
- no H1 signals, scoring or legacy AI explanation members;
- recomputed Chart Facts hash and snapshot hash at finalization;
- no raw pages/headers, credentials, contacts, provider free text, source
  opponent identifiers or names;
- identical-hash idempotency only; finalized content is never replaced.

`ArbitrationBasisV1` is a private immutable persistence object, not a public
model. Its identifier-bearing allowlist contains only a closed
`InternalCaseIdentityV1(source_kind=case_id|id,value)` used for deterministic
dedup/order and a closed `PrivateOpponentTokenV1` with algorithm version,
nonsecret key ID and full 64-hex HMAC. It may contain sanitized roles, dates,
Decimal strings and counters required by section 31. It never contains the
HMAC secret, party INN/OGRN, opposing-party name, raw case/party/page,
provider free text, contact, identifier-bearing URL or arbitrary dictionary.
Transient identifiers are discarded after attribution/HMAC calculation.

Privacy validators are distinct: `PrivateArbitrationBasisPolicyV1` permits
only those two internal values at exact closed paths; `PublicBoundaryPolicyV1`
rejects internal case identities, HMAC tokens, mask key IDs and every source/
raw/private marker in DTO, HTTP body/headers, logs, telemetry-shaped values and
Claims. Public scanning uses exact structural/taint checks and does not confuse
legitimate digests such as `projection_digest` with a private token.

## 8. Lossless finance Decimal transport

Before ordinary JSON-number coercion, the DataNewton client builds an in-memory
JSON-pointer-to-number-lexeme manifest from exact response bytes. It rejects
duplicate keys/nonfinite constants and verifies lexical topology against the
decoded payload. The manifest is never logged or persisted; legacy v1/v2
consumption remains unchanged if the lexical pass is invalid.

`company_card_source_decimal_v1` accepts an exact string or proven number
lexeme matching `-?(0|[1-9][0-9]*)(\.[0-9]+)?`, at most 128 ASCII bytes, 96
significant digits and 32 fractional digits. Float, boolean, exponent, plus,
whitespace, comma, leading zero and nonfinite values fail closed. Canonical
form removes fractional trailing zeroes and maps negative zero to `0`.

The twelve approved `(form, code, year)` inputs are classified as
`available_nonzero|zero_unverified|missing|conflict|decimal_transport_lossy|invalid`.
Only `available_nonzero` owns a Decimal. Provider zero owns no numeric fact and
cannot participate in display, arithmetic or geometry. Unit policy is
`datanewton_finance_thousand_rub_v2`; source truth remains thousand-ruble
Decimal, signed values preserve sign, and missing never becomes zero.

F1–F5 use the closed iteration-19 formulas and deterministic windows. A
required zero/missing/conflict makes the relevant fact unavailable with an
explicit limitation; non-positive denominators produce null ratios/geometry.

## 9. Counterparty boundary

The local v3 parser validates only exact observed paths/types from provider
manifest v2 for status, OPF, capital, tax modes, OKVED, managers, owners,
workers and tax authority. It infers no meaning from names. Personal
identifiers and contacts are discarded before persistence/public/AI/telemetry.

Public H2 may reuse only approved names, exact INN/OGRN/KPP, valid
registration/dissolution dates and approved address/inaccuracy behavior. All
new observed fields remain null/empty with field-specific limitations. Parser
success is not publication approval and no flag overrides the gate.

## 10. Arbitration foundation

The shipped registry intentionally leaves provider envelope bindings
unverified. The network-facing collector validates the whole registry before
constructing or invoking a request; failure returns
`arbitration_envelope_gate_closed` before a provider callback.

Synthetic fixture processing uses page size 100, max 10 pages, 1000 raw-row
cap, 8 MiB sanitized-basis cap, 256 KiB case cap and detail cap 20. Ordering,
drift/non-progress detection, dedup/conflict removal, counters, completion
reasons and canonical byte accounting follow iteration-19 section 31.

Only exact target-INN matches attribute roles: only plaintiff → plaintiff,
only respondent → respondent, any other nonempty set → other, empty →
unattributed. HMAC masking follows the privacy ADR and its golden vector; raw
name/INN/OGRN/provider key/HMAC token/identifier URL never crosses the public
boundary.

Public H2 always returns all A1–A5 blocks null with `gate_closed` coverage and
allowlisted limitations in this iteration, regardless of fixture results.

A fixture-only alias helper is separately tested for verified legal/state
identities: greatest valid update date, greatest start date, Unicode-scalar
smallest NFC/whitespace-normalized safe name, then smallest canonical internal
case identity. Natural/unknown parties never receive a cross-case name alias.

Visible case number has an independent shipped-closed gate. Closed/missing/
blank/invalid yields null; a synthetic open test may bind one exact fixture
path. Internal `case_id`/fallback `id` is never substituted or emitted. Tests
cover every date/name/case-identity tie and gate closed/open/missing cases.

## 11. Closed H2 projection

The strict recursive Pydantic DTO implements the iteration-19 leaf contract,
exact block/coverage/source/action/breadcrumb order and canonical JSON profile.
It supports report capabilities `legacy_read_only|card_v2`, but legacy v1/v2
H2 preview is always noindex and unavailable facts are never synthesized.

Iteration 20 does not generate a narrative. The builder accepts only an
already validated immutable narrative binding protocol; tests use a synthetic
safe binding. Runtime without a valid binding returns `report_not_eligible`.

The finance override is `datanewton_finance_thousand_rub_v2` and
nonzero-only. Arbitration leaf models may exist for future compatibility, but
the builder cannot populate A1–A5. Every null/non-available block has a linked
limitation; `zero_unverified` is neither missing nor public zero.

Canonical JSON is NFC, no-float, sorted-key, deterministic UTF-8 with
preserved array order and the iteration-19 size caps. `projection_digest` is
SHA-256 over the sanitized DTO with its digest member removed.

## 12. Public H2 HTTP and read boundary

```http
GET  /company-reports/{inn}/public-h2
HEAD /company-reports/{inn}/public-h2
```

The closed result matrix covers success, forbidden query, invalid INN,
disabled feature/cohort, not found, pending, failed, not eligible, invalid
projection, unsupported method/Accept and rate limit. Success and errors use
`Cache-Control: no-store`, `X-Content-Type-Options: nosniff` and
`X-Robots-Tag: noindex,follow`. HEAD has the same selected status/metadata and
an empty body. No 304/version-selection path exists.

GET/HEAD may only SELECT exact immutable bindings. They never call provider,
FNS, Gateway, AI, worker, queue, signals or scoring; never create/refresh/
republish; and never add, flush, commit, rollback or execute DML. Default-off
stops before DB access.

After the feature/cohort check, selection precedence is: exact active H2
assignment/pin/v3; otherwise exact staged H2 pointer/pin/v3; otherwise latest
independently valid H1-compatible v1/v2 legacy preview; otherwise the exact
lifecycle error. A newer unpinned v3 cannot shadow legacy preview. Corrupt
exact active/staged H2 is terminal `public_projection_invalid` and never falls
back; corrupt legacy candidates may be skipped only for an older independently
valid v1/v2. V3-only without an exact H2 binding is `report_not_eligible`.
Legacy preview is always `legacy_read_only`, `latest_unpublished`, noindex and
uses `legacy_unavailable` for unsupported charts.

## 13. Persistence and assignment foundation

Existing reports/jobs receive explicit profile, presentation contract and
rollout generation; jobs also receive fence generation. Existing v1/v2 rows
are backfilled to H1 generation 0, while unknown historical versions fail the
migration rather than being guessed.

New immutable tables model presentations, append-only pin generations,
staged H2 pointers, exact presentation assignments and an append-only
assignment journal. Composite FKs bind pointers/assignments to an exact pin.
No H2 assignment is created and no route exposes assignment mutation.

Migration deterministically imports every structurally and cryptographically
valid active H1 publication as an immutable H1 pin whose generation equals the
existing positive `batch_generation` and whose report/hash/policy/path/
indexability/lastmod are preserved exactly. Paused/disabled rows are not
imported; corrupt active rows abort atomically; old publication/batch/journal
rows are untouched. No assignment or H2 pin is created.

Runtime H1 publication candidate selection applies the v1/v2 H1-compatible
predicate before choosing latest by generated time and ID, so a newer v3 never
shadows v2. Every successful active H1 publication is mirrored to the same
immutable generation in the same transaction. Identical retry is idempotent;
a conflicting binding rolls back the publication transaction. Existing H1
publication/resolver/sitemap remain authoritative until a later rollout.

An internal CAS locks the assignment, checks expected generation, revalidates
the exact pin/report/hash/contract, appends journal and advances the reference.
Mismatch is `presentation_assignment_conflict`; corrupt resolution never falls
back to latest or another projection.

## 14. Claims compatibility

Claims continues to accept only exact `report_id`. V3 dispatch validates the
strict snapshot, record/report/subject equality, final lifecycle, hash and
exact target/counterparty INN, and exposes only debtor name and INN. It never
uses latest/assignment/client debtor identity or new finance/counterparty/
arbitration fields. Existing v1/v2 behavior and idempotency remain unchanged.

## 15. Security, migration and acceptance

Private-basis validation rejects everything outside its exact internal
case-identity/HMAC allowlist. Public-boundary scanners reject those internal
values plus raw payload/header, secret/token, personal/source opponent
identifier, provider case key, identifier URL, contact, provider free text and
unknown keys. Fixtures are synthetic; logs contain safe codes/UUIDs/versions
only.

An append-only `0016_company_card_v2_foundation` migration follows `0015`.
It is executed only against disposable PostgreSQL in this DevFlow. Tests prove
upgrade/backfill/constraints/downgrade and that no H2 assignment/activation is
created.

Iteration is ready only if strict versioning, H1 compatibility, default-off
fences, immutable v3, Decimal lexeme preservation, zero prohibition,
core-only counterparty projection, pre-call arbitration block, null A1–A5,
privacy goldens, exact Claims handoff, zero-side-effect GET/HEAD, unit/full
regressions and disposable-PostgreSQL suites pass without unexplained skips.
No dependency/frontend/Gateway/Roadmap/deploy/production activation change is
permitted.
