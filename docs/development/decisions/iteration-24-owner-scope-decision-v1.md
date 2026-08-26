# Owner decision: narrowed iteration 24 scope v1

Artifact ID: `company_card_v2_iteration_24_owner_scope_decision_v1`

Decision date: `2026-08-26`

Repository base: `8a1d27866187df470bc628f9b5e7f500204222e7`

State: `APPROVED FOR ITERATION 24 PLANNING`

Production activation: `NOT AUTHORIZED`

## 1. Decision

The owner approves the complete D1–D6 package proposed by
`iteration-24-gate-readiness-v1.md`, including the exact-INN-only target rule.
Iteration 24 may therefore be planned in a narrowed, fail-closed form without
waiting for a provider ordering guarantee, a historical calendar horizon or a
party entity classifier.

This is a versioned product-scope decision. It does not rewrite the iteration
19 contract, relabel historical evidence, reinterpret `ArbitrationBasisV1`,
authorize a DataNewton request or enable Company Card v2 in production.

```text
iteration_24_planning = ready
iteration_24_scope = narrowed_fail_closed_v1
target_attribution = exact_inn_only
live_evidence_pass = not_required
provider_runtime_operation = disabled
company_card_v2_feature_default = off
production_publication = disabled
```

## 2. D1 — versioned case identity

New arbitration writes use the named policy:

```text
identity_policy = arbitration_case_identity_case_id_only_v1
normalization_path = company_card_arbitration_basis_v2
authoritative private case key = exact nonblank case_id
```

Missing, non-string or blank `case_id` makes the row malformed. Provider `id`
never repairs it. `first_number` is an optional display field and never an
identity fallback.

Existing `ArbitrationBasisV1`, historical snapshots, fixture tests and readers
keep their frozen `case_id -> id` fallback. They are not rewritten,
re-normalized or made eligible for the new semantics. New persistence and
publication lineage must carry the new identity/basis version explicitly.

## 3. D2 — exact-INN target attribution

Target role attribution remains:

```text
target match = exact normalized party.inn == exact normalized subject INN
```

Party OGRN/OGRNIP, names, fuzzy matching and `inn_src`, `ogrn_src` or
`name_src` are forbidden as target-role fallbacks. One exact plaintiff role is
`plaintiff`, one exact respondent role is `respondent`, any other nonempty role
set is `other`, and no exact match is `unattributed`.

An INN+OGRN target algorithm would be a different versioned product decision
and is not part of iteration 24.

## 4. D3 — single-page completeness profile

New basis-v2 writes use:

```text
collection_policy = datanewton_arbitration_single_page_1000_v1
method = GET
path = /v1/arbitration-cases
inn = exact target INN
company_role = ALL
offset = 0
limit = 1000
all other filters = omitted
request count = exactly one
```

The collection is complete only when:

```text
total_cases, offset and limit are present exact integers; bool is rejected
offset == 0
limit == 1000
total_cases == 0 -> data is absent or exactly []
0 < total_cases <= 1000 -> data is present and len(data) == total_cases
total_cases > 1000 -> always partial; no second request
total_cases == 0 with nonempty data -> envelope_invalid
all row, byte, case_id, dedup and privacy checks pass
```

Any failed clause is partial or invalid, never complete. Safe rows already
admitted before a row/cap failure may remain a returned slice, but no count is
extrapolated to `total_cases`. `total_cases > 1000` always means returned-slice
scope even when exactly 1,000 rows were received.

The policy supersedes the old page-size-100 collector only for the new
basis-v2 path. It does not change legacy V1 fixtures/readers. The evidence
registry must bind the exact endpoint, request, OpenAPI fingerprint, identity
policy and collection policy before the new collector is callable. A separate
default-off operational gate must still block production provider traffic.

## 5. D4 — RUB-only A4

The provider field `sum` is a claim price, not debt, awarded amount or
collection. A4 admits an amount only after exact source-lexeme transport to a
finite `Decimal` and only with the exact currency token:

```text
RUBLES -> source_currency_id=RUB, ruble display
OTHER -> unidentified source currency, excluded from A4 groups
missing/null -> excluded and counted in missing_currency_count
unknown nonblank -> unidentified source currency, excluded from A4 groups
```

`OTHER` and unknown nonblank tokens add the limitation
`arbitration_currency_unidentified`; they are not counted as missing. A public
unidentified-currency count is deferred because it would require a separately
versioned DTO extension. FX conversion, an inferred symbol and debt wording
are forbidden.

## 6. D5 — all-masked A5

Only actual opposing collections are eligible:

```text
target role plaintiff  -> respondents
target role respondent -> plaintiffs
target role other or unattributed -> none
```

