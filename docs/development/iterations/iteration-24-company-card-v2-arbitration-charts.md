# Итерация 24 — Арбитражные графики Company Card v2

ID: 24

Slug: company-card-v2-arbitration-charts

Base commit: `8a1d27866187df470bc628f9b5e7f500204222e7`

Статус: implementation in progress after reviewed specification, independent
general and contract/privacy reviews `APPROVED`, and owner approval 2026-08-27

Owner implementation approval: `APPROVED` — user command 2026-08-27

Production activation: `NOT AUTHORIZED`

Implementation checkpoint 2026-08-27:

- approved code scope is implemented;
- Product API unit, focused backend, web test/lint/build, Gateway, release,
  migration-contract, compile and static repository checks pass;
- disposable PostgreSQL acceptance is pending because the local Docker Desktop
  daemon is unavailable; the runner was not allowed to fall back to an unknown
  database and no database was touched;
- final independent code review is `APPROVED` with no findings;
- iteration status remains `in_progress`, not `ready_for_merge`, only until the
  disposable-PostgreSQL acceptance check passes.

## 1. Цель

Реализовать default-off путь от одного bounded DataNewton arbitration response
до пяти доказательных представлений A1–A5:

- exact provider population либо явно обозначенная returned slice;
- только observed start years без synthetic zero;
- exact-INN роли и narrow company-scoped outcome;
- exact RUB claim prices без FX и debt wording;
- только маскированные opposing parties без имён и идентификаторов;
- одинаковые факты в immutable snapshot, DTO, SSR и React;
- table-first fallback и lazy accessible SVG enhancement.

Production provider operation, publication activation, deploy и rollout не
входят в итерацию.

## 2. Источники истины

Итерация следует, в порядке специфичности:

1. `decisions/iteration-24-owner-scope-decision-v1.md`.
2. `evidence/iteration-19-company-card-v2/iteration-24-gate-readiness-v2.md`.
3. `evidence/iteration-19-company-card-v2/arbitration-contract-evidence-v3.md`.
4. Architecture/privacy ADR и нормативным sections 13–16, 26–31 iteration 19.
5. Merged snapshot/persistence/public contracts iterations 20–23.
6. Эта спецификация и утверждённый implementation plan iteration 24.

При противоречии D1–D6 и evidence v3 точечно supersede старые предположения о
`id` fallback, multi-page completeness, named opponents и non-RUB currency.
Остальные архитектурные и privacy invariants iteration 19 сохраняются.

## 3. Scope

В scope входят:

1. Versioned arbitration evidence binding и отдельный operational gate.
2. Один exact `ALL/0/1000` provider request и conditional-zero envelope.
3. `ArbitrationBasisV2`, sanitized cases, provenance, counters и limitations.
4. `case_id`-only identity, strict role collections и exact-INN attribution.
5. Source-byte arbitration Decimal transport через существующий lexeme manifest.
6. Report-scoped all-masked opponent HMAC/grouping/public ordinals.
7. Pure deterministic arbitration Chart Facts и A1–A5 projection.
8. Durable report/job arbitration/key decision через additive migration.
9. Новый immutable snapshot schema v3 и publication policy v3.
10. Frozen reads/pins/digests для snapshot V1/V2 и publication policy v1/v2.
11. Closed Python/TypeScript validators и negative mutation corpus.
12. Factual SSR/React parity и независимый lazy arbitration chart chunk.
13. Unit, component, integration, asset/release and privacy tests.

## 4. Вне scope

Не входят:

- live DataNewton/FNS/Gateway/AI calls или production credentials in tests;
- production config changes, provider operation, assignment, deploy or rollout;
- production migration execution, backfill, refresh или rewrite immutable
  reports/pins; disposable test-DB upgrade/down/up остаётся обязательным;
- second arbitration request, multi-page pagination или completeness >1,000;
- historical calendar horizon, synthetic zero years или no-cases assertions;
- OGRN/name/fuzzy/`*_src` target matching;
- named legal/state/natural opponents или entity-type inference;
- non-RUB groups, FX, debt/award/collection semantics;
- `result_type`, instance/court labels и KAD links in first implementation;
- arbitration scoring, probability, verdict, prediction или win rate;
- изменения H1 normalizer/signals/scoring/Claims semantics;
- real-browser responsive/zoom/screenshot rollout matrix iteration 25;
- новые Python/npm dependencies.

## 5. Default-off operational boundary

Существующие defaults не меняются:

```text
COMPANY_CARD_V2_PRESENTATIONS_ENABLED=false
COMPANY_CARD_V2_WRITER_ENABLED=false
COMPANY_CARD_V2_ROLLOUT_GENERATION=0
COMPANY_CARD_V2_ALLOWLIST_INNS=[]
COMPANY_CARD_V2_PERCENTAGE_BASIS_POINTS=0
```

Добавляется отдельный default-off gate:

```text
COMPANY_CARD_V2_ARBITRATION_COLLECTION_ENABLED=false
```

При `false` новый enqueue сохраняет decision `false/null`; такой job использует
текущий snapshot-v2/finance-only behavior и не строит arbitration callback.
Уже сохранённый enabled job обрабатывается по emergency-gate правилу ниже.
Включение общего writer не включает arbitration автоматически.

При сохранённом enabled decision worker до provider call обязан:

1. проверить live emergency collection gate;
2. проверить exact evidence registry v2;
3. разрешить claimed mask key ID через private key-ring resolver и проверить
   secret bytes length;
4. зафиксировать request profile и report UUID.

Missing/unknown/malformed key или stale registry дают safe failed/gate-closed
arbitration result с `provider_callback_count=0`. Pure normalizer не читает
Settings/environment. Worker передаёт ему только provider result, target INN,
report UUID, secret bytes и nonsecret key ID.

Exact settings boundary:

```text
COMPANY_CARD_V2_ARBITRATION_COLLECTION_ENABLED=false
COMPANY_CARD_V2_ARBITRATION_MASK_ACTIVE_KEY_ID=<optional nonsecret ID>
COMPANY_CARD_V2_ARBITRATION_MASK_KEYRING_JSON=<optional SecretStr>
```

The raw active ID is accepted without trimming only when it matches
`[a-z][a-z0-9_]{0,31}`; otherwise enqueue persists null rather than failing
global Settings construction. The key-ring
secret is at most 8,192 UTF-8 bytes and is parsed only by the worker as a JSON
object with 1..16 unique matching key IDs and no duplicate/unknown structure.
Each value is canonical unpadded base64url; strict decode plus exact re-encode
must produce 32..64 secret bytes. Malformed JSON, encoding, IDs, missing active
entry or wrong length return only `privacy_key_unavailable`; secret text never
enters startup validation errors, logs, repr, model dump or persistence.

Operationally, a key ID is an immutable registry binding to one exact decoded
secret byte sequence: rotation creates a new ID, while every old ID/secret
mapping remains available until all reports and jobs that persist that ID have
drained or reached a terminal state. The runtime persists only the nonsecret
ID, not a secret fingerprint, so it cannot detect a same-ID byte rebind across
configuration changes or process restarts and this iteration does not claim
that guarantee. Such rebinding is forbidden by the external secret-registry
contract. Production activation remains unauthorized until iteration 25
verifies an immutable KMS/versioned-secret registry and retention procedure.
Removing old material early follows the safe `privacy_key_unavailable` path;
it does not make same-ID rebinding valid.

