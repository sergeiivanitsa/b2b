# Итерация 7 — система фактических сигналов

## 1. Предусловия реализации

### Спецификация выходного результата

До production-кода обновить и отдельно утвердить `ITERATION_07_SIGNALS.md`.

Публичный контракт:

```text
evaluate_signals(report: CompanyReport) -> SignalEvaluationResult
```

```text
SignalEvaluationResult:
- ruleset_version: "1"
- signals: list[Signal]
- warnings: list[SignalWarning]
```

`signals` остаётся упорядоченным списком из спецификации. Envelope нужен для предупреждений при нуле сигналов.

`SignalWarning` содержит:

- стабильный `code`;
- `rule_code`, если warning относится к конкретному правилу;
- dataset;
- безопасный message;
- `evaluation_basis` для воспроизводимой причины подавления.

### Evidence-gate для `finance.reporting_absent`

Текущий репозиторий не подтверждает семантику успешного отсутствия отчётности:

- успешные сохранённые probes содержат финансовые формы;
- `available_count: 0` встречается вместе с заполненной отчётностью;
- отсутствует проверенный успешный fixture «отчётности нет».

До finance-этапа необходимо:

1. Получить обезличенный реальный fixture или официально документированную форму успешного ответа без отчётности.
2. Сравнить её с успешным ответом с данными, malformed `200`, `not_found`, access denied и тарифным ограничением.
3. Прогнать успешные варианты через текущий `normalize_finance()`.
4. Доказать, что `FinanceFacts` сохраняет однозначное различие без raw payload.
5. Добавить проверенный fixture и normalizer-тест.

Если существующий `FinanceFacts` теряет различие, `finance.reporting_absent` не реализуется: итерация блокируется до отдельно согласованного расширения normalizer-контракта. Новые DataNewton-запросы требуют отдельного разрешения.

## 2. Текущая архитектура и место signals

Существующий поток:

```text
CompanyReportProvider
→ DataNewtonResult
→ normalizers
→ CounterpartyFacts / FinanceFacts / ArbitrationFacts
→ DatasetReport
→ completeness / freshness / warnings
→ CompanyReport v1
→ persistence snapshot и provider journal
```

Новый поток:

```text
CompanyReport v1
→ evaluate_signals()
→ SignalEvaluationResult
```

Signals — отдельный pure-domain package `product_api/company_reports/signals/`.

Он:

- использует только нормализованные facts, dataset statuses, completeness, `SourceMetadata` и безопасные warnings;
- не выполняет HTTP, БД, AI, чтение raw payload или текущего времени;
- не меняет provider, normalizers, orchestrator и persistence;
- не добавляет поле в `CompanyReport`;
- не требует миграций, endpoints или UI.

## 3. Новые контракты

### Signal

Сохраняются все девять полей:

- `code`;
- `category`;
- `direction`;
- `strength`;
- `factual_basis`;
- `source`;
- `period`;
- `confidence`;
- `warnings`.

Закрытые enums:

- category: `legal_status`, `financial`, `arbitration`;
- direction: `positive`, `negative`, `informational`;
- strength: `low`, `medium`, `high`, `critical`;
- confidence: `low`, `medium`, `high`.

`source` имеет тип `list[SourceMetadata]`.

### Полное основание правила

Каждый созданный сигнал содержит:

```text
SignalFactualBasis:
- facts
- eligibility
- trigger
- strength_decision
- period_basis
- years
- case_ids
```

`facts` — упорядоченные `{id, normalized_path, exact_value}`.

`eligibility` содержит все gates:

- dataset status;
- наличие facts;
- completeness;
- отсутствие блокирующего конфликта;
- пригодность обязательных значений;
- возможность построить корректный period;
- подтверждённую семантику отсутствия отчётности;
- согласованность cases и агрегатов.

`trigger` содержит бизнес-условие срабатывания.

Expression tree поддерживает:

- `predicate`;
- `all_of`;
- `any_of`;
- `not`.

Predicate ссылается на facts и использует операторы presence, equality, comparison, count и точное Decimal-соотношение.

`strength_decision` содержит default strength и упорядоченные overrides `when → strength`.

`period_basis` перечисляет факты, из которых построен обязательный `period`.

### Основание подавленного правила