Every eligible opponent has `entity_class="masked_unknown"`. No legal,
government or natural-person name is emitted. A future verified entity
classifier and named-opponent mode require another owner decision.

Private stable grouping uses exactly one valid, normalized, verified and
nonconflicting party `inn`; if none exists, exactly one equally eligible party
`ogrn`; otherwise it uses the exact case-position identity. Invalid, multiple,
ambiguous or provenance-conflicting candidates fall back to case position.
`*_src` is never an identifier value. The same stable identity contributes a
case at most once to a group.

The HMAC input is the frozen `OpponentHmacIdentityV1` canonical-JSON object
from the iteration 19 privacy ADR, with literal domain, lowercase report UUID,
`entity_class="masked_unknown"` and a discriminated stable-identifier or
case-position object. The full 32-byte HMAC-SHA-256 is stored as 64 lowercase
hex with only its algorithm version and nonsecret key ID. Secret material,
raw identifiers and raw names are transient and discarded. Missing, disabled
or unknown key material fails arbitration normalization closed.

Public identifiers remain `opponent_[0-9]{6}`. The only public label is
`Сторона скрыта N`, where `N` is the unpadded ASCII-decimal exact one-based
public ordinal after deterministic ordering. Neither value contains source
identity or HMAC bytes.

## 7. D6 — optional details

The first implementation may publish a safely normalized `first_number` as
the visible case number. Internal `case_id` never becomes a display fallback.

`result_type`, instance/court labels and KAD links stay null initially. They
may enter a later version only with an explicit closed catalog or typed
scheme/host/path/case-binding validator and dedicated tests. A KAD link also
requires the public no-referrer boundary. These optional details do not block
A1–A5 aggregates.

## 8. Required iteration 24 deliverables

The implementation plan may cover only:

1. A new immutable basis/normalization path carrying D1–D5 policy identities,
   with explicit snapshot/publication lineage and frozen V1/V2 reads.
2. One exact request through a separately default-off operational gate, the
   conditional zero envelope and bounded partial-slice behavior.
3. Source-byte number-lexeme reuse for arbitration `sum` and exact `Decimal`
   transport without `float` truth.
4. Pure deterministic A1–A5 facts and public projection: observed years only,
   exact roles, narrow outcomes, RUB-only A4 and all-masked A5.
5. Top-20 details, exact `N/M`, report-scoped public ordinals, typed privacy
   allowlists and negative sink scans.
6. Immutable writer/pin/narrative/resolver compatibility for old and new
   snapshot/publication policies, with no read-side writes or provider calls.
7. Equivalent SSR and React facts, lazy accessible SVG enhancement and local
   error fallback using the iteration 23 asset-manifest boundary.
8. Unit, component, contract, release and disposable-PostgreSQL tests while
   every production default remains off.

## 9. Explicitly out of scope

- Live DataNewton, FNS, Gateway or paid-AI calls during implementation/tests.
- Production provider operation, deploy, feature activation, publication
  assignment, backfill, report refresh or migration execution on production.
- Multi-request pagination or a claim of completeness when `total_cases` is
  greater than 1,000.
- Historical calendar completeness, synthetic zero years or wording that an
  unobserved year had no cases.
- OGRN/name/fuzzy target attribution.
- Named opponents, entity-type inference or publication of any party name,
  INN, OGRN, HMAC, source ordinal or provider case identity.
- Non-ruble currency grouping, FX, debt/award/collection interpretation.
- Initial publication of `result_type`, instances/courts or KAD links.
- Arbitration-derived scoring, verdict, probability, prediction or win rate.
- Changes to Claims, H1 signals/scoring or existing report meaning.
- Full iteration 25 rollout/browser matrix.

## 10. Acceptance boundary

Iteration 24 can be ready for merge only when independent review confirms:

- V1/V2 snapshots and publication policies retain their exact old behavior;
- the new path uses only `case_id`, exact target INN and the one approved
  request profile;
- missing/partial/failed/complete/available-empty remain distinguishable and
  no partial slice is extrapolated;
- source monetary truth is exact `Decimal`, never binary float;
- A1 creates no calendar zero, A2/A3 counts and percentages reconcile, A4 is
  RUB-only claim price, and A5 is fully masked;
- raw identities/names/HMACs/URLs do not cross persistence/public/SSR/client/
  logs/telemetry/Claims boundaries;
- provider and public reads have zero side effects;
- all applicable targeted, repository and disposable-PostgreSQL checks pass;
- production defaults and H1 rollback behavior remain unchanged.

This decision permits specification and implementation planning. It does not
pre-approve the resulting implementation plan, code changes, provider traffic,
commit, push, merge, deploy or production activation.
