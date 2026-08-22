# Итерация 18 — Публичная React-страница H1 CompanyReport

ID: `18`
Slug: `company-report-h1-frontend`
Contract: `company_public_h1_v1`
Branch: `feat/iteration-18-company-report-h1-frontend`
Base commit: `c5f20fdedbc068fb9462cf230d512d510d6c294a`
Статус спецификации: `reviewed_after_correction`
Зависимость: merged iteration 17 (`f4ea53762be9228b8b46fdac0a9a3150dc538bf6`)

## 1. Цель

Перевести публичный React-маршрут `/company/{inn}` и
`/company/{inn}-{slug}` с legacy `GET /company-reports/{inn}` на единственный
источник фактов:

```http
GET /company-reports/{inn}/public-h1
```

Страница отображает strict `company_public_h1_v1` без клиентского выбора
snapshot, интерпретации provider paths, вычисления source semantics,
преобразования timezone, округления Decimal, scoring, verdict или AI.

Canonical и plain-INN страницы остаются публичными и одинаковыми для anonymous
и authenticated пользователя. Чтение существующего отчёта не обновляет его и
не создаёт provider run.

## 2. Source of truth и runtime-граница

Нормативные источники:

- `AGENTS.md`, `README.md`, Roadmap и DevFlow state;
- утверждённый H1 contract iteration 16;
- merged specification, plan, code и tests iteration 17;
- текущие React route, lifecycle, landing и Claims handoff iteration 14–15.

Merged iteration 17 намеренно уже полной reserved topology H1:

- `identity.status_code`, `status_label`, `status_effective_at` равны `null`;
- `blocks.requisites.legal_form` равен `null`;
- finance money и `unit_policy_version` отсутствуют, разрешён только
  backend-generated YoY;
- `blocks.tax`, `blocks.bankruptcy`, `blocks.management` равны `null`;
- `internal_links=[]`;
- соответствующие coverage имеют `not_requested` и фиксированные limitations.

Iteration 18 соблюдает эту границу:

1. TypeScript сохраняет reserved iteration-16 types для `PublicMoney`, tax,
   bankruptcy, management и internal links.
2. Detached tests фиксируют их structural topology.
3. Root parser текущего `company_public_h1_v1` принимает только разрешённый
   merged iteration-17 runtime.
4. Non-null disabled block, finance money, status/legal-form fact или non-empty
   internal links дают fail-safe `contract_mismatch`.
5. Dormant runtime rendering для этих значений отсутствует.
6. Будущая активация требует отдельного backend evidence gate и согласованного
   client update.

## 3. Scope

В scope:

1. Полная TypeScript topology `company_public_h1_v1` и runtime parser без
   новых dependencies.
2. `/public-h1` как единственный factual read страницы.
3. Legacy create/status только для lifecycle до finalized H1.
4. Canonical path только из validated backend response.
5. DTO-driven renderer для текущих runtime blocks:
   breadcrumbs, identity/status shell, known summary, in-page navigation,
   coverage/date, requisites, finance YoY, arbitration, sources/limitations и
   neutral actions.
6. Loading, pending, terminal, contract и transport states.
7. Path-scoped SPA всегда остаётся `noindex,follow`; published SSR/sitemap
   остаются единственным authority для indexability.
8. Responsive, accessibility, privacy и deterministic formatting.
9. Safe published SSR/API/SPA fixture parity и latest-unpublished API/SPA
   fixture parity.
10. Frontend gates, Product API contract regression и DevFlow docs/state.

## 4. Вне scope

- Product API, DTO, resolver, lifecycle и source-semantics changes.
- DB schema, Alembic, snapshots, backfill и publication writes.
- DataNewton/provider calls, live probes, optional evidence gates.
- Finance unit activation и абсолютные monetary facts.
- Tax, bankruptcy, management и internal-link runtime activation.
- Refresh button, TTL и automatic refresh existing report.
- Score, verdict, probability, signals, rating и AI controls.
- Contacts, phone, email, website, social links и FSSP.
- New SEO publication, sitemap, SSR routing, nginx или deployment rollout.
- Gateway, Docker и production operations.
- Новые dependencies, `package.json` или lockfile.
- Redesign landing `/`, Claims flow или других страниц.

