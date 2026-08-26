import { createRoot, type Root } from 'react-dom/client'
import { flushSync } from 'react-dom'
import type { ReactNode } from 'react'
import { CompanyPublicH2Page } from './CompanyPublicH2Page'
import { collectCompanyPublicH2ParityVector } from './parityVector'
import { parseCompanyPublicH2 } from './contract'
import type { CompanyPublicH2 } from './contractSchema'
import { classifyArbitrationPolicyV3 } from './arbitrationContractSemantics'

const STATE_ID = 'company-public-h2-state'
const ROOT_ID = 'company-public-h2-root'
const controllerByDocument = new WeakMap<Document, () => void>()
type FinanceChartsModule = typeof import('./FinanceCharts')
type FinanceChartsLoader = () => Promise<FinanceChartsModule>
type ArbitrationChartsModule = typeof import('./ArbitrationCharts')
type ArbitrationChartsLoader = () => Promise<ArbitrationChartsModule>

/** Stop enhancement roots and invalidate a pending lazy module load exactly once. */
export function teardownCompanyPublicH2(documentRef: Document = document): void { controllerByDocument.get(documentRef)?.() }

/** Enhances signed SSR facts; optional chart code loads only after parity and intersection. */
export async function bootstrapCompanyPublicH2(documentRef: Document = document, cryptoImpl: Pick<Crypto, 'subtle'> = crypto, loadFinanceCharts: FinanceChartsLoader = () => import('./FinanceCharts'), loadArbitrationCharts: ArbitrationChartsLoader = () => import('./ArbitrationCharts')): Promise<boolean> {
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
    controllerByDocument.set(documentRef, armLazyCharts(documentRef, root, parsed.dto, loadFinanceCharts, loadArbitrationCharts))
    return true
  } catch {
    root?.unmount(); rootElement.innerHTML = ssrHtml
    return fail(documentRef)
  }
}

type LazySectionOptions<Module, HostId extends string> = Readonly<{
  targetId: 'finance' | 'arbitration'
  eligible: boolean
  hostIds: readonly HostId[]
  hostAttribute: 'data-h2-finance-enhancement' | 'data-h2-arbitration-enhancement'
  loadModule: () => Promise<Module>
  render: (module: Module, hostId: HostId) => ReactNode
}>

function armLazySection<Module, HostId extends string>(documentRef: Document, options: LazySectionOptions<Module, HostId>): () => void {
  const target = options.eligible ? documentRef.getElementById(options.targetId) : null
  let observer: IntersectionObserver | null = null
  let disposed = false
  let imported = false
  let generation = 0
  const chartRoots: Root[] = []
  const mountedHosts = new Set<HTMLElement>()
  const hostFor = (hostId: HostId) => documentRef.querySelector<HTMLElement>(`[${options.hostAttribute}="${hostId}"]`)
  const mountStatus = (message: string): void => {
    const host = options.hostIds.map(hostFor).find(candidate => candidate !== null && !mountedHosts.has(candidate))
    if (host === undefined || host === null || disposed) return
    mountedHosts.add(host); host.removeAttribute('aria-hidden')
    const statusRoot = createRoot(host); chartRoots.push(statusRoot)
    flushSync(() => statusRoot.render(<p className="company-public-h2__chart-status" role="status" aria-live="polite">{message}</p>))
  }
  const load = (): void => {
    if (disposed || imported) return
    imported = true
    const currentGeneration = ++generation
    let pending: Promise<Module>
    try { pending = options.loadModule() } catch {
      mountStatus('Интерактивный график недоступен; фактические данные сохранены.')
      return
    }
    void pending.then(module => {
      if (disposed || currentGeneration !== generation) return
      for (const hostId of options.hostIds) {
        const host = hostFor(hostId)
        if (host === null || mountedHosts.has(host)) continue
        try {
          const content = options.render(module, hostId)
          if (content === null || content === undefined) continue
          mountedHosts.add(host); host.removeAttribute('aria-hidden')
          const chartRoot = createRoot(host); chartRoots.push(chartRoot)
          flushSync(() => chartRoot.render(content))
        } catch {
          mountStatus('Интерактивный график недоступен; фактические данные сохранены.')
          break
        }
      }
    }).catch(() => {
      if (!disposed && currentGeneration === generation) mountStatus('Интерактивный график недоступен; фактические данные сохранены.')
    })
  }
  if (target && typeof IntersectionObserver !== 'undefined') {
    try {
      observer = new IntersectionObserver(entries => { if (entries.some(entry => entry.isIntersecting)) { observer?.disconnect(); observer = null; load() } }, { rootMargin: '160px' })
      observer.observe(target)
    } catch {
      observer?.disconnect(); observer = null
      mountStatus('Интерактивные графики не поддерживаются; фактические данные сохранены.')
    }
  } else if (target) mountStatus('Интерактивные графики не поддерживаются; фактические данные сохранены.')
  return () => {
    if (disposed) return
    disposed = true; generation += 1; observer?.disconnect(); observer = null
    for (const chartRoot of chartRoots) chartRoot.unmount()
  }
}

function armLazyCharts(documentRef: Document, factualRoot: Root, dto: CompanyPublicH2, loadFinanceCharts: FinanceChartsLoader, loadArbitrationCharts: ArbitrationChartsLoader): () => void {
  const finance = armLazySection(documentRef, {
    targetId: 'finance',
    eligible: [dto.blocks.finance_f1, dto.blocks.finance_f2, dto.blocks.finance_f3, dto.blocks.finance_f4].some(view => view !== null),
    hostIds: ['finance-f1', 'finance-f2', 'finance-f3', 'finance-f4'] as const,
    hostAttribute: 'data-h2-finance-enhancement',
    loadModule: loadFinanceCharts,
    render: ({ FinanceChartForHost }, hostId) => <FinanceChartForHost dto={dto} hostId={hostId} onError={() => undefined} />,
  })
  const arbitration = armLazySection(documentRef, {
    targetId: 'arbitration',
    eligible: classifyArbitrationPolicyV3(dto) === 'bound' && [
      (dto.blocks.arbitration_a1?.buckets.length ?? 0) > 0,
      (dto.blocks.arbitration_a2?.denominator.value ?? 0n) > 0n,
      (dto.blocks.arbitration_a3?.denominator.value ?? 0n) > 0n,
      (dto.blocks.arbitration_a4?.currency_groups[0]?.cases.length ?? 0) > 0,
      (dto.blocks.arbitration_a5?.groups.length ?? 0) > 0,
    ].some(Boolean),
    hostIds: ['arbitration-a1', 'arbitration-a2', 'arbitration-a3', 'arbitration-a4', 'arbitration-a5'] as const,
    hostAttribute: 'data-h2-arbitration-enhancement',
    loadModule: loadArbitrationCharts,
    render: ({ ArbitrationChartForHost }, hostId) => <ArbitrationChartForHost dto={dto} hostId={hostId} onError={() => undefined} />,
  })
  let disposed = false
  const controller = (): void => {
    if (disposed) return
    disposed = true; finance(); arbitration(); factualRoot.unmount()
    if (controllerByDocument.get(documentRef) === controller) controllerByDocument.delete(documentRef)
  }
  return controller
}

function fail(documentRef: Document): false {
  const live = documentRef.querySelector<HTMLElement>('.company-public-h2__live')
  if (live) live.textContent = 'Интерактивное улучшение страницы недоступно.'
  return false
}
