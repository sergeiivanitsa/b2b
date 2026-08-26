# Технический план итерации 24 — Арбитражные графики Company Card v2

Base commit: `8a1d27866187df470bc628f9b5e7f500204222e7`

Intended implementation branch:
`codex/iteration-24-company-card-v2-arbitration-charts`

Статус: implementation in progress after reviewed implementation plan,
independent general and contract/privacy reviews `APPROVED`, and owner approval
2026-08-27

Owner implementation approval: `APPROVED` — user command 2026-08-27

Production activation: `NOT AUTHORIZED`

Implementation checkpoint 2026-08-27:

- stages B–N and their tests are implemented on the intended feature branch;
- all locally available mandatory checks pass;
- stage 19 remains pending because Docker Desktop daemon is unavailable; the
  safe runner did not select another database and touched no database;
- final independent code review is `APPROVED` with no findings;
- the iteration remains `in_progress` and cannot be marked `ready_for_merge`
  before disposable-PostgreSQL acceptance.

## 1. Planning inputs and constraints

Реализовать только утверждённый narrowed scope D1–D6 из:

- `docs/development/decisions/iteration-24-owner-scope-decision-v1.md`;
- `docs/development/evidence/iteration-19-company-card-v2/iteration-24-gate-readiness-v2.md`;
- `docs/development/evidence/iteration-19-company-card-v2/arbitration-contract-evidence-v3.md`;
- iteration 24 specification.

Запрещены live provider/AI/FNS calls, production DB/deploy/config activation,
second-page collection, named opponents, entity inference, non-RUB/FX, calendar
zero-fill, KAD/result/instance details, scoring/verdict, H1/Claims semantic
changes, dependencies, screenshots и iteration 25 rollout work.

Implementation starts only after the owner approves this reviewed plan.
Commit and push require a later separate explicit owner command.

## 2. Expected production surfaces

### 2.1. Provider, settings and worker boundary

- `services/product_api/src/product_api/settings.py`
- `services/product_api/src/product_api/providers/datanewton/models.py`
- `services/product_api/src/product_api/providers/datanewton/client.py`
- `services/product_api/src/product_api/company_reports/provider_protocol.py`
- `services/product_api/src/product_api/company_reports/worker.py`
- `services/product_api/src/product_api/routers/company_report_presentations.py`

Provider model/client changes are allowed only if the exact request/result
binding cannot be expressed through existing `ALL/0/1000` parameters and
`lexical_number_lexemes`. Do not create a second JSON decoder.
The global provider protocol already exposes arbitration; prefer a local
writer callback protocol and do not change H1/global semantics without a
demonstrated type-only need.

### 2.2. Company Card v2 domain and writer

- `services/product_api/src/product_api/company_reports/company_card_v2/evidence.py`
- `services/product_api/src/product_api/company_reports/company_card_v2/arbitration.py`
- `services/product_api/src/product_api/company_reports/company_card_v2/models.py`
- `services/product_api/src/product_api/company_reports/company_card_v2/writer.py`
- `services/product_api/src/product_api/company_reports/company_card_v2/privacy.py`
- `services/product_api/src/product_api/company_reports/company_card_v2/__init__.py`

New arbitration code may be split into a narrowly named sibling module when
that keeps V1 fixture code frozen. Do not parameterize `_identity()` or the
page-100 V1 collector into changing historical semantics.

### 2.3. Snapshot, persistence and presentation lineage

- `services/product_api/src/product_api/company_reports/persistence/v3.py`
- `services/product_api/src/product_api/company_reports/persistence/models.py`
- `services/product_api/src/product_api/company_reports/persistence/jobs.py`
- `services/product_api/src/product_api/company_reports/persistence/repository.py`
- `services/product_api/src/product_api/company_reports/persistence/presentations.py`
- `services/product_api/src/product_api/company_reports/company_card_v2/narrative/models.py`
- `services/product_api/src/product_api/company_reports/company_card_v2/narrative/identity.py`
- `services/product_api/src/product_api/company_reports/company_card_v2/narrative/service.py`
- `services/product_api/src/product_api/company_reports/company_card_v2/narrative/prompt.py`
  as a byte-compatibility boundary; no prompt/body behavior change is expected
- `services/product_api/src/product_api/company_reports/company_card_v2/service.py`

Add one append-only Alembic revision under
`services/product_api/alembic/versions/` for the report/job arbitration
decision fields. No pin/presentation column changes are expected.

### 2.4. Public projection and SSR

- `services/product_api/src/product_api/company_reports/company_card_v2/public_h2.py`
- `services/product_api/src/product_api/company_reports/company_card_v2/public_h2_models.py`
- `services/product_api/src/product_api/company_reports/company_card_v2/public_h2_document.py`

Routers remain read-only and should not need semantic changes.

### 2.5. Frontend and assets

- `services/web_ui/src/companyPublicH2/contractSchema.ts`
- `services/web_ui/src/companyPublicH2/contractSemantics.ts`
- `services/web_ui/src/companyPublicH2/parityVector.ts`
- `services/web_ui/src/companyPublicH2/bootstrap.tsx`
- `services/web_ui/src/companyPublicH2/CompanyPublicH2Page.tsx`
- `services/web_ui/src/companyPublicH2/CompanyPublicH2Page.css`
- new `arbitrationPresentation.ts`
- new `ArbitrationFacts.tsx`
- new `arbitrationGeometry.ts`
- new `ArbitrationCharts.tsx`
- new local arbitration chart error boundary if the finance boundary cannot be
  generalized without coupling the chunks
- colocated tests
- `services/web_ui/scripts/company-public-h2-manifest.mjs` only if existing
  multi-dynamic-import traversal needs a correction