## 5. API и TypeScript contract

### 5.1. Lifecycle types

Legacy lifecycle остаётся только для create/poll:

```text
CompanyReportAccepted:
  report_id: string
  status: "pending"
  reused: boolean

CompanyReportLifecycle:
  report_id: string
  status: "pending" | "complete" | "partial" | "failed"
  started_at: string
  generated_at: string | null
  finished_at: string | null
  fresh_until: string | null
```

Legacy latest response, signals, scoring и AI больше не являются page-facing
типами H1 renderer.

### 5.2. Root topology

```text
CompanyPublicH1Response:
  contract_version: "company_public_h1_v1"
  report_id: UUID
  report_version: "1" | "2"
  projection_scope: "published" | "latest_unpublished"
  canonical_path: /company/{same-inn}-{slug}
  indexable: boolean
  checked_at: UTC ISO datetime
  checked_date: ISO date
  checked_date_display: string
  identity: CompanyPublicIdentity
  block_order: PublicBlockId[]
  blocks: CompanyPublicH1Blocks
  coverage: PublicCoverageItem[6]
  sources: PublicSourceItem[]
  limitations: PublicLimitation[]
  actions: PublicAction[2]
  breadcrumbs: PublicBreadcrumb[2]
  internal_links: PublicInternalLink[]
```

`PublicBlockId` allowlist:

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

### 5.3. Current factual blocks и числовые типы

```text
CompanyPublicIdentity:
  legal_full_name: string
  legal_short_name: string | null
  display_name: string
  inn: 10/12 ASCII digits
  status_code/status_label/status_effective_at: null in current root

RequisitesBlock:
  legal_form: null in current root
  ogrn_or_ogrnip: 13/15 ASCII digits | null
  kpp: 9 ASCII digits | null
  registration_date/dissolved_date: ISO date | null
  region: {code: string|null, name: string|null} | null
  legal_address: PublicAddress | null

PublicAddress:
  display_line: string
  postal_code/country/region/city/street/house/office: string | null
  is_inaccuracy: boolean | null

FinanceBlock:
  unit_policy_version: null in current root
  metrics: FinanceMetric[1..N]

FinanceMetric:
  metric_id: approved PublicFinanceMetricId
  year: safe integer
  money: null in current root
  yoy: PublicPercentChange

PublicPercentChange:
  exact_percent: canonical Decimal string
  display_value: backend string
  current_year/previous_year: safe integer
  formula_version: "finance_yoy_v1"
```

```text
ArbitrationBlock:
  total_cases/returned_cases/normalized_case_count/malformed_count:
    safe integer >= 0
  limit: safe integer >= 1
  offset: safe integer >= 0
  role_counts: safe non-negative integer counters
  unattributed_count: safe integer >= 0
  status_counts/result_counts: safe non-negative integer counters
  claim_amounts: ArbitrationClaimAmount[]
  selected_cases: PublicArbitrationCase[0..10]
```

JSON numeric fields остаются TypeScript `number`:

- `FinanceMetric.year`;
- `current_year`, `previous_year`;
- arbitration counts;
- coverage `total`, `returned`, `limit`, `offset`;
- bankruptcy/tax/management reserved integer counters, где они определены
  contract.

Каждый такой field принимается только при `Number.isSafeInteger(value)`.
Counts/offset требуют `>= 0`, limit требует `>= 1`. Parser отвергает numeric
strings, fractions, `NaN`, infinities, unsafe integers и отрицательные counts.

Запрет JavaScript numeric conversion распространяется только на exact Decimal
fields и связанные backend display strings:

```text
PublicMoney.source_decimal
PublicMoney.rub_decimal
PublicPercentChange.exact_percent
ArbitrationClaimAmount.exact_decimal
PublicOwner.share_percent_decimal
PublicMoney.display_value
PublicPercentChange.display_value
ArbitrationClaimAmount.display_value
```

