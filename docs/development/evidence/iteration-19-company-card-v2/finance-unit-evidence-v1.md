# Finance unit evidence v1 - Company Card v2

Artifact ID: `company_card_v2_finance_unit_evidence_v1`

Candidate policy: `datanewton_finance_thousand_rub_v1`

Evidence date: `2026-08-23`

Current gate: `UNVERIFIED`

Runtime capability: `BLOCKED`

Live-stage authorization: `not_granted`

## 1. Decision

Iteration 19 does not activate a DataNewton monetary unit. The inspected local
and repository evidence proves that finance values can be parsed as exact
`Decimal` series keyed by form, code, and reporting year. It does not contain a
verified provider unit, currency, OKEI, scale, or endpoint-contract statement.

Until a separately authorized field-level matrix passes atomically:

- finance monetary Chart Facts are not publishable;
- `RUB`, `₽`, `тыс. ₽`, and `млн ₽` are forbidden;
- multiplying or dividing provider values by `1000` is forbidden;
- absolute finance values, tooltips, and table cells remain unavailable in
  `company_public_h2_v1`;
- iteration 23 is blocked;
- a feature flag cannot override this evidence gate.

Unit-independent formulas may be implemented only in the later scope that owns
their complete contract and only from persisted exact facts. They do not prove
or activate a monetary unit.

## 2. Provenance and safety boundary

No live DataNewton or FNS request, production database read, paid AI call,
refresh, backfill, or publication was performed.

| Evidence ID | Source | What it proves | What it does not prove |
|---|---|---|---|
| `FIN-CODE-20260823` | Current finance normalizer and Decimal models at base `c3805dd1fbb8cdac38b1aa315e1f1e94597e7537` | Recursive form/code/year parsing and Decimal-like values after ordinary JSON coercion; missing/zero/conflict behavior | Vendor scale, production availability, or lexical source-number exactness |
| `FIN-FIX-20260823` | Tracked synthetic finance fixture | Parser-shape behavior for most required codes and several years | Vendor evidence; it omits required code `1240` and cannot prove a unit |
| `FIN-LOCAL-SHAPE-20260822` | Owner-supplied ignored evidence, inspected read-only | The twelve required code/value shapes occur in one local sample | Vendor contract, cross-company scale, filter stability, or unit proof |
| `FIN-UX-20260822` | Chart technical specification and page mockup | Desired calculations and display intent | Provider scale |
| `FIN-FNS-POLICY-V1` | Approved future comparator procedure using official FNS ГИР БО statements | How an authorized comparison must establish FNS units | No DataNewton conclusion until exact cross-source cells match |

Tracked content contains no company name, identifier, raw amount, raw response,
identifier-bearing locator, credential, contact, or personal data. Private raw
files and the `C01..C05` identifier map must remain outside git.

## 3. Required scope

The candidate policy is limited to the exact finance endpoint, request/filter
shape, response shape version, and these twelve `(form, code)` pairs:

| Form ID | Required line codes |
|---|---|
| `balance` / source root `$.balances` | `1210`, `1230`, `1240`, `1250`, `1300`, `1400`, `1500`, `1600` |
| `financial_results` / source root `$.fin_results` | `2100`, `2110`, `2200`, `2400` |

Code `4400` belongs to a different form and is excluded from
`company_public_h2_v1`. Its presence in older periods cannot fill a missing
approved line or extend the policy.

For every approved code the parser locator is:

```text
exact form root
-> recursive object with exact sibling code
-> exact sibling sum object
-> exact reporting-year key
-> Decimal or explicit null/missing
```

The following distinctions are mandatory:

- explicit numeric zero is `zero`;
- absent key or explicit null is `missing`;
- invalid numeric input is malformed, not missing or zero;
- equal duplicates may collapse with provenance;
- unequal duplicates are `conflict` and cannot be selected;
- source names and value magnitude are not unit evidence.

## 4. Why current inputs cannot prove `thousand_rub`

### 4.1. Provider response shape

