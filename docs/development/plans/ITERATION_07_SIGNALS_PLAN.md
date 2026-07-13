# Инженерная итерация 7 — signals: implementation plan

## 1. Канонический контракт и нумерация

Этот план реализует спецификацию
[`ITERATION_07_SIGNALS.md`](../iterations/ITERATION_07_SIGNALS.md). В случае
расхождения каноническим является единый контракт, зафиксированный в обоих
документах:

```python
evaluate_signals(
    report: CompanyReport,
) -> SignalEvaluationResult
```

Точные публичные типы результата:

- `SignalEvaluationResult.ruleset_version: Literal["1"]`;
- `SignalEvaluationResult.signals: list[Signal]`;
- `SignalEvaluationResult.warnings: list[SignalWarning]`.

`SignalSet`, `build_signal_set(...)` и возврат только `list[Signal]` superseded
и не используются.

Нумерация фиксирована:

```text
Итерация 7 — signals
Итерация 8 — scoring
```

Итерация 7 не содержит score, verdict, probability, recommendation или AI.

## 2. Инварианты до начала production-работ

- Единственный вход — `CompanyReport v1`; `CompanyReport`, его snapshot и hash
  не меняются. Signals не входят в snapshot.
- Provider, normalizers, persistence, ORM, migrations и API не меняются.
- Нет HTTP, БД, raw payload, новых endpoint, UI или зависимостей.
- Signal содержит `code`, `category`, `direction`, `strength`, `factual_basis`,
  `source: list[SourceMetadata]`, `period`, `confidence`,
  `warnings: list[SignalWarning]`; `source` созданного Signal непустой.
- `SignalFactualBasis` содержит `facts`, `eligibility`, `trigger`,
  `strength_decision`, `period_basis`, `years`, `case_ids`.
- `SignalWarning` содержит `code`, `rule_code: str | None`,
  `dataset: str | None`, `message`, обязательный
  `evaluation_basis: SignalEvaluationBasis`.
- `SignalEvaluationBasis` содержит `facts`, `eligibility`,
  `failed_eligibility`, `years`, `case_ids`; suppression из-за качества,
  неполноты, конфликта или отсутствующего периода всегда имеет непустой
  `failed_eligibility` и однозначное основание.
- `SignalFact` содержит `id`, `normalized_path`, `exact_value`; fact ID уникален
  внутри basis, `Decimal` не превращается во `float`, `None` не превращается в
  zero.
- Expression tree — закрытый discriminated union только из `predicate`,
  `all_of`, `any_of`, `not`.
- Period models — закрытый union `NoPeriod`, `DatePeriod`, `DateRangePeriod`,
  `YearPeriod`, `YearRangePeriod`.
- `Decimal` не превращается во `float`; missing не превращается в ноль.
- Повтор signal code и повтор fact id запрещены.
- Точные sort keys: signals — category order, `code`, canonical serialized
  representation всего Signal; facts — `id`, `normalized_path`, canonical
  serialized representation всего SignalFact; sources — `provider`, `dataset`,
  `received_at`, `endpoint`, `response_hash`, canonical serialized
  representation всего SourceMetadata; warnings — `code`, `rule_code or ""`,
  `dataset or ""`, canonical serialized representation всего SignalWarning;
  years — numeric ascending; case IDs — lexicographic ascending; expression
  children — canonical serialized representation всего ExpressionNode.
- Canonical serialized representation единообразно строится через
  `model_dump(mode="json")`, JSON object keys sorted, `separators=(",", ":")`,
  `ensure_ascii=False`, `allow_nan=False`; `Decimal` не преобразуется во
  `float`. Full-object tie-breaker гарантирует одинаковый JSON при перестановке
  sources/warnings с одинаковыми primary fields.

### Закрытые модели Stage 1

`SignalFact.exact_value` допускает только
`None | bool | int | str | Decimal | date | datetime`; дополнительные поля
запрещены. Любой `predicate` ссылается на существующий fact ID.

Operator contract закрыт и содержит минимум:

```text
LiteralOperand = {kind: "literal", value: ExactValue}
FactOperand = {kind: "fact", fact_id: str}
ComparisonOperand = LiteralOperand | FactOperand
```

- `presence`, `absence` без правого operand;
- `equality`, `inequality`, `greater_than`, `greater_or_equal`, `less_than`,
  `less_or_equal` с единственным `operand: ComparisonOperand`;
