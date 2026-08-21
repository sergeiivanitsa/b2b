# Итерация 17 — Backend публичной проекции H1 CompanyReport

ID: `17`
Slug: `company-report-h1-backend`
Contract: `company_public_h1_v1`
Branch: `feat/iteration-17-company-report-h1-backend`
Base commit: `f4776595375a485732fff96053eb9362194f203a`
Статус спецификации: `approved`
Зависимость: merged iteration 16

## 1. Цель

Реализовать вычисляемую strict projection `company_public_h1_v1` и публичный
anonymous read-only endpoint:

```http
GET /company-reports/{inn}/public-h1
```

Projection строится только из одного детерминированно выбранного immutable
CompanyReport snapshot. Active publication pin имеет приоритет над любым новым
run. При отсутствии active pin API может показать latest eligible
`complete|partial` snapshot как `latest_unpublished` и всегда с
`indexable=false`.

Новые snapshots используют `report_version="2"` и отдельный
`optional_datasets` envelope. Snapshot v1 остаётся читаемым без rewrite и
backfill. Required lifecycle, completeness и freshness по-прежнему определяют
ровно три datasets:

```text
counterparty
finance
arbitration
```

В репозитории нет утверждённых evidence/operational artifacts для finance unit,
`tax_info`, `bankruptcy`, owners или public manager identity. Live evidence в
этой итерации запрещён. Поэтому все такие возможности fail closed:
не выполняются новые optional provider calls, facts не строятся, coverage
получает `not_requested`, а projection — безопасные allowlisted limitations.

## 2. Source of truth

Нормативные источники:

- `AGENTS.md`;
- `README.md`;
- `docs/development/ROADMAP.md`;
- `docs/development/DEVFLOW_STATE.yaml`;
- `docs/development/iterations/iteration-16-company-report-h1-public-contract.md`;
- завершённые контракты CompanyReport iterations 7–15;
- фактический код и тесты на base commit
  `f4776595375a485732fff96053eb9362194f203a`.

При конфликте этой спецификации с утверждённым iteration 16 runtime не
изменяется до нового documentation review.

## 3. Scope

В scope:

1. Snapshot v2 и legacy-safe parser/writer.
2. Единая константа текущей writer version для enqueue, aggregate и finalize.
3. Отдельный `optional_datasets` envelope, не участвующий в required lifecycle.
4. Provider-neutral optional fact models, недоступные runtime без evidence
   gate.
5. Версионированный evidence registry с explicit enabled/disabled state.
6. Сохранение role-specific arbitration parties в новых v2 snapshots и pure
   exact-ID public attribution.
7. Strict DTO `company_public_h1_v1`.
8. Fixed date policy `checked_date_msk_v1` в `Europe/Moscow`.
9. Unit-independent finance YoY; абсолютные finance amounts запрещены.
10. Единый service-level resolver active-pin/latest-eligible.
11. Anonymous read-only API с exact error mapping и zero side effects.
12. Перевод anonymous SSR canonical page на ту же H1 projection.
13. Published SSR/API parity и unpublished API projection.
14. Existing publication registry, canonical redirect и sitemap filtering через
    ту же pin validation.
15. Safe fixtures, unit и PostgreSQL integration tests.
16. Legacy CompanyReport, publication, Claims handoff, signals, scoring и AI
    compatibility tests.

## 4. Out of scope

- React/TypeScript H1 presentation и iteration 18.
- Изменение plain-INN SPA flow.
- Refresh button, TTL refresh или automatic report creation на H1 read path.
- Deployment, nginx, production migration execution и publication rollout.
- Production/live DataNewton probes.
- Paid AI или новые Gateway calls.
- Новые `tax_info`, `bankruptcy`, FSSP или batch-cards runtime calls.
- Изменение tariff, quota, pagination, retry, timeout или cache policy.
- OWNER_BLOCK или MANAGER_BLOCK activation для новых CompanyReport runs.
- Контакты, phone, email, website и social links.
- FSSP и indirect debt flags.
- Score, verdict, signals, probability, rating и AI explanation в H1 DTO/HTML.
- Изменение Claims legal semantics.
- Новая DB table, DB column, backfill или Alembic migration.
- Изменение roadmap.

## 5. Неподвижные инварианты

### 5.1. Required lifecycle

Required datasets — фиксированный ordered tuple:

```python
("counterparty", "finance", "arbitration")
```

Только они определяют lifecycle:

| Available required | Status | Completeness |
| ---: | --- | --- |
| 3 | `complete` | `3/3` |
| 1–2 | `partial` | `1/3` или `2/3` |
| 0 | `failed` | `0/3` |

`CompanyReport.datasets` содержит только required datasets. Любое число и любой
status optional datasets не меняют:

- `CompanyReport.status`;
- `CompanyReportCompleteness`;
- `ReportFreshness`;
- `usable_for_public_page`;
- `usable_for_future_scoring`;
- signals/scoring inputs.

### 5.2. Read path

Public H1 read:

- не вызывает provider;
- не вызывает AI/Gateway;
- не вызывает `evaluate_publication` или `evaluate_report_ephemerally`;
- не извлекает signals и не вычисляет scoring/verdict;
- не запускает worker;
- не enqueue-ит job;
- не вызывает existing POST;
- не обновляет report, publication, journal или timestamps;
- не выполняет flush/commit;
- не переписывает snapshot;
- не использует текущее время как fact date.

JSON API, canonical SSR и sitemap используют только persisted publication
outcome, immutable stored snapshot, pure integrity validation и pure
`company_public_h1_v1` builder. Для каждого из трёх read surfaces точный
ceiling равен:

```text
provider=0
evaluate_publication=0
evaluate_report_ephemerally=0
signals=0
scoring/verdict=0
AI/explanation=0
jobs=0
DB writes=0
```

Persisted `policy_version`, `sufficiency_status`, `indexable` и publication
status разрешено валидировать, но запрещено пересчитывать на read path. Tests
для API, SSR и sitemap ставят fail-if-called doubles на оба publication
evaluator, provider, signals, scoring, AI, jobs и persistence writes.

### 5.3. Missing semantics

`missing`, `null`, empty, `false`, `0`, `not_found`, `not_requested`, `partial`,
`failed` и `conflict` не взаимозаменяемы.

Неполученный dataset или field запрещено превращать в:

- числовой ноль;
- отсутствие долга;
- отсутствие дела или публикации;
- действующий/ликвидированный статус;
- положительный либо отрицательный business verdict.

## 6. Evidence registry

Runtime использует immutable registry с explicit version, evidence references,
schema state, operational state и public behavior. Gate нельзя активировать
env-переменной без tracked evidence artifact и code review.

| Capability | Schema evidence на base commit | Operational gate | Runtime state iteration 17 | Conservative behavior |
| --- | --- | --- | --- | --- |
| Counterparty core identity/requisites | Existing safe synthetic fixture, normalizer и tests iterations 4–16 | Existing required call | `enabled` | Разрешены только уже нормализованные core fields. |
| Counterparty address mapping | Existing safe fixture и normalizer path | Новый filter не утверждён для CompanyReport worker | `read_existing_only` | Stored block используется только при `block_status=available`; worker не расширяет filters. |
| Finance normalized series | Existing safe fixture и normalizer | Existing required call | `enabled_without_unit` | Разрешён только unit-independent YoY. |
| Finance absolute values | `finance_unit_evidence_v1` отсутствует | Not applicable until schema pass | `disabled` | `money=null`, `unit_policy_version=null`, safe limitation. |
| Arbitration cards/parties | Existing safe fixture и normalizer | Existing required call | `enabled` | Exact typed attribution строится только из сохранённых identifiers. |
| Tax facts | `tax_info_schema_v1` отсутствует | Optional-call approval отсутствует | `disabled` | Dataset key absent, block `null`, coverage `not_requested`. |
| Bankruptcy facts | `bankruptcy_schema_v1` отсутствует | Optional-call approval отсутствует | `disabled` | Dataset key absent, block `null`, coverage `not_requested`. |
| Public manager identity | Raw path известен, `management_privacy_v1` отсутствует | MANAGER_BLOCK не включается | `disabled` | Managers отсутствуют; privacy limitation. |
| Owners | `owner_schema_v1` и privacy classification отсутствуют | OWNER_BLOCK approval отсутствует | `disabled` | Owners отсутствуют; schema/privacy/operational limitations. |
| Contacts | Prohibited contract | Prohibited | `disabled` | Никогда не входят в DTO, HTML или evidence fixture. |
| FSSP | Нет eligible H1 source | Optional call prohibited | `disabled` | Никогда не входит в DTO/HTML. |

