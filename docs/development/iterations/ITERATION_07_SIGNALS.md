# Инженерная итерация 7 — signals

## 1. Назначение и границы

Итерация 7 формирует из нормализованного `CompanyReport` проверяемые фактические
сигналы о юридическом статусе, финансовых фактах и арбитражной активности
компании. Сигнал — отдельное наблюдение с воспроизводимым основанием; он не
является оценкой компании в целом.

Нумерация инженерных итераций фиксирована:

```text
Итерация 7 — signals
Итерация 8 — scoring
```

Итерация 7 не включает scoring, агрегацию направлений, verdict, probability,
recommendation, текстовые выводы для пользователя или AI. Все они относятся к
отдельной инженерной итерации 8 либо к последующим решениям.

Единственный вход — `CompanyReport v1` и его нормализованные
`CounterpartyFacts`, `FinanceFacts` и `ArbitrationFacts`. Signals не выполняют
HTTP- или БД-операции, не используют `raw_payload`, не запрашивают provider и
не заменяют отсутствующие значения нулём или отрицательным фактом.

## 2. Единственный публичный контракт

```python
evaluate_signals(
    report: CompanyReport,
) -> SignalEvaluationResult
```

`SignalEvaluationResult` — единственный публичный envelope результата с точными
публичными типами:

- `SignalEvaluationResult.ruleset_version: Literal["1"]`;
- `SignalEvaluationResult.signals: list[Signal]`;
- `SignalEvaluationResult.warnings: list[SignalWarning]` — warnings уровня всего
  результата.

`signals` содержит только сработавшие сигналы. Suppression, недоступный dataset
и неполные данные могут давать result-level warnings даже при пустом `signals`.
Все публичные warnings безопасны для сериализации и не содержат raw payload.

`SignalSet`, `build_signal_set(...)` и публичный контракт с возвратом только
`list[Signal]` объявлены superseded. Они не должны появляться в новых
production-контрактах, примерах, тестах или exports.

## 3. Модели результата

### Signal

Каждый `Signal` содержит ровно следующие контрактные поля:

- `code` — стабильный машинный код правила;
- `category` — `legal_status`, `financial` или `arbitration`;
- `direction` — `positive`, `negative` или `informational`; это не общий
  вердикт;
- `strength` — сила правила (`low`, `medium`, `high`, `critical`);
- `factual_basis: SignalFactualBasis`;
- `source: list[SourceMetadata]` — непустой список использованных
  нормализованных источников;
- `period` — один из моделей периода раздела 5;
- `confidence` — доказательная полнота сигнала;
- `warnings: list[SignalWarning]` — стабильный список относящихся к сигналу
  безопасных warnings.

Для каждого созданного Signal `source` содержит минимум один
`SourceMetadata`; пустой список запрещён валидатором.

`strength` описывает правило, а `confidence` — достаточность его фактического
основания. Значения фактов, включая `Decimal`, сохраняют точность: `Decimal` не
преобразуется во `float`.

Confidence имеет однозначную политику:

- `high` — чистое, полное и непротиворечивое основание без normalization
  warnings;
- `medium` — достаточное и непротиворечивое основание с неблокирующими
  normalization warnings;
- `low` не создаёт `positive`, `negative` или `informational` Signal. Вместо
  Signal создаётся result-level warning с code
  `signal_confidence_insufficient` и полным evaluation basis подавления.

Обычный false trigger после успешно выполненной eligibility не создаёт ни
Signal, ни warning.

### SignalWarning и SignalEvaluationBasis

`SignalWarning` — строгая модель со следующими полями:

- `code: str` — стабильный code из реестра раздела 6;
- `rule_code: str | None` — code затронутого правила; обязателен для подавления
  конкретного правила, `None` допустим только для warning всего dataset/result;
- `dataset: str | None` — `counterparty`, `finance` или `arbitration`, если
  warning относится к dataset;
- `message: str` — безопасное детерминированное сообщение без raw payload и
  чувствительных значений;
- `evaluation_basis: SignalEvaluationBasis` — обязательное воспроизводимое
  основание warning.

`SignalEvaluationBasis` содержит ровно:

- `facts: list[SignalFact]` — доступные факты, использованные при проверке;
- `eligibility: ExpressionNode` — полное условие допуска правила;
- `failed_eligibility: list[ExpressionNode]` — точные неуспешные узлы из
  `eligibility`; для suppression список непустой, для неблокирующего warning у
  созданного Signal он пуст;
