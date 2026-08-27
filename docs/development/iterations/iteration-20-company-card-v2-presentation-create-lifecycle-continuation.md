# Iteration 20 — presentation create/status/read lifecycle continuation

ID: `20`

Slug: `company-card-v2-backend-foundation`

Continuation key: `presentation-create-lifecycle-contract-v1`

Scope version: `presentation_create_lifecycle_contract_continuation_v1`

Base commit: `886f207d945e35acc1a7e5c07dcff8c36e501bf6`

Public contract: `company_public_h2_v1`

Статус спецификации:
`IMPLEMENTATION IN PROGRESS AFTER APPROVED REVIEWED PLAN`

Independent plan review: `APPROVED` after one Roadmap prerequisite correction

Owner planning authorization: `APPROVED` — 2026-08-27

Owner implementation approval: `APPROVED` — user command 2026-08-27

Production activation: `NOT AUTHORIZED`

## 1. Цель

Закрыть bounded post-merge debt iteration 20 до iteration 25:

- восстановить frozen create/status response;
- сохранить opaque exact-report polling после flag flip;
- запретить client-controlled query/header selectors;
- исправить OpenAPI;
- доказать atomic reuse/history behavior на disposable PostgreSQL;
- выровнять один frozen public-H2 no-subject error literal.

Это continuation существующего ID 20, а не новая итерация и не пересмотр
Company Card v2 backend. Исторические iteration-20 spec/plan не переписываются.

## 2. Источники истины

Приоритет:

1. `iteration-20-owner-scope-decision-v1.md`;
2. `iteration-20-gate-readiness-v3.md`;
3. iteration-19 sections 28–31 и 35;
4. iteration-19 architecture/privacy ADR;
5. merged iteration-20 specification;
6. baseline evidence v1 этой continuation;
7. эта specification и reviewed implementation plan.

Current runtime не является источником контракта там, где он расходится с
frozen sources.

## 3. Неизменные границы

```text
COMPANY_CARD_V2_PRESENTATIONS_ENABLED=false
COMPANY_CARD_V2_WRITER_ENABLED=false
COMPANY_CARD_V2_ROLLOUT_GENERATION=0
COMPANY_CARD_V2_ALLOWLIST_INNS=[]
COMPANY_CARD_V2_PERCENTAGE_BASIS_POINTS=0

production provider operation = disabled
production H2 publication/assignment = disabled
live DataNewton/FNS/Gateway/AI = prohibited
production DB/deploy = prohibited
```

Ни один default, feature flag или production configuration не меняется.

## 4. Exact wire contract

### 4.1. Request DTO

```http
POST /company-report-presentations
Content-Type: application/json

{"identifier":"7701234567"}
```

Body содержит ровно одно string field `identifier`. Extra fields, array,
scalar, null и missing field дают framework `422` strict validation response.

До cohort и до DB identifier проходит существующую INN normalization и
validation. Нормализуемый формат принимает то же решение cohort, что и его
digit-only INN. OGRN/OGRNIP, empty и invalid length дают route-owned:

```json
{"detail":{"code":"invalid_company_identifier","message":"invalid INN"}}
```

со статусом `422`.

### 4.2. Selector guards

Для POST и GET status:

- любой query parameter, включая blank, repeated и unknown, даёт
  `422 presentation_query_forbidden`;
- наличие case-insensitive `X-Report-Version` или `X-Writer-Profile`, включая
  empty value, даёт `422 presentation_selector_forbidden`;
- unknown non-selector headers игнорируются;
- Authorization, cookies и Accept-Language не меняют facts, cohort или
  binding.

Guard выполняется до cohort/DB. Ни один rejected request не создаёт subject,
report, job, presentation или lifecycle head.

### 4.3. Success DTO

Обе success routes возвращают strict
`CompanyReportPresentationLifecycle` без extra keys:

```text
presentation_id: UUID
presentation_contract: literal "company_public_h2_v1"
report_id: UUID
lifecycle_status: "pending" | "complete" | "partial" | "failed"
public_read_path: "/company-reports/{normalized_inn}/public-h2"
canonical_document_path: null
reused: boolean
```

Legacy key `status` удаляется. Одновременная выдача `status` и
`lifecycle_status` запрещена: она нарушила бы closed DTO.

`public_read_path` строится только из stored normalized subject INN exact
presentation binding. Он не строится из request after creation, latest report
или assignment.

### 4.4. `reused` semantics

`reused` отвечает на один вопрос:

> Вернул ли этот HTTP operation уже сохранённую exact lifecycle binding вместо
> создания новой?

Следовательно:

- первый accepted POST, создавший job/report/presentation/head:
  `reused=false`;
- exact repeated/concurrent POST, переиспользовавший тот же active binding:
  `reused=true`;
- successful GET status всегда читает уже сохранённую binding и возвращает
  `reused=true`.

Значение не является immutable business fact, не сохраняется в snapshot и не
требует DB column. Клиенты используют его только как operation metadata.

### 4.5. `canonical_document_path`

В этой continuation значение всегда `null`.

Current persistence не хранит immutable
`presentation_id -> canonical document path` proof. H2 pin по DB contract
имеет `canonical_path IS NULL`; current assignment/staged/head являются
subject-level selectors и могут измениться. Status запрещено использовать их,
generic latest, H1 canonical, DTO slug helper или current cohort для
синтетического redirect.

