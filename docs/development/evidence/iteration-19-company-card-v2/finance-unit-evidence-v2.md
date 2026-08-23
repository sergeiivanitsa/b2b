# Finance unit evidence v2 — live DataNewton/FNS matrix

Artifact ID: `company_card_v2_finance_unit_evidence_v2`

Supersedes for future decisions: none; immutable v1 remains historical.

Evidence session: `64fcf9bb84f045d5bd8652ecabdf2a81`

Evidence date: `2026-08-24` (Asia/Vladivostok)

Candidate policy: `datanewton_finance_thousand_rub_v1`

Final gate: `REJECTED`

Runtime capability: `BLOCKED`

## 1. Atomic decision

The separately authorized live matrix does **not** activate the candidate
policy. It contains 72 deterministic field-level comparisons over three
pseudonymous legal entities, both required forms, all twelve required line
codes, and reporting years 2024–2025.

Observed outcomes:

| Outcome | Count |
|---|---:|
| `exact_nonzero` | 69 |
| `exact_zero` | 1 |
| `mismatch` | 2 |
| Total | 72 |

Both mismatches are the same closed semantic conflict:

| Pseudonym | Form | Code | Year | DataNewton | FNS |
|---|---|---:|---:|---|---|
| `C02` | `balance` | `1240` | 2024 | `zero` | `missing` |
| `C02` | `balance` | `1240` | 2025 | `zero` | `missing` |

The v1 contract forbids converting missing to zero and states that any one
mismatch fails promotion atomically. The failed cells therefore cannot be
discarded, reinterpreted as equal, or removed by replacing `C02` after the
result is known.

Final state:

```text
schema_gate = rejected
semantic_gate = rejected
candidate_policy = inactive
runtime_capability = BLOCKED
reason_code = exact_value_mismatch
detail = provider_explicit_zero_vs_official_missing
```

The 69 exact non-zero matches are strong evidence that the observed provider
numbers use the same *thousand-ruble scale* as the official statements. They
do not waive the contracted missing/zero invariant and therefore do not
activate a product policy.

## 2. Authorization, scope and safety

The owner explicitly authorized live DataNewton requests, quota use and reads
of public FNS data. Collection stayed inside the approved boundary:

- exactly three Russian legal entities, tracked only as `C01..C03`;
- exactly three finance calls, one per company, each successful on attempt 1;
- endpoint `GET /v1/finance`; no finance retry;
- official FNS ГИР БО statements for the same companies and periods;
- no production database, report refresh/backfill, paid AI or contacts;
- raw responses, PDFs and the private identifier map remain outside git;
- tracked content contains only pseudonyms, presence classes, outcomes,
  timestamps, shape/tool IDs and SHA-256 provenance hashes.

The three finance response hashes and three official document hashes occur in
the row matrix below. They identify private source artifacts without exposing
their values or identifier-bearing locators.

## 3. OKEI classification

