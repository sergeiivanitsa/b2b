import { afterEach, describe, expect, it, vi } from 'vitest'
import { bootstrapCompanyPublicH2 } from './bootstrap'
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

afterEach(() => {
  document.documentElement.innerHTML = initialDocument
  window.history.replaceState({}, '', initialPath)
  vi.restoreAllMocks()
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
    expect(document.querySelectorAll('[data-h2-block]').length).toBe(10)
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
})
