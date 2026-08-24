# Итерация 20 — Backend Company Card v2: continuation implementation plan

ID: `20`

Slug: `company-card-v2-backend-foundation`

Статус плана: `approved_after_single_correction`

## 1. Execution rules

- Работать только в continuation worktree/branch.
- Старый blocked worktree read-only до plan approval.
- После approval переносить только code/tests/runbook seed, не старые state/
  spec/plan/evidence.
- Seed untrusted: сначала blocker reproduction tests, затем исправления.
- Не менять Roadmap, deploy/nginx, frontend source, dependencies.
- Не выполнять live provider/FNS/Gateway/AI, production DB/deploy.
- Commit/push только после full green matrix и independent `READY`.

## 2. Changed-file manifest

### Docs/state

```text
docs/development/DEVFLOW_STATE.yaml
docs/development/iterations/iteration-20-company-card-v2-backend-foundation.md
docs/development/plans/iteration-20-company-card-v2-backend-foundation.md
```

### Settings/provider/routes

```text
services/product_api/.env.example
services/product_api/src/product_api/settings.py
services/product_api/src/product_api/main.py
services/product_api/src/product_api/providers/datanewton/models.py
services/product_api/src/product_api/providers/datanewton/client.py
services/product_api/src/product_api/routers/company_reports.py
services/product_api/src/product_api/routers/company_report_presentations.py
```

### V2 domain

```text
services/product_api/src/product_api/company_reports/company_card_v2/__init__.py
services/product_api/src/product_api/company_reports/company_card_v2/models.py
services/product_api/src/product_api/company_reports/company_card_v2/decimal_transport.py
services/product_api/src/product_api/company_reports/company_card_v2/canonical_json.py
services/product_api/src/product_api/company_reports/company_card_v2/evidence.py
services/product_api/src/product_api/company_reports/company_card_v2/counterparty.py
services/product_api/src/product_api/company_reports/company_card_v2/finance.py
services/product_api/src/product_api/company_reports/company_card_v2/arbitration.py
services/product_api/src/product_api/company_reports/company_card_v2/privacy.py
services/product_api/src/product_api/company_reports/company_card_v2/public_h2_models.py
services/product_api/src/product_api/company_reports/company_card_v2/public_h2.py
services/product_api/src/product_api/company_reports/company_card_v2/service.py
```

### Persistence/lifecycle/Claims

```text
services/product_api/src/product_api/company_reports/persistence/models.py
services/product_api/src/product_api/company_reports/persistence/jobs.py
services/product_api/src/product_api/company_reports/persistence/repository.py
services/product_api/src/product_api/company_reports/persistence/public_h1.py
services/product_api/src/product_api/company_reports/persistence/publications.py
services/product_api/src/product_api/company_reports/persistence/serialization.py
services/product_api/src/product_api/company_reports/persistence/v3.py
services/product_api/src/product_api/company_reports/persistence/presentations.py
services/product_api/src/product_api/company_reports/persistence/__init__.py
services/product_api/src/product_api/company_reports/service.py
services/product_api/src/product_api/company_reports/worker.py
services/product_api/src/product_api/claims/company_report_handoff.py
services/product_api/alembic/versions/0016_company_card_v2_foundation.py
```

### Tests/fixtures/runbook

