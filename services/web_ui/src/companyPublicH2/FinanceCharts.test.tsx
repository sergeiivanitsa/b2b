import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { FinanceChartForHost } from './FinanceCharts'
import { parseCompanyPublicH2 } from './contract'
import fixture from '../../../../shared/fixtures/company_public_h2_contract_v1.json?raw'
import './CompanyPublicH2Page.css'

afterEach(cleanup)

function numericAttribute(element: Element, name: string): number {
  const value = element.getAttribute(name)
  if (value === null) throw new Error(`missing ${name}`)
  return Number(value)
}

function renderedTargetSize(mark: SVGRectElement): Readonly<{ width: number; height: number }> {
  const svg = mark.closest('svg')
  if (svg === null) throw new Error('chart mark is outside an svg')
  const viewBox = (svg.getAttribute('viewBox') ?? '').split(/\s+/).map(Number)
  const style = getComputedStyle(svg)
  return {
    width: numericAttribute(mark, 'width') * Number.parseFloat(style.width) / viewBox[2],
    height: numericAttribute(mark, 'height') * Number.parseFloat(style.height) / viewBox[3],
  }
}

function cssPixels(value: string): number {
  if (value === '') return 0
  const result = Number.parseFloat(value)
  if (!Number.isFinite(result)) throw new Error(`expected CSS pixel length, received ${value}`)
  return result
}

function horizontalInsets(element: Element): number {
  const style = getComputedStyle(element)
  return cssPixels(style.paddingLeft) + cssPixels(style.paddingRight) + cssPixels(style.borderLeftWidth) + cssPixels(style.borderRightWidth)
}

function contentBoxWidth(element: Element, borderBoxWidth: number): number {
  const boxSizing = getComputedStyle(element).boxSizing
  // JSDOM leaves inherited box-sizing empty; the rendered root and browser
  // contract resolve `.company-public-h2 * { box-sizing: inherit }` to border-box.
  if (boxSizing !== '') expect(boxSizing).toBe('border-box')
  return borderBoxWidth - horizontalInsets(element)
}

function outwardWidth(element: Element, assignedBorderBoxWidth: number, childOutwardWidth: number): number {
  const requiredWidth = horizontalInsets(element) + childOutwardWidth
  return ['auto', 'scroll', 'hidden', 'clip'].includes(getComputedStyle(element).overflowX)
    ? assignedBorderBoxWidth
    : Math.max(assignedBorderBoxWidth, requiredWidth)
}