- `years: list[int]` — годы, влияющие на решение;
- `case_ids: list[str]` — идентификаторы дел, влияющие на решение.

При suppression из-за качества, неполноты, конфликта или отсутствующего
периода `evaluation_basis` обязателен и однозначно показывает нарушенный gate:
нельзя ограничиваться только message или warning code.

### SignalFact

`SignalFact` содержит ровно:

- `id: str` — стабильный идентификатор, уникальный внутри конкретного
  `SignalFactualBasis` или `SignalEvaluationBasis`;
- `normalized_path: str` — точный путь к нормализованному полю или явно
  вычисленному детерминированному агрегату;
- `exact_value: None | bool | int | str | Decimal | date | datetime` — точное
  типизированное значение.

Структурные extras запрещены. `Decimal` сериализуется без преобразования во
`float`; `None` сохраняется как `None` и не преобразуется в zero. Повтор одного
`id` запрещён даже при совпадающем значении.

### SignalFactualBasis

`SignalFactualBasis` — строгая воспроизводимая модель, а не свободный JSON. Она
содержит ровно:

- `facts` — типизированные использованные факты с уникальными `fact id`;
- `eligibility` — expression tree, доказывающее возможность применять правило;
- `trigger` — expression tree с условием срабатывания;
- `strength_decision` — default strength и упорядоченные overrides `when → strength`;
- `period_basis` — факты и операция, из которых построен `period`;
- `years` — использованные годы;
- `case_ids` — использованные идентификаторы дел.

Причина подавления правила фиксируется безопасным warning и обязательным
воспроизводимым `SignalEvaluationBasis`; фиктивный Signal не создаётся.
Конфликты фактов не разрешаются порядком входа.

### Expression tree

И `eligibility`, и `trigger`, и условия strength override используют закрытый
discriminated union `ExpressionNode`, выбранный только по полю `kind`:

- `PredicateExpression`: `kind="predicate"`, обязательный `fact_id` и один из
  закрытых operator-вариантов ниже;
- `AllOfExpression`: `kind="all_of"`, непустой `children: list[ExpressionNode]`;
- `AnyOfExpression`: `kind="any_of"`, непустой `children: list[ExpressionNode]`;
- `NotExpression`: `kind="not"`, ровно один `child: ExpressionNode`.

Predicate всегда ссылается на существующий `SignalFact.id`. Закрытый набор
операторов и их поля:

```text
LiteralOperand = {kind: "literal", value: ExactValue}
FactOperand = {kind: "fact", fact_id: str}
ComparisonOperand = LiteralOperand | FactOperand
```

- `presence` и `absence`: `fact_id`, без правого операнда;
- `equality`, `inequality`, `greater_than`, `greater_or_equal`, `less_than`,
  `less_or_equal`: `fact_id` и ровно одно поле
  `operand: ComparisonOperand`;
- `count`: `fact_id` точного целочисленного count, `comparator` из шести
  операторов сравнения и `value: int`;
- `decimal_comparison`: `fact_id`, `comparator` и ровно одно
  `operand: ComparisonOperand`; literal и разрешённый fact обязаны содержать
  `Decimal`, оба операнда сравниваются точно;
- `decimal_ratio`: `fact_id` числителя, `denominator_fact_id`, `comparator` и
  `value: Decimal`; деление и сравнение выполняются в `Decimal`, а отсутствие
  или нулевой знаменатель проваливает соответствующий eligibility gate.

Другие kinds, operators и дополнительные поля запрещены. Пустые `all_of` и
`any_of` запрещены; `not` не может иметь ноль или несколько children. Циклы
запрещены. `children` в `all_of` и `any_of` сортируются по canonical serialized
representation. Lambda, callable и скрытые guards запрещены: все gates,
predicates, period inputs и strength overrides представлены в basis.

## 4. Набор правил v1

