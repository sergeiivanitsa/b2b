# Iteration 20 gate readiness v1

Artifact ID: `company_card_v2_iteration_20_gate_readiness_v1`

Decision date: `2026-08-24`

Base commit: `205f34a`

Evidence session: `64fcf9bb84f045d5bd8652ecabdf2a81`

Final decision: `BLOCKED — DO NOT START ITERATION 20`

## 1. Outcome

The authorized evidence pass produced useful live bindings but did not satisfy
the Roadmap prerequisite “closed finance-unit and provider-field evidence/
schema gates.” Iteration 20 therefore stays `planned` with an explicit blocker;
no runtime code, migration, worktree for implementation, DevFlow iteration,
deploy or production database action is authorized by this artifact.

## 2. Gate matrix

| Gate | State | What is now known | Blocking remainder |
|---|---|---|---|
| FNS OKEI | verified | all three official PDFs explicitly use thousand rubles; controlled OKEI mapping is 384 | none for FNS side |
| DataNewton non-zero finance scale | strong exact evidence, not independently activatable | 69/69 comparable non-zero cells match FNS exactly | atomic policy includes missing/zero semantics |
| `datanewton_finance_thousand_rub_v1` | **rejected** | 72-cell matrix complete | two `zero` vs `missing` mismatches for `C02/balance/1240/2024–2025` |
| finance lexical Decimal transport | unverified, implementation-owned | current files are post-decoder | iteration 20 source-byte parser/tests, after unblock |
| counterparty evidence request profile | verified for this session | exact manager/address/owner/OKVED/workers filters; no contact filter | one-time evidence authorization is not runtime approval |
| counterparty runtime operational gate | disabled | no production/runtime authorization was inferred | implementation, quota and rollout decision required |
| counterparty field schema | verified observed shape | exact paths/types for activities, managers, owners, workers, tax authority, status/form/tax modes | meanings/dictionaries/share basis still unverified |
| counterparty privacy | approved transform | personal identifiers prohibited; contacts excluded | public names/roles still depend on semantics |
| arbitration envelope | unverified; live path/type observation only | `data`, `total_cases`, `offset`, `limit`; second-page total/offset stability and no overlap | authoritative request/shape version and `total_scope` are not bound; pre-call gate remains closed |
| arbitration field schema | verified observed shape | case IDs, visible-number candidate, dates, outcome, currency, instances and KAD candidate | business meanings/catalogs remain unverified |
| arbitration entity type | **rejected missing** | no entity-type candidate in 1,678 inspected party rows | legal/state names cannot be distinguished from natural/unknown; opaque mask only |
| arbitration outcome/currency/link semantics | unverified | live paths and token shapes known | target scope, currency mapping and case-link meaning not bound |
| overall iteration 20 prerequisite | **blocked** | evidence is versioned and reproducible | finance policy rejection plus provider semantic gaps |

## 3. Request and data budget actually used

| Source/dataset | Calls or reads | Result |
|---|---:|---|
| DataNewton finance | 3 | HTTP 200, attempt 1 each; approved maximum of 5 not exceeded |
| DataNewton counterparty, deployed default profile | 3 | HTTP 200; used only to diagnose missing requested blocks |
| DataNewton counterparty, exact extended no-contact profile | 3 | HTTP 200, attempt 1 each |
| DataNewton arbitration first page | 3 | HTTP 200, attempt 1 each |
| DataNewton arbitration page at offset 100 | 2 | HTTP 200, attempt 1 each |
| FNS ГИР БО JSON | 3 public reads | official 2025 records |
| FNS ГИР БО PDF | 3 public reads | visually verified identity/year/unit |

No paid AI, production DB, report refresh/backfill, deployment or public
publication was performed. The finance budget is counted independently exactly
as the immutable v1 policy requires.

## 4. Versioned evidence set

- `finance-unit-evidence-v1.md` — immutable pre-live contract and rules;
- `finance-unit-evidence-v2.md` — 72-row sanitized live matrix and rejection;
- `provider-field-manifest-v1.md` — immutable local-only baseline;
- `provider-field-manifest-v2.md` — live counterparty paths/types and gaps;
- `arbitration-contract-evidence-v1.md` — immutable pre-live contract;
- `arbitration-contract-evidence-v2.md` — five-page live envelope/field/privacy evidence.

Raw files, PDFs and the pseudonym↔identifier map remain outside tracked paths.
The three v1 files were not edited.

## 5. Recommended next decision pass

The first docs-only part of the recommended pass is now prepared:

- `finance-unit-policy-v2-proposal.md` separates non-zero scale proof from
  presence, zero, lexical transport and publication gates;
- `finance-unit-evidence-v3-plan.md` freezes the next fresh-matrix protocol
  before any values are observed;
- both artifacts are proposals only: no new live call has been executed and
  `datanewton_finance_thousand_rub_v2` is inactive.

The remaining safe route before DevFlow 20 is:

1. Review and explicitly approve or amend the proposed finance policy and the
   pre-live matrix plan, including the future exact-zero threshold.
2. Only after approval, execute the fresh predetermined matrix. Do not discard
   the current failed company or cherry-pick only passing cells.
3. Obtain a versioned DataNewton schema/dictionary from the provider, or approve
   a separate controlled FNS ЕГРЮЛ comparison for OKVED/manager/owner/worker/
   tax-authority semantics. Live field names alone remain insufficient.
4. Decide whether arbitration v1 may safely ship with every opposing party
   masked and non-ISO currency/outcome extensions omitted. If not, require a
   provider entity-type and currency/outcome contract before iteration 20.
5. Only after those decisions produce closed external gates, update this
   readiness record in a new version and start a fresh full DevFlow iteration
   20 with its own specification, plan and independent plan review.

The recommended finance design is to preserve exact provider facts, record the
two cells as conflicts, omit conflicted cells from chart inputs and keep the
unit-scale decision separate. This is a proposal, not an approved contract
change.
