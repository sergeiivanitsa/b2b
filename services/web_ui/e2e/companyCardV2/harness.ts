import { expect, type Page, type Request, type Route } from '@playwright/test'
import type { CompanyCardV2E2EContract, CompanyCardV2E2EProfile } from './manifest'

type ShiftRecord = Readonly<{ value: number; startTime: number; hadRecentInput: boolean; sources: readonly string[] }>
type BrowserShiftState = { cutoff: number; observer: PerformanceObserver; entries: PerformanceEntry[] }
type BrowserDiagnosticState = { observer: PerformanceObserver | null; lcpEntries: PerformanceEntry[] }

export type BrowserDiagnostics = Readonly<{
  lcp_supported: boolean
  largest_contentful_paint: Readonly<{ start_time_ms: number; size: number; element: string }> | null
  navigation: Readonly<{ dom_content_loaded_ms: number; load_event_ms: number; response_end_ms: number }> | null
  resources: readonly Readonly<{ duration_ms: number; initiator_type: string; path: string; response_end_ms: number; start_time_ms: number }>[]
}>

export type HeldDocument = Readonly<{
  entryPath: string
  externalRequests: readonly string[]
  sameOriginRequests: readonly string[]
  failedRequests: readonly string[]
  consoleErrors: readonly string[]
  runtimeErrors: readonly string[]
  releaseEntry: () => void
}>

function normalizedRootVector(): string {
  const root = document.getElementById('company-public-h2-root')
  if (!root) throw new Error('Company Public H2 root is absent')
  const normalize = (value: string | null | undefined) => (value ?? '').replace(/\s+/gu, ' ').trim()
  const renderedText = (element: Element) => normalize(element instanceof HTMLElement ? element.innerText : element.textContent)
  const marker = (element: Element) => ({
    tag: element.tagName,
    id: element.id,
    field: element.getAttribute('data-h2-field') ?? '',
    block: element.getAttribute('data-h2-block') ?? '',
    finance: element.getAttribute('data-h2-finance-article') ?? '',
    arbitration: element.getAttribute('data-h2-arbitration-article') ?? '',
    coverage: element.getAttribute('data-h2-coverage') ?? '',
    limitation: element.getAttribute('data-h2-limitation') ?? '',
    href: element.getAttribute('href') ?? '',
    text: renderedText(element),
  })
  return JSON.stringify({
    title: document.title,
    description: document.querySelector('meta[name="description"]')?.getAttribute('content') ?? '',
    robots: document.querySelector('meta[name="robots"]')?.getAttribute('content') ?? '',
    canonical: document.querySelector('link[rel="canonical"]')?.getAttribute('href') ?? '',
    text: renderedText(root),
    markers: [...root.querySelectorAll('[data-h2-field],[data-h2-block],[data-h2-finance-article],[data-h2-arbitration-article],[data-h2-coverage],[data-h2-limitation],a[href]')].map(marker),
  })
}

function sameOrigin(url: string, allowedOrigin: string): boolean {
  if (url.startsWith('data:') || url.startsWith('blob:')) return true
  try { return new URL(url).origin === allowedOrigin } catch { return false }
}

