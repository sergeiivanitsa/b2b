# Finance unit evidence v3 — fresh DataNewton/FNS matrix

Artifact ID: `company_card_v2_finance_unit_evidence_v3`

Evidence session: `3e34f7484501432dbf2b73c38e7c3d31`

Evidence date: `2026-08-24` (Asia/Vladivostok)

Policy under test: `datanewton_finance_thousand_rub_v2`

Pre-call commitment commit:
`32146f0148af25f5d5b2059e7698bf1556594a7b`

Result:

```text
unit_scale_gate = verified_nonzero_thousand_rub
presence_semantics_gate = conflict_observed
zero_semantics_gate = blocked_conflict
lexical_decimal_transport_gate = not_evaluated
pre_live_protocol_conformance = deviation_fns_metadata_read_budget
evidence_promotion_gate = blocked_protocol_deviation
publication_gate = inactive_owner_decision_required
iteration_20 = BLOCKED
```

## 1. Atomic result

Fresh cohort `C04..C08` was fixed and pushed before the first provider call.
The pass emitted all 120 expected rows: five samples, both forms, twelve exact
line codes and reporting years 2024–2025. Failed sample `C08` was neither
retried nor replaced.

| Outcome | Count |
|---|---:|
| `exact_nonzero` | 93 |
| `not_comparable` | 3 |
| `unavailable` | 24 |
| Total | 120 |

Presence outcomes are independent from scale:

| Presence outcome | Count |
|---|---:|
| `both_nonzero` | 93 |
| `exact_zero` | 1 |
| `zero_vs_missing` | 2 |
| `unavailable_provider` | 24 |
| Total | 120 |

All 93 comparable non-zero pairs matched exactly after direct OKEI-384
normalization. There were no `scale_mismatch`, `rejected_okei`, mixed-scale,
unequal-duplicate or shape-error outcomes. Distributed coverage therefore
satisfies every scale criterion from policy v2 even though one source artifact
was unavailable.

This numeric result is not a claim of complete pre-live protocol compliance.
The FNS metadata transport budget was exceeded and was not fully instrumented,
as recorded in section 2. Consequently evidence promotion remains blocked
pending an explicit decision on this deviation; the policy stays inactive.

The two conflicts are retained, not coerced:

| Sample | Form | Code | Year | DataNewton | FNS | Outcome |
|---|---|---:|---:|---|---|---|
| `C07` | `balance` | `1240` | 2024 | `zero` | `missing` | `zero_vs_missing` |
| `C07` | `balance` | `1240` | 2025 | `zero` | `missing` | `zero_vs_missing` |

The single aligned zero is `C05/balance/1240/2025`. It does not meet the
precommitted public-zero threshold and cannot override the higher-priority
presence conflict. Provider zeros remain `zero_unverified` and are not
eligible for numeric Chart Facts.

## 2. Authorization, commitment and call accounting

The owner separately authorized the live pass, DataNewton quota use and public
FNS reads. The private canonical cohort manifest was committed by hash before
any included provider response was observed:

```text
cohort commitment SHA-256 = 2870e8e1ade3f0b1237993ee4cc6bac94387078a2892cd4293c4682411de4a89
pre-call pushed commit = 32146f0148af25f5d5b2059e7698bf1556594a7b
ordered samples = C04,C05,C06,C07,C08
retry count = 0
```

| Source artifact/call set | Planned | Bound/completed | Successful | Failed |
|---|---:|---:|---:|---:|
| DataNewton `GET /v1/finance` | 5 | 5 | 4 | 1 |
| Unique FNS ГИР БО JSON artifacts | 5 | 5 | 5 | 0 |
| Unique FNS ГИР БО official PDFs | 5 | 5 | 5 | 0 |

Each provider call used `DATANEWTON_RETRY_COUNT=0` and exactly one attempt.
`C08` received HTTP 409 with safe type `DataNewtonValidationError` and
`retryable=false`. The closed pre-live catalog has no generic HTTP-rejection
state. It is recorded as `billing_ambiguous`: this means only that a completed
provider rejection cannot safely prove data absence or quota/billing
disposition. It does **not** assert that billing occurred. Its 24 expected
cells remain `not_observed/unavailable_provider`, with no raw or shape hash.

### 2.1. Pre-live protocol deviation: FNS metadata reads

