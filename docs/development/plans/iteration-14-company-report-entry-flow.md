# Итерация 14 — CompanyReport entry flow: implementation plan

## Изменяемые поверхности

| Поверхность | План |
|---|---|
| Backend | Добавить optional `canonical_path` в финальный public response и вычислять его ephemerally из already-safe counterparty facts. |
| Entry UI | Добавить landing и переиспользуемую форму ИНН; оба варианта формы используют один page-level navigation coordinator и не вызывают API. |
| Router/lifecycle | Научить parser plain и canonical key; plain resolver сначала читает, только после verified 404 запускает/переиспользует job, polls и replace-redirects после final read. |
| Claims | Оставить trusted plain-INN backlink, теперь явно как поддерживаемый resolver contract. |
| Styles/tests | Добавить scoped entry styles и тесты API, формы, routing, lifecycle и Claim backlink. |

## Реализация

1. `services/product_api/src/product_api/company_reports/schemas.py`: добавить `canonical_path: str | None` к `CompanyReportResponse`.
2. `services/product_api/src/product_api/company_reports/service.py`: добавить safe helper, выбирающий `short_name`, затем `full_name`, и вызывающий `seo.canonical_path` только для matching INN. Не использовать `evaluate_publication`; не модифицировать snapshot. Failed/no-name даёт `None`.
3. Обновить backend unit tests API/service: additive schema, correct transliteration/path, missing identity and no snapshot; без real provider/DB.
4. Добавить `CompanyReportInnForm` и landing page. Landing владеет одним coordinator (shared validated input/transition ref) для header и hero: он normalizes spaces, validates exact digit format, однократно navigates на plain path и блокирует обе формы, не делая POST.
5. В `AppRouter` заменить home redirect на landing. Сохранить CompanyReport за existing auth gate и добавить allowlisted sessionStorage return target для strict plain/canonical company path; ConfirmPage consumes it once after magic-link. Обновить route/auth tests для home, plain и canonical.
6. В `companyReportPresentation` вернуть discriminated parse result for plain and canonical key и validate returned canonical path before navigation.
7. В `CompanyReportPage` разделить `plain` и `canonical` behavior: plain reads once, only verified `404 company_report_not_found` auto-starts once, `409 report_pending` polls and final response replace-redirects only to a valid same-INN `canonical_path`; canonical only reads/presents. Failed final never auto-starts and has explicit retry only. Убрать 404/create как обычный UI step, не нарушая cleanup таймера и abort.
8. В `companyReportTypes`, `CompanyReportContent`, Claims handoff helper и tests закрепить новый contract без untrusted slug и без location-state data.
9. Добавить только scoped `.company-entry-*` CSS, использовать существующие breakpoints/token palette/focus rules.

## Проверки

Targeted сначала:

`python -m pytest services/product_api/tests_unit/test_company_report_service.py services/product_api/tests_unit/test_company_reports_api.py -q`

`npm run test --prefix services/web_ui -- --run src/companyReport/companyReportPresentation.test.ts src/companyReport/companyReportApi.test.ts src/components/company-report/CompanyReportInnForm.test.tsx src/pages/CompanyLandingPage.test.tsx src/pages/CompanyReportPage.test.tsx src/router/AppRouter.companyPage.test.tsx src/claims/companyReportHandoff.test.ts src/pages/ClaimStep2Page.test.tsx`

После них:

`python -m pytest services/product_api/tests_unit -q`

`npm run lint --prefix services/web_ui`

`npm run test --prefix services/web_ui`

`npm run build --prefix services/web_ui`

`git diff --check`

`services/product_api/tests/test_company_reports_api.py` запускается только если локальная disposable PostgreSQL уже доступна; production DB не используется.

## Review focus

- API/UI compatibility and additive contract.
- Direct SPA opening, auth gate and no redirect loops.
- Async idempotency and one in-flight form submit.
- A11y/focus/mobile behavior.
- INN handling and no leakage of raw/provider/SEO publication data.
- Exact scope and absence of migrations/deploy changes.
