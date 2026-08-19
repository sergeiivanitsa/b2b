# Итерация 16 — Публичный контракт H1 CompanyReport

ID: `16`
Slug: `company-report-h1-public-contract`
Версия контракта: `company_public_h1_v1`
Ветка спецификации: `codex/company-report-h1-public-contract`
Статус спецификации: `approved`
Дата утверждения продуктовых решений: `2026-08-18`

## 1. Цель

Зафиксировать единый публичный контракт H1 для одной доказательной карточки
компании по адресу:

```text
/company/{inn}-{slug}
```

Один self-canonical документ отвечает на вопросы об идентификации, статусе,
реквизитах, финансовой отчётности, арбитраже, налоговом признаке, публикациях о
банкротстве, руководстве и владельцах. H1 не создаёт дочерние индексируемые
страницы `/finance`, `/courts`, `/management` или их аналоги.

Контракт определяет семантику фактов, источники, нормализацию, отображение,
coverage, missing/partial/conflict поведение и запрещённые выводы. Реализация
контракта выполняется отдельным этапом после этой документационной итерации.

## 2. Контекст и граница итерации

Текущий CompanyReport сохраняет immutable snapshot и использует в агрегате
`counterparty`, `finance` и `arbitration`. Provider уже умеет получать
`tax_info`, `bankruptcy`, `batch_cards` и `fssp`, но эти наборы не образуют
публичный H1-контракт. Текущая finance-модель содержит
`provider_units_unknown`; текущий arbitration normalizer может засчитать одно
дело сразу в несколько role buckets.

Эта итерация изменяет только нормативные документы:

- спецификацию H1;
- implementation plan будущей реализации;
- roadmap и состояние разработки.

Runtime-код, БД, миграции, API, provider-вызовы, UI, SEO rollout и production
не меняются.

## 3. Термины и инварианты

### 3.1. Snapshot и дата проверки

`checked_at` — timezone-aware `report.generated_at` immutable-отчёта. Это дата
получения и составления снимка, а не автоматически доказанная дата вступления
юридического статуса в силу.

Публичная формулировка:

```text
По данным отчёта, сформированного {checked_date}: статус «{status_label}».
```

Правила:

1. Если отчёта по ИНН нет, только plain-INN lifecycle создаёт новый report,
   делает provider-вызовы и сохраняет новый `checked_at`; canonical 404 ничего
   не создаёт.
2. Если active publication либо eligible finalized report уже есть, H1 resolver
   использует выбранный immutable snapshot без нового provider-вызова;
   `checked_at` не меняется. Страница не вызывает существующий POST для
   обновления final report.
3. Текущее время чтения страницы не используется как freshness/date факта.
4. Если источник передаёт отдельную подтверждённую дату юридического события,
   она хранится как `status_effective_at` и не подменяет `checked_at`.
5. Будущая кнопка «Обновить отчёт» создаст новый immutable run, но не входит в
   `company_public_h1_v1`.

Публичная проекция передаёт полный ISO timestamp. Один versioned display policy
преобразует его в календарную дату одинаково для SSR и SPA; browser locale не
может менять фактический день между двумя представлениями одной страницы.

Для H1 v1 утверждена policy `checked_date_msk_v1`:

- exact `checked_at` хранится и передаётся как UTC ISO timestamp;
- `checked_date` и русская display-строка вычисляются backend в фиксированной
  IANA timezone `Europe/Moscow`;
- SSR и SPA используют переданные `checked_date`/display string и не повторяют
  timezone conversion в браузере.

#### Единый snapshot resolver

Canonical SSR и публичный H1 API обязаны использовать один resolver:

1. Если для subject существует active publication, выбирается только
   закреплённый в ней `report_id`; snapshot hash, policy eligibility и
   canonical path перепроверяются как сейчас.
2. Неконсистентный/corrupt active pin завершается safe internal error и не
   переключается на latest snapshot.
3. Если active publication отсутствует, выбирается latest eligible
   `complete|partial` snapshot с normalized data и exact identity; failed или
   unusable newer run его не подменяет. Projection получает
   `projection_scope=latest_unpublished` и `indexable=false`.
4. Новый finalized run не подменяет active published snapshot. Переключение
   происходит только атомарным controlled republish, который меняет pin и
   publication lastmod.
5. Plain-INN resolver и SPA принимают возвращённый H1 `canonical_path`; они не
   вычисляют slug или snapshot самостоятельно.

Публичный read-only endpoint фиксируется как:

```text
GET /company-reports/{inn}/public-h1
```

Он не требует авторизации, не принимает query parameters и не вызывает
provider, AI, worker, job enqueue или запись в БД. Ответ всегда содержит
`contract_version`, `report_id`, `projection_scope`, `canonical_path`,
`indexable`, `checked_at` и `checked_date`. Несовместимый будущий контракт
получает новый suffix (`public-h2`), а v1 меняется только аддитивно.

