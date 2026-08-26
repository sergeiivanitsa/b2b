import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ArbitrationChartForHost, type ArbitrationChartHostId } from './ArbitrationCharts'
import { arbitrationCountCoordinate, arbitrationStackCoordinates } from './arbitrationGeometry'
import { arbitrationPolicyV3Dto } from './arbitrationTestFixture'
import { parseCompanyPublicH2 } from './contract'
import { StrictJsonIntegerToken } from './strictJson'
import maskedV3Raw from '../../../../shared/fixtures/company_public_h2_contract_v1_arbitration_masked_v3.json?raw'
import './CompanyPublicH2Page.css'

afterEach(cleanup)

const HOSTS: readonly ArbitrationChartHostId[] = ['arbitration-a1', 'arbitration-a2', 'arbitration-a3', 'arbitration-a4', 'arbitration-a5']

function numberAttribute(element: Element, name: string): number {
  const value = element.getAttribute(name)
  if (value === null) throw new Error(`missing ${name}`)
  return Number(value)
}

describe('ArbitrationChartForHost', () => {
  it('uses patterned, focusable 44px marks with exact accessible names', async () => {
    const dto = (await parseCompanyPublicH2(maskedV3Raw)).dto
    const { container } = render(<>{HOSTS.map(hostId => <ArbitrationChartForHost dto={dto} hostId={hostId} onError={() => undefined} key={hostId} />)}</>)
    const marks = [...container.querySelectorAll<SVGRectElement>('[data-h2-arbitration-chart-mark]')]
    expect(marks.length).toBeGreaterThan(10)
    for (const mark of marks) {
      expect(numberAttribute(mark, 'width')).toBeGreaterThanOrEqual(44)
      expect(numberAttribute(mark, 'height')).toBeGreaterThanOrEqual(44)
      expect(mark.getAttribute('aria-describedby')).toMatch(/^arbitration-a[1-5]-tooltip-/u)
    }
    expect(new Set([...container.querySelectorAll('[data-h2-chart-pattern]')].map(item => item.getAttribute('data-h2-chart-pattern')?.split('-').at(-1))).size).toBeGreaterThanOrEqual(4)
    expect(screen.getByRole('button', { name: /A1; 2025; Истец; 1 дел; показано 1 из 1 дел/u })).toBeTruthy()
    expect(screen.getByRole('button', { name: /A4; А40-123\/2025; 2025; −12,34 ₽; показано 1 из 1 дел/u })).toBeTruthy()
    expect(screen.getByRole('button', { name: /A5; Сторона скрыта 1; 1 дел; показано 1 из 1 дел/u })).toBeTruthy()
  })

  it('shares disclosure across focus, mouse and touch and closes on every exit path', async () => {
    const dto = await arbitrationPolicyV3Dto()
    render(<ArbitrationChartForHost dto={dto} hostId="arbitration-a2" onError={() => undefined} />)
    const mark = screen.getByRole('button', { name: /A2; Истец/u })
    const layer = mark.closest('.company-public-h2__chart-layer')!
    fireEvent.focus(mark)
    expect(screen.getByRole('tooltip').textContent).toContain('A2; Истец')
    fireEvent.keyDown(layer, { key: 'Escape' })
    expect(screen.queryByRole('tooltip')).toBeNull()
    fireEvent.mouseEnter(mark)
    expect(screen.getByRole('tooltip')).toBeTruthy()
    fireEvent.mouseLeave(layer)
    expect(screen.queryByRole('tooltip')).toBeNull()
    fireEvent.touchStart(mark)
    expect(screen.getByRole('tooltip')).toBeTruthy()
    fireEvent.pointerDown(document.body)
    expect(screen.queryByRole('tooltip')).toBeNull()
    const outside = document.createElement('button'); document.body.append(outside)
    fireEvent.focus(mark); fireEvent.blur(mark, { relatedTarget: outside })
    expect(screen.queryByRole('tooltip')).toBeNull()
    outside.remove()
  })

  it('places negative and positive exact A4 intervals on opposite sides of zero', async () => {
    const dto = await arbitrationPolicyV3Dto()
    const original = dto.blocks.arbitration_a4!
    const group = original.currency_groups[0]
    const positive = group.cases[0]
    const negative = { ...positive, case_public_id: 'case_000002', case_number: 'А40-2/2025', amount: { ...positive.amount!, source_decimal: '-125.5', display_exact: '−125,5 ₽' } }
    const signedDto = {
      ...dto,
      blocks: { ...dto.blocks, arbitration_a4: { ...original, currency_groups: [{ ...group, axis: { axis_min_decimal: '-125.5', axis_max_decimal: '125.5' }, cases: [negative, positive], case_geometries: [{ case_public_id: 'case_000002', geometry: { start_ratio_decimal: '0', end_ratio_decimal: '-125.5' } }, { case_public_id: 'case_000001', geometry: { start_ratio_decimal: '0', end_ratio_decimal: '125.5' } }], scope: { ...group.scope, eligible_total: new StrictJsonIntegerToken('2'), shown: new StrictJsonIntegerToken('2'), label: 'показано 2 из 2 дел' } }] } },
    } as typeof dto
    const { container } = render(<ArbitrationChartForHost dto={signedDto} hostId="arbitration-a4" onError={() => undefined} />)
    const axis = container.querySelector('[data-h2-arbitration-zero-axis]')!
    const zero = numberAttribute(axis, 'x1')
    const shapes = [...container.querySelectorAll<SVGRectElement>('[data-h2-chart-pattern]')]
    expect(shapes).toHaveLength(2)
    expect(numberAttribute(shapes[0], 'x') + numberAttribute(shapes[0], 'width')).toBeCloseTo(zero)
    expect(numberAttribute(shapes[1], 'x')).toBeCloseTo(zero)
  })

  it('keeps huge integer inputs exact before bounded coordinates', () => {
    const maximum = new StrictJsonIntegerToken('90071992547409931234567890')
    const half = new StrictJsonIntegerToken('45035996273704965617283945')
    expect(arbitrationCountCoordinate(half, maximum, 430)).toBe(215)
    expect(arbitrationStackCoordinates([half, half], maximum, 430)).toEqual([[0, 215], [215, 430]])
  })

  it('renders no SVG for exact available_empty views', async () => {
    const dto = await arbitrationPolicyV3Dto(false)
    const { container } = render(<>{HOSTS.map(hostId => <ArbitrationChartForHost dto={dto} hostId={hostId} onError={() => undefined} key={hostId} />)}</>)
    expect(container.querySelector('svg')).toBeNull()
  })

  it('contains a render error in the local host and preserves a visible status', async () => {
    const dto = await arbitrationPolicyV3Dto()
    const original = dto.blocks.arbitration_a4!
    const group = original.currency_groups[0]
    const broken = { ...dto, blocks: { ...dto.blocks, arbitration_a4: { ...original, currency_groups: [{ ...group, axis: { axis_min_decimal: '1', axis_max_decimal: '1' } }] } } } as typeof dto
    const onError = vi.fn()
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    render(<ArbitrationChartForHost dto={broken} hostId="arbitration-a4" onError={onError} />)
    expect((await screen.findByRole('status')).textContent).toContain('фактические данные сохранены')
    expect(onError).toHaveBeenCalledOnce()
  })
})
