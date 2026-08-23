# Итерация 19 — Company Card v2 contract/evidence: implementation plan

ID: `19`

Slug: `company-card-v2-contract-evidence`

Contract: `company_public_h2_v1`

Branch: `feat/iteration-19-company-card-v2-contract-evidence`

Base commit: `c3805dd1fbb8cdac38b1aa315e1f1e94597e7537`

Статус плана: `approved_after_fresh_restart`

Mode: `documentation/evidence/wireframes only`

Specification:

```text
docs/development/iterations/iteration-19-company-card-v2-contract-evidence.md
```

## 1. Execution constraints

Implementation is documentation-only.

Запрещено:

- менять Product API, Gateway API, React, shared, deploy или CI;
- менять `docs/development/ROADMAP.md`;
- выполнять production DB access;
- выполнять paid AI;
- выполнять live DataNewton/FNS call до отдельной live-stage authorization boundary;
- копировать raw payload, identifiers, PII, contacts, credentials или headers в repo;
- refresh/backfill/publish existing reports;
- commit, push или merge как implementer step.

Локальные PDF, PNG, technical spec и ignored evidence читаются read-only и не изменяются.

Existing `docs/development/DEVFLOW_STATE.yaml` change принадлежит DevFlow orchestration и сохраняется. Implementer не откатывает чужие изменения.

## 2. Exact changed-file manifest

### 2.1. Specification, plan and state

```text
docs/development/iterations/iteration-19-company-card-v2-contract-evidence.md
docs/development/plans/iteration-19-company-card-v2-contract-evidence.md
docs/development/DEVFLOW_STATE.yaml
```

Allowed state changes:

- lifecycle iteration 19 only;
- preserve exact branch;
- if evidence gates remain closed, preserve iteration 20/23 blockers;
- no rewrite of completed iteration history.

### 2.2. Evidence

```text
docs/development/evidence/iteration-19-company-card-v2/provider-field-manifest-v1.md
docs/development/evidence/iteration-19-company-card-v2/finance-unit-evidence-v1.md
docs/development/evidence/iteration-19-company-card-v2/arbitration-contract-evidence-v1.md
```

### 2.3. Decisions

```text
docs/development/decisions/iteration-19-company-card-v2-architecture.md
docs/development/decisions/iteration-19-company-card-v2-privacy.md
```

### 2.4. Wireframes

```text
docs/development/wireframes/iteration-19-company-card-v2/desktop.svg
docs/development/wireframes/iteration-19-company-card-v2/tablet.svg
docs/development/wireframes/iteration-19-company-card-v2/mobile.svg
```

No other file is in scope.

Explicitly unchanged:

```text
README.md
docs/development/ROADMAP.md
services/product_api/**
services/gateway_api/**
services/web_ui/**
shared/**
deploy/**
.github/workflows/**
docker-compose*.yml
```

## 3. Ownership

| Role | Responsibility |
|---|---|
| Documentation implementer | Integrates only exact manifest and preserves unrelated work |
| Evidence analyst | Read-only shape/unit comparisons; writes sanitized Markdown only |
| Contract owner | H2/v3/publication/pagination/AI/SSR ADR decisions |
| UX wireframe owner | Three accessible reviewable SVGs |
| Privacy/security owner | Public field classification, masking, CSP/XSS, telemetry |
| Independent plan reviewer | Reviews spec/plan/evidence before implementation handoff |
| Independent docs reviewer | Reviews final diff, privacy and no-runtime boundary |

The same person/agent must not approve their own planning or review findings.

## 4. Stage A — Baseline and provenance inventory

1. Confirm branch and base commit.
2. Record existing dirty paths without modifying them.
3. Read the complete required repository documents and iterations 16–18.
4. Record input provenance without copying raw content:
   - page-layout PDF;
   - chart technical specification;
   - CTA PNG;
   - owner-supplied ignored evidence batch;
   - repository synthetic fixtures/code;
   - FNS ГИР БО/ОКЕИ comparator policy.
5. Record current evidence conclusions:
   - local sample supports observed finance/case shapes;
   - current H1 DTO cannot support the ten views;
   - current arbitration collection is one page;
   - current normalized snapshot discards required outcome/entity semantics;
   - finance unit remains unverified.
6. Do not print raw evidence into command logs or documentation.
7. Use pseudonyms only in tracked artifacts.

Output:

- provenance preamble in all three evidence files;
- current gate-state matrix.

## 5. Stage B — Provider field manifest

Create `provider-field-manifest-v1.md`.

For every field in the specification, add a row with:

```text
field_id
dataset/endpoint
exact path or NOT_VERIFIED
JSON type
cardinality
nullability
subject scope
effective/reference date
identity semantics
observed source
evidence date
schema gate
semantic gate
privacy gate
operational gate
public transformation
missing/conflict behavior
future iteration owner
```

Procedure:

1. Reconcile existing normalizer paths with synthetic fixtures.
2. Inspect only key/type/cardinality from ignored owner evidence.
3. Do not copy values, names, identifiers, URLs containing identifiers or free provider text.
4. Mark repository synthetic fixtures as `parser-shape evidence`, not vendor evidence.
5. Mark owner local evidence as `observed shape`, not vendor semantic/unit proof.
6. Mark unknown leaves exactly `NOT_VERIFIED`.
7. Keep contacts `prohibited`.
8. Separate:
   - manager safe public composition;
   - owner safe composition;
   - opposing-party privacy.
9. Do not infer entity type from name, OPF text or INN length.
10. Do not infer effective date from response/report date.

Acceptance:

- every content-manifest field maps to one row;
- no row uses “likely”, guessed path or guessed unit;
- hidden fields have explicit limitation behavior.

## 6. Stage C — Arbitration evidence

Create `arbitration-contract-evidence-v1.md`.

Document sanitized structural evidence for:

- page envelope;
- `total/offset/limit/data`;
- `case_id`, fallback `id`, visible case number;
- year/start/update dates;
- plaintiffs/respondents and any observed party collections;
- `party_result` versus `result_type`;
- sum/currency;
- instance/court candidates;
- KAD URL candidate;
- entity-type gap.

Include no case number, party name, INN/OGRN, amount or raw URL from owner evidence.

Record exact gaps:

- only one page observed;
- full pagination semantics unproven;
- preferred key currently lost by normalizer;
- `party_result` currently not persisted;
- entity type unverified;
- current single-page completeness does not prove multi-page behavior;
- equal-amount cases are distinct;
- zero amount is distinct from missing.

Embed the exact ADR parameters:

```text
page_size=100
max_pages=10
case cap=1000
storage cap=8 MiB
preferred case_id, fallback id
conflicting duplicate excluded
cap/non-progress/drift => partial
```

Record gate state separately for:

- pagination completeness;
- case identity;
- role;
- outcome;
- currency;
- party entity type;
- KAD URL.

## 7. Stage D — Finance evidence, offline part

Create `finance-unit-evidence-v1.md` with initial:

```text
candidate_policy: datanewton_finance_thousand_rub_v1
current_gate: UNVERIFIED
runtime_capability: BLOCKED
```

Document:

- required forms and twelve codes;
- existing Decimal shape;
- absence of provider unit field in inspected evidence;
- why PDF, UI prototype, Checko and FNS alone cannot prove DataNewton scale;
- FNS ГИР БО as primary comparator;
- OKEI `384`/`385` distinction;
- exact matrix procedure and pass/fail rules;
- no-tolerance Decimal comparison;
- current consequence: no ruble label/scaling and iteration 23 blocked.

