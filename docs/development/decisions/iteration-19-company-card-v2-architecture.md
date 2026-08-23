# ADR: архитектура Company Card v2 / public H2

Статус: принято как implementation-ready контракт для итераций 20–25

Дата: 2026-08-23

Область: H1/H2 presentation boundary, v3 writer и lifecycle, immutable publication, арбитражный basis, durable AI, dedicated SSR shell

Активация: запрещена до итерации 25 и отдельного явного решения владельца

## Контекст

Company Card v2 нельзя безопасно добавить как несовместимое расширение текущего
H1-контракта. H1 продолжает обслуживать существующих клиентов и публикации
версий 1/2, а новый H2-контур должен уметь читать legacy snapshots в
ограниченном noindex-режиме и публиковать полный v3 без подмены версий.

Это решение фиксирует будущую реализацию. Оно не открывает закрытые evidence
gates, не активирует cohort, не выполняет backfill и не разрешает provider,
Gateway, AI или DB работу на публичном GET.

## Решение

### 1. Разделение H1, H2 и v3

| Поверхность | Контракт |
|---|---|
| H1 JSON | Существующий `company_public_h1_v1` и существующий public-H1 route остаются без изменений |
| H2 JSON | Новый read-only `GET /company-reports/{inn}/public-h2`, контракт `company_public_h2_v1` |
| H1 snapshots | Только `report_version IN ('1','2')`; v3 никогда не возвращается как v2 |
| H2 legacy preview | Версии 1/2 разрешены только как `legacy_read_only`, noindex, с явными limitations |
| H2 full card | Только `report_version="3"` и `snapshot_capability="card_v2"` |
| Канонический документ | Product API выбирает H1 или dedicated H2 SSR shell по assignment и точному immutable pin |

H1 остаётся production default как минимум до завершения итерации 24. У H1 и
H2 отдельные DTO, snapshot/Chart Facts, unit, AI и publication versions.
Существующие H1 pin, действия, frontend и запрет hidden JSON не меняются.
Ни клиентский body/query/header, ни cookie не выбирают report version, writer
profile или presentation contract.

Публичный H2 GET/HEAD анонимен, без query, только читает уже подготовленную
sanitized projection. Он не вызывает provider/Gateway/AI, не создаёт job,
reservation, report или pin и не пишет в БД. Ответы JSON получают `no-store`,
`nosniff` и `noindex,follow`.

### 2. Закрытый H2 DTO

Все objects рекурсивно запрещают дополнительные ключи. Все строки проходят
Unicode NFC до проверки; пустая/whitespace-only строка недопустима, если поле
явно не nullable. Неизвестное поле, enum, cardinality, path или Decimal shape
даёт целиком `contract_mismatch`: частично разобранные факты не показываются.

#### 2.1. Общие scalar- и byte-границы

| Тип | Ограничение |
|---|---|
| Schema/member identifier | ASCII `[a-z][a-z0-9_]{0,63}` |
| Contract/version/code | 1–64 ASCII |
| Human label | 1–256 Unicode scalar values |
| Safe display name | 1–512 Unicode scalar values |
| Address | 1–1024 Unicode scalar values |
| Limitation | 1–512 Unicode scalar values |
| Narrative description | 400–700 Unicode scalar values после нормализации |
| Narrative chart comment | 1–280 Unicode scalar values |
| Case number | 1–128 Unicode scalar values |
| Same-origin path / approved URL | 1–2048 ASCII |
| Date / timestamp | `YYYY-MM-DD` / RFC 3339 с seconds и точным `Z` |
| UUID / SHA-256 | lowercase canonical UUID / 64 lowercase hex |
| Integer | JSON integer без float, exponent или coercion |
| Decimal | Каноническая строка профиля `company_public_h2_cjson_v1` |
| Canonical DTO | не более 524288 UTF-8 bytes, включая `projection_digest` |
| Script-safe DTO | не более 786432 UTF-8 bytes |
| Embedded state | ровно один script element |

Равенство byte-limit допустимо; превышение на один byte даёт
`public_projection_too_large`. Projection не обрезается.

#### 2.2. Leaf-level traceability

