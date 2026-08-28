/* global process */
import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Browser, type Page } from '@playwright/test'
import {
  CORE_PROFILE_IDS, CORE_WIDTHS, loadCompanyCardV2E2EContract,
  type CompanyCardV2E2EProfile,
} from './manifest'
import {
  armPostFontShiftObserver, assertResponsiveGeometry, assertVisibleContract, collectBrowserDiagnostics,
  finishPostFontShiftObserver, openHeldCompanyCard, releaseAndHydrate,
  triggerExpectedLazyHosts,
} from './harness'

const contract = loadCompanyCardV2E2EContract(process.env)
const coreProfiles = CORE_PROFILE_IDS.map(profileId => contract.profiles.find(profile => profile.profile_id === profileId)!)
const lazyFailureProfile = contract.profiles.find(profile => profile.profile_id === 'lazy_failure_v1')!

function profileTitle(profile: CompanyCardV2E2EProfile): string { return profile.profile_id.replaceAll('_', ' ') }

async function waitForStableFullPageLayout(page: Page): Promise<void> {
  await page.evaluate(async () => {
    const root = document.getElementById('company-public-h2-root')
    if (root === null) throw new Error('full-page layout root is absent')
    let previous = ''
    let stableSamples = 0
    const deadline = performance.now() + 10_000
    while (performance.now() < deadline) {
      await new Promise<void>(resolve => requestAnimationFrame(() => resolve()))
      const current = `${document.documentElement.scrollHeight}:${root.scrollHeight}`
      stableSamples = current === previous ? stableSamples + 1 : 0
      if (stableSamples >= 4) return
      previous = current
    }
    throw new Error('full-page layout height did not stabilize')
  })
}

async function runHeldCore(page: Page, profile: CompanyCardV2E2EProfile): Promise<void> {
  const scriptRequests: string[] = []
  const documentRequests: string[] = []
  page.on('request', request => {
    if (request.resourceType() === 'script') scriptRequests.push(new URL(request.url()).pathname)
    if (request.resourceType() === 'document') documentRequests.push(new URL(request.url()).pathname)
  })
  const { held, ssrVector } = await openHeldCompanyCard(page, contract, profile)
  await assertVisibleContract(page, profile)
  expect(scriptRequests).toEqual([held.entryPath])
  await armPostFontShiftObserver(page)
  const reactVector = await releaseAndHydrate(page, held)
  expect(reactVector).toBe(ssrVector)
  expect(scriptRequests).toEqual([held.entryPath])
  await triggerExpectedLazyHosts(page, profile)
  await assertVisibleContract(page, profile)
  await assertResponsiveGeometry(page)
  await waitForStableFullPageLayout(page)
  expect(await finishPostFontShiftObserver(page)).toEqual([])
  expect(documentRequests.filter(path => path === profile.canonical_path)).toHaveLength(1)
  expect(held.externalRequests).toEqual([])
  expect(held.sameOriginRequests.filter(path => path !== profile.canonical_path && path !== '/favicon.ico' && !/^\/assets\/company-public-h2\.[A-Za-z0-9_-]{8,}\.(?:js|css)$/u.test(path))).toEqual([])
  expect(held.failedRequests).toEqual([])
  expect(held.consoleErrors).toEqual([])
  expect(held.runtimeErrors).toEqual([])
  expect(scriptRequests.filter(path => path !== held.entryPath).length).toBeGreaterThan(0)
}

for (const profile of coreProfiles) {
  test.describe(profileTitle(profile), () => {
    for (const width of CORE_WIDTHS) {
      test(`SSR, hydration, lazy parity and visual at ${width}px`, async ({ page }, testInfo) => {
        await page.setViewportSize({ width, height: 720 })
        await runHeldCore(page, profile)
        const diagnostics = await collectBrowserDiagnostics(page)
        await testInfo.attach('company-card-v2-browser-diagnostics.json', {
          body: Buffer.from(`${JSON.stringify(diagnostics, null, 2)}\n`, 'utf8'),
          contentType: 'application/json',
        })
        await expect(page).toHaveScreenshot(`${profile.profile_id}-${width}.png`, { fullPage: true, timeout: 30_000 })
      })
    }
  })
}