If no authorized live stage occurs, this is the final state for iteration 19.

## 8. Stage E — Separately authorized 3–5 company finance matrix

This is a distinct stage and is not implicitly authorized by docs implementation.

### 8.1. Authorization boundary

Before any network request, record explicit authorization for:

- DataNewton live finance reads;
- FNS comparator reads;
- maximum 3–5 companies;
- maximum five DataNewton finance calls;
- no production DB;
- no paid AI;
- raw output outside git;
- sanitized tracked result only.

Without this authorization, stop this stage and retain `UNVERIFIED/BLOCKED`.

### 8.2. Preflight

1. Select exactly 3–5 Russian legal entities with public ГИР БО statements.
2. Keep the exact identifier map in an ignored/private local file.
3. Assign tracked pseudonyms `C01..C05`.
4. Verify no natural person/contact dataset is requested.
5. Use finance dataset only and the exact intended endpoint/filter shape.
6. Verify secrets are loaded through existing protected configuration and are not printed.
7. Create an ignored raw destination outside tracked paths.
8. Record tool/version/date and an opaque evidence-session ID.
9. Do not use production DB or existing production reports as evidence.

### 8.3. Collection

For each company:

1. Make at most one DataNewton finance request.
2. Obtain the matching FNS ГИР БО statement from the official source.
3. Record FNS unit/OKEI.
4. Compare the twelve required codes over the latest two common years.
5. Compare exact Decimal values as thousands of rubles.
6. Compare missing as missing and zero as zero.
7. Do not round, tolerate, interpolate or choose a best-looking scale.
8. Do not retry an ambiguous provider request automatically.

### 8.4. Sanitized field-level artifact

Aggregate-only company counts cannot activate the gate. Every attempted
`(pseudonym, form_id, line_code, reporting_year)` cell produces one tracked row
with exactly this privacy-safe schema:

```text
evidence_session_id
pseudonym = C01..C05
form_id = balance | financial_results
line_code = one of the twelve approved codes
reporting_year = four-digit public accounting year
datanewton_presence = missing | zero | nonzero
fns_presence = missing | zero | nonzero
fns_okei_state = accepted_384 | accepted_385 |
                 rejected_missing | rejected_ambiguous | rejected_other
fns_okei_code = 384 | 385 | null
comparison_outcome = exact_nonzero | exact_zero | exact_missing |
                     mismatch | unavailable | rejected_okei
scale_outcome = direct_thousand | exact_million_to_thousand | not_applicable
datanewton_raw_sha256
fns_document_sha256
provider_shape_version
collection_tool_version
collected_at
```

`accepted_384` requires `fns_okei_code=384` and `direct_thousand`.
`accepted_385` requires `fns_okei_code=385` and
`exact_million_to_thousand`. Every `rejected_*` state requires
`fns_okei_code=null`, `comparison_outcome=rejected_okei`, and
`scale_outcome=not_applicable`; a rejected raw OKEI token is never tracked.
Accepted states cannot have a rejected outcome, and rejected states cannot
contribute a proof cell. Private exact values are compared without tolerance
and are represented in git only by source-artifact hashes.

Forbidden tracked content:

- identifiers;
- raw amounts;
- raw provider/FNS payload;
- company names;
- identifier-bearing URLs;
- request headers;
- tokens/secrets;
- contact/person data.

### 8.5. Pass/fail

Pass only when all specification conditions and every condition below are
satisfied:

1. Exactly three to five pseudonyms complete the matrix.
2. At least three pseudonyms contribute the latest two common years across both
   forms.
3. Both forms and all twelve exact `(form_id,line_code)` pairs are represented.
4. Every pair has an exact non-zero match in at least two distinct pseudonyms.
5. Each form has non-zero evidence in both compared year positions.
6. Each form has at least one direct non-zero `accepted_384` cell.
7. No pseudonym contributes more than half of all non-zero proof cells.
8. Every comparable cell, including missing and zero, has its field-level row.
9. Every comparable non-zero cell is exact Decimal equality at
   `1 provider source unit = 1 thousand rubles` after only the accepted FNS
   normalization.
10. Every OKEI state is accepted; there is no mismatch, unavailable proof cell,
    rejected OKEI, contradictory state/code/outcome tuple, duplicate conflict,
    mixed or form-specific scale, endpoint/filter drift, or shape drift.
11. Evidence session, endpoint/filter/shape, tool version, UTC collection time,
    and both private source hashes are reproducibly recorded for every row.

Missing/missing and zero/zero rows prove coverage semantics only; they do not
count toward non-zero unit proof. Promotion is atomic:

```text
schema_gate = verified
semantic_gate = verified
candidate_policy = active-for-implementation
```

Any mismatch, rejected OKEI, unavailable proof cell, contradiction, drift, or
insufficient coverage leaves:

```text
gate = unverified or rejected
runtime = blocked
```

If blocked:

- iteration 19 may finish its docs-only scope;
- iteration 20 retains its evidence blocker under the current Roadmap dependency;
- iteration 23 cannot start;
- no reduced-evidence ruble display is allowed.

After iteration 19 is merged, evidence-v1 is immutable. Later new evidence uses a new versioned artifact rather than rewriting history.

## 9. Stage F — Architecture ADR

Create `iteration-19-company-card-v2-architecture.md`.

It must record as accepted decisions:

1. `GET /company-reports/{inn}/public-h2`.
2. `company_public_h2_v1`.
3. Separate public DTO, snapshot, chart, unit, AI and publication versions.
4. H1 unchanged and default through iteration 24.
5. Server-side default-off v3 writer profile; no client version choice.
6. Pending job version fencing.
7. Exact v1/v2/v3 read matrix.
8. Separate H2 pin and presentation assignment.
9. H2 staged/noindex behavior and corrupt-pin fail closed.
10. H1 rollback without snapshot mutation.
11. Bounded full arbitration set plus Chart Facts.
12. Pagination/cap/dedup/page-provenance algorithms.
13. AI immutable artifact/pin/fallback.
14. One H2 embedded DTO, no refetch.
15. CSP and XSS serializer.
16. Feature/rollout dependencies 20–25.

Rejected alternatives:

- extending `company_public_h1_v1` incompatibly;
- returning v3 as fake report version2;
- global v3 constant switch before cutover;
- reusing one H1 publication row for both contracts;
- live provider/AI on GET;
- raw embedded snapshot;
- client-side source semantics;
- reading old snapshots and backfilling them;
- single-page arbitration presented as complete;
- human/second-AI validation boundary.

## 10. Stage G — Privacy ADR

Create `iteration-19-company-card-v2-privacy.md`.

Include an exhaustive table:

| Data class | Stored v3 | Public DTO/SSR | AI envelope | Telemetry |
|---|---|---|---|---|
| Company identity/address | Allowlisted | Allowed | Excluded | Excluded |
| Manager name/role | Safe subset | Allowed | Excluded | Excluded |
| Manager personal ID/contact | Discard/hidden | Forbidden | Forbidden | Forbidden |
| Owner name/share | Safe subset | Allowed | Excluded | Excluded |
| Owner identifiers/contacts | Hidden | Forbidden | Forbidden | Forbidden |
| Legal/state opponent name | Safe normalized | Allowed | Excluded | Excluded |
| Legal opponent INN | Internal grouping only | Forbidden | Forbidden | Forbidden |
| Natural opponent | HMAC token only | Masked | Forbidden | Forbidden |
| Unknown/conflict opponent | HMAC token only | Masked | Forbidden | Forbidden |
| Case amount/currency | Exact safe fact | Allowed | Evidence ID only | Forbidden |
| Raw provider payload | Never persisted | Forbidden | Forbidden | Forbidden |