At enqueue, the live collection flag is sampled into the exact boolean
`arbitration_collection_enabled` and nullable nonsecret
`arbitration_mask_key_id`. Disabled requires null. Enabled may persist a valid
active ID or null; null guarantees pre-call failure. Report/job values must
match at reuse, claim, heartbeat and finalization. The worker resolves only the
claimed ID, never the then-current active ID. The live collection flag is also
an emergency execution gate: if a persisted-enabled job is claimed while the
flag is false, it records V3 `operation_gate_closed` with zero arbitration
fetch callbacks; it never falls back to V2 or changes the saved decision.
Rotation therefore affects only new jobs; old key material must remain in the
key-ring until old jobs drain, and premature removal fails those jobs safely
without an arbitration fetch callback.
Immutable old tokens are never recalculated. Production secret provisioning
and actual activation remain iteration 25 and a separate operational decision.

## 6. Version and compatibility matrix

### 6.1. Snapshot schemas

```text
CompanyCardV2SnapshotV1:
  frozen legacy shape without snapshot_schema_version

CompanyCardV2SnapshotV2:
  snapshot_schema_version = company_card_v2_snapshot_v2
  finance basis + narrative evidence
  arbitration_basis = frozen ArbitrationBasisV1

CompanyCardV2SnapshotV3 extends V2:
  snapshot_schema_version = company_card_v2_snapshot_v3
  arbitration_basis = ArbitrationBasisV2
  arbitration_chart_facts = ArbitrationChartFactsV1
  arbitration_chart_facts_hash = exact CJSON SHA-256
```

`report_version` remains literal `"3"`, writer profile remains
`company_card_v2_writer_v3`, and public contract remains
`company_public_h2_v1`. Persistence parser dispatches only by the exact raw
snapshot discriminator. Missing/unknown/coerced/cross-version shapes fail
closed. V1/V2 bytes, hashes and parser results remain unchanged.

The existing finance `ChartFactsV1` and its hash remain finance-only. They are
not extended with arbitration keys. The separate arbitration facts leaf avoids
changing old finance hashes.

Inherited `evidence_version="evidence_registry_v1"` and
`privacy_version="privacy_v1"` also keep their current counterparty/finance
meaning. Arbitration carries its own registry/normalization/privacy literals
inside `ArbitrationBasisV2`; they are not smuggled into the inherited fields.

### 6.2. Publication policies

```text
company_public_h2_publication_v1 = finance closed, arbitration closed
company_public_h2_publication_v2 = finance enabled, arbitration closed
company_public_h2_publication_v3 = finance enabled, arbitration enabled
```

Policy v3 is valid only with snapshot v3 and exact arbitration facts/hash.
Policy v2 forever remains finance-only even if code knows snapshot v3. Old
resolved/unresolved pins never switch policy, and historical report without a
pin is never backfilled on read/retry.

When the persisted arbitration decision is off, new writer behavior remains
snapshot v2 + policy v2. When that persisted decision is on, the writer records the
arbitration attempt as snapshot v3 + policy v3 even when evidence/key preflight
fails safely before a provider call. A preflight-admitted attempt makes exactly
one logical callback and records complete, partial or provider-failed V3 arbitration;
a rejected preflight makes zero requests and records a V3 failed/gate-closed
arbitration basis with no invented cases. Fenced report completion, immutable
snapshot, existing outbox result and unresolved pin remain one DB transaction.
Retry reuses exact lineage; mixed snapshot/policy/hash identity fails closed.

The existing pin fields stay finance-only:

```text
pin.chart_facts_version/hash = snapshot.chart_facts.version/hash
pin.evidence_registry_version = snapshot.evidence_version
```

No second arbitration hash is added to a pin. Policy v3 first parses snapshot
v3, recomputes arbitration facts and `arbitration_chart_facts_hash`, then
requires the exact stored report `snapshot_hash`; that hash transitively binds
the arbitration registry, basis, facts and hash. Narrative identity already
binds the same snapshot hash. The public root `chart_facts_version/hash` stays
finance-only, while the public `projection_digest` binds the projected A1–A5.
Mutation of any arbitration registry/basis/facts/hash at append, finalization
or resolve therefore fails without changing V1/V2 pin bytes.

The shared `WriterDecision` has a closed surface/version tuple before any
arbitration setting is sampled:

| Selected surface | Snapshot/publication lineage | Persisted arbitration decision |
|---|---|---|
| H1 | frozen existing H1 lineage | `false/null` only |
| historical H2 finalized | snapshot V1 / publication v1 | `false/null` only, saved snapshot plus exact pin |
| historical H2 finalized | snapshot V2 / publication v1 | `false/null` only, saved snapshot plus exact pin |
| H2 finance-only | snapshot V2 / publication v2 | `false/null` only |
| H2 arbitration-enabled | snapshot V3 / publication v3 | `true/(valid key ID or null)` only |

The live flag and active key ID are sampled only after exact H2 selection.
H1 never reads them. `true/null` is valid only for the H2 V3 safe pre-call
privacy failure; `false/non-null`, H1+enabled, V2+enabled, V3+disabled and every
cross-policy tuple are invalid. For live report jobs the same validator is
applied at enqueue, reuse, claim, heartbeat, expired/failure reconciliation
and finalization, not only in known constructors. After the guarded migration
described below, an active H2 `false/null` tuple means only a new V2/v2 job
created by upgraded code, while an active H2 enabled tuple means only V3/v3.

Historical H2 V1/v1 and V2/v1 are accepted only when the report is already
`complete` or `partial`, its immutable snapshot parses as the claimed V1/V2
version, and an exact unresolved or resolved publication-v1 pin supplies the
lineage. Historical V2/v2 reads use the same finalized snapshot-plus-pin rule.
Those finalized reports may continue public reads and narrative
retry/reconciliation because their policy is durable. A pre-upgrade H2
`pending` report or `queued`/`running` report job is never interpreted as any
historical/current policy and is not eligible for claim, heartbeat, retry or
reconciliation after the revision. New enqueue may create only V2/v2 or
enabled V3/v3 and must never create a policy-v1 lineage.

Narrative finalization inherits only the saved pin policy and creates/reuses a
resolved pin with the same policy. Resolver selects v1/v2/v3 projection only
from the resolved pin, checks exact projection digest and never writes.

Snapshot V3 may be added to the narrative snapshot-version allowlist, but it
does not widen the AI evidence contract. `NarrativeEvidenceEnvelope` remains
the existing closed primary-activity-only shape: evidence registry version,
one admitted primary-activity label or its fixed missing limitation. The
prompt builder and Gateway request schema remain unchanged, chart comments
remain empty and no snapshot object is passed to them. For equal primary
activity, evidence version, dispatch ID and request settings, V2 and V3 build
the same Gateway body bytes.

No arbitration basis/facts, private or public case/opponent ID, `first_number`,
name, full HMAC, key metadata, amount/Decimal, currency, role, outcome,
counter, limitation or raw value may enter the evidence envelope, prompt,
Gateway body, request logs or AI response-validation context. Snapshot hash
may continue to bind private generation identity but is not prompt evidence.
Tests use only a mocked Gateway sender and poison every forbidden arbitration
leaf, compare the captured request with the V2 reference body and scan its
recursive values/serialized bytes; no live AI call is allowed.