| Тип | Обязательные leaves и cardinality |
|---|---|
| `CompanyPublicH2Response` | literal `contract_version="company_public_h2_v1"`; `projection_digest` SHA-256; `report_id` UUID; `report_version` enum `"1"|"2"|"3"`; `snapshot_capability` enum `legacy_read_only|card_v2`; `projection_scope` enum `active_publication|staged_publication|latest_unpublished`; `canonical_path`; `indexable` boolean; `checked_at`; `checked_date`; `checked_date_display`; `identity`; `narrative`; `block_order` exactly 16; `blocks`; `coverage` exactly 13; `sources` 1..3; `limitations` 0..128; `actions` exactly 2; `breadcrumbs` exactly 2; `primary_claim_cta` |
| `PublicH2Identity` | `display_name`, `legal_full_name`; nullable `short_name`; `inn` exact 10- or 12-digit ASCII company identifier; nullable exact 13/15-digit ASCII `ogrn`, exact 9-digit ASCII `kpp`, registration/dissolution dates and `status` |
| `PublicH2Status` | `state` active/inactive/other; `code`; `label`; nullable `effective_date` |
| `PublicH2Requisites` | nullable `legal_form`, `address`, `charter_capital`, `employees`, `tax_authority`; `tax_modes` 0..8; `primary_activity` nullable; `additional_activities` 0..20; `managers` 0..20; `owners` 0..50 |
| `PublicLabeledCode` | `code`, `label` |
| `PublicH2Address` | `display`; nullable `region` and `is_inaccuracy` |
| `PublicTaxMode` | closed `mode_id`; `label`; literal `applies=true`; nullable `effective_date` |
| `PublicActivity` | 2..16 digit/dot `code`; `label`; `is_primary`; nullable `effective_date` |
| `PublicManager` | safe `name`; approved `role`; nullable `appointed_at` and `is_inaccuracy` |
| `PublicOwner` | safe `display_name`; `owner_type` person/organization/state; nullable `share_percent_decimal`, `share_display`, `effective_date` |
| `PublicEmployees` | `count` integer 0..999999999; `period`; nullable `effective_date` |
| `PublicH2Narrative` | `mode` artifact/fallback; `renderer_version`; description 400–700; unique `statement_ids` 1..16; `comments` 0..2; `render_digest` |
| `PublicH2ChartComment` | one F1..F5/A1..A5 `chart_id`; `text`; unique `evidence_ids` 1..8 |
| `PublicH2CoverageItem` | `block_id` is `requisites`, `narrative`, `finance_f1..finance_f5`, `arbitration_a1..arbitration_a5` or `sources_limitations`; closed `state`; `population_scope` is not-applicable/complete-collection/returned-slice; nullable `total`, `returned`, `eligible`; unique `limitation_codes` 0..16 |
| `PublicH2SourceItem` | `dataset` counterparty/finance/arbitration; `received_at`; nullable `effective_at` and `period`; `normalization_version`; `evidence_version` |
| `PublicH2Limitation` | unique `code`; nullable `block_id` and `field_id`; `message` |
| `PublicH2Action` | `action_id` is exactly `check_another_company` or `prepare_claim`; exact fixed `label`; same-origin `path` |
| `PublicH2Breadcrumb` | `label`; same-origin `path`; `current` |
| `PublicH2ClaimCta` | literal `action_id="prepare_claim"`; exact fixed heading, desktop copy and button label; exact Claims path bound to root report |
| `PublicFinanceMoney` | exact `source_thousand_decimal`, `rub_decimal`, `million_decimal`; backend `display_exact` and `display_compact`; literal `unit_id="RUB"`; literal `unit_policy_version="datanewton_finance_thousand_rub_v1"` |
| `PublicCaseAmount` | exact `source_decimal`; `source_currency_id`; backend `display_exact` |
| `PublicChartAxis` | `axis_min_decimal`, `axis_max_decimal` |
| `PublicChartInterval` | `start_ratio_decimal`, `end_ratio_decimal` |
| `PublicChartPoint` | `ratio_decimal` |
| `PublicDetailScope` | `population_scope`; nullable `source_total`; `rows_received`; `eligible_total`; `shown` 0..20; literal `cap=20`; exact backend `label` |
| `PublicF1` | literal view ID; `year`; four source money values; derived `available_without_inventory` and `difference`; common `axis`; exactly 4 ordered interval segments |
| `PublicFinanceSegment` | closed `metric_id`; `value`; `geometry` |
| `PublicF2` | literal view ID; `anchor_year`; `window_start_year=anchor-6`; exactly 7 consecutive ascending `periods` |
| `PublicF2Period` | `year`; `state` available/gap/denominator-unavailable; nullable equity/long/short/debt/denominator money and shares; `mode`; nullable common axis; keyed interval map exactly `equity_1300`, `debt` |
| `PublicF3` | literal view ID; anchor/window; exactly 7 ascending `points`; independent `revenue_summary` and `assets_summary`, each with its own comparison years, multiple/change and axis |
| `PublicF3Point` | `year`; nullable revenue/assets money, YoY Decimals and keyed point map exactly `revenue_2110`, `assets_1600` |
| `PublicF4` | literal view ID; `year`; four money inputs; literal-or-null revenue per 100; nullable three other ratios; `mode`; nullable axis and keyed interval map exactly `revenue_2110`, `gross_2100`, `operating_2200`, `net_2400` |
| `PublicF5` | literal view ID; anchor; exactly 7 consecutive `years`; exactly 9 fixed-order `rows` |
| `PublicF5Row` | fixed `metric_id` and `label`; exactly 7 `cells` |
| `PublicF5Cell` | `year`; nullable `value` and `yoy_decimal` |
| `PublicArbitrationSummary` | nullable `source_total`; `rows_observed`; `unique_case_count`; `malformed_count`; `duplicate_identical_count`; `duplicate_conflict_count`; `collection_complete`; closed `completion_reason`; separate `calendar_complete`; `calendar_scope` only `unverified|all_time|bounded_interval`; nullable calendar evidence version/bounds; observed bounds; `unknown_year_count`; `zero_years_proven` |
| `PublicSafeCaseDetail` | opaque `case_public_id`; nullable `case_number`, `year`, `result_detail`, `amount`, `start_date`, `update_date`, `days_to_last_update`, `instance_count`, `public_case_url`; closed `role` and `outcome`; `courts` 0..10; `opponents` 0..20 |
| `PublicSafeOpponent` | opaque `opponent_public_id`; safe `display_name`; `display_kind` legal/state/masked-natural/masked-unknown |
| `PublicA1` | literal view ID; `summary`; nullable displayed year bounds; `buckets` 0..11; `all_time_case_count` |
| `PublicA1YearBucket` | nullable `year`; four role counts plus total; exactly 4 ordered `role_details` |
| `PublicA1 window` | unknown-year bucket is optional and separate; with no verified-year case bounds are null/no ordinary bucket; otherwise use bounded calendar interval only with zero proof, else observed bounds, cap deterministic display to the most recent 10 years, and permit synthetic zero only within the chosen proven interval |
| `PublicRoleDetail` | closed `role`; `scope`; `cases` 0..20 |
| `PublicA2` | literal view ID; `summary`; `denominator`; exactly 4 ordered role `bars` |
| `PublicCountBar` | role/outcome `category_id`; `count`; nullable `percent_decimal`; `scope`; `cases` 0..20 |
| `PublicA3` | literal view ID; `summary`; `denominator`; exactly 4 ordered outcome bars |
| `PublicA4` | literal view ID; `summary`; `currency_groups` 0..16; missing-amount and missing-currency counts |
| `PublicA4CurrencyGroup` | `source_currency_id`; `display_currency`; shared `axis: PublicChartAxis`; ordered `case_geometries: PublicA4CaseGeometry[0..20]`; scope and cases |
| `PublicA4CaseGeometry` | exact `case_public_id` matching one listed case; `geometry: PublicChartInterval`; geometry order/cardinality matches cases |
| `PublicA5` | literal view ID; `summary`; root `scope`; `groups` 0..20; no-safe-opponent and multi-opponent counts |
| `PublicA5OpponentGroup` | opaque opponent ID; safe name/kind; `case_count>=1`; nested `case_scope`; `cases` 0..20 |
| `PublicH2Blocks` | always-present `requisites`; nullable `finance_f1..f5` and `arbitration_a1..a5` |

