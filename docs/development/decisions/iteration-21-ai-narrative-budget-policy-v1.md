# Owner decision: iteration 21 AI narrative budget policy v1

Artifact ID: `company_card_v2_ai_narrative_budget_policy_v1`

Decision date: `2026-08-24`

Repository base: `f4fe88e51f89a85cbd3c8881affbb8b0b87fbe6c`

State: `APPROVED FOR DEVFLOW 21 PLANNING`

Production activation and paid smoke: `NOT AUTHORIZED`

## 1. Budget unit

The authorization unit is one integer `dispatch_credit`. One durable budget
reservation consumes exactly one credit and permits at most one paid model
dispatch for one exact immutable narrative generation key.

Provider token counts, reported usage dictionaries, currency prices and model
cost estimates are observability only. They are not authorization truth and
cannot create or restore budget.

## 2. Periods and limits

Daily and monthly windows use `Europe/Moscow` calendar boundaries:

```text
daily   = [local 00:00, next local 00:00)
monthly = [first local day 00:00, first local day of next month 00:00)
```

Daily limit, monthly limit and worker concurrency are explicit non-negative
configuration values. Their repository defaults are `0`, meaning disabled.
Iteration 21 does not invent positive production thresholds. Enabling the kill
switch without explicit positive limits and concurrency must fail closed.

Tests may inject small positive values, but those are fixtures and not product
or production defaults.

## 3. Reservation and dispatch rules

1. Reserve one credit transactionally before any external call.
2. A reservation is unique for the complete immutable generation key.
3. Enter durable `dispatching` before sending the Gateway request.
4. One reservation can cross the Gateway boundary at most once.
5. A definitive pre-dispatch failure may release the reservation and reschedule
   locally without a model call.
6. Timeout, worker death, lost response or any state after dispatch began is
   ambiguous and is never retried automatically.
7. Ambiguous, invalid, stale, schema-failed or policy-failed work resolves to
   the deterministic fallback without another AI call.
8. Fallback generation and public reads consume no dispatch credit.
9. Daily and monthly counters are durable and transactionally checked together
   with the reservation; process-local counters are forbidden.
10. Limits are never inferred from Gateway/OpenAI response usage.

## 4. Safety boundary

- The narrative worker and feature are default-off.
- Public GET/HEAD/SSR/crawler/React paths never enqueue work, reserve budget or
  call Gateway.
- No paid AI or controlled smoke is part of this DevFlow run.
- Product API never receives an OpenAI key; only the isolated Gateway may own
  it.
- No production deploy, runtime flag change or H2 publication assignment is
  authorized.

## 5. Chart comments during iteration 21

The contract permits zero to two comments, but runtime-visible chart bindings
do not exist before the later chart iterations. Iteration 21 therefore emits
zero runtime chart comments. It implements closed validation for comments only
through sanitized pure fixtures; any reference to a hidden or unsupported chart
fails closed.

This decision supplies operational planning inputs. It does not approve a
specific schema, migration or implementation plan; those require independent
DevFlow plan review.
