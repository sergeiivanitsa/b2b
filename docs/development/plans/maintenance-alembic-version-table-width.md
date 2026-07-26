# Maintenance — Alembic version table bootstrap plan

## Changed-file manifest

| File | Планируемое изменение |
|---|---|
| `docs/development/iterations/maintenance-alembic-version-table-width.md` | Короткая specification и acceptance criteria. |
| `docs/development/plans/maintenance-alembic-version-table-width.md` | Этот implementation plan. |
| `services/product_api/alembic/env.py` | PostgreSQL bootstrap до `context.run_migrations()`. |
| `services/product_api/tests/test_alembic_version_table_bootstrap.py` | Реальные CLI integration scenarios на disposable PostgreSQL. |
| `services/product_api/tests/conftest.py` | Исключение self-managed disposable migration tests из общей DB cleanup fixture. |
| `services/product_api/tests/test_company_report_jobs_migration.py` | Удаление test-only precreation `VARCHAR(128)`. |
| `services/product_api/tests/test_company_report_publications_migration.py` | Удаление test-only precreation `VARCHAR(128)`. |

Revision files, application models/tables, roadmap/DevFlow state, Docker
Compose и deploy workflow не меняются.

## Stage 1 — bootstrap

1. Получить revisions через публичные `ScriptDirectory.from_config()` и
   `walk_revisions()`.
2. Вычислить max ID length, добавить 16 символов запаса и округлить вверх до
   16; минимальная ширина — 64. Для текущего max 38 итог равен 64.
3. В отдельной управляемой transaction на online migration connection:
   - создать отсутствующую version table через SQLAlchemy metadata;
   - проверить реальный `version_num` через SQLAlchemy Inspector;
   - расширить ограниченный string column PostgreSQL DDL, если он уже;
   - fail closed для отсутствующей/non-string column.
4. После commit bootstrap настроить Alembic context и выполнить обычную
   migration transaction. Stamp/reset и изменение application tables не
   добавлять.

## Stage 2 — PostgreSQL integration tests

Добавить subprocess helper, запускающий реальный Alembic CLI module из
`services/product_api` с тем же `alembic.ini` и `DATABASE_URL`, что использует
production command.

Fresh database:

- подтвердить отсутствие `alembic_version`;
- выполнить `upgrade head` и `current`;
- подтвердить единственный head и достаточную ширину;
- повторить `upgrade head`, сравнить version/schema;
- downgrade с `0014` через `0013` до `0012`, затем upgrade до head.

Existing `VARCHAR(32)`:

- реальными migrations подготовить schema/current на
  `0006_chat_api_v1`, затем сузить только version column до 32;
- добавить независимую sentinel table/row и снять fingerprint application
  schema;
- выполнить CLI `current`, подтвердить расширение, сохранение revision/row и
  неизменность application schema/data;
- выполнить первый и повторный `upgrade head`, подтвердить current head.

Удалить старые test-only `VARCHAR(128)` workarounds, чтобы существующие
migration tests также проходили через production bootstrap.

## Stage 3 — verification

На disposable `postgres:16-alpine` container/volume:

```text
python -m pytest services/product_api/tests/test_alembic_version_table_bootstrap.py -q
python -m pytest services/product_api/tests/test_company_report_jobs_migration.py services/product_api/tests/test_company_report_publications_migration.py -q
python -m pytest services/product_api/tests -q
```

После тестов container и volume удаляются.

Остальные обязательные проверки:

```text
python -m pytest services/product_api/tests_unit -q
python -m compileall -q services/product_api/src services/product_api/alembic services/product_api/tests services/product_api/tests_unit
docker compose -f docker-compose.yml config
docker compose -f docker-compose.product.yml config
git diff --check
```

Deploy validation проверяет, что workflow продолжает запускать ровно
production `alembic -c alembic.ini upgrade head` до старта Product API/worker.
Security/path scan проверяет diff на secrets, raw payload, опасные DB targets,
stamp/reset и запрещённые Git/production operations.

## Completion gate

- Independent plan review approved; допускается один correction pass.
- PostgreSQL scenarios и затронутые Product API tests проходят.
- Independent code review не содержит существенных замечаний; допускается один
  fix pass и повтор затронутых проверок.
- Финальный diff не затрагивает revision graph, application schema или
  iteration 13.
- Создан ровно один локальный conventional commit; push/PR/merge не
  выполняются; worktree после commit чистый.