Lifecycle error distinction является частью public contract:

| Situation | HTTP/code | Plain-INN action |
| --- | --- | --- |
| Ни одного run нет | `404 company_report_not_found` | Разрешено создать один новый report. |
| Есть только pending | `409 report_pending` | Только polling. |
| Есть failed, но нет older eligible snapshot | `409 report_failed` | Показать terminal state; не создавать автоматически. |
| Есть complete/partial, но нет eligible identity/projection | `409 report_not_eligible` | Показать terminal state; не создавать автоматически. |

Только exact `404 company_report_not_found` разрешает auto-create из plain
route. Canonical route не создаёт report при любом error.

Нормативная topology `CompanyPublicH1Response`:

```text
contract_version: "company_public_h1_v1"
report_id: UUID
report_version: "1" | "2"
projection_scope: "published" | "latest_unpublished"
canonical_path: string
indexable: boolean
checked_at: UTC ISO datetime
checked_date: ISO date under checked_date_msk_v1
checked_date_display: string
identity: CompanyPublicIdentity
block_order: PublicBlockId[]
blocks:
  requisites: RequisitesBlock | null
  finance: FinanceBlock | null
  arbitration: ArbitrationBlock | null
  bankruptcy: BankruptcyBlock | null
  tax: TaxBlock | null
  management: ManagementBlock | null
coverage: PublicCoverageItem[]
sources: PublicSourceItem[]
limitations: PublicLimitation[]
actions: PublicAction[]
breadcrumbs: PublicBreadcrumb[2]
internal_links: PublicInternalLink[]

CompanyPublicIdentity:
  legal_full_name: string
  legal_short_name: string | null
  display_name: string
  inn: 10 or 12 ASCII digits
  status_code: string | null
  status_label: string | null
  status_effective_at: ISO date | null

RequisitesBlock:
  legal_form: string | null
  ogrn_or_ogrnip: string | null
  kpp: 9 ASCII digits | null
  registration_date: ISO date | null
  dissolved_date: ISO date | null
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

FinanceBlock:
  unit_policy_version: string | null
  metrics: FinanceMetric[1..N]

FinanceMetric:
  metric_id: allowlisted finance metric
  year: integer
  money: PublicMoney | null
  yoy: PublicPercentChange | null

PublicMoney:
  source_decimal: Decimal string
  source_unit: "thousand_rub"
  rub_decimal: Decimal string
  display_value: string
  unit_policy_version: string

PublicPercentChange:
  exact_percent: Decimal string
  display_value: string
  current_year: integer
  previous_year: integer
  formula_version: string

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
  selected_cases: PublicArbitrationCase[]

ArbitrationRoleCounts:
  plaintiff: integer >= 0
  respondent: integer >= 0
  applicant: integer >= 0
  creditor: integer >= 0
  debtor: integer >= 0
  other: integer >= 0

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

ArbitrationClaimAmount:
  role: "plaintiff" | "respondent"
  currency: ISO-like source currency string
  exact_decimal: Decimal string
  display_value: string

PublicArbitrationCase:
  case_number: string
  date_start: ISO date | null
  date_update: ISO date | null
  attributed_role: allowlisted role | "other" | "unattributed"
  claim_amount: ArbitrationClaimAmount | null

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
  organization_inn: string | null
  organization_ogrn: string | null
  share_percent_decimal: Decimal string | null
  share_display: string | null
  ownership_effective_at: ISO date | null

PublicCoverageItem:
  block_id: PublicBlockId
  dataset: allowlisted dataset
  state: "available" | "available_empty" | "not_found" |
         "not_requested" | "partial" | "failed" | "conflict"
  total: integer | null
  returned: integer | null
  limit: integer | null
  offset: integer | null
  limitation_codes: string[]

PublicSourceItem:
  dataset: allowlisted dataset
  received_at: UTC ISO datetime
  effective_at: ISO date | null
  period: string | null
  normalization_version: string

PublicLimitation:
  code: allowlisted string
  block_id: PublicBlockId | null
  field_id: allowlisted field id | null
  message: safe allowlisted string

PublicAction:
  action_id: "check_another_company" | "prepare_claim"
  label: fixed allowlisted string
  path: same-origin absolute path

PublicBreadcrumb:
  label: fixed or identity-derived safe string
  path: same-origin absolute path

PublicInternalLink:
  label: fixed allowlisted string
  path: identifier-resolved same-origin absolute path
  relation: allowlisted relation
```

Serialized contract rules:

- `blocks` всегда содержит шесть перечисленных keys; каждый value — strict
  object либо `null`.
- `FinanceBlock` существует, только если хотя бы один metric имеет `money` или
  `yoy`; metrics сортируются по versioned metric allowlist, затем year desc.
- `selected_cases` содержит 0–10 записей, детерминированно выбранных по
  `date_update` desc, `date_start` desc, `case_number` asc.
