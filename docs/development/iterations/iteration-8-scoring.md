# Инженерная итерация 8 — scoring

## 1. Статус документа

Статус продуктового контракта: `APPROVED`.

Статус итерации: `planning`; production implementation ожидает
`VERDICT: APPROVED` независимого plan reviewer в текущем новом planning cycle.

Человек явно утвердил scoring ruleset v1: только Model B, weights, category
caps, thresholds, missing/partial policy, hard gates, confidence formula,
warning semantics, ephemeral lifecycle и публичную функцию `score_signals`.

Model A отклонена и сохраняется в приложении только как историческая
альтернатива. Реализовывать, конфигурировать или тестировать её как доступную
production-ветвь запрещено.

## 2. Цель

Преобразовать фактический результат:

```python
SignalEvaluationResult
```

в отдельную прозрачную детерминированную оценку перспективности взыскания:

```python
score_signals(
    signal_evaluation: SignalEvaluationResult,
) -> ScoringResult
```

Scoring не изменяет и не расширяет `CompanyReport` или
`SignalEvaluationResult`, не рассчитывает probability, не является юридической
рекомендацией и не генерирует пользовательский текст.

## 3. Scope

- отдельный pure-domain пакет `company_reports.scoring`;
- строгие frozen/extra-forbid модели scoring result;
- версия scoring ruleset;
- закрытый реестр поддерживаемых signal codes ruleset signals v1;
- проверка code, category, direction и strength входных signals;
- детерминированная агрегация positive, negative и informational signals;
- явная обработка конфликтов и suppressed rules;
- уровни `high`, `medium`, `low`, `insufficient_data`;
- exact `Decimal`;
- structured reasons, confidence breakdown и безопасные warnings;
- stable ordering и permutation invariance;
- неизменность входов и существующего CompanyReport snapshot/hash;
- unit-тесты моделей, правил, границ, incomplete data и совместимости.

## 4. Out of scope

- изменение `CompanyReport`, `SignalEvaluationResult` или signals ruleset v1;
- `finance.reporting_absent`;
- probability или процент взыскания;
- AI, текстовое объяснение, recommendation или юридическое заключение;
- API, routers, service runtime, background jobs и UI;
- persistence scoring, ORM, Alembic и backfill;
- автоматический вызов scoring из orchestrator или persistence;
- новые provider datasets, normalizers и signal rules;
- новые зависимости.

## 5. Входной контракт

Единственный вход — `SignalEvaluationResult` с `ruleset_version="1"`.

Scorer поддерживает только 13 реально реализованных production rules:

| Code | Category | Direction | Allowed strength |
|---|---|---|---|
| `counterparty.active` | `legal_status` | `positive` | `medium` |
| `counterparty.dissolved` | `legal_status` | `negative` | `critical` |
| `counterparty.long_operating_history` | `legal_status` | `positive` | `low` |
| `counterparty.status_conflict` | `legal_status` | `informational` | `high` |
| `finance.negative_equity` | `financial` | `negative` | `high` |
| `finance.revenue_decline` | `financial` | `negative` | `medium` |
| `finance.net_loss` | `financial` | `negative` | `medium` |
| `finance.cash_shortfall` | `financial` | `negative` | `medium` или `high` |
| `finance.high_accounts_payable` | `financial` | `negative` | `high` |
| `arbitration.high_respondent_case_count` | `arbitration` | `negative` | `high` |
| `arbitration.respondent_case_growth` | `arbitration` | `negative` | `medium` |
| `arbitration.open_cases` | `arbitration` | `negative` | `medium` |
| `arbitration.frequent_plaintiff` | `arbitration` | `positive` | `medium` |

`finance.reporting_absent` не входит в реестр.

Для каждого rule code существует ровно одно из состояний:

1. присутствует Signal — trigger сработал;
2. присутствует result-level `SignalWarning` с этим `rule_code` — правило
   suppressed;
3. отсутствуют и Signal, и result-level warning — eligibility была достаточной,
   trigger был false.

Вход отвергается как contract error (`ValueError`), если:

- code отсутствует в scoring registry;
- category, direction или strength не соответствует production contract; для
  `finance.cash_shortfall` разрешены `medium` и `high`;
- один rule одновременно представлен Signal и result-level suppression warning;
- на один `rule_code` приходится более одного result-level suppression warning;
- warning ссылается на неизвестный rule code;
- warning dataset не соответствует registry rule: `counterparty`, `finance`
  или `arbitration` выводится из префикса code;
- ruleset несовместим.

Signal-level normalization warnings не являются suppression warnings.

