# Итерация 23 — Финансовые графики Company Card v2

ID: 23
Slug: company-card-v2-finance-charts
Base commit: fca4cc7
Статус: corrected specification after independent plan review

## 1. Цель

Реализовать пять утверждённых финансовых представлений Company Card v2:

- строить публичные F1–F5 на backend из immutable snapshot.finance_basis;
- показывать точные финансовые факты в SSR и React без обязательной загрузки chart bundle;
- добавить lazy-loaded SVG enhancement с mouse, keyboard и touch;
- сохранить immutable H2 pins и ранее рассчитанные projection digests;
- оставить production-default route выключенным.

Production activation, deploy и rollout не входят в итерацию.

## 2. Источники истины

Итерация следует контракту и ADR iteration 19, finance policy
datanewton_finance_thousand_rub_v2 и результатам iterations 20–22. Публичные
CompanyPublicH2Response, FinanceBasisV1, ChartFactsV1 и immutable presentation
pins остаются источниками истины. Отклонённая policy
datanewton_finance_thousand_rub_v1 не используется.

## 3. Scope

В scope входят:

1. Runtime-построение F1–F5 из snapshot.finance_basis.
2. Независимые anchors и windows каждого view.
3. Exact selection по (form, code, year).
4. Backend Decimal math, display strings и safe geometry.
5. Missing, gaps, provider zero, derived zero, conflicts, negative values и invalid denominator.
6. Версионированная v1/v2 publication lineage.
7. Atomic create/reuse unresolved v2 pin при finalization нового immutable v3 report.
8. SSR/JS-disabled factual tables и эквивалентное React-представление без factual refetch.
9. Lazy interactive SVG, a11y, local fallback и deterministic component tests.
10. Exact TypeScript F1–F5 contracts и structural factual parity.
11. Dynamic optional chunk в asset manifest.
12. Unit, integration, component, manifest/release и structural performance tests.
13. Feature gate, выключенный в production defaults.

## 4. Вне scope

Не входят:

- arbitration A1–A5 и iteration 24;
- full rollout/browser matrix и iteration 25;
- responsive screenshots, 200% zoom campaign и generated browser evidence;
- deploy, release execution и production activation;
- provider/filter changes, live DataNewton/FNS, production DB и paid AI;
- новые API fields, finance codes, units, thresholds, scores или verdicts;
- forecast, interpolation, risk colors, backfill или rewrite старых reports/pins;
- изменение Claims flow или версии company_public_h2_v1.

## 5. Finance admission gate

Публичное денежное значение допускается только при:

~~~text
unit_policy_version = datanewton_finance_thousand_rub_v2
cell.state = available_nonzero
~~~

Provider zero остаётся zero_unverified, не публикуется как numeric zero и
сохраняет limitation finance_zero_unverified. Derived zero разрешён только как
детерминированный результат операций над допущенными non-zero operands.

Tests обязаны различать missing, provider zero, conflict/invalid/lossy input и
valid derived zero. FinanceBasisV1, ChartFactsV1, их версии, hashes и immutable
snapshot schema не меняются.

## 6. Versioned publication lineage

Поддерживаются две policy:

~~~text
company_public_h2_publication_v1
company_public_h2_publication_v2
~~~

Policy v1 всегда воспроизводит прежнюю closed projection: F1–F5 равны null,
finance coverage равен gate_closed. Старые unresolved/resolved v1 pins не
переключаются на v2.

Policy v2 строит F1–F5 из immutable v3 snapshot и применяется только к report,
который успешно finalized через новый writer path.

В той же DB transaction, которая принимает fenced completion v3 job, сохраняет
immutable report/snapshot и существующий post-persist outbox result, production
path создаёт или переиспользует unresolved H2 pin:

1. Identity включает subject, report, snapshot hash, chart facts version/hash,
   evidence registry version, presentation contract, generation и policy.
2. Для нового report без lineage создаётся ровно один unresolved v2 pin.
3. Generation выделяется под существующей subject/H2 row lock.
4. Retry той же finalization переиспользует exact row и generation.
5. Existing v1/v2 lineage не получает другую policy.
6. Resolved/unresolved lineage проверяется целиком; mixed policy или conflicting
   identity даёт fail-closed.
7. Historical terminal report без pin не backfill-ится read-side или retry-side.
8. Report, outbox и pin либо commit-ятся вместе, либо не commit-ится ничего.

Текущих DB constraints, locking и String(64) достаточно; миграция не требуется.

