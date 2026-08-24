# Итерация 20 — Backend и данные Company Card v2: continuation

ID: `20`

Slug: `company-card-v2-backend-foundation`

Scope: `narrowed_fail_closed_v1_continuation_v2`

Base commit: `6bee95e881a3e9ea1fe324ca13c11ae239f896f4`

Public contract: `company_public_h2_v1`

Snapshot writer version: `3`

Статус спецификации: `approved_after_single_correction`

Production activation: `NOT AUTHORIZED`

## 1. Назначение

Continuation-проход завершает тот же нормативный scope итерации 20 после
заблокированного code review. Он не создаёт новую продуктовую итерацию и не
сокращает контракт. Старый незакоммиченный worktree является только
непроверенным implementation seed: перенос допускается после plan approval,
а каждая перенесённая строка повторно проходит тесты и review.

Обязательный результат:

1. V3 не меняет H1 status/latest/publication и не затеняет v1/v2.
2. Реализован полный recursive leaf-level `company_public_h2_v1`.
3. Реализованы cohort, presentation create/status и GET/HEAD lifecycle.
4. Pin/assignment persistence использует нормативные composite bindings.
5. H1 publication и H1 pin атомарны.
6. Migration доказана на clean `0015`, corrupt upgrade и downgrade/re-upgrade.
7. Весь job lifecycle использует полный immutable writer/fence tuple.
8. Fixture-only arbitration закрывает section 31, но shipped network gate
   остаётся закрытым, public A1–A5 — `null`.
9. Counterparty/privacy/Claims закрывают разрешённые и запрещённые матрицы.
10. Unit, Targeted/Full PostgreSQL, Gateway и web checks проходят полностью.

## 2. Приоритет источников

1. `decisions/iteration-20-owner-scope-decision-v1.md`.
2. `evidence/iteration-19-company-card-v2/iteration-20-gate-readiness-v3.md`.
3. Sections 26–31 и 35 iteration 19.
4. Architecture/privacy ADR iteration 19.
5. Provider/finance/arbitration evidence v2/v3.
6. Существующие H1/v1/v2 runtime contracts и goldens.
7. Эта continuation-спецификация.
8. Старые iteration-20 spec/plan.
9. Старый partial diff.

Partial diff не является evidence или нормативным источником.

## 3. Неизменные границы

```text
COMPANY_CARD_V2_PRESENTATIONS_ENABLED=false
COMPANY_CARD_V2_WRITER_ENABLED=false
COMPANY_CARD_V2_ROLLOUT_GENERATION=0
COMPANY_CARD_V2_ALLOWLIST_INNS=[]
COMPANY_CARD_V2_PERCENTAGE_BASIS_POINTS=0

production provider operation = disabled
production H2 assignment/publication = disabled
live DataNewton/FNS/Gateway/AI = prohibited
production DB/deploy = prohibited
provider zero publication = prohibited
public arbitration A1..A5 = gate_closed/null
```

H1 остаётся production resolver и rollback path. Вне scope: iteration 21 AI,
iteration 22–24 frontend/charts, iteration 25 activation, dependencies,
`ROADMAP.md`, deploy/nginx и production configuration.

## 4. Exact version compatibility

- Legacy snapshot parser принимает только raw discriminator `"1"|"2"`.
- V3 parser принимает только raw discriminator `"3"`.
- Missing/unknown/integer/coerced/cross-version discriminator отклоняется.
- V1/V2 bytes/hash и H1 DTO/goldens не меняются.
- V3 не проходит через H1 normalizers, signals, scoring или AI explanation.

Permanent H1 decision:

```text
writer_profile = h1_legacy_writer_v2
report_version = 2
presentation_contract = company_public_h1_v1
rollout_config_generation = 0
```

`POST /company-reports` никогда не читает H2 cohort/assignment. Все H1
repository/status/latest/publication/API queries применяют H1 predicate
до любого выбора кандидата:

```sql
writer_profile = 'h1_legacy_writer_v2'
AND presentation_contract = 'company_public_h1_v1'
AND rollout_config_generation = 0
AND report_version IN ('1','2')
```

Finalized reads дополнительно требуют `complete|partial`. Для
finalized/latest selection нормативный порядок ровно:

```sql
ORDER BY generated_at DESC NULLS LAST, id DESC
```

