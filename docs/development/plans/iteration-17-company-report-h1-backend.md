# Итерация 17 — Backend H1: implementation plan

ID: `17`
Slug: `company-report-h1-backend`
Contract: `company_public_h1_v1`
Branch: `feat/iteration-17-company-report-h1-backend`
Base commit: `f4776595375a485732fff96053eb9362194f203a`
Статус плана: `approved`

Specification:

```text
docs/development/iterations/iteration-17-company-report-h1-backend.md
```

## 1. Implementation decisions

1. Выпустить полезный conservative H1 backend без ожидания внешних gates.
2. Не выполнять live/network evidence.
3. Не активировать optional calls или новые counterparty filters.
4. Добавить v2 snapshot envelope, но сохранять optional facts null/absent.
5. Сохранить existing signals/scoring/AI и legacy API behavior.
6. Реализовать arbitration exact attribution как отдельную H1 pure projection
   поверх сохранённых typed parties; legacy scoring summaries не менять.
7. Использовать новый isolated public-H1 service и DTO builder, а existing
   `seo.py` оставить publication-policy compatibility layer.
8. Использовать existing publication tables; migration не создавать.
9. Renderer принимает готовый H1 DTO, чтобы SSR/API не интерпретировали snapshot
   независимо.
10. Plan реализуется одним implementer pass с production code и tests вместе.

## 2. Exact changed-file manifest

### 2.1. Documentation/state

| File | Change |
| --- | --- |
| `docs/development/iterations/iteration-17-company-report-h1-backend.md` | Approved final specification. |
| `docs/development/plans/iteration-17-company-report-h1-backend.md` | Approved implementation plan. |
| `docs/development/DEVFLOW_STATE.yaml` | DevFlow status transitions only; preserve unknown fields. |
| `README.md` | Document anonymous H1 read, v2 compatibility and no-side-effect behavior. |

`docs/development/ROADMAP.md` не меняется.

### 2.2. Domain and serialization

| File | Change |
| --- | --- |
| `services/product_api/src/product_api/company_reports/aggregate.py` | Add current version constant, `"1"|"2"`, optional envelope/facts, explicit required-key lifecycle validator. |
| `services/product_api/src/product_api/company_reports/models.py` | Add provider-neutral inactive optional fact types and additive arbitration role-party/malformed evidence fields. |
| `services/product_api/src/product_api/company_reports/normalizers/arbitration.py` | Preserve all existing role-specific party collections and malformed metadata; no raw payload persistence. |
| `services/product_api/src/product_api/company_reports/orchestrator.py` | Emit v2, keep exactly three existing provider calls and required-only freshness/completeness. |
| `services/product_api/src/product_api/company_reports/persistence/serialization.py` | Version-aware v1/v2 parser/writer and original v1 hash preservation. |
| `services/product_api/src/product_api/company_reports/persistence/repository.py` | Use shared current version default and keep dataset rows required-only. |
| `services/product_api/src/product_api/company_reports/persistence/jobs.py` | Enqueue pending records with shared current version. |
| `services/product_api/src/product_api/company_reports/persistence/publications.py` | Fail-closed batch/ORM/snapshot integrity before publication evaluation/upsert. |
| `services/product_api/src/product_api/company_reports/schemas.py` | Legacy response accepts report versions 1 and 2 without exposing optional H1 facts. |
| `services/product_api/src/product_api/company_reports/explanation/models.py` | Accept report versions 1 and 2 without expanding explanation facts. |
| `services/product_api/src/product_api/company_reports/__init__.py` | Intentional exports for new version/domain types used by tests. |

No change to provider protocol/client/settings because optional calls are
disabled.

### 2.3. Evidence, projection and resolver

| File | Change |
| --- | --- |
| `services/product_api/src/product_api/company_reports/evidence.py` | New immutable evidence registry with enabled/disabled gates. |
| `services/product_api/src/product_api/company_reports/public_h1.py` | New strict DTOs, pure projection, coverage/source/limitation policies, date/Decimal formatting and DTO-only HTML renderer. |
| `services/product_api/src/product_api/company_reports/public_h1_service.py` | New typed resolver/service, active pin validation, latest eligible fallback and error classification. |
| `services/product_api/src/product_api/company_reports/persistence/public_h1.py` | New read-only outer-join publication lookup and ordered report-history query records. |
| `services/product_api/src/product_api/company_reports/persistence/__init__.py` | Export only resolver read records/functions needed by service. |
| `services/product_api/src/product_api/routers/company_reports.py` | Add anonymous `GET /{inn}/public-h1`, query rejection, rate limit, exact error/headers. |
| `services/product_api/src/product_api/routers/company_reports_public.py` | Use shared H1 resolver/DTO renderer for canonical SSR and shared pin validator for sitemap. |

