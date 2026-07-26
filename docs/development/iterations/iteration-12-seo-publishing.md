# Итерация 12 — SEO и контролируемая публикация CompanyReport

ID: `12`
Slug: `seo-publishing`
Ветка: `feat/iteration-12-seo-publishing`

## 1. Цель

Сделать существующий маршрут компании технически индексируемым без
обязательного выполнения SPA JavaScript:

```text
/company/{inn}-{slug}
```

Anonymous request получает содержательный FastAPI SSR из уже сохранённого
immutable CompanyReport snapshot. Авторизованный пользователь продолжает
получать существующую React/Vite страницу iteration 11. Публикация идёт только
явными ограниченными batch-операциями и изначально остановлена.

Не добавляются frontend framework, renderer service, SaaS, внешний JSON API или
новая постоянная инфраструктура: используются существующие Product API, nginx
и PostgreSQL.

## 2. Scope

В scope:

- anonymous FastAPI SSR;
- детерминированные title, description, canonical и robots;
- корректные `200`, `301`, `404`, `500`, `503`;
- `robots.txt`, sitemap index, ограниченные XML chunks и `lastmod`;
- строгая versioned index/noindex policy;
- защита от thin, duplicate и URL-combination content;
- persisted rollout control, публикации, immutable batch manifest и журнал;
- bounded manual CLI с global pause/resume и batch pause/resume;
- nginx routing, сохраняющий authenticated SPA;
- crawl, SEO, privacy, migration, concurrency и regression tests.

Out of scope:

- массовая публикация всех компаний;
- provider/normalizer/CompanyReport snapshot changes;
- новые или изменённые signals/scoring/AI rules;
- claims generation, реклама, Search Console/Яндекс submission;
- реальные DataNewton/OpenAI/browser/search-engine calls;
- автоматический production rollout, migration или nginx install;
- raw provider payload, transport metadata, arbitrary case documents или
  user-specific data в HTML/SEO persistence.

## 3. Rendering architecture

`deploy/nginx/product_api.conf` является source of truth.

Для точного `^/company/{inn}-{slug}$` nginx выполняет internal
`auth_request` к `/internal/whoami` с текущей session cookie:

1. auth `2xx` — существующий SPA fallback `/index.html`;
2. auth `401` — internal proxy исходного URI в anonymous FastAPI SSR;
3. auth `403`, `5xx` или недоступность auth — соответствующая ошибка, без
   fallback в SSR;
4. routing никогда не зависит от User-Agent, crawler IP, Referer или
   SEO-маркера.

Это разделение public и authenticated presentation, а не cloaking. React
`/company/:companyKey`, Product API authenticated CompanyReport endpoints и
frontend bundle не меняются.

`/robots.txt`, `/sitemaps/index.xml` и `/sitemaps/{chunk}.xml` nginx напрямую
proxy в Product API. Остальные API, SSE, assets и SPA routes не меняются.

## 4. Public URL и HTTP contract

Canonical path:

```text
/company/{inn}-{canonical-slug}
```

- `inn`: ровно 10 или 12 ASCII digits;
- slug: `[a-z0-9]+(?:-[a-z0-9]+)*`;
- slug один раз детерминированно строится из allowlisted company name и
  сохраняется в publication registry;
- query string на page/sitemap routes запрещён и даёт `404`;
- приложение само нигде не генерирует noncanonical URL.

| Состояние | Ответ |
|---|---|
| Exact active и indexable canonical page | `200`, `index,follow`. |
| Active publication, valid wrong slug | `301` на canonical без query. |
| Active legacy publication, безопасная, но уже insufficient по текущей policy | `200`, `noindex,follow`, не в sitemap. |
| Missing/unpublished/paused publication, missing/pending/failed report, invalid path | `404`, `noindex,follow`, причина не раскрывается. |
| Active publication с hash/snapshot corruption | `500`, `noindex,follow`. |
| БД или внутренняя инфраструктура недоступна | `503`, `noindex,follow`. |
| Invalid/query sitemap route | `404`, `noindex,follow`. |

Public responses выставляют:

```text
X-Robots-Tag
Cache-Control: no-store
X-Content-Type-Options: nosniff
```

HTML содержит matching `<meta name="robots">`. GET не пишет в registry,
control, batch или journal.

## 5. Strict index policy

Policy version: `publication_sufficiency_v1`.

`index,follow` разрешён только когда одновременно:

1. publication entry `active`;
2. linked report существует и имеет lifecycle `complete` либо `partial`;
3. stored snapshot hash совпадает с immutable report hash;
4. `usable_for_public_page = true`;
5. `usable_for_future_scoring = true`;
6. identity содержит совпадающий INN и непустое allowlisted company name;
7. существующий scoring, вычисленный поверх immutable snapshot, имеет level не
   `insufficient_data`; scoring не меняется и не сохраняется;
8. присутствует хотя бы один substantive block:
   - finance: explicit year и хотя бы одно allowlisted ненулевое или нулевое
     значение, присутствующее в snapshot; либо
   - arbitration: хотя бы один реально присутствующий allowlisted aggregate;
9. canonical/base URL валидны, а privacy/forbidden-key validation проходит;
10. для `partial` identity dataset доступен и хотя бы один substantive dataset
    действительно доступен, а не только содержит placeholder/warning.

Status/requisites без finance или arbitration являются thin content и
`noindex`. Ноль считается фактом только когда он явно присутствует в snapshot;
missing никогда не становится нулём. Policy не вводит финансовых, юридических
или риск-порогов.

Global rollout `paused` останавливает создание/продолжение batch, но не
деиндексирует уже active publications. Emergency global disable остаётся
отдельным fail-closed setting. Это предотвращает массовые `404` при обычной
операционной паузе.

## 6. Allowlisted SSR model

Renderer принимает узкую typed projection, созданную прямо из immutable
stored snapshot. Он не вызывает authenticated `get_latest_company_report`, AI,
provider или worker.

Разрешены:

- name, INN, безопасные реквизиты, registration/activity status;
- finance year/period и exact decimal strings с explicit unit;
- arbitration aggregate counts и суммы только под explicit currency key;
- completeness/freshness timestamps и safe warnings.

Запрещены:

```text
raw_payload, headers, authorization, api_key, provider_limit_metadata,
request_id, endpoint, response_hash, worker_token, lease_expires_at,
safe_error_type, factual_basis, evaluation_basis
```

Также не выводятся arbitrary cases/parties/documents, signals, scoring details,
AI output или неallowlisted recursive JSON.

Missing поля опускаются. Decimal не преобразуется во float. Unit/currency,
выводы и факты не придумываются.

JSON-LD в v1 не выводится: это исключает недоказанные Organization properties;
semantic HTML, canonical и metadata достаточны для scope.

## 7. Deterministic metadata

```text
title = "{company_name} — сведения по ИНН {inn} | Pork.su"
description =
  "Сведения о компании {company_name}, ИНН {inn}: {section-list}."
```

`section-list` — фиксированно упорядоченный список только реально
присутствующих substantive blocks: `финансовые показатели`,
`арбитражные сведения`. Одинаковый snapshot, policy version и settings дают
одинаковые slug, metadata, HTML и policy decision.

## 8. Persistence

Append-only migration `0014_company_report_publications.py` добавляет пять
таблиц.

### `company_report_publication_control`

- singleton `id = 1` с `CHECK (id = 1)`;
- `state IN ('paused', 'active')`;
- `policy_version`, `updated_at`;
- migration seed: `paused`, `publication_sufficiency_v1`.

Control управляет только batch intake/resume.

### `company_report_publications`

- `subject_id` unique FK, `report_id` unique FK;
- `status IN ('active', 'paused', 'disabled')`;
- `canonical_slug`, unique `canonical_path`;
- `snapshot_hash`, `policy_version`, `indexable`, `sufficiency_status`;
- persisted `batch_generation` FK to the immutable PostgreSQL identity of the
  batch that last wrote the row;
- immutable `published_lastmod`;
- publication/disable/audit timestamps.

Checks связывают active/indexable/status fields и grammar canonical path.
Active row всегда имеет non-null report/hash/lastmod. FKs не используют
destructive cascade. Sitemap index: `(status, indexable, canonical_path)`.

`published_lastmod` устанавливается только при успешной publication/replacement:

```text
report.generated_at, иначе report.finished_at
```

GET, sitemap, recheck и audit timestamps его не меняют.

### `company_report_publication_batches`

- state: `running | paused | completed | failed`;
- `requested_limit`, `candidate_count`, `next_ordinal`, `claimed_ordinal`;
- policy version, timestamps, fixed safe failure code;
- immutable, DB-generated monotonic `generation` (unique identity), used for
  publication replacement ordering rather than UUID or wall-clock time;
- checks: `1 <= candidate_count <= requested_limit <= configured max` либо
  zero-candidate completed batch; cursor не выходит за manifest.

