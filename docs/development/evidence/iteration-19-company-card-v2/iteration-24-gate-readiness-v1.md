# Iteration 24 gate readiness v1

Artifact ID: `company_card_v2_iteration_24_gate_readiness_v1`

Decision date: `2026-08-26`

Repository base: `8a1d27866187df470bc628f9b5e7f500204222e7`

Evidence:
`arbitration-contract-evidence-v3.md`

Final decision: `BLOCKED — OWNER SCOPE DECISION REQUIRED`

Production activation: `NOT AUTHORIZED`

## 1. What changed

The new official OpenAPI binding closes the old external blockers for the
target endpoint/envelope, request-scoped total, authoritative `case_id` leaf,
exact role collections, start-year meaning, company-scoped `party_result`,
claim-price meaning and ruble currency. The identity-policy transition remains
an owner decision. Another live provider sample is not needed before planning.

The original broad iteration 24 still requires named legal/state opponents and
does not choose a safe completeness policy when provider ordering across pages
is undocumented. Those are product-scope decisions, not facts that code or a
live sample may invent.

## 2. Per-view readiness

| View | External evidence | Remaining pre-planning decision | Implementation-owned acceptance gates |
|---|---|---|---|
| A1 activity | target total, roles and start year verified | choose identity/completeness versions; observed years only | bounds, dedup, partial scope, no zero-fill, accessible chart/fallback |
| A2 roles | role collections and exact party INN verified | retain exact-INN-only product rule | one case/one bucket, percentages, details and exact N/M |
| A3 outcomes | company-scoped catalog verified | retain narrow `WON/LOST/RETURNED/unknown` mapping | multi-role unknown, no win rate, exact denominator |
| A4 amounts | claim price and `RUBLES` verified | accept RUB-only view; exclude `OTHER` with limitation | source-byte Decimal, zero/negative/missing, no FX/debt wording |
| A5 opponents | party identifiers verified; entity type absent | choose all-masked A5 or defer the view/classifier | report-scoped HMAC, grouping fallback, scanner allowlist, no names/IDs |

Visible case number, instances/courts and KAD links are optional detail
enhancements. They do not block the five aggregate views when null. KAD links
must remain null until exact scheme/host/path/case-id validation and
`Referrer-Policy: no-referrer` pass.

## 3. Recommended owner decision package

### D1 — versioned case identity

Adopt `arbitration_case_identity_case_id_only_v1` for a new
`company_card_arbitration_basis_v2` / normalization-v2 path:

```text
new writes: exact nonblank case_id is the sole private case key
missing/blank case_id: row is malformed; id never repairs it
first_number: optional display only
```

Existing `ArbitrationBasisV1`, snapshots, fixture tests and readers retain the
historical `case_id -> id` fallback and are never rewritten or re-normalized.
The new writer stores an explicit identity-policy version. This is a versioned
compatibility transition, not a reinterpretation of V1.

### D2 — target attribution

Retain the current versioned rule:

```text
target role match = exact normalized party.inn only
party.ogrn, names, fuzzy values and every *_src field = forbidden fallbacks
```

This preserves the iteration 19 Chart Facts meaning. Adding OGRN would require
a new role-policy version, conflict rules and compatibility path.

### D3 — versioned completeness profile

Adopt `datanewton_arbitration_single_page_1000_v1` for new basis-v2 writes
only. It supersedes the iteration 19 `page_size=100` policy only on that path;
legacy V1 fixtures/snapshots/readers remain unchanged.

```text
GET /v1/arbitration-cases
inn=<exact target>
company_role=ALL
offset=0
limit=1000
no other filters
```

The complete predicate is exact:

```text
total_cases, offset and limit are present exact integers; bool is rejected
offset == 0 and limit == 1000
total_cases == 0 -> data is absent or exactly []
0 < total_cases <= 1000 -> data is present and len(data) == total_cases
total_cases > 1000 -> always partial; no second request
total_cases == 0 with nonempty data -> envelope_invalid
all byte/row/case_id/dedup/privacy checks pass
```