- tracked H2 asset manifest and generated content-addressed assets
- `deploy/nginx/test_company_public_h2_release.py`

### 2.6. Fixtures, runners and docs state

- minimal synthetic provider-byte fixtures under
  `services/product_api/tests_unit/fixtures/company_card_v2/`
- `shared/fixtures/company_public_h2_contract_v1.json`
- `shared/fixtures/company_public_h2_contract_v1_cases.json`
- new `shared/fixtures/company_public_h2_contract_v1_arbitration_masked_v3.json`
- closed, finance-only and finance+arbitration SSR JSON/HTML goldens
- new `scripts/run-iteration24-postgres-tests.ps1`
- iteration spec/plan and `docs/development/DEVFLOW_STATE.yaml`

Historical V1/V2 snapshot/provider fixtures and the existing dense generic
public-v1 contract fixture stay byte-identical. Any new golden receives a new
name rather than overwriting immutable compatibility evidence.

## 3. Stage A — baseline and RED matrix

1. Confirm clean scope against the approved base commit.
2. Record existing targeted backend/frontend results before behavior changes.
3. Add RED tests for:
   - operation-disabled arbitration fetch callback count zero;
   - exact request parameters and one-call maximum;
   - conditional zero envelope and every integer/bool/type boundary;
   - `999/1000/1001` totals and returned-slice behavior;
   - `case_id`-only versus legacy `id` fallback compatibility;
   - missing/non-array role collections and exact-INN-only matching;
   - byte-number manifest `/data/{i}/sum` lookup and Decimal negatives;
   - all-masked HMAC/grouping/order/ordinal/privacy vectors;
   - acceptance of finalized snapshot-plus-pin historical V1/v1 and V2/v1
     plus current V2/v2 and V3/v3, rejection of active pre-upgrade H2 and every
     unlisted snapshot/policy pair;
   - A1–A5 arithmetic, top-20/N-of-M and `available_empty`;
   - SSR/React factual parity and independent lazy arbitration loading.
4. Do not fix unrelated baseline failures.

## 4. Stage B — operation configuration and evidence binding

In settings/worker:

1. Add `COMPANY_CARD_V2_ARBITRATION_COLLECTION_ENABLED=false`.
2. Add exact optional settings
   `COMPANY_CARD_V2_ARBITRATION_MASK_ACTIVE_KEY_ID` and secret
   `COMPANY_CARD_V2_ARBITRATION_MASK_KEYRING_JSON`.
3. Keep key-ring JSON behind `SecretStr`; parse at worker preflight, not global
   startup, with the exact 8 KiB/16-entry/unique-ID/canonical-unpadded-
   base64url/32..64-byte contract from the specification.
4. Convert malformed/missing/unknown key input to only
   `privacy_key_unavailable`; never include values in repr, validation text,
   logs or dumps.
5. Resolve the active nonsecret ID at enqueue and persist the exact
   arbitration-enabled/ID decision on both report and job; malformed or
   whitespace-normalized ID becomes null without startup failure. Worker resolves
   only the claimed ID and injects bytes into writer; pure domain code must not
   import Settings.
6. Recheck the live collection flag only as an emergency execution gate. A
   persisted-enabled/live-disabled claim produces V3
   `operation_gate_closed` with zero arbitration fetch callbacks; it never
   changes to V2 or rewrites the stored decision.

In persistence/jobs/router:

1. Add the two report/job fields through one append-only Alembic migration.
   Before DDL in the same transaction, lock `company_reports` then
   `company_report_jobs` with PostgreSQL `SHARE ROW EXCLUSIVE`, preventing
   enqueue/state-write races. Use two independent `EXISTS` predicates, never
   an inner/equality join: any pending exact report tuple
   `company_card_v2_writer_v3/3/company_public_h2_v1/generation>0`, regardless
   of job presence/binding; and any queued/running exact H2 job
   profile/contract/generation tuple, regardless of its report tuple. Abort
   with fixed `iteration24_active_h2_lineage_ambiguous` on either. Do not add
   columns or mutate rows on rejection. Test missing/mismatched job for the
   exact report, mismatched report for the exact job, and the existing FK that
   forbids a physical job without a report. After a zero-active guard,
   existing terminal rows
   backfill/default to `false/null`, with the disabled/null DB check on both
   tables. Document the iteration-25 operational prerequisite: pause H2
   enqueue, drain/safely terminalize old active H2 jobs with the old binary,
   prove both active counts zero, then upgrade; do not perform it here.
2. Make `WriterDecision` enforce the exact closed surface/version matrix:
   H1 permits only `false/null`; active H2 `false/null` after the guarded
   revision is only a new V2/v2 job; active H2 enabled is only V3/v3.
   Historical H2 V1/v1, V2/v1 and V2/v2 are accepted only for a
   complete/partial report with a valid immutable snapshot and matching saved
   pin; finalized narrative retry/reconciliation derives policy from that pin,
   not the new columns. New enqueue may create only V2/v2 or V3/v3 and never
   policy v1. Sample arbitration settings only after current H2 selection.
   Reject pre-upgrade active H2, H1+enabled, V1/V2+enabled, V3+disabled,
   false/non-null and every unlisted cross-policy tuple.
3. Extend the live-job validator through enqueue/reuse/claim/heartbeat/
   completion fences, expired/failure reconciliation and claimed DTO with
   exact matching values. This explicitly includes
   `_has_immutable_job_binding`, `fail_owned_job` and every stale/expired
   ownership path. Disabled requires null; enabled may carry one syntactically
   valid ID or null for safe pre-call failure. Keep the separate finalized
   historical snapshot-plus-pin validator out of report-job claim paths.
