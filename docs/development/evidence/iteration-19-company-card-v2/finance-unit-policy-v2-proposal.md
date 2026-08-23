# Finance unit policy v2 — proposal

Artifact ID: `company_card_v2_finance_unit_policy_v2_proposal`

Policy candidate: `datanewton_finance_thousand_rub_v2`

Decision date: `2026-08-24`

Base evidence: `finance-unit-evidence-v1.md`, `finance-unit-evidence-v2.md`

State: `PROPOSED — UNVERIFIED — INACTIVE`

## 1. Причина новой версии

Policy v1 остаётся неизменяемой и отклонённой. Она атомарно связывала
доказательство масштаба денежных значений с совпадением `missing` и явного
provider-zero. Матрица v2 дала 69 из 69 точных совпадений ненулевых значений,
но две строки содержали DataNewton `zero` при отсутствии соответствующей
строки в официальном источнике. Эти строки нельзя молча объявить ни нулём, ни
отсутствием данных.

Policy v2 запрещает special case для конкретной компании, года или кода строки
и разделяет четыре независимых вопроса:

1. в каком масштабе передаются сравнимые ненулевые денежные значения;
2. как источник кодирует присутствие, отсутствие и явный ноль;
3. как сохранять и публично проецировать конфликт источников;
4. сохраняется ли точное десятичное представление от ответа provider до DTO.

## 2. Нормативные состояния одной ячейки

| Source state | Нормализованное состояние | Публичное поведение до закрытия gates |
|---|---|---|
| поле отсутствует или `null` | `missing` | значение и геометрия отсутствуют; не показывать `0` |
| явное числовое `0` | `zero_unverified` | сохранить как отдельный source fact, но не отдавать числом в Chart Facts |
| ненулевое число | `nonzero_candidate` | хранить как exact Decimal; не публиковать с единицей до активации scale/transport gates |
| provider zero, comparator missing | `comparator_presence_conflict` | не менять ни одну сторону; исключить ячейку из chart input и показать limitation |
| provider missing, comparator zero | `comparator_presence_conflict` | то же поведение |
| provider nonzero, comparator missing/zero | `comparator_value_presence_conflict` | не использовать для доказательства масштаба; после независимых scale/lexical gates provider nonzero допустим как source-attributed runtime fact с policy-level limitation |
| provider missing/zero, comparator nonzero | `comparator_value_presence_conflict` | не использовать для доказательства масштаба; provider missing остаётся gap, provider zero следует zero gate |
| обе стороны nonzero, значения различаются после OKEI-normalization | `scale_mismatch` | отклонить scale gate |
| один из source artifacts недоступен | `source_unavailable` | не считать missing или conflict; не использовать ячейку как proof |

Ноль не является missing. Missing не является нулём. Конфликт не является
основанием выбрать «более удобный» источник. Отрицательное ненулевое значение
участвует в scale comparison с сохранением знака.

## 3. Независимые gates

### 3.1 `unit_scale_gate`

Доказывает только соответствие одной единицы DataNewton одной тысяче рублей.
В доказательство входят исключительно пары, в которых обе стороны содержат
сравнимые ненулевые значения, а официальный источник явно задаёт OKEI.

Gate может получить состояние `verified_nonzero_thousand_rub`, если свежая
предопределённая матрица удовлетворяет всем критериям раздела 4. Любой
`scale_mismatch`, смешанный масштаб между формами/компаниями/периодами либо
shape drift отклоняет gate.

### 3.2 `presence_semantics_gate`

Отдельно проверяет, одинаково ли источники выражают наличие строки и
отсутствие значения. `zero/missing`, `missing/zero` и
`nonzero/missing` сохраняются как самостоятельные outcomes. Они не считаются
scale mismatch, но не могут подтверждать масштаб и оставляют affected cells
непригодными для доказательства масштаба. Comparator существует только в
offline evidence: он не становится per-report runtime source. После закрытия
scale/lexical gates явный provider nonzero может публиковаться как
source-attributed fact; provider missing/zero остаётся fail-closed по матрице
publication ниже.

Закрытый каталог решений с приоритетом сверху вниз:

| State | Детерминированное условие |
|---|---|
| `rejected` | отсутствует ожидаемая строка матрицы, состояние не входит в закрытый каталог, обнаружены duplicate/shape/classification errors |
| `conflict_observed` | существует хотя бы один `zero_vs_missing`, `missing_vs_zero`, `nonzero_vs_missing`, `missing_vs_nonzero`, `zero_vs_nonzero` или `nonzero_vs_zero` |
| `insufficient` | конфликтов нет, но хотя бы один source недоступен либо agreement coverage ниже заданного порога |
| `verified_observed_alignment` | все ожидаемые строки классифицированы; конфликтов нет; в каждой форме есть минимум по одному `exact_zero` и `exact_missing`; agreement coverage охватывает минимум три компании и четыре разных line codes |

Gate доказывает только поведение наблюдаемой версии provider shape. Он не
превращает comparator в runtime dependency и не разрешает заполнять missing.

### 3.3 `zero_semantics_gate`

Закрытый каталог и приоритет решения:

1. `rejected`, если presence gate равен `rejected` либо обнаружена ошибка
   zero-classification/schema;
2. `blocked_conflict`, если presence gate равен `conflict_observed`;
3. `insufficient`, если presence gate равен `insufficient` либо он verified,
   но exact-zero coverage ниже порога;
