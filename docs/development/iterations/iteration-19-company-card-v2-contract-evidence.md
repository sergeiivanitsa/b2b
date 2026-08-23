# Итерация 19 — Контракт, проектирование и evidence Company Card v2

ID: `19`

Slug: `company-card-v2-contract-evidence`

Public contract: `company_public_h2_v1`

Snapshot writer version: `3`

Branch: `feat/iteration-19-company-card-v2-contract-evidence`

Base commit: `c3805dd1fbb8cdac38b1aa315e1f1e94597e7537`

Статус спецификации: `approved_after_fresh_restart`

Тип итерации: `documentation/evidence/wireframes only`

## 1. Цель

Зафиксировать implementation-ready контракт новой публичной карточки компании до любых изменений Product API, Gateway API, React, SSR, persistence или provider-интеграции.

Итерация утверждает:

- отдельный successor endpoint и closed DTO;
- совместимость с неизменным H1;
- stored snapshot `report_version="3"` для нового Card-v2 writer;
- content-to-source и privacy manifest;
- точные алгоритмы пяти финансовых и пяти арбитражных представлений;
- правила evidence gates;
- AI artifact, SSR takeover, CSP/XSS и rollout boundaries;
- три reviewable wireframe для desktop, tablet и mobile.

Итерация не включает runtime-код.

## 2. Нормативные входы и приоритет решений

Нормативными являются:

1. `AGENTS.md`, `README.md`, Roadmap, DevFlow state и завершённые итерации 16–18.
2. Утверждённые владельцем решения из текущего planning input.
3. `Новая схема страницы.pdf` — источник порядка секций и общей композиции.
4. `sks-chart-technical-spec.md` — источник названий, полей и исходных формул десяти представлений.
5. `ФОРМА СПРАВА.png` — референс композиции Claims CTA.
6. Локальные ignored evidence-файлы — только observed shape, но не самостоятельное доказательство vendor semantics, финансовой единицы или production availability.

При конфликте применяются утверждённые решения этой итерации:

- отрицательные значения сохраняют знак и расходятся относительно нуля;
- missing не становится zero;
- физические opposing parties маскируются;
- неизвестный entity type не выводится из названия;
- PDF-цвета и оценочные формулировки не являются verdict semantics;
- точный CTA-copy из этой спецификации важнее регистра текста на PNG.

На дату планирования официальная DataNewton-документация не дала проверяемого подтверждения единицы финансовых значений. Макет, Checko, имя поля или пользовательское ожидание не доказывают `thousand_rub`. Gate остаётся `unverified`.

Официальным первичным comparator для будущей bounded matrix выбран ФНС ГИР БО: line codes и значения сравниваются с документами, где единица явно задана через ОКЕИ. ОКЕИ `384` означает тысячи рублей, `385` — миллионы рублей. Это подтверждает единицу ФНС, но не mapping DataNewton без exact cross-company matrix.

## 3. Scope

В scope только документация, evidence и wireframes:

- эта спецификация и implementation plan;
- provider field/source manifest;
- finance-unit evidence artifact;
- arbitration contract evidence artifact;
- architecture и privacy ADR;
- три SVG-wireframe;
- DevFlow lifecycle state.

## 4. Вне scope

- Product API, Gateway API, React, nginx, deploy, CI и runtime configuration.
- SQLAlchemy, Alembic, snapshot, provider, normalizer или public DTO code.
- Production DB, production publication, refresh или backfill.
- Live DataNewton или ФНС requests во время planning.
- Paid AI.
- Создание, commit, push или merge runtime-изменений.
- Contacts, scoring, verdict, recovery probability, rating и рекомендации о надёжности.
- Изменение `docs/development/ROADMAP.md`.
- Копирование raw provider payload, production identifiers, PII или secrets в git.

## 5. Название, endpoint и contract axes

### 5.1. Successor contract

Несовместимый successor фиксируется как:

```http
GET /company-reports/{inn}/public-h2
```

```text
contract_version = "company_public_h2_v1"
```

Термины имеют разные значения:

| Ось | Значение |
|---|---|
| Product generation | `Company Card v2` |
| HTTP route family | `public-h2` |
| Public DTO version | `company_public_h2_v1` |
| Stored report schema | `report_version="3"` |
| Chart facts | `company_card_chart_facts_v1` |
| Finance unit policy | `datanewton_finance_thousand_rub_v1` |
| AI schema/prompt/catalog/model | Независимые versioned identifiers |
| Publication policy | Отдельная H2 policy, не H1 sufficiency policy |

Ни одна из этих версий не подменяет другую.

`public-h2`:

- anonymous;
- не принимает query parameters;
- read-only;
- не вызывает provider, Gateway, AI, worker, queue или DB write;
- возвращает только strict sanitized projection;
- использует `Cache-Control: no-store`, `X-Content-Type-Options: nosniff` и корректный `X-Robots-Tag`.

### 5.2. Неизменный H1

Остаются неизменными:

```text
GET /company-reports/{inn}/public-h1
contract_version = "company_public_h1_v1"
report_version = "1" | "2"
```

Также неизменными остаются:

- strict H1 frontend reader;
- H1 payload topology и dormant gates;
- H1 prohibition на embedded serialized DTO;
- H1 active publication pin;
- H1 Claims actions;
- H1 canonical route как production default до завершения iteration 24 включительно.

H1 никогда не возвращает `report_version="3"` и не получает chart-v2, narrative-v2, party или finance fields.

При наличии v3 run H1 resolver:

1. сначала использует exact active H1 pin;
2. без pin ищет latest eligible v1/v2 snapshot;
3. не считает v3 H1-compatible;
4. не преобразует v3 в фиктивный `"2"`;
5. не переписывает и не backfill-ит snapshot;
6. при отсутствии пригодного v1/v2 возвращает safe legacy-unavailable outcome.

Новый v3 run не смещает H1 pin или latest eligible v1/v2 молча.

## 6. Writer/version compatibility

### 6.1. Gated writer profile

Глобальная замена `CURRENT_COMPANY_REPORT_VERSION = "3"` до cutover запрещена: она нарушила бы H1 serializer, legacy API, publication validator, Claims handoff и strict frontend.

`POST /company-reports` permanently remains the H1 lifecycle entry point: it
creates or reuses only `h1_legacy_writer_v2` / `report_version="2"` /
`company_public_h1_v1`, with no client-controlled version/header/query and no
dependency on the H2 assignment/cohort. It can return
`409 report_writer_profile_conflict` only when an incompatible active H2 job
already owns the one-active-job-per-subject slot. v3 is created only through
`POST /company-report-presentations`.

| Profile | Stored version | Availability |
|---|---:|---|
| `h1_legacy_writer_v2` | `"2"` | Текущее production behavior до cutover |
| `company_card_v2_writer_v3` | `"3"` | Default-off, test/allowlist only до iteration 25 |

Инварианты:

- новый Card-v2 writer пишет только `"3"`;
- внутри Card-v2 path версии `"1"`/`"2"` read-only;
- server сохраняет выбранную version в pending record до provider call;
- последующее изменение flag не меняет уже созданный pending job;
- v2 и v3 pending jobs не переиспользуются друг вместо друга;
- mixed-version reuse/fencing покрывается отдельно;
- клиент не выбирает writer version.

H1 status/latest/public-H1 resolve only H1/v1-v2. An active H2 assignment does
not hide an existing H1 pin or eligible v1/v2 report. A previously created H1
job remains H1-pollable after any later rollout change. H2 uses its separate
opaque presentation lifecycle and never changes these rules.

До iteration 25 production resolver выбирает H1 profile. В iteration 25 переход на v3 profile допускается только для owner-approved rollout cohort.

### 6.2. Read matrix

| Surface | v1/v2 | v3 |
|---|---|---|
| Exact snapshot deserializer | Читает старую форму и сохраняет прежний hash | Читает только exact v3 discriminator |
| Snapshot writer | Card-v2 path не пишет | Пишет immutable v3 |
| `public-h1` | Без изменений | Не возвращает |
| `public-h2` | Safe legacy projection, всегда noindex, отсутствующие v3 facts имеют limitations | Полная projection при закрытых gates |
| Legacy latest API | Продолжает прежний compatible выбор | Не выдаёт v3 старому клиенту как v2 |
| Claims handoff | Existing exact-report behavior | Тот же narrow identity prefill после explicit v3 parser support |
| GET/SSR | Никогда не upgrade/rewrite | Никогда не refresh/provider-write |

Unknown, absent или coerced report version fail closed.

### 6.3. Legacy projection

H2 может прочитать v1/v2 только без мутации. DTO получает:

```text
snapshot_capability = "legacy_read_only"
indexable = false
```

Отсутствующие v3 facts:

- не вычисляются из raw на GET;
- не запрашиваются у provider;
- не становятся нулями;
- имеют `legacy_snapshot_v1_v2` и field-specific limitations;
- соответствующий view получает `legacy_unavailable` либо `partial`.

Existing published v1/v2 subjects продолжают оставаться на H1, пока controlled owner-approved H2 pin не создан.

## 7. Projection-specific publication и rollback

Текущая H1 publication row уникальна на subject и не может одновременно хранить H1 и H2 pins. Итерация 20 должна реализовать отдельный H2 registry, не переиспользуя H1 sufficiency как доказательство Card v2.

Концептуальные records:

```text
H2PublicationPin:
  subject_id
  contract_version = "company_public_h2_v1"
  report_id
  snapshot_hash
  chart_facts_version
  evidence_registry_version
  publication_policy_version
  narrative_binding
  canonical_path
  indexable
  status
  published_lastmod
  generation/fence metadata

PublicPresentationAssignment:
  subject_id
  active_contract = "company_public_h1_v1" | "company_public_h2_v1"
  approved_generation
  changed_at
```

`narrative_binding` содержит либо exact immutable artifact key, либо exact deterministic fallback version. Поздно появившийся AI artifact не меняет опубликованный текст без controlled republish.

H2 projection scopes:

```text
active_publication
staged_publication
latest_unpublished
```

Правила:

1. H2 pin и H1 pin могут сосуществовать.
2. Отсутствующий assignment означает H1.
3. `staged_publication` всегда `indexable=false`.
4. `latest_unpublished` всегда `indexable=false`.
5. `active_publication` допустим только для exact valid H2 pin и H2 assignment.
6. Corrupt/missing active H2 pin fail closed; resolver не падает обратно на H1 или latest.
7. Sitemap, canonical SSR и robots выбирают только active assignment.
8. Один subject не получает две indexable canonical-карточки.
9. Rollback меняет assignment обратно на H1, не удаляя и не переписывая reports, pins или AI artifacts.
10. Assignment на H2 до iteration 25 запрещён.
11. Activation в iteration 25 требует отдельного явного owner approval.

## 8. Public H2 DTO

### 8.1. Root topology

```text
CompanyPublicH2Response:
  contract_version: "company_public_h2_v1"
  projection_digest: lowercase SHA-256 of sanitized canonical DTO
  report_id: UUID
  report_version: "1" | "2" | "3"
  snapshot_capability: "legacy_read_only" | "card_v2"
  projection_scope:
    "active_publication" | "staged_publication" | "latest_unpublished"
  canonical_path: /company/{same-inn}-{slug}
  indexable: boolean
  checked_at: UTC ISO datetime
  checked_date: ISO date in Europe/Moscow
  checked_date_display: backend string
  identity: PublicH2Identity
  narrative: PublicH2Narrative
  block_order: PublicH2BlockId[]
  blocks: PublicH2Blocks
  coverage: PublicH2CoverageItem[]
  sources: PublicH2SourceItem[]
  limitations: PublicH2Limitation[]
  actions: PublicH2Action[2]
  breadcrumbs: PublicH2Breadcrumb[2]
  primary_claim_cta: PublicH2ClaimCta
```

Все objects recursively `extra=forbid`. Unknown key, enum, path, Decimal shape или contract version даёт `contract_mismatch`; клиент не показывает partially parsed facts.

`projection_digest` вычисляется только по sanitized public DTO с исключённым собственным digest. Raw snapshot hash не включается в HTML/embedded state.

### 8.2. Exact block order

```text
hero_status
narrative
in_page_navigation
requisites
finance_f1_liquidity
finance_f2_funding
finance_f3_growth
finance_f4_profit_per_100
finance_f5_yearly_table
arbitration_a1_activity
arbitration_a2_roles
arbitration_a3_outcomes
arbitration_a4_case_amounts
arbitration_a5_opponents
sources_limitations
neutral_actions
```

PDF tabs становятся доступной in-page navigation:

- `Реквизиты`
- `Финансы`
- `Арбитраж`

Это anchor navigation, а не tabs, скрывающие SSR content. Все факты присутствуют в JS-disabled document.

### 8.3. Common value primitives

```text
ExactDecimal:
  decimal: canonical Decimal string
  display_exact: backend-provided string
  display_compact: backend-provided string | null
  unit_id: allowlisted string | null
  unit_policy_version: allowlisted string | null

PublicChartAxis:
  axis_min_decimal: CanonicalDecimal
  axis_max_decimal: CanonicalDecimal

PublicChartInterval:
  start_ratio_decimal: CanonicalDecimal
  end_ratio_decimal: CanonicalDecimal

PublicChartPoint:
  ratio_decimal: CanonicalDecimal
```

Decimal source truth никогда не является `float`. Browser может преобразовать только bounded geometry ratios, но не денежную истину.

```text
DetailScope:
  population_scope: "complete_collection" | "returned_slice"
  source_total: integer | null
  rows_received: integer
  eligible_total: integer
  shown: integer
  cap: 20
  label: exact backend string "показано N из M ..."
```

`M` всегда является eligible population конкретного detail view, а не source total другого view.

### 8.4. Coverage states

```text
available
available_empty
partial
missing
not_requested
failed
conflict
gate_closed
legacy_unavailable
```

Overall report `complete|partial` не выводится клиентом из coverage. Показывается только exact per-block state.

## 9. Immutable report date

`checked_at` равен stored `generated_at` displayed report.

```text
checked_date =
  generated_at.astimezone(ZoneInfo("Europe/Moscow")).date()
```

Запрещены:

- browser timezone conversion;
- скрытое текущее время;
- auto-refresh;
- TTL-based replacement;
- backfill на GET;
- подмена датой AI artifact, публикации или открытия страницы.

Повторное открытие через год показывает ту же дату отчёта.

Status effective date и source received/effective dates являются отдельными полями. Они не заменяют report date.

При наличии проверенного status применяется датированная нейтральная формулировка:

```text
По данным отчёта, сформированного {checked_date_display}: {status_label}.
```

При отсутствии status не выводятся «действует», «ликвидирована» или иной inferred verdict.

