# Итерация 25 — одноразовая чистая установка production

ID: 25

Slug: `company-card-v2-qa-rollout`

Implementation branch: `codex/production-fresh-install`

Статус: `IMPLEMENTATION APPROVED — IN PROGRESS`

Owner decision: существующие данные production можно полностью удалить. Владелец
выбрал чистую установку непосредственно в production без backup/bootstrap старой
БД. Разрушительное разрешение ограничено заменой PostgreSQL schema `public`.
Файлы Claims не являются данными этой schema и удалению не подлежат.

## Цель

Одним защищённым exact-SHA workflow перевести проверенный legacy production с
Alembic `0015` на чистую schema `0019`, установить Product, report/narrative
workers, тот же exact Gateway, H2/Web/nginx и оставить Company Card v2 строго
default-off. После успеха отдельным шагом остаётся H1 rollback anchor для
`7707079463`, затем отдельно авторизуемый H2 canary.

## Scope

1. Ручной workflow исполняется только из защищённого `main`, принимает exact
   lowercase SHA из истории `main`, повторно использует `qa.yml`, единственные
   build-once artifacts и canonical successful attestation этого SHA.
2. GitHub environment `production` требует reviewer. Разрушительная фраза
   должна быть ровно `DROP-AND-RECREATE-PRODUCTION-PUBLIC-SCHEMA`.
3. Read-only preflight подтверждает точный RU legacy topology, sole revision
   `0015`, server/database/OID/URL-hash/session-role/database-owner/ACL/version
   identity, schema capabilities и exact US Gateway topology без вывода URL или
   секретов.
4. Claims получают постоянный bind
   `/var/lib/pork/claims-uploads/v1:/data/claims_uploads`. До mutation workflow
   подтверждает, что старый effective path равен `/data/claims_uploads`, не
   смонтирован и не содержит файлов. Новый host root создаётся и проверяется до
   recreate. После синхронного maintenance и непосредственно перед остановкой
   legacy Product отсутствие mount/файлов доказывается повторно и фиксируется
   checked/frozen markers; остановленный Product без этих доказательств —
   `STOP`. Содержимое и имена файлов никогда не выводятся.
5. До DROP кандидат проверяется offline: exact release, сохранённый DataNewton
   state, непустой server-local `SUPERADMIN_EMAIL` и все H2/narrative/rollout
   controls off/zero.
6. Тот же exact-SHA Gateway разворачивается и health/signed ping проверяется до
   destructive boundary. Первый prior Gateway фиксируется неизменяемыми
   canonical receipt и image tag; retry принимает текущим только его или exact
   candidate и не переопределяет rollback anchor. Failure/cancellation до
   durable RU boundary восстанавливает прежний Gateway; после boundary Gateway
   rollback запрещён.
7. H2 seed/Web roots и maintenance ingress устанавливаются до остановки всех
   Product-side DB writers.
8. DB helper повторно подтверждает защищённый identity digest и sole legacy
   inventory, требует zero other sessions, в одной транзакции выполняет только
   `DROP SCHEMA public CASCADE`, `CREATE SCHEMA public AUTHORIZATION
   CURRENT_USER`, `REVOKE ALL FROM PUBLIC`, затем выдаёт runtime role только
   `USAGE,CREATE`. DB-side marker связывает reset с exact SHA/identity.
9. Exact candidate image выполняет `alembic upgrade head`; принимается только
   sole `0019_company_card_v2_rollout_control`, пустые application tables и
   точные default-off singleton rows. Interrupted empty Alembic stub допускается
   только по exact structural catalog contract и полному raw `pg_depend`
   closure; неожиданный trigger, policy, collation или иной dependent object —
   `STOP`.
10. Запускаются Product/report/narrative, проверяются image/config identity,
    persistent Claims mount, health, единственный созданный initial superadmin,
    signed Gateway, Web/H2/nginx и публичные smokes.
11. Boot-enabled systemd runner и отдельный nginx admission guard делают boot
    fail-closed: incomplete recovery сначала атомарно ставит maintenance, и
    только затем nginx разрешён к запуску. Recovery unit не имеет strong
    `Requires` на mutable Docker/nginx lifetimes. Перед regular config пишется
    durable `ingress-armed`; retry немедленно возвращает maintenance.
12. До первого ingress DB проходит strict empty `verify-runtime`. После
    возможной публичной экспозиции `verify-live-runtime` сохраняет exact
    head/marker/ACL/default-off и единственного configured superadmin, но
    допускает легитимные non-superadmin/application rows. Success публикуется
    только после повторной live verification и public smokes.

## Вне scope

- удаление или перенос Claims upload files;
- `DROP DATABASE`, Docker volumes, другие schemas или server data;
- backup/restore, legacy bootstrap и прежние P1–P9 inputs;
- автоматическое включение presentation/writer/narrative/percentage/allowlist;
- production mutation до merge и отдельного ручного запуска workflow;
- создание H2 assignment. H1 anchor и canary остаются последующими
  operator-owned шагами runbook.

## Acceptance

- workflow fail-closed связан с protected main, exact QA SHA, reviewed
  environment, точной confirmation phrase и защищённым DB identity digest;
- preflight не изменяет production и останавливается при любом topology,
  identity, revision, Claims или superadmin mismatch;
- seed archive bounded и traversal-safe; artifacts/checksums/image config
  digests перепроверяются;
- до DROP работает maintenance, все DB writers остановлены, а reset касается
  только `public` и устанавливает строгий ACL;
- после DROP никогда не запускается legacy Product; reboot/retry продолжает
  exact-SHA roll-forward, а nginx boot guard не допускает regular config при
  incomplete/invalid recovery;
- migration заканчивается exact `0019`, default-off singleton rows точны,
  остальные tables пусты до startup;
- startup создаёт ровно одного server-configured active superadmin;
- normal deploy требует canonical global fresh success и не выполняет writes
  при active/failed/enabled recovery; superseded legacy bootstrap отвергает
  active/success receipt и любой оставшийся fresh recovery unit;
- Product и Claims используют точный постоянный bind, Gateway/Product/Web/H2
  имеют exact SHA/receipt/smoke evidence;
- targeted deploy tests, affected regressions, syntax/YAML checks и
  `git diff --check` проходят; независимое review не содержит blocker.