Scoring не переоценивает `factual_basis` и не извлекает новые факты из
`CompanyReport`.

## 6. Выходной контракт

```python
class ScoringResult(FrozenDomainModel):
    ruleset_version: Literal["1"]
    signal_ruleset_version: Literal["1"]
    level: ScoringLevel
    score_points: Decimal | None
    reasons: list[ScoringReason]
    domain_breakdown: list[ScoringDomainBreakdown]
    confidence: ScoringConfidenceBreakdown
    warnings: list[ScoringWarning]
```

`ScoringLevel` — закрытый enum:

```text
high
medium
low
insufficient_data
```

`ScoringReason` содержит ровно:

- `signal_code`;
- `category`;
- `direction`;
- `strength`;
- `signal_confidence`;
- `weight: Decimal`;
- `contribution: Decimal`;
- `role: scored | informational`.

На каждый реально присутствующий входной Signal создаётся ровно одна reason.
Reasons для отсутствующих или suppressed codes запрещены. Informational reason
имеет `weight=0` и `contribution=0`.

`ScoringDomainBreakdown` содержит:

- `category`;
- `raw_points`;
- `capped_points`;
- `considered_signal_codes`;
- `suppressed_rule_codes`.

`ScoringConfidenceBreakdown` содержит:

- `value: Decimal` в диапазоне `[0, 1]`;
- `quality_points`;
- `max_quality_points`;
- `evaluated_rule_count`;
- `suppressed_rule_count`;
- `high_confidence_signal_count`;
- `medium_confidence_signal_count`;
- `conflict_multiplier`.

`ScoringWarning` содержит:

- стабильный `code`;
- `rule_code: str | None`;
- `source_warning_codes: list[str]`;
- `signal_codes: list[str]`;
- безопасный статический `message`.

Минимальный реестр scoring warning codes:

```text
source_rule_suppressed
mixed_directions
status_conflict
insufficient_data
```

### 6.1. Закрытые типы и cross-field invariants

```python
class ScoringLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT_DATA = "insufficient_data"


class ScoringReasonRole(StrEnum):
    SCORED = "scored"
    INFORMATIONAL = "informational"


class ScoringWarningCode(StrEnum):
    SOURCE_RULE_SUPPRESSED = "source_rule_suppressed"
    MIXED_DIRECTIONS = "mixed_directions"
    STATUS_CONFLICT = "status_conflict"
    INSUFFICIENT_DATA = "insufficient_data"


class ScoringReason(FrozenDomainModel):
    signal_code: str
    category: SignalCategory
    direction: SignalDirection
    strength: SignalStrength
    signal_confidence: SignalConfidence
    weight: Decimal
    contribution: Decimal
    role: ScoringReasonRole


class ScoringDomainBreakdown(FrozenDomainModel):
    category: SignalCategory
    raw_points: Decimal
    capped_points: Decimal
    considered_signal_codes: list[str]
    suppressed_rule_codes: list[str]


class ScoringConfidenceBreakdown(FrozenDomainModel):
    value: Decimal
    quality_points: int
    max_quality_points: int
    evaluated_rule_count: int
    suppressed_rule_count: int
    high_confidence_signal_count: int
    medium_confidence_signal_count: int
    conflict_multiplier: Decimal


class ScoringWarning(FrozenDomainModel):
    code: ScoringWarningCode
    rule_code: str | None
    source_warning_codes: list[str]
    signal_codes: list[str]
    message: str
```

Все модели frozen/extra-forbid и отвергают `float`. Для `role="scored"`
`weight` равен registered weight для code/strength, а
`contribution == weight`: signal confidence не умножает и не меняет score. Для
informational reason оба значения равны `Decimal("0")`.

`domain_breakdown` содержит ровно три записи в порядке `legal_status`,
`financial`, `arbitration`. `considered_signal_codes` содержит все present
signals категории, включая informational; `suppressed_rule_codes` — rules этой
категории с единственным result-level suppression warning. Вложенные code lists
лексикографически сортируются и дедуплицируются. `capped_points` всегда строится
по утверждённым category caps Model B.

`evaluated_rule_count + suppressed_rule_count == 13`; counts и quality points —
неотрицательные `int`, confidence находится в `[Decimal("0"), Decimal("1")]`.
`score_points is None` iff level равен `insufficient_data`; иначе score равен
сумме трёх `capped_points`.

### 6.2. Точные warning semantics

- `source_rule_suppressed`: ровно один на suppressed rule;
  `rule_code=<suppressed rule>`, `source_warning_codes` — sorted unique input
  warning codes этого rule, `signal_codes=[]`, message
  `"A source signal rule was not evaluable."`.