## 10. Content-to-source manifest

`NOT_VERIFIED` является окончательным текущим решением «не показывать», а не приглашением угадать path.

| Surface/fact | Provider/source | Mapping | Gate/current decision | Public/privacy behavior |
|---|---|---|---|---|
| Legal/full name | `$.company.company_names.full_name` | Exact nonblank string | Existing core contract | Public |
| Short name | `$.company.company_names.short_name` | Exact nonblank string | Existing core contract | Public |
| INN | `$.inn`, затем `$.company.inn` | Exact normalized value must equal target | Existing identity contract | Public in company identity only |
| OGRN/OGRNIP | `$.ogrn`, затем `$.company.ogrn` | Exact normalized string | Existing core contract | Public |
| KPP | `$.company.kpp` | Exact normalized string | Existing core contract | Public |
| Registration/dissolution dates | `$.company.registration_date`, `$.company.dissolved_date` | Exact ISO date | Existing core contract | Public when valid |
| Address | `$.company.address.*` | Existing exact address fields | Existing privacy approval | Public; inaccuracy flag visible |
| Legal status | `$.company.status.*` | Closed status catalog required | Semantic/effective-date gate unverified | Hidden with limitation |
| Status effective date | Candidate status date | `NOT_VERIFIED` | Gate closed | Never infer from report date |
| Legal form | `$.company.opf` | Closed code/label mapping required | Dictionary gate unverified | Hidden |
| Charter capital | `$.company.charter_capital` | Decimal plus separate unit | Unit gate unverified | Hidden; finance unit gate does not apply |
| Tax modes | `$.company.tax_mode_info.*` | Scoped boolean and publication date | Semantics/scope gate unverified | Hidden until verified |
| Primary/full OKVED | `$.company.okveds` | Exact code, label, primary flag, effective date | Leaf schema unverified | Hidden |
| Manager | `$.company.managers[*]` | Name, role, appointed date, inaccuracy only | Shape observed; semantic gate required | Name/role/date safe; `innfl` forbidden |
| Owners/shares | `$.company.owners` | Exact owner type/name/share/effective date | Leaf schema unverified | Names and shares safe; identifiers hidden |
| Employees | `$.company.workers_count` | Count plus exact reference period/scope | Shape/semantics unverified | Hidden |
| Tax authority | `NOT_VERIFIED` | Exact authority name/code/date required | Gate closed | Hidden |
| Contacts | `$.company.contacts` | No public mapping | Prohibited | Not requested for Card v2; never emitted |
| Finance statements | `$.balances`, `$.fin_results`, exact `code` and `sum[year]` | Form+code+year Decimal map | Shape observed | Monetary presentation gate closed |
| Finance unit | No proven DataNewton field | Exact DataNewton→FNS mapping | `unverified` | No `₽`, `тыс. ₽` or scaled money |
| Arbitration page | Observed synthetic/current shape: `$.data`, `$.total_cases`, `$.offset`, `$.limit`; authoritative provider total leaf: `NOT_VERIFIED` | Exact total path/type/scope must be evidence-bound before v3; `$.total` is never asserted | Single-page shape observed; provider envelope/full semantics unverified | Partial/gate-closed until exact bind |
| Case identity | `$.data[*].case_id`, fallback `id` | Preferred `case_id`, fallback exact `id` | Observed | Internal key; visible case number separate |
| Case year | `$.data[*].year` | Year of case start only | Semantic gate required | Missing remains unknown |
| Role parties | `plaintiffs[]`, `respondents[]` and verified other collections | Exact target INN only | Shape observed | Party identifiers internal only |
| Outcome | `$.data[*].party_result` | Exact `WON|LOST|RETURNED`; other → unknown | Scope/semantic gate required | `result_type` never substitutes |
| Result detail | `$.data[*].result_type` | Closed clarification catalog only | Optional gate | Never classifies outcome |
| Amount | `$.data[*].sum` | Exact Decimal, including zero/negative | Shape observed | Not called debt |
| Currency | `$.data[*].currency` | Closed source-currency mapping | Semantic mapping gate required | No symbol for missing/unknown |
| Entity type | Party leaf `NOT_VERIFIED` | Exact provider type required | Gate closed | Unknown/conflict is masked |
| Instances/courts | `instance_count`, `instances[]` candidates | Exact path/type/scope required | Gate closed | Omit until verified |
| KAD URL | `$.data[*].kad_arbitr_link` | Exact HTTPS allowlist required | Host/pattern gate unverified | No link until gate passes |

Every tracked field-manifest row must contain:

- dataset/endpoint and observed shape version;
- exact JSON path or `NOT_VERIFIED`;
- JSON type, cardinality and nullability;
- subject scope;
- effective/reference date semantics;
- identity semantics;
- evidence provenance and date;
- schema, semantic, privacy and operational gate states;
- public transformation;
- missing/conflict behavior.

## 11. Finance source normalization

### 11.1. Required forms and codes

Balance:

```text
1210, 1230, 1240, 1250, 1300, 1400, 1500, 1600
```

Financial results:

```text
2100, 2110, 2200, 2400
```

Code `4400` is excluded from `company_public_h2_v1`. Its historical presence must not create values in later periods.

The builder indexes exact `(form, code, year)`:

- valid numeric values become `Decimal`;
- explicit `0` remains zero;
- null/absent remains missing;
- two equal duplicates collapse with provenance;
- conflicting duplicates make that form/code/year `conflict`;
- conflict never selects an arbitrary value.

### 11.2. Window policy

There is no global finance window. Каждый view выбирает anchor и calendar window самостоятельно и показывает exact periods in its heading.

Для любого required-code set:

```text
complete_years = intersection(years having non-conflicting explicit values
                              for every required code)
anchor_year = max(complete_years)
```

Anchor выводится только из данных. Browser current year, report year и system time не участвуют.

Для seven-year views:

```text
window = [anchor_year - 6, ..., anchor_year]
```

Это семь последовательных calendar years, а не семь разрозненных точек. Gaps сохраняются.

### 11.3. Finance unit gate

До active `datanewton_finance_thousand_rub_v1`:

- monetary Chart Facts не считаются publishable;
- `₽`, `тыс. ₽`, `млн ₽` не выводятся;
- деление/умножение на `1000` запрещено;
- iteration 23 не стартует.

После exact evidence pass:

```text
source_thousand_decimal = provider Decimal
rub_decimal = source_thousand_decimal * 1000
million_decimal = source_thousand_decimal / 1000
```

Gate applies only to the exact proved endpoint/filter/shape and twelve approved codes. Shape/filter drift makes it stale.

Formatter:

- source truth — exact Decimal string;
- compact money — millions, one decimal, `ROUND_HALF_UP`;
- example: `273,3 млн ₽`;
- exact tooltip/table — three decimals in millions when source is integral thousands;
- example: `273,325 млн ₽`;
- missing — `—` or `Нет данных`;
- explicit zero — `0`/`0,000 млн ₽`;
- negative — Unicode minus in display, negative Decimal in DTO;
- no JavaScript money rounding.

Если matrix обнаружит fractional-thousand precision, mixed units или иной scale, candidate policy получает `rejected`, а formatter пересматривается в новой versioned evidence iteration.

## 12. Five finance views

### F1 — Хватит ли средств на ближайшие обязательства?

Required codes:

```text
1250 cash
1240 short financial investments
1230 receivables
1500 short-term liabilities
```

Year: latest complete common year.

```text
available_without_inventory = 1250 + 1240 + 1230
difference = available_without_inventory - 1500
```

Rules:

- отсутствие любого required value скрывает factual chart;
- explicit zero valid;
- every segment keeps sign;
- mixed-sign segments use a shared diverging zero axis;
- no `abs`, clamp or omission;
- positive difference is not called safety reserve;
- receivables always carry the limitation that repayment time/probability is not assessed;
- negative difference is a factual signed difference, not a solvency verdict.

### F2 — В компании больше своих средств или долгов?

Required codes:

```text
1300 equity
1400 long-term liabilities
1500 short-term liabilities
```

Anchor: latest complete common year. Window: seven calendar years.

For each year with all values:

```text
debt = 1400 + 1500
denominator = 1300 + debt
```

If `denominator > 0`:

```text
equity_share = 1300 / denominator * 100
debt_share = debt / denominator * 100
```

If `denominator <= 0`, shares are `null`; exact signed components remain visible with `finance_denominator_non_positive`.

If denominator is positive but a component is negative:

- signed percentages are retained;
- a 100%-stack is not used;
- a diverging zero-axis view is used;
- percentages are not clamped to `[0,100]`.

A year with any missing/conflicting required value appears as an explicit gap, not as zero and not as a skipped calendar year.

### F3 — Компания растёт или уменьшается?

Required codes:

```text
2110 revenue
1600 assets
```

Anchor: latest common valid year. Window: seven calendar years.

Each series retains its own points. Missing revenue creates a gap only in revenue; missing assets creates a gap only in assets.

Each series independently uses its earliest and latest valid years inside the
window. Fewer than two valid points in that series means no comparison/multiple
for that series; one series never borrows or suppresses the other's endpoints.

For each series:

- multiple is rendered only when first and last values are both strictly positive;
- zero/negative baseline or negative last value suppresses “во сколько раз”;
- exact signed absolute change may be shown after unit gate;
- no interpolation, forecast, normalization or logarithmic scale;
- YoY uses the immediately preceding calendar year only;
- previous missing/zero/non-positive suppresses YoY.

### F4 — Сколько прибыли остаётся со 100 ₽ выручки?

Required codes:

```text
2110 revenue
2100 gross profit
2200 operating profit
2400 net profit
```

Year: latest complete common year.

If revenue is strictly positive:

```text
revenue_per_100 = 100
gross_per_100 = 2100 / 2110 * 100
operating_per_100 = 2200 / 2110 * 100
net_per_100 = 2400 / 2110 * 100
```

Rules:

- profit values retain negative sign;
- negative ratios diverge left of zero;
- axis is data-derived and includes zero;
- revenue zero or negative suppresses all ratios and shows exact signed components with denominator limitation;
- no `[0,100]` clamp;
- profit values over 100 are not clipped;
- no good/bad colors or verdict wording.

### F5 — Главные финансовые показатели

Fixed row order:

```text
2110 Продажи
1600 Всё имущество
1250 Деньги на счетах
1240 Финансовые вложения
1230 Долги покупателей
1210 Запасы
1500 Ближайшие обязательства
1300 Свои средства
2400 Чистая прибыль
```

Anchor is the maximum non-conflicting year present in any fixed row. Window is seven consecutive calendar years.

Rules:

- all nine rows remain in the contract;
- missing cell is `—`;
- zero is visible;
- signed values retain sign;
- a row absent for all seven years remains present with a limitation;
- horizontal scrolling is confined to the table on small screens;
- no inferred value for code `4400`.

## 13. Arbitration collection and persistence ADR

Выбран вариант: bounded full sanitized normalized case set плюс write-time deterministic Chart Facts and provenance.

### 13.1. Hard bounds

```text
page_size = 100
max_pages = 10
hard_case_row_cap = 1000
sanitized_arbitration_storage_cap = 8 MiB canonical UTF-8 JSON
detail_cap = 20 per view
```

Это technical product guards, а не заявления о DataNewton limits.

При любом cap exhaustion:

```text
collection_state = "partial"
completion_reason = "case_cap_exhausted" | "storage_cap_exhausted"
```

Агрегаты относятся только к фактически сохранённой eligible population.

### 13.2. Pagination

1. Первый request: `offset=0`, `limit=100`.
2. До первого v3 request evidence registry обязан bind-ить exact provider total path/type к normalized `source_total`; без bind collection не запускается. Первый valid nonnegative bound value фиксируется как `source_total`.
3. Каждая следующая page обязана вернуть тот же total и ожидаемый offset.
4. Следующий offset равен previous requested offset плюс фактически returned rows.
5. `len(data)` обязан быть `0..limit`.
6. Empty/non-progress page до достижения total завершает collection как partial.
7. Повтор page hash на новом offset завершает collection как partial.
8. Total drift, offset drift, short page before total, overlap conflict или malformed envelope завершают collection как partial.
9. Complete допустим только когда fetched source positions достигает exact stable total без cap/error/drift.
10. `total=0`, `data=[]`, `offset=0` является successful empty только при valid envelope.
11. Provider errors одного page не уничтожают уже сохранённую safe slice.
12. Raw pages не сохраняются.

Internal page manifest содержит только:

- page ordinal;
- request offset/limit;
- returned count;
- observed total;
- response hash;
- safe request identifier;
- received timestamp;
- outcome code.

### 13.3. Case identity and dedup

```text
case_key = exact nonblank case_id
fallback = exact nonblank id
```

`case_number` является отдельным visible field и не подменяет key.

Dedup:

- identical canonical normalized records with same key collapse once;
- conflicting records with same key исключаются все, а collection становится partial;
- row без обоих key считается malformed;
- равные суммы при разных keys никогда не дедуплицируют дела;
- dedup происходит до aggregates/top-20;
- collision/conflict counts сохраняются.

### 13.4. Stored v3 arbitration shape

```text
ArbitrationCollectionV1:
  source_total
  rows_received
  unique_case_count
  malformed_count
  duplicate_identical_count
  duplicate_conflict_count
  page_manifest
  collection_complete
  completion_reasons
  completion_reason
  calendar_complete
  calendar_scope: "unverified" | "all_time" | "bounded_interval"
  calendar_start_year
  calendar_end_year
  calendar_evidence_version
  observed_start_year
  observed_end_year
  unknown_year_count
  zero_years_proven
  sanitized_cases
  normalized_basis_hash
  chart_facts
  chart_facts_hash
```

`chart_facts` includes the exact immutable object:

```text
ArbitrationCalendarFactsV1:
  collection_complete
  calendar_complete
  calendar_scope
  calendar_start_year
  calendar_end_year
  calendar_evidence_version
  observed_start_year
  observed_end_year
  unknown_year_count
  zero_years_proven
```

`calendar_scope="unverified"` requires false completeness and null bounds/
evidence; `bounded_interval` requires both bounds with start <= end; `all_time`
does not invent infinite bounds. `chart_facts_hash` includes every member.

`chart_facts` pure-builder должен воспроизводиться из `sanitized_cases`. Finalization сравнивает recomputed hash; mismatch fail closed.

## 14. Arbitration roles, outcomes, currency and privacy

### 14.1. Exact target role

Используется только normalized target INN. OGRN и name не участвуют.

Для каждого case строится множество exact roles, в которых target INN найден:

- only plaintiff → `plaintiff`;
- only respondent → `respondent`;
- более одной role collection, включая plaintiff+respondent или third/other → `other`;
- нет exact match → `unattributed`;
- malformed case не входит в normalized denominator.

