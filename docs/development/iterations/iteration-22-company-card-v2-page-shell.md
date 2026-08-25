# Итерация 22 — Каркас страницы, SSR и CTA Company Card v2

ID: 22
Slug: company-card-v2-page-shell
Public contract: company_public_h2_v1
Canonical JSON profile: company_public_h2_cjson_v1
Asset manifest: company_public_h2_asset_manifest_v1
Base commit: 5fa69e7
Branch: feat/iteration-22-company-card-v2-page-shell
Статус спецификации: approved_after_single_correction
Production activation: NOT AUTHORIZED

## 1. Цель

Реализовать responsive page shell Company Card v2 поверх сохранённой строгой
проекции company_public_h2_v1:

- server-rendered SEO/text document;
- hero, status, immutable report date и narrative/fallback;
- доступную навигацию по странице;
- реквизиты, coverage, sources, limitations и actions;
- desktop sticky Claims CTA;
- tablet/mobile fixed bottom CTA;
- безопасный embedded DTO;
- React takeover без повторного factual GET;
- server-authoritative выбор H1/H2 document;
- отдельную Webvisor-free asset boundary.

H1 остаётся production-default, совместимым публичным документом и rollback
path. Итерация не активирует H2 assignment и не добавляет финансовые либо
арбитражные chart renderers.

## 2. Нормативные источники

Приоритет решений:

1. AGENTS.md, README.md, Roadmap и DEVFLOW_STATE.yaml.
2. Итерация 19, в особенности sections 18–21, 24, 26–30 и 34–35.
3. Реализованные backend и persistence contracts итерации 20.
4. Saved-result-only narrative и SSR adapter итерации 21.
5. C:\Дебиторка\Новая схема страницы.pdf как структурный, не pixel-perfect,
   референс порядка секций.
6. C:\Дебиторка\ФОРМА СПРАВА.png как композиционный референс CTA.
7. Утверждённый planning input итерации 22.
8. Существующий H1 frontend/SSR behavior и Claims handoff.

При конфликте:

- DTO и source facts не дополняются UI-выводами;
- missing не становится zero или отрицательным фактом;
- #EE5A2A используется как CTA accent, не как verdict color;
- CTA copy и Claims target из этой спецификации важнее регистра или
  декоративных деталей PNG;
- PDF определяет секционный ритм, но не размеры, типографику или chart art;
- H1 bytes, renderer и goldens остаются неизменными.

## 3. Scope

### 3.1. Backend document boundary

- Active-assignment-only selector canonical document.
- H1/H2 selection до rendering.
- H2 SSR text shell и safe error documents.
- Per-response CSP nonce.
- Один script-safe embedded H2 DTO.
- Exact asset-manifest validation при старте Product API.
- Canonical, wrong-slug, HEAD, robots и lifecycle behavior.
- No-write/no-provider/no-Gateway/no-AI guards.

### 3.2. Frontend

- Dedicated H2 React entrypoint, не импортирующий SPA App, AuthProvider,
  BrowserRouter, index.html или index.css.
- Recursive closed parser полного company_public_h2_v1.
- Strict raw JSON parser с duplicate-key и surrogate rejection.
- TypeScript company_public_h2_cjson_v1 и projection digest verification.
- React shell и responsive CSS.
- Accessible CTA, navigation, focus и live-region enhancement.
- Landing → company через full document navigation.

### 3.3. Deployment

- Content-addressed H2 JS/CSS build.
- Product-embedded pinned asset manifest.
- Asset-first nginx storage, не очищаемое обычным Vite build.
- Plain-INN H1 SPA fallback и canonical document proxy separation.
- Синхронизация product_api.conf и pork.su.conf.
- Compatibility and rollback checks.

### 3.4. Tests and evidence

- Product unit/integration tests.
- Frontend contract/component/bootstrap tests.
- Shared Python/TypeScript canonical vectors.
- Nginx, deploy и asset-manifest tests.
- Real-browser responsive visual matrix.

## 4. Вне scope

- F1–F5 financial chart renderers, geometry, interactions и chart-specific
  tables.
- A1–A5 arbitration chart renderers, KAD links, tooltips и large-N drill-down.
- Claims auth, form, storage, prefill или handoff semantics.
- Provider datasets, provider calls, refresh, backfill или probes.
- AI prompt, Gateway, budget, narrative generation или fallback semantics.
- Signals, scoring, verdict, probability или recommendations.
- H2 assignment/CAS activation, sitemap inclusion, rollout percentage или
  production flag changes.
- Изменение или удаление H1.
- Production deploy.
- Новые runtime/npm/Python dependencies.
- Alembic migration или изменение DB schema.

## 5. Неизменные инварианты

### 5.1. Default-off and rollback

Default configuration remains:

    COMPANY_CARD_V2_PRESENTATIONS_ENABLED=false
    COMPANY_CARD_V2_WRITER_ENABLED=false
    COMPANY_CARD_V2_ROLLOUT_GENERATION=0
    COMPANY_CARD_V2_ALLOWLIST_INNS=[]
    COMPANY_CARD_V2_PERCENTAGE_BASIS_POINTS=0

- assign_pin_cas продолжает запрещать H2 assignment.
- Итерация не создаёт и не изменяет H2 assignment.
- Отсутствующий assignment означает H1.
- H1 canonical SSR body и H1 DTO/goldens byte-stable.
- H1 lifecycle, auto-create, polling и Claims flow не меняются.
- Rollback не требует удаления H2 assets, reports, pins или narrative
  artifacts.

### 5.2. Read-only document path

H2 document read выполняет только SELECT и локальное deterministic rendering.
Он не вызывает:

- generic resolve_public_h2 selection;
- provider/FNS;
- Gateway/AI;
- report/presentation create;
- queue/worker/reconciler;
- reservation/budget;
- signals/scoring;
- publication mutation;
- Claims mutation;
- telemetry/Webvisor.

### 5.3. Exact displayed identity

На странице видимо отображается exact root.report_id.