export async function openHeldCompanyCard(
  page: Page,
  contract: CompanyCardV2E2EContract,
  profile: CompanyCardV2E2EProfile,
): Promise<Readonly<{ held: HeldDocument; ssrVector: string }>> {
  const externalRequests: string[] = []
  const sameOriginRequests: string[] = []
  const failedRequests: string[] = []
  const consoleErrors: string[] = []
  const runtimeErrors: string[] = []
  let entryPath = ''
  let releaseEntry = (): void => { throw new Error('entry module was not intercepted') }
  let signalEntry = (): void => undefined
  const entryIntercepted = new Promise<void>(resolveEntry => { signalEntry = resolveEntry })
  const entryGate = new Promise<void>(resolveEntry => { releaseEntry = resolveEntry })

  await page.addInitScript(() => {
    const target = globalThis as typeof globalThis & { __companyCardV2DiagnosticState?: BrowserDiagnosticState }
    const lcpEntries: PerformanceEntry[] = []
    const observer = PerformanceObserver.supportedEntryTypes.includes('largest-contentful-paint')
      ? new PerformanceObserver(list => lcpEntries.push(...list.getEntries()))
      : null
    observer?.observe({ type: 'largest-contentful-paint', buffered: true })
    target.__companyCardV2DiagnosticState = { observer, lcpEntries }
  })

  page.on('console', message => { if (message.type() === 'error' || message.type() === 'assert') consoleErrors.push(message.text()) })
  page.on('pageerror', error => runtimeErrors.push(error.message))
  page.on('requestfailed', request => failedRequests.push(`${request.url()} ${request.failure()?.errorText ?? 'failed'}`))
  await page.route('**/*', async (route: Route, request: Request) => {
    if (!sameOrigin(request.url(), contract.baseUrl)) {
      externalRequests.push(request.url())
      await route.abort('blockedbyclient')
      return
    }
    const path = new URL(request.url()).pathname
    sameOriginRequests.push(path)
    if (entryPath === '' && request.resourceType() === 'script' && /^\/assets\/company-public-h2\.[A-Za-z0-9_-]{8,}\.js$/u.test(path)) {
      entryPath = path
      signalEntry()
      await entryGate
    }
    await route.continue()
  })

  const navigation = page.goto(profile.canonical_path, { waitUntil: 'commit' })
  await Promise.all([navigation, entryIntercepted])
  await page.locator('#company-public-h2-root').waitFor({ state: 'attached' })
  await page.waitForFunction(() => document.styleSheets.length > 0)
  await page.evaluate(() => document.fonts.ready)
  await expect(page.locator('#company-public-h2-root')).not.toHaveAttribute('data-enhanced', 'true')
  const ssrVector = await page.evaluate(normalizedRootVector)
  return { held: Object.freeze({ entryPath, externalRequests, sameOriginRequests, failedRequests, consoleErrors, runtimeErrors, releaseEntry }), ssrVector }
}

export async function collectBrowserDiagnostics(page: Page): Promise<BrowserDiagnostics> {
  return page.evaluate(() => {
    const target = globalThis as typeof globalThis & { __companyCardV2DiagnosticState?: BrowserDiagnosticState }
    const state = target.__companyCardV2DiagnosticState
    if (state === undefined) throw new Error('browser diagnostic observer was not armed')
    state.lcpEntries.push(...(state.observer?.takeRecords() ?? []))
    state.observer?.disconnect()
    const latest = state.lcpEntries.at(-1) as (PerformanceEntry & { element?: Element | null; size?: number }) | undefined
    const element = latest?.element
    const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined
    const resources = performance.getEntriesByType('resource').map(raw => {
      const entry = raw as PerformanceResourceTiming
      let path = '<invalid-url>'
      try { path = new URL(entry.name).pathname } catch { /* retain the closed marker */ }
      return {
        duration_ms: entry.duration,
        initiator_type: entry.initiatorType,
        path,
        response_end_ms: entry.responseEnd,
        start_time_ms: entry.startTime,
      }
    }).sort((left, right) => left.start_time_ms - right.start_time_ms || left.path.localeCompare(right.path))
    delete target.__companyCardV2DiagnosticState
    return {
      lcp_supported: state.observer !== null,
      largest_contentful_paint: latest === undefined ? null : {
        start_time_ms: latest.startTime,
        size: latest.size ?? 0,
        element: element instanceof Element ? `${element.tagName.toLowerCase()}#${element.id}.${[...element.classList].join('.')}` : 'unknown',
      },
      navigation: navigation === undefined ? null : {
        dom_content_loaded_ms: navigation.domContentLoadedEventEnd,
        load_event_ms: navigation.loadEventEnd,
        response_end_ms: navigation.responseEnd,
      },
      resources,
    }
  })
}

export async function armPostFontShiftObserver(page: Page): Promise<void> {
  await page.evaluate(() => {
    if (!PerformanceObserver.supportedEntryTypes.includes('layout-shift')) throw new Error('Layout Shift observer is unsupported')
    const target = globalThis as typeof globalThis & { __companyCardV2ShiftState?: BrowserShiftState }
    const entries: PerformanceEntry[] = []
    const cutoff = performance.now()
    const observer = new PerformanceObserver(list => entries.push(...list.getEntries()))
    observer.observe({ type: 'layout-shift', buffered: true })
    target.__companyCardV2ShiftState = { cutoff, observer, entries }
  })
}

