# Roadmap разработки сервиса оценки взыскуемости задолженности

## 1. Назначение документа

Этот документ фиксирует последовательность инженерных итераций продукта и является источником верхнеуровневого scope для автоматизированного оркестратора разработки.

Продуктовый путь:

```text
ИНН должника
→ получение и нормализация данных
→ CompanyReport
→ фактические сигналы
→ скоринг взыскуемости
→ понятное объяснение результата
→ API и страница компании
→ SEO-публикация
→ переход к оценке конкретного долга и claims-flow
```

Каждая итерация реализуется отдельно:

```text
одна спецификация
→ одна ветка
→ один pull request
→ ручной merge
```

Оркестратор не должен самостоятельно менять цели, scope, out of scope, критерии приёмки или бизнес-правила итерации.

## 2. Текущий прогресс

| Итерация | Slug | Статус |
|---:|---|---|
| 1 | `provider-foundation` | Завершена |
| 2 | `provider-datasets` | Завершена для реализованных методов |
| 3 | `provider-probe` | Завершена |
| 4 | `normalizers` | Завершена для `counterparty`, `finance`, `arbitration` |
| 5 | `company-report` | Завершена |
| 6 | `persistence` | Завершена |
| 7 | `signals` | Обязательная часть завершена |
| 8 | `scoring` | Завершена |
| 9 | `ai-explanation` | Завершена |
| 10 | `company-reports-api` | Завершена |
| 11 | `company-page` | Завершена |
| 12 | `seo-publishing` | Завершена |
| 13 | `claims-handoff` | Завершена |
| 14 | `company-report-entry-flow` | Завершена |
| 15 | `company-report-landing-visual` | Завершена |
| 16 | `company-report-h1-public-contract` | Завершена |
| 17 | `company-report-h1-backend` | Завершена |
| 18 | `company-report-h1-frontend` | Завершена |
| 19 | `company-card-v2-contract-evidence` | Завершена |
| 20 | `company-card-v2-backend-foundation` | Завершена |
| 21 | `company-card-v2-ai-narrative` | Завершена |
| 22 | `company-card-v2-page-shell` | Завершена |
| 23 | `company-card-v2-finance-charts` | Завершена |
| 24 | `company-card-v2-arbitration-charts` | Завершена |
| 25 | `company-card-v2-qa-rollout` | Запланирована |

## 3. Инженерные правила roadmap

- Номер и `Slug` итерации после утверждения не меняются.
- До реализации каждой итерации создаются отдельная спецификация и implementation plan.
- При противоречии между roadmap, спецификацией и текущим кодом работа останавливается.
- Нельзя молча расширять scope или менять контракты завершённых итераций.
- Все доменные расчёты должны быть детерминированными, если в scope прямо не указано обратное.
- Отсутствующие данные нельзя подменять нулём, отрицательным фактом или положительным выводом.
- Raw payload, API-ключи и чувствительные транспортные данные не должны попадать в публичные модели.
- Каждая итерация обязана сохранять совместимость с уже утверждёнными контрактами либо явно включать их версионирование.
- Commit, push и создание pull request разрешаются только после прохождения критериев приёмки.
- Merge остаётся ручным действием владельца проекта.

---

## Итерация 1 — Основа DataNewton provider

ID: 1  
Slug: provider-foundation

### Цель

Создать изолированный, безопасный и тестируемый provider layer для обращения к DataNewton без вмешательства в существующий claims-flow.

### Результат

В репозитории существует асинхронный `DataNewtonClient`, транспортный слой, единый result envelope, типизированные ошибки, нормализация идентификаторов, безопасное логирование и поддержка пакетного метода `batchCards`.

### Scope

- Валидация ИНН, ОГРН и ОГРНИП.
- Асинхронный HTTP transport.
- Timeout, retry и ограниченный backoff.
- Типизированная классификация ошибок.
- `DataNewtonResult` с метаданными запроса и response hash.
- Безопасный cache key.
- `POST /v1/batchCards`.
- Unit-тесты через mock transport.

### Out of scope

- Публичные endpoints.
- CompanyReport.
- Normalizers.
- Persistence.
- Signals и scoring.
- Frontend.
- Реальные платные запросы в unit-тестах.

### Критерии приёмки

- Provider не зависит от claims-flow.
- API key не сохраняется в result envelope, логах и cache key.
- Retry применяется только к разрешённым классам ошибок.
- Порядок batch identifiers сохраняется.
- Raw payload исключён из автоматического `repr`.
- Все provider unit-тесты проходят.
- Production HTTP не вызывается тестами.

### Зависимости

- Существующие настройки Product API.
- `httpx`.
- Документация DataNewton API.

---

## Итерация 2 — Методы DataNewton для CompanyReport

ID: 2  
Slug: provider-datasets

### Цель

Реализовать provider methods для наборов данных, необходимых будущему отчёту о компании.

### Результат

`DataNewtonClient` умеет получать доступные данные по контрагенту, финансам, арбитражу и технически поддерживаемым дополнительным наборам через единый контракт.

### Scope

- `GET /v1/counterparty`.
- `GET /v1/finance`.
- `GET /v1/taxInfo`.
- `GET /v1/arbitration-cases`.
- `POST /v1/fssp`.
- `GET /v1/bankruptcy`.
- Единый result envelope.
- Dataset-specific request validation.
- Разделение authentication и access denied.
- Unit-тесты каждого метода.

### Out of scope

- Автоматическая pagination.
- Интерпретация provider payload.
- Normalizers.
- CompanyReport.
- Автоматический выбор платных методов.
- Обход тарифных ограничений.

### Критерии приёмки

- Каждый метод использует общий transport.
- Ошибки 401 и 403 классифицируются отдельно.
- Partial failure одного dataset не ломает остальные вызовы на уровне клиента.
- В result envelope нет API key и небезопасных полей.
- Методы не выполняют скрытые дополнительные запросы.
- Все unit-тесты проходят.

### Зависимости

- Итерация 1.
- Фактическая DataNewton OpenAPI-схема.
- Доступность методов на тарифе пользователя.

---

## Итерация 3 — Безопасный DataNewton probe

ID: 3  
Slug: provider-probe

### Цель

Создать локальный инструмент для безопасного исследования реальных ответов DataNewton и проверки доступности datasets.

### Результат

CLI probe умеет работать в dry-run и live-режиме, сохраняет обезличенные метаданные, raw response, shape и manifest, продолжая работу после ошибки отдельного dataset.

### Scope

- CLI `python -m product_api.tools.datanewton_probe`.
- Dry-run по умолчанию.
- Явное подтверждение live-запросов.
- Выбор datasets.
- Сохранение `manifest.json`, `meta.json`, `raw.json`, `shape.json`.
- Атомарная запись файлов.
- Safe error metadata.
- Structural JSON shape.
- Partial-success execution.
- Exit codes.
- Unit-тесты CLI и filesystem behavior.

### Out of scope

- Автоматическая покупка или изменение тарифа.
- Production scheduling.
- Массовое получение данных компаний.
- Normalization.
- Публикация raw probes.
- Использование probe как runtime-компонента приложения.

### Критерии приёмки

- Без `--confirm-live` реальные запросы невозможны.
- API key и полный идентификатор не выводятся.
- Ошибка одного dataset не останавливает остальные.
- Raw response сохраняется только в локальной игнорируемой директории.
- Shape не содержит значения response.
- Все probe unit-тесты проходят.

### Зависимости

- Итерации 1–2.
- Локальная `.env`.
- Явное разрешение на live-запросы.

---

## Итерация 4 — Нормализация данных CompanyReport

ID: 4  
Slug: normalizers

### Цель

Преобразовать ответы доступных DataNewton datasets в строгие нормализованные доменные модели без raw payload.

### Результат

Реализованы pure normalizers и frozen-модели для:

- `CounterpartyFacts`;
- `FinanceFacts`;
- `ArbitrationFacts`.