Also include:

- HMAC domain separator and report scoping;
- no name-based entity classification;
- no name-only grouping;
- exact display ordinal rules;
- Webvisor disabled;
- allowed aggregate UI telemetry only;
- KAD referrer/host rules;
- embedded DTO negative-field allowlist.

## 11. Stage H — Wireframes

Create all three SVGs directly as text/vector artifacts.

### 11.1. Shared requirements

Each SVG:

- is valid standalone XML/SVG;
- uses viewBox matching target viewport;
- uses synthetic content;
- contains no external raster, font or script;
- has a title/description;
- labels every section F1–F5 and A1–A5;
- shows sources, limitations, neutral actions and primary CTA;
- has edge-state callouts;
- uses `#EE5A2A` only for CTA accent;
- uses neutral grayscale/patterns for chart semantics;
- does not pretend to be final decorative design.

### 11.2. Desktop

`desktop.svg`:

- 1440px viewport;
- flexible main column;
- 320px right rail;
- 32px gap;
- sticky CTA annotation;
- full desktop supporting copy;
- no bottom fixed bar.

### 11.3. Tablet

`tablet.svg`:

- 1024px viewport;
- single content column;
- fixed horizontal bottom bar;
- heading and button;
- no supporting paragraph;
- visible safe-area/reserver annotation.

### 11.4. Mobile

`mobile.svg`:

- 390px viewport;
- stacked content;
- stacked fixed bottom CTA;
- full-width button;
- no supporting paragraph;
- local finance-table scroll;
- wrapped long labels;
- safe-area/reserver annotation.

### 11.5. Required state callouts in every file

```text
LONG
EMPTY/MISSING
PARTIAL returned/total
NEGATIVE/MIXED SIGN/ZERO DENOMINATOR
LARGE-N shown N/M
FOCUS/TOUCH
NO OVERLAP
```

## 12. Stage I — Specification and plan integration

1. Ensure both documents are standalone and cross-reference exact artifact paths.
2. Reconcile every Roadmap iteration-19 acceptance item.
3. Ensure no decision is deferred to iteration 20 unless it is an evidence gate explicitly allowed to remain blocked.
4. Reconcile all ten chart views with the technical specification and approved overrides.
5. Confirm exact CTA copy and colors.
6. Confirm H1 remains unchanged.
7. Confirm report-date immutability.
8. Confirm v3/H1 compatibility.
9. Confirm AI length/max-two/fallback contract.
10. Confirm SSR embedded DTO is H2-only.
11. Confirm rollout activation is iteration25 + owner approval only.
12. Update only iteration19 DevFlow lifecycle state as directed by orchestration.
13. Do not change Roadmap.

## 13. Documentation validation commands

Run from:

```text
C:\GPT\.worktrees\iteration-19-company-card-v2-contract-evidence
```

### 13.1. Baseline/status

```powershell
git status --short --branch
git rev-parse HEAD
```

Expected base:

```text
c3805dd1fbb8cdac38b1aa315e1f1e94597e7537
```

### 13.2. Exact manifest

```powershell
git diff --name-only c3805dd1fbb8cdac38b1aa315e1f1e94597e7537 --
```

Review output against the eleven-file allowlist in section 2.

Automated allowlist check:

```powershell
python -c "import subprocess,sys; allowed={'docs/development/iterations/iteration-19-company-card-v2-contract-evidence.md','docs/development/plans/iteration-19-company-card-v2-contract-evidence.md','docs/development/DEVFLOW_STATE.yaml','docs/development/evidence/iteration-19-company-card-v2/provider-field-manifest-v1.md','docs/development/evidence/iteration-19-company-card-v2/finance-unit-evidence-v1.md','docs/development/evidence/iteration-19-company-card-v2/arbitration-contract-evidence-v1.md','docs/development/decisions/iteration-19-company-card-v2-architecture.md','docs/development/decisions/iteration-19-company-card-v2-privacy.md','docs/development/wireframes/iteration-19-company-card-v2/desktop.svg','docs/development/wireframes/iteration-19-company-card-v2/tablet.svg','docs/development/wireframes/iteration-19-company-card-v2/mobile.svg'}; changed=set(subprocess.check_output(['git','diff','--name-only','c3805dd1fbb8cdac38b1aa315e1f1e94597e7537','--'],text=True).splitlines()); bad=sorted(changed-allowed); print('\n'.join(bad)); sys.exit(bool(bad))"
```

### 13.3. No runtime and no Roadmap diff

```powershell
git diff --exit-code c3805dd1fbb8cdac38b1aa315e1f1e94597e7537 -- services/product_api services/gateway_api services/web_ui shared deploy .github
git diff --exit-code c3805dd1fbb8cdac38b1aa315e1f1e94597e7537 -- docs/development/ROADMAP.md README.md
```

Both commands must produce no diff.

### 13.4. Whitespace/YAML

```powershell
git diff --check c3805dd1fbb8cdac38b1aa315e1f1e94597e7537 --
python -c "from pathlib import Path; import yaml; data=yaml.safe_load(Path('docs/development/DEVFLOW_STATE.yaml').read_text(encoding='utf-8')); assert data"
```

### 13.5. SVG/XML

```powershell
python -c "from pathlib import Path; from xml.etree import ElementTree as ET; files=sorted(Path('docs/development/wireframes/iteration-19-company-card-v2').glob('*.svg')); assert len(files)==3; [ET.parse(path) for path in files]"
```

Required view labels:

```powershell
rg -n "F1|F2|F3|F4|F5|A1|A2|A3|A4|A5|Вам задолжали\\?|Создать претензию" docs/development/wireframes/iteration-19-company-card-v2
```

Each file must contain all required IDs and CTA copy.

### 13.6. Contract decision presence

```powershell
rg -n "public-h2|company_public_h2_v1|report_version=.3.|datanewton_finance_thousand_rub_v1|page_size.?=.?100|max_pages.?=.?10|1000|8 MiB|400.?700|#EE5A2A|показано N из M" docs/development/iterations/iteration-19-company-card-v2-contract-evidence.md docs/development/decisions/iteration-19-company-card-v2-architecture.md
```

### 13.7. Privacy review

Review the docs-only diff without printing raw source files:

```powershell
git diff --stat c3805dd1fbb8cdac38b1aa315e1f1e94597e7537 --
git diff --word-diff=porcelain c3805dd1fbb8cdac38b1aa315e1f1e94597e7537 -- docs/development/evidence docs/development/decisions docs/development/wireframes
```

Reviewer must verify:

- no real 10/12-digit identifiers;
- no company/case/party names from raw evidence;
- no raw amounts or identifier-bearing URLs;
- no token, API key, Authorization header or `.env` value;
- no contacts/personal IDs;
- no raw JSON payload.

### 13.8. Required-file existence

```powershell
python -c "from pathlib import Path; files=['docs/development/iterations/iteration-19-company-card-v2-contract-evidence.md','docs/development/plans/iteration-19-company-card-v2-contract-evidence.md','docs/development/evidence/iteration-19-company-card-v2/provider-field-manifest-v1.md','docs/development/evidence/iteration-19-company-card-v2/finance-unit-evidence-v1.md','docs/development/evidence/iteration-19-company-card-v2/arbitration-contract-evidence-v1.md','docs/development/decisions/iteration-19-company-card-v2-architecture.md','docs/development/decisions/iteration-19-company-card-v2-privacy.md','docs/development/wireframes/iteration-19-company-card-v2/desktop.svg','docs/development/wireframes/iteration-19-company-card-v2/tablet.svg','docs/development/wireframes/iteration-19-company-card-v2/mobile.svg']; missing=[f for f in files if not Path(f).is_file()]; print('\n'.join(missing)); raise SystemExit(bool(missing))"
```

