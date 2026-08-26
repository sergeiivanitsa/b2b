import { describe, expect, it } from 'vitest'
import { canonicalProjectionDigest } from './canonicalJson'
import { parseCompanyPublicH2, CompanyPublicH2ContractError } from './contract'
import { isStrictJsonInteger, isStrictJsonObject, parseStrictJson, stringifyStrictJson, type StrictJsonInteger, type StrictJsonValue } from './strictJson'
import sharedDto from '../../../../shared/fixtures/company_public_h2_contract_v1.json?raw'
import sharedCases from '../../../../shared/fixtures/company_public_h2_contract_v1_cases.json?raw'
import sharedArbitrationV3Dto from '../../../../shared/fixtures/company_public_h2_contract_v1_arbitration_masked_v3.json?raw'
import sharedClosedHtml from '../../../../shared/fixtures/company_public_h2_ssr_v1_closed.html?raw'
import { arbitrationPolicyV3Raw, arbitrationSourceLessRaw } from './arbitrationTestFixture'
import { classifyArbitrationPolicyV3 } from './arbitrationContractSemantics'

type Mutation = Readonly<{ op: 'add' | 'remove' | 'replace' | 'swap'; path: string; from?: string; raw?: string }>
type CorpusCase = Readonly<{ id: string; expect: 'accept' | 'reject'; recompute_digest: boolean; mutations: readonly Mutation[] }>
type MutableValue = null | boolean | string | StrictJsonInteger | MutableArray | MutableObject
type MutableArray = MutableValue[]
type MutableObject = { [key: string]: MutableValue }
type Mutable = MutableObject | MutableArray

function cloneTokenTree(value: StrictJsonValue): MutableValue {
  if (value === null || typeof value === 'boolean' || typeof value === 'string' || isStrictJsonInteger(value)) return value
  if (Array.isArray(value)) return value.map(cloneTokenTree)
  if (isStrictJsonObject(value)) {
    const output: MutableObject = Object.create(null)
    for (const [key, child] of Object.entries(value)) output[key] = cloneTokenTree(child)
    return output
  }
  throw new Error('unreachable strict JSON value')
}
function isMutableObject(value: MutableValue | undefined): value is MutableObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value) && !isStrictJsonInteger(value)
}
function read(parent: Mutable, key: string | number): MutableValue | undefined {
  if (Array.isArray(parent)) return typeof key === 'number' ? parent[key] : undefined
  return typeof key === 'string' ? parent[key] : undefined
}
function write(parent: Mutable, key: string | number, value: MutableValue): void {
  if (Array.isArray(parent)) {
    if (typeof key !== 'number') throw new Error('array pointer requires numeric key')
    parent[key] = value
  } else {
    if (typeof key !== 'string') throw new Error('object pointer requires string key')
    parent[key] = value
  }
}
function remove(parent: Mutable, key: string | number): void {
  if (Array.isArray(parent)) {
    if (typeof key !== 'number') throw new Error('array pointer requires numeric key')
    parent.splice(key, 1)
  } else {
    if (typeof key !== 'string') throw new Error('object pointer requires string key')
    delete parent[key]
  }
}

function at(root: MutableObject, pointer: string): [Mutable, string | number] {
  if (!pointer.startsWith('/')) throw new Error(`invalid JSON pointer: ${pointer}`)
  const parts = pointer.slice(1).split('/').map(part => part.replaceAll('~1', '/').replaceAll('~0', '~'))
  let parent: Mutable = root
  for (const part of parts.slice(0, -1)) {
    const child = read(parent, Array.isArray(parent) ? Number(part) : part)
    if (!Array.isArray(child) && !isMutableObject(child)) throw new Error(`pointer does not select a container: ${pointer}`)
    parent = child
  }
  return [parent, Array.isArray(parent) ? Number(parts.at(-1)) : parts.at(-1)!]
}
function patchValue(mutation: Mutation): MutableValue {
  if (mutation.raw === undefined) throw new Error(`${mutation.op} mutation requires raw`)
  return cloneTokenTree(parseStrictJson(mutation.raw))
}
function apply(root: MutableObject, mutation: Mutation): void {
  const [parent, key] = at(root, mutation.path)
  if (mutation.op === 'replace') write(parent, key, patchValue(mutation))
  else if (mutation.op === 'add') {
    const value = patchValue(mutation)
    if (Array.isArray(parent)) {
      if (typeof key !== 'number') throw new Error('array pointer requires numeric key')
      parent.splice(key, 0, value)
    } else write(parent, key, value)
  }
  else if (mutation.op === 'remove') remove(parent, key)
  else {
    if (!mutation.from) throw new Error('swap mutation requires from')
    const [other, otherKey] = at(root, mutation.from)
    const first = read(parent, key)
    const second = read(other, otherKey)
    if (first === undefined || second === undefined) throw new Error('swap pointer missing')
    write(parent, key, second)
    write(other, otherKey, first)
  }
}
async function rawFor(caseItem: CorpusCase): Promise<string> {
  const parsed = parseStrictJson(sharedDto)
  if (!isStrictJsonObject(parsed)) throw new Error('shared DTO root must be object')
  const value = cloneTokenTree(parsed)
  if (!isMutableObject(value)) throw new Error('shared DTO clone must be object')
  caseItem.mutations.forEach(mutation => apply(value, mutation))
  if (caseItem.recompute_digest) {
    value.projection_digest = '0'.repeat(64)
    value.projection_digest = await canonicalProjectionDigest(value)
  }
  return stringifyStrictJson(value)
}

async function resignJson(value: Record<string, unknown>): Promise<string> {
  value.projection_digest = '0'.repeat(64)
  value.projection_digest = await canonicalProjectionDigest(parseStrictJson(JSON.stringify(value)))
  return JSON.stringify(value)
}

function rewriteSafeCaseDates(value: Record<string, unknown>, startDate: string, updateDate: string, days: number | null): void {
  const stack: unknown[] = [value]
  while (stack.length > 0) {
    const current = stack.pop()
    if (Array.isArray(current)) stack.push(...current)
    else if (current !== null && typeof current === 'object') {
      const item = current as Record<string, unknown>
      if (typeof item.case_public_id === 'string' && Object.hasOwn(item, 'start_date')) {
        item.year = null
        item.start_date = startDate
        item.update_date = updateDate
        item.days_to_last_update = days
      }
      stack.push(...Object.values(item))
    }
  }
  const blocks = value.blocks as Record<string, Record<string, unknown>>
  for (const blockId of ['arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4', 'arbitration_a5']) {
    const summary = blocks[blockId].summary as Record<string, unknown>
    summary.observed_start_year = null
    summary.observed_end_year = null
    summary.unknown_year_count = 1
  }
  blocks.arbitration_a1.displayed_start_year = null
  blocks.arbitration_a1.displayed_end_year = null
  const buckets = blocks.arbitration_a1.buckets as Record<string, unknown>[]
  if (buckets[0] !== undefined) buckets[0].year = null
  const coverage = (value.coverage as Record<string, unknown>[]).find(item => item.block_id === 'arbitration_a1')
  if (coverage === undefined) throw new Error('synthetic A1 coverage missing')
  if (!(coverage.limitation_codes as string[]).includes('arbitration_unknown_year')) coverage.limitation_codes = [...(coverage.limitation_codes as string[]), 'arbitration_unknown_year']
  const limitations = value.limitations as Record<string, unknown>[]
  if (!limitations.some(item => item.code === 'arbitration_unknown_year')) limitations.push({ code: 'arbitration_unknown_year', block_id: 'arbitration_a1', field_id: null, message: 'Для части дел год не подтверждён.' })
}

function mutateVisibleCase(value: Record<string, unknown>, casePublicId: string, mutation: (item: Record<string, unknown>) => void): number {
  const stack: unknown[] = [value]
  let count = 0
  while (stack.length > 0) {
    const current = stack.pop()
    if (Array.isArray(current)) stack.push(...current)
    else if (current !== null && typeof current === 'object') {
      const item = current as Record<string, unknown>
      if (item.case_public_id === casePublicId && Object.hasOwn(item, 'start_date')) { mutation(item); count += 1 }
      stack.push(...Object.values(item))
    }
  }
  return count
}

function embeddedCompanyPublicH2State(html: string): string {
  const match = /<script id="company-public-h2-state"[^>]*>([\s\S]*?)<\/script>/u.exec(html)
  if (match === null) throw new Error('Company Public H2 embedded state is missing')
  return match[1]
}

function atomicProjectionCapFallbackDto(): Record<string, unknown> {
  const value = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
  const blocks = value.blocks as Record<string, unknown>
  for (const blockId of ['arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4', 'arbitration_a5']) blocks[blockId] = null
  const capCode = 'arbitration_public_projection_cap_exhausted'
  for (const item of value.coverage as Record<string, unknown>[]) {
    if (typeof item.block_id !== 'string' || !item.block_id.startsWith('arbitration_')) continue
    item.state = 'failed'
    item.limitation_codes = [capCode]
  }
  value.limitations = [
    ...(value.limitations as Record<string, unknown>[]).filter(item => typeof item.code !== 'string' || !item.code.startsWith('arbitration_')),
    { code: capCode, block_id: null, field_id: null, message: 'Арбитражные представления не опубликованы из-за предельного размера ответа.' },
  ]
  return value
}

