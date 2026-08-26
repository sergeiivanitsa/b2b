import { describe, expect, it } from 'vitest'
import { canonicalProjectionDigest } from './canonicalJson'
import { CompanyPublicH2ContractError, parseCompanyPublicH2 } from './contract'
import { parseStrictJson } from './strictJson'
import fixture from '../../../../shared/fixtures/company_public_h2_contract_v1.json?raw'

type MutableObject = Record<string, unknown>
type Mutation = (root: MutableObject) => void

function object(value: unknown, path: string): MutableObject {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${path} must be an object`)
  return value as MutableObject
}
function array(value: unknown, path: string): unknown[] {
  if (!Array.isArray(value)) throw new Error(`${path} must be an array`)
  return value
}
function block(root: MutableObject, key: string): MutableObject {
  return object(object(root.blocks, 'blocks')[key], `blocks.${key}`)
}
function coverage(root: MutableObject, blockId: string): MutableObject {
  const item = array(root.coverage, 'coverage').map((value, index) => object(value, `coverage[${index}]`)).find(value => value.block_id === blockId)
  if (!item) throw new Error(`coverage missing: ${blockId}`)
  return item
}
function row(value: MutableObject, key: string, index: number): MutableObject {
  return object(array(value[key], key)[index], `${key}[${index}]`)
}
function setMoney(value: MutableObject, source: string, rub: string, million: string, exact: string, compact: string): void {
  Object.assign(value, { source_thousand_decimal: source, rub_decimal: rub, million_decimal: million, display_exact: exact, display_compact: compact })
}
async function rawAfter(...mutations: readonly Mutation[]): Promise<string> {
  const root = JSON.parse(fixture) as MutableObject
  mutations.forEach(mutation => mutation(root))
  root.projection_digest = '0'.repeat(64)
  root.projection_digest = await canonicalProjectionDigest(parseStrictJson(JSON.stringify(root)))
  return JSON.stringify(root)
}

const corruptions: readonly (readonly [string, Mutation])[] = [
  ['F1 exact axis', root => { object(block(root, 'finance_f1').axis, 'F1.axis').axis_max_decimal = '61' }],
  ['F1 difference arithmetic', root => { setMoney(object(block(root, 'finance_f1').difference, 'F1.difference'), '21', '21000', '0.021', '0,021 млн ₽', '0 млн ₽') }],
  ['F2 computed share', root => { row(block(root, 'finance_f2'), 'periods', 0).equity_share_decimal = '45' }],
  ['F2 fixed stacked axis', root => { object(row(block(root, 'finance_f2'), 'periods', 0).axis, 'F2.axis').axis_max_decimal = '101' }],
  ['F2 exact interval', root => { object(array(row(block(root, 'finance_f2'), 'periods', 0).geometry_by_metric, 'geometry')[1], 'F2.geometry').end_ratio_decimal = '99' }],
  ['F3 exact series axis', root => { object(object(block(root, 'finance_f3').revenue_summary, 'F3.summary').axis, 'F3.axis').axis_max_decimal = '201' }],
  ['F3 exact multiple', root => { object(block(root, 'finance_f3').revenue_summary, 'F3.summary').multiple_decimal = '2' }],
  ['F3 immediate-calendar YoY', root => { row(block(root, 'finance_f3'), 'points', 1).revenue_yoy_decimal = '1' }],
  ['F4 computed ratio', root => { block(root, 'finance_f4').gross_per_100_decimal = '41' }],
  ['F4 exact interval', root => { object(array(block(root, 'finance_f4').geometry_by_metric, 'F4.geometry')[1], 'F4.geometry[1]').end_ratio_decimal = '41' }],
  ['F5 fixed label', root => { row(block(root, 'finance_f5'), 'rows', 0).label = 'Выручка' }],
  ['F5 immediate-calendar YoY', root => { row(row(block(root, 'finance_f5'), 'rows', 0), 'cells', 1).yoy_decimal = '1' }],
  ['server-owned money display', root => { object(block(root, 'finance_f1').cash_1250, 'F1.cash').display_compact = '10 000 ₽' }],
]

describe('exact TypeScript finance semantics', () => {
  it.each(corruptions)('rejects a digest-valid %s tamper', async (_name, mutate) => {
    await expect(parseCompanyPublicH2(await rawAfter(mutate))).rejects.toBeInstanceOf(CompanyPublicH2ContractError)
  })

  it('accepts partial coverage with a non-null view', async () => {
    const raw = await rawAfter(root => {
      const item = coverage(root, 'finance_f1')
      item.state = 'partial'
      item.limitation_codes = ['receivables_collection_unassessed']
    })
    await expect(parseCompanyPublicH2(raw)).resolves.toBeTruthy()
  })

  it('accepts a missing null view with no invented limitation', async () => {
    const raw = await rawAfter(root => {
      object(root.blocks, 'blocks').finance_f1 = null
      const item = coverage(root, 'finance_f1')
      item.state = 'missing'
      item.limitation_codes = []
    })
    await expect(parseCompanyPublicH2(raw)).resolves.toBeTruthy()
  })
})