Следующие значения обязаны быть byte-identical после lowercase canonical UUID
validation:

    root.report_id
    SSR root data-report-id
    visible report ID
    primary_claim_cta.path report_id
    actions.prepare_claim.path report_id
    React root data-report-id

Ни presentation_id, ни lifecycle/report IDs других runs не могут появиться в
DOM или Claims target.

## 6. Server-authoritative document selection

### 6.1. Critical selector rule

Canonical document selector не вызывает существующие generic
resolve_public_h1 или resolve_public_h2 до того, как одним assignment-aware
SQL statement зафиксирован выбор документа.

Persistence helper выполняет один SELECT:

    CompanyReportSubject
    LEFT JOIN CompanyReportPresentationAssignment
      ON assignment.subject_id = subject.id
    LEFT JOIN CompanyReportPresentationPin
      ON pin.subject_id = assignment.subject_id
     AND pin.presentation_contract = assignment.presentation_contract
     AND pin.generation = assignment.pin_generation
    LEFT JOIN CompanyReportRecord
      ON report.id = pin.report_id
     AND report.subject_id = subject.id
    WHERE subject.normalized_identifier = :inn

Этот joined SELECT является единственным чтением assignment для запроса и
возвращает immutable `PublicDocumentAssignmentRow` с subject, assignment,
exact pin и exact report. Selector не выполняет повторный assignment lookup и
не смешивает строки, прочитанные до и после concurrent assignment change.

Generic resolve_public_h2 запрещён, поскольку его precedence равен:

    assignment
    → staged pointer
    → lifecycle head
    → legacy preview

Staged pointer, lifecycle head и legacy preview не имеют права вытеснить H1
canonical document.

Selection:

| Joined assignment state | Canonical document |
|---|---|
| Subject отсутствует | обычный H1 not-found/lifecycle result |
| Assignment отсутствует | legacy-compatible H1 через обычный resolve_public_h1 |
| Exact H1 assignment + valid exact H1 pin/report | H1, построенный только из exact assigned pin/report |
| Exact H2 assignment + valid exact H2 pin/report/artifact/digest | H2 |
| Assignment существует, но joined pin/report отсутствует | fail closed |
| Unknown contract или tuple mismatch | fail closed |
| Corrupt/changed exact H1 pin/report/snapshot/canonical binding | fail closed |
| Corrupt exact H2 binding/artifact/digest | fail closed |
| Staged/head/legacy H2 без assignment | H1 |

Exact H1 assignment запрещено разрешать через active publication, latest
report, history scan или resolve_public_h1. Для него pure validator проверяет:

- assignment subject/contract/pin_generation;
- exact pin subject/contract/generation/report_id;
- report subject, lifecycle, snapshot hash и serialized report identity;
- H1 publication_policy_version;
- indexable=true;
- canonical_path и его exact INN;
- published_lastmod, равный generated_at.

После проверки H1 DTO строится через существующий build_public_h1 с
projection_scope="published" и persisted canonical/indexable значениями exact
pin. HTML всегда выдаёт неизменённый render_public_h1_html.

Если exact assigned H1 отличается от active publication или latest report,
выбирается assigned H1. Повреждение assigned H1 даёт 500 и никогда не
переключает запрос на active/latest H1 либо H2.

H2 success в iteration-22 tests достигается прямой fixture/injected exact
assignment. assign_pin_cas продолжает запрещать H2; persistence activation
остаётся невозможной до iteration 25.

### 6.2. Route forms

Accepted company keys:

    /company/{10-or-12-digit-inn}
    /company/{10-or-12-digit-inn}-{lowercase-ascii-slug}

Query parameters запрещены.

Plain INN:

- если exact selected H1 или H2 projection существует, сервер делает 301 на
  canonical_path этой exact projection;
- если H1 projection отсутствует, сервер возвращает controlled 404 только для
  nginx H1 SPA fallback;
- selected H2 lifecycle/corruption error никогда не превращается в 404.

Canonical key:

- correct H1 slug → unchanged H1 SSR;
- correct H2 slug → H2 SSR;
- wrong slug → 301 на path exact selected DTO;
- no projection → direct safe response, без SPA fallback.

### 6.3. Document HTTP matrix

| Situation | Status | Body |
|---|---:|---|
| Correct canonical selected document | 200 | H1 or H2 HTML |
| HEAD equivalent | same as GET | empty |
| Plain key or wrong slug with exact selected projection | 301 | empty |
| Plain key without eligible H1/H2 projection | 404 | nginx may serve H1 SPA |
| Query parameter | 422 | safe noindex error |
| Invalid route key reaching backend | 404 | safe noindex error |
| Selected H2 pending | 409 | safe noindex lifecycle document |
| Selected H2 failed/not eligible | 409 | safe noindex lifecycle document |
| Corrupt assignment/pin/DTO/digest | 500 | safe noindex error |
| Database unavailable | 503 | safe noindex error |

H2-selected errors contain no DTO, assets or factual React root and never fall
back to H1.

### 6.4. Pre-correction digest isolation matrix

Три сценария старого H2 projection digest проверяются раздельно:

| Scenario | Endpoint | Expected result |
|---|---|---|
| Нет assignment, staged H2 pin имеет старый digest | canonical `/company/{company_key}` | canonical H1; staged H2 не читается selector |
| Нет assignment, тот же staged H2 pin имеет старый digest | generic `/company-reports/{inn}/public-h2` при разрешённом test cohort | существующий H2 API воспроизводит exact staged pin и fail closed с 500 |
| Exact H2 assignment указывает на pin со старым digest | canonical `/company/{company_key}` | safe noindex 500; H1 fallback запрещён |

Эти tests используют отдельные database fixtures. Они не переписывают pin,
не создают новый digest и не меняют поведение generic H2 API.

## 7. H2 navigation contract correction

Iteration 20 currently emits /company for check_another_company, хотя route
отсутствует и approved contract требует /.