The current client path uses ordinary `response.json()` decoding before the
normalizer receives finance values. That path can prove only the observed
shape and post-coercion parser behavior; it does **not** preserve or prove the
original JSON number lexeme and therefore cannot prove exact Decimal transport.
For v3, `company_card_source_decimal_v1` accepts only a number lexeme captured
from response bytes before float coercion or a JSON string matching the closed
Decimal grammar in the iteration-19 specification. A Python `float` received
after `response.json()` is rejected as `decimal_transport_lossy`.

Current gate:

```text
finance_decimal_transport = UNVERIFIED / BLOCKED
```

It is independent of the unit matrix: no monetary Chart Facts or v3 finance
chart may activate until lexical ingestion, finite/precision boundary tests,
and the separate unit evidence gate all pass.

The inspected shapes expose finance codes and year-indexed values but no
verified unit/currency/OKEI/scale member. A value being arithmetically
plausible as thousands of rubles is not a semantic contract.

### 4.2. UI and chart references

The PDF, CTA image, technical chart specification, and prototype formatting
describe intended presentation. They are downstream design inputs and cannot
establish the unit of an upstream provider field.

### 4.3. Third-party sites and field names

A similar number on a commercial company-information site, a Russian finance
line-code convention, or a field named `sum` does not bind DataNewton's
endpoint/filter/shape to a scale. Rounding, cached periods, alternate sources,
and form-specific transformations could differ.

### 4.4. FNS alone

FNS ГИР БО is the primary official comparator, but it proves only its own
statement and OKEI. It proves DataNewton scale only after exact values for the
same company, form, code, and year match under the controlled matrix below.

## 5. FNS comparator and OKEI normalization

The authorized matrix must classify the explicit unit marker of each official
FNS statement before reading or comparing its value. The closed classification
is:

```text
OKEI 384:
  fns_okei_state = accepted_384
  fns_okei_code = 384
  official_thousand_decimal = official_decimal
  scale_outcome = direct_thousand

OKEI 385:
  fns_okei_state = accepted_385
  fns_okei_code = 385
  official_thousand_decimal = official_decimal * 1000
  scale_outcome = exact_million_to_thousand

missing OKEI:
  fns_okei_state = rejected_missing
  fns_okei_code = null
  comparison_outcome = rejected_okei
  scale_outcome = not_applicable

ambiguous OKEI:
  fns_okei_state = rejected_ambiguous
  fns_okei_code = null
  comparison_outcome = rejected_okei
  scale_outcome = not_applicable

any OKEI other than 384 or 385:
  fns_okei_state = rejected_other
  fns_okei_code = null
  comparison_outcome = rejected_okei
  scale_outcome = not_applicable
  cell cannot prove the candidate policy
```

An OKEI-385 conversion is allowed only when the official document explicitly
supplies that marker and the conversion uses exact Decimal arithmetic. At least
one direct non-zero OKEI-384 match is required in each form; a matrix made only
from converted OKEI-385 cells cannot pass.

The tracked row never stores a rejected raw OKEI token. `fns_okei_code` is
populated only for accepted `384` or `385`; the closed state records why all
other inputs were rejected without leaking or widening the code vocabulary.

No tolerance, rounding, interpolation, absolute-value comparison, inferred
scale, or best-looking multiplier is allowed.

## 6. Separate live-stage authorization boundary

Stage E is not implied by documentation work. Before any network request, the
operator must record explicit authorization covering all of the following:

1. live DataNewton finance reads;
2. official FNS comparator reads;
3. exactly three to five Russian legal entities with public statements;
4. at most five DataNewton finance calls, one per selected company;
5. finance dataset only and the exact intended endpoint/filter shape;
6. no production database and no existing production report as evidence;
7. no paid AI, contacts, or natural-person dataset;
8. raw outputs and the identifier map outside tracked paths;
9. sanitized field-level results only in git;
10. no automatic retry of an ambiguous request.

Current authorization record:

```text
authorization = absent
companies_selected = 0
datanewton_calls = 0
fns_reads = 0
tracked_matrix_rows = 0
candidate_policy_state = UNVERIFIED
runtime_capability = BLOCKED
```

