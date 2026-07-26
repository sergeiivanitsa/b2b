# Итерация 13 — Claims handoff из CompanyReport

ID: `13`
Slug: `claims-handoff`
Ветка: `feat/iteration-13-claims-handoff`

## 1. Цель

Связать авторизованную страницу компании с существующим Claims flow так, чтобы
реквизиты должника, уже подтверждённые immutable `CompanyReport`, не требовали
повторного ручного ввода.

Итерация переиспользует существующие Claims API, persistence, edit-token
access, frontend-форму, extraction и генерацию претензии. Новый Claims-сервис,
параллельная модель дела или генератор не создаются.

Уточнение пользователя имеет приоритет над более широким текстом roadmap
iteration 13:

- scoring, signals, warnings, AI explanation и recommended next step не
  передаются в Claims и не сохраняются там;
- score и `insufficient_data` не управляют доступностью CTA;
- итерация не добавляет юридическое заключение, сопровождение, оплату или
  автоматическую отправку претензии.

## 2. Архитектурное решение

Добавляются два endpoint внутри существующего public Claims router:

```http
GET  /claims/handoff/company-reports/{report_id}
POST /claims/handoff/company-reports/{report_id}
```

Оба endpoint требуют существующую Product API cookie-session и ту же роль, что
CompanyReport API:

```python
require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_MEMBER)
```

Existing superadmin bypass сохраняется.

Текущая модель `CompanyReport` не имеет tenant/company ownership FK: отчёты
доступны глобально активным участникам согласно существующей role-based policy.
Итерация не выдумывает новую tenant-привязку. Handoff не расширяет текущий
доступ: anonymous/inactive получает `401`, пользователь без допустимой роли —
`403`. После создания Claim продолжает защищаться существующим
`claim_id + X-Claim-Edit-Token`.

## 3. Trusted preflight

`GET /claims/handoff/company-reports/{report_id}` не создаёт Claim и не
изменяет БД.

Backend самостоятельно:

1. Загружает точный `CompanyReportRecord` по UUID и соответствующий
   `CompanyReportSubject` по `record.subject_id`.
2. Различает missing, pending, failed и отсутствие пригодной identity.
3. Для finalized snapshot создаёт независимую копию и проверяет
   `calculate_company_report_snapshot_hash(snapshot)` против сохранённого
   `record.snapshot_hash`.
4. Только после успешной hash-проверки десериализует snapshot существующим
   `company_report_from_snapshot()`.
5. Fail-closed проверяет точное соответствие snapshot записи:
   - `snapshot.report_id == record.id`;
   - `snapshot.report_version == record.report_version`;
   - `snapshot.status.value == record.lifecycle_status`;
   - normalized `snapshot.target_identifier ==
     subject.normalized_identifier`;
   - normalized `snapshot.counterparty.inn ==
     subject.normalized_identifier`.
6. Формирует allowlist projection только из verified normalized
   `counterparty`.

Snapshot с корректным собственным hash, но принадлежащий другой записи или
subject, не является trusted. Он не даёт prefill и завершается безопасной
ошибкой без раскрытия содержимого.

Текущая Claims `normalized_data` поддерживает для должника только:

- `debtor_name`;
- `debtor_inn`.

Поэтому ОГРН, КПП, адрес и статус организации в iteration 13 не переносятся и
новые debt-party поля не добавляются.

Response для пригодного `complete` или `partial` report:

```json
{
  "report_id": "00000000-0000-0000-0000-000000000000",
  "availability": "available",
  "reason": null,
  "prefill": {
    "debtor_name": "ООО «Должник»",
    "debtor_inn": "7700000000"
  },
  "prefilled_fields": ["debtor_inn", "debtor_name"]
}
```

Для известного `pending`, `failed` или finalized report без достоверной
identity возвращается безопасный manual fallback:

```json
{
  "report_id": "00000000-0000-0000-0000-000000000000",
  "availability": "manual_required",
  "reason": "report_pending",
  "prefill": null,
  "prefilled_fields": []
}
```

Разрешённые reasons: `report_pending`, `report_failed`,
`identity_unavailable`.

Неизвестный UUID возвращает безопасный `404 company_report_not_found`. Corrupt
snapshot, hash mismatch, identity mismatch, swapped snapshot и DB failure
обрабатываются fail-closed без выдачи report contents; frontend разрешает
перейти к обычной ручной форме.

## 4. Создание linked Claim

