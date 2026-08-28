import { isAbsolute, resolve } from 'node:path'
import { readFileSync } from 'node:fs'

export const CORE_PROFILE_IDS = [
  'sks_morphology_complete_v1',
  'sparse_missing_fallback_v1',
  'partial_long_limitations_v1',
  'large_n_signed_masked_v1',
] as const
export const PROFILE_IDS = [...CORE_PROFILE_IDS, 'lazy_failure_v1'] as const
export const CORE_WIDTHS = [320, 390, 768, 1024, 1199, 1200, 1440] as const
export const LAZY_HOST_IDS = [
  'finance-f1', 'finance-f2', 'finance-f3', 'finance-f4',
  'arbitration-a1', 'arbitration-a2', 'arbitration-a3', 'arbitration-a4', 'arbitration-a5',
] as const

export type CompanyCardV2ProfileId = typeof PROFILE_IDS[number]
export type CompanyCardV2LazyHostId = typeof LAZY_HOST_IDS[number]
export type CompanyCardV2E2EProfile = Readonly<{
  profile_id: CompanyCardV2ProfileId
  canonical_path: string
  wrong_slug_path: string
  expected_report_id: string
  expected_indexable: boolean
  expected_lazy_hosts: readonly CompanyCardV2LazyHostId[]
  expected_visible_text: readonly string[]
  forbidden_visible_text: readonly string[]
  lazy_failure_chunk: 'finance' | 'arbitration' | null
}>
export type CompanyCardV2E2EContract = Readonly<{
  baseUrl: string
  releaseSha: string
  manifestPath: string
  robotsPath: string
  sitemapIndexPath: string
  profiles: readonly CompanyCardV2E2EProfile[]
}>

