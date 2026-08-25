function normalizedText(value: string | null): string {
  return (value ?? '').replace(/\r?\n/gu, '').trim()
}

/** Ordered semantic vector used by both SSR fixture and synchronous takeover. */
export function collectCompanyPublicH2ParityVector(documentRef: Document): string {
  const root = documentRef.getElementById('company-public-h2-root')
  const ids = ['hero-status', 'narrative', 'in-page-navigation', 'requisites', 'finance', 'arbitration', 'sources-limitations', 'neutral-actions']
  const vector = {
    head: [documentRef.title, documentRef.querySelector('meta[name="description"]')?.getAttribute('content') ?? '', documentRef.querySelector('meta[name="robots"]')?.getAttribute('content') ?? '', documentRef.querySelector('link[rel="canonical"]')?.getAttribute('href') ?? ''],
    root: [root?.getAttribute('data-contract') ?? '', root?.getAttribute('data-report-id') ?? '', normalizedText(root?.textContent ?? '')],
    sections: ids.map(id => [id, normalizedText(documentRef.getElementById(id)?.textContent ?? '')]),
    links: [...(root?.querySelectorAll('a') ?? [])].map(link => [link.getAttribute('href') ?? '', normalizedText(link.textContent)]),
    coverage: [...(root?.querySelectorAll('[data-h2-coverage]') ?? [])].map(item => [item.getAttribute('data-h2-coverage') ?? '', normalizedText(item.textContent)]),
    limitations: [...(root?.querySelectorAll('[data-h2-limitation]') ?? [])].map(item => [item.getAttribute('data-h2-limitation') ?? '', normalizedText(item.textContent)]),
  }
  return JSON.stringify(vector)
}
