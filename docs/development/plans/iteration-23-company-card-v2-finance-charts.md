# Технический план итерации 23 — Финансовые графики Company Card v2

Base commit: fca4cc7
Branch: feat/iteration-23-company-card-v2-finance-charts
Статус: corrected implementation plan after independent review

## 1. Ограничения

Реализовать только iteration 23. Запрещены iteration 24 arbitration,
iteration 25 rollout/full browser matrix, deploy/production activation,
live DataNewton/FNS, paid AI, production DB, provider changes, migration,
backfill, новые thresholds/units/API fields, chart dependency, responsive
screenshots/generated evidence и изменения .gitignore.

## 2. Production surfaces

Backend:

- services/product_api/src/product_api/company_reports/company_card_v2/finance.py
- services/product_api/src/product_api/company_reports/company_card_v2/public_h2.py
- services/product_api/src/product_api/company_reports/company_card_v2/public_h2_models.py
- services/product_api/src/product_api/company_reports/company_card_v2/public_h2_document.py
- services/product_api/src/product_api/company_reports/company_card_v2/service.py
- services/product_api/src/product_api/company_reports/company_card_v2/narrative/service.py
- services/product_api/src/product_api/company_reports/persistence/presentations.py
- services/product_api/src/product_api/company_reports/persistence/jobs.py

writer.py, persistence models, settings и routers не менять: limitations
берутся из preserved cell/snapshot states; текущих DB columns достаточно.

Frontend:

- services/web_ui/src/companyPublicH2/contractSchema.ts
- services/web_ui/src/companyPublicH2/contractSemantics.ts
- services/web_ui/src/companyPublicH2/parityVector.ts
- services/web_ui/src/companyPublicH2/bootstrap.tsx
- services/web_ui/src/companyPublicH2/CompanyPublicH2Page.tsx
- services/web_ui/src/companyPublicH2/CompanyPublicH2Page.css
- services/web_ui/src/companyPublicH2/financePresentation.ts
- services/web_ui/src/companyPublicH2/FinanceFacts.tsx
- services/web_ui/src/companyPublicH2/FinanceCharts.tsx
- services/web_ui/src/companyPublicH2/FinanceChartErrorBoundary.tsx
- services/web_ui/src/companyPublicH2/financeGeometry.ts
- colocated tests

Assets/release:

- services/web_ui/vite.company-public-h2.config.ts
- services/web_ui/scripts/company-public-h2-manifest.mjs
- tracked Product H2 manifest/assets
- deploy/nginx/test_company_public_h2_release.py

Fixtures/scripts/docs:

- shared/fixtures/company_public_h2_contract_v1.json
- shared/fixtures/company_public_h2_ssr_v1.json
- shared/fixtures/company_public_h2_ssr_v1.html
- shared/fixtures/company_public_h2_ssr_v1_closed.json
- shared/fixtures/company_public_h2_ssr_v1_closed.html
- iteration-specific sanitized Product fixtures
- scripts/run-iteration23-postgres-tests.ps1
- iteration specification/plan and DEVFLOW_STATE.yaml

## 3. Stage A — Baseline и RED

1. Проверить scope относительно fca4cc7.
2. Запустить существующие targeted backend/frontend tests.
3. Добавить RED tests для exact forms, per-view anchors, F1 cumulative
   geometry, F2 modes/denominator, F3 independent axes/gaps/precision,
   F4 signed ratios, F5 rows, formatter, provider/derived zero, limitations,
   v1/v2 lineage, SSR facts, bootstrap/parity/lazy и manifest closure.
4. Не исправлять unrelated baseline problems.

## 4. Stage B — Pure finance views

В finance.py:

1. Индексировать по (form, code, year) и закрытому required-form catalog.
2. Удалить global anchor и выбрать anchor независимо:
   - F1/F2/F4 — latest complete exact cells;
   - F3 — latest common valid 2110/1600 point;
   - F5 — latest available fixed-row cell.
3. Сохранить seven-calendar-year windows.
4. В arithmetic допускать только available_nonzero; provider zero оставлять gap.
5. Исправить axes:
   - F1 — cumulative endpoints;
   - F2 — [0,100] или signed endpoints;
   - F3 — отдельная axis каждой серии;
   - F4 — zero, 100 и все signed ratios.