- `mixed_directions`: не более одного и iff присутствуют минимум один positive
  и один negative Signal; `rule_code=None`, `source_warning_codes=[]`,
  `signal_codes` — sorted unique всех present positive/negative codes без
  informational, message
  `"Positive and negative factual signals are both present."`. Modifier к
  score/confidence отсутствует.
- `status_conflict`: ровно один iff present `counterparty.status_conflict` либо
  есть source warning `status_conflict`; `rule_code="counterparty.status_conflict"`,
  `source_warning_codes=["status_conflict"]` при наличии source warning,
  `signal_codes=["counterparty.status_conflict"]` при наличии Signal, иначе
  соответствующий список пуст; message
  `"Counterparty status facts are conflicting."`.
- `insufficient_data`: ровно один iff level равен `insufficient_data`;
  `rule_code=None`, `source_warning_codes` — sorted unique input warning codes,
  повлиявших на hard/confidence gate, `signal_codes` — sorted unique present
  codes, повлиявших на hard gate; message
  `"Available evidence is insufficient for a scoring level."`.

## 7. Утверждённая product model

Scoring ruleset v1 реализует только Model B из приложения A:

```text
legal_status: clamp(raw, -8, +3)
financial:    clamp(raw, -8,  0)
arbitration:  clamp(raw, -5, +1)

score = capped_legal + capped_financial + capped_arbitration
```

Утверждены:

- все weights и cash-shortfall strength override из A.1;
- thresholds `high >= 3`, `medium -6..2`, `low <= -7`;
- dissolved evaluability, status-conflict и confidence hard gates;
- confidence quality `4/3/4/0`, denominator `52`, status-conflict multiplier
  `0.5`, quantization `0.0001` с `ROUND_HALF_UP` и minimum `0.6500`;
- informational contribution `0`;
- mixed directions warning без score/confidence modifier;
- `score_points=None` при `insufficient_data`;
- отсутствие всего arbitration допустимо, если итоговая confidence не ниже
  `0.6500` и остальные hard gates выполнены;
- ephemeral scoring без persistence, migration и backfill;
- scoring ruleset version `"1"` и функция `score_signals`.

Уровни являются эвристической детерминированной классификацией. Они не являются
probability, процентом взыскания, юридической гарантией или рекомендацией.

## 8. Обязательные инварианты Model B

- Только `Decimal`; входные `float` запрещены.
- Операции деления используют явно заданные `Decimal`, rounding и quantization.
- Одинаковый семантический вход даёт byte-equivalent JSON.
- Перестановка signals, signal warnings и result warnings не меняет результат.
- Stable order: reasons — category order
  `legal_status → financial → arbitration`, затем `signal_code`; domain
  breakdown — тот же category order; warnings — `code`, `rule_code or ""`,
  затем canonical full-object tie-breaker.
- Canonical representation: `model_dump(mode="json")`, sorted JSON keys,
  `separators=(",", ":")`, `ensure_ascii=False`, `allow_nan=False`.
- Positive и negative signals влияют только через явно зарегистрированный
  weight.
- Informational signals никогда не имеют скрытого score impact.
- Любое влияние informational conflict на confidence/level отражено отдельным
  warning и breakdown.
- Missing, partial, failed, not_found, access/tariff failure или malformed data
  не создают отрицательные points и сами по себе не приводят к `low`.
- Если данных недостаточно, результат — `insufficient_data`, а
  `score_points=None`.
- `low` возможен только из реально присутствующих adverse signals.
- Mixed positive/negative evidence не получает скрытого penalty; оно отражается
  warning `mixed_directions`, а агрегация остаётся математически прозрачной.
- Scoring не использует время, сеть, БД, randomness, environment, provider или
  raw payload.
- Входные модели не мутируются.

## 9. Persistence и совместимость

Утверждено: результат остаётся ephemeral и вычисляется поверх
`SignalEvaluationResult`.

В этой итерации не меняются:

- CompanyReport snapshot и hash;
- persistence serialization;
- ORM и Alembic;
- provider journal;
- API и сохранённые записи.

Будущее сохранение scoring требует отдельного решения о input snapshot hash,
versions, recalculation/backfill и миграции.

## 10. Критерии приёмки

- Реализована только утверждённая Model B; Model A отсутствует как runtime
  option или альтернативная execution branch.
- Публичен только `score_signals(SignalEvaluationResult) -> ScoringResult`.
- Реестр содержит ровно 13 production codes и не содержит
  `finance.reporting_absent`.
