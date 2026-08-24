# Owner decision: narrowed iteration 20 scope v1

Artifact ID: `company_card_v2_iteration_20_owner_scope_decision_v1`

Decision date: `2026-08-24`

Repository base: `806005f30e4cea888455fb7f7d1e129681ecc037`

State: `APPROVED FOR DEVFLOW 20 PLANNING`

Production activation: `NOT AUTHORIZED`

## 1. Decision

The owner accepts a narrowed, fail-closed iteration 20 instead of waiting for
every external DataNewton semantic dictionary. This is an explicit versioned
scope decision; it does not rewrite iteration 19 evidence, convert an
unverified field to verified, or authorize a production provider request.

Iteration 20 may implement the v3 persistence/API foundation and parsers for
observed shapes. A fact whose semantic, privacy or operational gate remains
open must be `null`/hidden with a machine-readable limitation. The iteration
is not required to make all proposed Company Card v2 content visible.

```text
iteration_20_planning = ready
iteration_20_scope = narrowed_fail_closed_v1
company_card_v2_feature_default = off
production_provider_operation = disabled
production_publication = disabled
```

## 2. Finance decision

The owner accepts `deviation_fns_metadata_read_budget` as non-material to the
numeric scale conclusion because the cohort/order/provider calls never
changed, no replacement occurred, and the comparator used only the five
hashed FNS JSON/PDF pairs. The deviation remains permanently disclosed; the
pass is never relabelled protocol-clean.

```text
datanewton_finance_policy = datanewton_finance_thousand_rub_v2
unit_scale_gate = verified_nonzero_thousand_rub
evidence_promotion = accepted_with_disclosed_protocol_deviation
presence_semantics_gate = conflict_observed
zero_semantics_gate = blocked_conflict
provider_nonzero = approved implementation input
provider_zero = prohibited numeric/public input
provider_missing = gap, never zero
```

Iteration 20 owns the still-unverified
`lexical_decimal_transport_gate`. Before that gate passes, every finance
numeric Chart Fact remains unavailable even when non-zero. Required tests must
prove source lexeme/string → `Decimal` → normalized fact → immutable snapshot
→ Chart Facts → JSON DTO without float truth, hidden rounding or loss of sign
and precision.

After the lexical gate passes, only explicit provider non-zero values may be
projected as DataNewton-attributed thousand-ruble facts. Provider zero remains
`zero_unverified`, is omitted from numeric geometry/display and produces the
policy-level limitation. This decision does not approve zero publication and
does not change the precommitted public-zero threshold.

## 3. Counterparty boundary

Iteration 20 may reuse the approved H1/core mapping for:

- full/short legal name;
- exact subject INN, OGRN/OGRNIP and KPP;
- valid registration/dissolution dates;
- existing approved address fields and address-inaccuracy behavior.

The observed v2 counterparty request profile and paths may be implemented as
strict fail-closed parsers/fixtures, but these fields remain hidden from the
public H2 projection because their semantic gates are open:

- status/effective date and legal form;
- charter capital and tax modes;
- OKVED/activity rows and primary flag;
- managers and their provider role/date scope;
- owners, owner type, share and effective date;
- employee counts;
- tax authority.

This explicitly defers the desired visible manager/owner/activity/worker/tax
authority content. Parser presence is not publication approval. Contacts are
still neither requested nor published. Personal identifiers such as manager
`innfl` and owner `inn` are discarded before any public/AI/telemetry boundary.

No runtime DataNewton counterparty profile is enabled by this decision. A
future version may expose an individual field only after its own tracked
semantic and operational gate passes.

## 4. Arbitration boundary

Iteration 20 may implement and test the algorithmic foundation entirely with
sanitized fixtures:

- pre-call registry checks that refuse network access when the authoritative
  envelope/shape binding is absent or stale;
- page size/cap, drift, overlap, non-progress and byte-cap protections;
- deterministic canonical dedup and conflict exclusion;
- immutable safe provenance/counters without raw pages;
- exact target-INN role attribution, with multiple roles classified `other`;
- report-scoped opaque masking primitives and privacy scanners;
- complete/partial/gate-closed states without extrapolation.

The current provider envelope gate remains closed, so iteration 20 does not
perform live/runtime arbitration collection. Public H2 must return all five
arbitration views `A1..A5` as unavailable/gate-closed with limitations. It may
not publish or infer:

- complete case totals or calendar zeroes;
- case year semantics;
- `party_result` outcome meaning;
- amounts or currency labels/groups;
- opposing-party names or entity types;
- visible case number, instances/courts or KAD links.

All opposing parties are treated as unknown for public-name purposes. No name,
INN, OGRN, provider case key or identifier-bearing URL crosses the public
boundary. Iteration 24 remains blocked until its original
completeness/outcome/currency/entity-type/privacy prerequisites are closed.

## 5. Required iteration 20 deliverables

DevFlow 20 planning may cover only:

1. Explicit v1/v2/v3 read compatibility and default-off v3 write fencing.
2. Immutable v3 persistence, projection digest and H2 pin/assignment
   foundation without activation.
3. Closed public H2 DTO/API lifecycle with null/gate-closed states and
   zero-side-effect GET/HEAD behavior.
4. Exact lexical Decimal transport and the approved non-zero-only finance
   policy path.
5. Fail-closed counterparty parsers for observed shapes, with only existing
   core identity/address visible.
6. Fixture-driven arbitration bounds/dedup/role/masking foundation whose
   pre-call registry blocks real collection.
7. Claims exact-report compatibility, privacy scanning, old-snapshot tests and
   disposable PostgreSQL integration coverage.

Every implementation surface stays behind a default-off Company Card v2
feature/write profile. H1 remains the production resolver and rollback path.

## 6. Explicitly out of scope

- Production deploy, DB migration execution on production, backfill or report
  refresh.
- Live DataNewton/FNS/Gateway/AI calls during DevFlow implementation/tests.
- Production runtime enablement of the extended counterparty profile or
  arbitration pagination.
- Visible counterparty fields listed as hidden in section 3.
- Provider-zero finance publication.
- Public A1–A5 arbitration facts, amounts, outcomes, currencies, party names or
  links.
- React page/charts, AI narrative and presentation assignment activation.
- Changes to H1 signals, scoring or Claims semantics.

## 7. Acceptance boundary

Iteration 20 can be `READY` only when independent review confirms:

- no open evidence gate is bypassed by a feature flag or optimistic fallback;
- unavailable differs from missing and missing differs from zero;
- source numeric truth is exact `Decimal`, never `float`;
- public DTO recursively rejects raw/unknown/private fields;
- read paths perform no provider, worker, AI, queue or DB write;
- v1/v2 snapshots and H1 routes remain byte/semantic compatible where
  contracted;
- v3 write/public feature gates are off by default;
- arbitration pre-call gate blocks network while the registry is unverified;
- all required unit, integration and disposable-PostgreSQL checks pass.

This decision makes iteration 20 eligible for full DevFlow planning and plan
review. It does not pre-approve an implementation plan, commit, merge or
production activation.