No change to `main.py`: both existing routers are already registered.

### 2.4. Safe fixtures

| File | Change |
| --- | --- |
| `services/product_api/tests_unit/fixtures/company_reports/public_h1_v1_expected.json` | New synthetic expected DTO golden fixture with no raw/contacts/PII. |
| `services/product_api/tests_unit/fixtures/company_reports/snapshot_v1_legacy.json` | Minimal synthetic immutable v1 compatibility fixture with fixed hash expectation. |
| `services/product_api/tests_unit/fixtures/datanewton/arbitration_success.json` | Minimal sanitized role-party/currency/malformed shapes for approved normalizer/H1 tests. |

No other fixture may change. No tax/bankruptcy/owner live-shaped fixture is
added without evidence gate.

### 2.5. Unit tests

New files:

```text
services/product_api/tests_unit/test_company_report_evidence.py
services/product_api/tests_unit/test_company_report_public_h1.py
services/product_api/tests_unit/test_company_report_public_h1_service.py
```

Updated files:

```text
services/product_api/tests_unit/test_company_report_aggregate_models.py
services/product_api/tests_unit/test_company_report_arbitration_normalizer.py
services/product_api/tests_unit/test_company_report_orchestrator_success.py
services/product_api/tests_unit/test_company_report_orchestrator_partial.py
services/product_api/tests_unit/test_company_report_persistence_serialization.py
services/product_api/tests_unit/test_company_report_repository_finalize.py
services/product_api/tests_unit/test_company_report_repository_pending.py
services/product_api/tests_unit/test_company_report_jobs.py
services/product_api/tests_unit/test_company_report_publications.py
services/product_api/tests_unit/test_company_report_service.py
services/product_api/tests_unit/test_company_report_api_schemas.py
services/product_api/tests_unit/test_company_reports_api.py
services/product_api/tests_unit/test_company_report_public_routes.py
services/product_api/tests_unit/test_company_report_explanation_models.py
services/product_api/tests_unit/test_company_report_explanation_validation.py
services/product_api/tests_unit/test_company_report_explanation_service.py
services/product_api/tests_unit/company_report_signal_test_helpers.py
```

Helpers изменяются только для explicit report version и synthetic H1 fixtures.

### 2.6. PostgreSQL integration tests

Updated:

```text
services/product_api/tests/test_company_reports_api.py
services/product_api/tests/test_company_report_jobs.py
services/product_api/tests/test_company_report_publications.py
services/product_api/tests/test_claims_company_report_handoff.py
```

No migration test is added because DB schema is unchanged.

### 2.7. Explicitly unchanged surfaces

```text
services/product_api/alembic/versions/*
services/product_api/src/product_api/providers/*
services/product_api/src/product_api/settings.py
services/product_api/.env.example
services/product_api/src/product_api/company_reports/provider_protocol.py
services/product_api/src/product_api/company_reports/seo.py
services/product_api/src/product_api/company_reports/seo_publish.py
services/product_api/src/product_api/company_reports/worker.py
services/product_api/src/product_api/company_reports/signals/*
services/product_api/src/product_api/company_reports/scoring/*
services/product_api/src/product_api/company_reports/explanation/__init__.py
services/product_api/src/product_api/company_reports/explanation/catalog.py
services/product_api/src/product_api/company_reports/explanation/prompt.py
services/product_api/src/product_api/company_reports/explanation/service.py
services/product_api/src/product_api/company_reports/explanation/validation.py
services/product_api/src/product_api/claims/*
services/gateway_api/*
services/web_ui/*
deploy/*
.github/workflows/*
docker-compose*.yml
```

Если implementation требует изменение этой unchanged list, implementer
останавливается и возвращает blocker вместо scope expansion.

## 3. Stage A — lock evidence and tests first

1. Создать `evidence.py` с frozen registry entries.
2. Внести enabled entries только для existing counterparty core/address-read,
   finance normalized-series и arbitration stored-party evidence.
3. Зафиксировать disabled:
   - finance unit;
   - tax schema/call;
   - bankruptcy schema/call;
   - manager privacy/call;
   - owner schema/privacy/call;
   - contacts;
   - FSSP.
4. Не читать env и не добавлять runtime toggle, который может активировать gate.
5. Добавить tests:
   - entry uniqueness;
   - evidence path existence;
   - disabled gate immutability;
   - zero optional provider calls;
   - forbidden capability registry state.

Stage completion:

- registry deterministic;
- нет unsupported enabled gate;
- provider surface не расширен.

## 4. Stage B — snapshot v2 compatibility

1. В `aggregate.py` добавить:

```python
CURRENT_COMPANY_REPORT_VERSION = "2"
REQUIRED_DATASETS = ("counterparty", "finance", "arbitration")
OPTIONAL_DATASETS = ("tax_info", "bankruptcy")
```