Registry содержит только safe metadata:

```text
gate_id
registry_version
schema_state
operational_state
evidence_paths
public_behavior
```

Он не содержит raw provider payload, API keys, endpoints с credential data,
production identifiers или arbitrary external text.

Candidate tax/bankruptcy/owner fields и candidate finance unit policy могут
существовать как strict provider-neutral types, но ни normalizer, ни call, ни
public block для них в этой итерации не активируется.

## 7. Snapshot v2

### 7.1. Current writer version

Одна константа задаёт writer version:

```text
CURRENT_COMPANY_REPORT_VERSION = "2"
```

Её обязаны использовать:

- pending record enqueue;
- lower-level `create_pending_report` default;
- `build_company_report`;
- finalized model;
- ORM record/snapshot identity check.

Несовпадение pending ORM version и finalized report version — hard state
conflict. Writer не делает silent coercion.

Один lifecycle имеет одну immutable version:

```text
enqueued == claimed == builder output == raw discriminator ==
parsed snapshot == ORM report_version == finalized publication version
```

При mixed-version rollout reused active pending v1 не передаётся v2
builder. Claim/precondition сравнивает pending version с current writer
version до provider boundary; mismatch безопасно terminally fails
job/report с provider calls `0`. После этого обычный lifecycle может
создать свежий v2 run; silent upgrade v1 pending запрещён.

### 7.2. Domain topology

```text
CompanyReport:
  report_version: "1" | "2"
  ...
  datasets: dict[str, DatasetReport]              # required only
  optional_datasets: dict[str, DatasetReport] = {}
  tax_info: TaxInfoFacts | null = null
  bankruptcy: BankruptcyFacts | null = null
```

Allowed optional dataset keys:

```text
tax_info
bankruptcy
```

В iteration 17 writer всегда сохраняет:

```json
{
  "optional_datasets": {},
  "tax_info": null,
  "bankruptcy": null
}
```

поскольку gates disabled.

Provider-neutral models не утверждают raw mappings. Они могут быть
инстанцированы только будущим gate-enabled normalizer:

```text
TaxInfoFacts:
  source
  has_unpaid_debts
  as_of_date
  records
  warnings

BankruptcyFacts:
  source
  total
  returned
  limit
  offset
  publications
  warnings
```

### 7.3. v1 compatibility

До любой Pydantic model/union/default parser обязан проверить raw
discriminator в таком порядке:

1. raw value — dictionary и имеет key `report_version`;
2. `type(raw["report_version"]) is str`;
3. value равно exact `"1"` или `"2"`;
4. missing, `null`, boolean, number и unknown string reject до model defaults;
5. canonical hash считается из untouched raw dictionary до parse;
6. parser dispatches exact versioned model и повторно сверяет parsed
   discriminator.

Model default никогда не классифицирует snapshot без explicit raw version.
Missing, non-string и unknown raw discriminator — integrity failures.

Snapshot v1:

- принимается без новых keys;
- интерпретируется как
  `optional_datasets={}`, `tax_info=null`, `bankruptcy=null`;
- не переписывается;
- не backfill-ится;
- проверяется hash от original stored JSON до Pydantic default expansion;
- при сериализации восстановленной v1 model v2-only default keys опускаются,
  чтобы canonical v1 hash не менялся.

Snapshot v2:

- обязан явно содержать v2 envelope и nullable optional fact fields;
- сериализуется детерминированно;
- writer не создаёт v1 после rollout.

Legacy `GET /company-reports/{inn}` принимает обе версии. Его response topology
не получает optional H1 facts; меняется только enum `report_version` с `"1"` на
`"1" | "2"`.

Legacy explicit AI opt-in также остаётся совместимым:
`ExplanationInputEnvelope.report_version` принимает exact
`Literal["1", "2"]`. Это не расширяет explanation facts: optional H1 datasets,
public limitations/links и другие v2-only public fields не входят в
AI envelope/prompt. Existing eligibility, privacy и allowlists не меняются.

### 7.4. Persistence behavior

Existing columns достаточны:

- `company_reports.report_version` — `VARCHAR(16)`;
- `normalized_snapshot` — JSON;
- `snapshot_hash` — existing hash field.

Optional facts сохраняются только внутри immutable normalized snapshot.
`company_report_datasets` остаётся required-only. Новых dataset rows для
disabled optional datasets нет.

DB migration не требуется. Если implementation обнаружит DB constraint,
который не принимает `"2"`, это blocker: migration нельзя придумывать внутри
итерации.

### 7.5. Publication finalization integrity

`finalize_batch_claim` до publication policy evaluation и до `_upsert_publication`
fail-closed сверяет:

- batch subject/report ID/report version с ORM report;
- ORM subject с normalized subject;
- ORM status exact `complete|partial`;
- batch expected hash, stored hash и canonical hash untouched raw snapshot;
- strict raw discriminator и parsed version;
- snapshot `report_id`, `report_version`, `status`, `generated_at` с ORM;
- snapshot target INN и `counterparty.inn` с normalized subject INN.

Любое mismatch даёт safe terminal state conflict, не запускает policy
evaluation/upsert, не создаёт pin и не заменяет existing pin.

## 8. Arbitration exact public attribution

### 8.1. New v2 normalized evidence

Новые v2 case facts аддитивно сохраняют:

```text
applicants
creditors
debtors
interested_persons
third_parties
other_parties
party_collections_valid
malformed_entry_count at ArbitrationFacts level
```

Existing `plaintiffs`, `respondents`, `company_roles`, legacy summaries и
signals/scoring behavior не удаляются. Public H1 не доверяет legacy
`company_roles` как exact attribution evidence.

v1 snapshots без новых role-specific collections остаются читаемыми.
Plaintiff/respondent attribution может быть выполнена из сохранённых lists.
Роли, для которых v1 не сохранил party records, остаются `unattributed` с
`legacy_arbitration_role_detail_unavailable`.

### 8.2. Typed target identity

Target identity:

```text
target_inn = exact 10/12-digit counterparty INN
target_ogrn = exact form-compatible 13/15-digit OGRN/OGRNIP or null
```

Правила party match:

1. Party only INN: match только exact `party.inn == target_inn`.
2. Party only OGRN: match только exact `party.ogrn == target_ogrn`.
3. Party has both identifiers: target обязан иметь оба; совпасть должны оба.
4. One matches and one conflicts: `identity_conflict`, no role.
5. Party has both, target only one: `target_identity_incomplete`, no role.
6. Name-only match: no role.
7. Cross-type comparison запрещён.
8. Невалидный identifier не нормализуется в совпадение.

### 8.3. One case — one bucket

| Exact matches | Public bucket |
| --- | --- |
| One of `plaintiff/respondent/applicant/creditor/debtor` | Same role |
| One `third_party/interested_person/provider-other` | `other` |
| More than one exact role | `other` |
| No exact role, conflict, incomplete target or name-only | `unattributed` |
| No parseable case identity or invalid party collection | `malformed` |

Invariant:

```text
sum(role_counts) + unattributed_count == normalized_case_count
normalized_case_count + malformed_count == returned_cases
```

Один case учитывается ровно один раз.

### 8.4. Claim amounts

Amount aggregate разрешён только когда:

- attributed role ровно `plaintiff` или `respondent`;
- `claim_amount` присутствует;
- source currency является non-empty safe scalar.

No currency inference. Unknown/missing currency исключает amount и даёт
limitation. Amounts группируются по `(role, exact source currency)`, используют
`Decimal`, никогда `float`.