### Scope

- Общие `SourceMetadata` и `NormalizationWarning`.
- Counterparty normalizer.
- Finance normalizer.
- Arbitration normalizer.
- Exact `Decimal`.
- Детерминированная сортировка.
- Обработка partial и malformed payload.
- Обезличенные fixtures.
- Unit-тесты моделей и normalizers.

### Out of scope

- HTTP.
- БД.
- CompanyReport aggregation.
- Persistence.
- Signals.
- Scoring.
- Пользовательские тексты.
- Интерпретация missing как zero.

### Критерии приёмки

- Normalizers принимают только `DataNewtonResult`.
- Raw payload отсутствует в нормализованных моделях.
- Одинаковый вход даёт одинаковый JSON.
- `Decimal` не преобразуется во `float`.
- Missing и malformed различаются.
- Warnings безопасны и детерминированы.
- Все normalizer unit-тесты проходят.

### Зависимости

- Итерации 1–3.
- Проверенные provider fixtures.
- Утверждённые доменные модели.

---

## Итерация 5 — CompanyReport и orchestration

ID: 5  
Slug: company-report

### Цель

Собрать нормализованные datasets в единый `CompanyReport v1` и реализовать конкурентный orchestrator с безопасной partial-failure семантикой.

### Результат

Существует чистый application flow:

```text
CompanyReportProvider
→ concurrent dataset calls
→ normalizers
→ DatasetReport
→ CompanyReport v1
```

### Scope

- `CompanyReport v1`.
- `DatasetReport`.
- Dataset statuses.
- Safe dataset errors.
- Completeness.
- Freshness.
- Concurrent orchestration.
- Partial и failed report semantics.
- Privacy tests.
- Aggregate и orchestrator unit-тесты.

### Out of scope

- Persistence.
- Signals.
- Scoring.
- API endpoints.
- Frontend.
- AI explanation.
- Автоматический запуск из runtime Product API.

### Критерии приёмки

- Доступны `counterparty`, `finance`, `arbitration`.
- Partial failure не уничтожает доступные datasets.
- Report не содержит raw payload, API key и HTTP client.
- Completeness вычисляется детерминированно.
- Freshness основана на `SourceMetadata.received_at`.
- Orchestrator не выполняет скрытых повторных запросов.
- Все unit-тесты проходят.

### Зависимости

- Итерации 1–4.
- Provider protocol.
- Нормализованные модели datasets.

---

## Итерация 6 — Persistence CompanyReport

ID: 6  
Slug: persistence

### Цель

Добавить надёжное хранение CompanyReport, dataset snapshots и журнала provider requests без изменения доменной модели отчёта.

### Результат

Реализованы ORM-модели, Alembic migration, сериализация и async repository для lifecycle:

```text
pending → complete
pending → partial
pending → failed
```

### Scope

- Таблицы subjects, reports, datasets и provider requests.
- Alembic migration.
- Snapshot serialization.
- Snapshot hash.
- Async repository.
- Pending idempotency.
- Finalization lifecycle.
- Privacy и query tests.
- Migration tests.

### Out of scope

- HTTP API.
- Signals persistence.
- Scoring persistence.
- Background workers.
- Автоматический runtime запуск CompanyReport.
- Объединение с tenant-компаниями.

### Критерии приёмки

- Используется существующий SQLAlchemy `Base`.
- Повторный pending-запрос идемпотентен.
- Финализированный snapshot не изменяется.
- Snapshot/hash детерминированы.
- Provider journal не содержит API key и raw headers.
- Migration проходит проверку.
- Все persistence unit-тесты проходят.

### Зависимости

- Итерация 5.
- Существующий PostgreSQL/Alembic stack.
- Утверждённый `CompanyReport v1`.

---

## Итерация 7 — Система фактических сигналов

ID: 7  
Slug: signals

### Цель

Преобразовать нормализованный `CompanyReport` в проверяемые фактические сигналы о юридическом статусе, финансах и арбитражной активности компании.

### Результат

Реализован публичный pure-domain контракт:

```python
evaluate_signals(
    report: CompanyReport,
) -> SignalEvaluationResult
```

Результат содержит:

- `ruleset_version="1"`;
- упорядоченный список `Signal`;
- result-level `SignalWarning`.

### Scope

- Строгие модели сигнала и factual basis.
- Expression tree.
- Period models.
- Legal-status signals.
- Financial signals.
- Arbitration signals.
- Exact Decimal comparisons.
- Rule-specific suppression.
- Confidence.
- Deterministic composition.
- Public `evaluate_signals()`.
- Совместимость с CompanyReport snapshot/hash.
- Unit-тесты Stage 1–4.

### Out of scope

- Общий score.
- Verdict.
- Probability.
- Recommendation.
- AI.
- API.
- Persistence signals.
- Frontend.
- `finance.reporting_absent` без отдельного evidence approval.

### Критерии приёмки

- Signals используют только нормализованные facts.
- HTTP, БД, raw payload и текущее время не используются.
- Один signal code встречается максимум один раз.
- Все основания воспроизводимы.
- Missing не подменяется zero.
- Result-level warnings сохраняются при пустом списке signals.
- `CompanyReport` не мутируется.
- Persistence snapshot/hash не меняются после evaluation.
- Все unit-тесты проходят.
- `finance.reporting_absent` отсутствует без evidence approval.

### Зависимости

- Итерации 4–6.
- `CompanyReport v1`.
- Утверждённая спецификация signals.
- Evidence fixture для возможного будущего Stage 5.

---

## Итерация 8 — Детерминированный скоринг взыскуемости

ID: 8  
Slug: scoring

### Цель

Преобразовать фактические сигналы и информацию о полноте данных в прозрачную детерминированную оценку перспективности взыскания.

### Результат

Реализован версионированный scoring contract, который возвращает итоговый уровень оценки, структурированные причины, confidence и предупреждения без использования AI.

Предварительные уровни результата:

```text
high
medium
low
insufficient_data
```

Окончательная модель, правила агрегации и пороги утверждаются в отдельной спецификации до production-кода.

### Scope

- Строгие модели scoring result.
- Версия ruleset.
- Детерминированные правила агрегации signals.
- Обработка positive, negative и informational signals.
- Обработка conflicting signals.
- Missing и partial data policy.
- `insufficient_data`.
- Confidence результата.
- Structured reasons.
- Stable ordering.
- Pure-domain public function.
- Unit-тесты правил, границ и перестановочной инвариантности.
- Совместимость с `CompanyReport` и `SignalEvaluationResult`.

### Out of scope

- AI.
- Генерация пользовательского текста.
- Субъективное изменение score моделью.
- API endpoints.
- Persistence scoring без отдельного решения.
- Frontend.
- Юридическая рекомендация по конкретному долгу.
- Вероятность взыскания в процентах без доказанной модели.

### Критерии приёмки

- До кода утверждены scoring model, levels, rules и thresholds.
- Одинаковый набор signals всегда даёт одинаковый результат.
- Порядок входных signals не влияет на score.
- Missing/partial не превращаются в негативный score.
- `insufficient_data` отделён от `low`.
- Каждая причина score ссылается на существующие signal codes.
- AI и текущее время не используются.
- Input models не мутируются.
- Все targeted и regression tests проходят.

### Зависимости

- Итерация 7.
- Утверждённая спецификация scoring.
- Решение о persistence scoring либо явное сохранение расчёта как ephemeral.

---

## Итерация 9 — AI-объяснение результата

ID: 9  
Slug: ai-explanation

### Цель

Сформировать понятное пользователю объяснение готового CompanyReport, фактических сигналов и детерминированного scoring result.

### Результат

AI генерирует структурированное объяснение:

- общий вывод;
- факторы в пользу взыскания;
- основные риски;
- срочность действий;
- рекомендуемый следующий шаг;
- ограничения и неполноту данных.

AI не рассчитывает score и не меняет доменный результат.