Any failed clause is partial/invalid, never complete. The evidence registry
must bind the exact request/profile/identity/collection-policy versions.

### D4 — amount/currency scope

Publish A4 only for exact source token `RUBLES`, mapped to `RUB`. An
absent/null token alone contributes to existing `missing_currency_count`.
`OTHER` or an unknown nonblank token is excluded from currency groups and adds
`arbitration_currency_unidentified`, without being counted as missing. A
public unidentified-currency count is deferred until a versioned DTO extension
is approved. No FX conversion or guessed symbol is allowed.

### D5 — A5 privacy scope

Use all-masked A5 only for actual opposing-party collections:

```text
target plaintiff  -> eligible respondents
target respondent -> eligible plaintiffs
target other/unattributed -> no guessed opponent
all eligible opponents -> entity_class=masked_unknown
```

Stable private grouping uses one exact normalized, verified, nonconflicting
`party.inn`, else one equally eligible `party.ogrn`. Invalid, multiple,
ambiguous or provenance-conflicting candidates use the exact case-position
identity; `*_src` is never an identifier. INN has priority only after those
checks. The same stable identity contributes a case once to a group.

HMAC input is the existing exact canonical-JSON `OpponentHmacIdentityV1` with
the literal domain, lowercase report UUID and discriminated identifier. Only
the full 64-hex HMAC, algorithm version and nonsecret key ID survive in the
sanitized basis; raw names and identifiers are transient and discarded.
Missing/unknown key material fails closed. Public IDs keep
`opponent_[0-9]{6}` and the fixed masked label is `Сторона скрыта N`, where
`N` is the unpadded ASCII decimal form of the exact one-based public ordinal.

This preserves useful report-scoped grouping while revealing no natural or
legal names. A future verified entity classifier requires another versioned
decision.

### D6 — optional details

Allow validated `first_number`. Keep `result_type`, instance labels and KAD
links null in the first implementation unless their typed catalogs/security
validators are explicitly included and tested in the approved iteration 24
plan. Internal `case_id` never becomes a display fallback.

## 4. Readiness if the package is approved

Approval of D1–D6 permits a new owner-decision artifact to mark:

```text
iteration_24_planning = ready
scope = narrowed_fail_closed_v1
live_evidence_pass = not_required
provider_runtime_operation = not_authorized
company_card_v2_feature_default = off
production_publication = not_authorized
```

It does not pre-approve code, provider traffic or production activation. A
full iteration 24 DevFlow specification and plan must still cover:

1. new exact `company_card_arbitration_basis_v2` and normalization-v2 models,
   plus immutable `ArbitrationBasisV1` read compatibility;
2. conditional zero-envelope handling and the named single-page collection
   policy/registry binding;
3. direct raw-number-lexeme capture and exact `Decimal` transport;
4. deterministic role/outcome/A1–A5 Chart Facts and top-20/N-of-M rules;
5. eligible-opponent all-masked HMAC grouping, typed public allowlists and
   negative privacy scans;
6. immutable writer/projection compatibility and old snapshot/client reads;
7. SSR/DTO/frontend parity, accessibility and textual fallbacks;
8. default-off flags, zero read-path calls and no production activation.

The shipped arbitration registry remains closed, the existing collector is a
fixture-only seam, and the current writer persists an empty gate-closed
arbitration basis. Those surfaces change only inside the later approved
iteration 24 implementation and remain unauthorized for live use afterward
until a separate runtime/rollout decision.

## 5. If the package is not approved

- INN+OGRN target matching requires a separate versioned algorithm decision.
- Named A5 remains blocked until an authoritative entity classifier is
  supplied; names cannot be inferred from identifiers or text.
- Multi-page `limit=100` completeness remains blocked without a provider
  ordering/snapshot guarantee; such collections must be partial.
- Exact non-ruble A4 remains blocked because `OTHER` is not a currency ID.

Until an owner decision is recorded, Roadmap/DevFlow iteration 24 stays
`planned` with its current blocker and no runtime or production state changes.