Each official PDF was visually checked and contains the explicit unit label
`Тыс. руб.`. The controlled classifier maps that exact label to OKEI
`384` using the official
[Rosstat OKEI open dataset](https://rosstat.gov.ru/opendata/7708234640-okei).
No document contained a million-ruble label, an ambiguous marker or a mixed
form-specific unit.

Therefore every row is classified:

```text
fns_okei_state = accepted_384
fns_okei_code = 384
scale_outcome = direct_thousand
```

This classification proves the FNS side's unit. DataNewton scale promotion
still depends on the whole matrix, which failed for the independent
missing/zero reason above.

## 4. Coverage and pass-criteria audit

| Criterion from v1 | Result | Evidence |
|---|---|---|
| 3–5 companies | PASS | 3 pseudonyms |
| two common years for both forms | PASS | 2024 and 2025 |
| all forms and twelve exact codes | PASS | 72 attempted cells |
| at least one non-zero match per code | PASS | all 12 codes |
| non-zero matches in at least two companies per code | PASS | code 1240: 2; every other code: 3 |
| non-zero evidence in both year positions per form | PASS | both forms, both years |
| direct OKEI-384 non-zero evidence in each form | PASS | both forms |
| no company contributes over half of proof cells | PASS | C01=23, C02=22, C03=24 of 69 |
| field-level row for every cell | PASS | 72 rows below |
| all comparable non-zero values match exactly | PASS | 69 of 69 |
| no mismatch/rejected OKEI/mixed scale/conflict/drift | **FAIL** | 2 zero-vs-missing mismatches |
| reproducible endpoint/shape/tool/session/hashes | PASS | row matrix and provenance |

Because promotion is atomic, the single failing criterion controls the final
decision.

## 5. Versioned provenance and tool manifest

The identifiers repeated in every CSV row have these closed bindings.

### 5.1. Provider request and shape binding

`provider_shape_version=datanewton_finance_2026-08-23_shape_v2` means exactly:

```text
repository base = 205f34a
probe_version = 2
method = GET
endpoint = /v1/finance
query = inn=<private identifier from the out-of-git C01..C03 map>
filters = none
request body = none
calls = one per pseudonym
retry result = attempts=1 for every call
```

The closed live shape is a root object with
`available_count`, `balances`, `demo_available_count`, `fin_results` and
`money_flow`. The policy reads only:

```text
$.balances
  {assets: object, indicators: array, liabilities: object,
   okud: string, years: integer array}

$.fin_results
  {indicators: array, okud: string, years: integer array}

within the exact form root:
  recursive object with code: string and sum: object
  -> exact sum["2024"] or sum["2025"] numeric/string/null candidate
```

The three private `shape.json` artifacts bind this union:

| Pseudonym | `shape.json` SHA-256 |
|---|---|
| `C01` | `024f7ffb8f3f55b977bddabce365e7ab277ab42a737a59a8e1b30aeea24c4b23` |
| `C02` | `221717392c24193bbe476c613791189e00cef30e2d08f0829bbae6fcb8966540` |
| `C03` | `566d4904b6130c4617bec7162e9da409ba37537a8162deca7f445dc2f2bdcf40` |

Any endpoint, query/filter, root/form/member type or shape-hash drift makes this
version stale. `money_flow` and code `4400` remain outside policy scope.

### 5.2. FNS machine/document binding

The comparator selected exactly one root list item with `period="2025"` and
exactly one `typeCorrections[].correction`, then read:

```text
balance.current<code>  -> 2025
balance.previous<code> -> 2024
financialResult.current<code>  -> 2025
financialResult.previous<code> -> 2024
```

The CSV carries each official PDF hash in `fns_document_sha256`. The machine
values were read from these separate private FNS JSON artifacts:

| Pseudonym | FNS JSON SHA-256 | Official PDF SHA-256 |
|---|---|---|
| `C01` | `1c8f777fe0e813f8094155f511dc91aafc77be9994ddadda20d84523c78ba4f7` | `fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7` |
| `C02` | `92dc83085c92d6e31ee155557a602fc94f881151bdc2ff47bc72e54f89665fb6` | `a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99` |
| `C03` | `ff429ae7208c0f96d49722eeb7b0ce53aa74a79047c49c6cee982a8555f46f57` | `05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc` |

Identifier-bearing FNS locators remain private; hashes bind the tracked rows to
the exact machine values and visually checked documents.

### 5.3. Collector binding

`collection_tool_version=company-card-v2-finance-matrix-v2` is the following
closed deterministic procedure, executed against the hashes above:

1. Decode the private serialized JSON with `parse_int=Decimal` and
   `parse_float=Decimal`; accept closed Decimal strings, reject booleans,
   non-finite values and other scalar types.
2. Inside only the named form root, recursively collect objects with exact
   sibling `code` and `sum`; select only years 2024/2025.
3. Preserve absent/null as `missing`, exact Decimal zero as `zero`, and every
   other finite Decimal as `nonzero`; unequal duplicates are conflicts.
4. Select the FNS correction and year leaves exactly as section 5.2 states.
5. Require the visually verified exact PDF unit label `Тыс. руб.` and map it
   through the cited OKEI dataset to accepted code 384 before comparison.
6. Compare Decimal values without tolerance, rounding, interpolation or
   missing/zero coercion and emit the closed outcomes from v1.
7. Sort by pseudonym, form order `balance,financial_results`, numeric code and
   reporting year; emit exactly the sixteen CSV fields below.

The procedure is versioned by this immutable artifact and repository commit.
The temporary executable used to apply it is not a production component and
is not evidence by itself; the closed algorithm, exact input hashes and the
72-row output are the reproducible evidence.

## 6. Decimal-transport boundary

The private raw files used here were serialized by the existing probe after
the current HTTP JSON decoder had already coerced source numbers. Exact
comparison of the integer-like observed values is sufficient for this matrix,
but it does not prove source-byte lexical Decimal transport.

```text
finance_decimal_transport = UNVERIFIED / BLOCKED
owner = iteration 20 implementation and negative tests
```

A future policy must require lexical number/string capture before float
coercion and preserve the v1 missing/zero distinction.

## 7. Sanitized field-level matrix

The CSV header is the exact `FinanceEvidenceCellV1` field catalog. Raw
monetary values are intentionally absent.

```csv
evidence_session_id,pseudonym,form_id,line_code,reporting_year,datanewton_presence,fns_presence,fns_okei_state,fns_okei_code,comparison_outcome,scale_outcome,datanewton_raw_sha256,fns_document_sha256,provider_shape_version,collection_tool_version,collected_at
64fcf9bb84f045d5bd8652ecabdf2a81,C01,balance,1210,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,62f67ab7eaaeaed9cb3a4dcc900271ad25045579fdf8160d49986672f3d6306e,fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:12:51.548372Z
64fcf9bb84f045d5bd8652ecabdf2a81,C01,balance,1210,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,62f67ab7eaaeaed9cb3a4dcc900271ad25045579fdf8160d49986672f3d6306e,fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:12:51.548372Z
64fcf9bb84f045d5bd8652ecabdf2a81,C01,balance,1230,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,62f67ab7eaaeaed9cb3a4dcc900271ad25045579fdf8160d49986672f3d6306e,fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:12:51.548372Z
64fcf9bb84f045d5bd8652ecabdf2a81,C01,balance,1230,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,62f67ab7eaaeaed9cb3a4dcc900271ad25045579fdf8160d49986672f3d6306e,fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:12:51.548372Z
64fcf9bb84f045d5bd8652ecabdf2a81,C01,balance,1240,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,62f67ab7eaaeaed9cb3a4dcc900271ad25045579fdf8160d49986672f3d6306e,fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:12:51.548372Z
64fcf9bb84f045d5bd8652ecabdf2a81,C01,balance,1240,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,62f67ab7eaaeaed9cb3a4dcc900271ad25045579fdf8160d49986672f3d6306e,fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:12:51.548372Z
64fcf9bb84f045d5bd8652ecabdf2a81,C01,balance,1250,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,62f67ab7eaaeaed9cb3a4dcc900271ad25045579fdf8160d49986672f3d6306e,fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:12:51.548372Z
64fcf9bb84f045d5bd8652ecabdf2a81,C01,balance,1250,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,62f67ab7eaaeaed9cb3a4dcc900271ad25045579fdf8160d49986672f3d6306e,fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:12:51.548372Z
64fcf9bb84f045d5bd8652ecabdf2a81,C01,balance,1300,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,62f67ab7eaaeaed9cb3a4dcc900271ad25045579fdf8160d49986672f3d6306e,fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:12:51.548372Z
64fcf9bb84f045d5bd8652ecabdf2a81,C01,balance,1300,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,62f67ab7eaaeaed9cb3a4dcc900271ad25045579fdf8160d49986672f3d6306e,fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:12:51.548372Z
64fcf9bb84f045d5bd8652ecabdf2a81,C01,balance,1400,2024,zero,zero,accepted_384,384,exact_zero,direct_thousand,62f67ab7eaaeaed9cb3a4dcc900271ad25045579fdf8160d49986672f3d6306e,fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:12:51.548372Z
64fcf9bb84f045d5bd8652ecabdf2a81,C01,balance,1400,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,62f67ab7eaaeaed9cb3a4dcc900271ad25045579fdf8160d49986672f3d6306e,fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:12:51.548372Z
64fcf9bb84f045d5bd8652ecabdf2a81,C01,balance,1500,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,62f67ab7eaaeaed9cb3a4dcc900271ad25045579fdf8160d49986672f3d6306e,fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:12:51.548372Z
64fcf9bb84f045d5bd8652ecabdf2a81,C01,balance,1500,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,62f67ab7eaaeaed9cb3a4dcc900271ad25045579fdf8160d49986672f3d6306e,fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:12:51.548372Z
64fcf9bb84f045d5bd8652ecabdf2a81,C01,balance,1600,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,62f67ab7eaaeaed9cb3a4dcc900271ad25045579fdf8160d49986672f3d6306e,fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:12:51.548372Z
64fcf9bb84f045d5bd8652ecabdf2a81,C01,balance,1600,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,62f67ab7eaaeaed9cb3a4dcc900271ad25045579fdf8160d49986672f3d6306e,fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:12:51.548372Z
64fcf9bb84f045d5bd8652ecabdf2a81,C01,financial_results,2100,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,62f67ab7eaaeaed9cb3a4dcc900271ad25045579fdf8160d49986672f3d6306e,fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:12:51.548372Z
64fcf9bb84f045d5bd8652ecabdf2a81,C01,financial_results,2100,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,62f67ab7eaaeaed9cb3a4dcc900271ad25045579fdf8160d49986672f3d6306e,fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:12:51.548372Z
64fcf9bb84f045d5bd8652ecabdf2a81,C01,financial_results,2110,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,62f67ab7eaaeaed9cb3a4dcc900271ad25045579fdf8160d49986672f3d6306e,fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:12:51.548372Z
64fcf9bb84f045d5bd8652ecabdf2a81,C01,financial_results,2110,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,62f67ab7eaaeaed9cb3a4dcc900271ad25045579fdf8160d49986672f3d6306e,fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:12:51.548372Z
64fcf9bb84f045d5bd8652ecabdf2a81,C01,financial_results,2200,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,62f67ab7eaaeaed9cb3a4dcc900271ad25045579fdf8160d49986672f3d6306e,fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:12:51.548372Z
64fcf9bb84f045d5bd8652ecabdf2a81,C01,financial_results,2200,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,62f67ab7eaaeaed9cb3a4dcc900271ad25045579fdf8160d49986672f3d6306e,fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:12:51.548372Z
64fcf9bb84f045d5bd8652ecabdf2a81,C01,financial_results,2400,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,62f67ab7eaaeaed9cb3a4dcc900271ad25045579fdf8160d49986672f3d6306e,fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:12:51.548372Z
64fcf9bb84f045d5bd8652ecabdf2a81,C01,financial_results,2400,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,62f67ab7eaaeaed9cb3a4dcc900271ad25045579fdf8160d49986672f3d6306e,fd14a1b0909031ecb7e4b641abf678f38b14cc939b28064497e47c3561dfd6d7,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:12:51.548372Z
64fcf9bb84f045d5bd8652ecabdf2a81,C02,balance,1210,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,bbf7f51db00f75b22617953202157bcb5a1382e7f1196ed464784ddec8ad6e7f,a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:05.19964Z
64fcf9bb84f045d5bd8652ecabdf2a81,C02,balance,1210,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,bbf7f51db00f75b22617953202157bcb5a1382e7f1196ed464784ddec8ad6e7f,a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:05.19964Z
64fcf9bb84f045d5bd8652ecabdf2a81,C02,balance,1230,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,bbf7f51db00f75b22617953202157bcb5a1382e7f1196ed464784ddec8ad6e7f,a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:05.19964Z
64fcf9bb84f045d5bd8652ecabdf2a81,C02,balance,1230,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,bbf7f51db00f75b22617953202157bcb5a1382e7f1196ed464784ddec8ad6e7f,a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:05.19964Z
64fcf9bb84f045d5bd8652ecabdf2a81,C02,balance,1240,2024,zero,missing,accepted_384,384,mismatch,direct_thousand,bbf7f51db00f75b22617953202157bcb5a1382e7f1196ed464784ddec8ad6e7f,a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:05.19964Z
64fcf9bb84f045d5bd8652ecabdf2a81,C02,balance,1240,2025,zero,missing,accepted_384,384,mismatch,direct_thousand,bbf7f51db00f75b22617953202157bcb5a1382e7f1196ed464784ddec8ad6e7f,a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:05.19964Z
64fcf9bb84f045d5bd8652ecabdf2a81,C02,balance,1250,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,bbf7f51db00f75b22617953202157bcb5a1382e7f1196ed464784ddec8ad6e7f,a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:05.19964Z
64fcf9bb84f045d5bd8652ecabdf2a81,C02,balance,1250,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,bbf7f51db00f75b22617953202157bcb5a1382e7f1196ed464784ddec8ad6e7f,a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:05.19964Z
64fcf9bb84f045d5bd8652ecabdf2a81,C02,balance,1300,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,bbf7f51db00f75b22617953202157bcb5a1382e7f1196ed464784ddec8ad6e7f,a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:05.19964Z
64fcf9bb84f045d5bd8652ecabdf2a81,C02,balance,1300,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,bbf7f51db00f75b22617953202157bcb5a1382e7f1196ed464784ddec8ad6e7f,a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:05.19964Z
64fcf9bb84f045d5bd8652ecabdf2a81,C02,balance,1400,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,bbf7f51db00f75b22617953202157bcb5a1382e7f1196ed464784ddec8ad6e7f,a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:05.19964Z
64fcf9bb84f045d5bd8652ecabdf2a81,C02,balance,1400,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,bbf7f51db00f75b22617953202157bcb5a1382e7f1196ed464784ddec8ad6e7f,a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:05.19964Z
64fcf9bb84f045d5bd8652ecabdf2a81,C02,balance,1500,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,bbf7f51db00f75b22617953202157bcb5a1382e7f1196ed464784ddec8ad6e7f,a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:05.19964Z
64fcf9bb84f045d5bd8652ecabdf2a81,C02,balance,1500,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,bbf7f51db00f75b22617953202157bcb5a1382e7f1196ed464784ddec8ad6e7f,a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:05.19964Z
64fcf9bb84f045d5bd8652ecabdf2a81,C02,balance,1600,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,bbf7f51db00f75b22617953202157bcb5a1382e7f1196ed464784ddec8ad6e7f,a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:05.19964Z
64fcf9bb84f045d5bd8652ecabdf2a81,C02,balance,1600,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,bbf7f51db00f75b22617953202157bcb5a1382e7f1196ed464784ddec8ad6e7f,a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:05.19964Z
64fcf9bb84f045d5bd8652ecabdf2a81,C02,financial_results,2100,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,bbf7f51db00f75b22617953202157bcb5a1382e7f1196ed464784ddec8ad6e7f,a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:05.19964Z
64fcf9bb84f045d5bd8652ecabdf2a81,C02,financial_results,2100,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,bbf7f51db00f75b22617953202157bcb5a1382e7f1196ed464784ddec8ad6e7f,a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:05.19964Z
64fcf9bb84f045d5bd8652ecabdf2a81,C02,financial_results,2110,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,bbf7f51db00f75b22617953202157bcb5a1382e7f1196ed464784ddec8ad6e7f,a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:05.19964Z
64fcf9bb84f045d5bd8652ecabdf2a81,C02,financial_results,2110,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,bbf7f51db00f75b22617953202157bcb5a1382e7f1196ed464784ddec8ad6e7f,a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:05.19964Z
64fcf9bb84f045d5bd8652ecabdf2a81,C02,financial_results,2200,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,bbf7f51db00f75b22617953202157bcb5a1382e7f1196ed464784ddec8ad6e7f,a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:05.19964Z
64fcf9bb84f045d5bd8652ecabdf2a81,C02,financial_results,2200,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,bbf7f51db00f75b22617953202157bcb5a1382e7f1196ed464784ddec8ad6e7f,a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:05.19964Z
64fcf9bb84f045d5bd8652ecabdf2a81,C02,financial_results,2400,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,bbf7f51db00f75b22617953202157bcb5a1382e7f1196ed464784ddec8ad6e7f,a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:05.19964Z
64fcf9bb84f045d5bd8652ecabdf2a81,C02,financial_results,2400,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,bbf7f51db00f75b22617953202157bcb5a1382e7f1196ed464784ddec8ad6e7f,a2125f4390a1243b835e25d7ee3f80b08b2be4424cf49d89fbfccea6e0a0cf99,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:05.19964Z
64fcf9bb84f045d5bd8652ecabdf2a81,C03,balance,1210,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,abb9ef30366bd0da687704bf91dd60067fd9876941029e69e6f249318eccab85,05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:18.387587Z
64fcf9bb84f045d5bd8652ecabdf2a81,C03,balance,1210,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,abb9ef30366bd0da687704bf91dd60067fd9876941029e69e6f249318eccab85,05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:18.387587Z
64fcf9bb84f045d5bd8652ecabdf2a81,C03,balance,1230,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,abb9ef30366bd0da687704bf91dd60067fd9876941029e69e6f249318eccab85,05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:18.387587Z
64fcf9bb84f045d5bd8652ecabdf2a81,C03,balance,1230,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,abb9ef30366bd0da687704bf91dd60067fd9876941029e69e6f249318eccab85,05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:18.387587Z
64fcf9bb84f045d5bd8652ecabdf2a81,C03,balance,1240,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,abb9ef30366bd0da687704bf91dd60067fd9876941029e69e6f249318eccab85,05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:18.387587Z
64fcf9bb84f045d5bd8652ecabdf2a81,C03,balance,1240,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,abb9ef30366bd0da687704bf91dd60067fd9876941029e69e6f249318eccab85,05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:18.387587Z
64fcf9bb84f045d5bd8652ecabdf2a81,C03,balance,1250,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,abb9ef30366bd0da687704bf91dd60067fd9876941029e69e6f249318eccab85,05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:18.387587Z
64fcf9bb84f045d5bd8652ecabdf2a81,C03,balance,1250,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,abb9ef30366bd0da687704bf91dd60067fd9876941029e69e6f249318eccab85,05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:18.387587Z
64fcf9bb84f045d5bd8652ecabdf2a81,C03,balance,1300,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,abb9ef30366bd0da687704bf91dd60067fd9876941029e69e6f249318eccab85,05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:18.387587Z
64fcf9bb84f045d5bd8652ecabdf2a81,C03,balance,1300,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,abb9ef30366bd0da687704bf91dd60067fd9876941029e69e6f249318eccab85,05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:18.387587Z
64fcf9bb84f045d5bd8652ecabdf2a81,C03,balance,1400,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,abb9ef30366bd0da687704bf91dd60067fd9876941029e69e6f249318eccab85,05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:18.387587Z
64fcf9bb84f045d5bd8652ecabdf2a81,C03,balance,1400,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,abb9ef30366bd0da687704bf91dd60067fd9876941029e69e6f249318eccab85,05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:18.387587Z
64fcf9bb84f045d5bd8652ecabdf2a81,C03,balance,1500,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,abb9ef30366bd0da687704bf91dd60067fd9876941029e69e6f249318eccab85,05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:18.387587Z
64fcf9bb84f045d5bd8652ecabdf2a81,C03,balance,1500,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,abb9ef30366bd0da687704bf91dd60067fd9876941029e69e6f249318eccab85,05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:18.387587Z
64fcf9bb84f045d5bd8652ecabdf2a81,C03,balance,1600,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,abb9ef30366bd0da687704bf91dd60067fd9876941029e69e6f249318eccab85,05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:18.387587Z
64fcf9bb84f045d5bd8652ecabdf2a81,C03,balance,1600,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,abb9ef30366bd0da687704bf91dd60067fd9876941029e69e6f249318eccab85,05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:18.387587Z
64fcf9bb84f045d5bd8652ecabdf2a81,C03,financial_results,2100,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,abb9ef30366bd0da687704bf91dd60067fd9876941029e69e6f249318eccab85,05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:18.387587Z
64fcf9bb84f045d5bd8652ecabdf2a81,C03,financial_results,2100,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,abb9ef30366bd0da687704bf91dd60067fd9876941029e69e6f249318eccab85,05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:18.387587Z
64fcf9bb84f045d5bd8652ecabdf2a81,C03,financial_results,2110,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,abb9ef30366bd0da687704bf91dd60067fd9876941029e69e6f249318eccab85,05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:18.387587Z
64fcf9bb84f045d5bd8652ecabdf2a81,C03,financial_results,2110,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,abb9ef30366bd0da687704bf91dd60067fd9876941029e69e6f249318eccab85,05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:18.387587Z
64fcf9bb84f045d5bd8652ecabdf2a81,C03,financial_results,2200,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,abb9ef30366bd0da687704bf91dd60067fd9876941029e69e6f249318eccab85,05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:18.387587Z
64fcf9bb84f045d5bd8652ecabdf2a81,C03,financial_results,2200,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,abb9ef30366bd0da687704bf91dd60067fd9876941029e69e6f249318eccab85,05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:18.387587Z
64fcf9bb84f045d5bd8652ecabdf2a81,C03,financial_results,2400,2024,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,abb9ef30366bd0da687704bf91dd60067fd9876941029e69e6f249318eccab85,05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:18.387587Z
64fcf9bb84f045d5bd8652ecabdf2a81,C03,financial_results,2400,2025,nonzero,nonzero,accepted_384,384,exact_nonzero,direct_thousand,abb9ef30366bd0da687704bf91dd60067fd9876941029e69e6f249318eccab85,05f92ede7f5543590ec5fb08a1d497c840070a6f5263bf9f46cda062f427cbdc,datanewton_finance_2026-08-23_shape_v2,company-card-v2-finance-matrix-v2,2026-08-23T14:13:18.387587Z
```

## 8. Downstream consequence

Iteration 20 remains blocked under the current Roadmap dependency. A next
evidence/design pass must create a new policy version that explicitly resolves
provider-explicit-zero versus official-missing semantics without rewriting
this result. Re-running the same policy with cherry-picked companies cannot
turn this rejected session into a pass.
