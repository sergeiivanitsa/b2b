# Maintenance — Alembic version table bootstrap

Ветка: `fix/alembic-version-table-width`

## Цель

Исправить production migration bootstrap так, чтобы обычный
`alembic -c alembic.ini upgrade head` работал:

- на полностью пустой PostgreSQL database;
- на существующей database с
  `alembic_version.version_num VARCHAR(32)` и сохранённой короткой revision.

Это отдельная maintenance-задача. Статусы roadmap/DevFlow, iteration 13,
Claims, CompanyReport, SEO, scoring и AI не изменяются.

## Контракт решения

Online Alembic environment до выполнения revision scripts и до записи нового
revision ID:

1. читает весь revision graph через публичный `ScriptDirectory`;
2. вычисляет максимальную длину существующих revision IDs;
3. добавляет разумный запас и округляет ширину до блока, не меньшего 64;
4. через тот же управляемый SQLAlchemy connection создаёт отсутствующую
   `alembic_version` с primary key либо расширяет ограниченный `VARCHAR`;
5. оставляет уже достаточный или неограниченный string type без изменения.

Bootstrap поддерживает только PostgreSQL, идемпотентен и не использует
process-local state. Он не выполняет stamp/reset, не меняет revision graph,
не удаляет текущую revision и не обращается к application tables.

Существующие revision IDs и `down_revision` остаются неизменными. Новая
feature migration не создаётся, потому что исправление должно сработать до
первой записи длинного historical revision ID.

## Acceptance criteria

- Fresh disposable PostgreSQL проходит от base до единственного текущего head.
- `alembic current`, первый и повторный `upgrade head` успешны.
- Созданная version column вмещает максимальный revision ID с запасом.
- Существующая `VARCHAR(32)` расширяется до записи длинной revision, а её
  текущее короткое значение сохраняется.
- Повторный запуск не меняет head и не создаёт duplicate objects.
- Изолированный `current` не меняет application schema/data и не удаляет
  строку version table.
- Downgrade последних применимых feature revisions и повторный upgrade до head
  успешны.
- Проверки выполняются только на disposable PostgreSQL; SQLite и production
  database не используются.

## Риски и ограничения

- PostgreSQL `ALTER COLUMN TYPE VARCHAR(n)` берёт блокировку version table;
  таблица содержит только revision rows, а production deploy уже запускает
  один migration process до старта нового API/worker.
- Bootstrap не пытается чинить несовместимую пользовательскую таблицу
  `alembic_version` без string column `version_num`: такой случай завершается
  явной ошибкой вместо stamp/reset или потери данных.
- Offline `--sql` не имеет managed database connection и не входит в scope;
  production entrypoint использует online asyncpg connection.