Display policy не заменяет currency символом:

```text
exact_decimal + " " + source_currency
```

Decimal separator для display — запятая, trailing insignificant zeros
удаляются; exact DTO string остаётся canonical Decimal string.

### 8.5. Selection and ordering

`selected_cases` содержит не более 10 normalized cases с `case_number`.

Порядок:

```text
date_update desc nulls last
date_start desc nulls last
case_number asc
```

Status/result counts считаются только для normalized cases. Slice counts нельзя
экстраполировать на `total_cases`.

## 9. Finance behavior

### 9.1. Absolute values

`finance_unit_evidence_v1` отсутствует. Поэтому:

```text
FinanceMetric.money = null
FinanceBlock.unit_policy_version = null
```

Запрещены:

- `thousand_rub`;
- scaling `* 1000`;
- RUB display;
- любые absolute finance amounts в DTO/HTML;
- изменение persisted `FinanceFacts.unit="provider_units_unknown"`.

### 9.2. YoY

Unit-independent YoY разрешён только для утверждённых metric IDs iteration 16
и одной unambiguous normalized indicator series:

```text
total_assets
non_current_assets
current_assets
inventories
accounts_receivable
cash_and_equivalents
equity
long_term_liabilities
short_term_liabilities
short_term_borrowings
accounts_payable
revenue
cost_of_sales
gross_profit
operating_profit
profit_before_tax
net_profit
net_cash_flow
cash_at_start
cash_at_end
```

Formula:

```text
(current - previous) / abs(previous) * 100
```

Условия:

- explicit current year и previous year;
- `previous_year == current_year - 1`;
- оба exact values присутствуют в одной unambiguous series;
- `previous != 0`;
- duplicate/conflicting series не выбирается случайно.

DTO:

```text
exact_percent: canonical Decimal string
display_value: sign + one decimal + "%"
current_year
previous_year
formula_version: "finance_yoy_v1"
```

Display округляется `ROUND_HALF_UP`. Missing/zero previous скрывает YoY.
`FinanceBlock` равен `null`, если ни один YoY не прошёл условия.

Metrics сортируются по фиксированному allowlist выше, затем `year desc`.

## 10. Identity, requisites and address

### 10.1. Identity gate

Eligible public identity требует:

- report lifecycle `complete|partial`;
- available counterparty dataset;
- snapshot target INN == subject INN == request INN;
- `counterparty.inn` exact match;
- non-empty safe `full_name`;
- no control-character corruption.

No full name — snapshot ineligible. `legal_short_name` optional.
`display_name = legal_short_name or legal_full_name`.

Names use pure versioned `legal_name_display_v1`: deterministic whitespace,
iteration-16-approved display casing and quotes presentation. Source value
остаётся в immutable snapshot; policy не переводит, не добавляет legal
tokens и не угадывает unknown shapes.

### 10.2. Status

`counterparty_status_v1` — explicit default-deny versioned mapping:

- reviewed source code/text mapping может выдать mapped `status_code` и
  Russian `status_label`;
- unknown code/text скрывает оба поля и даёт
  `identity_status_mapping_unknown`;
- raw status code/text passthrough запрещён;
- backend не выводит status из boolean alone;
- boolean/status/date conflict скрывает categorical label и добавляет
  `identity_status_conflict`;
- `status_effective_at=null`, пока отдельный approved effective-date source
  отсутствует.

Публичная формулировка в SSR всегда связывает status с immutable report date,
а не с текущим моментом.

### 10.3. Requisites

Allowed:

- `legal_form` только из explicit default-deny `legal_form_opf_v1` mapping;
- form-compatible OGRN/OGRNIP;
- KPP only for 10-digit legal-entity INN;
- registration/dissolved dates;
- region;
- address when stored block status is `available`.

Address with `is_inaccuracy=true` остаётся видимым только с explicit
limitation. `not_requested`, empty or invalid address block не превращается в
пустой адресный факт.
Неизвестный OPF скрывается и даёт `legal_form_mapping_unknown`; raw OPF
passthrough запрещён.

Charter capital, tax modes, contacts and arbitrary counterparty blocks не
входят в H1.

## 11. Optional tax, bankruptcy and management

В iteration 17:

```text
blocks.tax = null
blocks.bankruptcy = null
blocks.management = null
coverage.tax.state = not_requested
coverage.bankruptcy.state = not_requested
coverage.management.state = not_requested
```

Mandatory limitations:

| Block | Code | Safe message |
| --- | --- | --- |
| `tax` | `tax_schema_gate_not_passed` | `Налоговые сведения не запрашивались: схема источника не подтверждена.` |
| `tax` | `tax_operational_gate_not_passed` | `Дополнительный запрос налоговых сведений не активирован.` |
| `bankruptcy` | `bankruptcy_schema_gate_not_passed` | `Сведения о банкротных публикациях не запрашивались: схема источника не подтверждена.` |
| `bankruptcy` | `bankruptcy_operational_gate_not_passed` | `Дополнительный запрос банкротных публикаций не активирован.` |
| `management` | `management_privacy_gate_not_passed` | `Персональные сведения о руководителях не публикуются без утверждённой privacy policy.` |
| `management` | `management_schema_gate_not_passed` | `Сведения о владельцах не публикуются: схема и семантика долей не подтверждены.` |
| `management` | `management_operational_gate_not_passed` | `Дополнительные блоки руководителей и владельцев не запрашивались.` |

Raw candidate tax/bankruptcy codes, owner shares, person identifiers и manager
INNFL не входят в serialized public response.

## 12. Resolver

### 12.1. Query phases and call ceiling

Resolver выполняет:

1. validation/normalization INN — zero DB calls on failure;
2. one publication lookup with outer-joined pinned report and subject;
3. if active publication exists, no report-history query;
4. only when active publication отсутствует — one ordered subject report
   history query.

DB SELECT ceiling:

| Path | Maximum SELECT executions |
| --- | ---: |
| Invalid INN/query rejection | 0 |
| Active publication | 1 |
| No active publication | 2 |

No write statement is permitted.

### 12.2. Active publication

Если publication status `active`, выбирается только pin.

Required equality:

```text
publication.subject_id == subject.id
publication.report_id == report.id
report.subject_id == subject.id
requested INN == subject.normalized_identifier
report.lifecycle_status in {"complete", "partial"}
report.normalized_snapshot is not null
hash(original snapshot) == report.snapshot_hash
hash(original snapshot) == publication.snapshot_hash
snapshot.report_id == report.id
snapshot.report_version == report.report_version
snapshot.status == report.lifecycle_status
snapshot.target_identifier == subject.normalized_identifier
snapshot.counterparty.inn == subject.normalized_identifier
snapshot.generated_at == report.generated_at
publication canonical path/slug/INN grammar is internally consistent
publication.policy_version is supported
```

Publication lookup заякорен на publication/subject и возвращает active
row даже при missing joined report. Такая row — invalid active pin, а не
absence of publication; latest fallback запрещён.

Existing publication sufficiency не пересчитывается. Resolver читает
persisted `policy_version`, `sufficiency_status`, `indexable` и publication
status, проверяет их supported combination и строит H1 pure projection.
`evaluate_publication` и `evaluate_report_ephemerally` на H1 read path не
вызываются. Structurally valid legacy pin может быть returned с
persisted `indexable=false`; corrupt, unsupported или unbuildable pin invalid.

Any corrupt, mismatched or unsupported active pin returns:

```text
500 public_projection_invalid
```

Resolver никогда не falls back с invalid active pin на latest report.

### 12.3. No active publication

Inactive/paused/disabled registry row не является pin. Resolver рассматривает
reports in deterministic order:

```text
created_at desc
id desc
```

Он выбирает первый snapshot, который:

- имеет lifecycle `complete|partial`;
- имеет stored snapshot/hash;
- проходит original hash check;
- парсится как v1/v2;
- совпадает с ORM record и subject;
- проходит exact identity gate;
- может построить strict H1 projection.

