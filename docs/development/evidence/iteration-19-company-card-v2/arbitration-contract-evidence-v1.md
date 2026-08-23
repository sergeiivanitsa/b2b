# Arbitration contract evidence v1 - Company Card v2

Artifact ID: `company_card_v2_arbitration_contract_evidence_v1`

Evidence date: `2026-08-23`

Current gate: `UNVERIFIED`

Runtime capability: `BLOCKED`

Live-stage authorization: `not_granted`

## 1. Decision

Local evidence establishes a useful single-page arbitration shape but does not
establish the authoritative vendor envelope, stable total semantics,
multi-page pagination, company-scoped outcome semantics, party entity type,
currency catalog, visible case-number leaf, court/instance schema, or public
KAD link contract.

Consequently:

- the current single page must not be generalized to a complete collection;
- v3 arbitration collection cannot start until an evidence registry binds the
  exact envelope total/data/offset/limit paths, types, scope, and shape version;
- A1-A5 remain blocked until their required semantic/privacy gates close;
- current normalized `result_type` is not a substitute for `party_result`;
- no live provider request, production DB read, refresh, or backfill is
  authorized by this document.

## 2. Provenance and sanitization

| Evidence ID | Source | Permitted conclusion | Explicit limitation |
|---|---|---|---|
| `ARB-CODE-20260823` | Current provider request model, orchestrator, arbitration normalizer/models, and H1 projection at base `c3805dd1fbb8cdac38b1aa315e1f1e94597e7537` | Existing one-request behavior, parser paths, retained/lost fields, current attribution behavior | Not vendor evidence and not a v3 algorithm |
| `ARB-FIX-20260823` | Tracked synthetic arbitration fixture | Parser shape for a partial first page, party arrays, amounts/currency, result detail, documents, and link candidate | Contains no `party_result`, instance collection, entity type, or automatic pagination evidence |
| `ARB-LOCAL-SHAPE-20260822` | Owner-supplied ignored evidence for pseudonymous subject `S01`, inspected read-only | One page where returned rows equal its observed total candidate; observed case/result/party/amount/instance/link candidates | One subject and one page cannot prove a vendor contract or multi-page behavior |
| `ARB-UX-20260822` | Chart technical specification and page mockup | Desired A1-A5 fields, formulas, order, partial and top-20 behavior | Not provider evidence |

No company or party name, identifier, case number, amount, raw URL, raw object,
contact, personal identifier, provider free text, header, or credential from
owner evidence is reproduced here. Counts and algorithms below are product
bounds or sanitized structural facts, not copied case content.

## 3. Sanitized observed shape

### 3.1. Page envelope

| Contract field | Observed candidate | Observed type/cardinality | Evidence conclusion | Current binding |
|---|---|---|---|---|
| Case array | `$.data` | array; one page observed | A case-array shape exists | observed, semantics unverified |
| Source total | local candidate `$.total_cases` | nonnegative integer candidate; one per page | Candidate exists in synthetic/local shapes | `NOT_VERIFIED`; authoritative path/type/scope not bound |
| Offset | `$.offset` candidate | nonnegative integer candidate | Zero-offset first-page shape observed | semantics unverified |
| Limit | `$.limit` candidate | positive integer candidate | Page-limit member observed | semantics and stability unverified |
| Alternative total | `$.total` | not established | Must not be invented from generic pagination conventions | never asserted |

The ignored `S01` sample is complete-looking only in the narrow sense that its
single returned array length equals its observed total candidate and the page
limit is not exhausted. This does not prove that the candidate total is
authoritative, that offsets are stable, that all filters share the same total,
or that later pages behave consistently.

### 3.2. Case identity and dates

| Fact | Observed candidate | Current conclusion |
|---|---|---|
| Preferred stable key | `$.data[*].case_id` | Observed; vendor identity semantics still require binding |
| Fallback key | `$.data[*].id` | Observed; used only when preferred key is absent/blank |
| Visible case number | A local candidate exists | Exact path remains `NOT_VERIFIED`; key fields are never display fallback |
| Case year | `$.data[*].year` | Integer shape observed; meaning as start year is unverified |
| Start date | `$.data[*].date_start` | Date-string shape observed; scope unverified |
| Update date | `$.data[*].date_update` | Date-string shape observed; scope unverified |

Equal amounts, dates, names, or visible numbers do not define identity. Two
different case keys always represent distinct cases unless future verified
vendor evidence explicitly contradicts that rule and a new contract is
approved.