Каждое normalized дело получает ровно один bucket:

```text
plaintiff + respondent + other + unattributed = unique_case_count
```

Name-only, OGRN-only и fuzzy match запрещены.

### 14.2. Outcome

Outcome берётся только из verified company-scoped `party_result`:

```text
"WON"      -> won
"LOST"     -> lost
"RETURNED" -> returned
anything else/null -> unknown
```

Mapping exact and case-sensitive; raw unknown value публично не выводится.

`result_type`, `status`, `status_by_document`, documents или слова в судебном тексте не заменяют `party_result`.

`result_type` может использоваться только как detail clarification из закрытого catalog после отдельного gate.

### 14.3. Currency and amount

- Amount — exact Decimal.
- Missing amount не становится zero.
- Explicit `0` остаётся видимым.
- Negative amount сохраняет знак и расходится относительно zero.
- Different source currencies получают отдельные axes и populations.
- FX conversion запрещён.
- Missing/unknown currency не получает `₽`.
- Source amount не называется задолженностью, долгом или взысканной суммой.
- Currency symbol выводится только по closed verified mapping.

### 14.4. Calendar

Case year берётся только из evidence-proven `year` semantics. Missing year попадает в `Год не указан`.

`collection_complete` доказывает только полное прохождение bound provider
population. `calendar_complete` является отдельным фактом и требует exact
method/path/filter/filter-version binding и отдельный evidence version,
доказывающий `all_time` либо `bounded_interval`. Complete collection может
иметь `calendar_complete=false`; unknown-year rows не делают
`collection_complete=false` сами по себе. `calendar_scope="unverified"`
requires false calendar completeness, null evidence/bounds and
`zero_years_proven=false`. A bounded interval requires both bounds and
`start<=end`; all-time does not invent infinite bounds. Observed bounds are
both null when no verified-year case exists, otherwise they are the exact
minimum/maximum observed verified years.

Synthetic zero year допустим только при `zero_years_proven=true`. Этот флаг
требует одновременно complete collection/calendar, `unknown_year_count=0` и
отсутствия malformed, duplicate-conflict, oversized, privacy-excluded или
cap-excluded case, который мог принадлежать утверждаемому году. Иначе A1
показывает только observed years плюс nullable `Год не указан`; фраза `дел нет`
запрещена. Пустая proven collection не создаёт произвольный current-year
bucket. For bounded scope, synthetic zero is limited to the bound interval; for
all-time it is limited to the inclusive observed bounds, so an empty all-time
result creates no arbitrary bucket. Returned/total and calendar scope are
always visible.

## 15. Five arbitration views

Общий scope label:

- complete: counts из full proven normalized collection;
- partial: counts только из returned sanitized slice;
- никакой экстраполяции на `source_total`.

Common case detail sort:

```text
case_year DESC NULLS LAST
date_start DESC NULLS LAST
date_update DESC NULLS LAST
case_key ASC
```

### A1 — Как часто компания участвовала в арбитражных делах?

- calendar buckets;
- stacked exact roles `plaintiff`, `respondent`, `other`, `unattributed`;
- unknown year отдельным bucket;
- total over all available years separate;
- each role/year drilldown capped at 20;
- `M` = eligible cases в exact role/year bucket;
- exact `показано N из M дел`.

### A2 — Компания чаще подавала иски или отвечала по ним?

Four bars:

```text
plaintiff
respondent
other
unattributed
```

Denominator = all normalized unique cases in current collection scope.

Backend provides count and exact percentage. UI не пересчитывает роль из selected cases.

Each bucket detail capped at 20; `M` is exact bucket population.

### A3 — Чем закончились дела для компании?

Four categories:

```text
won
lost
returned
unknown
```

Denominator = all normalized unique cases in current collection scope.

No “win rate” is calculated. Returned не считается рассмотренным спором. Unknown не считается loss.

Each category detail capped at 20.

### A4 — Какие суммы указаны в делах?

Eligibility per currency:

- normalized unique case;
- explicit amount, including zero/negative;
- verified source currency.

Top-20 строится отдельно для каждой currency:

```text
ABS(amount) DESC
amount DESC
case_year DESC NULLS LAST
date_update DESC NULLS LAST
case_key ASC
```

Tie-breaker never removes equal amounts.

For each currency:

```text
M = eligible cases with explicit amount in that currency
N = min(M, 20)
label = "показано N из M дел в {currency}"
```

Tooltip/detail may contain only safe:

- case number;
- role;
- outcome;
- exact amount/currency;
- start/update dates;
- calendar days between dates, labelled `От подачи до последнего обновления`;
- verified instance/court labels;
- masked/safe opposing party;
- allowed KAD link.

### A5 — С кем судилась компания?

Opposing parties:

- target only plaintiff → respondents;
- target only respondent → plaintiffs;
- `other`/`unattributed` не получают guessed opponent;
- multiple opposing parties count the case in each group;
- explanatory copy states that sum of group counts may exceed case count.

Grouping:

- verified legal/state party: exact party INN internal key;
- natural party: report-scoped HMAC token;
- unknown/conflicting entity type: masked HMAC token;
- verified legal/state party without exact INN: case+position scoped group, no cross-case merge;
- name-only cross-case grouping prohibited.

Visible legal/state names allowed; internal INN never appears in DTO, HTML, embedded state, tooltip, aria label or telemetry.

Group sort:

```text
case_count DESC
safe_display_name ASC
safe_stable_key ASC
```

Top-20:

```text
M = eligible safe groups in current collection scope
N = min(M, 20)
label = "показано N из M сторон"
```

Nested case details inside a displayed group are separately capped at 20 with their own `N/M`.

## 16. Privacy and masking contract

### 16.1. Allowed

- legal address and its inaccuracy state;
- manager name, approved role, appointed date and inaccuracy flag;
- owner name, owner type, share and ownership effective date;
- legal entity/state body opposing-party name;
- safe business activity/OKVED label;
- verified employee count with period.

### 16.2. Forbidden

- contacts, phone, email, website and social identifiers;
- personal INN/INNFL, passport, SNILS or other personal identifiers;
- raw provider party/name objects;
- natural opposing-party names;
- unknown-type opposing-party names;
- private IDs in URLs, metadata, JSON-LD, data attributes, comments, logs or telemetry;
- raw payload/provider headers/request body;
- scoring/signals/verdict/probability.

Manager/owner name allowance is limited to management composition. It does not allow natural opposing-party names.

### 16.3. Masking algorithm

For every masked natural/unknown opposing party, HMAC input is the exact
discriminated named object from section 31.6. Closed enums are:

```text
OpponentEntityClassV1 = "masked_natural" | "masked_unknown"
SourceRoleCollectionV1 =
  "plaintiffs" | "respondents" | "applicants" | "creditors" |
  "creditors_current_payments" | "debtors" |
  "interested_persons" | "third_parties" | "others"
StableIdentifierKindV1 = "inn" | "ogrn"
```

```text
OpponentHmacIdentityV1:
  identity_version: literal "OpponentHmacIdentityV1"
  domain: literal "company-card-v2:opponent:v1"
  report_id: lowercase UUID
  entity_class: OpponentEntityClassV1
  identifier: StableOpponentIdentifierV1 | CasePositionIdentifierV1

StableOpponentIdentifierV1:
  kind: "inn" | "ogrn"
  value: exact normalized value from that verified source field

CasePositionIdentifierV1:
  kind: literal "case_position"
  case_key: NFC nonblank private case key
  source_role_collection: SourceRoleCollectionV1
  zero_based_ordinal: integer >=0
```

Unknown keys are forbidden. Message bytes are
`UTF-8(CJSON_company_public_h2_cjson_v1(OpponentHmacIdentityV1))`; the complete
32-byte HMAC-SHA-256 is stored as 64 lowercase hex. Secret bytes are at least
32 bytes, resolved only by worker through a nonsecret `mask_key_id` matching
`[a-z][a-z0-9_]{0,31}`. Delimiter concatenation, base64, locale JSON and token
truncation are forbidden. The private identifier and raw natural name are
discarded from sanitized v3 facts. Case-position identities are deliberately
not merged across cases.

Public ordering is based on exact private named objects before projection:

```text
CasePublicOrderIdentityV1:
  identity_version: literal "CasePublicOrderIdentityV1"
  report_id: lowercase UUID
  case_key: private canonical case key

OpponentPublicOrderIdentityV1:
  identity_version: literal "OpponentPublicOrderIdentityV1"
  report_id: lowercase UUID
  display_kind: "legal" | "state" | "masked_natural" | "masked_unknown"
  private_identity_kind:
    "stable_inn" | "stable_ogrn" | "masked_hmac" | "case_position_hmac"
  private_identity_value: exact private identifier or full 64-hex HMAC
```

Cases validate/deduplicate, sort by UTF-8 CJSON bytes, receive one-based index
`1..1000` and encode as `case_` plus six zero-padded ASCII digits. Opponents
validate/deduplicate, sort by fixed display-kind rank
`legal,state,masked_natural,masked_unknown` and then their named-object UTF-8
CJSON bytes, receive one-based index `1..20000` and encode as `opponent_` plus
six digits. Exact patterns are `case_[0-9]{6}` and
`opponent_[0-9]{6}`. Zero, overflow or duplicate index invalidates projection;
the width never expands. Per-case display cap 20 is applied only after this
deterministic identity/order assignment. Public IDs contain no provider key,
private identifier, HMAC bytes/prefix or source ordinal.

The scanner-safe test vector uses the 43-byte ASCII key
`iteration-nineteen-hmac-vector-key-material` and exact CJSON:

```text
{"domain":"company-card-v2:opponent:v1","entity_class":"masked_unknown","identifier":{"case_key":"case-alpha","kind":"case_position","source_role_collection":"respondents","zero_based_ordinal":0},"identity_version":"OpponentHmacIdentityV1","report_id":"a1b2c3d4-e5f6-4a7b-8c9d-a1b2c3d4e5f6"}
```

Expected lowercase HMAC-SHA-256 is
`21d8c54c7052e3112c6c748f3ae5fa545c121d23b37ca02561b2978b9f767220`.
Case-order golden sorts `case-alpha,case-beta,case-zeta` to
`case_000001,case_000002,case_000003`. The independently reproducible
opponent-order golden uses the same report UUID
`a1b2c3d4-e5f6-4a7b-8c9d-a1b2c3d4e5f6`,
`display_kind="masked_unknown"`, `private_identity_kind="masked_hmac"`, and
the two exact synthetic values
`aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` and
`bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb`.
Their exact CJSON bytes are, respectively:

```text
{"display_kind":"masked_unknown","identity_version":"OpponentPublicOrderIdentityV1","private_identity_kind":"masked_hmac","private_identity_value":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","report_id":"a1b2c3d4-e5f6-4a7b-8c9d-a1b2c3d4e5f6"}
{"display_kind":"masked_unknown","identity_version":"OpponentPublicOrderIdentityV1","private_identity_kind":"masked_hmac","private_identity_value":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","report_id":"a1b2c3d4-e5f6-4a7b-8c9d-a1b2c3d4e5f6"}
```

The exact CJSON bytes sort `a` before `b`, yielding
`opponent_000001,opponent_000002`; the DTO contains neither private value.

Masked display labels follow the resulting public order:

```text
Физическое лицо 1
Физическое лицо 2
...
```

Unknown/conflicting type:

```text
Сторона скрыта 1
Сторона скрыта 2
...
```

Properties:

- same verified natural party inside one report remains distinguishable across cases;
- different verified parties do not merge except negligible full-HMAC collision;
- ordinals are not stable across reports;
- token/digest itself is never public;
- identical display name never causes grouping;
- masking is identical in DTO, SSR, embedded state, tooltips and accessibility text.

### 16.4. Telemetry/Webvisor

H2 pages do not load Webvisor or third-party session recording.

Allowed telemetry contains only closed UI event and aggregate presentation fields, for example:

```text
view_id
event_id
viewport_bucket
interaction_kind
coverage_state
```

Forbidden telemetry fields include report ID, INN/OGRN/KPP, slug, company name, case key/number, party identity/token/name, amount, currency, address and narrative text.

At H2 activation, navigation from an existing SPA document that loaded Webvisor performs a full navigation to the H2 SSR document, ensuring the recorder is not retained.

## 17. AI narrative contract

### 17.1. Output

Public narrative contains:

- one description of 400–700 Unicode scalar characters;
- zero to two chart comments;
- no human moderation;
- no admin approval;
- no second AI validator or repair call.

Length is measured after:

1. Unicode NFC normalization;
2. CR/LF normalization;
3. trimming;
4. collapsing repeated whitespace to one space.

Spaces and punctuation count.

### 17.2. Structured envelope

AI does not return public prose or numbers. It returns a closed render plan:

```text
description_plan:
  intro_template_id
  statement_ids[]
  connector_ids[]
chart_comments[0..2]:
  chart_id
  comment_template_id
  evidence_ids[]
```

Input contains only:

- versioned allowlisted evidence IDs;
- neutral categorical relations;
- availability/limitation states;
- business-activity labels approved for public use;
- no company/case/party identifiers;
- no address or manager/owner name;
- no raw values;
- no scoring/signals/verdict.

Exact numbers and display values are inserted only by deterministic local renderer from immutable Chart Facts.

### 17.3. Automatic validation

A generated result is publishable only if all checks pass:

1. exact JSON schema, recursively extra-forbid;
2. exact artifact context and versions;
3. every statement/template/evidence ID exists;
4. every evidence ID belongs to the same report/snapshot;
5. unit/privacy/provider gates permit the selected statement;
6. no score, verdict, probability, advice or unsupported comparison;
7. no duplicate chart comment and at most two comments;
8. referenced chart is visible and supported;
9. final rendered description is 400–700 characters;
10. each comment is a single allowlisted rendered statement;
11. two independent local renders are byte-identical;
12. rendered artifact hash matches stored hash.

Invalid output receives no repair/second AI call.

### 17.4. Artifact identity

Immutable internal key contains:

```text
report_id
snapshot_hash
chart_facts_hash
evidence_registry_version
statement_catalog_version
template_catalog_version
prompt_version
json_schema_version
policy_version
  renderer_version
  gateway_profile_version
  fallback_catalog_version
  resolved_model_version
```

Artifact stores:

- raw structured model output in private artifact storage only;
- validated render plan;
- rendered text/comments;
- validation result/codes;
- created time;
- immutable artifact hash.

Raw model output is never in public DTO.

Publication pin binds exact artifact key or exact fallback version. New artifact does not replace pinned text automatically.

### 17.5. Generation and fallback