Before frontend consumption, H2 model/builders/goldens are corrected to:

    actions[0]:
      action_id = check_another_company
      label = Проверить другую компанию
      path = /

    actions[1]:
      action_id = prepare_claim
      label = Подготовить претензию
      path = /claims?report_id={root.report_id}

    breadcrumbs[0]:
      label = Главная
      path = /
      current = false

    breadcrumbs[1]:
      label = identity.display_name
      path = root.canonical_path
      current = true

    primary_claim_cta:
      action_id = prepare_claim
      heading = Вам задолжали?
      desktop_copy =
        Запустите процесс взыскания прямо сейчас: создайте досудебную
        претензию онлайн!
      button_label = Создать претензию
      path = /claims?report_id={root.report_id}

CompanyPublicH2Response root validator проверяет все cross-bindings.

Compatibility:

- H2 никогда не был production-active.
- Existing staged pre-iteration-22 pins не переписываются.
- Их старый projection digest может перестать воспроизводиться и обязан fail
  closed.
- Возврат такого report в будущий active H2 требует explicit append-only
  republish/new pin generation, а не mutation/backfill.
- H1 и immutable snapshots не меняются.

## 8. SSR document contract

### 8.1. Visible structure

H2 SSR body содержит в порядке:

1. breadcrumbs;
2. hero/status/identity;
3. immutable checked date and visible report ID;
4. narrative or deterministic fallback;
5. in-page navigation;
6. requisites;
7. finance shell;
8. arbitration shell;
9. sources;
10. limitations;
11. neutral bottom actions;
12. primary Claims CTA.

Finance/arbitration shell:

- содержит semantic headings;
- показывает exact coverage state и связанные limitations;
- не интерпретирует chart facts;
- не вычисляет trends, totals, verdicts или summaries;
- не рисует charts;
- сохраняет anchors для iterations 23–24.

### 8.2. Embedded state

Ровно один state element:

    <script id="company-public-h2-state"
            type="application/json"
            nonce="{per-response-nonce}">{script-safe-json}</script>

Requirements:

- complete validated DTO including verified digest;
- no surrounding whitespace/newline inside element;
- maximum 786432 UTF-8 bytes;
- <, >, &, U+2028 и U+2029 escaped;
- unpaired surrogate rejected;
- no raw snapshot/provider/private fields;
- no second embedded state.

### 8.3. Head

H2 server owns:

- html lang=ru;
- UTF-8 and viewport;
- title;
- description from fixed product template, not new AI generation;
- one robots meta;
- one canonical link;
- stylesheet and module asset references;
- no client-side head mutation.

Robots:

    structurally indexable + persisted indexable=true -> index,follow
    persisted indexable=false                        -> noindex,follow
    errors/redirect                                  -> noindex,follow

«Structurally indexable SSR» означает, что документ уже содержит полноценные
server-owned title, description, canonical link, visible factual text и
robots/header consistency, достаточные для будущего индексируемого режима.
Это не означает, что H2 индексируется в iteration 22.

Текущая DB constraint допускает H2 pins только с indexable=false и
canonical_path=NULL. Поэтому любой test-injected exact H2 assignment в
iteration 22 выдаётся с noindex,follow; canonical path берётся из строго
воспроизведённого DTO, а не записывается обратно в pin. Возможность
indexable=true, persistence/CAS activation, sitemap inclusion и production
indexing принадлежат iteration 25.

### 8.4. Security headers

    Cache-Control: no-store
    X-Content-Type-Options: nosniff
    Referrer-Policy: no-referrer
    Permissions-Policy: camera=(), microphone=(), geolocation=()

CSP:

    default-src 'none';
    base-uri 'none';
    object-src 'none';
    frame-ancestors 'none';
    form-action 'self';
    img-src 'self' data:;
    font-src 'self';
    style-src 'self';
    script-src 'self' 'nonce-{nonce}';
    connect-src 'self';
    manifest-src 'self';

Forbidden:

- unsafe-inline;
- third-party scripts;
- analytics/Webvisor;
- inline style;
- external factual fetch.

## 9. Dedicated asset manifest

### 9.1. Product-pinned current manifest

Текущий manifest является tracked Product resource:

    services/product_api/src/product_api/company_reports/company_card_v2/
      public_h2_asset_manifest.json

`services/product_api/pyproject.toml` включает этот JSON в package data.
Product загружает exact bytes через importlib.resources при startup, запрещает
BOM/non-UTF-8/unknown fields и вычисляет identity:

    manifest_sha256 = lowercase SHA-256 exact tracked file bytes

Manifest schema:

    schema_version: company_public_h2_asset_manifest_v1
    public_contract_version: company_public_h2_v1
    canonical_json_profile: company_public_h2_cjson_v1
    entry_js_path: /assets/company-public-h2.{content-hash}.js
    entry_css_path: /assets/company-public-h2.{content-hash}.css
    optional_chunk_paths: sorted same-origin content-hashed paths
    assets[]:
      path
      media_type
      sha256_hex

Rules:

- recursively extra-forbid;
- UTF-8 with LF and exactly one terminal LF;
- all paths same-origin absolute and traversal-free;
- basenames begin with company-public-h2.;
- filename content hash agrees with built Vite output;
- paths are unique;
- optional_chunk_paths and assets are sorted by path;
- exactly one primary JS and CSS;
- every referenced path occurs once in assets;
- sha256_hex is lowercase 64-hex;
- SRI is derived as `sha256-{base64 digest bytes}`;
- schema, contract and CJSON profile are exact constants.

Product startup validates and pins this manifest before serving traffic.
Renderer receives the already-loaded immutable object. Product does not read
nginx dist, host manifest history or asset bytes.

### 9.2. Vite verification and release artifact

Dedicated Vite output is isolated at:

    services/web_ui/dist-company-public-h2/

It is not written into or discovered from the SPA dist. The authoring command
is the only command allowed to update the tracked Product manifest. Normal
build/CI runs verification-only mode:

1. read the tracked manifest;
2. traverse the dedicated Vite entry graph;
3. require exact equality of entry/chunk/CSS path sets;
4. recompute every SHA-256;
5. scan dedicated bytes for forbidden SPA/Auth/Webvisor markers;
6. fail on any missing, extra or mismatched file;
7. package exactly the tracked manifest and referenced assets into the release
   artifact.

The release artifact records manifest_sha256 and contains no previous
manifests. Previous manifests come only from the destination host’s durable
verified history.

### 9.3. Durable host store and history

Stable host root:

    /var/lib/pork/company-public-h2/v1/

Layout:

    assets/{basename}
    manifests/sha256/{manifest_sha256}.json
    manifest-set.json
    .install.lock

`manifest-set.json` schema is exact:

    schema_version: company_public_h2_manifest_set_v1
    current_manifest_sha256: <64 lowercase hex>
    retained_manifest_sha256:
      - <current>
      - <previous>
      - <previous-2>

The retained array contains exactly three distinct identities, newest first,
and its first element equals current_manifest_sha256. Immutable manifest files
are addressed by SHA-256 of their exact bytes.

For a non-idempotent release, previous and previous-2 are read only from the
already verified destination `manifest-set.json` and immutable manifest
directory. Git history, filename order, dist contents and CI cache are not
history sources.

Installer behavior under an exclusive lock:

1. validate current release manifest and source bytes;
2. load and validate the existing manifest-set;
3. load all three existing immutable manifests by digest;
4. verify every existing manifest identity and every referenced stored asset;
5. install new assets through same-directory temporary files, fsync and atomic
   rename; reject a mismatched existing basename;
6. install the new immutable manifest using the same procedure;
7. form `[new, old-current, old-previous]`;
8. verify all three manifests and every referenced asset again;
9. verify every URL through loopback nginx and hash returned bytes;
10. write a complete temporary manifest-set, fsync it, atomic-rename it over
    manifest-set.json and fsync the parent directory;
11. rerun identity, stored-hash and loopback reachability checks.

An idempotent install revalidates the existing exact three-entry set without
rotating it. A missing/malformed pointer, fewer than two valid predecessors,
missing manifest, missing asset, hash mismatch, unreachable URL or a new empty
host fails before Product replacement. Initial/DR history seeding requires a
separately reviewed iteration-25 runbook and is outside iteration 22.

The workflow may replace Product only after the host current digest equals the
manifest digest extracted offline from the candidate Product image and all
current-plus-two checks pass. Rebuilding or publishing SPA dist never deletes
this store.

## 10. React takeover

Dedicated entrypoint:

    services/web_ui/src/companyPublicH2/main.tsx

It imports only H2 modules and H2 CSS.

Bootstrap:

1. find exactly one state script;
2. enforce script-safe byte cap;
3. parse raw JSON with duplicate-key/NFC-collision detection;
4. validate full recursive DTO;
5. validate root DOM contract/report ID/canonical path;
6. canonicalize DTO without projection_digest;
7. verify SHA-256 via crypto.subtle;
8. mount React using the already parsed DTO;
9. perform zero fetch/XHR/lifecycle/create/status calls.

Failure:

- SSR factual root remains unchanged;
- React does not mount;
- H1 app does not mount;
- a fixed local non-factual enhancement-unavailable notice may be placed in the
  pre-existing live region;
- no head mutation.

On successful takeover, an SSR fixture parity test requires the ordered
data-h2-field map and visible text to remain equal before and after React
rendering.

All links are regular anchors. H2 bundle does not use React Router.

## 11. Page shell

### 11.1. Hero and narrative

Hero displays:

- neutral status marker;
- identity.display_name;
- exact INN;
- backend-provided status label/effective date, when present;
- otherwise «Статус не указан в отчёте»;
- exact checked_date_display;
- visible exact report_id.

No status is inferred from missing data.

Narrative displays exact saved description and a visible mode note
distinguishing saved artifact from deterministic fallback. There is no
client-side generation, repair, formatting inference or markdown
interpretation.

### 11.2. Requisites

Render only DTO leaves:

- legal full/short names;
- INN/OGRN/KPP;
- registration/dissolution dates;
- legal form;
- approved address;
- charter capital only when present;
- admitted tax modes and activities;
- admitted managers/owners/employees/tax authority only when already public in
  DTO.

Null/empty values are either omitted or shown as neutral unavailable text. They
never become zero or negative facts.

### 11.3. Sources and limitations

- source order remains backend order;
- received/effective dates and period use backend strings;
- limitation order remains DTO order;
- coverage blocks reference existing limitation DOM IDs;
- partial/missing/failed/gate-closed states remain distinct;
- no UI aggregation into overall completeness.

### 11.4. In-page navigation

Exact labels:

    Реквизиты
    Финансы
    Арбитраж

These are anchors, not hiding tabs. Enhanced activation focuses the destination
heading and announces the section in a polite live region. Native navigation
remains functional without JS.

## 12. CTA and actions

Primary CTA:

    Heading: Вам задолжали?
    Desktop copy:
      Запустите процесс взыскания прямо сейчас: создайте досудебную
      претензию онлайн!
    Button: Создать претензию
    Target: /claims?report_id={exact root.report_id}

The click uses a normal anchor, does not create a Claim, does not authenticate,
does not call provider and does not choose latest report. Claim creation
remains the existing explicit Claims form action.

Bottom actions keep exact order:

    Проверить другую компанию
    Подготовить претензию

Targets come from validated DTO and are cross-checked against / and exact root
report ID.

CTA states:

| State | Background | Foreground |
|---|---|---|
| Base | #EE5A2A | #111827 |
| Hover | #F36B3F | #111827 |
| Active | #E65327 | #111827 |
| Disabled/noninteractive fixture | #F6C6B5 | #5A2A1B |

Focus uses an inner 2px white separation ring and outer 3px #111827 ring.

## 13. Responsive contract

