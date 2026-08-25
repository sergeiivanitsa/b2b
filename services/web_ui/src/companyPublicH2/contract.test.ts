import { describe, expect, it } from 'vitest'
import { canonicalProjectionDigest } from './canonicalJson'
import { parseCompanyPublicH2, CompanyPublicH2ContractError } from './contract'
import { isStrictJsonInteger, isStrictJsonObject, parseStrictJson, stringifyStrictJson, type StrictJsonInteger, type StrictJsonValue } from './strictJson'
import sharedDto from '../../../../shared/fixtures/company_public_h2_contract_v1.json?raw'
import sharedCases from '../../../../shared/fixtures/company_public_h2_contract_v1_cases.json?raw'

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