4. `verified_public_zero` только при
   `presence_semantics_gate=verified_observed_alignment` и не менее шести
   `exact_zero` ячеек, распределённых минимум по трём компаниям, обеим формам
   и трём line codes.

Других состояний нет. До `verified_public_zero` provider-zero остаётся
`zero_unverified`; вычисления, которым нужна такая ячейка, возвращают
`partial/unavailable`, а не используют подстановку.

### 3.4 `lexical_decimal_transport_gate`

Доказывает сохранение исходной десятичной лексемы и exact Decimal через
decoder, normalizer, snapshot, Chart Facts и JSON DTO. Post-decoder evidence
не закрывает этот gate. Он проверяется fixture/contract tests в реализации
только после снятия внешних blockers.

### 3.5 `publication_gate`

До отдельного owner decision и успешного evidence pass policy имеет состояние
`inactive`. Закрытая матрица разрешённой публикации:

| Scale | Lexical | Presence | Zero | Разрешённые numeric Chart Facts |
|---|---|---|---|---|
| не `verified_nonzero_thousand_rub` | любое | любое | любое | никакие |
| verified | не verified | любое | любое | никакие |
| verified | verified | `rejected` | любое | никакие |
| verified | verified | `conflict_observed` или `insufficient` | не verified | только provider nonzero как DataNewton-attributed fact; provider missing остаётся gap, все provider zero опускаются с policy-level limitation |
| verified | verified | `verified_observed_alignment` | `insufficient`/`blocked_conflict` | только provider nonzero; provider zero опускаются с limitation |
| verified | verified | `verified_observed_alignment` | `verified_public_zero` | provider nonzero и явный provider zero; missing остаётся gap |

FNS comparator не вызывается в runtime, поэтому offline conflict не
приписывается новой runtime-ячейке и FNS value не подменяет DataNewton.
Вместо этого любой незакрытый zero gate глобально запрещает numeric projection
всех provider-zero для этой policy version. Ненулевые provider facts
разрешаются только после независимых scale/lexical gates, сохраняют явную
DataNewton attribution, а projection несёт limitation о наблюдавшихся
presence-различиях policy-level evidence.

Разрешённый будущий частичный результат:

- `unit_scale_gate=verified_nonzero_thousand_rub`;
- `zero_semantics_gate=insufficient|blocked_conflict`;
- ненулевые exact Decimal facts могут быть подготовлены backend после закрытия
  lexical gate;
- нули и конфликты по-прежнему исключаются из numeric Chart Facts с явной
  limitation.

Такой результат сам по себе не разблокирует iteration 20: остаются независимые
counterparty и arbitration gates.

## 4. Критерии свежей scale-матрицы

Scale gate проходит только одновременно при следующих условиях:

- все сравнимые ненулевые ячейки совпадают точно после явной OKEI-normalization;
- каждый из 12 утверждённых кодов имеет exact non-zero evidence минимум у двух
  компаний;
- минимум три разные компании вносят хотя бы одну доказательную exact non-zero
  ячейку;
- представлены обе формы отчётности и обе позиции периода в окне из двух лет;
- ни одна компания не даёт более половины доказательных ненулевых ячеек;
- отсутствуют mixed/form-specific scale, undocumented transform и shape drift;
- все missing/zero/conflict outcomes сохранены, а не удалены из отчёта.

Существующая матрица C01–C03 остаётся отрицательным историческим evidence и не
заменяет свежую матрицу. Её строки нельзя удалить, переименовать в passing или
использовать как единственный cohort для v2.

## 5. Публичная проекция и вычисления

- Денежная единица и формат вроде `273,3 млн ₽` появляются только для
  разрешённых policy/gate states.
- Source truth остаётся Decimal в тысячах рублей; миллионы — только точное
  display formatting, не переписанное хранимое значение.
- `missing`, `zero_unverified` и `comparator_presence_conflict` не создают
  bar/point с нулевой геометрией. Для `comparator_value_presence_conflict`
  допустим только явный provider nonzero после scale/lexical gates; provider
  missing/zero остаётся без геометрии.
- Derived metric становится `partial/unavailable`, если обязательный operand
  отсутствует, содержит неподтверждённый zero либо неразрешённый conflict.
- DTO передаёт machine-readable reason и безопасную русскую limitation;
  браузер не выбирает источник и не восстанавливает значение самостоятельно.
- FNS используется только как offline evidence comparator. Runtime-запросов к
  FNS на read/write path CompanyReport не добавляется.

## 6. Запрещённые трактовки

- special case для кода `1240`, C02, 2024/2025 или любого будущего совпадения;
- преобразование отсутствующей официальной строки в подтверждение provider-zero;
- отбрасывание конфликтов ради прохода процента совпадений;
- вывод масштаба из округлённых сайтов-агрегаторов или визуально похожих сумм;
- `float` как source of truth, скрытое округление или browser-side unit inference;
- активация runtime policy одной лишь правкой документации.

## 7. Решение, требуемое после evidence

После независимого review свежего evidence владелец отдельно решает:

1. активировать ли scale policy только для доказанных ненулевых значений;
2. достаточны ли limitations для частичных финансовых графиков;
3. остаются ли остальные blockers iteration 20 закрытыми.

Public-zero threshold уже зафиксирован policy v2 до cohort commitment:
`6 exact-zero / 3 компании / 2 формы / 3 line codes`. Его изменение после
просмотра evidence запрещено и требует новой policy version и новой
предопределённой матрицы.

До этого решения candidate policy не используется кодом и не меняет H1.