`REQUIRED_DATASETS` импортируется из одного места; duplicate constants
удаляются или становятся alias без расходящейся семантики.

2. Расширить `CompanyReport.report_version` до `"1"|"2"`.
3. Добавить v2 fields/defaults.
4. Validator:
   - требует exact required key set в `datasets`;
   - считает status только по required tuple;
   - optional map не участвует;
   - optional keys ограничены allowlist.
5. Создать provider-neutral optional models, но не создавать normalizers.
6. Обновить writer/parser:
   - parser до Pydantic/defaults требует raw key `report_version`, exact
     Python string type и value `"1"|"2"`;
   - missing/null/boolean/numeric/unknown discriminator reject before model;
   - untouched raw snapshot hashes before parse/version dispatch;
   - v1 может omit только additive v2 fields, но не discriminator;
   - v1 output omits v2 defaults;
   - v2 output explicitly includes envelope/nulls;
   - raw original snapshot is hash source before parse.
7. Использовать current version в:
   - `build_company_report`;
   - `create_pending_report`;
   - `enqueue_company_report_job`.
8. Оставить `finalize_report` mismatch hard.
9. `company_report_datasets` persistence loop продолжает читать только
   `report.datasets`.
10. Legacy API schema принимает both version strings, but DTO topology
    unchanged.
11. Claim/precondition до provider boundary отклоняет reused pending v1
    при current writer v2; safe terminal state conflict, provider calls `0`, no
    silent upgrade. После terminal failure обычный lifecycle может создать
    fresh v2 run.
12. В `explanation/models.py` расширить только
    `ExplanationInputEnvelope.report_version` до `Literal["1", "2"]`.
    Explanation fact schema/prompt/eligibility/privacy allowlists не менятся;
    optional H1 facts не попадают в envelope.

Stage tests:

- fixed v1 fixture/hash;
- missing, non-string and unknown raw discriminator rejection before defaults;
- v1 parse/serialize/hash/no-mutation;
- v2 deterministic round trip;
- version alignment enqueue/build/finalize;
- mismatch rollback/state conflict;
- exhaustive optional state vs required lifecycle matrix;
- optional timestamps excluded from required freshness.
- pending v1 rejected before provider with fail-if-called provider;
- explanation v1/v2 accepted, missing/unknown rejected, optional H1 facts absent.

Stage completion:

- old snapshots readable;
- new writer v2;
- no migration;
- no lifecycle regression.

## 5. Stage C — additive arbitration evidence

1. В `ArbitrationCaseFacts` добавить default-empty lists:
   - applicants;
   - creditors;
   - debtors;
   - interested persons;
   - third parties;
   - other parties.
2. Добавить tri-state/explicit collection-valid marker appropriate for v1
   default and v2 normalized records.
3. В `ArbitrationFacts` добавить malformed raw-entry count default for v1.
4. `normalize_arbitration`:
   - сохраняет normalized parties из всех existing provider containers;
   - не меняет raw path assumptions;
   - не сохраняет raw payload;
   - non-list party container marks case attribution evidence invalid;
   - non-object raw case increments malformed count;
   - сохраняет existing legacy fields/summaries.
5. Не менять signals/scoring rules.
6. В `public_h1.py` реализовать pure attribution from typed target identity and
   stored party collections.
7. Для v1:
   - verify plaintiff/respondent from existing lists;
   - unsupported role detail stays unattributed;
   - add legacy limitation.
8. Реализовать status/result/amount/selection counts over public normalized
   cases.
9. Assert count invariants before DTO creation.

Stage tests use table matrix from specification.

Stage completion:

- one case/one bucket;
- no name matching;
- no cross-type matching;
- legacy scoring behavior stays regression-compatible.

## 6. Stage D — strict H1 projection

### 6.1. DTOs

В `public_h1.py` определить strict Pydantic models for every iteration-16
topology node. No `dict[str, Any]` in public fact DTO.

`PublicMoney`, tax, bankruptcy, management/owner и `PublicInternalLink` strict
DTOs MUST exist exactly as iteration 16 even while runtime blocks are null.
`FinanceBlock.unit_policy_version`, `FinanceMetric.money` и
`FinanceMetric.yoy` retain their approved nullable schema types; disabled-gate
behavior is enforced by the builder, not by narrowing the contract.

Validators restore exact 10/12 ASCII INN, 9-digit ASCII KPP, non-negative
arbitration counts and ISO-like source-currency constraints.

### 6.2. Identity and canonical

1. Validate subject/target/counterparty exact INN.
2. Require safe full legal name.
3. Use short/full display precedence.
4. Apply versioned `legal_name_display_v1`, default-deny `legal_form_opf_v1`
   and `counterparty_status_v1` mappings; unknown values are hidden, never raw
   passthrough.