`created_at` не участвует ни как tie-break, ни как fallback. Regression обязан
создать два eligible H1 report с одинаковым `generated_at` и намеренно
инвертированным `created_at`; выбирается больший `id`.

H1 current status сначала рассматривает единственный active H1 job. Если его
нет, status-кандидаты фильтруются по H1 profile/contract/version до применения
существующего status contract. Более новый v3 pending, failed или finalized
никогда не меняет H1 status/latest/public-H1. V3-only subject не даёт legacy
snapshot, но explicit H1 POST может создать новый v2.

## 5. Cohort, presentation lifecycle и durable H2 head

`RolloutConfigV1` startup-validates positive generation when enabled,
normalized/sorted/unique INN allowlist и percentage `0..10000`. Exact allowlist
имеет приоритет; затем применяется зафиксированный SHA-256 bucket section 28.
Body/query/header/cookie/auth/locale не выбирают version/profile/bucket.

H2 decision:

```text
writer_profile = company_card_v2_writer_v3
report_version = 3
presentation_contract = company_public_h2_v1
rollout_config_generation > 0
normalized_identifier = exact INN
```

```http
POST /company-report-presentations
GET  /company-report-presentations/{presentation_id}/status
```

POST принимает ровно `{"identifier":"<INN>"}`. После cohort decision одна
транзакция:

1. блокирует exact subject;
2. проверяет единственный active job;
3. переиспользует только полный совпадающий H2 decision;
4. возвращает `409 report_writer_profile_conflict` при несовместимом H1/H2 job;
5. создаёт или переиспользует opaque presentation;
6. обновляет durable lifecycle head;
7. flush-ит job/report/presentation/head как один atomic result.

Presentation навсегда связан с exact
`subject_id + report_id + presentation_contract + rollout_config_generation`.
Status читает только presentation ID, не выбирает latest, не пересчитывает
cohort и не использует lifecycle head.

INN-keyed `public-h2` lifecycle определяется не generic latest, а отдельной
таблицей:

```text
company_report_h2_lifecycle_heads:
  subject_id: primary key
  presentation_id
  report_id
  presentation_contract: literal company_public_h2_v1
  rollout_config_generation: positive integer
  head_generation: positive integer
  changed_at
```

Composite FK связывает head с exact presentation
`(presentation_id, subject_id, report_id, presentation_contract,
rollout_config_generation)`. Head обновляется только explicit POST create/reuse
в той же транзакции. Exact reuse того же presentation/report не увеличивает
`head_generation`; новый explicit H2 run увеличивает его на один. Conflict или
failed transaction не меняет head.

Это делает несколько presentation/history rows детерминированными:

- status по старому presentation ID остаётся привязанным к старому report;
- public-H2 после pin precedence смотрит только exact current head;
- pending head → `409 report_pending`;
- failed head → `409 report_failed`;
- finalized head без eligible exact pin/binding → `409 report_not_eligible`;
- старый presentation или более новый unbound v3 не выбирается как latest;
- legacy v1/v2 preview допустим только когда у subject нет H2 head и нет v3
  report, как требует section 29.3.

Disabled gate останавливается до DB session/provider.

## 6. One-claim job fence

Iteration 20 сохраняет существующий one-claim lifecycle. Reclaim/replay
запрещён.

```text
queued:
  fence_generation = 0
  attempt_count = 0

sole successful claim:
  fence_generation: 0 -> 1
  attempt_count: 0 -> 1
  immutable lease_token assigned

expired running:
  job/report become terminal failed
  safe code = report_execution_interrupted
  never returned to queued/running
```

Новый run после terminal failure возможен только новым explicit POST и получает
новые job/report IDs.

Каждый enqueue/reuse, sole claim, heartbeat, H1 completion, H2 completion,
owned failure, expired-job reconciliation и worker exception path сверяет:

```text
job_id, report_id, subject_id,
writer_profile, report_version, presentation_contract,
rollout_config_generation, lease_token, fence_generation
```

Старый token, fence `0`, чужой decision или изменённая generation не может
heartbeat/finalize/fail sole claim. Mismatch не пишет snapshot и не изменяет новое
ownership state. Никакой код не увеличивает fence выше `1` и не реанимирует
expired job.

H1 worker запускает только H1 builder. H2 worker требует stored H2 decision,
enabled writer и явно injected fixture builder; shipped default не создаёт
v3/arbitration provider request.

