# Итерация 14 — Единая точка входа CompanyReport

ID: 14
Slug: company-report-entry-flow

## Цель

Убрать штатный путь через 404 при проверке контрагента: пользователь вводит ИНН на `/`, существующий отчёт открывается по каноническому адресу, а новый безопасно ставится в существующую очередь и ожидается через поддерживаемый plain-INN resolver.

## Scope

- Первый экран `/`: header, навигация, hero, четыре преимущества и карточка проверки.
- Один переиспользуемый компонент формы ИНН для hero и компактной формы header.
- Единый контракт URL: canonical `/company/{inn}-{slug}` и resolver `/company/{inn}`.
- Расширение финального read API безопасным `canonical_path`.
- Обновление CompanyReport lifecycle и Claims backlink.
- Targeted и регрессионные тесты этого потока.

## Вне scope

- Остальная главная, кейсы, методика, policy/SEO rollout, публикации, миграции, инфраструктура, gateway, deploy и server configuration.

## Краткая UX-спецификация

- Header: `ClaimsBrand`, якорная навигация, `/claims`, `/login` и компактная форма ИНН. На узком экране элементы переносятся без скрытия действия.
- Hero: один ясный оффер проверки контрагента и четыре коротких преимущества. На desktop проверочная карточка находится рядом с текстом, на mobile — после него; CTA занимает всю доступную ширину.
- Карточка: label, поле ИНН, CTA и пояснение «10 или 12 цифр». Состояния validation/loading/API-error/success сообщаются через `aria-live`; focus, Enter и повтор после ошибки работают корректно.
- Формы используют один компонент и page-level coordinator. Пробельные символы удаляются, принимаются только 10 либо 12 ASCII-цифр; coordinator одновременно блокирует обе CTA и не даёт дважды начать navigation.

## Контракты

### API

Сохраняется существующий `POST /company-reports`: он ставит в очередь или переиспользует активную задачу и возвращает `202` с `report_id`, `pending` и `reused`. Первый экран его не вызывает: валидный submit переходит на plain resolver, чтобы existing final report не создавал новый run.

Финальный `GET /company-reports/{inn}` аддитивно получает `canonical_path`, например `/company/7700000000-ooo-vektor`.

Значение строится только из уже безопасных final counterparty facts через существующий pure `seo.canonical_path`; для failed/no-identity оно `null`. Оно не обозначает public SEO publication/indexability. DB snapshot, очередь, provider, scoring, signals и миграции не меняются.

### Routing

- Canonical route разбирается и продолжает показывать report; она не запускает новый POST и не редиректит по slug.
- Plain-INN route сначала делает один final read: final response ведёт на canonical, `409 report_pending` — к polling, и только verified `404 company_report_not_found` запускает один POST. После `202` (включая `reused`) resolver остаётся pending. Failed final не запускает POST автоматически, а предлагает явный retry.
- При прямом plain открытии без отчёта resolver создаёт/переиспользует один job только после verified 404. Некорректный ключ даёт controlled UI state, не запрос и не случайный 404.
- Это client-side redirect: nginx уже отдаёт plain route SPA fallback. HTTP redirect для него в этой итерации не добавляется; anonymous SSR canonical pages и SEO routing не изменяются.
- Если Claims знает только trusted INN, он намеренно ведёт на supported plain resolver. Если URL со slug известен, он должен быть canonical.
- `/` остаётся public: валидный submit попадает на protected resolver без API-вызова. `RequireAuth` сохраняет только строго проверенный company path в sessionStorage; после magic-link подтверждения он однократно восстанавливается. Внешние/некорректные target не сохраняются, а при недоступном storage используется обычный post-auth route.

## Acceptance criteria

1. Валидный ИНН из обеих форм один раз переходит на plain resolver; невалидный не запускает ни navigation, ни API.
2. Existing complete/partial report получает canonical URL; новый/active report корректно остаётся pending и после финализации уходит на canonical.
3. Plain route не создаёт redirect loop; canonical route продолжает работать.
4. Claims backlink больше не ведёт к неподдерживаемому маршруту.
5. Controlled auth/server/failed states не создают ложный success или дубликат; failed final повторяется только явным действием пользователя.
6. Изменения не затрагивают migration, deployment и SEO publication.