### 3.3. Parties and roles

Observed party collections include:

```text
plaintiffs
respondents
applicants
creditors
creditors_current_payments
debtors
interested_persons
third_parties
others
```

Observed party leaves include candidates for display name, normalized name,
INN, OGRN, and raw role. The collection ID and zero-based array ordinal define
an exact party position. No verified party entity-type leaf is available.

Role attribution for Card v2 is a product decision, not a claim about provider
free role text: it uses only exact normalized target INN within verified role
collections. Name, normalized name, OGRN, fuzzy matching, identifier length,
and OPF-like text never assign a target role.

### 3.4. Outcome and result detail

The owner-local shape contains a `$.data[*].party_result` candidate. The
tracked fixture does not contain it, and the current normalizer does not retain
it. Its company scope and semantics remain unverified.

`$.data[*].result_type` is observed in tracked and local shapes. It may become
an optional closed detail label after a separate gate, but it never classifies
the company outcome. `status`, document status, and court text also never
replace `party_result`.

### 3.5. Amount and currency

`$.data[*].sum` has only a Decimal-shaped post-coercion parser observation; it
does not prove lexical source Decimal transport. `arbitration_decimal_transport`
is `UNVERIFIED/BLOCKED`, so A4 amount display and geometry remain blocked, and
`$.data[*].currency` is an observed string candidate. Evidence does not yet
bind a closed currency catalog or source semantics.

Required distinctions:

- missing amount is not zero;
- explicit zero remains an eligible exact amount;
- a negative amount retains its sign;
- equal amounts under different case keys remain separate cases;
- source amounts are not called debt, recovered amount, or award;
- currencies never mix and are never FX-converted;
- missing/unknown currency receives no symbol and is not admitted to an A4
  currency group.

### 3.6. Instances, courts, and KAD link

The ignored local shape contains candidates for an instance count, instance
collection/court labels, and case link. The tracked fixture/current snapshot do
not retain the first two as an exact case-instance contract. Therefore:

```text
arbitration_instance_count_path = NOT_VERIFIED
arbitration_instances_path = NOT_VERIFIED
arbitration_court_label_path = NOT_VERIFIED
arbitration_visible_case_number_path = NOT_VERIFIED
```

`$.data[*].kad_arbitr_link` is an observed URL candidate, but the exact HTTPS
host/path/case-binding contract is unverified. Until it passes, the public URL
is null and a safe visible case number, if independently verified, remains
plain text.

### 3.7. Entity-type gap

No approved leaf distinguishes legal entity, state body, natural person, or
unknown/conflict. Entity type must never be inferred from a name, identifier
length, OPF text, role, or capitalization.

The approved privacy transformation remains blocked on this schema gate:

- verified legal/state party: safe normalized name may be public; exact INN is
  internal grouping only;
- verified natural party: report-scoped HMAC token internally, masked ordinal
  publicly;
- unknown/conflicting type: report-scoped HMAC token internally, hidden-party
  ordinal publicly;
- no reliable private identifier: case-key + exact role + party position input,
  with no cross-case merge.

## 4. Current implementation gap analysis

| Surface | Current behavior | Required v3 correction |
|---|---|---|
| Orchestrator | Performs one arbitration request at offset zero | Bounded evidence-gated page loop with stable-total/offset checks |
| Pagination completeness | Normalizer decides from one slice | Collection-level provenance and completion reasons across every accepted page |
| Case key | Current normalizer prefers `id` before `case_id` | Prefer exact nonblank `case_id`, fallback exact nonblank `id` |
| Dedup | No cross-page canonical dedup | Dedup before aggregates/top-20; conflicting key excludes every version |
| Outcome | `party_result` is discarded; `result_type` is normalized | Persist verified company-scoped `party_result`; detail remains separate |
| Role | Current normalization may match INN or OGRN and summary can multi-count | Exact target INN only and exactly one `plaintiff/respondent/other/unattributed` bucket |
| Entity type/privacy | No entity-type fact or HMAC masking contract in stored cases | Fail-closed privacy normalization before admission |
| Amount/currency | Parser-shape amount/currency observed, but lexical transport and catalog are not verified | Preserve missing/zero/sign distinctions only after decimal transport; keep A4 blocked separately |
| Instance/court fields | Local candidates are not stored as the required contract | Keep null/empty until exact evidence bind; never derive from documents |
| Link | Candidate URL retained internally | Exact HTTPS host/path allowlist, no-referrer link policy, otherwise null |
| Public detail | H1 selects at most ten limited case summaries | H2 per-view/per-currency top-20 from bounded sanitized collection with exact `N/M` |