- Generation occurs only in a separate worker/write path.
- Public GET, SSR, crawler and React takeover never enqueue or call Gateway.
- One budget reservation permits at most one paid model dispatch.
- Definitive pre-dispatch failure may retry local scheduling without a model call.
- Ambiguous timeout is not automatically retried.
- Schema/policy/evidence failure immediately selects fallback.
- Missing, stale, invalid, unpinned or unavailable artifact selects deterministic fallback.
- Every fallback trigger binds and renders the same immutable 691-scalar
  `fallback_profile_any_v1`; facts, limitations and coverage never change its
  bytes.
- Page availability never depends on AI availability.
- AI artifact never mutates snapshot, signals or scoring.

## 18. SSR, embedded DTO, CSP and XSS

### 18.1. Narrow H2 exception

H1 prohibition on hidden JSON remains unchanged.

Only H2 SSR may emit one embedded projection:

```html
<script
  id="company-public-h2-state"
  type="application/json"
  nonce="{per-response-nonce}"
>
  {strict sanitized CompanyPublicH2Response}
</script>
```

No raw/private/provider JSON or second state object is permitted.

### 18.2. Script-safe serialization

Canonical serializer:

- emits UTF-8 without BOM;
- has deterministic key/list order;
- rejects unpaired surrogates;
- escapes JSON control characters;
- escapes `<` as `\u003C`;
- escapes `>` as `\u003E`;
- escapes `&` as `\u0026`;
- escapes U+2028/U+2029;
- makes literal `</script>` impossible;
- enforces DTO/string/array size limits before rendering.

Required negative fixtures include:

- `</script><script>`;
- `<`, `>`, `&`;
- `<!--`;
- quotes and backslashes;
- U+0000–U+001F;
- U+2028/U+2029;
- combining Unicode;
- unpaired surrogates;
- very long names/labels/limitations;
- unknown private keys.

### 18.3. Takeover

1. SSR resolver selects one exact H2 pin/report/projection.
2. SSR visible HTML and embedded DTO use that same in-memory projection.
3. JS-disabled HTML contains every factual section.
4. Client reads the one embedded DTO once.
5. Strict parser reconstructs an allowlisted object.
6. Client validates contract, report ID, canonical path and projection digest.
7. Hydration/takeover performs no factual GET.
8. Mismatch leaves safe SSR facts unchanged and disables interactive enhancement.
9. No provider, Gateway, AI, queue, worker or DB write is reachable.
10. SPA navigation into an active H2 card performs a full canonical document navigation.

### 18.4. H2 security headers

H2 SSR uses a per-response cryptographic nonce and a policy equivalent to:

```text
default-src 'none';
base-uri 'none';
object-src 'none';
frame-ancestors 'none';
form-action 'self';
img-src 'self' data:;
font-src 'self';
style-src 'self';
script-src 'self' 'nonce-{nonce}';
connect-src 'self';
manifest-src 'self';
```

Also required:

```text
X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

No `unsafe-inline`, third-party analytics or recorder script is allowed.

External KAD links require:

```text
target="_blank"
rel="noopener noreferrer"
```

and an evidence-backed HTTPS host allowlist. Without the gate the case number remains text.

## 19. CTA and neutral actions

### 19.1. Exact primary CTA

Heading:

```text
Вам задолжали?
```

Desktop supporting copy:

```text
Запустите процесс взыскания прямо сейчас: создайте досудебную претензию онлайн!
```

Button:

```text
Создать претензию
```

CTA is fixed product copy and never generated by AI.

Target:

```text
/claims?report_id={exact displayed report_id}
```

Click:

- does not create a Claim;
- does not call provider;
- does not choose latest report;
- does not show login/prefill choice;
- opens the existing anonymous Claims entry;
- Claim creation remains the existing explicit form action.

### 19.2. Existing bottom actions

Exact order and labels:

```text
Проверить другую компанию -> /
Подготовить претензию -> /claims?report_id={exact displayed report_id}
```

Primary CTA and `Подготовить претензию` use the same Claims target.

### 19.3. Responsive placement

Breakpoints:

| Range | CTA placement |
|---|---|
| `>=1200px` | Right sticky rail |
| `768–1199px` | Fixed bottom tablet bar |
| `320–767px` | Fixed bottom mobile bar |

Desktop:

- page grid uses flexible main column, `320px` rail and `32px` gap;
- rail sticky top `24px`;
- supporting paragraph visible.

Tablet:

- heading and button in a horizontal bar;
- supporting paragraph omitted;
- button does not create horizontal page scroll.

Mobile:

- heading and full-width button stack;
- supporting paragraph omitted;
- safe-area inset included.

Tablet/mobile server HTML contains a noninteractive `aria-hidden inert` in-flow reserver with the same responsive sizing as the fixed bar. It contains no focusable link. This reserves exact height under wrapping, JS-disabled rendering and 200% zoom. Hydration may additionally verify size but is not the source of correctness.

### 19.4. CTA colors and states

| State | Background | Foreground | Contrast |
|---|---|---|---:|
| Base | `#EE5A2A` | `#111827` | about `5.18:1` |
| Hover | `#F36B3F` | `#111827` | about `5.90:1` |
| Active | `#E65327` | `#111827` | about `4.76:1` |
| Disabled | `#F6C6B5` | `#5A2A1B` | about `7.67:1` |

Focus uses:

- inner `2px` white separation ring;
- outer `3px #111827` ring;
- no focus removal.

`#EE5A2A` is CTA accent, not a positive/negative/verdict chart color.

## 20. Wireframe contract

Tracked files:

```text
docs/development/wireframes/iteration-19-company-card-v2/desktop.svg
docs/development/wireframes/iteration-19-company-card-v2/tablet.svg
docs/development/wireframes/iteration-19-company-card-v2/mobile.svg
```

Required frames:

| File | Viewport |
|---|---:|
| `desktop.svg` | `1440px` |
| `tablet.svg` | `1024px` |
| `mobile.svg` | `390px` |

Each SVG must show, in order:

1. status/identity and immutable report date;
2. AI description/fallback;
3. in-page navigation;
4. requisites;
5. F1;
6. F2;
7. F3;
8. F4;
9. F5;
10. A1;
11. A2;
12. A3;
13. A4;
14. A5;
15. sources/limitations;
16. neutral actions;
17. primary CTA in its breakpoint-owned placement.

Each SVG contains review callouts for:

- long identity/address/party label;
- empty/missing;
- partial collection and exact returned/total;
- negative/mixed-sign/zero denominator;
- large-N `показано N из M`;
- fixed-bar safe-area/reserved space;
- focus/hover/touch affordance;
- no content overlap.

Wireframes use synthetic names and values only. They do not embed the supplied raster/PDF and do not contain production identifiers.

Decorative palette, typography and final chart art remain iteration 22–24 work. Only CTA accent, placement, ordering and semantic states are normative.

## 21. Accessibility contract

Every chart view provides:

- semantic heading and visible scope/period;
- textual summary;
- data table/list fallback in DOM;
- SVG `role="img"` with `aria-labelledby`;
- mouse hover, keyboard focus and touch disclosure;
- no tooltip-only fact;
- deterministic focus order;
- at least `12px` chart labels;
- bounded wrapping/ellipsis with full accessible text;
- no page-wide horizontal scroll at `320px`;
- reduced-motion behavior;
- patterns/labels in addition to color;
- neutral colors, not red/green verdict mapping.

At 200% zoom:

- CTA does not cover content;
- controls remain reachable;
- table scroll stays local;
- long strings wrap with `overflow-wrap:anywhere`;
- no fixed pixel-height content clipping.

## 22. Evidence artifacts and gate model

Tracked artifacts:

```text
docs/development/evidence/iteration-19-company-card-v2/provider-field-manifest-v1.md
docs/development/evidence/iteration-19-company-card-v2/finance-unit-evidence-v1.md
docs/development/evidence/iteration-19-company-card-v2/arbitration-contract-evidence-v1.md
docs/development/decisions/iteration-19-company-card-v2-architecture.md
docs/development/decisions/iteration-19-company-card-v2-privacy.md
```

Gate axes:

```text
schema_gate:
  unverified | verified | rejected

semantic_gate:
  unverified | verified | rejected

privacy_gate:
  unreviewed | approved_transform | prohibited

operational_gate:
  disabled | approved

implementation_state:
  blocked | planned | implemented
```

A field may be public only when every required axis is satisfied and its feature flag is enabled. Feature flags cannot override evidence.

Current mandatory states:

| Capability | Current state |
|---|---|
| Existing core identity/address | Reused approved H1 contract |
| Status/effective date | Unverified, hidden |
| Legal-form dictionary | Unverified, hidden |
| Charter-capital unit | Unverified, hidden |
| Tax modes/OKVED/owners/workers/tax authority | Per-field unverified, hidden |
| Manager safe composition | Privacy transform approved; provider semantics still gated |
| Contacts | Prohibited |
| Finance statement values | Shape observed |
| DataNewton finance thousand-ruble unit | `UNVERIFIED / BLOCKED` |
| Arbitration pagination completeness | Unverified |
| `party_result` scope/semantics | Unverified |
| Party entity type | Unverified |
| Currency mapping | Unverified |
| KAD host/path | Unverified |
| Natural opposing-party masking | Approved contract, implementation pending |
| AI artifact | Approved contract, implementation pending |
| H2 embedded DTO exception | Approved contract, implementation pending |

Ignored raw files are never the only tracked evidence. Synthetic fixtures prove parser expectations only, not vendor semantics.

## 23. Finance evidence matrix pass/fail

A separate implementation stage may promote `datanewton_finance_thousand_rub_v1`.

Preconditions:

- explicit live-stage authorization;
- exactly 3–5 Russian legal entities with public accounting statements;
- private ignored mapping `C01..C05 -> INN`;
- finance dataset only;
- no production DB;
- no contacts or natural-person data;
- maximum five DataNewton finance calls;
- FNS ГИР БО as primary comparator;
- raw responses remain outside git.

The only normative tracked row is:

```text
FinanceEvidenceCellV1:
  evidence_session_id: opaque non-PII ID
  pseudonym: "C01" | "C02" | "C03" | "C04" | "C05"
  form_id: "balance" | "financial_results"
  line_code: one of the exact twelve approved form/code pairs
  reporting_year: integer 1900..2100
  datanewton_presence: "missing" | "zero" | "nonzero"
  fns_presence: "missing" | "zero" | "nonzero"
  fns_okei_state:
    "accepted_384" | "accepted_385" |
    "rejected_missing" | "rejected_ambiguous" | "rejected_other"
  fns_okei_code: 384 | 385 | null
  comparison_outcome:
    "exact_nonzero" | "exact_zero" | "exact_missing" |
    "mismatch" | "unavailable" | "rejected_okei"
  scale_outcome:
    "direct_thousand" | "exact_million_to_thousand" | "not_applicable"
  datanewton_raw_sha256: 64 lowercase hex
  fns_document_sha256: 64 lowercase hex
  provider_shape_version: Contract/version/code
  collection_tool_version: Contract/version/code
  collected_at: UTC timestamp
```

Closed invariants:

- `accepted_384` iff `fns_okei_code=384` and
  `scale_outcome=direct_thousand`;
- `accepted_385` iff `fns_okei_code=385` and
  `scale_outcome=exact_million_to_thousand`, with exact Decimal
  `official_thousand_decimal = official_decimal * 1000`;
- every `rejected_*` state requires null code,
  `comparison_outcome=rejected_okei` and `scale_outcome=not_applicable`;
- accepted states forbid `rejected_okei`; rejected rows never prove the unit;
- raw missing/ambiguous/other OKEI tokens are not stored in git.

Required comparison covers all twelve approved `(form,line_code)` pairs, the
latest two common reporting years where legally available and both forms.
Missing is compared as missing and explicit zero as zero. There is no
tolerance, rounding or inferred scale. Every form has at least one direct
non-zero accepted-384 match; accepted-385 rows may supplement but never replace
that direct evidence.

Pass requires 3–5 completed pseudonymized companies, at least three companies
with two common years across both forms, exact equality for every comparable
accepted cell after the closed normalization above, no contradictory field or
mixed/form-specific scale, a bound endpoint/filter/shape scope, and reproducible
field-level evidence. Aggregate counts without these rows cannot pass.

Any mismatch, ambiguity, insufficient coverage, drift or failed comparator yields:

```text
gate = rejected or unverified
finance monetary capability = blocked
```

The tracked artifact contains only pseudonym, form, code/year coverage, match counts, observed scale and pass/fail reason. It contains no raw values, identifiers, URLs containing identifiers, provider payload or credentials.

Если stage не выполняется, iteration 19 может завершить documentation scope с gate `UNVERIFIED`, но iteration 20 сохраняет соответствующий blocker, а iteration 23 не стартует.

## 24. Inputs to iterations 20–25

### Iteration 20 — Backend foundation

Must implement:

- separate exact parsers/serializers for v1/v2/v3;
- default-off v3 write profile and pending-version fencing;
- no global v3 switch;
- H2 projection and H2 publication registry;
- server-side presentation assignment contract;
- bounded pagination and sanitized v3 case persistence;
- pure versioned Chart Facts;
- per-page provenance without raw;
- Claims v3 exact-report compatibility;
- H1/legacy compatibility;
- evidence-gated fields only.

Unknown fields stay null/hidden. If mandatory gates remain unverified, iteration 20 remains blocked rather than guessing or silently reducing evidence requirements.

### Iteration 21 — AI narrative

Must implement the task-specific artifact/job/budget contract, one paid dispatch maximum, automatic validation and deterministic fallback. No read-path Gateway call.

### Iteration 22 — Page shell

Must implement hero, narrative, requisites, sources/actions, desktop rail, tablet/mobile fixed bar, H2 SSR, CSP and single embedded DTO. H1 remains production default.

### Iteration 23 — Finance charts

Cannot start without active `datanewton_finance_thousand_rub_v1`. Implements F1–F5 from backend Chart Facts only.

### Iteration 24 — Arbitration charts

Cannot start without complete pagination, `party_result`, currency, entity-type and privacy gates. Implements A1–A5 with exact partial/top-20 behavior.

### Iteration 25 — QA/rollout

Must verify:

- full backend/Gateway/frontend/browser matrix;
- H1/H2 coexistence;
- SSR/DTO/client semantic parity;
- Webvisor/telemetry absence;
- Claims target;
- no paid/provider call from reads/crawlers/tests;
- 320/390/768/1024/1199/1200/1440 responsive matrix;
- keyboard/touch/200% zoom/reduced motion;
- staged assignment and rollback.

Only iteration 25, after successful QA and explicit owner approval, may activate H2 assignment. H1 is production default through iteration 24.