- `ManagementBlock` существует, только если после schema/privacy gates остался
  хотя бы один manager/owner; lists сортируются по normalized role/type, name и
  effective date. Person identifiers отсутствуют.
- `TaxBlock` существует только для доказанного scoped boolean; record amount
  остаётся `null`, пока его unit policy отдельно не доказана.
- `BankruptcyBlock` существует только после schema gate; unknown raw type не
  попадает в DTO, только normalized `kind=unknown` и allowlisted message.
- `coverage` содержит ровно по одному item для каждого factual block
  (`requisites`, `finance`, `arbitration`, `bankruptcy`, `tax`, `management`),
  даже когда block равен `null`.
- `sources` содержит не более одного item на dataset и только для successful
  normalized source; порядок фиксирован source precedence.
- `limitations` уникальны и сортируются по `(block_id, field_id, code)`;
  свободный provider error text запрещён.
- `breadcrumbs` всегда содержит `/` и текущий `canonical_path`;
  `internal_links` может быть пустым.

`PublicBlockId` имеет фиксированный allowlist:
`breadcrumbs`, `identity_status`, `known_summary`, `in_page_navigation`,
`coverage_checked_at`, `requisites`, `finance`, `arbitration`, `bankruptcy`,
`tax`, `management`, `sources_limitations`, `neutral_actions`,
`internal_links`. `null` означает невидимый factual block; причина остаётся в
coverage. DTO
не содержит arbitrary dictionaries: каждый fact block получает отдельную
strict schema, Decimal передаётся строкой, даты — ISO, display strings — только
из versioned backend policy. `report_id` является snapshot identity для parity;
SPA не подменяет его результатом legacy latest-read.

Resolver проверяет инварианты:

```text
dto.report_id == publication.report_id == ORM report.id == snapshot.report_id
publication.subject_id == report.subject_id
requested INN == subject identifier == snapshot target INN == public identity INN
hash(snapshot) == report.snapshot_hash == publication.snapshot_hash
ORM lifecycle == snapshot status in {complete, partial}
checked_at == pinned snapshot generated_at
dto.canonical_path == active publication canonical_path
```

Для `latest_unpublished` publication-сравнения не применяются, но report,
snapshot, target и identity equality обязательны. Invalid active pin всегда
fail-closed. Wrong-slug SSR перенаправляет на сохранённый registry path. Для
новых публикаций name precedence единообразна: safe `legal_short_name`, затем
`legal_full_name`; уже опубликованный path меняется только republish.

`publication.policy_version` выбирает совместимый projection/policy builder.
Claims action использует именно H1 `report_id`, поэтому опубликованная карточка
не создаёт claim из другого latest run.

SSR/API parity относится к active publication: оба строят один pinned response.
Для `latest_unpublished` SSR publication route остаётся 404/noindex и nginx
может отдать public SPA; API/SPA показывают noindex projection. Непубликованный
latest snapshot никогда не маскируется под SSR/indexable документ.

### 3.2. Состояния данных

Для каждого dataset или блока различаются:

| Состояние | Семантика | Публичное поведение |
| --- | --- | --- |
| `available` | Есть безопасные нормализованные факты. | Показать факты, источник и дату. |
| `available_empty` | Успешный ответ в явно определённом scope не содержит записей. | Допустима только узкая датированная формулировка. |
| `not_found` | Источник явно сообщил отсутствие субъекта/результата в своём scope. | Не превращать в общий положительный вывод. |
| `not_requested` | Набор или блок не запрашивался. | Скрыть факты; в coverage указать, что вывод не делается. |
| `partial` | Получена часть результата либо `returned < total`. | Показать доступное вместе с `total/returned/limit`. |
| `failed` | Запрос или нормализация завершились ошибкой. | Не подставлять ноль; вывести safe limitation. |
| `conflict` | Идентификаторы или профильные источники противоречат друг другу. | Конфликтный факт скрыть или пометить, не выбирать значение случайно. |

Missing, `null`, пустой массив, `false` и числовой ноль не взаимозаменяемы.

### 3.3. Provenance

Каждый публичный fact family несёт:

```text
source_dataset
source_received_at
effective_at или period, если существует
coverage state
normalization/formula version
limitation codes
```

Raw payload, headers, API keys, request/response hashes, endpoint diagnostics,
worker/job metadata и свободный provider error text не входят в публичную
проекцию.

## 4. H1 page manifest