The tracked fixture intentionally contains more source-total candidates than
returned rows. It proves that a partial-envelope shape can be parsed; it does
not prove the request loop or that a provider's next page is obtainable.

## 5. Gate-state matrix

| Capability | Schema gate | Semantic gate | Privacy gate | Operational gate | Public behavior now |
|---|---|---|---|---|---|
| Pagination envelope/completeness | unverified | unverified | approved_transform | disabled | `gate_closed`; no collection call |
| Preferred/fallback case identity | verified observed shape | unverified vendor identity | internal only | disabled | no public provider key; no v3 dedup yet |
| Visible case number | unverified | unverified | approved_transform | disabled | null / `Номер не указан` |
| Exact-INN role algorithm | verified party shape | product algorithm accepted; collection semantics unverified | identifiers internal | disabled | no A1/A2 publication |
| Company outcome `party_result` | unverified tracked contract | unverified company scope | approved_transform | disabled | outcome unknown; `result_type` never substitutes |
| Amount | verified parser shape | field scope unverified | approved_transform | disabled | no A4 publication |
| Currency mapping | verified observed scalar | unverified closed catalog | approved_transform | disabled | no symbol/group |
| Party entity type | unverified | unverified | approved masking contract | disabled | natural/unknown names never public; A5 blocked |
| Instance/court | unverified | unverified | approved_transform | disabled | count null, courts empty |
| KAD URL | verified observed scalar | host/path/case binding unverified | approved_transform | disabled | no public link |

## 6. Accepted bounded collection parameters

These are technical product guards, not statements about provider tariff or
maximums:

```text
page_size = 100
max_pages = 10
hard_case_row_cap = 1000
sanitized_arbitration_storage_cap = 8 MiB canonical UTF-8 JSON
individual_sanitized_case_cap = 262144 bytes
detail_cap = 20 per view or per currency/group scope
preferred key = exact nonblank case_id
fallback key = exact nonblank id
conflicting duplicate key = exclude all versions
cap, non-progress, error, or drift = partial
```

The row cap counts raw array elements encountered before validation or dedup,
including malformed and duplicate rows. The 1001st element is not normalized.
The storage-cap comparison includes the next tentative canonical basis; exact
equality with `8388608` bytes is accepted and one byte over is rejected.

## 7. Evidence binding required before the first v3 request

The evidence registry must bind all fields below to one exact provider shape:

```text
arbitration_total_path
arbitration_total_type
total_scope
data_path
offset_path
limit_path
shape_version
request endpoint/filter shape
```

Missing or stale binding returns `arbitration_envelope_gate_closed` before any
provider call. The observed `$.total_cases` candidate is not silently promoted,
and `$.total` is never invented.

Visible case number, outcome, entity type, currency, instances/courts, and KAD
URL have independent gates; an envelope bind does not activate them.

## 8. Deterministic pagination algorithm

After the envelope bind is approved:

1. Request `offset=0`, `limit=100`.
2. Validate `data`, bound total, returned offset, and returned limit before row
   normalization.
3. Freeze the first valid nonnegative total as `source_total`.
4. Require every later page to report the same total and expected offset.
5. Require `0 <= len(data) <= requested_limit`.
6. Set the next offset to previous requested offset plus actual returned rows.
7. Hash every page response privately and record only a safe page manifest.
8. Stop partial on an empty/non-progress page before total, repeated page hash
   at a new offset, total drift, offset drift, short page before total, overlap
   conflict, malformed envelope, provider error, or any cap.
9. Preserve every previously admitted safe row when a later page fails.
10. Complete only when exact source positions reach the stable total with no
    earlier failure/cap/drift/conflict reason.
11. Treat valid `total=0`, `data=[]`, and offset zero as successful empty.
12. Never persist raw pages.

Each internal page-manifest item contains only:

```text
page ordinal
requested offset and limit
returned count
observed total
response hash
safe request identifier
received timestamp
outcome code
```

## 9. Per-row processing, storage cap, and provenance

Rows are processed in provider page/array order:

1. Increment `rows_observed`.
2. Enforce the raw-row cap.
3. Validate the minimum object/key shape.
4. Normalize strings, dates, lexical Decimal only after the dedicated transport gate, and parties.
5. Apply the privacy transformation before persistence.
6. Build one `SanitizedCaseV1`.
7. Serialize it with `company_public_h2_cjson_v1`.
8. Deduplicate by preferred/fallback case key.
9. Tentatively build `ArbitrationBasisV1`.
10. Admit the row only if canonical basis bytes are at most `8388608`.
11. Stop before the first oversized/storage-cap row and every later row/page.

An individual sanitized case over `262144` canonical bytes is not admitted,
increments `oversized_case_count`, and makes the collection partial. Processing
does not continue after that stop, avoiding a size-biased slice.

`ArbitrationBasisV1` contains exactly:

```text
shape_version
source_total
page_manifest
counters
sanitized_cases sorted by canonical case key
mask_algorithm_version
mask_key_id
```

Derived Chart Facts are outside the 8 MiB basis cap but remain subject to the
public DTO cap. Raw pages and private identifiers are never basis members.

## 10. Canonical deduplication

Canonical equality compares the complete `SanitizedCaseV1`, including dates,
amount/currency, role evidence, outcome/detail, sanitized party tokens, safe
court/link fields, and null versus explicit zero.

Rules:

- same key and byte-identical canonical row => collapse once and increment
  `duplicate_identical_count`;
- same key and different canonical row => remove the previously admitted row,
  blacklist the key, exclude every version, record conflict, and mark partial;
- a blacklisted key cannot be re-admitted by a later duplicate;
- neither preferred nor fallback key => malformed;
- equal amounts under different keys never deduplicate;
- dedup occurs before aggregates, rankings, and detail caps.

## 11. Counters and completion reasons

Required counters:

```text
pages_requested
pages_accepted
rows_observed
rows_shape_valid
malformed_count
oversized_case_count
duplicate_identical_count
duplicate_conflict_row_count
duplicate_conflict_key_count
unique_case_count
masked_natural_count
masked_unknown_count
```

Every processed row has one primary disposition: malformed, oversized,
duplicate-identical, duplicate-conflict, or current unique candidate. Conflict
removal is tracked separately so `unique_case_count` is never presented as a
simple sum of row dispositions.

`completion_reasons` is nonempty, unique, and sorted by this fixed precedence:

```text
privacy_key_unavailable
envelope_gate_closed
envelope_invalid
provider_error
total_drift
offset_drift
duplicate_conflict
oversized_case
storage_cap_exhausted
case_cap_exhausted
max_pages_exhausted
non_progress
complete
```

`completion_reason` is the first member. `complete` may be the only member and
requires a stable total, all positions fetched and no prior collection reason.
Calendar evidence is deliberately not a collection-completeness precondition.

Persisted `ArbitrationCollectionV1`, derived `ArbitrationCalendarFactsV1`
(included in `chart_facts_hash`) and `PublicArbitrationSummary` carry these
separate facts:

```text
collection_complete: boolean
completion_reason(s): collection-only closed values above
calendar_complete: boolean
calendar_scope: "unverified" | "all_time" | "bounded_interval"
calendar_start_year: integer | null
calendar_end_year: integer | null
calendar_evidence_version: Contract/version/code | null
observed_start_year: integer | null
observed_end_year: integer | null
unknown_year_count: integer >= 0
zero_years_proven: boolean
```

`collection_complete=true` never implies `calendar_complete=true`, a calendar
scope, bounds, or a zero bucket. `calendar_scope="all_time"` has no claimed
calendar bounds; `bounded_interval` requires both bounds and a non-null
`calendar_evidence_version`; `unverified` requires null calendar bounds and
version. Only separately bound calendar evidence and zero-year proof may set
`zero_years_proven=true`; otherwise A1 is observed-only and retains an explicit
unknown-year bucket when applicable. All calendar evidence gates remain
`UNVERIFIED/BLOCKED` in this artifact.

## 12. Exact role attribution

For every sanitized case, build the set of verified source role collections in
which the exact normalized target INN occurs:

```text
exactly {plaintiff}  -> plaintiff
exactly {respondent} -> respondent
any other nonempty set, including a singleton third/other role -> other
empty set -> unattributed
```

Every normalized unique case enters exactly one bucket:

```text
plaintiff + respondent + other + unattributed = unique_case_count
```

Name-only, normalized-name, OGRN-only, and fuzzy matches are prohibited. A
malformed case does not enter the denominator.

## 13. Outcome, amount, currency, and calendar

