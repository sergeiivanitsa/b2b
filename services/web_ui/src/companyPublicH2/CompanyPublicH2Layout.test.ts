import { describe, expect, it } from 'vitest'
import css from './CompanyPublicH2Page.css?raw'

describe('Company Public H2 stable responsive layout contract', () => {
  it('exposes one production-safe bottom inset token which the harness can override', () => {
    expect(css).toContain('--company-public-h2-safe-area-bottom: env(safe-area-inset-bottom, 0px)')
    expect(css.match(/env\(safe-area-inset-bottom/gu)).toHaveLength(1)
    expect(css).toContain('calc(12px + var(--company-public-h2-safe-area-bottom))')
    expect(css).toContain('calc(144px + var(--company-public-h2-safe-area-bottom))')
    expect(css).toContain('calc(80px + var(--company-public-h2-safe-area-bottom))')
  })

  it('reserves only factual lazy-chart hosts and contains their local overflow', () => {
    expect(css).toContain('--company-public-h2-chart-reserved-block-size: 228px')
    expect(css).toContain('[data-h2-finance-article]:is(:has(> dl), :has(> table), :has(> section > table))')
    expect(css).toContain('[data-h2-arbitration-article]:has([data-h2-arbitration-scope])')
    expect(css).toContain('block-size: var(--company-public-h2-chart-reserved-block-size)')
    expect(css).toContain('overscroll-behavior: contain')
    expect(css).toContain('scrollbar-gutter: stable')
  })

  it('contains the two unwrapped finance table shapes at extreme reflow widths', () => {
    expect(css).toContain('[data-h2-finance-article] > table, .company-public-h2 [data-h2-finance-article] > section > table')
    expect(css).toContain('display: block; max-width: 100%; overflow-x: auto; overscroll-behavior-inline: contain')
    expect(css).not.toContain('overflow-x: hidden')
  })

  it('keeps the frozen breakpoint and reduced-motion boundaries', () => {
    expect(css).toContain('@media (min-width: 1200px)')
    expect(css).toContain('@media (min-width: 768px) and (max-width: 1199px)')
    expect(css).toContain('@media (max-width: 767px)')
    expect(css).toContain('@media (prefers-reduced-motion: reduce)')
    expect(css).toContain('transition: none !important')
    expect(css).toContain('animation: none !important')
  })
})