Therefore this artifact stops before preflight selection or collection.

## 7. Authorized preflight procedure

When separately authorized, the collector must:

1. Select exactly `3..5` Russian legal entities with public FNS statements.
2. Store the private mapping only in an ignored/private file and assign tracked
   pseudonyms `C01..C05`.
3. Confirm the finance-only DataNewton endpoint/filter and record an exact
   response shape version.
4. Confirm that no contact or natural-person data is requested.
5. Resolve credentials only through existing protected configuration and never
   print them.
6. Create an ignored raw destination outside tracked paths.
7. Record tool version, UTC collection date, and an opaque evidence-session ID.
8. Verify the official FNS document and explicit OKEI for each form/year.
9. Refuse production DB URLs and production report storage as comparators.
10. Abort rather than retry if request success or billing outcome is ambiguous.

## 8. Field-level matrix schema

Every attempted comparable cell must produce one sanitized tracked row with
exactly these evidence fields:

| Field | Contract |
|---|---|
| `evidence_session_id` | Opaque non-identifying session token |
| `pseudonym` | One of `C01..C05` |
| `form_id` | `balance` or `financial_results` |
| `line_code` | One of the twelve approved codes |
| `reporting_year` | Four-digit public accounting year; not an identifier |
| `datanewton_presence` | `missing \| zero \| nonzero` |
| `fns_presence` | `missing \| zero \| nonzero` |
| `fns_okei_state` | `accepted_384 \| accepted_385 \| rejected_missing \| rejected_ambiguous \| rejected_other` |
| `fns_okei_code` | `384 \| 385 \| null`; non-null only for the matching accepted state |
| `comparison_outcome` | `exact_nonzero \| exact_zero \| exact_missing \| mismatch \| unavailable \| rejected_okei` |
| `scale_outcome` | `direct_thousand \| exact_million_to_thousand \| not_applicable` |
| `datanewton_raw_sha256` | Hash of the private exact source artifact; no raw value |
| `fns_document_sha256` | Hash of the private official document; no identifier-bearing URL |
| `provider_shape_version` | Exact closed shape/version scope |
| `collection_tool_version` | Exact collector version |
| `collected_at` | UTC timestamp |

Raw values are compared privately but are never copied into the tracked row.
Aggregate-only counts cannot activate the gate; every cell outcome must remain
auditable through its field-level row and private content hashes.

The OKEI columns obey these non-contradictory invariants:

- `accepted_384` iff `fns_okei_code=384`, with `direct_thousand`;
- `accepted_385` iff `fns_okei_code=385`, with
  `exact_million_to_thousand`;
- every `rejected_*` state has `fns_okei_code=null`,
  `comparison_outcome=rejected_okei`, and `scale_outcome=not_applicable`;
- accepted states cannot have `comparison_outcome=rejected_okei`;
- a rejected state cannot contribute an exact match or any proof cell.

## 9. Deterministic comparison algorithm

For each pseudonym:

1. Collect at most one DataNewton finance response.
2. Select the latest two common reporting years for which the corresponding
   FNS form is legally available; do not use browser/system current year.
3. For every required `(form,code,year)`, classify each side independently as
   `missing`, `zero`, or `nonzero` before comparison.
4. Classify the FNS OKEI into the closed state catalog in section 5 before
   value normalization. Rejected OKEI states stop that cell with
   `rejected_okei`; no raw rejected token is tracked.
5. Normalize the FNS value to exact thousands only for `accepted_384` or
   `accepted_385`, then compare exact Decimal values:
   - two absent values => `exact_missing`;
   - two explicit zeros => `exact_zero`;
   - two exact non-zero Decimals => `exact_nonzero`;
   - every other comparable difference => `mismatch`;
   - unavailable source/form/year => `unavailable`;
   - invalid OKEI => `rejected_okei`.
6. Do not round, tolerate, interpolate, coerce missing to zero, or choose a
   multiplier after seeing the result.
