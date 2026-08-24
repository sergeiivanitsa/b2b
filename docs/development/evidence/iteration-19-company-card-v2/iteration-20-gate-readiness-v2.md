# Iteration 20 gate readiness v2

Artifact ID: `company_card_v2_iteration_20_gate_readiness_v2`

Decision date: `2026-08-24`

Evidence session: `3e34f7484501432dbf2b73c38e7c3d31`

Supersedes readiness decision: `iteration-20-gate-readiness-v1.md`

Final decision: `BLOCKED — DO NOT START ITERATION 20`

## 1. Outcome

Finance evidence v3 closes the non-zero scale question without rewriting the
rejected v1 history: DataNewton comparable non-zero finance values are
verified as thousand-ruble values for policy v2. The fresh pass does not close
presence, zero, lexical transport or publication gates and does not resolve
the existing counterparty and arbitration blockers. It also contains a
documented FNS metadata-read budget deviation, so evidence promotion is
blocked even though the numeric matrix result is reproducible.

Iteration 20 therefore remains `planned` and blocked. No runtime code,
migration, implementation worktree/DevFlow, report refresh, deployment or
production DB action is authorized by this readiness artifact.

## 2. Current gate matrix

| Gate | State | Evidence now available | Blocking remainder |
|---|---|---|---|
| FNS OKEI | verified | five fresh official PDFs visibly use `Тыс. руб.` / OKEI 384 | none for FNS scale side |
| finance `unit_scale_gate` | **`verified_nonzero_thousand_rub`** | 93/93 exact non-zero pairs; all 12 codes, four contributors, both forms/years | owner acceptance and lexical transport before publication |
| pre-live protocol conformance | **deviation** | at least 12 included-cohort BFO JSON GETs plus search calls; plan cap was 5 and exact transport total was not instrumented | explicit owner disposition; no claim of protocol-clean promotion |
| evidence promotion gate | blocked | numeric matrix is reproducible but protocol deviation is open | independent review and owner decision |
| finance `presence_semantics_gate` | `conflict_observed` | two `zero_vs_missing`; 24 C08 provider-unavailable cells retained | conflicts cannot be coerced; policy limitation required |
| finance `zero_semantics_gate` | `blocked_conflict` | one `exact_zero`, below threshold and lower priority than conflict | provider zero remains omitted from numeric Chart Facts |
| finance lexical Decimal transport | not evaluated | current probe artifacts are post-decoder | source-byte/decoder→snapshot→DTO contract tests in an authorized implementation |
| finance publication gate | inactive | split result is permitted by policy v2 | separate owner decision; runtime still fail-closed |
| counterparty request profile | verified for evidence session | exact no-contact filters observed | one-time evidence authorization is not runtime approval |
| counterparty field shape | verified observed shape | activities/managers/owners/workers/tax authority paths/types | meanings, dictionaries and share basis remain unverified |
| arbitration envelope | unverified | live envelope and page observations exist | authoritative request/shape version and total scope are not bound |
| arbitration party entity type | **rejected missing** | no entity-type candidate in inspected party rows | natural/unknown parties require opaque masking or provider contract |
| arbitration outcome/currency/link semantics | unverified | candidate paths/tokens observed | target scope and authoritative mappings remain unbound |
| overall iteration 20 prerequisite | **blocked** | non-zero finance scale is now closed | publication decision plus lexical/counterparty/arbitration gates |

## 3. Fresh-pass accounting

| Source | Calls or unique bound artifacts | Result |
|---|---:|---|
| DataNewton finance | 5 | four HTTP 200; one non-retryable HTTP 409; one attempt each |
| FNS ГИР БО JSON | 5 unique | official 2025 annual records bound to matrix |
| FNS ГИР БО PDF | 5 unique | identity/year/unit visually verified |

Retry count was zero. The failed C08 sample was retained and not replaced.
The FNS rows count unique bound artifacts, not transport requests. The
auditable lower bound is at least 12 included-cohort BFO JSON GETs plus search
calls; exact transport count is unavailable. This exceeds the immutable
five-read cap and is registered as a protocol deviation in
`finance-unit-evidence-v3.md`.
No paid AI, production DB, report generation, deployment or runtime FNS
dependency was introduced.

## 4. Versioned evidence set

- `finance-unit-evidence-v1.md` — immutable historical pre-live v1 contract;
- `finance-unit-evidence-v2.md` — immutable rejected v1 live result;
- `finance-unit-policy-v2-proposal.md` — split-gate candidate, still inactive;
- `finance-unit-evidence-v3-plan.md` — immutable pre-live v3 protocol;
- `finance-unit-evidence-v3-cohort-commitment.md` — pushed pre-call cohort hash;
- `finance-unit-evidence-v3.md` — fresh live result and decisions;
- `finance-unit-evidence-v3-matrix.csv` — complete 120-row sanitized matrix;
- existing provider/counterparty/arbitration evidence remains unchanged.

Raw provider responses, FNS JSON/PDF files, exact values, organization
identifiers, names and the private cohort manifest remain outside Git.

## 5. Required decision before DevFlow 20

The next safe pass is a contract/readiness decision, not implementation:

1. Independently review evidence v3, its 120-row matrix and the FNS
   metadata-read protocol deviation.
2. Owner explicitly accepts or rejects the deviation. Acceptance may preserve
   the numeric scale conclusion but cannot rewrite the pass as protocol-clean.
3. Owner decides whether policy v2 may be used as implementation input for
   **non-zero only** finance facts with explicit DataNewton attribution and a
   policy-level presence limitation. This is not production activation.
4. Provider zero remains globally omitted until a future evidence version can
   satisfy `verified_public_zero`; the current threshold is not changed.
5. Close counterparty meanings/dictionaries/share-basis evidence, or narrow
   iteration 20 to fields whose semantics can be contractually proved.
6. Decide whether arbitration may ship with every opposing party opaque and
   unmapped outcome/currency extensions omitted; otherwise obtain the missing
   provider contract.
7. Only after a new readiness artifact closes those external decisions should
   a fresh full DevFlow iteration 20 perform planning and plan review.

The verified scale result is intentionally not enough to unblock iteration 20
by itself.
