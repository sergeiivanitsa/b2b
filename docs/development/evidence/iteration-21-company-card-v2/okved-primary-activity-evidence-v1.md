# Iteration 21 primary-activity evidence v1

Artifact ID: `company_card_v2_okved_primary_activity_evidence_v1`

Evidence date: `2026-08-24`

Repository base: `f4fe88e51f89a85cbd3c8881affbb8b0b87fbe6c`

Evidence session: `33b7c1a8`

Decision: `APPROVED AS NARROW FAIL-CLOSED INPUT FOR ITERATION 21`

Production/runtime activation: `NOT AUTHORIZED`

## 1. Question and boundary

Iteration 20 intentionally kept OKVED/activity hidden because live shape alone
did not establish the meaning of `okveds[].main`, `value` or `mode`. Iteration
21 needs one safe business-activity label for the public narrative evidence
envelope. This pass tests only the following narrow proposition:

```text
under the exact OKVED_BLOCK profile and the observed mode token "new",
one strict row with main=true identifies the same primary OKVED code and label
as the current public EGRUL extract for the exact target company
```

The pass does not approve additional activities, percentages, effective dates,
provider ordering, unknown mode tokens, runtime rollout or report refresh.

## 2. Authorized collection

Two Russian legal entities were queried once each through the deployed RU
`product_api` probe with this exact profile:

```text
endpoint = GET /v1/counterparty
filters = OKVED_BLOCK
retry_count = 0
contacts/managers/owners = not requested
attempts = 1 per subject
successful_responses = 2
maximum DataNewton quota impact = 2 request units
```

The cohort is pseudonymized as `C01` and `C02`. Raw responses remain only in a
private `/tmp/company-card-v2-iteration21-okved-33b7c1a8` path on RU and were
analyzed in place. They were not copied to the worktree, chat or git.

Official comparison used fresh public EGRUL PDFs obtained from
`https://egrul.nalog.ru/`. The governing FNS description of primary and
additional OKVED data is `https://www.nalog.gov.ru/okved/`.

## 3. Sanitized observations

| Sample | Received at UTC | DataNewton response SHA-256 | Rows | Unique codes | `main=true` | Mode tokens |
|---|---|---|---:|---:|---:|---|
| `C01` | `2026-08-24T13:17:44.039306Z` | `646ae07b48097dcf08c5d740d36629a3f5d9a077549ee1802edc3a032a9e81a2` | 6 | 6 | 1 | `new`: 6 |
| `C02` | `2026-08-24T13:17:57.064567Z` | `34e6000d41e2b585faa0da97d1b509e7da95a9d06d32cde4613e8db176402e81` | 45 | 43 | 1 | `new`: 45 |

Every row was an object. Every `code` matched the bounded dotted numeric
grammar, every `value` was a non-empty string, and every `main` was boolean.
The duplicated additional codes in `C02` prove that provider code uniqueness
cannot be assumed for the whole array.

## 4. Official comparison

Comparison is exact after this non-semantic document normalization:

1. Unicode NFC;
2. remove PDF soft hyphens;
3. join a word split after a visible hyphen by PDF line wrapping;
4. collapse whitespace;
5. Unicode casefold.

| Sample | DataNewton primary code | FNS primary code | Normalized label SHA-256 (both sources) | Result |
|---|---|---|---|---|
| `C01` | `46.73` | `46.73` | `b141fcb41624d6ce6bfdd4520ea830a20512d229adf126d37200c4a917783152` | exact code and normalized label match |
| `C02` | `62.01` | `62.01` | `b6a2de843f6f169be792cc01d735ea98cab4ebdfa4d5809d7b1395e935d6c2d1` | exact code and normalized label match |

The final compared FNS PDF hashes were:

```text
C01 8772c0260d6e38fc8adf031bf5af45b0eac0944e6e635109ca0f9ab03de9dc75
C02 588c59d86782ab4963df18adb0c01e740e7b17218c0c1060b3f6833ac0861444
```

FNS PDFs are generated artifacts and may change bytes between downloads. The
decision depends on the extracted primary code and normalized-label match, not
on stable PDF bytes.

## 5. Approved parser/public-AI rule

Iteration 21 may expose one `primary_activity` evidence item only when all of
the following are true:

1. the counterparty result is bound to the exact report target;
2. `OKVED_BLOCK` was explicitly requested and successfully returned;
3. `$.company.okveds` is an array of bounded strict objects;
4. exactly one row has literal boolean `main=true`;
5. that row has a valid bounded code and a non-empty bounded label;
6. the row has the exact opaque allowlisted token `mode="new"`;
7. no duplicate row conflicts with the chosen code or label;
8. the evidence and parser versions are included in snapshot/artifact identity.

`mode="new"` is an opaque admission token only. It is not rendered and this
pass does not assign it a reporting/declarative business meaning.

The public/AI statement may say only that the label is the company's primary
activity according to the admitted source data. It must not claim actual
revenue share, current operational focus, exclusivity or an effective date.

If any condition fails, activity is unavailable and the deterministic fallback
is used. No first-row inference, label repair, fuzzy matching or secondary-row
fallback is permitted.

## 6. Still prohibited

- additional OKVED rows and percentages;
- unknown/absent `mode` tokens;
- activity inference from company name, finance, websites or AI;
- raw DataNewton/FNS payloads in snapshots, prompts, logs or fixtures;
- contacts, managers, owners or personal identifiers;
- automatic refresh of old reports;
- production DataNewton profile activation or H2 assignment.

The two-subject cohort is sufficient only for this exact narrow admission rule.
Any broader activity model requires a new evidence/version decision.