4. Prove only the runtime property it can enforce: the persisted nonsecret key
   ID never changes across queue/retry paths. Rotation uses a new ID and changes
   only newly enqueued jobs; a queued job keeps its old ID, and premature old
   secret removal makes zero arbitration fetch callbacks. Explicitly document
   that, without a durable secret fingerprint, this iteration cannot detect a
   same-ID secret-byte rebind across config/restart. Treat immutable KMS/key-ID
   binding and old-version retention as an external iteration-25 production
   activation gate; do not claim a runtime proof or add a hidden fingerprint.
   Report/job ID mismatch still fails closed.
5. Audit every existing H1 report/job constructor and expired/failure
   reconciliation path: callers that do not opt into Company Card v2
   arbitration must materialize exact `false/null` on both rows and must never
   sample the active mask key. Add regression tests for those persisted tuples
   and unchanged H1 provider behavior. Separately prove finalized historical
   H2 reads/narrative work only with a valid snapshot-plus-pin pair and prove
   no legacy active H2 job reaches claim/reconciliation after the guard.
6. Do not apply the migration to production; run upgrade/downgrade only in the
   disposable test database.

In `evidence.py`:

1. Keep `ARBITRATION_EVIDENCE_REGISTRY_V1` unchanged.
2. Add exact immutable registry v2 metadata from evidence v3.
3. Make pre-call admission require both verified exact binding and explicit
   operation enablement.
4. Validate exact runtime dataset literal `arbitration_cases` plus
   registry/request/identity/collection policy as one closed tuple.
5. Test stale fingerprint/path/filter/version and arbitration callback
   construction count zero, not merely failure after a mock call.

## 5. Stage C — new V2 arbitration models

In `models.py` or a focused sibling:

1. Add exact closed models for V2 page manifest, counters, sanitized case,
   private opponent token, basis and separate arbitration chart facts.
2. Carry literal versions from sections 7–9 of the specification.
3. Enforce:
   - one page, offset 0, limit 1000;
   - the exact closed counter field set, strict bounds, row-conservation
     equation and duplicate-conflict row/key distinction from specification
     section 8;
   - the frozen `PublicArbitrationSummary` v1 field set with no additions,
     including public
     `duplicate_conflict_count=duplicate_conflict_key_count`; keep oversize,
     storage and opponent-probe counters private;
   - optional bound provider receipt time and signed-int64 source total;
   - calendar always unverified/false/no-zero in this policy;
   - `case_id` source kind only;
   - exact case amount-state enum `available|missing|invalid`: Decimal is
     non-null iff available, and missing/invalid carry only their matching
     per-case amount limitation;
   - exact case currency-state enum
     `rub|missing|unidentified|invalid`, with no invalid-to-unidentified
     collapse;
   - full HMAC/effective-key metadata paired-null rules;
   - retained opponent-token/group counters, saturated 20,001 transient probe
     counter and the atomic all-token scrub boundary;
   - literal `arbitration_basis_metadata_reserve_v1`, the exact closed 25-code
     basis limitation catalog and a finite longest-CJSON representative for
     every non-case basis member;
   - no raw/name/source identifier fields;
   - sorted unique cases/limitations/facts;
   - facts exactly recomputed from basis and exact hash.
4. Keep `ArbitrationBasisV1`, `InternalCaseIdentityV1`, V1 validators and
   exports behavior unchanged.
5. Retain finance `ChartFactsV1` and hash exactly; arbitration is a separate
   leaf, never extra keys in V1.

Tests must round-trip old models and compare frozen CJSON/hash bytes before
accepting new V2 models. Add a pure reserve-envelope helper and freeze its
computed metadata bytes/golden mapping. Exhaustively prove each bounded
non-case field value serializes no longer than its selected representative;
unknown limitation values fail rather than escaping the reserve.

## 6. Stage D — pure single-page normalization

Implement a new function/class rather than altering V1 page-100 semantics.

Order:

1. Read the persisted operation/key decision, then short-circuit preflight in
   exact live-gate, registry, claimed-key order before constructing a callback.
2. Contain provider exceptions as `provider_error` with one logical callback.
3. Validate the complete `DataNewtonResult` tuple before reading payload:
   provider/dataset/endpoint, exact requested identifier, empty plural list,
   exact four-key parameter map, null body, 200 status, report request ID and
   recomputed response hash.
4. Before any `astimezone` canonicalization, harden the shared
   `DataNewtonResult.received_at` validator to reject naive or non-zero-offset
   inputs; preserve valid UTC V1/V2 behavior and byte fixtures. After outer
   binding succeeds, capture its exact UTC-Z `received_at` without reading
   payload. Retain this bound source receipt even when the following lexical
   or envelope gate rejects the result; use null only when no bound provider
   result exists and never repair it with current time.
5. Require `lexical_transport_valid=true` before reading any envelope,
   identity, role or amount leaf. Duplicate keys or topology mismatch reject
   the whole result with zero parsed rows.
6. Validate signed-int64 total and the conditional-zero envelope without
   Pydantic coercion.
7. Count raw rows before normalization and enforce the 1,000 cap. Before any
   row exclusion/dedup/early stop, pre-scan the accepted array into the bounded
   ephemeral collision set of every object `case_id` string that independently
   passes the first-number display grammar. Never persist/hash/log that set.