- `count` с integer fact, comparator и integer threshold;
- exact `decimal_comparison` с единственным Decimal
  `operand: ComparisonOperand`;
- exact `decimal_ratio` с fact IDs числителя/знаменателя, comparator и Decimal
  threshold; нулевой/отсутствующий знаменатель проваливает eligibility.

`all_of.children` и `any_of.children` непусты; `not` содержит ровно один
`child`; циклы, lambda, callable и скрытые guards запрещены. Children
`all_of`/`any_of` сортируются по canonical serialized representation. Все
eligibility gates, triggers, period inputs и strength overrides сериализуются.

Period contract полностью фиксирован:

- `NoPeriod`: `kind="no_period"`, `as_of: datetime`;
- `DatePeriod`: `kind="date"`, `value: date`;
- `DateRangePeriod`: `kind="date_range"`, `start: date`, `end: date`;
- `YearPeriod`: `kind="year"`, `year: int`;
- `YearRangePeriod`: `kind="year_range"`, `start_year: int`, `end_year: int`.

Обязательные поля не nullable, extras и другие kinds запрещены; validators:
`start <= end`, `start_year <= end_year`. `as_of` берётся только из
`SourceMetadata.received_at`. Arbitration не использует `no_period`.

Confidence contract: `high` означает чистое полное непротиворечивое основание;
`medium` — достаточное основание с неблокирующими normalization warnings; `low`
не создаёт `positive`, `negative` или `informational` Signal и вместо него даёт
result-level `signal_confidence_insufficient` с evaluation basis. Обычный false
trigger после выполненной eligibility warning не создаёт.

## 3. Evidence-gate для reporting absent

Единственный заблокированный код — `finance.reporting_absent`. Gate не
блокирует `negative_equity`, `revenue_decline`, `net_loss`, `cash_shortfall` или
`high_accounts_payable`.

До отдельного evidence approval запрещено реализовывать `reporting_absent` или
считать clean empty `FinanceFacts` доказанным no-reporting. Для approval нужны:

1. обезличенный реальный fixture либо официально документированная успешная
   форма ответа без отчётности;
2. сравнение с успешным response с отчётностью, malformed `200`, `not_found`,
   access denied и тарифным ограничением;
3. проверка всех успешных вариантов через текущий `normalize_finance()`;
4. доказательство, что `FinanceFacts` сохраняет различие без raw payload;
5. отдельное согласование fixture и normalizer-теста.

Если нормализованный контракт не сохраняет различие, требуется отдельное
разрешение на его изменение. Новые DataNewton-запросы не входят в этот план.

### Стабильные warning codes

Каждый warning всегда содержит `code`, безопасный `message` и
`evaluation_basis`; `rule_code` обязателен для suppression конкретного правила,
`dataset` — для dataset warning. Реализуется и тестируется следующий реестр:

- `dataset_unavailable` — нужный dataset отсутствует или не `AVAILABLE`;
- `required_fact_missing` — доступный dataset не содержит обязательный fact;
- `required_period_unavailable` — legal-status/finance period нельзя построить;
- `normalization_warning_present` — normalization warning: при достаточном
  основании он signal-level, `failed_eligibility` пуст и confidence `medium`; у
  правила, требующего clean normalization, он result-level и содержит failed
  clean-normalization gate;
- `status_conflict` — единственный конфликт ruleset v1
  `is_active == true AND dissolved_date is present` подавил затронутое правило;
- `finance_reporting_semantics_unconfirmed` — evidence-gate
  `finance.reporting_absent` не пройден;
- `finance_period_conflict` — затрагивающие правило financial periods одного
  года противоречат друг другу;
- `arbitration_incomplete` — `is_complete` не равно `true`, result-level warning
  для каждого подавленного arbitration rule;
- `arbitration_period_unavailable` — обязательный year отсутствует у влияющего
  дела;
- `arbitration_summary_conflict` — cases и summaries противоречат агрегату
  затронутого правила;
- `signal_confidence_insufficient` — trigger выполнен, но confidence был бы
  `low`, поэтому Signal не создан.

Для каждого suppression warning `evaluation_basis` содержит доступные facts,
полную eligibility, точные failed eligibility nodes, влияющие years и case IDs.

### Контракты правил для реализации

Для каждого правила модели и тесты отдельно фиксируют `eligibility`, `trigger`,
`strength_decision`, `period_basis` и suppression warning codes; общая таблица
не заменяет эти проверки.