### Scope

- Строгий input envelope для AI.
- Строгая output schema.
- Prompt version.
- Model configuration.
- Безопасный redaction.
- Защита от передачи raw payload.
- Retry и typed failures.
- Fallback без AI-текста.
- Проверка соответствия текста фактам.
- Unit-тесты prompt builder и output validation.
- Mocked integration tests Gateway/OpenAI boundary.

### Out of scope

- Пересчёт score.
- Изменение signal strength или confidence.
- Новые факты, отсутствующие во входе.
- Юридическое заключение по конкретному договору.
- Публичная страница.
- SEO.
- Claims generation.
- Неконтролируемый web search.

### Критерии приёмки

- AI получает только нормализованные и разрешённые данные.
- Текст не противоречит score и signals.
- AI не может изменить машинный результат.
- Ответ проходит JSON-schema validation.
- При недоступности AI доменный отчёт остаётся пригодным.
- Prompt и output version сохраняются.
- API key и raw payload не попадают в артефакты.
- Все тесты проходят без реальных платных запросов.

### Зависимости

- Итерации 7–8.
- Существующий Gateway API.
- Утверждённая структура пользовательского объяснения.
- Выбранная модель и бюджет вызова.

---

## Итерация 10 — Интеграция CompanyReport с Product API

ID: 10  
Slug: company-reports-api

### Цель

Подключить существующие provider, orchestrator, persistence, signals, scoring и AI explanation к уже работающему Product API.

### Результат

В существующем FastAPI доступны внутренние продуктовые endpoints:

```http
POST /company-reports
GET  /company-reports/{inn}
GET  /company-reports/{inn}/status
```

Frontend обращается через существующий nginx-префикс `/api`.

### Scope

- Service layer CompanyReport.
- Создание или переиспользование pending report.
- Запуск provider/orchestrator.
- Finalization persistence.
- Расчёт signals и scoring.
- Опциональное AI explanation.
- Status polling.
- Получение последнего отчёта.
- Валидация ИНН.
- Safe error mapping.
- Idempotency.
- Rate limiting/abuse protection.
- API tests.
- Integration tests repository/service/router.

### Out of scope

- Отдельный внешний API для клиентов.
- API keys для сторонних интеграций.
- `/api/public/company-reports`.
- Новый API Gateway.
- Массовая генерация страниц.
- SEO.
- Claims-flow handoff.
- Платёжная система.

### Критерии приёмки

- Используется существующий `product_api`.
- Nginx продолжает снимать `/api`.
- Повторный запрос не создаёт конкурирующие pending reports.
- Partial report возвращается безопасно.
- Provider ошибки не раскрывают секреты.
- Status endpoint отражает реальный lifecycle.
- API не выполняет лишние платные запросы.
- Unit и integration tests проходят.
- Существующие claims endpoints не ломаются.

### Зависимости

- Итерации 5–9.
- Существующий Product API.
- Persistence migration итерации 6.
- Решение о синхронном или фоновом запуске.

---

## Итерация 11 — Страница компании

ID: 11  
Slug: company-page

### Цель

Создать пользовательскую страницу компании, отвечающую на вопрос о её финансовом состоянии и возможности взыскания задолженности.

### Результат

Доступен маршрут:

```text
/company/{inn}-{slug}
```

Страница отображает оценку взыскуемости, основания, риски, финансовые и судебные данные и переводит пользователя к следующему действию.

### Scope

- Hero:
  - название компании;
  - «оценка финансового состояния и возможности взыскания задолженности».
- Краткий итог scoring.
- Ключевые аргументы за и против взыскания.
- Financial block.
- Arbitration block.
- Legal status.
- Completeness/freshness.
- Безопасные warnings.
- Реквизиты компании в нижней части страницы.
- CTA для оценки конкретного долга.
- Loading, partial, failed и not-found states.
- Mobile responsiveness.
- Accessibility.
- Frontend unit/component tests.

### Out of scope

- Массовая публикация миллионов страниц.
- Полная SEO-инфраструктура.
- Генерация претензии на этой же странице.
- Платёжная система.
- Личный кабинет мониторинга.
- Редактирование доменного score пользователем.

### Критерии приёмки

- Страница использует реальные CompanyReport API endpoints.
- Machine score и AI-текст визуально различимы.
- Partial data не маскируется.
- Нет raw provider payload.
- CTA сохраняет контекст компании.
- Маршрут стабилен и канонизируем.
- Страница корректна на desktop и mobile.
- Component и integration tests проходят.

### Зависимости

- Итерация 10.
- Утверждённый UX страницы.
- Реализованные states API.
- Решение о server rendering/prerender для следующей итерации.

---

## Итерация 12 — SEO и массовая публикация страниц

ID: 12  
Slug: seo-publishing

### Цель

Сделать страницы компаний индексируемыми, технически корректными и пригодными для контролируемого масштабирования органического трафика.

### Результат

Страницы компаний отдаются поисковым роботам с полноценным HTML, уникальными metadata, canonical, sitemap и управляемой политикой публикации.

### Scope

- SSR, SSG или надёжный prerender.
- Уникальные title и description.
- Canonical URL.
- Robots directives.
- XML sitemap и sitemap index.
- Корректные HTTP statuses.
- Structured data, если соответствует содержанию.
- Политика index/noindex.
- Page freshness и lastmod.
- Контроль thin/duplicate content.
- Очередь или batch-процесс публикации.
- Ограниченное начальное количество страниц.
- Search Console/Яндекс Вебмастер readiness.
- Логи генерации и обновления.
- SEO tests и crawl validation.

### Out of scope

- Мгновенная публикация всех доступных компаний.
- Автоматически сгенерированные неподтверждённые факты.
- Doorway pages.
- Копирование одинакового FAQ на миллионы страниц без ценности.
- Гарантии трафика или позиций.
- Платная реклама.
- Claims generation.

### Критерии приёмки

- Search bot получает содержательный HTML без выполнения SPA JavaScript.
- Неуспешные и пустые отчёты не индексируются.
- Canonical и sitemap согласованы.
- Metadata формируется детерминированно.
- Массовая публикация имеет лимиты, pause/resume и журнал.
- Страницы с недостаточной ценностью получают `noindex`.
- Crawl не создаёт бесконечных URL.
- Lighthouse/crawl/SEO tests проходят.
- Начальный rollout выполняется контролируемой партией.

### Зависимости

- Итерации 10–11.
- Выбранная rendering architecture.
- Утверждённая стратегия массовых страниц.
- Доступ к панелям вебмастеров и аналитике.

---

## Итерация 13 — Переход к конкретному долгу и claims-flow

ID: 13  
Slug: claims-handoff

### Цель

Перевести пользователя со страницы оценки компании к практическому действию: оценке конкретного долга, подготовке претензии и предложению взыскания под ключ.

### Результат

Существующий claims-flow принимает контекст CompanyReport и не требует повторного ввода уже известных данных о должнике.

### Scope

- CTA «Оценить конкретный долг».
- Передача:
  - ИНН;
  - реквизитов должника;
  - `report_id`;
  - scoring result;
  - ключевых signal codes;
  - warnings;
  - рекомендованного следующего шага.
- Ввод пользователем:
  - суммы долга;
  - основания;
  - договора;
  - срока оплаты;
  - документов.
- Связь claim с CompanyReport.
- Переиспользование существующего claims-flow.
- Генерация досудебной претензии.
- Предложение юридического сопровождения.
- Privacy и consent.
- End-to-end tests.

### Out of scope

- Второй claims-сервис.
- Дублирование существующего генератора претензий.
- Автоматическая подача иска без подтверждения пользователя.
- Автоматическая юридическая гарантия результата.
- Полный CRM взыскания.
- Платёжная система, если она не утверждена отдельной итерацией.

### Критерии приёмки