Exact `block_order` is:

1. `hero_status`
2. `narrative`
3. `in_page_navigation`
4. `requisites`
5. `finance_f1_liquidity`
6. `finance_f2_funding`
7. `finance_f3_growth`
8. `finance_f4_profit_per_100`
9. `finance_f5_yearly_table`
10. `arbitration_a1_activity`
11. `arbitration_a2_roles`
12. `arbitration_a3_outcomes`
13. `arbitration_a4_case_amounts`
14. `arbitration_a5_opponents`
15. `sources_limitations`
16. `neutral_actions`

Coverage states are exactly `available`, `available_empty`, `partial`,
`missing`, `not_requested`, `failed`, `conflict`, `gate_closed` and
`legacy_unavailable`. Overall complete/partial не вычисляется клиентом из
coverage. Null chart требует non-available coverage; `available` требует
non-null chart. `available_empty` допустим только для доказанной пустой
арбитражной population, не для synthetic zero.

Root invariants: v3 iff card-v2 capability; v1/v2 iff legacy-read-only и
`indexable=false`; indexable возможен только у active publication;
`checked_date` — Moscow date stored `checked_at`; все non-available blocks
ссылаются на существующие limitations; identity/path/breadcrumb/action
bindings совпадают; массивы имеют contract order.

CTA literals неизменяемы: heading `Вам задолжали?`, desktop copy
`Запустите процесс взыскания прямо сейчас: создайте досудебную претензию онлайн!`,
button `Создать претензию`, path
`/claims?report_id={root.report_id}`. Source order —
counterparty/finance/arbitration; actions — check-another, затем prepare-claim;
breadcrumbs — root, затем current canonical company. Limitations сортируются
по block-order index, nullable field ID и code.

