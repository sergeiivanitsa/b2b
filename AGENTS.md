# Инструкция для агентов

## Назначение и структура

Репозиторий содержит B2B-продукт: RU `product_api` (FastAPI), изолированный
US/EU `gateway_api` (FastAPI) и React SPA `web_ui`. Продукт включает Claims и
контур `CompanyReport` для получения, нормализации, хранения и последующей
оценки данных о компаниях.

- `services/product_api/` — продуктовые API, Claims, CompanyReport,
  SQLAlchemy/Alembic и unit/integration tests.
- `services/gateway_api/` — отдельная HMAC-защищённая граница для OpenAI; она
  не имеет доступа к БД Product API.
- `services/web_ui/` — React/TypeScript/Vite UI.
- `shared/` — общие межсервисные схемы и константы.
- `docs/development/` — roadmap, состояние DevFlow, спецификации и планы.
- `deploy/` и `.github/workflows/` — deployment и CI.

Поток CompanyReport:
`DataNewton provider → pure normalizers → aggregate/orchestrator через provider
protocol → persistence`. Provider не зависит от routers, Claims и persistence.
Claims и CompanyReport остаются разными доменами и связываются только через
явно утверждённые контракты.

## Архитектурные и бизнес-инварианты

- Normalizers не выполняют HTTP- или БД-операции, не хранят `raw_payload` и
  используют только переданный provider result.
- `missing`, `not_found`, `partial` и `failed` имеют разную семантику.
  Неполные и ошибочные данные дают безопасные warnings/errors, а не
  выдуманные факты.
- Отсутствующие показатели запрещено превращать в нули, отрицательные факты
  или положительные выводы.
- Не выдумывайте поля DataNewton, значения, бизнес-пороги и единицы измерения.
  Неизвестная или отсутствующая единица остаётся неизвестной; точные числа
  сохраняются как `Decimal`, а не `float`.
- Правила, нормализация, сериализация и порядок элементов детерминированы:
  одинаковые входы дают одинаковый результат. Не используйте скрыто текущее
  время, сеть, БД или случайность в pure-domain логике.
- Signals фиксируют воспроизводимые факты и основания. Scoring является
  отдельным версионированным слоем; запрещено смешивать signals со scoring,
  verdict, probability или AI-объяснением.
- `CompanyReport` сохраняет безопасные статусы `complete`, `partial` и
  `failed`; partial failure одного dataset не уничтожает доступные datasets.
- Persistence сохраняет immutable snapshots, историю, приватность и
  идемпотентность lifecycle. Provider journal и публичные модели не содержат
  API keys, raw headers или raw payload.

## Порядок работы

1. Прочитайте `README.md`, `docs/development/ROADMAP.md`,
   `docs/development/DEVFLOW_STATE.yaml`, релевантные спецификации/планы,
   документацию и код. Применяйте вложенные `AGENTS.md`.
2. Подготовьте план до изменений. Порядок его утверждения зависит от режима:
   - в обычной интерактивной работе план утверждает пользователь;
   - при явном запуске `$devflow` план считается утверждённым после
     `VERDICT: APPROVED` независимого plan reviewer; при
     `VERDICT: CHANGES_REQUIRED` разрешён ровно один предусмотренный DevFlow
     проход исправления. Отдельное подтверждение пользователя после plan review
     не требуется.
3. Реализуйте только утверждённый scope небольшими проверяемыми этапами,
   создавая или обновляя тесты вместе с поведением.
4. Выполните применимые проверки и независимое review.
5. Подготовьте итоговый отчёт. В обычной работе commit и push требуют отдельной
   явной команды пользователя. Явный запуск `$devflow` заранее разрешает
   итоговые commit и push только текущей feature-ветки и только после успешных
   проверок и review. Merge всегда выполняет человек.

Не меняйте несвязанный код и не исправляйте несвязанные baseline-проблемы.
Не добавляйте зависимости без объяснения необходимости, влияния и
альтернатив. Не выполняйте `reset`, удаление данных и другие разрушительные
операции без явного разрешения.

## Реальные команды проверок

Запускайте из корня репозитория:

```bash
python -m pytest services/product_api/tests_unit -q
python -m pytest services/gateway_api/tests -q
npm run lint --prefix services/web_ui
npm run test --prefix services/web_ui
npm run build --prefix services/web_ui
```

`npm run build` выполняет TypeScript type checking (`tsc -b`) и Vite build.
Отдельные Python lint и type-check команды в репозитории не настроены; не
заявляйте их выполненными. Интеграционные тесты Product API требуют доступного
PostgreSQL:

```bash
python -m pytest services/product_api/tests -q
```

## Миграции и совместимость

Команды Alembic выполняйте из `services/product_api`:

```bash
alembic -c alembic.ini upgrade head
alembic -c alembic.ini revision --autogenerate -m "<описание>"
```

Создавайте миграцию только при намеренном изменении схемы. Миграции
append-only: не переписывайте применённую историю. Не применяйте их к
production или неизвестной БД без явного разрешения, backup/restore-плана и
проверки сохранности данных.

API, модели, сериализация, snapshots и сохранённые записи должны оставаться
обратно совместимыми либо получать явно утверждённую версию и migration path.
Тесты изменённого поведения покрывают ошибки, неполные данные, старые записи и
старых клиентов.

## Безопасность и готовность итерации

Не коммитьте секреты, токены, auth-файлы, `.env`, production raw probe data,
логи, кэши и временные файлы. Допустимые fixtures должны быть минимальными,
обезличенными и не содержать секретов.

Итерация готова, когда утверждены спецификация и план, выполнен весь scope без
несвязанных изменений, сохранены архитектурные инварианты и совместимость,
проходят targeted и затронутые regression checks, `git diff --check` не
находит ошибок, а независимое review не содержит блокеров. Итоговый отчёт
перечисляет изменённые поверхности, миграции/контракты, точные команды и
результаты, baseline-падения, ограничения и решение reviewer.