## 7. Immutable v3 snapshot

Frozen `extra=forbid` snapshot содержит report/profile/contract/generation,
exact subject/target identity, UTC generated time, approved counterparty core,
safe source metadata, finance basis, private sanitized arbitration basis,
versioned Chart Facts/hash, evidence/privacy/policy versions и limitations.

Finance basis, snapshot и Chart Facts несут exact owner-approved policy:

```text
datanewton_finance_thousand_rub_v2
```

Любой missing policy, `datanewton_finance_thousand_rub_v1` или иной token
отклоняет v3 snapshot/facts/projection. V3/H2 не наследует draft literal v1 из
section 26.

Iteration 20 не владеет narrative artifact table, generation job, Gateway
dispatch или durable narrative relation. Snapshot может содержать только opaque
unresolved narrative metadata, если оно необходимо для forward compatibility;
оно не считается validated binding.

Обязательны record/report/subject/target/counterparty equality, equality с job
fence, exact recompute Chart Facts/hash/snapshot hash, same-hash idempotency и
запрет замены finalized snapshot. Запрещены raw page/payload/header, secret,
contact, source opponent ID/name, arbitrary provider text/URL и H1 scoring/AI.

## 8. Decimal и finance policy v2

Lexical manifest берётся из exact response bytes до float coercion и остаётся
строго ephemeral. Поле provider result использует `exclude=True` и не может
появиться в:

- `model_dump`;
- v1/v2/v3 snapshot;
- dataset/provider request journal;
- probe payload/shape/metadata artifacts;
- logs или exception context.

JSON string также допустим. Grammar и bounds: exact non-exponent decimal;
максимум 128 ASCII bytes, 96 significant digits, 32 fractional digits;
bool/float/plus/comma/whitespace/leading zero/nonfinite forbidden; negative
zero → `"0"`.

Finance policy во всех v3/H2 слоях ровно:

```text
datanewton_finance_thousand_rub_v2
```

Она обязательна в `FinanceBasisV1`, snapshot finance identity, Chart Facts root
и каждом `PublicFinanceMoney.unit_policy_version`. V1 literal в любом из этих
мест является contract error.

Finance cell state:

```text
available_nonzero | zero_unverified | missing | conflict |
decimal_transport_lossy | invalid
```

Только nonzero хранит Decimal. Zero не numeric, не участвует в arithmetic/
geometry/display и создаёт limitation; missing не становится zero.

F1–F5 реализуют все section-26 leaves/formulas: seven-year windows, keyed
geometry, signed axes including zero, F2 residual/denominator modes,
independent F3 gaps/summaries, positive F4 denominator, fixed nine F5 rows и
adjacent-year YoY. Math uses Decimal precision 34, scale 6, `ROUND_HALF_UP`.

Draft section-26 literal `datanewton_finance_thousand_rub_v1` считается
superseded owner decision и никогда не принимается v3/H2 validators или goldens.

## 9. Полный H2 DTO и CJSON

`company_public_h2_v1` рекурсивно реализует все section-26 families без
`dict[str, object]`/placeholder leaves: root/identity/status/requisites,
narrative/comments, coverage/sources/limitations/navigation/actions/CTA,
money/geometry/detail, full F1–F5, arbitration summary/safe detail/full A1–A5
и blocks. Shipped builder всегда ставит A1–A5 `null` с `gate_closed` coverage
и linked limitations.

Cross-field validators закрывают exact cardinality/order, enum, timestamp/date,
path, UUID/digest/INN/OGRN/KPP, NFC/scalar/nonblank и byte rules. Unknown nested
keys forbidden.

Iteration 20 не создаёт и не сохраняет narrative artifact, generation,
fallback catalog или artifact FK. Pure DTO builder принимает только явно
переданный validated in-memory `NarrativeBindingProtocol`; это разрешено только
unit/golden fixtures и не создаёт durable state.

Runtime resolver не может сконструировать такую binding самостоятельно.
Missing/unresolved binding даёт `report_not_eligible`. Ни fixed local prose,
ни iteration-21 universal fallback, ни synthetic binding не используются runtime-кодом.