| Порядок | Блок | Условие |
| ---: | --- | --- |
| 1 | Breadcrumbs | Обязательный; только существующие маршруты. |
| 2 | Identity and status hero | Обязательный после exact identity gate. |
| 3 | Что известно | Обязательный; перечисляет только видимые блоки. |
| 4 | Навигация по странице | При наличии не менее двух content blocks. |
| 5 | Покрытие и дата проверки | Обязательный. |
| 6 | Реквизиты и юридический адрес | Обязательный после identity gate; пустые строки скрываются. |
| 7 | Финансовая динамика | При наличии безопасного денежного или derived fact. |
| 8 | Арбитраж | При успешном scoped zero либо полученных карточках. |
| 9 | Банкротные публикации | При успешном exact-subject результате. |
| 10 | Налоговые факты | При семантически разобранном признаке или датированном документе. |
| 11 | Руководитель и владельцы | При наличии privacy-safe данных. |
| 12 | Источники и ограничения | Обязательный. |
| 13 | Нейтральные действия | Обязательный UI-блок, не factual content. |
| 14 | Точные внутренние связи | Только для identifier-resolved существующих страниц. |

ФССП, контакты, рейтинг, отзывы, критические события и change history не входят
в H1 v1 без отдельного утверждённого публичного контракта.

## 5. Контракт публичных полей

### 5.1. Идентификация, статус и реквизиты

| Публичное поле | Источник | Нормализация | Missing/conflict поведение |
| --- | --- | --- | --- |
| `legal_full_name` | `counterparty.company.company_names.full_name` | Пробелы, display casing и кавычки; source value сохраняется отдельно. | Без надёжного имени route не проходит identity gate. |
| `legal_short_name` | `counterparty.company.company_names.short_name` | То же; fallback только на полное имя. | Пустое поле скрывается. |
| `legal_form` | `counterparty.company.opf` | Versioned OPF mapping. | Не выводить выдуманную форму. |
| `inn` | Subject и `counterparty` | Только 10/12 ASCII digits; exact equality. | Несовпадение блокирует публичную карточку. |
| `ogrn_or_ogrnip` | `counterparty` | Только валидный identifier для формы. | Пустое поле скрывается; конфликт блокирует зависимые facts. |
| `kpp` | `counterparty.company.kpp` | Только для юридического лица. | Для ИП не применимо, заголовок не показывается. |
| `status_code` | `counterparty.company.status.code_egr` | Строковый allowlisted code. | Не выводить неизвестную расшифровку. |
| `status_label` | `counterparty.company.status.status_rus_short` | Versioned status mapping; boolean не является единственным источником текста. | Конфликт boolean/code/text даёт limitation и скрывает категоричный вывод. |
| `registration_date` | `counterparty` | ISO date. | Пустое поле скрывается. |
| `dissolved_date` | `counterparty` | ISO date. | Missing не означает действующее состояние. |
| `legal_address` | `counterparty` `ADDRESS_BLOCK` | Структурированный адрес плюс display line; учитывается `is_inaccuracy`. | Недостоверный адрес показывается только с явной пометкой; missing скрывается. |
| `region` | Нормализованный address/identity | Код и название региона не смешиваются. | Пустое поле скрывается. |

`checked_at` берётся из отчёта, `source_received_at` — из dataset metadata. Они
не заменяют друг друга.

### 5.2. Руководитель и владельцы

Основной источник — профильный `counterparty` с `MANAGER_BLOCK` и
`OWNER_BLOCK`.

Руководитель:

```text
manager_name
manager_role
manager_innfl — только internal identity aid, никогда не public в H1 v1
appointed_at
is_inaccuracy
source_received_at
```

Публично показываются имя/наименование, роль и дата, если они безопасны и
семантически разобраны. Запись без имени и роли не создаёт пустой блок.

Публичное имя руководителя активируется только после
`management_privacy_v1`, подтверждающего допустимые категории лиц, форму
организации и public fields. До gate managers скрыты с coverage
`not_requested` и limitation `privacy_gate_not_passed`. `manager_innfl`
запрещён в H1 v1 независимо от решения.

Владельцы:

```text
owner_name_or_org
owner_type
owner_inn_or_ogrn, если это организация и идентификатор безопасен
share_decimal
ownership_effective_at
information_limited
source_received_at
```

Правила формы и приватности:

- для ООО участник и доля показываются только при однозначной семантике;
- исторический учредитель АО/ПАО не называется текущим акционером;
- для ИП management/ownership block не применим;
- `information_limited=true`, missing identity или персональные данные без
  утверждённой privacy-классификации скрывают значение и дают limitation;
- значение `0` доли не превращается в факт отсутствия владельца.

`owner_name_or_org`, тип владельца, организационные идентификаторы и доля — это
provider-neutral target fields. Они включаются только после safe schema fixture
или официальной схемы, подтверждающей source path, тип субъекта, актуальность и
семантику/масштаб доли. До этого OWNER_BLOCK имеет coverage
`not_requested` с limitation `schema_gate_not_passed`, а владельцы не
публикуются.

Контакты (`phone`, `email`, websites, social links) не входят в H1 v1 и не
передаются в публичную проекцию, даже если присутствуют в `batch_cards`.

### 5.3. Финансы

#### Единица и точность

Целевая продуктовая гипотеза: денежные строки текущего DataNewton `finance`
могут иметь единицу `thousand_rub`.

```text
value_thousand_rub = source Decimal
value_rub = value_thousand_rub * Decimal("1000")
```