## 14. Runtime checks not applicable

Because the exact manifest contains no runtime code:

- Product API pytest is not required for this iteration;
- Gateway pytest is not required;
- frontend lint/test/build is not required;
- Alembic is not run;
- production or disposable PostgreSQL is not used.

The final report must not claim these checks were executed.

No-runtime-diff commands, XML/YAML parsing, evidence/privacy review and `git diff --check` are mandatory.

## 15. Independent review handoff

The independent reviewer receives:

1. specification;
2. implementation plan;
3. complete eleven-file diff;
4. provider field manifest;
5. finance evidence state and, if authorized, sanitized matrix;
6. arbitration evidence;
7. architecture ADR;
8. privacy ADR;
9. all three SVGs;
10. exact validation commands/results;
11. explicit no-runtime/Roadmap diff result;
12. list of gate states and blockers.

Reviewer must answer:

- Is H1 unchanged?
- Is `public-h2/company_public_h2_v1` exact?
- Does v3 writer avoid breaking H1?
- Can H1/H2 pins coexist and roll back?
- Are all fields sourced or gated?
- Is finance unit still blocked unless exact matrix passed?
- Are all ten algorithms deterministic?
- Are cap/dedup/role/outcome/currency/calendar decisions complete?
- Are privacy transformations consistent across all public surfaces?
- Can AI or provider be reached on GET/SSR/takeover?
- Is embedded state strict/script-safe and H2-only?
- Do wireframes show all views/states/placements without overlap?
- Is the diff free of runtime/raw/PII/secrets?

A `CHANGES_REQUIRED` verdict gets only the single DevFlow correction pass allowed by repository workflow.

## 16. Completion and handoff boundary

The documentation implementer stops after:

- exact manifest completion;
- applicable validation success;
- privacy inspection;
- evidence gate recording;
- independent review handoff.

This plan contains no implementer commit, push or merge step. Merge remains a human action under repository workflow.

Iteration 19 is ready only when:

- independent review has no blocking/substantial finding;
- `git diff --check` passes;
- no runtime/Roadmap diff exists;
- all three SVGs parse;
- raw/PII/secrets are absent;
- finance gate outcome is explicit;
- downstream blockers are preserved when evidence is unverified.

## 17. Historical stopped-run integration record (non-authoritative)

This section records requirements from the previous stopped DevFlow run. It is
not the current plan or approval status. The current authoritative corpus is
section 22 together with the corrected primary specification sections.

The following items are not deferred:

1. Copy the complete leaf-level DTO, cardinalities, sizes and invariants into
   the architecture ADR in a compact traceability table.
2. Add `company_public_h2_cjson_v1`, digest exclusion and canonical/script-safe
   byte distinction to the architecture ADR.
3. Record the one-active-job-per-subject exact-match reuse/conflict decision.
4. Record the legacy versus presentation lifecycle/read predicates and HTTP
   matrix.
5. Record immutable pin generations, composite assignment FK/CAS and exact H2
   indexability policy.
6. Record Product API-owned document selection, dedicated no-Webvisor H2 asset
   manifest and deploy/rollback order.
7. Keep arbitration total and visible-case-number paths `NOT_VERIFIED` until
   field evidence binds them.
8. Record the exact arbitration processing/cap/privacy/date/alias algorithms.
9. Use strengthened field-level finance matrix pass/fail; aggregate counts
   alone cannot pass.
10. Record durable AI generation/reservation/dispatch/fallback state.
11. Use the corrected manifest/privacy validation in section 18.
12. Perform per-SVG structural render and visual QA in section 19.
13. Preserve per-iteration verification ownership in section 20.

Historical status note: that run ended its planning correction at
`corrected_ready_for_root_verification`, was later approved as
the prior corrected plan, then failed final docs review and stopped.
Neither value is authoritative for this fresh run and neither consumes its
single correction allowance.

## 18. Corrected exact-manifest and privacy validation

This section replaces sections 13.2, 13.3, 13.7 and 13.8 wherever their
commands are less strict.

### 18.1. Exact eleven paths from tracked plus untracked state

PowerShell-safe command:

```powershell
python -c "import subprocess,sys; base='c3805dd1fbb8cdac38b1aa315e1f1e94597e7537'; expected={'docs/development/DEVFLOW_STATE.yaml','docs/development/iterations/iteration-19-company-card-v2-contract-evidence.md','docs/development/plans/iteration-19-company-card-v2-contract-evidence.md','docs/development/evidence/iteration-19-company-card-v2/provider-field-manifest-v1.md','docs/development/evidence/iteration-19-company-card-v2/finance-unit-evidence-v1.md','docs/development/evidence/iteration-19-company-card-v2/arbitration-contract-evidence-v1.md','docs/development/decisions/iteration-19-company-card-v2-architecture.md','docs/development/decisions/iteration-19-company-card-v2-privacy.md','docs/development/wireframes/iteration-19-company-card-v2/desktop.svg','docs/development/wireframes/iteration-19-company-card-v2/tablet.svg','docs/development/wireframes/iteration-19-company-card-v2/mobile.svg'}; tracked=set(filter(None,subprocess.check_output(['git','diff','--name-only',base,'--'],text=True).splitlines())); untracked=set(filter(None,subprocess.check_output(['git','ls-files','--others','--exclude-standard'],text=True).splitlines())); actual=tracked|untracked; missing=sorted(expected-actual); extra=sorted(actual-expected); print('MISSING'); print('\n'.join(missing)); print('EXTRA'); print('\n'.join(extra)); sys.exit(1 if missing or extra else 0)"
```

This is an exact set comparison, not a prefix/directory allowlist. Both
`MISSING` and `EXTRA` must be empty.

For reviewer-readable inventory:

```powershell
git diff --name-only c3805dd1fbb8cdac38b1aa315e1f1e94597e7537 --
git ls-files --others --exclude-standard
```

### 18.2. No runtime, Roadmap or README path

The exact-set command is the primary no-runtime proof. Also run:

```powershell
git diff --exit-code c3805dd1fbb8cdac38b1aa315e1f1e94597e7537 -- services/product_api services/gateway_api services/web_ui shared deploy .github docs/development/ROADMAP.md README.md
```

And verify no untracked forbidden path:

```powershell
python -c "import subprocess,sys; prefixes=('services/product_api/','services/gateway_api/','services/web_ui/','shared/','deploy/','.github/'); exact={'docs/development/ROADMAP.md','README.md'}; paths=set(filter(None,subprocess.check_output(['git','ls-files','--others','--exclude-standard'],text=True).splitlines())); bad=sorted(p for p in paths if p in exact or p.startswith(prefixes)); print('\n'.join(bad)); sys.exit(bool(bad))"
```

### 18.3. Whitespace for tracked and untracked manifest members

Run the required git check:

```powershell
git diff --check -- docs/development/DEVFLOW_STATE.yaml docs/development/iterations/iteration-19-company-card-v2-contract-evidence.md docs/development/plans/iteration-19-company-card-v2-contract-evidence.md docs/development/evidence/iteration-19-company-card-v2/provider-field-manifest-v1.md docs/development/evidence/iteration-19-company-card-v2/finance-unit-evidence-v1.md docs/development/evidence/iteration-19-company-card-v2/arbitration-contract-evidence-v1.md docs/development/decisions/iteration-19-company-card-v2-architecture.md docs/development/decisions/iteration-19-company-card-v2-privacy.md docs/development/wireframes/iteration-19-company-card-v2/desktop.svg docs/development/wireframes/iteration-19-company-card-v2/tablet.svg docs/development/wireframes/iteration-19-company-card-v2/mobile.svg
```

Because `git diff --check` does not inspect wholly untracked files, also scan
the exact eleven paths without modifying the index:

```powershell
python -c "from pathlib import Path; files=['docs/development/DEVFLOW_STATE.yaml','docs/development/iterations/iteration-19-company-card-v2-contract-evidence.md','docs/development/plans/iteration-19-company-card-v2-contract-evidence.md','docs/development/evidence/iteration-19-company-card-v2/provider-field-manifest-v1.md','docs/development/evidence/iteration-19-company-card-v2/finance-unit-evidence-v1.md','docs/development/evidence/iteration-19-company-card-v2/arbitration-contract-evidence-v1.md','docs/development/decisions/iteration-19-company-card-v2-architecture.md','docs/development/decisions/iteration-19-company-card-v2-privacy.md','docs/development/wireframes/iteration-19-company-card-v2/desktop.svg','docs/development/wireframes/iteration-19-company-card-v2/tablet.svg','docs/development/wireframes/iteration-19-company-card-v2/mobile.svg']; missing=[p for p in files if not Path(p).is_file()]; bad=[]; [(bad.append(f'{p}:{n}:trailing-whitespace') if line.rstrip('\r\n').endswith((' ','\t')) and not (p.endswith('.md') and line.rstrip('\r\n').endswith('  ')) else None) for p in files if Path(p).is_file() for n,line in enumerate(Path(p).read_text(encoding='utf-8').splitlines(keepends=True),1)]; print('\n'.join(missing+bad)); raise SystemExit(bool(missing or bad))"
```

Markdown hard line breaks of exactly two trailing spaces are permitted;
tabs/other trailing whitespace are not.

### 18.4. Privacy/secret scan over every manifest file

The scanner reports only path, line and rule name, never the suspected value:

```powershell
$iteration19ManifestFiles = @(
    'docs/development/DEVFLOW_STATE.yaml'
    'docs/development/iterations/iteration-19-company-card-v2-contract-evidence.md'
    'docs/development/plans/iteration-19-company-card-v2-contract-evidence.md'
    'docs/development/evidence/iteration-19-company-card-v2/provider-field-manifest-v1.md'
    'docs/development/evidence/iteration-19-company-card-v2/finance-unit-evidence-v1.md'
    'docs/development/evidence/iteration-19-company-card-v2/arbitration-contract-evidence-v1.md'
    'docs/development/decisions/iteration-19-company-card-v2-architecture.md'
    'docs/development/decisions/iteration-19-company-card-v2-privacy.md'
    'docs/development/wireframes/iteration-19-company-card-v2/desktop.svg'
    'docs/development/wireframes/iteration-19-company-card-v2/tablet.svg'
    'docs/development/wireframes/iteration-19-company-card-v2/mobile.svg'
)

$allowedDigestPattern = [regex]::new(
    '(?i)(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{64}|[0-9A-Fa-f]{40})(?![0-9A-Fa-f])'
)
$identifierPattern = [regex]::new(
    '(?<![0-9])(?:[0-9]{12}|[0-9]{10})(?![0-9])'
)

function Test-Iteration19Identifier([string] $Text) {
    $withoutAllowedDigests = $allowedDigestPattern.Replace($Text, '')
    return $identifierPattern.IsMatch($withoutAllowedDigests)
}

function Join-Iteration19Repeated([string] $Character, [int] $Count) {
    return (($Character * $Count) -join '')
}

# Positive probes include a leading zero and alphabetic surroundings. They prove
# digit boundaries, rather than hexadecimal boundaries, for both valid lengths.
$positiveProbes = @(
    ('x' + '0' + (Join-Iteration19Repeated '1' 9) + 'y')
    ('x' + '0' + (Join-Iteration19Repeated '2' 11) + 'y')
)
for ($index = 0; $index -lt $positiveProbes.Count; $index++) {
    if (-not (Test-Iteration19Identifier $positiveProbes[$index])) {
        throw "privacy-self-probe:positive-$($index + 1)-not-detected"
    }
}

# The first two negative probes are whole 40/64-hex digests containing a
# bounded 10/12-digit run before scrubbing. The rest prove length boundaries.
$negativeProbes = @(
    ('a' + '0' + (Join-Iteration19Repeated '3' 9) +
        (Join-Iteration19Repeated 'b' 29))
    ('c' + '0' + (Join-Iteration19Repeated '4' 11) +
        (Join-Iteration19Repeated 'd' 51))
    ('x' + (Join-Iteration19Repeated '5' 9) + 'y')
    ('x' + (Join-Iteration19Repeated '6' 11) + 'y')
    ('x' + (Join-Iteration19Repeated '7' 13) + 'y')
)
for ($index = 0; $index -lt $negativeProbes.Count; $index++) {
    if (Test-Iteration19Identifier $negativeProbes[$index]) {
        throw "privacy-self-probe:negative-$($index + 1)-unexpected-detection"
    }
}

$otherRules = [ordered]@{
    bearer = [regex]::new(
        '(?i)bearer[ \t]+[A-Za-z0-9._~+/=-]{8,}'
    )
    secret_assignment = [regex]::new(
        '(?i)(?:api[_-]?key|token|secret|password)[ \t]*[:=][ \t]*["'']?[A-Za-z0-9._~+/=-]{12,}'
    )
    private_key = [regex]::new(
        'BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY'
    )
    raw_json_marker = [regex]::new(
        '(?i)raw[_ -]?(?:payload|response)[ \t]*[:=][ \t]*(?:\{|\[)'
    )
}

$hits = [System.Collections.Generic.List[string]]::new()
foreach ($path in $iteration19ManifestFiles) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "privacy-scan:missing-manifest-file:$path"
    }

    $lineNumber = 0
    foreach ($line in [System.IO.File]::ReadLines(
        (Resolve-Path -LiteralPath $path).Path,
        [System.Text.Encoding]::UTF8
    )) {
        $lineNumber++
        $withoutAllowedDigests = $allowedDigestPattern.Replace($line, '')
        if ($identifierPattern.IsMatch($withoutAllowedDigests)) {
            $hits.Add("$path`:$lineNumber`:real_identifier")
        }
        foreach ($entry in $otherRules.GetEnumerator()) {
            if ($entry.Value.IsMatch($line)) {
                $hits.Add("$path`:$lineNumber`:$($entry.Key)")
            }
        }
    }
}

if ($hits.Count -ne 0) {
    $hits | Sort-Object -Unique | Write-Output
    throw "privacy-scan:failed:$($hits.Count)-rule-hits"
}
Write-Output 'privacy-scan:pass'
```

An empty result is necessary but not sufficient. A human/privacy reviewer also
checks every one of the eleven files for company/case/party names, raw amounts,
identifier-bearing URLs, contacts, personal IDs and copied provider text.

## 19. Per-SVG structural, render and visual QA

This section replaces section 13.5.

### 19.1. Individual structural validation

The validator checks each file separately:

```powershell
$wireframeRoot = 'docs/development/wireframes/iteration-19-company-card-v2'
$svgSpecs = @(
    [pscustomobject]@{
        Name = 'desktop.svg'; Prefix = 'desktop'; Width = 1440; Height = 4040
        RequireReserver = $false
    }
    [pscustomobject]@{
        Name = 'tablet.svg'; Prefix = 'tablet'; Width = 1024; Height = 4120
        RequireReserver = $true
    }
    [pscustomobject]@{
        Name = 'mobile.svg'; Prefix = 'mobile'; Width = 390; Height = 4800
        RequireReserver = $true
    }
)
$requiredStateText = @(
    'LONG'
    'EMPTY/MISSING'
    'PARTIAL'
    'returned/total'
    'NEGATIVE/MIXED SIGN/ZERO DENOMINATOR'
    'LARGE-N'
    'FOCUS/TOUCH'
    'NO OVERLAP'
)
$forbiddenElementNames = @('script', 'image', 'foreignobject')
$errors = [System.Collections.Generic.List[string]]::new()

foreach ($spec in $svgSpecs) {
    $path = Join-Path $wireframeRoot $spec.Name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        $errors.Add("$($spec.Name):missing-file")
        continue
    }

    $resolvedPath = (Resolve-Path -LiteralPath $path).Path
    $raw = [System.IO.File]::ReadAllText(
        $resolvedPath,
        [System.Text.Encoding]::UTF8
    )
    $xml = New-Object System.Xml.XmlDocument
    $xml.PreserveWhitespace = $true
    try {
        $xml.Load($resolvedPath)
    }
    catch {
        $errors.Add("$($spec.Name):xml-parse")
        continue
    }

    $root = $xml.DocumentElement
    if ($root.LocalName -cne 'svg' -or
        $root.NamespaceURI -cne 'http://www.w3.org/2000/svg') {
        $errors.Add("$($spec.Name):root-svg-namespace")
    }
    $expectedViewBox = "0 0 $($spec.Width) $($spec.Height)"
    if ($root.GetAttribute('viewBox') -cne $expectedViewBox) {
        $errors.Add("$($spec.Name):viewBox")
    }
    if ($root.GetAttribute('width') -cne [string] $spec.Width -or
        $root.GetAttribute('height') -cne [string] $spec.Height) {
        $errors.Add("$($spec.Name):native-size")
    }
    if ($root.GetAttribute('role') -cne 'img') {
        $errors.Add("$($spec.Name):role")
    }
    $expectedLabel = "$($spec.Prefix)-title $($spec.Prefix)-desc"
    if ($root.GetAttribute('aria-labelledby') -cne $expectedLabel) {
        $errors.Add("$($spec.Name):aria-labelledby")
    }

    $titleId = "$($spec.Prefix)-title"
    $descId = "$($spec.Prefix)-desc"
    $titleNode = $root.SelectSingleNode(
        "./*[local-name()='title' and @id='$titleId']"
    )
    $descNode = $root.SelectSingleNode(
        "./*[local-name()='desc' and @id='$descId']"
    )
    if ($null -eq $titleNode -or
        [string]::IsNullOrWhiteSpace($titleNode.InnerText)) {
        $errors.Add("$($spec.Name):accessible-title")
    }
    if ($null -eq $descNode -or
        [string]::IsNullOrWhiteSpace($descNode.InnerText)) {
        $errors.Add("$($spec.Name):accessible-desc")
    }

    $allElements = @($xml.SelectNodes('//*'))
    $idPositions = @{}
    for ($index = 0; $index -lt $allElements.Count; $index++) {
        $id = $allElements[$index].GetAttribute('id')
        if ([string]::IsNullOrEmpty($id)) {
            continue
        }
        if ($idPositions.ContainsKey($id)) {
            $errors.Add("$($spec.Name):duplicate-id:$id")
        }
        else {
            $idPositions[$id] = $index
        }
    }

    $orderedIds = @(
        "$($spec.Prefix)-hero-status"
        "$($spec.Prefix)-narrative"
        "$($spec.Prefix)-in-page-navigation"
        "$($spec.Prefix)-requisites"
        "$($spec.Prefix)-finance-f1"
        "$($spec.Prefix)-finance-f2"
        "$($spec.Prefix)-finance-f3"
        "$($spec.Prefix)-finance-f4"
        "$($spec.Prefix)-finance-f5"
        "$($spec.Prefix)-arbitration-a1"
        "$($spec.Prefix)-arbitration-a2"
        "$($spec.Prefix)-arbitration-a3"
        "$($spec.Prefix)-arbitration-a4"
        "$($spec.Prefix)-arbitration-a5"
        "$($spec.Prefix)-sources-limitations"
        "$($spec.Prefix)-neutral-actions"
    )
    if ($spec.RequireReserver) {
        $orderedIds += "$($spec.Prefix)-cta-reserver"
    }
    $orderedIds += "$($spec.Prefix)-primary-cta"

    $previousPosition = -1
    foreach ($id in $orderedIds) {
        if (-not $idPositions.ContainsKey($id)) {
            $errors.Add("$($spec.Name):missing-id:$id")
            continue
        }
        $node = $xml.SelectSingleNode("//*[@id='$id']")
        if ($node.LocalName -cne 'g') {
            $errors.Add("$($spec.Name):id-not-group:$id")
        }
        if ($idPositions[$id] -le $previousPosition) {
            $errors.Add("$($spec.Name):group-order:$id")
        }
        $previousPosition = $idPositions[$id]
    }

    $ctaHeadingCount = 0
    $ctaButtonCount = 0
    foreach ($textNode in @($xml.SelectNodes("//*[local-name()='text']"))) {
        if ($textNode.InnerText.Trim() -ceq 'Вам задолжали?') {
            $ctaHeadingCount++
        }
        if ($textNode.InnerText.Trim() -ceq 'Создать претензию') {
            $ctaButtonCount++
        }
    }
    $ctaId = "$($spec.Prefix)-primary-cta"
    $ctaNode = $xml.SelectSingleNode("//*[@id='$ctaId']")
    if ($ctaHeadingCount -ne 1 -or $ctaButtonCount -ne 1 -or
        $null -eq $ctaNode -or
        -not $ctaNode.InnerText.Contains('Вам задолжали?') -or
        -not $ctaNode.InnerText.Contains('Создать претензию')) {
        $errors.Add("$($spec.Name):cta-copy-placement")
    }
    if (-not $raw.Contains('#EE5A2A') -or
        -not $raw.ToUpperInvariant().Contains('DARK TEXT')) {
        $errors.Add("$($spec.Name):cta-color-contrast-callout")
    }
    foreach ($requiredText in $requiredStateText) {
        if (-not $raw.Contains($requiredText)) {
            $errors.Add("$($spec.Name):missing-state:$requiredText")
        }
    }

    foreach ($node in $allElements) {
        if ($forbiddenElementNames -contains $node.LocalName.ToLowerInvariant()) {
            $errors.Add("$($spec.Name):forbidden-element:$($node.LocalName)")
        }
        foreach ($attribute in @($node.Attributes)) {
            if ($attribute.LocalName.ToLowerInvariant() -in @('href', 'src') -and
                $attribute.Value.Trim() -match '^(?i:https?:|//|data:)') {
                $errors.Add("$($spec.Name):external-resource-attribute")
            }
        }
    }
    $rawLower = $raw.ToLowerInvariant()
    foreach ($token in @('url(http', '@import', '@font-face',
            'http://', 'https://', 'data:')) {
        if ($rawLower.Contains($token)) {
            $errors.Add("$($spec.Name):external-resource-token:$token")
        }
    }
}

if ($errors.Count -ne 0) {
    $errors | Sort-Object -Unique | Write-Output
    throw "svg-structural-validation:failed:$($errors.Count)-rule-hits"
}
Write-Output 'svg-structural-validation:pass:3-files'
```