## 25. Acceptance criteria

Iteration 19 is accepted when:

1. Successor is exactly `/public-h2` and `company_public_h2_v1`.
2. H1 route/DTO/reader remain unchanged.
3. New Card-v2 writer is exact v3 and default-off.
4. v1/v2 remain immutable/read-only in Card-v2 path.
5. H1/v3 compatibility and projection-specific pins are explicitly solved.
6. Every visible field has a source, gate, missing behavior and privacy decision.
7. Unknown provider paths are `NOT_VERIFIED`, never invented.
8. Finance periods, gaps, zero, signed values, denominator and units are deterministic.
9. All ten views have exact formulas, denominators and detail populations.
10. Arbitration pagination, caps, dedup, role, outcome, currency and calendar behavior are closed.
11. Top-20 is per view/per currency, deterministic, with exact `N/M`.
12. Natural/unknown opponents are masked consistently and legal INN stays internal.
13. Contacts and personal identifiers cannot enter public surfaces.
14. AI output is automatically validated, artifact-pinned and never called on read.
15. Invalid/missing AI always gives deterministic fallback without human/second AI.
16. H2 uses one script-safe DTO, CSP and no second factual GET.
17. CTA exact copy/path/layout/states are fixed.
18. Three SVGs show all views and required edge states without overlap.
19. Finance evidence is either exact-pass or explicitly `UNVERIFIED/BLOCKED`.
20. No runtime file, Roadmap, raw evidence, secret or production identifier changes.
21. Documentation checks and independent review pass.
22. Exactly one `FinanceEvidenceCellV1` OKEI state/code schema exists.
23. Collection, calendar and zero-year proof are independently represented in
    persisted, Chart Facts and public arbitration shapes.
24. `fallback_catalog_version` fences `generation_key`; the only v1 fallback
    and exact `FallbackIdentityV1` golden are immutable.
25. F2/F3/F4 geometry is keyed/per-series and v3 lexical Decimal transport is
    explicitly blocked until lossless finite parsing is implemented and tested.
26. HMAC/private identity/public ordinal encodings are closed schemas with
    exact synthetic bytes, patterns, bounds and golden vectors.

## 26. Normative closed leaf-level H2 DTO

Sections 8 and 10–15 give the product topology. This section is the normative
serialization contract and supersedes any shorthand that is less specific.

### 26.1. Universal scalar and size rules

All strings are Unicode NFC before validation. Empty or whitespace-only strings
are invalid unless a field is explicitly nullable. No object accepts an unknown
key.

```text
Schema/member identifier: ASCII [a-z][a-z0-9_]{0,63}
Contract/version/code: 1..64 ASCII characters
Human label: 1..256 Unicode scalar values
Company/person-safe display name: 1..512 Unicode scalar values
Address: 1..1024 Unicode scalar values
Limitation text: 1..512 Unicode scalar values
Narrative description: 400..700 Unicode scalar values
Narrative chart comment: 1..280 Unicode scalar values
Case number: 1..128 Unicode scalar values
Same-origin path / allowed external URL: 1..2048 ASCII characters
ISO date: exact YYYY-MM-DD
UTC timestamp: RFC 3339, seconds required, optional fractional seconds,
               exact Z suffix, no numeric offset
UUID: lowercase canonical 8-4-4-4-12
SHA-256: 64 lowercase hexadecimal characters
Integer: JSON integer, no float/exponent/coercion
Decimal: canonical string defined in section 27
```

Maximum serialized sizes:

```text
canonical public DTO bytes, including projection_digest: 524288
script-safe embedded JSON bytes: 786432
individual source/limitation arrays: limits below
H2 state script elements: exactly 1
```

The byte limits use UTF-8 bytes, not characters. Equality with the limit is
accepted; one byte over is rejected as `public_projection_too_large`. The
projection is never truncated.

### 26.2. Root

```text
CompanyPublicH2Response:
  contract_version: literal "company_public_h2_v1"
  projection_digest: SHA-256
  report_id: UUID
  report_version: enum "1" | "2" | "3"
  snapshot_capability: enum "legacy_read_only" | "card_v2"
  projection_scope:
    enum "active_publication" | "staged_publication" | "latest_unpublished"
  canonical_path: same-origin exact canonical company path
  indexable: boolean
  checked_at: UTC timestamp
  checked_date: ISO date
  checked_date_display: Human label
  identity: PublicH2Identity
  narrative: PublicH2Narrative
  block_order: exactly the 16 unique literals from section 8.2, in that order
  blocks: PublicH2Blocks
  coverage: exactly 13 PublicH2CoverageItem objects
  sources: 1..3 PublicH2SourceItem objects
  limitations: 0..128 PublicH2Limitation objects
  actions: exactly 2 PublicH2Action objects
  breadcrumbs: exactly 2 PublicH2Breadcrumb objects
  primary_claim_cta: PublicH2ClaimCta
```

Cross-field invariants:

- `report_version="3"` iff `snapshot_capability="card_v2"`;
- versions `"1"|"2"` require `legacy_read_only` and `indexable=false`;
- only `active_publication` may be indexable;
- `indexable=true` requires the publication policy in section 30;
- `checked_date` is the Moscow date of `checked_at`;
- every non-available block has at least one linked limitation code;
- every limitation code referenced by coverage exists exactly once in
  `limitations`;
- `canonical_path`, breadcrumbs and actions contain the same normalized INN
  and displayed `report_id` where applicable;
- list order is contract order, never map/provider arrival order.

### 26.3. Identity and requisites

```text
PublicH2Identity:
  display_name: Company display name
  legal_full_name: Company display name
  short_name: Company display name | null
  inn: exact 10 or 12 ASCII digits
  ogrn: exact 13 or 15 ASCII digits | null
  kpp: exact 9 ASCII digits | null
  registration_date: ISO date | null
  dissolution_date: ISO date | null
  status: PublicH2Status | null

PublicH2Status:
  state: enum "active" | "inactive" | "other"
  code: Contract/version/code
  label: Human label
  effective_date: ISO date | null

PublicH2Requisites:
  legal_form: PublicLabeledCode | null
  address: PublicH2Address | null
  charter_capital: PublicCharterCapital | null
  tax_modes: PublicTaxMode[0..8]
  primary_activity: PublicActivity | null
  additional_activities: PublicActivity[0..20]
  managers: PublicManager[0..20]
  owners: PublicOwner[0..50]
  employees: PublicEmployees | null
  tax_authority: PublicLabeledCode | null

PublicLabeledCode:
  code: Contract/version/code
  label: Human label

PublicH2Address:
  display: Address
  region: Human label | null
  is_inaccuracy: boolean | null

PublicCharterCapital:
  source_decimal: CanonicalDecimal
  unit_id: Contract/version/code
  display_exact: Human label
  unit_policy_version: Contract/version/code

PublicTaxMode:
  mode_id:
    "common_mode" | "usn_sign" | "ausn_sign" | "envd_sign" |
    "eshn_sign" | "npd_sign" | "psn_sign" | "srp_sign"
  label: Human label
  applies: literal true
  effective_date: ISO date | null

PublicActivity:
  code: 2..16 ASCII digits/dots
  label: Human label
  is_primary: boolean
  effective_date: ISO date | null

PublicManager:
  name: Company/person-safe display name
  role: Human label
  appointed_at: ISO date | null
  is_inaccuracy: boolean | null

PublicOwner:
  display_name: Company/person-safe display name
  owner_type: enum "person" | "organization" | "state"
  share_percent_decimal: CanonicalDecimal | null
  share_display: Human label | null
  effective_date: ISO date | null

PublicEmployees:
  count: integer 0..999999999
  period: Human label
  effective_date: ISO date | null
```

`tax_modes`, activities, managers and owners are sorted by their closed
catalog/order keys and then safe NFC display strings. Personal identifiers are
not members of any public type.

`charter_capital` is emitted only when the separate
`charter_capital_unit` evidence gate binds amount, currency/scale and policy
version; the finance-thousand-ruble gate is not a substitute. Tax mode is
emitted only for a verified true source leaf; absence is unknown, not false.

### 26.4. Narrative, coverage, sources and navigation

```text
PublicH2Narrative:
  mode: enum "artifact" | "deterministic_fallback"
  renderer_version: Contract/version/code
  description: Narrative description
  statement_ids: 1..16 unique Contract/version/code values
  comments: PublicH2ChartComment[0..2]
  render_digest: SHA-256

PublicH2ChartComment:
  chart_id: one of F1..F5/A1..A5 view IDs
  text: Narrative chart comment
  evidence_ids: 1..8 unique Contract/version/code values

PublicH2CoverageItem:
  block_id: one of:
    requisites, narrative,
    finance_f1..finance_f5,
    arbitration_a1..arbitration_a5,
    sources_limitations
  state: coverage enum from section 8.4
  population_scope:
    enum "not_applicable" | "complete_collection" | "returned_slice"
  total: integer >=0 | null
  returned: integer >=0 | null
  eligible: integer >=0 | null
  limitation_codes: 0..16 unique limitation codes

PublicH2SourceItem:
  dataset: enum "counterparty" | "finance" | "arbitration"
  received_at: UTC timestamp
  effective_at: ISO date | null
  period: Human label | null
  normalization_version: Contract/version/code
  evidence_version: Contract/version/code

PublicH2Limitation:
  code: unique Contract/version/code
  block_id: coverage block ID | null
  field_id: Schema/member identifier | null
  message: Limitation text

PublicH2Action:
  action_id: enum "check_another_company" | "prepare_claim"
  label: exact fixed product label
  path: same-origin path

PublicH2Breadcrumb:
  label: Human label
  path: same-origin path
  current: boolean

PublicH2ClaimCta:
  action_id: literal "prepare_claim"
  heading: literal "Вам задолжали?"
  desktop_copy:
    literal "Запустите процесс взыскания прямо сейчас: создайте досудебную претензию онлайн!"
  button_label: literal "Создать претензию"
  path: exact "/claims?report_id={root.report_id}"
```

Source order is `counterparty`, `finance`, `arbitration`. Limitations sort by
`(block_order_index, field_id nulls first, code)`. Actions are exactly
`check_another_company`, then `prepare_claim`. Breadcrumbs are root with
`current=false`, then canonical company with `current=true`.

### 26.5. Money, geometry and detail primitives

```text
CanonicalDecimal:
  canonical decimal string from section 27

PublicFinanceMoney:
  source_thousand_decimal: CanonicalDecimal
  rub_decimal: CanonicalDecimal
  million_decimal: CanonicalDecimal
  display_exact: Human label
  display_compact: Human label
  unit_id: literal "RUB"
  unit_policy_version: literal "datanewton_finance_thousand_rub_v1"

PublicCaseAmount:
  source_decimal: CanonicalDecimal
  source_currency_id: Contract/version/code
  display_exact: Human label

PublicChartAxis:
  axis_min_decimal: CanonicalDecimal
  axis_max_decimal: CanonicalDecimal

PublicChartInterval:
  start_ratio_decimal: CanonicalDecimal
  end_ratio_decimal: CanonicalDecimal

PublicChartPoint:
  ratio_decimal: CanonicalDecimal

PublicDetailScope:
  population_scope: enum "complete_collection" | "returned_slice"
  source_total: integer >=0 | null
  rows_received: integer >=0
  eligible_total: integer >=0
  shown: integer 0..20
  cap: literal 20
  label: Human label
```

`shown = min(eligible_total,20)` for nonempty detail views. A zero eligible
population has `shown=0` and an empty details array. Geometry bounds must
contain zero whenever any signed input is negative.

All derived chart math uses `company_card_chart_math_v1`. Inputs are finite
`Decimal`; binary floats, NaN/infinity and implicit context precision are
forbidden. Exact addition/subtraction and powers-of-ten multiplication do not
round. Division/ratio uses precision 34, scale 6 and `ROUND_HALF_UP`; canonical
strings remove trailing fractional zeros. For a positive F2 denominator,
shares are `component / denominator * 100`; after quantization the residual
`100 - sum(shares)` goes to the greatest absolute unrounded remainder, with
fixed tie order `equity`, then `debt`. A2/A3 use the same residual algorithm
with their fixed DTO category order. A zero denominator yields null percentages.
Every interval uses the keyed source metric and the common axis; missing,
conflict or prohibited denominator produces null derived geometry, never zero.
F3 multiple/change are computed independently per series from its own first
and last valid points. F5 YoY exists only when current and immediately prior
calendar values are present and the prior value is strictly positive.

### 26.6. F1–F5 exact shapes

```text
PublicF1:
  view_id: literal "finance_f1_liquidity"
  year: integer 1900..2100
  cash_1250: PublicFinanceMoney
  investments_1240: PublicFinanceMoney
  receivables_1230: PublicFinanceMoney
  short_liabilities_1500: PublicFinanceMoney
  available_without_inventory: PublicFinanceMoney
  difference: PublicFinanceMoney
  axis: PublicChartAxis
  segments: exactly 4 PublicFinanceSegment objects in order

PublicFinanceSegment:
  metric_id: closed code-backed metric ID
  value: PublicFinanceMoney
  geometry: PublicChartInterval
```

F1 segments are `1250,1240,1230,1500`. Derived values must equal exact source
Decimal arithmetic.

```text
PublicF2:
  view_id: literal "finance_f2_funding"
  anchor_year: integer 1900..2100
  window_start_year: anchor_year - 6
  periods: exactly 7 PublicF2Period objects, ascending consecutive years

PublicF2Period:
  year: integer
  state: enum "available" | "gap" | "denominator_unavailable"
  equity_1300: PublicFinanceMoney | null
  long_liabilities_1400: PublicFinanceMoney | null
  short_liabilities_1500: PublicFinanceMoney | null
  debt: PublicFinanceMoney | null
  denominator: PublicFinanceMoney | null
  equity_share_decimal: CanonicalDecimal | null
  debt_share_decimal: CanonicalDecimal | null
  mode: enum "stacked_100" | "diverging_signed" | "unavailable"
  axis: PublicChartAxis | null
  geometry_by_metric:
    equity_1300: PublicChartInterval | null
    debt: PublicChartInterval | null
```

All three source values are simultaneously null only for `gap`. `gap` requires
null shares, axis and both keyed geometries. A non-positive denominator keeps
the source money but requires `mode="unavailable"` and null shares, axis and
geometries. A positive denominator requires both shares. Non-negative shares
use `stacked_100` with intervals `[0,equity]` and `[equity,100]`; a signed share
uses `diverging_signed` and each keyed interval runs from zero to its signed
value. Keyed metric leaves never exchange positions. Shares sum exactly to
canonical `100` after the residual rule in section 26.5.