Newer failed, corrupt, identity-ineligible или otherwise unusable run
пропускается и не скрывает older eligible snapshot.

Результат:

```text
projection_scope = "latest_unpublished"
indexable = false
canonical_path = short-name-first deterministic path
```

Если eligible snapshot отсутствует, lifecycle classification определяется
последним run:

| Latest state | HTTP/code |
| --- | --- |
| No run | `404 company_report_not_found` |
| `pending` | `409 report_pending` |
| `failed` | `409 report_failed` |
| `complete|partial`, но ни один snapshot не eligible | `409 report_not_eligible` |

Older failed/ineligible history не подавляет текущий pending run. Ни один из
этих ответов не создаёт новый report. Только exact
`404 company_report_not_found` разрешает future plain-INN UI выполнить existing
POST. `409 report_pending` разрешает polling. Остальные `409` terminal для H1.

### 12.4. Canonical path

Published projection использует exact stored
`publication.canonical_path`. Existing path не пересчитывается из нового name
precedence.

Wrong-slug SSR redirect использует stored canonical path.

Latest unpublished path строится:

```text
safe legal_short_name
else legal_full_name
```

через existing deterministic `seo.canonical_path`. Slug не принимается как
source fact.

## 13. Public API

### 13.1. Route

```http
GET /company-reports/{inn}/public-h1
```

Properties:

- anonymous, без auth dependency;
- session cookie и Authorization header не меняют result;
- existing read IP rate limiter;
- strict response model;
- query surface отсутствует;
- duplicate и любой query parameter rejected до service call;
- no redirect.

### 13.2. Query rejection

Любой query parameter, включая duplicate, возвращает existing FastAPI
validation form:

```text
422 Unprocessable Entity
```

Resolver и DB не вызываются.

### 13.3. Errors

| Condition | HTTP | Detail code | Safe message |
| --- | ---: | --- | --- |
| Invalid INN | 400 | `invalid_inn` | `invalid INN` |
| No run | 404 | `company_report_not_found` | `company report not found` |
| Latest pending, no eligible snapshot | 409 | `report_pending` | `company report is pending` |
| Latest failed, no eligible snapshot | 409 | `report_failed` | `company report failed` |
| Final snapshot exists but no eligible projection | 409 | `report_not_eligible` | `company report is not eligible for public projection` |
| Invalid active pin/projection | 500 | `public_projection_invalid` | `public company projection is invalid` |
| Persistence unavailable | 503 | `company_report_unavailable` | `company report service is unavailable` |
| Read rate limit | 429 | `rate_limited` | `rate limit` |

JSON error envelope:

```json
{
  "detail": {
    "code": "report_pending",
    "message": "company report is pending"
  }
}
```

Arbitrary DB/provider exception text не возвращается и не логируется с
snapshot content.

### 13.4. Headers

H1 API JSON always returns:

```text
Cache-Control: no-store
X-Content-Type-Options: nosniff
X-Robots-Tag: noindex,follow
```

Эти три headers обязательны на success `200` и на каждом JSON
response `400`, `404`, `409`, `422`, `429`, `500` и `503`. Route использует
один H1 JSON success/error response factory; query/identifier rejection,
validation, rate-limit, typed domain и unexpected-safe errors возвращаются
через него. Установка headers только после successful service call
недостаточна.

`response.indexable` описывает canonical HTML publication, а не разрешение
индексировать JSON endpoint.

## 14. Exact DTO

### 14.1. Topology

```text
CompanyPublicH1Response:
  contract_version: Literal["company_public_h1_v1"]
  report_id: UUID
  report_version: Literal["1", "2"]
  projection_scope: Literal["published", "latest_unpublished"]
  canonical_path: string
  indexable: boolean
  checked_at: UTC datetime
  checked_date: ISO date
  checked_date_display: string
  identity: CompanyPublicIdentity
  block_order: PublicBlockId[]
  blocks: CompanyPublicBlocks
  coverage: PublicCoverageItem[6]
  sources: PublicSourceItem[]
  limitations: PublicLimitation[]
  actions: PublicAction[]
  breadcrumbs: PublicBreadcrumb[2]
  internal_links: PublicInternalLink[]
```

All models use `extra="forbid"`. Public DTO has no arbitrary fact dictionary.

### 14.2. Identity

```text
CompanyPublicIdentity:
  legal_full_name: string
  legal_short_name: string | null
  display_name: string
  inn: 10 or 12 ASCII digits
  status_code: string | null
  status_label: string | null
  status_effective_at: date | null
```

### 14.3. Blocks

`blocks` always serializes all keys:

```text
CompanyPublicBlocks:
  requisites: RequisitesBlock | null
  finance: FinanceBlock | null
  arbitration: ArbitrationBlock | null
  bankruptcy: BankruptcyBlock | null
  tax: TaxBlock | null
  management: ManagementBlock | null
```

In this iteration `bankruptcy`, `tax` and `management` are always `null`.

```text
RequisitesBlock:
  legal_form: string | null
  ogrn_or_ogrnip: string | null
  kpp: 9 ASCII digits | null
  registration_date: date | null
  dissolved_date: date | null
  region: PublicRegion | null
  legal_address: PublicAddress | null

PublicRegion:
  code: string | null
  name: string | null

PublicAddress:
  display_line: string
  postal_code: string | null
  country: string | null
  region: string | null
  city: string | null
  street: string | null
  house: string | null
  office: string | null
  is_inaccuracy: boolean | null
```

```text
FinanceBlock:
  unit_policy_version: string | null
  metrics: FinanceMetric[1..N]

FinanceMetric:
  metric_id: PublicFinanceMetricId
  year: integer
  money: PublicMoney | null
  yoy: PublicPercentChange | null

PublicMoney:
  source_decimal: Decimal string
  source_unit: Literal["thousand_rub"]
  rub_decimal: Decimal string
  display_value: string
  unit_policy_version: string

PublicPercentChange:
  exact_percent: Decimal string
  display_value: string
  current_year: integer
  previous_year: integer
  formula_version: Literal["finance_yoy_v1"]
```

Схема остаётся exact iteration 16. Runtime behavior при disabled
`finance_unit_evidence_v1` жёстче схемы: `unit_policy_version=null` и
`money=null` для каждого metric. `PublicMoney` обязан существовать
как strict reserved DTO, но его instance в iteration 17 не сериализуется.
Positive percent display имеет exact form `+29,1%` без пробела
перед `%`.

```text
ArbitrationBlock:
  total_cases: integer >= 0
  returned_cases: integer >= 0
  normalized_case_count: integer >= 0
  malformed_count: integer >= 0
  limit: integer >= 1
  offset: integer >= 0
  role_counts: ArbitrationRoleCounts
  unattributed_count: integer >= 0
  status_counts: ArbitrationStatusCounts
  result_counts: ArbitrationResultCounts
  claim_amounts: ArbitrationClaimAmount[]
  selected_cases: PublicArbitrationCase[0..10]
```

```text
ArbitrationRoleCounts:
  plaintiff: integer >= 0
  respondent: integer >= 0
  applicant: integer >= 0
  creditor: integer >= 0
  debtor: integer >= 0
  other: integer >= 0
```

```text
ArbitrationStatusCounts:
  open: integer >= 0
  completed: integer >= 0
  unknown: integer >= 0

ArbitrationResultCounts:
  satisfied_full: integer >= 0
  refused: integer >= 0
  returned: integer >= 0
  undefined: integer >= 0
  other: integer >= 0
```

```text
ArbitrationClaimAmount:
  role: Literal["plaintiff", "respondent"]
  currency: ISO-like ASCII source currency matching ^[A-Z][A-Z0-9_-]{2,15}$
  exact_decimal: Decimal string
  display_value: string

PublicArbitrationCase:
  case_number: string
  date_start: date | null
  date_update: date | null
  attributed_role:
    "plaintiff" | "respondent" | "applicant" | "creditor" |
    "debtor" | "other" | "unattributed"
  claim_amount: ArbitrationClaimAmount | null
```

