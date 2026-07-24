# Итерация 11 — Страница компании

ID: `11` · Slug: `company-page` · ветка: `feat/iteration-11-company-page`

## Цель и границы

Добавить защищённую SPA-страницу компании, которая показывает безопасную
проекцию существующего CompanyReport v1: машинную оценку взыскуемости,
доступные факты, основания, ограничения и явный CTA к claims UI.

Страница использует только существующие endpoints:

```text
GET  /company-reports/{inn}
GET  /company-reports/{inn}/status
POST /company-reports
```

Меняются только frontend и документация. Нет изменений Product API, Gateway,
схемы БД, миграций, зависимостей, SSR/prerender, SEO metadata/canonical headers
или Claims backend.

## Маршрут, доступ и URL

Маршрут защищён существующим `RequireAuth`:

```text
/company/:companyKey
```

Он доступен после cookie-session; сервер остаётся источником прав:
CompanyReport API разрешает только активного `owner`/`admin`/`member` либо
`superadmin`. `401`/`403` отображаются безопасно, без попытки обходить RBAC.

`companyKey` принимается только в синтаксисе:

```text
{inn}-{slug}
```

где `inn` — ровно 10 либо 12 ASCII-цифр, а `slug` — непустой нижнерегистровый
ASCII slug `[a-z0-9]+(?:-[a-z0-9]+)*`. Парсер возвращает только `inn`; slug не
отправляется в API и не трактуется как факт о компании. Некорректный путь
показывает локальную ошибку и не выполняет запросов.

Это канонизируемый клиентский синтаксис URL, но не серверная
SEO-каноникализация: не создаются `<link rel="canonical">`, redirect, sitemap,
robots, SSR/SSG и не проверяется соответствие slug названию компании, поскольку
текущий API не предоставляет серверный canonical slug.

## UX и состояния

| Состояние | Поведение |
|---|---|
| Initial loading | Один `GET /company-reports/{inn}` без query-параметра; никаких POST, AI-вызовов или платных side effect. |
| `200 complete` | Показываются все allowlisted блоки, machine score и CTA. |
| `200 partial` | Показываются доступные блоки, заметный статус неполноты и безопасные warnings; отсутствующие значения не заменяются нулями. |
| `200 failed` с snapshot | Показывается безопасный failed state, имеющиеся completeness/warnings и, если API его вернул, отдельный machine score; CTA нового запуска только явный. |
| `200 failed` без snapshot | Показываются только safe failure code/message/retryable; факты, signals, scoring и AI не подставляются. |
| `404 company_report_not_found` | Явная кнопка «Создать отчёт». Только нажатие выполняет `POST /company-reports` с `{inn}`. |
| `409 report_pending` | Начинается polling status endpoint; никакого POST. |
| POST `202` | Экран pending и polling `GET /company-reports/{inn}/status`. |
| Status `pending` | Единственный следующий запрос через фиксированный `STATUS_POLL_INTERVAL_MS = 3000`; не более одного in-flight запроса. |
| Status terminal (`complete`/`partial`/`failed`) | Polling прекращается, затем выполняется обычный `GET /company-reports/{inn}` и рендерится terminal response. |
| `400`, `409 state conflict`, `429`, `503`, `500`, network error | Безопасное понятное сообщение и явная кнопка повторить подходящую операцию; автоматического retry нет. |
| `401`/`403` | Сообщение о необходимости актуальной сессии/разрешения и ссылка на вход/возврат; доступ не предполагается на клиенте. |

Polling обязан использовать `AbortController`, `clearTimeout` и cleanup при
unmount, смене `companyKey`, ручном retry и terminal state. Интервал инженерно
ограничен константой 3 секунды; таймер не создаётся до завершения предыдущего
status request.

## Данные и приватность

Frontend определяет узкие TypeScript DTO для реально отображаемых полей и
рендерит только следующий allowlist:

- Counterparty: `short_name`, `full_name`, `inn`, `ogrn`, `kpp`, `legal_form`,
  `is_active`, `status_code`, `status_text`, `registration_date`,
  `dissolved_date`, `years_from_registration`, `address.line_address`.
- Finance: `latest_year`, `years` и из period только `year`, `total_assets`,
  `current_assets`, `cash_and_equivalents`, `equity`, `accounts_payable`,
  `revenue`, `net_profit`; также `unit`.
- Arbitration: `total_cases`, `returned_cases`, `is_complete`, `role_summary`,
  `status_summary`, `result_summary`, `claim_amounts_by_currency`.
- Report metadata: status, timestamps, completeness, datasets’ status/source
  time/safe warning/failure, report/freshness warnings и usability flags.
- Signals: только `code`, `category`, `direction`, `strength`, `confidence`,
  `period`, safe warnings.
- Scoring: level, exact `score_points`, confidence value, reasons, domain
  breakdown и safe warnings.