6. Не соединять F3 gaps.
7. _series_summary считать в localcontext precision 34, ROUND_HALF_UP,
   scale 6, независимо для revenue/assets.
8. ChartFactsV1 и snapshot hash не менять.

## 5. Stage C — DTO, formatter и validators

В public_h2.py:

1. Выделить pure converter из fixture-only seam.
2. Runtime v2 вызывает build_finance_views(snapshot.finance_basis).
3. Runtime v1 не вызывает finance builder и остаётся closed.
4. Реализовать exact/compact money, Unicode minus, comma display и no float.
5. Не добавлять display fields для non-money decimals.

В public_h2_models.py:

1. Проверить endpoint containment в соответствующей axis.
2. Валидировать F1 fixed order/arithmetic/cumulative geometry.
3. Валидировать F2 seven years, state/mode, shares=100 и geometry.
4. Валидировать F3 independent axes, geometry, gaps, summaries и YoY.
5. Валидировать F4 denominator equivalence/keyed intervals.
6. Валидировать F5 fixed rows/labels/years/YoY.
7. Coverage cross-rule: available требует non-null; partial может быть
   non-null; null не может быть available.

## 6. Stage D — Safe limitations

Writer/snapshot schema не менять.

1. Читать только существующие FinanceCellV1.state и preserved limitations.
2. Для relevant view/code/window переносить missing, zero_unverified,
   conflict, invalid и decimal_transport_lossy.
3. Детерминированно deduplicate public codes.
4. Не создавать finance_failed и не выводить provider failure из missing.
5. Добавлять только finance_denominator_non_positive и
   receivables_collection_unassessed.
6. Complete → available; non-null с gaps/invalid denominator → partial;
   unbuildable null → missing.
7. Tests проверяют exact links и отсутствие invented state.

## 7. Stage E — Atomic unresolved v2 pin

В persistence/presentations.py:

1. Ввести H2_PUBLICATION_POLICY_V1, H2_PUBLICATION_POLICY_V2, accepted closed
   set и new-finalization policy v2.
2. Добавить helper create/reuse unresolved pin по exact report/snapshot/chart/
   evidence identity.
3. Под subject/H2 lock проверить все pins report lineage:
   - reuse exact unresolved;
   - не создавать v2 поверх v1;
   - при отсутствии lineage выделить generation и создать v2;
   - mixed policy/identity reject;
   - existing resolved lineage блокирует новую policy lineage.
4. Не вызывать helper из GET.

В persistence/jobs.py:

1. В existing fenced v3 completion transaction после validation snapshot и
   до commit сохранить/reuse report, outbox и unresolved pin.
2. Report/outbox/pin составляют одну atomic transaction.
3. Retry возвращает existing report/outbox/pin без новой generation.
4. Historical terminal report без lineage не backfill-ится.
5. Rollback не оставляет partial rows.

Unit tests:

- services/product_api/tests_unit/test_company_card_v2_finance_publication_policy.py
- services/product_api/tests_unit/test_company_card_v2_presentations.py

Integration:

- services/product_api/tests/test_company_report_presentations.py

Cases: new v2 unresolved, retry, rollback, concurrent/idempotent completion,
old unresolved v1, resolved v1, mixed identity/policy.

## 8. Stage F — Narrative и resolver

Narrative service:

1. Найти exact unresolved pin report и one unambiguous saved policy.
2. Рассчитать projection/digest по этой policy.
3. Append/reuse resolved pin с той же policy.
4. Не использовать writer default или digest heuristic.
5. Exact existing row reuse; mismatch reject.

company_card_v2/service.py:

1. Разрешить saved policy v1/v2.
2. v1 строит legacy closed, v2 — snapshot-derived finance.
3. Сравнить exact stored digest.
4. Unknown policy/mismatch fail-closed.
5. GET не делает pin/report writes.

Tests покрывают old resolved/unresolved v1, new v2, digest mismatch и no GET writes.

## 9. Stage G — Fixtures и SSR