Candidate mapping после evidence применяется только к allowlisted денежным
показателям форм БФО:

```text
total_assets, non_current_assets, current_assets, inventories,
accounts_receivable, cash_and_equivalents, equity,
long_term_liabilities, short_term_liabilities,
short_term_borrowings, accounts_payable, revenue, cost_of_sales,
gross_profit, operating_profit, profit_before_tax, net_profit,
net_cash_flow, cash_at_start, cash_at_end
```

ОКУД, годы, проценты, ratios, counts и другие немонетарные значения не
умножаются на 1000. Все вычисления используют `Decimal`, не `float`.

До runtime-реализации действует evidence gate: гипотеза должна быть подтверждена
официальным контрактом/ответом DataNewton либо проверяемой матрицей
DataNewton value → официальный ГИР БО value/unit для разных форм и периодов.
Пока gate не пройден, существующее runtime-значение
`provider_units_unknown` не меняется, абсолютные денежные значения не входят в
H1 projection, а пример `273,3 млн ₽` является только целевым acceptance
example. После доказательства активируется отдельная versioned policy
`datanewton_finance_thousand_rub_v1`; если evidence её опровергает или выявляет
неоднородность форм, contract не угадывает единицу и policy пересматривается до
кодирования.

#### Публичное форматирование

После активации unit policy публичный DTO сохраняет exact Decimal string в
тысячах рублей, вычисленное exact значение в рублях и backend-generated display
string. Компактное отображение имеет вид:

```text
273325 thousand_rub → 273,3 млн ₽
1250000 thousand_rub → 1,3 млрд ₽
850 thousand_rub → 850 тыс. ₽
0 thousand_rub → 0 ₽
```

Миллионы/миллиарды округляются backend до одного десятичного знака через
Decimal `ROUND_HALF_UP`; decimal separator — запятая. SPA выводит готовую
display string и не преобразует сумму через JavaScript `Number`. Missing не
форматируется как `0 ₽`. Отрицательное значение сохраняет знак и не получает
оценочного цвета.

#### Derived facts

Допустима только воспроизводимая нейтральная динамика с видимыми периодами:

```text
yoy_percent = (current - previous) / abs(previous) * 100
```

Если previous missing либо равен нулю, YoY скрывается. Формула получает
version, входные годы и exact Decimal inputs. Запрещены good/bad thresholds,
прогноз, рейтинг и совет по сделке.

### 5.4. Арбитраж

#### Exact attribution

Target identity содержит отдельные нормализованные `target_inn` и
`target_ogrn`. Идентификаторы разных типов не сравниваются друг с другом.

Для каждой party record:

1. Если передан только ИНН, он должен точно совпасть с `target_inn`.
2. Если передан только ОГРН, он должен точно совпасть с `target_ogrn`.
3. Если переданы оба идентификатора и target содержит оба, совпасть должны оба.
4. Совпадение одного и несовпадение другого — `identity_conflict`, роль не
   присваивается.
5. Если party передаёт оба идентификатора, а target содержит только один, роль
   не присваивается: `target_identity_incomplete` нельзя считать exact match.
6. Совпадение только названия не присваивает роль.

#### Один case — один role bucket

| Ситуация | Bucket |
| --- | --- |
| Одна подтверждённая роль `plaintiff`, `respondent`, `applicant`, `creditor` или `debtor` | Эта роль. |
| Несколько подтверждённых ролей в одном деле | `other`. |
| Одна подтверждённая роль `third_party`, `interested_person` или provider-other | `other`. |
| Нет exact identifier match либо есть identifier conflict | `unattributed`. |
| Нет parseable case identity (`internal_id` и `case_number`) либо parties не являются коллекцией записей | `malformed`, только coverage/warning. |

Одно дело учитывается в role summary ровно один раз. `other` не смешивается с
`unattributed`. Role buckets описывают только нормализованные возвращённые
карточки.

Публичный арбитражный контракт:

```text
total_cases
returned_cases
normalized_case_count
malformed_count
limit
offset
role_counts
unattributed_count
status_counts
result_counts
selected_cases
source_received_at
limitations
```

Всегда показываются отдельно source `total_cases` и `returned_cases`. Нельзя
переносить распределение полученного slice на весь source total.

Claim amount входит в plaintiff/respondent aggregate только при одной exact
роли `plaintiff` либо `respondent` и при явной валюте. Случаи `other`,
`unattributed`, multiple-role и unknown currency не входят в такую сумму.

### 5.5. Банкротные публикации

`bankruptcy` является optional enrichment: его сбой не уничтожает доступные
обязательные datasets и не превращает report в failed.

Названия raw paths, participant shape, GUID/number, totals и роли не считаются
доказанными текущими transport tests. До реализации обязателен
`bankruptcy_schema_v1` evidence artifact: официальная схема либо минимальный
обезличенный fixture с exact source paths, типами, pagination metadata и
идентификаторами участника. Без него dataset остаётся `not_requested`, даже
если transport client умеет вызвать endpoint.