- AI: только explicit-response `status`; при `ok` — six reader-facing fields
  (`overall_conclusion`, factors, risks, urgency, next step, limitations); при
  failure — безопасный status without provider diagnostics.

Запрещено отображать или передавать дальше `raw_payload`, provider headers/keys,
endpoint/request IDs, response hashes, worker/job/lease data, `factual_basis`,
`evaluation_basis`, signal source paths, arbitrary case/party/document data, AI
technical metadata и любые неallowlisted поля.

Все decimal-поля приходят и остаются строками: frontend не преобразует их в
`number`, не округляет, не делает currency inference и не добавляет символ
рубля. `finance.unit === "provider_units_unknown"` отображается как неизвестная
единица; финансовое значение остаётся точной строкой с соответствующей
пометкой. Arbitration amount показывается только в
`claim_amounts_by_currency` рядом с явно заданным API currency key;
отсутствующее значение не подменяется `0`.

## Presentation

Hero использует allowlisted short/full name, иначе нейтральное «Компания с ИНН
{inn}». Он содержит назначение страницы: «оценка финансового состояния и
возможности взыскания задолженности».

Machine scoring — самостоятельный блок с level, points, confidence, reasons и
warnings. Он визуально и семантически отделён от AI. `insufficient_data` не
получает числовой score и отображается как недостаточность доказательств, а не
отрицательный вывод.

AI-пояснение отсутствует при первоначальной загрузке. Только явная кнопка
«Показать AI-пояснение» выполняет
`GET /company-reports/{inn}?include_ai_explanation=true`; запрос отменяем при
unmount, не запускается повторно автоматически и не меняет machine
score/report. AI failure — неблокирующее безопасное сообщение и явный повтор
кнопкой.

Labels signal codes определяются одной детерминированной map только для
текущего реестра из 13 кодов:

```text
counterparty.active                         → Компания отмечена действующей
counterparty.dissolved                      → Компания отмечена прекратившей деятельность
counterparty.long_operating_history         → Длительный срок деятельности
counterparty.status_conflict                → Противоречивые сведения о статусе
finance.negative_equity                     → Отрицательный капитал
finance.revenue_decline                     → Снижение выручки
finance.net_loss                            → Чистый убыток
finance.cash_shortfall                      → Недостаток денежных средств
finance.high_accounts_payable               → Высокая кредиторская задолженность
arbitration.high_respondent_case_count      → Много дел в роли ответчика
arbitration.respondent_case_growth          → Рост дел в роли ответчика
arbitration.open_cases                      → Открытые арбитражные дела
arbitration.frequent_plaintiff              → Частые обращения в суд как истец
```

Неизвестный code получает нейтральный label «Сигнал требует проверки» и может
показать экранированный code как технический идентификатор; ему не
приписывается направление, причина или бизнес-вывод. Direction/strength/
confidence отображаются только как API-provided descriptors.

CTA «Оценить конкретный долг» переводит на `/claims` c минимальным in-memory
`location.state.companyReportContext`: `{ inn, companyName?, reportId? }`.
Контекст не записывается в Claims API, не отправляется в backend и не содержит
scoring, signals, warnings, реквизиты, raw facts или AI. Полная интеграция
Claims — scope iteration 13.

## Accessibility и responsive

Используются семантические `main`, `header`, `section`, заголовки в
последовательном порядке, таблицы только для табличных финансовых данных, списки
для reasons/warnings, видимые label для status и `aria-live="polite"` для
загрузки/pending/error. Кнопки имеют понятные names, disabled состояние и не
полагаются только на цвет; focus остаётся видимым. На ширинах до 1024px блоки
становятся одной колонкой, табличные данные имеют горизонтальный scroll wrapper,
а на малых экранах CTA занимает доступную ширину без обрезки.

## Out of scope

Public/anonymous report API, SEO, SSR/SSG/prerender, metadata/canonical headers,
backend Claims handoff, создание претензии, payment, мониторинг, редактирование
scoring, новые datasets/signals/scoring rules, изменение API projection,
provider/persistence/worker и миграции.

## Acceptance criteria

- `/company/{inn}-{slug}` защищён аутентификацией и валидирует URL до API call.
- Initial GET не создаёт отчёт и не запускает AI.
- `404` предлагает только явный POST; pending корректно poll’ится с
  cancellation и после terminal status загружает report.
- Complete, partial, snapshot-failed, infrastructure-failed, not-found и
  transport/auth errors безопасны и различимы.
- Display строго ограничен allowlist; `factual_basis` и raw/internal поля не
  рендерятся.
- Decimal strings и unknown unit не искажаются.
- Machine result и AI visually/semantically separated; AI исключительно по
  explicit click.
- CTA переносит только минимальный UI context без Claims backend integration.
- Desktop/mobile/a11y и unit/component/router/API tests проходят.
- BLOCKER: отсутствует.
