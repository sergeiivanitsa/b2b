# Итерация 15 — CompanyReport landing visual: implementation plan

## Изменяемые поверхности

| Поверхность | План |
|---|---|
| Landing markup | Заменить ClaimsBrand только на `/` scoped текстовым брендом, выстроить header, hero, четыре преимущества и карточку согласно макету. |
| Общая форма ИНН | Добавить только optional presentation props для placeholder, CTA и visual variant; не менять validation, normalization, loading, submit или callback. |
| Scoped styles | Заменить `.company-entry-*` правила белым canvas, responsive header/grid, оранжевыми CTA, timeline преимуществ и светло-серой карточкой. |
| Tests | Сохранить сценарий общего INN и единственного перехода; закрепить копирайт, доступные формы, отсутствие visual CompanyReport и root-route smoke assertion. |
| DevFlow artifacts | Отразить визуальный scope, review и готовность итерации 15. |

## Реализация

1. Оставить page-level coordinator (`inn`, `isNavigating`, `transitionStarted`)
   без изменений и передать одинаковый callback в обе формы.
2. Создать на landing семантичный текстовый бренд и центральную навигацию с
   точными visual labels «Как работаем», «Оплата», «Кейсы», «FAQ». Пока у этих
   пунктов нет утверждённых destinations, они остаются статичным текстом, а
   не получают ложные ссылки; новые routes или sections не добавляются.
3. Дать header и карточке формы разные presentation props; label остаётся
   доступным даже при визуальном скрытии в compact-варианте.
4. Использовать только scoped `.company-entry-*` CSS: ограниченные контейнеры,
   `min-width: 0`, responsive breakpoints и overflow-safe decoration.
5. Обновить тесты только в затронутой frontend области.

Точный copy из макета фиксируется в iteration specification: headline, hero
paragraph, четыре преимущества, card eyebrow/title/paragraph/reassurance,
оба placeholder и оба CTA. Реализация не заменяет эти строки альтернативным
маркетинговым текстом.

## Проверки

Сначала targeted:

```text
npm run test --prefix services/web_ui -- --run src/components/company-report/CompanyReportInnForm.test.tsx src/pages/CompanyLandingPage.test.tsx src/router/AppRouter.companyPage.test.tsx src/router/AppRouter.claims.test.tsx
```

Затем:

```text
npm run test --prefix services/web_ui
npm run build --prefix services/web_ui
git diff --check
```

Браузерная проверка: локальный `/` на 1440, 768 и 390 px, сравнение с
макетом и `scrollWidth <= clientWidth` на каждой ширине.

## Review focus

- Сохранение единого form coordinator и accessibility.
- Отсутствие изменений API, router, resolver, auth или lifecycle.
- Responsive overflow, читаемость и соответствие утверждённой композиции.
- Отсутствие случайного выхода за scope.