- `counterparty.active`: eligibility — `AVAILABLE`, facts и `is_active`,
  `source.received_at`, отсутствие status conflict; trigger — `is_active=true`
  и отсутствие `dissolved_date`; strength `medium`; period basis — received_at,
  `no_period`; suppression — `dataset_unavailable`, `required_fact_missing`,
  `required_period_unavailable`, `status_conflict`,
  `signal_confidence_insufficient`.
- `counterparty.dissolved`: eligibility — `AVAILABLE`, пригоден хотя бы один из
  `is_active`/`dissolved_date`, status conflict отсутствует; trigger —
  `is_active=false` или дата присутствует; strength `critical`; period basis —
  дата для `date`, иначе received_at для `no_period`; suppression —
  `dataset_unavailable`, `required_fact_missing`, `required_period_unavailable`,
  `status_conflict`, `signal_confidence_insufficient`.
- `counterparty.long_operating_history`: eligibility — counterparty `AVAILABLE`,
  присутствуют `CounterpartyFacts`, нормализованный
  `CounterpartyFacts.years_from_registration`, `registration_date` и
  `source.received_at`, причём
  `registration_date <= source.received_at.date()`; trigger — нормализованный
  `years_from_registration >= 5`; strength `low`; period basis —
  `registration_date` и `source.received_at`; period —
  `DateRangePeriod(start=registration_date,
  end=source.received_at.date())`; Signal.source — непустой список
  `[CounterpartyFacts.source]`; factual basis содержит normalized
  `years_from_registration`, `registration_date`, `source.received_at`;
  suppression — `dataset_unavailable`, `required_fact_missing`,
  `required_period_unavailable`, `signal_confidence_insufficient`. Signals не
  вычисляет годы заново из дат и не использует текущее время.
- `counterparty.status_conflict`: eligibility — `AVAILABLE`,
  `CounterpartyFacts`, `is_active`, `dissolved_date`, `source.received_at`;
  единственный trigger ruleset v1 —
  `is_active == true AND dissolved_date is present`; strength `high`; period
  basis — received_at, `no_period`; suppression — `dataset_unavailable`,
  `required_fact_missing`, `required_period_unavailable`,
  `signal_confidence_insufficient`. Новые виды конфликтов требуют новой версии
  ruleset.
- `finance.reporting_absent`: eligibility — `AVAILABLE`, подтверждённая clean
  no-reporting semantics, отсутствие structural warnings, received_at; trigger —
  нет periods и reporting years; strength `medium`; period basis — только
  `FinanceFacts.source.received_at`, `no_period`; suppression —
  `dataset_unavailable`, `finance_reporting_semantics_unconfirmed`,
  `normalization_warning_present`, `required_period_unavailable`,
  `signal_confidence_insufficient`; реализация только в Stage 5 после approval.
- `finance.negative_equity`: eligibility — последний пригодный
  непротиворечивый year, exact equity и unit; trigger — equity `<0`; strength
  `high`; period basis — выбранный year; suppression — `dataset_unavailable`,
  `required_fact_missing`, `required_period_unavailable`,
  `finance_period_conflict`, `signal_confidence_insufficient`.
- `finance.revenue_decline`: eligibility — два последних пригодных
  непротиворечивых последовательных year, exact revenue и сопоставимые units;
  trigger — later revenue `<` previous revenue; strength `medium`; period basis
  — оба year, `year_range`; suppression — `dataset_unavailable`,
  `required_fact_missing`, `required_period_unavailable`,
  `finance_period_conflict`, `signal_confidence_insufficient`.
- `finance.net_loss`: eligibility — последний пригодный непротиворечивый year,
  exact net_profit и unit; trigger — net_profit `<0`; strength `medium`; period
  basis — выбранный year; suppression — `dataset_unavailable`,
  `required_fact_missing`, `required_period_unavailable`,
  `finance_period_conflict`, `signal_confidence_insufficient`.
