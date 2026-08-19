# Итерация 17 — Backend публичной проекции H1 CompanyReport

ID: 17
Slug: company-report-h1-backend
Статус спецификации: reviewed planning_input; runtime implementation не утверждена
Зависимость: merged iteration 16

После merge iteration 16 эта спецификация является source input для отдельного
DevFlow planning/plan-review на актуальном `main`. Она не заменяет финальный
утверждённый implementation plan/manifest итерации 17.

## 1. Цель

Реализовать strict computed projection company_public_h1_v1 и публичный
read-only endpoint поверх одного детерминированно выбранного immutable
CompanyReport snapshot. Расширить новые reports optional enrichments, сохранив
status/completeness/freshness трёх required datasets и чтение snapshot v1.

Source of truth:

    docs/development/iterations/iteration-16-company-report-h1-public-contract.md

## 2. Обязательные pre-implementation gates

Перед реализацией фиксируется versioned evidence registry:

| Capability | Required evidence | Disabled behavior |
| --- | --- | --- |
| Finance absolute values | finance_unit_evidence_v1 | provider_units_unknown; amounts absent |
| Tax facts | tax_info_schema_v1 | optional dataset not requested; schema_gate_not_passed limitation |
| Bankruptcy facts | bankruptcy_schema_v1 | optional dataset not requested; schema_gate_not_passed limitation |
| Manager public name | management_privacy_v1 | Managers absent; privacy_gate_not_passed limitation |
| Owners | owner_schema_v1 plus management_privacy_v1 | OWNER_BLOCK not requested; owners absent |
| Optional production calls | tariff/quota/pagination/retry/timeout/cache approval | calls disabled |

Official docs/support response or minimal safe fixtures are acceptable.
Production raw, contacts, secrets and unrelated PII are prohibited. A live
probe is a separate explicitly approved operation.

Gates are independent. For example, iteration 17 may ship the endpoint and
projection while finance amounts and optional enrichments remain disabled.

## 3. Required runtime invariants

Required datasets remain exactly:

    counterparty
    finance
    arbitration

Only their AVAILABLE count determines:

| Available required | Report status | Required completeness |
| ---: | --- | --- |
| 3 | complete | 3/3 |
| 1–2 | partial | 1/3 or 2/3 |
| 0 | failed | 0/3 |

Optional dataset state never changes the table. Optional facts cannot make a
failed report public and optional failure cannot downgrade a required-complete
report.

Existing CompanyReportCompleteness and ReportFreshness retain required-only
semantics. H1 source registry carries each optional source_received_at
separately.

## 4. Snapshot v2

Newly generated reports use report_version 2. Snapshot v2 adds:

    optional_datasets: dict[str, DatasetReport] = {}
    tax_info: TaxInfoFacts | null
    bankruptcy: BankruptcyFacts | null

The existing datasets mapping continues to contain only required datasets.
Counterparty owners remain a typed optional block of CounterpartyFacts and
carry an explicit block status.

Compatibility rules:

- snapshot v1 is immutable and parses as optional_datasets empty;
- v1 hashes are checked against the original stored JSON, not reserialized v2;
- no v1 rewrite/backfill occurs;
- DB columns already store a string report_version, so no schema migration is
  introduced;
- parser accepts v1 and v2; writer creates only v2 after rollout.
- enqueue, ORM record version and finalized snapshot version are set from one
  explicit constant; version mismatch remains a hard failure.

## 5. Optional execution and public state mapping

Enabled tax_info and bankruptcy calls may run in parallel with required calls,
but final lifecycle status is calculated only after required results and only
from required results.

| Runtime condition | Public state | Source timestamp |
| --- | --- | --- |
| Gate disabled or key absent | not_requested plus limitation when relevant | none |
| Provider explicit subject absence | not_found | none unless contract proves a safe source time |
| Successful normalized facts | available | source_received_at |
| Successful exact scoped zero | available_empty | source_received_at |
| returned lower than total | partial | source_received_at |
| Transport/normalization failure | failed | none |
| Dataset available but a field conflicts | dataset available; field conflict and fact hidden | source_received_at |

schema_gate_not_passed is a limitation code, not a new dataset state.

## 6. Public snapshot resolver

Один service-level resolver используется public SSR и endpoint:

1. Normalize and validate INN.
2. Read publication for subject.
3. If publication status is active, load only its pinned report_id.
4. Verify lifecycle, stored snapshot hash, publication snapshot hash, policy
   eligibility and canonical path.