| Code | Условие | Category / direction / strength |
| --- | --- | --- |
| `counterparty.active` | `is_active=true`, `dissolved_date` отсутствует | `legal_status` / `positive` / `medium` |
| `counterparty.dissolved` | `is_active=false` или известна `dissolved_date`, но не одновременно `is_active=true` | `legal_status` / `negative` / `critical` |
| `counterparty.long_operating_history` | `years_from_registration >= 5` и известна дата регистрации | `legal_status` / `positive` / `low` |
| `counterparty.status_conflict` | `is_active == true AND dissolved_date is present` | `legal_status` / `informational` / `high` |
| `finance.reporting_absent` | только доказанный clean no-reporting response, без финансовых periods и reporting years | `financial` / `informational` / `medium` |
| `finance.negative_equity` | пригодный последний год с `equity < 0` | `financial` / `negative` / `high` |
| `finance.revenue_decline` | в двух последних последовательных пригодных годах поздняя `revenue` строго меньше ранней | `financial` / `negative` / `medium` |
| `finance.net_loss` | пригодный последний год с `net_profit < 0` | `financial` / `negative` / `medium` |
| `finance.cash_shortfall` | `cash_and_equivalents < short_term_liabilities`; override `high`, если `cash_and_equivalents < short_term_liabilities * Decimal("0.25")` | `financial` / `negative` / `medium` |
| `finance.high_accounts_payable` | `accounts_payable > current_assets` в пригодном году | `financial` / `negative` / `high` |
| `arbitration.high_respondent_case_count` | полный dataset и не менее 10 дел ответчика | `arbitration` / `negative` / `high` |
| `arbitration.respondent_case_growth` | полный dataset; два последних последовательных года, рост строго положительный и не менее 3 | `arbitration` / `negative` / `medium` |
| `arbitration.open_cases` | полный dataset и не менее одного открытого дела | `arbitration` / `negative` / `medium` |
| `arbitration.frequent_plaintiff` | полный dataset; истец не менее чем в 10 делах и чаще, чем ответчик | `arbitration` / `positive` / `medium` |

Для финансовых правил выбирается последний пригодный год конкретного правила;
отсутствие, ноль или неизвестная единица измерения не становятся отрицательным
значением. Годы сравнения должны быть последовательными. Неизвестные единицы
исключают абсолютные денежные пороги и межединичные сравнения.

`frequent_plaintiff` не означает успешного взыскания. Неполный arbitration
dataset не создаёт ни одного арбитражного aggregate signal. Несогласованность
cases и summaries подавляет затронутое правило с warning.

### Явный контракт каждого правила

Ни одно из следующих условий не остаётся неявным guard. Для каждого правила
`eligibility`, `trigger`, `strength_decision`, `period_basis` и suppression codes
входят в сериализуемый basis.

#### Legal status

- `counterparty.active`: eligibility — dataset `counterparty` имеет `AVAILABLE`,
  присутствуют `CounterpartyFacts`, `is_active` и `source.received_at`, status
  conflict отсутствует; trigger — `is_active=true` и `dissolved_date` отсутствует;
  strength_decision — фиксированный `medium`; period_basis —
  `source.received_at`, period `no_period`; suppression — `dataset_unavailable`,
  `required_fact_missing`, `required_period_unavailable`, `status_conflict`,
  `signal_confidence_insufficient`.
- `counterparty.dissolved`: eligibility — `AVAILABLE`, `CounterpartyFacts`, хотя
  бы один из `is_active`/`dissolved_date` пригоден, status conflict отсутствует;
  trigger — `is_active=false` или `dissolved_date` присутствует;
  strength_decision — фиксированный `critical`; period_basis —
  `dissolved_date` для `date`, иначе `source.received_at` для `no_period`;
  suppression — `dataset_unavailable`, `required_fact_missing`,
  `required_period_unavailable`, `status_conflict`,
  `signal_confidence_insufficient`.
- `counterparty.long_operating_history`: eligibility — dataset `counterparty`
  имеет `AVAILABLE`, присутствуют `CounterpartyFacts`, нормализованный
  `CounterpartyFacts.years_from_registration`, `registration_date` и
  `source.received_at`, причём
  `registration_date <= source.received_at.date()`; trigger — нормализованный
  `years_from_registration >= 5`; strength_decision — фиксированный `low`;
  period_basis — `registration_date` и `source.received_at`; period —
  `DateRangePeriod(start=registration_date,
  end=source.received_at.date())`; Signal.source — непустой список
  `[CounterpartyFacts.source]`; factual basis содержит normalized
  `years_from_registration`, `registration_date` и `source.received_at`;
  suppression — `dataset_unavailable`, `required_fact_missing`,
  `required_period_unavailable`, `signal_confidence_insufficient`. Signals не
  вычисляет количество лет повторно из дат и не использует текущее время.