Publication связывается с компанией только по exact INN/OGRN participant.
Совпадение в свободном `content` или только по названию недостаточно. Raw
`content` публично не выводится.

Candidate allowlist H1 v1, активируемый только после
`bankruptcy_schema_v1`:

| Raw type | Публичная формулировка |
| --- | --- |
| `DebtorIntentionGoToCourt` | `Опубликовано намерение должника обратиться в суд с заявлением о банкротстве.` |
| `CreditorIntentionGoToCourt` | `Опубликовано намерение кредитора обратиться в суд с заявлением о банкротстве компании.` |

Неизвестный тип остаётся в source total/coverage, но не получает придуманной
расшифровки. Для exact-subject записи допустима нейтральная строка
`Тип публикации не классифицирован`; raw type может храниться только как
internal allowlist candidate и не публикуется до утверждения.

Для блока обязательна формулировка ограничения:

```text
Наличие публикации не подтверждает, что заявление принято судом, возбуждено
дело, компания признана банкротом или процедура продолжается сейчас.
```

Target normalized fields после schema gate: `total`, `returned`, `limit`, typed
counts, publication date, safe number/guid reference, exact participant role,
source date и limitation. Raw path каждого поля фиксируется evidence artifact,
а не угадывается из названия target field.

### 5.6. Налоговые факты

`tax_info` является optional enrichment. False flag не является доказательством
отсутствия любых налоговых обязательств.

`has_unpaid_debts` ниже — provider-neutral normalized field, а не утверждение о
существовании одноимённого raw path. Его mapping разрешён только после
`tax_info_schema_v1` evidence artifact, подтверждающего source path, boolean
семантику, scope и дату/период. Текущий transport test с произвольным
`paid_taxes` этого не доказывает; без evidence блок имеет `not_requested` и
limitation `schema_gate_not_passed`, а публичная строка не выводится.

Утверждённая короткая формулировка для `has_unpaid_debts=false`:

```text
Признак неоплаченной налоговой задолженности не установлен.
```

Она всегда сопровождается датой снимка/источника и coverage в соседнем UI,
даже если дата не повторяется внутри самой строки.

Для `has_unpaid_debts=true` допустима нейтральная строка:

```text
Источник передал признак неоплаченной налоговой задолженности.
```

Она не является суммой долга, судебным выводом или основанием для взыскания.
Tax amounts выводятся только при подтверждённой единице и датированном
документе/периоде. Пустой массив не подменяет flag и не означает универсальный
ноль.

### 5.7. Source precedence и конфликты

| Fact family | Primary source |
| --- | --- |
| Identity, status, address, manager, owners, tax mode | `counterparty` |
| Financial statements | `finance` |
| Arbitration | `arbitration` |
| Unpaid-tax flag и tax records | `tax_info` |
| Bankruptcy publications | `bankruptcy` |
| Direct enforcement | Нет eligible source в H1 v1. |

`batch_cards` может стать только supplemental source после отдельной
field-level верификации. Он не переопределяет профильный источник. При
противоречии профильный факт не заменяется batch-значением; конфликт
регистрируется как limitation. FSSP/risk flags из `batch_cards` не образуют
публичный FSSP или debt fact.

## 6. Coverage и completeness

Lifecycle-required datasets остаются отдельным решением агрегата. Для
совместимой будущей реализации H1 v1 утверждённый baseline:

```text
required: counterparty, finance, arbitration
optional enrichment: tax_info, bankruptcy
counterparty optional blocks: ADDRESS_BLOCK, MANAGER_BLOCK, OWNER_BLOCK
blocked: fssp
not public: contacts
```

H1 coverage показывает dataset и field-level состояние. Процент `3/3` означает
только доступность lifecycle-required datasets и не называется «полнотой
сведений о компании».

Lifecycle и snapshot v2 используют точную матрицу:

| Required availability | Optional state | Report status | Required completeness | H1 coverage |
| --- | --- | --- | --- | --- |
| 3 из 3 available | любой | `complete` | `3/3` | Optional показывается отдельно. |
| 1–2 из 3 available | любой | `partial` | `1/3` или `2/3` | Доступные required и optional facts сохраняются. |
| 0 из 3 available | любой | `failed` | `0/3` | Optional не превращает failed report в complete/partial. |

`datasets` snapshot v1/v2 продолжает содержать только три required dataset
reports. Snapshot v2 получает отдельный additive `optional_datasets` envelope
с default `{}` и typed facts `tax_info`/`bankruptcy`. Отсутствующий ключ
означает `not_requested`; failed optional call сохраняет safe status/limitation.
Required `CompanyReportCompleteness` и существующий `ReportFreshness` считаются
только по required datasets. Optional `source_received_at` живёт в block/source
registry H1 и не изменяет required freshness задним числом.