F1 arithmetic выполняется exact Decimal. F2 shares существуют только при
положительном denominator и в сумме дают canonical 100. F3 geometry не
соединяет gap; comparison years парны. F4 ratios существуют только при
положительной revenue. F5 years/cells совпадают. Signed geometry включает
zero. Detail `shown=min(eligible_total,20)`. A1 counts сходятся; A2/A3 counts
сходятся с denominator, а percentages отсутствуют только при zero denominator;
A4 не смешивает currency; A5 явно допускает один case в нескольких groups.

### 3. Canonical digest и embedded bytes

Профиль `company_public_h2_cjson_v1` является language-neutral:

1. Сначала DTO полностью реконструируется и валидируется.
2. Keys и string values приводятся к NFC; collision после NFC и unpaired
   surrogate отклоняются.
3. Разрешены object/array/string/boolean/null/integer; dates, UUID, hashes и
   Decimals остаются validated strings; float запрещён.
4. Object keys сортируются по Unicode scalar sequence; array order сохраняется.
5. Integer grammar — `0|[1-9][0-9]*`; H2 v1 не имеет signed integer leaves.
6. Decimal grammar —
   `-?(0|[1-9][0-9]*)(\.[0-9]*[1-9])?`; zero только `"0"`.
7. JSON escapes quote, backslash и controls; slash не escape; separators
   `,`/`:` без whitespace; нет BOM или trailing newline.

Digest вычисляется так: member `projection_digest` удаляется целиком,
оставшийся DTO canonicalizes, SHA-256 кодируется lowercase hex, затем digest
вставляется. Canonical bytes без digest — единственный hash input.

Script-safe bytes — отдельное, не re-hashed представление полного DTO. Помимо
canonical escaping оно escape-ит `<`, `>`, `&`, U+2028 и U+2029. Клиент
парсит embedded DTO, заново строит canonical bytes без digest и сверяет hash.
Python/TypeScript используют общие positive/negative golden vectors.

### 4. Server-owned writer profile и lifecycle

#### 4.0 Normative lifecycle correction

This subsection supersedes every earlier contrary lifecycle sentence in this
ADR. Legacy `POST /company-reports` is permanently H1/v2 and
cohort-independent: it never reads, snapshots or branches on H2 rollout
configuration. The H2-only `POST /company-report-presentations` is the sole
presentation-create surface. If its H2 cohort is closed or disabled it returns
`404 company_public_h2_disabled` and creates no H1 work; an incompatible active
pending H1/v2 or H2/v3 job returns `409 report_writer_profile_conflict`.

H1 reads resolve an active H1 pin first and otherwise the latest eligible
finalized v1/v2 report. Only when the subject exists and neither source exists
may H1 read/status return `409 report_not_eligible`; an H2 assignment or v3 row
does not change this. H2 presentation status is only the immutable stored
presentation ID binding and never re-resolves cohort or latest state.

Server заранее строит endpoint-specific immutable decision. Legacy H1 has the
constant `h1_legacy_writer_v2` / `company_public_h1_v1` / report version `"2"`
and no rollout generation. H2 has `rollout_config_generation`, normalized
identifier, literal `company_public_h2_v1`, Company Card writer v3 and report
version `"3"`. V3 writer is server-default-off and available only to the
allowlist/test cohort before owner activation.

Порядок create неизменяем:

1. normalize и validate identifier;
2. snapshot rollout generation only for H2; use the constant H1 decision for
   legacy POST, always before provider work;
3. начать transaction и lock exact subject;
4. найти максимум один active pending job;
5. reuse только при полном совпадении profile/report version/presentation
   contract; stored rollout generation остаётся исходной и не мутируется;
6. при несовпадении вернуть `409 report_writer_profile_conflict`;
7. сохранить decision в pending/job до provider call.

Ограничение one-active-job-per-subject сохраняется. Не создаются параллельные
v2/v3 pending jobs. Flag flip не меняет и не переиспользует mixed-profile job:
старый job продолжает свой профиль, новый create получает conflict. Finalized
v2 может породить v3 только через явный presentation create; finalized v3 не
затмевает H1 v1/v2.

Claim/lease/orchestration/finalization несут и сравнивают `job_id`,
`writer_profile`, `report_version`, `presentation_contract`,
`rollout_config_generation`, `lease_token` и `fence_generation`. Finalization
дополнительно сравнивает report ID, subject, lifecycle и snapshot hash.
Mismatch не публикует данные, пишет безопасный
`writer_profile_fence_mismatch` и сохраняет durable recoverability.