Если eligibility не выполнен из-за качества или полноты данных, сигнал не создаётся, а result-level warning получает:

- `code`;
- `rule_code`;
- dataset;
- message;
- `evaluation_basis` с facts и failed eligibility.

Обычный false trigger при достаточных данных warning не создаёт.

## 4. Периоды

### Legal status

- `counterparty.active`: `no_period`, `as_of=source.received_at`.
- `counterparty.dissolved` с датой: `date`.
- `counterparty.dissolved` при `is_active=false` без `dissolved_date`: `no_period`, `as_of=source.received_at`.
- `counterparty.long_operating_history`: `date_range` от регистрации до даты получения источника.
- `counterparty.status_conflict`: `no_period`, `as_of=source.received_at`.

### Finance

- `finance.reporting_absent`: `no_period`, `as_of=FinanceFacts.source.received_at`.
- `finance.negative_equity`, `net_loss`, `cash_shortfall`, `high_accounts_payable`: `year`.
- `finance.revenue_decline`: `year_range` из двух сравниваемых последовательных лет.

Для `finance.reporting_absent`:

- `period_basis` содержит точный `source.received_at`;
- текущее время не используется;
- отсутствие отчётных лет не подменяется фиктивным годом;
- сериализация периода детерминирована.

### Arbitration

`no_period` для arbitration не используется.

- `high_respondent_case_count` и `frequent_plaintiff` требуют period, покрывающий полный dataset. Если хотя бы одно дело полного набора не имеет `year`, сигнал подавляется с `arbitration_period_unavailable`.
- `respondent_case_growth` требует год у каждого respondent case, способного влиять на годовой агрегат.
- `open_cases` использует только открытые дела. Если хотя бы одно использованное открытое дело не имеет `year`, сигнал подавляется.
- Один известный год даёт `year`.
- Несколько лет дают `year_range(min, max)`.

Тесты с отсутствующим годом обязательны для всех четырёх arbitration-правил. Для `open_cases` отдельно проверяется, что годы закрытых дел не расширяют его период.

## 5. Правила обработки данных

### Eligibility и конфликты

- Dataset должен иметь `AVAILABLE`, а соответствующие facts должны присутствовать.
- `counterparty.active`:
  - eligibility: доступный counterparty и пригодный `is_active`;
  - trigger: `is_active=true AND dissolved_date is null`.
- `counterparty.dissolved`:
  - eligibility: отсутствие status conflict;
  - trigger: `is_active=false OR dissolved_date present`.
- `counterparty.status_conflict`:
  - trigger: `is_active=true AND dissolved_date present`.
- `counterparty.long_operating_history`:
  - registration date присутствует;
  - `years_from_registration >= 5`.
- Все arbitration-правила включают `is_complete=true` в eligibility.
- Finance reporting absent включает в eligibility проверенную версию контракта отсутствия отчётности, available status, clean normalized state и отсутствие structural warnings, способных объяснить потерю данных.

### Missing и warnings

- `None` не превращается в ноль.
- Отсутствие обязательного факта подавляет правило с rule-specific evaluation warning, если это data-quality limitation.
- Normalization warning при достаточном основании переносится в Signal и снижает confidence до `medium`.
- Confidence `low` не создаёт направленный сигнал.
- `not_found`, disabled, access/tariff failures и malformed data не означают отсутствия отчётности или дел.
- Неполный arbitration возвращает `arbitration_incomplete`, даже если signals пуст.
- Конфликтующие periods одного года подавляют affected finance rule.
- Несогласованность arbitration cases и summaries подавляет затронутое aggregate rule.

## 6. Составные factual basis

- `cash_shortfall`:
  - trigger: `cash < short_term_liabilities`;
  - default strength `medium`;
  - override `high`: `cash < liabilities × 0.25`.
- `frequent_plaintiff`:
  - eligibility: complete dataset и корректный полный period;
  - trigger: `plaintiff_count >= 10 AND plaintiff_count > respondent_count`.
- `dissolved`:
  - eligibility: `NOT(status conflict)`;
  - trigger: `is_active=false OR dissolved_date present`.
- `respondent_case_growth`:
  - eligibility: complete dataset, relevant years известны, последние два года последовательны;
  - trigger: later count `>` previous count AND delta `>=3`.
