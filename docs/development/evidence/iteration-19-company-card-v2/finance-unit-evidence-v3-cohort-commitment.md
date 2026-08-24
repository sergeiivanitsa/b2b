# Finance unit evidence v3 — pre-call cohort commitment

Artifact ID: `company_card_v2_finance_unit_evidence_v3_cohort_commitment`

Evidence session: `3e34f7484501432dbf2b73c38e7c3d31`

Committed at: `2026-08-24T00:19:22.7676609Z`

Base commit: `2ef3f856376564300eb0f6a4f66109e75aab5f3c`

State: `LOCKED PRE-CALL — ZERO DATANEWTON CALLS EXECUTED`

## 1. Bound versions

| Surface | Version |
|---|---|
| Policy | `datanewton_finance_thousand_rub_v2` |
| Private manifest | `company-card-v2-finance-cohort-manifest-v1` |
| Selection rule | `company-card-v2-finance-cohort-selection-v3` |
| Request profile | `datanewton-finance-get-v1-no-filters-no-retry` |
| Collector | `company-card-v2-finance-matrix-v3` |

The future provider request is exactly `GET /v1/finance` with only the private
sample identifier, no filters, no body, one call per sample and no retry.

## 2. Ordered sanitized cohort

The immutable order is:

```text
C04
C05
C06
C07
C08
```

The cohort contains five active Russian legal entities. For every included
sample the metadata-only FNS ГИР БО check established:

- one exact organization match;
- annual period type `12`;
- both `balance` and `financialResult` form references;
- common periods `2025` and `2024`;
- neither Central Bank nor KFO reporting mode;
- no overlap with the private C01–C03 cohort.

Selection did not inspect any included sample's finance line presence or
amounts. One preliminary endpoint-validation candidate whose search response
was displayed with a search-level aggregate was excluded before the cohort was
locked and is not represented by C04–C08.

Insufficient line-code coverage, source unavailability or transport failure in
the locked cohort must produce the policy-defined `insufficient`/failed state.
No sample may be removed, reordered or replaced after this commitment.

## 3. Private canonical manifest commitment

The private manifest contains the high-entropy nonce, ordered identifiers,
FNS organization IDs, periods, forms and every version from section 1. It
remains outside Git with the private identifier map.

Canonical bytes are UTF-8 without BOM, LF-only, with one final LF and fields in
the fixed manifest order. The commitment is:

```text
sha256 = 2870e8e1ade3f0b1237993ee4cc6bac94387078a2892cd4293c4682411de4a89
byte_length = 1056
```

The hash must be recomputed and matched before the first provider call and
again before result interpretation. The result evidence must record this
artifact's pushed Git commit hash.

## 4. Privacy and execution boundary

This tracked artifact contains no company name, INN, OGRN, FNS organization
ID, address, finance amount, contact, person, credential, raw response or
private nonce.

As of the committed timestamp:

- DataNewton finance calls used: `0/5`;
- DataNewton retry budget: `0`;
- paid AI calls: `0`;
- production DB/report mutations: `0`;
- deployment/runtime changes: `0`.

No DataNewton call is allowed until this exact artifact is in a dedicated Git
commit pushed to the remote feature branch.