Exact strict reserved iteration-16 schemas обязаны существовать:

```text
BankruptcyBlock:
  total: integer >= 0
  returned: integer >= 0
  limit: integer >= 1
  offset: integer >= 0
  typed_counts: BankruptcyTypedCounts
  publications: PublicBankruptcyPublication[]
  disclaimer: fixed allowlisted string

BankruptcyTypedCounts:
  debtor_intention: integer >= 0
  creditor_intention: integer >= 0
  unknown: integer >= 0

PublicBankruptcyPublication:
  safe_reference: string | null
  publication_date: ISO date | null
  kind: "debtor_intention" | "creditor_intention" | "unknown"
  message: allowlisted string
  participant_role: "debtor" | "creditor" | "other" | "unknown"

TaxBlock:
  unpaid_debt_indicator: boolean
  message: allowlisted string
  as_of_date: ISO date | null
  records: PublicTaxRecord[]

PublicTaxRecord:
  record_type: allowlisted string
  document_date: ISO date | null
  period: string | null
  amount: PublicMoney | null

ManagementBlock:
  managers: PublicManager[]
  owners: PublicOwner[]

PublicManager:
  name: string
  role: string
  appointed_at: ISO date | null
  is_inaccuracy: boolean | null

PublicOwner:
  name_or_org: string
  owner_type: "person" | "organization"
  organization_inn: 10 or 12 ASCII digits | null
  organization_ogrn: form-compatible OGRN | null
  share_percent_decimal: Decimal string | null
  share_display: string | null
  ownership_effective_at: ISO date | null
```

В iteration 17 runtime instances `bankruptcy`, `tax` и `management` равны
`null`; strict model topology не сужается из-за disabled gates.

### 14.4. Coverage

Coverage fixed order:

```text
requisites
finance
arbitration
bankruptcy
tax
management
```

```text
PublicCoverageItem:
  block_id: factual PublicBlockId
  dataset:
    "counterparty" | "finance" | "arbitration" |
    "bankruptcy" | "tax_info"
  state:
    "available" | "available_empty" | "not_found" |
    "not_requested" | "partial" | "failed" | "conflict"
  total: integer | null
  returned: integer | null
  limit: integer | null
  offset: integer | null
  limitation_codes: string[]
```

Mapping:

| Internal/runtime condition | Public coverage |
| --- | --- |
| Required dataset available, safe facts | `available` |
| Arbitration success with exact `total=0, returned=0` | `available_empty` |
| Arbitration `returned < total` or malformed records | `partial` |
| Provider explicit not found | `not_found` |
| Optional key absent/gate disabled | `not_requested` |
| Required transport/normalization error | `failed` |
| Field identity conflict | Dataset remains available; affected block/field limitation, or `conflict` when block cannot safely expose any fact |

Required report без eligible counterparty identity не достигает DTO.

### 14.5. Sources

Source order:

```text
counterparty
finance
arbitration
tax_info
bankruptcy
```

Только successful normalized source:

```text
PublicSourceItem:
  dataset
  received_at: UTC datetime
  effective_at: date | null
  period: string | null
  normalization_version: allowlisted string
```

Initial normalization-version allowlist:

```text
counterparty_normalizer_v1
finance_normalizer_v1
arbitration_normalizer_v1
arbitration_normalizer_v2
```

Emitted value обязан честно соответствовать stored snapshot; v1
не помечается v2 и не теряет source item.

Не включаются endpoint, response hash, request ID, status code, attempts,
duration, provider limit metadata или warning path.

### 14.6. Limitations

```text
PublicLimitation:
  code: allowlisted string
  block_id: PublicBlockId | null
  field_id: allowlisted field id | null
  message: safe allowlisted string
```

Допустимы только exact rows ниже. `null` означает absent
`field_id`; provider/exception text, identifiers и raw values в message
запрещены.

| code | block_id | field_id | exact message |
| --- | --- | --- | --- |
| `address_not_requested` | `requisites` | `requisites.legal_address` | `Юридический адрес не запрашивался в сохранённом отчёте.` |
| `address_marked_inaccurate` | `requisites` | `requisites.legal_address` | `Источник пометил юридический адрес как недостоверный.` |
| `legal_form_mapping_unknown` | `requisites` | `requisites.legal_form` | `Организационно-правовая форма не отображена: значение отсутствует в утверждённом справочнике.` |
| `identity_status_mapping_unknown` | `identity_status` | `identity.status_label` | `Статус компании не отображён: значение отсутствует в утверждённом справочнике.` |
| `identity_status_conflict` | `identity_status` | `identity.status_label` | `Статус компании не отображён из-за противоречивых сохранённых сведений.` |
| `finance_unit_evidence_not_passed` | `finance` | `finance.metrics.money` | `Денежные значения не показаны: единица источника не подтверждена сохранёнными доказательствами.` |
| `finance_series_conflict` | `finance` | `finance.metrics.yoy` | `Изменение показателя не рассчитано из-за неоднозначного сопоставления периодов.` |
| `finance_dataset_not_found` | `finance` | null | `Финансовые сведения не найдены в области ответа источника; нулевые значения не предполагаются.` |
| `finance_dataset_failed` | `finance` | null | `Финансовые сведения недоступны из-за ошибки получения или нормализации.` |
| `arbitration_identity_conflict` | `arbitration` | `arbitration.selected_cases.attributed_role` | `Роль компании в отдельных делах не определена из-за противоречивых идентификаторов.` |
| `arbitration_target_identity_incomplete` | `arbitration` | `arbitration.selected_cases.attributed_role` | `Роль компании в отдельных делах не определена из-за неполных идентификаторов.` |
| `arbitration_unknown_currency` | `arbitration` | `arbitration.claim_amounts` | `Часть сумм требований не показана: валюта источника не распознана.` |
| `arbitration_partial_slice` | `arbitration` | null | `Показана только сохранённая часть арбитражных сведений.` |
| `arbitration_malformed_records` | `arbitration` | null | `Часть арбитражных записей пропущена из-за некорректной структуры.` |
| `legacy_arbitration_role_detail_unavailable` | `arbitration` | `arbitration.selected_cases.attributed_role` | `Для отчёта версии 1 детализация роли по отдельным делам недоступна.` |
| `arbitration_dataset_not_found` | `arbitration` | null | `Арбитражные сведения не найдены в области ответа источника; отсутствие дел не предполагается.` |
| `arbitration_dataset_failed` | `arbitration` | null | `Арбитражные сведения недоступны из-за ошибки получения или нормализации.` |
| `tax_schema_gate_not_passed` | `tax` | null | `Налоговые сведения не запрашивались: схема источника не подтверждена.` |
| `tax_operational_gate_not_passed` | `tax` | null | `Дополнительный запрос налоговых сведений не активирован.` |
| `bankruptcy_schema_gate_not_passed` | `bankruptcy` | null | `Сведения о банкротных публикациях не запрашивались: схема источника не подтверждена.` |
| `bankruptcy_operational_gate_not_passed` | `bankruptcy` | null | `Дополнительный запрос банкротных публикаций не активирован.` |
| `management_privacy_gate_not_passed` | `management` | null | `Персональные сведения о руководителях не публикуются без утверждённой privacy policy.` |
| `management_schema_gate_not_passed` | `management` | null | `Сведения о владельцах не публикуются: схема и семантика долей не подтверждены.` |
| `management_operational_gate_not_passed` | `management` | null | `Дополнительные блоки руководителей и владельцев не запрашивались.` |

Allowed `field_id` values — только values из таблицы. Required finance
и arbitration `failed|not_found` обязаны дать both coverage state и
matching fixed limitation.

Deduplication и ascending lexical serialization используют exact tuple:

```text
(block_id, field_id-or-empty-string, code)
```

Page block order/index для limitations не используется.

### 14.7. Actions, breadcrumbs and links

Fixed actions order:

```json
[
  {
    "action_id": "check_another_company",
    "label": "Проверить другую компанию",
    "path": "/"
  },
  {
    "action_id": "prepare_claim",
    "label": "Подготовить претензию",
    "path": "/claims?report_id={displayed_report_id}"
  }
]
```