The response validator no longer receives `PreparedNarrativeDispatch` or
`ValidatedNarrativeReport`. It accepts only a closed
`NarrativeResponseValidationContextV1` containing exact
`gateway_dispatch_id`, 64-hex `generation_key` and the existing
`NarrativeEvidenceEnvelope`, plus the Gateway response. It returns the
validated artifact draft/rendered narrative without reading a snapshot or
computing a public projection. Only after that validation succeeds does the
caller use its separately held private snapshot and saved publication policy
to compute the projection digest. That post-validation projection step is not
passed back into the AI validator, Gateway or logs. A recursive poison test
captures the actual validator arguments as well as the external request.

One append-only Alembic migration is required solely to add the durable
arbitration decision to both report and job rows:

```text
arbitration_collection_enabled BOOLEAN NOT NULL DEFAULT false
arbitration_mask_key_id VARCHAR(32) NULL
```

Before any DDL, inside the same migration transaction, the revision locks
`company_reports` and then `company_report_jobs` in fixed order using
PostgreSQL `SHARE ROW EXCLUSIVE` so enqueue/state writes cannot race the guard.
It then evaluates two independent `EXISTS` predicates without an inner/equality
join: (1) any `pending` report with exact
`writer_profile="company_card_v2_writer_v3"`, `report_version="3"`,
`presentation_contract="company_public_h2_v1"`, `rollout_generation>0`,
regardless of whether a job exists or matches; and (2) any `queued`/`running`
job with exact `writer_profile="company_card_v2_writer_v3"`,
`presentation_contract="company_public_h2_v1"`, `rollout_generation>0`,
regardless of its report tuple. Either predicate aborts upgrade with the fixed
safe error `iteration24_active_h2_lineage_ambiguous`; it does not add columns,
rewrite a row or guess V1/v1, V2/v1 or V2/v2. Thus a missing/mismatched job for
an exact pending H2 report and a mismatched report for an exact active H2 job
both fail closed; physical job-without-report remains impossible under the
existing foreign key and is regression-tested. The eventual iteration
25 production procedure must pause H2 enqueue, drain or safely terminalize old
active H2 report jobs under the old binary, prove both counts are zero, and
only then run the revision. That operational procedure and production upgrade
remain unauthorized here.

After the guard passes, existing terminal rows become `false/null`.
Application validators enforce the ID grammar; each table has
`CHECK (arbitration_collection_enabled OR
arbitration_mask_key_id IS NULL)`, so disabled/non-null is impossible.
Report/job equality is part of the existing writer fence. No snapshot, pin or
presentation schema column is added. Existing H1 constructors and their
reconciliation/failure paths always materialize the same `false/null` tuple
and never sample or persist the arbitration active key; their report meaning
and provider behavior remain unchanged. Finalized historical H2 lineage is
derived only from its snapshot and pin, never from these defaulted columns.
The migration is applied only to the disposable test database in this
iteration; production migration execution remains unauthorized.

## 7. Evidence registry and exact request

`ARBITRATION_EVIDENCE_REGISTRY_V1` remains the frozen closed iteration-20
registry. New V2 metadata binds:

```text
registry_version = datanewton_arbitration_registry_v2
contract_binding = datanewton_arbitration_openapi_v1_2026_08_26
openapi_sha256 = 2c3d34ab00a35e58e07f7c3dea32b605b9e61d112a92a1654fd54e415ef851d2
runtime_dataset = arbitration_cases
endpoint = GET /v1/arbitration-cases
identity_policy = arbitration_case_identity_case_id_only_v1
target_policy = arbitration_target_exact_inn_v1
collection_policy = datanewton_arbitration_single_page_1000_v1
```

The only request is:

```text
identifier = exact normalized 10- or 12-digit subject INN
company_role = ALL
offset = 0
limit = 1000
status/start_date/end_date/updated_at_from/need_document = omitted
```

The returned `DataNewtonResult` must bind exact
`dataset="arbitration_cases"`, endpoint, requested INN and the exact parameter
map. Any drift is rejected before normalization. No second call is constructed
under any outcome.

The shared `DataNewtonResult.received_at` validator checks the parsed input
offset before canonicalization and accepts only an aware zero-UTC-offset
timestamp. A non-zero offset is rejected rather than silently converted with
`astimezone`; existing V1/V2 UTC inputs and their serialized bytes remain
unchanged.

The closed result binding is:

```text
provider = datanewton
dataset = arbitration_cases
endpoint = /v1/arbitration-cases
requested_identifier = exact target INN
requested_identifiers = []
request_parameters = {inn: target INN, company_role: ALL, offset: 0, limit: 1000}
request_body = null
status_code = 200
request_id = company-report:{lowercase report UUID}
response_hash = calculate_response_hash(raw_payload)
```

Key set and JSON scalar types are exact; bool never equals integer. One request
means one logical `fetch_arbitration_cases` callback and no pagination/follow-up
call. The existing transport may retry the identical GET according to its
configured retry setting; `DataNewtonResult.attempts>=1` records that and
no attempt payloads are merged. Tests distinguish callback count from HTTP
attempt count. After this outer binding, `lexical_transport_valid=true` is the
separate mandatory whole-response transport gate in section 8. A future
multi-page call remains forbidden.

## 8. Envelope and completeness

`total_cases`, `offset` and `limit` are exact JSON integers. Boolean, float,
string, missing or negative values are invalid. `total_cases` is additionally
bounded to signed int64 `0..9223372036854775807`. Local envelope rules:

```text
offset == 0
limit == 1000
total_cases == 0:
  data absent or exactly [] -> valid empty
  nonempty/non-array data -> envelope_invalid
0 < total_cases <= 1000:
  data must be an array and len(data) == total_cases
total_cases > 1000:
  data must be a nonempty array of at most 1000 rows
  collection is always partial with source_total_exceeds_cap
```

Complete requires an exact valid envelope with `total_cases<=1000`, every raw
row processed within caps, valid `case_id`/role shape, no conflicting duplicate
and successful privacy normalization. Identical canonical duplicate rows may
collapse with a counter; conflicting duplicates remove the key and force
partial. A malformed/oversized/cap-excluded row forces partial.

Single-page completion reasons have fixed precedence:

```text
operation_gate_closed
evidence_gate_closed
privacy_key_unavailable
provider_error
provider_binding_invalid
lexical_transport_invalid
envelope_invalid
malformed_rows
duplicate_conflict
oversized_case
storage_cap_exhausted
opponent_group_cap_exhausted
source_total_exceeds_cap
complete
```

`complete` is the sole reason when true. `completion_reason` exposed in each
non-null public summary is exactly the first ordered basis reason. Optional
case field/date/amount/currency limitations that do not remove the case affect only relevant view
coverage, not collection completeness.

`lexical_transport_valid=false` rejects the entire provider result before any
envelope, `case_id`, role, party or amount leaf is read. Duplicate JSON keys or
scalar/object/array topology drift may affect identity, not merely money, so
this state persists zero cases with `lexical_transport_invalid`; it is never a
local A4-only limitation.

Counter stages are unambiguous: every preflight rejection has
`pages_requested=pages_accepted=0`; invoking the one logical callback sets
`pages_requested=1` even when it raises; `pages_accepted=1` only after exact
result binding, lexical transport and envelope acceptance. `rows_observed` is
then exactly the accepted `data` length before row validation. The one page
manifest exists iff `pages_accepted=1`.

`ArbitrationCollectionCountersV2` is a closed immutable model with exactly:

```text
pages_requested: 0 | 1
pages_accepted: 0 | 1
rows_observed: 0..1000
rows_processed: 0..1000
rows_shape_valid: 0..1000
malformed_count: 0..1000
oversized_case_count: 0 | 1
storage_cap_rejected_count: 0 | 1
duplicate_identical_count: 0..1000
duplicate_conflict_row_count: 0..1000
duplicate_conflict_key_count: 0..500
unique_case_count: 0..1000
opponent_token_count: 0..20000000
opponent_group_count: 0..20000
opponent_group_probe_count: 0..20001
```

Every member is a strict integer; bool and coercion are rejected. Invoking the
logical callback sets `pages_requested=1`; only exact binding plus lexical and
envelope acceptance sets `pages_accepted=1`. If no page is accepted, all row
and opponent counters are zero, `source_total` is null and the page manifest
is absent; a bound `provider_received_at` may still exist after a later
lexical/envelope rejection. On an accepted page, `source_total` is the exact
validated total and `rows_observed=len(data)`. `rows_processed` counts the source-order prefix for
which classification began, including the row that triggers a case/basis cap.
`malformed_count == rows_processed - rows_shape_valid`.

After mandatory row shape/role normalization, each shape-valid row belongs to
exactly one final non-overlapping class: retained unique representative,
identical duplicate of a nonconflicting key, row of a conflicting key,
oversized case, or basis-cap rejected row. Therefore:

```text
rows_shape_valid ==
  unique_case_count
  + duplicate_identical_count
  + duplicate_conflict_row_count
  + oversized_case_count
  + storage_cap_rejected_count
```

Case size is checked before dedup. An oversized row does not enter the dedup
map. Conflict classification is final: every case-size-valid row for a key
that acquires two different normalized candidates counts only in
`duplicate_conflict_row_count`, including its first row and later repeats;
that key contributes nothing to unique/identical counts.
`duplicate_conflict_row_count >= 2 * duplicate_conflict_key_count`.
Only after this identical/conflict transition is the exact metadata-reserved
envelope below rebuilt from the post-dedup case tuple and checked against
8 MiB. Identical rows and a conflict that removes a previously retained key
cannot trigger the basis cap. `storage_cap_rejected_count=1` only for a new
nonconflicting representative whose post-dedup reserved envelope exceeds the
cap; that row is not admitted and processing stops.
At most one of `oversized_case_count` and `storage_cap_rejected_count` is one.
Without either cap reason, `rows_processed==rows_observed`; a shorter prefix
requires exactly one of those reasons. Identical duplicates do not make the
collection partial; conflicting keys are removed and do.

`unique_case_count==len(sanitized_cases)`. For the sole accepted manifest,
`returned_count==rows_observed` and `accepted_count==unique_case_count`.
`opponent_token_count` is the sum of persisted, within-case-deduplicated token
tuple lengths; `opponent_group_count` is the exact distinct persisted HMAC
count. `opponent_group_probe_count` is the distinct transient HMAC count from
the deterministic cap probe, saturated at 20,001. Without overflow it equals
`opponent_group_count`; with overflow it is exactly 20,001 while both
persisted opponent counters are zero under the scrub rule in section 12.

Every non-null `PublicArbitrationSummary` keeps the frozen
`company_public_h2_v1` field set exactly: `source_total`, `rows_observed`,
`unique_case_count`, `malformed_count`, `duplicate_identical_count`,
`duplicate_conflict_count`, `collection_complete`, `completion_reason`,
`calendar_complete`, `calendar_scope`, nullable `calendar_start_year`,
`calendar_end_year`, `calendar_evidence_version`, nullable
`observed_start_year`, `observed_end_year`, `unknown_year_count` and
`zero_years_proven`. No new summary field is added. Mapping is exact:
`rows_observed`, `unique_case_count`, `malformed_count` and
`duplicate_identical_count` use their same-named private counters, while
public `duplicate_conflict_count=duplicate_conflict_key_count`, never the raw
conflict-row count. Calendar values obey the unverified/observed-only contract
in sections 9 and 14. Oversize, storage and opponent/HMAC probe counters remain
private; their effect is exposed only through existing completion reason,
limitations, coverage totals and, when valid, A5 public group/detail scopes.

Hard bounds remain:

```text
raw rows encountered <= 1000
sanitized cases <= 1000
persisted distinct private opponent groups <= 20000
transient opponent group probe <= 20001
persisted opponent token memberships <= 20000000
one sanitized case <= 262144 CJSON bytes
sanitized ArbitrationBasisV2 <= 8388608 CJSON bytes
public CompanyPublicH2Response <= 524288 CJSON bytes
```

The basis storage policy is literal
`arbitration_basis_metadata_reserve_v1`. For each post-dedup candidate tuple,
the cap check builds an exact CJSON sizing mapping with that actual
`sanitized_cases` array and substitutes every other V2 basis member with its
lexically longest permitted CJSON representative. This includes a present
maximal page manifest, signed-int64 source total, longest admitted UTC-Z
receipt/key ID/fixed literal, maximum value of every counter, every ordered
non-`complete` completion reason and the full closed basis-limitation catalog.
The sizing mapping is not a semantic basis instance; it is a deterministic
byte upper bound with the same fixed object keys and actual case-array bytes.

The closed `ArbitrationBasisLimitationV2` catalog is exactly:

```text
operation_gate_closed
evidence_gate_closed
privacy_key_unavailable
provider_error
provider_binding_invalid
lexical_transport_invalid
envelope_invalid
malformed_rows
duplicate_conflict
oversized_case
storage_cap_exhausted
opponent_group_cap_exhausted
source_total_exceeds_cap
arbitration_calendar_unverified
arbitration_unknown_year
arbitration_date_invalid
arbitration_date_inversion
arbitration_year_conflict
arbitration_first_number_unavailable
arbitration_first_number_identity_collision
arbitration_amount_missing
arbitration_amount_invalid
arbitration_currency_missing
arbitration_currency_unidentified
arbitration_currency_invalid
```

Unknown/free-form codes are rejected; the public-only projection-cap code is
not a basis limitation. CJSON equality at 8,388,608 bytes is admitted and
8,388,609 is rejected. Tests freeze the computed reserve bytes and prove for
every bounded non-case field representative that actual final metadata is no
longer than the reserve. Therefore later counter digit growth, reasons,
limitations, group metadata and token scrubbing cannot make a previously
admitted final `ArbitrationBasisV2` exceed 8 MiB. Final construction still
asserts the real CJSON length as a defense-in-depth invariant.

Bounds count raw array elements before validation. Raw pages, headers, request
body, names, identifiers, secrets and arbitrary provider text are not persisted.
Safe page provenance stores only exact offset/limit, returned/accepted counts
and the provider response hash. `provider_received_at` stores the exact UTC-Z
`DataNewtonResult.received_at` only after outer result binding succeeds; it is
null when no bound provider result exists. Its CJSON uses the existing strict
UTC serializer in `YYYY-MM-DDTHH:MM:SS[.ffffff]Z` form, 20..27 ASCII bytes;
offset/naive/out-of-range values fail binding rather than expanding storage.
No current/read time repairs it.

The writer/public lifecycle is exact:

| Persisted decision/outcome | Callback | Snapshot/policy | Arbitration basis | A1–A5 coverage | Report effect |
|---|---:|---|---|---|---|
| disabled `false/null` | 0 | V2 / policy v2 | frozen V1 closed basis | null / `gate_closed` | exact existing finance lifecycle |
| persisted enabled, live operation gate off | 0 | V3 / policy v3 | zero cases, `operation_gate_closed` | null / `gate_closed` | arbitration is failed; available finance is preserved and report is at most `partial` |
| enabled, evidence preflight rejected | 0 | V3 / policy v3 | zero cases, `evidence_gate_closed` | null / `gate_closed` | same containment |
| enabled, key ID/secret rejected | 0 | V3 / policy v3 | zero cases, `privacy_key_unavailable` | null / `failed` | same containment |
| admitted, provider raises before result | 1 logical | V3 / policy v3 | zero cases, `provider_error` | null / `failed` | same containment |
| returned result has binding/lexical/envelope failure | 1 logical | V3 / policy v3 | zero cases, exact failure reason | null / `failed` | same containment |
| valid returned slice | 1 logical | V3 / policy v3 | admitted safe cases, incomplete | non-null / `partial` except view-specific failure | report `partial` |
| valid exact complete population | 1 logical | V3 / policy v3 | complete, including exact zero | non-null / `available` or `available_empty`, subject to view limitations | existing other datasets determine `complete` versus `partial` |

Preflight short-circuits in live-gate, evidence, then key order and therefore
records exactly one preflight reason. Post-response row/cap reasons may coexist;
their fixed precedence chooses the public primary reason and every safe reason
remains in the ordered basis tuple. A whole
report becomes `failed` only under the pre-existing aggregate rule that no
required dataset remains usable; arbitration failure alone never destroys
available counterparty/finance data.

All V3 failure rows in the table assume usable counterparty/finance inputs and
therefore finalize a snapshot with report lifecycle `partial`. If the existing
core-dataset rule independently yields whole-report `failed`, no normalized
snapshot or presentation pin is finalized; iteration 24 does not change that
older rule.

## 9. ArbitrationBasisV2 and sanitized case

`ArbitrationBasisV2` is a new closed model and contains:

```text
basis_version = company_card_arbitration_basis_v2
normalization_version = company_card_arbitration_normalization_v2
contract_binding / openapi_sha256
identity_policy / target_policy / collection_policy
storage_budget_policy = arbitration_basis_metadata_reserve_v1
outcome_policy = arbitration_party_result_narrow_v1
currency_policy = arbitration_rubles_only_v1
privacy_policy = arbitration_opponents_all_masked_v1
source_total = signed int64 | null
page_manifest = zero or one accepted page
provider_received_at = UTC-Z | null
counters and ordered completion_reasons
collection_complete
calendar_complete = false
calendar_scope = unverified
unknown_year_count
zero_years_proven = false
mask_algorithm_version = opponent_hmac_sha256_v1 | null
mask_key_id = validated nonsecret ID | null
sanitized_cases sorted by private case key
limitations sorted and deduplicated
```

`mask_algorithm_version` and `mask_key_id` are paired: both are non-null only
after the persisted job key ID resolves to valid secret bytes, even if the
later provider call fails; otherwise both are null. The intended job key ID
remains only in the durable report/job decision. Every private token must carry
the same effective pair as its basis; a null pair requires zero tokens.

Every `SanitizedArbitrationCaseV2` contains only:

```text
private case_id key
optional safe first_number
optional verified start year
one role: plaintiff | respondent | other | unattributed
one outcome: won | lost | returned | unknown
optional start/update ISO dates and safe duration input
amount state: available | missing | invalid, plus paired exact Decimal
currency state: rub | missing | unidentified | invalid
ordered tuple of eligible PrivateOpponentTokenV2
case-level limitation codes
```

`PrivateOpponentTokenV2` contains only full 64-hex HMAC, algorithm version and
nonsecret key ID. It contains no name, source INN/OGRN, source role/ordinal or
source row.

`ArbitrationChartFactsV1` is a separate immutable derived leaf. It contains
the closed summary/aggregate/detail inputs for A1–A5 and no raw provider value.
Its `collection_state` is exact:

```text
operation_gate_closed or evidence_gate_closed -> gate_closed
privacy/provider/binding/lexical/envelope failure -> failed
valid admitted incomplete collection -> partial
complete basis -> complete
```

`gate_closed`/`failed` facts have no aggregates and cannot be projected as a
known empty population. `partial` may legitimately have zero admitted cases;
only exact complete zero becomes `available_empty`.
The writer builds it purely from `ArbitrationBasisV2`; model/finalization
recomputation must match both the exact object and its CJSON hash. Derived facts
are not added to the 8 MiB sanitized-basis cap, but the final public DTO cap
still applies.

## 10. Identity, rows and role attribution

The new case key is a `case_id` string that is already NFC, contains 1..256
Unicode scalars and at most 1,024 UTF-8 bytes, has no leading/trailing Unicode
whitespace and contains none of U+0000..U+001F, U+007F..U+009F,
U+D800..U+DFFF, U+202A..U+202E or U+2066..U+2069. Non-string, blank, rewritten
or over-bound values make the row malformed.
Provider `id` is ignored by V2 normalization. `first_number` is separately
admitted only by `arbitration_first_number_display_v1`: the source string must
already be NFC, contain no surrounding whitespace, fit 1..22 Unicode scalars
and 32 UTF-8 bytes, and exactly match
`(?:(?:А|A)[0-9]{1,3}|СИП)-[0-9]{1,12}/[0-9]{4}`. It is not rewritten. Any
other value becomes null with `arbitration_first_number_unavailable`. This is
a deliberately conservative public allowlist, not a claim that the regex
enumerates every provider case-number spelling; `case_id` never repairs it.
Immediately after lexical/envelope acceptance and before any row can be
excluded, deduplicated or skipped by a cap, normalization builds one bounded
ephemeral collision set. It includes the exact `case_id` string leaf from
every object in the accepted `data` array when that leaf independently passes
the full `arbitration_first_number_display_v1` grammar. This pre-scan covers
otherwise malformed, conflicting, oversized, basis-cap-excluded and later
unprocessed rows. The set is never persisted, hashed, logged or returned and
is discarded after normalization. A valid `first_number` equal by exact
Unicode value to any member is stored as null with
`arbitration_first_number_identity_collision`. Projection also redundantly
sets a candidate equal to any surviving private basis `case_id` to null before
the recursive sink scan. Thus a provider case identity cannot reach the
approved display leaf through an excluded row.

All nine documented role members must be arrays for a nonzero case row:

```text
plaintiffs
respondents
third_parties
interested_persons
creditors
creditors_current_payments
debtors
applicants
others
```

Missing/non-array collection or non-object party makes role evidence
incomplete and the case malformed; it is never interpreted as an empty role.
Target match uses only an exact ASCII 10/12-digit `party.inn` equal to the
subject INN. OGRN, names, fuzzy values and every `*_src` leaf are forbidden
target fallbacks.

The set of matching collections maps to exactly one public role:

```text
only plaintiffs  -> plaintiff
only respondents -> respondent
any other nonempty set -> other
empty set -> unattributed
```

Each admitted case enters one and only one role bucket.

## 11. Dates, year, outcome and amount

`year` is accepted only as a non-boolean integer in `1900..2100`. It is not
derived from current time. When valid `date_start` and `year` disagree, year is
unavailable with `arbitration_year_conflict`; the date does not silently repair
the provider year. Unknown year is counted and appears only in the separate
unknown bucket.