`POST /claims/handoff/company-reports/{report_id}` — единственная точка
создания handoff draft. Переход, preflight, refresh и просмотр страницы ничего
не создают.

Request:

```http
Idempotency-Key: <opaque client command key>
Content-Type: application/json
```

```json
{"input_text":"Описание долга, введённое пользователем"}
```

Request model использует `extra="forbid"` и не принимает client-provided name,
INN, address, status, score или source metadata.

Перед insert backend повторно выполняет trusted resolution report. Он создаёт
обычный `Claim` через существующий repository, записывает server-derived
`debtor_name`/`debtor_inn` в существующий `normalized_data_json`, возвращает
существующий edit-token contract и добавляет safe audit event только с report
UUID и allowlisted именами полей.

Если report больше не пригоден для prefill, endpoint возвращает
`409 company_report_prefill_unavailable` и не создаёт Claim. Пользователь может
явно продолжить через неизменённый `POST /claims`.

Обычный `POST /claims` остаётся обратно совместимым и не требует auth, report
ID или idempotency header.

## 5. Idempotency и actor scope

Linked create требует canonical `Idempotency-Key`. Backend не хранит raw key.

Command digest и deterministic edit capability вычисляются разными
domain-separated HMAC inputs, каждый из которых привязан к:

- `current_user.id`;
- exact `report_id`;
- canonical idempotency key.

Концептуальный контракт:

```text
command_digest =
  HMAC(secret,
       "claim-handoff:idempotency:v1\0"
       + current_user.id + "\0"
       + report_id + "\0"
       + canonical_key)

raw_edit_capability =
  HMAC(secret,
       "claim-handoff:edit:v1\0"
       + current_user.id + "\0"
       + report_id + "\0"
       + canonical_key)
```

`raw_edit_capability` затем защищается существующим
`hash_claim_edit_token()` перед записью в `edit_token_hash`. Конкретное
безопасное binary/text encoding детерминировано и покрыто test vectors; domain
separators никогда не переиспользуются.

При lookup существующей строки backend:

1. Вычисляет digest заново из authenticated `current_user.id`, path
   `report_id` и canonical key.
2. Ищет Claim только по этому actor-scoped digest.
3. Проверяет `source_company_report_id == report_id`.
4. Проверяет exact normalized `input_text`.
5. Только после всех проверок возвращает тот же Claim и детерминированную edit
   capability с `reused=true`.

Успешный lookup по HMAC digest подтверждает actor scope: digest другого actor
не совпадает. Report/input mismatch возвращает безопасный
`409 idempotency_key_reused` и не раскрывает существующий Claim или edit
capability.

Одинаковый raw key у двух разных авторизованных пользователей создаёт два
независимых actor-scoped draft, если оба пользователя имеют доступ к report по
существующей CompanyReport policy. Их command digests и edit capabilities
различаются. Если второй пользователь не проходит report authorization, запрос
завершается `401/403` до lookup/create. Cross-user key никогда не
переиспользует и не раскрывает чужой Claim.

Concurrent requests одного actor с одинаковыми report/key/input разрешаются
unique constraint + savepoint/re-read и создают ровно один Claim и один набор
creation events.

Frontend синхронно блокирует повторный submit, отключает CTA во время запроса и
сохраняет pending handoff key в `sessionStorage`, чтобы network retry/refresh
повторял ту же команду.

## 6. Persistence и связь

Migration `0015_claims_company_report_handoff` добавляет в `claims`:

| Column | Contract |
|---|---|
| `source_company_report_id` | nullable UUID FK → `company_reports.id`, `ON DELETE SET NULL`, index |
| `handoff_idempotency_key_hash` | nullable `VARCHAR(64)`, unique |

Nullable FK связывает Claim с точным immutable source snapshot. Новый отчёт по
тому же ИНН получает другой UUID и не меняет существующий Claim.
`ON DELETE SET NULL` оставляет Claim работоспособным, поскольку фактические
debtor fields уже сохранены в `normalized_data_json`.

Claim API возвращает nullable `source_company_report_id`. Он не возвращает
snapshot, scoring, signals, provider journal или internal IDs.

Никакие raw payload, provider metadata, scoring/signals/AI data и факты самого
требования в linkage/event не сохраняются.

## 7. Extraction и ручное подтверждение

При первом existing extraction server-prefilled `debtor_name` и `debtor_inn`
сохраняются при merge и не заменяются AI extraction result. Остальные сведения
требования извлекаются существующим flow.