Narrative finalization находит exact unresolved pin, наследует только сохранённую
policy, не использует default constant или digest heuristic и creates/reuses
resolved pin с той же policy. Missing/ambiguous lineage даёт fail-closed.

Resolver выбирает builder только по policy resolved pin, проверяет exact stored
projection_digest и не выполняет writes/backfill. Unknown policy или digest
mismatch дают fail-closed. Public contract остаётся company_public_h2_v1.

## 7. Default-off

Production defaults не меняются:

~~~text
COMPANY_CARD_V2_PRESENTATIONS_ENABLED=false
COMPANY_CARD_V2_WRITER_ENABLED=false
COMPANY_CARD_V2_ROLLOUT_GENERATION=0
~~~

## 8. Exact index, forms и limitations

Finance index использует только (form, code, year).

Required forms:

- balance: 1210, 1230, 1240, 1250, 1300, 1400, 1500, 1600;
- financial_results: 2100, 2110, 2200, 2400.

Одинаковый code/year из другой формы не замещает required cell, не участвует в
anchor/formula и покрывается collision tests.

Public limitations берутся только из сохранённых states/limitations missing,
zero_unverified, conflict, invalid, decimal_transport_lossy и из двух
утверждённых formula limitations: finance_denominator_non_positive и
receivables_collection_unassessed.

Итерация не синтезирует finance_failed и не выводит provider failure из missing.
Повторы codes сворачиваются детерминированно.

Coverage:

- complete non-null view → available;
- non-null view с gaps или invalid denominator → partial;
- null view без complete publishable operands → missing;
- references указывают только на реально сохранённые relevant limitations.

## 9. F1–F5

Глобальный finance anchor запрещён.

### F1 — ликвидные средства и ближайшие обязательства

Required balance cells: 1250, 1240, 1230, 1500. Anchor — максимальный полный
год. available_without_inventory = 1250 + 1240 + 1230; difference =
available_without_inventory - 1500. Сегменты имеют фиксированный порядок и
сохраняют знак. Axis содержит zero и каждый cumulative start/end endpoint.

### F2 — собственные средства и долги

Required balance cells: 1300, 1400, 1500. Anchor — максимальный полный год;
window — anchor-6..anchor. debt = 1400 + 1500; denominator = 1300 + debt.
При denominator > 0 shares вычисляются Decimal с scale 6 и ROUND_HALF_UP.
Non-negative shares используют stacked_100 и axis [0,100]; signed shares —
diverging_signed с zero и обоими endpoints. При denominator <= 0 source
components видимы, shares/axis/geometry null. Gap не превращается в zero.

### F3 — динамика выручки и активов

Required: financial_results:2110 и balance:1600. Anchor — максимальный общий
valid year; window — семь последовательных календарных лет.

Revenue и assets сохраняют независимые gaps и независимые axes.
revenue_summary.axis содержит zero и revenue points; assets_summary.axis —
zero и assets points. Geometry каждой серии проверяется только по её axis.
UI показывает две явно подписанные независимые шкалы/панели, без видимости
общей monetary scale. Линии не пересекают gaps.

Summary каждой серии использует первый/последний valid point. Multiple требует
два positive endpoints; signed change — два available endpoints; YoY требует
immediately previous calendar year и positive previous value.

_series_summary использует localcontext precision 34, ROUND_HALF_UP и scale 6.
Implicit process Decimal context запрещён.

### F4 — прибыль на 100 рублей выручки

Required financial_results cells: 2110, 2100, 2200, 2400. Anchor — максимальный
полный год. При positive 2110 ratios считаются Decimal относительно 100. Axis
содержит zero, 100 и все signed ratios; clamp запрещён. При non-positive
revenue source values видимы, ratios/axis/geometry null.

### F5 — финансовая таблица

Anchor — максимальный available non-conflicting год любой fixed row; window —
семь лет. Фиксированные строки: 2110 Продажи, 1600 Всё имущество, 1250 Деньги
на счетах, 1240 Финансовые вложения, 1230 Долги покупателей, 1210 Запасы,
1500 Ближайшие обязательства, 1300 Свои средства, 2400 Чистая прибыль.

Все строки остаются в DTO/UI; missing/provider-zero отображаются как em dash;
signed и valid derived zero сохраняются. YoY требует current и immediately
previous available value и positive previous value.

## 10. Display

Backend заполняет существующий PublicFinanceMoney без float. Compact money —
millions с одной цифрой, ROUND_HALF_UP: 273,3 млн ₽. Exact integral
source-thousand — три цифры: 273,325 млн ₽. Display использует comma и Unicode
minus; missing — em dash; derived zero exact — 0,000 млн ₽.

