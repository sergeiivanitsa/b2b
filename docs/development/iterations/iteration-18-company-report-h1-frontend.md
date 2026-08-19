# Итерация 18 — Публичная страница H1 CompanyReport

ID: 18
Slug: company-report-h1-frontend
Статус спецификации: reviewed planning_input; runtime implementation не утверждена
Зависимость: merged iteration 17

После merge iteration 17 документ становится source input для отдельного
DevFlow planning/plan-review на актуальном backend DTO. Final changed/test
manifest утверждается тогда; этот документ не разрешает начинать frontend-код.

## 1. Цель

Перевести публичную React-страницу /company/{inn}-{slug} на strict
company_public_h1_v1 DTO и утверждённый H1 block manifest. Браузер отображает
backend semantics без повторной интерпретации provider paths, snapshot
selection, timezone или Decimal unit/rounding.

## 2. Public access

- Страница и H1 JSON endpoint доступны anonymous и authenticated users
  одинаково.
- RequireAuth/RequireRole не оборачивают company route.
- Auth требуется только там, где его требует существующий Claims handoff после
  явного action; сама карточка остаётся публичной.
- Contacts, scoring, verdict и AI controls отсутствуют именно в H1
  presentation.

## 3. Data source

Единственный factual source страницы:

    GET /company-reports/{inn}/public-h1

SPA не использует legacy latest response как H1 fact source. Из legacy
create/status endpoints разрешён только lifecycle plain-INN flow до появления
finalized H1 response.

Top-level report_id является identity показанного snapshot и передаётся в
prepare_claim. canonical_path принимается от backend; slug и company-name
precedence не вычисляются в TypeScript.

## 4. Entry and canonical flow

### Canonical key

1. Parse strict 10/12-digit INN from company key.
2. Request public-h1.
3. If response canonical_path differs, replace-navigate to it.
4. Render returned projection.
5. A canonical 404 does not create a report automatically.

### Plain INN

1. Request public-h1.
2. On success replace-navigate to response canonical_path and render it.
3. On `409 report_pending` poll the existing status endpoint.
4. On `409 report_failed` or `409 report_not_eligible`, show the terminal safe
   state and do not create/refresh.
5. On `404 company_report_not_found` only from a plain key, call existing create
   endpoint once.
6. After finalized status, request public-h1 and use its canonical_path.
7. Duplicate submit/poll/navigation remains idempotent and abortable.

Existing report access never performs a refresh/provider request. Refresh
button and TTL remain out of scope.

## 5. Page manifest

Rendered order comes from block_order but every ID is checked against a local
strict allowlist:

1. breadcrumbs;
2. identity_status;
3. known_summary;
4. in_page_navigation when eligible;
5. coverage_checked_at;
6. requisites;
7. finance when non-null;
8. arbitration when non-null;
9. bankruptcy when non-null;
10. tax when non-null;
11. management when non-null;
12. sources_limitations;
13. neutral_actions;
14. internal_links when supplied and identifier-resolved.

Unknown future block IDs fail safe: they are not rendered and produce a
development/test contract failure, not arbitrary DOM.

## 6. Display policy

### Date

- Display checked_date_display exactly as returned.
- Keep checked_at available for machine-readable time datetime.
- Do not call browser-local date formatting for the report date.

### Money

- Display backend monetary display_value only when unit_policy is active.
- Exact Decimal strings may be used for accessible machine context but never
  converted through JavaScript Number.
- Missing is not zero; negative values retain sign and neutral styling.
- YoY uses backend value/display and visible periods.

### Text

- Tax and bankruptcy wording comes from allowlisted backend text/code mapping.
- UI does not generate stronger conclusions from boolean/count/empty states.
- Limitation text is adjacent or directly linked by aria-describedby.

## 7. Page states

| State | Behavior |
| --- | --- |
| Initial loading | Stable skeleton/status with aria-live |
| Pending new report | Existing staged progress and cancellable polling |
| Complete | All visible typed blocks |
| Partial | Available facts plus prominent coverage/limitations |
| `report_failed`/`report_not_eligible` | Safe search/support state; no automatic create or invented facts |
| Not found canonical | Not-found state; no auto-create |
| Invalid INN/key | Local validation error |
| 429/503 | Safe retryable service message |
| Contract mismatch | Fail-safe page error and telemetry-safe code |