Legacy lifecycle остаётся H1-only. `POST /company-reports` always creates or
reuses H1/v2 unless an incompatible pending H2 job owns the subject slot.
Status/latest/public-H1 filter finalized version 1/2 and lifecycle
complete/partial; pending must have the H1 writer. Reads resolve the active H1
pin and otherwise latest eligible v1/v2. Only an existing subject with neither
source can return terminal `409 report_not_eligible`; H2 assignment alone is
never the cause.

Новый lifecycle:

- `POST /company-report-presentations` принимает только identifier, без query
  и version/profile headers;
- `GET /company-report-presentations/{presentation_id}/status` reads only the
  immutable stored presentation ID binding;
- response содержит contract, report ID, pending/complete/partial/failed,
  exact public read path, nullable canonical document path и reused flag.

## Cross-contract implementation invariants

The primary Iteration-19 contract sections 6, 28 and 29 govern the H1/H2
lifecycle. The legacy
`POST /company-reports` is permanently H1/v2. The successor POST returns a
server-generated opaque UUID `presentation_id`; only
`GET /company-report-presentations/{presentation_id}/status` reads it. The ID
is immutably bound to one subject/report/contract and never chooses latest.
Cohort precedence for the H2-only endpoint is exact: disabled selects no H2 and
returns `404 company_public_h2_disabled` without H1 work; normalized allowlist
selects H2; otherwise the specified SHA-256 modulo-10000 basis-point test
decides. The accepted H2 decision is persisted before provider work. Legacy H1
POST does not consult this configuration.

Pins are append-only and contract-discriminated, binding report version,
snapshot hash, projection digest, `chart_facts_version`, `chart_facts_hash`,
evidence/policy versions and artifact-or-fallback identity. Staging is noindex
and separate from active selection. Active switch and rollback are subject-lock
CAS operations over the expected assignment generation; zero affected rows are
`presentation_assignment_conflict`. H1 `lastmod` stays bound only to its
selected immutable H1 pin.

The pin union is explicit: `H1PresentationPin` is v1/v2 and contains only the
existing H1 report/hash/policy/canonical/indexable/lastmod binding; all H2
projection/chart/evidence/narrative members are absent. `H2PresentationPin` is
v3 and contains the full H2 binding. Each has its own uniqueness predicate.
The staged H2 composite pointer is separate from the active discriminated
assignment reference, so an H1 active pin never needs impossible H2 fields.

`PublicCharterCapital` is separate from finance money and has its own unit
gate. The literal tax-mode enum, list identity/sort/cap/conflict behavior and
finite Decimal math profile (precision 34, scale 6, `ROUND_HALF_UP`, residual
allocation and null handling including F5 YoY) are fixed in sections 26.5–26.8
and 27 and
are backend facts, not browser calculations.

V3 Decimal input is separately gated for finance, arbitration amount and
charter-capital amount by `finance_decimal_transport`,
`arbitration_decimal_transport` and `charter_capital_decimal_transport`:
`response.json()` post-coercion does not prove preservation of a source number
lexeme. Until source-byte lexical ingestion or a valid JSON string meets
`company_card_source_decimal_v1` and its negative/precision tests pass, the
gates are each `UNVERIFIED / BLOCKED`; finance monetary Chart Facts/geometry,
A4 amount display/geometry and charter capital do not activate even if a unit
matrix later passes.

The same scale-6 residual allocation applies to A2/A3 positive-denominator
percentages in their fixed category order. F3 has explicit multiple, signed
change and immediately-preceding-calendar YoY formulas/null rules. All capped
arrays deduplicate and sort before first-cap emission; overflow retains the
first cap and emits the exact `*_truncated` limitation plus partial metadata.

The arbitration registry binds endpoint/filter/version before a request;
collection and calendar completeness are independent. Primary sections 13–16
and 31 fix
private-ID normalization/priority/conflicts, UTF-8 named-object HMAC framing,
public IDs, and court/opponent overflow/order. Provider IDs and HMAC tokens
remain private.

The exact privacy primitives are the closed `OpponentHmacIdentityV1`,
`StableOpponentIdentifierV1` and `CasePositionIdentifierV1` CJSON schemas in
the privacy ADR; its full 32-byte lowercase-hex HMAC, scanner-safe digest
golden, public ordering identities, six-digit `case_`/`opponent_` patterns and
`1..1000`/`1..20000` bounds are part of this architecture. Generic identifier
tuples and provider-order or unversioned public identities are forbidden.

One normalized INN and OGRN may coexist: INN wins. Conflict exists only among
distinct normalized values of the same kind or invalid party association; the
case-local fallback is used only with no stable kind.