- Пользователь не вводит повторно известные реквизиты должника.
- Claims-flow получает стабильный `report_id`.
- Машинные signals и score сохраняются как контекст, но не подменяют данные долга.
- Пользователь подтверждает передаваемые сведения.
- Existing claims-flow не дублируется.
- Претензия формируется по существующим контрактам.
- E2E-путь от страницы компании до созданного claim проходит.
- Privacy и audit требования соблюдены.

### Зависимости

- Итерации 10–12.
- Существующий claims-flow.
- Утверждённая UX-воронка.
- Решение о коммерческой модели и оплате.

---

## Итерация 14 — Единая точка входа CompanyReport

ID: 14
Slug: company-report-entry-flow

### Цель

Устранить блокирующий разрыв между вводом ИНН, созданием CompanyReport и его каноническим URL до production-деплоя.

### Scope

- Первый экран с общей формой ИНН в header и hero.
- Поддерживаемый plain-INN resolver `/company/{inn}`.
- Переход на `/company/{inn}-{slug}` после готовности данных.
- Безопасное аддитивное API-поле canonical path и исправление Claims backlink.
- Targeted/regression tests.

### Вне scope

- Публикации, массовый SEO rollout, миграции, инфраструктура и deployment.

### Критерии приёмки

- Валидный ИНН запускает или открывает отчёт без штатного 404.
- Plain URL не образует redirect loop и ведёт на canonical при наличии slug.
- Повторный submit не создаёт дубликат активной задачи.
- Canonical URL и existing Claims flow сохраняют совместимость.

---

## Итерация 15 — Визуальный первый экран CompanyReport

ID: 15
Slug: company-report-landing-visual

### Цель

Привести первый экран `/` к утверждённой композиции без изменения API,
маршрутизации, resolver, auth return target или lifecycle CompanyReport.

### Scope

- Текстовый бренд, header, навигация, hero и карточка проверки на `/`.
- Два визуальных варианта общей формы ИНН и responsive layout.
- Frontend tests, build и desktop/tablet/mobile visual verification.

### Вне scope

- Backend, миграции, Claims handoff, инфраструктура, deployment и новые
  продуктовые страницы.

### Критерии приёмки

- Экран соответствует утверждённому макету и не содержит видимой технической
  подписи `CompanyReport`.
- Существующий единый вход в `/company/{inn}` и canonical flow не меняются.
- На 1440, 768 и 390 px нет горизонтальной прокрутки.

---

## Итерация 16 — Публичный контракт H1 CompanyReport

ID: 16
Slug: company-report-h1-public-contract

### Цель

Зафиксировать versioned публичный контракт одной доказательной карточки
компании на canonical URL `/company/{inn}-{slug}` до расширения CompanyReport,
SSR и SPA новыми fact families.

### Scope

- Семантика immutable `checked_at` и отсутствие автоматического refresh.
- H1 block manifest и field-level public allowlist.
- Candidate finance unit `thousand_rub` с обязательным evidence gate; до него
  абсолютные суммы публично не выводятся.
- Один snapshot resolver для public SSR и SPA и точный versioned H1 API.
- Exact INN/OGRN arbitration attribution без двойного role count.
- Optional tax and bankruptcy semantics.
- Address, manager and owner visibility with form/privacy rules.
- Contacts, FSSP indirect facts, score and verdict prohibition.
- Source precedence, coverage states and backward compatibility.
- Спецификация и implementation plan будущей runtime-итерации.

### Вне scope

- Runtime/API/UI/DB/migration изменения.
- Provider live calls, production rollout и deployment.
- Кнопка обновления отчёта.
- Контакты и FSSP.

### Критерии приёмки

- Публичные поля имеют source, normalization и missing/conflict behavior.
- Finance, arbitration, tax и bankruptcy wording однозначны.
- Один case входит в один arbitration role bucket.
- Старый report не выглядит проверенным в текущий день.
- H1 не содержит score, verdict, raw payload или unverified contacts.
- Реализация может быть спланирована без новых продуктовых решений.

---

## Итерация 17 — Backend публичной проекции H1 CompanyReport

ID: 17
Slug: company-report-h1-backend

Статус: planning input; implementation требует отдельного DevFlow
planning/plan-review после merge итерации 16.

### Цель

Реализовать вычисляемую `company_public_h1_v1` projection и публичный read-only
API поверх одного детерминированно выбранного immutable snapshot, расширив
CompanyReport optional enrichments без изменения lifecycle трёх required
datasets.

### Scope

- `GET /company-reports/{inn}/public-h1` без auth, provider/AI/job/write на read
  path.
- Один resolver: active publication pin имеет приоритет; без него используется
  latest eligible `complete|partial` snapshot с `indexable=false`; failed или
  unusable newer run его не подменяет.
- Computed projection без новой таблицы и без миграции БД.
- Report snapshot v2 с отдельным optional dataset envelope для `tax_info` и
  `bankruptcy`; чтение snapshot v1 сохраняется.
- Pure normalizers, public coverage/source/limitation models и exact-ID
  arbitration attribution.
- Fixed `Europe/Moscow` checked-date policy, готовые display strings и exact
  typed values в DTO.
- Safe fixtures, unit/integration tests и SSR/API parity.

### Вне scope

- React presentation, refresh button, deployment и production provider probes.
- Активация финансовых сумм или optional calls до прохождения соответствующих
  evidence/operational gates.

### Критерии приёмки

- SSR и API возвращают один `report_id` и одну H1 projection для active
  publication.
- Новый finalized run не подменяет опубликованный snapshot до controlled
  republish.
- Optional failures не меняют `complete/partial/failed` required lifecycle.
- Старые snapshots и текущий `GET /company-reports/{inn}` остаются читаемыми.
- Недоказанные provider fields и единицы не попадают в публичный DTO.

---

## Итерация 18 — Публичная страница H1 CompanyReport

ID: 18
Slug: company-report-h1-frontend

Статус: planning input; implementation требует отдельного DevFlow
planning/plan-review после merge итерации 17.

### Цель

Перевести публичную React-страницу компании на `company_public_h1_v1`, не
дублируя в браузере source semantics, timezone conversion и Decimal rounding.

### Scope

- Публичный, не требующий авторизации H1 renderer для canonical и plain-INN
  flow.
- Утверждённый block manifest, coverage, sources и limitations.
- Отображение backend-provided checked date и денежных display strings.
- Loading/pending/not-found/partial/failed states, responsive и accessibility.
- Отсутствие contacts, scoring, verdict и AI controls в H1 presentation.
- Frontend tests, lint, build, published SSR/API/SPA parity fixtures и
  latest-unpublished API/SPA parity fixtures.

### Вне scope

- Изменение backend source semantics, provider calls, refresh, SEO rollout и
  deployment.

### Критерии приёмки

- Для active publication SPA показывает тот же pinned `report_id`, block order,
  facts, dates и limitations, что H1 API/SSR fixture; latest_unpublished имеет
  только API/SPA parity и остаётся noindex/SSR-404.
- Browser locale и JavaScript `Number` не меняют дату или денежное значение.
- Existing entry flow, canonical redirect и Claims handoff не ломаются.
- На desktop/tablet/mobile нет горизонтального scroll и недоступных controls.

---

## Итерация 19 — Контракт, проектирование и evidence Company Card v2

ID: 19
Slug: company-card-v2-contract-evidence

Статус: завершена.

### Зависимости

- Завершённые и reconciled итерации 16–18.
- Утверждённые владельцем продуктовые решения Company Card v2.

### Цель

Зафиксировать implementation-ready продуктовый, доказательный и технический
контракт новой публичной карточки компании до изменения provider, snapshot,
API, SSR, SPA или AI-контура.

### Scope

- Три согласованных wireframe для desktop, tablet и mobile на основе макета
  карточки СКС, без преждевременной фиксации декоративного дизайна.
- Точный content-to-source manifest: hero, описание деятельности, реквизиты,
  пять финансовых и пять арбитражных представлений, sources, limitations и
  actions.