- `counterparty.status_conflict`: eligibility — `AVAILABLE`, имеются
  `CounterpartyFacts`, `is_active`, `dissolved_date` и `source.received_at`;
  единственный trigger ruleset v1 —
  `is_active == true AND dissolved_date is present`; strength_decision —
  фиксированный `high`; period_basis — `source.received_at`, period `no_period`;
  suppression — `dataset_unavailable`, `required_fact_missing`,
  `required_period_unavailable`, `signal_confidence_insufficient`. Сам
  сработавший informational Signal не получает warning `status_conflict`; этот
  warning относится к подавленным им правилам. Новые виды status conflict
  добавляются только новой версией ruleset.

#### Finance

`normalize_finance()` сохраняет в `FinanceFacts.indicators` все структурно
различающиеся варианты одного `form/code`; полностью идентичные варианты
дедуплицируются с объединением отсортированных `source_paths`. Значение поля
`FinancialPeriod` строится по consensus distinct non-null exact `Decimal`:
`None` вместе с одним exact value не конфликтует, несколько разных non-null
values дают ambiguous period field `None`. Metadata-only conflict сохраняет
warning и снижает confidence до `medium`, но не является value conflict.
Evaluator воспроизводит `finance_period_conflict` из indicator variants и не
использует `required_fact_missing` для доказанного value conflict; basis
содержит form, code, normalized field, year и все конфликтующие exact values.

- `finance.reporting_absent`: eligibility — `AVAILABLE`, `FinanceFacts`,
  отдельно подтверждённая clean no-reporting semantics, отсутствие structural
  normalization warnings, `source.received_at` доступен; trigger — отсутствуют
  financial periods и reporting years; strength_decision — фиксированный
  `medium`; period_basis — только `FinanceFacts.source.received_at`, period
  `no_period`; suppression — `dataset_unavailable`,
  `finance_reporting_semantics_unconfirmed`, `normalization_warning_present`,
  `required_period_unavailable`, `signal_confidence_insufficient`. До evidence
  approval правило не реализуется.
- `finance.negative_equity`: eligibility — `AVAILABLE`, выбран последний
  пригодный непротиворечивый год с exact `equity` и сопоставимой unit; trigger —
  `equity < 0`; strength_decision — фиксированный `high`; period_basis — год
  выбранного period, period `year`; suppression — `dataset_unavailable`,
  `required_fact_missing`, `required_period_unavailable`,
  `finance_period_conflict`, `signal_confidence_insufficient`.
- `finance.revenue_decline`: eligibility — `AVAILABLE`, выбраны два последних
  пригодных непротиворечивых последовательных года с exact `revenue` и
  сопоставимыми units; trigger — revenue позднего года строго меньше раннего;
  strength_decision — фиксированный `medium`; period_basis — оба года, period
  `year_range`; suppression — `dataset_unavailable`, `required_fact_missing`,
  `required_period_unavailable`, `finance_period_conflict`,
  `signal_confidence_insufficient`.
- `finance.net_loss`: eligibility — `AVAILABLE`, выбран последний пригодный
  непротиворечивый год с exact `net_profit` и сопоставимой unit; trigger —
  `net_profit < 0`; strength_decision — фиксированный `medium`; period_basis —
  выбранный год, period `year`; suppression — `dataset_unavailable`,
  `required_fact_missing`, `required_period_unavailable`,
  `finance_period_conflict`, `signal_confidence_insufficient`.
- `finance.cash_shortfall`: eligibility — `AVAILABLE`, выбран последний
  пригодный непротиворечивый год с exact `cash_and_equivalents` и
  `short_term_liabilities` в сопоставимых units; trigger —
  `cash_and_equivalents < short_term_liabilities`; strength_decision — default
  `medium`, ordered override `high` только при строгом
  `cash_and_equivalents < short_term_liabilities * Decimal("0.25")`;
  period_basis — выбранный год, period `year`;
  suppression — `dataset_unavailable`, `required_fact_missing`,
  `required_period_unavailable`, `finance_period_conflict`,
  `signal_confidence_insufficient`.

  Сериализуемый strength basis содержит исходные SignalFact для
  `cash_and_equivalents` и `short_term_liabilities`, коэффициент
  `Decimal("0.25")` как exact literal в `strength_decision` и детерминированный
  derived SignalFact:

  ```text
  id: short_term_liabilities_25_percent
  normalized_path: derived.finance.short_term_liabilities_25_percent
  exact_value: short_term_liabilities * Decimal("0.25")
  ```

  Strength override использует exact `decimal_comparison` между
  `cash_and_equivalents` и `short_term_liabilities_25_percent`. Деление,
  `decimal_ratio` и специальная семантика нулевого знаменателя в этом правиле
  запрещены.