```text
services/product_api/tests_unit/test_datanewton_provider_result.py
services/product_api/tests_unit/test_datanewton_provider_finance.py
services/product_api/tests_unit/test_datanewton_probe_files.py
services/product_api/tests_unit/test_company_report_persistence_serialization.py
services/product_api/tests_unit/test_company_report_repository_pending.py
services/product_api/tests_unit/test_company_report_repository_queries.py
services/product_api/tests_unit/test_company_report_repository_privacy.py
services/product_api/tests_unit/test_company_report_job_models.py
services/product_api/tests_unit/test_company_report_jobs.py
services/product_api/tests_unit/test_company_report_worker.py
services/product_api/tests_unit/test_company_report_worker_settings.py
services/product_api/tests_unit/test_company_report_public_h1_service.py
services/product_api/tests_unit/test_company_report_publications.py
services/product_api/tests_unit/test_company_reports_api.py
services/product_api/tests_unit/test_claims_company_report_handoff.py
services/product_api/tests_unit/test_company_card_v2_decimal_transport.py
services/product_api/tests_unit/test_company_card_v2_canonical_json.py
services/product_api/tests_unit/test_company_card_v2_cohort.py
services/product_api/tests_unit/test_company_card_v2_counterparty.py
services/product_api/tests_unit/test_company_card_v2_finance.py
services/product_api/tests_unit/test_company_card_v2_arbitration.py
services/product_api/tests_unit/test_company_card_v2_privacy.py
services/product_api/tests_unit/test_company_card_v2_serialization.py
services/product_api/tests_unit/test_company_card_v2_public_h2.py
services/product_api/tests_unit/test_company_card_v2_presentations.py
services/product_api/tests_unit/test_company_card_v2_public_h2_side_effects.py
services/product_api/tests_unit/fixtures/company_reports/snapshot_v2_exact.json
services/product_api/tests_unit/fixtures/company_card_v2/snapshot_v3_complete.json
services/product_api/tests_unit/fixtures/company_card_v2/snapshot_v3_sparse_signed.json
services/product_api/tests_unit/fixtures/company_card_v2/public_h2_v1_expected.json
services/product_api/tests_unit/fixtures/company_card_v2/public_h2_v2_expected.json
services/product_api/tests_unit/fixtures/company_card_v2/public_h2_v3_expected.json
services/product_api/tests_unit/fixtures/company_card_v2/cjson_vectors.json
services/product_api/tests_unit/fixtures/company_card_v2/counterparty_observed_shape.json
services/product_api/tests_unit/fixtures/company_card_v2/finance_lexical_payload.json
services/product_api/tests_unit/fixtures/company_card_v2/arbitration_pages.json
services/product_api/tests/conftest.py
services/product_api/tests/test_company_card_v2_migration.py
services/product_api/tests/test_company_report_presentations.py
services/product_api/tests/test_company_report_public_h2_reads.py
services/product_api/tests/test_company_report_publications.py
services/product_api/tests/test_company_report_publications_migration.py
services/product_api/tests/test_company_report_jobs.py
services/product_api/tests/test_company_report_jobs_migration.py
services/product_api/tests/test_company_reports_api.py
services/product_api/tests/test_company_report_public_h1_reads.py
services/product_api/tests/test_claims_company_report_handoff.py
scripts/run-iteration20-postgres-tests.ps1
```

`company_report_h2_lifecycle_heads` реализуется в уже перечисленных:

```text
services/product_api/src/product_api/company_reports/persistence/models.py
services/product_api/src/product_api/company_reports/persistence/presentations.py
services/product_api/alembic/versions/0016_company_card_v2_foundation.py
services/product_api/tests/test_company_report_presentations.py
services/product_api/tests/test_company_report_public_h2_reads.py
```

Новый production file не требуется.

Existing v1 fixture/goldens are immutable. Expansion requires scope review.

Integrator note: `test_company_report_jobs_migration.py` is included solely to
keep its historical `0013` schema assertion independent from the new `0016`
writer/fence columns. The test continues to assert the complete `0013` shape;
it must not compare that historical revision to the current ORM table.

## 3. Stage 0 — seed and baseline

After approval:

1. Record both worktree/base hashes and old partial manifest.
2. Mechanically transfer code/tests/runbook only; keep current state/spec/plan.
3. Reject transferred path outside manifest.
4. Run `git diff --check` and secret/raw scan.
5. Lock v1 fixture/H1 golden hashes and Alembic `0015` head.
6. Run current focused H1/jobs/Claims baseline.
7. Maintain a ten-blocker closure checklist.

## 4. Stage 1 — RED blocker and named regression tests

До production fixes добавить failing tests:

1. H1 v3-shadow для newer v3 pending/failed/finalized.
2. Full H2 leaf/CJSON и finance-policy-v1 rejection.
3. Presentation/head/public-H2 lifecycle, multiple history и full HTTP matrix.
4. Composite cross-subject pin/head/assignment и stale H1 CAS.
5. Atomic H1 publication/pin rollback.
6. Clean-0015/corrupt/downgrade/re-upgrade migration.
7. One-claim stale token/fence и terminal expiry; отсутствие reclaim.
8. Full section-31 arbitration.
9. Counterparty/privacy/Claims.
10. Targeted/Full runbook.

Обязательные exact regression names:

```text
test_lock_or_create_subject_for_update_two_subjects_has_no_cartesian_join
test_h1_status_ignores_newer_v3_pending
test_h1_status_ignores_newer_v3_failed
test_h1_status_ignores_newer_v3_finalized
test_public_h1_missing_exact_publication_report_is_terminal
test_public_h1_corrupt_exact_publication_report_is_terminal
test_latest_equal_generated_at_uses_id_not_created_at
test_publication_equal_generated_at_uses_id_not_created_at
test_lexical_manifest_excluded_from_model_dump
test_lexical_manifest_absent_from_snapshots_and_journals
test_lexical_manifest_absent_from_probe_metadata_and_logs
```

Tests сначала обязаны падать по контрактной причине.

## 5. Conflict-free per-file ownership

Workers не редактируют shared/integrator files. Нужные изменения передаются
integrator как точные notes/diffs.

| Owner | Exact production files |
|---|---|
| A — DTO/API | `providers/datanewton/models.py`, `providers/datanewton/client.py`, `company_card_v2/decimal_transport.py`, `canonical_json.py`, `finance.py`, `public_h2_models.py`, `public_h2.py`, `company_card_v2/service.py`, `company_reports/service.py`, `routers/company_reports.py` |
| B — persistence | `persistence/models.py`, `jobs.py`, `repository.py`, `public_h1.py`, `publications.py`, `serialization.py`, `v3.py`, `presentations.py`, `worker.py`, `routers/company_report_presentations.py`, migration `0016` |
| C — evidence/privacy | `company_card_v2/models.py`, `evidence.py`, `counterparty.py`, `arbitration.py`, `privacy.py`, `claims/company_report_handoff.py` |
| D — integration | только `services/product_api/tests/*.py`, `services/product_api/tests/conftest.py`, `scripts/run-iteration20-postgres-tests.ps1` |
| Integrator | `.env.example`, `settings.py`, `main.py`, оба `__init__.py`, docs/state и любые import/export conflict resolutions |

Unit test ownership:

| Owner | Tests/fixtures |
|---|---|
| A | provider result/finance/probe-files, Decimal, CJSON, cohort, finance, public-H2, side-effects, public-H1 service, company-reports API; snapshot/public-H2/CJSON/finance fixtures |
| B | persistence serialization, repository pending/queries/privacy, job models/jobs/worker/settings, publications, presentations |
| C | counterparty, arbitration, privacy, Claims handoff; counterparty/arbitration fixtures |
| D | только PostgreSQL integration tests/conftest/runbook |

`company_card_v2/service.py` и `company_reports/service.py` принадлежат A.
Ни B, ни C их не редактируют. `settings.py`, `main.py` и `__init__.py`
редактирует только integrator после получения notes.

Integration order:

1. C domain contracts;
2. A Decimal/DTO/API;
3. B persistence/lifecycle/migration;
4. D integration/runbook;
5. integrator applies shared notes and resolves imports;
6. focused matrices;
7. full verification.

## 6. Package A gates

- Decimal grammar/bounds and exact response-byte manifest; legacy provider
  remains usable when v3 lexical gate fails.
- Every section-26 model family/cross-validator/cardinality/order.
- Section-27 golden/negative/size/digest/script-safe vectors.
- All 12 finance codes, state distinctions, signs, F1–F5 formulas/windows/
  denominator/residual/geometry.
- Exact H2 selection/HTTP/no-DML/external-call tests and H1 API compatibility.

Package A дополнительно обязан:

- hard-code/validate only `datanewton_finance_thousand_rub_v2`;
- reject v1 at FinanceBasis, snapshot, Chart Facts and every PublicFinanceMoney;
- ensure lexical manifest uses `exclude=True`;
- prove absence from dumps/snapshots/journals/probes/logs;
- use finalized order exactly `generated_at DESC NULLS LAST, id DESC`;
- implement public-H2 head resolution supplied by B repository API;
- accept narrative only through injected in-memory protocol in pure tests;
- never create runtime fallback/prose.

Focused command includes decimal, CJSON, finance, public-H2, side-effect,
cohort and company-reports API unit tests.

## 7. Package B gates

- Add exact presentation composite unique key and
  `company_report_h2_lifecycle_heads`.
- Update head only in explicit POST create/reuse transaction.
- Test exact reuse does not increment head; a new explicit run does.
- Replace generic pin identity by composite PK/FKs/discriminated H1/H2 shapes.
- Persist H2 narrative status only as unresolved with null kind/key/digest and
  `indexable=false`.