5. Any invalid active pin fails closed with a safe internal error; it never
   falls back to latest.
6. If active publication is absent, load the latest eligible complete/partial
   snapshot with normalized data and exact identity; a newer failed/unusable
   run does not replace it. Mark it latest_unpublished/indexable=false.
7. If no eligible snapshot exists, distinguish no run, pending-only,
   finalized-failed and finalized-not-eligible before returning a safe error.
8. Build company_public_h1_v1 with no external calls or writes.

Controlled republish atomically changes publication report_id, snapshot hash,
canonical path/policy metadata and published_lastmod. Until commit, both SSR
and API continue to show the previous pin.

When there is no active publication, the SSR publication route remains
404/noindex; only API/SPA may render latest_unpublished. SSR/API equality is
therefore asserted for active published pages, while API/SPA equality is
asserted for unpublished pages.

## 7. Public endpoint

    GET /company-reports/{inn}/public-h1

Properties:

- public and anonymous; existing IP read rate limit applies;
- duplicate or any query parameter is rejected;
- does not call provider, AI, worker, enqueue, update publication or write DB;
- existing GET /company-reports/{inn} remains unchanged;
- response_model is strict CompanyPublicH1Response.

Error mapping:

| Condition | HTTP/code |
| --- | --- |
| Invalid INN | 400 invalid_inn |
| No report run of any lifecycle exists | 404 company_report_not_found |
| Only pending run | 409 report_pending |
| Finalized failed run exists and no older eligible snapshot exists | 409 report_failed |
| Finalized complete/partial run exists but identity/projection is not eligible and no older eligible snapshot exists | 409 report_not_eligible |
| Invalid active publication pin/projection | 500 public_projection_invalid |
| Persistence unavailable | 503 company_report_unavailable |

Only `404 company_report_not_found` authorizes the plain-INN frontend to call
the existing create endpoint. `409 report_pending` authorizes polling.
`report_failed` and `report_not_eligible` are terminal display states in H1 v1
and never trigger automatic create/refresh.

## 8. DTO contract

Serialized field topology, nullability, cardinality, enums, ordering and all
nested DTOs are normative in iteration 16, section 3.1. Iteration 17 may not
invent an alternative shape; any incompatible correction returns to
documentation review before implementation.

Top level:

    contract_version: company_public_h1_v1
    report_id: UUID
    report_version: 1 or 2
    projection_scope: published or latest_unpublished
    canonical_path: string
    indexable: boolean
    checked_at: UTC ISO datetime
    checked_date: ISO date
    checked_date_display: string
    identity: strict CompanyPublicIdentity
    block_order: strict PublicBlockId list
    blocks: strict nullable typed blocks
    coverage: PublicCoverageItem list
    sources: PublicSourceItem list
    limitations: PublicLimitation list
    actions: PublicAction list

Rules:

- no arbitrary dict in public DTO;
- Decimal exact values serialize as strings;
- checked_date/display follows checked_date_msk_v1 and Europe/Moscow;
- money display is generated only by an active unit policy in backend;
- source item contains dataset, received_at, optional period and public policy
  version, but no endpoint/hash/request ID/duration/error text;
- limitation contains allowlisted code, block/field reference and safe text;
- contacts, manager INNFL, FSSP, raw data, scoring, verdict, signals and AI are
  recursively prohibited.
- active publication policy_version dispatches a compatible H1 builder;
- new canonical paths use safe short name then full name; existing path changes
  only on republish;
- prepare_claim action uses the response report_id, never a separate latest
  lookup.

Neutral action allowlist:

| action_id | Meaning |
| --- | --- |
| check_another_company | Return to the existing INN entry surface |
| prepare_claim | Use the existing report-bound Claims handoff when eligible |

Actions contain only allowlisted id/label/path and never provider facts.

## 9. Domain normalization

### Finance

- Until finance_unit_evidence_v1, exact raw Decimal may remain internal but
  absolute values and money display are absent from H1.
- Unit-independent YoY may be emitted only from the same indicator/source
  series with explicit years and versioned formula.
- After evidence, only allowlisted monetary codes activate
  datanewton_finance_thousand_rub_v1.
- Scaling and display use Decimal; no float.

### Arbitration

