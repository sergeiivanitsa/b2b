# Finance unit evidence v3 — pre-live plan

Artifact ID: `company_card_v2_finance_unit_evidence_v3_plan`

Policy under test: `datanewton_finance_thousand_rub_v2`

Plan date: `2026-08-24`

State: `PRE-LIVE PLAN — NO CALLS EXECUTED`

## 1. Цель и границы

Следующий live-pass проверяет новую policy на заранее определённой выборке, а
не повторно оценивает уже увиденные C01–C03. Pass не реализует iteration 20,
не меняет runtime, не обращается к production DB, не создаёт/обновляет отчёты,
не вызывает AI и не публикует raw provider data.

Перед первым запросом создаются opaque session ID, private mapping и полный
список компаний. После первого DataNewton response список и правила не
меняются.

## 2. Выборка и бюджет

- Ровно пять новых российских юридических лиц, отсутствующих в C01–C03.
- Выбор до просмотра их DataNewton finance values.
- Нейтральные критерии: юридическое лицо, доступный официальный ГИР БО
  документ, наличие обеих требуемых форм и двух общих доступных периодов.
  Line-level presence и значения FNS не просматриваются до фиксации cohort.
- Запрещено выбирать компании по ожидаемому совпадению значений или наличию
  удобных нулей/строк. Недостаточное последующее покрытие кодов даёт
  `insufficient`; компания не заменяется.
- Maximum budget: пять DataNewton finance calls, по одному на компанию,
  без retry. Transport failure сохраняется как failed sample и не заменяется
  другой компанией.
- FNS reads: до пяти JSON metadata и пяти официальных PDF/BFO artifacts.

Live-вызовы требуют отдельной явной команды владельца после утверждения этого
плана, даже если предыдущая evidence-сессия была разрешена.

### 2.1. Pre-call cohort commitment

До первого DataNewton-вызова создаётся отдельный tracked sanitized artifact
`finance-unit-evidence-v3-cohort-commitment.md` со следующими полями:

- новый opaque evidence session ID;
- ordered sample IDs `C04..C08` без названий и идентификаторов;
- policy, selection-rule, request-profile и collector versions;
- UTC timestamp;
- SHA-256 commitment приватного canonical cohort manifest, включающего
  high-entropy random nonce, ordered identifiers и все перечисленные versions.

Nonce, identifiers и canonical private manifest остаются вне Git. Commitment
проверяется локально повторным hash до обработки результатов. Sanitized
artifact проходит privacy scan и должен находиться в отдельном pre-call Git
commit, отправленном в remote до первого вызова. Commit hash записывается в
result evidence. После commitment ни sample, ни порядок, ни правило не
заменяются; failed/unavailable sample остаётся в матрице.

## 3. Зафиксированная поверхность

Provider request profile до первого вызова:

```text
method = GET
endpoint = /v1/finance
query = inn=<private identifier from the out-of-git sample map>
filters = none
request body = none
calls = one per sample
retry = forbidden
```

Для каждой компании сравниваются обе формы и два последних общих периода по
этому закрытому каталогу из immutable v1 contract:

| Form ID / source root | Exact line codes |
|---|---|
| `balance` / `$.balances` | `1210`, `1230`, `1240`, `1250`, `1300`, `1400`, `1500`, `1600` |
| `financial_results` / `$.fin_results` | `2100`, `2110`, `2200`, `2400` |

Parser/probe version и ожидаемая shape binding берутся из уже
зарегистрированного v2 collector. Для каждой новой response записывается новый
shape hash. Endpoint, request profile, каталог, tool version и правила
сравнения не меняются после первого вызова; любой drift даёт `shape_error`.

Официальная единица берётся только из самого FNS artifact. OKEI code и label
фиксируются отдельно; перевод OKEI 384 в «тысячи рублей» связывается с точной
версией официального классификатора. OKEI 385, если встретится, нормализуется
отдельным задокументированным множителем и не смешивается с 384 скрыто.

## 4. Строка sanitized evidence

Каждая ожидаемая ячейка записывается, даже если значение отсутствует:

```text
evidence_session_id, sample_id, form_id, line_code, reporting_year,
provider_availability, fns_availability,
provider_presence, fns_presence, fns_okei_state, fns_okei_code,
fns_normalization, scale_comparison_outcome, presence_outcome,
provider_raw_sha256, fns_document_sha256,
provider_shape_version, collection_tool_version, collected_at
```

Разрешённые `scale_comparison_outcome`:

- `exact_nonzero`;
- `not_comparable`;
- `scale_mismatch`;
- `rejected_okei`;
- `unavailable`;
- `shape_error`.

Разрешённые availability states:

- provider: `available`, `transport_failed`, `billing_ambiguous`;
- FNS: `available`, `metadata_unavailable`, `document_unavailable`,
  `document_invalid`.

`provider_presence` и `fns_presence` имеют значения `missing`, `zero`,
`nonzero` только при соответствующем `availability=available`; иначе значение
равно `not_observed`.

Разрешённые `presence_outcome`:

- `both_nonzero`;
- `exact_zero`;
- `exact_missing`;
- `zero_vs_missing`;
- `missing_vs_zero`;
- `nonzero_vs_missing`;
- `missing_vs_nonzero`;
- `zero_vs_nonzero`;
- `nonzero_vs_zero`;
- `unavailable_provider`;
- `unavailable_fns`;
- `unavailable_both`.

Для unavailable sample эмитируются все ожидаемые строки с `not_observed`,
`scale_comparison_outcome=unavailable` и соответствующим availability outcome.
Недоступность никогда не кодируется как `missing` и не является
presence-conflict. Она не участвует в scale proof; остальные samples всё равно
должны выполнить все scale coverage rules. Любая недоступность даёт
`presence_semantics_gate=insufficient` и по закрытому приоритету
`zero_semantics_gate=insufficient`. Sample не заменяется.

Raw response, production identifier, company name, address, people, API key,
headers, private mapping и exact monetary values не попадают в Git. Exact
Decimal comparison выполняется в private collector без tolerance, rounding,
interpolation и `float`. Tracked artifact содержит только opaque sample IDs,
presence classes, closed outcomes, hashes, source versions, aggregate counts
и полную field-level sanitized matrix.

## 5. Предопределённое решение

### Scale

`unit_scale_gate=verified_nonzero_thousand_rub` только если выполнены все
критерии policy section 4. Один `scale_mismatch` или shape error даёт
`rejected`. Недостаточное распределённое покрытие даёт `insufficient`, а не
passing.

### Presence и zero

Все outcomes публикуются в evidence независимо от scale result.
`presence_semantics_gate` вычисляется ровно по закрытому каталогу и приоритету
policy section 3.2. Zero gate также вычисляется только по приоритету policy
section 3.3: `rejected` → `blocked_conflict` → `insufficient` →
`verified_public_zero`. Verified state требует verified presence и заранее
заданный threshold: минимум шесть `exact_zero` у минимум трёх компаний, в
обеих формах и минимум по трём line codes. Presence `insufficient` всегда даёт
zero `insufficient`, даже если числовой threshold формально набран.

### Общий результат

Возможен split-result: scale `verified_nonzero_thousand_rub`, presence
`conflict_observed|insufficient` и zero `blocked_conflict|insufficient`. Он
разрешает только последующее проектирование nonzero path; не активирует policy,
не разблокирует iteration 20 автоматически и не разрешает runtime/provider
calls.

## 6. Обязательные result artifacts и review

После live-pass создаётся новая версия evidence, содержащая:

- immutable request/tool/source provenance и call accounting;
- pre-call commitment artifact и его pushed Git commit hash;
- hash каждого private raw artifact без его содержимого;
- полную sanitized matrix и детерминированные aggregate counts;
- отдельные решения scale, presence, zero и publication gates;
- явный список limitations и влияние на iteration 20 readiness;
- privacy/secret scan, YAML validation, `git diff --check` и независимое
  evidence review.

Если pass не выполнен, этот файл остаётся только планом и не считается
доказательством масштаба.
