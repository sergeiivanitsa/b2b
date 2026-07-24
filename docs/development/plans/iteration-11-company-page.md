# Итерация 11 — Company page: implementation plan

## Изменяемый manifest

| Файл | Изменение |
|---|---|
| `docs/development/iterations/iteration-11-company-page.md` | Утверждённая спецификация iteration 11. |
| `docs/development/plans/iteration-11-company-page.md` | Этот implementation plan. |
| `services/web_ui/src/router/AppRouter.tsx` | Добавить nested `RequireAuth` route `/company/:companyKey` без изменения existing routes. |
| `services/web_ui/src/router/AppRouter.companyPage.test.tsx` | New router/auth protection tests. |
| `services/web_ui/src/companyReport/companyReportTypes.ts` | Узкие display DTO, public status/error/context types. |
| `services/web_ui/src/companyReport/companyReportApi.ts` | `getCompanyReport`, `getCompanyReportStatus`, `createCompanyReport` поверх `apiFetchJson`; `AbortSignal`; literal API paths. |
| `services/web_ui/src/companyReport/companyReportApi.test.ts` | Methods, paths, body, AI query и abort propagation. |
| `services/web_ui/src/companyReport/companyReportPresentation.ts` | URL parser, fixed poll interval, safe-error mapper, strict field selectors, decimal/date presentation, 13-code label map and unknown fallback. |
| `services/web_ui/src/companyReport/companyReportPresentation.test.ts` | URL, allowlist/selectors, decimal/unknown-unit and label-map tests. |
| `services/web_ui/src/components/company-report/CompanyReportContent.tsx` | Pure report sections: hero, machine score, AI, facts, warnings, failure/pending views and CTA. |
| `services/web_ui/src/components/company-report/CompanyReportContent.test.tsx` | Allowlisted rendering, absence/missing, machine-vs-AI and CTA state tests. |
| `services/web_ui/src/pages/CompanyReportPage.tsx` | Fetch/create/poll/AI state machine, request cancellation and retry callbacks. |
| `services/web_ui/src/pages/CompanyReportPage.test.tsx` | Lifecycle integration tests with mocked API/timers. |
| `services/web_ui/src/index.css` | Scoped `company-report-*` layout, status, focus and responsive rules. |

Не меняются Product API, Gateway, database/migrations, package manifests,
existing Claims components/pages и deployment.

## Stage 1 — contracts and pure helpers

1. Создать строгие frontend-only types из public response итерации 10, сохраняя
   сериализованные decimals как `string | null`.
2. Моделировать только поля, нужные для отображения; не добавлять
   `factual_basis` или raw/internal fields в presentation props.
3. Реализовать `parseCompanyKey`, принимающий exact `10|12 digits` и lowercase
   slug grammar. Invalid input возвращает typed local route error.
4. Реализовать selectors, возвращающие `null`/«нет данных», а не `0`, когда
   данные или unit отсутствуют.
5. Добавить immutable map 13 codes и neutral unknown fallback; не выводить
   labels из code fragments.
6. Добавить API wrappers для default GET (`include_ai_explanation` omitted),
   opt-in GET (`?include_ai_explanation=true`), status GET и JSON POST.

## Stage 2 — route and page state machine

1. Добавить `/company/:companyKey` under `RequireAuth`.
2. На valid route запустить один ordinary report GET с новым abort signal.
3. Классифицировать response/error по `ApiHttpError.status` и safe API detail
   code.
4. На `404` отрисовать explicit create action. POST только после click, затем
   polling.
5. На initial `409 report_pending` или successful POST poll status с
   `STATUS_POLL_INTERVAL_MS = 3000`, одним request за раз.
6. Останавливать и abort all pending/timer work на route change, unmount, retry
   и terminal status. После terminal status выполнить один normal report GET.
7. Держать AI request отдельно: только click создаёт GET; machine report
   остаётся видимым; cleanup отменяет request, automatic AI retry отсутствует.

## Stage 3 — safe presentation

1. Построить hero, completeness/freshness, legal/requisites, finance,
   arbitration, safe warning, machine scoring и AI sections только из
   allowlisted selectors.
2. Рендерить finance decimal strings буквально и всегда показывать unknown
   finance unit; arbitration monetary values — только с explicit currency key.
3. Рендерить clear partial/failed/not-found state. Доступные partial blocks
   остаются видимыми; infrastructure failure не получает invented report data.
4. Разместить machine scoring до AI и отделить его от explicit AI section в
   markup и styles.
5. CTA navigates to `/claims` с минимальным
   `location.state.companyReportContext`; без persistence/API call/backend
   contract.

## Stage 4 — responsive and accessibility

1. Добавить scoped responsive CSS для desktop two-column summary, collapsing to
   one column.
2. Обеспечить mobile-safe long values/tables, focus styles, non-color status
   indicators и reduced-motion-safe loading.
3. Проверить headings, buttons, `aria-live` updates и error/retry semantics
   component assertions.

## Stage 5 — tests and verification

| Surface | Required cases |
|---|---|
| URL helper | Valid 10/12-digit keys; malformed INN/slug rejected; invalid route causes no fetch. |
| API client | Exact GET/status/POST routes; default GET has no AI query; opt-in uses only `include_ai_explanation=true`; credentials inherited by shared fetch; abort signal passed. |
| Presentation | Only allowlisted fields rendered; `factual_basis`/internal keys absent; missing stays unavailable; exact decimal string and unknown unit; all 13 labels and unknown fallback. |
| Router | Anonymous visitor is redirected by `RequireAuth`; authenticated route reaches page; existing route behaviour stays intact. |
| Page lifecycle | Initial GET only; 404 does not POST until click; POST body is `{inn}`; 409/status pending polls at 3s; terminal status fetches final report; timers/requests cancelled. |
| States | Complete, partial, snapshot failed, infrastructure failed, `401/403/429/503/network`, explicit retries and safe messages. |
| AI | No initial opt-in; click invokes opt-in GET; machine score remains separate; failure nonfatal; no automatic retry. |
| CTA/a11y | Minimal location state only; buttons/heading/live regions accessible; responsive CSS class contracts. |

Run from `C:\GPT`:

```text
npm run lint --prefix services/web_ui
npm run test --prefix services/web_ui
npm run build --prefix services/web_ui
python -m pytest services/product_api/tests_unit -q
python -m pytest services/gateway_api/tests -q
git diff --check
```

Because the page consumes the existing Product API contract, also run the
focused API regression when disposable PostgreSQL is available:

```text
python -m pytest services/product_api/tests/test_company_reports_api.py -q
```

Run the full Product API integration suite when a migrated PostgreSQL is
available:

```text
python -m pytest services/product_api/tests -q
```

No Python lint/type-check command is claimed because none is configured. No
migration/Alembic command is needed.

## Completion gate

Implementation is ready for independent review only when the manifest is
respected, no backend/migration/dependency diff exists, all applicable commands
pass, `git diff --check` is clean, and review finds no unresolved blocker.