Для них запрещены `Number`, unary `+`, `parseInt`, `parseFloat`, arithmetic с
IEEE-754 и locale formatting. Exact и display strings сохраняются без
преобразования.

Reserved `PublicMoney`, `BankruptcyBlock`, `TaxBlock`, `ManagementBlock` и
`PublicInternalLink` точно повторяют iteration 17, но не эмитятся current root.

### 5.4. Coverage, sources и limitations

Coverage имеет exact order/mapping:

| # | block_id | dataset |
|---:|---|---|
| 1 | `requisites` | `counterparty` |
| 2 | `finance` | `finance` |
| 3 | `arbitration` | `arbitration` |
| 4 | `bankruptcy` | `bankruptcy` |
| 5 | `tax` | `tax_info` |
| 6 | `management` | `counterparty` |

States сохраняются без слияния:

```text
available | available_empty | not_found | not_requested |
partial | failed | conflict
```

Sources уникальны и следуют order:

```text
counterparty → finance → arbitration → tax_info → bankruptcy
```

Allowed normalization versions:

```text
counterparty_normalizer_v1
finance_normalizer_v1
arbitration_normalizer_v1
arbitration_normalizer_v2
```

Limitations принимаются только из exact merged iteration-17 catalog. Их
backend message отображается verbatim и не усиливается браузером.

### 5.5. Runtime parser

`parseCompanyPublicH1(value: unknown)`:

1. Не выполняет coercion.
2. Требует exact contract version.
3. Рекурсивно требует exact object keys, соответствуя backend
   `extra="forbid"`; любой unknown key является mismatch.
4. Проверяет scalar types, safe/lossless integer constraints, ASCII
   identifiers, UUID, ISO date/datetime и canonical Decimal strings.
5. Проверяет `canonical_path` как same-origin path с тем же INN.
6. Проверяет fixed coverage/source/action/breadcrumb order и `report_id` в
   `prepare_claim`.
7. Проверяет block order, отсутствие duplicates и nullable block consistency.
8. Проверяет `latest_unpublished => indexable=false`.
9. Проверяет current-runtime disabled gates.
10. Выполняет recursive forbidden-field audit.
11. Строит новый allowlisted object; исходный JSON не сохраняется.
12. Unknown block, limitation, dataset, metric, role, action или normalization
    value даёт
    mismatch.
13. Ошибка содержит только stable code
    `company_public_h1_contract_mismatch`, без payload/ИНН/company name.
14. Parser не логирует raw response и не добавляет telemetry.

### 5.6. Exact mirrored client invariants

Client parser зеркалит structural/serialization invariants merged iteration 17,
но не становится источником backend policy.

