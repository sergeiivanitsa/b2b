import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import type {
  CompanyPublicH2, PublicH2ArbitrationA1Dto, PublicH2ArbitrationA2Dto, PublicH2ArbitrationA3Dto,
  PublicH2ArbitrationA4Dto, PublicH2ArbitrationA5Dto, PublicH2DetailScopeDto,
} from './contractSchema'
import {
  arbitrationAmountCoordinates, arbitrationCountCoordinate, arbitrationPercentCoordinate,
  arbitrationStackCoordinates,
} from './arbitrationGeometry'
import {
  arbitrationCount, arbitrationOutcomeLabel, arbitrationPercent, arbitrationRoleLabel, arbitrationYear,
} from './arbitrationPresentation'
import { ArbitrationChartErrorBoundary } from './ArbitrationChartErrorBoundary'

export type ArbitrationChartHostId = 'arbitration-a1' | 'arbitration-a2' | 'arbitration-a3' | 'arbitration-a4' | 'arbitration-a5'
type Disclosure = Readonly<{ id: string; text: string }> | null
type Open = (item: Disclosure, persistent?: boolean) => void
const WIDTH = 640
const LEFT = 150
const PLOT = 430
const ROW = 52
const TOP = 28
const ROLE_PATTERNS = ['diagonal', 'dots', 'cross', 'horizontal'] as const

function PatternDefs({ prefix }: { prefix: string }) {
  return <defs>
    <pattern id={`${prefix}-diagonal`} width="8" height="8" patternUnits="userSpaceOnUse"><path d="M-2 2 L2 -2 M0 8 L8 0 M6 10 L10 6" stroke="currentColor" strokeWidth="2" /></pattern>
    <pattern id={`${prefix}-dots`} width="8" height="8" patternUnits="userSpaceOnUse"><circle cx="4" cy="4" r="2" fill="currentColor" /></pattern>
    <pattern id={`${prefix}-cross`} width="10" height="10" patternUnits="userSpaceOnUse"><path d="M0 0 L10 10 M10 0 L0 10" stroke="currentColor" strokeWidth="1.5" /></pattern>
    <pattern id={`${prefix}-horizontal`} width="8" height="8" patternUnits="userSpaceOnUse"><path d="M0 2 H8 M0 6 H8" stroke="currentColor" strokeWidth="1.5" /></pattern>
  </defs>
}

function Canvas({ label, height, prefix, children }: { label: string; height: number; prefix: string; children: ReactNode }) {
  return <div className="company-public-h2__chart-viewport" data-h2-arbitration-chart-viewport>
    <svg className="company-public-h2__arbitration-chart" width={WIDTH} height={height} viewBox={`0 0 ${WIDTH} ${height}`} role="group" aria-label={label}>
      <PatternDefs prefix={prefix} />{children}
    </svg>
  </div>
}

function scopeText(scope: PublicH2DetailScopeDto): string { return scope.label }

function SvgLabel({ value, y }: { value: string; y: number }) {
  const words = value.split(' ')
  const lines: string[] = []
  for (const word of words) {
    const last = lines.at(-1)
    if (last !== undefined && `${last} ${word}`.length <= 18) lines[lines.length - 1] = `${last} ${word}`
    else lines.push(word)
  }
  return <text aria-hidden="true" x="8" y={y}>{lines.slice(0, 2).map((line, index) => <tspan x="8" dy={index === 0 ? 0 : 16} key={line}>{line}</tspan>)}</text>
}

function Mark({ id, label, tooltipId, x, y, width, height = 18, pattern, open }: { id: string; label: string; tooltipId: string; x: number; y: number; width: number; height?: number; pattern: string; open: Open }) {
  const visibleWidth = Math.max(4, width)
  const visibleHeight = Math.max(4, height)
  const hit = 44
  const item = { id, text: label }
  const disclose = () => open(item)
  return <g>
    <rect aria-hidden="true" data-h2-chart-pattern={pattern} x={x} y={y} width={visibleWidth} height={visibleHeight} fill={`url(#${pattern})`} stroke="currentColor" />
    <rect data-h2-arbitration-chart-mark={id} tabIndex={0} role="button" aria-describedby={tooltipId} aria-label={label} x={x + visibleWidth / 2 - hit / 2} y={y + visibleHeight / 2 - hit / 2} width={hit} height={hit} fill="transparent" onFocus={disclose} onMouseEnter={disclose} onPointerEnter={event => { if (event.pointerType !== 'touch') open(item, false) }} onTouchStart={() => open(item, true)} onPointerDown={event => open(item, event.pointerType === 'touch')} onClick={disclose} />
  </g>
}