| Width | Layout |
|---:|---|
| >=1200px | flexible main + 320px rail + 32px gap; CTA sticky at top 24px |
| 768–1199px | single main column; fixed horizontal bottom CTA |
| 320–767px | single main column; fixed stacked bottom CTA |

Tablet/mobile:

- desktop supporting paragraph omitted;
- CTA has at least 44px touch target;
- padding-bottom includes env(safe-area-inset-bottom);
- an aria-hidden inert in-flow reserver mirrors fixed-bar wrapping and height;
- reserver contains no focusable element;
- content is not hidden underneath the fixed bar.

At every supported width:

- no page-wide horizontal scroll;
- long name/address/limitation wraps;
- local tables may scroll only inside their own container;
- controls remain reachable at 200% zoom;
- no fixed-height content clipping.

Reduced motion disables smooth scrolling, transitions and animation.

## 14. Nginx and navigation

Landing form uses full document navigation to /company/{inn}.

Nginx has two separate locations:

1. plain INN proxies Product API first, intercepts only a controlled 404 to the
   regular H1 SPA fallback and preserves all 409, 422, 429 and 5xx;
2. canonical slug proxies Product API without SPA fallback and preserves the
   selected H1/H2 status.

H2 assets are served before the generic asset rule from the durable store in
section 9, outside dist. The installer retains and verifies the asset closure
of exactly the current manifest plus its two recorded predecessors. Rebuilding
dist cannot remove this closure; an incomplete durable store blocks release.

deploy/nginx/product_api.conf and deploy/nginx/pork.su.conf must express the
same canonical production config.

Asset-first release order:

1. build SPA and dedicated H2 assets;
2. verify tracked manifest;
3. load and validate durable manifest history;
4. stage incoming H2 assets and manifest in the stable store;
5. select incoming current plus its two recorded predecessors;
6. verify every selected manifest, referenced hash and loopback URL;
7. atomically update the durable manifest-set;
8. only then deploy Product API containing the matching manifest;
9. run nonactive smoke;
10. leave H2 assignment disabled.

## 15. Accessibility

Required:

- one page h1 and logical h2 hierarchy;
- main, navigation and CTA aside landmarks;
- ordered breadcrumbs with aria-current=page;
- visible focus and keyboard-operable anchors;
- minimum 44px interactive size;
- polite enhancement/navigation live region;
- no tooltip-only content;
- overflow-wrap:anywhere for untrusted-length public strings;
- no color-only status;
- native anchors functional without JS;
- fixed CTA does not duplicate focusable controls;
- reduced-motion support;
- no focus trapping.

## 16. Privacy and security fixtures

Forbidden in HTML, embedded DTO, asset manifest, headers, logs and tests:

- raw payload or raw snapshot hash;
- provider headers/errors;
- secrets/HMAC/API keys;
- contact details;
- private arbitration identity/HMAC/key ID;
- internal subject/presentation IDs;
- narrative prompt/model output beyond saved public description;
- Webvisor/telemetry.

XSS fixtures include:

- </script><script>;
- <, >, &, <!--;
- quotes and backslashes;
- controls U+0000–U+001F;
- U+2028/U+2029;
- decomposed Unicode;
- unpaired surrogates;
- maximum and over-limit DTOs.

## 17. Migration and dependencies

Database migration: none.

DB schema and Alembic head 0017_company_card_v2_ai_narrative remain unchanged.

New runtime or npm dependency: none.

Existing Python standard library, Pydantic, browser crypto.subtle, React,
React DOM, Vite/Rollup, Node standard library and current pytest/Vitest tooling
are sufficient.

## 18. Acceptance criteria

Iteration is accepted only when:

1. One joined SELECT captures subject, assignment, exact pin and exact report
   for both H1 and H2 selection.
2. Assignment is neither re-read nor combined with staged/head/latest rows.
3. Unassigned staged/head/legacy H2 state leaves canonical H1 selected.
4. Exact assigned H1 is built from its exact pin/report even when it differs
   from active/latest H1.
5. Corrupt or concurrently changed assigned H1 fails closed without
   active/latest fallback.
6. The three old-digest scenarios in section 6.4 pass independently.
7. H2 assignment mutation remains forbidden.
8. Plain-INN full navigation preserves H1 redirect or missing-report SPA
   behavior.
9. Canonical selected errors never mount or select another factual app.
10. render_public_h1_html and H1 goldens remain byte-identical.
11. H2 actions use `/` and exact report-bound Claims paths.
12. Visible report ID and both Claims targets equal root.report_id.
13. H2 SSR contains all shell-owned facts and sections without chart renderers.
14. Exactly one script-safe DTO is embedded.
15. CSP nonce and security headers pass.
16. H2 is structurally indexable, but every iteration-22 H2 response remains
    noindex because current H2 pins are indexable=false.
17. React performs no factual GET and no whoami/auth request.
18. Parse/digest failure leaves SSR facts and head unchanged.
19. TypeScript parser preserves every valid integer token exactly; digest
    canonicalization never passes through JavaScript Number.
20. Shared vectors for 2^53-1, 2^53 and a larger valid integer match Python.
21. Dedicated bundle contains no Webvisor, Yandex, AuthProvider or H1 app.
22. Product-pinned manifest and dedicated Vite bytes match exactly.
23. Host release state retains and verifies current plus two predecessor
    manifests and every reachable asset.
24. New/incomplete host state fails before Product replacement.
25. Workflow static tests prove asset install/history validation precedes
    Product replacement.
26. CTA placement switches at exact 768/1200 boundaries and never overlaps
    content.
27. Visual matrix passes at 320/390/768/1024/1199/1200/1440 px.
28. Keyboard, touch, 200% zoom, safe-area and reduced-motion checks pass.
29. Product unit, Gateway regression, web lint/test/build, disposable
    PostgreSQL, nginx and deployment-contract checks pass.
30. git diff --check passes.
31. Independent code review has no blocker.
32. No migration, dependency, charts, assignment activation or production
    activation is introduced.

## 19. Risks

### Pre-22 staged pin digest