Dates are strict ISO calendar dates. Update before start makes duration null
and adds `arbitration_date_inversion`; missing date stays missing. The duration
label, when available, is `От подачи до последнего обновления`, never proceeding
duration.

Outcome is case-sensitive:

```text
unambiguous plaintiff/respondent + WON      -> won
unambiguous plaintiff/respondent + LOST     -> lost
unambiguous plaintiff/respondent + RETURNED -> returned
all other tokens, missing, other/unattributed role -> unknown
```

Raw outcome tokens are not public. `result_type`, document/status text and
court text never repair outcome.

For `/data/{index}/sum`, an absent/null value is missing. The only admitted
non-null source type is the schema-bound JSON number, accepted through the
existing byte-number lexeme manifest at the exact pointer and parsed by
`company_card_source_decimal_v1`. JSON string, post-decoding float without an
exact manifest, bool, missing manifest, exponent/nonfinite/over-precision or
invalid grammar produces an unavailable A4 amount and limitation, not zero.
Valid exact zero and negative Decimal remain valid.

Currency normalization is exact:

```text
RUBLES -> rub
absent/null -> missing
OTHER or any unknown nonblank token -> unidentified
empty/whitespace-only string or non-string -> invalid
```

Only `(amount available, currency rub)` is A4-group eligible. Exact public
display replaces decimal dot with comma, uses Unicode minus and appends
` ₽` without numeric rounding. The value is always described as `Цена иска`.

Amount pairing is closed: `available` requires one non-null exact Decimal and
no amount limitation; `missing` requires null Decimal plus
`arbitration_amount_missing`; `invalid` requires null Decimal plus
`arbitration_amount_invalid`. Zero and negative are valid `available` values.
No state is inferred only from a limitation string during later parsing.

## 12. Opponent privacy and public ordinals

Eligible source collections are only:

```text
case role plaintiff  -> respondents
case role respondent -> plaintiffs
case role other/unattributed -> none
```

Every eligible party is `masked_unknown`. Names and entity type are never read
for public output. Stable private identity uses the exact party row under
`arbitration_opponent_stable_identifier_v1`:

1. one valid, direct and nonconflicting `inn` candidate;
2. otherwise one valid, direct and nonconflicting `ogrn` candidate;
3. otherwise `case_id + source role collection + zero-based party ordinal`.

The field name supplies the kind; length never changes an INN into an OGRN or
vice versa. An INN is exact ASCII digits of length 10 or 12 and an OGRN is
exact ASCII digits of length 13 or 15; there is no punctuation/whitespace
stripping, checksum inference or name repair. Transport-level duplicate object
keys invalidate the response before this matrix. `inn_src` may be absent/null
or exact `INN` for the INN to be direct; `ogrn_src` may be absent/null or exact
`OGRN` for the OGRN to be direct. `NAME`, `ADDRESS`, the opposite-kind token,
unknown/non-string/collection provenance makes that candidate ineligible for
stable grouping. `name_src` is never consulted. One eligible INN and OGRN may
coexist and INN wins. Otherwise the exact case-position fallback is mandatory.
The provenance value never becomes an identifier. Duplicate eligible parties
with the same HMAC inside one case collapse before group counts.

After all admitted cases are normalized, scan cases by private case key and
each within-case token by full-HMAC order. The transient distinct-group probe
stops at a saturated sentinel of 20,001. At 0..20,000, persist every token and
the exact token/group counts. At 20,001, atomically replace every admitted
case's opponent-token tuple with empty, set persisted `opponent_token_count`
and `opponent_group_count` to zero, retain only
`opponent_group_probe_count=20001`, discard the transient HMAC set, add
`opponent_group_cap_exhausted`, make collection completeness false and make
A5 null/failed. A1–A4 retain the scrubbed admitted cases with
returned-slice/partial scope. No HMAC or provider/popularity-order subset is
persisted. Dedup/duplicate-conflict classification and its counters are frozen
from each pre-scrub normalized candidate CJSON; the atomic token scrub never
changes identity history or makes two formerly different rows identical.
Exactly 20,000 remains valid subject to basis/public byte caps.

Normal projected A5 coverage uses `total=source_total`,
`returned=rows_observed` and `eligible=opponent_group_count`, with the exact
complete/returned-slice population scope. The 20,001 overflow does not claim
an exact group total from its saturated private probe. Its public tuple is
exactly:

```text
block = null
state = failed
population_scope = returned_slice
total = source_total
returned = rows_observed
eligible = null
limitation_codes = [opponent_group_cap_exhausted]
```

The private sentinel is never projected as `eligible=20001`, and scrubbed zero
counts are never misreported as `eligible=0`. If the later whole-response byte
fallback applies, it preserves this nullable candidate count evidence while
using the projection-cap limitation required by section 19.

HMAC uses the exact `OpponentHmacIdentityV1` CJSON contract and full digest.
Missing key fails before provider call. Raw names/identifiers are discarded
before `ArbitrationBasisV2` construction.

Cases receive report-scoped `case_[0-9]{6}` IDs by the frozen
`CasePublicOrderIdentityV1` CJSON order. Opponents receive
`opponent_[0-9]{6}` by the frozen `OpponentPublicOrderIdentityV1` order using
the fixed all-masked values `display_kind="masked_unknown"`,
`private_identity_kind="masked_hmac"` and the full private HMAC only during
ordinal assignment. Index zero, overflow, duplicate or mismatched ordinal
fails projection. Every
opponent display is exactly `Сторона скрыта N`, with the same one-based ordinal
as its zero-padded public ID and unpadded ASCII-decimal `N`.

The policy-v3 emitter scanner becomes path/type-aware only for these
contracted public fields. It runs with the saved v3 pin policy before digest,
cache and SSR; the TypeScript semantic check uses the exact two-branch v3
discriminator matrix in section 19, never a mutable default. Global rejection of raw
case/opponent identity, names, full HMAC, secret/key data, arbitrary URLs and
HTTPS strings is not weakened. The generic frozen `company_public_h2_v1`
parser remains able to read the historical dense contract corpus; its broader
legacy value domain is not authority for a new v3 emitter.

## 13. Common A1–A5 scope and details

Every non-null arbitration block exposes the same reconciled summary. Scope is:

```text
collection_complete=true  -> complete_collection
collection_complete=false -> returned_slice
```

Counts use only admitted unique cases; they are never scaled to source total.
Every scope visibly carries exact returned/source totals where known. Detail
arrays are sorted before cap and use `shown=min(eligible_total,20)` with exact:

```text
показано N из M дел
показано N из M сторон
```

Common case detail order is year descending/null last, start date
descending/null last, update date descending/null last, then the assigned
report-scoped case public ordinal ascending. The ordinal is assigned before
top-20 selection by the frozen `CasePublicOrderIdentityV1` CJSON order; the raw
private case key never survives projection.

First implementation details allow case number, role, outcome, exact RUB
amount, start/update date and safe duration. `result_detail`, instance count,
courts, opponents inside generic case detail and public case URL remain null or
empty. A5 group identity supplies its masked opponent separately.

Coverage rules:

- exact complete zero uses non-null zero-population blocks and
  `available_empty`;
- valid nonempty complete A1–A3 are `available`;
- a returned slice is `partial`, including one with zero admitted rows, except
  the exact 20,001-opponent-group overflow whose A5 coverage is `failed` with
  `population_scope=returned_slice`;