## 8. Privacy and forbidden presentation

No component, metadata, data attribute or hidden JSON renders:

- phone, email, websites or social links;
- manager INNFL, manager person records without management_privacy_v1 or
  unapproved owner identifiers/person data;
- FSSP indirect flags;
- raw content/parties/documents not in typed DTO;
- scoring points/level, verdict, probability or rating;
- signals or AI explanation/control;
- provider endpoint, hashes, request IDs, latency or raw errors.

## 9. Responsive and accessibility

- Semantic h1/h2 hierarchy and labelled definition/table structures.
- Keyboard-operable navigation/actions and visible focus.
- aria-live for lifecycle changes, not for every poll tick.
- Tables/cards wrap long identifiers and amounts without horizontal page
  scrolling at 1440, 768 and 390 px.
- Color is not the sole carrier of status/limitation.
- Published SSR text and SPA text for the same pinned golden DTO are
  equivalent; latest_unpublished has API/SPA parity and remains noindex.

## 10. Expected changed surfaces

Expected frontend scope:

    services/web_ui/src/companyReport/companyReportApi.ts
    services/web_ui/src/companyReport/companyReportTypes.ts
    services/web_ui/src/companyReport/companyReportPresentation.ts
    services/web_ui/src/components/company-report/CompanyReportContent.tsx
    services/web_ui/src/components/company-report/ new H1 block components
    services/web_ui/src/pages/CompanyReportPage.tsx
    services/web_ui/src/router/AppRouter.tsx only if wiring requires it
    services/web_ui/src/index.css or scoped company-report styles
    targeted TypeScript/component/router tests

Backend source semantics, DB, provider, Gateway, deployment and nginx are not
changed in iteration 18.

Перечень выше является expected surface для planning input, а не финальным
manifest. DevFlow planner обязан назвать точные production/test/fixture files
после merge iteration 17, и plan reviewer должен утвердить их до реализации.

## 11. Test requirements

Contract/API:

- strict parsing of company_public_h1_v1 and rejection of malformed DTO;
- public request with no auth dependency;
- report_id/canonical_path preserved end to end.

Flow:

- canonical load never creates report;
- plain existing load redirects without create;
- plain exact 404 creates once, polls and redirects;
- plain report_pending polls; report_failed/report_not_eligible never create;
- stale request cannot replace state after INN navigation;
- prepare_claim receives displayed report_id.

Presentation:

- exact block order/conditions;
- complete/partial/failed/coverage states;
- backend date unaffected by browser timezone/locale;
- backend money display rendered without Number conversion;
- approved tax/bankruptcy/management wording;
- recursive absence of contacts/score/verdict/signals/AI;
- keyboard, semantics and mobile long-value cases.

Required commands:

    npm run lint --prefix services/web_ui
    npm run test --prefix services/web_ui
    npm run build --prefix services/web_ui
    python -m pytest services/product_api/tests_unit -q
    git diff --check

Product API unit suite is a touched-contract regression; iteration 18 does not
change backend behavior.

## 12. Visual QA

Verify representative complete, partial, long-name/long-address and
missing-optional fixtures at 1440, 768 and 390 px. Screenshots must use safe
fixtures, not production raw or personal contacts.

## 13. Out of scope

- Provider/schema/lifecycle changes.
- Refresh report button and TTL.
- New SEO publication rollout or sitemap policy.
- Contacts/FSSP/score/verdict/AI.
- Deployment and production changes.

## 14. Acceptance

- Public page consumes only company_public_h1_v1 for facts.
- Published golden response yields equivalent SSR/API/SPA facts/text/order;
  latest_unpublished yields API/SPA parity and remains noindex/SSR-404.
- Existing report opens without provider request; canonical 404 does not create.
- Forbidden data and conclusions are absent.
- Frontend checks and touched backend regression pass.
- Independent review and visual QA have no blockers.
- Отдельный DevFlow planning/review на merged iteration 17 утверждает final
  manifest; planning-input сам по себе не разрешает runtime changes.
