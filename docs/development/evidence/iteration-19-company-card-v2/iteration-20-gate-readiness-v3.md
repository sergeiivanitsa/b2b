# Iteration 20 gate readiness v3

Artifact ID: `company_card_v2_iteration_20_gate_readiness_v3`

Decision date: `2026-08-24`

Base commit: `806005f30e4cea888455fb7f7d1e129681ecc037`

Owner decision:
`docs/development/decisions/iteration-20-owner-scope-decision-v1.md`

Supersedes start decision: `iteration-20-gate-readiness-v2.md`

Final decision: `READY FOR FULL DEVFLOW 20 PLANNING — NARROWED SCOPE`

Production activation: `BLOCKED`

## 1. Why planning is now allowed

Readiness v2 correctly blocked the original broad iteration 20 because it
required unverified counterparty and arbitration semantics and an unresolved
finance evidence deviation. The owner has now made two explicit decisions:

1. accept the disclosed FNS metadata-read deviation for the reproducible
   non-zero finance scale conclusion, without calling the pass protocol-clean;
2. narrow iteration 20 so every still-unverified external fact is hidden and
   cannot block implementation of the versioned backend foundation.

This removes the contradiction between Roadmap scope and current evidence. It
does not close the underlying field gates.

## 2. Gate disposition

| Surface | State for iteration 20 | Public/runtime consequence |
|---|---|---|
| Finance non-zero scale | approved implementation input with disclosed deviation | usable only after lexical Decimal gate passes |
| Finance presence | `conflict_observed` | policy-level limitation required |
| Finance zero | `blocked_conflict` | zero omitted from numeric facts/geometry |
| Finance lexical transport | implementation-owned gate | all numeric finance unavailable until tested/verified |
| Existing identity/address | approved H1/core contract | may be projected with v3 compatibility tests |
| New counterparty fields | schema-observed, semantics unverified | strict parser allowed; public field hidden/gate-closed |
| Contacts/personal identifiers | prohibited | neither requested nor emitted |
| Arbitration algorithms/privacy | implementation-owned from closed contract | sanitized fixture implementation allowed |
| Arbitration provider envelope | unverified | pre-call registry must refuse network |
| Arbitration A1–A5 semantics | unverified/blocked | every view null/gate-closed |
| H2 production assignment | not authorized | H1 remains production default |

## 3. Iteration boundaries

Iteration 20 may finish with unavailable/gate-closed counterparty and
arbitration fields. This is an intentional owner-approved scope, not a claim
that those datasets are empty. The backend must make those states explicit in
coverage and limitations.

Downstream status:

- iteration 21 remains dependent on merged iteration 20 and may consume only
  the safe factual envelope actually produced;
- iteration 22 remains dependent on iterations 20–21 and renders unavailable
  sections honestly;
- iteration 23 may start only after iteration 20 verifies lexical Decimal
  transport and exposes the approved non-zero-only Chart Facts contract;
- iteration 24 remains blocked by arbitration completeness/outcome/currency/
  entity-type/privacy gates;
- iteration 25 remains the only place where an owner may authorize staged H2
  production assignment.

## 4. Required DevFlow controls

The next action is a normal full `$devflow` iteration 20:

1. planner reads the iteration 19 contract, all evidence v1–v3, this readiness
   artifact and the owner decision;
2. plan reviewer must reject any attempt to publish a gated field, perform
   live/paid calls, start frontend/AI work or activate production;
3. implementation includes tests and migrations only when schema changes are
   intentionally planned;
4. disposable PostgreSQL is mandatory for affected persistence/API tests;
5. independent code review must return `VERDICT: READY` before feature-branch
   commit/push; PR and merge remain manual.

No further live evidence call is required before DevFlow 20 planning under
this narrowed scope.