8. For each row in source-array order:
   - require object and the exact NFC/control/256-scalar/1,024-byte `case_id`;
   - ignore `id` for V2;
   - require all nine role arrays and object party rows;
   - derive the one target role from exact party INN only;
   - normalize year/dates/outcome and admit `first_number` only through exact
     `arbitration_first_number_display_v1` grammar;
   - resolve a JSON-number `/data/{index}/sum` only from the byte lexeme
     manifest; reject a JSON string;
   - normalize currency state;
   - select only eligible opposing collection;
   - HMAC exact stable identifier or case-position fallback;
   - discard name/raw IDs/provenance values;
   - enforce the per-case CJSON cap before dedup;
   - classify identical/conflicting `case_id`, remove conflicts permanently;
   - rebuild the `arbitration_basis_metadata_reserve_v1` sizing mapping from
     the actual post-dedup case tuple plus maximal CJSON representatives for
     every counter/reason/limitation/page/source/key field, and only then
     enforce the 8 MiB cap. Identical rows and conflict removals cannot trigger
     it; only a new nonconflicting representative can become the single
     `storage_cap_rejected_count` row.
9. Stop deterministically on the first oversize/storage-cap boundary; do not
   size-select later rows.
10. Sort admitted cases only after processing, enforce the 20,000-group bound
   without truncating by popularity/provider order and build exact
   reasons/counters.
11. Build arbitration Chart Facts purely and validate hash.

Tests cover malformed/missing roles, bool/int identities, Unicode/control/
length case key/number, duplicate same/conflict/equal amount distinct keys,
int64 and all caps at equality/+1, dates/year conflict, every role set,
provider/binding/lexical/envelope failure and no raw retention. Counter tests
exercise the exact conservation equation and final conflict-row/key
classification. First-number collision fixtures include a raw display-shaped
`case_id` in malformed, conflicting, oversized, basis-cap-excluded and later
unprocessed rows.
Reserved-envelope equality/+1 fixtures separately cover a new unique row, an
identical duplicate, a conflict that removes the previously admitted key,
counter decimal-width growth, the maximal reason/limitation tuples and group
metadata. Independently assert final real basis CJSON never exceeds 8 MiB.

## 7. Stage E — Decimal and currency proof

Reuse `DataNewtonResult.lexical_number_lexemes` and
`company_card_source_decimal_v1`:

1. Map exact JSON pointer `/data/{index}/sum` before row reorder/dedup.
2. Admit only the schema-bound JSON number through its exact byte lexeme;
   reject JSON strings even when their contents look numeric.
3. Reject decoded float without a valid exact manifest, bool, exponent,
   nonfinite, whitespace/comma/plus, excessive digits/fraction and mismatch.
4. Canonicalize negative zero only under the existing decimal contract.
5. Preserve valid zero/negative and never use ambient Decimal context.
6. Normalize only exact `RUBLES` to RUB; distinguish absent/null from
   `OTHER`/unknown nonblank and from empty/non-string invalid currency.
7. Round-trip all three amount states and their exact Decimal/null/limitation
   pairing; `missing_amount_count` counts only missing, while invalid makes A4
   partial without incrementing it.
8. Round-trip all four exact case currency states and require invalid state to
   carry `arbitration_currency_invalid` and make A4 partial.
9. Prove Decimal → basis → facts → DTO → strict JSON round-trip without float.

Provider transport tests must verify duplicate JSON keys/topology mismatch
reject the entire arbitration result before rows, even when corruption is in
`case_id`, a role key or party identifier rather than `sum`. No second lexical
parser is introduced.

## 8. Stage F — all-masked opponent privacy

1. Freeze exact eligible collections by case role.
2. Apply `arbitration_opponent_stable_identifier_v1`: exact ASCII INN 10/12
   and OGRN 13/15 by field kind, no cleanup/checksum/kind inference; allow
   absent/null or matching self-provenance (`INN`/`OGRN`) only, and treat
   indirect/opposite/unknown/malformed provenance as ineligible.
3. Use one eligible INN, else one eligible OGRN, else exact case-position
   identity; never names, `name_src` or any `*_src` value.
4. Reuse exact `OpponentHmacIdentityV1`, existing CJSON and full HMAC vector.
5. Store tuple of tokens; dedup same token within a case.
6. Reuse frozen case/opponent public-order identities to assign six-digit IDs;
   all opponents use fixed `masked_unknown`/`masked_hmac` ordering members and
   the full HMAC only during private ordering.
7. Bind masked label ordinal exactly to `opponent_000001 -> Сторона скрыта 1`.
8. Keep basis algorithm/key metadata both null until the claimed key resolves;
   after resolution both are fixed even if provider later fails, and every
   token must carry the same pair.
9. Missing/rotated/unknown claimed key fails before the arbitration fetch
   callback; rotation affects new reports only through the persisted enqueue
   decision.
10. Probe full HMACs in deterministic case/token order with the count saturated
    at 20,001. At exactly 20,000 retain all tokens. At 20,001 atomically scrub
    every case token tuple, set retained token/group counters to zero, persist
    only nonidentity probe count 20,001, keep resolved basis key metadata,
    fail A5 closed and mark collection partial. Retain scrubbed cases for
    A1–A4 and never choose a provider-order or popularity subset. Freeze
    dedup/conflict identity and counters from pre-scrub candidate CJSON.
11. Project normal A5 coverage as exact
    `total=source_total/returned=rows_observed/eligible=retained group count`.
    For overflow use null block, failed/returned-slice coverage, exact
    total/returned, `eligible=null` and only
    `opponent_group_cap_exhausted`; never project sentinel 20,001 or scrubbed
    zero as an exact eligible count.