const TOP_LEVEL_KEYS = ['profiles', 'release_sha', 'routes', 'schema_version'] as const
const ROUTE_KEYS = ['robots_path', 'sitemap_index_path'] as const
const PROFILE_KEYS = [
  'canonical_path', 'expected_indexable', 'expected_lazy_hosts', 'expected_report_id',
  'expected_visible_text', 'forbidden_visible_text', 'lazy_failure_chunk', 'profile_id',
  'wrong_slug_path',
] as const
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u
const RELEASE_SHA = /^[0-9a-f]{40}$/u
const SAFE_PATH = /^\/[A-Za-z0-9._~!$&'()*+,;=:@%/-]+$/u
const CANONICAL_COMPANY_PATH = /^\/company\/(?:[0-9]{10}|[0-9]{12})-[a-z0-9]+(?:-[a-z0-9]+)*$/u
const MAX_MANIFEST_BYTES = 1_048_576

function record(value: unknown, label: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${label} must be an object`)
  return value as Record<string, unknown>
}

function exactKeys(value: Record<string, unknown>, expected: readonly string[], label: string): void {
  const actual = Object.keys(value).sort()
  const wanted = [...expected].sort()
  if (JSON.stringify(actual) !== JSON.stringify(wanted)) throw new Error(`${label} has unknown or missing keys`)
}

function stringValue(value: unknown, label: string, maximum = 512): string {
  const hasControl = typeof value === 'string' && [...value].some(character => {
    const codePoint = character.codePointAt(0)!
    return codePoint <= 0x1f || codePoint === 0x7f
  })
  if (typeof value !== 'string' || value.length === 0 || value.length > maximum || hasControl) {
    throw new Error(`${label} must be a bounded non-control string`)
  }
  return value
}

function pathValue(value: unknown, label: string): string {
  const result = stringValue(value, label, 1024)
  if (!SAFE_PATH.test(result) || result.includes('//') || result.includes('/../') || result.includes('/./') || result.includes('?') || result.includes('#')) {
    throw new Error(`${label} must be a normalized absolute same-origin path`)
  }
  return result
}

function stringArray(value: unknown, label: string, maximum: number): readonly string[] {
  if (!Array.isArray(value) || value.length > maximum) throw new Error(`${label} must be a bounded array`)
  const result = value.map((item, index) => stringValue(item, `${label}[${index}]`, 512))
  if (new Set(result).size !== result.length) throw new Error(`${label} must be unique`)
  return Object.freeze(result)
}

function parseProfile(value: unknown, expectedId: CompanyCardV2ProfileId): CompanyCardV2E2EProfile {
  const source = record(value, `profile ${expectedId}`)
  exactKeys(source, PROFILE_KEYS, `profile ${expectedId}`)
  if (source.profile_id !== expectedId) throw new Error(`profiles must contain ${expectedId} in closed order`)
  const reportId = stringValue(source.expected_report_id, `${expectedId}.expected_report_id`, 36)
  if (!UUID.test(reportId)) throw new Error(`${expectedId}.expected_report_id must be a canonical UUID`)
  if (typeof source.expected_indexable !== 'boolean') throw new Error(`${expectedId}.expected_indexable must be boolean`)
  const lazyHosts = stringArray(source.expected_lazy_hosts, `${expectedId}.expected_lazy_hosts`, LAZY_HOST_IDS.length)
  if (lazyHosts.some(host => !(LAZY_HOST_IDS as readonly string[]).includes(host))) throw new Error(`${expectedId}.expected_lazy_hosts contains an unknown host`)
  const orderedHosts = LAZY_HOST_IDS.filter(host => lazyHosts.includes(host))
  if (JSON.stringify(lazyHosts) !== JSON.stringify(orderedHosts)) throw new Error(`${expectedId}.expected_lazy_hosts must use closed host order`)
  let failure: 'finance' | 'arbitration' | null
  if (source.lazy_failure_chunk === null) failure = null
  else if (source.lazy_failure_chunk === 'finance' || source.lazy_failure_chunk === 'arbitration') failure = source.lazy_failure_chunk
  else throw new Error(`${expectedId}.lazy_failure_chunk is invalid`)
  if (expectedId === 'lazy_failure_v1') {
    if (failure === null) throw new Error('lazy_failure_v1 must select one lazy chunk')
  } else if (failure !== null) throw new Error(`${expectedId}.lazy_failure_chunk must be null`)
  if (failure !== null && !lazyHosts.some(host => host.startsWith(failure))) throw new Error('lazy failure chunk must name an expected lazy host family')
  const canonicalPath = pathValue(source.canonical_path, `${expectedId}.canonical_path`)
  const wrongSlugPath = pathValue(source.wrong_slug_path, `${expectedId}.wrong_slug_path`)
  if (!CANONICAL_COMPANY_PATH.test(canonicalPath) || !CANONICAL_COMPANY_PATH.test(wrongSlugPath)) throw new Error(`${expectedId} paths must use the canonical Company Card boundary`)
  const visibleText = stringArray(source.expected_visible_text, `${expectedId}.expected_visible_text`, 64)
  const forbiddenText = stringArray(source.forbidden_visible_text, `${expectedId}.forbidden_visible_text`, 64)
  if (visibleText.length === 0 || forbiddenText.length === 0) throw new Error(`${expectedId} must bind visible and forbidden fixture text`)
  return Object.freeze({
    profile_id: expectedId,
    canonical_path: canonicalPath,
    wrong_slug_path: wrongSlugPath,
    expected_report_id: reportId,
    expected_indexable: source.expected_indexable,
    expected_lazy_hosts: Object.freeze(lazyHosts as CompanyCardV2LazyHostId[]),
    expected_visible_text: visibleText,
    forbidden_visible_text: forbiddenText,
    lazy_failure_chunk: failure as 'finance' | 'arbitration' | null,
  })
}

function strictLoopbackBaseUrl(raw: string | undefined): string {
  if (raw === undefined || raw === '') throw new Error('COMPANY_CARD_V2_E2E_BASE_URL is required')
  let url: URL
  try { url = new URL(raw) } catch { throw new Error('COMPANY_CARD_V2_E2E_BASE_URL must be an absolute URL') }
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || url.port === '' || url.username !== '' || url.password !== '' || url.pathname !== '/' || url.search !== '' || url.hash !== '') {
    throw new Error('COMPANY_CARD_V2_E2E_BASE_URL must be an explicit http://127.0.0.1:<port> origin')
  }
  const port = Number(url.port)
  if (!Number.isInteger(port) || port < 1 || port > 65_535) throw new Error('COMPANY_CARD_V2_E2E_BASE_URL port is invalid')
  return url.origin
}

export function parseCompanyCardV2E2EManifest(text: string, baseUrl: string, manifestPath = '<memory>'): CompanyCardV2E2EContract {
  const normalizedBaseUrl = strictLoopbackBaseUrl(baseUrl)
  if (Buffer.byteLength(text, 'utf8') > MAX_MANIFEST_BYTES || text.startsWith('\uFEFF')) throw new Error('E2E manifest is too large or has a BOM')
  let decoded: unknown
  try { decoded = JSON.parse(text) } catch { throw new Error('E2E manifest must be valid JSON') }
  const source = record(decoded, 'E2E manifest')
  exactKeys(source, TOP_LEVEL_KEYS, 'E2E manifest')
  if (source.schema_version !== 'company_card_v2_e2e_manifest_v1') throw new Error('unsupported E2E manifest schema')
  const releaseSha = stringValue(source.release_sha, 'release_sha', 40)
  if (!RELEASE_SHA.test(releaseSha)) throw new Error('release_sha must be exact lowercase 40-hex')
  const profileSources = source.profiles
  if (!Array.isArray(profileSources) || profileSources.length !== PROFILE_IDS.length) throw new Error('E2E manifest must contain the five closed profiles')
  const profiles = PROFILE_IDS.map((profileId, index) => parseProfile(profileSources[index], profileId))
  const canonical = profiles.map(profile => profile.canonical_path)
  const wrong = profiles.map(profile => profile.wrong_slug_path)
  const reportIds = profiles.map(profile => profile.expected_report_id)
  if (new Set(canonical).size !== canonical.length || new Set(wrong).size !== wrong.length || new Set(reportIds).size !== reportIds.length) {
    throw new Error('profile paths and report IDs must be unique')
  }
  if (profiles.some(profile => profile.canonical_path === profile.wrong_slug_path)) throw new Error('wrong slug path must differ from canonical path')
  const routes = record(source.routes, 'routes')
  exactKeys(routes, ROUTE_KEYS, 'routes')
  return Object.freeze({
    baseUrl: normalizedBaseUrl,
    releaseSha,
    manifestPath,
    robotsPath: pathValue(routes.robots_path, 'routes.robots_path'),
    sitemapIndexPath: pathValue(routes.sitemap_index_path, 'routes.sitemap_index_path'),
    profiles: Object.freeze(profiles),
  })
}

export function loadCompanyCardV2E2EContract(environment: Readonly<Record<string, string | undefined>>): CompanyCardV2E2EContract {
  const baseUrl = strictLoopbackBaseUrl(environment.COMPANY_CARD_V2_E2E_BASE_URL)
  const path = environment.COMPANY_CARD_V2_E2E_MANIFEST
  if (path === undefined || path === '' || !isAbsolute(path)) throw new Error('COMPANY_CARD_V2_E2E_MANIFEST must be an explicit absolute path')
  const resolved = resolve(path)
  const text = readFileSync(resolved, 'utf8')
  return parseCompanyCardV2E2EManifest(text, baseUrl, resolved)
}