Correcting /company to / changes prerelease H2 projection bytes. Old staged
pins are immutable and may fail digest reproduction. Canonical selection
without assignment ignores such a staged pin and remains H1. Generic
`/public-h2` resolution of that staged pin fails closed under its existing
rules. An exact assignment to the old digest produces canonical HTTP 500
without H1 fallback. There is no rewrite or production activation; future
activation requires an explicit append-only republish.

### Python/React presentation drift

Mitigation: checked-in backend SSR fixture consumed by frontend before/after
takeover parity tests.

### Asset/API deploy skew and unseeded host

Mitigation: exact Product-packaged manifest identity, isolated verified Vite
artifact, atomic host manifest-set, current-plus-two retention, full stored and
loopback hash verification before Product replacement.

A new or incomplete production host intentionally cannot accept the release.
Initial/DR seeding is not inferred or automated in iteration 22; it is an
explicit iteration-25 prerequisite.

### Accidental H2 activation

Mitigation: assignment-only selector plus unchanged H2 CAS rejection and
default-off mutation/create settings.

### Fixed-bar overlap

Mitigation: same-layout inert reserver, breakpoint boundary tests and
real-browser matrix.

Open product questions: none.

## 21. Fresh DevFlow recovery pass after blocked correction

Recovery planning date: 2026-08-25.

This section is mandatory scope clarification after the previous DevFlow run
exhausted its single implementation-correction pass and ended `blocked`. The
uncommitted diff on `feat/iteration-22-company-card-v2-page-shell` is the
intentionally preserved recovery baseline. It must not be reset, cleaned or
replaced by a rewrite from scratch. The principal records `blocked ->
planning`; planner and reviewer remain read-only.

This is still iteration 22. It does not start iteration 23 or add chart
renderers, production activation, deploy, migration, dependency, live
DataNewton, production database or AI work.

### 21.1. Fixed recovery gates

| Gate | Mandatory recovery result |
|---|---|
| Full frontend regression | Landing submits through one full-document handoff to `/company/{inn}`; no factual SPA read/create/status call; full Vitest is green |
| TypeScript contract | Complete closed recursive validation equivalent to `public_h2_models.py`, including all F1-F5/A1-A5 leaves and semantics |
| SSR/React parity | One sanitized shared fixture proves ordered section, field, text, link, coverage and limitation parity before/after takeover |
| Responsive CTA | Mobile stacked, tablet horizontal fixed, desktop 320px sticky rail at exact 768/1200 boundaries |
| Document selector | One joined assignment-aware SELECT, exact assigned H1/H2 binding, fail-closed corruption and no DML |
| Old digest | Three independent database fixtures prove unassigned canonical H1, generic H2 500 and assigned canonical H2 500 |
| Disposable PostgreSQL | Iteration-22 runner independently executes exact Targeted/Full suites and validates its own JUnit/counts |
| Asset release | Executable temporary-store rotation, failure, identity, hash, reachability and workflow-order tests replace source-string-only checks |
| Browser evidence | All five synthetic profiles at 320/390/768/1024/1199/1200/1440 pass without production/network/provider/AI access |

### 21.2. Full TypeScript contract gate

Frontend validates the complete DTO before React mount. The validator must
enforce exact object keys, required/optional/nullability rules, scalar types,
integer bounds through `BigInt`, fixed tuples, bounded arrays, literals,
ordering, NFC/nonblank/length constraints, identifiers, dates/UTC, paths,
digests and canonical Decimal strings. No numeric token may pass through
JavaScript `Number` for validation, canonicalization or digesting.

Validation includes owner-share co-occurrence, requisites ordering, narrative
bounds and uniqueness, finance unit/arithmetic rules, all F1-F5 shapes and
all A1-A5 fields/counts/scopes/caps, exact block and coverage order, source
order, report/capability/indexability bindings, action/breadcrumb/CTA/report
bindings, limitation uniqueness and coverage-to-limitation links, and
coverage state versus block presence. Projection digest is checked last.

The 524288-byte canonical DTO cap and 786432-byte embedded-state cap are
separate. Unknown fields and malformed data in currently unrendered blocks
fail before mount. Python and TypeScript consume the same sanitized valid DTO
and mutation corpus and must agree on every accept/reject case; semantic
mutations use recomputed digests so they do not merely test digest rejection.

### 21.3. Factual shell and parity gate

SSR and React render the same shell-owned factual surface: breadcrumbs;
status/date; display, legal full and short names; INN/OGRN/KPP; registration
and dissolution dates; legal form; address and inaccuracy; charter capital;
tax modes; primary/additional activities; managers; owners; employees; tax
authority; narrative; F1-F5 and A1-A5 coverage; coverage-to-limitation links;
source dataset, received/effective dates and periods; limitations; actions;
visible report ID and both exact Claims links.

Finance and arbitration remain semantic coverage shells. No chart, SVG,
canvas, geometry interpretation, trend, verdict or recommendation is added.
Navigation uses only `#requisites`, `#finance`, `#arbitration` and other real
shell IDs; it is never derived directly from chart-level `block_order` IDs.
The unavailable-status fallback is fixed human text, not `projection_scope`.

Both user-approved lower actions and the primary claim CTA use the orange
accent contract. SSR and React must have identical action order, classes and
hrefs. A fixed DTO, asset manifest, nonce and expected document form a shared
sanitized fixture. Tests compare ordered IDs, `data-h2-field` values, visible
facts, report/Claims bindings and coverage/limitation associations before and
after takeover. Bootstrap performs no fetch, XHR, beacon, auth, provider,
Gateway or AI request and leaves the server-owned head unchanged.

### 21.4. Responsive CTA and accessibility gate

Breakpoints are exact:

- `max-width: 767px`: one-column stacked fixed-bottom CTA;
- `768px..1199px`: horizontal fixed-bottom CTA;
- `min-width: 1200px`: 320px sticky desktop rail.