### `company_report_publication_batch_items`

Immutable manifest создаётся одной транзакцией:

- `(batch_id, ordinal)` unique/primary;
- subject/report/hash/policy tuple;
- state: `pending | claimed | published | skipped | disabled | failed`;
- claim token/timestamps/fixed reason code;
- state-shape checks и `(batch_id, state, ordinal)` index.

Resume читает только этот manifest и никогда не добавляет candidates.

### `company_report_publication_journal`

Append-only rows содержат batch/ordinal/subject/report/hash/policy, allowlisted
action/reason и timestamp. Нет free-form provider/error text.

Idempotency constraints:

- unique `(batch_id, ordinal, action)`;
- terminal decision key unique
  `(report_id, snapshot_hash, policy_version, action)`.

Policy version входит в ключ. Unique conflict перечитывает existing row и
переиспользует его только при полном совпадении; mismatch — safe state conflict.

## 9. Batch и pause/resume

CLI:

```text
python -m product_api.company_reports.seo_publish control resume
python -m product_api.company_reports.seo_publish control pause
python -m product_api.company_reports.seo_publish run --limit N
python -m product_api.company_reports.seo_publish batch pause --batch-id UUID
python -m product_api.company_reports.seo_publish batch resume --batch-id UUID
```

Дополнительный `SEO_PUBLIC_ROLLOUT_ENABLED=false` по умолчанию является hard
gate; человек должен явно установить его до `control resume`. Migration и
deploy этого не делают.

`run`:

1. требует enabled hard gate и active control;
2. валидирует `1 <= N <= SEO_PUBLISH_BATCH_MAX_LIMIT`;
3. выбирает latest finalized report per subject, исключая уже завершённый
   identical report/hash/policy decision;
4. детерминированно сортирует `(report.created_at, report.id)`;
5. materializes не более N immutable batch items одной транзакцией;
6. обрабатывает только ordinal manifest.

Claim/finalize item использует row locks, conditional updates и claim token.
`pause` блокирует старт следующего unclaimed item; уже claimed item завершается
транзакционно. `resume` продолжает тот же manifest/cursor. Concurrent
run/resume/pause не публикуют один ordinal дважды и не превышают N.

Same report/hash/policy — idempotent reuse. New hash — replacement только после
успешной policy. New policy — отдельная re-evaluation. Failed/insufficient new
candidate не уничтожает предыдущую независимую active publication.
Publication upsert is one PostgreSQL `ON CONFLICT` statement: it can update a
subject only when `excluded.batch_generation` is newer than the persisted
generation. A resumed older batch gets a terminal no-op and preserves journal
history.

CLI не создаёт CompanyReport jobs и не вызывает provider, AI, browser или сеть.

## 10. Sitemap и freshness

`/sitemaps/index.xml` содержит только реально существующие непустые chunks.
Chunk size валидируется `1..50000`. Chunks детерминированно формируются по
`canonical_path`; noindex/paused/disabled rows исключаются.

Каждый `<url>` имеет exact canonical `<loc>` и UTC `<lastmod>` из immutable
`published_lastmod`. Sitemap generation не использует текущее время и не
мутирует persistence.

`robots.txt` указывает только на sitemap index и не выполняет submission.

## 11. Deployment handoff

Добавляется `deploy/nginx/install_product_api_conf.sh`. Он выполняется только
явно человеком на target host, проверяет tracked source path, staging copy,
temporary config validation, backup/atomic install, итоговый `nginx -t`,
rollback при ошибке и reload только после успеха.

Workflow не устанавливает nginx config, не запускает migration/CLI сверх
существующего production deploy и не включает rollout. Локальный contract test
проверяет source-of-truth, auth branch, отсутствие User-Agent routing и public
SEO locations.

## 12. Acceptance criteria

- Anonymous eligible canonical URL даёт meaningful SSR без SPA JS.
- Authenticated `/company/:companyKey` сохраняет iteration 11 behavior.
- Metadata, canonical, robots, statuses и lastmod детерминированы.
- Failed/pending/missing/thin/private/corrupt/insufficient pages не
  индексируются и не попадают в sitemap.
- Partial индексируется только по явной sufficiency policy.
- Нет raw/internal/AI/signals/scoring disclosure.
- Batch manifest ограничен N, pause/resume не меняет состав и rerun idempotent.
- Rollout начинается paused и production автоматически не активируется.
- Crawl не создаёт бесконечные URL combinations.
