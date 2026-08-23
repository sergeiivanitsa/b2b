# Arbitration contract evidence v2 — live page and privacy matrix

Artifact ID: `company_card_v2_arbitration_contract_evidence_v2`

Evidence date: `2026-08-24`

Evidence session: `64fcf9bb84f045d5bd8652ecabdf2a81`

Overall arbitration gate: `UNVERIFIED / BLOCKED`

## 1. Decision

The authorized live pass strengthens the observed response-envelope and
field-path evidence left by v1. It does **not** close the mandatory pre-call
envelope binding because provider total scope and a versioned authoritative
request/schema contract remain unavailable. It also proves that the current
response does not provide a usable party entity-type leaf. Shape evidence does
not establish company-scoped outcome meaning, a currency dictionary or
complete bounded collection.

```text
envelope_path_type_observation = verified_observed_shape
pre_call_envelope_gate = unverified
total_scope = unverified
authoritative_request_shape_version = unverified
offset_page_observation = stable for offset 0 -> 100
case_field_schema_gate = verified for paths listed below
pagination_completeness = unverified / implementation-owned
case_identity_semantics = unverified
party_result_company_scope = unverified
currency_mapping = unverified
party_entity_type = rejected_missing / blocked
instance_and_visible_number_semantics = unverified
kad_public_link = unverified / disabled
```

The safe implementation consequence is fail-closed: iteration 20 may implement
the bounded collector and persist sanitized evidence only after it is otherwise
unblocked, but public A1–A5 activation remains gated per field.

## 2. Authorized collection

The first pass made one arbitration request per pseudonym with `offset=0`,
`limit=100`, retry disabled in the follow-up profile. Because two populations
exceeded one page, a controlled follow-up made exactly two additional requests
with `offset=100`, `limit=100`, retry disabled. No attempt was made to collect
all 883 or 11,574 cases.

The observed request shape was `GET /v1/arbitration-cases` with a private
`inn`, `offset` and `limit`, and without `company_role`, `status`, date,
`updated_at_from` or `need_document` filters. This records what was sampled;
it is not an authoritative statement that `total_cases` has the required
target/filter population scope.

| Pseudonym/page | Received at (UTC) | `total_cases` | Returned | Private raw SHA-256 |
|---|---|---:|---:|---|
| `C01/0` | `2026-08-23T14:12:52.393017Z` | 5 | 5 | `8d84ce8f608189e8f673971481ef1dced56cee2161f37acc5aeb655dcb57d9f3` |
| `C02/0` | `2026-08-23T14:13:06.442077Z` | 883 | 100 | `25988680dd7d568551e82ce40d1ba90523f17b5808c0ba583c9df4382cf8fa27` |
| `C02/100` | `2026-08-23T14:26:07.337847Z` | 883 | 100 | `927eae27bd306855ffcb164e2de15f57472050e88acc3c41a898ae9e57d16a55` |
| `C03/0` | `2026-08-23T14:13:19.569718Z` | 11,574 | 100 | `3fb09e8a8e4fe75da64c51e63e082e25b91ef701fd2acb9b2a4c64637e6de017` |
| `C03/100` | `2026-08-23T14:26:08.483515Z` | 11,574 | 100 | `c8fe3caa464cbfb8885f127ae4cf14638e4a6bd29fb1f47007efe1e68884e8b7` |

All raw pages remain private. Tracked evidence contains no case number, party
name, INN/OGRN, amount, raw URL or provider free text.

## 3. Envelope binding

The exact live envelope for the tested request profile is:

| Member | Exact path | Required type | Observation |
|---|---|---|---|
| rows | `$.data` | array | present on all five pages |
| total | `$.total_cases` | nonnegative integer | present; stable across the two C02 and two C03 pages |
| offset | `$.offset` | nonnegative integer | exact 0/100 response values matched requests |
| limit | `$.limit` | positive integer | exact 100 on all pages |

For both two-page observations:

- total and limit were stable;
- response offsets were exactly 0 then 100;
- both pages contained 100 rows;
- effective `case_id`/`id` sets had zero overlap.

This verifies a five-page path/type observation and supports the proposed
expected-offset check. It is not sufficient to close the v1 pre-call envelope
gate: `total_scope` and an authoritative request/shape version are still
missing. It is also not proof that a future ten-page bounded collector
completes every population, and it does not waive total/offset drift,
duplicate, short-page, byte-cap or non-progress protections.

## 4. Live case-field schema