5. For published scope take stored canonical.
6. For unpublished build existing `seo.canonical_path(short or full)`.

### 6.3. Requisites

1. Map only existing normalized core fields.
2. Validate form-compatible OGRN/KPP.
3. Address only for stored `block_status=available`.
4. Preserve missing and inaccuracy limitations.
5. Exclude charter capital, tax mode and non-H1 blocks.

### 6.4. Finance

1. Select only exact approved metric mapping already present in normalized
   periods/series.
2. Reject duplicate/conflicting series.
3. Emit adjacent-year YoY only.
4. `money=null`, `unit_policy_version=null`.
5. Add finance-unit limitation when normalized values exist.
6. Use Decimal/ROUND_HALF_UP, no float.
7. Positive percent display is exact `+29,1%`, without a space before `%`.

### 6.5. Coverage/sources/limitations

1. Create exactly six coverage items.
2. Map internal statuses through exhaustive function.
3. Add disabled-gate limitations unconditionally for optional/management
   blocks.
4. Translate only allowlisted internal warnings.
5. Limitations use the complete specification table and ascending lexical
   `(block_id, field_id-or-empty-string, code)` ordering; page block index is
   forbidden.
6. Required finance/arbitration `failed|not_found` emit both coverage and the
   fixed safe limitation.
7. Source items contain only public provenance fields and an honest allowlisted
   stored normalizer version, including `arbitration_normalizer_v1|v2`.

### 6.6. Date, actions and manifest

1. Use `zoneinfo.ZoneInfo("Europe/Moscow")`.
2. Build checked date/display from report generated time.
3. Build exact block order.
4. Claims path uses selected report ID.
5. Breadcrumb uses selected canonical path.
6. Internal links empty.

### 6.7. Safety and determinism

1. Recursive forbidden-key validator allows legitimate mapped identity
   `status_code` and rejects only unapproved transport/provider/raw-result
   status fields.
2. Canonical JSON helper for byte equality tests.
3. DTO-only renderer:
   - escaped semantic HTML;
   - safe parity data attributes;
   - no script/JSON-LD/raw state;
   - only DTO values.

Stage completion:

- golden DTO passes;
- same input produces same canonical JSON/HTML;
- no forbidden field/fact.

## 7. Stage E — read-only persistence and resolver

### 7.0. Publication finalization integrity

Обновить `persistence/publications.py::finalize_batch_claim`. До existing
publication-policy evaluation и до upsert:

1. lock/load batch item, report и normalized subject;
2. сверить batch/ORM subject, report ID, report version и expected hash;
3. потребовать ORM status exact `complete|partial`;
4. проверить raw discriminator до Pydantic и hash untouched raw JSON;
5. parse exact versioned snapshot;
6. сверить snapshot/ORM ID, version, status, generated_at;
7. сверить snapshot target INN и counterparty INN с subject;
8. сверить batch/stored/raw hashes;
9. только после полной матрицы запустить policy decision/upsert.

Любое mismatch — safe terminal state conflict: no new pin, existing pin
unchanged, policy evaluator/upsert fail-if-called before integrity completion.

### 7.1. Persistence query module

Create `persistence/public_h1.py`.

Records:

```text
PublicationResolutionRecord
ReportResolutionRecord
```

Queries:

1. `get_publication_resolution_record(session, inn)`:
   - subject/publication anchored query;
   - outer join pinned report;
   - returns inactive rows too so resolver can distinguish active pin;
   - one SELECT.
2. `list_report_resolution_records(session, inn)`:
   - all subject reports ordered `created_at desc, id desc`;
   - defensive copies of JSON;
   - one SELECT.

Functions do not commit, flush or mutate.

### 7.2. Active pin validation

`public_h1_service.py`:

1. Validate INN.
2. Load publication record.
3. If active:
   - publication/subject-anchored outer join обязан вернуть active row
     даже при missing pinned report;
   - require joined report; missing report is invalid pin, not no-publication;
   - verify all equality/hash/version/status/time/canonical invariants;
   - validate persisted supported publication policy/sufficiency/indexability
     outcome without recomputation;
   - build H1 published DTO;
   - stop.
4. Any active failure maps to `PublicProjectionInvalidError`.
5. Never call report-history query after active record observed.
6. Never call `evaluate_publication` or `evaluate_report_ephemerally`; both are
   fail-if-called together with signals/scoring/AI/provider/jobs/writes.

### 7.3. Latest fallback

When no active pin:

1. Load ordered history by exact `(created_at DESC, id DESC)`.
2. Track latest run for error classification.
3. For every complete/partial candidate:
   - raw hash check;
   - parse v1/v2;
   - record/snapshot/subject identity;
   - public identity eligibility;
   - H1 build.