The immutable plan said “up to five JSON metadata reads”. Execution did not
meet that bound:

- cohort selection required at least one BFO metadata GET for each of C04–C08;
- after commitment, the BFO metadata endpoint was read twice more for C04
  during schema-only inspection;
- the five exact JSON artifacts later bound by hash to the comparator were
  downloaded once each;
- selection also used public search calls, and the total FNS transport count
  was not instrumented.

Therefore the auditable lower bound is **at least 12 included-cohort BFO JSON
GETs**, plus selection search calls; the exact total is unavailable. This is
`deviation_fns_metadata_read_budget`, not compliance with the five-read cap.
The table above reports the unique value-bearing artifact set and must not be
read as the HTTP GET count.

Impact assessment:

- no DataNewton call, retry, sample, order or request profile changed;
- no additional company/document entered the comparator after commitment;
- schema-only rereads did not inspect included finance line values;
- all comparisons use exactly the five hashed JSON/PDF pairs listed below;
- repeated reads of the same public metadata do not change the 120 row
  arithmetic or distributed scale coverage;
- nevertheless the evidence package cannot claim full pre-live protocol
  conformance, and promotion remains blocked until the owner explicitly
  accepts or rejects this deviation after independent review.

No production DB, report generation/refresh, deployment, paid AI, contact
collection or iteration 20 runtime work was performed.

## 3. Official unit and source binding