7. Preserve pseudonym, form, code, year, presence classes, closed OKEI state,
   accepted OKEI code or null, scale outcome, and hashes in deterministic
   order.
8. Generate per-code summaries from the field rows; summaries never replace
   them.

Deterministic row order is:

```text
pseudonym ASC
form catalog order: balance, financial_results
line_code numeric ASC
reporting_year ASC
```

## 10. Strengthened pass criteria

Promotion is atomic and requires every condition below:

1. Exactly three to five pseudonyms complete the matrix.
2. Each company contributes two common reporting years for both forms wherever
   those statements are legally available; every unavailable cell is recorded.
3. At least three companies contribute two common years across both forms.
4. Both forms and all twelve exact `(form,code)` pairs are represented.
5. Every `(form,code)` pair has at least one exact non-zero comparison.
6. Every `(form,code)` pair has exact non-zero matches in at least two distinct
   companies.
7. Each form has non-zero evidence in both compared year positions.
8. At least one direct non-zero OKEI-384 match exists in each form.
9. No one company contributes more than half of all non-zero proof cells.
10. Every comparable cell, including missing and zero, has a tracked
   field-level outcome.
11. Every comparable non-zero cell matches exact Decimal at
    `1 source unit = 1 thousand rubles` after permitted FNS normalization.
12. Every OKEI state is accepted, and there is no mismatch, rejected OKEI,
    contradictory OKEI state/code/outcome tuple, mixed scale, form-specific
    scale, duplicate conflict, or shape/filter drift.
13. Endpoint, filter, response shape, tool version, evidence session, and
    private source hashes are recorded reproducibly.

Missing/zero pairs prove coverage semantics only. They never count as non-zero
unit proof.

## 11. Fail and rejection rules

Any single mismatch fails the whole candidate policy. Insufficient coverage or
authorization leaves it `unverified`; contradictory evidence makes it
`rejected`.

Closed reason codes:

```text
authorization_missing
company_count_out_of_bounds
call_budget_exceeded
form_coverage_insufficient
year_coverage_insufficient
line_code_nonzero_coverage_insufficient
company_diversity_insufficient
direct_okei_384_evidence_insufficient
okei_missing
okei_ambiguous
okei_other
exact_value_mismatch
mixed_or_form_specific_scale
provider_shape_or_filter_drift
duplicate_conflict
private_provenance_missing
```

Failure consequences:

```text
schema_gate = unverified or rejected
semantic_gate = unverified or rejected
candidate_policy = inactive
runtime_capability = BLOCKED
```

There is no reduced-evidence mode, percentage threshold, manual override, or
UI-only ruble label.

## 12. Atomic promotion and stale policy

Only a full pass may change the registry decision together:

```text
schema_gate = verified
semantic_gate = verified
candidate_policy = active-for-implementation
```

Activation scope is the exact endpoint, filter, provider shape version, forms,
codes, and comparison procedure recorded by the passing artifact. A change in
any of these makes the policy stale and blocks new monetary facts until a new
versioned evidence artifact passes.

If a future matrix observes fractional-thousand precision, a different scale,
mixed units, or a form-specific scale, the candidate is rejected and the
formatter/scaling policy must be redesigned in a new iteration. Existing
immutable evidence-v1 is not rewritten.

## 13. Downstream handoff

- Iteration 20 may implement exact persisted finance series and blocked
  coverage/limitations, but it must not emit monetary H2 Chart Facts while this
  gate is closed.
- Iteration 23 cannot start until an active evidence policy exists.
- `finance_decimal_transport` remains `UNVERIFIED / BLOCKED` until the future
  lexical source-byte ingestion evidence and negative tests pass; a successful
  OKEI matrix alone does not close it.
- Old v1/v2 snapshots are never upgraded, refreshed, or backfilled on read.
- Public GET, SSR, crawler, and client takeover never perform the comparator or
  call DataNewton/FNS.
- After merge, later evidence is a new immutable version; this artifact remains
  the record that iteration 19 finished with `UNVERIFIED / BLOCKED`.
