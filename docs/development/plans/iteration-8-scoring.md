# Инженерная итерация 8 — scoring: implementation plan

## 1. Текущий DevFlow-запуск и review gate

Статус продуктового контракта: `APPROVED`.

Iteration 8 находится в `planning` на branch `feat/iteration-8-scoring`.
Человек утвердил только Model B, все weights/caps/thresholds, hard gates,
confidence formula, warning semantics, ephemeral lifecycle, функцию
`score_signals` и scoring ruleset version `"1"`.

После сохранения обновлённых specification/plan главный агент запускает
независимый plan review текущего нового planning cycle:

- при `VERDICT: APPROVED` iteration переводится в `implementing`, и разрешён
  запуск `devflow_implementer`;
- при `VERDICT: CHANGES_REQUIRED` применяется единственный разрешённый
  correction pass, после которого главный агент самостоятельно проверяет
  closure; второй независимый plan review не запускается;
- если после correction pass остаётся обязательный blocker, iteration
  переводится в `blocked`, implementer не запускается.

Production-код, tests implementation, commit и push запрещены до
`VERDICT: APPROVED`.

## 2. Точный manifest реализации

Новые production-файлы:

```text
services/product_api/src/product_api/company_reports/scoring/__init__.py
services/product_api/src/product_api/company_reports/scoring/models.py
services/product_api/src/product_api/company_reports/scoring/rules.py
services/product_api/src/product_api/company_reports/scoring/evaluation.py
```

Новые тесты:

```text
services/product_api/tests_unit/test_company_report_scoring_models.py
services/product_api/tests_unit/test_company_report_scoring_evaluation.py
```

DevFlow-артефакты:

```text
docs/development/iterations/iteration-8-scoring.md
docs/development/plans/iteration-8-scoring.md
docs/development/DEVFLOW_STATE.yaml
```

Существующие `aggregate.py`, `signals/**`, `persistence/**`, ORM, migration,
router, gateway и UI файлы не изменяются.

## 3. Контракты файлов

### `scoring/models.py`

Реализовать frozen/extra-forbid:

- `ScoringLevel`;
- `ScoringReasonRole`;
- `ScoringReason`;
- `ScoringDomainBreakdown`;
- `ScoringConfidenceBreakdown`;
- `ScoringWarning`;
- `ScoringResult`.

Validators:

- reject `float`;
- confidence `[0,1]`;
- unique reason signal codes;
- category/direction/strength соответствуют registry;
- informational reason всегда zero;
- scored `contribution == registered weight`, confidence не масштабирует score;
- `score_points is None` iff level `insufficient_data`;
- ровно три domain entries в порядке `legal_status`, `financial`,
  `arbitration`;
- `considered_signal_codes` содержит все present signals category, включая
  informational; `suppressed_rule_codes` содержит rules с единственным
  result-level suppression warning;
- nested code lists лексикографически сортируются и дедуплицируются;
- точные cardinality/field semantics четырёх warning codes;
- deterministic sorting;
- no extras;
- no probability/verdict/recommendation fields.

### `scoring/rules.py`

Зафиксировать immutable approved registry:

- все 13 codes;
- expected category/direction;
- allowed strengths;
- approved Model B weights;
- caps `legal_status [-8,+3]`, `financial [-8,0]`,
  `arbitration [-5,+1]`;
- thresholds `high >=3`, `medium -6..2`, `low <=-7`;
- confidence quality `4/3/4/0`, denominator `52`, multiplier `0.5`,
  quantization `0.0001`/`ROUND_HALF_UP` и minimum `0.6500`;
- scoring ruleset version.

Registry не содержит `finance.reporting_absent`. Изменение production values
после release требует новой scoring ruleset version.

### `scoring/evaluation.py`

Реализовать:

```python
score_signals(
    signal_evaluation: SignalEvaluationResult,
) -> ScoringResult
```

Последовательность:

1. проверить input ruleset и registry compatibility;
2. проверить code/category/direction/strength каждого Signal;
3. проверить warning rule/dataset compatibility;
4. отвергнуть более одного result-level suppression warning на rule;
5. отвергнуть overlap Signal и suppression warning;
6. построить rule states: triggered, suppressed, clean false;
7. построить reason только для каждого присутствующего Signal;
8. вычислить raw domain points и применить только approved Model B category
   caps;
