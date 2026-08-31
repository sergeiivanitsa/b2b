# Итерация 26 — Генерация URL страницы компании

ID: 26

Slug: `company-page-url-generation`

Статус: `READY_FOR_MERGE`. Решения владельца A1/B1/C1 зафиксированы
2026-08-31; реализация и обязательные проверки завершены 2026-09-01.

## 1. Цель

Ввести единый canonical URL страницы компании:

```text
/company/{legal-form}-{company-name}-{inn}
```

Порядок фиксирован: URL-токен организационно-правовой формы,
детерминированный ASCII-slug наименования, исходная строка ИНН. Примеры:

```text
/company/ooo-nazvanie-kompanii-7707079463
/company/pao-nazvanie-kompanii-7707079463
/company/ip-familiya-imya-123456789012
```

Прямой переход на authoritative новый URL открывает правильную компанию.
Старый ready URL остаётся рабочим и, если для этой компании уже существует
authoritative v2 generation, отвечает одним постоянным redirect на неё без
цепочки и loop.

## 2. Подтверждённое текущее состояние

- H1 строит `/company/{inn}-{slug}` в `company_reports/seo.py`.
- Часть H2-кода строит `/company/{inn}-company`.
- Backend, frontend parsers, H1/H2 validators, auth return target и nginx
  признают plain INN и legacy INN-first grammar, но не form-first grammar.
- Claims backlink `/company/{inn}` остаётся discovery/lifecycle URL.
- Sitemap читает сохранённый canonical path текущей publication/pin.
- H1 publication upsertable. Reports, H2 pins, journals и сохранённые
  historical generations не переписываются на месте.
- H2 canonical path входит в projection digest, а public snapshot уже не
  содержит исходную OPF. Поэтому binding должен быть рассчитан по
  нормализованному provider result до потери OPF и передан отдельно от report
  snapshot через writer → worker → jobs → pin.
- В tracked evidence нет проверенного словаря OPF DataNewton. Синтетические
  fixtures не доказывают реальные provider aliases или поддержку ИП
  end-to-end.

## 3. Scope

- Один pure backend-модуль: registry форм, точное распознавание, фиксированная
  транслитерация, cleanup, v2 builder и parser plain/legacy/v2.
- Owner-defined mapping шести обязательных форм: ООО, АО, ОАО, ЗАО, ПАО, ИП.
- V2 URL для новых или естественно заново публикуемых authoritative H1/H2
  generations. Массовая перепубликация existing legacy страниц не входит в
  итерацию.
- Fail-closed compatibility: unknown, empty или conflicting OPF, пустое имя и
  превышение лимита не создают v2; прежний legacy path остаётся допустимым.
- Передача immutable canonical binding по H2 writer/worker/jobs/pin pipeline
  отдельно от структуры CompanyReport и public projection.
- Backend router и frontend contract layer принимают plain, legacy и v2
  grammar. Frontend не транслитерирует и не строит canonical URL.
- Ready mismatch для GET/HEAD: один `301` на сохранённый authoritative path;
  exact canonical: `200`. Pending H2 сохраняет существующий временный `302` на
  plain lifecycle URL.
- SSR, sitemap, auth return target и Claims regression coverage.
- Tracked nginx-конфигурации и contract tests обновляются; production deploy,
  reload и traffic switch не выполняются.
- Append-only migration `0021` меняет только constraints/state compatibility,
  без backfill и без URL-version columns.

Не меняются внешний вид, текст и структура breadcrumbs, отображаемое название,
содержимое/структура отчёта, signals, scoring и provider contracts.

## 4. Canonical identity и источник имени

Builder получает явную нормализованную identity:

```text
inn + legal_form + legal_short_name + legal_full_name
```

Имя выбирается строго как `legal_short_name`, затем fallback
`legal_full_name`. В исходном CompanyReport эти значения происходят из
нормализованных `counterparty.short_name` и `counterparty.full_name`; raw
payload не сохраняется в publication/pin и не используется public read.

Из выбранного имени удаляется не более одного exact alias распознанной OPF:

1. сначала проверяется начало имени;
2. при отсутствии leading alias проверяется конец;
3. если alias есть с обеих сторон, удаляется только leading;
4. сравнение выполняется после NFKC, casefold и свёртки пробелов;
5. кавычки/скобки разрешены только на внешней границе alias;
6. internal matches не удаляются; fuzzy matching и stemming запрещены.

Form нельзя угадывать по названию, breadcrumbs, title, presentation DTO или
первому/последнему слову. Если explicit form не распознана однозначно, v2
binding отсутствует и применяется legacy compatibility.

## 5. Owner-defined registry правовых форм