После открытия step 2 пользователь может исправить debtor fields обычным
существующим `PATCH /claims/{id}`. Это считается явным пользовательским
редактированием, а не trusted report prefill. Повторный GET/refresh возвращает
сохранённые пользовательские значения.

Сумма, основание, договор, даты, просрочка, поставка/услуги, документы,
частичные платежи, неустойка и юридическая квалификация никогда не выводятся из
CompanyReport.

## 8. Frontend flow

Company page показывает основной CTA «Перейти к взысканию» и пояснение «Данные
должника уже заполнены — останется указать основание и сумму долга».

Для complete/identity-sufficient partial report переход имеет только:

```text
/claims?report_id=<uuid>
```

Company name, INN, address, score, signals и AI через URL/location state не
передаются.

Для pending, failed, missing и transport-error state CTA ведёт в обычный
`/claims` с безопасным in-memory пояснением о ручном заполнении. CTA не зависит
от score.

Step 1:

- валидирует UUID query;
- выполняет authenticated preflight;
- показывает trusted prefill summary либо manual fallback;
- не создаёт Claim до submit формы;
- linked submit вызывает handoff POST;
- manual submit использует существующий `POST /claims`;
- после create сохраняет `claim_id`, edit token, source report ID и
  idempotency key в существующей session storage и запускает existing
  extraction.

Step 2:

- восстанавливается существующим GET Claim;
- показывает заметку, что debtor fields исходно заполнены из CompanyReport и
  требуют проверки;
- разрешает редактирование;
- при наличии source UUID повторный safe preflight восстанавливает backlink на
  страницу компании;
- ошибка backlink/prefill не блокирует ручную работу с Claim.

Matching saved source draft предлагается продолжить, а повторная навигация сама
Claim не создаёт.

## 9. Состояния и ошибки

Обязательное поведение:

- complete и partial с verified identity — trusted prefill;
- partial без verified counterparty identity — manual;
- pending/failed/missing/corrupt — manual fallback, без invented facts;
- anonymous direct handoff URL — no trusted prefill, existing manual Claims
  доступен;
- `401/403/404/409/503/network` — безопасное сообщение и retry/manual action;
- Claims API unavailable — форма остаётся доступной, submit показывает
  retryable error;
- refresh step 1 повторяет только preflight;
- refresh step 2 восстанавливает existing Claim;
- double click/retry не создаёт duplicate;
- пользовательские debtor edits сохраняются;
- source report replacement не меняет Claim.

## 10. Accessibility и privacy

Loading/error/fallback messages используют `aria-live="polite"`. Prefilled
inputs имеют текстовый source hint, не только цвет. Кнопки имеют accessible
names, visible focus и disabled/loading state. Backlink является обычной
keyboard-accessible ссылкой.

URL, responses, Claim JSON и events не содержат raw payload, address,
provider/worker IDs, scoring internals, signals, AI output, secrets или internal
errors.

## 11. Out of scope

Новые Claims-service/domain, новые Claims party fields, scoring/AI changes,
SEO, publication, CRM, payment, document workflow beyond existing Claims,
legal opinion, auto-send, provider/OpenAI calls in tests и изменение
publication policy.

## 12. Acceptance criteria

### Owner-approved baseline verification

The PostgreSQL regression baseline was verified against exact commit
`db06e3dffc8ff597297693b610c71ad16f8028a0` in a detached temporary worktree.
Both runs used `postgres:16-alpine`, a freshly migrated disposable database,
the same environment shape, a 900-second timeout, and:

```text
python -m pytest services/product_api/tests -q
```

Results:

- base: `107 passed, 30 failed`, 97 warnings, 203.15 seconds;
- iteration 13: `113 passed, 30 failed`, 112 warnings, 207.89 seconds;
- the six additional passing tests are exactly the iteration 13 PostgreSQL
  handoff and migration tests;
- failed node IDs are identical 30/30;
- normalized failure messages are identical 30/30; normalization removed only
  run timestamps permitted by the owner-approved comparison;
- no setup or fixture failures occurred;
- no new iteration 13 failure exists.

The matching baseline failed node IDs are:

- `tests/test_admin_claims.py::test_admin_claim_status_transition_send_and_files`
- `tests/test_company_admin_detach.py::test_detach_admin_can_detach_member`
- `tests/test_company_admin_detach.py::test_detach_email_can_be_invited_to_another_company`
- `tests/test_company_admin_detach.py::test_detach_owner_success_user_hidden_from_stats_and_history_kept`
- `tests/test_company_admin_summary.py::test_company_summary_contract_and_math`
- `tests/test_company_admin_summary.py::test_company_summary_rbac_owner_admin_allowed_member_forbidden`
- `tests/test_invite_invariants.py::test_company_invite_reject_active_invite_other_org`
- `tests/test_invite_invariants.py::test_company_invite_reject_user_with_company`
- `tests/test_invite_invariants.py::test_company_invite_saves_profile_fields_and_list_returns_them`
- `tests/test_invite_invariants.py::test_invite_accept_creates_user_with_profile_and_joined_company_at`
- `tests/test_invite_invariants.py::test_invite_accept_updates_existing_user_without_company_profile`
- `tests/test_last_n.py::test_last_n_trimming`
- `tests/test_public_claims_preview.py::test_generate_and_get_preview_ip_ai_keeps_line2_consistent_and_line3_none`
- `tests/test_public_claims_preview.py::test_generate_and_get_preview_keep_line3_consistent_with_write_path_contract[all_caps_female_structured_inflect]`
- `tests/test_public_claims_preview.py::test_generate_and_get_preview_keep_line3_consistent_with_write_path_contract[all_caps_male_structured_inflect]`
- `tests/test_public_claims_preview.py::test_generate_and_get_preview_keep_line3_consistent_with_write_path_contract[all_caps_structured_normalize_only]`
- `tests/test_public_claims_preview.py::test_generate_and_get_preview_keep_line3_consistent_with_write_path_contract[hyphen_raw_fallback]`
- `tests/test_public_claims_preview.py::test_generate_and_get_preview_keep_line3_consistent_with_write_path_contract[initials_raw_fallback]`
- `tests/test_public_claims_preview.py::test_generate_and_get_preview_keep_line3_consistent_with_write_path_contract[ivanitsa_female_all_caps_override]`
- `tests/test_public_claims_preview.py::test_generate_and_get_preview_keep_line3_consistent_with_write_path_contract[ivanitsa_male_all_caps_override]`
- `tests/test_public_claims_preview.py::test_generate_and_get_preview_keep_line3_consistent_with_write_path_contract[latin_raw_fallback]`
- `tests/test_public_claims_preview.py::test_generate_and_get_preview_keep_line3_consistent_with_write_path_contract[not_three_words_raw_fallback]`
- `tests/test_public_claims_preview.py::test_generate_and_get_preview_legal_entity_ai_keeps_line3_consistent`
- `tests/test_public_claims_preview.py::test_generate_preview_and_get_preview`
- `tests/test_public_claims_preview.py::test_get_preview_upgrades_legacy_broken_header_with_emergency_bridge_without_mutation`
- `tests/test_public_claims_preview.py::test_get_preview_upgrades_legacy_header_full_raw_without_mutating_stored_payload`
- `tests/test_public_claims_preview.py::test_get_preview_upgrades_legacy_header_with_normalized_fallback_without_mutation`
- `tests/test_rbac.py::test_rbac_roles`
- `tests/test_superadmin_hardening.py::test_admin_company_admins_conflict_active_invite_409`
- `tests/test_superadmin_hardening.py::test_admin_company_admins_missing_company_404_not_500`

Failure signatures remain confined to the existing baseline categories:
HTTP status mismatches, the existing user role/company check-constraint
violation, preview mocks missing the existing `reference_date` argument, and
legacy JSON/text persistence mismatches. The owner-approved waiver applies
only to these exact 30 failures.

- CTA доступен независимо от score и безопасно работает во всех report states.
- Navigation/preflight не создают Claim.
- Backend доверяет только report UUID и самостоятельно строит debtor prefill.
- Client-provided debtor fields в linked create запрещены.
- Linked submit создаёт обычный Claim только после explicit action.
- Repeat/concurrent command возвращает один Claim и одну edit capability.
- Handoff digest и edit capability domain-separated и actor/report scoped.
- Cross-user replay одинакового key не возвращает чужой Claim/edit capability;
  при разрешённом report access создаётся независимый draft.
- Snapshot с пересчитанным корректным hash, но перенесённый из другой record,
  subject или report UUID, не используется для prefill.
- Manual Claims flow остаётся совместимым.
- Refresh, editing и backlink работают.
- FK остаётся привязан к исходному immutable report при появлении нового
  report.
- Claims persistence не содержит raw/scoring/signals/AI data.
- Tests, migration validation, build, lint, compileall и independent review
  проходят.