AI generation, artifact and fallback identities use named CJSON objects with
literal identity versions. The fallback catalog has exactly one immutable
691-scalar golden; invalid binding fails before publication without prose
generation, padding, repair or a second AI call. The v1 catalog is frozen to
its single literal `fallback_profile_any_v1`; any future replacement requires
a new catalog version and owner decision, never a v1 mutation.
Migration is nullable columns
→ dual reader → legacy drain → deterministic H1 backfill with historical
generation 0 → constraints; a null row is legacy H1 only until constrained.

Read predicates:

| Resolver | Exact selection |
|---|---|
| H1 public/SSR | Active H1 pin, иначе latest finalized v1/v2 |
| Legacy latest/status | H1 writer и только v1/v2 |
| Presentation status | Exact stored report ID + contract |
| H2 active | Assignment → exact H2 pin generation → exact v3 report |
| H2 staged | Exact stored staged H2 pointer only; missing/corrupt pointer is ineligible |
| H2 legacy preview | Latest v1/v2 только при отсутствии v3, всегда noindex |

Latest lookup, где он разрешён, детерминирован
`generated_at DESC, id DESC` и всегда включает subject equality.

`public-h2` HTTP matrix: valid GET/HEAD → 200; any query или invalid identifier
→ 422; disabled/no report → 404; pending/failed/not eligible → 409; corrupt
pin/hash/DTO/digest → 500; unsupported method/Accept → 405/406; rate limit →
429 без partial body. Conditional selection, 304 и version response/request
overrides не поддерживаются.

### 5. Immutable pins, assignment и publication

`H1PresentationPin` and `H2PresentationPin` are the only pin shapes. H1 is
v1/v2 with the existing H1 report/hash/policy/canonical/indexable/lastmod
binding and no H2-only fields. H2 is v3 with exact projection digest, Chart
Facts version/hash, evidence/policy and narrative binding. Their per-shape
uniqueness predicates are in primary sections 7 and 30 of the specification.

The active assignment is the discriminated immutable composite pin reference;
the staged H2 pointer is a separate exact H2 composite reference. Neither is
a generic leaf bag and a missing/corrupt staged pointer never falls back to
latest or participates in active resolution.

Activation/rollback — один CAS transaction:

1. lock assignment;
2. проверить caller-supplied expected assignment generation;
3. join candidate pin, exact report, subject и narrative binding;
4. revalidate hashes, policy, canonical path и indexability;
5. append safe assignment journal;
6. update reference/generation и commit.

CAS mismatch → `409 presentation_assignment_conflict`. Resolver, sitemap и SSR
используют один shared join
`assignment → pin generation → report → narrative binding`. Missing/corrupt
member fails closed; слой не выбирает latest самостоятельно. H1 и H2 pins
сосуществуют. Corrupt active H2 pin не fallback-ит на H1/latest. Rollback тем
же CAS указывает на прежний immutable H1 pin, не меняя snapshot, artifact или
report.

Staged H2 pin всегда noindex. Eligibility policy
`company_public_h2_publication_v1` требует exact finalized v3 complete/partial,
identity equality, valid snapshot/Chart Facts/digest, immutable narrative
binding, privacy version, canonical uniqueness и coherent coverage/limitations.
Indexable дополнительно требует lifecycle complete, все фактически
использованные gates verified, отсутствие failed/conflict/gate-closed/
legacy-unavailable, available identity, десять безопасных view states,
bounded disclosed arbitration partial без conflict/malformed/privacy failure,
valid narrative и owner-approved assignment. Missing отличается от proved
empty. Scoring/AI quality opinion не являются eligibility inputs.

Ни один H2 assignment не создаётся до итерации 25 и отдельного owner approval.

### 6. Arbitration basis, pagination и attribution

Авторитетные provider total и visible-case-number leaves остаются
`NOT_VERIFIED`, пока tracked evidence не свяжет exact path/type/scope/shape.
Перед первым call registry обязан связать total, data, offset, limit и shape
fields: `arbitration_total_path`, `arbitration_total_type`, `total_scope`,
`data_path`, `offset_path`, `limit_path` и `shape_version`. Stale/missing
binding закрывает gate до сети. Visible case number имеет отдельный
`arbitration_visible_case_number` gate; internal dedup key не показывается.
Отсутствующее safe display значение — `Номер не указан`.

Bounded collection:

- `page_size=100`, `max_pages=10`;
- raw-row cap — 1000, причём учитываются malformed, duplicate, conflict и
  oversized rows до normalization; элемент 1001 не нормализуется;
- canonical `ArbitrationBasisV1` — максимум 8 MiB (8388608 bytes);
- один sanitized case — максимум 262144 bytes;
- public detail cap — 20.