`prepare_claim` использует только `response.report_id`. Никакой latest lookup
для action не выполняется.

Breadcrumbs:

```json
[
  {"label": "Главная", "path": "/"},
  {"label": "{identity.display_name}", "path": "{canonical_path}"}
]
```

`internal_links=[]` в iteration 17: repository не содержит отдельного
identifier-resolved registry для дочерних H1 pages.

Strict reserved topology:

```text
PublicInternalLink:
  label: fixed allowlisted string
  path: identifier-resolved same-origin absolute path
  relation: allowlisted relation
```

## 15. Block order

Full allowlist:

```text
breadcrumbs
identity_status
known_summary
in_page_navigation
coverage_checked_at
requisites
finance
arbitration
bankruptcy
tax
management
sources_limitations
neutral_actions
internal_links
```

Construction:

1. `breadcrumbs`;
2. `identity_status`;
3. `known_summary`;
4. `in_page_navigation` only if at least two factual blocks are non-null;
5. `coverage_checked_at`;
6. non-null factual blocks in fixed order;
7. `sources_limitations`;
8. `neutral_actions`;
9. `internal_links` only when links non-empty.

`requisites` после identity gate всегда strict object, даже если его optional
fields all null. Other factual blocks use `null` when invisible.

## 16. Date and deterministic serialization

### 16.1. Checked date

```text
checked_at = report.generated_at
```

It must equal ORM `report.generated_at` for selected snapshot.

Policy:

```text
checked_date_msk_v1
timezone = Europe/Moscow
```

Backend returns:

- exact UTC ISO timestamp;
- Moscow calendar `checked_date`;
- Russian display:
  `"{day} {genitive_month} {year} года"`.

Boundary tests cover UTC instants immediately before and after Moscow midnight.
Server timezone, process locale, browser locale and current read time are
irrelevant.

### 16.2. Ordering

- DTO keys follow model definition.
- Coverage and sources use fixed orders.
- Finance metrics: metric allowlist, then year desc.
- Cases: defined date/number order.
- Claim amounts: role order `plaintiff`, `respondent`, then currency.
- Limitations: ascending lexical `(block_id, field_id-or-empty-string, code)`.
- Actions and breadcrumbs: fixed.
- Internal links: relation, path, label.

Same snapshot, publication metadata, registry version and contract version
produce byte-equivalent canonical JSON.

## 17. SSR, visibility and indexability

Anonymous canonical SSR calls the same resolver and renders the returned H1 DTO.
SSR читает persisted publication outcome и не пересчитывает publication
policy, signals или scoring. Для него действует exact zero-call/write
ceiling из § 5.2.

### 17.1. Published page

Valid active pin:

- exact slug: `200`;
- wrong valid slug: `301` to stored canonical path;
- `robots=index,follow` only if response `indexable=true`;
- otherwise `robots=noindex,follow`;
- HTML and API use the same report ID, checked date, identity, blocks, coverage,
  sources, limitations and actions.

Renderer consumes DTO only. It does not read raw `CompanyReport` separately.

HTML root exposes safe parity attributes:

```text
data-contract-version
data-report-id
data-report-version
data-projection-scope
```

No serialized raw JSON state or script is embedded.

### 17.2. Unpublished page

If resolver returns `latest_unpublished`:

- API returns `200`, `indexable=false`;
- canonical anonymous SSR route remains `404`, `noindex,follow`;
- it is absent from sitemap;
- iteration 18 SPA may consume the API projection.

### 17.3. Invalid active pin

- API: `500 public_projection_invalid`;
- SSR: `500 Internal error`, `noindex,follow`;
- sitemap excludes it;
- no latest fallback.

### 17.4. Sitemap

Sitemap continues to include only active, indexable publications that pass the
same pin integrity and H1 build validation. It uses persisted
`published_lastmod`; GET does not update it.
Sitemap uses the pure preloaded-row integrity/H1 predicate, never
`evaluate_publication`/`evaluate_report_ephemerally`, and has the exact
zero-call/write ceiling from § 5.2.

## 18. Privacy and forbidden fields

Recursive H1 DTO/HTML prohibition:

```text
raw_payload
headers
authorization
api_key
apikey
provider_limit_metadata
request_id
endpoint
response_hash
provider_status_code
http_status_code
result_status
result_status_code
attempts
duration_ms
worker_token
lease_expires_at
safe_error_type
raw_role
raw_status
raw_result_type
source_paths
requested_filters
factual_basis
evaluation_basis
signals
scoring
score
verdict
probability
ai_explanation
innfl
contacts
phone
email
website
social
fssp
```

Legitimate mapped `CompanyPublicIdentity.status_code` is explicitly allowed;
generic recursive rejection must not reject it. Forbidden status names above
refer only to unapproved transport/provider/raw-result fields.

Arbitration public cases do not expose:

- internal case ID;
- party names;
- party identifiers;
- documents;
- KAD link;
- raw result/status;
- arbitrary dispute data.

Manager person identity and owners are absent. Company identity and
organization requisites remain allowed only through strict fields.

## 19. Backward compatibility

Must remain unchanged:

- `POST /company-reports`;
- `GET /company-reports/{inn}/status`;
- `GET /company-reports/{inn}` semantics and fields, except additive support for
  `report_version="2"`;
- explicit AI opt-in behavior on legacy GET;
- worker fencing/job lifecycle;
- provider call ceiling of exactly three required method calls;
- signals/scoring evaluation contracts;
- Claims handoff exact `report_id` validation;
- publication batch/control/journal schema and behavior;
- canonical SPA/plain-INN flow;
- Gateway, Web UI and nginx behavior.

`CompanyReportPublicSnapshot` requires an explicit raw version and reads both
v1/v2 without rewriting v1. `ExplanationInputEnvelope` accepts v1/v2 but keeps
the existing fact/prompt allowlist; no optional H1 facts enter AI input.

v1 snapshots remain immutable and hash-stable. Existing publication pins to v1
remain eligible if they satisfy H1 identity/integrity requirements.

## 20. Call ceilings and side effects

### Worker per new report

```text
fetch_counterparty: 1
fetch_finance: 1
fetch_arbitration_cases: 1
fetch_tax_info: 0
fetch_bankruptcy: 0
fetch_fssp: 0
fetch_batch_cards: 0
AI: 0
```

No new counterparty filter is activated by iteration 17.

### Public read

```text
provider calls: 0
AI/Gateway calls: 0
evaluate_publication calls: 0
evaluate_report_ephemerally calls: 0
signals calls: 0
scoring/verdict calls: 0
job enqueue: 0
worker calls: 0
DB writes: 0
publication writes: 0
Claims writes: 0
DB SELECTs: 0/1/2 according to resolver table
```

## 21. Test requirements

### 21.1. Snapshot and lifecycle unit tests

- explicit raw `"1"`/`"2"` dispatches exact versioned model;
- missing, null, boolean, numeric and unknown raw `report_version` reject before
  Pydantic defaults;
- canonical hash is calculated from untouched raw JSON before parse;
- v1 fixture parses with empty optional envelope and nullable optional facts;
- original v1 hash remains unchanged after parse/serialize;
- no v1 rewrite;
- v2 round-trip/hash deterministic;
- writer creates only v2;
- enqueue/build/finalize versions align;
- version mismatch is hard failure;
- reused pending v1 is rejected before provider boundary; provider fail-if-called;
- v1/v2 explanation envelopes pass while optional H1 facts remain excluded;
- required dataset key set remains exactly three;
- optional dataset available/not-found/failed combinations do not affect
  status/completeness/freshness/usability;
- optional source timestamps do not enter required freshness.

### 21.2. Evidence tests

- registry contains every declared gate once;
- disabled gates cannot be activated from environment;
- evidence paths exist for enabled entries;
- tax/bankruptcy/owners/manager privacy/finance unit remain disabled;
- no optional provider method is invoked;
- candidate fact objects never enter DTO under disabled registry.

### 21.3. Arbitration tests

