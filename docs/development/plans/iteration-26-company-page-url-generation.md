# Итерация 26 — Генерация URL страницы компании: technical plan

ID: 26

Slug: `company-page-url-generation`

Статус: `APPROVED`; решения владельца A1/B1/C1 зафиксированы 2026-08-31.

## 1. Архитектурное решение

Создать pure-модуль
`services/product_api/src/product_api/company_reports/company_urls.py` как
единственный backend source of truth для form registry, boundary stripping,
транслитерации, cleanup, v2 builder и parser трёх URL grammar.

Предлагаемые immutable типы:

```python
@dataclass(frozen=True)
class LegalFormRule:
    full_ru: str
    short_ru: str
    url_token: str

@dataclass(frozen=True)
class CanonicalCompanyIdentity:
    inn: str
    legal_form: str | None
    legal_short_name: str | None
    legal_full_name: str | None

@dataclass(frozen=True)
class CanonicalUrlBinding:
    canonical_path: str
    form_token: str | None
    name_slug: str

@dataclass(frozen=True)
class ParsedCompanyKey:
    kind: Literal["plain", "legacy", "v2"]
    inn: str
    form_token: str | None
    name_slug: str | None
```

`seo.py` сохраняет legacy helper для historical reproduction, но новые
call-sites получают готовый binding из `company_urls.py`. Версионные DB-поля
не добавляются: grammar отличает v2, а policy version — константа кода.

## 2. Затрагиваемые поверхности

### 2.1 Pure URL policy

- новый `services/product_api/src/product_api/company_reports/company_urls.py`;
- `services/product_api/src/product_api/company_reports/seo.py`;
- новый `services/product_api/tests_unit/test_company_report_company_urls.py`;
- существующий `services/product_api/tests_unit/test_company_report_seo.py`.

Реализовать шесть owner-defined rules без недоказанных provider aliases,
строгий алгоритм NFKC/casefold → exact OPF boundary strip → transliteration →
quote deletion → delimiter collapse/trim → bounds, typed parser без slicing и
controlled legacy fallback.

### 2.2 H1 publication

- `services/product_api/src/product_api/company_reports/service.py`;
- `services/product_api/src/product_api/company_reports/public_h1.py`;
- `services/product_api/src/product_api/company_reports/public_h1_service.py`;
- `services/product_api/src/product_api/company_reports/persistence/publications.py`.

Выбрать `legal_short_name`, fallback `legal_full_name`; построить v2 до
upsert publication. Если OPF/name/bounds непригодны, сохранить существующий
legacy generation path. Не добавлять bulk republish и не переписывать existing
authoritative rows.

### 2.3 H2 writer → worker → jobs → pins

- `services/product_api/src/product_api/company_reports/company_card_v2/writer.py`;
- `services/product_api/src/product_api/company_reports/worker.py`;
- `services/product_api/src/product_api/company_reports/persistence/jobs.py`;
- `services/product_api/src/product_api/company_reports/persistence/presentations.py`;
- `services/product_api/src/product_api/company_reports/company_card_v2/public_h2.py`;
- `services/product_api/src/product_api/company_reports/company_card_v2/public_h2_models.py`;
- `services/product_api/src/product_api/company_reports/company_card_v2/service.py`;
- `services/product_api/src/product_api/company_reports/company_card_v2/narrative/service.py`;
- `services/product_api/src/product_api/company_reports/company_card_v2/rollout.py`;
- `services/product_api/src/product_api/company_reports/company_card_v2/canary.py`;
- `services/product_api/src/product_api/company_reports/company_card_v2/canary_models.py`.

Writer вычисляет binding из наблюдённого нормализованного provider result до
потери OPF. Worker передаёт binding отдельно от report snapshot. Jobs сохраняет
report + unresolved pin + outbox атомарно. Resolution и activation копируют
binding byte-for-byte; digest вычисляется только после финального active path.
Retry reuse, null/non-null mismatch conflict, terminal no-provider/no-backfill и
historical NULL fallback покрываются тестами.

### 2.4 Persistence и migration

- `services/product_api/src/product_api/company_reports/persistence/models.py`;
- новый
  `services/product_api/alembic/versions/0021_company_page_canonical_urls.py`;
- новый
  `services/product_api/tests/test_company_page_url_migration_0021.py`.

Миграция только расширяет constraints/state shapes для legacy/v2 и staged
bindings. Она не добавляет URL-version columns и не изменяет данные. Проверить
upgrade `0020 → 0021`, H1 union grammar, H2 unresolved/resolved/active rules,
exact predecessor copy, historical NULL compatibility и guarded downgrade.

