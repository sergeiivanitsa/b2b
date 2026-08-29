import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import type { CompanyPublicH2, PublicH2AxisDto, PublicH2FinanceF1Dto, PublicH2FinanceF2Dto, PublicH2FinanceF3Dto, PublicH2FinanceF4Dto, PublicH2IntervalDto, PublicH2MoneyDto } from './contractSchema'
import { intervalCoordinates, decimalCoordinate } from './financeGeometry'
import { moneyExact, per100, year } from './financePresentation'
import { FinanceChartErrorBoundary } from './FinanceChartErrorBoundary'

type HostId = 'finance-f1' | 'finance-f2' | 'finance-f3' | 'finance-f4'
type Disclosure = Readonly<{ id: string; text: string }> | null
type Open = (item: Disclosure, persistent?: boolean) => void
const WIDTH = 560; const HEIGHT = 180; const BASE = 150; const PLOT = 440; const F2_VERTICAL_PLOT = 120

function AxisSvg({ children, label }: { children: ReactNode; label: string }) { return <div className="company-public-h2__chart-viewport" data-h2-chart-viewport><svg className="company-public-h2__chart" width={WIDTH} height={HEIGHT} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="group" aria-label={label}><line x1="30" y1={BASE} x2="540" y2={BASE} stroke="currentColor" opacity=".4" />{children}</svg></div> }
function markLabel(metric: string, period: string, value: PublicH2MoneyDto | string, state: string): string { return `${metric}; ${period}; ${typeof value === 'string' ? value : moneyExact(value)}; состояние: ${state}` }
function ChartMark({ id, label, tooltipId, x, y, width = 12, height = 12, open }: { id: string; label: string; tooltipId: string; x: number; y: number; width?: number; height?: number; open: Open }) { const visibleWidth=Math.max(4,width), visibleHeight=Math.max(4,height), hit=44; const item={ id, text: label }; const disclose=()=>open(item); return <g><rect aria-hidden="true" x={x} y={y} width={visibleWidth} height={visibleHeight} fill="#EE5A2A" /><rect data-h2-chart-mark={id} tabIndex={0} role="button" aria-describedby={tooltipId} aria-label={label} x={x+visibleWidth/2-hit/2} y={y+visibleHeight/2-hit/2} width={hit} height={hit} fill="transparent" onFocus={disclose} onMouseEnter={disclose} onPointerEnter={event => { if (event.pointerType !== 'touch') open(item, false) }} onTouchStart={() => open(item, true)} onPointerDown={event => open(item, event.pointerType === 'touch')} onClick={disclose} /></g> }
function orderedInterval(geometry: PublicH2IntervalDto, axis: PublicH2AxisDto): readonly [number, number] { const [left, right] = intervalCoordinates(geometry.start_ratio_decimal, geometry.end_ratio_decimal, axis.axis_min_decimal, axis.axis_max_decimal, PLOT); return left <= right ? [left, right] : [right, left] }

function F1({ view, open, tooltipId }: { view: PublicH2FinanceF1Dto; open: Open; tooltipId: string }) { return <AxisSvg label="График ликвидности">{view.segments.map((segment, index) => { const [start, end] = orderedInterval(segment.geometry, view.axis); return <ChartMark key={segment.metric_id} id={`f1-${segment.metric_id}`} tooltipId={tooltipId} label={markLabel(segment.metric_id, year(view.year), segment.value, 'available')} x={50 + start} y={20 + index * 30} width={end - start} open={open} /> })}</AxisSvg> }

function F2({ view, open, tooltipId }: { view: PublicH2FinanceF2Dto; open: Open; tooltipId: string }) { return <AxisSvg label="График структуры финансирования">{view.periods.flatMap((period, periodIndex) => { if (period.state !== 'available' || period.axis === null) return []; const values: readonly [string, PublicH2MoneyDto | null, PublicH2IntervalDto | null][] = [['Собственные средства', period.equity_1300, period.geometry_by_metric[0]], ['Долг', period.debt, period.geometry_by_metric[1]]]; return values.flatMap(([metric, value, geometry], metricIndex) => { if (value === null || geometry === null) return []; const [start, end] = intervalCoordinates(geometry.start_ratio_decimal, geometry.end_ratio_decimal, period.axis!.axis_min_decimal, period.axis!.axis_max_decimal, F2_VERTICAL_PLOT); const [bottom, top] = start <= end ? [start, end] : [end, start]; return [<ChartMark key={`${year(period.year)}-${metric}`} id={`f2-${year(period.year)}-${metricIndex}`} tooltipId={tooltipId} label={markLabel(metric, year(period.year), value, period.state)} x={46 + periodIndex * 66} y={BASE - top} width={24} height={top - bottom} open={open} />] }) })}</AxisSvg> }

