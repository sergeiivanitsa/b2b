# Технический план одноразовой чистой установки production

Specification:
`docs/development/iterations/iteration-25-production-fresh-install.md`

Статус: `APPROVED — IN PROGRESS`

## Этап 1 — постоянное Claims storage

- добавить Product-only bind из server-local `CLAIMS_UPLOAD_ROOT` в effective
  `CLAIMS_UPLOAD_DIR`;
- для production закрепить `/var/lib/pork/claims-uploads/v1` и
  `/data/claims_uploads`;
- до mutation проверить legacy path/mount/zero-file state, создать root-owned
  host directory и проверить rendered compose/mount после recreate;
- после maintenance и непосредственно до legacy Product stop повторить live
  no-mount/empty proof и сохранить crash-resumable checked/frozen markers.

## Этап 2 — защищённый workflow

- отдельный manual workflow на current protected-main definition;
- exact main-history release SHA, reusable QA, exact artifacts/attestation;
- reviewed `production` environment, strict RU/US SSH/known-hosts;
- exact confirmation phrase
  `DROP-AND-RECREATE-PRODUCTION-PUBLIC-SCHEMA` и secret
  `RU_DATABASE_IDENTITY_SHA256`;
- фиксированный reviewed seed run `33253311395` и inner tgz SHA-256
  `708fb8d9a665e31854a15183328234b728cd996e276b6db1d74c887dedd28937`;
- bounded safe archive verification, no rebuild.

## Этап 3 — read-only identity preflight

- доказать exact legacy Product/report/no-narrative topology, revision `0015`,
  legacy release, provider state, empty/unmounted Claims path и configured
  persistent root;
- helper fingerprint/inspect связывает URL hash, DB name/OID, server
  address/port/version, current/session role, database owner/ACL and schema
  capability одним digest без раскрытия raw URL;
- проверить exact Gateway topology и отсутствие другого active/success fresh
  install.

## Этап 4 — durable fail-closed transaction

- stage exact artifacts/tools and protected root-only DB digest credential;
- один раз зафиксировать prior Gateway immutable canonical receipt/tag, на
  retry валидировать только prior/exact-candidate graph без перезаписи anchor;
- deploy/verify same exact Gateway SHA, then durable RU marker;
- rollback Gateway на failure/cancellation разрешать только до durable RU
  boundary;
- boot-enable exact systemd runner и nginx admission guard без reverse
  `Requires` на nginx/Docker lifetime;
- offline exact/default-off/provider/superadmin validation;
- initialize reviewed H2 seed/candidate and Web roots, install maintenance;
- stop Product/report/narrative writers and recheck zero running writers;
- guarded schema-only reset with strict ACL and DB marker;
- exact candidate Alembic to sole `0019`; interrupted stub принимать только по
  dynamic-OID structural contract и полному dependency closure;
- verify empty DB/default-off rows before first ingress, write `ingress-armed`,
  then use live-runtime reconciliation after any possible exposure;
- recreate Product/workers, verify initial superadmin, Claims mount, Gateway,
  H2/Web/nginx and public/auth smokes;
- atomically publish stage/global success receipts and disable recovery unit.

## Этап 5 — failure semantics

- before the durable RU handoff a candidate Gateway failure/cancellation
  restores only the prior Gateway;
- after the durable RU handoff the exact candidate Gateway remains and only the
  same-SHA runner may continue, even if DROP has not happened yet;
- after DROP no legacy runtime rollback is legal;
- any later failure leaves maintenance and a `roll-forward-required` marker;
- systemd/retry accepts only exact canonical phase markers and exact SHA;
- reboot/stop/final-cutover crash reasserts maintenance before regular nginx;
- success/active global receipts prevent a second destructive install.

## Этап 6 — documentation, tests and handoff

- update runbook/README/roadmap/state to replace the superseded backup
  bootstrap path;
- add static/unit contracts for workflow, DB identity/reset/defaults/runtime,
  full Alembic dependency closure, archive bounds, Claims bind/freeze,
  systemd boot ordering, workflow exclusion, cancellation, ingress ordering
  and retry semantics;
- run targeted deploy suites, Python/YAML/bash syntax and affected regressions;
- hand off the exact fingerprint command and GitHub secret value procedure;
- after merge/run success create the retained H1 anchor for `7707079463`, then
  stop until the owner separately authorizes H2 activation.