Optional coverage mapping:

| Public state | Facts | Optional source time |
| --- | --- | --- |
| `available` | Safe normalized facts. | Обязателен `source_received_at`. |
| `available_empty` | Только доказанный exact scoped zero. | Обязателен `source_received_at`. |
| `partial` | Доступный slice плюс `total/returned/limit/offset`. | Обязателен `source_received_at`. |
| `not_requested` | Нет; возможен allowlisted gate limitation. | Нет. |
| `not_found` | Нет. | Нет, если evidence contract не доказывает отдельную safe source date. |
| `failed` | Нет; только safe limitation. | Нет. |
| `conflict` | Конфликтный field скрыт. | Разрешены timestamps успешно полученных источников. |

`available_empty` и `partial` являются public projection states поверх
внутреннего successful dataset envelope, а не новыми значениями текущего
`DatasetReportStatus`.

Для slice datasets показываются `total`, `returned`, `limit`, `offset`.
Successful scoped zero допустим только при доказанном success и exact subject;
missing/failed/not requested никогда не становится нулём.

## 7. Запрещённые публичные данные и выводы

H1 v1 не показывает и не включает в metadata/JSON-LD:

- scoring points/level, probability, rating или traffic light;
- вердикт надёжности, платёжеспособности или рекомендацию заключать сделку;
- AI-generated new facts;
- утверждение `долгов нет`;
- утверждение о текущем банкротстве только по публикации;
- FSSP/debt факт из indirect flags или failed/403 call;
- unverified phone, email, website или social link;
- raw provider content, arbitrary parties/documents и PII без approval;
- transport/internal metadata и секреты.

Signals/scoring могут оставаться внутренними слоями существующего продукта и
технического sufficiency gate, но не входят в H1 public projection и не меняют
текст исходных фактов.

## 8. Детерминированность и совместимость

1. Одинаковый immutable snapshot и contract version дают одинаковый block
   manifest, факты, порядок, форматирование и limitations.
2. Публичная проекция не вызывает provider, AI или worker на read path.
3. Старые snapshots не переписываются. Утверждена computed
   `company_public_h1_v1` projection; отдельная таблица и миграция БД не нужны.
   Новые reports используют snapshot `report_version="2"`, parser продолжает
   читать v1 как `optional_datasets={}`.
4. Legacy `provider_units_unknown` не меняется в persistence. После finance
   evidence gate H1 projection может применить утверждённое source-specific
   правило; существующий API field сохраняется для старых клиентов либо
   получает совместимый versioned migration path.
5. Новые `tax_info`/`bankruptcy` поля additive; их отсутствие в старой записи
   имеет состояние `not_requested`, а не scoped zero.
6. Миграция БД для спецификации и computed runtime projection не требуется;
   строковое поле существующего `report_version` хранит `2` без schema change.

## 9. Эталонная текстовая проекция: ООО «Яндекс»

Пример использует фиксированный исследовательский snapshot, а не live-проверку
на дату чтения документа.

```text
URL
/company/7736207543-ooo-yandeks

TITLE
ООО «Яндекс» — ИНН 7736207543: реквизиты, финансы и арбитраж | CompanyReport

H1
Общество с ограниченной ответственностью «Яндекс» — ИНН 7736207543

СТАТУС И РЕКВИЗИТЫ
ОГРН: 1027700229193
КПП: 770401001
Статус: Действует
Дата регистрации: 14 сентября 2000 года
Регион: Москва
Юридический адрес: 119021, Россия, г. Москва,
ул. Льва Толстого, д. 16
По данным отчёта, сформированного 8 августа 2026 года.

ФИНАНСЫ
Выручка в 2024 году изменилась на +29,1% относительно 2023 года.
Абсолютные значения до finance evidence gate не показываются. После активации
`datanewton_finance_thousand_rub_v1` значение 273325 thousand_rub получает
backend display `273,3 млн ₽`.

АРБИТРАЖ
Источник сообщил 1 448 дел и передал 100 карточек.
Распределения ролей относятся только к этим 100 карточкам.
Каждое дело входит ровно в один bucket; multiple roles → «Другое»;
name-only/no exact identifier → «Роль не подтверждена».

БАНКРОТНЫЕ ПУБЛИКАЦИИ
До bankruptcy_schema_v1 блок скрыт с coverage not_requested и limitation
schema_gate_not_passed. После gate исследовательский snapshot-кандидат может
дать 29 публикаций: 28 намерений должника и 1 намерение кредитора обратиться в
суд. Эти числа не являются acceptance fixture без evidence artifact.
Публикации не подтверждают принятие заявления, возбужденное дело, признание
банкротом или текущую процедуру.

НАЛОГИ
До tax_info_schema_v1 блок скрыт. После доказанного scoped boolean=false
показывается: «Признак неоплаченной налоговой задолженности не установлен».

РУКОВОДИТЕЛЬ И ВЛАДЕЛЬЦЫ
Показываются только при наличии safe имени/организации, роли/типа,
даты/доли и допустимой privacy state. Пустые или information-limited записи
не превращаются в выдуманные факты.

КОНТАКТЫ
Не публикуются в H1 v1.

ИСТОЧНИКИ И ОГРАНИЧЕНИЯ
Показываются даты dataset, coverage, total/returned и все material limitations.
```