function malformedOpponentOverflowDto(): Record<string, unknown> {
  const value = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
  const blocks = value.blocks as Record<string, Record<string, unknown> | null>
  blocks.arbitration_a5 = null
  for (const blockId of ['arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4']) {
    const block = blocks[blockId]
    if (block === null || block === undefined) throw new Error(`shared ${blockId} block missing`)
    const summary = block.summary as Record<string, unknown>
    Object.assign(summary, { source_total: 3, rows_observed: 3, malformed_count: 1, collection_complete: false, completion_reason: 'malformed_rows' })
    const stack: unknown[] = [block]
    while (stack.length > 0) {
      const current = stack.pop()
      if (Array.isArray(current)) stack.push(...current)
      else if (current !== null && typeof current === 'object') {
        const item = current as Record<string, unknown>
        if (Object.hasOwn(item, 'eligible_total') && Object.hasOwn(item, 'rows_received')) Object.assign(item, { population_scope: 'returned_slice', source_total: 3, rows_received: 3 })
        stack.push(...Object.values(item))
      }
    }
  }
  for (const item of value.coverage as Record<string, unknown>[]) {
    if (typeof item.block_id !== 'string' || !item.block_id.startsWith('arbitration_')) continue
    Object.assign(item, { population_scope: 'returned_slice', total: 3, returned: 3 })
    if (item.block_id === 'arbitration_a5') Object.assign(item, { state: 'failed', eligible: null, limitation_codes: ['opponent_group_cap_exhausted'] })
    else Object.assign(item, { state: 'partial', limitation_codes: ['malformed_rows', 'opponent_group_cap_exhausted', ...(item.limitation_codes as string[])] })
  }
  ;(value.limitations as Record<string, unknown>[]).push(
    { code: 'malformed_rows', block_id: null, field_id: null, message: 'Часть строк источника не прошла проверку структуры.' },
    { code: 'opponent_group_cap_exhausted', block_id: null, field_id: null, message: 'Группировка скрытых сторон недоступна из-за лимита приватности.' },
  )
  return value
}

function truncatedTopTwentySubstitutionDto(): Record<string, unknown> {
  const value = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
  const blocks = value.blocks as Record<string, Record<string, unknown>>
  const makeCase = (ordinal: number, year: number): Record<string, unknown> => ({
    case_public_id: `case_${String(ordinal).padStart(6, '0')}`,
    case_number: `А40-${100 + ordinal}/${year}`,
    year,
    role: 'plaintiff', outcome: 'won', result_detail: null,
    amount: { source_decimal: '-12.34', source_currency_id: 'RUB', display_exact: '−12,34 ₽' },
    start_date: `${year}-01-02`, update_date: `${year}-01-05`, days_to_last_update: 3,
    instance_count: null, courts: [], opponents: [], public_case_url: null,
  })
  const clone = (item: Record<string, unknown>): Record<string, unknown> => JSON.parse(JSON.stringify(item)) as Record<string, unknown>
  const cases2025 = Array.from({ length: 20 }, (_, index) => makeCase(index + 1, 2025))
  const newest = makeCase(21, 2026)
  const correctTopTwenty = [newest, ...cases2025.slice(0, 19)]
  const detailScope = (eligible: number, cases: readonly Record<string, unknown>[]): Record<string, unknown> => ({
    population_scope: 'complete_collection', source_total: 21, rows_received: 21,
    eligible_total: eligible, shown: Math.min(eligible, 20), cap: 20,
    label: `показано ${Math.min(eligible, 20)} из ${eligible} дел`,
    cases: cases.map(clone),
  })
  const scopeOnly = (eligible: number, cases: readonly Record<string, unknown>[]): Record<string, unknown> => {
    const scope = detailScope(eligible, cases)
    delete scope.cases
    return scope
  }
  for (const blockId of ['arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4', 'arbitration_a5']) {
    Object.assign(blocks[blockId].summary as Record<string, unknown>, {
      source_total: 21, rows_observed: 21, unique_case_count: 21,
      malformed_count: 0, duplicate_identical_count: 0, duplicate_conflict_count: 0,
      collection_complete: true, completion_reason: 'complete',
      observed_start_year: 2025, observed_end_year: 2026, unknown_year_count: 0,
    })
  }
  const roleDetails = (cases: readonly Record<string, unknown>[]): Record<string, unknown>[] => [
    { role: 'plaintiff', scope: scopeOnly(cases.length, cases), cases: cases.map(clone) },
    ...['respondent', 'other', 'unattributed'].map(role => ({ role, scope: scopeOnly(0, []), cases: [] })),
  ]
  const bucket = (year: number, cases: readonly Record<string, unknown>[]): Record<string, unknown> => ({
    year, plaintiff_count: cases.length, respondent_count: 0, other_count: 0, unattributed_count: 0,
    total_count: cases.length, role_details: roleDetails(cases),
  })
  Object.assign(blocks.arbitration_a1, {
    displayed_start_year: 2025, displayed_end_year: 2026, all_time_case_count: 21,
    buckets: [bucket(2025, cases2025), bucket(2026, [newest])],
  })
  const setBars = (view: Record<string, unknown>, populatedCategory: string, populatedCases: readonly Record<string, unknown>[]): void => {
    for (const bar of view.bars as Record<string, unknown>[]) {
      const populated = bar.category_id === populatedCategory
      const count = populated ? 21 : 0
      const cases = populated ? populatedCases : []
      Object.assign(bar, { count, percent_decimal: populated ? '100' : '0', scope: scopeOnly(count, cases), cases: cases.map(clone) })
    }
  }
  blocks.arbitration_a2.denominator = 21
  setBars(blocks.arbitration_a2, 'plaintiff', cases2025)
  blocks.arbitration_a3.denominator = 21
  setBars(blocks.arbitration_a3, 'won', correctTopTwenty)
  Object.assign(blocks.arbitration_a4, {
    missing_amount_count: 0, missing_currency_count: 0,
    currency_groups: [{
      source_currency_id: 'RUB', display_currency: '₽',
      axis: { axis_min_decimal: '-12.34', axis_max_decimal: '0' },
      case_geometries: correctTopTwenty.map(item => ({ case_public_id: item.case_public_id, geometry: { start_ratio_decimal: '0', end_ratio_decimal: '-12.34' } })),
      scope: scopeOnly(21, correctTopTwenty),
      cases: correctTopTwenty.map(clone),
    }],
  })
  Object.assign(blocks.arbitration_a5, {
    scope: { population_scope: 'complete_collection', source_total: 21, rows_received: 21, eligible_total: 1, shown: 1, cap: 20, label: 'показано 1 из 1 сторон' },
    cases_without_safe_opponent: 0, multi_opponent_case_count: 0,
    groups: [{
      opponent_public_id: 'opponent_000001', display_kind: 'masked_unknown', display_name: 'Сторона скрыта 1', case_count: 21,
      case_scope: scopeOnly(21, correctTopTwenty),
      cases: correctTopTwenty.map(clone),
    }],
  })
  for (const coverage of value.coverage as Record<string, unknown>[]) {
    if (typeof coverage.block_id !== 'string' || !coverage.block_id.startsWith('arbitration_')) continue
    Object.assign(coverage, {
      state: 'available', population_scope: 'complete_collection', total: 21, returned: 21,
      eligible: coverage.block_id === 'arbitration_a5' ? 1 : 21,
      limitation_codes: coverage.block_id === 'arbitration_a1' ? ['arbitration_calendar_unverified'] : [],
    })
  }
  value.limitations = [
    ...(value.limitations as Record<string, unknown>[]).filter(item => typeof item.code !== 'string' || !item.code.startsWith('arbitration_')),
    { code: 'arbitration_calendar_unverified', block_id: 'arbitration_a1', field_id: null, message: 'Календарная полнота арбитражных данных не подтверждена.' },
  ]
  return value
}

const TEST_LIMITATION_PRECEDENCE = [
  'arbitration_calendar_unverified', 'arbitration_unknown_year', 'arbitration_date_invalid',
  'arbitration_date_inversion', 'arbitration_year_conflict', 'arbitration_first_number_unavailable',
  'arbitration_first_number_identity_collision', 'arbitration_amount_missing',
  'arbitration_amount_invalid', 'arbitration_currency_missing',
  'arbitration_currency_unidentified', 'arbitration_currency_invalid',
] as const
const TEST_A1_LIMITATIONS = new Set(['arbitration_calendar_unverified', 'arbitration_unknown_year'])
const TEST_A4_LIMITATIONS = new Set([
  'arbitration_amount_missing', 'arbitration_amount_invalid', 'arbitration_currency_missing',
  'arbitration_currency_unidentified', 'arbitration_currency_invalid',
])