- `reporting_absent`:
  - eligibility: dataset available, подтверждённая no-reporting semantics, clean normalization;
  - trigger: отсутствуют financial periods и reporting years;
  - period basis: `source.received_at`;
  - period: `no_period`.

Все predicates, gates, period inputs и strength overrides сериализуются; внешние неявные guards запрещены.

## 7. Детерминированность и дубли

- `ruleset_version="1"`.
- Пороги v1: 5 лет, 10 дел, рост 3 дела, 25%.
- Каждый evaluator возвращает максимум один Signal на code.
- Повторяющиеся code запрещены валидатором.
- Порядок: `legal_status`, `financial`, `arbitration`, затем code.
- Facts, expressions, sources, warnings, years и case IDs сортируются стабильными ключами.
- Структурные дубли удаляются только при полном совпадении.
- Конфликтующие значения не разрешаются порядком входа.
- Decimal не переводится во float.
- `as_of` берётся из source, а не из clock.
- Перестановка periods, cases и warnings даёт идентичный JSON.

## 8. Этапы реализации

### Этап 1. Спецификация, модели основания и legal-status rules

Результат: утверждённый контракт, expression tree, eligibility trace и legal-status rules.

Изменяемые файлы:

- `docs/development/iterations/ITERATION_07_SIGNALS.md` — до production-кода и после отдельного утверждения.

Новые production-файлы:

- `company_reports/signals/models.py`;
- `company_reports/signals/common.py`;
- `company_reports/signals/counterparty.py`;
- `company_reports/signals/__init__.py`.

Новые тесты:

- `company_report_signal_test_helpers.py`;
- `test_company_report_signal_models.py`;
- `test_company_report_counterparty_signals.py`.

Тесты:

- expression tree AND/OR/NOT;
- eligibility, trigger, strength и period basis сериализуются;
- active;
- dissolved с датой;
- `is_active=false` без `dissolved_date` и `no_period`;
- status conflict и suppression basis;
- порог 5 лет;
- unknown registration date;
- warning downgrade;
- unique code/fact IDs;
- permutation determinism;
- отсутствие raw payload.

Проверки:

```text
python -m pytest services/product_api/tests_unit/test_company_report_signal_models.py services/product_api/tests_unit/test_company_report_counterparty_signals.py -q
python -m pytest services/product_api/tests_unit -q
git diff --check
```

Критерий завершения: legal-status signal полностью воспроизводится по basis; причины data-quality suppression представлены warning.

Риск отката: низкий.

### Этап 2. Finance evidence-gate и financial rules

Предусловие: подтверждена provider-семантика отсутствия отчётности. Иначе этап блокируется.

Изменяемые production-файлы:

- `company_reports/signals/__init__.py`.

Новые production-файлы:

- `company_reports/signals/finance.py`.

Новые/изменяемые тесты и fixtures:

- проверенный обезличенный no-reporting fixture;
- malformed fixture;
- `test_company_report_finance_normalizer.py`;
- `test_company_report_finance_signals.py`.

Контракты:

- `reporting_absent`;
- `negative_equity`;
- `revenue_decline`;
- `net_loss`;
- `cash_shortfall`;
- `high_accounts_payable`.

Тесты:

- success с отчётностью и подтверждённый success без неё;
- malformed, `not_found`, access/tariff failure;
- `available_count` не используется;
- reporting absence eligibility целиком входит в basis;
- `finance.reporting_absent.period.kind == "no_period"`;
- `finance.reporting_absent.period.as_of == FinanceFacts.source.received_at`;
- `period_basis` содержит тот же `source.received_at`;
- перестановка warnings не меняет `reporting_absent.period`;
- точные финансовые границы;
- два predicates cash shortfall и strength override;
- последовательность revenue years;
- missing/zero;
- последний пригодный период;
- conflicting duplicate year;
- deterministic serialization.

Проверки:

```text
python -m pytest services/product_api/tests_unit/test_company_report_finance_normalizer.py services/product_api/tests_unit/test_company_report_finance_signals.py -q
python -m pytest services/product_api/tests_unit -q
git diff --check
```

Критерий завершения: reporting absent доказан на provider → normalizer → signal цепочке и имеет воспроизводимый `no_period` с source `as_of`.