4. Return first eligible with noindex/latest scope.
5. If none, classify last run exactly.

### 7.4. Error isolation

Typed public-H1 errors carry fixed codes/messages only.
SQLAlchemy/persistence exceptions become 503.
Unexpected builder/integrity exception becomes safe 500.
No exception includes INN, company name, snapshot or provider diagnostics in
public message.

Stage tests assert SELECT ceilings with a counting fake session and assert
absence of flush/commit/add/delete/update.

## 8. Stage F — API and SSR

### 8.1. H1 endpoint

Add route before generic legacy read handler for readability, although path
segment count prevents collision:

```python
@router.get("/{inn}/public-h1", response_model=CompanyPublicH1Response)
```

Steps:

1. `_reject_unexpected_query_parameters(request)`.
2. Existing read rate limiter.
3. Call public H1 service.
4. Validate DTO before success serialization.
5. Use one H1 JSON success/error response factory.
6. Add exact no-store/noindex/nosniff headers on `200` and every JSON
   `400|404|409|422|429|500|503`, including query, identifier, validation,
   rate-limit, typed-domain and unexpected-safe exception paths.
7. Map exact typed errors; post-success-only header mutation is forbidden.

No auth dependency.

### 8.2. Canonical SSR

Refactor `company_reports_public.py`:

1. Preserve exact canonical key grammar.
2. Reject SSR query as existing 404/noindex.
3. Call shared H1 resolver.
4. If `latest_unpublished`, return 404/noindex.
5. For published:
   - redirect wrong slug to DTO/stored canonical;
   - render DTO;
   - robots follows DTO `indexable`.
6. Map active invalid 500 and DB unavailable 503.
7. Do not independently parse/evaluate snapshot in router.
8. Fail if either publication evaluator, provider, signals, scoring, AI, jobs
   or persistence writes are called.

### 8.3. Sitemap

1. Continue loading persisted active/indexable pages.
2. For each preloaded page, call shared pure pinned validation/H1 builder, not a
   second alternative policy projection.
3. Exclude invalid/noindex.
4. Preserve canonical order and persisted lastmod.
5. No writes.
6. Fail if either publication evaluator, provider, signals, scoring, AI, jobs
   or persistence writes are called.

Stage completion:

- active SSR/API parity;
- latest API-only noindex;
- existing redirects/statuses retained.

## 9. Stage G — backward compatibility

Run and, where necessary, extend tests proving:

1. Legacy GET returns v2 snapshot through old response shape.
2. Legacy POST/status lifecycle unchanged.
3. Existing AI default/opt-in unchanged; explanation envelope accepts v1/v2
   and remains closed to optional H1 facts.
4. Provider call list remains exactly three required calls.
5. Signals/scoring receive required facts only and no optional facts.
6. Publication batch/control/upsert keeps policy behavior after the new strict
   pre-upsert integrity gate.
7. Claims handoff reads v1/v2, verifies exact selected report ID/hash and does
   not use latest.
8. Existing frontend contract still accepts legacy response before iteration
   18.
9. Existing Gateway behavior unchanged.

No production code changes outside manifest are allowed to make a regression
test pass.

## 10. Detailed test matrix

| Surface | Cases |
| --- | --- |
| Evidence | Enabled evidence paths, every disabled gate, no env activation, no optional provider methods. |
| Snapshot v1 | Explicit raw v1, missing v2 fields, original hash before parse, no rewrite, published pin. |
| Snapshot v2 | Explicit envelope/nulls, deterministic hash, enqueue/build/finalize alignment. |
| Raw discriminator | Missing/null/boolean/numeric/unknown rejected before defaults; pending v1 rejected before provider. |
| Required lifecycle | 0/1/2/3 required available crossed with empty/available/not-found/failed optional states. |
| Freshness | Optional received_at never changes required oldest/newest/age. |
| Arbitration identity | INN-only, OGRN-only, both, conflict, target incomplete, name-only, malformed. |
| Arbitration role | Single five primary roles, other role, multiple roles, unattributed, one-bucket invariant. |
| Arbitration slice | Source total vs returned, malformed count, partial, scoped zero, ordering/limit. |
| Arbitration amounts | Exact role only, source currency, missing/mixed currency, Decimal aggregation. |
| Finance | No money, adjacent YoY, missing/zero previous, negative previous, duplicate conflict, exact rounding. |
| Identity | Exact INN, missing full name, record/snapshot mismatch, status conflict, IP/legal requisites. |
| Address | Available, not requested, empty, invalid, inaccurate. |
| Optional blocks | Tax/bankruptcy/management always null + not_requested + limitations. |
| DTO | Exact iteration-16 nullable/reserved topology, ASCII/count/currency constraints, mapping policies, exact percent, strict extra forbid and public status_code safety. |
| Date | UTC/Moscow midnight boundaries, locale/process-timezone independence. |
| Resolver active | Valid, noindex legacy, hash mismatch, wrong report/subject/version/status/time/path, unsupported policy, no fallback. |
| Resolver latest | Older eligible behind newer failed/ineligible/corrupt; pending/failed/not-eligible/no-run errors. |
| Publication finalizer | Full batch/ORM/snapshot identity matrix before evaluator/upsert; pin unchanged on mismatch. |
| Call ceiling | 0 invalid/query; 1 active; 2 fallback; API/SSR/sitemap each zero evaluators/provider/signals/scoring/AI/job/write. |
| API | Anonymous, query rejection, invalid INN, exact errors/rate limit and all three headers on 200/400/404/409/422/429/500/503. |
| SSR | Exact page, wrong slug, noindex, invalid pin 500, unpublished 404, DTO parity attributes/content. |
| Sitemap | Same pin integrity, indexable only, persisted lastmod, no mutation. |
| Claims | Action shown report ID; handoff exact v1/v2 report. |
| Legacy | GET/status/create, AI opt-in, worker and publication behavior. |