- Unknown inputs и code/category/direction/strength mismatches отвергаются.
- Reasons ссылаются только на присутствующие signals.
- Informational contribution равен нулю.
- Missing/partial снижает confidence либо даёт `insufficient_data`, но не `low`.
- Все численные границы покрыты тестами.
- Перестановки дают идентичный JSON.
- `CompanyReport`, `SignalEvaluationResult` и snapshot/hash не меняются.
- Нет persistence/API/UI/migration/AI/runtime integration.
- Targeted и полный Product API unit suite проходят.
- `git diff --check` проходит.
- Независимый review не содержит блокеров.

---

## Приложение A. Product decision memo — scoring v1

Статус Model B, её weights, caps, thresholds, hard gates и confidence constants:
`APPROVED`.

Model A имеет статус `REJECTED — HISTORY ONLY`.

### A.1. Фактический production registry

| Code | Current direction | Current strength | Approved signed weight |
|---|---|---:|---:|
| `counterparty.active` | positive | medium | `+2` |
| `counterparty.dissolved` | negative | critical | `-8` |
| `counterparty.long_operating_history` | positive | low | `+1` |
| `counterparty.status_conflict` | informational | high | `0` |
| `finance.negative_equity` | negative | high | `-4` |
| `finance.revenue_decline` | negative | medium | `-2` |
| `finance.net_loss` | negative | medium | `-2` |
| `finance.cash_shortfall` | negative | medium | `-2` |
| `finance.cash_shortfall` | negative | high override | `-4` |
| `finance.high_accounts_payable` | negative | high | `-3` |
| `arbitration.high_respondent_case_count` | negative | high | `-3` |
| `arbitration.respondent_case_growth` | negative | medium | `-2` |
| `arbitration.open_cases` | negative | medium | `-1` |
| `arbitration.frequent_plaintiff` | positive | medium | `+1` |

`finance.reporting_absent` исключён: production code отсутствует и evidence
gate не пройден.

`arbitration.frequent_plaintiff` получает ограниченный positive weight: текущий
signal фиксирует частоту выступления истцом, но не успех взыскания.

### A.2. Отклонённая альтернатива — Model A

Статус: `REJECTED — HISTORY ONLY`.

```text
score = sum(reason.contribution)
```

Для каждого domain `raw_points` равен сумме contributions, а
`capped_points == raw_points`. Algebraic registry range при независимом
одновременном включении всех weights равен `-29..+4`; фактическая достижимость
уже из-за signal invariants и несовместимых legal-status комбинаций.

Model A отклонена из-за неограниченного суммирования коррелированных financial
и arbitration signals, чувствительности шкалы к количеству negative rules и
риска чрезмерного понижения результата несколькими отражениями одного
неблагоприятного состояния.

Эти сведения сохраняются только как история решения. Model A не входит в scope,
registry configuration, public API, implementation branches или acceptance
tests.

### A.3. Модель B — hard gates + category caps

Статус: `APPROVED`; единственная модель scoring ruleset v1.

Raw contribution каждого Signal берётся из таблицы. Затем применяются caps:

```text
legal_status: clamp(raw, -8, +3)
financial:    clamp(raw, -8,  0)
arbitration:  clamp(raw, -5, +1)

score = capped_legal + capped_financial + capped_arbitration
```

Утверждённые thresholds:

```text
high:   score >= +3
medium: -6 <= score <= +2
low:    score <= -7
```

До thresholds применяются hard gates:

- rule `counterparty.dissolved` должен быть evaluable: либо Signal, либо clean
  false; suppression этого rule даёт `insufficient_data`;
- присутствие `counterparty.status_conflict` либо source warning
  `status_conflict` даёт `insufficient_data`;
- confidence должен быть `>= 0.6500`;
- при провале gate `score_points=None`.

Основания утверждения Model B:

- critical dissolved остаётся достаточным сильным adverse основанием;
- category caps ограничивают двойной учёт коррелированных finance/arbitration
  facts;
- missing data решается отдельно от adverse evidence;
- при добавлении signals в одной категории шкала устойчивее;
- вся агрегация остаётся воспроизводимой и объяснимой.

### A.4. Informational и conflicts

Статус: `APPROVED`.

- Любой informational Signal: weight и contribution строго `0`.
- `counterparty.status_conflict` не меняет score скрыто; он создаёт reason с zero
  contribution, warning `status_conflict` и явный `insufficient_data` gate.
- Result-level `status_conflict`, `finance_period_conflict` и
  `arbitration_summary_conflict` делают соответствующий rule suppressed и
  снижают confidence.