function Layer({ hostId, children }: { hostId: ArbitrationChartHostId; children: (open: Open, tooltipId: string, patternPrefix: string) => ReactNode }) {
  const [disclosure, setDisclosure] = useState<Disclosure>(null)
  const [persistent, setPersistent] = useState(false)
  const root = useRef<HTMLElement>(null)
  const instance = useId().replaceAll(':', '')
  const tooltipId = `${hostId}-tooltip-${instance}`
  const patternPrefix = `${hostId}-pattern-${instance}`
  const open: Open = (item, keep) => { if (keep !== undefined) setPersistent(keep); setDisclosure(item) }
  const close = () => { setPersistent(false); setDisclosure(null) }
  useEffect(() => {
    const closeOutside = (event: PointerEvent) => { if (root.current !== null && !root.current.contains(event.target as Node)) { setPersistent(false); setDisclosure(null) } }
    document.addEventListener('pointerdown', closeOutside)
    return () => document.removeEventListener('pointerdown', closeOutside)
  }, [])
  return <section ref={root} className="company-public-h2__chart-layer" onMouseLeave={() => { if (!persistent) close() }} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null) && (!persistent || event.relatedTarget !== null)) close() }} onKeyDown={event => { if (event.key === 'Escape') close() }}>
    {children(open, tooltipId, patternPrefix)}
    {disclosure !== null && <p className="company-public-h2__chart-tooltip" id={tooltipId} role="tooltip">{disclosure.text}</p>}
  </section>
}

function A1({ view, open, tooltipId, prefix }: { view: PublicH2ArbitrationA1Dto; open: Open; tooltipId: string; prefix: string }) {
  const height = Math.max(180, TOP + view.buckets.length * ROW + 28)
  return <Canvas label="A1: арбитражная активность по наблюдаемым годам и ролям" height={height} prefix={prefix}>
    {view.buckets.map((bucket, row) => {
      const counts = [bucket.plaintiff_count, bucket.respondent_count, bucket.other_count, bucket.unattributed_count] as const
      const coordinates = arbitrationStackCoordinates(counts, bucket.total_count, PLOT)
      return <g key={arbitrationYear(bucket.year)}>
        <SvgLabel value={arbitrationYear(bucket.year)} y={TOP + row * ROW + 12} />
        {coordinates.map(([start, end], index) => {
          const detail = bucket.role_details[index]
          const pattern = `${prefix}-${ROLE_PATTERNS[index]}`
          const role = detail.role
          const label = `A1; ${arbitrationYear(bucket.year)}; ${arbitrationRoleLabel(role)}; ${arbitrationCount(counts[index])} дел; ${scopeText(detail.scope)}`
          return <Mark key={role} id={`a1-${bucket.year?.token ?? 'unknown'}-${role}`} label={label} tooltipId={tooltipId} x={LEFT + start} y={TOP + row * ROW} width={end - start} pattern={pattern} open={open} />
        })}
      </g>
    })}
  </Canvas>
}

function A23({ view, open, tooltipId, prefix }: { view: PublicH2ArbitrationA2Dto | PublicH2ArbitrationA3Dto; open: Open; tooltipId: string; prefix: string }) {
  const roles = view.view_id === 'arbitration_a2_roles'
  return <Canvas label={roles ? 'A2: роли компании в арбитражных делах' : 'A3: исходы арбитражных дел'} height={TOP + 4 * ROW + 22} prefix={prefix}>
    {view.bars.map((bar, row) => {
      const category = roles ? arbitrationRoleLabel(bar.category_id as 'plaintiff' | 'respondent' | 'other' | 'unattributed') : arbitrationOutcomeLabel(bar.category_id as 'won' | 'lost' | 'returned' | 'unknown')
      const width = bar.percent_decimal === null ? 0 : arbitrationPercentCoordinate(bar.percent_decimal, PLOT)
      const pattern = `${prefix}-${ROLE_PATTERNS[row]}`
      const label = `${roles ? 'A2' : 'A3'}; ${category}; ${arbitrationCount(bar.count)} дел; ${arbitrationPercent(bar.percent_decimal)}; ${scopeText(bar.scope)}`
      return <g key={bar.category_id}><SvgLabel value={category} y={TOP + row * ROW + 12} /><Mark id={`${roles ? 'a2' : 'a3'}-${bar.category_id}`} label={label} tooltipId={tooltipId} x={LEFT} y={TOP + row * ROW} width={width} pattern={pattern} open={open} /></g>
    })}
  </Canvas>
}