- A4 is `partial` when any amount/currency exclusion affects its source cases;
- A5 may be `available_empty` when complete and no eligible opposing group;
- pre-call/provider/envelope failure with no valid collection makes blocks null
  and coverage `failed`/`gate_closed` with linked limitations;
- old policy v1/v2 always keeps A1–A5 null/gate-closed.

Python and TypeScript root validators must treat non-null `available_empty` as
valid; the current two-sided drift that rejects it is fixed together.

## 14. A1 — activity by observed year

A1 uses verified provider `year` only. Without calendar evidence:

```text
calendar_complete = false
calendar_scope = unverified
zero_years_proven = false
```

No absent year is inserted. If verified years span at most ten distinct years,
show all observed years ascending; otherwise show the ten greatest observed
years. The nullable unknown-year bucket is last. Empty data creates no current
year.

Each bucket contains fixed role order plaintiff/respondent/other/unattributed;
counts sum to bucket total. `all_time_case_count` includes all admitted cases,
including observed years outside the displayed ten and unknown-year cases.
Role details are exact bucket populations capped at 20.

## 15. A2 — roles

Bars have fixed order:

```text
plaintiff, respondent, other, unattributed
```

Denominator equals unique admitted cases and bar counts sum exactly to it.
Zero denominator gives four null percentages. Positive denominator uses
Decimal precision 34, scale 6, `ROUND_HALF_UP`; residual to exact canonical
100 goes to greatest absolute unrounded remainder with fixed category tie
order. UI uses backend strings and never recomputes roles or percentages.

## 16. A3 — outcomes

Bars have fixed order:

```text
won, lost, returned, unknown
```

Denominator/count/percentage rules equal A2. Unknown is not loss, returned is
not a decided dispute and no win rate is produced. Details use only the stored
company-scoped narrow mapping.

## 17. A4 — RUB claim prices

There is at most one currency group:

```text
source_currency_id = RUB
display_currency = ₽
```

Top-20 order is:

```text
ABS(amount) DESC
amount DESC
year DESC NULLS LAST
update_date DESC NULLS LAST
assigned report-scoped case public ordinal ASC
```

Equal amounts with different case ordinals remain distinct. Axis is exact over
displayed cases and contains zero; each geometry interval is `[0, amount]` and
matches the case ID/order exactly. No client monetary arithmetic is allowed.

`missing_amount_count` counts only absent/null `sum`. Invalid/lossy numeric
transport is excluded with its own limitation and makes A4 partial, but never
increments the missing count. `missing_currency_count` counts
only absent/null currency tokens. `OTHER`/unknown nonblank adds
`arbitration_currency_unidentified` and is not missing. Excluded cases remain
in A1–A3/A5 populations. Invalid currency is also not missing; it adds
`arbitration_currency_invalid` and makes A4 partial.

## 18. A5 — all-masked opposing parties

One case contributes once to each distinct eligible HMAC group and at most
once per group. Several opponents may therefore make the sum of group counts
larger than the number of cases. `multi_opponent_case_count` counts cases with
more than one distinct eligible group. `cases_without_safe_opponent` counts
admitted cases with no eligible group, including other/unattributed roles.

Public ordinal assignment is independent of popularity. Displayed groups then
sort by:

```text
case_count DESC
opponent_public_id ASC
```

Root top-20 scope counts groups. Each displayed group has a separately capped
case scope and exact nested N/M. All labels are masked; no alias selection or
entity classification runs.

## 19. DTO, limitations and factual parity

The public wire shape stays `company_public_h2_v1`. Existing generic
Python/TypeScript parsing and the historical dense corpus remain compatible.
The predeclared A1–A5 members receive additional policy-v3 projection/resolver
validators, dispatched from saved v3 lineage server-side and the exact
two-branch matrix below client-side, for:

- public ID patterns and ordinal/label agreement;
- summary/counter/calendar invariants;
- coverage/block nullability including `available_empty`;
- fixed A1/A2/A3 orders, sums, percentages and scopes;
- A4 RUB-only group, exact axis/geometry/detail matching and counts;
- A5 masked-only groups, ordering, unique membership and nested scopes;
- top-20 cardinality and exact N/M labels;
- D6-deferred null/empty fields;
- public CJSON cap and recursive privacy boundary.

Policy-v3 client semantic dispatch has exactly two branches. A bound-result
branch is selected only by the exact arbitration source tuple defined below.
The source-less pre-result branch is selected only when all of these hold:

```text
contract_version = company_public_h2_v1
snapshot_capability = card_v2
sources = the valid frozen counterparty/finance sequence, with no arbitration item
arbitration_a1..arbitration_a5 = null
all five arbitration coverage population_scope = not_applicable
all five coverage total/returned/eligible = null
all five coverage limitation_codes = [R]
R is the same token in all five entries
```

The closed `R -> coverage.state` mapping is:

```text
operation_gate_closed  -> gate_closed
evidence_gate_closed   -> gate_closed
privacy_key_unavailable -> failed
provider_error          -> failed
provider_binding_invalid -> failed
```

The arbitration-related root limitation subset is exactly the same single
safe code `R`, with `block_id=null` and `field_id=null`; unrelated
non-arbitration limitations/sources retain their existing rules. No other
reason, mixed state/code, non-null count/block or arbitration source is valid
in this source-less branch. Conversely,
lexical/envelope/post-binding V3 states require the bound-result source branch.
Legacy policy-v1/v2 gate-closed coverage retains its frozen block-specific
codes and does not match this matrix. Python/TypeScript positive cases for all
five `R` values and one-field mutation cases must agree exactly.

The 524,288-byte cap applies to exact CJSON of the complete public response,
not an arbitration fragment; exactly 524,288 is allowed. The projection first
validates each candidate component and every root cross-field semantic except
the byte cap, then assembles the exact primitive wire mapping. Invalid IDs,
counts, scopes, privacy or any error other than exact size fail normally and
can never be laundered through the fallback. The atomic fallback is available
only to the bound-result branch with the exact non-null arbitration source
tuple. If that otherwise valid bound-result candidate is larger than the cap,
it performs one deterministic fallback before root model construction:

```text
arbitration_a1..arbitration_a5 = null
their five coverage states = failed
their population_scope/total/returned/eligible = exact candidate evidence
their limitation_codes = [arbitration_public_projection_cap_exhausted]
```

No view priority, smaller hidden detail cap or partially retained arbitration
subset is allowed; frozen `PublicDetailScope.cap=20` and
`shown=min(eligible_total,20)` remain exact. Non-arbitration blocks,
limitations and sources are preserved; candidate arbitration limitations are
replaced in the public response by the single deterministic cap limitation.
The private snapshot, basis, facts and their hashes are unchanged, and the
publication digest is calculated only from the final fallback response. The
projection limitation is not added to basis `completion_reasons` and does not
rewrite the report lifecycle or collection `completion_reason`. The fallback
is independently validated and must itself be at most 524,288 CJSON bytes. If
it is still larger, publication fails closed with
`public_projection_too_large`; no oversized DTO, cache entry, resolved pin or
staged publication is emitted. A source-less pre-result V3 candidate is never
rewritten to the cap code because that would destroy its exact discriminator:
it is emitted unchanged at or below 524,288, and at 524,289 or above it goes
directly to the same fail-closed `public_projection_too_large` outcome. Tests
hold the exact source-less pre-result tuple fixed while filling only otherwise
valid non-arbitration public fields to the 524,288/+1 boundary. In every
failure the already-created single unresolved v3 pin remains byte-unchanged
and retryable under the existing fenced lifecycle.