### 2.5 Public routing, SSR и sitemap

- `services/product_api/src/product_api/routers/company_reports_public.py`;
- `services/product_api/src/product_api/company_reports/public_document_service.py`.

Общий parser возвращает kind/form/name/INN. Lookup только по INN. Exact
authoritative path даёт `200`; ready plain/legacy/wrong-v2 mismatch — прямой
`301`; legacy authoritative остаётся `200`; GET/HEAD parity; pending H2
сохраняет `302`; invalid grammar даёт existing safe behavior. Public read не
пишет в БД и не вызывает provider/AI. Sitemap читает persisted assignment.

### 2.6 Frontend compatibility

- `services/web_ui/src/companyReport/companyReportPresentation.ts`;
- `services/web_ui/src/companyReport/companyReportH1Contract.ts`;
- `services/web_ui/src/companyPublicH2/contractSemantics.ts`;
- `services/web_ui/src/auth/companyReturnTarget.ts`;
- `services/web_ui/src/pages/CompanyReportPage.tsx`;
- `services/web_ui/src/router/AppRouter.tsx`;
- соответствующие colocated tests.

Обновить grammar validation и INN extraction из v2 suffix. Browser принимает
готовый backend path; transliteration и построение canonical в SPA запрещены.
Зафиксировать Claims `/company/{inn}`, auth return target и bootstrap regressions.

### 2.7 Tracked nginx contract

- `deploy/nginx/product_api.conf`;
- `deploy/nginx/pork.su.conf`;
- `deploy/nginx/product_api_legacy_0015_h2_bootstrap.conf`;
- `deploy/nginx/test_product_api_conf.ps1`;
- `deploy/nginx/test_product_api_legacy_0015_h2_bootstrap.py`.

Направить plain, legacy и form-first paths в Product API до SPA fallback.
Deployment, reload, production migration и traffic switch не выполнять.

## 3. Этапы реализации

1. Зафиксировать решения владельца A1/B1/C1 без расширения утверждённого scope.
2. Реализовать registry, exact OPF matching/stripping, transliteration,
   cleanup, limits, builder и typed parser; сохранить legacy helper.
3. Добавить pure tests для всех mappings, aliases, vectors (`ё/й/х/щ/ъ/ь`),
   punctuation, mixed alphabet, 10/12-digit INN, invalid/ambiguous input,
   boundary stripping, round trip, limits и uniqueness.
4. Добавить `0021`, ORM constraint alignment и dedicated migration tests без
   data backfill/version columns.
5. Перевести новые/естественно новые H1 publications на v2 при пригодной
   identity; unknown/empty/conflicting/overlength сохраняют legacy.
6. Пронести immutable binding через H2 writer → worker → jobs → unresolved →
   resolved staged → active pin; вычислять digest после final path.
7. Обновить router/SSR/sitemap: exact `200`, ready mismatch `301`, pending
   `302`, GET/HEAD parity, без redirect chains и read side effects.
8. Обновить frontend parser/validators/bootstrap/auth target и Claims
   regression tests без UI/breadcrumb changes.
9. Обновить tracked nginx configs и contract tests без deployment.
10. Выполнить targeted/full checks и независимое code review. При
    `CHANGES_REQUIRED` исправить только замечания reviewer и повторить проверки.
11. После `VERDICT: APPROVED` и успешных checks обновить DevFlow state,
    выполнить разрешённые текущим `$devflow` commit/push feature-ветки. Merge
    остаётся ручным.

## 4. Обязательные test surfaces

### Pure/H1/router

- `services/product_api/tests_unit/test_company_report_company_urls.py`;
- `services/product_api/tests_unit/test_company_report_seo.py`;
- `services/product_api/tests_unit/test_company_report_service.py`;
- `services/product_api/tests_unit/test_company_reports_api.py`;
- `services/product_api/tests_unit/test_company_report_public_h1.py`;
- `services/product_api/tests_unit/test_company_report_public_h1_service.py`;
- `services/product_api/tests_unit/test_company_report_public_routes.py`;
- `services/product_api/tests_unit/test_company_report_public_assignment_sitemap.py`.

### H2 lifecycle

- writer/worker/jobs tests;
- `services/product_api/tests_unit/test_company_card_v2_public_h2.py`;
- `services/product_api/tests_unit/test_company_card_v2_public_h2_contract_parity.py`;
- `services/product_api/tests_unit/test_company_card_v2_public_h2_activation.py`;
- `services/product_api/tests_unit/test_company_card_v2_public_h2_side_effects.py`;
- narrative/rollout/canary regressions.