- `finance.high_accounts_payable`: eligibility — `AVAILABLE`, выбран последний
  пригодный непротиворечивый год с exact `accounts_payable` и `current_assets` в
  сопоставимых units; trigger — `accounts_payable > current_assets`;
  strength_decision — фиксированный `high`; period_basis — выбранный год, period
  `year`; suppression — `dataset_unavailable`, `required_fact_missing`,
  `required_period_unavailable`, `finance_period_conflict`,
  `signal_confidence_insufficient`.

Неблокирующий normalization warning для любого из пяти реализуемых financial
rules не подавляет достаточное основание: Signal получает
`normalization_warning_present` и confidence `medium`. Structural warning,
объясняющий отсутствие обязательного факта, подавляет правило соответствующим
suppression code и basis.

#### Arbitration

Все четыре arbitration rules требуют dataset status `AVAILABLE`, наличие
`ArbitrationFacts` и `is_complete=true`. При `is_complete=false` правило
подавляется с `arbitration_incomplete`. Конфликт cases и summaries подавляет
только затронутое правило с `arbitration_summary_conflict`.

- `arbitration.high_respondent_case_count`: eligibility — dataset имеет
  `AVAILABLE`, присутствуют `ArbitrationFacts`, `is_complete=true`, year известен
  у каждого дела полного dataset и cases/summaries согласованы;
  trigger — exact respondent count `>=10`; strength_decision — фиксированный
  `high`; period_basis — years и case IDs всего полного dataset; один год даёт
  `year`, несколько — `year_range`; suppression — `dataset_unavailable`,
  `required_fact_missing`, `arbitration_incomplete`,
  `arbitration_period_unavailable`, `arbitration_summary_conflict`,
  `signal_confidence_insufficient`.
- `arbitration.respondent_case_growth`: eligibility — dataset имеет `AVAILABLE`,
  присутствуют `ArbitrationFacts`, `is_complete=true`, year известен у каждого
  respondent case, способного влиять на годовой агрегат, выбраны два последних
  последовательных года и агрегат согласован; trigger — later count
  строго больше previous count и exact delta `>=3`; strength_decision —
  фиксированный `medium`; period_basis — два выбранных года и влияющие respondent
  case IDs, period `year_range`; suppression — `dataset_unavailable`,
  `required_fact_missing`, `arbitration_incomplete`,
  `arbitration_period_unavailable`, `arbitration_summary_conflict`,
  `signal_confidence_insufficient`.
- `arbitration.open_cases`: eligibility — dataset имеет `AVAILABLE`, присутствуют
  `ArbitrationFacts`, `is_complete=true`, берутся только открытые дела, year
  известен у каждого открытого дела и агрегат согласован; открытое
  дело без year подавляет правило; trigger — open case count `>=1`;
  strength_decision — фиксированный `medium`; period_basis — years и case IDs
  только открытых дел, закрытые дела period не расширяют; один год даёт `year`,
  несколько — `year_range`; suppression — `dataset_unavailable`,
  `required_fact_missing`, `arbitration_incomplete`,
  `arbitration_period_unavailable`, `arbitration_summary_conflict`,
  `signal_confidence_insufficient`.
- `arbitration.frequent_plaintiff`: eligibility — dataset имеет `AVAILABLE`,
  присутствуют `ArbitrationFacts`, `is_complete=true`, year известен у каждого
  дела полного dataset и cases/summaries согласованы; trigger — exact
  plaintiff count `>=10` и строго больше respondent count; strength_decision —
  фиксированный `medium`; period_basis — years и case IDs всего полного dataset;
  один год даёт `year`, несколько — `year_range`; suppression —
  `dataset_unavailable`, `required_fact_missing`, `arbitration_incomplete`,
  `arbitration_period_unavailable`, `arbitration_summary_conflict`,
  `signal_confidence_insufficient`.