Add a typed path-aware allowlist for contracted v3 public IDs/labels, invoked
from the saved-policy-v3 emitter/resolver and recognized client-side by the
exact two-branch v3 discriminator matrix. Do not narrow the frozen generic
`company_public_h2_v1` parser or invalidate the historical dense corpus. Add
negative scans over v3 DTO, serialized bytes, SSR, embedded state, React DOM,
aria/live strings, logs and Claims handoff.
Tests inject raw name, INN, OGRN, case ID, HMAC and arbitrary URL at every
relevant nested path and require rejection. First-number tests accept only the
closed A/court-code and SIP forms, reject names/URLs/controls/whitespace and
prove `case_id` is never a fallback or an equal-value display collision with
any surviving or excluded raw case identity from the ephemeral collision set.
Extend the sink matrix through `NarrativeEvidenceEnvelope`, prompt content,
the complete serialized Gateway `ChatRequest`, mocked sender arguments and
request logging; UI/Claims sinks alone are insufficient.

## 9. Stage G — writer and snapshot V3

In writer/models/persistence parser/repository:

1. Add `CompanyCardV2SnapshotV3(CompanyCardV2SnapshotV2)` with exact new
   discriminator and separate arbitration facts/hash.
2. Extend parser dispatch explicitly to V3; V1 no-discriminator and V2 paths
   remain exact.
3. When the persisted arbitration decision is off, execute the current V2 path
   unchanged and do not construct the arbitration provider callback.
4. When the persisted decision is on, always build V3/policy-v3 lineage for
   the arbitration attempt. A rejected live/evidence/key preflight records
   failed/gate-closed V3 arbitration and makes zero arbitration fetch
   callbacks; a preflight-admitted attempt executes exactly one logical
   request through the injected provider.
5. Implement the specification lifecycle table exactly: zero-case reasons and
   null `failed/gate_closed` A1–A5 for preflight/provider/binding/lexical/
   envelope failure; non-null partial views only after an admitted collection;
   paired-null effective key metadata and stored provider receipt time.
6. Contain safe arbitration provider/shape/privacy failure as dataset partial;
   preserve admitted counterparty/finance and never leak raw exception text.
   Do not swallow `CancelledError` or ownership loss.
7. Lifecycle is complete only when currently required datasets and enabled
   arbitration collection are complete; safe partial arbitration keeps the
   report partial without destroying finance.
8. In `persistence/repository.py`, parse V3 and independently recompute both
   finance facts/hash and arbitration facts/hash before accepting finalization,
   then validate exact snapshot CJSON/hash and persisted arbitration decision.
9. Add negative finalization tests for changed arbitration registry, basis,
   facts, facts hash, decision/key ID and snapshot discriminator.

Settings/worker tests cover disabled, enabled with mock provider, missing key,
provider failure, cancellation propagation and exact request/result binding.
No unit test reaches network.

## 10. Stage H — atomic publication policy v3

In presentations/jobs/narrative/service:

1. Add `company_public_h2_publication_v3` to closed allowlists.
2. Preserve exact meanings:
   - v1 all charts closed;
   - v2 finance only;
   - v3 finance plus arbitration.
3. Select new unresolved policy from exact saved snapshot type, never a
   mutable default or digest heuristic.
4. V3 snapshot creates/reuses one unresolved v3 pin in the existing fenced
   report/outbox transaction; V2 still creates/reuses v2.
5. Keep pin `chart_facts_version/hash` and `evidence_registry_version`
   finance-only exactly as V2. Validate arbitration registry/basis/facts/hash
   transitively by parsing/recomputing V3 and matching the pin/report
   `snapshot_hash`; do not add or overload a pin column.
6. Retry, rollback and concurrency cannot create duplicate generation or
   mixed policy lineage.
7. Narrative finalization finds one exact unresolved pin and resolves with the
   same saved policy.
8. Resolver accepts exactly finalized snapshot-plus-pin historical V1/v1,
   historical V2/v1, current V2/v2 and new V3/v3, rebuilds the right projection
   and compares stored digest; every other cross-pair/unknown/mismatch fails
   closed.
9. GET/HEAD never backfills or writes.
10. Extend only the narrative snapshot-version allowlist to V3. Keep
    `NarrativeEvidenceEnvelope`, `build_narrative_gateway_body`, prompt/output
    schema and empty chart comments unchanged. Extract only inherited admitted
    primary activity; never pass snapshot/basis/facts to the prompt builder.
11. With the same primary activity, evidence version, dispatch ID, timeout and
    token settings, assert captured V3 Gateway request bytes equal the V2
    reference. Poison V3 arbitration case IDs, first numbers, HMAC/key data,
    amounts/currencies, roles/outcomes/counters/limitations and recursively
    prove none enter envelope/prompt/body/log context. Use a mocked sender only.
12. Replace the response validator's `PreparedNarrativeDispatch` parameter
    with closed `NarrativeResponseValidationContextV1` containing only
    gateway dispatch ID, 64-hex generation key and the existing narrow
    evidence envelope. Validation returns draft/rendered narrative without
    snapshot access or projection digest. The caller computes projection
    digest afterward from its separately held private report/snapshot/policy.
    Capture and recursively poison-scan the real validator arguments; never
    pass `ValidatedNarrativeReport`, snapshot, arbitration basis or facts.

Extend narrative identity snapshot-version allowlists without changing old
generation keys. Add V3 fixtures rather than modifying frozen V1/V2 identity
vectors.

