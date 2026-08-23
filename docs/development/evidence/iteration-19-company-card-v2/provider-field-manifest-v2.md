# Provider field manifest v2 — live observed counterparty shape

Artifact ID: `company_card_v2_provider_field_manifest_v2`

Public contract target: `company_public_h2_v1`

Evidence date: `2026-08-24`

Evidence session: `64fcf9bb84f045d5bd8652ecabdf2a81`

Overall provider-field gate: `UNVERIFIED / BLOCKED`

## 1. Decision

The authorized live pass closes the exact **observed schema** and request-profile
questions for the counterparty blocks needed by Company Card v2. It does not
silently promote key names into provider semantic guarantees.

```text
counterparty_request_profile_gate = verified
counterparty_schema_gate = verified for the exact paths in section 4
counterparty_privacy_gate = approved_transform / prohibited identifiers
evidence_collection_authorized = true for this evidence session only
counterparty_runtime_operational_gate = disabled
counterparty_semantic_gate = unverified
overall_provider_field_gate = BLOCKED
```

Iteration 20 may use these paths in fail-closed parsers and tests, but the
affected public fields remain omitted until their listed semantic gate is
closed. A feature flag cannot override a semantic or privacy gate.

## 2. Evidence-authorized request profile

Three pseudonymous Russian legal entities were queried once with this exact
filter set and retry disabled:

```text
MANAGER_BLOCK
ADDRESS_BLOCK
OWNER_BLOCK
OKVED_BLOCK
WORKERS_COUNT_BLOCK
```

`CONTACT_BLOCK` was not requested. Every call returned HTTP 200 on attempt 1.
Raw responses remain in a private RU-container path and were analyzed in place;
they were not copied into git or into this worktree.

This one-time authorization proves that the exact profile can be queried for
evidence. It is not approval for continuous runtime/production use, rollout,
automatic refresh or an operational quota policy. Those remain disabled until
the owning implementation and rollout decisions pass.

| Pseudonym | Received at (UTC) | Private raw SHA-256 |
|---|---|---|
| `C01` | `2026-08-23T14:21:51.832741Z` | `66ddb1fe479a154f42c5ae816c5c6dd466065e5c2ba14a62c9963ce7ad341a69` |
| `C02` | `2026-08-23T14:22:04.666834Z` | `02315a1b909c4e8da4aa8014f4f60c5d1646d635dffd52961613af18e6ef42b3` |
| `C03` | `2026-08-23T14:22:15.874364Z` | `8045ea422e230ba9eda716b2fbeb0cad2648c14f161e9f0176d9b10570a27e05` |

The first three broader probes used the deployed default
`MANAGER_BLOCK,ADDRESS_BLOCK` profile and therefore returned empty owner/OKVED/
worker blocks. They are not used to claim absence. The extended profile above
is the authoritative v2 schema observation.

## 3. Sanitization boundary

Only paths, JSON types, cardinalities, timestamps and hashes are tracked.
Company names, identifiers, personal names, shares, capital, activity labels,
department labels and all contact values are absent.

These source leaves are explicitly prohibited from public DTO, SSR, embedded
JSON, AI input/output, telemetry and logs:

```text
$.company.managers[].innfl
$.company.owners.fl[].inn
$.company.owners.ul_rus[].inn
```

An observed `null` at `$.company.contacts` means only “not requested/returned
under this filter profile”; it is not evidence that the company has no
contacts.

## 4. Live schema bindings

### 4.1. Status, form, capital and tax modes

| Public concern | Exact observed path | Live type/cardinality | Schema | Semantic/public decision |
|---|---|---|---|---|
| status root | `$.company.status` | object, 1/response | verified | closed state catalog and effective date remain unverified; omit |
| active candidate | `$.company.status.active_status` | boolean, 1/response | verified | does not by itself establish dated legal status |
| status code | `$.company.status.code_egr` | string, 1/response | verified | raw code not public until closed mapping |
| status labels | `$.company.status.{status_egr,status_rus_short,status_eng_short}` | strings, 1 each | verified | provider free text not passed through |
| status end date | `$.company.status.date_end` | string, 1/response | verified | not substituted for the report/status date |
| legal form | `$.company.opf` | string, 1/response | verified | dictionary semantics unverified; omit |
| charter capital | `$.company.charter_capital` | string, 1/response | verified | lexical transport, scale/currency and reference date unverified; omit |
| tax modes | `$.company.tax_mode_info` | object, 1/response | verified | boolean scope/effective semantics unverified; omit |
| tax-mode flags | `common_mode`, `usn_sign`, `ausn_sign`, `envd_sign`, `eshn_sign`, `npd_sign`, `psn_sign`, `srp_sign` | boolean, 1 each/response | verified | missing is unknown, never false |
| tax-mode publication date | `$.company.tax_mode_info.publication_date` | string, 1/response | verified | exact publication/effective semantics unverified |