## 5. Period models

Каждый Signal имеет ровно одну модель закрытого discriminated union периода:

- `NoPeriod`: `kind = "no_period"`, `as_of: datetime`;
- `DatePeriod`: `kind = "date"`, `value: date`;
- `DateRangePeriod`: `kind = "date_range"`, `start: date`, `end: date`;
- `YearPeriod`: `kind = "year"`, `year: int`;
- `YearRangePeriod`: `kind = "year_range"`, `start_year: int`, `end_year: int`.

Все перечисленные поля обязательны и не nullable; дополнительные поля и другие
`kind` запрещены. `DateRangePeriod` валидирует `start <= end`,
`YearRangePeriod` — `start_year <= end_year`. `NoPeriod.as_of` берётся только из
`SourceMetadata.received_at`, никогда из clock или другого поля. Arbitration не
использует `no_period`.

`counterparty.active`, конфликт статуса и `dissolved` без даты используют
`no_period` с `as_of=source.received_at`; `dissolved` с датой использует
`date`; long history — `date_range` от регистрации до получения источника.
Одиночные financial rules используют `year`, revenue decline — `year_range`.

Арбитражный signal обязан иметь доказуемый period, построенный по нужным
`case.year`: full-dataset rules требуют год каждого влияющего дела; `open_cases`
требует год каждого использованного открытого дела. При отсутствии нужного года
правило подавляется (`arbitration_period_unavailable`), а не использует
`no_period`.

`finance.reporting_absent`, когда он будет допущен evidence approval, использует
`no_period` с `as_of=FinanceFacts.source.received_at`; текущие часы и фиктивные
reporting years запрещены.

## 6. Missing, partial, failed, warning codes и evidence gate

Отсутствующие, disabled, `not_found`, access/tariff failures, malformed либо
failed datasets не означают отсутствия отчётности, дел или статуса. Они дают
безопасные warnings и не создают сигнал на основании предположения.

Warnings нормализации переносятся в относящийся Signal, если основание остаётся
достаточным; тогда confidence равен `medium`. Неполный arbitration dataset
всегда возвращает result-level `arbitration_incomplete`, в том числе при пустых
signals.

Стабильный реестр warning codes и условия появления:

| Code | Условие появления | Обязательные warning fields |
| --- | --- | --- |
| `dataset_unavailable` | Нужный dataset отсутствует либо его status не `AVAILABLE`, включая disabled, `not_found`, failed, access/tariff и malformed. | `rule_code`, `dataset`, `message`, basis с dataset-status gate в `failed_eligibility` |
| `required_fact_missing` | Dataset доступен, но обязательный нормализованный fact отсутствует/`None` и это не обычный false trigger. | `rule_code`, `dataset`, `message`, basis с отсутствующим fact и failed presence gate |
| `required_period_unavailable` | Для legal-status/finance нельзя построить обязательную валидную period model. | `rule_code`, `dataset`, `message`, basis с period inputs и failed period gate |
| `normalization_warning_present` | Normalization warning присутствует: при достаточном основании он переносится в Signal и confidence становится `medium`; если правило требует clean normalization, как `finance.reporting_absent`, он подавляет правило. | `rule_code`, `dataset`, `message`, basis с facts; для Signal eligibility выполнена и `failed_eligibility` пуст, для suppression failed clean-normalization gate указан явно |
| `status_conflict` | Единственный конфликт ruleset v1 `is_active == true AND dissolved_date is present` подавляет затронутое правило. | `rule_code`, `dataset="counterparty"`, `message`, basis с `is_active`, `dissolved_date` и failed conflict gate |
| `finance_reporting_semantics_unconfirmed` | Для `finance.reporting_absent` не пройден отдельный evidence-gate. | `rule_code="finance.reporting_absent"`, `dataset="finance"`, `message`, basis с failed confirmed-semantics gate |
| `finance_period_conflict` | Дубли/periods одного financial year противоречат друг другу и затрагивают правило. | `rule_code`, `dataset="finance"`, `message`, basis с конфликтующими years/facts и failed consistency gate |
| `arbitration_incomplete` | `ArbitrationFacts.is_complete` не равно `true`; создаётся result-level warning для каждого подавленного arbitration rule. | `rule_code`, `dataset="arbitration"`, `message`, basis с failed completeness gate |
| `arbitration_period_unavailable` | Отсутствует обязательный year хотя бы у одного дела, указанного period contract правила. | `rule_code`, `dataset="arbitration"`, `message`, basis с влияющими `case_ids`, известными `years` и failed year gate |
| `arbitration_summary_conflict` | Cases и summaries противоречат агрегату затронутого правила. | `rule_code`, `dataset="arbitration"`, `message`, basis с cases/summary facts и failed consistency gate |
| `signal_confidence_insufficient` | Trigger выполнен, но confidence основания был бы `low`; Signal любого direction не создаётся. | `rule_code`, `dataset`, `message`, basis с facts и точным failed confidence gate |

