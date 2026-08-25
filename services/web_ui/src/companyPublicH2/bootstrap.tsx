import { createRoot } from 'react-dom/client'
import { flushSync } from 'react-dom'
import { CompanyPublicH2Page } from './CompanyPublicH2Page'
import { collectCompanyPublicH2ParityVector } from './parityVector'
import { parseCompanyPublicH2 } from './contract'

const STATE_ID = 'company-public-h2-state'
const ROOT_ID = 'company-public-h2-root'

/**
 * Enhances a signed SSR artifact in place.  The SSR bytes are retained unless
 * parsing, binding or exact semantic parity succeeds; neither path performs a
 * factual, auth, analytics or provider request.
 */
export async function bootstrapCompanyPublicH2(documentRef: Document = document, cryptoImpl: Pick<Crypto, 'subtle'> = crypto): Promise<boolean> {
  const states = documentRef.querySelectorAll(`#${STATE_ID}`)
  const root = documentRef.getElementById(ROOT_ID)
  if (states.length !== 1 || root === null) return fail(documentRef)
  const raw = states[0].textContent ?? ''
  if (new TextEncoder().encode(raw).byteLength > 786_432) return fail(documentRef)
  const ssrHtml = root.innerHTML
  const ssrVector = collectCompanyPublicH2ParityVector(documentRef)
  try {
    const parsed = await parseCompanyPublicH2(raw, cryptoImpl)
    if (
      root.dataset.contract !== 'company_public_h2_v1'
      || root.dataset.reportId !== parsed.dto.report_id
      || documentRef.location.pathname !== parsed.dto.canonical_path
    ) return fail(documentRef)
    flushSync(() => createRoot(root).render(<CompanyPublicH2Page dto={parsed.dto} />))
    if (collectCompanyPublicH2ParityVector(documentRef) !== ssrVector) {
      root.innerHTML = ssrHtml
      return fail(documentRef)
    }
    root.dataset.enhanced = 'true'
    return true
  } catch {
    root.innerHTML = ssrHtml
    return fail(documentRef)
  }
}

function fail(documentRef: Document): false {
  const live = documentRef.querySelector<HTMLElement>('.company-public-h2__live')
  if (live) live.textContent = 'Интерактивное улучшение страницы недоступно.'
  return false
}