Для non-money decimals новые display fields не добавляются. UI не использует
Number/Intl/rounding и добавляет к canonical DTO string только literal suffix:

- share/YoY: space + percent;
- multiple: multiplication sign;
- F4 ratio: space + ₽ из 100 ₽.

## 11. Validators и factual parity

Python и TypeScript проверяют ordered axes, zero containment, endpoints внутри
соответствующей axis, fixed orders, arithmetic, seven-year windows, F2 modes,
F3 independent axes/gaps/summaries, F4 denominator equivalence, F5 rows/YoY и
coverage/limitation cross-rules. Number допустим только для final bounded SVG
coordinate после exact decimal validation.

Python SSR всегда выводит пять finance articles. Available/partial article
содержит heading, caption, semantic table/dl, headers, exact strings, gaps,
limitations и пустой stable enhancement host. Null article содержит factual
absence и preserved limitations, но не synthetic chart. React воспроизводит
ту же factual structure без GET.

Structural parity vector включает article order, table/dl kind, captions,
headers, cells, gaps, limitations и empty enhancement hosts. Facts остаются в
DOM после enhancement и при его ошибке.

## 12. Bootstrap, lazy enhancement и a11y

bootstrap.tsx выполняет parse, exact binding/digest validation, сравнение
DTO-derived и SSR factual vectors, React takeover, проверку React factual vector
и лишь затем arm lazy controller.

При parse/binding/parity mismatch import не вызывается, observer не создаётся
или disconnect-ится, generation token инвалидируется, SSR остаётся. Bootstrap
хранит React root handle; teardown disconnects observer, invalidates stale
import и unmounts root ровно один раз. Stale Promise не mount-ит chart.

Без IntersectionObserver eager import не выполняется, facts остаются и
показывается local enhancement status.

Charts — hand-authored React/SVG без dependency. Import разрешён только после
успешного bootstrap и приближения non-null finance section к viewport.
Mouse/focus/touch управляют одним disclosure; Escape, outside pointer и focus
exit закрывают его. Tooltip имеет role=tooltip и aria-describedby. Accessible
name включает metric, period, exact value и state. Tooltip ограничен local
container, а fact не существует только внутри tooltip. Reduced motion
отключает animation.

Import/render error сохраняет factual table, показывает видимый
role=status aria-live=polite, не запускает retry и не делает factual/provider/
AI/auth requests.

## 13. Asset manifest, fixtures и tests

Vite manifest generator обходит entry imports/dynamic imports, собирает
reachable JS/CSS, записывает dynamic assets в sorted optional_chunk_paths,
проверяет hashes/same-origin и reject-ит reachable non-JS/CSS asset. One-JS/
one-CSS assumption удаляется. Старый manifest совместим только с явным полем
optional_chunk_paths: [].

Sanitized fixtures:

- dense company_public_h2_contract_v1.json обновляется для F1–F5;
- company_public_h2_ssr_v1.json/html — finance-enabled v2 golden;
- company_public_h2_ssr_v1_closed.json/html — отдельный legacy v1 closed golden.

Legacy report fixtures не переписываются. Screenshots/evidence не создаются,
.gitignore не меняется.

Обязательны finance/contract/policy/SSR/component/a11y/bootstrap/manifest tests,
PostgreSQL atomic/idempotency tests и structural performance assertions.
Full responsive/zoom/screenshot rollout matrix остаётся iteration 25.

## 14. Migration, dependencies и acceptance

Alembic migration, snapshot rewrite/backfill, новая npm dependency, schema
version change и production flag change не требуются.

Итерация принята, если:

1. Runtime v2 строит F1–F5, а v1 воспроизводит closed projection.
2. Новый finalized v3 report atomic получает/reuses один unresolved v2 pin.
3. Retry/rollback/concurrency не создают duplicate или partial state.
4. Старые v1 lineage и digests сохраняются.
5. Narrative/GET используют только saved policy; GET не пишет.
6. Exact forms, independent anchors и independent F3 axes доказаны.
7. Provider zero не публикуется, missing не интерполируется, failed не синтезируется.
8. Decimal precision/display/geometry проходят Python и TypeScript validation.
9. SSR/React factual structure совпадает и остаётся при lazy failure.
10. Lazy import невозможен до parse/binding/parity success.
11. A11y contract и local live error status покрыты тестами.
12. Optional chunk и old optional_chunk_paths: [] совместимы.
13. Targeted/repository checks проходят.
14. Нет iteration 24/25 scope, migration, deploy, live/AI/prod operations.
15. Production defaults остаются выключенными.