Эти шесть правил являются продуктовым решением владельца, а не утверждением о
наблюдавшихся значениях DataNewton:

| Полное русское название | Краткое русское название | URL token |
|---|---|---|
| Общество с ограниченной ответственностью | ООО | `ooo` |
| Акционерное общество | АО | `ao` |
| Открытое акционерное общество | ОАО | `oao` |
| Закрытое акционерное общество | ЗАО | `zao` |
| Публичное акционерное общество | ПАО | `pao` |
| Индивидуальный предприниматель | ИП | `ip` |

Для каждого правила exact aliases — только указанные полная и краткая формы.
Дополнительные provider aliases/codes нельзя добавлять без tracked sanitized
evidence и contract tests. Наличие `ИП → ip` в registry само по себе не
доказывает, что текущий DataNewton CompanyReport pipeline поддерживает shape
индивидуального предпринимателя end-to-end.

## 6. Фиксированная транслитерация и cleanup

Политика хранится в коде и не зависит от locale или случайного поведения
библиотеки:

```text
а a   б b   в v   г g   д d   е e   ё yo  ж zh  з z
и i   й j   к k   л l   м m   н n   о o   п p   р r
с s   т t   у u   ф f   х x   ц c   ч ch  ш sh  щ shh
ъ <delete>   ы y   ь <delete>   э e   ю yu   я ya
```

Алгоритм применяется ровно в таком порядке:

1. Проверить тип и непустое значение, применить Unicode NFKC.
2. Для OPF boundary matching выполнить casefold и свёртку whitespace, затем
   удалить максимум один exact alias по правилу раздела 4.
3. Перевести остаток в lowercase.
4. Посимвольно транслитерировать кириллицу по таблице; исходные ASCII
   `a-z0-9` сохранить.
5. Удалить кавычки, апострофы, backticks и маркеры `ъ`/`ь` без separator.
6. Любые прочие whitespace, punctuation и separators преобразовать в `-`.
7. Свернуть повторные дефисы и удалить дефисы с краёв.
8. Проверить grammar и непустой name slug.

Тихое усечение запрещено. Максимум name slug — 200 ASCII-символов, максимум
полного H1 path — 240 символов. Превышение означает controlled v2-unavailable
и legacy compatibility.

Обязательные vectors:

```text
Ёж Йод Хлеб Щука Объект Подъезд
=> yozh-jod-xleb-shhuka-obekt-podezd

ООО + «Ёлка и Щука» + 7707079463
=> /company/ooo-yolka-i-shhuka-7707079463

АО + «Объект» + 7707079463
=> /company/ao-obekt-7707079463

ПАО + ПАО «Компания» + 7707079463
=> /company/pao-kompaniya-7707079463

ИП + Иванов Иван + 123456789012
=> /company/ip-ivanov-ivan-123456789012
```

## 7. URL grammar и parser contract

```text
plain:  /company/{10-or-12-digit-inn}
legacy: /company/{10-or-12-digit-inn}-{legacy-slug}
v2:     /company/{known-form}-{name-token}[-{name-token}...]-{inn}
```

Общий parser возвращает typed result:

```text
ParsedCompanyKey(kind, inn, form_token, name_slug)
```

`kind` равен `plain`, `legacy` или `v2`; для legacy `canonical_slug` остаётся
name-only, а не результатом slicing полного path. INN извлекается по grammar и
сохраняется строкой без изменений. Unicode digits, 11-значный INН,
неизвестный form token, пустое имя, trailing slash и неоднозначный key
отклоняются до DB lookup.

Уникальность обеспечивается ИНН в конце v2 path и существующей уникальностью
полного persisted `canonical_path`: одинаковая identity детерминированна, а
разные ИНН не коллидируют.

## 8. Publication policy и routing

- Новые и естественно заново публикуемые H1 publications получают v2, если
  identity пригодна; H1 остаётся upsertable.
- Новые H2 generations получают binding до public projection и digest.
- Existing authoritative legacy pages продолжают `200` и остаются в sitemap,
  пока штатная новая generation не сделает v2 authoritative.
- Массовая конверсия уже опубликованных страниц и controlled bulk republish —
  отдельная задача.
- Exact persisted authoritative path отвечает `200`.
- Plain path отвечает `301` на ready authoritative path.
- Legacy path отвечает `301`, только если authoritative path уже v2; если
  legacy path сам authoritative, он отвечает `200`.
- Valid wrong-v2 path с тем же INN отвечает прямым `301` на authoritative.
- GET и HEAD имеют одинаковые status/Location semantics, HEAD без body.
- Pending H2 сохраняет текущий `302` на `/company/{inn}`.
- Router не пересчитывает canonical path при наличии assignment/pin и не
  вызывает provider/AI.