- `finance.cash_shortfall`: eligibility — последний пригодный непротиворечивый
  year с exact `cash_and_equivalents`/`short_term_liabilities` в сопоставимых
  units; trigger — `cash_and_equivalents < short_term_liabilities`; strength
  default `medium`, ordered override `high` только при строгом
  `cash_and_equivalents < short_term_liabilities * Decimal("0.25")`; period basis
  — выбранный year; suppression — `dataset_unavailable`,
  `required_fact_missing`, `required_period_unavailable`,
  `finance_period_conflict`, `signal_confidence_insufficient`.

  Strength basis содержит исходные `cash_and_equivalents` и
  `short_term_liabilities`, коэффициент `Decimal("0.25")` как exact literal в
  `strength_decision` и derived SignalFact:

  ```text
  id: short_term_liabilities_25_percent
  normalized_path: derived.finance.short_term_liabilities_25_percent
  exact_value: short_term_liabilities * Decimal("0.25")
  ```

  Override сравнивает `cash_and_equivalents` с derived fact через exact
  `decimal_comparison`. Деление, `decimal_ratio` и специальная семантика нулевого
  знаменателя для `finance.cash_shortfall` запрещены.
- `finance.high_accounts_payable`: eligibility — последний пригодный
  непротиворечивый year с exact accounts_payable/current_assets и units; trigger
  — accounts_payable `>` current_assets; strength `high`; period basis — year;
  suppression — `dataset_unavailable`, `required_fact_missing`,
  `required_period_unavailable`, `finance_period_conflict`,
  `signal_confidence_insufficient`.

Все arbitration rules требуют `AVAILABLE`, `ArbitrationFacts` и
`is_complete=true`; иначе применяются `dataset_unavailable`,
`required_fact_missing` или `arbitration_incomplete`. Конфликт cases/summaries
подавляет только затронутое правило с `arbitration_summary_conflict`.

- `arbitration.high_respondent_case_count`: eligibility — `AVAILABLE`,
  `ArbitrationFacts`, `is_complete=true`, year у каждого дела полного dataset и
  согласованный агрегат; trigger — respondent count `>=10`; strength `high`;
  period basis — все years/case IDs, один year даёт `year`, несколько
  `year_range`; suppression — `dataset_unavailable`, `required_fact_missing`,
  `arbitration_incomplete`, `arbitration_period_unavailable`,
  `arbitration_summary_conflict`, `signal_confidence_insufficient`.
- `arbitration.respondent_case_growth`: eligibility — `AVAILABLE`,
  `ArbitrationFacts`, `is_complete=true`, year у каждого respondent case,
  способного влиять на годовой агрегат, два последних года последовательны,
  агрегат согласован; trigger — later `>` previous и delta `>=3`; strength
  `medium`; period basis — выбранные years и влияющие case IDs, `year_range`;
  suppression — `dataset_unavailable`, `required_fact_missing`,
  `arbitration_incomplete`, `arbitration_period_unavailable`,
  `arbitration_summary_conflict`, `signal_confidence_insufficient`.
- `arbitration.open_cases`: eligibility — `AVAILABLE`, `ArbitrationFacts`,
  `is_complete=true`, только открытые дела, year у каждого открытого дела,
  агрегат согласован; открытое дело без year подавляет правило; trigger — open
  count `>=1`; strength `medium`; period basis — только years и case IDs открытых
  дел, закрытые дела period не расширяют, один year даёт `year`, несколько
  `year_range`; suppression — `dataset_unavailable`, `required_fact_missing`,
  `arbitration_incomplete`, `arbitration_period_unavailable`,
  `arbitration_summary_conflict`, `signal_confidence_insufficient`.
- `arbitration.frequent_plaintiff`: eligibility — `AVAILABLE`,
  `ArbitrationFacts`, `is_complete=true`, year у каждого дела полного dataset и
  согласованный агрегат; trigger — plaintiff count `>=10` и `>` respondent count;
  strength `medium`; period basis — все years/case IDs, один year даёт `year`,
  несколько `year_range`; suppression — `dataset_unavailable`,
  `required_fact_missing`, `arbitration_incomplete`,
  `arbitration_period_unavailable`, `arbitration_summary_conflict`,
  `signal_confidence_insufficient`.

## 4. Последовательность реализации

### Stage 1 — models, expression tree, periods, legal-status signals

Результат: модели `Signal`, `SignalFactualBasis`, `SignalEvaluationResult`,
строго сериализуемое expression tree, все period models и legal-status rules:
`active`, `dissolved`, `long_operating_history`, `status_conflict`.

Работа включает unique code/fact-id validation, stable sorting, exact Decimal,
no raw payload, conflict suppression и source-based `as_of`. Тесты покрывают
AND/OR/NOT, все contract fields, period variants legal status, 5-летний порог,
warnings/confidence, дубли и permutation determinism.