function A4({ view, open, tooltipId, prefix }: { view: PublicH2ArbitrationA4Dto; open: Open; tooltipId: string; prefix: string }) {
  const group = view.currency_groups[0]
  if (group === undefined) return null
  const height = Math.max(180, TOP + group.cases.length * ROW + 28)
  const zero = arbitrationAmountCoordinates('0', '0', group.axis.axis_min_decimal, group.axis.axis_max_decimal, PLOT)[0]
  return <Canvas label="A4: точные цены исков в рублях" height={height} prefix={prefix}>
    <line aria-hidden="true" data-h2-arbitration-zero-axis x1={LEFT + zero} x2={LEFT + zero} y1="8" y2={height - 8} stroke="currentColor" strokeWidth="2" />
    {group.cases.map((item, row) => {
      const geometry = group.case_geometries[row]
      if (geometry === undefined || item.amount === null) return null
      const [first, second] = arbitrationAmountCoordinates(geometry.geometry.start_ratio_decimal, geometry.geometry.end_ratio_decimal, group.axis.axis_min_decimal, group.axis.axis_max_decimal, PLOT)
      const start = Math.min(first, second); const end = Math.max(first, second)
      const label = `A4; ${item.case_number ?? item.case_public_id}; ${arbitrationYear(item.year)}; ${item.amount.display_exact}; ${scopeText(group.scope)}`
      return <g key={item.case_public_id}><SvgLabel value={item.case_number ?? item.case_public_id} y={TOP + row * ROW + 12} /><Mark id={`a4-${item.case_public_id}`} label={label} tooltipId={tooltipId} x={LEFT + start} y={TOP + row * ROW} width={end - start} pattern={`${prefix}-diagonal`} open={open} /></g>
    })}
  </Canvas>
}

function A5({ view, open, tooltipId, prefix }: { view: PublicH2ArbitrationA5Dto; open: Open; tooltipId: string; prefix: string }) {
  const maximum = view.groups[0]?.case_count
  if (maximum === undefined) return null
  const height = Math.max(180, TOP + view.groups.length * ROW + 28)
  return <Canvas label="A5: скрытые противоположные стороны по количеству дел" height={height} prefix={prefix}>
    {view.groups.map((group, row) => {
      const width = arbitrationCountCoordinate(group.case_count, maximum, PLOT)
      const label = `A5; ${group.display_name}; ${arbitrationCount(group.case_count)} дел; ${scopeText(group.case_scope)}`
      return <g key={group.opponent_public_id}><SvgLabel value={group.display_name} y={TOP + row * ROW + 12} /><Mark id={`a5-${group.opponent_public_id}`} label={label} tooltipId={tooltipId} x={LEFT} y={TOP + row * ROW} width={width} pattern={`${prefix}-${ROLE_PATTERNS[row % ROLE_PATTERNS.length]}`} open={open} /></g>
    })}
  </Canvas>
}

/** Mounted only by the independent post-parity arbitration lazy controller. */
export function ArbitrationChartForHost({ dto, hostId, onError }: { dto: CompanyPublicH2; hostId: ArbitrationChartHostId; onError: () => void }) {
  const child = hostId === 'arbitration-a1' && (dto.blocks.arbitration_a1?.buckets.length ?? 0) > 0 ? (open: Open, tooltipId: string, prefix: string) => <A1 view={dto.blocks.arbitration_a1!} open={open} tooltipId={tooltipId} prefix={prefix} />
    : hostId === 'arbitration-a2' && (dto.blocks.arbitration_a2?.denominator.value ?? 0n) > 0n ? (open: Open, tooltipId: string, prefix: string) => <A23 view={dto.blocks.arbitration_a2!} open={open} tooltipId={tooltipId} prefix={prefix} />
      : hostId === 'arbitration-a3' && (dto.blocks.arbitration_a3?.denominator.value ?? 0n) > 0n ? (open: Open, tooltipId: string, prefix: string) => <A23 view={dto.blocks.arbitration_a3!} open={open} tooltipId={tooltipId} prefix={prefix} />
        : hostId === 'arbitration-a4' && (dto.blocks.arbitration_a4?.currency_groups[0]?.cases.length ?? 0) > 0 ? (open: Open, tooltipId: string, prefix: string) => <A4 view={dto.blocks.arbitration_a4!} open={open} tooltipId={tooltipId} prefix={prefix} />
          : hostId === 'arbitration-a5' && (dto.blocks.arbitration_a5?.groups.length ?? 0) > 0 ? (open: Open, tooltipId: string, prefix: string) => <A5 view={dto.blocks.arbitration_a5!} open={open} tooltipId={tooltipId} prefix={prefix} /> : null
  if (child === null) return null
  return <ArbitrationChartErrorBoundary onError={onError}><Layer hostId={hostId}>{child}</Layer></ArbitrationChartErrorBoundary>
}