- Одновременные positive и negative Signals — не data conflict. Они
  агрегируются по weights, создают warning `mixed_directions`, но не получают
  дополнительного score/confidence modifier.
- Ни warning, ни отсутствие Signal не создают negative points.

### A.5. Missing/partial policy

Статус: `APPROVED`.

Для каждого из 13 rules:

- present Signal/high confidence: rule quality `4`;
- present Signal/medium confidence: rule quality `3`;
- clean false trigger: rule quality `4`;
- result-level suppression warning: rule quality `0`.

Missing, failed, disabled, not_found, access/tariff, malformed, incomplete или
conflicting data:

- не дают weight;
- не создают reason;
- уменьшают confidence;
- при hard-gate/threshold failure дают `insufficient_data`;
- никогда сами по себе не дают `low`.

`low` требует реальных present negative Signals.

### A.6. Confidence formula

Статус: `APPROVED`.

```text
max_quality_points = 13 * 4 = 52
base = sum(rule_quality_points) / Decimal("52")
conflict_multiplier =
    Decimal("0.5")
    if (
        counterparty.status_conflict present
        or source status_conflict warning present
    )
    else Decimal("1")

confidence = quantize(
    base * conflict_multiplier,
    Decimal("0.0001"),
    rounding=ROUND_HALF_UP,
)
```

`counterparty.status_conflict` также является hard gate, поэтому multiplier
остаётся прозрачной диагностикой, а не способом получить уровень.

Примеры:

- все rules чисто evaluated: `52/52 = 1.0000`;
- один triggered Signal имеет medium confidence: `51/52 = 0.9808`;
- весь finance suppressed: `32/52 = 0.6154` → ниже approved minimum,
  `insufficient_data`;
- весь arbitration suppressed: `36/52 = 0.6923` → confidence gate пройден,
  если другие hard gates выполнены; отсутствие всего arbitration поэтому
  разрешено, но не гарантирует достаточность при дополнительных снижениях
  confidence;
- весь counterparty suppressed: `36/52 = 0.6923`, но dissolved evaluability gate
  провален → `insufficient_data`;
- все rules suppressed: `0.0000` → `insufficient_data`.

### A.7. Structured reasons

Статус: `APPROVED`.

Reasons содержат все и только реально присутствующие Signals. Примеры:

```json
{
  "signal_code": "finance.negative_equity",
  "category": "financial",
  "direction": "negative",
  "strength": "high",
  "signal_confidence": "high",
  "weight": "-4",
  "contribution": "-4",
  "role": "scored"
}
```

```json
{
  "signal_code": "counterparty.status_conflict",
  "category": "legal_status",
  "direction": "informational",
  "strength": "high",
  "signal_confidence": "high",
  "weight": "0",
  "contribution": "0",
  "role": "informational"
}
```

Suppressed codes могут присутствовать только в `warnings` и
`domain_breakdown.suppressed_rule_codes`, но не в reasons.

### A.8. Граничные примеры модели B

Все результаты являются утверждёнными boundaries scoring ruleset v1.

| Present signals | Score | Result |
|---|---:|---|
| `active +2`, `long_history +1` | `+3` | `high` lower boundary |
| `active +2` | `+2` | `medium` upper boundary |
| `active +2`, finance raw `-8` | `-6` | `medium` lower boundary |
| `active +2`, `negative_equity -4`, `high_accounts_payable -3`, `respondent_case_growth -2` | `-7` after domain calculation | `low` upper boundary |
| `dissolved -8` | `-8` | `low`, если data gates пройдены |
| Любые positive signals + весь finance suppressed | points не финализируются | `insufficient_data`, `score_points=None` |
| `status_conflict` + любые другие signals | points не финализируются | `insufficient_data`, informational contribution `0` |
| Failed report, signals отсутствуют | отсутствует | `insufficient_data`, не `low` |

### A.9. Запись продуктового решения

Человек утвердил:

1. только Model B;
2. все weights A.1 и category caps A.3;
3. thresholds `high >= +3`, `medium -6..+2`, `low <= -7`;
4. dissolved evaluability и status-conflict hard gates;
5. confidence formula A.6 и minimum `0.6500`;
6. отсутствие hidden modifier для mixed directions;
7. `score_points=None` при `insufficient_data`;
8. возможность результата без arbitration при достаточной итоговой confidence;
9. ephemeral lifecycle без persistence/migration/backfill;
10. функцию `score_signals` и scoring ruleset version `"1"`.

Открытых продуктовых вопросов для начала implementation не осталось.