for (const width of CORE_WIDTHS) {
  test(`lazy failure preserves facts and Claims at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 720 })
    const { held, ssrVector } = await openHeldCompanyCard(page, contract, lazyFailureProfile)
    await assertVisibleContract(page, lazyFailureProfile)
    await armPostFontShiftObserver(page)
    expect(await releaseAndHydrate(page, held)).toBe(ssrVector)

    let failureInjected = false
    let failedChunkPath = ''
    await page.route('**/assets/company-public-h2.*.js', async route => {
      const path = new URL(route.request().url()).pathname
      if (!failureInjected && path !== held.entryPath) {
        failureInjected = true
        failedChunkPath = path
        await route.abort('failed')
      } else await route.fallback()
    })
    await triggerExpectedLazyHosts(page, lazyFailureProfile)
    expect(failureInjected).toBe(true)
    expect(failedChunkPath).toMatch(/^\/assets\/company-public-h2\.[A-Za-z0-9_-]{8,}\.js$/u)
    expect(failedChunkPath).not.toBe(held.entryPath)
    await expect(page.locator(`#${lazyFailureProfile.lazy_failure_chunk} .company-public-h2__chart-status`).first()).toContainText('фактические данные сохранены')
    await assertVisibleContract(page, lazyFailureProfile)
    await assertResponsiveGeometry(page)
    await waitForStableFullPageLayout(page)
    expect(await finishPostFontShiftObserver(page)).toEqual([])
    expect(held.externalRequests).toEqual([])
    expect(held.failedRequests).toEqual([`${new URL(failedChunkPath, contract.baseUrl).href} net::ERR_FAILED`])
    const cssRequest = /^\/assets\/company-public-h2\.[A-Za-z0-9_-]{8,}\.css$/u
    const javascriptRequest = /^\/assets\/company-public-h2\.[A-Za-z0-9_-]{8,}\.js$/u
    expect(held.sameOriginRequests.filter(path => path === lazyFailureProfile.canonical_path)).toHaveLength(1)
    expect(held.sameOriginRequests.filter(path => path === held.entryPath)).toHaveLength(1)
    expect(held.sameOriginRequests.filter(path => cssRequest.test(path))).toHaveLength(1)
    expect(held.sameOriginRequests.filter(path => path !== lazyFailureProfile.canonical_path && path !== '/favicon.ico' && !cssRequest.test(path) && !javascriptRequest.test(path))).toEqual([])
    expect(held.consoleErrors).toEqual(['Failed to load resource: net::ERR_FAILED'])
    expect(held.runtimeErrors).toEqual([])
  })
}