Integration cases: V2 finance-only unchanged, new V3 complete/partial/empty/
preflight-failed, retry, rollback, concurrent finalization, mixed pins,
resolved v1/v2/v3, arbitration tamper under unchanged finance pin fields,
digest mismatch and no GET writes. A final fallback that still exceeds the
public cap leaves exactly one unchanged unresolved v3 pin and no resolved pin,
cache entry, DTO or staged publication; a retry reuses that pin.
Migration/backfill regressions keep finalized historical H2 V1/v1 and V2/v1
snapshot-plus-pin lineage at `false/null` through narrative
retry/reconciliation/resolution, reject missing/mismatched snapshot or pin,
exercise the pre-DDL active-H2 guard, and prove no new policy-v1 enqueue path
exists.

## 11. Stage I — pure A1–A5 and public projection

Create pure builder(s) from validated `ArbitrationBasisV2`:

1. Assign public IDs before top-20 selection.
2. Build common summary and complete/returned-slice scopes.
3. A1:
   - observed years only;
   - greatest ten distinct observed years;
   - unknown bucket last;
   - four fixed roles and exact totals/details.
4. A2:
   - fixed role counts/details;
   - exact denominator and scale-6 residual percentages.
5. A3:
   - fixed outcome counts/details;
   - same percentage algorithm, no win rate.
6. A4:
   - one RUB group maximum;
   - exact missing versus unidentified semantics;
   - abs/value/date/assigned-public-ordinal top-20;
   - axis over displayed amounts and `[0,amount]` keyed geometries.
7. A5:
   - distinct eligible token groups;
   - once-per-case/group counting;
   - overlap/no-safe counters;
   - popularity then public-ID order;
   - root/nested top-20 scopes.
   - exact coverage tuple for normal, zero-group and 20,001-overflow states.
8. Keep D6 fields null/empty and never display `case_id`.
9. Set public `completion_reason` to the first ordered basis reason and map
   preflight/evidence/privacy/provider/binding/transport/envelope states to the
   exact null/coverage states in the specification.
10. Emit a policy-v3 arbitration source only from stored
    `provider_received_at`; its exact tuple has dataset `arbitration`, that
    UTC-Z `received_at`, null `effective_at`/`period`, and the frozen
    arbitration normalization/evidence versions. Omit it when no bound result
    exists and never use current render time. Mutate every tuple member in the
    Python/TypeScript parity corpus.
11. For source-less V3 pre-result states emit the exact second discriminator:
    all A1–A5 null; no arbitration source; frozen counterparty/finance source
    sequence; all five coverage counts null and scope `not_applicable`; one
    common reason/state mapping (`operation_gate_closed|evidence_gate_closed`
    -> gate_closed,
    `privacy_key_unavailable|provider_error|provider_binding_invalid` ->
    failed). Use exactly that reason as each coverage limitation and the sole
    arbitration-related root limitation, whose `block_id` and `field_id` are
    both null. Reject mixtures and require bound source for lexical/envelope
    states; mutate both root linkage fields in parity tests.
12. Reuse/extract root cross-field semantics so every candidate component and
    every whole-response invariant except the byte cap is validated first;
    other invalidity must not enter the size fallback. Assemble the exact
    complete primitive wire mapping and measure its CJSON before root model
    construction. Allow exactly 524,288 bytes. Only for the exact bound-result
    source branch, at 524,289 or more atomically set all A1–A5 blocks null and
    all five coverage states failed, preserve their exact candidate population
    scope/total/returned/eligible evidence, and use only
    `arbitration_public_projection_cap_exhausted` for those coverage entries.
    Do not reduce the frozen detail cap, prioritize views or keep a subset.
13. Preserve snapshot/basis/facts/hashes and non-arbitration projection data;
    compute `projection_digest` from the bound-result fallback only. Validate
    that fallback against the same cap; if it still exceeds it, fail
    publication with `public_projection_too_large`. Never rewrite a source-less
    pre-result candidate to the cap code: emit its exact discriminator through
    524,288 and at 524,289 fail publication directly. In either failure keep
    the existing unresolved v3 pin unchanged/retryable and create no cache
    entry, resolved pin, DTO or staged publication.

In `public_h2.py`, enable arbitration only for saved policy v3. Generate exact
coverage/limitations/sources from basis state. Fix Python `available_empty`
root nullability. Policy v2 must not call the arbitration builder.

## 12. Stage J — closed validators and fixtures

Strengthen `public_h2_models.py` and the shared mutation corpus together:

1. Policy-v3 ID/label/ordinal and masked-only rules without narrowing generic
   historical public-v1 parsing.
2. Summary/counter/calendar/complete invariants.
3. Scope labels/cardinality/source-total consistency.
4. A1 bucket/order/sum/displayed bounds/all-time invariants.
5. A2/A3 fixed order/count/percentage/residual invariants.
6. A4 RUB-only/axis/geometry/case matching and count semantics.
7. A5 order/membership/group/nested scope invariants.
8. Deferred detail null/empty contract.
9. Coverage non-null rules including `available_empty`.
10. Projection digest/CJSON/public byte/privacy checks, including exact
    524,288/524,289 behavior, bound-result atomic all-view cap fallback and
    source-less direct fail-closed +1 behavior without a cap-code rewrite.
11. Exact allowlisting/linkage of the public-only
    `arbitration_public_projection_cap_exhausted` code; reject it on any
    non-atomic or source-less state and prove it does not alter basis/report
    completion.
12. Exact positive/mutation parity for bound-source v3 and all five source-less
    pre-result v3 discriminator tuples; keep legacy block-specific gate codes
    outside that dispatch.