Every official PDF was visually inspected. All five show the exact unit label
`Тыс. руб.`. The controlled mapping remains OKEI 384 from the official Rosstat
[OKEI open dataset](https://rosstat.gov.ru/opendata/7708234640-okei). All
matrix rows therefore use:

```text
fns_okei_state = accepted_384
fns_okei_code = 384
fns_normalization = direct_thousand
```

The following hashes bind tracked pseudonyms to the exact private artifacts;
identifier-bearing locators and exact monetary values stay outside Git.

| Sample | Provider raw SHA-256 | Provider shape SHA-256 | FNS JSON SHA-256 | Official PDF SHA-256 |
|---|---|---|---|---|
| `C04` | `11a9170d8a6cb72655f236c0a57b37158578a4849a27436d541cd179f900cce3` | `a37ddf05df8a3dda9326839bee2a73352cb6adbc3e1f0f997b167a2dcda11f01` | `e0ed9ed4197fb0756aeebf09584a7ebfa8485ae8046b45146a3870ceb68c2ddd` | `fbe60d7b9f4087bce612e1422e2b106bf0c67fadb933c69a20e641cbea083b1c` |
| `C05` | `d61a3fc8cf51e871f7f6d0a7651277e1f388aab3ff3b1eb69f1be0a3a603ce54` | `54a91ba78c4c3f09223e70718a53959b44e5d2ad47161f1c40e3f096b44537ca` | `1020ebc88f9b3adaf8ac204137becad97860beca8be4afada9c1016492899b94` | `50bcaa332096c7b33cb502bb632659c8a7b37168360f59426b5a0dbe91668c09` |
| `C06` | `148f7818b8088785d42bab606636015596d0455d769e55d2dbcced24cfeda9ec` | `6c31a8601fc27aebfd8b7d57e2e9ef4f5fdc92a15ec98e7b0f9ca26f84370146` | `86626e70104883268e82102429bd13977276e4fa5b4290c342a228013c672ee3` | `1bfb6d4a01b870ba8e42a01c443f77cec48d7182f58923ce093b45965b24a7ed` |
| `C07` | `4a70f79197417bd75f486296cedd16c923cd8ff1ff7c531cd8874e955726d69e` | `54a91ba78c4c3f09223e70718a53959b44e5d2ad47161f1c40e3f096b44537ca` | `a80346345d9ec1c2f11304f018923207fe89d392945277fb6fcaa4c9c2df3abc` | `f74739abbd663c3cacde1b8d9a70bff60e927713af2a7c5d2146c0294dbe6106` |
| `C08` | unavailable | unavailable | `968929d173dcf241ab5f449e098409d0e105ea90c28a8ef87368739202906e30` | `47711e9ab73ba5ab3f0b40cff2a1141f9a76e4e898da1072944c3f137c4da411` |

Provider response hashes are:

| Sample | Run ID | Response hash | Attempts/result |
|---|---|---|---|
| `C04` | `20260824T003210Z_ae15010e41d3` | `59c5b7812126e26d8a50eae19877fd284080c12e15c004eff4dfe85fd2dcd7a1` | 1 / HTTP 200 |
| `C05` | `20260824T003224Z_d09a8ddee601` | `ff848ca6adbf64de6a802fd330a0773031998b06a7cdf386b7b9d34572051ce2` | 1 / HTTP 200 |
| `C06` | `20260824T003247Z_b8b341318096` | `7975e41055b942272fa7f0527eb3a3cadabc276cb170ee77a1061a602c3d00a8` | 1 / HTTP 200 |
| `C07` | `20260824T003324Z_d46fa6de66cc` | `aff1f0f3c9adc309b40f39b5a1ecabc87687ab584b46c91ad5c2b80a2bbe8c1c` | 1 / HTTP 200 |
| `C08` | `20260824T003340Z_61aed0707719` | unavailable | 1 / HTTP 409 |

## 4. Scale coverage audit

| Criterion from policy v2 | Result | Evidence |
|---|---|---|
| every comparable non-zero pair matches exactly | PASS | 93 of 93 |
| every one of 12 codes has proof from at least two companies | PASS | code 1240: 3; all other codes: 4 |
| at least three proof-contributing companies | PASS | C04–C07 |
| both forms and both year positions | PASS | balance/financial_results; 2024/2025 |
| no company contributes over half of proof cells | PASS | C04=24, C05=23, C06=24, C07=22 of 93 |
| no mixed scale, undocumented transform or shape drift | PASS | none observed |
| all zero/missing/unavailable outcomes retained | PASS | 120-row matrix |

The unavailable C08 cells do not prove scale. They also do not fail scale by
the precommitted split-gate rule because C04–C07 independently satisfy every
distributed coverage requirement. Unavailability does prevent a verified
presence gate and is retained in addition to the higher-priority observed
conflict.

## 5. Collector binding and full matrix

`provider_shape_version=datanewton_finance_2026-08-23_shape_v2` retains the
same endpoint, form roots, exact codes and structural binding as evidence v2.
`collection_tool_version=company-card-v2-finance-matrix-v3` applies that closed
algorithm and emits the expanded v3 availability/outcome fields:

1. JSON numbers are decoded using `Decimal`; booleans, non-finite values and
   unsupported scalars fail classification.
2. Only `$.balances` and `$.fin_results` are traversed for exact sibling
   `code`/`sum` objects and years 2024–2025.
3. Equal duplicate representations in `childrenMap` and `indicators` collapse
   to one cell; this is the existing v2 rule that only **unequal** duplicates
   are conflicts. No unequal duplicate was observed.
4. FNS values come only from the selected 2025 annual correction:
   `current<code>` for 2025 and `previous<code>` for 2024.
5. Exact Decimal comparison uses no tolerance, rounding, interpolation,
   float conversion or missing/zero coercion.
6. Every expected cell is emitted in deterministic sample/form/code/year
   order, including all 24 unavailable C08 cells.

An initial private executable incorrectly rejected equal duplicate balance
representations. It made no provider or FNS request and was not used as
evidence. The implementation was corrected to the already frozen v2 rule and
rerun solely against the same immutable input hashes.

The complete 120-row sanitized matrix is stored in
`finance-unit-evidence-v3-matrix.csv` with the exact field catalog frozen by
the pre-live plan. Matrix SHA-256:
`b65544ff8206428932f3ba73f24f0ecb7e61e177ea563340357b8679b4aa755c`.

## 6. Decision boundaries

This pass proves only the observed non-zero finance scale. It does not:

- activate `datanewton_finance_thousand_rub_v2` in runtime;
- authorize public numeric Chart Facts;
- prove lexical source-number preservation through decoder/snapshot/DTO;
- authorize provider-zero publication;
- reinterpret `zero_vs_missing` as agreement;
- close counterparty or arbitration semantic/privacy/completeness gates;
- start iteration 20.

In addition, `evidence_promotion_gate=blocked_protocol_deviation`: the
policy-level numeric result remains reproducible, but it cannot be promoted as
a protocol-clean evidence pass.

After independent review, the owner must separately decide whether the
verified non-zero scale and mandatory limitations are acceptable as iteration
20 design input. Runtime publication remains fail-closed until the lexical
transport gate is implemented and verified and all other required gates are
closed.