for (const profile of coreProfiles) {
  for (const width of [390, 1024, 1440] as const) {
    test(`keyboard/focus contract ${profile.profile_id} at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 720 })
      const { held } = await openHeldCompanyCard(page, contract, profile)
      held.releaseEntry()
      await expect(page.locator('#company-public-h2-root')).toHaveAttribute('data-enhanced', 'true')
      await triggerExpectedLazyHosts(page, profile)
      const focusable = page.locator([
        '#company-public-h2-root a[href]:visible',
        '#company-public-h2-root button:not([disabled]):visible',
        '#company-public-h2-root summary:visible',
        '#company-public-h2-root [tabindex]:not([tabindex="-1"]):visible',
      ].join(', '))
      const focusableCount = await focusable.count()
      expect(focusableCount).toBeGreaterThan(0)
      await page.evaluate(() => {
        document.body.tabIndex = -1
        document.body.focus()
        document.body.removeAttribute('tabindex')
        window.scrollTo(0, 0)
      })
      for (let index = 0; index < focusableCount; index += 1) {
        await page.keyboard.press('Tab')
        await expect(focusable.nth(index), `tab stop ${index + 1} must follow factual DOM order`).toBeFocused()
      }
      const requisites = page.locator('#in-page-navigation a[href="#requisites"]')
      await requisites.focus()
      await expect(requisites).toBeFocused()
      await requisites.press('Enter')
      await expect(page.locator('#requisites')).toBeFocused()
      await expect(page.locator('.company-public-h2__live')).toContainText('Реквизиты')
      expect(new URL(page.url()).hash).toBe('#requisites')
      const cta = page.locator('.company-public-h2__cta a')
      await cta.focus()
      await expect(cta).toBeFocused()
      const focusStyle = await cta.evaluate(element => {
        const style = getComputedStyle(element)
        return { outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth }
      })
      expect(focusStyle.outlineStyle).not.toBe('none')
      expect(Number.parseFloat(focusStyle.outlineWidth)).toBeGreaterThanOrEqual(3)
      expect(held.externalRequests).toEqual([])
    })
  }
}

async function newIsolatedPage(browser: Browser, profile: CompanyCardV2E2EProfile, options: Parameters<Browser['newContext']>[0]): Promise<Readonly<{ page: Page; close: () => Promise<void> }>> {
  const context = await browser.newContext({ baseURL: contract.baseUrl, locale: 'ru-RU', timezoneId: 'UTC', colorScheme: 'light', serviceWorkers: 'block', ...options })
  const page = await context.newPage()
  const close = async () => context.close()
  return { page, close }
}

for (const profile of coreProfiles) {
  for (const width of [390, 768] as const) {
    test(`real touch disclosure ${profile.profile_id} at ${width}px`, async ({ browser }) => {
      const isolated = await newIsolatedPage(browser, profile, { viewport: { width, height: 720 }, hasTouch: true, isMobile: true, deviceScaleFactor: 1 })
      try {
        const { held } = await openHeldCompanyCard(isolated.page, contract, profile)
        held.releaseEntry()
        await expect(isolated.page.locator('#company-public-h2-root')).toHaveAttribute('data-enhanced', 'true')
        await triggerExpectedLazyHosts(isolated.page, profile)
        const mark = isolated.page.locator('[data-h2-chart-mark],[data-h2-arbitration-chart-mark]').first()
        await expect(mark).toBeVisible()
        await mark.tap()
        await expect(isolated.page.getByRole('tooltip')).toBeVisible()
      } finally { await isolated.close() }
    })
  }
}

for (const profile of coreProfiles) {
  for (const physicalWidth of [390, 1024, 1440] as const) {
    test(`200 percent reflow ${profile.profile_id} at ${physicalWidth}px`, async ({ browser }) => {
      const isolated = await newIsolatedPage(browser, profile, { viewport: { width: Math.floor(physicalWidth / 2), height: 600 }, deviceScaleFactor: 2 })
      try {
        const { held } = await openHeldCompanyCard(isolated.page, contract, profile)
        held.releaseEntry()
        await expect(isolated.page.locator('#company-public-h2-root')).toHaveAttribute('data-enhanced', 'true')
        await assertResponsiveGeometry(isolated.page)
        expect(await isolated.page.evaluate(() => devicePixelRatio)).toBe(2)
      } finally { await isolated.close() }
    })
  }
}

for (const profile of [...coreProfiles, lazyFailureProfile]) {
  for (const width of [390, 1440] as const) {
    test(`reduced motion ${profile.profile_id} at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 720 })
      await page.emulateMedia({ reducedMotion: 'reduce' })
      const { held } = await openHeldCompanyCard(page, contract, profile)
      held.releaseEntry()
      await expect(page.locator('#company-public-h2-root')).toHaveAttribute('data-enhanced', 'true')
      const styles = await page.locator('#requisites').evaluate(element => {
        const style = getComputedStyle(element)
        return { animation: style.animationDuration, transition: style.transitionDuration, scroll: style.scrollBehavior }
      })
      expect(styles).toEqual({ animation: '0s', transition: '0s', scroll: 'auto' })
    })
  }
}

for (const viewport of [{ width: 390, height: 844 }, { width: 844, height: 390 }] as const) {
  test(`non-zero safe area ${viewport.width}x${viewport.height}`, async ({ browser }) => {
    const profile = coreProfiles[0]
    const isolated = await newIsolatedPage(browser, profile, { viewport, hasTouch: true, isMobile: true, deviceScaleFactor: 1 })
    try {
      const { held } = await openHeldCompanyCard(isolated.page, contract, profile)
      held.releaseEntry()
      await expect(isolated.page.locator('#company-public-h2-root')).toHaveAttribute('data-enhanced', 'true')
      await isolated.page.locator('#company-public-h2-root').evaluate(root => root.style.setProperty('--company-public-h2-safe-area-bottom', '32px'))
      const paddingBottom = await isolated.page.locator('.company-public-h2__cta').evaluate(element => Number.parseFloat(getComputedStyle(element).paddingBottom))
      expect(paddingBottom).toBe(44)
      await assertResponsiveGeometry(isolated.page)
    } finally { await isolated.close() }
  })
}

for (const profile of [coreProfiles[0], coreProfiles[2]]) {
  for (const width of [390, 1440] as const) {
    test(`JavaScript-disabled factual document ${profile.profile_id} at ${width}px`, async ({ browser }) => {
      const isolated = await newIsolatedPage(browser, profile, { viewport: { width, height: 720 }, javaScriptEnabled: false, deviceScaleFactor: 1 })
      try {
        const response = await isolated.page.goto(profile.canonical_path, { waitUntil: 'domcontentloaded' })
        expect(response?.status()).toBe(200)
        await assertVisibleContract(isolated.page, profile)
        await expect(isolated.page.locator('#company-public-h2-root')).not.toHaveAttribute('data-enhanced', 'true')
      } finally { await isolated.close() }
    })
  }
}