function F3Panel({ label, view, metric, open, tooltipId }: { label: string; view: PublicH2FinanceF3Dto; metric: 'revenue' | 'assets'; open: Open; tooltipId: string }) {
  const summary = metric === 'revenue' ? view.revenue_summary : view.assets_summary
  const axis = summary.axis
  if (axis === null) return null
  const positioned = view.points.map((point, index) => {
    const value = metric === 'revenue' ? point.revenue_2110 : point.assets_1600
    if (value === null) return null
    return {
      id: `f3-${metric}-${year(point.year)}`,
      label: markLabel(label, year(point.year), value, 'available'),
      value,
      year: year(point.year),
      x: 45 + index * 68,
      y: BASE - decimalCoordinate(value.source_thousand_decimal, axis.axis_min_decimal, axis.axis_max_decimal, F2_VERTICAL_PLOT),
    }
  })
  const segments = positioned.slice(1).map((current, index) => {
    const previous = positioned[index]
    if (previous === null || current === null) return null
    return <line
      aria-hidden="true"
      data-h2-chart-segment={`${metric}-${previous.year}-${current.year}`}
      key={`${previous.year}-${current.year}`}
      x1={previous.x + 6}
      x2={current.x + 6}
      y1={previous.y + 6}
      y2={current.y + 6}
      stroke="currentColor"
      strokeWidth="2"
    />
  })
  return <section className="company-public-h2__chart-panel" aria-label={`${label}: отдельная шкала`}><h4>{label}</h4><AxisSvg label={`${label}: отдельная шкала`}>{segments}{positioned.map(item => item === null ? null : <ChartMark key={item.year} id={item.id} tooltipId={tooltipId} label={item.label} x={item.x} y={item.y} open={open} />)}</AxisSvg></section>
}
function F3({ view, open, tooltipId }: { view: PublicH2FinanceF3Dto; open: Open; tooltipId: string }) { return <div className="company-public-h2__chart-panels"><F3Panel label="Выручка" view={view} metric="revenue" open={open} tooltipId={tooltipId} /><F3Panel label="Активы" view={view} metric="assets" open={open} tooltipId={tooltipId} /></div> }
function F4({ view, open, tooltipId }: { view: PublicH2FinanceF4Dto; open: Open; tooltipId: string }) { const axis=view.axis; if (axis === null || view.mode !== 'per_100') return null; const values = [['Валовая прибыль', view.gross_per_100_decimal], ['Прибыль от продаж', view.operating_per_100_decimal], ['Чистая прибыль', view.net_per_100_decimal]] as const; return <AxisSvg label="Прибыль на 100 рублей выручки">{values.map(([metric, value], index) => value === null ? null : <ChartMark key={metric} id={`f4-${index}`} tooltipId={tooltipId} label={markLabel(metric, year(view.year), per100(value), 'available')} x={80 + index * 135} y={BASE - decimalCoordinate(value, axis.axis_min_decimal, axis.axis_max_decimal, 120)} open={open} />)}</AxisSvg> }

function Layer({ hostId, children }: { hostId: HostId; children: (open: Open, tooltipId: string) => ReactNode }) { const [disclosure, setDisclosure] = useState<Disclosure>(null); const [persistent, setPersistent] = useState(false); const root=useRef<HTMLElement>(null); const instance=useId().replaceAll(':',''); const tooltipId = `${hostId}-tooltip-${instance}`; const open:Open=(item, keep)=>{if(keep!==undefined)setPersistent(keep);setDisclosure(item)}; const close=()=>{setPersistent(false);setDisclosure(null)}; useEffect(()=>{const closeOutside=(event:PointerEvent)=>{if(root.current!==null&&!root.current.contains(event.target as Node)){setPersistent(false);setDisclosure(null)}};document.addEventListener('pointerdown',closeOutside);return()=>document.removeEventListener('pointerdown',closeOutside)},[]); return <section ref={root} className="company-public-h2__chart-layer" onMouseLeave={() => { if (!persistent) close() }} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null) && (!persistent || event.relatedTarget !== null)) close() }} onKeyDown={event => { if (event.key === 'Escape') close() }}>{children(open, tooltipId)}{disclosure && <p className="company-public-h2__chart-tooltip" id={tooltipId} role="tooltip">{disclosure.text}</p>}</section> }

/** Mounted only by the post-parity lazy controller into an empty factual host. */
export function FinanceChartForHost({ dto, hostId, onError }: { dto: CompanyPublicH2; hostId: HostId; onError: () => void }) {
  const child = hostId === 'finance-f1' && dto.blocks.finance_f1 ? (open: Open, tooltipId: string) => <F1 view={dto.blocks.finance_f1!} open={open} tooltipId={tooltipId} />
    : hostId === 'finance-f2' && dto.blocks.finance_f2 ? (open: Open, tooltipId: string) => <F2 view={dto.blocks.finance_f2!} open={open} tooltipId={tooltipId} />
      : hostId === 'finance-f3' && dto.blocks.finance_f3 ? (open: Open, tooltipId: string) => <F3 view={dto.blocks.finance_f3!} open={open} tooltipId={tooltipId} />
        : hostId === 'finance-f4' && dto.blocks.finance_f4 ? (open: Open, tooltipId: string) => <F4 view={dto.blocks.finance_f4!} open={open} tooltipId={tooltipId} /> : null
  if (child === null) return null
  return <FinanceChartErrorBoundary onError={onError}><Layer hostId={hostId}>{child}</Layer></FinanceChartErrorBoundary>
}