- Reject every H2 assignment/CAS attempt; implement H1 CAS foundation only.
- Preserve one-claim lifecycle: generation `0→1`, no reclaim, expiry terminal.
- Central full tuple comparison on every transition.
- Apply H1 predicate before selection everywhere.
- Use exact finalized ordering `generated_at DESC NULLS LAST, id DESC`.
- Fix two-subject subject-lock query without cartesian join.
- Preserve terminal corrupt/missing active H1 publication behavior without
  fallback.
- Mirror H1 publication/pin atomically.
- Prove migration including lifecycle head, corrupt rollback and downgrade.

Focused command includes repository/job/worker/public-H1/publication/
presentation unit tests.

## 8. Package C gates

- Exact manifest-driven counterparty paths/types/caps; deferred leaves hidden.
- Full arbitration registry/page/row/byte/dedup/counter/reason/date/role matrix.
- Permanent conflict exclusion, HMAC/ordinal goldens, alias/visible-number gates.
- Private path policy and public taint scanner across DTO/body/headers/logs/
  Claims.
- Exact v1/v2/v3 Claims lifecycle/hash/identity/profile/generation matrix.

Focused command includes counterparty/arbitration/privacy/Claims unit tests.

## 9. Package D and PostgreSQL gates

Runbook requires already-local `postgres:16-alpine`, `--pull=never`, loopback
dynamic port, tmpfs/no volume, generated credentials, root/Product `.env`
rejection, external/H2 activation env cleared, exact labels/cleanup, and proof
that imported Product API path belongs to continuation worktree. JUnit requires
tests > 0 and zero failure/error/skip.

Migration tests use separate databases for clean-0015, corrupt atomic failures
and downgrade/re-upgrade. Targeted includes all new migration/presentation/H2
files plus affected H1 publication/jobs/API/read and Claims. Full runs all
`services/product_api/tests`.

Package D owns `services/product_api/tests/conftest.py` exclusively.

Targeted PostgreSQL must include named cases for:

- two-subject subject lock;
- three v3-shadow H1 statuses;
- corrupt/missing active public-H1 outer join;
- equal generated/inverted created ordering;
- presentation history plus exact H2 head;
- cross-subject head/pin/assignment rejection;
- unresolved H2 pin not eligible/not assignable;
- one-claim expiry terminal/no reclaim;
- atomic H1 publication mirror;
- migration clean/corrupt/downgrade/re-upgrade.

## 10. Cross-package assertions

- Finance policy is v2 in basis/snapshot/Chart Facts/PublicFinanceMoney; v1
  fails every layer.
- Snapshot, migration, pin and service field identities coincide.
- Public-H2 uses active pin → staged pin → exact lifecycle head; never latest v3.
- H2 pin narrative status is unresolved; kind/key/digest are null.
- No narrative artifact table, generation, durable relation or runtime fallback
  exists.
- Pure DTO goldens use only injected validated in-memory bindings.
- H2 assignment/CAS is impossible in iteration 20; H1 CAS remains tested.
- One claim only; fence never exceeds 1; expiry is terminal.
- Same Chart Facts hash is used in snapshot/pin/DTO.
- Public builder receives no private basis token.
- H1 pin preserves existing hash/policy/path semantics.
- Claims uses exact v3 parser, not latest/public resolver.
- A1–A5 remain null with populated synthetic basis.
- F1–F5 publish only admitted nonzero Decimal under policy v2.

## 11. Mandatory final verification

```powershell
python -m pytest services/product_api/tests_unit -q
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-iteration20-postgres-tests.ps1 -Mode Targeted
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-iteration20-postgres-tests.ps1 -Mode Full
python -m pytest services/gateway_api/tests -q
npm run lint --prefix services/web_ui
npm run test --prefix services/web_ui
npm run build --prefix services/web_ui
python -m compileall services/product_api/src/product_api
git diff --check
git status --short --branch
```

Web source is unchanged. If dependencies are absent, only lockfile-preserving
`npm ci` in this worktree is allowed; package/lock must stay unchanged.
Environment failures are not passes. No Python lint/typecheck is claimed.

## 12. Review/finalization

Reviewer receives spec/plan, full diff, ten-blocker closure map, exact results,
Targeted/Full JUnit counts and migration scenario report. One correction pass
is allowed for BLOCKING/SUBSTANTIAL findings. Only all-green checks plus
`VERDICT: READY` permit state `ready_for_merge`, one conventional commit and
push of the continuation branch. PR/merge remain manual.