## 9. H2 binding pipeline и immutable history

Canonical binding рассчитывается в `company_card_v2/writer.py` из наблюдённого
нормализованного provider result до исключения OPF. `company_reports/worker.py`
передаёт его отдельно; `persistence/jobs.py` атомарно сохраняет report,
unresolved pin и outbox; `persistence/presentations.py` копирует binding без
пересчёта.

State rules:

- новая unresolved pin хранит non-null legacy или v2 binding;
- resolved staged pin копирует binding predecessor byte-for-byte;
- active pin копирует тот же binding и использует его до вычисления финального
  projection digest;
- retry повторно использует binding; mismatch, включая `NULL` против non-null,
  становится state conflict;
- terminal retry не вызывает provider и не выполняет backfill;
- historical pins с `NULL` разрешены; их activation сохраняет прежний fallback
  `/company/{inn}-company`;
- historical rows, snapshots, DTO bytes, journals и digests не обновляются.

## 10. Migration `0021`

URL-version columns не добавляются: plain/legacy/v2 различаются grammar,
canonical path уже хранится, а policy version фиксируется константой в коде.

Append-only migration после `0020`:

- расширяет H1 path constraint до union legacy/v2;
- для H2 допускает historical unresolved/resolved staged pins с `NULL`;
- требует у новых unresolved pins non-null legacy/v2 binding;
- требует от новых resolved pins точной копии binding predecessor;
- требует у active pins non-null authoritative path;
- снимает прежний запрет `NULL`/non-null shape только настолько, насколько
  нужно staged lifecycle; каждый non-null path обязан соответствовать grammar;
- не обновляет данные, assignments, digests или immutable rows;
- downgrade отказывает, если существуют form-first H1 publications/pins или
  non-null staged pins, несовместимые с `0020`.

Нужны отдельные upgrade tests `0020 → 0021`, state/constraint tests и downgrade
guard tests.

## 11. Nginx, SSR, sitemap и frontend

- Три tracked nginx-конфигурации направляют form-first company path в Product
  API до SPA fallback; contract tests фиксируют plain/legacy/v2. Deployment и
  reload вне scope.
- SSR, DTO links и browser location используют сохранённый backend path.
- Sitemap публикует только current assignment/pin path.
- Frontend parsers/validators извлекают INN из v2 suffix, принимают все три
  grammar и не реализуют собственную транслитерацию.
- Claims `/company/{inn}` и auth return target остаются совместимыми.
- Breadcrumb text/structure и отображаемое имя не меняются.

## 12. Acceptance criteria

- Для пригодной identity новая H1/H2 generation получает
  `/{form}-{name}-{inn}` с одним фиксированным алгоритмом.
- Шесть owner-defined форм распознаются только по exact full/short aliases.
- Unknown/conflicting form безопасно сохраняет legacy compatibility.
- Пробелы/separators становятся одним дефисом; кавычки и лишние символы
  удаляются; INN остаётся в конце без изменения.
- Pure vectors, boundary stripping, limits, round-trip parser и uniqueness
  покрыты тестами.
- Новый direct URL открывает правильную компанию.
- Старый authoritative URL не ломается; после появления authoritative v2 он
  отвечает одним `301` без redirect loop.
- H2 writer → worker → jobs → pins сохраняет exact binding при retry,
  resolution и activation.
- Historical H1/H2 paths, snapshots, DTO bytes и digests не меняются.
- Migration append-only, не содержит backfill и защищает downgrade.
- Nginx contract, backend/frontend/SSR/sitemap/auth/Claims regressions проходят.
- UI, breadcrumbs, display name, report content и data structure не меняются.

## 13. Вне scope

- Массовая конверсия existing authoritative legacy pages.
- Production migration/deploy/reload/traffic switch.
- Недоказанные DataNewton OPF aliases/codes или изменение provider contract.
- Добавление `legal_form` в H2 public snapshot/DTO.
- Переписывание applied migrations или immutable history.
- CompanyReport Lab.

## 14. Решения владельца

31 августа 2026 года владелец выбрал A1/B1/C1:

- A1: ИП входит в итерацию только как owner-defined mapping, parser и test
  vectors. DataNewton `individual` end-to-end не меняется и требует отдельной
  задачи с tracked sanitized evidence.
- B1: переход постепенный. V2 получают новые и естественно заново публикуемые
  generations; existing authoritative legacy pages продолжают работать до
  штатного появления новой generation. Bulk conversion вне scope.
- C1: production registry ограничен шестью owner-defined формами ООО, АО, ОАО,
  ЗАО, ПАО и ИП. Unknown forms используют legacy compatibility; дополнительные
  aliases/forms добавляются только после tracked sanitized evidence.
