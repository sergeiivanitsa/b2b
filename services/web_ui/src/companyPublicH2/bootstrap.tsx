import { createRoot, type Root } from 'react-dom/client'
import { flushSync } from 'react-dom'
import { CompanyPublicH2Page } from './CompanyPublicH2Page'
import { collectCompanyPublicH2ParityVector } from './parityVector'
import { parseCompanyPublicH2 } from './contract'
import type { CompanyPublicH2 } from './contractSchema'

const STATE_ID = 'company-public-h2-state'
const ROOT_ID = 'company-public-h2-root'
const controllerByDocument = new WeakMap<Document, () => void>()
type FinanceChartsModule = typeof import('./FinanceCharts')
type FinanceChartsLoader = () => Promise<FinanceChartsModule>

/** Stop enhancement roots and invalidate a pending lazy module load exactly once. */
export function teardownCompanyPublicH2(documentRef: Document = document): void { controllerByDocument.get(documentRef)?.() }

/** Enhances signed SSR facts; optional chart code loads only after parity and intersection. */
export async function bootstrapCompanyPublicH2(documentRef: Document = document, cryptoImpl: Pick<Crypto, 'subtle'> = crypto, loadFinanceCharts: FinanceChartsLoader = () => import('./FinanceCharts')): Promise<boolean> {
  teardownCompanyPublicH2(documentRef)
  const states = documentRef.querySelectorAll(`#${STATE_ID}`)
  const rootElement = documentRef.getElementById(ROOT_ID)
  if (states.length !== 1 || rootElement === null) return fail(documentRef)
  const raw = states[0].textContent ?? ''
  if (new TextEncoder().encode(raw).byteLength > 786_432) return fail(documentRef)
  const ssrHtml = rootElement.innerHTML
  const ssrVector = collectCompanyPublicH2ParityVector(documentRef)
  let root: Root | null = null
  try {
    const parsed = await parseCompanyPublicH2(raw, cryptoImpl)
    if (rootElement.dataset.contract !== 'company_public_h2_v1' || rootElement.dataset.reportId !== parsed.dto.report_id || documentRef.location.pathname !== parsed.dto.canonical_path) return fail(documentRef)
    root = createRoot(rootElement)
    flushSync(() => root!.render(<CompanyPublicH2Page dto={parsed.dto} />))
    const reactVector = collectCompanyPublicH2ParityVector(documentRef)
    if (reactVector !== ssrVector) {
      root.unmount(); rootElement.innerHTML = ssrHtml
      return fail(documentRef)
    }
    rootElement.dataset.enhanced = 'true'
    controllerByDocument.set(documentRef, armLazyCharts(documentRef, root, parsed.dto, loadFinanceCharts))
    return true
  } catch {
    root?.unmount(); rootElement.innerHTML = ssrHtml
    return fail(documentRef)
  }
}

function armLazyCharts(documentRef: Document, factualRoot: Root, dto: CompanyPublicH2, loadFinanceCharts: FinanceChartsLoader): () => void {
  const target = documentRef.getElementById('finance')
  let observer: IntersectionObserver | null = null
  let disposed = false
  let imported = false
  let generation = 0
  const chartRoots: Root[] = []
  const announce = (message: string) => { const live = documentRef.querySelector<HTMLElement>('.company-public-h2__live'); if (live) live.textContent = message }
  const load = (): void => {
    if (disposed || imported) return
    imported = true
    const currentGeneration = ++generation
    void loadFinanceCharts().then(({ FinanceChartForHost }) => {
      if (disposed || currentGeneration !== generation) return
      for (const hostId of ['finance-f1', 'finance-f2', 'finance-f3', 'finance-f4'] as const) {
        const host = documentRef.querySelector<HTMLElement>(`[data-h2-finance-enhancement="${hostId}"]`)
        if (!host) continue
        const chartRoot = createRoot(host)
        chartRoots.push(chartRoot)
        host.removeAttribute('aria-hidden')
        flushSync(() => chartRoot.render(<FinanceChartForHost dto={dto} hostId={hostId} onError={() => announce('Интерактивный график недоступен; табличные данные сохранены.')} />))
      }
    }).catch(() => {
      if (!disposed && currentGeneration === generation) announce('Интерактивный график недоступен; табличные данные сохранены.')
    })
  }
  if (target && typeof IntersectionObserver !== 'undefined') {
    observer = new IntersectionObserver(entries => { if (entries.some(entry => entry.isIntersecting)) { observer?.disconnect(); observer = null; load() } }, { rootMargin: '160px' })
    observer.observe(target)
  } else if (target) announce('Интерактивные графики не поддерживаются; табличные данные сохранены.')
  return () => {
    if (disposed) return
    disposed = true; generation += 1; observer?.disconnect(); observer = null
    for (const chartRoot of chartRoots) chartRoot.unmount()
    factualRoot.unmount()
    controllerByDocument.delete(documentRef)
  }
}

function fail(documentRef: Document): false {
  const live = documentRef.querySelector<HTMLElement>('.company-public-h2__live')
  if (live) live.textContent = 'Интерактивное улучшение страницы недоступно.'
  return false
}
