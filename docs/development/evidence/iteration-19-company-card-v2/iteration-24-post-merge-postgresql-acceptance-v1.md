# Iteration 24 post-merge PostgreSQL acceptance v1

Artifact ID: `company_card_v2_iteration_24_post_merge_postgresql_acceptance_v1`

Decision date: `2026-08-28`

Repository base: `557244b69c5bf54bba6ae07bfd5a39638ff14f18`

Merged iteration 24 commit: `e7478a2fba9aaca17829c3d99e89e8d83d4b3188`

Final decision: `ACCEPTED — POST-MERGE POSTGRESQL GATE CLOSED`

Production activation: `NOT AUTHORIZED`

## 1. Acceptance boundary

A dedicated acceptance worktree was created from the exact merged repository
base `557244b69c5bf54bba6ae07bfd5a39638ff14f18`. Before the final successful
run, it contained only the two approved migration-test corrections documented
below. The runner was executed there with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-iteration24-postgres-tests.ps1
```

The runner created a uniquely labelled disposable local PostgreSQL 16
container with tmpfs storage and two validated test databases. It rejected
inherited database URLs and repository `.env` input. No production or unknown
database, live provider call, AI call, publication or feature activation was
in scope.

## 2. Acceptance findings and corrections

The first run exposed a test-fixture-only asyncpg type inference conflict: the
same `:state` bind was used for a `VARCHAR(16)` target and a `CASE` comparison.
The approved correction added an explicit `CAST(:state AS VARCHAR(16))` inside
the fixture expression.

The second run passed the pre-DDL guard test and exposed a test assertion that
looked up logical Alembic constraint names. The repository SQLAlchemy naming
convention creates these physical PostgreSQL names:

- `ck_company_reports_company_reports_arbitration_decision`;
- `ck_company_report_jobs_company_report_jobs_arbitration_decision`.

The approved correction changed only the migration test expectations to those
physical names. Migration `0018`, ORM metadata, production runtime and the
dedicated runner were not changed.

## 3. Final verification

| Gate | Result |
|---|---|
| Iteration 24 migration module | `2 passed, 24 warnings in 12.27s` |
| Runner-defined affected nine-file integration suite | `79 passed, 22 warnings in 45.43s` |
| Product API unit regression | `1524 passed, 4 warnings in 56.55s` |
| Disposable resource cleanup | no containers remained with label `com.b2b.iteration24.disposable=true` |
| Docker engine after cleanup | available, server version `29.1.3` |

The final runner exited with code `0`. Both pytest summaries contained no
failures, errors or skips. Reported warnings were existing framework
deprecation and OpenAPI operation-ID warnings, not acceptance failures.

## 4. Disposition

The dedicated post-merge PostgreSQL acceptance debt for iteration 24 is
closed. This evidence closes the iteration-24 acceptance prerequisite for
iteration 25 readiness. It does not authorize iteration 25 implementation: a
separate specification and implementation plan must first be prepared,
reviewed and explicitly approved. All production provider, publication and
feature flags remain off until a separate rollout decision.