## 11. Verification commands

Run from repository root.

Because the host may have an editable install from another worktree, every
Python check first pins and proves this checkout:

```powershell
$repoPath = (Get-Location).Path
$env:PYTHONPATH = "$repoPath\services\product_api\src;$repoPath"
$expectedProductApi = (Resolve-Path -LiteralPath "$repoPath\services\product_api\src\product_api").Path
$actualProductApi = python -c "import pathlib, product_api; print(pathlib.Path(product_api.__file__).resolve().parent)"
if ((Resolve-Path -LiteralPath $actualProductApi).Path -ne $expectedProductApi) {
    throw "product_api imported outside iteration-17 worktree: $actualProductApi"
}
```

Repeat the import assertion in the same shell before reporting final results.

### 11.1. Targeted unit

```text
python -m pytest services/product_api/tests_unit/test_company_report_evidence.py services/product_api/tests_unit/test_company_report_public_h1.py services/product_api/tests_unit/test_company_report_public_h1_service.py services/product_api/tests_unit/test_company_report_aggregate_models.py services/product_api/tests_unit/test_company_report_models.py services/product_api/tests_unit/test_company_report_arbitration_normalizer.py services/product_api/tests_unit/test_company_report_orchestrator_success.py services/product_api/tests_unit/test_company_report_orchestrator_partial.py services/product_api/tests_unit/test_company_report_persistence_serialization.py services/product_api/tests_unit/test_company_report_repository_finalize.py services/product_api/tests_unit/test_company_report_repository_pending.py services/product_api/tests_unit/test_company_report_jobs.py services/product_api/tests_unit/test_company_report_publications.py services/product_api/tests_unit/test_company_report_service.py services/product_api/tests_unit/test_company_report_api_schemas.py services/product_api/tests_unit/test_company_reports_api.py services/product_api/tests_unit/test_company_report_public_routes.py services/product_api/tests_unit/test_company_report_seo_crawl.py services/product_api/tests_unit/test_company_report_explanation_models.py services/product_api/tests_unit/test_company_report_explanation_validation.py services/product_api/tests_unit/test_company_report_explanation_service.py -q
```

### 11.2. CompanyReport regression

```text
python -m pytest services/product_api/tests_unit -q -k "company_report or datanewton"
```

### 11.3. Full Product API unit

```text
python -m pytest services/product_api/tests_unit -q
```

### 11.4. Targeted PostgreSQL integration

Requires an available disposable/migrated test PostgreSQL, never production:

```text
python -m pytest services/product_api/tests/test_company_reports_api.py services/product_api/tests/test_company_report_jobs.py services/product_api/tests/test_company_report_publications.py services/product_api/tests/test_claims_company_report_handoff.py -q
```

### 11.5. Full PostgreSQL integration

```text
python -m pytest services/product_api/tests -q
```

If unavailable, report it as an environment limitation. Do not replace it with
production DB access and do not claim it passed.

### 11.6. Repository-required regressions

```text
python -m pytest services/gateway_api/tests -q
npm run lint --prefix services/web_ui
npm run test --prefix services/web_ui
npm run build --prefix services/web_ui
```

### 11.7. Syntax and diff

```text
python -m compileall -q services/product_api/src/product_api
git diff --check
git status --short
```

No Python lint/type-check command exists in repository; do not claim one.

No Alembic upgrade/revision command is run because schema is unchanged.

## 12. Migration decision

Expected migration: **none**.

Implementation must verify:

- `report_version` column accepts `"2"`;
- JSON snapshot accepts v2 fields;
- no optional dataset rows are required;
- no publication schema change is needed.

If this expectation fails, implementation stops as blocked. It must not add an
unreviewed migration.

## 13. Security/privacy checks

Before review:

1. Search diff for `.env`, tokens, auth files, raw probes and logs.
2. Assert fixtures contain only synthetic identifiers/names.
3. Run recursive forbidden-key tests over DTO and HTML.
4. Confirm no tax/bankruptcy/owner source path was added.
5. Confirm no manager INNFL/contact enters public schema.
6. Confirm public read logs contain no snapshot/provider data.
7. Confirm no arbitrary provider error text enters limitations/errors.
8. Confirm no `float` conversion in finance/arbitration public formatting.

## 14. Risks and rollback

### 14.1. Implementation rollback before deployment

Iteration has no DB migration or backfill. Before any future deployment, the
feature commit may be reverted without data cleanup.

### 14.2. Future production rollback constraint

Once a deployed writer persists v2, rollback to a binary that understands only
v1 would make new snapshots unreadable. Deployment is outside this iteration,
but future rollout must:

- retain a v2-capable reader in the rollback image;
- never rewrite/delete v2 snapshots;
- disable report creation during emergency rollback if only a v1 binary is
  available;
- restore service with a compatibility build, not DB downgrade.

### 14.3. Functional rollback

H1 endpoint/SSR can be removed by reverting code while preserving immutable
reports and publication registry. No publication row or snapshot is mutated by
read path, so there is no data rollback.

## 15. Review focus

Independent reviewer receives:

- approved iteration-16 contract;
- final iteration-17 specification and plan;
- evidence registry;
- full diff from base;
- exact test commands, exit codes and summaries;
- integration environment status;
- any baseline failures.

Mandatory review questions:

1. Did any disabled gate become active?
2. Can optional state affect required lifecycle?
3. Can invalid active pin fall back?
4. Can API/SSR/sitemap call either evaluator, provider, signals, scoring, AI,
   jobs or writes?
5. Are v1 hashes preserved?
6. Are enqueue/build/finalize versions aligned?
7. Does arbitration count each case once?
8. Are finance amounts absent?
9. Does Claims action use selected report ID?
10. Did any migration/deploy/frontend scope leak into diff?
11. Is raw version required before Pydantic defaults and raw hash preserved?
12. Does publication finalization validate every batch/ORM/snapshot identity
    dimension before evaluation/upsert?
13. Are all specified JSON success/error headers present?

## 16. Completion gates

Implementation is ready for code review only when:

- exact manifest respected;
- no unexpected migration/dependency/config change;
- all enabled facts grounded in existing evidence;
- optional calls remain zero;
- snapshot v1/v2 and version alignment tests pass;
- missing/non-string/unknown raw versions reject before defaults;
- reused pending v1 rejects before provider boundary;
- explanation v1/v2 compatibility passes without optional H1 facts;
- required lifecycle matrix passes;
- publication finalization integrity/no-pin matrix passes;
- active pin/no-fallback and latest eligibility tests pass;
- exact DTO/constraints/mapping/limitation/forbidden/privacy tests pass;
- API/SSR parity tests pass;
- API/SSR/sitemap zero evaluator/provider/signal/scoring/AI/job/write tests pass;
- `200|400|404|409|422|429|500|503` H1 header tests pass;
- legacy and Claims compatibility tests pass;
- targeted and full applicable checks pass;
- `git diff --check` is clean.

Iteration becomes `ready_for_merge` only after:

- independent code reviewer returns `VERDICT: READY`;
- final state is updated without changing roadmap;
- one conventional commit contains the approved scope;
- feature branch push succeeds.

Merge remains manual.

## 17. Corrective unblock stage

This is the single approved implementation pass after independent plan review.
Before implementer launch, only iteration 17 in `DEVFLOW_STATE.yaml` moves from
`blocked` to `implementing`; branch
`feat/iteration-17-company-report-h1-backend` and base
`f4776595375a485732fff96053eb9362194f203a` stay unchanged. `ROADMAP.md` is not
modified.

### 17.1. Implementation order

1. Add a reusable exact SELECT-count and complete capability-guard test helper.
2. Add independent API, SSR and sitemap tests through real resolver/read paths.
3. Expand the real-finalizer unit matrix and PostgreSQL all-column sentinel
   matrix, marking every row representable or unit-only.
4. Add missing arbitration and reserved DTO tests.
5. Apply only production corrections demonstrated by those failing tests in
   `public_h1.py` and the arbitration normalizer. `publications.py` may change
   only if a named integrity row proves a missing comparison first.
6. Repair the exact web UI lint sites without rule suppression or H1 UI work,
   and add focused behavior tests.