function appendTestArbitrationLimitation(
  value: Record<string, unknown>,
  limitation: Readonly<{ code: string; block_id: string | null; message: string; coverage_blocks: readonly string[] }>,
): void {
  const limitations = value.limitations as Record<string, unknown>[]
  limitations.push({ code: limitation.code, block_id: limitation.block_id, field_id: null, message: limitation.message })
  const group = (code: string): number => TEST_A1_LIMITATIONS.has(code) ? 0 : TEST_A4_LIMITATIONS.has(code) ? 1 : 2
  const general = limitations.filter(item => typeof item.code !== 'string' || !item.code.startsWith('arbitration_'))
  const arbitration = limitations.filter(item => typeof item.code === 'string' && item.code.startsWith('arbitration_'))
    .sort((left, right) => {
      const leftCode = left.code as string; const rightCode = right.code as string
      return group(leftCode) - group(rightCode) || (leftCode === rightCode ? 0 : leftCode < rightCode ? -1 : 1)
    })
  value.limitations = [...general, ...arbitration]
  for (const coverage of value.coverage as Record<string, unknown>[]) {
    if (typeof coverage.block_id !== 'string' || !limitation.coverage_blocks.includes(coverage.block_id)) continue
    const codes = coverage.limitation_codes as string[]
    codes.push(limitation.code)
    codes.sort((left, right) => TEST_LIMITATION_PRECEDENCE.indexOf(left as typeof TEST_LIMITATION_PRECEDENCE[number]) - TEST_LIMITATION_PRECEDENCE.indexOf(right as typeof TEST_LIMITATION_PRECEDENCE[number]))
  }
}