Across 405 inspected case rows (three first pages plus two second pages), the
following paths had stable observed types:

| Concern | Exact path | Observed type/presence | Schema decision | Semantic/public decision |
|---|---|---|---|---|
| preferred key | `$.data[*].case_id` | nonblank string, 405/405 | verified | internal only; long-term identity semantics unverified |
| fallback key | `$.data[*].id` | nonblank string, 405/405 | verified | used only when preferred key is absent/blank; never public |
| visible number | `$.data[*].first_number` | nonblank string, 405/405 | verified | display semantics unverified; do not substitute a key |
| year | `$.data[*].year` | integer, 405/405 | verified | start-year semantics unverified |
| start/update dates | `$.data[*].{date_start,date_update}` | strings, 405/405 each | verified | validate independently; inversion remains a limitation |
| amount | `$.data[*].sum` | number, optional | verified post-coercion | lexical Decimal and business meaning unverified |
| currency | `$.data[*].currency` | string, optional | verified | observed tokens were not ISO three-letter codes; mapping remains blocked |
| target result | `$.data[*].party_result` | nonblank string, 405/405 | verified | company scope/meaning unverified |
| result detail | `$.data[*].result_type` | nonblank string, 405/405 | verified | never substitutes for outcome |
| instance count | `$.data[*].instance_count` | integer, 405/405 | verified | count semantics unverified |
| instances | `$.data[*].instances` | array of strings | verified | court/instance label contract unverified |
| KAD candidate | `$.data[*].kad_arbitr_link` | nonblank string, 405/405 | verified | public link remains disabled pending identity/path semantics |

The observed `party_result` token union was:

```text
IN_PROGRESS
LOST
LOST_PARTIAL
RETURNED
SETTLEMENT
TERMINATED
UNDEF
WON
WON_PARTIAL
```

The already approved public transform remains closed and conservative:
`WON`, `LOST` and `RETURNED` may only map after company-scope semantics are
verified; every other or missing token is `unknown`. `result_type` is never an
outcome fallback.

## 5. Roles and entity privacy

The nine role collections were observed as arrays:

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

Party rows exposed `inn`, optional `inn_src`, `ogrn`, optional `ogrn_src`,
`name`, `norm_name` and `role` candidates. Identifiers remain internal-only;
free role text cannot override the source collection. Target attribution uses
only an exact normalized target INN match, and a case with multiple matched
role collections is classified as `other`.

Across 1,678 inspected party rows, no key containing an entity/person-type or
kind candidate was present. Therefore the provider response cannot safely
distinguish a legal entity, state body, natural person or unknown party.

```text
party_entity_type_schema = rejected_missing
public_opponent_name = prohibited without another verified classifier
safe_fallback = report-scoped opaque mask
```

Names must not be classified from text, OPF fragments, INN/OGRN length or a
role. This missing field is a real blocker for public A5 names, not a parser
task.

## 6. Currency and KAD limitations

The currency field was present whenever an amount was present, but its live
strings did not satisfy the closed ISO `[A-Z]{3}` grammar. Raw tokens are not
tracked, guessed or mapped. Amounts therefore remain excluded from public A4
currency groups until a versioned dictionary is evidenced.

All 405 KAD candidates used HTTPS, host `kad.arbitr.ru`, and no query or
fragment. Host shape is verified, but the identifier-bearing path is not
tracked and its exact case correspondence was not semantically proven. Public
links stay disabled; a future allowlist must require HTTPS, the exact host/path
grammar and `Referrer-Policy: no-referrer`.

## 7. Implementation-owned gates

These cannot be closed by a five-page live sample and remain mandatory tests
inside iteration 20 if the iteration is later unblocked:

1. source-byte lexical Decimal capture and lossy-float rejection;
2. page size 100, maximum 10 pages, 1,000-row and 8 MiB caps;
3. total/offset/limit drift, overlap, empty/non-progress and cap+1 handling;
4. deterministic canonical dedup with conflict exclusion;
5. `collection_complete` independent from calendar completeness;
6. exact counts, completion reasons and immutable page/hash provenance;
7. public identifier/HMAC and negative privacy scans.

## 8. Downstream consequence

The observations are suitable for fixtures and fail-closed parser design, but
they do not authorize the first v3 provider request. The pre-call envelope
gate, outcome scope, currency, visible-number/instance meaning and party entity
type remain blocked. Iteration 24 cannot start from this artifact alone, and
iteration 20 must not invent the missing semantics.