Exact viewBox requirements:

```text
desktop: 0 0 1440 4040
tablet:  0 0 1024 4120
mobile:  0 0 390 4800
```

Every file, not merely the directory union, must contain all ten view IDs,
exact CTA strings/color and all seven edge-state callouts. External scripts,
rasters, foreignObject, data URLs, remote hrefs/fonts/imports are forbidden.

### 19.2. Mandatory render-to-image

Use the locally installed `inkscape` when present. Otherwise use a locally
installed headless Edge/Chrome/Chromium with a temporary profile, a local
`file:` input, background networking disabled, and all DNS mapped to the
non-routable address. Lack of both renderer paths is a blocker, not an allowed
skip. Every output is rendered and verified at its exact native SVG size.

```powershell
$iteration19RenderDir = Join-Path $env:TEMP 'iteration-19-company-card-v2-wireframes'
New-Item -ItemType Directory -Force -Path $iteration19RenderDir | Out-Null

$renderSpecs = @(
    [pscustomobject]@{
        Name = 'desktop'; Width = 1440; Height = 4040
    }
    [pscustomobject]@{
        Name = 'tablet'; Width = 1024; Height = 4120
    }
    [pscustomobject]@{
        Name = 'mobile'; Width = 390; Height = 4800
    }
)
$wireframeRoot = 'docs/development/wireframes/iteration-19-company-card-v2'
$inkscapeCommands = @(Get-Command inkscape.exe, inkscape -ErrorAction SilentlyContinue)
$inkscapeCommand = $inkscapeCommands | Select-Object -First 1
$browserPath = $null

if ($null -eq $inkscapeCommand) {
    $browserCandidates = [System.Collections.Generic.List[string]]::new()
    foreach ($commandName in @('msedge.exe', 'chrome.exe', 'chromium.exe')) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($null -ne $command) {
            $browserCandidates.Add($command.Source)
        }
    }
    if ($env:ProgramFiles) {
        $browserCandidates.Add((Join-Path -Path $env:ProgramFiles -ChildPath 'Microsoft/Edge/Application/msedge.exe'))
        $browserCandidates.Add((Join-Path -Path $env:ProgramFiles -ChildPath 'Google/Chrome/Application/chrome.exe'))
    }
    $programFilesX86 = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
    if ($programFilesX86) {
        $browserCandidates.Add((Join-Path -Path $programFilesX86 -ChildPath 'Microsoft/Edge/Application/msedge.exe'))
        $browserCandidates.Add((Join-Path -Path $programFilesX86 -ChildPath 'Google/Chrome/Application/chrome.exe'))
    }
    $browserPath = $browserCandidates |
        Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
        Select-Object -First 1
    if ($null -eq $browserPath) {
        throw 'svg-render:no-local-inkscape-edge-chrome-or-chromium'
    }
}

foreach ($spec in $renderSpecs) {
    $svgRelativePath = Join-Path $wireframeRoot "$($spec.Name).svg"
    $svgPath = (Resolve-Path -LiteralPath $svgRelativePath).Path
    $pngPath = Join-Path $iteration19RenderDir "$($spec.Name).png"
    if (Test-Path -LiteralPath $pngPath) {
        Remove-Item -LiteralPath $pngPath -Force
    }

    $rendererExitCode = $null
    if ($null -ne $inkscapeCommand) {
        $inkscapeArguments = @(
            $svgPath
            '--export-area-page'
            "--export-filename=$pngPath"
            "--export-width=$($spec.Width)"
            "--export-height=$($spec.Height)"
        )
        & $inkscapeCommand.Source @inkscapeArguments
        $rendererExitCode = $LASTEXITCODE
    }
    else {
        $profilePath = Join-Path $iteration19RenderDir "browser-profile-$PID-$($spec.Name)"
        New-Item -ItemType Directory -Force -Path $profilePath | Out-Null
        $fileUri = ([System.Uri]::new($svgPath)).AbsoluteUri
        $browserArguments = @(
            '--headless=new'
            '--no-sandbox'
            '--disable-gpu'
            '--disable-breakpad'
            '--disable-crash-reporter'
            '--noerrdialogs'
            '--hide-scrollbars'
            '--force-device-scale-factor=1'
            '--disable-background-networking'
            '--disable-component-update'
            '--disable-sync'
            '--disable-default-apps'
            '--disable-domain-reliability'
            '--metrics-recording-only'
            '--no-first-run'
            '--no-default-browser-check'
            '--host-resolver-rules="MAP * 0.0.0.0"'
            '--disable-features=OptimizationHints,MediaRouter,AutofillServerCommunication'
            "--user-data-dir=$profilePath"
            "--window-size=$($spec.Width),$($spec.Height)"
            "--screenshot=$pngPath"
            $fileUri
        )
        $rendererProcess = Start-Process -FilePath $browserPath `
            -ArgumentList $browserArguments -Wait -PassThru -WindowStyle Hidden
        $rendererExitCode = $rendererProcess.ExitCode
    }
    if ($null -eq $rendererExitCode -or $rendererExitCode -ne 0) {
        throw "svg-render:$($spec.Name):renderer-exit-$rendererExitCode"
    }
}