for (const width of [390, 1440] as const) {
  test(`axe and semantic gate after SSR and lazy enhancement at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 720 })
    const profile = coreProfiles[0]
    const { held } = await openHeldCompanyCard(page, contract, profile)
    const ssrViolations = (await new AxeBuilder({ page }).analyze()).violations
    expect(ssrViolations).toEqual([])
    held.releaseEntry()
    await expect(page.locator('#company-public-h2-root')).toHaveAttribute('data-enhanced', 'true')
    await triggerExpectedLazyHosts(page, profile)
    const enhancedViolations = (await new AxeBuilder({ page }).analyze()).violations
    expect(enhancedViolations).toEqual([])
  })
}

test('canonical, wrong-slug, crawler and exact Claims navigation remain closed', async ({ page, request }) => {
  const profile = coreProfiles[0]
  const wrongSlug = await request.get(profile.wrong_slug_path, { maxRedirects: 0 })
  expect(wrongSlug.status()).toBe(301)
  expect(new URL(wrongSlug.headers().location!, contract.baseUrl).pathname).toBe(profile.canonical_path)
  expect(wrongSlug.headers()['x-robots-tag']).toBe('noindex,follow')

  const robots = await request.get(contract.robotsPath)
  expect(robots.status()).toBe(200)
  expect(await robots.text()).toContain(new URL(contract.sitemapIndexPath, contract.baseUrl).href)
  const sitemap = await request.get(contract.sitemapIndexPath)
  expect(sitemap.status()).toBe(200)
  expect(sitemap.headers()['content-type']).toContain('xml')
  const sitemapIndex = await sitemap.text()
  expect(sitemapIndex).toContain('<sitemapindex')
  const sitemapLocations = [...sitemapIndex.matchAll(/<loc>([^<]+)<\/loc>/gu)].map(match => match[1])
  const sitemapDocuments = [sitemapIndex]
  if (sitemapIndex.includes('<sitemapindex')) {
    if (contract.profiles.some(candidate => candidate.expected_indexable)) expect(sitemapLocations.length).toBeGreaterThan(0)
    for (const location of sitemapLocations) {
      const url = new URL(location)
      expect(url.origin).toBe(contract.baseUrl)
      const chunk = await request.get(url.href)
      expect(chunk.status()).toBe(200)
      sitemapDocuments.push(await chunk.text())
    }
  }
  const completeSitemap = sitemapDocuments.join('\n')
  for (const candidate of contract.profiles) {
    const canonical = new URL(candidate.canonical_path, contract.baseUrl).href
    const occurrences = completeSitemap.split(canonical).length - 1
    expect(occurrences, candidate.profile_id).toBe(candidate.expected_indexable ? 1 : 0)
  }

  const canonicalGet = await request.get(profile.canonical_path)
  const canonicalHead = await request.head(profile.canonical_path)
  expect(canonicalGet.status()).toBe(200)
  expect(canonicalHead.status()).toBe(200)
  expect(await canonicalHead.body()).toHaveLength(0)
  expect(canonicalHead.headers()['x-robots-tag']).toBe(canonicalGet.headers()['x-robots-tag'])
  expect(canonicalHead.headers()['content-type']).toBe(canonicalGet.headers()['content-type'])

  const documents: string[] = []
  page.on('request', incoming => { if (incoming.resourceType() === 'document') documents.push(incoming.url()) })
  const { held } = await openHeldCompanyCard(page, contract, profile)
  held.releaseEntry()
  await expect(page.locator('#company-public-h2-root')).toHaveAttribute('data-enhanced', 'true')
  expect(await page.evaluate(async () => (await navigator.serviceWorker.getRegistrations()).length)).toBe(0)

  const claimsPath = `/claims?report_id=${profile.expected_report_id}`
  let intercepted: Readonly<{ method: string; resourceType: string; path: string }> | null = null
  await page.route(`**${claimsPath}`, async route => {
    const incoming = route.request()
    intercepted = { method: incoming.method(), resourceType: incoming.resourceType(), path: `${new URL(incoming.url()).pathname}${new URL(incoming.url()).search}` }
    await route.abort('blockedbyclient')
  })
  await page.locator('.company-public-h2__cta a').click().catch(() => undefined)
  await expect.poll(() => intercepted).not.toBeNull()
  expect(intercepted).toEqual({ method: 'GET', resourceType: 'document', path: claimsPath })
  expect(documents.filter(url => new URL(url).pathname === profile.canonical_path)).toHaveLength(1)
  expect(held.externalRequests).toEqual([])
})