9. построить ровно три domain breakdown entries;
10. вычислить confidence breakdown;
11. применить explicit insufficient-data gates;
12. если gate не пройден — `level=insufficient_data`, `score_points=None`;
13. иначе классифицировать approved thresholds;
14. сформировать warnings с точными semantics спецификации;
15. вернуть новый immutable result без мутации входа.

### `scoring/__init__.py`

Экспортировать модели и `score_signals`. Не добавлять автоматический вызов из
CompanyReport orchestrator.

## 4. Этапы

### Stage 0 — зафиксированное approval и plan review

Product approval уже получен и записан в specification/plan:

- только Model B;
- exact weights/caps/thresholds;
- missing/partial и hard gates;
- confidence formula;
- exact warning semantics;
- ephemeral lifecycle.

Перед Stage 1 независимый plan reviewer должен вернуть `VERDICT: APPROVED`.

### Stage 1 — модели

Реализовать строгие модели, Decimal validation, ordering и cross-field
invariants.

Тесты:

- frozen/extra-forbid;
- enum closure;
- float rejection;
- unique reason codes;
- informational zero;
- scored contribution равен registry weight и не умножается на confidence;
- confidence bounds;
- insufficient-data/score invariant;
- ровно три domain entries и fixed order;
- considered/suppressed list semantics и nested sort/dedupe;
- warning cardinality и exact fields;
- canonical permutation-identical JSON;
- отсутствие raw payload и запрещённых output fields.

### Stage 2 — registry и evaluator

Реализовать только approved Model B weights, category-capped aggregation,
thresholds, hard gates и confidence.

Тесты:

- все 13 production codes;
- отсутствие `finance.reporting_absent`;
- direction/strength validation;
- category mismatch rejection;
- cash-shortfall medium/high variants;
- positive, negative и informational behavior;
- отсутствие runtime/configuration branch для отклонённой Model A;
- exact Model B category caps и algebraic capped range `-21..+4`;
- checked arithmetic boundaries `+3`, `+2`, `-6`, `-7`, `-8`;
- mixed directions без hidden modifier;
- status conflict;
- unknown code/warning и overlap signal+suppression errors.
- duplicate result-level suppression warning rejection.

### Stage 3 — missing/partial и compatibility

Тесты:

- failed evaluation: `insufficient_data`, не `low`;
- отсутствующий finance dataset;
- полностью отсутствующий arbitration dataset: результат разрешён при
  confidence `>=0.6500` и выполненных остальных hard gates;
- отсутствующий counterparty/dissolved gate;
- normalization warning и medium signal confidence;
- source conflicts;
- reasons только для present codes;
- один `source_rule_suppressed` на suppressed rule с exact fields;
- не более одного `mixed_directions`, ровно один `status_conflict` по
  signal/source condition и ровно один `insufficient_data` iff level
  insufficient;
- exact sorted source/signal code lists и static safe messages;
- input permutation invariance;
- отсутствие мутации `SignalEvaluationResult`;
- неизменность `CompanyReport` snapshot/hash;
- scorer не вызывается orchestrator/persistence автоматически;
- отсутствие persistence columns/imports, API, HTTP, DB, clock и randomness.

## 5. Проверки

Targeted:

```text
python -m pytest services/product_api/tests_unit/test_company_report_scoring_models.py services/product_api/tests_unit/test_company_report_scoring_evaluation.py -q
```

Signals и snapshot regression:

```text
python -m pytest services/product_api/tests_unit/test_company_report_signal_models.py services/product_api/tests_unit/test_company_report_signal_evaluation.py services/product_api/tests_unit/test_company_report_counterparty_signals.py services/product_api/tests_unit/test_company_report_finance_signals.py services/product_api/tests_unit/test_company_report_arbitration_signals.py services/product_api/tests_unit/test_company_report_persistence_serialization.py -q
```

Полный затронутый suite:

```text
python -m pytest services/product_api/tests_unit -q
python -m compileall -q services/product_api/src/product_api/company_reports
git diff --check
```

Интеграционные Product API tests не обязательны: нет DB/API/persistence
изменений. Gateway и UI checks не применимы. Python lint/type-check в
репозитории не настроены.

## 6. Definition of done

- approved product contract реализован после `VERDICT: APPROVED` plan reviewer;
- реализована только Model B; Model A отсутствует как runtime/configuration
  option;
- реализован только утверждённый scope;
- нет migration/API/UI/persistence;
- все проверки успешны;
- полный diff прошёл независимый code review;
- DevFlow state переведён в `ready_for_merge` только после проверок/review;
- commit/push выполняет главный DevFlow-агент; merge остаётся ручным.
