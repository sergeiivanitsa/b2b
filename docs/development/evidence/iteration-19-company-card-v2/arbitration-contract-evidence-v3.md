# Arbitration contract evidence v3 — official OpenAPI binding

Artifact ID: `company_card_v2_arbitration_contract_evidence_v3`

Evidence date: `2026-08-26`

Retrieved at: `2026-08-26T12:34:59Z`

Supersedes gate conclusions in:
`arbitration-contract-evidence-v2.md`. The v1/v2 observations remain immutable
historical evidence and are not relabelled.

Overall provider-contract gate: `VERIFIED FOR THE EXACT PROFILE BELOW`

Iteration 24 readiness: `BLOCKED — OWNER SCOPE DECISION REQUIRED`

Production/runtime activation: `NOT AUTHORIZED`

## 1. Decision

Current public DataNewton documentation exposes an embedded OpenAPI 3.1.0
contract with API version `v1`. Together with the live shape observations in
v2, it authoritatively binds the Company Card v2 arbitration endpoint,
request-scoped total, envelope members and most case semantics without another
provider call.

```text
contract_binding = datanewton_arbitration_openapi_v1_2026_08_26
endpoint = GET /v1/arbitration-cases
target_profile = exact INN + explicit company_role=ALL + no restrictive filters
total_scope = provider rows for that exact target-only request
envelope_paths_and_types = verified with conditional zero-data rule
authoritative_case_identity_leaf = case_id
case_identity_policy = owner versioning decision pending
visible_case_number = first_number
start_year = verified
party_result_company_scope = verified for unambiguous target role
claim_amount_meaning = claim price
currency_catalog = RUBLES | OTHER
party_entity_type = absent
calendar_horizon = unverified
ordering_or_snapshot_stability = unverified
source_byte_decimal = implementation_owned
```

This evidence does not activate the shipped registry, authorize provider
traffic, prove calendar zeroes or permit public opposing-party names. It
reduces the remaining pre-planning work to explicit scope decisions plus
implementation-owned exactness/privacy tests.

## 2. Authoritative sources and fingerprints

No `api.datanewton.ru` or documentation-sandbox request was sent. The sources
were read through the public documentation UI only.

| Source | Contract use | Retrieved article-text SHA-256 | UTF-8 bytes |
|---|---|---|---:|
| `https://datanewton.ru/docs/api/arbitration-cases` | target endpoint, request, envelope and case schema | `95ad211f6010a614231dae44d8abee35ea7b6ef5d8cad26f45bfcfcccee851df` | 5,939 |
| `https://datanewton.ru/docs/api/dictionary-arbitration-party-results` | target-scoped outcome semantics and dictionary shape | `3819bc92d2e75bbcce9f07210654a1c9db876ce50a50089f4581d763426e79cc` | 2,792 |
| `https://datanewton.ru/docs/api/arbitration-batch-cases` | filtered total and case-schema corroboration | `7fd413262924b086f9a7d2b492c66136971d55e02cc24cec01f22801d266dfb5` | 6,084 |
| `https://datanewton.ru/docs/api/arbitration-batch-cases-stat` | role/year aggregate corroboration | `6bf434085297c50918fb7f0a7e26e2125851626f85891d9511f3b09ac8f201f3` | 6,843 |
| `https://datanewton.ru/sources` | KAD source and refresh cadence | not used as a schema identity | n/a |

The page footer identified UI `3.0.40` dated 25 August 2026. The embedded
public `openApiSchema` identified OpenAPI `3.1.0`, title `Datanewton API`, API
version `v1` and server `https://api.datanewton.ru`.

For a stable schema fingerprint, the selected OpenAPI document was reduced to
`openapi`, `info`, `servers` and these paths:

```text
/v1/arbitration-cases
/v1/dictionary/arbitration/party-results
/v1/arbitration/batchCasesStat
/v1/arbitration/batch-cases-stat
/v1/arbitration/batch-cases
```

Object keys were recursively sorted, array order was retained and the result
was serialized as UTF-8 JSON:

```text
canonical_bytes = 107453
sha256 = 2c3d34ab00a35e58e07f7c3dea32b605b9e61d112a92a1654fd54e415ef851d2
```

The same hash was reproduced from loader data on a second documentation page.
The UI version is provenance only; `openApiSchema.info.version=v1`, URL,
retrieval time and content hash form the actual evidence binding.

## 3. Relationship to observed evidence

The v2 session observed five pages and 405 rows. It showed stable
`total_cases`, offsets and non-overlapping `case_id`/`id` sets across two
offset transitions. Three first-page raw responses remain private and their
hashes still match v2. The two offset-100 raw byte files are no longer present
locally; only their committed hashes and sanitized aggregate statements
remain. This retention limitation does not alter the new official contract,
but it prevents treating the old bytes as a reproducible full-pagination
corpus.

A separate ignored historical corpus contains 59 unique first pages, 4,366
case rows and 16,696 party rows. It strongly corroborates stable field
presence and the absence of an entity/person classifier, but it is
first-page-only and non-authoritative. No company identifiers, party names,
case numbers, amounts or URLs from that corpus are tracked here.

## 4. Exact request and envelope binding

The evidence-approved future request profile is narrower than the complete
provider API surface:

```text
method = GET
path = /v1/arbitration-cases
target parameter = inn only, exact 10 or 12 digits
company_role = ALL, sent explicitly
dispute/status/date/year/updated_at/document filters = omitted
```

The provider also documents OGRN/OGRNIP as an alternative request identifier.
That does not change the existing Company Card v2 exact-INN role-attribution
contract and does not authorize OGRN target matching.

| Member | Exact path | Official type/meaning | Binding rule |
|---|---|---|---|
| total | `$.total_cases` | nonnegative `integer<int64>`; total court cases | exact provider population for the profile above |
| offset | `$.offset` | nonnegative `integer<int32>`; case-count skip | must equal requested offset |
| limit | `$.limit` | `integer<int32>`; requested page size, maximum 1,000 | must equal the approved request size |
| rows | `$.data` | array of case objects | required when total or offset is non-zero |

The OpenAPI response schema has no `required` array, and its official zero-case
example omits `data`. Therefore the only safe absent-data normalization is:

```text
total_cases, offset or limit absent/wrong-type -> envelope_invalid
total_cases == 0 && offset == 0 && data absent -> data = []
total_cases == 0 && data == [] -> valid zero rows
total_cases == 0 && data nonempty -> envelope_invalid
total_cases > 0 && data absent/non-array -> envelope_invalid
```

`total_cases` verifies the exact request population. It does not prove an
eternal historical horizon, calendar bounds, stable ordering or snapshot
isolation across several requests.

## 5. Arbitration field-manifest delta

This section is the authoritative arbitration delta to the historical
`provider-field-manifest-v1.md` and `arbitration-contract-evidence-v2.md` rows.
Those observations remain immutable; their `id`, `inn_src` and `ogrn_src`
fallback assumptions are not valid inputs to a future v2 normalization path.

Common manifest scope for every row below:

```text
evidence dataset family = arbitration
local DataNewtonResult.dataset binding = arbitration_cases
endpoint = GET /v1/arbitration-cases
provider shape = OpenAPI 3.1.0, info.version=v1
contract fingerprint = 2c3d34ab00a35e58e07f7c3dea32b605b9e61d112a92a1654fd54e415ef851d2
subject scope = exact target INN, explicit company_role=ALL, no restrictive filters
provenance = official public docs retrieved 2026-08-26 plus v2 observations
operational gate = not_authorized for every row
```

Gate abbreviations are `Sch` schema, `Sem` semantics, `Priv` privacy and `Op`
operational. `V` means verified for the common scope, `P` pending an owner or
implementation gate, `R` rejected/missing, `NA` not applicable and `N` not
authorized.

