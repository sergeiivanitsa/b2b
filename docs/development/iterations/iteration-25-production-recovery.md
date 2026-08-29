# Итерация 25 — production recovery Company Card v2

ID: 25

Slug: `company-card-v2-qa-rollout`

Recovery branch: `codex/iteration-25-production-recovery`

Recovery base: `c92597839e838da1cdc8acd015e0652dd430c08e`

Historical merge: PR `#155`, commit
`4aa2bd118a65edc13679ea88c1a29b0292634775`,
`2026-08-29T21:13:38+10:00`.

Статус: `SUPERSEDED BY OWNER DECISION`

Эта backup/bootstrap стратегия сохранена как историческая спецификация, но не
исполняется. Владелец разрешил удалить production DB data и выбрал более
простой schema-only fresh install без backup/bootstrap. Текущая спецификация:
`docs/development/iterations/iteration-25-production-fresh-install.md`.

Owner approval: пользователь явно потребовал исправить фактический
production-путь после проверки ИНН `7707079463` 2026-08-29.

## Причина возобновления

Merged iteration 25 доказала disposable QA и default-off contracts, но не
довела production до Company Card v2. Read-only проверка обнаружила:

- production остался на Alembic `0015_claims_company_report_handoff` и старом
  runtime без H2;
- migration `0016` не могла пройти поверх допустимых historical
  `succeeded/attempt_count=1` jobs, потому что добавляла им fence `0` перед
  constraint, требующим fence `1`;
- первый deploy ожидал уже существующие narrative worker, H2 asset store и
  versioned Web store, которых legacy production не мог иметь;
- обычный rollback старым image после `0016` не совместим с новым fencing
  contract и поэтому требует реального возврата БД к `0015`;
- public H1 UI мог опрашивать `pending` бесконечно;
- для одного production target отсутствовало operator-only средство создать
  rollback pin, exact H2 job и проверяемые activation/rollback decisions.

Таким образом, прежний статус `merged` остаётся историческим фактом PR, но
продуктовый результат iteration 25 считается незавершённым до закрытия этой
recovery-спецификации.

## Scope

1. Исправить unapplied-in-production revision `0016`: перенести immutable
   historical `attempt_count` в новый `fence_generation` до constraints.
2. Добавить real-PostgreSQL regression с production-like legacy cohort:
   `0015 -> head` сохраняет legacy rows, а lossy Alembic downgrade атомарно
   отказывается и оставляет head и данные неизменными. Возврат production к
   `0015` проверяется отдельно только restore exact backup с последующим
   rehearsal `0015 -> head`; identity/hash этого evidence связываются с
   bootstrap.
3. Ограничить automatic H1 pending polling утверждённым трёхминутным UX-окном.
   По истечении окна статус не объявляется failed: UI останавливает автопрос и
   предлагает одну ручную read-only проверку.
4. Добавить отдельный one-time legacy-0015 bootstrap. Обычный post-bootstrap
   deploy остаётся строгим и не получает permissive legacy branches.
5. Bootstrap обязан проверить exact legacy state, использовать один
   0015-aware report-worker drain, установить verified H2/Web assets, применить
   exact QA release и поднять Product/report/narrative workers.
6. После начала migration аварийный возврат разрешён только через заранее
   проверенный restore exact backup к `0015`, затем exact legacy runtime. Нельзя
   выдавать image-only rollback за совместимый.
7. Сохранить фактическое состояние DataNewton между deploys. H2 default-off
   определяется writer/presentation/generation/arbitration/narrative controls,
   а не отключением существующего H1 provider.
8. Добавить operator-only CLI для одного target: inspect, digest-confirmed
   prepare с durable private exact-lineage receipt, receipt-bound read-only
   status и canonical activation/rollback decision build. CLI не является HTTP
   router и сам не вызывает provider или AI.
9. Для `7707079463` текущая авторизация допускает только создание и проверку
   staged arbitration-enabled V3 с deterministic narrative fallback,
   percentage `0` и без assignment. H1 rollback pin по DB contract всегда
   indexable, поэтому безопасная пара H2/H1 decisions может быть только
   indexable. Noindex activation запрещена, а indexable activation требует
   отдельного явного решения владельца; без него recovery останавливается на
   staged H2.

## Вне scope

- массовый H2 backfill, percentage или GA rollout;
- paid AI;
- ослабление immutable snapshot, pin, assignment, fencing или privacy
  contracts;
- автоматическое создание production secret в коде или git;
- production mutation до exact merged SHA, successful checks, independent
  review и проверенного backup/restore.

## Production prerequisites

Перед фактическим bootstrap нужны не условные P1–P9 ярлыки, а конкретные
проверяемые входы:

- exact main SHA и успешная exact-SHA QA;
- backup production DB и успешный restore rehearsal к `0015`;
- verified three-release H2 seed bundle;
- pinned SSH host identities и protected production credentials;
- retained arbitration mask key вне git;
- exact target `7707079463`, private receipt path и retained observation/abort
  inputs; для activation также отдельное явное разрешение indexable H2 и
  команда немедленного rollback.

Отсутствующий вход означает остановку перед mutation, а не подстановку
фиктивного evidence digest.

## Acceptance

- production-shaped `0015 -> head` проходит без потери legacy jobs;
- lossy Alembic downgrade атомарно отказывается, сохраняя head, schema и
  migrated state; это не считается production rollback path;
- exact backup restore rehearsal возвращает sole `0015`, повторный upgrade
  достигает head без потери состояния, а bootstrap binds retained restore
  evidence identity/hash;
- migration failure атомарно оставляет `0015`;
- UI прекращает auto-poll не позднее трёх минут и manual check не создаёт job;
- legacy bootstrap невозможно запустить на любой форме, кроме exact reviewed
  `0015` state, и невозможно повторить после успеха;
- bootstrap rollback сначала возвращает DB, затем legacy runtime;
- normal deploy сохраняет DataNewton state и оставляет H2 controls off/zero;
- canary prepare создаёт не более одного exact H2 job и lone H1 rollback pin не
  меняет canonical/sitemap;
- staged fallback строго связан с prepare receipt; stale/missing receipt не
  может следовать за новым lifecycle head или породить decision;
- после отдельного разрешения indexable canary generated decisions проходят
  existing rollout validate/plan/apply/status и exact H1 -> H2 -> H1 recovery;
- targeted, full affected, deploy-contract, Web and real PostgreSQL checks
  проходят; independent review не содержит blocker;
- commit/push выполняются только по отдельной команде пользователя, merge —
  только человеком.