На каждом page фиксируются safe manifest/provenance, offset/limit, accepted
count и stable total evidence; raw pages не сохраняются. Drift, non-progress,
provider error и исчерпание bounds дают partial, не false-complete.

Per-row порядок: count → cap → minimum shape → exact normalization →
privacy transform → sanitized case → canonical bytes → dedup → tentative basis
→ admit только внутри byte cap. После первого oversized/storage stop более
поздние строки/pages не рассматриваются, чтобы size не влиял на выбор.
Basis содержит shape version, source total, page manifest, counters, sorted
sanitized cases, mask algorithm version и key ID. Derived Chart Facts находятся
вне basis cap, но внутри public DTO cap.

Dedup equality — полные canonical sanitized bytes, включая dates, exact
amount/currency, attribution evidence, safe parties, courts/link и
null-vs-zero. Identical duplicate схлопывается. Same key с различными bytes
удаляет ранее admitted case, навсегда блокирует key и создаёт
duplicate-conflict limitation.

Exact counters: `pages_requested`, `pages_accepted`, `rows_observed`,
`rows_shape_valid`, `malformed_count`, `oversized_case_count`,
`duplicate_identical_count`, `duplicate_conflict_row_count`,
`duplicate_conflict_key_count`, `unique_case_count`,
`masked_natural_count` и `masked_unknown_count`. Каждый processed row получает
одну primary disposition; удаление conflict candidate учитывается отдельно.

`completion_reasons` — nonempty unique list с fixed precedence:
`privacy_key_unavailable`, `envelope_gate_closed`, `envelope_invalid`,
`provider_error`, `total_drift`, `offset_drift`, `duplicate_conflict`,
`oversized_case`, `storage_cap_exhausted`, `case_cap_exhausted`,
`max_pages_exhausted`, `non_progress`, `complete`. Singular
`completion_reason` — первый элемент. `complete` может быть единственной
причиной и требует stable total, всех rows, отсутствия ранней причины и unknown
calendar evidence is not a collection-completeness condition. Persisted
`ArbitrationCollectionV1`, `ArbitrationCalendarFactsV1` and the public summary
keep separate `calendar_complete`, calendar scope limited to
`unverified|all_time|bounded_interval`, calendar evidence version,
calendar/observed bounds, `unknown_year_count` and `zero_years_proven`; collection completion alone
never creates a synthetic zero. Client показывает exact returned/total и
`показано N из M` конкретного detail scope; partial никогда не становится
«дел нет».

Target role определяется только exact target identifier match по каждой source
role collection: только plaintiff → plaintiff, только respondent → respondent,
любое другое непустое множество → other, пустое → unattributed. Party position
— normalized collection ID + zero-based ordinal. Ни имя, ни порядок display
не меняют attribution.

Amount остаётся exact Decimal в source currency: нет FX, debt terminology или
подмены missing нулём; zero и negative сохраняются. Dates дают только calendar
days to last update; inversion/missing → null с limitation, никогда
«длительность разбирательства». Legal/state alias допускается только при
verified same identifier и выбирается latest update, затем start, затем
lexicographic safe name, затем case key. Natural/unknown alias по имени
запрещён.

### 7. Durable AI и deterministic fallback

AI работает только на worker/write path. До выбора модели создаётся unique
durable reservation по SHA-256 от report/snapshot/Chart Facts hashes и
evidence/catalog/template/prompt/schema/policy/renderer/Gateway profile
versions. Resolved model намеренно отсутствует в generation key.

State machine:

`reserved → leased → dispatching → dispatched → validating → rendered →
finalized`; terminal alternatives: `pre_dispatch_failed`,
`ambiguous_timeout`, `invalid_output`, `fallback_finalized`.

Durable row хранит generation key, state, lease token/expiry, fence generation,
local attempt count, dispatch-start time, unique nullable Gateway dispatch ID,
resolved model, response time, validation codes и artifact ID. Все transitions
сравнивают lease token + fence.

Definitive local pre-dispatch failure можно retry только из закрытого
allowlist, пока dispatch/model fields null и attempt count меньше 3.
Непосредственно перед платным call worker атомарно фиксирует
`dispatch_started_at` и `dispatching`. После этого timeout, death или ambiguous
response не retry-ятся и завершаются fallback. Invalid output также сразу
выбирает fallback без repair/second AI call.

Final artifact identity hash включает generation key, resolved model,
validated render-plan bytes и rendered bytes. Он unique; на generation key
приходится одна finalized artifact/fallback binding. Pin связывает именно
final identity.

AI envelope содержит только allowlisted evidence IDs, нейтральные categories,
coverage и approved business labels. Exact values добавляет локальный
renderer. Automatic schema/evidence/unit/privacy/policy validation обязательна;
нет human moderation, admin approval или второго AI.

