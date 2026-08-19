# Итерация 18 — Frontend H1: implementation plan

Статус: reviewed design draft / DevFlow planning input; implementation не утверждена
Specification:
docs/development/iterations/iteration-18-company-report-h1-frontend.md

Stage map не заменяет будущий план на merged backend contract. Перед любыми
frontend-изменениями DevFlow planner фиксирует exact production/test/fixture
manifest, а независимый plan reviewer его утверждает.

## 1. Preconditions

1. Iteration 17 merged and public-h1 DTO is stable.
2. Backend golden responses cover complete, partial, unpublished and
   gate-disabled cases.
3. Current plain/canonical lifecycle tests pass on main.
4. Final changed-file manifest is approved before implementation.

## 2. Stage A — TypeScript boundary

1. Add strict TypeScript types matching company_public_h1_v1.
2. Add one API client for GET /company-reports/{inn}/public-h1.
3. Reject unknown contract version and malformed required top-level fields.
4. Keep legacy create/status calls isolated to plain-INN lifecycle.
5. Add safe error mapping for 400/404/409/429/500/503.

Completion: golden backend JSON parses without lossy Decimal/date conversion.

## 3. Stage B — route lifecycle

1. Preserve public AppRouter access without RequireAuth.
2. Canonical route reads H1 and never auto-creates on 404.
3. Plain route reads H1 first; only `404 company_report_not_found` creates once.
4. Poll only `409 report_pending`; `report_failed` and `report_not_eligible`
   render terminal safe states without automatic create.
5. Replace-navigate only to backend canonical_path.
6. Abort stale requests and prevent duplicate creates/polls.
7. Pass response report_id to the existing Claims handoff.

Completion: route tests prove no refresh/provider-triggering behavior for an
existing report and no cross-INN stale-state race.

## 4. Stage C — H1 block renderer

1. Replace legacy fact/scoring presentation with typed H1 block components.
2. Render only known block_order IDs and nullable typed blocks.
3. Add coverage/date, sources/limitations and neutral actions.
4. Use backend checked_date_display and monetary display values verbatim.
5. Keep exact machine values as strings; never use Number for Decimal money.
6. Remove H1 scoring, verdict, signals and AI controls without deleting
   internal/backend capabilities.

Completion: all required blocks and conditional absence cases pass component
tests with no forbidden field exposure.

## 5. Stage D — responsive and accessibility

1. Implement semantic headings, lists, definitions/tables and time elements.
2. Link limitations with aria-describedby where appropriate.
3. Ensure keyboard navigation, focus visibility and restrained aria-live.
4. Verify long names, addresses, identifiers and values at 1440/768/390 px.
5. Use safe fixtures for screenshots and visual review.

## 6. Stage E — parity and regression

1. Use shared golden DTO fixtures derived from iteration 17 safe fixtures.
2. Compare published SSR/API/SPA block order, facts, checked date and text;
   compare latest_unpublished only across API/SPA and assert noindex.
3. Test different browser timezone/locale settings.
4. Test forbidden strings/keys recursively.
5. Preserve landing form, auth return target and Claims backlink behavior.

Required commands:

    npm run lint --prefix services/web_ui
    npm run test --prefix services/web_ui
    npm run build --prefix services/web_ui
    python -m pytest services/product_api/tests_unit -q
    git diff --check

## 7. Review and delivery

- Independent code review receives the spec, plan, full diff, exact checks and
  visual QA evidence.
- Backend semantics are not changed to work around frontend assumptions.
- Deployment and production rollout require separate authorization.
- Commit/push follow repository authorization rules.