## 10. Acceptance criteria спецификации

- [x] Один H1 URL и page manifest определены.
- [x] `checked_at` отделён от effective date и текущего времени чтения.
- [x] Утверждены `checked_date_msk_v1` и единый published/latest-unpublished
  snapshot resolver для SSR и SPA.
- [x] Отсутствие автоматического обновления существующего report закреплено.
- [x] Finance `thousand_rub` зафиксирован как candidate policy; до evidence
  абсолютные суммы запрещены, Decimal conversion/display определены условно.
- [x] Arbitration exact-ID attribution, conflicts, multiple-role `other` и
  `unattributed` определены без двойного счёта.
- [x] Candidate bankruptcy allowlist и non-status wording определены; вывод
  заблокирован до bankruptcy_schema_v1.
- [x] Утверждена налоговая false-flag формулировка; вывод заблокирован до
  tax_info_schema_v1.
- [x] Address, manager и owners разрешены условно; contacts запрещены.
- [x] Source precedence и batch/FSSP ограничения определены.
- [x] Missing/partial/failed/conflict не маскируются.
- [x] Scoring, verdict и raw/internal data исключены из public projection.
- [x] Совместимость старых immutable snapshots описана.
- [x] Public endpoint/DTO identity, computed projection и optional lifecycle
  matrix определены.

## 11. Риски и контроль

| Риск | Контроль |
| --- | --- |
| Неверная глобальная finance unit | Evidence gate до изменения runtime; Decimal fixtures и официальный источник. |
| Старый report выглядит свежим | Всегда показывать immutable `checked_at`; не использовать current read time. |
| Двойной счёт судебного дела | Один case — один role bucket; invariant tests. |
| Название приписывает дело другой компании | Только exact typed INN/OGRN; name-only → `unattributed`. |
| Публикация превращается в статус банкротства | Schema-gated candidate type allowlist и обязательный semantic disclaimer. |
| False tax flag превращается в «долгов нет» | Только утверждённая узкая формулировка плюс coverage/date. |
| Batch contacts/risks попадают на страницу | Recursive allowlist и explicit contact/FSSP prohibition. |
| Ломаются старые snapshot/API clients | Additive versioned projection; без rewrite старых записей. |
| SSR и SPA показывают разные runs | Один resolver; active publication pin имеет приоритет, republish атомарно меняет snapshot. |
| Opaque payload трактуется как доказанный schema | Отдельные finance/tax/bankruptcy/owners evidence gates до mapping и публичного вывода. |
| Optional failure меняет lifecycle | Required status/completeness считают только фиксированные три datasets; optional envelope отдельный. |

## 12. Открытые вопросы

Блокирующих продуктовых и архитектурных вопросов для формулировки контракта
нет: computed projection, endpoint, snapshot resolver, timezone и optional
lifecycle выбраны.

До включения соответствующих runtime-возможностей обязательны evidence и
operational gates:

1. `finance_unit_evidence_v1`: официальный контракт DataNewton либо
   воспроизводимая матрица DataNewton → ГИР БО/ОКЕИ.
2. `tax_info_schema_v1`, `bankruptcy_schema_v1`, `owner_schema_v1`: официальные
   схемы или минимальные safe fixtures с exact paths, types, scope и dates.
3. `management_privacy_v1` для публичных имён руководителей и
   физлиц-владельцев по формам; до него management person records скрыты с
   `privacy_gate_not_passed`. ИННФЛ руководителя запрещён независимо от
   результата.
4. Operational approval для добавления `tax_info`, `bankruptcy` и OWNER_BLOCK
   в каждый новый run: тариф, quota amplification, pagination, timeouts,
   retry/cache policy и деградация. Непройденный gate даёт `not_requested`.
5. Production live probe выполняется только по отдельному разрешению и не
   сохраняет raw в репозиторий.

## 13. Результаты проверок и review

- Runtime-тесты: не применимы к документационной итерации.
- `DEVFLOW_STATE.yaml`: успешно разобран YAML; IDs 1–18 уникальны и упорядочены.
- Новые Markdown-файлы: code fences сбалансированы, trailing whitespace не
  обнаружен.
- `git diff --check`: успешно.
- Первый независимый reviewer: `CHANGES_REQUIRED`.
- Corrective pass: выполнен; первый повторный verdict `CHANGES_REQUIRED`,
  замечания закрыты в том же документационном scope.
- Итоговый повторный reviewer: `VERDICT: APPROVED` (`2026-08-19`).
- Итоговое решение review: `approved`.