`company_public_h2_cjson_v1` реализует NFC key/value normalization, collision и
surrogate rejection, no float, canonical integer/Decimal, Unicode-scalar key
sort, preserved arrays, exact escaping/separators/UTF-8. Projection digest
исключает собственное поле. DTO cap `524288`, script-safe cap `786432`:
equality accepted, `+1` rejected.

## 10. Public H2 GET/HEAD

```http
GET  /company-reports/{inn}/public-h2
HEAD /company-reports/{inn}/public-h2
```

Order: query → INN → Accept → rate limit → default-off/cohort → DB session →
exact binding/report/snapshot/DTO/digest. Matrix: `200`, query/INN `422`,
disabled `404`, not found `404`, pending/failed/not-eligible `409`, corrupt
projection `500`, method `405`, Accept `406`, rate limit `429`. All responses
use no-store/nosniff/noindex headers. HEAD shares selection/status/headers but
has empty body.

Read precedence:

1. exact active H2 composite assignment;
2. exact staged H2 composite pointer;
3. exact durable H2 lifecycle head;
4. safe v1/v2 legacy preview только если нет H2 head и вообще нет v3 report;
5. exact lifecycle error.

Active/staged H2 pin с unresolved narrative всегда `report_not_eligible`.
Pending/failed/finalized state берётся только из report, указанного exact head.
Multiple presentation/history rows не участвуют в latest-selection. Corrupt
active/staged/head binding terminal и не fallback-ит. Generic latest v3 запрещён.
GET/HEAD выполняет SELECT только: no provider/FNS/Gateway/AI, queue/worker,
signals/scoring, creation, refresh, publication или DML.

## 11. Normative persistence

Reports/jobs receive immutable profile/contract/generation; jobs receive fence.
Backfill accepts historical `1|2` only as H1 generation 0; unknown aborts.
DB constraints bind H1 to v1/v2/gen0 and H2 to v3/gen>0 while retaining
one-active-job-per-subject.

Presentation имеет composite unique key:

```text
(presentation_id, subject_id, report_id,
 presentation_contract, rollout_config_generation)
```

Он является FK target для `company_report_h2_lifecycle_heads`.

H2 lifecycle head:

```text
subject_id PRIMARY KEY
presentation_id
report_id
presentation_contract = company_public_h2_v1
rollout_config_generation > 0
head_generation > 0
changed_at
```

Composite FK запрещает cross-subject/report/contract/generation head.

Pins используют primary key
`(subject_id, contract_version, generation)` и exact report/version/hash/path/
indexability/lastmod.

H1 pin содержит H1 publication policy и запрещает H2-only leaves.

H2 pin iteration-20 foundation содержит:

```text
projection_digest: null
narrative_binding_status: literal "unresolved"
narrative_binding_kind: null
narrative_binding_key: null
chart_facts_version
chart_facts_hash
evidence_registry_version
publication_policy_version
indexable: false
```

Iteration 20 не создаёт resolved H2 pin. Nullable opaque narrative columns
резервируют schema surface, но не доказывают relation. Полный artifact relation/join
принадлежит iteration 21.

Staged pointer и assignment используют exact composite pin FK и требуют
subject equality. Generic `pin_id` не заменяет composite binding.

Iteration-20 CAS полностью реализует H1 activation/rollback foundation.
Попытка CAS на H2 pin с unresolved/missing narrative отклоняется до изменения
assignment/journal. Эта итерация не заявляет complete H2 narrative join или H2
CAS eligibility. No H2 assignment создаётся.

Journal append-only фиксирует subject, expected old generation, new assignment
generation и exact composite pin.

## 12. H1 publication mirror и migration

H1 candidate SQL filters compatibility before per-subject latest. Successful
active H1 publication и same-generation immutable H1 pin are one caller-owned
transaction. Exact retry is idempotent; conflict raises and rolls back
publication/journal/batch item/pin. Helper не commits самостоятельно.

Append-only migration `0016_company_card_v2_foundation` follows `0015`. It
validates all active H1 rows before insertion and imports exact report/version/
hash/policy/path/indexable/lastmod at `batch_generation`. Paused/disabled rows
remain, but are not imported. Corrupt identity/hash/path/policy/generation or
unknown historical version aborts atomically. No H2 pin/pointer/assignment is
created.

Separate disposable DB scenarios prove clean-0015 upgrade, backfill/schema/
FK/check/indexes, valid import, paused/disabled, corrupt atomic failures,
unchanged revision/legacy rows after failure, no activation, 0016→0015
downgrade preservation, deterministic re-upgrade, post-upgrade atomic mirror,
cross-subject rejection и stale/concurrent CAS. Дополнительно обязательны:

- presentation composite key и lifecycle-head composite FK;
- first create, exact reuse и new-run head-generation transitions;
- two subjects cannot cross-bind presentation/head;
- several presentations/history rows resolve only through exact head;
- downgrade removes H2 head/pin foundation while preserving legacy rows.

## 13. Arbitration section 31

Shipped registry remains unverified and blocks before provider callback
construction/invocation (`callback_count=0`). Synthetic verified registry is
test-only. Collector enforces page 100/max 10/raw rows 1000, case 256 KiB,
basis 8 MiB, exact equality/+1 bounds, page provenance, total/offset/limit
drift, overlap/repetition/non-progress, provider error, exact processing order,
counters and reason precedence. Collection and calendar completeness differ.

Dedup uses case_id then id privately; identical rows collapse, conflicting key
removes prior candidate and is permanently excluded, distinct keys never dedup
by amount. Roles use exact target INN; any multi/other role is `other`. Dates,
aliases, visible number and HMAC/public ordinal follow section 31 and privacy
ADR. Visible number never falls back to internal case key. Natural/unknown
never get public name alias. Private key must be ≥32 bytes; missing/rotated key
fails closed. Public A1–A5 remain null regardless of fixture results.

## 14. Counterparty, privacy и Claims

Counterparty parser is manifest-driven for exact paths/types/caps. Public only:
approved names, INN/OGRN/KPP, valid dates and approved address/inaccuracy.
Status/form/capital/tax/activity/manager/owner/worker/authority remain null/
empty with limitations. Contacts and personal identifiers are discarded.

Private arbitration policy path-allows only internal case identity/full HMAC.
Public taint-aware policy rejects them, key ID, source/private/raw/provider
markers, opponent IDs/names, contacts, secrets and URLs across DTO, serialized
body, headers, logs and Claims. Legitimate named digests remain valid.

Claims uses exact `report_id`, raw version dispatch and validates final
lifecycle, profile/contract/generation, snapshot hash/report/subject/target/
counterparty identity. V3 exposes only debtor name/INN and never latest,
cohort/assignment or new finance/arbitration/hidden fields. V1/v2 semantics and
idempotency remain unchanged.

## 14.1. Обязательные named regressions

1. `test_company_report_repository_pending.py`:
   `test_lock_or_create_subject_for_update_two_subjects_has_no_cartesian_join`.

2. `test_company_report_repository_queries.py` и
   `tests/test_company_reports_api.py`:
   newer v3 `pending`, `failed`, `finalized` + older eligible H1; каждый H1
   status/latest response остаётся H1.

3. `test_company_report_public_h1_service.py` и
   `tests/test_company_report_public_h1_reads.py`:
   active publication outer join с missing/corrupt exact report terminally
   fails; resolver не fallback-ит на latest report.

4. `test_company_report_repository_queries.py` и
   `test_company_report_publications.py`:
   equal `generated_at`, inverted `created_at`; larger `id` wins.

5. `test_datanewton_provider_result.py`,
   `test_company_report_persistence_serialization.py`,
   `test_company_report_repository_privacy.py`,
   `test_datanewton_probe_files.py`:
   lexical manifest отсутствует в model dump, every snapshot, dataset/provider
   journal, probe metadata/artifact и captured logs.

## 15. Acceptance

`READY` requires closure of all ten original blocker groups; full DTO/CJSON,
H1 shadow, lifecycle/HTTP/side-effect, composite persistence/CAS/atomic mirror,
migration, full fence, arbitration, counterparty/privacy/Claims matrices;
Product unit, Targeted/Full PostgreSQL with zero skips, Gateway, web lint/test/
build, compileall и diff-check; and independent `VERDICT: READY`. Otherwise
iteration remains blocked and commit/push are forbidden.

Дополнительно `READY` требует:

- v1 finance policy rejected in basis/snapshot/Chart Facts/PublicFinanceMoney;
- no finalized/latest query orders by `created_at`;
- public-H2 uses exact lifecycle head, not generic latest;
- all H2 pins remain unresolved/noindex and cannot be assigned;
- no reclaim path and no fence generation above 1;
- all five named regression groups pass.