| Field | Exact path | Type/cardinality/nullability | Subject/date/identity semantics | Gates `Sch/Sem/Priv/Op` | Public transform | Missing/conflict behavior |
|---|---|---|---|---|---|---|
| total | `$.total_cases` | `int64`, one, required by local binding, nonnegative | exact request population; not calendar horizon | `V/V/NA/N` | coverage total only | absent/bool/negative/drift invalid |
| offset | `$.offset` | `int32`, one, required by local binding, nonnegative | provider row-position skip | `V/V/NA/N` | provenance only | absent/bool/unexpected value invalid |
| limit | `$.limit` | `int32`, one, required by local binding, `0..1000` officially | provider page size | `V/V/NA/N` | provenance only | absent/bool/request mismatch invalid |
| rows | `$.data` | array, `0..limit`; conditionally absent only for zero example | cases for exact request | `V/V/P/N` | normalized cases only | absent allowed only for exact zero envelope; otherwise invalid |
| case key candidate | `$.data[*].case_id` | string, at most one/row, nullable by non-required schema | KAD case identity | `V/V/P/N` | private dedup key in a new policy version only | missing/blank row ineligible under proposed policy; conflicts excluded |
| legacy `id` | `$.data[*].id` | schema object but official example string | contradictory visible-number-like value; not proven KAD identity | `V/R/P/N` | retained only by legacy V1 readers | never admitted by proposed V2 identity policy |
| visible number | `$.data[*].first_number` | string, at most one/row, nullable | public case number; not identity | `V/V/P/N` | implementation-owned closed display grammar or null | missing/invalid null; never fall back to key |
| opened date | `$.data[*].date_start` | string, at most one/row, nullable | case opening date | `V/V/P/N` | strict ISO date or null | invalid null plus limitation |
| updated date | `$.data[*].date_update` | string, at most one/row, nullable | last update date | `V/V/P/N` | strict ISO date or null | invalid null; inversion limits duration |
| start year | `$.data[*].year` | `int32`, at most one/row, nullable | year of case start | `V/V/P/N` | observed-year bucket | missing/invalid `Год не указан`; no zero-fill |
| amount | `$.data[*].sum` | JSON number, at most one/row, nullable | claim price; reference is the case | `V/V/P/N` | exact Decimal only, never debt | missing stays missing; lexical failure excludes A4 value |
| currency | `$.data[*].currency` | string enum `RUBLES|OTHER`, at most one/row, nullable | source currency category | `V/V/P/N` | `RUBLES -> RUB`; `OTHER` no group | missing count differs from unidentified-token limitation |
| outcome | `$.data[*].party_result` | string closed enum, at most one/row, nullable | bound counterparty perspective when role is unambiguous | `V/V/P/N` | exact narrow mapping in section 6 | missing/other/multi-role `unknown`; raw token hidden |
| result detail | `$.data[*].result_type` | string closed enum, at most one/row, nullable | overall case result, not target outcome | `V/V/P/N` | null in first implementation | never outcome fallback |
| role collections | nine paths listed below | arrays, each `0..n`, nullable/non-required | source collection defines the party role | `V/V/P/N` | exact target-INN role evidence | missing/non-array collection makes role evidence incomplete; never infer empty |
| party INN | `<role>[*].inn` | string, at most one/party, nullable | identifier associated with that party row | `V/V/P/N` | transient exact match/HMAC input only | invalid/ambiguous/conflicting value not stable identity |
| party OGRN | `<role>[*].ogrn` | string, at most one/party, nullable | identifier associated with that party row | `V/V/P/N` | transient HMAC fallback only; never target-role fallback | invalid/ambiguous/conflicting value not stable identity |
| party provenance | `<role>[*].{inn_src,ogrn_src,name_src}` | string enum `OGRN|INN|NAME|ADDRESS`, at most one/party, nullable | describes how a value was restored | `V/V/P/N` | no public value; never identifier fallback | exact stable-ID eligibility matrix remains implementation-owned; no repair |
| party name | `<role>[*].{name,norm_name}` | string, at most one each/party, nullable | provider party label | `V/V/R/N` | prohibited in all-masked mode | absent/invalid ignored; never used to infer type/ID |
| party entity type | `NOT PRESENT` | no leaf in official schema or observed rows | unknown legal/natural/state class | `R/R/R/N` | all opponents `masked_unknown` or A5 closed | never infer from name/identifier length |
| instances | `$.data[*].{instances,instance_count}` | string array plus `int32`, nullable | passed instances and count | `V/V/P/N` | optional null or validated labels | mismatch makes optional detail unavailable |
| KAD link | `$.data[*].kad_arbitr_link` | string, at most one/row, nullable | link to KAD; exact grammar only exemplified | `V/P/P/N` | null until typed allowlist | any scheme/host/path/case mismatch null |