```text
PublicF3:
  view_id: literal "finance_f3_growth"
  anchor_year: integer
  window_start_year: anchor_year - 6
  points: exactly 7 PublicF3Point objects, ascending consecutive years
  revenue_summary: PublicF3SeriesSummary
  assets_summary: PublicF3SeriesSummary

PublicF3SeriesSummary:
  metric_id: enum "revenue_2110" | "assets_1600"
  comparison_start_year: integer | null
  comparison_end_year: integer | null
  multiple_decimal: CanonicalDecimal | null
  change: PublicFinanceMoney | null
  axis: PublicChartAxis | null

PublicF3Point:
  year: integer
  revenue_2110: PublicFinanceMoney | null
  assets_1600: PublicFinanceMoney | null
  revenue_yoy_decimal: CanonicalDecimal | null
  assets_yoy_decimal: CanonicalDecimal | null
  geometry_by_metric:
    revenue_2110: PublicChartPoint | null
    assets_1600: PublicChartPoint | null
```

No line geometry crosses a missing point. Each series independently selects
its earliest and latest valid years. A series with fewer than two valid points
has null comparison years, multiple and change. `multiple_decimal` additionally
requires two strictly positive endpoints; signed `change` requires only two
present endpoints. A gap in one series does not suppress the other series.

```text
PublicF4:
  view_id: literal "finance_f4_profit_per_100"
  year: integer
  revenue_2110: PublicFinanceMoney
  gross_2100: PublicFinanceMoney
  operating_2200: PublicFinanceMoney
  net_2400: PublicFinanceMoney
  revenue_per_100_decimal: literal "100" | null
  gross_per_100_decimal: CanonicalDecimal | null
  operating_per_100_decimal: CanonicalDecimal | null
  net_per_100_decimal: CanonicalDecimal | null
  mode: enum "per_100" | "denominator_unavailable"
  axis: PublicChartAxis | null
  geometry_by_metric:
    revenue_2110: PublicChartInterval | null
    gross_2100: PublicChartInterval | null
    operating_2200: PublicChartInterval | null
    net_2400: PublicChartInterval | null
```

Strictly positive revenue requires all four ratios, the common axis and all
four keyed intervals; each interval runs from zero to its ratio. Zero or
negative revenue keeps source money but requires `denominator_unavailable`,
null ratios, null axis and four null keyed geometries.

```text
PublicF5:
  view_id: literal "finance_f5_yearly_table"
  anchor_year: integer
  years: exactly 7 ascending consecutive integers
  rows: exactly 9 PublicF5Row objects in the fixed section-12 order

PublicF5Row:
  metric_id: fixed code-backed metric ID
  label: fixed catalog label
  cells: exactly 7 PublicF5Cell objects matching root years

PublicF5Cell:
  year: integer
  value: PublicFinanceMoney | null
  yoy_decimal: CanonicalDecimal | null
```

### 26.7. Arbitration common and safe detail

```text
PublicArbitrationSummary:
  source_total: integer >=0 | null
  rows_observed: integer >=0
  unique_case_count: integer >=0
  malformed_count: integer >=0
  duplicate_identical_count: integer >=0
  duplicate_conflict_count: integer >=0
  collection_complete: boolean
  completion_reason: closed enum from section 31
  calendar_complete: boolean
  calendar_scope: enum "unverified" | "all_time" | "bounded_interval"
  calendar_start_year: integer 1900..2100 | null
  calendar_end_year: integer 1900..2100 | null
  calendar_evidence_version: Contract/version/code | null
  observed_start_year: integer 1900..2100 | null
  observed_end_year: integer 1900..2100 | null
  unknown_year_count: integer >=0
  zero_years_proven: boolean

PublicSafeCaseDetail:
  case_public_id: Schema/member identifier
  case_number: Case number | null
  year: integer 1900..2100 | null
  role: enum "plaintiff" | "respondent" | "other" | "unattributed"
  outcome: enum "won" | "lost" | "returned" | "unknown"
  result_detail: Human label | null
  amount: PublicCaseAmount | null
  start_date: ISO date | null
  update_date: ISO date | null
  days_to_last_update: integer >=0 | null
  instance_count: integer >=0 | null
  courts: Human label[0..10]
  opponents: PublicSafeOpponent[0..20]
  public_case_url: allowed HTTPS URL | null

PublicSafeOpponent:
  opponent_public_id: Schema/member identifier
  display_name: Company/person-safe display name
  display_kind: enum "legal" | "state" | "masked_natural" | "masked_unknown"
```

`case_public_id` and `opponent_public_id` are report-scoped public ordinals with
the exact section-31 encoding, never provider IDs, private identifiers or HMAC
values.

### 26.8. A1–A5 exact shapes

```text
PublicA1:
  view_id: literal "arbitration_a1_activity"
  summary: PublicArbitrationSummary
  displayed_start_year: integer | null
  displayed_end_year: integer | null
  buckets: PublicA1YearBucket[0..11]
  all_time_case_count: integer >=0

PublicA1YearBucket:
  year: integer | null
  plaintiff_count: integer >=0
  respondent_count: integer >=0
  other_count: integer >=0
  unattributed_count: integer >=0
  total_count: integer >=0
  role_details: exactly 4 PublicRoleDetail objects in role order

PublicRoleDetail:
  role: role enum
  scope: PublicDetailScope
  cases: PublicSafeCaseDetail[0..20]
```

The optional nullable unknown-year bucket is last and may be the eleventh
bucket. For every ordinary-year bucket, the four role counts sum to
`total_count`; `all_time_case_count` equals the sum of all ordinary-year and
unknown-year bucket totals. If there is no verified-year case,
`displayed_start_year` and `displayed_end_year` are null and A1 emits no
arbitrary ordinary-year bucket.

Otherwise choose the candidate interval as follows: use
`calendar_start_year..calendar_end_year` only when
`summary.zero_years_proven=true` and `calendar_scope="bounded_interval"`; for
`calendar_scope="all_time"`, and whenever zero proof is absent, use
`observed_start_year..observed_end_year`. If the inclusive candidate span is at
most 10 years, display all of it; if it is greater than 10, display the most
recent 10 years ending at the candidate end. The chosen endpoints are exactly
`displayed_start_year` and `displayed_end_year`.

Only with zero proof may A1 fill zero buckets inside this chosen interval.
Without zero proof it emits only observed years inside the interval. The
unknown-year bucket is separate from the interval and does not alter its
bounds. Empty proven data does not invent a current-year bucket.

```text
PublicA2:
  view_id: literal "arbitration_a2_roles"
  summary: PublicArbitrationSummary
  denominator: integer >=0
  bars: exactly 4 PublicCountBar objects in role order

PublicCountBar:
  category_id: role or outcome enum
  count: integer >=0
  percent_decimal: CanonicalDecimal | null
  scope: PublicDetailScope
  cases: PublicSafeCaseDetail[0..20]
```

A2 bar counts sum exactly to denominator. Percent is null iff denominator is
zero; otherwise the unrounded Decimal shares sum to `100`.

```text
PublicA3:
  view_id: literal "arbitration_a3_outcomes"
  summary: PublicArbitrationSummary
  denominator: integer >=0
  bars: exactly 4 PublicCountBar objects in won/lost/returned/unknown order
```

A3 has the same count/percentage invariants as A2.

```text
PublicA4:
  view_id: literal "arbitration_a4_case_amounts"
  summary: PublicArbitrationSummary
  currency_groups: PublicA4CurrencyGroup[0..16]
  missing_amount_count: integer >=0
  missing_currency_count: integer >=0

PublicA4CurrencyGroup:
  source_currency_id: Contract/version/code
  display_currency: Human label
  axis: PublicChartAxis
  case_geometries: PublicA4CaseGeometry[0..20]
  scope: PublicDetailScope
  cases: PublicSafeCaseDetail[0..20]

PublicA4CaseGeometry:
  case_public_id: exact matching case ID
  geometry: PublicChartInterval
```

Currency groups sort by closed currency catalog order. Every listed case has a
non-null amount in that exact currency. A case appears at most once per group;
`case_geometries` has the same order/cardinality as cases and uses the group's
single signed axis.

```text
PublicA5:
  view_id: literal "arbitration_a5_opponents"
  summary: PublicArbitrationSummary
  scope: PublicDetailScope
  groups: PublicA5OpponentGroup[0..20]
  cases_without_safe_opponent: integer >=0
  multi_opponent_case_count: integer >=0

PublicA5OpponentGroup:
  opponent_public_id: Schema/member identifier
  display_name: Company/person-safe display name
  display_kind: opponent display-kind enum
  case_count: integer >=1
  case_scope: PublicDetailScope
  cases: PublicSafeCaseDetail[0..20]
```

Root A5 scope counts eligible groups; nested scope counts cases in that group.
The same case may occur in more than one group, and the explicit
`multi_opponent_case_count` limitation is then required.

### 26.9. Blocks and nullability

```text
PublicH2Blocks:
  requisites: PublicH2Requisites
  finance_f1: PublicF1 | null
  finance_f2: PublicF2 | null
  finance_f3: PublicF3 | null
  finance_f4: PublicF4 | null
  finance_f5: PublicF5 | null
  arbitration_a1: PublicA1 | null
  arbitration_a2: PublicA2 | null
  arbitration_a3: PublicA3 | null
  arbitration_a4: PublicA4 | null
  arbitration_a5: PublicA5 | null
```

`requisites` is always present, even if all optional leaves are null/empty.
Every null chart block requires coverage state other than `available`.
`available` requires a non-null block. `available_empty` may use a non-null
zero-population arbitration block, but never a synthetic zero from missing or
failed data.

## 27. Cross-language projection digest and script-safe bytes

### 27.0. Lossless v3 source Decimal transport

`company_card_source_decimal_v1` applies to every v3 monetary source leaf:
finance values, arbitration `amount` and charter-capital amount. It accepts
only a JSON number lexeme captured from response bytes before binary-float
coercion, or a JSON string. Boolean is forbidden. The complete lexeme/string must match
`-?(0|[1-9][0-9]*)(\.[0-9]+)?`; exponent, plus, comma, whitespace, leading or
trailing decimal point, NaN and Infinity are forbidden. Maximum ASCII lexeme
length is 128, significant digits 96 and fractional digits 32.

The accepted lexeme is converted directly to `Decimal`, must be finite, and is
stored as a canonical exact string; negative zero canonicalizes to `"0"` and
trailing fractional zeros are removed only from canonical representation.
Python `float` received after ordinary `response.json()` coercion is rejected
for v3 as `decimal_transport_lossy`. Source add/subtract and powers-of-ten
multiplication do not round; only division/ratio uses
`company_card_chart_math_v1` precision 34, scale 6 and `ROUND_HALF_UP`.
Legacy v1/v2 parsing and H1 remain unchanged.

Current runtime proves only parser shape and creation of Decimal-like values
after existing JSON coercion; it does not prove preservation of the source
number lexeme. Therefore `finance_decimal_transport`,
`arbitration_decimal_transport` and `charter_capital_decimal_transport` are
each `UNVERIFIED/BLOCKED`. Neither finance unit nor v3 monetary charts, A4
amount display/geometry, or charter capital activates until lexical ingestion
and finite/precision negative tests pass. Legacy H1/v1/v2 behavior is unchanged.

### 27.1. Canonical JSON profile `company_public_h2_cjson_v1`

The digest does not use Python `json.dumps` defaults, JavaScript
`JSON.stringify` defaults or locale behavior. Both implementations follow this
language-neutral profile:

1. Validate/reconstruct the closed DTO first.
2. Normalize every key and string value to Unicode NFC; reject normalization
   that makes two object keys equal.
3. Reject unpaired UTF-16 surrogates and non-Unicode scalar values.
4. JSON values are only object, array, string, boolean, null and integer.
   Decimal/UUID/date/time/hash values remain validated strings.
5. Object keys are sorted by Unicode scalar value sequence. Current schema keys
   are ASCII, making this byte-identical to ascending UTF-8 order.
6. Array order is preserved exactly.
7. Integers use grammar `0|[1-9][0-9]*`; negative integers are allowed only for
   explicitly signed integer fields, of which H2 v1 has none. `-0`, plus,
   decimal point and exponent are forbidden.
8. Canonical Decimal grammar is
   `-?(0|[1-9][0-9]*)(\.[0-9]*[1-9])?`.
   Decimal zero is exactly `"0"`; plus, exponent, leading zero, `-0`, trailing
   fractional zero and a bare decimal point are forbidden.
9. JSON strings escape `"` as `\"`, backslash as `\\`, and every U+0000–U+001F
   as lowercase `\u00xx`. Slash is not escaped. All other Unicode scalars,
   including `<`, `>`, `&`, U+2028 and U+2029, remain literal UTF-8.
10. Separators are one byte `,` and `:` with no whitespace.
11. The document has no BOM, prefix, suffix or trailing newline.

### 27.2. Digest

To calculate:

1. Remove the `projection_digest` member entirely, not as null/empty.
2. Serialize the remaining validated DTO with
   `company_public_h2_cjson_v1`.
3. Hash those canonical UTF-8 bytes with SHA-256.
4. Encode lowercase hexadecimal.
5. Insert the result as `projection_digest`.

The canonical bytes without the digest are the only digest input.

### 27.3. Script-safe serialization

Embedded bytes are a separate representation:

1. Start from the complete DTO including the verified digest.
2. Use the same key order, integer/Decimal rules and separators.
3. Apply the canonical escaping plus:
   - `<` → `\u003C`;
   - `>` → `\u003E`;
   - `&` → `\u0026`;
   - U+2028 → `\u2028`;
   - U+2029 → `\u2029`.
4. Emit no whitespace/newline around the JSON inside the script element.

Script-safe bytes are not re-hashed. The client parses them, reconstructs
canonical bytes with `projection_digest` excluded and verifies the stored
digest.

### 27.4. Shared golden vectors

Iteration 20/22 must share byte-for-byte Python/TypeScript vectors containing:

- decomposed `e` + combining acute and precomposed `é`, both normalizing to the
  same canonical bytes/digest;
- Cyrillic;
- literal `<>&`;
- U+2028/U+2029;
- quotes, slash and backslash;
- all JSON controls;
- Decimal `0`, negative and fractional values;
- nested keys deliberately supplied out of order;
- digest exclusion/insertion.

Negative vectors include:

- unpaired high/low surrogate;
- `-0`, `01`, `1.0`, exponent and plus Decimal forms;
- float JSON number;
- duplicate key after NFC;
- unexpected root/nested key;
- invalid array order/cardinality;
- canonical DTO `524289` bytes;
- script-safe DTO `786433` bytes.

Fixture ownership is specified in section 35.