7. Add the tracked disposable PostgreSQL script and README commands.
8. Run targeted, full and repository-required checks.
9. Move to `reviewing` only through the normal DevFlow transition.

### 17.2. Corrective manifest

State, documentation and runbook:

- `docs/development/DEVFLOW_STATE.yaml`;
- iteration-17 specification and plan;
- `README.md`;
- `.gitignore` with only `/.tmp/iteration17-postgres/` for generated JUnit
  evidence;
- new `scripts/run-iteration17-postgres-tests.ps1`.

Backend production and tests:

- `company_reports/public_h1.py`;
- `company_reports/normalizers/arbitration.py`;
- optional `company_reports/persistence/publications.py` only after a failing
  named matrix row;
- `main.py` only to place the public one-segment `/company/{company_key}`
  route after the existing static `/company/*` routes when the Full gate proves
  route shadowing;
- `repositories.py` only to preserve the existing
  `company_id is null -> role is null` database constraint during detach;
- new `tests_unit/company_report_public_h1_side_effect_test_helpers.py`;
- public H1, arbitration, resolver, API, SSR/sitemap and publication unit tests;
- publication/API integration tests and new
  `tests/test_company_report_public_h1_reads.py`;
- Full-gate compatibility corrections limited to
  `tests/test_admin_claims.py`, `tests/test_company_admin_detach.py`,
  `tests/test_invite_invariants.py`, `tests/test_last_n.py`,
  `tests/test_public_claims_preview.py` and
  `tests/test_superadmin_hardening.py`.

Web UI:

- new Auth and ClaimsAdmin context modules plus their provider/hook imports;
- `RequireClaimsAdmin.test.tsx`;
- queue/typewriter hooks and tests;
- Admin confirm page and a focused test;
- Superadmin page and a focused test.

Explicitly unchanged: `ROADMAP.md`, Alembic revisions, `package.json`, lockfile,
provider fixtures, deployment and every H1/iteration-18 frontend surface.

### 17.3. UI dependency and verification gate

Prefer `npm ci --offline --prefix services/web_ui`, followed by
`npm ls --all --prefix services/web_ui`. If offline installation is not
available, a temporary junction to `C:\GPT\services\web_ui\node_modules` is
permitted only after SHA-256 equality of source/worktree `package.json` and
lockfile plus successful `npm ls --all` on both sides. Cleanup verifies
`LinkType=Junction`, the exact target and reparse attribute before removing only
the junction.

Then run from this worktree:

```text
npm run lint --prefix services/web_ui
npm run test --prefix services/web_ui
npm run build --prefix services/web_ui
```

Acceptance is zero lint errors and warnings plus passing targeted/full tests
and build.

### 17.4. Disposable PostgreSQL gate

Run both modes independently:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-iteration17-postgres-tests.ps1 -Mode Targeted
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-iteration17-postgres-tests.ps1 -Mode Full
```

Targeted includes publication, public API/read and Claims handoff integration
tests. Full runs all `services/product_api/tests`, proves the self-managed
migration cases, and applies the repository's existing migrations only to the
new disposable DB. Each JUnit must have tests > 0 and zero
failures/errors/skips. No externally supplied DB URL is accepted.

### 17.5. Remaining mandatory verification

With `PYTHONPATH` pinned to and import-proven from this worktree:

```text
python -m pytest services/product_api/tests_unit/test_company_report_public_h1.py services/product_api/tests_unit/test_company_report_arbitration_normalizer.py services/product_api/tests_unit/test_company_report_public_h1_service.py services/product_api/tests_unit/test_company_reports_api.py services/product_api/tests_unit/test_company_report_public_routes.py services/product_api/tests_unit/test_company_report_publications.py -q
python -m pytest services/product_api/tests_unit -q
python -m pytest services/gateway_api/tests -q
python -m compileall -q services/product_api/src/product_api
git diff --check
git status --short
```

The pass is reviewable only when all section 26 acceptance gates in the
specification are green and no migration, roadmap, dependency, optional-call,
deployment or iteration-18 scope leak exists.

### 17.6. Full-gate evidence reconciliation

The first executable Full run is allowed to expose failures that had previously
been hidden by the unavailable PostgreSQL environment. Corrections remain in
scope only when they are required for the section 17.4 zero-failure/zero-skip
gate and are one of the exact files listed in section 17.2. The accepted
minimal classes are:

- test fixtures and monkeypatch signatures brought into line with already
  enforced request, credit, JSON binding and preview-rendering contracts;
- the public CompanyReport route ordered after legacy static company routes;
- detach behavior aligned with the already-applied user role/company check
  constraint.

These corrections do not alter the H1 public DTO, evidence policy, provider
surface, database schema or iteration-18 frontend scope.