Keep the existing dense public-v1 contract data byte-identical. Add a new
masked-v3 contract corpus that is internally reconciled and uses
`case_000001`, `opponent_000001`, `masked_unknown` and exact Russian labels.
Keep separate closed, finance-only and v3 arbitration-enabled goldens.
Add a genuine worst-case candidate fixture with 11 A1 buckets × 4 roles × 20
details, 80 A2, 80 A3, 20 A4 and 20 A5 groups × 20 nested details: 1,460
repeated `PublicSafeCaseDetail` objects. Prove the full candidate exceeds the
cap, the atomic fallback remains within it, exact coverage counts survive,
facts/snapshot hashes do not change and the digest binds only the fallback.

Run Python/TypeScript contract parity after every fixture change. A mutation
accepted by one language and rejected by the other is a blocker.

## 13. Stage K — factual SSR

Extend `public_h2_document.py` with five deterministic articles:

- A1 year/role table;
- A2 role table;
- A3 outcome table;
- A4 RUB claim-price table;
- A5 masked-party table/list with overlap explanation.

Every article includes heading, visible collection scope, exact returned/total,
semantic caption/headers, N/M, limitations and empty enhancement host. Null
views render honest unavailable copy. `available_empty` renders known empty
population without an invented year/chart.

Escape every value and prove no case ID/HMAC/source identifier/name/arbitrary
URL appears in HTML or embedded JSON. Closed/v2/v3 SSR goldens and script-safe
closing-tag/control/Unicode cases are required.

## 14. Stage L — TypeScript semantics and factual parity

In `contractSchema.ts`:

1. Export concrete typed A1–A5/summary/detail/scope models rather than generic
   `PublicH2ViewDto` leaves.
2. Keep strict integers/canonical Decimal strings and exact nullable members.

In `contractSemantics.ts`:

1. Mirror every Stage J invariant without Number monetary truth.
2. Fix `available_empty` in sync with Python.
3. Dispatch v3 semantics only through the exact bound-source or source-less
   pre-result matrix from the specification; reject mixed codes/states/counts.
4. Enforce public ID/masked label/deferred detail/privacy patterns.

Add `arbitrationPresentation.ts` for literal suffix/labels only. The browser
does not calculate percentages, claim prices, roles, outcome or N/M.

Extend `parityVector.ts` with exact arbitration article kinds, headings,
scopes, captions, headers, cells/items, IDs, limitations and empty hosts.
Pre- and post-takeover vectors must match.

## 15. Stage M — React facts and lazy SVG

`ArbitrationFacts.tsx` reproduces SSR structure and always remains mounted.
Replace the current generic arbitration `view_id` surface in
`CompanyPublicH2Page.tsx`.

Generalize bootstrap to independent finance/arbitration lazy targets:

1. arm neither before strict parse/binding/digest/SSR/React parity;
2. create one observer/import generation per eligible section;
3. import arbitration renderer at most once near viewport;
4. teardown both controllers and root exactly once;
5. stale promises cannot mount;
6. unsupported observer/import/render failure stays local with visible
   `aria-live` and no retry/fetch.

`ArbitrationCharts.tsx` uses hand-authored SVG and bounded coordinate helpers:

- stacked A1 observed-year roles;
- A2/A3 fixed bars;
- signed A4 zero-axis intervals;
- A5 case-count bars.

Tests cover keyboard focus, mouse, touch, Escape/outside/focus-exit, tooltip
association, exact accessible names, 44×44 targets, long masked labels,
patterns/non-color distinction, reduced motion, partial/empty/large-N and
deterministic DOM/SVG snapshots. Browser screenshots remain iteration 25.

## 16. Stage N — asset manifest and release

1. Build Vite manifest with finance and arbitration dynamic chunks.
2. Confirm both dynamic JS/CSS closures are sorted optional paths and absent
   from initial entry closure.
3. Preserve old explicit `optional_chunk_paths: []` and current finance-only
   manifest-set compatibility.
4. Test missing/tampered arbitration chunk and retained SSR facts.
5. Continue rejecting unknown reachable asset types.
6. Do not run deploy/installer or modify production symlinks/config.

## 17. Targeted backend tests

```powershell
python -m pytest services/product_api/tests_unit/test_datanewton_provider_arbitration.py services/product_api/tests_unit/test_datanewton_provider_transport.py services/product_api/tests_unit/test_company_card_v2_decimal_transport.py services/product_api/tests_unit/test_company_card_v2_arbitration.py services/product_api/tests_unit/test_company_card_v2_writer.py services/product_api/tests_unit/test_company_report_worker.py services/product_api/tests_unit/test_company_report_worker_settings.py services/product_api/tests_unit/test_company_card_v2_serialization.py services/product_api/tests_unit/test_company_card_v2_privacy.py services/product_api/tests_unit/test_company_card_v2_public_h2.py services/product_api/tests_unit/test_company_card_v2_public_h2_contract_parity.py services/product_api/tests_unit/test_company_card_v2_public_h2_document.py services/product_api/tests_unit/test_company_card_v2_public_h2_side_effects.py services/product_api/tests_unit/test_company_card_v2_narrative_identity.py services/product_api/tests_unit/test_company_card_v2_narrative_service.py services/product_api/tests_unit/test_company_card_v2_presentations.py -q
```

Add focused new test modules when a single existing file would mix frozen V1
and new V2 matrices. The command must then include them explicitly.

Required matrices: durable operation/key decision and rotation, exact result/
lexical/envelope/cap binding, case identity/roles, Decimal/currency,
HMAC/grouping/public IDs, snapshot/repository/policy compatibility, A1–A5
reconciliation, source receipt, privacy sinks and no read writes.

## 18. Targeted frontend and asset tests