## 28. Writer profile, cohort resolution and mixed jobs

### 28.1. H1 constant decision and H2 cohort fence

Legacy `POST /company-reports` has a constant server decision:
`h1_legacy_writer_v2`, `company_public_h1_v1`, report version `"2"`. It never
reads the H2 cohort configuration. The presentation create surface accepts only
an identifier and is H2-only. Its immutable rollout configuration is:

```text
RolloutConfigV1:
  generation: positive integer
  enabled: boolean
  h2_allowlist_inns: sorted unique normalized INNs
  h2_percentage_basis_points: integer 0..10000

H2WriterDecision:
  rollout_config_generation
  normalized_identifier
  presentation_contract: literal "company_public_h2_v1"
  writer_profile: literal "company_card_v2_writer_v3"
  report_version: literal "3"
```

For H2, normalize the INN; if `enabled=false`, select no H2. Otherwise an exact
allowlist match selects H2. For every other INN compute
`n = unsigned_big_endian(SHA-256(UTF-8("company-card-v2-cohort-v1\\0" +
normalized_inn))[0:8]) mod 10000`; select H2 iff
`n < h2_percentage_basis_points`. Malformed/unknown configuration fails closed
to no H2. A no-H2 decision returns `404 company_public_h2_disabled` and creates
no H1 job. Request body/query/headers never choose contract, profile, version or
bucket.

For either endpoint, after its server decision: begin a transaction, lock the
exact subject row, inspect the one active pending job, reuse only an exact
profile/version/contract match, otherwise return deterministic
`409 report_writer_profile_conflict`, and persist the exact decision before
provider work. H2 additionally persists the rollout configuration generation.

Current one-active-job-per-subject unique constraint is retained. Iteration 20
adds nullable `writer_profile`, `presentation_contract` and
`rollout_config_generation`, deploys the dual reader, drains legacy jobs,
backfills remaining legacy H1 rows to the reserved historical generation, and
only then adds non-null/check constraints; it does not create parallel v2/v3
pending jobs.

### 28.2. Worker and finalization fence

Claim, lease, provider orchestration and finalization all carry:

```text
job_id
writer_profile
report_version
presentation_contract
rollout_config_generation
lease_token
fence_generation
```

Every transition compares all fields to the stored pending row. Mismatch:

- releases no data;
- performs no finalization;
- records safe `writer_profile_fence_mismatch`;
- leaves the job recoverable/terminal according to its previous durable state.

Repository finalization additionally requires report/pending
`report_version`, report ID, subject, lifecycle and snapshot hash equality.

### 28.3. Flag-flip matrix

| Existing state | New server decision | Result |
|---|---|---|
| No pending; legacy `POST /company-reports` | H1/v2 | Create v2 pending regardless of H2 assignment |
| No pending; H2 presentation create and gate open | H2/v3 | Create v3 pending |
| Pending H1/v2; legacy POST | H1/v2 | Exact reuse |
| Pending H2/v3; presentation create | H2/v3 | Exact reuse |
| Pending H1/v2; H2 presentation create | H2/v3 | `409 report_writer_profile_conflict`; v2 job continues |
| Pending H2/v3; legacy H1 POST | H1/v2 | `409 report_writer_profile_conflict`; v3 job continues |
| Finalized v2; H2 selected | H2/v3 | New v3 run only through explicit presentation create |
| Finalized v3; H1 selected | H1/v2 | H1 selects pinned/older v1/v2; never coerces v3 |

No flag flip mutates an existing job/report or changes a polling identity.

## 29. Create/status/read presentation contract and HTTP matrix

### 29.1. Legacy surfaces

Existing old-client endpoints remain H1-only:

```text
POST /company-reports
GET  /company-reports/{inn}/status
GET  /company-reports/{inn}
GET  /company-reports/{inn}/public-h1
```

Their finalized SQL candidate predicate is exact:

```text
report_version IN ('1','2')
AND lifecycle_status IN ('complete','partial')
```

Their pending/status predicate additionally requires
`writer_profile='h1_legacy_writer_v2'`. Active H1 pin still wins. A newer v3
row never shadows an older eligible v1/v2 row.

`POST /company-reports` is excluded from that read outcome: it always attempts
the permanent H1/v2 lifecycle and is independent of H2 assignment. The H1
status/latest/public-H1 read surfaces return terminal
`409 report_not_eligible` only when the subject exists but has neither a
compatible H1 pin nor an eligible v1/v2 report. They never auto-create or poll
a v3 job as if it were v2. An active H2 assignment does not by itself cause
that 409.

### 29.2. Server-authoritative presentation lifecycle

New H2-capable clients use:

```http
POST /company-report-presentations
GET  /company-report-presentations/{presentation_id}/status
```

POST request:

```text
body: {"identifier":"<INN>"}
query: none
version/profile headers: forbidden
```

Response:

```text
PresentationLifecycle:
  presentation_id: opaque UUID
  presentation_contract: literal "company_public_h2_v1"
  report_id: UUID
  lifecycle_status: "pending" | "complete" | "partial" | "failed"
  public_read_path: "/company-reports/{inn}/public-h2"
  canonical_document_path: same-origin path | null
  reused: boolean
```

When the H2 cohort/feature gate is closed, create returns
`404 company_public_h2_disabled` and does not create H1 work. An incompatible
pending H1 job returns `409 report_writer_profile_conflict`. No raw report
version is a request choice. Status lookup is only by immutable opaque
`presentation_id`, which encodes no INN/report/profile/order information and is
bound at creation to one `subject_id + report_id + presentation_contract`.
There is no INN-keyed presentation status route; polling never re-resolves
latest, assignment, cohort or rollout configuration.

### 29.3. Exact read predicates

| Resolver | SQL/selection contract |
|---|---|
| H1 public/SSR | Active H1 pin; otherwise latest finalized v1/v2 |
| Legacy latest/status | H1 writer/profile plus v1/v2 only |
| Presentation status | Exact stored report ID and presentation contract |
| H2 active | Assignment → exact immutable H2 pin generation → exact v3 report |
| H2 staged | Exact stored staged H2 pointer only; missing/corrupt pointer is not eligible |
| H2 legacy preview | Latest v1/v2 only when no v3 and explicitly noindex |

All queries include subject/normalized-INN equality and deterministic
`generated_at DESC, id DESC` tie-breaks where a latest lookup is allowed.

### 29.4. `public-h2` HTTP contract

| Request/situation | Result |
|---|---|
| `GET`, valid INN, valid projection | `200` strict JSON |
| `HEAD`, same | Same status/headers, empty body |
| Any query parameter | `422 public_h2_query_forbidden` |
| Invalid INN | `422 invalid_company_identifier` |
| H2 feature unavailable for caller/cohort | `404 company_public_h2_disabled` |
| No subject/run | `404 company_report_not_found` |
| Exact H2 job pending | `409 report_pending` |
| Exact H2 job failed and no older eligible projection | `409 report_failed` |
| Snapshot exists but projection gates fail | `409 report_not_eligible` |
| Corrupt pin/hash/DTO/digest | `500 public_projection_invalid` |
| Unsupported method | `405` |
| Unsupported `Accept` excluding JSON | `406` |
| Rate limit | `429` with no partial body |

API responses always use `no-store`, `nosniff` and `noindex,follow`.
`Authorization`, cookies and `Accept-Language` do not change facts.
`X-Report-Version`, `X-Writer-Profile`, version query parameters and conditional
`304` selection are unsupported. Unknown headers are ignored, not interpreted
as version choice.

### 29.5. Required lifecycle cases

Downstream tests cover:

- H2 pending and failed;
- newer v3 plus older v2: H2 selects v3, H1/legacy select v2;
- v3-only subject with no compatible H1 report: H1 read/status returns terminal
  not-eligible, while permanent H1 POST still follows the H1/v2 contract;
- flag flip during v2 or v3 pending;
- old client polling remains bound to H1 profile/report;
- presentation client polling remains bound to exact report/contract;
- corrupt active pin never falls back;
- query/header attempts cannot choose report version.

## 30. Immutable H2 pin generations and publication policy

### 30.1. Append-only pin

```text
H1PresentationPin:
  subject_id
  contract_version: "company_public_h1_v1"
  generation: positive integer
  report_id
  report_version: "1" | "2"
  snapshot_hash
  h1_publication_policy_version
  canonical_path
  indexable
  published_lastmod
  created_at
  absent: projection_digest, chart_facts_version, chart_facts_hash,
          evidence_registry_version, narrative_binding_kind,
          narrative_binding_key, publication_policy_version

H2PresentationPin:
  subject_id
  contract_version: "company_public_h2_v1"
  generation: positive integer
  report_id
  report_version: "3"
  snapshot_hash
  projection_digest
  narrative_binding_kind: "artifact" | "fallback"
  narrative_binding_key
  chart_facts_version
  chart_facts_hash
  evidence_registry_version
  publication_policy_version
  canonical_path
  indexable
  published_lastmod
  created_at

primary key for either shape:
  (subject_id, contract_version, generation)

H1 unique:
  (subject_id, contract_version, report_id, snapshot_hash,
   h1_publication_policy_version, canonical_path, indexable)

H2 unique:
  (subject_id, contract_version, report_id, snapshot_hash, projection_digest,
   chart_facts_version, chart_facts_hash, evidence_registry_version,
   publication_policy_version, narrative_binding_kind, narrative_binding_key,
   canonical_path, indexable)
```

Rows are immutable. Republish creates generation `previous+1`; no pin row is
updated/deleted.

```text
PublicPresentationAssignment:
  subject_id primary key
  active_contract
  pin_subject_id
  pin_contract_version
  pin_generation
  expected_previous_assignment_generation
  assignment_generation
  changed_at

PublicStagedH2Pointer:
  subject_id primary key
  pin_subject_id
  pin_contract_version: "company_public_h2_v1"
  pin_generation

composite foreign key:
  (pin_subject_id, pin_contract_version, pin_generation)
  -> PublicPresentationPin
```

The referenced pin itself binds exact report/hash/digest/narrative. Assignment
cannot point to arbitrary duplicated leaves.

### 30.2. CAS activation/rollback

One transaction:

1. lock subject assignment;
2. require caller-supplied expected assignment generation;
3. join candidate pin, report, subject and narrative binding;
4. revalidate all hashes/policy/canonical/indexability;
5. append safe assignment journal row;
6. update assignment generation/reference;
7. commit.

CAS mismatch returns `409 presentation_assignment_conflict`. No partial switch
is visible.

Rollback uses the same transaction and references a previously validated
immutable H1 pin generation. Existing H1 publication state is imported/mirrored
as immutable H1 generations without changing `company_public_h1_v1`.

Resolver, sitemap and SSR call one shared SELECT/join:

```text
assignment -> immutable pin generation -> exact report
           -> exact narrative binding (when H2)
```

No layer independently chooses “latest”. Missing/corrupt joined member fails
closed.

### 30.3. H2 publication eligibility `company_public_h2_publication_v1`

Staged noindex eligibility requires:

- exact v3 finalized `complete|partial` report;
- subject/target/counterparty INN equality;
- valid snapshot and Chart Facts hashes;
- strict H2 DTO and projection digest;
- valid artifact or fallback binding;
- privacy transform/version present;
- no raw/private/unknown public key;
- canonical path uniqueness;
- all coverage/limitations internally consistent.

`indexable=true` additionally requires:

- lifecycle `complete`;
- all mandatory schema, finance-unit, outcome, entity-type, currency and KAD
  gates used by visible content are verified/approved;
- no coverage `failed`, `conflict`, `gate_closed` or `legacy_unavailable`;
- requisites identity available;
- all ten view coverage entries are one of
  `available`, `available_empty`, `missing`, or disclosed bounded `partial`;
- a partial arbitration collection has exact returned/total/cap limitation and
  no duplicate conflict, malformed unknown-year zero assertion or privacy
  failure;
- pinned narrative validates automatically;
- owner-approved rollout assignment.

`missing` and `available_empty` may be indexable only when source scope is
proved and their distinction is explicit. Scoring, thin-content H1 sufficiency
and AI quality opinion are not H2 eligibility inputs.

## 31. Arbitration evidence binding and deterministic processing

### 31.1. Envelope and visible case number

Current/synthetic observation is `$.total_cases`; the authoritative DataNewton
total leaf remains `NOT_VERIFIED`. `$.total` is never claimed as provider
contract.

Before v3 collection, the evidence registry must bind:

```text
arbitration_total_path
arbitration_total_type
total_scope
data_path
offset_path
limit_path
shape_version
```

Missing/stale bind yields `arbitration_envelope_gate_closed` before a provider
call.

Visible case number has its own gate:

```text
field_id: arbitration_visible_case_number
initial path: NOT_VERIFIED
allowed runtime source: the one exact path approved by evidence
public missing value: null
display fallback: "Номер не указан"
```

Neither dedup `case_id` nor fallback `id` is displayed as a case number unless
that exact path separately passes this gate.

### 31.2. Processing order and cap accounting

`hard_case_row_cap=1000` counts raw elements encountered in bound `data`
arrays before validation/dedup, including malformed, duplicate, conflicting
and oversized rows. The 1001st element is not normalized.

Per row, in provider page/array order:

1. increment `rows_observed`;
2. enforce row cap;
3. validate minimum object/key shape;
4. normalize strings/dates/Decimals and parties;
5. apply privacy transformation;
6. build `SanitizedCaseV1`;
7. serialize it with `company_public_h2_cjson_v1`;
8. deduplicate by preferred key;
9. tentatively build `ArbitrationBasisV1`;
10. admit only if canonical basis bytes are `<= 8388608`;
11. otherwise stop before this row and all later rows/pages.

`ArbitrationBasisV1` is exactly:

```text
shape_version
source_total
page_manifest
counters
sanitized_cases sorted by canonical case key
mask_algorithm_version
mask_key_id
```

Derived Chart Facts are excluded from the 8 MiB basis cap and have the public
DTO cap. Equality at `8388608` is accepted; `8388609` is rejected.

An individual sanitized case whose canonical object exceeds `262144` bytes is
not admitted, increments `oversized_case_count` and makes collection partial.
No later row is processed after the first oversized/storage-cap stop, avoiding
selection by size.

### 31.3. Canonical duplicate equality

Duplicate equality compares the complete canonical `SanitizedCaseV1` bytes,
including:

- normalized dates/amount/currency;
- role evidence;
- outcome/detail;
- all sanitized party public/internal tokens;
- safe court/link fields;
- null versus explicit zero.

Same key and same bytes is `duplicate_identical`. Same key and different bytes
removes any previously admitted case with that key, records one
`duplicate_conflict` key and prevents re-admission of that key.