- Status/check date остаётся датой формирования immutable отчёта в
  `Europe/Moscow`, а не датой открытия страницы; существующие approved H1
  wordings и distinction missing/negative fact сохраняются.
- Правый sticky CTA на широком экране и компактная fixed bottom CTA-полоса на
  tablet/mobile с текстом `Создать претензию`.
- Desktop CTA содержит fixed UI copy `Вам задолжали?` и `Запустите процесс
  взыскания прямо сейчас: создайте досудебную претензию онлайн!`; compact
  tablet/mobile bar сохраняет heading `Вам задолжали?` и кнопку без
  обязательного supporting paragraph. Этот текст не генерируется AI.
- Сохранение нижних действий `Проверить другую компанию` и
  `Подготовить претензию`; accent background всех CTA-кнопок `#EE5A2A`, с
  отдельно проверяемыми contrast/focus/hover/disabled состояниями.
- Один Claims target, построенный из `report_id` показанного snapshot, без
  нового login/prefill choice и без изменения существующего anonymous flow.
- Versioned contract будущей Public Company Card v2: exact values,
  chart-ready values, block ordering, coverage, sources, limitations,
  actions, compatibility и fail-closed parsing.
- Отдельный coexisting v2 endpoint/schema и точные routing/fallback gates:
  `company_public_h1_v1`, его strict frontend reader и старые клиенты не
  расширяются молча и продолжают получать прежние responses.
- Формулы, closed dictionaries, missing/zero/partial/conflict semantics,
  formatter policy и accessibility contract для десяти графиков.
- Signed-value policy: отрицательные значения сохраняют знак, используют общую
  нулевую ось и расходятся влево; запрещены `abs`, clamp, omission и
  verdict-coloring. Отдельно фиксируются zero, mixed-sign и
  zero/negative-denominator cases.
- Exact finance-period algorithm разрешает неоднозначность исходного chart
  document: источник окна, required-code set, data-derived max year, общий или
  per-chart common-year selection и допустимые gaps фиксируются до backend
  реализации, без browser/current-year inference.
- Финансовый evidence gate: immutable
  `datanewton_finance_thousand_rub_v1` отклонён evidence v2; candidate
  `datanewton_finance_thousand_rub_v2` разделяет non-zero scale, presence,
  zero, lexical transport и publication gates и активируется только после
  заранее утверждённой свежей матрицы. Raw provider payload в git не
  добавляется.
- Проверенный field-level provider manifest с exact path/type/scope/date и
  identity semantics для legal status/effective date, legal form dictionary,
  charter-capital unit/format, tax-mode flags, полного OKVED code/label,
  руководителя, владельцев/долей, работников, налогового органа,
  `party_result`, parties/entity type, currency, pagination и KAD URL.
- Tracked sanitized shape/evidence/decision artifacts с provenance и без raw,
  секретов или production identifiers; внешние ignored-файлы не являются
  единственным доказательством контракта.
- Privacy contract: контакты и персональные идентификаторы не публикуются;
  адрес, руководитель и владельцы допускаются только в утверждённом safe
  составе; юридические лица и государственные органы в арбитраже допустимы,
  физические лица маскируются; Webvisor/telemetry не получают чувствительные
  данные.
- Маскирование физических лиц применяется одинаково в DTO, SSR/HTML,
  embedded state, tooltips и telemetry, сохраняет различимость записей без
  раскрытия identity и не объединяет разных лиц в одного «контрагента».
- Маскирование natural persons относится к opposing parties арбитража.
  Утверждённые manager/owner names и owner share могут показываться в safe
  management composition, но без personal INN, contacts и иных персональных
  идентификаторов.
- Entity type не выводится из display name: unknown/conflicting type
  fail-closed маскируется; ИНН юридического лица служит internal grouping key,
  но не показывается в chart UI, embedded presentation или telemetry.
- Large-N policy: агрегаты по полному доказанно нормализованному набору,
  detail cap `top-20` после validation/privacy eligibility, deterministic sort
  и tie-breakers, точная подпись `показано N из M`, где `M` — eligible
  population данного detail view; partial slice показывает returned/total
  scope и не экстраполируется.
- Per-view large-N rules: case-amount details имеют отдельный cap/ranking для
  каждой source currency, opposing parties сортируются по case count и затем
  safe stable key/name; каждый `N/M` явно называет свой denominator.
- Arbitration currency/calendar rules: разные currencies не смешиваются и не
  FX-convert, missing currency не получает `₽`, explicit amount `0` остаётся
  видимым, равные суммы не дедуплицируют дела; календарный zero допустим только
  при доказанно полной pagination, partial slice не создаёт empty years и
  вывод `дел нет`.
- Arbitration persistence ADR выбирает воспроизводимую v3 форму: bounded full
  normalized case set либо write-time aggregates/chart facts плюс
  deterministic top-20 evidence; hard provider/storage cap, cap exhaustion как
  `partial`, auditability и privacy определяются до итерации 20.
- AI narrative contract: generation только вне read path, автоматическая
  schema/evidence/policy validation, deterministic renderer, immutable
  artifact key/pin по `report_id`, `snapshot_hash` и всем
  policy/schema/catalog/prompt/model versions, deterministic fallback, без
  ручной модерации и без второго AI как trust boundary.
- SSR/client-takeover ADR: один sanitized versioned embedded DTO, его
  consumption без второго factual GET, JS-disabled factual document и zero
  provider/AI/job/write work во время takeover.
- ADR явно вводит только для v2 узкое исключение из H1-запрета hidden
  serialized response: разрешена лишь strict public projection с script-safe
  serialization, CSP/XSS boundary и negative fixtures; raw/provider/private
  JSON остаётся запрещённым.
- Version/feature gates, rollback, exact old-report/publication-pin behavior и
  acceptance matrix будущих итераций 20–25.
- Новый writer contract использует `CompanyReport.report_version="3"`;
  versions `"1"|"2"` остаются read-only compatible, не переписываются и
  получают explicit legacy limitations для отсутствующих v3 facts.
- Bounded evidence matrix из 3–5 компаний допускается только как отдельно
  перечисленный scope DevFlow-итерации 19; roadmap-подготовка не выполняет
  network/live calls. Запрещены production DB, paid AI и публикация
  raw/provider secrets.

### Вне scope

- Product API, Gateway API, React, nginx, deploy, migration и runtime-код.
- Создание нового отчёта, refresh/backfill старых snapshots и изменение
  production publication.
- Платные AI-вызовы и production rollout.
- Контакты, scoring, verdict, recovery probability и рекомендации о
  надёжности компании.

### Критерии приёмки

- Каждый видимый факт и derived value имеет источник, формулу, единицу,
  missing/partial behavior и public/privacy решение.
- Finance window/common-year/gap и arbitration persistence/cap algorithms
  сформулированы так, что итерация 20 не принимает скрытых data-size или period
  решений.
- Все три wireframe однозначно показывают breakpoint ownership, desktop CTA
  rail, tablet/mobile bottom bar, safe-area/reserved padding, content order,
  все десять views, long/empty/partial/negative/large-N states и отсутствие
  перекрытия контента.
- `#EE5A2A` остаётся exact accent background, а выбранные text/font и
  focus/hover/disabled states проходят применимые contrast requirements.
- Финансовая денежная единица либо проходит versioned evidence gate, либо
  денежные графики остаются явно заблокированными; пользовательское решение
  о `thousand_rub` не подменяет техническое evidence.
- AI не пишет публичные числа, verdict или неподтверждённые факты: невалидный,
  отсутствующий или устаревший artifact всегда заменяется deterministic
  fallback без участия человека.
- Старые immutable reports не выглядят обогащёнными и не вызывают DataNewton
  на read path: v1/v2 snapshots не rewrite/backfill/refresh на GET/SSR, нет
  provider/job/write/AI side effects, unavailable Card-v2 facts имеют explicit
  legacy limitation либо остаются на H1, active publication pin не меняется
  молча.