| Surface | Exact client invariant |
|---|---|
| Safe integers | Years/counts/limit/offset are `Number.isSafeInteger`; counts/offset `>=0`, limit `>=1`. |
| YoY periods | `previous_year === current_year - 1`; оба safe integers. |
| YoY exact value | `exact_percent` — canonical Decimal string. |
| YoY display | `display_value` имеет signed one-decimal percent shape; pure decimal-string validation подтверждает approved `ROUND_HALF_UP` relation, но original server string сохраняется. |
| Finance block | `metrics.length >= 1`; в current root у каждого metric `money===null`, `yoy!==null`, а `unit_policy_version===null`. |
| Claim currency | Exact regex `^[A-Z][A-Z0-9_-]{2,15}$`. |
| Claim display | `display_value === exact_decimal.replace(".", ",") + " " + currency`; exact string сохраняется. |
| Case claim role | Case amount разрешён только при `attributed_role` `plaintiff|respondent`, и `claim_amount.role === attributed_role`. |
| Aggregate claim role | Aggregate amount role — только `plaintiff|respondent`. |
| Arbitration role sum | `sum(role_counts) + unattributed_count === normalized_case_count`. |
| Arbitration returned sum | `normalized_case_count + malformed_count === returned_cases`. |
| Arbitration status sum | `sum(status_counts) === normalized_case_count`. |
| Arbitration result sum | `sum(result_counts) === normalized_case_count`. |
| Coverage references | Каждый `coverage[*].limitation_codes[*]` имеет exact present root limitation с тем же code и catalog-approved block/field/message. |
| Coverage order | Ровно шесть items в exact factual order и dataset mapping из § 5.4. |
| Sources | Unique datasets, exact source precedence и honest normalization version. |
| Current blocks | `requisites` non-null; `tax`, `bankruptcy`, `management` null; `internal_links=[]`. |
| Current status/form | Identity status fields и `requisites.legal_form` null. |
| Optional coverage | Bankruptcy/tax/management: `not_requested`, все numeric slice fields null, exact gate codes в backend order. |
| Block order | Exact sequence вычисляется только из presence разобранных current blocks: required shell, optional in-page nav iff factual count >=2, затем current factual order, sources/limitations, actions. |
| Actions | Ровно `check_another_company` и `prepare_claim`; exact labels/paths; claims UUID равен root `report_id`. |
| Breadcrumbs | Ровно `Главная` `/` и `identity.display_name`/root `canonical_path`. |
| Projection | `latest_unpublished` никогда не `indexable=true`. |

Backend-authoritative policies не пересчитываются как facts:

- client не преобразует `checked_at` в Moscow date;
- client не проверяет Moscow calendar через `Date`, timezone database или
  process/browser locale;
- client проверяет только UTC timestamp grammar, ISO `checked_date`, Russian
  month catalog и string relationship
  `{day without leading zero} {genitive month} {year} года`;
- client не создаёт `checked_date`/`checked_date_display`, а сохраняет server
  values;
- client не создаёт rounded percent/amount display;
- decimal-string validators могут только подтвердить approved serialization
  relationship и вернуть original server strings;
- current time не участвует ни в одной validation/rendering policy.

## 6. Routing и lifecycle

### 6.1. Canonical route

Для `/company/{inn}-{slug}`:

1. Parse strict key и вызвать public-H1.
2. `200` проверить parser; wrong slug replace-навигацией привести к backend
   `canonical_path` и отрисовать тот же DTO.
3. `409 report_pending` разрешает только read-only status polling.
4. `404`, `report_failed`, `report_not_eligible` и другие `409` не вызывают
   POST.
5. Existing report никогда не refresh-ится.

### 6.2. Plain-INN route

Для `/company/{inn}`:

1. Сначала public-H1.
2. `200` → replace на `canonical_path` и render того же DTO.
3. `409 report_pending` → existing status polling.
4. Только exact `404 company_report_not_found` → один POST, затем polling.
5. После terminal status снова public-H1.
6. `report_failed`, `report_not_eligible` и
   `public_projection_invalid` — terminal без POST/legacy fallback.

### 6.3. Concurrency

- Active H1/create request и poll имеют отдельные AbortControllers.
- Есть не более одного poll timer/request.
- Navigation на другой INN abort-ит старые операции.
- Late response не меняет новый DOM/URL.
- StrictMode не создаёт duplicate POST.
- Auto-create key включает route kind и INN.
- Cleanup отменяет timers/controllers.

При успешном H1 response перед replace-navigation page сохраняет optional
parsed DTO в in-memory ref:

```text
{inn, canonical_path, dto}
```

После route update ref потребляется только при exact same INN и exact new
pathname. В этом случае второй H1 read не выполняется. Ref одноразовый,
очищается после consumption, route change, error или unmount; cross-INN/stale
DTO отвергается. DTO не записывается в URL, `history.state`, session/local
storage или telemetry. Если component действительно remount-ился и ref
недоступен, обычный read остаётся безопасным fallback.

## 7. UI state matrix

H1 DTO не содержит overall lifecycle status. UI не выводит badge
`complete/partial` и не выводит его из coverage.