Риск отката: средний для provider-семантики, низкий для остальных правил.

### Этап 3. Arbitration rules и обязательный полный period

Результат: arbitration rules без недоказуемых периодов.

Изменяемые production-файлы:

- `company_reports/signals/__init__.py`.

Новые production-файлы:

- `company_reports/signals/arbitration.py`.

Новые тесты:

- `test_company_report_arbitration_signals.py`.

Тесты:

- пороги 10 и 3;
- consecutive years;
- open cases;
- plaintiff `>=10 AND >respondent`;
- `is_complete=false`;
- completeness gate в basis;
- общий период отличается от периода открытых дел;
- open case без year подавляет `open_cases`;
- любое дело без year подавляет full-dataset-period rules;
- respondent case без year подавляет growth;
- structured suppression warnings;
- cases/summary conflict;
- case IDs;
- permutation determinism.

Проверки:

```text
python -m pytest services/product_api/tests_unit/test_company_report_signal_models.py services/product_api/tests_unit/test_company_report_arbitration_signals.py -q
python -m pytest services/product_api/tests_unit -q
git diff --check
```

Критерий завершения: ни один arbitration signal не создаётся без доказуемого обязательного period.

Риск отката: низкий.

### Этап 4. Композиция и совместимость

Результат: публичный `evaluate_signals()` и неизменный CompanyReport v1.

Изменяемые production-файлы:

- `company_reports/signals/__init__.py`;
- `company_reports/__init__.py`.

Новые production-файлы:

- `company_reports/signals/service.py`.

Новые/изменяемые тесты:

- `test_company_report_signal_evaluation.py`;
- `test_company_report_persistence_serialization.py`;
- `test_company_report_orchestrator_success.py`.

Тесты:

- complete, partial и failed reports;
- warnings при `signals=[]`;
- все eligibility gates присутствуют в созданных Signals;
- suppression warnings содержат evaluation basis;
- итоговый category/code ordering;
- unique codes;
- identical input → identical JSON;
- permutation determinism;
- нет score/verdict/probability/AI;
- старые snapshots читаются;
- CompanyReport snapshot/hash не меняются;
- нет raw payload и циклических импортов.

Проверки:

```text
python -m pytest services/product_api/tests_unit/test_company_report_signal_evaluation.py services/product_api/tests_unit/test_company_report_persistence_serialization.py services/product_api/tests_unit/test_company_report_orchestrator_success.py -q
python -m pytest services/product_api/tests_unit -q
python -m compileall -q services/product_api/src/product_api/company_reports
git diff --check
```

Критерий завершения: спецификация, runtime-контракт и serialization совпадают; Product API unit suite проходит; независимое review — `approved`.

Риск отката: низкий, миграция данных не требуется.

## 9. Совместимость и открытые вопросы

### Совместимость

- `CompanyReport v1` не меняется.
- Signals не входят в persistence snapshot.
- Старые snapshots и hashes сохраняются.
- Provider protocol, normalizers, ORM, migrations и API не меняются.
- Новые exports additive.
- Predicate schema, periods, ordering и ruleset version становятся стабильным контрактом.

### Вопросы вне репозитория

- Реальная семантика успешного finance no-reporting.
- Хранение ruleset/signals для scoring.
- Срок поддержки старых ruleset.
- Пользовательские и юридические формулировки.
- Будущая политика Tax/FSSP/Bankruptcy warnings.

### Нельзя менять молча

- Пороги 5 лет, 10 дел, рост 3 и 25%.
- `is_active=false` достаточно для dissolved.
- `finance.reporting_absent` всегда использует `no_period` с source `received_at`.
- `frequent_plaintiff=positive` не означает успешное взыскание.
- Неполный arbitration не создаёт агрегатные сигналы.
- Arbitration signal без полного доказуемого period подавляется.
- Clean no-reporting должен быть подтверждён provider evidence.
- Неизвестные finance units запрещают абсолютные пороги.
- Signals не являются score, рекомендацией, вердиктом или вероятностью.

### Нумерация

Во всех новых артефактах использовать:

```text
Итерация 7 — signals
Итерация 8 — scoring
```

Старый заголовок «6. Сигналы» считать номером главы общего плана, а не номером инженерной итерации.