- SSR и SPA используют один factual projection; прямой canonical hard-load и
  client navigation не создают две разные карточки; takeover потребляет один
  sanitized embedded DTO без второго factual GET, content/order mismatch или
  скрытого paid/provider work.
- Script-safe embedded projection проходит XSS tests для closing-tag/control/
  Unicode/long-string cases и не содержит raw/private/unknown keys.
- V2 endpoint/schema сосуществует с неизменённым H1 v1, а old clients и
  current production route проходят compatibility tests.
- Planning inputs 20–25 не требуют новых незафиксированных продуктовых
  решений, а визуальная композиция подтверждена владельцем проекта.

---

## Итерация 20 — Backend и данные Company Card v2

ID: 20
Slug: company-card-v2-backend-foundation

Статус: завершена. Production activation, live provider operation и public
A1–A5 по-прежнему не разрешены.

### Зависимости

- Merged контракт/планирование итерации 19.
- `iteration-20-owner-scope-decision-v1.md` и
  `iteration-20-gate-readiness-v3.md`.
- Finance v3 non-zero scale evidence; lexical transport закрывается тестами
  этой итерации, zero остаётся запрещённым numeric input.

### Цель

Реализовать default-off backend foundation Company Card v2, который сохраняет
immutable history и совместимость H1/v1/v2, публикует только доказанные факты,
а каждый открытый gate выражает как явную недоступность без догадок.

### Scope

- Existing approved H1/core identity/address projection. Strict fail-closed
  parsers/fixtures для наблюдённых counterparty paths; status/form/OKVED,
  managers/owners, workers, tax modes/authority и charter capital остаются
  скрытыми до своих semantic gates. Контакты не запрашиваются/не публикуются.
- `CompanyReport.report_version="3"` для новых writes, с явным raw
  discriminator и read-only compatibility path для snapshots `"1"|"2"`;
  текущий snapshot v2 не перегружается новой несовместимой семантикой и не
  переписывается.
- Fixture-driven bounded arbitration collector foundation: pre-call registry,
  caps/non-progress/drift, deterministic dedup/conflict, provenance, exact-INN
  role attribution и opaque masking. Пока envelope gate закрыт, сеть
  запрещена, а public A1–A5 равны unavailable/gate-closed.
- Pure versioned Chart Facts foundation: exact Decimal, deterministic display/
  geometry and missing/zero/partial semantics. Finance разрешает только
  non-zero path после lexical transport tests; arbitration facts скрыты.
- Versioned finance policy v2 как accepted-with-deviation implementation
  input. Rejected v1 не переопределяется, provider zero не публикуется.
- Versioned Public Company Card v2 API/projection с closed contracts,
  coverage, sources, limitations, actions и zero-side-effect read path.
- Feature gate выключен по умолчанию; H1 v1 и существующий Claims handoff не
  меняются.
- Unit, provider-fixture, serialization, old-snapshot, disposable PostgreSQL,
  API/SSR parity и negative contract tests.

### Вне scope

- AI generation, React presentation, графические компоненты, route cutover,
  deployment, refresh button и production backfill.
- Live DataNewton/FNS/Gateway/AI calls и runtime enablement расширенных
  counterparty/arbitration profiles.
- Visible gated counterparty fields, provider-zero finance и любые public
  arbitration A1–A5 facts.
- Scoring/signals changes и вывод новых данных на старом H1 v1.

### Критерии приёмки

- Все chart inputs берутся только из сохранённого immutable snapshot и
  воспроизводимо формируют тот же versioned projection.
- Missing не превращается в zero, partial arbitration не экстраполируется, а
  Decimal не превращается в float source of truth.
- До verified lexical gate finance numeric facts недоступны; после него
  разрешён только non-zero path, а provider zero остаётся omitted с limitation.
- Arbitration pre-call registry гарантированно блокирует network при
  unverified binding; A1–A5 остаются gate-closed.
- Каждый скрытый counterparty fact имеет explicit coverage/limitation и не
  появляется в DTO из одного лишь observed key name.
- Старые snapshots остаются читаемыми и не переписываются на read path.
- Public Card v2 не публикует contacts, raw payload, personal identifiers,
  scoring или verdict.
- Feature gate не изменяет production-default H1 до отдельного rollout.

### Post-merge continuation: presentation create/status/read lifecycle

Static audit exact `origin/main` на 2026-08-27 подтвердил, что merged
foundation не выдаёт frozen seven-field `PresentationLifecycle`, молча
принимает query/header selectors, документирует POST как `200 {}` и повторно
применяет current rollout flag к status polling. Дополнительно public-H2
no-subject literal расходится с frozen matrix.

Это bounded continuation того же ID 20:

- key `presentation-create-lifecycle-contract-v1`;
- branch `codex/iteration-20-presentation-create-lifecycle-continuation`;
- отдельные specification, implementation plan и baseline evidence;
- без migration, settings/default, provider/writer, frontend, deploy или
  production activation;
- code started only after independent plan review and explicit owner approval.

Continuation squash-merged через PR `#150` в
`604bf6deeea453187841bdf454f8dfc0c390d72d`
2026-08-27T21:28:19+10:00; merged tree идентично source commit
`ebc421b6c919d81ba7732494e5c74e152becd1e7`. Product API unit завершился
`1524 passed`, iteration-20 disposable PostgreSQL Targeted — `117 passed`,
Full — `290 passed`; JUnit clean без failures, errors и skips. Финальный
независимый code-review verdict: `APPROVED`. Production activation остаётся
`NOT AUTHORIZED`. Эта acceptance не закрывает отдельный dedicated
PostgreSQL gate итерации 24.

---

## Итерация 21 — Публичное AI-описание Company Card v2

ID: 21
Slug: company-card-v2-ai-narrative

Статус: завершена. AI/narrative pipeline и H2 остаются выключенными по
умолчанию; production activation не выполнялась.

### Зависимости

- Merged Public Card v2 data/projection foundation итерации 20.
- Доступный, но выключенный по умолчанию task-specific Gateway capability.

### Цель

Создавать доказательное нейтральное описание деятельности компании и не более
двух комментариев к графикам как сохранённый, бюджетируемый и автоматически
валидируемый artifact, не вызывая paid AI на публичном read path.

### Scope

- Separate AI job/artifact persistence, immutable cache key по report/snapshot
  hash и версиям evidence/insights/catalog/prompt/schema/model profile.
- Отдельный worker, bounded queue, lease/fencing, durable budget reservation,
  daily/monthly limits, concurrency cap, kill switch и безопасная retry policy.
- Task-specific structured Gateway profile и минимальный обезличенный evidence
  envelope без ИНН/ОГРН, адресов, персональных данных, case identities, raw,
  signals или scoring.
- Strict JSON schema, allowlisted evidence/statement IDs, автоматическая
  schema/evidence/policy validation и deterministic Russian renderer.
- Описание длиной 400–700 знаков и максимум два комментария к выбранным
  графикам; AI не вычисляет числа, роли, суммы, проценты или verdict.
- Deterministic fallback при отсутствующем, невалидном, просроченном или
  недоступном artifact; SSR/API/SPA только читают сохранённый результат.
- Publication pin связывает artifact с exact `report_id` и `snapshot_hash`;
  новый artifact не меняет опубликованный текст молча.
- Unit/integration/Gateway contract tests без paid calls; один отдельный
  controlled smoke возможен только с явным операционным разрешением.

### Вне scope

- Ручная модерация, admin UI и второй AI-валидатор.
- Свободный рекламный текст, scoring explanation, recommendations и AI call из
  GET/SSR/crawler request.
- Включение генерации для всех anonymous-created reports и production rollout.

### Критерии приёмки

- Повторный public GET не создаёт job и не вызывает Gateway.
- Любая публичная фраза трассируется к сохранённому evidence/statement ID, а
  точные значения подставляет локальный renderer.