describe('company public H2 closed contract boundary', () => {
  it('retains arbitrary integers as BigInt tokens before any presentation work', () => {
    const parsed = parseStrictJson('{"n":90071992547409931234567890}')
    expect(isStrictJsonObject(parsed)).toBe(true)
    if (!isStrictJsonObject(parsed)) throw new Error('unreachable')
    expect(isStrictJsonInteger(parsed.n)).toBe(true)
    if (!isStrictJsonInteger(parsed.n)) throw new Error('unreachable')
    expect(parsed.n.token).toBe('90071992547409931234567890')
    expect(parsed.n.value).toBe(90071992547409931234567890n)
  })

  it('rejects an incomplete object before digest verification', async () => {
    await expect(parseCompanyPublicH2('{"contract_version":"company_public_h2_v1"}')).rejects.toBeInstanceOf(CompanyPublicH2ContractError)
  })

  it('accepts the shared dense DTO without numeric coercion', async () => {
    const parsed = await parseCompanyPublicH2(sharedDto)
    expect(parsed.dto.report_id).toBe('00000000-0000-4000-8000-000000000001')
    expect(parsed.dto.blocks).toBeTruthy()
    expect(classifyArbitrationPolicyV3(parsed.dto)).toBeNull()
  })

  it('dispatches only the exact bound policy-v3 source tuple', async () => {
    const raw = sharedArbitrationV3Dto
    const parsed = await parseCompanyPublicH2(raw)
    expect(classifyArbitrationPolicyV3(parsed.dto)).toBe('bound')

    const value = JSON.parse(raw) as Record<string, unknown>
    const sources = value.sources as Record<string, unknown>[]
    sources[2].evidence_version = 'evidence_v1'
    value.projection_digest = '0'.repeat(64)
    value.projection_digest = await canonicalProjectionDigest(parseStrictJson(JSON.stringify(value)))
    await expect(parseCompanyPublicH2(JSON.stringify(value))).rejects.toThrow(/discriminator/u)
  })

  it('rejects a frozen dense source carrying either half of the v3 source marker', async () => {
    for (const [field, marker] of [
      ['normalization_version', 'company_card_arbitration_normalization_v2'],
      ['evidence_version', 'datanewton_arbitration_registry_v2'],
    ] as const) {
      const value = JSON.parse(sharedDto) as Record<string, unknown>
      const sources = value.sources as Record<string, unknown>[]
      sources[2][field] = marker
      await expect(parseCompanyPublicH2(await resignJson(value)), field).rejects.toThrow(/discriminator/u)
    }
  })

  it('accepts every exact source-less pre-result tuple and rejects mixed state', async () => {
    const reasons = ['operation_gate_closed', 'evidence_gate_closed', 'privacy_key_unavailable', 'provider_error', 'provider_binding_invalid'] as const
    for (const reason of reasons) {
      const parsed = await parseCompanyPublicH2(await arbitrationSourceLessRaw(reason))
      expect(classifyArbitrationPolicyV3(parsed.dto)).toBe('source_less')
    }
    const value = JSON.parse(await arbitrationSourceLessRaw()) as Record<string, unknown>
    const coverage = value.coverage as Record<string, unknown>[]
    coverage.find(item => item.block_id === 'arbitration_a5')!.state = 'failed'
    value.projection_digest = '0'.repeat(64)
    value.projection_digest = await canonicalProjectionDigest(parseStrictJson(JSON.stringify(value)))
    await expect(parseCompanyPublicH2(JSON.stringify(value))).rejects.toThrow(/discriminator/u)
  })

  it('rejects every malformed all-null v3 structural candidate instead of treating it as legacy', async () => {
    for (const state of ['gate_closed', 'missing'] as const) {
      const value = JSON.parse(await arbitrationSourceLessRaw()) as Record<string, unknown>
      const coverage = value.coverage as Record<string, unknown>[]
      const legacyLimitations: Record<string, unknown>[] = []
      for (const item of coverage) {
        if (typeof item.block_id !== 'string' || !item.block_id.startsWith('arbitration_')) continue
        const code = `legacy_${item.block_id}_closed`
        item.state = state
        item.limitation_codes = [code]
        legacyLimitations.push({ code, block_id: item.block_id, field_id: null, message: 'Историческое представление закрыто.' })
      }
      value.limitations = [...(value.limitations as Record<string, unknown>[]).filter(item => item.code !== 'operation_gate_closed'), ...legacyLimitations]
      await expect(parseCompanyPublicH2(await resignJson(value))).rejects.toThrow(/discriminator/u)
    }
  })

  it('accepts the frozen closed third-source/all-null SSR state as generic legacy', async () => {
    const parsed = await parseCompanyPublicH2(embeddedCompanyPublicH2State(sharedClosedHtml))
    expect(parsed.dto.sources.some(item => item.dataset === 'arbitration')).toBe(true)
    expect(['arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4', 'arbitration_a5'].every(blockId => parsed.dto.blocks[blockId as keyof typeof parsed.dto.blocks] === null)).toBe(true)
    expect(classifyArbitrationPolicyV3(parsed.dto)).toBeNull()
  })

  it('rejects a legacy source branch carrying an exact known v3 root limitation marker', async () => {
    const value = JSON.parse(sharedDto) as Record<string, unknown>
    const limitations = value.limitations as Record<string, unknown>[]
    limitations.push({
      code: 'arbitration_calendar_unverified', block_id: 'arbitration_a1', field_id: null,
      message: 'Календарная полнота арбитражных данных не подтверждена.',
    })
    await expect(parseCompanyPublicH2(await resignJson(value))).rejects.toThrow(/discriminator/u)
  })

  it('keeps a generic legacy dense DTO with a root complete limitation outside policy-v3', async () => {
    const value = JSON.parse(sharedDto) as Record<string, unknown>
    const limitations = value.limitations as Record<string, unknown>[]
    limitations.push({ code: 'complete', block_id: null, field_id: null, message: 'Историческая выгрузка завершена.' })
    const parsed = await parseCompanyPublicH2(await resignJson(value))
    expect(classifyArbitrationPolicyV3(parsed.dto)).toBeNull()
  })

  it('keeps frozen generic report versions 1 and 2 outside the v3 discriminator', async () => {
    for (const reportVersion of ['1', '2']) {
      const value = JSON.parse(sharedDto) as Record<string, unknown>
      value.report_version = reportVersion
      value.snapshot_capability = 'legacy_read_only'
      value.indexable = false
      const parsed = await parseCompanyPublicH2(await resignJson(value))
      expect(classifyArbitrationPolicyV3(parsed.dto)).toBeNull()
    }
  })

  it('accepts exact non-null available_empty arbitration views', async () => {
    const parsed = await parseCompanyPublicH2(await arbitrationPolicyV3Raw(false))
    expect(parsed.dto.blocks.arbitration_a1?.buckets).toHaveLength(0)
    expect(parsed.dto.blocks.arbitration_a1?.summary.observed_start_year).toBeNull()
    expect(parsed.dto.blocks.arbitration_a1?.summary.observed_end_year).toBeNull()
    expect(parsed.dto.coverage.filter(item => item.block_id.startsWith('arbitration_')).every(item => item.state === 'available_empty')).toBe(true)
  })

  it('accepts an unknown-year-only population with null observed bounds', async () => {
    const value = JSON.parse(await arbitrationPolicyV3Raw()) as Record<string, unknown>
    const blocks = value.blocks as Record<string, Record<string, unknown>>
    for (const blockId of ['arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4', 'arbitration_a5']) {
      const summary = blocks[blockId].summary as Record<string, unknown>
      summary.observed_start_year = null
      summary.observed_end_year = null
      summary.unknown_year_count = 1
    }
    blocks.arbitration_a1.displayed_start_year = null
    blocks.arbitration_a1.displayed_end_year = null
    const buckets = blocks.arbitration_a1.buckets as Record<string, unknown>[]
    buckets[0].year = null
    const a1Coverage = (value.coverage as Record<string, unknown>[]).find(item => item.block_id === 'arbitration_a1')
    if (a1Coverage === undefined) throw new Error('synthetic A1 coverage missing')
    a1Coverage.limitation_codes = [...(a1Coverage.limitation_codes as string[]), 'arbitration_unknown_year']
    ;(value.limitations as Record<string, unknown>[]).push({ code: 'arbitration_unknown_year', block_id: 'arbitration_a1', field_id: null, message: 'Для части дел год не подтверждён.' })
    const stack: unknown[] = [value]
    while (stack.length > 0) {
      const current = stack.pop()
      if (Array.isArray(current)) stack.push(...current)
      else if (current !== null && typeof current === 'object') {
        const item = current as Record<string, unknown>
        if (typeof item.case_public_id === 'string' && Object.hasOwn(item, 'year')) item.year = null
        stack.push(...Object.values(item))
      }
    }
    const parsed = await parseCompanyPublicH2(await resignJson(value))
    expect(parsed.dto.blocks.arbitration_a1?.buckets[0]?.year).toBeNull()
    expect(parsed.dto.blocks.arbitration_a1?.summary.observed_start_year).toBeNull()
  })

  it('rejects a non-null A5 opponent population above the 20,000 group cap', async () => {
    const value = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const blocks = value.blocks as Record<string, Record<string, unknown>>
    const scope = blocks.arbitration_a5.scope as Record<string, unknown>
    const coverage = (value.coverage as Record<string, unknown>[]).find(item => item.block_id === 'arbitration_a5')
    if (coverage === undefined) throw new Error('shared A5 coverage missing')
    scope.eligible_total = 20_001
    scope.shown = 20
    scope.label = 'показано 20 из 20001 сторон'
    coverage.eligible = 20_001
    await expect(parseCompanyPublicH2(await resignJson(value))).rejects.toThrow(/A5 eligible opponent population exceeds cap/u)
  })

  it('rejects an atomic projection-cap fallback that preserves more than 20,000 A5 candidates', async () => {
    const value = atomicProjectionCapFallbackDto()
    const a5Coverage = (value.coverage as Record<string, unknown>[]).find(item => item.block_id === 'arbitration_a5')
    if (a5Coverage === undefined) throw new Error('shared A5 coverage missing')
    a5Coverage.eligible = 20_001
    await expect(parseCompanyPublicH2(await resignJson(value))).rejects.toThrow(/invalid atomic projection-cap counts/u)
  })

  it('rejects a positive A5 candidate count when an atomic fallback has zero cases', async () => {
    const value = atomicProjectionCapFallbackDto()
    for (const coverage of value.coverage as Record<string, unknown>[]) {
      if (coverage.block_id === 'arbitration_a1' || coverage.block_id === 'arbitration_a2' || coverage.block_id === 'arbitration_a3' || coverage.block_id === 'arbitration_a4') coverage.eligible = 0
      if (coverage.block_id === 'arbitration_a5') coverage.eligible = 1
    }
    await expect(parseCompanyPublicH2(await resignJson(value))).rejects.toThrow(/invalid atomic projection-cap counts/u)
  })

  it('rejects incomplete or non-conserving atomic projection-cap evidence', async () => {
    const cases = [
      { label: 'missing total', total: null, returned: 2, denominator: 2, message: /invalid atomic projection-cap evidence/u },
      { label: 'total below returned', total: 1, returned: 2, denominator: 2, message: /invalid atomic projection-cap evidence/u },
      { label: 'complete total mismatch', total: 3, returned: 2, denominator: 2, message: /invalid atomic projection-cap evidence/u },
      { label: 'denominator above returned', total: 2, returned: 2, denominator: 3, message: /invalid atomic projection-cap counts/u },
    ] as const
    for (const item of cases) {
      const value = atomicProjectionCapFallbackDto()
      for (const coverage of value.coverage as Record<string, unknown>[]) {
        if (typeof coverage.block_id !== 'string' || !coverage.block_id.startsWith('arbitration_')) continue
        coverage.total = item.total
        coverage.returned = item.returned
        if (['arbitration_a1', 'arbitration_a2', 'arbitration_a3'].includes(coverage.block_id)) coverage.eligible = item.denominator
      }
      await expect(parseCompanyPublicH2(await resignJson(value)), item.label).rejects.toThrow(item.message)
    }
  })

  it('rejects small incomplete and oversized empty source envelopes in normal summaries', async () => {
    const cases = [
      { raw: await arbitrationPolicyV3Raw(), total: 500, rows: 1, reason: 'storage_cap_exhausted' },
      { raw: await arbitrationPolicyV3Raw(false), total: 1_001, rows: 0, reason: 'source_total_exceeds_cap' },
    ] as const
    for (const item of cases) {
      const value = JSON.parse(item.raw) as Record<string, unknown>
      const blocks = value.blocks as Record<string, Record<string, unknown>>
      for (const blockId of ['arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4', 'arbitration_a5']) {
        const summary = blocks[blockId].summary as Record<string, unknown>
        Object.assign(summary, { source_total: item.total, rows_observed: item.rows, collection_complete: false, completion_reason: item.reason })
      }
      await expect(parseCompanyPublicH2(await resignJson(value)), `${item.total}/${item.rows}`).rejects.toThrow(/invalid policy-v3 source population/u)
    }
  })

  it('rejects small incomplete and oversized empty atomic projection-cap envelopes', async () => {
    for (const item of [{ total: 500, returned: 1 }, { total: 1_001, returned: 0 }] as const) {
      const value = atomicProjectionCapFallbackDto()
      for (const coverage of value.coverage as Record<string, unknown>[]) {
        if (typeof coverage.block_id !== 'string' || !coverage.block_id.startsWith('arbitration_')) continue
        Object.assign(coverage, { population_scope: 'returned_slice', total: item.total, returned: item.returned })
      }
      await expect(parseCompanyPublicH2(await resignJson(value)), `${item.total}/${item.returned}`).rejects.toThrow(/invalid atomic projection-cap evidence/u)
    }
  })

  it('accepts malformed_rows as the earlier primary reason when A5 also overflows', async () => {
    const parsed = await parseCompanyPublicH2(await resignJson(malformedOpponentOverflowDto()))
    expect(parsed.dto.blocks.arbitration_a1?.summary.completion_reason).toBe('malformed_rows')
    expect(parsed.dto.blocks.arbitration_a5).toBeNull()
  })

  it('rejects primary completion drift to a later coexisting opponent overflow', async () => {
    const value = malformedOpponentOverflowDto()
    const blocks = value.blocks as Record<string, Record<string, unknown> | null>
    for (const blockId of ['arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4']) {
      const block = blocks[blockId]
      if (block === null || block === undefined) throw new Error(`${blockId} block missing`)
      ;(block.summary as Record<string, unknown>).completion_reason = 'opponent_group_cap_exhausted'
    }
    await expect(parseCompanyPublicH2(await resignJson(value))).rejects.toThrow(/completion precedence disagrees/u)
  })

  it('rejects row classifications that exceed or under-classify the observed slice', async () => {
    const overclassified = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const overclassifiedBlocks = overclassified.blocks as Record<string, Record<string, unknown>>
    for (const blockId of ['arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4', 'arbitration_a5']) {
      ;(overclassifiedBlocks[blockId].summary as Record<string, unknown>).malformed_count = 1
    }
    await expect(parseCompanyPublicH2(await resignJson(overclassified)), 'base upper bound').rejects.toThrow(/invalid policy-v3 public counters/u)

    const underclassified = malformedOpponentOverflowDto()
    const underclassifiedBlocks = underclassified.blocks as Record<string, Record<string, unknown> | null>
    for (const blockId of ['arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4']) {
      const block = underclassifiedBlocks[blockId]
      if (block === null || block === undefined) throw new Error(`${blockId} block missing`)
      Object.assign(block.summary as Record<string, unknown>, {
        source_total: 2, rows_observed: 2, unique_case_count: 1, malformed_count: 0,
        completion_reason: 'opponent_group_cap_exhausted', observed_start_year: null, observed_end_year: null,
      })
    }
    for (const coverage of underclassified.coverage as Record<string, unknown>[]) {
      if (typeof coverage.block_id !== 'string' || !coverage.block_id.startsWith('arbitration_')) continue
      coverage.total = 2; coverage.returned = 2
      if (coverage.block_id !== 'arbitration_a5') coverage.limitation_codes = (coverage.limitation_codes as string[]).filter(code => code !== 'malformed_rows')
    }
    underclassified.limitations = (underclassified.limitations as Record<string, unknown>[]).filter(item => item.code !== 'malformed_rows')
    await expect(parseCompanyPublicH2(await resignJson(underclassified)), 'exact lower bound').rejects.toThrow(/row classification does not conserve/u)
  })

  it('rejects mutually exclusive storage boundary reasons', async () => {
    const value = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const blocks = value.blocks as Record<string, Record<string, unknown>>
    for (const blockId of ['arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4', 'arbitration_a5']) {
      Object.assign(blocks[blockId].summary as Record<string, unknown>, { source_total: 3, rows_observed: 3, collection_complete: false, completion_reason: 'oversized_case' })
      const stack: unknown[] = [blocks[blockId]]
      while (stack.length > 0) {
        const current = stack.pop()
        if (Array.isArray(current)) stack.push(...current)
        else if (current !== null && typeof current === 'object') {
          const item = current as Record<string, unknown>
          if (Object.hasOwn(item, 'eligible_total') && Object.hasOwn(item, 'rows_received')) Object.assign(item, { population_scope: 'returned_slice', source_total: 3, rows_received: 3 })
          stack.push(...Object.values(item))
        }
      }
    }
    for (const coverage of value.coverage as Record<string, unknown>[]) {
      if (typeof coverage.block_id !== 'string' || !coverage.block_id.startsWith('arbitration_')) continue
      Object.assign(coverage, { state: 'partial', population_scope: 'returned_slice', total: 3, returned: 3 })
      coverage.limitation_codes = ['oversized_case', 'storage_cap_exhausted', ...(coverage.limitation_codes as string[])]
    }
    ;(value.limitations as Record<string, unknown>[]).push(
      { code: 'oversized_case', block_id: null, field_id: null, message: 'Строка дела превысила допустимый безопасный размер.' },
      { code: 'storage_cap_exhausted', block_id: null, field_id: null, message: 'Сохранён безопасный префикс данных в пределах лимита.' },
    )
    await expect(parseCompanyPublicH2(await resignJson(value))).rejects.toThrow(/storage boundary limitations conflict/u)
  })

  it('rejects a consistently renumbered case ordinal above the admitted case population', async () => {
    const value = JSON.parse(sharedArbitrationV3Dto.replaceAll('"case_000002"', '"case_001000"')) as Record<string, unknown>
    await expect(parseCompanyPublicH2(await resignJson(value))).rejects.toThrow(/invalid policy-v3 public case ID/u)
  })

  it('rejects a consistently renumbered opponent ordinal above A5 eligible_total', async () => {
    const value = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const blocks = value.blocks as Record<string, Record<string, unknown>>
    const groups = blocks.arbitration_a5.groups as Record<string, unknown>[]
    const opponent = groups.find(item => item.opponent_public_id === 'opponent_000002')
    if (opponent === undefined) throw new Error('shared masked opponent missing')
    opponent.opponent_public_id = 'opponent_020000'
    opponent.display_name = 'Сторона скрыта 20000'
    await expect(parseCompanyPublicH2(await resignJson(value))).rejects.toThrow(/invalid policy-v3 masked opponent/u)
  })

  it('rejects A4 eligible and missing counters that exceed the case denominator', async () => {
    const mutations = ['eligible', 'missing_amount', 'missing_currency'] as const
    for (const mutation of mutations) {
      const value = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
      const blocks = value.blocks as Record<string, Record<string, unknown>>
      const a4 = blocks.arbitration_a4
      if (mutation === 'eligible') {
        const group = (a4.currency_groups as Record<string, unknown>[])[0]
        if (group === undefined) throw new Error('shared A4 group missing')
        group.scope = { ...(group.scope as Record<string, unknown>), eligible_total: 3, shown: 3, label: 'показано 3 из 3 дел' }
        const coverage = (value.coverage as Record<string, unknown>[]).find(item => item.block_id === 'arbitration_a4')
        if (coverage === undefined) throw new Error('shared A4 coverage missing')
        coverage.eligible = 3
      } else if (mutation === 'missing_amount') a4.missing_amount_count = 2
      else a4.missing_currency_count = 2
      await expect(parseCompanyPublicH2(await resignJson(value)), mutation).rejects.toThrow(/A4 counters exceed case population/u)
    }
  })

  it('rejects a zero-eligible A4 projection that still emits an empty RUB group', async () => {
    const value = JSON.parse(await arbitrationPolicyV3Raw(false)) as Record<string, unknown>
    const blocks = value.blocks as Record<string, Record<string, unknown>>
    const a4 = blocks.arbitration_a4
    a4.currency_groups = [{
      source_currency_id: 'RUB', display_currency: '₽',
      axis: { axis_min_decimal: '0', axis_max_decimal: '0' }, case_geometries: [],
      scope: { population_scope: 'complete_collection', source_total: 0, rows_received: 0, eligible_total: 0, shown: 0, cap: 20, label: 'показано 0 из 0 дел' },
      cases: [],
    }]
    await expect(parseCompanyPublicH2(await resignJson(value))).rejects.toThrow(/A4 currency group existence disagrees/u)
  })

  it('rejects more emitted A4 exclusion states than excluded cases can support', async () => {
    const cases = [
      {
        label: 'amount states',
        limitations: [{ code: 'arbitration_amount_invalid', message: 'Для части дел цена иска не прошла точную числовую проверку.' }],
      },
      {
        label: 'currency states',
        limitations: [
          { code: 'arbitration_currency_unidentified', message: 'Для части дел валюта цены иска не идентифицирована как рубль.' },
          { code: 'arbitration_currency_invalid', message: 'Для части дел значение валюты некорректно.' },
        ],
      },
    ] as const
    for (const item of cases) {
      const value = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
      for (const limitation of item.limitations) {
        appendTestArbitrationLimitation(value, {
          ...limitation, block_id: 'arbitration_a4', coverage_blocks: ['arbitration_a4'],
        })
      }
      await expect(parseCompanyPublicH2(await resignJson(value)), item.label).rejects.toThrow(/A4 limitation population is invalid/u)
    }
  })

  it('bounds A4 eligible and excluded populations by distinct amounts visible in A1', async () => {
    const mutateA1Case = (value: Record<string, unknown>, caseId: string, amount: unknown): void => {
      const blocks = value.blocks as Record<string, Record<string, unknown>>
      const stack: unknown[] = [blocks.arbitration_a1]
      while (stack.length > 0) {
        const current = stack.pop()
        if (Array.isArray(current)) stack.push(...current)
        else if (current !== null && typeof current === 'object') {
          const item = current as Record<string, unknown>
          if (item.case_public_id === caseId && Object.hasOwn(item, 'amount')) item.amount = amount
          stack.push(...Object.values(item))
        }
      }
    }

    const tooManyAmounts = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    mutateA1Case(tooManyAmounts, 'case_000001', { source_decimal: '5', source_currency_id: 'RUB', display_exact: '5 ₽' })
    await expect(parseCompanyPublicH2(await resignJson(tooManyAmounts)), 'eligible lower bound').rejects.toThrow(/eligible population is smaller than visible amounts/u)

    const tooManyExclusions = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    mutateA1Case(tooManyExclusions, 'case_000002', null)
    await expect(parseCompanyPublicH2(await resignJson(tooManyExclusions)), 'excluded lower bound').rejects.toThrow(/excluded population is smaller than visible amount exclusions/u)
  })

  it('rejects impossible A5 overlap, zero-group, and single-group counters', async () => {
    const overlap = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const overlapBlocks = overlap.blocks as Record<string, Record<string, unknown>>
    overlapBlocks.arbitration_a5.cases_without_safe_opponent = 2
    await expect(parseCompanyPublicH2(await resignJson(overlap)), 'overlap').rejects.toThrow(/A5 overlap counters exceed population/u)

    const zero = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const zeroBlocks = zero.blocks as Record<string, Record<string, unknown>>
    const zeroA5 = zeroBlocks.arbitration_a5
    zeroA5.scope = { ...(zeroA5.scope as Record<string, unknown>), eligible_total: 0, shown: 0, label: 'показано 0 из 0 сторон' }
    zeroA5.groups = []
    zeroA5.multi_opponent_case_count = 0
    const zeroCoverage = (zero.coverage as Record<string, unknown>[]).find(item => item.block_id === 'arbitration_a5')
    if (zeroCoverage === undefined) throw new Error('shared A5 coverage missing')
    Object.assign(zeroCoverage, { state: 'available_empty', eligible: 0 })
    await expect(parseCompanyPublicH2(await resignJson(zero)), 'zero groups').rejects.toThrow(/A5 zero-group counters disagree/u)

    const single = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const singleBlocks = single.blocks as Record<string, Record<string, unknown>>
    const singleA5 = singleBlocks.arbitration_a5
    const groups = singleA5.groups as Record<string, unknown>[]
    const sole = groups.find(item => item.opponent_public_id === 'opponent_000001')
    if (sole === undefined) throw new Error('shared single opponent missing')
    singleA5.scope = { ...(singleA5.scope as Record<string, unknown>), eligible_total: 1, shown: 1, label: 'показано 1 из 1 сторон' }
    singleA5.groups = [sole]
    singleA5.multi_opponent_case_count = 0
    const singleCoverage = (single.coverage as Record<string, unknown>[]).find(item => item.block_id === 'arbitration_a5')
    if (singleCoverage === undefined) throw new Error('shared A5 coverage missing')
    singleCoverage.eligible = 1
    await expect(parseCompanyPublicH2(await resignJson(single)), 'single group').rejects.toThrow(/A5 single-group counters disagree/u)
  })

  it('accepts the shared fully visible A5 union and membership conservation', async () => {
    const parsed = await parseCompanyPublicH2(sharedArbitrationV3Dto)
    const a5 = parsed.dto.blocks.arbitration_a5
    expect(a5?.groups.map(group => group.case_count.value)).toEqual([2n, 1n])
    expect(a5?.multi_opponent_case_count.value).toBe(1n)
  })

  it('rejects A5 visible unions and duplicate memberships that exceed declared counters', async () => {
    const unsafeGap = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const unsafeBlocks = unsafeGap.blocks as Record<string, Record<string, unknown>>
    unsafeBlocks.arbitration_a5.cases_without_safe_opponent = 1
    await expect(parseCompanyPublicH2(await resignJson(unsafeGap)), 'per-group safe population').rejects.toThrow(/group count exceeds safe-opponent population/u)

    const missingMulti = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const missingMultiBlocks = missingMulti.blocks as Record<string, Record<string, unknown>>
    missingMultiBlocks.arbitration_a5.multi_opponent_case_count = 0
    await expect(parseCompanyPublicH2(await resignJson(missingMulti)), 'displayed membership upper bound').rejects.toThrow(/displayed group membership total is impossible/u)

    const fullDrift = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const fullBlocks = fullDrift.blocks as Record<string, Record<string, unknown>>
    fullBlocks.arbitration_a5.multi_opponent_case_count = 2
    await expect(parseCompanyPublicH2(await resignJson(fullDrift)), 'full membership').rejects.toThrow(/A5 full visible memberships disagree/u)
  })

  it('enforces the displayed-membership upper bound for a truncated 20-of-21 A5 projection', async () => {
    const value = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const blocks = value.blocks as Record<string, Record<string, unknown>>
    const a5 = blocks.arbitration_a5
    const sourceGroups = a5.groups as Record<string, unknown>[]
    const template = sourceGroups.find(group => group.case_count === 2)
    if (template === undefined) throw new Error('shared two-case opponent group missing')
    a5.groups = Array.from({ length: 20 }, (_, index) => ({
      ...(JSON.parse(JSON.stringify(template)) as Record<string, unknown>),
      opponent_public_id: `opponent_${String(index + 1).padStart(6, '0')}`,
      display_name: `Сторона скрыта ${index + 1}`,
    }))
    a5.scope = { ...(a5.scope as Record<string, unknown>), eligible_total: 21, shown: 20, label: 'показано 20 из 21 сторон' }
    const coverage = (value.coverage as Record<string, unknown>[]).find(item => item.block_id === 'arbitration_a5')
    if (coverage === undefined) throw new Error('shared A5 coverage missing')
    coverage.eligible = 21
    await expect(parseCompanyPublicH2(await resignJson(value))).rejects.toThrow(/displayed group membership total is impossible/u)
  })

  it('rejects a truncated cross-view substitution outside the deterministic top 20', async () => {
    await expect(parseCompanyPublicH2(await resignJson(truncatedTopTwentySubstitutionDto()))).rejects.toThrow(/count-bar visible membership disagrees/u)
  })

  it('rejects cross-view role, outcome, and safe-opponent aggregate contradictions', async () => {
    const fullRoleDrift = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const fullRoleBlocks = fullRoleDrift.blocks as Record<string, Record<string, unknown>>
    ;(fullRoleBlocks.arbitration_a2.bars as Record<string, unknown>[])[0].count = 2
    await expect(parseCompanyPublicH2(await resignJson(fullRoleDrift)), 'fully displayed role').rejects.toThrow(/A1 and A2 role aggregates disagree/u)

    const truncatedRoleDrift = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const truncatedBlocks = truncatedRoleDrift.blocks as Record<string, Record<string, unknown>>
    for (const blockId of ['arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4', 'arbitration_a5']) {
      Object.assign(truncatedBlocks[blockId].summary as Record<string, unknown>, { source_total: 3, rows_observed: 3, unique_case_count: 3 })
    }
    ;(truncatedBlocks.arbitration_a2.bars as Record<string, unknown>[])[0].count = 3
    await expect(parseCompanyPublicH2(await resignJson(truncatedRoleDrift)), 'truncated role upper bound').rejects.toThrow(/A1 and A2 role aggregates disagree/u)

    const unknownOutcomeDrift = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const unknownBlocks = unknownOutcomeDrift.blocks as Record<string, Record<string, unknown>>
    const unknownA1 = unknownBlocks.arbitration_a1.buckets as Record<string, unknown>[]
    const unknownA2 = unknownBlocks.arbitration_a2.bars as Record<string, unknown>[]
    unknownA1[1].respondent_count = 0; unknownA1[1].other_count = 1
    unknownA2[1].count = 0; unknownA2[2].count = 1
    await expect(parseCompanyPublicH2(await resignJson(unknownOutcomeDrift)), 'unknown outcome lower bound').rejects.toThrow(/A2 roles and A3 unknown outcome aggregate disagree/u)

    const safeOpponentDrift = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const safeBlocks = safeOpponentDrift.blocks as Record<string, Record<string, unknown>>
    const safeA1 = safeBlocks.arbitration_a1.buckets as Record<string, unknown>[]
    const safeA2 = safeBlocks.arbitration_a2.bars as Record<string, unknown>[]
    const safeA3 = safeBlocks.arbitration_a3.bars as Record<string, unknown>[]
    safeA1[1].respondent_count = 0; safeA1[1].other_count = 1
    safeA2[1].count = 0; safeA2[2].count = 1
    safeA3[2].count = 0; safeA3[3].count = 1
    await expect(parseCompanyPublicH2(await resignJson(safeOpponentDrift)), 'safe opponent lower bound').rejects.toThrow(/A2 roles and A5 safe-opponent aggregate disagree/u)
  })

  it('rejects other and unattributed cases inside visible A5 opponent memberships', async () => {
    const value = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const blocks = value.blocks as Record<string, Record<string, unknown>>
    const groups = blocks.arbitration_a5.groups as Record<string, unknown>[]
    const cases = groups[0].cases as Record<string, unknown>[]
    cases[0].role = 'other'
    cases[0].outcome = 'unknown'
    await expect(parseCompanyPublicH2(await resignJson(value))).rejects.toThrow(/A5 visible case role is not opponent-eligible/u)
  })

  it('rejects visible case calendar, role/outcome, and observed-year contradictions', async () => {
    const yearMismatch = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    expect(mutateVisibleCase(yearMismatch, 'case_000002', item => { item.start_date = '2024-01-02' })).toBeGreaterThan(0)
    await expect(parseCompanyPublicH2(await resignJson(yearMismatch)), 'year/start').rejects.toThrow(/year disagrees with start date/u)

    const roleMismatch = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    expect(mutateVisibleCase(roleMismatch, 'case_000002', item => { item.role = 'other' })).toBeGreaterThan(0)
    await expect(parseCompanyPublicH2(await resignJson(roleMismatch)), 'role/outcome').rejects.toThrow(/role and outcome disagree/u)

    const outsideBounds = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    expect(mutateVisibleCase(outsideBounds, 'case_000002', item => { item.year = 2026; item.start_date = '2026-01-02'; item.update_date = '2026-01-05' })).toBeGreaterThan(0)
    await expect(parseCompanyPublicH2(await resignJson(outsideBounds)), 'observed bounds').rejects.toThrow(/year exceeds observed bounds/u)

    const missingUnknownEvidence = JSON.parse(await arbitrationPolicyV3Raw()) as Record<string, unknown>
    expect(mutateVisibleCase(missingUnknownEvidence, 'case_000001', item => { item.year = null })).toBeGreaterThan(0)
    await expect(parseCompanyPublicH2(await resignJson(missingUnknownEvidence)), 'unknown year').rejects.toThrow(/lacks unknown-year evidence/u)
  })

  it('requires a root limitation when any visible case has an inverted date interval', async () => {
    const inverted = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    expect(mutateVisibleCase(inverted, 'case_000002', item => { item.start_date = '2025-01-05'; item.update_date = '2025-01-02'; item.days_to_last_update = null })).toBeGreaterThan(0)
    await expect(parseCompanyPublicH2(await resignJson(inverted))).rejects.toThrow(/date inversion lacks limitation evidence/u)

    const admitted = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    expect(mutateVisibleCase(admitted, 'case_000002', item => { item.start_date = '2025-01-05'; item.update_date = '2025-01-02'; item.days_to_last_update = null })).toBeGreaterThan(0)
    for (const coverage of admitted.coverage as Record<string, unknown>[]) {
      if (typeof coverage.block_id !== 'string' || !coverage.block_id.startsWith('arbitration_')) continue
      const codes = coverage.limitation_codes as string[]
      const firstNumberIndex = codes.indexOf('arbitration_first_number_unavailable')
      coverage.limitation_codes = firstNumberIndex < 0 ? [...codes, 'arbitration_date_inversion'] : [...codes.slice(0, firstNumberIndex), 'arbitration_date_inversion', ...codes.slice(firstNumberIndex)]
    }
    const limitations = admitted.limitations as Record<string, unknown>[]
    const firstNumberIndex = limitations.findIndex(item => item.code === 'arbitration_first_number_unavailable')
    limitations.splice(firstNumberIndex, 0, { code: 'arbitration_date_inversion', block_id: null, field_id: null, message: 'Для части дел порядок дат не подтверждён.' })
    const parsed = await parseCompanyPublicH2(await resignJson(admitted))
    expect(parsed.dto.limitations.some(item => item.code === 'arbitration_date_inversion')).toBe(true)
  })

  it('rejects impossible date and year limitation truth when every case is visible', async () => {
    const allArbitrationBlocks = ['arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4', 'arbitration_a5'] as const
    const dateInvalid = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    expect(mutateVisibleCase(dateInvalid, 'case_000001', item => {
      item.start_date = '2025-01-01'; item.update_date = '2025-01-02'; item.days_to_last_update = 1
    })).toBeGreaterThan(0)
    appendTestArbitrationLimitation(dateInvalid, {
      code: 'arbitration_date_invalid', block_id: null, coverage_blocks: allArbitrationBlocks,
      message: 'Для части дел дата не прошла строгую проверку.',
    })
    await expect(parseCompanyPublicH2(await resignJson(dateInvalid))).rejects.toThrow(/invalid-date limitation lacks a visible candidate/u)

    const yearConflict = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    appendTestArbitrationLimitation(yearConflict, {
      code: 'arbitration_year_conflict', block_id: null, coverage_blocks: allArbitrationBlocks,
      message: 'Для части дел год не согласуется с датой начала.',
    })
    await expect(parseCompanyPublicH2(await resignJson(yearConflict))).rejects.toThrow(/year-conflict limitation lacks a visible candidate/u)

    const dateInversion = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    appendTestArbitrationLimitation(dateInversion, {
      code: 'arbitration_date_inversion', block_id: null, coverage_blocks: allArbitrationBlocks,
      message: 'Для части дел порядок дат не подтверждён.',
    })
    await expect(parseCompanyPublicH2(await resignJson(dateInversion))).rejects.toThrow(/date-inversion limitation lacks a visible candidate/u)
  })

  it('rejects more first-number limitation states than hidden or undisplayed cases can support', async () => {
    const value = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    appendTestArbitrationLimitation(value, {
      code: 'arbitration_first_number_identity_collision', block_id: null,
      coverage_blocks: ['arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4', 'arbitration_a5'],
      message: 'Номер дела скрыт из-за совпадения с приватным идентификатором.',
    })
    await expect(parseCompanyPublicH2(await resignJson(value))).rejects.toThrow(/first-number limitation population is impossible/u)
  })

  it('rejects the reviewer counterexample when observed_end_year exceeds the last A1 year', async () => {
    const value = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const blocks = value.blocks as Record<string, Record<string, unknown>>
    for (const blockId of ['arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4', 'arbitration_a5']) {
      const summary = blocks[blockId].summary as Record<string, unknown>
      summary.observed_end_year = 2026
    }
    await expect(parseCompanyPublicH2(await resignJson(value))).rejects.toThrow(/A1 observed bounds mismatch/u)
  })

  it('requires an earlier observed_start_year when A1 displays only a suffix of known years', async () => {
    const value = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const blocks = value.blocks as Record<string, Record<string, unknown>>
    for (const blockId of ['arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4', 'arbitration_a5']) {
      const summary = blocks[blockId].summary as Record<string, unknown>
      summary.source_total = 3
      summary.rows_observed = 3
      summary.unique_case_count = 3
    }
    blocks.arbitration_a1.all_time_case_count = 3
    const coverage = (value.coverage as Record<string, unknown>[]).find(item => item.block_id === 'arbitration_a1')
    if (coverage === undefined) throw new Error('shared A1 coverage missing')
    coverage.total = 3; coverage.returned = 3; coverage.eligible = 3
    for (const bucket of blocks.arbitration_a1.buckets as Record<string, unknown>[]) {
      for (const detail of bucket.role_details as Record<string, unknown>[]) {
        const detailScope = detail.scope as Record<string, unknown>
        detailScope.source_total = 3
        detailScope.rows_received = 3
      }
    }
    await expect(parseCompanyPublicH2(await resignJson(value))).rejects.toThrow(/A1 observed bounds mismatch/u)
  })

  it('requires exactly ten known-year buckets for a truncated A1 suffix', async () => {
    const value = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const blocks = value.blocks as Record<string, Record<string, unknown>>
    for (const blockId of ['arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4', 'arbitration_a5']) {
      Object.assign(blocks[blockId].summary as Record<string, unknown>, {
        source_total: 3, rows_observed: 3, unique_case_count: 3, observed_start_year: 2024,
      })
    }
    blocks.arbitration_a1.all_time_case_count = 3
    const a1Coverage = (value.coverage as Record<string, unknown>[]).find(item => item.block_id === 'arbitration_a1')
    if (a1Coverage === undefined) throw new Error('shared A1 coverage missing')
    Object.assign(a1Coverage, { total: 3, returned: 3, eligible: 3 })
    for (const bucket of blocks.arbitration_a1.buckets as Record<string, unknown>[]) {
      for (const detail of bucket.role_details as Record<string, unknown>[]) {
        Object.assign(detail.scope as Record<string, unknown>, { source_total: 3, rows_received: 3 })
      }
    }
    await expect(parseCompanyPublicH2(await resignJson(value))).rejects.toThrow(/exactly ten buckets/u)
  })

  it('rejects a visible known-year case omitted from a non-top-ten A1 projection', async () => {
    const value = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const blocks = value.blocks as Record<string, Record<string, unknown>>
    const stack: unknown[] = [blocks.arbitration_a1]
    while (stack.length > 0) {
      const current = stack.pop()
      if (Array.isArray(current)) stack.push(...current)
      else if (current !== null && typeof current === 'object') {
        const item = current as Record<string, unknown>
        if (item.case_public_id === 'case_000002') item.case_public_id = 'case_000001'
        stack.push(...Object.values(item))
      }
    }
    await expect(parseCompanyPublicH2(await resignJson(value))).rejects.toThrow(/A1 top-ten suffix/u)
  })

  it('rejects generic year ordering when A4 absolute-amount priority requires another order', async () => {
    const value = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    let larger: Record<string, unknown> | undefined
    const stack: unknown[] = [value]
    const amount = { source_decimal: '999', source_currency_id: 'RUB', display_exact: '999 ₽' }
    while (stack.length > 0) {
      const current = stack.pop()
      if (Array.isArray(current)) stack.push(...current)
      else if (current !== null && typeof current === 'object') {
        const item = current as Record<string, unknown>
        if (item.case_public_id === 'case_000001') {
          item.amount = { ...amount }
          larger ??= JSON.parse(JSON.stringify(item)) as Record<string, unknown>
        }
        stack.push(...Object.values(item))
      }
    }
    const blocks = value.blocks as Record<string, Record<string, unknown>>
    const a4 = blocks.arbitration_a4
    const group = (a4.currency_groups as Record<string, unknown>[])[0]
    const first = (group.cases as Record<string, unknown>[])[0]
    if (group === undefined || first === undefined || larger === undefined) throw new Error('shared A4 fixture is incomplete')
    group.axis = { axis_min_decimal: '-12.34', axis_max_decimal: '999' }
    group.scope = { ...(group.scope as Record<string, unknown>), eligible_total: 2, shown: 2, label: 'показано 2 из 2 дел' }
    group.cases = [first, larger]
    group.case_geometries = [
      (group.case_geometries as Record<string, unknown>[])[0],
      { case_public_id: 'case_000001', geometry: { start_ratio_decimal: '0', end_ratio_decimal: '999' } },
    ]
    a4.missing_amount_count = 0
    a4.missing_currency_count = 0
    const a4Coverage = (value.coverage as Record<string, unknown>[]).find(item => item.block_id === 'arbitration_a4')
    if (a4Coverage === undefined) throw new Error('shared A4 coverage missing')
    a4Coverage.state = 'available'
    a4Coverage.eligible = 2
    a4Coverage.limitation_codes = (a4Coverage.limitation_codes as string[]).filter(code => !['arbitration_amount_missing', 'arbitration_currency_missing'].includes(code))
    value.limitations = (value.limitations as Record<string, unknown>[]).filter(item => !['arbitration_amount_missing', 'arbitration_currency_missing'].includes(item.code as string))
    await expect(parseCompanyPublicH2(await resignJson(value))).rejects.toThrow(/A4 case details are not ordered/u)
  })

  it('accepts ISO years 0001-0099 and compares early-year duration/order without 1900 coercion', async () => {
    const ordered = JSON.parse(await arbitrationPolicyV3Raw()) as Record<string, unknown>
    rewriteSafeCaseDates(ordered, '0001-01-01', '0001-01-02', 1)
    const parsed = await parseCompanyPublicH2(await resignJson(ordered))
    expect(parsed.dto.blocks.arbitration_a4?.currency_groups[0]?.cases[0]?.days_to_last_update?.value).toBe(1n)

    const inverted = JSON.parse(await arbitrationPolicyV3Raw()) as Record<string, unknown>
    rewriteSafeCaseDates(inverted, '0001-01-02', '0001-01-01', 1)
    await expect(parseCompanyPublicH2(await resignJson(inverted))).rejects.toThrow(/duration fields disagree/u)
  })

  it('rejects every policy-v3 arbitration limitation linkage drift', async () => {
    const mutations = [
      ['arbitration_calendar_unverified', 'block_id', null],
      ['arbitration_amount_missing', 'block_id', null],
      ['arbitration_first_number_unavailable', 'block_id', 'arbitration_a1'],
      ['arbitration_calendar_unverified', 'field_id', 'unexpected_field'],
    ] as const
    for (const [code, field, replacement] of mutations) {
      const value = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
      const limitation = (value.limitations as Record<string, unknown>[]).find(item => item.code === code)
      if (limitation === undefined) throw new Error(`shared v3 limitation missing: ${code}`)
      limitation[field] = replacement
      await expect(parseCompanyPublicH2(await resignJson(value))).rejects.toThrow(/limitation linkage/u)
    }
  })

  it('enforces exact limitation messages, root order, and per-block coverage order', async () => {
    const wrongMessage = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const wrongMessageItem = (wrongMessage.limitations as Record<string, unknown>[]).find(item => item.code === 'arbitration_first_number_unavailable')
    if (wrongMessageItem === undefined) throw new Error('shared first-number limitation missing')
    wrongMessageItem.message = 'Номер дела не опубликован.'
    await expect(parseCompanyPublicH2(await resignJson(wrongMessage)), 'fixed message').rejects.toThrow(/limitation message/u)

    const wrongRootOrder = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const root = wrongRootOrder.limitations as Record<string, unknown>[]
    const calendar = root.findIndex(item => item.code === 'arbitration_calendar_unverified')
    const unknown = root.findIndex(item => item.code === 'arbitration_unknown_year')
    ;[root[calendar], root[unknown]] = [root[unknown], root[calendar]]
    await expect(parseCompanyPublicH2(await resignJson(wrongRootOrder)), 'root order').rejects.toThrow(/limitation order/u)

    const wrongCoverageOrder = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const a1Coverage = (wrongCoverageOrder.coverage as Record<string, unknown>[]).find(item => item.block_id === 'arbitration_a1')
    if (a1Coverage === undefined) throw new Error('shared A1 coverage missing')
    const codes = a1Coverage.limitation_codes as string[]
    ;[codes[0], codes[1]] = [codes[1], codes[0]]
    await expect(parseCompanyPublicH2(await resignJson(wrongCoverageOrder)), 'coverage order').rejects.toThrow(/coverage linkage/u)

    const wrongCoverageBlock = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const a2Coverage = (wrongCoverageBlock.coverage as Record<string, unknown>[]).find(item => item.block_id === 'arbitration_a2')
    if (a2Coverage === undefined) throw new Error('shared A2 coverage missing')
    a2Coverage.limitation_codes = [...(a2Coverage.limitation_codes as string[]), 'arbitration_amount_missing']
    await expect(parseCompanyPublicH2(await resignJson(wrongCoverageBlock)), 'coverage matrix').rejects.toThrow(/coverage linkage/u)
  })

  it('uses the exact Russian identity-collision message and accepts that evidence tuple', async () => {
    const value = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    for (const coverage of value.coverage as Record<string, unknown>[]) {
      if (typeof coverage.block_id === 'string' && coverage.block_id.startsWith('arbitration_')) coverage.limitation_codes = (coverage.limitation_codes as string[]).map(code => code === 'arbitration_first_number_unavailable' ? 'arbitration_first_number_identity_collision' : code)
    }
    const limitation = (value.limitations as Record<string, unknown>[]).find(item => item.code === 'arbitration_first_number_unavailable')
    if (limitation === undefined) throw new Error('shared first-number limitation missing')
    limitation.code = 'arbitration_first_number_identity_collision'
    limitation.message = 'Номер дела скрыт из-за совпадения с приватным идентификатором.'
    await expect(parseCompanyPublicH2(await resignJson(value))).resolves.toBeTruthy()

    limitation.message = 'Номер дела скрыт из-за совадения с приватным идентификатором.'
    await expect(parseCompanyPublicH2(await resignJson(value))).rejects.toThrow(/limitation message/u)
  })

  it('requires unavailable or identity-collision evidence for every visible hidden case number', async () => {
    const value = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    value.limitations = (value.limitations as Record<string, unknown>[]).filter(item => item.code !== 'arbitration_first_number_unavailable')
    for (const coverage of value.coverage as Record<string, unknown>[]) {
      if (typeof coverage.block_id === 'string' && coverage.block_id.startsWith('arbitration_')) coverage.limitation_codes = (coverage.limitation_codes as string[]).filter(code => code !== 'arbitration_first_number_unavailable')
    }
    await expect(parseCompanyPublicH2(await resignJson(value))).rejects.toThrow(/hidden case number lacks limitation evidence/u)
  })

  it('rejects a safe non-v3 limitation code referenced by admitted arbitration coverage', async () => {
    const value = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const coverage = (value.coverage as Record<string, unknown>[]).find(item => item.block_id === 'arbitration_a2')
    if (coverage === undefined) throw new Error('shared A2 coverage missing')
    coverage.limitation_codes = [...(coverage.limitation_codes as string[]), 'requisites_partial']
    await expect(parseCompanyPublicH2(await resignJson(value))).rejects.toThrow(/unknown policy-v3 arbitration limitation/u)
  })

  it('rejects removal of required calendar, unknown-year, or missing-value limitations', async () => {
    for (const code of ['arbitration_calendar_unverified', 'arbitration_unknown_year', 'arbitration_amount_missing', 'arbitration_currency_missing']) {
      const value = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
      value.limitations = (value.limitations as Record<string, unknown>[]).filter(item => item.code !== code)
      for (const coverage of value.coverage as Record<string, unknown>[]) {
        if (typeof coverage.block_id === 'string' && coverage.block_id.startsWith('arbitration_')) coverage.limitation_codes = (coverage.limitation_codes as string[]).filter(item => item !== code)
      }
      await expect(parseCompanyPublicH2(await resignJson(value)), code).rejects.toThrow(/limitation facts disagree/u)
    }
  })

  it('rejects complete counters that do not conserve returned rows', async () => {
    const value = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const blocks = value.blocks as Record<string, Record<string, unknown>>
    for (const blockId of ['arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4', 'arbitration_a5']) {
      const summary = blocks[blockId].summary as Record<string, unknown>
      summary.unique_case_count = 1
      summary.unknown_year_count = 0
    }
    await expect(parseCompanyPublicH2(await resignJson(value))).rejects.toThrow(/do not conserve rows/u)
  })

  it('rejects an emitted A1 bucket with a zero total', async () => {
    const value = JSON.parse(sharedArbitrationV3Dto) as Record<string, unknown>
    const blocks = value.blocks as Record<string, Record<string, unknown>>
    const buckets = blocks.arbitration_a1.buckets as Record<string, unknown>[]
    buckets[0].plaintiff_count = 0
    buckets[0].total_count = 0
    await expect(parseCompanyPublicH2(await resignJson(value))).rejects.toThrow(/bucket total mismatch/u)
  })

  it('rejects non-NFC contract strings before digest verification', async () => {
    const caseItem: CorpusCase = { id: 'inline_non_nfc', expect: 'reject', recompute_digest: true, mutations: [{ op: 'replace', path: '/identity/short_name', raw: '"e\\u0301"' }] }
    await expect(parseCompanyPublicH2(await rawFor(caseItem))).rejects.toBeInstanceOf(CompanyPublicH2ContractError)
  })

  it('matches the closed shared Python mutation-corpus outcomes', async () => {
    const corpus = JSON.parse(sharedCases) as { constraint_ids: string[]; cases: CorpusCase[] }
    expect(corpus.constraint_ids.length).toBeGreaterThanOrEqual(80)
    expect(new Set(corpus.constraint_ids).size).toBe(corpus.constraint_ids.length)
    expect(corpus.cases.map(item => item.id)).toEqual(corpus.constraint_ids)
    for (const item of corpus.cases) {
      const raw = await rawFor(item)
      if (item.expect === 'accept') await expect(parseCompanyPublicH2(raw)).resolves.toBeTruthy()
      else await expect(parseCompanyPublicH2(raw)).rejects.toBeInstanceOf(CompanyPublicH2ContractError)
    }
  }, 30_000)
})