There is exactly one focusable primary CTA. Its same-layout reserver is inert,
hidden from accessibility APIs and contains no focusable descendant. Targets
are at least 44x44 CSS pixels; focus is visible; headings/landmarks are valid;
in-page destinations can be focused and announced; safe-area, long wrapping,
200% zoom and reduced motion are supported. The page has no horizontal scroll
or CTA/content overlap.

### 21.5. Exact persistence and HTTP gate

Canonical selection performs one joined assignment-aware SELECT for subject,
assignment, exact pin and exact report and never rereads assignment. Required
independent cases are:

1. no assignment plus staged old-digest H2 -> canonical H1;
2. staged old-digest H2 through generic public-H2 -> 500;
3. exact assigned old-digest H2 through canonical document -> noindex 500,
   without H1 fallback;
4. exact assigned H1 differing from active/latest -> assigned pin/report;
5. corrupt or concurrently changed assigned H1 -> 500, no fallback;
6. injected exact H2 assignment -> H2 noindex document;
7. incomplete/cross-subject/unknown assignment -> 500;
8. pending/failed/not-eligible and SQL-unavailable retain the approved 409/503
   class instead of collapsing into an unrelated 500;
9. canonical GET/HEAD execute no DML and create no assignment, pin,
   presentation, narrative or activation row;
10. H1 renderer output remains byte-identical.

The startup-validated H2 asset manifest is injected as the immutable pinned
object; a request does not reread package resources. Python model semantics
needed by the public contract are tested alongside TypeScript parity.

### 21.6. Disposable PostgreSQL gate

`run-iteration22-postgres-tests.ps1` is self-contained and does not delegate
execution to an earlier iteration. It preserves local-image-only,
`--pull=never`, loopback, tmpfs, generated credentials, repository `.env`
refusal, default-off provider/AI/Gateway/H2 switches, current-worktree import
proof, disposable-only Alembic upgrade and exact labeled-container cleanup.

Targeted mode executes exactly the H1 reads, H2 reads, public documents,
presentations and Claims handoff integration files. Full mode executes all
`services/product_api/tests`. Each mode creates and validates its own fresh
JUnit with tests greater than zero and zero failures, errors and skips.

### 21.7. Executable release gate

Temporary-store tests exercise the same release-decision implementation used
by the installer. They cover four sequential rotations, exact current plus
two retention, idempotency, atomic pointer preservation on injected failure,
immutable-name collision, fresh/incomplete host, malformed history, missing
manifest/asset, hash mismatch, candidate/Product mismatch, unreachable asset,
response-byte SHA-256 for every retained URL and workflow order before Product
replacement. Tests use only temporary paths and a loopback fixture server;
they never touch `/var/lib`, production nginx, DNS or deploy.

### 21.8. Recovery completion condition

Iteration 22 remains blocked unless all gates above, full Product/Gateway/web
regressions, both PostgreSQL modes, executable release checks and all 35
browser cells pass; generated `.tmp`, `dist*`, JUnit, cache and node_modules
paths are absent from staged content; privacy/secret and changed-file audits
are clean; `git diff --check` passes; and independent code review has no
blocking or substantial finding. Iteration 23 remains blocked until iteration
22 is merged and reconciled.

## 22. Separate blocker-only continuation after the second blocked run

Continuation planning date: 2026-08-25.

This human-authorized continuation retains the full dirty
`feat/iteration-22-company-card-v2-page-shell` worktree as its recovery
baseline. It must not be reset, cleaned, rewritten from scratch or moved to a
new branch. Scope is limited to the five unresolved completion gates and the
TypeScript build failure. Landing handoff, strict-JSON prototype protection,
startup manifest injection, CTA styling/breakpoints and nginx routing remain
regression-only.

This remains iteration 22. It does not authorize iteration 23, chart
rendering, H2 assignment activation, rollout/deploy, live provider/Gateway/AI,
production database, migration, dependency or Claims-contract work.

### 22.1. Exhaustive TypeScript/Python contract parity

`parseCompanyPublicH2` validates the complete serialized current
`CompanyPublicH2Response` before digest verification and React mount. The
authority is the full current `public_h2_models.py`, including all common,
F1-F5 and A1-A5 model families and its exact existing semantics. TypeScript
must neither omit Python rules nor invent stricter rules for plain Python
`str`, independently nullable fields or arbitration relations absent from the
Python model.

Validation is split into three layers: `contractSchema.ts` owns exact keys,
wire types, nullability, literals, regexes, bounds, tuples and immutable typed
DTO construction; `contractSemantics.ts` owns Decimal arithmetic, ordering,
co-occurrence, mode/state shapes and root bindings; `contract.ts` owns strict
parse, the full 524288-byte canonical DTO cap, schema, semantics, digest-last
verification and deep freeze. The 786432-byte embedded-state cap remains
separate.

Integer tokens never pass through JavaScript `Number`; bounds use `BigInt`.
A sound branded/class-based or exact-shape discriminator rejects raw JSON
integer-wrapper spoofing. Prototype-dangerous keys remain rejected.
Public-H2 strings/keys must already be NFC, while generic CJSON remains able
to normalize its own vectors. Unicode length uses scalar values. TS2352 is
fixed through real narrowing, never casts, suppression or compiler relaxation.

Canonical Decimal operations use sign/coefficient/scale and `BigInt`. Finance
money enforces rub = source-thousand * 1000 and million = source-thousand /
1000; axes include zero and detail scope follows Python count/cap rules. F1
validates all leaves, segment order and arithmetic. F2 validates the exact
seven-year window and three Python state shapes. F3 validates seven years,
optional leaves/tuples and summary IDs. F4 validates the exact Python
`per_100` equivalence without strengthening denominator-unavailable. F5
validates seven years, nine ordered metric rows and cell years.

A1-A5 recursively validate every arbitration summary, safe opponent/case,
role detail, bar, geometry, currency and opponent-group field, literal, bound,
nullable value and collection cap. TypeScript does not invent ordering,
arithmetic, calendar, URL or identity relations absent from Python.