### 4.2. Activities

`$.company.okveds` was an array in all three responses. Observed row counts were
6, 92 and 56; cardinality is therefore not safely bounded by the provider and
the public cap/sort must be deterministic.

| Leaf | Type/presence | Schema | Semantic/public decision |
|---|---|---|---|
| `$.company.okveds[].code` | string on every observed row | verified | exact code candidate; semantic gate pending |
| `$.company.okveds[].value` | string on every observed row | verified | bounded safe label only after semantic gate |
| `$.company.okveds[].main` | boolean on every observed row | verified | primary/additional meaning not inferred solely from the key name |
| `$.company.okveds[].mode` | string on every observed row | verified | raw token hidden until a closed catalog exists |

No array order is treated as primary status. Missing/invalid `code`, `value` or
`main` makes the row ineligible; it is never repaired from another row.

### 4.3. Managers

All three responses contained one manager object at
`$.company.managers[]`. These exact leaves were present with stable types:

| Leaf | Type | Public/privacy rule |
|---|---|---|
| `fio` | string | safe bounded name only after role/scope semantic gate |
| `position` | string | closed safe role label only; raw unknown role hidden |
| `date` | string | validated date or null after scope gate |
| `is_inaccuracy` | boolean | missing remains unknown |
| `innfl` | string | prohibited and discarded before public projection |

Schema is verified; manager role/scope semantics remain unverified.

### 4.4. Owners

`$.company.owners` was an object in every response. The live union observed two
category paths:

```text
$.company.owners.fl[]
$.company.owners.ul_rus[]
```

`C01` and `C03` populated the first path; `C02` populated the second. Each
observed owner row contained `name` (string), `share` (string),
`captable_size` (number), `date` (string), `information_limited` (boolean) and
`inn` (string). Natural-person rows additionally exposed boolean
`disqualified_person` and `mass_owner` candidates.

The paths/types are schema-verified. The category meanings, share scale/basis,
effective-date scope and safe public name policy are not proven by live shape
alone. Owner rows therefore remain hidden; `inn` is prohibited regardless of
future activation. Owner type must never be inferred from a name or identifier
length.

### 4.5. Workers and tax authority

| Concern | Exact observed path | Observation | Decision |
|---|---|---|---|
| workers root | `$.company.workers_count` | object in all three responses | schema verified |
| workers value | `$.company.workers_count.<year>` | integer years 2018–2025 in C01; empty objects in C02/C03 | year→headcount semantics and empty-object meaning unverified; omit, never zero-fill |
| authority root | `$.company.uchet_department` | object, 1/response | schema verified |
| authority code | `$.company.uchet_department.department_code` | string, 1/response | internal candidate only |
| authority label | `$.company.uchet_department.department_name` | string, 1/response | bounded label after scope gate |
| authority date | `$.company.uchet_department.uchet_date` | string, 1/response | validated date after semantic gate |

## 5. Finance and arbitration handoff

- Finance path/schema is live-observed for `$.balances` and `$.fin_results`,
  but the v2 matrix rejects `datanewton_finance_thousand_rub_v1`; see
  `finance-unit-evidence-v2.md`.
- Arbitration live schema/pagination evidence is recorded separately in
  `arbitration-contract-evidence-v2.md`.
- Source-byte lexical Decimal transport is not proven by these post-decoder
  files and remains owned by iteration 20 implementation/tests if that
  iteration is later unblocked.

## 6. Why the overall gate remains blocked

The exact observed paths are now sufficient to write fail-closed parser tests,
but live response shape is not an authoritative semantic dictionary. Attempts
to read the provider OpenAPI endpoint, including with the protected key inside
the RU container, returned HTTP 403. No versioned provider schema/document was
available to bind the remaining meanings.

Before public activation, a new evidence pass must bind at least:

1. `okveds[].main`, `value` and `mode` semantics;
2. owner category meanings and exact share basis/unit;
3. worker year/value and empty-object semantics;
4. manager role/scope;
5. tax-mode publication/effective scope;
6. tax-authority scope and reference date;
7. legal-form/status dictionaries and charter-capital scale.

Until then, these fields are represented by explicit limitations rather than
invented values. The exact no-contact profile is verified for this evidence
session and the privacy transforms are approved, but runtime operation remains
disabled and neither can override the semantic gate.