Table-driven cases:

- only matching INN;
- only matching OGRN;
- both matching;
- one matching/one conflicting;
- party-both/target-one;
- name-only;
- single primary role;
- multiple primary roles;
- exact other role;
- no role;
- invalid party collection;
- missing case identity;
- v1 missing role detail;
- mixed/unknown currency;
- amount only for exact plaintiff/respondent;
- each normalized case in one bucket;
- selected-case ordering and limit 10;
- `total/returned/normalized/malformed` invariants.

### 21.4. Finance/date/DTO tests

- absolute finance values absent;
- unit policy null;
- exact iteration-16 nullable money/YoY and all reserved DTO topology;
- INN/KPP ASCII constraints, non-negative arbitration counts and ISO-like
  source currency;
- adjacent-year YoY;
- negative previous denominator uses `abs`;
- previous zero/missing suppresses YoY;
- conflicting series suppresses YoY;
- Decimal `ROUND_HALF_UP`;
- exact positive display `+29,1%`;
- Moscow midnight boundary;
- server/browser locale independence;
- strict extra rejection;
- all six block keys;
- fixed block/coverage/source/action orders;
- honest `arbitration_normalizer_v1|v2` source versions;
- exact limitation code/block/field/message table, required dataset failure
  limitations and lexical `(block_id, field_id, code)` order;
- versioned legal-name/OPF/status mapping and unknown-value hiding;
- public identity `status_code` accepted while transport result-status rejected;
- recursive forbidden-key scan;
- deterministic canonical JSON.

### 21.5. Resolver unit tests

- valid active pin;
- unsupported publication policy;
- subject/report/snapshot/report ID mismatches;
- hash mismatch;
- generated-at mismatch;
- canonical registry mismatch;
- active invalid pin never falls back;
- no active pin selects latest eligible;
- newer failed skipped;
- newer ineligible skipped;
- latest pending/failed/not-eligible/no-run classification;
- active SELECT ceiling 1;
- fallback SELECT ceiling 2;
- invalid input ceiling 0;
- no session flush/commit/write.

### 21.6. HTTP and SSR unit tests

- anonymous access;
- cookies/Authorization do not change result;
- any/duplicate query returns 422 and no service call;
- invalid INN 400;
- all exact 404/409/500/503 codes;
- rate limit 429;
- exact noindex/no-store/nosniff headers on `200` and every JSON
  `400|404|409|422|429|500|503`, including exception/error paths;
- published SSR/API report ID and checked date parity;
- wrong-slug redirect uses stored canonical;
- latest unpublished API 200/noindex and SSR 404;
- invalid active pin SSR 500;
- renderer uses DTO only;
- Claims action contains displayed report ID;
- API, SSR and sitemap separately fail if either publication evaluator,
  provider, signals, scoring/verdict, AI, jobs or writes are called.

### 21.7. PostgreSQL integration

- v1 and v2 stored records are readable;
- latest eligible skips newer failed/unusable records;
- active pin wins over newer final report;
- corrupt active pin does not fallback;
- controlled republish atomically switches SSR/API to new report;
- publication hash/path/subject integrity;
- endpoint performs no mutations;
- published_lastmod unchanged on read;
- sitemap excludes noindex/invalid/unpublished;
- legacy GET/status/create continue to work;
- Claims handoff resolves both v1 and v2 exact report IDs.

### 21.8. Publication finalization integrity

Unit and PostgreSQL integration tests independently cover batch/ORM subject,
report ID, report version and hash mismatch; invalid ORM status; missing,
non-string and unknown raw version; snapshot/ORM ID, version, status and
generated-at mismatch; target-INN and counterparty-INN mismatch. Every negative
case asserts no policy evaluation/upsert, no new pin and no replacement of an
existing pin.

## 22. Migration applicability

Alembic migration: **not applicable**.

Rationale:

- existing `report_version VARCHAR(16)` stores `"2"`;
- snapshot is existing JSON;
- no new table/column/index/constraint;
- optional data remains inside immutable snapshot;
- publication registry schema remains unchanged.

No production or unknown database may be accessed during implementation.

## 23. Risks and controls

| Risk | Control |
| --- | --- |
| Old snapshot hash changes through default expansion | Hash original JSON; version-aware v1 serializer omits v2 defaults. |
| Enqueue says v1 while aggregate says v2 | One current-version constant and mismatch tests. |
| Optional failures alter lifecycle | Required-key validator and exhaustive optional-state tests. |
| Invalid active pin silently shows latest | Active branch terminates with 500; history query not executed. |
| New failed run hides older usable report | Ordered eligibility scan skips failed/unusable. |
| Finance values presented in unknown units | `money=null`; finance gate disabled. |
| Tax/bankruptcy mapping guessed | No normalizer and zero calls; `not_requested`. |
| Owner/manager PII disclosed | Privacy/schema gates disabled; recursive forbidden scan. |
| Arbitration double count | Pure exact typed attribution and sum invariant. |
| v1 lacks all party collections | Conservative unattributed result plus limitation. |
| API gets indexed | JSON always `X-Robots-Tag: noindex,follow`. |
| SSR/API choose different snapshots | One resolver and DTO-driven renderer. |
| Claim uses latest rather than shown report | Action path constructed from response `report_id`. |
| Rollback binary cannot read v2 | Deployment is out of scope; any future rollout must retain a v2-capable reader in rollback image. No DB downgrade/backfill is permitted. |

## 24. Acceptance criteria

- [x] Independent plan review returned `CHANGES_REQUIRED`; the single permitted
      corrective pass closed every finding and root verification approved the
      corrected specification/plan.
- [ ] Evidence registry is explicit and all unproven gates disabled.
- [ ] New reports persist v2; v1 remains hash-stable and readable.
- [ ] Raw `report_version` is required and checked before model defaults.
- [ ] Explanation accepts v1/v2 without admitting optional H1 facts.
- [ ] Required lifecycle remains exactly three-dataset.
- [ ] No tax/bankruptcy/owner/manager provider expansion or public facts.
- [ ] Finance absolute values are absent.
- [ ] Arbitration public counts use exact typed one-bucket attribution.
- [ ] Active publication pin wins and invalid pin never falls back.
- [ ] Publication finalization validates the complete batch/ORM/snapshot
      integrity matrix before evaluation/upsert.
- [ ] Latest unpublished projection skips newer failed/unusable runs and is
      noindex.
- [ ] API is anonymous, rejects all query parameters and has no side effects.
- [ ] API, SSR and sitemap call neither publication evaluator and have zero
      provider/signals/scoring/AI/job/write activity.
- [ ] Success and every specified JSON error status carry all three H1 headers.
- [ ] Published SSR and API use the same DTO/report ID.
- [ ] Claims action uses displayed report ID.
- [ ] Legacy endpoints, v1 snapshots, publication registry and Claims handoff
      remain compatible.
- [ ] No migration, deploy, nginx, live probe or paid AI work appears in diff.
- [ ] Targeted and required regression checks pass.
- [ ] `git diff --check` passes.
- [ ] Independent code review returns `VERDICT: READY`.

## 25. Blockers

Блокирующего schema/migration решения на base commit нет.

Finance unit, tax, bankruptcy, owners, public manager identity и optional calls
остаются intentionally disabled gates, а не blockers для выпуска conservative
H1 backend.

All iteration-16 contract requirements and corrective-review findings are
closed by this specification. No frontend, migration, deploy, live evidence,
production DB/provider probe or paid-AI action is authorized.

## 26. User-authorized unblock pass

This section is the approved corrective delta for the separate unblock pass.
It supersedes any less strict test wording above without changing the H1
product contract. Before the implementer starts, iteration 17 is moved from
`blocked` to `implementing`; its feature branch and base remain unchanged, and
`ROADMAP.md` is not modified.

### 26.1. Exact read ceilings and zero side effects

API, canonical SSR and sitemap are tested independently through the real H1
resolver/validator and read-only persistence path.