| Input | UI | Create/retry |
|---|---|---|
| Initial read | «Загружаем сведения о компании», `aria-busy` | Нет |
| Plain exact 404 | POST один раз, затем pending | Только здесь auto-create |
| `report_pending` / POST 202 | Semantic formation stages, polling | Без duplicate action |
| H1 200 | Blocks из `block_order` | Без refresh |
| Coverage partial/failed/not_found/conflict | Server state + limitations | Без overall badge |
| Canonical 404 | «Публичный отчёт не найден» | Без create |
| `report_failed` | «Отчёт не сформирован» | Без create |
| `report_not_eligible` | «Публичный отчёт недоступен» | Без create |
| Invalid key | Safe local error | 0 API calls |
| 429 | Safe rate-limit copy | Retry current read/status |
| 503/network | Safe temporary-unavailable copy | Retry current operation |
| Projection invalid | Safe terminal copy | Без fallback/create |
| Contract mismatch | Unsupported format copy | Без raw detail/create |
| Abort/stale | Не показывается как ошибка | Нет |

`aria-live` сообщает semantic lifecycle transition, не каждый poll tick.

## 8. Rendering manifest

Renderer итерирует `block_order` через exhaustive local registry. Unknown ID
не создаёт DOM и уже должен быть отклонён parser.

### 8.1. Breadcrumbs и identity

- Breadcrumbs: backend labels/paths; второй элемент `aria-current="page"`.
- Hero содержит единственный page `h1`:
  `{identity.legal_full_name} — ИНН {identity.inn}`.
- Short name выводится только если отличается от full name.
- Report date:
  `По данным отчёта, сформированного {checked_date_display}.`
- `<time datetime={checked_at}>` сохраняет backend display verbatim.
- Current runtime не получает status badge и не угадывает legal status.

### 8.2. Known summary и in-page navigation

«Что известно» перечисляет только non-null factual blocks в backend order:
requisites, finance и arbitration. Navigation рендерится только при наличии
соответствующего ID и ведёт только к существующим sections.

### 8.3. Coverage/date

Заголовок: «Покрытие и дата проверки».

Обязательное пояснение:

```text
Дата относится к сохранённому отчёту и не является датой просмотра страницы.
```

| State | Label |
|---|---|
| `available` | Сведения доступны |
| `available_empty` | Источник успешно проверен; в подтверждённой области ответа записей нет |
| `not_found` | Источник не нашёл сведения в своей области ответа |
| `not_requested` | Сведения не запрашивались |
| `partial` | Доступна часть сведений |
| `failed` | Сведения недоступны |
| `conflict` | Сведения противоречивы |

Counts/pagination показываются только при non-null. Missing не становится zero.

### 8.4. Requisites

Блок показывает только non-null OGRN/OGRNIP, KPP, registration/dissolution
dates, region и legal address. ISO date форматируется string-only
`YYYY-MM-DD → DD.MM.YYYY`, без `Date`, locale или timezone. Structured address
не склеивается в новый invented address. Inaccuracy связывается с limitation.

### 8.5. Finance

Current runtime показывает только YoY row:

```text
{metric label}: {current_year} к {previous_year} — {yoy.display_value}
```

Metric labels используют closed registry из iteration-16 allowlist. Exact
percent остаётся string; знак не получает good/bad color. Money и unit не
выводятся. Arbitration amount остаётся отдельным backend display string и не
зависит от finance unit gate.

### 8.6. Arbitration

Отдельно показываются source total, returned, normalized, malformed, limit и
offset. Role/status/result distributions явно относятся только к
нормализованным карточкам сохранённого ответа. `other` и `unattributed`
различаются. Claim amounts и selected-case amount используют только backend
`display_value`. Party names/IDs, internal ID, documents и links отсутствуют.

`available_empty` показывает scoped numeric `0/0`, но не создаёт универсальную
фразу «арбитражных дел нет». Partial slice всегда показывает pagination и
fixed limitation.

### 8.7. Sources, limitations и actions