- Match typed target INN and OGRN separately.
- Both party identifiers require both target identifiers and exact agreement.
- One available party identifier requires exact match of the same target type.
- Party-both/target-one is target_identity_incomplete and unattributed.
- Single allowlisted role is one bucket; multiple exact roles are other.
- Name-only/conflict/no exact match is unattributed.
- Missing parseable case identity or non-collection parties is malformed.
- A normalized case is counted at most once.

### Tax, bankruptcy and owners

- Normalizers consume only ProviderResult and remain pure.
- Raw paths are implemented only from approved evidence fixtures.
- Unknown bankruptcy type has no invented interpretation.
- Tax false wording is allowed only for a semantically proven scoped boolean.
- Owner share is public only with proven scale/currentness and privacy-safe
  subject classification.
- Manager name/role/date are public only under management_privacy_v1; otherwise
  manager person records are absent with privacy_gate_not_passed.
- Manager INNFL is never included in H1 v1.

## 10. Expected changed surfaces

Expected backend scope:

    services/product_api/src/product_api/company_reports/aggregate.py
    services/product_api/src/product_api/company_reports/models.py
    services/product_api/src/product_api/company_reports/provider_protocol.py
    services/product_api/src/product_api/company_reports/orchestrator.py
    services/product_api/src/product_api/company_reports/normalizers/
    services/product_api/src/product_api/company_reports/public_h1.py
    services/product_api/src/product_api/company_reports/schemas.py
    services/product_api/src/product_api/company_reports/service.py
    services/product_api/src/product_api/company_reports/seo.py
    services/product_api/src/product_api/company_reports/persistence/publications.py
    services/product_api/src/product_api/company_reports/persistence/repository.py
    services/product_api/src/product_api/company_reports/persistence/jobs.py
    services/product_api/src/product_api/routers/company_reports.py
    services/product_api/src/product_api/routers/company_reports_public.py
    services/product_api/src/product_api/settings.py
    services/product_api/.env.example
    targeted product_api unit/integration tests and safe fixtures

Final manifest создаёт и утверждает будущий DevFlow plan reviewer перед
implementation. Gateway, Claims semantics,
deployment, nginx, AI, signals and scoring are outside scope.

## 11. Test requirements

Unit:

- snapshot v1/v2 parsing, original-hash preservation and no rewrite;
- required-only status/completeness/freshness under every optional state;
- published/latest-unpublished resolver and fail-closed invalid pin;
- checked_at UTC plus Moscow boundary dates;
- strict DTO and recursive forbidden-key scan;
- finance disabled/enabled policy, Decimal boundaries and YoY;
- full arbitration identity/role/malformed matrix;
- schema-gated tax/bankruptcy/owners, manager privacy enabled/disabled and
  manager-INNFL prohibition cases.

Integration:

- public endpoint anonymous access and rejected query/auth assumptions;
- exact server classification: no runs → 404 company_report_not_found;
  pending-only → 409 report_pending; failed without older eligible → 409
  report_failed; complete/partial but ineligible without older eligible → 409
  report_not_eligible;
- an older eligible snapshot is returned instead of any newer failed/unusable
  run, without auto-create;
- pinned report_id parity with SSR;
- latest unpublished fallback is noindex;
- new finalized run does not replace active pin before republish;
- republish switches SSR/API together;
- read path performs no provider/job/publication write;
- legacy endpoints and snapshots remain compatible.

Required commands:

    python -m pytest services/product_api/tests_unit -q
    python -m pytest services/product_api/tests -q
    python -m pytest services/gateway_api/tests -q
    git diff --check

Gateway tests are regression-only; no Gateway behavior change is expected.

## 12. Out of scope

- React H1 page and visual design.
- Refresh button or TTL refresh.
- Contacts, FSSP, new score/verdict/AI facts.
- Production provider probes, migration, deploy or publication rollout.
- Claims legal semantics.

## 13. Acceptance

- All enabled facts have approved evidence and typed pure normalization.
- Required lifecycle remains three-dataset and legacy-compatible.
- For active publication, SSR and endpoint resolve one pinned report_id and one
  projection; for latest_unpublished, API/SPA resolve one report_id while SSR
  remains 404/noindex.
- DTO contains no forbidden facts or internal metadata.
- Disabled gates degrade to not_requested plus safe limitations.
- Targeted and regression checks pass; independent review has no blockers.
- Перед runtime отдельный DevFlow planning/review утверждает exact changed/test
  manifest на актуальном `main`; этот planning-input сам по себе не разрешает
  изменения кода.