export async function releaseAndHydrate(page: Page, held: HeldDocument): Promise<string> {
  held.releaseEntry()
  await expect(page.locator('#company-public-h2-root')).toHaveAttribute('data-enhanced', 'true')
  return page.evaluate(normalizedRootVector)
}

export async function triggerExpectedLazyHosts(page: Page, profile: CompanyCardV2E2EProfile): Promise<void> {
  for (const section of ['finance', 'arbitration'] as const) {
    const expected = profile.expected_lazy_hosts.filter(host => host.startsWith(section))
    if (expected.length === 0) continue
    await page.locator(`#${section}`).scrollIntoViewIfNeeded()
    if (profile.lazy_failure_chunk === section) {
      await expect(page.locator(`#${section} .company-public-h2__chart-status`).first()).toBeVisible()
      continue
    }
    for (const host of expected) {
      await expect(page.locator(`[data-h2-${section}-enhancement="${host}"] svg, [data-h2-${section}-enhancement="${host}"] [role="status"]`).first()).toBeVisible()
    }
  }
}

export async function finishPostFontShiftObserver(page: Page): Promise<readonly ShiftRecord[]> {
  await page.evaluate(() => new Promise<void>(resolveFrame => requestAnimationFrame(() => requestAnimationFrame(() => resolveFrame()))))
  return page.evaluate(() => {
    const target = globalThis as typeof globalThis & { __companyCardV2ShiftState?: BrowserShiftState }
    const state = target.__companyCardV2ShiftState
    if (!state) throw new Error('Layout Shift observer was not armed')
    state.entries.push(...state.observer.takeRecords())
    state.observer.disconnect()
    delete target.__companyCardV2ShiftState
    return state.entries.map(entry => {
      const shift = entry as PerformanceEntry & { value?: number; hadRecentInput?: boolean; sources?: { node?: Node | null }[] }
      return {
        value: shift.value ?? 0,
        startTime: shift.startTime,
        hadRecentInput: shift.hadRecentInput ?? false,
        sources: (shift.sources ?? []).map(source => {
          const node = source.node
          return node instanceof Element ? `${node.tagName.toLowerCase()}#${node.id}.${[...node.classList].join('.')}` : 'unknown'
        }),
      }
    }).filter(entry => entry.startTime >= state.cutoff && entry.value > 0)
  })
}

export async function assertVisibleContract(page: Page, profile: CompanyCardV2E2EProfile): Promise<void> {
  const root = page.locator('#company-public-h2-root')
  await expect(root).toHaveAttribute('data-contract', 'company_public_h2_v1')
  await expect(root).toHaveAttribute('data-report-id', profile.expected_report_id)
  await expect(root.locator('[data-h2-field="report_id"]')).toHaveText(profile.expected_report_id)
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', profile.canonical_path)
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', profile.expected_indexable ? 'index,follow' : 'noindex,follow')
  for (const expectedText of profile.expected_visible_text) await expect(root).toContainText(expectedText)
  const completeText = (await root.textContent()) ?? ''
  for (const forbiddenText of profile.forbidden_visible_text) expect(completeText).not.toContain(forbiddenText)
  await expect(root.locator('[data-h2-finance-article]')).toHaveCount(5)
  await expect(root.locator('[data-h2-arbitration-article]')).toHaveCount(5)
  const expectedClaimsPath = `/claims?report_id=${profile.expected_report_id}`
  await expect(root.locator(`a[href="${expectedClaimsPath}"]`)).toHaveCount(2)
}