- Source timestamps/dates остаются exact strings; browser timezone не
  применяется.
- Limitation message показывается verbatim в backend order и получает stable
  DOM ID; factual/coverage section связывается через `aria-describedby`.
- Ровно две backend actions в backend order:
  `check_another_company` и `prepare_claim`.
- Claims path содержит displayed root `report_id`.
- Reserved blocks и internal links не имеют reachable runtime sections.

## 9. Accessibility и responsive

- Для CompanyReport SPA route устанавливается route-scoped `lang=ru`.
- Один h1; следующие sections h2, subsections h3.
- Разные accessible names для breadcrumbs, in-page nav и actions.
- Requisites/counts используют `<dl>`; dense data — labelled scroll region или
  responsive cards.
- Loading/pending имеют `aria-busy`; live-region не шумит на каждом poll.
- После semantic content/error transition focus переносится на heading.
- Native links/buttons, visible focus, target height >= 44px.
- Color не является единственным carrier state.
- Long name/address/case/UUID/amount используют `overflow-wrap:anywhere`.
- `prefers-reduced-motion` отключает необязательные transitions.

Widths `1440`, `768`, `390` проходят:

```text
document.documentElement.scrollWidth <= clientWidth
document.body.scrollWidth <= clientWidth
```

## 10. SEO, document head и SPA fallback

Iteration 17 остаётся единственным authority для indexability:

- published SSR HTTP status/body/robots;
- publication pin;
- sitemap membership;
- canonical redirect.

React SPA никогда не promote-ит company fallback до `index,follow`, даже если
DTO имеет `projection_scope=published` и `indexable=true`. Indexable document —
только backend SSR/sitemap surface. Любой company SPA state остаётся
`noindex,follow`.

Единый owner contract для head nodes:

```text
data-company-report-head-owner="company-report-h1-v1"
data-company-report-head-kind="robots" | "canonical"
```

Правила:

1. Inline bootstrap находится в `index.html` до Yandex telemetry.
2. Bootstrap ничего не отправляет, не логирует и не вызывает `ym`.
3. Он проверяет только strict company pathname grammar; query не отменяет
   protective noindex.
4. Для company path он route-scoped устанавливает
   `document.documentElement.lang="ru"`.
5. Он находит все owned robots nodes, сохраняет/создаёт первый, удаляет только
   owned duplicates и устанавливает `name="robots" content="noindex,follow"`.
6. В результате существует ровно один owned robots meta.
7. Non-company path не меняет lang/head.
8. React head manager использует те же owner/kind constants и принимает
   bootstrap node во владение, не создавая второй.
9. Loading, pending, content, unpublished и every error сохраняют ровно один
   owned `noindex,follow`.
10. После parsed DTO manager создаёт либо обновляет ровно один owned canonical
    link с validated `canonical_path`; до DTO owned canonical отсутствует.
11. Dynamic title строится только после parsed DTO:
    `{identity.display_name} — ИНН {identity.inn}`.
    Loading/error title использует fixed safe copy без company payload.
12. При уходе с company route cleanup удаляет только owned robots/canonical
    nodes, восстанавливает previous title/lang и не трогает unowned metadata.
13. После cleanup на non-company route нет stale owned noindex.
14. Published backend SSR не использует SPA bootstrap и остаётся indexable
    согласно iteration 17.
15. JSON-LD, sitemap, synthetic description и new telemetry не добавляются.

Ограничение фиксируется явно: JavaScript meta не определяет initial HTTP
`X-Robots-Tag`. Header для SPA fallback остаётся существующей server/deploy
responsibility и не меняется iteration 18.

## 11. Privacy и security

Renderer/state/DOM/metadata/fixtures не содержат raw payload, transport/job
metadata, secrets, contacts, manager INNFL, unapproved owner/person data,
FSSP, signals, scoring, verdict, probability или AI. Нет hidden serialized
response JSON и generic object renderer. React text escaping и same-origin path
validation обязательны. Existing telemetry не получает новых events/payloads.