The nine documented role arrays are:

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

The current normative role algorithm remains exact target INN only. A single
plaintiff match maps to `plaintiff`, a single respondent match maps to
`respondent`, any other nonempty role set maps to `other`, and no exact match
maps to `unattributed`. OGRN, names, fuzzy matching and all `*_src` fields are
forbidden as target-role fallbacks.

## 6. Outcome, amount and currency decisions

The official dictionary states that `party_result` is present from the
counterparty's perspective when the company role is unambiguous. The exact
provider catalog is:

```text
WON
LOST
WON_PARTIAL
LOST_PARTIAL
SETTLEMENT
TERMINATED
RETURNED
IN_PROGRESS
UNDEF
```

The existing deliberately narrow public mapping remains:

```text
WON      -> won
LOST     -> lost
RETURNED -> returned
all other/missing/multi-role -> unknown
```

`UNDEF` maps to `unknown`; no stronger public meaning is inferred from the
token. `result_type`, status and document text never substitute for
`party_result`.

The provider defines `sum` as the claim price, not debt, awarded amount or
collected amount. OpenAPI type `number` is not proof of the original JSON
number lexeme. The existing probe files were reserialized after decoding and
cannot prove precision. Iteration 24 must capture the source lexeme directly
and prove lexeme/string → `Decimal` → immutable basis → Chart Facts → DTO
without a float source of truth.

The closed usable currency catalog is intentionally partial:

```text
RUBLES -> source_currency_id=RUB, display unit ruble
OTHER  -> unidentified source currency; excluded from A4 groups
missing/unknown -> excluded from A4 groups
```

`missing_currency_count` counts only an absent/null token. Exact `OTHER` and
unknown nonblank tokens produce `arbitration_currency_unidentified` without
being added to that missing count. A public unidentified-currency count would
require a separately versioned DTO extension; the first narrowed scope does
not add it. Excluded rows are never assigned RUB, converted, merged or removed
from collection totals.

## 7. Completeness and calendar boundary

Official documentation verifies offset mechanics and a maximum page size of
1,000, but it does not promise a stable sort or snapshot across several
requests. Stable totals and non-overlap in v2 are supporting observations,
not a general ordering guarantee.

Until an owner scope decision is recorded, neither of these policies is
active:

1. retain `limit=100` and mark every collection requiring a second page
   `partial` with `ordering_stability_unverified`;
2. adopt `datanewton_arbitration_single_page_1000_v1` for new V2 arbitration
   writes only and make exactly one `offset=0`, `limit=1000` request.

The proposed second policy has this complete predicate:

```text
total_cases, offset and limit are present exact integers; bool is rejected
offset == 0
limit == 1000
total_cases == 0 -> data is absent or exactly []
0 < total_cases <= 1000 -> data is present and len(data) == total_cases
total_cases > 1000 -> collection is always partial
total_cases == 0 with nonempty data -> envelope_invalid
all row/byte/case_id/dedup/privacy checks pass
```

Any failed clause is partial/invalid, never complete. The policy supersedes
the fixed `page_size=100` collector only for the new versioned arbitration
basis/normalizer path. Existing `ArbitrationBasisV1`, fixture tests, snapshots
and readers retain their historical semantics and are never rewritten.

The second policy is recommended because it matches the existing 1,000-row
hard cap and removes cross-request ordering from the complete path. It changes
the approved request profile and therefore requires the named versioned owner
decision, registry binding, compatibility tests and response-size/transport
tests.

