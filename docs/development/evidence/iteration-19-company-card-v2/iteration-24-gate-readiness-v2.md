# Iteration 24 gate readiness v2

Artifact ID: `company_card_v2_iteration_24_gate_readiness_v2`

Decision date: `2026-08-26`

Repository base: `8a1d27866187df470bc628f9b5e7f500204222e7`

Evidence: `arbitration-contract-evidence-v3.md`

Owner decision:
`docs/development/decisions/iteration-24-owner-scope-decision-v1.md`

Supersedes start decision: `iteration-24-gate-readiness-v1.md`

Final decision: `READY FOR FULL ITERATION 24 PLANNING — NARROWED SCOPE`

Production activation: `NOT AUTHORIZED`

## 1. Why planning is now allowed

Readiness v1 correctly blocked the broad Roadmap scope because it depended on
provider ordering across requests, a party entity classifier and an unchosen
case-identity transition. The owner has now approved D1–D6:

- `case_id`-only new writes with frozen legacy fallback reads;
- exact-INN-only target attribution;
- one `offset=0,limit=1000,company_role=ALL` request and forced partial above
  1,000 cases;
- RUB-only claim-price A4;
- all-masked A5 with report-scoped HMAC grouping;
- only `first_number` among the initially optional details.

These decisions remove the pre-planning contradictions without claiming that
the absent provider guarantees exist. No further live evidence pass is needed
before iteration 24 planning.

## 2. Gate disposition

| Surface | State for iteration 24 | Runtime/public consequence |
|---|---|---|
| Endpoint/request/OpenAPI binding | verified for the exact D3 profile | a versioned registry may bind it; operation remains separately off |
| New case identity | owner-approved `case_id`-only | new basis only; V1 fallback reads remain frozen |
| Collection completeness | owner-approved single-page policy | complete only at exact `total<=1000`; above it always returned-slice partial |
| Calendar horizon | unverified | observed years only; no synthetic zero or no-cases assertion |
| Target role | verified fields plus owner-approved INN-only rule | OGRN/name/`*_src` target fallbacks forbidden |
| Outcome | verified company-scoped catalog | only WON/LOST/RETURNED map publicly; everything else unknown |
| Amount | verified as claim price | source-byte lexical Decimal is an implementation gate |
| Currency | RUBLES verified; OTHER unidentified | one RUB group; OTHER/unknown excluded with limitation |
| Entity type | absent/rejected | no named opponents |
| All-masked A5 | owner-approved | eligible opponents only, `masked_unknown`, HMAC/ordinal privacy contract |
| Optional details | first number approved | result detail, instances/courts and links remain null |
| Provider/runtime operation | not authorized | production defaults and an explicit operation gate remain off |

## 3. Implementation-owned gates

Planning must close these gates with code and tests rather than new external
facts:

1. Exact conditional-zero envelope validation and request-profile binding.
2. Exact `DataNewtonResult.dataset="arbitration_cases"` binding and whole-result
   fail-closed handling when the raw-number transport/topology is invalid;
   `/data/{index}/sum` then uses direct finite Decimal parsing and negative
   float/string/exponent/precision cases.
3. Raw-row, case, basis and public-byte bounds; deterministic dedup/conflict
   exclusion and reason/counter invariants.
4. Missing role collections, malformed rows, duplicate conflicts and cap
   stops producing partial/failed states rather than false completeness.
5. Report-scoped HMAC, persisted report/job key decision, key rotation/failure,
   stable/group fallback ordering, public ordinal generation and all-masked
   labels.
6. Typed public allowlists for the contracted case/opponent IDs while retaining
   global rejection of raw identity, HMAC, names, arbitrary URL and secrets.
7. New immutable snapshot/publication lineage plus the minimal append-only
   report/job decision migration, without rewriting V1/V2 or changing
   finance-only publication policy v2.
8. A1–A5 arithmetic, top-20/N-of-M, coverage/limitation cross-rules and exact
   backend display/geometry.
9. Python/TypeScript DTO parity, SSR factual fallback, lazy accessible SVG and
   asset-manifest compatibility.
10. Zero provider/AI/write work on GET/HEAD and default-off production settings.

## 4. Planning boundary

The full iteration 24 specification and plan may now be written and reviewed.
They must preserve:

```text
company_card_v2_feature_default = off
provider_runtime_operation = disabled
production_publication = disabled
live_provider_calls_in_tests = prohibited
```

The historical `arbitration-contract-evidence-v3.md` and readiness v1 remain
unchanged records of the state before the owner decision. This v2 readiness
artifact changes planning eligibility only; it does not activate the shipped
collector or evidence registry by itself.

Because this is ordinary interactive work rather than an explicit `$devflow`
run, independent plan review does not replace owner approval of the completed
implementation plan. Production code begins only after that separate approval.