`company_card_h2_fallback_catalog_v1` is frozen to exactly one universal
literal, `fallback_profile_any_v1`, rendered by
`company_card_h2_fallback_renderer_v1`. Its only golden is the normalized
691-scalar text and named-object fallback identity. It has no coverage
combinations, variants or compiler selection. A replacement needs a new
catalog version and explicit owner decision; AI unavailability does not affect
page availability.

### 8. SSR shell, assets и rollback

Product API авторитетен для `/company/{company_key}`. Один resolver проверяет
plain/canonical key, читает assignment + exact pin, отдаёт H1 либо dedicated
H2 SSR shell, а при invalid projection — lifecycle/not-found/noindex response
без factual app. Wrong slug redirect строится только из выбранного pin. Nginx,
cookie и frontend flag ничего не выводят из URL/report version. GET никогда не
создаёт report.

H2 shell отделён от `services/web_ui/index.html` и не включает Yandex/Webvisor.
Manifest `company_public_h2_asset_manifest_v1` содержит schema version,
content-hashed same-origin JS/CSS, sorted optional chunks, SHA-256 integrity
каждого asset, `company_public_h2_v1` и
`company_public_h2_cjson_v1`. Product API pin-ит одну exact manifest version.

Shell содержит только эти assets и один strict embedded H2 DTO. SSR DOM и DTO
строятся из одной in-memory projection. Клиент читает её один раз, проверяет
schema/report/path/digest и не refetch-ит facts. При parse/schema/path/digest
failure SSR facts остаются, H1/H2 app не mount-ятся и не выполняется factual,
lifecycle, provider, AI или telemetry call; допустим только fixed local notice.

H2 CSP использует per-response nonce, deny-by-default sources, same-origin
scripts/styles/assets, без `unsafe-inline` и third-party analytics. Обязательны
`nosniff`, `no-referrer` и закрытый Permissions-Policy.

Deploy order: content-addressed assets → hash/reachability check → Product API
с exact manifest → nonactive smoke → assignment только в iteration 25.
Хранятся current и previous two manifest generations. Rollback: CAS assignment
на immutable H1 pin → Claims/canonical continuity check → при необходимости
Product API rollback; H2 assets и v3 snapshots сохраняются. Nginx SPA fallback
не заменяет выбранный H2 document.

### 9. Зависимости и verification ownership

| Итерация | Обязательная реализация/проверка |
|---|---|
| 20 | DTO/API/error/query/header matrix; v1/v2/v3 compatibility; writer fences; exact SQL; v3 persistence/digest; pins/CAS/eligibility; arbitration bounds/privacy/date/alias |
| 21 | Durable reservation/lease/fence; one paid dispatch; ambiguous no-retry; artifact identity; exhaustive deterministic fallback |
| 22 | Python/TypeScript digest vectors; dedicated shell/manifest/CSP/XSS; one DTO/no refetch; Product API/nginx/deploy rollback |
| 23 | F1–F5 missing/zero/conflict/signed/denominator/precision; backend display and geometry-only client; accessible interactions |
| 24 | A1–A5 partial/calendar/cap/detail; role/outcome/currency/privacy/link/telemetry; accessible interactions |
| 25 | Cross-layer SSR/API/client parity; responsive/zoom/input/a11y; real network no-read-work proof; canary/CAS activation/H1 rollback; owner approval |

Iteration 25 не заменяет пропущенные проверки 20–24.

## Отклонённые варианты

- расширить H1 несовместимыми optional leaves;
- выдавать v3 под видом v2 или выбирать глобальный latest;
- разрешить клиенту version/profile/experiment choice;
- переиспользовать один mutable H1 publication row для H2;
- provider/AI/backfill на GET;
- embed raw snapshot или второй state object;
- вычислять source semantics, money или report date в browser;
- считать один arbitration page полным;
- retry ambiguous paid dispatch;
- human/second-AI validation;
- менять snapshot/artifact при rollback.

## Неоднозначности и закрытые gates

Эта ADR намеренно не угадывает:

- DataNewton finance unit: `datanewton_finance_thousand_rub_v1` остаётся
  `UNVERIFIED / BLOCKED` до field-level evidence matrix; агрегатные совпадения
  недостаточны;
- authoritative arbitration total path/type/scope и visible case-number path:
  `NOT_VERIFIED`;
- status/effective date, legal-form catalog, charter-capital unit, tax modes,
  activity leaves, owners/workers/tax authority, outcome scope, entity type,
  currency и KAD host/path: только после своих evidence gates;
- rollout cohort, assignment и indexability: только server config, downstream
  tests и отдельное owner approval в iteration 25.

Закрытый gate означает hidden/limitation/fail-closed, а не inferred value,
zero, negative fact или optimistic conclusion.