### 31.4. Counters and invariants

```text
pages_requested
pages_accepted
rows_observed
rows_shape_valid
malformed_count
oversized_case_count
duplicate_identical_count
duplicate_conflict_row_count
duplicate_conflict_key_count
unique_case_count
masked_natural_count
masked_unknown_count
```

Invariants are checked before persistence. Among processed rows, every row
ends in exactly one primary row disposition: malformed, oversized,
duplicate-identical, duplicate-conflict or current unique candidate. Conflict
removal is reflected separately so counters do not pretend that
`unique_case_count + dispositions == rows_observed`.

`completion_reasons` is a nonempty unique list sorted by this fixed precedence:

```text
privacy_key_unavailable
envelope_gate_closed
envelope_invalid
provider_error
total_drift
offset_drift
duplicate_conflict
oversized_case
storage_cap_exhausted
case_cap_exhausted
max_pages_exhausted
non_progress
complete
```

`completion_reason` is the first list item. `complete` may be the only item and
requires stable total, all rows fetched and no earlier collection reason.
Calendar evidence never changes collection completeness; it is represented by
the separate calendar fields and limitations.

### 31.5. Roles and party positions

Party position is exact:

```text
party_position =
  normalized source collection ID
  + ":"
  + zero-based array ordinal
```

The target role set contains each source role collection with an exact target
INN match:

- exactly `{plaintiff}` → `plaintiff`;
- exactly `{respondent}` → `respondent`;
- any other nonempty set → `other`;
- empty set → `unattributed`.

This includes a singleton third/creditor/debtor/other collection in `other`.

### 31.6. Mask key lifecycle

Private configuration is a versioned key ring:

```text
mask_algorithm_version = "opponent_hmac_sha256_v1"
mask_key_id = nonsecret closed identifier
active secret = resolved only inside normalization worker
```

The v3 snapshot stores algorithm version/key ID and derived full tokens, never
the secret or private identifier. Rotation changes the active key ID only for
new reports; existing immutable tokens are not recalculated.

Missing/disabled key or unknown key ID fails arbitration privacy normalization
closed with `privacy_key_unavailable`. Plain SHA, name hash, random ordinal or
unkeyed fallback is forbidden.

### 31.7. Dates, duration and aliases

If both case dates exist:

```text
update_date >= start_date:
  days_to_last_update = calendar-day difference

update_date < start_date:
  days_to_last_update = null
  limitation = arbitration_date_inversion
```

Missing either date yields null duration. It is never called proceeding
duration.

For verified legal/state parties sharing one exact INN, safe display alias is:

1. NFC/whitespace-normalized nonempty safe name;
2. candidate from the case with greatest `date_update`;
3. then greatest `date_start`;
4. then lexicographically smallest Unicode-scalar name;
5. then smallest case key.

Natural/unknown parties never use name aliases.

### 31.8. Mandatory iteration-20 tests

Fixtures/tests include exact boundary pairs:

- 999, 1000 and 1001 source rows;
- 8 MiB equality and one-byte-over basis;
- oversized first/mid-page case;
- mid-page storage stop and proof later rows are not selected;
- identical duplicate and conflicting duplicate removal;
- equal amount/different key;
- total/offset drift and repeated page;
- every role-set combination;
- missing/rotated mask key;
- date equality/inversion/missing;
- alias date/tie normalization;
- visible case-number gate closed/open.

## 32. Finance matrix strengthened against false pass

Missing/zero comparisons prove coverage semantics only. They never prove a
scale.

For each of the twelve exact `(form,code)` pairs, pass requires at least one
exact non-zero DataNewton/FNS comparison after explicit OKEI normalization.
Additionally:

- exactly 3–5 pseudonymized companies complete the matrix;
- each company contributes two common reporting years for both forms where
  legally available;
- every `(form,code)` has non-zero matches in at least two different companies;
- both years are represented by non-zero matches in each form;
- no company supplies more than half of all non-zero proof cells;
- every comparable cell, including missing/zero cells, has a tracked
  field-level outcome;
- one mismatch fails the whole candidate policy.

The authoritative OKEI normalization, `FinanceEvidenceCellV1` schema and all
accepted/rejected invariants are defined once in section 23. This section adds
only false-pass protection: `reporting_year` is the public year, raw files and
identifier-bearing mappings/locators remain outside git, content hashes are
safe provenance, and deterministic per-code summaries accompany every tracked
field-level row. Iteration 23 owns executable matrix tests; it may not redefine
the row or activate the gate from aggregate match counts.

## 33. Durable AI dispatch and deterministic fallback

### 33.1. Pre-dispatch generation key

Before model resolution:

```text
generation_key = SHA-256(UTF-8(CJSON({
  "identity_version":"GenerationIdentityV1",
  "report_id":report_id,
  "snapshot_hash":snapshot_hash,
  "chart_facts_hash":chart_facts_hash,
  "evidence_registry_version":evidence_registry_version,
  "statement_catalog_version":statement_catalog_version,
  "template_catalog_version":template_catalog_version,
  "prompt_version":prompt_version,
  "json_schema_version":json_schema_version,
  "policy_version":policy_version,
  "renderer_version":renderer_version,
  "gateway_profile_version":gateway_profile_version,
  "fallback_catalog_version":"company_card_h2_fallback_catalog_v1"
})))
```

Unique durable reservation constraint:

```text
UNIQUE(generation_key)
```

The resolved model is deliberately absent because it is not known until the
dispatch boundary.

### 33.2. State machine and fencing

```text
reserved
leased
dispatching
dispatched
validating
rendered
finalized

terminal alternatives:
pre_dispatch_failed
ambiguous_timeout
invalid_output
fallback_finalized
```

Durable row contains:

```text
generation_key
state
lease_token
lease_expires_at
fence_generation
local_attempt_count
dispatch_started_at
gateway_dispatch_id
resolved_model_version
response_received_at
validation_codes
artifact_id
```

Lease/transition updates require exact lease token and fence generation.
`gateway_dispatch_id` is unique when non-null.

Definitive pre-dispatch retry is allowed only when:

- no network/model dispatch began;
- `dispatch_started_at`, dispatch ID and resolved model are null;
- failure code is in a closed pre-dispatch allowlist;
- `local_attempt_count < 3`.

Immediately before the network call, the worker atomically sets
`dispatch_started_at` and state `dispatching`. After that write, timeout,
worker death or ambiguous response is never retried. It finalizes fallback.
Invalid model output also finalizes fallback without a repair/second call.

### 33.3. Final artifact identity

After a response resolves the model:

```text
artifact_identity = SHA-256(UTF-8(CJSON({
  "identity_version":"ArtifactIdentityV1",
  "generation_key":generation_key,
  "resolved_model_version":resolved_model_version,
  "validated_render_plan_bytes_sha256":SHA-256(validated_render_plan_bytes),
  "rendered_output_bytes_sha256":SHA-256(rendered_output_bytes)
})))
```

Constraints:

```text
UNIQUE(artifact_identity)
one finalized artifact/fallback binding per generation_key
```

Publication binds this final identity, never only the pre-dispatch key.

### 33.4. Sparse-safe fallback

Fallback catalog:

```text
company_card_h2_fallback_catalog_v1
company_card_h2_fallback_renderer_v1
```

Version `company_card_h2_fallback_catalog_v1` contains exactly one immutable
entry, `fallback_profile_any_v1`, whose NFC-normalized value is this exact
691-Unicode-scalar literal:

```text
Карточка построена по зафиксированному снимку отчёта и отражает только факты, прошедшие проверку контракта. Деятельность и реквизиты показываются лишь при подтверждённом источнике; неизвестные значения не заменяются выводом. Финансовые показатели доступны после проверки единиц и исходных строк; закрытый или неполный раздел содержит ограничение. Арбитражные сведения зависят от подтверждённой выборки и правил приватности; неполная коллекция не означает отсутствия дел. Для скрытых данных применяется безопасное ограничение, а не догадка. Текст не содержит оценки надёжности, вероятности результата, рекомендации или интерпретации за пределами подтверждённых фактов и указанных ограничений.
```

It is universal regardless of coverage state. The renderer accepts no facts,
limitations, coverage or profile-selection input and emits the literal without
padding, truncation, compilation or AI. v1 has no variants or mutation path.
Its sole golden binds the exact normalized UTF-8 bytes, scalar length and
named-object fallback identity. A replacement requires a new catalog version
and explicit owner decision; it cannot extend v1.

Exact fallback binding:

```text
FallbackIdentityV1:
  identity_version: literal "FallbackIdentityV1"
  generation_key: 64 lowercase hex
  fallback_catalog_version:
    literal "company_card_h2_fallback_catalog_v1"
  fallback_profile_id: literal "fallback_profile_any_v1"
  renderer_version: literal "company_card_h2_fallback_renderer_v1"
  rendered_output_bytes_sha256: 64 lowercase hex

fallback_identity = lowercase_hex(
  SHA-256(UTF-8(CJSON_company_public_h2_cjson_v1(FallbackIdentityV1)))
)
```

`fallback_catalog_version` is part of `GenerationIdentityV1` and therefore of
`generation_key`. A catalog-only upgrade creates a new reservation/binding;
it can never reuse or replace the finalized binding of an older generation.

### 33.5. Mandatory iteration-21 tests

- reservation concurrency produces one generation row;
- lease expiry and stale fence cannot dispatch;
- two pre-dispatch local retries then success still make one paid dispatch;
- dispatch flag followed by timeout/worker death produces no retry;
- ambiguous timeout produces fallback;
- invalid schema/evidence/policy produces fallback without second AI;
- resolved-model change creates a different final artifact identity;
- finalization/pin is immutable;
- the sole v1 universal fallback renders its exact 691 scalars and identity;
- zero, one and two comments pass; three/duplicate/hidden-chart comments fail;
- public GET/SSR/crawler create no reservation/job/dispatch.

## 34. Dedicated H2 document, assets and deployment boundary

### 34.1. Server-mediated document choice

Product API remains authoritative for `/company/{company_key}`. Nginx does not
infer H1/H2 from URL, cookie, frontend flag or report version.

One Product API resolver:

1. validates plain/canonical company key;
2. resolves server assignment and exact pin;
3. returns H1 behavior for H1 assignment;
4. returns dedicated H2 SSR shell for a valid H2 assignment/pin;
5. returns lifecycle/not-found/noindex response without mounting either factual
   app when no projection is valid;
6. redirects wrong slug only from the selected exact pin.

GET never creates a report. Plain-INN lifecycle uses the presentation create
surface in section 29 only after an explicit client command.

### 34.2. Dedicated no-Webvisor entrypoint

H2 shell is not `services/web_ui/index.html` and never includes the current
global Yandex/Webvisor bootstrap.

Exact logical asset manifest:

```text
company_public_h2_asset_manifest_v1:
  schema_version
  app_js_path: /assets/company-public-h2.<content-hash>.js
  app_css_path: /assets/company-public-h2.<content-hash>.css
  optional_chunk_paths: sorted same-origin content-hashed paths
  integrity_sha256 for every asset
  public_contract_version: company_public_h2_v1
  canonical_json_profile: company_public_h2_cjson_v1
```

The Product API deployment pins one exact manifest version. H2 shell includes
only those same-origin assets and its one embedded DTO.

If strict parse, schema, canonical path or digest verification fails:

- SSR factual DOM remains unchanged;
- React H2 app does not mount;
- H1 app does not mount;
- no H1/H2 factual GET, lifecycle create/status, provider, AI or telemetry call
  occurs;
- only a fixed local enhancement-unavailable notice may be exposed.

### 34.3. Deploy compatibility and rollback

Because web assets and Product API deploy separately:

1. publish content-addressed H2 assets first;
2. verify manifest files/hashes are reachable;
3. deploy Product API supporting the pinned manifest and DTO;
4. run nonactive compatibility smoke;
5. activate assignment only in iteration 25.

Asset storage retains the current and previous two manifest generations. A
Product API release may reference only a manifest declared compatible with its
exact public contract/canonical profile. Asset deletion is never part of the
same rollout.

Rollback order:

1. CAS assignments back to immutable H1 pin generations;
2. verify canonical/Claims continuity;
3. roll back Product API if needed;
4. keep content-addressed H2 assets and v3 snapshots intact.

Nginx continues proxying `/company` to Product API; its SPA fallback must not
replace a selected H2 document. Product API/web version compatibility and
rollback are tested before activation.

## 35. Fixture and verification ownership by iteration

### Iteration 20

Owns Product API/persistence fixtures and tests:

```text
legacy v1 fixed-hash snapshot
legacy v2 exact round-trip snapshot
v3 complete golden snapshot
v3 sparse/partial/signed golden snapshot
public-h2 legacy-v1, legacy-v2 and full-v3 golden JSON
all closed-DTO negative/cardinality/size fixtures
Python canonical-JSON golden vectors
writer profile/unique subject/flag-flip jobs
create/status/read SQL and HTTP matrix
immutable pin/assignment CAS and eligibility
arbitration cap/dedup/privacy/date/alias matrix
Claims exact v3 handoff
H1/legacy v1-v3 compatibility
```

### Iteration 21

Owns durable reservation/lease/one-dispatch/artifact/fallback tests from
section 33 and Gateway isolation. It does not defer them to iteration 25.

### Iteration 22

Owns:

- TypeScript closed DTO parser;
- shared Python/TypeScript canonical JSON vectors;
- nonce/CSP and one embedded state;
- XSS/surrogate/size fixtures;
- no second factual GET;
- parse/digest failure no-mount/no-H1-fallback behavior;
- Product API document resolver/nginx boundary;
- dedicated no-Webvisor asset manifest;
- Product API/web version compatibility and deploy rollback tests.

### Iteration 23

Owns complete F1–F5 component/contract tests for missing, explicit zero,
conflict, seven-year gaps, negative/mixed-sign, positive/zero/negative
denominators, formatter precision, geometry, keyboard/touch and textual
fallback.

### Iteration 24

Owns complete A1–A5 tests for full/partial pagination, calendar zero,
top-20/cap+1, every role/outcome, equal/zero/negative/missing amounts,
multi-currency, masking/entity-type/name alias, external-link gates and nested
N/M.

### Iteration 25

Does not absorb unit/component/contract gaps from iterations 20–24. It owns
only cross-layer and real-browser rollout gates:

- end-to-end SSR/API/embedded/client parity;
- real browser responsive/zoom/keyboard/touch/reduced-motion matrix;
- Webvisor/telemetry/network observation;
- asset/deploy compatibility rehearsal;
- staged assignment, canary, monitoring and atomic H1 rollback;
- final owner activation decision.

No iteration may mark its own required matrix “deferred to iteration 25”.