- Невалидный AI output fail-closed заменяется fallback и не блокирует страницу.
- Budget/kill switch/ambiguous timeout не допускают неконтролируемых повторных
  платных вызовов.
- AI artifact не изменяет CompanyReport snapshot, signals или scoring.

---

## Итерация 22 — Каркас страницы, SSR и CTA Company Card v2

ID: 22
Slug: company-card-v2-page-shell

Статус: завершена. H2 assignment и production activation не выполнялись;
старый H1 остаётся production-default и rollback path.

### Зависимости

- Merged Public Card v2 API/projection итерации 20.
- Merged narrative artifact/fallback contract итерации 21.

### Цель

Реализовать общий responsive shell новой карточки для прямого canonical SSR и
React navigation без расхождения factual content, сохранив старый H1 как
production-default и rollback path.

### Scope

- Hero, checked date/status, narrative/fallback, in-page navigation,
  requisites, sources, limitations и actions поверх Public Card v2.
- Desktop main/aside layout со sticky CTA и tablet/mobile fixed bottom bar;
  CTA `Создать претензию` использует report-specific Claims target.
- Нижние действия сохраняют labels `Проверить другую компанию` и
  `Подготовить претензию`; CTA background `#EE5A2A` и доступные interaction
  states.
- FastAPI SEO/text shell, shared assets, безопасный embedded DTO и React
  client takeover без второго factual GET.
- Canonical/wrong-slug/noindex/error/lifecycle behavior, head ownership,
  focus/live regions, safe-area, keyboard/touch и reduced-motion support.
- Contract/lifecycle/SSR/nginx/frontend tests и real-browser visual matrix для
  утверждённых wireframes.
- V2 presentation остаётся за выключенным feature gate.

### Вне scope

- Финансовые и арбитражные chart renderers, Claims auth/prefill changes,
  provider/AI semantics, production activation и удаление H1.

### Критерии приёмки

- Canonical hard-load и SPA navigation показывают один report, content order,
  facts, narrative, limitations и actions.
- CTA не перекрывает контент, существует в утверждённых placements и всегда
  использует `report_id` отображаемого snapshot.
- JavaScript-disabled SSR остаётся индексируемым factual документом, а
  interactive client не выполняет повторный paid/provider/factual read.
- На 320/390/768/1024/1200/1440 px нет page-wide horizontal scroll и
  недоступных controls.

---

## Итерация 23 — Финансовые графики Company Card v2

ID: 23
Slug: company-card-v2-finance-charts

Статус: завершена. Production activation не выполнялась; feature gate остаётся
выключенным для production-default route.

### Зависимости

- Merged responsive/SSR/client shell итерации 22.
- Approved versioned policy v2 и non-zero-only Chart Facts contract итерации
  20; отклонённая v1 не используется, provider zero остаётся omitted до
  отдельного verified zero gate.

### Цель

Показать пять утверждённых финансовых представлений интерактивно, точно и
доступно, не вычисляя source semantics и monetary truth в браузере.

### Scope

- Средства/инвестиции/дебиторка против краткосрочных обязательств.
- Собственный капитал против долгов.
- Динамика выручки и активов за последние семь полных общих периодов.
- Валовая, операционная и чистая прибыль на 100 рублей выручки.
- Таблица утверждённых финансовых строк и периодов.
- Backend-provided exact display strings и safe scaled geometry; gaps/missing,
  explicit zero, negative/diverging bars и denominator-zero policy.
- Mouse hover, keyboard focus, touch disclosure, bounded tooltip,
  textual/table fallback, reduced motion и lazy/error fallback.
- Targeted contract/component/accessibility/visual/performance tests.
- Feature gate остаётся выключенным для production-default route.

### Вне scope

- Новые финансовые business thresholds, forecast/interpolation, risk colors,
  arbitration charts, provider changes и production activation.

### Критерии приёмки

- Ни один missing показатель не отображается как zero и ни один gap не
  интерполируется.
- Tooltip/table показывают exact backend strings; JavaScript Number не является
  источником денежной истины.
- Денежная подпись появляется только при активном evidence-backed unit policy.
- Все графики доступны мышью, клавиатурой и touch, а fallback сохраняет факты
  при отключённом или не загрузившемся chart bundle.

---

## Итерация 24 — Арбитражные графики Company Card v2

ID: 24
Slug: company-card-v2-arbitration-charts

Статус: завершена. Реализация merged в
`e7478a2fba9aaca17829c3d99e89e8d83d4b3188`
2026-08-27T09:23:32+10:00. Код утверждённого scope получил финальный
независимый code-review verdict `APPROVED`; доступные unit, frontend, build,
gateway, release и migration-contract проверки проходят. Dedicated
post-merge disposable PostgreSQL acceptance закрыт 2026-08-28 на repository
base `557244b69c5bf54bba6ae07bfd5a39638ff14f18`: migration module завершился
`2 passed`, а затронутый nine-file integration suite — `79 passed`, без
failures, errors или skips. Product API unit regression завершился
`1524 passed`; labeled disposable container удалён. Воспроизводимый отчёт:
[`iteration-24-post-merge-postgresql-acceptance-v1.md`](evidence/iteration-19-company-card-v2/iteration-24-post-merge-postgresql-acceptance-v1.md).
Scope намеренно сужен до single-page completeness, observed years, RUB-only A4
и all-masked A5. Production provider operation, publication и feature
activation не разрешены.

### Зависимости

- Merged chart shell/interaction patterns итераций 22–23.
- `arbitration-contract-evidence-v3.md` с официальным OpenAPI binding.
- `iteration-24-owner-scope-decision-v1.md` и
  `iteration-24-gate-readiness-v2.md`.

### Цель

Показать пять утверждённых арбитражных представлений по exact provider
population либо честно обозначенной returned slice без двойной атрибуции,
экстраполяции и раскрытия идентификаторов или имён сторон.

### Scope

- Versioned `case_id`-only basis-v2 и новый immutable snapshot/publication
  lineage без переосмысления старых `ArbitrationBasisV1`/policy v1/v2.
- Additive report/job decision migration для immutable arbitration-enabled и
  mask-key-ID binding; race-free pre-DDL guard запрещает upgrade при любом
  старом active H2 lifecycle, terminal legacy rows остаются `false/null`, а
  production upgrade не выполняется в этой итерации.
- Один exact request `inn + company_role=ALL + offset=0 + limit=1000`; при
  `total_cases>1000` результат всегда partial и второй request запрещён.
- A1 только по observed start years, с отдельным unknown-year bucket и без
  synthetic calendar zero.
- A2 exact-INN roles: `plaintiff`, `respondent`, `other`, `unattributed`.
- A3 только из narrow mapping `WON/LOST/RETURNED/unknown`, без win rate.
- A4 только для exact `RUBLES -> RUB`; claim price не называется долгом,
  `OTHER`/unknown исключаются с limitation, FX запрещён.
- A5 только actual opposing collections; все стороны `masked_unknown`,
  report-scoped HMAC grouping и fixed labels `Сторона скрыта N` без имён.
- Полные aggregates, top-20 details, exact `показано N из M`, honest
  available-empty/partial/failed states и отсутствие экстраполяции.
- Optional `first_number`; `result_type`, instances/courts и KAD links остаются
  null в первой реализации.
- SSR/React factual parity, lazy mouse/keyboard/touch SVG enhancement, textual
  fallback, long/large-N/privacy fixtures и component/contract/a11y tests.
- Отдельный arbitration operation gate и все production defaults остаются off.

### Вне scope

- Multi-request/full-pagination completeness, доказательство historical
  calendar horizon и synthetic zero years.
- Named opponents, entity-type inference, natural/legal/state party names,
  OGRN/name/fuzzy target matching и raw/HMAC/provider identifiers.