| Surface | Scenario | SELECT count |
| --- | --- | ---: |
| API | valid active pin | 1 |
| API | no active pin, latest eligible | 2 |
| API | invalid INN or any query parameter | 0 |
| SSR | valid active page | 1 |
| SSR | wrong-slug redirect for valid active pin | 1 |
| SSR | corrupt active pin, fail closed 500 | 1 |
| SSR | no active pin and latest report is unpublished/eligible | 2, then 404 |
| SSR | invalid company key or any query parameter | 0 |
| Sitemap index | valid request | 1 |
| Sitemap chunk | valid request | 1 |
| Sitemap | any query parameter or malformed chunk path/index | 0 |

Every scenario installs fail-if-called guards at defining modules and actual
call-site aliases for all of these capability families:

1. `seo.evaluate_publication` and
   `ephemeral_evaluation.evaluate_report_ephemerally`;
2. every `DataNewtonClient.fetch_*` method;
3. signals evaluation;
4. scoring and its verdict result;
5. AI explanation and both Gateway chat aliases;
6. enqueue, claim, heartbeat, complete, fail and reconcile job mutations;
7. `run_one_claimed_job`, `heartbeat_supervisor` and `run_worker`;
8. publication control, create/state, claim/relinquish, finalize and process
   operations;
9. ORM `add`, `add_all`, `delete`, `merge`, `flush` and `commit`;
10. every SQL statement that is not an SQLAlchemy `Select`.

The guarded session accepts only `Select`. Driver `BEGIN/ROLLBACK` around a
SELECT is not a business write. Each surface asserts that every prohibited
counter is zero; replacing the real resolver with a stub does not satisfy the
matrix.

### 26.2. Arbitration completion matrix

The table in section 21.3 additionally covers these exact cases:

| Input | Public result |
| --- | --- |
| matching party plus incomplete party in one case | whole case `unattributed`, incomplete limitation, no amount |
| matching party plus conflicting party in one case | whole case `unattributed`, conflict limitation, no amount |
| exact applicant with amount | applicant bucket; no case or aggregate amount |
| exact creditor with amount | creditor bucket; no case or aggregate amount |
| exact debtor with amount | debtor bucket; no case or aggregate amount |

Conflict or incomplete identity anywhere in a case overrides otherwise
matching roles. A party container is invalid if it is not a list or any list
member is not a record; the whole case is malformed. Status-count and
result-count sums each equal `normalized_case_count`, in addition to role and
returned-count invariants. Sorting remains `date_update desc nulls last`, then
`date_start desc nulls last`, then `case_number asc`, limited to ten.

### 26.3. Reserved DTO structural usability

Disabled evidence gates are enforced by the H1 root response and builder, not
by unconditional validators that make reserved leaf models uninhabitable.
Detached strict-model tests cover `PublicMoney`, bankruptcy publication and
block, `PublicTaxRecord`, tax block, manager, owner, non-empty management block
and internal link.

- Approved bankruptcy disclaimer/messages and the two tax boolean messages
  retain their exact catalogs.
- Catalogs not enumerated in iteration 16 (`record_type`, manager `role`, link
  label/relation) accept only safe non-empty structural strings in detached
  tests; this does not approve runtime mappings.
- Internal-link paths are same-origin absolute paths.
- `ManagementBlock` rejects both lists empty.
- The iteration-17 root response still rejects non-null bankruptcy, tax and
  management blocks and non-empty internal links.
- Runtime optional blocks stay null, coverage stays `not_requested`, exact
  gate limitations remain, and optional provider calls remain zero.

### 26.4. Publication finalization integrity

Every unit row calls the real `finalize_batch_claim`; helper-only validation is
insufficient. Each row proves evaluator and upsert are unreachable.

PostgreSQL-representable rows include claim/batch/policy mismatch; a valid
alternate subject mismatch; item/ORM and raw/ORM hash mismatch; non-object
snapshot; missing stored hash; pending/failed lifecycle; unknown report
version; missing generated time; DB-valid wrong subject identifier; all raw
version discriminator failures; parsed report ID/version/status/generated time
mismatch; target mismatch; missing counterparty; and counterparty INN mismatch.

Rows made impossible by exact-key lookup, FK, NOT NULL or CHECK constraints are
unit-only and explicitly identify that protection. Tests never disable, defer
or rewrite PostgreSQL constraints.

Every PostgreSQL row begins with exactly one sentinel active publication.
Before and after finalization the exact row count and every mapped column are
compared: `id`, `subject_id`, `report_id`, `status`, `canonical_slug`,
`canonical_path`, `snapshot_hash`, `policy_version`, `batch_generation`,
`indexable`, `sufficiency_status`, `published_lastmod`, `published_at`,
`disabled_at` and `audited_at`. Count remains one and the tuples are identical;
only the mismatched candidate item/journal may terminate as
`failed/state_conflict`.

### 26.5. Narrow web UI lint unblock

This pass may repair only the observed 14 ESLint errors and one warning:

- move Auth and ClaimsAdmin contexts out of component files;
- remove unused mock callback parameters;
- replace synchronous effect-derived/reset state in the queue and typewriter
  hooks with collision-safe keyed/derived state and callback transitions;
- initialize the missing-token confirm state without an effect setter;
- replace the `return` in `SuperadminPage` `finally` with an equivalent guard.

ESLint rules and suppressions are not changed. Timing, same-run rerender,
restart, pause/resume, reduced-motion and cleanup behavior are covered. No H1
React page, route, styling or other iteration-18 work is authorized.

UI commands run against this exact worktree. Dependency provenance is proved
either by offline `npm ci` using the unchanged lockfile, or by a temporary
Windows junction after SHA-256 equality of both `package.json` and
`package-lock.json`, successful `npm ls --all` in both locations, and verified
reparse target cleanup. Package manifests and lockfiles remain unchanged.

### 26.6. Tracked disposable PostgreSQL runbook

`scripts/run-iteration17-postgres-tests.ps1` supports `Targeted` and `Full`.
Each mode writes separate ignored JUnit evidence and requires tests greater
than zero with failures, errors and skips all equal to zero. Full mode also
proves collection and execution of the self-managed Alembic and CompanyReport
migration tests.

The script uses only a locally present `postgres:16-alpine` image with
`--pull=never`, a generated `iteration17-pg-*` name, exact run labels, captured
container ID, loopback-only dynamic port, tmpfs data and no named volume.
`DATABASE_URL` and `TEST_DATABASE_URL` target its synthetic application DB;
`TEST_POSTGRES_ADMIN_URL` targets `/postgres` on the same host, port and
credentials. It runs bounded readiness and existing `alembic upgrade head`.
Cleanup may force-remove only after exact ID, generated name and both labels
are proven; otherwise it stops safely.

### 26.7. Unblock acceptance

- [ ] Exact API/SSR/sitemap SELECT ceilings pass.
- [ ] All canonical and call-site capability guards remain zero and guarded
      sessions observe `Select` only.
- [ ] Arbitration whole-case conflict/incomplete and non-plaintiff/respondent
      amount cases pass with all count invariants.
- [ ] Reserved leaves, including `PublicTaxRecord`, are usable; empty
      management and root optional emission reject.
- [ ] Every finalizer row is classified representable or unit-only; sentinel
      count and all mapped columns are identical.
- [ ] Exact-worktree lint reports zero errors and warnings; targeted/full UI
      tests and build pass.
- [ ] Targeted and Full disposable PostgreSQL JUnit files each have tests and
      zero failures/errors/skips; Full includes migration tests.
- [ ] No migration, roadmap, package/lock, provider, deploy or iteration-18
      scope enters the diff.

### 26.8. Full-gate compatibility boundary

Because the PostgreSQL suite was previously non-executable in the local
environment, the first Full run may reveal stale integration fixtures or an
existing production path that violates an already-applied database or routing
invariant. This pass may correct only failures actually observed in that Full
JUnit run and required to reach section 26.7 acceptance. Such corrections must
be individually classified as test compatibility or production behavior,
remain in the exact corrective manifest, and must not change the H1 contract,
schema, provider calls, deployment or iteration-18 frontend.
