import { afterEach, describe, expect, it, vi } from 'vitest'
import { bootstrapCompanyPublicH2, teardownCompanyPublicH2 } from './bootstrap'
import { collectCompanyPublicH2ParityVector } from './parityVector'
import sharedHtml from '../../../../shared/fixtures/company_public_h2_ssr_v1.html?raw'

const initialDocument = document.documentElement.innerHTML
const initialPath = window.location.pathname

function installFixture(): void {
  const fixture = new DOMParser().parseFromString(sharedHtml, 'text/html')
  document.head.innerHTML = fixture.head.innerHTML
  document.body.innerHTML = fixture.body.innerHTML
  window.history.replaceState({}, '', '/company/7701234567-dense-corpus')
}

function installIntersectionObserverHarness() {
  const observers: FakeIntersectionObserver[] = []
  class FakeIntersectionObserver {
    readonly callback: IntersectionObserverCallback
    readonly disconnect = vi.fn()
    constructor(callback: IntersectionObserverCallback) { this.callback = callback; observers.push(this) }
    observe = vi.fn()
    unobserve = vi.fn()
    takeRecords = vi.fn(() => [])
    root = null
    rootMargin = '0px'
    thresholds = []
  }
  vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver)
  return observers
}

afterEach(() => {
  teardownCompanyPublicH2(document)
  document.documentElement.innerHTML = initialDocument
  window.history.replaceState({}, '', initialPath)
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('bootstrapCompanyPublicH2', () => {
  it('fails closed without state and does not initiate a network request', async () => {
    const documentRef = document.implementation.createHTMLDocument('fixture')
    documentRef.body.innerHTML = '<main id="company-public-h2-root"><p class="company-public-h2__live" aria-live="polite"></p></main>'
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    expect(await bootstrapCompanyPublicH2(documentRef)).toBe(false)
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(documentRef.querySelector('.company-public-h2__live')?.textContent).toContain('недоступно')
  })

  it('takes over the exact SSR fixture synchronously with no network and stable head/vector', async () => {
    installFixture()
    const before = collectCompanyPublicH2ParityVector(document)
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    const xhrSpy = vi.spyOn(XMLHttpRequest.prototype, 'open')
    expect(await bootstrapCompanyPublicH2(document)).toBe(true)
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(xhrSpy).not.toHaveBeenCalled()
    expect(document.getElementById('company-public-h2-root')?.dataset.enhanced).toBe('true')
    expect(collectCompanyPublicH2ParityVector(document)).toBe(before)
    expect(document.title).toBe('Тестовое общество — проверка компании')
    expect(document.querySelector('meta[name="robots"]')?.getAttribute('content')).toBe('noindex,follow')
    expect(document.querySelectorAll('[data-h2-block]').length).toBe(5)
    expect(document.querySelectorAll('[data-h2-finance-article]').length).toBe(5)
  })

  it('preserves the SSR factual body when schema, semantic or digest validation fails', async () => {
    installFixture()
    const root = document.getElementById('company-public-h2-root')!
    const originalHeader = root.querySelector('#hero-status')?.textContent
    document.getElementById('company-public-h2-state')!.textContent = '{"contract_version":"company_public_h2_v1"}'
    expect(await bootstrapCompanyPublicH2(document)).toBe(false)
    expect(root.querySelector('#hero-status')?.textContent).toBe(originalHeader)
    expect(root.dataset.enhanced).toBeUndefined()
    expect(root.querySelector('.company-public-h2__live')?.textContent).toContain('недоступно')
  })

  it('does not create an observer when binding or SSR parity fails', async () => {
    installFixture()
    const created = vi.fn()
    class FakeIntersectionObserver { constructor(...args: unknown[]) { created(...args) } observe = vi.fn(); disconnect = vi.fn(); unobserve = vi.fn(); takeRecords = vi.fn(() => []); root = null; rootMargin = '0px'; thresholds = [] }
    vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver)
    document.getElementById('company-public-h2-root')!.dataset.reportId = '00000000-0000-4000-8000-000000000099'
    expect(await bootstrapCompanyPublicH2(document)).toBe(false)
    expect(created).not.toHaveBeenCalled()
    installFixture()
    document.getElementById('finance-f1')!.append(' SSR mismatch')
    expect(await bootstrapCompanyPublicH2(document)).toBe(false)
    expect(created).not.toHaveBeenCalled()
  })

  it('keeps factual page without an import when IntersectionObserver is unsupported', async () => {
    installFixture()
    vi.stubGlobal('IntersectionObserver', undefined)
    expect(await bootstrapCompanyPublicH2(document)).toBe(true)
    expect(document.querySelector('[data-h2-chart-mark]')).toBeNull()
    expect(document.querySelector('[role="status"]')?.textContent).toContain('не поддерживаются')
  })

  it('arms the lazy chart boundary only after observer intersection and disconnects it on teardown', async () => {
    installFixture()
    const observers = installIntersectionObserverHarness()
    expect(await bootstrapCompanyPublicH2(document)).toBe(true)
    expect(document.querySelector('[data-h2-chart-mark]')).toBeNull()
    observers[0].callback([{ isIntersecting: true } as IntersectionObserverEntry], observers[0] as unknown as IntersectionObserver)
    await vi.waitFor(() => expect(document.querySelector('[data-h2-chart-mark]')).toBeTruthy())
    teardownCompanyPublicH2(document)
    teardownCompanyPublicH2(document)
    expect(observers[0].disconnect).toHaveBeenCalledOnce()
  })

  it('announces a rejected dynamic chart import through the visible status region', async () => {
    installFixture()
    const observers = installIntersectionObserverHarness()
    const loadFinanceCharts = vi.fn(() => Promise.reject(new Error('chunk unavailable')))
    expect(await bootstrapCompanyPublicH2(document, crypto, loadFinanceCharts)).toBe(true)
    observers[0].callback([{ isIntersecting: true } as IntersectionObserverEntry], observers[0] as unknown as IntersectionObserver)
    await vi.waitFor(() => expect(document.querySelector('[role="status"]')?.textContent).toContain('Интерактивный график недоступен'))
    const status = document.querySelector<HTMLElement>('[role="status"]')!
    expect(status.hidden).toBe(false)
    expect(status.closest('[aria-hidden="true"]')).toBeNull()
    expect(getComputedStyle(status).display).not.toBe('none')
    expect(document.querySelector('[data-h2-chart-mark]')).toBeNull()
  })

  it('invalidates a pending chart import so it cannot mount into a later bootstrap', async () => {
    installFixture()
    const observers = installIntersectionObserverHarness()
    let resolveImport!: (module: typeof import('./FinanceCharts')) => void
    const pendingImport = new Promise<typeof import('./FinanceCharts')>(resolve => { resolveImport = resolve })
    const loadFinanceCharts = vi.fn(() => pendingImport)
    expect(await bootstrapCompanyPublicH2(document, crypto, loadFinanceCharts)).toBe(true)
    observers[0].callback([{ isIntersecting: true } as IntersectionObserverEntry], observers[0] as unknown as IntersectionObserver)
    expect(loadFinanceCharts).toHaveBeenCalledOnce()

    teardownCompanyPublicH2(document)
    installFixture()
    expect(await bootstrapCompanyPublicH2(document)).toBe(true)
    resolveImport(await import('./FinanceCharts'))
    await pendingImport
    await Promise.resolve()

    expect(document.querySelector('[data-h2-chart-mark]')).toBeNull()
    expect(document.querySelectorAll('[data-h2-finance-enhancement][aria-hidden="true"]')).toHaveLength(5)
    expect(document.querySelector('[role="status"]')?.textContent).toBe('')
  })
})