Add-Type -AssemblyName System.Drawing
foreach ($spec in $renderSpecs) {
    $pngPath = Join-Path $iteration19RenderDir "$($spec.Name).png"
    $file = Get-Item -LiteralPath $pngPath -ErrorAction SilentlyContinue
    if ($null -eq $file -or $file.Length -le 0) {
        throw "svg-render:$($spec.Name):missing-or-empty-png"
    }

    $image = $null
    try {
        $image = [System.Drawing.Image]::FromFile($file.FullName)
        if ($image.Width -ne $spec.Width -or
            $image.Height -ne $spec.Height) {
            throw "svg-render:$($spec.Name):unexpected-png-size"
        }
    }
    catch {
        throw "svg-render:$($spec.Name):invalid-or-wrong-size-png"
    }
    finally {
        if ($null -ne $image) {
            $image.Dispose()
        }
    }
}
Write-Output 'svg-render:pass:3-native-size-pngs'
```

Rendered PNGs remain temporary/untracked.

### 19.3. Recorded visual QA

Inspect every rendered image at native size and zoom. Record pass/fail per file
for every row:

```text
content order and all F1–F5/A1–A5 visible
LONG wraps without clipping
EMPTY/MISSING is distinct from zero
PARTIAL includes returned/total
negative/mixed sign diverges around zero
zero/negative denominator state is explicit
large-N has exact shown N/M
focus/touch affordance is visible
CTA placement/copy/color is exact
fixed CTA reserver/safe-area prevents overlap
no page-wide horizontal overflow
```

All 30 file/state combinations must pass. A structural XML pass without
rendered visual inspection is insufficient.

## 20. Verification ownership and downstream handoff

Each implementation iteration owns its full relevant verification before its
review:

### Iteration 20

- public-h2 closed DTO/API/error/query/header matrix;
- H1/legacy and v1/v2/v3 golden/negative compatibility;
- writer cohort/profile, unique subject, reuse/conflict and flag flips;
- exact SQL read filters and presentation polling identity;
- v3 serialization/hash/persistence and immutable pin/assignment CAS;
- H2 eligibility/indexability;
- full arbitration cap/cap+1/bytes/dedup/privacy/date/alias tests;
- Claims v3 handoff and no-read-side-effect guards.

### Iteration 21

- durable reservation/job/lease/fence transitions;
- one-dispatch concurrency and ambiguous-timeout no-retry;
- final model-bound artifact identity;
- automatic validation;
- exact universal `fallback_profile_any_v1` 691-scalar golden, named
  `FallbackIdentityV1`, catalog-version generation-key fencing and catalog
  upgrade creating a new immutable generation;
- GET/SSR/crawler zero job/Gateway work.

### Iteration 22

- Python/TypeScript canonical/digest golden vectors;
- nonce/CSP and exactly one embedded DTO;
- closing-tag/control/Unicode/surrogate/long/byte-limit XSS tests;
- parse/digest failure leaves SSR and performs no mount/refetch;
- Product API plain/canonical resolver and current nginx/SPA separation;
- dedicated no-Webvisor H2 entrypoint/asset manifest;
- Product API/web deploy compatibility and rollback.

### Iteration 23

- complete F1–F5 missing/zero/conflict/gap/signed/denominator/precision matrix;
- exact backend display strings and geometry-only client math;
- keyboard/touch/text fallback and responsive component tests.

### Iteration 24

- complete A1–A5 full/partial/calendar/top-20/cap+1 matrix;
- role/outcome/currency/zero/equal/negative/missing cases;
- entity privacy/masking/alias/link/telemetry and nested N/M;
- keyboard/touch/text fallback and responsive component tests.

### Iteration 25

Only cross-layer and real-browser rollout gates:

- SSR/API/embedded/client end-to-end parity;
- 320/390/768/1024/1199/1200/1440, 200% zoom, keyboard, touch and reduced
  motion;
- real network observation for no read/crawler provider/AI and no Webvisor;
- asset/deploy compatibility rehearsal;
- canary/monitoring/CAS assignment/atomic H1 rollback;
- owner activation approval.

Iteration 25 does not waive or re-own a failed/missing iteration 20–24 unit,
contract or component test.

## 21. Historical corrected review handoff

The completed sole planning-correction handoff gave root verification:

- both documents at the then-current status
  `corrected_ready_for_root_verification`;
- one numbered mapping of the thirteen reviewer findings to exact sections;
- scoped whitespace result for these two files;
- no claim that evidence/ADR/SVG/runtime artifacts were implemented in this
  correction pass.

Root verification approved that historical corrected plan, but its final code/
docs review still returned `CHANGES_REQUIRED` and the run ended `blocked`.
Sections 17 and 21 are provenance of that stopped run, not the current status
or correction budget. The owner explicitly started this fresh DevFlow run; the
authoritative current status is the header `approved_after_fresh_restart` and
section 22.

## 22. Fresh restart — mandatory five-finding reconciliation

This section is the current implementation plan. It does not authorize
iteration 20, live/provider/FNS/DB/AI calls, runtime changes, ROADMAP/README,
migrations, deploy or CI. Existing exact eleven files remain the complete
manifest. All three SVGs must replace dynamic AI-fallback wording and
the legacy accessibility-fallback label, then be revalidated/rendered.

### 22.1. OKEI evidence row

Replace every old two-code OKEI shorthand and legacy year-token name with the
exact `FinanceEvidenceCellV1` from the specification and finance evidence:
closed `fns_okei_state`, nullable `fns_okei_code`, accepted/rejected invariants,
`reporting_year`, comparison/scale outcomes and two 64-hex provenance hashes.
No live matrix or raw rejected OKEI token is added. Finance unit remains
`UNVERIFIED/BLOCKED`.

### 22.2. Collection, calendar and zero-year proof

Persisted v3, Chart Facts/hash and public summary all carry separate
`collection_complete`, `calendar_complete`, calendar scope/bounds/evidence,
observed bounds, unknown-year count and `zero_years_proven`. Collection
completeness never depends on calendar evidence. Synthetic zero buckets require
explicit zero-year proof; otherwise A1 is observed-only and may contain the
unknown-year bucket. Evidence/manifest retain separate blocked collection,
calendar and zero-assertion gates.

### 22.3. Fallback identity

Add non-null `fallback_catalog_version` to `GenerationIdentityV1` and thus to
`generation_key`. Freeze exactly one v1 entry, `fallback_profile_any_v1`, and
define exact named-object `FallbackIdentityV1` with generation key, catalog,
profile, renderer and output hash. Catalog upgrade is a new generation and
cannot replace an existing binding. Tests/goldens use the one 691-scalar
literal only; plural coverage/profile compilation is forbidden.

### 22.4. Finance transport and geometry

Document `company_card_source_decimal_v1`: lexical JSON number/string capture
before float coercion, closed grammar/limits, direct finite Decimal parsing,
lossy-float rejection and canonical negative-zero behavior. Current runtime
does not prove that transport, so the capability remains `UNVERIFIED/BLOCKED`.
Replace universal geometry with axis/interval/point leaves: F2 and F4 use keyed
per-metric intervals with null axis/geometries for invalid denominators; F3 has
independent revenue/assets summaries, endpoints, axes and keyed points. Future
iteration-20/23 tests cover exponent/nonfinite/precision/float negatives,
signed/null geometry and sparse independent series. H1/v1/v2 remain unchanged.

### 22.5. HMAC and public IDs

Use exact closed enums and discriminated CJSON objects
`OpponentHmacIdentityV1`, `StableOpponentIdentifierV1` and
`CasePositionIdentifierV1`; HMAC is full 32-byte SHA-256 encoded as 64 lowercase
hex with a >=32-byte worker secret. Define `CasePublicOrderIdentityV1` and
`OpponentPublicOrderIdentityV1`, fixed sort bytes, one-based capped indices and
exact `case_[0-9]{6}` / `opponent_[0-9]{6}` encodings. Golden vectors recompute
the synthetic HMAC and order; public DTO/privacy scans prove no private value or
token leaks.

### 22.6. Implementation ownership and checks

The single planning correction has already rewritten the primary specification
and this current plan and removed the former override appendix before approval.
After this correction is self-verified, set spec/plan to
`approved_after_fresh_restart`, state to `implementing`, and update only the
remaining artifacts within the eleven-file manifest. Synchronize both ADRs,
all three evidence documents, provider manifest and SVG wording. Run exact
manifest/no-runtime, YAML/XML/UTF-8/whitespace/privacy checks, HMAC/fallback
goldens, stale-token search, SVG structural validation, native render and visual
QA. Runtime pytest, npm, Alembic, PostgreSQL, provider and AI commands remain
inapplicable and must not be claimed.

The privacy scanner is not weakened or allowlisted. The authoritative HMAC
golden uses the nonnumeric 43-byte test key
`iteration-nineteen-hmac-vector-key-material`, UUID
`a1b2c3d4-e5f6-4a7b-8c9d-a1b2c3d4e5f6` and digest
`21d8c54c7052e3112c6c748f3ae5fa545c121d23b37ca02561b2978b9f767220`.
Legacy `POST /company-reports` remains permanent H1/v2 and cohort-independent;
the H2-only presentation create/status lifecycle is separate, opaque and
default-off. No rollout assignment alone makes the H1 POST ineligible.

Plan reviewer must independently verify all five subsections and return exact
`VERDICT: APPROVED` or `VERDICT: CHANGES_REQUIRED`. This fresh run has one
planning-correction allowance. Commit/push remain forbidden until final docs
review returns `VERDICT: READY`; PR/merge are always manual.