export async function assertResponsiveGeometry(page: Page): Promise<void> {
  const result = await page.evaluate(async () => {
    const initialScroll = { x: window.scrollX, y: window.scrollY }
    const afterTwoFrames = () => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
    const root = document.getElementById('company-public-h2-root')
    if (root === null) throw new Error('responsive geometry requires the Company Card root and CTA')
    const cta = root.querySelector('.company-public-h2__cta')
    const reserver = root.querySelector('.company-public-h2__cta-reserver')
    const live = root.querySelector('.company-public-h2__live')
    if (cta === null) throw new Error('responsive geometry requires the Company Card root and CTA')
    window.scrollTo(0, document.documentElement.scrollHeight)
    await afterTwoFrames()
    const ctaRect = cta?.getBoundingClientRect()
    const ctaPosition = getComputedStyle(cta).position
    const factualChildren = [...root.children].filter(item => item !== cta && item !== reserver && item !== live && getComputedStyle(item).display !== 'none')
    const overlaps = ctaPosition === 'sticky' && ctaRect ? factualChildren.filter(item => {
      const box = item.getBoundingClientRect()
      return ctaRect.left < box.right && ctaRect.right > box.left && ctaRect.top < box.bottom && ctaRect.bottom > box.top
    }).map(item => item.id || item.className) : []
    const factualBottom = factualChildren.reduce((bottom, item) => Math.max(bottom, item.getBoundingClientRect().bottom), Number.NEGATIVE_INFINITY)
    const clientWidth = document.documentElement.clientWidth
    const isLocallyContained = (element: Element) => {
      let ancestor = element.parentElement
      while (ancestor !== null && ancestor !== document.documentElement) {
        const overflow = getComputedStyle(ancestor).overflowX
        if (['auto', 'scroll'].includes(overflow)) {
          const box = ancestor.getBoundingClientRect()
          if (box.left >= -0.5 && box.right <= clientWidth + 0.5) return true
        }
        ancestor = ancestor.parentElement
      }
      return false
    }
    const offenders = [...document.body.querySelectorAll<HTMLElement>('*')].flatMap(element => {
      const box = element.getBoundingClientRect()
      if (box.width === 0 || box.height === 0 || (box.left >= -0.5 && box.right <= clientWidth + 0.5) || isLocallyContained(element)) return []
      const identity = `${element.tagName.toLowerCase()}${element.id === '' ? '' : `#${element.id}`}${[...element.classList].map(name => `.${name}`).join('')}`
      return [{ identity, left: box.left, right: box.right, scrollWidth: element.scrollWidth, clientWidth: element.clientWidth }]
    }).sort((left, right) => right.right - left.right || left.left - right.left).slice(0, 20)
    const targets = [...(root?.querySelectorAll<HTMLElement>('a[href],button,[role="button"]') ?? [])].map(item => {
      const box = item.getBoundingClientRect()
      const svgMark = item instanceof SVGRectElement && item.matches('[data-h2-chart-mark],[data-h2-arbitration-chart-mark]')
      return {
        width: box.width,
        height: box.height,
        declaredWidth: svgMark ? item.width.baseVal.value : null,
        declaredHeight: svgMark ? item.height.baseVal.value : null,
        svgMark,
        label: item.getAttribute('aria-label') ?? item.textContent?.trim().slice(0, 40) ?? '',
      }
    })
    const result = {
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth,
      ctaPosition,
      ctaInside: ctaRect !== undefined && ctaRect.left >= -0.5 && ctaRect.right <= clientWidth + 0.5 && ctaRect.top >= -0.5 && ctaRect.bottom <= window.innerHeight + 0.5,
      fixedClearance: ctaPosition !== 'fixed' || (ctaRect !== undefined && factualBottom <= ctaRect.top + 0.5),
      offenders,
      overlaps,
      targets,
    }
    window.scrollTo(initialScroll.x, initialScroll.y)
    await afterTwoFrames()
    return result
  })
  expect(result.scrollWidth, JSON.stringify(result.offenders, null, 2)).toBeLessThanOrEqual(result.clientWidth)
  expect(result.ctaInside).toBe(true)
  expect(result.fixedClearance, `fixed CTA obscures final factual content at max scroll; position=${result.ctaPosition}`).toBe(true)
  expect(result.overlaps).toEqual([])
  expect(result.targets.length).toBeGreaterThan(0)
  for (const target of result.targets) {
    if (target.svgMark) {
      expect(target.declaredWidth, target.label).toBeGreaterThanOrEqual(44)
      expect(target.declaredHeight, target.label).toBeGreaterThanOrEqual(44)
      // SVG transforms can report the declared 44px target a few 1/32768 CSS
      // pixels short; the epsilon remains much smaller than one device pixel.
      expect(target.width, target.label).toBeGreaterThanOrEqual(44 - 1 / 1024)
      expect(target.height, target.label).toBeGreaterThanOrEqual(44 - 1 / 1024)
    } else {
      expect(target.width, target.label).toBeGreaterThanOrEqual(44)
      expect(target.height, target.label).toBeGreaterThanOrEqual(44)
    }
  }
}