Even a complete provider population does not prove `calendar_complete`.
DataNewton identifies KAD as the source, refreshed weekly, but publishes no
historical horizon. Iteration 24 must use observed years only:

```text
calendar_complete = false
calendar_scope = unverified
zero_years_proven = false
```

No empty year or statement that there were no cases may be synthesized.

## 8. A5 privacy boundary

Neither the official schema nor 16,696 observed party rows contains an
entity/person classifier. Names, OPF fragments, identifier lengths and role
labels cannot repair this absence. Public legal/state names remain blocked.

The existing privacy ADR already supports a safe narrowed A5 that reveals no
names:

```text
eligible opponents:
  target role plaintiff  -> respondents only
  target role respondent -> plaintiffs only
  target role other/unattributed -> none; never guess

entity_class = masked_unknown for every eligible opponent
stable identifier = one exact normalized, verified, nonconflicting party.inn
                 else one exact normalized, verified, nonconflicting party.ogrn
                 else exact case_key + source_role_collection + zero_based_ordinal
same stable identity within one case contributes that case once to its group
```

The HMAC input remains the exact closed `OpponentHmacIdentityV1` named object
from the iteration 19 privacy ADR. Its message is UTF-8 canonical JSON with
the literal domain, lowercase report UUID, `entity_class="masked_unknown"`
and the discriminated stable-identifier or case-position object. The complete
32-byte HMAC-SHA-256 is stored as 64 lowercase hex together with only the
algorithm version and nonsecret key ID. Raw identifiers and names are
transient inputs and are discarded from the sanitized basis. Missing/unknown
key material fails arbitration privacy normalization closed.

Invalid, multiple, ambiguous or provenance-conflicting identifier candidates
cannot become stable identities. INN has priority only after those checks;
OGRN is considered only when no eligible INN remains, and otherwise the
case-position identity is used. `*_src` is never the identifier value.

Public IDs retain the existing `opponent_[0-9]{6}` order contract and the
fixed Russian masked label is `Сторона скрыта N`, where `N` is the unpadded
ASCII decimal form of the exact one-based public ordinal after deterministic
ordering. Neither value contains a provider identifier or HMAC bytes.

This all-masked mode can remove the entity-type dependency only after an
explicit owner decision. It also requires a typed allowlist in the public
models/scanner for the contracted public ID fields; the current broad scanner
rejects any key containing `opponent` and every HTTPS value, so it cannot be
weakened globally.

## 9. Gate disposition

| Gate | State after v3 | Consequence |
|---|---|---|
| official endpoint/request version | verified | may bind a future registry version |
| total/data/offset/limit paths and request scope | verified, conditional data rule | no further live pass required |
| case identity leaf | `case_id` verified; transition policy pending | owner must version new writes; legacy V1 fallback stays readable |
| exact role collections and party INN/OGRN leaves | verified | target algorithm remains INN-only |
| start-year semantics | verified | observed years allowed; zero-fill prohibited |
| `party_result` scope/catalog | verified | narrow public mapping allowed |
| claim-price meaning | verified | lexical Decimal remains implementation-owned |
| exact currency | verified for `RUBLES`; rejected for `OTHER` | A4 can be RUB-only with limitation |
| entity type/public names | rejected missing | named A5 remains blocked |
| all-masked A5 | contract available; owner decision pending | can replace named A5 safely |
| multi-request ordering/snapshot | unverified | single-page or forced-partial policy required |
| KAD public link | meaning verified; security grammar pending | omit until typed allowlist passes |
| provider runtime operation | not authorized | shipped registry stays closed; later activation needs a separate decision |

## 10. Downstream consequence

No additional live DataNewton pass is required to decide iteration 24
planning. A live sample could observe another page but could not prove stable
ordering, entity type, calendar horizon or original numeric lexemes.

Iteration 24 remains blocked until the owner accepts or rejects the narrowed
scope in `iteration-24-gate-readiness-v1.md`. After approval, a versioned owner
decision and a separate iteration 24 specification/plan must be reviewed
before code changes. Runtime collection, registry activation and production
publication remain distinct later decisions.