Во всех строках также обязательны `code` и `evaluation_basis`; таблица
перечисляет дополнительные ограничения для nullable полей. Suppression warnings
находятся на result level. Signal-level `normalization_warning_present` не
является suppression.

Evidence-gate блокирует только `finance.reporting_absent`. До отдельного
evidence approval этот код не реализуется и не включается в acceptance tests.
Для approval нужны проверенный обезличенный успешный no-reporting fixture либо
официально документированная форма ответа, сравнение с reporting, malformed
`200`, `not_found`, access/tariff responses и доказательство, что
`normalize_finance()` сохраняет различие без raw payload. Если различие теряется,
изменение normalizer-контракта требует отдельного согласования. Остальные
financial signals разрешены к реализации без этого approval.

## 7. Детерминированность и уникальность

- `ruleset_version` всегда равно `"1"`.
- Category order: `legal_status` → `financial` → `arbitration`.
- Внутри category signals сортируются по `code`.
- Детерминированные ключи заданы точно: signals — category order, `code`, затем
  canonical serialized representation всего Signal; facts — `id`,
  `normalized_path`, затем canonical serialized representation всего
  SignalFact; sources — `provider`, `dataset`, `received_at`, `endpoint`,
  `response_hash`, затем canonical serialized representation всего
  SourceMetadata; warnings — `code`, `rule_code or ""`, `dataset or ""`, затем
  canonical serialized representation всего SignalWarning; years — numeric
  ascending; case IDs — lexicographic ascending; expression children —
  canonical serialized representation всего ExpressionNode.
- Canonical serialized representation для всех перечисленных моделей строится
  единообразно: `model_dump(mode="json")`, JSON object keys sorted,
  `separators=(",", ":")`, `ensure_ascii=False`, `allow_nan=False`; `Decimal` не
  преобразуется во `float`.
- Full-object tie-breaker гарантирует, что перестановка sources и warnings с
  одинаковыми primary sort fields не меняет итоговый JSON.
- Перестановка входных facts, periods, cases или warnings не меняет итоговый
  сериализованный JSON.
- Повтор `signal code` запрещён; каждый evaluator возвращает максимум один
  signal на code.
- Повтор `fact id` запрещён; структурные дубли допускаются только после полного
  совпадения и не могут скрыть конфликт значений.
- `Decimal` не преобразуется во `float`; `as_of` берётся из source, а не clock.

## 8. Совместимость и исключения из scope

`CompanyReport v1` не меняется. Signals не входят в `CompanyReport` snapshot,
поэтому существующий snapshot hash не меняется и исторические snapshots
сохраняют обратную совместимость. Provider, normalizers, persistence, ORM,
migrations и API не меняются. Итерация не добавляет зависимости, endpoints,
UI, raw-payload storage или сетевые вызовы.

Signals не содержат score, verdict, probability, recommendation или AI. Любое
сохранение signals/ruleset для scoring, versioning или backfill — отдельное
решение итерации 8 или последующего scope.

## 9. Критерии приёмки

- [ ] Доступен только публичный `evaluate_signals(report) -> SignalEvaluationResult`.
- [ ] Result содержит `ruleset_version="1"`, signals и result-level warnings.
- [ ] Каждый Signal и SignalFactualBasis содержит все контрактные поля.
- [ ] Полностью реализуемые legal-status, arbitration и financial rules имеют
  детерминированный basis и period; `reporting_absent` ждёт отдельного approval.
- [ ] Все правила missing/partial/failed, ordering, exact Decimal и unique IDs
  проверены тестами, включая permutation-identical JSON.
- [ ] CompanyReport snapshot/hash, provider, normalizers, persistence, ORM,
  migrations и API не изменены; отсутствуют scoring и AI.