Non-null path потребует отдельного versioned contract/evidence и durable exact
binding. Эта continuation не добавляет migration и не обещает такой path.

## 5. HTTP matrix

### 5.1. Create

| Situation | Result |
|---|---|
| exact selected request, writer available | `202` full lifecycle |
| exact active H2 decision reused | `202`, same IDs, `reused=true` |
| query present | `422 presentation_query_forbidden` |
| selector header present | `422 presentation_selector_forbidden` |
| invalid semantic identifier | `422 invalid_company_identifier` |
| strict body validation failure | framework `422` |
| cohort/presentations gate closed | `404 company_public_h2_disabled` |
| writer gate closed after cohort | `503 company_card_v2_writer_unavailable` |
| incompatible active H1/H2 job | `409 report_writer_profile_conflict` |
| safe persistence unavailability | `503 presentation_unavailable` |

Create success assembly and full tuple validation happen before commit.
Conflict/validation/unavailability rolls back; partial presentation/head state
is forbidden.

### 5.2. Status

| Situation | Result |
|---|---|
| exact existing UUID | `200` full lifecycle, `reused=true` |
| unknown UUID | `404 presentation_not_found` |
| malformed UUID | framework `422` |
| query present | `422 presentation_query_forbidden` |
| selector header present | `422 presentation_selector_forbidden` |
| missing/mismatched exact tuple | `500 presentation_invalid` |
| safe persistence unavailability | `503 presentation_unavailable` |

Status не проверяет current presentations/writer flag. Existing opaque ID
остаётся pollable после любого flag/allowlist/percentage/generation change.

### 5.3. Headers

Все route-owned success/error responses create/status содержат:

```text
Cache-Control: no-store
X-Content-Type-Options: nosniff
X-Robots-Tag: noindex,follow
```

Framework validation response не переопределяется этой continuation.

## 6. Exact status resolver

Status читает только:

- `CompanyReportPresentation` по opaque ID;
- exact bound `CompanyReportRecord`;
- exact bound `CompanyReportSubject`.

Он валидирует:

```text
presentation.subject_id == report.subject_id == subject.id
presentation.report_id == report.id
presentation.presentation_contract == report.presentation_contract
presentation.presentation_contract == "company_public_h2_v1"
presentation.rollout_generation == report.rollout_generation > 0
report.writer_profile == "company_card_v2_writer_v3"
report.report_version == "3"
report.lifecycle_status in pending|complete|partial|failed
subject.normalized_identifier == valid INN
```

Resolver read-only, не берёт write lock, не вызывает provider и не читает:

- lifecycle head;
- presentation assignment/staged pointer/pin;
- latest report;
- cohort/settings;
- public projection/narrative.

Старый presentation после создания нового head продолжает возвращать старый
exact report lifecycle.

## 7. Public-H2 frozen literal

`PublicH2NotFound.code` меняется только с
`company_public_h2_not_found` на frozen `company_report_not_found`.

Selection, status mapping, response body shape и H2 resolver не меняются.
Targeted test доказывает enabled-cohort no-subject `404` и отсутствие writes.

## 8. OpenAPI

OpenAPI обязан объявить:

- POST JSON body only;
- POST success `202` с `$ref` на strict lifecycle schema;
- GET только UUID path parameter;
- GET success `200` с тем же `$ref`;
- request/response schemas с `additionalProperties: false`;
- отсутствие success schema `{}` и deprecated `status`.

## 9. Compatibility

- Endpoint default-off и не имеет repo-local first-party consumer.
- Исправление `status -> lifecycle_status` — explicit pre-activation frozen
  contract correction.
- H1 routes, legacy `/company-reports`, Claims и saved snapshots не меняются.
- ORM/schema/Alembic migration не нужна.
- No backfill, rewrite или production DB action.

## 10. Scope

В scope:

- strict request/lifecycle schemas;
- exact lifecycle read helper;
- presentation create/status router;
- one public-H2 error literal;
- unit/OpenAPI/PostgreSQL regression matrix;
- continuation docs/state.

Вне scope:

- models/migration/job/writer/provider/settings/env defaults;
- public projection/narrative/chart/SSR/React semantics;
- H1/Claims/scoring/signals;
- frontend/Gateway/dependencies/CI/deploy;
- publication assignment or iteration-25 rollout;
- production provider/AI/DB/config operations.

## 11. Acceptance

Continuation готова только когда:

1. RED tests воспроизводят current response/OpenAPI/flag-flip gaps.
2. Full lifecycle wire contract и selector guards проходят.
3. Exact reuse/history/flag-flip/conflict/corrupt cases доказаны на disposable
   PostgreSQL.
4. Targeted и Full iteration-20 runners дают clean JUnit без skipped/error.
5. Product API unit, Gateway и web regression checks проходят.
6. `git diff --check`, YAML parse, compile/static/secret/raw scans clean.
7. Production defaults и migrations не изменены.
8. Independent code review не содержит blockers.
9. Commit/push получают отдельную explicit owner command; merge остаётся
   ручным.

Docker unavailability блокирует readiness, но не specification/plan review.
