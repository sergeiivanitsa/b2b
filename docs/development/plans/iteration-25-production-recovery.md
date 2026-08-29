# Технический план production recovery итерации 25

Specification:
`docs/development/iterations/iteration-25-production-recovery.md`

Статус: `APPROVED — IN PROGRESS`

## Этап 1 — migration compatibility

- детерминированно backfill `fence_generation = attempt_count` внутри 0016 до
  fence constraints;
- seed 15 succeeded jobs и все остальные допустимые legacy state/attempt
  shapes на exact schema 0015;
- проверить `0015 -> head` и immutable legacy fields; отдельно доказать, что
  lossy Alembic downgrade атомарно отказывается и сохраняет head/state;
- проверить recovery path через restore exact pre-migration backup к sole
  `0015` и повторный `0015 -> head`, сохранив evidence identity/hash для
  one-time bootstrap. Не подменять restore обычным downgrade.

## Этап 2 — bounded pending UX

- использовать существующее обещание «за 3 минуты» только как automatic-poll
  window, не как backend failure SLO;
- считать более ранний deadline из server `started_at` и route-local first
  observation;
- после deadline остановить timer/abort active poll и показать one-shot status
  action без POST/create;
- покрыть old timestamp, exact boundary, pending manual result, terminal race,
  abort и route isolation.

## Этап 3 — one-time legacy bootstrap

- реализовать отдельный workflow, не добавляя legacy ветки в established
  deployment path;
- exact preflight: revision 0015, reviewed legacy Product/report image,
  narrative absence, legacy nginx and uninitialized H2/Web stores;
- verify/seed H2 bundle, временно добавить только immutable H2 asset route к
  legacy nginx, инициализировать Web root;
- отдельным helper остановить один legacy report worker только через SIGTERM и
  подтвердить две stable safe 0015 aggregate snapshots;
- применить exact QA image/migrations and start all current workers;
- переключить Web/nginx только после backend health;
- при post-migration failure сначала restore exact tested DB backup to 0015,
  затем recreate legacy Product/report and remove candidate narrative;
- добавить transactional rollback from first Web release to uninitialized
  pointer state; immutable orphan release может остаться.

## Этап 4 — exact-target canary tooling

- private target/plan/receipt files: absolute, nonsymlink, owner-only,
  canonical JSON, exclusive create and no overwrite;
- `inspect`: read-only exact release/config/storage plan;
- `prepare --confirm-digest --receipt-file`: exact H1 rollback pin without
  publication/assignment, one arbitration-enabled v3 enqueue and durable
  exact subject/head/presentation/report/job receipt before DB commit;
- `status`: privacy-safe receipt-bound lifecycle and staged-resolution state;
- `build-decisions`: receipt-bound exact active projection digest and canonical
  allowlist activation/emergency rollback documents for existing rollout CLI;
- default current outcome is STOP at staged fallback. Because H1 rollback is
  structurally indexable, noindex activation is invalid; indexable decision
  build/apply requires a new explicit owner authorization reference;
- no secrets, DB URL, INN or internal UUIDs in stdout/error messages.

## Этап 5 — documentation and state

- mark iteration 25 recovery as active while preserving historical merge
  identity;
- update runbook with the one-time bootstrap boundary and concrete canary
  sequence;
- record exact commands/results and remaining production-only inputs.

## Этап 6 — verification and review

Run from repository root:

```powershell
python -m pytest services/product_api/tests_unit -q
python -m pytest services/gateway_api/tests -q
npm run lint --prefix services/web_ui
npm run test --prefix services/web_ui
npm run build --prefix services/web_ui
python -m pytest deploy/nginx deploy/product_api deploy/web_ui -q -ra -p no:cacheprovider
pwsh -File deploy/nginx/test_product_api_conf.ps1
pwsh -NoProfile -File scripts/run-iteration25-postgres-tests.ps1 -Mode PostgresFull
git diff --check
```

Then perform independent code review against the full diff and resolve every
blocker before requesting commit/push.

## Этап 7 — production handoff

Only after merge:

1. collect exact live read-only state;
2. create and restore-test the exact backup;
3. verify/seed H2 assets;
4. run the one-time bootstrap for the exact merged SHA;
5. generate retained arbitration key outside git and recreate runtime with
   allowlist exactly `7707079463`;
6. inspect/prepare with an exact private receipt, close public writer flags,
   wait for report+narrative fallback completion and stop at staged H2;
7. only after a separate explicit indexable-canary authorization,
   build/validate/plan/apply the indexable decision, smoke canonical H2 and
   graphs, observe, then either retain or execute the prebuilt exact indexable
   H1 rollback decision.