Root semantics cover exact block/coverage order, one-to-three ordered sources,
version/capability/indexability, action/breadcrumb/canonical/Claims bindings,
unique limitations, coverage links and block-presence equivalence. Python is
strengthened to bind canonical-path INN to identity INN, as already required
by the public contract.

### 22.2. Dense shared mutation corpus

`company_public_h2_contract_v1.json` contains one sanitized digest-valid v3
DTO with every F1-F5/A1-A5 block non-null and every optional model family
represented. A companion cases file contains a closed constraint-ID registry
and JSON-pointer `add/remove/replace/swap` mutations with raw strict-JSON patch
payloads.

Python and TypeScript apply the same mutations. Every schema/semantic case
except explicit digest negatives removes the prior digest, recomputes it
natively and reinserts it. Both suites assert exact executed-ID equality with
the registry, expected outcomes and zero skips/xfails. The corpus covers every
model family and declared rule plus legal nullable/boundary accept cases and
one-step-outside rejects. Python validates strict JSON to prevent scalar
coercion from producing false parity.

### 22.3. Successful byte-exact SSR/React parity

The dense DTO drives fixed `company_public_h2_ssr_v1.json` and an actual
byte-exact `company_public_h2_ssr_v1.html` with fixed manifest, nonce and
robots. Backend tests regenerate the document and compare exact bytes.

SSR and React render the same deterministic surface: fixed status fallback,
all approved requisites/metadata, narrative, all 13 coverage rows and ordered
coverage counts/scope/limitation targets, sources, limitations, breadcrumbs,
exact three in-page links, actions, report ID and both Claims links. No chart
values, geometry, SVG, canvas, trend, total, verdict or recommendation appear.

Shared parity markers produce ordered records for section, field, element,
text, href, class, coverage state/counts and limitation targets. A successful
bootstrap test loads exact SSR HTML, snapshots head/surface, installs failing
fetch/XHR/beacon spies, verifies the DTO, performs a committed takeover and
requires unchanged head plus exact before/after vectors and visible text.
React returns direct root children, not a grid-changing wrapper. Any failure
keeps SSR/head intact and changes only the live-region message.

The missing-status text is exactly `Статус не указан в отчёте`. Enhanced
anchors focus/announce their headings; native SSR anchors still work without
JavaScript.

### 22.4. Real PostgreSQL assignment matrix

Disposable PostgreSQL creates real committed rows and calls actual
canonical/generic endpoints in separate request sessions. It covers assigned
H1 versus different active/latest H1, test-injected valid H2, incomplete/
unknown/corrupt bindings, corrupt assigned H1/H2 and three independent old-
digest cases: unassigned canonical H1, generic H2 500 and assigned canonical
noindex 500 without fallback. H2 assignment exists only in disposable
fixtures; production assignment remains closed.

SQLAlchemy instrumentation proves one assignment-aware joined SELECT and no
second assignment read. Assigned-H1 GET/HEAD execute exactly that SELECT;
exact H2 may perform only approved exact artifact reads. Logs contain no
DML/DDL; before/after counts for every Product table and relevant row bytes
are equal. Assigned-H1 body remains byte-identical to the H1 renderer/golden.
Exact-H2 SQL errors remain 503 and pending/failed/not-eligible remain their
approved 409 class.

### 22.5. Actual shared installer path

`company_public_h2_release.py` becomes the single strict dependency-free
release implementation/CLI for manifest and manifest-set parsing, source
graph, candidate/Product identity, immutable collision-safe copy, rotation,
stored and loopback hashes, fsync and atomic pointer replacement. The shell
keeps resolved production-root/host preflight and lock, then delegates to this
CLI without duplicating release decisions.

Temporary tests invoke the same path against a three-manifest store and
loopback asset server. They perform four rotations plus idempotency, validate
current-plus-two identities and every stored/response hash, and cover fresh/
one-predecessor/malformed history, missing/wrong manifest or asset, source
graph/candidate identity mismatch, unreachable/altered response, immutable
collision and failure at each pre-pointer phase. Every failure preserves the
prior pointer bytes. Workflow order proves candidate image build/extraction
precedes install and every release gate precedes Product replacement. Host
seeding remains iteration 25.

### 22.6. Five valid profiles and 35 real-browser cells

The loopback fixture server exposes `saved-artifact`,
`deterministic-fallback`, `gate-closed`, `partial-long-limitations` and
`long-public-strings`. Each profile is rebuilt from sanitized data, receives a
fresh digest and passes full Python and TypeScript validation. Saved/fallback
modes differ; block/coverage/limitation changes stay consistent; repository
and Product import roots must resolve inside the current worktree.

A deterministic no-download browser harness uses an already-local
Chrome/Edge/Chromium through CDP or the repository-supported Codex browser
client with a checked-in pure probe. It executes five profiles at
320/390/768/1024/1199/1200/1440 and writes ignored PNG/JSON evidence under
`.tmp/iteration22-visual/`.

Every cell requires HTTP 200, successful takeover, unchanged head, no overflow
or overlap, exact links, one primary CTA, zero focusable reserver descendants,
44px targets, correct breakpoint layout, all coverage/limitation targets, no
chart art, zero forbidden requests and no console error. At 390/1024/1440 for
each profile it additionally checks keyboard anchor focus/announcement, 200%
zoom and deterministic reduced motion. Aggregate evidence reports exactly 35
executed/passed and zero failed/skipped cells.

### 22.7. Completion gate

Iteration 22 remains blocked until TypeScript builds without suppression; the
dense corpus proves complete Python/TS parity; exact SSR/React takeover parity
passes; the real PostgreSQL matrix and one-SELECT/no-DML/row-count/H1-byte
gates pass Targeted and Full; the actual installer matrix passes; all five
profiles validate and all 35 browser cells pass; closed regressions and full
repository checks are green; generated/private paths are absent from staged
content; `git diff --check` passes; and independent review has no blocking or
substantial finding. No commit/push is allowed before this gate. Iteration 23
remains blocked until merge and reconciliation.
