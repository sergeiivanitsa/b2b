function normalizedText(value: string | null): string {
  return (value ?? '').replace(/\r?\n/gu, '').trim()
}

function factualRootText(root: HTMLElement | null): string {
  if (!root) return ''
  const clone = root.cloneNode(true) as HTMLElement
  clone.querySelectorAll('.company-public-h2__live, [data-h2-finance-enhancement], [data-h2-arbitration-enhancement]').forEach(node => node.remove())
  return normalizedText(clone.textContent)
}
function factualText(element: Element | null): string {
  if (!element) return ''
  const clone = element.cloneNode(true) as Element
  clone.querySelectorAll('.company-public-h2__live, [data-h2-finance-enhancement], [data-h2-arbitration-enhancement]').forEach(node => node.remove())
  return normalizedText(clone.textContent)
}
function semanticCell(item: Element): readonly unknown[] {
  return [
    item.tagName.toLowerCase(),
    item.getAttribute('scope') ?? '',
    normalizedText(item.textContent),
    [...item.querySelectorAll('[title]')].map(node => node.getAttribute('title') ?? ''),
  ]
}

/** Ordered semantic vector used by both SSR fixture and synchronous takeover. */
export function collectCompanyPublicH2ParityVector(documentRef: Document): string {
  const root = documentRef.getElementById('company-public-h2-root')
  const normalizeEnhancements = root?.dataset.enhanced === 'true'
  const ids = ['hero-status', 'narrative', 'in-page-navigation', 'requisites', 'finance', 'arbitration', 'sources-limitations', 'neutral-actions']
  const vector = {
    head: [documentRef.title, documentRef.querySelector('meta[name="description"]')?.getAttribute('content') ?? '', documentRef.querySelector('meta[name="robots"]')?.getAttribute('content') ?? '', documentRef.querySelector('link[rel="canonical"]')?.getAttribute('href') ?? ''],
    root: [root?.getAttribute('data-contract') ?? '', root?.getAttribute('data-report-id') ?? '', factualRootText(root)],
    sections: ids.map(id => [id, documentRef.getElementById(id)?.tagName.toLowerCase() ?? '', factualText(documentRef.getElementById(id))]),
    links: [...(root?.querySelectorAll('a') ?? [])].map(link => [link.getAttribute('href') ?? '', normalizedText(link.textContent)]),
    coverage: [...(root?.querySelectorAll('[data-h2-coverage]') ?? [])].map(item => [item.getAttribute('data-h2-coverage') ?? '', normalizedText(item.textContent)]),
    limitations: [...(root?.querySelectorAll('[data-h2-limitation]') ?? [])].map(item => [item.getAttribute('data-h2-limitation') ?? '', normalizedText(item.textContent)]),
    finance: [...(root?.querySelectorAll('[data-h2-finance-article]') ?? [])].map(article => [
      article.tagName.toLowerCase(), article.getAttribute('id') ?? '', article.getAttribute('data-h2-finance-article') ?? '',
      [...article.querySelectorAll('h3, h4')].map(item => [item.tagName.toLowerCase(), normalizedText(item.textContent)]),
      [...article.querySelectorAll('table, dl')].map(surface => [surface.tagName.toLowerCase(), surface.querySelector('caption')?.textContent?.trim() ?? '', [...surface.querySelectorAll('th, dt, dd, td')].map(semanticCell)]),
      [...article.querySelectorAll('[data-h2-finance-coverage]')].map(item => [item.getAttribute('data-h2-finance-coverage') ?? '', normalizedText(item.textContent)]),
      [...article.querySelectorAll('[data-h2-finance-advisory]')].map(item => [item.getAttribute('data-h2-finance-advisory') ?? '', normalizedText(item.textContent)]),
      [...article.querySelectorAll('[data-h2-finance-limitation]')].map(item => [item.getAttribute('data-h2-finance-limitation') ?? '', item.querySelector('a')?.getAttribute('href') ?? '', normalizedText(item.textContent)]),
      [...article.querySelectorAll('[data-h2-finance-enhancement]')].map(item => [item.tagName.toLowerCase(), item.getAttribute('data-h2-finance-enhancement') ?? '', normalizeEnhancements ? 'true' : item.getAttribute('aria-hidden') ?? '', normalizeEnhancements ? 0 : item.childElementCount, normalizeEnhancements ? '' : normalizedText(item.textContent)]),
    ]),
    arbitration: [...(root?.querySelectorAll('[data-h2-arbitration-article]') ?? [])].map(article => [
      article.tagName.toLowerCase(), article.getAttribute('id') ?? '', article.getAttribute('data-h2-arbitration-article') ?? '',
      [...article.querySelectorAll('h3, h4')].map(item => [item.tagName.toLowerCase(), normalizedText(item.textContent)]),
      [...article.querySelectorAll('table')].map(table => [table.querySelector('caption')?.textContent?.trim() ?? '', [...table.querySelectorAll('th, td')].map(semanticCell)]),
      [...article.querySelectorAll('ul, ol')].map(list => [list.tagName.toLowerCase(), [...list.children].map(item => [item.tagName.toLowerCase(), item.getAttribute('data-h2-case-public-id') ?? '', normalizedText(item.textContent)])]),
      [...article.querySelectorAll('[data-h2-case-public-id]')].map(item => [item.getAttribute('data-h2-case-public-id') ?? '', normalizedText(item.textContent)]),
      [...article.querySelectorAll('[data-h2-opponent-public-id]')].map(item => [item.getAttribute('data-h2-opponent-public-id') ?? '', normalizedText(item.textContent)]),
      [...article.querySelectorAll('[data-h2-arbitration-coverage]')].map(item => [item.getAttribute('data-h2-arbitration-coverage') ?? '', normalizedText(item.textContent)]),
      [...article.querySelectorAll('[data-h2-arbitration-scope], [data-h2-arbitration-detail-scope]')].map(item => [item.getAttribute('data-h2-arbitration-scope') ?? '', item.getAttribute('data-h2-arbitration-detail-scope') ?? '', normalizedText(item.textContent)]),
      [...article.querySelectorAll('[data-h2-arbitration-limitations]')].map(item => [item.getAttribute('data-h2-arbitration-limitations') ?? '', normalizedText(item.textContent)]),
      [...article.querySelectorAll('[data-h2-arbitration-limitation]')].map(item => [item.getAttribute('data-h2-arbitration-limitation') ?? '', item.querySelector('a')?.getAttribute('href') ?? '', normalizedText(item.textContent)]),
      [...article.querySelectorAll('[data-h2-arbitration-enhancement]')].map(item => [item.tagName.toLowerCase(), item.getAttribute('data-h2-arbitration-enhancement') ?? '', normalizeEnhancements ? 'true' : item.getAttribute('aria-hidden') ?? '', normalizeEnhancements ? 0 : item.childElementCount, normalizeEnhancements ? '' : normalizedText(item.textContent)]),
    ]),
  }
  return JSON.stringify(vector)
}