After the independent outcome gate proves company scope, mapping is exact and
case-sensitive:

```text
WON      -> won
LOST     -> lost
RETURNED -> returned
other or null -> unknown
```

`result_type`, `status`, document status, and court text never substitute.

Amounts may retain null, explicit zero and negative-sign distinctions only
after `arbitration_decimal_transport` proves lexical ingestion under
`company_card_source_decimal_v1`; until then amount facts and A4 stay blocked.
Currency groups are independent and use no FX. Public symbols require a closed mapping.

Case year uses only an evidence-proven year semantic. Missing year enters `Год
не указан`. Neither a complete nor a partial collection may synthesize a
calendar zero merely from collection results. Synthetic zero buckets require
separate `calendar_complete=true` and `zero_years_proven=true`; otherwise A1
displays observed years only, discloses its returned scope, and never says
`дел нет`.

## 14. Dates and safe aliases

Duration is calculated only when both verified dates exist:

```text
update_date >= start_date:
  days_to_last_update = calendar-day difference

update_date < start_date:
  days_to_last_update = null
  limitation = arbitration_date_inversion
```

It is labelled `От подачи до последнего обновления`, never proceeding
duration.

For verified legal/state parties sharing one exact internal INN, safe display
alias selection is deterministic:

1. normalized nonblank safe name;
2. greatest update date;
3. greatest start date;
4. lexicographically smallest Unicode-scalar name;
5. smallest case key.

Natural and unknown parties never use name aliases.

## 15. A1-A5 population safety

- Aggregates are computed only from admitted normalized unique cases.
- Partial collections describe only the returned sanitized slice and are never
  extrapolated to source total.
- Detail sort and cap occur after validation, privacy transformation, and
  dedup.
- `M` is the exact eligible population of that role/year, outcome, currency,
  or opponent-group view; `N=min(M,20)`.
- A4 ranks independently per verified source currency and keeps equal amounts
  as separate cases.
- A5 groups verified legal/state parties by internal exact INN; natural and
  unknown parties use report-scoped masked tokens. Name-only cross-case grouping
  is prohibited.
- Multiple opposing parties may make group-count sums exceed case count and
  require an explicit limitation.

## 16. Evidence and test requirements before activation

Tracked sanitized evidence must bind every gate in section 5 without names,
identifiers, amounts, raw URLs, raw response content, contacts, or credentials.
At minimum, iteration 20 fixtures/tests must include:

- row boundaries `999`, `1000`, and `1001`;
- storage equality at 8 MiB and one byte over;
- oversized first and mid-page cases;
- mid-page storage stop and proof later rows are not selected;
- identical and conflicting duplicates, including later reappearance;
- equal amount under different keys;
- total drift, offset drift, repeated page, empty/non-progress page, provider
  failure, and max-pages exhaustion;
- every exact target-role set, including third-only and multiple roles;
- outcome present/missing/unknown with proof that `result_type` never replaces
  it;
- amount missing/zero/negative and multi/missing/unknown currency;
- missing/rotated mask key and entity-type conflict;
- date equality, inversion, missing date, and alias tie-breaking;
- visible case-number and KAD gates closed/open independently;
- H1 and legacy behavior unchanged.
- independent collection-complete/calendar-incomplete, observed-bounds,
  unknown-year and zero-year-proof fixtures, including proof that collection
  completeness alone never emits synthetic zero.

## 17. Final gate conclusion

The owner-local sample supplies all desired case-level candidates for the
prototype but only as observed shape. The tracked fixture is intentionally
insufficient for outcome, entity type, instances, and full pagination.

Final iteration-19 state:

```text
pagination_completeness = UNVERIFIED / BLOCKED
case_identity_semantics = UNVERIFIED / BLOCKED
visible_case_number = UNVERIFIED / BLOCKED
exact_role_runtime = BLOCKED pending collection/entity evidence
party_result = UNVERIFIED / BLOCKED
currency_mapping = UNVERIFIED / BLOCKED
party_entity_type = UNVERIFIED / BLOCKED
instance_and_court_fields = UNVERIFIED / BLOCKED
kad_public_link = UNVERIFIED / BLOCKED
```

Iteration 19 may complete its documentation-only scope with these gates closed.
Iteration 20 must preserve the blockers rather than guess or silently weaken
them, and iteration 24 cannot start until its required gates pass. After merge,
later evidence uses a new immutable artifact version instead of rewriting this
record.