1. Обновить dense company_public_h2_contract_v1.json для F1–F5.
2. Unqualified company_public_h2_ssr_v1.json/html сделать finance-enabled v2.
3. До изменения сохранить legacy closed projection отдельно в
   company_public_h2_ssr_v1_closed.json/html.
4. Legacy report fixtures не переписывать.

public_h2_document.py рендерит пять articles. Available/partial содержат
heading, caption, semantic table/dl, headers/cells, exact strings, gaps,
limitations и empty enhancement host. Null содержит factual missing и
preserved limitations, но не SVG. Closed-v1 и finance-v2 goldens проверяются
отдельно.

## 10. Stage H — TypeScript contract

contractSchema.ts экспортирует exact F1–F5, money, axis, interval, point,
period/summary/cell interfaces. Integer leaves используют StrictJsonInteger,
Decimal leaves — canonical strings.

contractSemantics.ts зеркалит Python invariants exact arithmetic без Number,
проверяет independent F3 axes, coverage/limitations и сохраняет CJSON/digest.

Display helper:

- money — backend display_exact/display_compact;
- share/YoY — canonical string + literal percent suffix;
- multiple — canonical string + multiplication sign;
- F4 — canonical string + literal ₽ из 100 ₽;
- без Number, Intl и client rounding.

## 11. Stage I — SSR/React parity и bootstrap

parityVector.ts включает article IDs/order, table/dl kind, captions, row/column
headers, cells, gaps, limitations и empty enhancement hosts.

FinanceFacts.tsx воспроизводит SSR factual structure, сохраняет её после
enhancement, не делает fetch и использует approved display helper.

bootstrap.tsx:

1. Parse state, validate binding/digest и сравнить expected/SSR vector.
2. При mismatch не создавать observer/import и сохранить SSR.
3. После pre-takeover parity создать root и сохранить handle.
4. Проверить React factual vector и лишь затем arm lazy controller.
5. Teardown disconnects observer, invalidates import generation и unmounts
   stored root ровно один раз.
6. Stale import result не mount-ит chart.
7. Post-mount failure остаётся local и не удаляет factual root.

Tests: parse/binding failure, SSR/React parity mismatch, zero import on mismatch,
root unmount, observer disconnect, stale import и unsupported
IntersectionObserver fallback.

## 12. Stage J — Interactive charts и styling

Создать financeGeometry.ts, FinanceCharts.tsx и
FinanceChartErrorBoundary.tsx.

1. Hand-authored SVG, no dependency.
2. Dynamic import только после successful lazy arming.
3. Exact decimal parser переводит соответствующую axis в bounded layout;
   Number только для final coordinate.
4. F1 cumulative; F2 stacked/diverging; F3 two independent labelled panels
   without gap crossing; F4 signed; F5 table-first.
5. Каждый meaningful mark focusable; accessible name = metric + period +
   exact value + state.
6. Hover/focus/touch открывают один disclosure; Escape/outside/focus-exit
   закрывают. Tooltip имеет role=tooltip и aria-describedby.
7. Visible role=status aria-live=polite при error/unsupported; facts остаются;
   eager retry и factual/provider/AI/auth requests запрещены.
8. Reduced motion disables animation.
9. Reuse shell tokens; no risk colors; F5 overflow local; focus ring visible.
10. Deterministic SVG/DOM snapshots complete/gap/signed заменяют browser screenshots.

Iteration 23 не запускает responsive/zoom/screenshot rollout matrix.

## 13. Stage K — Dynamic asset manifest

1. Generate/read Vite manifest.
2. Обойти static/dynamic dependency graph.
3. Собрать reachable JS/CSS.
4. Dynamic JS/CSS положить в sorted optional_chunk_paths.
5. Проверить hashes/same-origin content-addressed paths.
6. Reject reachable non-JS/CSS under unchanged schema; unknown type не игнорировать.
7. Удалить one-JS/one-CSS assumption.

Release tests: positive optional chunk, old explicit optional_chunk_paths: [],
missing/tampered optional file, rejected unknown asset и retained old/current/
previous manifest-set compatibility. Deploy/installer не запускать.

## 14. Targeted backend tests