Допустимые root parity attributes ограничены contract/report version/scope,
report id, canonical path, indexability и block order.

## 12. Fixtures и parity

Tracked synthetic fixtures:

1. Published v2 JSON с synthetic long legal name/address, finance YoY, partial
   arbitration slice, ровно десять selected cases с long safe case numbers и
   всеми disabled optional gates.
2. Exact deterministic SSR HTML из merged iteration-17 renderer для этого JSON.
3. Latest-unpublished JSON с safe unavailable/limitation cases.

Published semantic parity сравнивает report/canonical identity, block order,
checked date, factual scalars, backend display strings, coverage, sources,
limitations, actions и breadcrumbs. Local Russian field labels могут отличаться
от технических SSR labels. Latest-unpublished имеет API/parser/SPA parity,
`noindex` и не заявляет SSR parity.

Fixtures synthetic, без production INN, raw provider content и contacts.

### 12.1. Reproducible real-browser QA

QA не добавляет production/test dependency и не создаёт tracked helper.

Environment:

- current iteration-18 worktree;
- already installed local frontend dependencies;
- Python standard library;
- existing Vite `DEV_API_PROXY_TARGET`;
- loopback only;
- tracked published/latest fixtures.

Temporary assets создаются только под unique directory в OS temp. Temporary
Python mock server:

- bind `127.0.0.1`;
- serves an exact allowlist of H1 GET paths from tracked JSON fixtures;
- sends `Content-Type: application/json`;
- returns 404 for all other paths;
- performs no POST, network forwarding, file write or telemetry.

Start protocol:

1. Record `git status --short`.
2. Create unique OS-temp directory; resolve and verify it is outside repository.
3. Choose two explicit loopback ports and fail if either already listens; do
   not kill unrelated processes.
4. Start mock process hidden; retain exact PID.
5. Start Vite hidden with
   `DEV_API_PROXY_TARGET=http://127.0.0.1:{mockPort}` and
   `--host 127.0.0.1 --port {vitePort} --strictPort`; retain exact PID.
6. Use bounded readiness probes, maximum 30 seconds per process.
7. Open only loopback published and latest-unpublished company URLs.

Browser matrix:

```text
1440 × 1000
768 × 1024
390 × 844
```

At every viewport verify:

- root contract/report/scope/block attributes;
- long name/address/case wrapping;
- all ten cases reachable/readable;
- document/body `scrollWidth <= clientWidth`;
- any dense-region scroll remains local;
- one h1 and correct h2/h3 order;
- `lang=ru`;
- exactly one owned robots meta with `noindex,follow`;
- exactly one owned canonical after content load;
- keyboard Tab/Shift+Tab order through breadcrumbs, in-page navigation,
  focusable dense region and actions;
- visible focus and Enter activation for safe internal navigation;
- focus lands on semantic heading after load/error;
- limitations are reachable and described;
- reduced-motion mode has no required animation.

Screenshots use only safe fixture content and are stored under the same OS-temp
directory for inspection. They are not copied into the repository.

Stop/cleanup protocol executes in `finally`:

1. Stop only the two exact retained PIDs.
2. Wait boundedly and verify both exited.
3. Verify cleanup target resolves under OS temp and has the unique iteration-18
   prefix.
4. Remove only that exact temporary directory.
5. Verify no mock/Vite listener remains on the selected ports.
6. Verify repository contains no QA screenshot/server/temp artifact.
7. Compare final `git status --short` with the recorded pre-QA status.

QA report records viewports, overflow booleans, keyboard/focus result and
cleanup result as text in the DevFlow final report; no tracked evidence file is
added.

## 13. Exact changed-file manifest

Documentation/state:

```text
docs/development/DEVFLOW_STATE.yaml
docs/development/iterations/iteration-18-company-report-h1-frontend.md
docs/development/plans/iteration-18-company-report-h1-frontend.md
```

Frontend production:

```text
services/web_ui/index.html
services/web_ui/src/companyReport/companyReportTypes.ts
services/web_ui/src/companyReport/companyReportApi.ts
services/web_ui/src/companyReport/companyReportPresentation.ts
services/web_ui/src/companyReport/companyReportH1Contract.ts
services/web_ui/src/components/company-report/CompanyReportContent.tsx
services/web_ui/src/components/company-report/CompanyReportH1Blocks.tsx
services/web_ui/src/pages/CompanyReportPage.tsx
services/web_ui/src/index.css
```

Fixtures:

```text
services/web_ui/src/companyReport/fixtures/company-public-h1-published.json
services/web_ui/src/companyReport/fixtures/company-public-h1-published-ssr.html
services/web_ui/src/companyReport/fixtures/company-public-h1-latest-unpublished.json
```

Tests:

```text
services/web_ui/src/companyReport/companyReportApi.test.ts
services/web_ui/src/companyReport/companyReportPresentation.test.ts
services/web_ui/src/companyReport/companyReportH1Contract.test.ts
services/web_ui/src/components/company-report/CompanyReportContent.test.tsx
services/web_ui/src/components/company-report/CompanyReportH1Blocks.test.tsx
services/web_ui/src/pages/CompanyReportPage.test.tsx
services/web_ui/src/router/PublicCompanyReportFlow.test.tsx
```

No wildcard manifest expansion. Explicitly unchanged: package/lock,
`AppRouter.tsx`, Claims production, Product/Gateway API, shared, deploy,
workflows, compose и Roadmap.

## 14. Compatibility и rollback

- Public route остаётся без RequireAuth.
- Landing ведёт на plain resolver.
- Existing create/status contracts не меняются.
- Claims получает только displayed H1 `report_id`; backlink остаётся plain INN.
- Legacy backend GET/scoring/signals/AI не удаляются, но page их не вызывает.
- Migration отсутствует.
- Rollback: revert одного frontend/docs commit; DB cleanup не нужен.

## 15. Acceptance

- [ ] Page facts поступают только из `/public-h1` через strict parser.
- [ ] Unknown keys/values и disabled gates fail closed.
- [ ] Legacy latest/AI read отсутствует в CompanyReport page.
- [ ] Canonical 404/terminal 409 не создают report.
- [ ] Plain exact 404 создаёт один report; pending polling abortable.
- [ ] Canonical path и Claims action используют displayed DTO.
- [ ] Overall complete/partial badge не выводится из coverage.
- [ ] Checked date/YoY/amount display сохраняются без locale/Number conversion.
- [ ] Years/counts/limit/offset use safe/lossless integer guards and negative tests.
- [ ] No-JS-number prohibition applies only to exact Decimal/display fields.
- [ ] All mirrored client invariants in § 5.6 pass.
- [ ] Moscow date and Decimal display remain backend-authoritative strings.
- [ ] Block order, coverage, sources, limitations и actions соблюдены.
- [ ] Replace-navigation consumes same parsed DTO without a second H1 read.
- [ ] Company SPA never promotes itself to indexable.
- [ ] Bootstrap and React share one exact head-owner marker.
- [ ] Exactly one owned robots node exists; cleanup leaves no stale noindex.
- [ ] Published SSR/API/SPA semantic parity проходит.
- [ ] Latest-unpublished API/SPA parity и noindex проходят.
- [ ] Contacts, score, verdict, signals и AI отсутствуют.
- [ ] Keyboard/a11y и no-overflow на 1440/768/390 подтверждены.
- [ ] Real-browser QA follows § 12.1 and leaves no repository/temp residue.
- [ ] Landing, public route и Claims regressions проходят.
- [ ] Lint, tests, build, Product API unit regression и diff check проходят.
- [ ] Independent code review возвращает `VERDICT: READY`.
- [ ] Backend, migration, dependency, deploy и production diff отсутствуют.

## 16. Blockers

Блокирующих продуктовых решений нет. Reserved optional blocks, status/legal
form dictionaries, internal links и finance money остаются intentionally
disabled backend gates и не активируются frontend-кодом.
