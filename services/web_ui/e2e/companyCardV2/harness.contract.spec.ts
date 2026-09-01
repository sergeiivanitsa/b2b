import { expect, test } from '@playwright/test'
import { assertResponsiveGeometry } from './harness'

const documentBody = `
  <main id="company-public-h2-root" style="width: 320px">
    <nav class="company-public-h2__breadcrumbs" aria-label="Хлебные крошки">
      <ol><li><a href="/" style="display: inline-flex; min-width: 44px; min-height: 44px; font-size: 12px">Главная</a></li></ol>
    </nav>
    <a id="regular-link" href="/regular" style="display: block; width: 44px; height: 44px">Обычная ссылка</a>
    <aside class="company-public-h2__cta" style="width: 120px; height: 44px"></aside>
    <div class="company-public-h2__cta-reserver"></div>
    <p class="company-public-h2__live"></p>
  </main>
`

test('keeps the compact breadcrumb link inside the 44px target gate', async ({ page }) => {
  await page.setContent(documentBody)

  const breadcrumbBox = await page.locator('.company-public-h2__breadcrumbs a').boundingBox()
  expect(breadcrumbBox?.width).toBeGreaterThanOrEqual(44)
  expect(breadcrumbBox?.height).toBeGreaterThanOrEqual(44)
  await assertResponsiveGeometry(page)

  await page.locator('.company-public-h2__breadcrumbs a').evaluate(element => {
    element.style.minWidth = '0'
    element.style.minHeight = '0'
    element.style.width = '20px'
    element.style.height = '20px'
  })
  await expect(assertResponsiveGeometry(page)).rejects.toThrow()
})