Limitations are deterministic, unique and linked only to affected blocks. The
basis uses only the exact closed catalog in section 8, covering
provider/evidence/privacy/envelope failure, returned slice/cap,
malformed/conflicting rows, calendar unverified, unknown year, invalid
dates/case number, decimal loss, missing amount/currency and unidentified
currency. The public-only catalog additionally includes exact
`arbitration_public_projection_cap_exhausted`; it is valid only on the atomic
five-block fallback of a bound-result response above and is invalid on the
source-less branch. Provider text never becomes a public message.

For policy v3, the `arbitration` source item is present only when
`basis.provider_received_at` is non-null. Its exact tuple is
`dataset="arbitration"`, `received_at=basis.provider_received_at`,
`effective_at=null`, `period=null`,
`normalization_version="company_card_arbitration_normalization_v2"` and
`evidence_version="datanewton_arbitration_registry_v2"`. No other value may
select the bound-result branch. Preflight/provider failure without a bound
`DataNewtonResult` omits the arbitration item; current request/render time is
never substituted. Frozen v1/v2 source tuples remain byte-compatible.

SSR always emits five arbitration factual articles. Non-null views contain
heading, visible scope, caption, semantic table/list, exact counts/strings,
limitations and an empty enhancement host. Null views contain an honest
unavailable state and linked limitations, never a synthetic chart. React
reproduces the same structure from the embedded DTO without a factual GET.

Structural parity includes article order, headings, scopes, captions, headers,
cells/items, case/public IDs, N/M labels, limitations and empty enhancement
hosts. Facts stay in the DOM after enhancement and on any chart error.

## 20. Lazy charts and accessibility

Arbitration rendering is a separate dynamic optional chunk from finance. The
bootstrap sequence remains:

1. strict parse/schema/semantic/digest/path validation;
2. SSR factual-vector comparison;
3. React takeover and React factual-vector comparison;
4. only then independent finance/arbitration lazy controllers may arm.

A controller imports at most once when its non-null section approaches the
viewport. Parse/binding/parity mismatch creates no observer/import. Teardown
disconnects both observers, invalidates stale imports and unmounts the stored
root exactly once. Unsupported observer/import/render error is local, visible
through `role=status aria-live=polite`, performs no retry/fetch and preserves
facts.

Hand-authored SVG uses backend counts/Decimal/axes only for bounded coordinates:

- A1 stacked role bars for observed buckets;
- A2/A3 fixed horizontal count/percentage bars;
- A4 signed zero-axis amount bars;
- A5 group case-count bars.

Every meaningful mark is keyboard-focusable and has an accessible name with
view, category/period, exact value and scope. Mouse/focus/touch share one
disclosure; Escape, outside pointer and focus exit close it. Tooltip is never
the sole fact. Controls/targets are at least 44×44 CSS pixels, labels wrap,
small-screen overflow is local, color is not the only distinction and reduced
motion disables animation. Risk red/green semantics are forbidden.

## 21. Fixtures, assets and verification boundary

The existing dense shared `company_public_h2_contract_v1.json` fixture remains
byte-identical as a legacy generic-wire corpus. Add a separately named masked
policy-v3 contract fixture for exact new public IDs, all-masked labels,
RUB-only A4, deferred details and reconciled counts. Neither fixture becomes
evidence of provider semantics.

Keep three distinct golden families:

1. closed policy v1;
2. finance-only policy v2 with A1–A5 null;
3. finance+arbitration policy v3 with sanitized A1–A5.

Historical report/snapshot fixtures are not rewritten. New provider fixtures
are minimal synthetic JSON/bytes with no real identifiers, names, cases or
credentials. Raw probe/evidence files and generated screenshots are not added.

The asset manifest includes the arbitration dynamic JS/CSS closure in sorted
`optional_chunk_paths`, retains finance chunks and stays compatible with an
old explicit empty optional list. Unknown reachable asset types remain errors.

## 22. Migration, dependencies and acceptance

The one additive report/job decision migration defined in section 6.2 is now
part of the plan; no other schema change and no new dependency is planned. Its
pre-DDL active-H2 rejection, upgrade/downgrade, terminal legacy-row defaults,
finalized snapshot/pin lineage, report/job mismatch and disposable-DB round
trip require tests. It is not applied to production in this iteration.

Итерация принята, если:

1. V1/V2 snapshots, hashes, H1 and publication policies remain compatible.
2. Arbitration disabled means exact old v2 writes and zero arbitration fetch
   callbacks.
3. Enabled, preflight-admitted test path makes exactly one `ALL/0/1000`
   mock-provider request; rejected preflight makes zero arbitration fetch
   callbacks. Non-zero-offset `received_at` is rejected before UTC
   canonicalization while existing V1/V2 UTC fixtures remain byte-compatible.
4. Exact zero, complete <=1,000, >1,000 partial and every failure/cap boundary
   have correct counters, states and no extrapolation; reserved-envelope
   equality/+1 also covers late metadata digit growth, identical duplicates
   and conflict-removal transitions.
5. New rows use `case_id` only and target attribution uses exact INN only.
6. Source numeric truth stays exact Decimal; zero/negative remain visible.
7. A1 has observed years only; A2/A3 reconcile to exact denominators.
8. A4 contains only RUB claim prices and distinguishes missing/unidentified.
9. A5 is all-masked, report-scoped and leaks no name/identifier/HMAC.
10. The persisted arbitration/key decision is immutable across enqueue, claim,
    retry and rotation. Migration rejects any pre-existing active H2 lineage
    before DDL; terminal old rows remain disabled/null, and historical public
    or narrative use requires a valid finalized snapshot-plus-pin pair.
11. Policy v3 is atomic, immutable and selected only from saved lineage;
    arbitration registry/facts/hash tampering fails through `snapshot_hash`.
12. GET/HEAD/SSR/client perform no provider/AI/write/factual refetch.
13. SSR and React factual vectors match and survive lazy failures.
14. Keyboard/touch/a11y, large-N and deterministic SVG tests pass.
15. The 20,000-group boundary retains all tokens; 20,001 atomically scrubs all
    token tuples, preserves A1–A4 and fails A5 without any subset or false
    public eligible count.
16. First-number collision tests include malformed, conflicting, oversized,
    basis-cap-excluded and unprocessed source rows, not only surviving cases.
17. Snapshot V3 narrative dispatch is byte-equivalent to the existing
    primary-activity-only V2 Gateway body and leaks no arbitration value.
18. Asset manifest/release compatibility and exact public byte-cap behavior
    pass, including the 1,460-detail bound-result fallback and source-less
    direct fail-closed behavior at the 524,288/+1 boundary.
19. Targeted, full mandatory and disposable-PostgreSQL checks pass.
20. Production defaults remain off; no live/deploy/rollout operation occurs.

Current acceptance record (2026-08-27): items covered by unit, contract,
frontend, build and release checks pass. Item 19 remains open only for the
disposable-PostgreSQL runner: Docker Desktop daemon is unavailable locally, so
no temporary database was created and no database was touched. Production
activation remains unauthorized. Final independent code review: `APPROVED`, no
findings.
