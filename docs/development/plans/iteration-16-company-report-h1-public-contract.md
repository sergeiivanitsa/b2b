# Итерация 16 — H1 public contract: corrective documentation plan

Статус: approved documentation plan
Contract: company_public_h1_v1
Specification:
docs/development/iterations/iteration-16-company-report-h1-public-contract.md

## 1. Назначение

Итерация 16 остаётся только документационной. Она закрывает продуктовый
контракт H1, фиксирует архитектурные решения после первого независимого review
и делит runtime на две последовательные итерации. Их spec/plan-файлы являются
reviewed planning inputs, но не разрешают реализацию без нового DevFlow
planning/plan-review на актуальном `main`:

- 17 — backend projection, snapshot resolution, optional enrichments и API;
- 18 — публичная React presentation поверх принятого backend DTO.

Runtime-код, БД, provider calls, UI и production в этой ветке не меняются.

## 2. Закрытые решения

### Snapshot и публикация

- Active publication pin является source of truth для indexable canonical H1.
- При отсутствии active publication используется latest eligible
  complete/partial snapshot с normalized data и exact identity; failed или
  unusable newer run пропускается. Projection получает
  projection_scope=latest_unpublished и indexable=false.
- Новый finalized run не меняет опубликованную страницу до controlled
  republish.
- Для active publication SSR и H1 API вызывают один resolver и возвращают
  одинаковый pinned report_id; latest_unpublished имеет только API/SPA parity.

### Backend boundary

- Точный endpoint: GET /company-reports/{inn}/public-h1.
- Endpoint публичный, без auth и query parameters.
- Он не выполняет provider/AI/worker/job/write.
- DTO strict и versioned: company_public_h1_v1; несовместимая версия получает
  новый route suffix.
- Projection computed; отдельная таблица и миграция БД не нужны.

### Дата и форматирование

- Exact checked_at — UTC ISO report.generated_at.
- Calendar/display policy — checked_date_msk_v1, timezone Europe/Moscow.
- Backend передаёт checked_date, date display и monetary display strings.
- SPA не повторяет timezone conversion и Decimal rounding.

### Required и optional datasets

- Required остаются counterparty, finance, arbitration.
- Только required определяют complete/partial/failed, completeness и required
  freshness.
- Snapshot v2 добавляет отдельный optional_datasets envelope; v1 читается как
  пустой envelope.
- Optional tax_info/bankruptcy failure влияет только на H1
  coverage/limitations.

### Evidence

- thousand_rub — candidate, а не активная unit policy.
- До finance_unit_evidence_v1 абсолютные суммы H1 отсутствуют.
- Tax, bankruptcy и owners требуют отдельных official/safe schema artifacts.
- Не прошедший schema/operational gate означает not_requested, а не guessed
  mapping.

## 3. Corrective-pass manifest

Изменяются только:

    docs/development/ROADMAP.md
    docs/development/DEVFLOW_STATE.yaml
    docs/development/iterations/iteration-16-company-report-h1-public-contract.md
    docs/development/plans/iteration-16-company-report-h1-public-contract.md
    docs/development/iterations/iteration-17-company-report-h1-backend.md
    docs/development/plans/iteration-17-company-report-h1-backend.md
    docs/development/iterations/iteration-18-company-report-h1-frontend.md
    docs/development/plans/iteration-18-company-report-h1-frontend.md

## 4. Выполненные исправления первого review

1. Finance unit переведена из утверждённого факта в candidate policy с
   блокировкой абсолютных значений.
2. Выбран один published/latest-unpublished snapshot resolver.
3. Зафиксированы endpoint, DTO identity, computed projection и timezone.
4. Определена required/optional lifecycle matrix и snapshot v2 envelope.
5. Tax/bankruptcy/owners получили блокирующие schema evidence gates.
6. Итерации 14–15 синхронизированы с merge commit в main.
7. Runtime разделён на roadmap iterations 17 и 18.
8. SPA явно публичная; authentication не является условием H1.
9. Arbitration matrix дополнена incomplete-target и malformed semantics.
10. Старая progress table roadmap синхронизирована с merged state.

## 5. Gates итерации 17

| Gate | Доказательство | Поведение без gate |
| --- | --- | --- |
| Finance unit | DataNewton official/support contract или versioned ГИР БО/ОКЕИ matrix | Unit unknown; absolute values absent. |
| Tax schema | Official schema или safe fixture с exact paths/types/scope/date | tax_info=not_requested. |
| Bankruptcy schema | Official schema или safe fixture с participants/types/pagination | bankruptcy=not_requested. |
| Manager privacy | management_privacy_v1 by legal form/person category | Manager person records hidden. |
| Owner schema/privacy | Safe fixture, share semantics, entity type и management_privacy_v1 | Owners hidden/not requested. |
| Operational | Tariff, quotas, pagination, retry/cache/timeout budget | Optional calls disabled. |

Evidence artifacts не содержат production raw, secrets, contacts или
необезличенные лишние данные. Live probes требуют отдельного разрешения.

## 6. Порядок следующих итераций

### Итерация 17

1. Зафиксировать evidence registry и enabled gates.
2. Добавить snapshot v2 parser/writer с legacy v1 compatibility.
3. Реализовать pure normalizers и required-only lifecycle invariant.
4. Реализовать computed H1 projection и strict DTO.
5. Реализовать один resolver для SSR и public API.
6. Перевести SSR renderer на H1 projection.
7. Выполнить backend targeted/regression checks и independent review.

### Итерация 18

1. Обновить TypeScript contract под утверждённый DTO iteration 17.
2. Перевести публичную страницу и entry flow на public-h1.
3. Собрать block renderer без client-side source interpretation.
4. Добавить accessibility/responsive и error states.
5. Проверить published SSR/API/SPA golden parity и unpublished API/SPA parity.
6. Выполнить frontend checks, visual QA и independent review.

Итерация 18 не начинается до merge стабильного backend contract итерации 17.

## 7. Backward compatibility

- Legacy GET /company-reports/{inn}, status и create endpoints не меняются в
  iteration 16.
- Iteration 17 добавляет новый endpoint, не меняя существующий response.
- Snapshot v1 immutable и читается без rewrite; новые reports используют v2.
- Publication report_id/hash/canonical pin сохраняет текущую controlled index
  policy.
- Claims handoff, signals, scoring и AI не начинают использовать новые H1 facts.
- H1 presentation исключает score/verdict/contacts, но другие существующие
  internal/product surfaces не удаляются.

## 8. Документационные проверки

    parse docs/development/DEVFLOW_STATE.yaml
    verify unique and ordered iteration IDs 1..18
    verify referenced iteration/spec/plan files exist
    verify Markdown code fences are balanced
    verify no trailing whitespace
    git diff --check
    independent read-only review

Runtime test suites не применимы, потому что corrective pass не меняет runtime.

## 9. Completion gate

- Все P1/P2 первого review адресованы в документации.
- Roadmap, state, H1 spec и планы 17–18 не противоречат друг другу.
- Finance и opaque provider schemas не представлены доказанными до evidence.
- Endpoint/snapshot/lifecycle/timezone решения однозначны.
- Документационные проверки проходят.
- Повторный independent reviewer возвращает VERDICT: APPROVED.
- Commit/push выполняются только по отдельной явной команде пользователя.
