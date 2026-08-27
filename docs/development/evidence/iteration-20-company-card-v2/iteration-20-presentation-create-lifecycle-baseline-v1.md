# Iteration 20 presentation lifecycle baseline v1

Дата фиксации: 2026-08-27

Iteration identity: `20 / company-card-v2-backend-foundation`

Continuation key: `presentation-create-lifecycle-contract-v1`

Base: `886f207d945e35acc1a7e5c07dcff8c36e501bf6`

Branch: `codex/iteration-20-presentation-create-lifecycle-continuation`

Production activation: `NOT AUTHORIZED`

## 1. Назначение evidence

Этот документ фиксирует post-merge расхождение между frozen
`company_public_h2_v1` create/status/read contract и кодом в точном
`origin/main`. Он не переоткрывает весь scope iteration 20 и не является
разрешением на product-code changes.

Проверка выполнялась в отдельном чистом worktree. Dirty root worktree
`C:\GPT` не был рабочим деревом continuation и не изменялся; случайное
разрешение editable import в root было обнаружено и отклонено до baseline.
Live DataNewton, FNS, Gateway, AI, production DB, deploy и feature activation
не выполнялись.

## 2. Hash-locked inputs

| Surface | Git blob |
|---|---|
| iteration-19 frozen contract | `df999bec416c8648eaa889e0452cdcca4f1fa840` |
| iteration-19 architecture ADR | `3562effb1e429f3859fbd39c0f6a88c6e7e83de6` |
| merged iteration-20 specification | `2166bcd4b2bbab2319a536967d7b04126675eb9f` |
| merged iteration-20 plan | `b5f9d0990063374aa00d80e756ef704861dfc22b` |
| current CompanyReport schemas | `41be9f088c444ecbc0b3e889de69b454443f952e` |
| current presentation router | `3da1c4893f2d66f5f5e58c250e7dd9cbf9eeadc0` |
| current public-H2 service | `a7481218516aff988bd323917944abdf90e0da31` |
| current presentation PostgreSQL tests | `37234c40ae760f84a1a1f4c794c5d9d099464dd2` |
| current public-H2 PostgreSQL tests | `af1b675894638a77264c5d038b0d8a08d121c730` |
| current presentation unit tests | `47cf56fbb3b31c0a59a291561539a506d86e7fee` |
| iteration-20 PostgreSQL runner | `c9d12abfda743608d65e03a2de1a0ede6792af70` |
| iteration-24 PostgreSQL runner | `14d3af0dee68cc2730396f6077aa2ee827efb2c2` |

## 3. Frozen contract

`POST /company-report-presentations` принимает только JSON body
`{"identifier":"<INN>"}`, без query и version/profile selector headers.
Accepted response имеет семь полей:

1. `presentation_id`;
2. `presentation_contract`;
3. `report_id`;
4. `lifecycle_status`;
5. `public_read_path`;
6. `canonical_document_path`;
7. `reused`.

`GET /company-report-presentations/{presentation_id}/status` читает только
immutable opaque presentation binding. Он не выбирает latest, lifecycle head,
assignment, cohort или текущую rollout configuration. Flag flip не меняет
polling identity.

`GET|HEAD /company-reports/{inn}/public-h2` возвращает для отсутствующего
subject/run exact `404 company_report_not_found`.

Нормативные ссылки:

- iteration-19 contract sections 28.4, 29.2–29.5;
- iteration-19 architecture ADR, lifecycle correction;
- iteration-20 specification section 5.

## 4. Confirmed origin/main gaps

Current POST:

- принимает и игнорирует любой query;
- принимает `X-Report-Version` и `X-Writer-Profile`;
- вычисляет cohort по raw, ещё не нормализованному identifier;
- возвращает runtime `202`, но OpenAPI объявляет `200`;
- возвращает `presentation_id`, `report_id`, legacy `status`, `reused`;
- не возвращает contract, frozen lifecycle key и оба paths;
- не имеет strict response schema.

Current GET status:

- принимает и игнорирует query/selector headers;
- возвращает только `presentation_id`, `report_id`, legacy `status`;
- повторно применяет текущий presentations flag и ломает polling после flag
  flip;
- не валидирует полный report/presentation H2 tuple на application boundary;
- не имеет strict response schema.

OpenAPI probe на base подтвердил:

```text
POST success response: 200, schema {}
GET  success response: 200, schema {}
POST request body: JSON _CreatePresentation
```

Current public-H2 no-subject code:

```text
company_public_h2_not_found
```

Frozen code:

```text
company_report_not_found
```

Repo-local HTTP consumer audit не нашёл first-party клиента presentation
lifecycle. Endpoint default-off; Web UI использует legacy
`/company-reports`, а static H2 bundle запрещает lifecycle calls. Поэтому
удаление ненормативного key `status` является явной pre-activation contract
correction, а не dual-shape migration.

## 5. Baseline checks

Correct worktree import был принудительно задан через
`PYTHONPATH=<worktree>/services/product_api/src`.

```text
python -m pytest services/product_api/tests_unit/test_company_card_v2_presentations.py -q
24 passed, 2 warnings

python -m pytest services/product_api/tests_unit -q
1498 passed, 2 warnings
```

Первый targeted запуск без worktree-local `PYTHONPATH` был отклонён при
collection, потому что Python импортировал editable package из dirty root.
После изоляции import path тот же target прошёл. Implementation runbook обязан
сохранять эту проверку.

Disposable PostgreSQL baseline не запускался:

```text
docker info --format '{{.ServerVersion}}'
failed to connect to npipe:////./pipe/dockerDesktopLinuxEngine
```

Docker Desktop daemon отсутствует. Ни fallback DB, ни production/unknown DB
не использовались. Это не блокирует планирование, но блокирует readiness
continuation и отдельно не закрывает iteration-24 PostgreSQL debt.

## 6. Scope conclusion

Persistence уже содержит opaque presentation, exact subject/report/contract
binding и durable H2 head. Для подтверждённой коррекции не нужна миграция.

Минимальный кодовый scope:

- strict request/lifecycle schemas;
- presentation create/status router;
- небольшой read-only exact lifecycle resolver;
- exact public-H2 no-subject error literal;
- targeted unit/OpenAPI/PostgreSQL regressions.

Запрещённое расширение:

- ORM/schema migration;
- writer/provider/narrative/chart/Claims/H1 semantics;
- frontend/Gateway/dependencies/CI/deploy;
- production config, publication, provider traffic или rollout.