describe('FinanceChartForHost', () => {
  it('uses focusable marks with exact accessible names and a local tooltip', async () => {
    const dto = (await parseCompanyPublicH2(fixture)).dto
    render(<FinanceChartForHost dto={dto} hostId="finance-f1" onError={() => undefined} />)
    const mark = screen.getByRole('button', { name: /1250; 2025;/ })
    expect(mark.getAttribute('aria-describedby')).toMatch(/^finance-f1-tooltip-/)
    fireEvent.focus(mark)
    expect(screen.getByRole('tooltip').textContent).toContain('1250; 2025')
    fireEvent.keyDown(mark.closest('.company-public-h2__chart-layer')!, { key: 'Escape' })
    expect(screen.queryByRole('tooltip')).toBeNull()
  })

  it('keeps every target at least 44 by 44 CSS pixels in a narrow responsive viewport', async () => {
    const dto = (await parseCompanyPublicH2(fixture)).dto
    const { container } = render(<div style={{ width: '280px' }}>
      <FinanceChartForHost dto={dto} hostId="finance-f1" onError={() => undefined} />
      <FinanceChartForHost dto={dto} hostId="finance-f2" onError={() => undefined} />
      <FinanceChartForHost dto={dto} hostId="finance-f3" onError={() => undefined} />
      <FinanceChartForHost dto={dto} hostId="finance-f4" onError={() => undefined} />
    </div>)
    const viewports = container.querySelectorAll<HTMLElement>('[data-h2-chart-viewport]')
    const marks = container.querySelectorAll<SVGRectElement>('[data-h2-chart-mark]')
    expect(viewports.length).toBeGreaterThan(0)
    expect(marks.length).toBeGreaterThan(0)
    for (const viewport of viewports) expect(getComputedStyle(viewport).overflowX).toBe('auto')
    for (const mark of marks) {
      const svg = mark.closest('svg')!
      expect(getComputedStyle(svg).width).toBe('560px')
      expect(getComputedStyle(svg).minWidth).toBe('560px')
      expect(getComputedStyle(svg).height).toBe('180px')
      expect(renderedTargetSize(mark).width).toBeGreaterThanOrEqual(44)
      expect(renderedTargetSize(mark).height).toBeGreaterThanOrEqual(44)
    }
  })

  it('contains a 560px F3 canvas in its local scroller without widening a nested 320px page', async () => {
    const dto = (await parseCompanyPublicH2(fixture)).dto
    const { container } = render(<main className="company-public-h2" style={{ width: '320px' }}>
      <section data-testid="narrow-finance">
        <article data-h2-finance-article="finance-f3">
          <div className="company-public-h2__finance-enhancement">
            <FinanceChartForHost dto={dto} hostId="finance-f3" onError={() => undefined} />
          </div>
        </article>
      </section>
    </main>)
    const page = container.querySelector<HTMLElement>('.company-public-h2')!
    const finance = container.querySelector<HTMLElement>('[data-testid="narrow-finance"]')!
    const article = container.querySelector<HTMLElement>('[data-h2-finance-article="finance-f3"]')!
    const enhancement = container.querySelector<HTMLElement>('.company-public-h2__finance-enhancement')!
    const layer = container.querySelector<HTMLElement>('.company-public-h2__chart-layer')!
    const panels = container.querySelector<HTMLElement>('.company-public-h2__chart-panels')!
    const panel = container.querySelector<HTMLElement>('.company-public-h2__chart-panel')!
    const viewport = panel.querySelector<HTMLElement>('[data-h2-chart-viewport]')!
    const svg = viewport.querySelector<SVGSVGElement>('svg')!

    const pageBorder = 320
    const financeBorder = contentBoxWidth(page, pageBorder)
    const articleBorder = contentBoxWidth(finance, financeBorder)
    const enhancementBorder = contentBoxWidth(article, articleBorder)
    const layerBorder = contentBoxWidth(enhancement, enhancementBorder)
    const panelsBorder = contentBoxWidth(layer, layerBorder)
    const panelsContent = contentBoxWidth(panels, panelsBorder)
    const gap = cssPixels(getComputedStyle(panels).columnGap)
    const columns = 1
    expect(getComputedStyle(panels).gridTemplateColumns).toBe('minmax(0, 1fr)')

    const panelBorder = panelsContent
    const viewportBorder = contentBoxWidth(panel, panelBorder)
    const viewportContent = contentBoxWidth(viewport, viewportBorder)
    const svgWidth = cssPixels(getComputedStyle(svg).width)
    const localScrollWidth = Math.max(viewportContent, svgWidth)
    expect(getComputedStyle(viewport).overflowX).toBe('auto')
    expect(localScrollWidth).toBe(560)
    expect(localScrollWidth).toBeGreaterThan(viewportBorder)

    const viewportOutward = outwardWidth(viewport, viewportBorder, svgWidth)
    const panelOutward = outwardWidth(panel, panelBorder, viewportOutward)
    const gridContentWidth = columns * panelOutward + (columns - 1) * gap
    const panelsOutward = outwardWidth(panels, panelsBorder, gridContentWidth)
    const layerOutward = outwardWidth(layer, layerBorder, panelsOutward)
    const enhancementOutward = outwardWidth(enhancement, enhancementBorder, layerOutward)
    const articleOutward = outwardWidth(article, articleBorder, enhancementOutward)
    const financeOutward = outwardWidth(finance, financeBorder, articleOutward)
    const modeledPageScrollWidth = outwardWidth(page, pageBorder, financeOutward)
    expect(modeledPageScrollWidth).toBeLessThanOrEqual(pageBorder)
  })

  it('renders both F2 metrics from every available period geometry and closes on document outside pointer', async () => {
    const dto = (await parseCompanyPublicH2(fixture)).dto
    const { container } = render(<FinanceChartForHost dto={dto} hostId="finance-f2" onError={() => undefined} />)
    expect(container.querySelectorAll('[data-h2-chart-mark^="f2-"]')).toHaveLength(14)
    for (const mark of container.querySelectorAll<SVGRectElement>('[data-h2-chart-mark^="f2-"]')) {
      const top = Number(mark.getAttribute('y'))
      expect(top).toBeGreaterThanOrEqual(0)
      expect(top + Number(mark.getAttribute('height'))).toBeLessThanOrEqual(180)
    }
    const mark = screen.getByRole('button', { name: /Собственные средства; 2019;/ })
    fireEvent.pointerDown(mark)
    expect(screen.getByRole('tooltip')).toBeTruthy()
    fireEvent.pointerDown(document.body)
    expect(screen.queryByRole('tooltip')).toBeNull()
  })

  it('renders diverging signed F2 intervals on opposite sides of their shared zero baseline', async () => {
    const dto = (await parseCompanyPublicH2(fixture)).dto
    const original = dto.blocks.finance_f2!
    const periods = original.periods.map((period, index) => index === 0 ? {
      ...period,
      equity_1300: period.equity_1300 === null ? null : {
        ...period.equity_1300,
        source_thousand_decimal: '-50',
        rub_decimal: '-50000',
        million_decimal: '-0.05',
        display_exact: '−0,050 млн ₽',
        display_compact: '−0,1 млн ₽',
      },
      equity_share_decimal: null,
      debt_share_decimal: null,
      mode: 'diverging_signed' as const,
      axis: { axis_min_decimal: '-50', axis_max_decimal: '60' },
      geometry_by_metric: [
        { start_ratio_decimal: '0', end_ratio_decimal: '-50' },
        { start_ratio_decimal: '0', end_ratio_decimal: '60' },
      ] as const,
    } : period) as unknown as typeof original.periods
    const signedDto = { ...dto, blocks: { ...dto.blocks, finance_f2: { ...original, periods } } }
    const { container } = render(<FinanceChartForHost dto={signedDto} hostId="finance-f2" onError={() => undefined} />)
    const negativeMark = container.querySelector<SVGRectElement>('[data-h2-chart-mark="f2-2019-0"]')!
    const positiveMark = container.querySelector<SVGRectElement>('[data-h2-chart-mark="f2-2019-1"]')!
    const negativeShape = negativeMark.previousElementSibling as SVGRectElement
    const positiveShape = positiveMark.previousElementSibling as SVGRectElement
    const negativeTop = numericAttribute(negativeShape, 'y')
    const negativeBottom = negativeTop + numericAttribute(negativeShape, 'height')
    const positiveTop = numericAttribute(positiveShape, 'y')
    const positiveBottom = positiveTop + numericAttribute(positiveShape, 'height')
    expect(positiveTop).toBeCloseTo(30)
    expect(positiveBottom).toBeCloseTo(negativeTop)
    expect(negativeBottom).toBeCloseTo(150)
  })

  it('opens disclosure on mouseenter and touchStart, then closes when focus exits the layer', async () => {
    const dto = (await parseCompanyPublicH2(fixture)).dto
    render(<FinanceChartForHost dto={dto} hostId="finance-f1" onError={() => undefined} />)
    const mark = screen.getByRole('button', { name: /1250; 2025;/ })
    const layer = mark.closest('.company-public-h2__chart-layer')!
    fireEvent.mouseEnter(mark)
    expect(screen.getByRole('tooltip')).toBeTruthy()
    fireEvent.mouseLeave(layer)
    expect(screen.queryByRole('tooltip')).toBeNull()
    fireEvent.touchStart(mark)
    expect(screen.getByRole('tooltip')).toBeTruthy()
    fireEvent.keyDown(layer, { key: 'Escape' })
    expect(screen.queryByRole('tooltip')).toBeNull()
    const outside = document.createElement('button')
    document.body.append(outside)
    fireEvent.focus(mark)
    expect(screen.getByRole('tooltip')).toBeTruthy()
    fireEvent.blur(mark, { relatedTarget: outside })
    expect(screen.queryByRole('tooltip')).toBeNull()
    outside.remove()
  })

  it('keeps tooltip identifiers unique across chart hosts', async () => {
    const dto = (await parseCompanyPublicH2(fixture)).dto
    const { container } = render(<><FinanceChartForHost dto={dto} hostId="finance-f1" onError={() => undefined} /><FinanceChartForHost dto={dto} hostId="finance-f2" onError={() => undefined} /></>)
    const ids = [...container.querySelectorAll('[data-h2-chart-mark]')].map(mark => mark.getAttribute('aria-describedby'))
    expect(new Set(ids).size).toBe(2)
  })

  it('draws F3 lines only between adjacent available calendar points', async () => {
    const dto = (await parseCompanyPublicH2(fixture)).dto
    const original = dto.blocks.finance_f3!
    const points = original.points.map((point, index) => index === 3
      ? { ...point, revenue_2110: null, revenue_yoy_decimal: null, geometry_by_metric: [null, point.geometry_by_metric[1]] as const }
      : index === 4 ? { ...point, revenue_yoy_decimal: null } : point) as unknown as typeof original.points
    const gapDto = { ...dto, blocks: { ...dto.blocks, finance_f3: { ...original, points } } }
    const { container } = render(<FinanceChartForHost dto={gapDto} hostId="finance-f3" onError={() => undefined} />)
    const revenuePanel = container.querySelector<HTMLElement>('[aria-label="Выручка: отдельная шкала"]')!
    expect([...revenuePanel.querySelectorAll('[data-h2-chart-segment]')].map(item => item.getAttribute('data-h2-chart-segment'))).toEqual([
      'revenue-2019-2020',
      'revenue-2020-2021',
      'revenue-2023-2024',
      'revenue-2024-2025',
    ])
    expect(revenuePanel.querySelector('[data-h2-chart-segment*="2021-2023"]')).toBeNull()
    expect(container.querySelectorAll('svg[role="group"]')).toHaveLength(2)
  })
})