Проверки:

```text
python -m pytest services/product_api/tests_unit/test_company_report_signal_models.py services/product_api/tests_unit/test_company_report_counterparty_signals.py -q
python -m pytest services/product_api/tests_unit -q
python -m compileall -q services/product_api/src/product_api/company_reports
git diff --check
```

### Stage 2 — arbitration signals

Результат: `high_respondent_case_count`, `respondent_case_growth`, `open_cases`
и `frequent_plaintiff` с обязательными completeness и period gates.

Тесты покрывают пороги 10 и 3, последовательные years, open cases, роли,
`is_complete=false`, result-level `arbitration_incomplete`, case IDs,
cases/summary conflicts, missing year suppression и перестановку cases/warnings.
Неполный dataset не даёт aggregate signal; отсутствие обязательного года не
подменяется `no_period`.

Проверки:

```text
python -m pytest services/product_api/tests_unit/test_company_report_signal_models.py services/product_api/tests_unit/test_company_report_arbitration_signals.py -q
python -m pytest services/product_api/tests_unit -q
git diff --check
```

### Stage 3 — financial signals, кроме reporting_absent

Результат: `negative_equity`, `revenue_decline`, `net_loss`, `cash_shortfall`,
`high_accounts_payable`. `finance.reporting_absent` намеренно отсутствует.

Тесты покрывают строгие границы, latest eligible year по каждому правилу,
consecutive revenue years, zero/missing values, conflicting duplicate year,
неизвестные units, derived threshold cash shortfall, строгий exact
`decimal_comparison` и ordered strength override, точность Decimal и permutation
determinism. Недоступность, malformed,
`not_found`, access/tariff failure дают warnings, а не reporting absence.

Проверки:

```text
python -m pytest services/product_api/tests_unit/test_company_report_finance_signals.py -q
python -m pytest services/product_api/tests_unit -q
git diff --check
```

### Stage 4 — evaluate_signals, ordering, result-level warnings, compatibility

Результат: единственный публичный `evaluate_signals(report)` композирует
legal-status, financial и arbitration signals, валидирует unique codes и
возвращает `SignalEvaluationResult` в contract order.

Тесты покрывают complete, partial и failed `CompanyReport`; warnings при
`signals=[]`; category/code order; permutation-identical JSON; отсутствие score,
verdict, probability и AI; отсутствие raw payload; неизменность snapshot/hash и
чтение старых snapshots. Тесты и exports используют только новый public API.

Проверки:

```text
python -m pytest services/product_api/tests_unit/test_company_report_signal_evaluation.py services/product_api/tests_unit/test_company_report_persistence_serialization.py services/product_api/tests_unit/test_company_report_orchestrator_success.py -q
python -m pytest services/product_api/tests_unit -q
python -m compileall -q services/product_api/src/product_api/company_reports
git diff --check
```

### Stage 5 — reporting_absent после отдельного evidence approval

Stage начинается только после approval из раздела 3. Результат:
`finance.reporting_absent` с complete eligibility basis, clean no-reporting
semantics, `no_period`, `as_of=FinanceFacts.source.received_at` и без
фиктивного reporting year.

Тесты подтверждают distinction между approved no-reporting, normal reporting,
malformed, `not_found`, disabled и access/tariff failures; `available_count` не
используется. Перестановка warnings не меняет period или JSON.

Проверки:

```text
python -m pytest services/product_api/tests_unit/test_company_report_finance_normalizer.py services/product_api/tests_unit/test_company_report_finance_signals.py -q
python -m pytest services/product_api/tests_unit -q
git diff --check
```

## 5. Definition of done и review

Итерация готова, когда выполнены Stage 1–4, Stage 5 либо имеет отдельный
evidence approval и выполнен, либо явно остаётся не реализованным без задержки
остальных financial signals. Пороги v1 (5 лет, 10 дел, рост 3, 25%) не меняются
молча. `is_active=false` остаётся достаточным условием dissolved;
`frequent_plaintiff=positive` не означает успешное взыскание.

После применимых stages проводится независимое review по
`CODE_REVIEW_CHECKLIST.md`: scope, deterministic ordering, missing/partial
semantics, privacy, serialization, compatibility и отсутствие незапланированных
persistence/API изменений. Commit и push требуют отдельной команды.