- Non-RUB currency groups, FX, collection probability, прогноз исхода,
  трактовка claim amount как долга/award/collection и win rate.
- Initial result detail, instance/court labels, KAD links, новые provider
  datasets, live provider/AI calls, deploy и production activation.

### Критерии приёмки

- Exact complete возможен только для валидного single-page envelope при
  `total_cases<=1000`; любой larger/drift/malformed/conflict/cap result честно
  остаётся partial/failed и не экстраполируется.
- Одно normalized дело входит ровно в один role bucket, multiple roles дают
  `other`, а unknown outcome не подменяется loss/return.
- A1 не создаёт ненаблюдавшиеся years; A4 показывает exact Decimal только в RUB и
  сохраняет explicit zero/negative sign.
- Large-N UI ограничен top-20, доступен и показывает exact nested N/M и
  complete-collection либо returned-slice scope.
- Публичные DTO, SSR, embedded state, client, aria/live text, logs, telemetry и
  Claims не раскрывают party/case identity, name, HMAC или arbitrary URL.
- V1/V2 snapshots и finance-only publication policy v2 остаются совместимыми;
  новый provider path и production publication выключены по умолчанию.
- Enqueue/claim/retry сохраняют exact arbitration/key decision; rotation
  влияет только на новые jobs, а missing old key даёт safe failure до
  arbitration fetch callback.

---

## Итерация 25 — QA и rollout Company Card v2

ID: 25
Slug: company-card-v2-qa-rollout

Статус: refreshed base-bound specification, proposed owner-decision register,
implementation plan и baseline evidence подготовлены в ветке
`codex/iteration-25-company-card-v2-qa-rollout-refresh` на exact base
`31b299ac88b5fac7d5c04082324fb122d63db7e7`. Bounded delta PR `#150–#152` и
Stage 0 подтверждают merged behavior iteration 20/24; Product unit
`1524`, Gateway `31`, Web `496`, release `34`, disposable PostgreSQL
iteration-24 `2 + 79` и iteration-20 `117 + 290` проходят. Реализация не
начата. Первый refreshed review вернул `CHANGES_REQUIRED`; единственный
planning correction pass закрывает subject-bound journal, full-validation
sitemap, staged/active fences, downgrade race и evidence reproducibility.
Correction review обнаружил stale iteration-24 `head == 0018` assumption;
forward-head amendment получил architecture/evidence `VERDICT: APPROVED` без
оставшихся findings. Owner implementation approval получен 2026-08-28;
реализация начата в reviewed scope.
Исторический iteration-24 runner не меняется и не
переиспользуется как gate; новый iteration-25 acceptance runner/checker
сохраняет все 0018 assertions, меняет в старом migration test только два stale
`head` alias на explicit `0018`, затем доказывает `0018 -> 0019/head` и
повторяет affected phase с JUnit nonzero/zero-skip proof. Production activation
не авторизована.

### Зависимости

- Все merged contracts/runtime/UI итераций 19–24 и закрытые evidence gates.
- Post-merge disposable PostgreSQL acceptance итерации 24 закрыт; результат
  зафиксирован в отдельном evidence artifact.
- Текущий iteration-24 runner подтверждал эти конкретные `2 + 79 passed`, но
  проверяет только exit code и остаётся исторически неизменным. Новый
  iteration-25 runner/checker обязан сохранить exact-0018 migration assertions,
  выполнить forward `0018 -> 0019/head` handoff и дать machine-readable
  nonzero/zero-skip JUnit proof до использования prerequisite phases как gate.
- Iteration-20 presentation lifecycle continuation merged/reconciled и
  повторно проходит exact contract/PostgreSQL baseline.
- Исправленные refreshed specification/plan прошли independent review и
  требуют отдельного owner implementation approval до изменения
  production/runtime behavior.
- Feature flags остаются выключенными до отдельного rollout decision.

### Цель

Доказать готовность всей Company Card v2 end-to-end, подготовить безопасное
ступенчатое включение и сохранить проверенный rollback на H1.

### Scope

- Полные затронутые Product API/Gateway/frontend/integration suites с
  disposable PostgreSQL и без paid/provider calls в CI.
- Browser E2E и visual matrix: 320/390/768/1024/1199/1200/1440 px, keyboard,
  touch, 200% zoom, reduced motion, safe-area, long/missing/partial/large-N.
- SSR/API/SPA semantic parity, canonical/wrong-slug/noindex/robots и
  crawler-safe behavior.
- Bundle/post-font zero-shift/performance diagnostics, lazy-chart failure, AI
  fallback/budget/kill switch, privacy/telemetry и Claims target verification.
- Acceptance fixtures: СКС и минимум три обезличенных edge profiles без
  production raw в git.
- Feature flag/runbook/observability/rollback rehearsal и staged activation
  plan: test publications → allowlisted companies → controlled production
  percentage → general availability.
- CI gates для обязательных backend, frontend и browser checks.

### Вне scope

- Автоматический refresh/backfill старых reports, удаление H1, массовая
  production republish и фактический production deploy/flag change без
  отдельного разрешения владельца.

### Критерии приёмки

- Все обязательные suites и browser/visual/privacy/performance gates проходят
  без необъяснённых skips или новых baseline failures.
- V2 можно включить и выключить без изменения immutable reports и без потери
  canonical/Claims continuity.
- Paid AI и DataNewton не вызываются crawler/read/test traffic.
- Runbook содержит точные preflight, canary, smoke, monitoring и rollback
  действия; production activation остаётся отдельным одобренным действием.
- Независимое end-to-end review выдаёт `VERDICT: READY` до commit/push и
  последующего ручного merge.

---

## 4. Условные и отложенные расширения

Эти работы не получают новый ID без отдельного решения. Завершённый путь 8–15
не пересматривается; H1 16–18 сохраняется как совместимый production-default
и rollback path, а Company Card v2 реализуется только в явно добавленных
19–25.

### `finance.reporting_absent`

Может получить только отдельную будущую итерацию после появления проверенного
evidence fixture; завершённая итерация 7 задним числом не расширяется. Evidence
должен однозначно отличать отсутствие отчётности от:

- access denied;
- tariff limitation;
- failed/malformed response;
- пустого или неполного payload;
- отчётности с provider-specific особенностями.

### Дополнительные datasets DataNewton

После расширения тарифа каждый новый dataset проходит полный цикл:

```text
provider/probe
→ fixture
→ normalizer
→ CompanyReport extension/versioning
→ signals
→ scoring impact
→ API/page
```

`taxInfo` и `bankruptcy` для публичного H1 уже маршрутизированы в итерацию 17 и
могут включаться только после её schema/operational gates, без автоматического
влияния на signals/scoring. Остальные приоритетные кандидаты:

- `fssp`;
- court cases общей юрисдикции;
- государственные контракты;
- дополнительные risk datasets.

### Persistence signals/scoring/explanation

Публичный narrative artifact отдельно маршрутизирован в итерацию 21 и не
изменяет signals/scoring/recovery explanation. Любое новое persistence или
перевычисление этих доменов требует отдельного решения. Если такие результаты
сохраняются, обязательны:

- версия ruleset;
- версия prompt/model;
- hash входного snapshot;
- воспроизводимость;
- миграция;
- политика пересчёта.

## 5. Definition of Done для любой новой итерации

Итерация считается завершённой, когда:

1. Утверждены спецификация и implementation plan.
2. Scope и out of scope не противоречат roadmap.
3. Реализация находится в отдельной feature-ветке.
4. Изменены только разрешённые файлы либо расширение scope явно согласовано.
5. Targeted tests проходят.
6. Полный затронутый regression suite проходит.
7. `compileall`/build/lint проходят в зависимости от стека.
8. `git diff --check` проходит.
9. Независимый code review не содержит блокеров.
10. Секреты, raw payload и чувствительные данные не попали в diff.
11. Создан commit и push.
12. Создан pull request с итоговым отчётом.
13. Merge выполнен человеком.