~~~powershell
python -m pytest services/product_api/tests_unit/test_company_card_v2_finance.py services/product_api/tests_unit/test_company_card_v2_decimal_transport.py services/product_api/tests_unit/test_company_card_v2_public_h2.py services/product_api/tests_unit/test_company_card_v2_public_h2_contract_parity.py services/product_api/tests_unit/test_company_card_v2_public_h2_document.py services/product_api/tests_unit/test_company_card_v2_public_h2_asset_manifest.py services/product_api/tests_unit/test_company_card_v2_narrative_service.py services/product_api/tests_unit/test_company_card_v2_presentations.py services/product_api/tests_unit/test_company_card_v2_finance_publication_policy.py -q
~~~

Matrices: anchors/forms, provider/derived zero, signed/denominator, independent
F3 axes, precision 34/ROUND_HALF_UP, preserved limitations/no synthetic failed,
old/new lineage и no GET writes.

## 15. Targeted frontend and asset tests

~~~powershell
npm run test --prefix services/web_ui -- src/companyPublicH2/contract.test.ts src/companyPublicH2/financePresentation.test.ts src/companyPublicH2/FinanceFacts.test.tsx src/companyPublicH2/FinanceCharts.test.tsx src/companyPublicH2/CompanyPublicH2Page.test.tsx src/companyPublicH2/parityVector.test.ts src/companyPublicH2/bootstrap.test.tsx
npm run build:company-public-h2-manifest --prefix services/web_ui
python -m pytest deploy/nginx/test_company_public_h2_release.py -q -p no:cacheprovider
~~~

Проверить factual structure, suffixes, independent axes, a11y interactions,
bounded tooltip, reduced motion, unsupported observer/import failure/stale
cancel, no import before parity и deterministic SVG snapshots.

Structural performance assertions: renderer отсутствует в initial closure;
dynamic JS/CSS optional; import не вызывается до parse/binding/parity/observer,
выполняется не более одного раза; missing/error chunk сохраняет facts. Новый
numeric bundle threshold не вводится.

## 16. Disposable PostgreSQL

Создать exact runner scripts/run-iteration23-postgres-tests.ps1.

Runner проверяет explicit local disposable PostgreSQL, создаёт уникальную
temporary database, применяет Alembic head, запускает
services/product_api/tests/test_company_report_presentations.py и удаляет
только созданную им DB. Production/unknown target запрещён.

Exact command:

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-iteration23-postgres-tests.ps1
~~~

Если jsdom не докажет lazy boundary, допускается один temporary sanitized local
smoke без production/network/provider/AI, tracked scripts или evidence.

## 17. Full mandatory checks

~~~powershell
python -m pytest services/product_api/tests_unit -q
python -m pytest services/gateway_api/tests -q
npm run lint --prefix services/web_ui
npm run test --prefix services/web_ui
npm run build --prefix services/web_ui
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-iteration23-postgres-tests.ps1
python -m compileall services/product_api/src/product_api shared
git diff --check
git status --short --branch
~~~

Если тот же disposable instance поддерживает общий Product integration suite,
дополнительно выполнить python -m pytest services/product_api/tests -q.
Python lint/type-check в repository не настроены и не заявляются.

## 18. Review и completion

Independent code review проверяет только iteration 23 scope, atomic jobs.py
pin creation, v1 compatibility, saved-policy narrative/resolver, independent
F3 axes, no synthetic failed, provider zero omission, explicit Decimal context,
SSR/React structural parity, post-parity lazy arm/cleanup, exact a11y names/live
status, optional_chunk_paths: [] compatibility, unknown asset rejection,
separate closed/finance goldens, disposable PostgreSQL и отсутствие generated
evidence/.gitignore changes.

После VERDICT: READY:

1. Поставить iteration 23 в ready_for_merge; branch сохранить, commit оставить pending.
2. Проверить staged paths на secrets/raw/generated artifacts.
3. Создать один conventional commit и push feature branch.
4. PR, merge и deploy не выполнять.
5. Итог перечисляет policy lineage, v1 compatibility, finance/geometry/display/
   limitations, SSR/React/lazy/a11y, manifest, no-migration и exact test results.