```powershell
npm run test --prefix services/web_ui -- src/companyPublicH2/contract.test.ts src/companyPublicH2/arbitrationPresentation.test.ts src/companyPublicH2/ArbitrationFacts.test.tsx src/companyPublicH2/ArbitrationCharts.test.tsx src/companyPublicH2/CompanyPublicH2Page.test.tsx src/companyPublicH2/bootstrap.test.tsx src/companyPublicH2/manifestGraph.test.ts
npm run build:company-public-h2-manifest --prefix services/web_ui
python -m pytest deploy/nginx/test_company_public_h2_release.py -q -p no:cacheprovider
```

If filenames differ, keep one-to-one coverage and record the exact command.
Test strict TS semantics, parity, no pre-parity import, independent teardown,
a11y interactions, signed A4, observed-only A1, masked A5, local error fallback
and optional asset integrity.

## 19. Disposable PostgreSQL

Create `scripts/run-iteration24-postgres-tests.ps1` using the proven iteration
23 safety pattern:

1. require an explicit local disposable PostgreSQL target;
2. create two uniquely named temporary databases: one migration-guard probe
   and one round-trip/integration target;
3. on the guard database, upgrade to the new revision's `down_revision` and
   exercise each independent predicate: exact pending H2 report with no job,
   exact pending H2 report with a mismatched job, exact queued/running H2 job
   with a mismatched report, and valid matching pending/queued plus
   pending/running pairs. Prove every upgrade aborts with
   `iteration24_active_h2_lineage_ambiguous` before either column exists,
   without changing the Alembic revision or rows; separately prove the
   predecessor FK rejects a physical job without a report;
4. run
   `services/product_api/tests/test_company_report_iteration24_migration.py`
   before the other integration tests. Against the round-trip database, the
   module must
   upgrade to the new revision's `down_revision`, create representative legacy
   terminal report/job rows and finalized H2 snapshot/pin pairs, upgrade to
   head, prove both new columns default to `false/null`, prove both DB checks
   reject disabled/non-null, prove historical policy derives only from the
   finalized snapshot/pin, downgrade the single new revision without losing
   predecessor data, and re-upgrade to head;
5. run the exact affected jobs/presentations/public-H2/narrative/Claims
   integration tests against the resulting head schema;
6. drop only the two databases created by this runner in `finally`;
7. reject production/unknown targets.

Exact entry command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-iteration24-postgres-tests.ps1
```

Required integration tests include
`services/product_api/tests/test_company_report_iteration24_migration.py`,
`services/product_api/tests/test_company_report_jobs.py` and
`services/product_api/tests/test_company_report_presentations.py`; add a
focused public-H2/Claims integration module only when unit coverage cannot
prove transaction/no-write behavior.

No production or unknown DB is touched.

## 20. Full mandatory checks

From repository root:

```powershell
python -m pytest services/product_api/tests_unit -q
python -m pytest services/gateway_api/tests -q
npm run lint --prefix services/web_ui
npm run test --prefix services/web_ui
npm run build --prefix services/web_ui
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-iteration24-postgres-tests.ps1
python -m compileall services/product_api/src/product_api shared
git diff --check
git status --short --branch
```

When the same disposable instance safely supports it, additionally run:

```powershell
python -m pytest services/product_api/tests -q
```

Python lint/type-check commands are not configured and must not be claimed.
Any baseline failure is reported with exact node IDs/signatures and compared
against the clean base; unrelated baseline code is not changed.

## 21. Independent code review

Reviewer checks the full diff and exact test results for:

1. No production/live/deploy/iteration-25 scope.
2. Separate operation gate and zero arbitration fetch callbacks when
   disabled/stale/keyless.
3. V1 collector/parser/hashes and v2 finance-only policy compatibility.
4. Snapshot v3 and policy v3 exact/atomic lineage.
5. One `ALL/0/1000` request and forced partial >1,000.
6. `case_id`-only new identity and exact-INN-only role attribution.
7. Raw-number manifest reuse and no float monetary truth.
8. Observed-only A1, reconciled A2/A3, RUB-only A4, all-masked A5.
9. Typed privacy allowlist without global scanner weakening.
10. Public/SSR/React parity, `available_empty`, top-20/N-of-M and byte cap.
11. Lazy chunk isolation, cleanup and keyboard/touch/error accessibility.
12. Only the approved additive report/job decision migration, with the
    pre-DDL zero-active-H2 guard, finalized snapshot/pin legacy lineage and safe
    terminal defaults; no dependency/raw fixture/secret/generated evidence
    leakage.
13. Disposable PostgreSQL safety and all claimed checks.

Blocking findings are fixed and re-reviewed before implementation is called
ready.

## 22. Completion and handoff

After `VERDICT: READY` from independent code review:

1. Mark iteration 24 `ready_for_merge` only after all required checks pass.
2. Inspect changed/staged paths for secrets, raw provider data, logs, caches,
   generated screenshots and unrelated edits.
3. Report exact snapshot/policy/operation compatibility, A1–A5 semantics,
   privacy, frontend/assets, migration status and test results.
4. Stop before commit/push unless the owner gives a separate explicit command.
5. PR, merge, deploy and production activation remain human/separate actions.

Recorded local results (2026-08-27):

- Product API unit suite: `1498 passed`;
- focused arbitration/presentation/public suite: `187 passed`;
- Gateway suite: `31 passed`;
- web suite: `496 passed`; ESLint and production build pass;
- H2 release suite: `34 passed`; iteration-24 migration contract: `5 passed`;
- `compileall`, Alembic head `0018_company_card_v2_arbitration`, runner parser,
  generated manifest/golden verification and `git diff --check` pass;
- disposable PostgreSQL execution is not claimed: Docker Desktop daemon is
  unavailable, no temporary database was created and no database was touched.
- final independent code review: `APPROVED`, no findings.
