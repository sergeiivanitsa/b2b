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
| 8 | `scoring` | Следующая |
| 9 | `ai-explanation` | Запланирована |
| 10 | `company-reports-api` | Запланирована |
| 11 | `company-page` | Запланирована |
| 12 | `seo-publishing` | Запланирована |
| 13 | `claims-handoff` | Запланирована |

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

## 4. Условные и отложенные расширения

Эти работы не получают новый ID без отдельного решения и не блокируют основной путь 8–13.

### `finance.reporting_absent`

Может быть добавлен как дополнительный Stage итерации 7 только после появления проверенного evidence fixture, однозначно отличающего отсутствие отчётности от:

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

Приоритетные кандидаты:

- `taxInfo`;
- `fssp`;
- `bankruptcy`;
- court cases общей юрисдикции;
- государственные контракты;
- дополнительные risk datasets.

### Persistence signals/scoring/explanation

Решение принимается отдельно. До утверждения допускается вычисление поверх сохранённого immutable `CompanyReport snapshot`. Если результаты сохраняются, обязательны:

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