Добавить focused scenario, который доказывает exact binding на всём пути
writer → worker → jobs → unresolved/resolved/active pins, включая retry,
conflict и historical NULL.

### PostgreSQL/migration

- новый `services/product_api/tests/test_company_page_url_migration_0021.py`;
- затронутые publication/presentation/jobs/public route integration tests;
- полный `services/product_api/tests`, если PostgreSQL доступен.

### Frontend/nginx

- colocated tests для шести перечисленных frontend files;
- Claims handoff/router regressions;
- nginx PowerShell и Python contract tests.

Frozen historical fixtures не переписывать. Новые v2 fixtures должны быть
минимальными, synthetic и не содержать raw DataNewton payload.

## 5. Targeted проверки

```powershell
python -m pytest services/product_api/tests_unit/test_company_report_company_urls.py -q
python -m pytest services/product_api/tests_unit/test_company_report_seo.py -q
python -m pytest services/product_api/tests_unit/test_company_report_service.py -q
python -m pytest services/product_api/tests_unit/test_company_report_public_h1.py -q
python -m pytest services/product_api/tests_unit/test_company_report_public_h1_service.py -q
python -m pytest services/product_api/tests_unit/test_company_report_public_routes.py -q
python -m pytest services/product_api/tests_unit/test_company_report_public_assignment_sitemap.py -q
python -m pytest services/product_api/tests_unit/test_company_report_worker.py -q
python -m pytest services/product_api/tests_unit/test_company_card_v2_writer.py -q
python -m pytest services/product_api/tests_unit/test_company_card_v2_public_h2.py -q
python -m pytest services/product_api/tests_unit/test_company_card_v2_public_h2_contract_parity.py -q
python -m pytest services/product_api/tests_unit/test_company_card_v2_public_h2_activation.py -q
python -m pytest services/product_api/tests_unit/test_company_card_v2_public_h2_side_effects.py -q
```

PostgreSQL/migration:

```powershell
python -m pytest services/product_api/tests/test_company_page_url_migration_0021.py -q
python -m pytest services/product_api/tests -q
```

Nginx:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\nginx\test_product_api_conf.ps1
python -m pytest deploy/nginx/test_product_api_legacy_0015_h2_bootstrap.py -q
```

## 6. Полные обязательные проверки

Из корня репозитория:

```powershell
python -m pytest services/product_api/tests_unit -q
python -m pytest services/gateway_api/tests -q
npm run lint --prefix services/web_ui
npm run test --prefix services/web_ui
npm run build --prefix services/web_ui
git diff --check
```

При доступном PostgreSQL:

```powershell
python -m pytest services/product_api/tests -q
```

Migration проверяется из `services/product_api`:

```powershell
alembic -c alembic.ini upgrade head
```

Production/неизвестная БД не затрагивается. Отдельные Python lint/type-check в
репозитории не настроены и не заявляются.

## 7. Риски и меры

| Риск | Мера |
|---|---|
| Выдуманные OPF aliases | Только шесть owner-defined full/short rules; новые — после tracked evidence |
| OPF теряется в H2 projection | Binding вычисляется в writer и передаётся отдельно до pin |
| Повреждение digest | Final path фиксируется до digest; historical rows неизменяемы |
| Разный slug в H1/H2/SPA | Один backend pure-модуль; SPA slug не строит |
| Redirect loop/chain | Сравнение request с persisted authoritative path и прямой `301` |
| Existing pages внезапно меняются | Только новые/естественно новые generations; без bulk republish |
| Migration ломает lifecycle | Минимальные constraints, `0020 → 0021` tests и downgrade guard |
| Unknown form публикует ложный v2 | Fail-closed legacy compatibility |
| Path тихо обрезан | Controlled v2-unavailable при превышении 200/240 |
| V2 не доходит до backend | Три nginx configs и contract tests |
| IP shape меняет provider contract | Отдельное owner decision A |

## 8. Основание для реализации

Владелец выбрал A1/B1/C1: только mapping/parser для ИП, постепенный переход и
шесть owner-defined форм с legacy fallback. Технические замечания plan reviewer
закрыты единственным разрешённым DevFlow correction pass; второй независимый
plan review не выполняется. IP end-to-end, bulk conversion и недоказанные
provider mappings остаются отдельными будущими scopes.
