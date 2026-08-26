import { CompanyPublicH2ContractError } from './contractErrors'
import type {
  CompanyPublicH2,
  PublicH2ArbitrationA1Dto,
  PublicH2ArbitrationA2Dto,
  PublicH2ArbitrationA3Dto,
  PublicH2ArbitrationA4Dto,
  PublicH2ArbitrationA5Dto,
  PublicH2ArbitrationSummaryDto,
  PublicH2CoverageItemDto,
  PublicH2DetailScopeDto,
  PublicH2SafeCaseDetailDto,
} from './contractSchema'
import type { StrictJsonInteger } from './strictJson'

export type ArbitrationPolicyV3Branch = 'bound' | 'source_less'

const ARBITRATION_BLOCK_IDS = ['arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4', 'arbitration_a5'] as const
const ROLES = ['plaintiff', 'respondent', 'other', 'unattributed'] as const
const OUTCOMES = ['won', 'lost', 'returned', 'unknown'] as const
const PRE_RESULT_STATES = new Map<string, 'gate_closed' | 'failed'>([
  ['operation_gate_closed', 'gate_closed'],
  ['evidence_gate_closed', 'gate_closed'],
  ['privacy_key_unavailable', 'failed'],
  ['provider_error', 'failed'],
  ['provider_binding_invalid', 'failed'],
])
const COMPLETION_PRECEDENCE = [
  'operation_gate_closed', 'evidence_gate_closed', 'privacy_key_unavailable', 'provider_error',
  'provider_binding_invalid', 'lexical_transport_invalid', 'envelope_invalid', 'malformed_rows',
  'duplicate_conflict', 'oversized_case', 'storage_cap_exhausted', 'opponent_group_cap_exhausted',
  'source_total_exceeds_cap', 'complete',
] as const
const BOUND_FAILURE_REASONS = new Set(['lexical_transport_invalid', 'envelope_invalid'])
const COMPLETION_REASONS = new Set<string>(COMPLETION_PRECEDENCE)
const COLLECTION_LIMITATIONS = new Set([...COMPLETION_REASONS].filter(reason => reason !== 'complete'))
const ARBITRATION_LIMITATIONS = new Set([
  ...COLLECTION_LIMITATIONS,
  'arbitration_calendar_unverified', 'arbitration_unknown_year', 'arbitration_date_invalid',
  'arbitration_date_inversion', 'arbitration_year_conflict', 'arbitration_first_number_unavailable',
  'arbitration_first_number_identity_collision', 'arbitration_amount_missing',
  'arbitration_amount_invalid', 'arbitration_currency_missing',
  'arbitration_currency_unidentified', 'arbitration_currency_invalid',
  'arbitration_public_projection_cap_exhausted',
])
const A1_LIMITATIONS = new Set(['arbitration_calendar_unverified', 'arbitration_unknown_year'])
const A4_LIMITATIONS = new Set([
  'arbitration_amount_missing', 'arbitration_amount_invalid', 'arbitration_currency_missing',
  'arbitration_currency_unidentified', 'arbitration_currency_invalid',
])
const LIMITATION_PRECEDENCE = [
  ...COMPLETION_PRECEDENCE.slice(0, -1),
  'arbitration_calendar_unverified', 'arbitration_unknown_year', 'arbitration_date_invalid',
  'arbitration_date_inversion', 'arbitration_year_conflict', 'arbitration_first_number_unavailable',
  'arbitration_first_number_identity_collision', 'arbitration_amount_missing',
  'arbitration_amount_invalid', 'arbitration_currency_missing',
  'arbitration_currency_unidentified', 'arbitration_currency_invalid',
] as const
const LIMITATION_MESSAGES: Readonly<Record<string, string>> = {
  operation_gate_closed: 'Сбор арбитражных данных отключён операционным ограничением.',
  evidence_gate_closed: 'Арбитражные данные недоступны до подтверждения evidence gate.',
  privacy_key_unavailable: 'Арбитражные данные недоступны из-за закрытого privacy-контура.',
  provider_error: 'Подтверждённый источник арбитражных данных временно недоступен.',
  provider_binding_invalid: 'Ответ источника не прошёл проверку привязки к отчёту.',
  lexical_transport_invalid: 'Числовой транспорт ответа источника не подтверждён.',
  envelope_invalid: 'Структура ответа источника не прошла проверку.',
  malformed_rows: 'Часть строк источника не прошла проверку структуры.',
  duplicate_conflict: 'Конфликтующие дубликаты дел исключены из представления.',
  oversized_case: 'Строка дела превысила допустимый безопасный размер.',
  storage_cap_exhausted: 'Сохранён безопасный префикс данных в пределах лимита.',
  opponent_group_cap_exhausted: 'Группировка скрытых сторон недоступна из-за лимита приватности.',
  source_total_exceeds_cap: 'Источник сообщает больше дел, чем возвращено в подтверждённом срезе.',
  arbitration_calendar_unverified: 'Календарная полнота арбитражных данных не подтверждена.',
  arbitration_unknown_year: 'Для части дел год не подтверждён.',
  arbitration_date_invalid: 'Для части дел дата не прошла строгую проверку.',
  arbitration_date_inversion: 'Для части дел порядок дат не подтверждён.',
  arbitration_year_conflict: 'Для части дел год не согласуется с датой начала.',
  arbitration_first_number_unavailable: 'Для части дел безопасный номер не опубликован.',
  arbitration_first_number_identity_collision: 'Номер дела скрыт из-за совпадения с приватным идентификатором.',
  arbitration_amount_missing: 'Для части дел цена иска отсутствует.',
  arbitration_amount_invalid: 'Для части дел цена иска не прошла точную числовую проверку.',
  arbitration_currency_missing: 'Для части дел валюта цены иска отсутствует.',
  arbitration_currency_unidentified: 'Для части дел валюта цены иска не идентифицирована как рубль.',
  arbitration_currency_invalid: 'Для части дел значение валюты некорректно.',
  arbitration_public_projection_cap_exhausted: 'Арбитражные представления не опубликованы из-за предельного размера ответа.',
}
const CASE_ID = /^case_([0-9]{6})$/u
const OPPONENT_ID = /^opponent_([0-9]{6})$/u
const CASE_NUMBER = /^(?:(?:А|A)[0-9]{1,3}|СИП)-[0-9]{1,12}\/[0-9]{4}$/u
const DATE = /^([0-9]{4})-([0-9]{2})-([0-9]{2})$/u
const DECIMAL = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$/u
const MAX_ROWS = 1_000n
const MAX_SOURCE_TOTAL = 9_223_372_036_854_775_807n

type Decimal = Readonly<{ coefficient: bigint; scale: number }>

function fail(message: string): never { throw new CompanyPublicH2ContractError(message) }
function integer(value: StrictJsonInteger): bigint { return value.value }
function token(value: StrictJsonInteger | null): string | null { return value?.token ?? null }
function equalInteger(left: StrictJsonInteger | null, right: StrictJsonInteger | null): boolean { return token(left) === token(right) }
function equalStringArrays(left: readonly string[], right: readonly string[]): boolean { return left.length === right.length && left.every((value, index) => value === right[index]) }
function coverageFor(dto: CompanyPublicH2, blockId: typeof ARBITRATION_BLOCK_IDS[number]): PublicH2CoverageItemDto {
  const item = dto.coverage.find(candidate => candidate.block_id === blockId)
  return item ?? fail(`missing ${blockId} coverage`)
}
function arbitrationCoverages(dto: CompanyPublicH2): readonly PublicH2CoverageItemDto[] {
  return ARBITRATION_BLOCK_IDS.map(blockId => coverageFor(dto, blockId))
}
function exactArbitrationSource(dto: CompanyPublicH2): boolean {
  const source = dto.sources[2]
  return dto.sources.length === 3
    && source?.dataset === 'arbitration'
    && source.effective_at === null
    && source.period === null
    && source.normalization_version === 'company_card_arbitration_normalization_v2'
    && source.evidence_version === 'datanewton_arbitration_registry_v2'
}
function validFrozenSourcePrefix(dto: CompanyPublicH2): boolean {
  const [counterparty, finance] = dto.sources
  return counterparty?.dataset === 'counterparty'
    && finance?.dataset === 'finance'
    && counterparty.received_at === dto.checked_at
    && finance.received_at === dto.checked_at
    && counterparty.effective_at === null
    && finance.effective_at === null
    && counterparty.period === null
    && finance.period === null
    && counterparty.normalization_version === 'company_card_v2_v1'
    && finance.normalization_version === 'company_card_v2_v1'
    && counterparty.evidence_version === finance.evidence_version
}
function arbitrationRootLimitations(dto: CompanyPublicH2) {
  return dto.limitations.filter(item => item.block_id?.startsWith('arbitration_') === true || item.code.startsWith('arbitration_') || ARBITRATION_LIMITATIONS.has(item.code))
}
function exactSourceLess(dto: CompanyPublicH2): boolean {
  if (dto.contract_version !== 'company_public_h2_v1' || dto.report_version !== '3' || dto.snapshot_capability !== 'card_v2' || dto.sources.length !== 2 || !validFrozenSourcePrefix(dto) || dto.sources.some(item => item.dataset === 'arbitration')) return false
  if (ARBITRATION_BLOCK_IDS.some(blockId => dto.blocks[blockId] !== null)) return false
  const coverage = arbitrationCoverages(dto)
  const reason = coverage[0]?.limitation_codes[0]
  const state = reason === undefined ? undefined : PRE_RESULT_STATES.get(reason)
  if (reason === undefined || state === undefined) return false
  if (coverage.some(item => item.state !== state || item.population_scope !== 'not_applicable' || item.total !== null || item.returned !== null || item.eligible !== null || item.limitation_codes.length !== 1 || item.limitation_codes[0] !== reason)) return false
  const limitations = arbitrationRootLimitations(dto)
  return limitations.length === 1 && limitations[0]?.code === reason && limitations[0].block_id === null && limitations[0].field_id === null && limitations[0].message === LIMITATION_MESSAGES[reason]
}

function isStructuralSourceLessCandidate(dto: CompanyPublicH2): boolean {
  return dto.contract_version === 'company_public_h2_v1'
    && dto.report_version === '3'
    && dto.snapshot_capability === 'card_v2'
    && !dto.sources.some(item => item.dataset === 'arbitration')
    && ARBITRATION_BLOCK_IDS.every(blockId => dto.blocks[blockId] === null)
}

/** The public v1 wire has no mutable policy flag; only these exact tuples select v3. */
export function classifyArbitrationPolicyV3(dto: CompanyPublicH2): ArbitrationPolicyV3Branch | null {
  if (dto.contract_version === 'company_public_h2_v1' && dto.report_version === '3' && dto.snapshot_capability === 'card_v2' && exactArbitrationSource(dto)) return 'bound'
  return exactSourceLess(dto) ? 'source_less' : null
}

function hasPolicyV3Marker(dto: CompanyPublicH2): boolean {
  if (isStructuralSourceLessCandidate(dto)) return true
  if (exactArbitrationSource(dto)) return true
  if (dto.sources.some(item => item.dataset === 'arbitration' && (item.normalization_version === 'company_card_arbitration_normalization_v2' || item.evidence_version === 'datanewton_arbitration_registry_v2'))) return true
  if (dto.limitations.some(item => ARBITRATION_LIMITATIONS.has(item.code))) return true
  if (arbitrationCoverages(dto).some(item => item.limitation_codes.some(code => ARBITRATION_LIMITATIONS.has(code)))) return true
  const stack: unknown[] = ARBITRATION_BLOCK_IDS.map(blockId => dto.blocks[blockId])
  while (stack.length > 0) {
    const value = stack.pop()
    if (typeof value === 'string' && (CASE_ID.test(value) || OPPONENT_ID.test(value))) return true
    if (Array.isArray(value)) stack.push(...value)
    else if (value !== null && typeof value === 'object') stack.push(...Object.values(value))
  }
  return false
}

function parseDecimal(raw: string, path: string): Decimal {
  if (!DECIMAL.test(raw)) fail(`${path} invalid decimal`)
  const negative = raw.startsWith('-')
  const [whole, fraction = ''] = (negative ? raw.slice(1) : raw).split('.')
  const coefficient = BigInt(`${whole}${fraction}`) * (negative ? -1n : 1n)
  if (coefficient === 0n && negative) fail(`${path} negative zero`)
  return { coefficient, scale: fraction.length }
}
function scaled(value: Decimal, scale: number): bigint { return value.coefficient * 10n ** BigInt(scale - value.scale) }
function compareDecimal(left: Decimal, right: Decimal): number {
  const scale = Math.max(left.scale, right.scale)
  const a = scaled(left, scale); const b = scaled(right, scale)
  return a === b ? 0 : a < b ? -1 : 1
}
function decimalEqual(left: string, right: string): boolean { return compareDecimal(parseDecimal(left, 'decimal'), parseDecimal(right, 'decimal')) === 0 }
function canonicalFixed6(coefficient: bigint): string {
  let value = coefficient; let scale = 6
  while (scale > 0 && value % 10n === 0n) { value /= 10n; scale -= 1 }
  if (scale === 0) return value.toString()
  const negative = value < 0n; const digits = (negative ? -value : value).toString().padStart(scale + 1, '0')
  const split = digits.length - scale
  return `${negative ? '-' : ''}${digits.slice(0, split)}.${digits.slice(split)}`
}
function expectedPercentages(counts: readonly bigint[], denominator: bigint): readonly (string | null)[] {
  if (denominator === 0n) return counts.map(() => null)
  const scale = 1_000_000n
  const numerators = counts.map(count => count * 100n * scale)
  const rounded = numerators.map(value => {
    const quotient = value / denominator; const remainder = value % denominator
    return quotient + (remainder * 2n >= denominator ? 1n : 0n)
  })
  const residual = 100n * scale - rounded.reduce((sum, value) => sum + value, 0n)
  let winner = 0
  for (let index = 1; index < numerators.length; index += 1) {
    const candidateError = numerators[index] - rounded[index] * denominator
    const winnerError = numerators[winner] - rounded[winner] * denominator
    const candidateAbsolute = candidateError < 0n ? -candidateError : candidateError
    const winnerAbsolute = winnerError < 0n ? -winnerError : winnerError
    if (candidateAbsolute > winnerAbsolute) winner = index
  }
  rounded[winner] += residual
  return rounded.map(canonicalFixed6)
}
function dateDay(raw: string, path: string): number {
  const match = DATE.exec(raw)
  if (match === null) fail(`${path} invalid date`)
  const year = Number(match[1]); const month = Number(match[2]); const day = Number(match[3])
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0)
  const monthLengths = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31] as const
  if (year < 1 || month < 1 || month > 12 || day < 1 || day > monthLengths[month - 1]) fail(`${path} invalid date`)
  const previousYear = year - 1
  const daysBeforeYear = previousYear * 365 + Math.floor(previousYear / 4) - Math.floor(previousYear / 100) + Math.floor(previousYear / 400)
  const daysBeforeMonth = monthLengths.slice(0, month - 1).reduce((sum, value) => sum + value, 0)
  return daysBeforeYear + daysBeforeMonth + day - 1
}
function exactAmountDisplay(raw: string): string { return `${raw.startsWith('-') ? `−${raw.slice(1)}` : raw}`.replace('.', ',') + ' ₽' }
function caseSignature(item: PublicH2SafeCaseDetailDto): string {
  return JSON.stringify([
    item.case_public_id, item.case_number, token(item.year), item.role, item.outcome, item.result_detail,
    item.amount === null ? null : [item.amount.source_decimal, item.amount.source_currency_id, item.amount.display_exact],
    item.start_date, item.update_date, token(item.days_to_last_update), token(item.instance_count),
    item.courts, item.opponents, item.public_case_url,
  ])
}
function descendingNullableDate(left: string | null, right: string | null): number {
  return left === right ? 0 : left === null ? 1 : right === null ? -1 : right.localeCompare(left, 'en')
}
function compareDetailOrder(left: PublicH2SafeCaseDetailDto, right: PublicH2SafeCaseDetailDto): number {
  if (left.year === null && right.year !== null) return 1
  if (left.year !== null && right.year === null) return -1
  if (left.year !== null && right.year !== null && left.year.value !== right.year.value) return left.year.value > right.year.value ? -1 : 1
  return descendingNullableDate(left.start_date, right.start_date)
    || descendingNullableDate(left.update_date, right.update_date)
    || left.case_public_id.localeCompare(right.case_public_id, 'en')
}
function compareA4DetailOrder(left: PublicH2SafeCaseDetailDto, right: PublicH2SafeCaseDetailDto): number {
  if (left.amount === null || right.amount === null) fail('A4 case detail lacks an amount')
  const leftAmount = parseDecimal(left.amount.source_decimal, 'A4 amount')
  const rightAmount = parseDecimal(right.amount.source_decimal, 'A4 amount')
  const absolute = (value: Decimal): Decimal => ({ coefficient: value.coefficient < 0n ? -value.coefficient : value.coefficient, scale: value.scale })
  const absoluteOrder = compareDecimal(absolute(rightAmount), absolute(leftAmount))
  if (absoluteOrder !== 0) return absoluteOrder
  const amountOrder = compareDecimal(rightAmount, leftAmount)
  if (amountOrder !== 0) return amountOrder
  if (left.year === null && right.year !== null) return 1
  if (left.year !== null && right.year === null) return -1
  if (left.year !== null && right.year !== null && left.year.value !== right.year.value) return left.year.value > right.year.value ? -1 : 1
  return descendingNullableDate(left.update_date, right.update_date) || left.case_public_id.localeCompare(right.case_public_id, 'en')
}
type VisibleCaseEvidence = { readonly fingerprints: Map<string, string>; readonly cases: Map<string, PublicH2SafeCaseDetailDto>; hasDateInversion: boolean }
function validateSafeCase(item: PublicH2SafeCaseDetailDto, summary: PublicH2ArbitrationSummaryDto, maximumOrdinal: bigint, evidence: VisibleCaseEvidence): void {
  const match = CASE_ID.exec(item.case_public_id)
  if (match === null || BigInt(match[1]) < 1n || BigInt(match[1]) > 1_000n || BigInt(match[1]) > maximumOrdinal) fail('invalid policy-v3 public case ID')
  if (item.year === null) {
    if (integer(summary.unknown_year_count) === 0n) fail('visible policy-v3 case lacks unknown-year evidence')
  } else {
    const year = integer(item.year)
    if (summary.observed_start_year === null || summary.observed_end_year === null || year < integer(summary.observed_start_year) || year > integer(summary.observed_end_year)) fail('visible policy-v3 case year exceeds observed bounds')
    if (item.start_date !== null && year !== BigInt(item.start_date.slice(0, 4))) fail('visible policy-v3 case year disagrees with start date')
  }
  if ((item.role === 'other' || item.role === 'unattributed') && item.outcome !== 'unknown') fail('visible policy-v3 role and outcome disagree')
  if (item.case_number !== null && (!CASE_NUMBER.test(item.case_number) || [...item.case_number].length > 22 || new TextEncoder().encode(item.case_number).byteLength > 32)) fail('invalid policy-v3 case number')
  if (item.result_detail !== null || item.instance_count !== null || item.courts.length !== 0 || item.opponents.length !== 0 || item.public_case_url !== null) fail('deferred case detail escaped')
  if (item.amount !== null) {
    if (item.amount.source_currency_id !== 'RUB' || item.amount.display_exact !== exactAmountDisplay(item.amount.source_decimal)) fail('invalid policy-v3 case amount')
    parseDecimal(item.amount.source_decimal, 'case amount')
  }
  const startDay = item.start_date === null ? null : dateDay(item.start_date, 'case start date')
  const updateDay = item.update_date === null ? null : dateDay(item.update_date, 'case update date')
  if (startDay !== null && updateDay !== null && startDay > updateDay) evidence.hasDateInversion = true
  const hasSafeDuration = startDay !== null && updateDay !== null && updateDay >= startDay
  if (hasSafeDuration !== (item.days_to_last_update !== null)) fail('case duration fields disagree')
  if (hasSafeDuration && startDay !== null && updateDay !== null && item.days_to_last_update !== null) {
    const days = updateDay - startDay
    if (BigInt(days) !== integer(item.days_to_last_update)) fail('case duration mismatch')
  }
  const signature = caseSignature(item); const previous = evidence.fingerprints.get(item.case_public_id)
  if (previous !== undefined && previous !== signature) fail('public case detail is inconsistent')
  evidence.fingerprints.set(item.case_public_id, signature)
  evidence.cases.set(item.case_public_id, item)
}
function summarySignature(summary: PublicH2ArbitrationSummaryDto): string {
  return JSON.stringify([
    token(summary.source_total), token(summary.rows_observed), token(summary.unique_case_count), token(summary.malformed_count),
    token(summary.duplicate_identical_count), token(summary.duplicate_conflict_count), summary.collection_complete,
    summary.completion_reason, summary.calendar_complete, summary.calendar_scope, token(summary.calendar_start_year),
    token(summary.calendar_end_year), summary.calendar_evidence_version, token(summary.observed_start_year),
    token(summary.observed_end_year), token(summary.unknown_year_count), summary.zero_years_proven,
  ])
}
function validateSummary(summary: PublicH2ArbitrationSummaryDto): void {
  const values = [summary.rows_observed, summary.unique_case_count, summary.malformed_count, summary.duplicate_identical_count, summary.duplicate_conflict_count]
  if (values.some(value => integer(value) > MAX_ROWS) || (summary.source_total !== null && integer(summary.source_total) > MAX_SOURCE_TOTAL)) fail('arbitration summary counter exceeds bound')
  const rows = integer(summary.rows_observed)
  const unique = integer(summary.unique_case_count)
  const malformed = integer(summary.malformed_count)
  const duplicateIdentical = integer(summary.duplicate_identical_count)
  const duplicateConflict = integer(summary.duplicate_conflict_count)
  if (malformed > rows || unique > rows || duplicateIdentical > rows || duplicateConflict * 2n > rows || malformed + unique + duplicateIdentical + duplicateConflict * 2n > rows) fail('invalid policy-v3 public counters')
  if (!COMPLETION_REASONS.has(summary.completion_reason) || summary.collection_complete !== (summary.completion_reason === 'complete')) fail('arbitration completion reason mismatch')
  if (summary.calendar_complete || summary.calendar_scope !== 'unverified' || summary.calendar_start_year !== null || summary.calendar_end_year !== null || summary.calendar_evidence_version !== null || summary.zero_years_proven) fail('policy-v3 calendar must stay unverified')
  if ((summary.observed_start_year === null) !== (summary.observed_end_year === null)) fail('observed year bounds must co-occur')
  if (summary.observed_start_year !== null && summary.observed_end_year !== null && integer(summary.observed_start_year) > integer(summary.observed_end_year)) fail('observed year bounds are inverted')
  if (summary.source_total === null || integer(summary.source_total) < rows || (summary.collection_complete && integer(summary.source_total) !== rows)) fail('invalid policy-v3 source population')
  const sourceTotal = integer(summary.source_total)
  if ((sourceTotal <= MAX_ROWS && rows !== sourceTotal) || (sourceTotal > MAX_ROWS && (rows < 1n || rows > MAX_ROWS))) fail('invalid policy-v3 source population')
  if (integer(summary.unknown_year_count) > unique) fail('unknown-year count exceeds population')
  const hasObservedYear = unique > integer(summary.unknown_year_count)
  if (hasObservedYear !== (summary.observed_start_year !== null)) fail('observed year evidence disagrees with population')
  if (summary.collection_complete && (malformed !== 0n || duplicateConflict !== 0n || unique + duplicateIdentical !== rows)) fail('complete policy-v3 counters do not conserve rows')
}
function scopeLabel(scope: PublicH2DetailScopeDto, noun: 'дел' | 'сторон'): string { return `показано ${scope.shown.token} из ${scope.eligible_total.token} ${noun}` }
function validateScope(scope: PublicH2DetailScopeDto, summary: PublicH2ArbitrationSummaryDto, eligible: bigint, casesLength: number, noun: 'дел' | 'сторон'): void {
  const expectedPopulation = summary.collection_complete ? 'complete_collection' : 'returned_slice'
  const shown = eligible < 20n ? eligible : 20n
  if (scope.population_scope !== expectedPopulation || !equalInteger(scope.source_total, summary.source_total) || !equalInteger(scope.rows_received, summary.rows_observed) || integer(scope.eligible_total) !== eligible || integer(scope.shown) !== shown || integer(scope.cap) !== 20n || BigInt(casesLength) !== shown || scope.label !== scopeLabel(scope, noun)) fail('policy-v3 detail scope mismatch')
}
function validateCoverage(item: PublicH2CoverageItemDto, summary: PublicH2ArbitrationSummaryDto, eligible: bigint, expectedState?: 'available' | 'available_empty' | 'partial'): void {
  const expectedPopulation = summary.collection_complete ? 'complete_collection' : 'returned_slice'
  if (item.population_scope !== expectedPopulation || !equalInteger(item.total, summary.source_total) || !equalInteger(item.returned, summary.rows_observed) || item.eligible === null || integer(item.eligible) !== eligible) fail(`${item.block_id} coverage counts disagree`)
  const exactState = expectedState ?? (summary.collection_complete ? (eligible === 0n ? 'available_empty' : 'available') : 'partial')
  if (item.state !== exactState) fail(`${item.block_id} invalid non-null state`)
}
function validateCases(items: readonly PublicH2SafeCaseDetailDto[], scope: PublicH2DetailScopeDto, summary: PublicH2ArbitrationSummaryDto, eligible: bigint, evidence: VisibleCaseEvidence): void {
  validateScope(scope, summary, eligible, items.length, 'дел')
  const ids = new Set<string>()
  for (const item of items) {
    if (ids.has(item.case_public_id)) fail('duplicate case in detail scope')
    ids.add(item.case_public_id); validateSafeCase(item, summary, integer(summary.unique_case_count), evidence)
  }
  const expected = [...items].sort(compareDetailOrder)
  if (expected.some((item, index) => item !== items[index])) fail('policy-v3 case details are not ordered')
}
function validateA4Cases(items: readonly PublicH2SafeCaseDetailDto[], scope: PublicH2DetailScopeDto, summary: PublicH2ArbitrationSummaryDto, eligible: bigint, evidence: VisibleCaseEvidence): void {
  validateScope(scope, summary, eligible, items.length, 'дел')
  const ids = new Set<string>()
  for (const item of items) {
    if (ids.has(item.case_public_id)) fail('duplicate case in A4 detail scope')
    ids.add(item.case_public_id); validateSafeCase(item, summary, integer(summary.unique_case_count), evidence)
    if (item.amount === null) fail('A4 case detail lacks an amount')
  }
  const expected = [...items].sort(compareA4DetailOrder)
  if (expected.some((item, index) => item !== items[index])) fail('policy-v3 A4 case details are not ordered')
}
function validateA1(view: PublicH2ArbitrationA1Dto, coverage: PublicH2CoverageItemDto, evidence: VisibleCaseEvidence): void {
  validateSummary(view.summary)
  if ((integer(view.summary.unique_case_count) === 0n) !== (view.buckets.length === 0)) fail('A1 empty population mismatch')
  const years = view.buckets.filter(bucket => bucket.year !== null).map(bucket => integer(bucket.year!))
  if (years.length > 10 || years.some((year, index) => index > 0 && year <= years[index - 1]) || view.buckets.slice(0, -1).some(bucket => bucket.year === null)) fail('A1 year bucket order mismatch')
  if (years.length === 0) {
    if (view.displayed_start_year !== null || view.displayed_end_year !== null) fail('A1 empty displayed bounds mismatch')
  } else if (view.displayed_start_year === null || view.displayed_end_year === null || integer(view.displayed_start_year) !== years[0] || integer(view.displayed_end_year) !== years[years.length - 1]) fail('A1 displayed bounds mismatch')
  let displayed = 0n; let unknown = 0n
  for (const bucket of view.buckets) {
    const counts = [bucket.plaintiff_count, bucket.respondent_count, bucket.other_count, bucket.unattributed_count].map(integer)
    if (bucket.role_details.some((detail, index) => detail.role !== ROLES[index])) fail('A1 role order mismatch')
    const total = counts.reduce((sum, value) => sum + value, 0n)
    if (total === 0n || total !== integer(bucket.total_count)) fail('A1 bucket total mismatch')
    bucket.role_details.forEach((detail, index) => {
      validateCases(detail.cases, detail.scope, view.summary, counts[index], evidence)
      if (detail.cases.some(item => item.role !== detail.role || token(item.year) !== token(bucket.year))) fail('A1 detail membership mismatch')
    })
    displayed += total; if (bucket.year === null) unknown = total
  }
  const denominator = integer(view.summary.unique_case_count)
  const unknownCount = integer(view.summary.unknown_year_count)
  if (integer(view.all_time_case_count) !== denominator || displayed > denominator || unknownCount !== unknown) fail('A1 all-time reconciliation mismatch')
  if (years.length > 0) {
    const knownPopulation = denominator - unknownCount
    const displayedKnownPopulation = displayed - unknown
    const observedStart = view.summary.observed_start_year
    const observedEnd = view.summary.observed_end_year
    if (observedStart === null || observedEnd === null || integer(observedEnd) !== years[years.length - 1]
      || (displayedKnownPopulation === knownPopulation && integer(observedStart) !== years[0])
      || (displayedKnownPopulation < knownPopulation && integer(observedStart) >= years[0])) fail('A1 observed bounds mismatch')
    if (displayedKnownPopulation < knownPopulation && years.length !== 10) fail('A1 truncated known-year population must expose exactly ten buckets')
  } else if (view.summary.observed_start_year !== null || view.summary.observed_end_year !== null) fail('A1 observed bounds mismatch')
  validateCoverage(coverage, view.summary, integer(view.all_time_case_count))
}
function validateA23(view: PublicH2ArbitrationA2Dto | PublicH2ArbitrationA3Dto, coverage: PublicH2CoverageItemDto, categories: readonly string[], evidence: VisibleCaseEvidence): void {
  validateSummary(view.summary)
  if (view.bars.some((bar, index) => bar.category_id !== categories[index])) fail('arbitration bar order mismatch')
  const counts = view.bars.map(bar => integer(bar.count)); const denominator = integer(view.denominator)
  if (counts.reduce((sum, value) => sum + value, 0n) !== denominator || denominator !== integer(view.summary.unique_case_count)) fail('arbitration bar denominator mismatch')
  const expected = expectedPercentages(counts, denominator)
  view.bars.forEach((bar, index) => {
    if (bar.percent_decimal !== expected[index]) fail('arbitration bar percentage mismatch')
    validateCases(bar.cases, bar.scope, view.summary, counts[index], evidence)
    if (view.view_id === 'arbitration_a2_roles' && bar.cases.some(item => item.role !== bar.category_id)) fail('A2 case role mismatch')
    if (view.view_id === 'arbitration_a3_outcomes' && bar.cases.some(item => item.outcome !== bar.category_id)) fail('A3 case outcome mismatch')
  })
  validateCoverage(coverage, view.summary, denominator)
}
function validateA4(view: PublicH2ArbitrationA4Dto, coverage: PublicH2CoverageItemDto, evidence: VisibleCaseEvidence): void {
  validateSummary(view.summary)
  if (view.currency_groups.length > 1) fail('A4 must contain at most one RUB group')
  const group = view.currency_groups[0]
  const eligible = group === undefined ? 0n : integer(group.scope.eligible_total)
  if ((eligible === 0n) !== (group === undefined)) fail('A4 currency group existence disagrees with eligible population')
  const denominator = integer(view.summary.unique_case_count)
  const missingAmount = integer(view.missing_amount_count)
  const missingCurrency = integer(view.missing_currency_count)
  if (eligible > denominator || eligible + missingAmount > denominator || eligible + missingCurrency > denominator) fail('A4 counters exceed case population')
  if (group !== undefined) {
    if (group.source_currency_id !== 'RUB' || group.display_currency !== '₽' || group.cases.length !== group.case_geometries.length) fail('A4 currency group mismatch')
    validateA4Cases(group.cases, group.scope, view.summary, eligible, evidence)
    const values: Decimal[] = [{ coefficient: 0n, scale: 0 }]
    group.cases.forEach((item, index) => {
      const geometry = group.case_geometries[index]
      if (geometry?.case_public_id !== item.case_public_id || item.amount === null || item.amount.source_currency_id !== 'RUB') fail('A4 case geometry membership mismatch')
      const amount = parseDecimal(item.amount.source_decimal, 'A4 amount'); values.push(amount)
      if (!decimalEqual(geometry.geometry.start_ratio_decimal, '0') || !decimalEqual(geometry.geometry.end_ratio_decimal, item.amount.source_decimal)) fail('A4 geometry interval mismatch')
    })
    let minimum = values[0]; let maximum = values[0]
    for (const value of values.slice(1)) { if (compareDecimal(value, minimum) < 0) minimum = value; if (compareDecimal(value, maximum) > 0) maximum = value }
    if (compareDecimal(parseDecimal(group.axis.axis_min_decimal, 'A4 axis'), minimum) !== 0 || compareDecimal(parseDecimal(group.axis.axis_max_decimal, 'A4 axis'), maximum) !== 0) fail('A4 exact axis mismatch')
  }
  if (missingAmount > denominator || missingCurrency > denominator) fail('A4 missing counters exceed population')
  const expectedState = view.summary.collection_complete
    ? (eligible === denominator ? (eligible === 0n ? 'available_empty' : 'available') : 'partial')
    : 'partial'
  validateCoverage(coverage, view.summary, eligible, expectedState)
}
function validateA5(view: PublicH2ArbitrationA5Dto, coverage: PublicH2CoverageItemDto, evidence: VisibleCaseEvidence): void {
  validateSummary(view.summary)
  const eligible = integer(view.scope.eligible_total)
  if (eligible > 20_000n) fail('A5 eligible opponent population exceeds cap')
  validateScope(view.scope, view.summary, eligible, view.groups.length, 'сторон')
  const denominator = integer(view.summary.unique_case_count)
  const casesWithout = integer(view.cases_without_safe_opponent)
  const multiOpponent = integer(view.multi_opponent_case_count)
  if (casesWithout > denominator || multiOpponent > denominator - casesWithout) fail('A5 overlap counters exceed population')
  const safeCases = denominator - casesWithout
  const opponentIds = new Set<string>()
  const visibleMemberships = new Map<string, number>()
  let previous: typeof view.groups[number] | undefined
  for (const group of view.groups) {
    const match = OPPONENT_ID.exec(group.opponent_public_id)
    if (match === null || BigInt(match[1]) < 1n || BigInt(match[1]) > 20_000n || BigInt(match[1]) > eligible || group.display_kind !== 'masked_unknown' || group.display_name !== `Сторона скрыта ${BigInt(match[1]).toString()}` || opponentIds.has(group.opponent_public_id)) fail('invalid policy-v3 masked opponent')
    opponentIds.add(group.opponent_public_id)
    if (integer(group.case_count) === 0n || integer(group.case_count) > safeCases) fail('A5 group count exceeds safe-opponent population')
    if (previous !== undefined && (integer(previous.case_count) < integer(group.case_count) || (integer(previous.case_count) === integer(group.case_count) && previous.opponent_public_id >= group.opponent_public_id))) fail('A5 group order mismatch')
    if (group.cases.some(item => item.role !== 'plaintiff' && item.role !== 'respondent')) fail('A5 visible case role is not opponent-eligible')
    validateCases(group.cases, group.case_scope, view.summary, integer(group.case_count), evidence)
    for (const item of group.cases) visibleMemberships.set(item.case_public_id, (visibleMemberships.get(item.case_public_id) ?? 0) + 1)
    previous = group
  }
  const memberships = view.groups.reduce((sum, group) => sum + integer(group.case_count), 0n)
  if (view.groups.length > 0 && memberships > safeCases + multiOpponent * BigInt(view.groups.length - 1)) fail('A5 displayed group membership total is impossible')
  if (eligible === 0n && (casesWithout !== denominator || multiOpponent !== 0n)) fail('A5 zero-group counters disagree')
  if (eligible === 1n && (multiOpponent !== 0n || view.groups.length !== 1 || integer(view.groups[0]!.case_count) !== denominator - casesWithout)) fail('A5 single-group counters disagree')
  const visibleCases = BigInt(visibleMemberships.size)
  const visibleMultiOpponent = BigInt([...visibleMemberships.values()].filter(count => count > 1).length)
  if (casesWithout > denominator - visibleCases || visibleMultiOpponent > multiOpponent) fail('A5 visible memberships exceed counters')
  const allGroupsVisible = eligible <= 20n
  const allMembershipsVisible = allGroupsVisible && view.groups.every(group => integer(group.case_scope.shown) === integer(group.case_count))
  if (allMembershipsVisible && (casesWithout !== denominator - visibleCases || multiOpponent !== visibleMultiOpponent)) fail('A5 full visible memberships disagree')
  if ((eligible === 0n) !== (casesWithout === denominator)) fail('A5 group existence disagrees with safe population')
  if (allGroupsVisible && memberships < safeCases + multiOpponent) fail('A5 group membership total is impossible')
  validateCoverage(coverage, view.summary, eligible)
}
function validateArbitrationLimitationCatalog(dto: CompanyPublicH2): void {
  for (const item of dto.limitations) {
    if ((item.block_id?.startsWith('arbitration_') === true || item.code.startsWith('arbitration_') || item.code === 'opponent_group_cap_exhausted') && !ARBITRATION_LIMITATIONS.has(item.code)) fail('unknown policy-v3 arbitration limitation')
  }
  if (arbitrationCoverages(dto).some(item => item.limitation_codes.some(code => !ARBITRATION_LIMITATIONS.has(code)))) fail('unknown policy-v3 arbitration limitation')
  if (dto.limitations.some(item => ARBITRATION_LIMITATIONS.has(item.code) && item.message !== LIMITATION_MESSAGES[item.code])) fail('invalid policy-v3 arbitration limitation message')
}
function validateAtomicCapFallback(dto: CompanyPublicH2): boolean {
  const coverage = arbitrationCoverages(dto); const code = 'arbitration_public_projection_cap_exhausted'
  if (!ARBITRATION_BLOCK_IDS.every(blockId => dto.blocks[blockId] === null) || coverage.some(item => item.state !== 'failed' || item.limitation_codes.length !== 1 || item.limitation_codes[0] !== code)) return false
  const populationScope = coverage[0]?.population_scope
  const total = coverage[0]?.total ?? null
  const returned = coverage[0]?.returned ?? null
  if (!['complete_collection', 'returned_slice'].includes(populationScope ?? '') || total === null || returned === null || coverage.some(item => item.population_scope !== populationScope || !equalInteger(item.total, total) || !equalInteger(item.returned, returned))) fail('invalid atomic projection-cap evidence')
  const totalValue = integer(total)
  const returnedValue = integer(returned)
  if (totalValue > MAX_SOURCE_TOTAL || returnedValue > MAX_ROWS || totalValue < returnedValue || (populationScope === 'complete_collection' && totalValue !== returnedValue) || (totalValue <= MAX_ROWS && returnedValue !== totalValue) || (totalValue > MAX_ROWS && returnedValue < 1n)) fail('invalid atomic projection-cap evidence')
  const denominator = coverage[0]?.eligible
  const a4Eligible = coverage[3]?.eligible
  const a5Eligible = coverage[4]?.eligible
  if (denominator === null || denominator === undefined || !equalInteger(coverage[1]?.eligible ?? null, denominator) || !equalInteger(coverage[2]?.eligible ?? null, denominator) || integer(denominator) > returnedValue || integer(denominator) > MAX_ROWS || a4Eligible === null || a4Eligible === undefined || integer(a4Eligible) > integer(denominator) || integer(a4Eligible) > MAX_ROWS || (a5Eligible === null && populationScope !== 'returned_slice') || (a5Eligible !== null && a5Eligible !== undefined && (integer(a5Eligible) > 20_000n || (integer(denominator) === 0n && integer(a5Eligible) > 0n)))) fail('invalid atomic projection-cap counts')
  const limitations = arbitrationRootLimitations(dto)
  if (limitations.length !== 1 || limitations[0]?.code !== code || limitations[0].block_id !== null || limitations[0].field_id !== null) fail('invalid atomic projection-cap limitation')
  return true
}
function validateBoundFailure(dto: CompanyPublicH2): void {
  const coverage = arbitrationCoverages(dto); const reason = coverage[0]?.limitation_codes[0]
  if (reason === undefined || !BOUND_FAILURE_REASONS.has(reason) || coverage.some(item => item.state !== 'failed' || item.population_scope !== 'not_applicable' || item.total !== null || item.returned !== null || item.eligible !== null || item.limitation_codes.length !== 1 || item.limitation_codes[0] !== reason)) fail('invalid bound-result failure matrix')
  const limitations = arbitrationRootLimitations(dto)
  if (limitations.length !== 1 || limitations[0]?.code !== reason || limitations[0].block_id !== null || limitations[0].field_id !== null) fail('invalid bound-result root limitation')
}
function validateBound(dto: CompanyPublicH2): void {
  if (!validFrozenSourcePrefix(dto)) fail('invalid bound policy-v3 source prefix')
  validateArbitrationLimitationCatalog(dto)
  if (validateAtomicCapFallback(dto)) return
  const { arbitration_a1: a1, arbitration_a2: a2, arbitration_a3: a3, arbitration_a4: a4, arbitration_a5: a5 } = dto.blocks
  if (a1 === null && a2 === null && a3 === null && a4 === null && a5 === null) { validateBoundFailure(dto); return }
  if (a1 === null || a2 === null || a3 === null || a4 === null) fail('bound policy-v3 must project A1-A4 atomically')
  const summaries = [a1.summary, a2.summary, a3.summary, a4.summary, ...(a5 === null ? [] : [a5.summary])]
  if (new Set(summaries.map(summarySignature)).size !== 1) fail('A1-A5 summaries disagree')
  validateSummary(a1.summary)
  const denominator = integer(a1.summary.unique_case_count)
  const preliminaryEmitted = new Set(dto.limitations.filter(item => ARBITRATION_LIMITATIONS.has(item.code)).map(item => item.code))
  const hasStorageBoundary = preliminaryEmitted.has('oversized_case') || preliminaryEmitted.has('storage_cap_exhausted')
  const classifiedRows = integer(a1.summary.malformed_count) + denominator + integer(a1.summary.duplicate_identical_count) + integer(a1.summary.duplicate_conflict_count) * 2n + (hasStorageBoundary ? 1n : 0n)
  if (classifiedRows > integer(a1.summary.rows_observed) || (integer(a1.summary.duplicate_conflict_count) === 0n && !hasStorageBoundary && classifiedRows !== integer(a1.summary.rows_observed))) fail('policy-v3 row classification does not conserve observed rows')
  const displayedA1Total = a1.buckets.reduce((sum, bucket) => sum + integer(bucket.total_count), 0n)
  if (displayedA1Total > denominator) fail('A1 displayed population exceeds arbitration denominator')
  const displayedRoleCounts = [
    a1.buckets.reduce((sum, bucket) => sum + integer(bucket.plaintiff_count), 0n),
    a1.buckets.reduce((sum, bucket) => sum + integer(bucket.respondent_count), 0n),
    a1.buckets.reduce((sum, bucket) => sum + integer(bucket.other_count), 0n),
    a1.buckets.reduce((sum, bucket) => sum + integer(bucket.unattributed_count), 0n),
  ]
  const a2RoleCounts = a2.bars.map(bar => integer(bar.count))
  const undisplayedA1 = denominator - displayedA1Total
  if (displayedRoleCounts.some((displayed, index) => a2RoleCounts[index] < displayed || a2RoleCounts[index] > displayed + undisplayedA1)) fail('A1 and A2 role aggregates disagree')
  const otherOrUnattributed = a2RoleCounts[2] + a2RoleCounts[3]
  if (integer(a3.bars[3].count) < otherOrUnattributed) fail('A2 roles and A3 unknown outcome aggregate disagree')
  if (a5 !== null && integer(a5.cases_without_safe_opponent) < otherOrUnattributed) fail('A2 roles and A5 safe-opponent aggregate disagree')
  const a1VisibleCaseIds = new Set(a1.buckets.flatMap(bucket => bucket.role_details.flatMap(detail => detail.cases.map(item => item.case_public_id))))
  const a1KnownYears = a1.buckets.filter(bucket => bucket.year !== null).map(bucket => integer(bucket.year!))
  const visibleOutsideA1 = [
    ...a2.bars.flatMap(bar => bar.cases), ...a3.bars.flatMap(bar => bar.cases),
    ...(a4.currency_groups[0]?.cases ?? []), ...(a5?.groups.flatMap(group => group.cases) ?? []),
  ]
  if (visibleOutsideA1.some(item => item.year !== null && !a1VisibleCaseIds.has(item.case_public_id)
    && (a1KnownYears.length !== 10 || integer(item.year) > a1KnownYears[0]))) fail('visible known-year case contradicts the A1 top-ten suffix')
  const evidence: VisibleCaseEvidence = { fingerprints: new Map<string, string>(), cases: new Map<string, PublicH2SafeCaseDetailDto>(), hasDateInversion: false }
  validateA1(a1, coverageFor(dto, 'arbitration_a1'), evidence)
  const projectedA4Eligible = a4.currency_groups[0] === undefined ? 0n : integer(a4.currency_groups[0].scope.eligible_total)
  const a1VisibleAmounts = [...evidence.cases.values()]
  if (BigInt(a1VisibleAmounts.filter(item => item.amount !== null).length) > projectedA4Eligible) fail('policy-v3 A4 eligible population is smaller than visible amounts')
  if (projectedA4Eligible <= denominator && BigInt(a1VisibleAmounts.filter(item => item.amount === null).length) > denominator - projectedA4Eligible) fail('policy-v3 A4 excluded population is smaller than visible amount exclusions')
  validateA23(a2, coverageFor(dto, 'arbitration_a2'), ROLES, evidence)
  validateA23(a3, coverageFor(dto, 'arbitration_a3'), OUTCOMES, evidence)
  validateA4(a4, coverageFor(dto, 'arbitration_a4'), evidence)
  if (a5 === null) {
    const item = coverageFor(dto, 'arbitration_a5')
    if (item.state !== 'failed' || item.population_scope !== 'returned_slice' || !equalInteger(item.total, a1.summary.source_total) || !equalInteger(item.returned, a1.summary.rows_observed) || item.eligible !== null || item.limitation_codes.length !== 1 || item.limitation_codes[0] !== 'opponent_group_cap_exhausted') fail('A5 group-cap fallback mismatch')
  } else validateA5(a5, coverageFor(dto, 'arbitration_a5'), evidence)
  const visibleCaseIds = new Set(evidence.cases.keys())
  const visibleAmountCaseIds = new Set([...evidence.cases].filter(([, item]) => item.amount !== null).map(([caseId]) => caseId))
  const visibleMissingAmountCaseIds = new Set([...evidence.cases].filter(([, item]) => item.amount === null).map(([caseId]) => caseId))
  const a4Coverage = coverageFor(dto, 'arbitration_a4')
  if (a4Coverage.eligible === null) fail('policy-v3 A4 eligible count is missing')
  const a4Eligible = integer(a4Coverage.eligible)
  if (a4Eligible < BigInt(visibleAmountCaseIds.size) || denominator - a4Eligible < BigInt(visibleMissingAmountCaseIds.size) || (BigInt(visibleCaseIds.size) === denominator && a4Eligible !== BigInt(visibleAmountCaseIds.size))) fail('policy-v3 A4 visible population disagrees')
  for (const bucket of a1.buckets) {
    const counts = [bucket.plaintiff_count, bucket.respondent_count, bucket.other_count, bucket.unattributed_count].map(integer)
    bucket.role_details.forEach((detail, index) => {
      const count = counts[index]
      const matching = [...evidence.cases.values()]
        .filter(item => token(item.year) === token(bucket.year) && item.role === ROLES[index])
        .sort(compareDetailOrder)
      const expected = matching.slice(0, Number(count < 20n ? count : 20n)).map(item => item.case_public_id)
      const actual = detail.cases.map(item => item.case_public_id)
      if (BigInt(matching.length) > count || !equalStringArrays(actual, expected)) fail('policy-v3 A1 visible membership disagrees')
    })
  }
  for (const view of [a2, a3] as const) {
    for (const bar of view.bars) {
      const count = integer(bar.count)
      const matching = [...evidence.cases.values()]
        .filter(item => view.view_id === 'arbitration_a2_roles' ? item.role === bar.category_id : item.outcome === bar.category_id)
        .sort(compareDetailOrder)
      const expected = matching.slice(0, Number(count < 20n ? count : 20n)).map(item => item.case_public_id)
      const actual = bar.cases.map(item => item.case_public_id)
      if (BigInt(matching.length) > count || !equalStringArrays(actual, expected)) fail('policy-v3 count-bar visible membership disagrees')
    }
  }
  const expectedA4 = [...evidence.cases.values()].filter(item => item.amount !== null).sort(compareA4DetailOrder)
    .slice(0, Number(a4Eligible < 20n ? a4Eligible : 20n)).map(item => item.case_public_id)
  const actualA4 = (a4.currency_groups[0]?.cases ?? []).map(item => item.case_public_id)
  if (!equalStringArrays(actualA4, expectedA4)) fail('policy-v3 A4 visible membership disagrees')
  const referenced = new Set(arbitrationCoverages(dto).flatMap(item => item.limitation_codes.filter(code => ARBITRATION_LIMITATIONS.has(code))))
  const arbitrationLimitations = dto.limitations.filter(item => ARBITRATION_LIMITATIONS.has(item.code))
  const emitted = new Set(arbitrationLimitations.map(item => item.code))
  if (referenced.size !== emitted.size || [...referenced].some(code => !emitted.has(code)) || emitted.has('arbitration_public_projection_cap_exhausted')) fail('policy-v3 arbitration limitations are not exact')
  const limitationGroup = (code: string): number => A1_LIMITATIONS.has(code) ? 0 : A4_LIMITATIONS.has(code) ? 1 : 2
  const expectedRootOrder = [...emitted].sort((left, right) => limitationGroup(left) - limitationGroup(right) || (left === right ? 0 : left < right ? -1 : 1))
  if (arbitrationLimitations.some((item, index) => item.code !== expectedRootOrder[index])) fail('policy-v3 arbitration limitation order is invalid')
  for (const coverageItem of arbitrationCoverages(dto)) {
    const expectedCodes = a5 === null && coverageItem.block_id === 'arbitration_a5'
      ? ['opponent_group_cap_exhausted']
      : LIMITATION_PRECEDENCE.filter(code => emitted.has(code) && (A1_LIMITATIONS.has(code)
        ? coverageItem.block_id === 'arbitration_a1'
        : A4_LIMITATIONS.has(code)
          ? coverageItem.block_id === 'arbitration_a4'
          : true))
    if (coverageItem.limitation_codes.length !== expectedCodes.length || coverageItem.limitation_codes.some((code, index) => code !== expectedCodes[index])) fail('policy-v3 arbitration coverage linkage is invalid')
  }
  const limitationFlag = (code: string, expected: boolean): void => {
    if (emitted.has(code) !== expected) fail('policy-v3 arbitration limitation facts disagree')
  }
  const summary = a1.summary
  limitationFlag('arbitration_calendar_unverified', true)
  limitationFlag('arbitration_unknown_year', integer(summary.unknown_year_count) > 0n)
  limitationFlag('arbitration_amount_missing', integer(a4.missing_amount_count) > 0n)
  limitationFlag('arbitration_currency_missing', integer(a4.missing_currency_count) > 0n)
  if ([...A4_LIMITATIONS].some(code => emitted.has(code)) !== (a4Eligible < denominator)) fail('policy-v3 arbitration limitation facts disagree')
  if (a4Eligible + integer(a4.missing_amount_count) + (emitted.has('arbitration_amount_invalid') ? 1n : 0n) > denominator) fail('policy-v3 A4 limitation population is invalid')
  if (a4Eligible + integer(a4.missing_currency_count) + (emitted.has('arbitration_currency_unidentified') ? 1n : 0n) + (emitted.has('arbitration_currency_invalid') ? 1n : 0n) > denominator) fail('policy-v3 A4 limitation population is invalid')
  limitationFlag('malformed_rows', integer(summary.malformed_count) > 0n)
  limitationFlag('duplicate_conflict', integer(summary.duplicate_conflict_count) > 0n)
  limitationFlag('source_total_exceeds_cap', summary.source_total !== null && integer(summary.source_total) > MAX_ROWS)
  limitationFlag('opponent_group_cap_exhausted', a5 === null)
  if (emitted.has('oversized_case') && emitted.has('storage_cap_exhausted')) fail('policy-v3 storage boundary limitations conflict')
  if (evidence.hasDateInversion && !emitted.has('arbitration_date_inversion')) fail('visible date inversion lacks limitation evidence')
  const allCasesVisible = BigInt(evidence.cases.size) === denominator
  if (allCasesVisible && emitted.has('arbitration_date_invalid') && [...evidence.cases.values()].every(item => item.start_date !== null && item.update_date !== null)) fail('policy-v3 invalid-date limitation lacks a visible candidate')
  if (allCasesVisible && emitted.has('arbitration_year_conflict') && ![...evidence.cases.values()].some(item => item.year === null && item.start_date !== null)) fail('policy-v3 year-conflict limitation lacks a visible candidate')
  if (allCasesVisible && emitted.has('arbitration_date_inversion') && ![...evidence.cases.values()].some(item => item.start_date !== null && item.update_date !== null && item.start_date > item.update_date)) fail('policy-v3 date-inversion limitation lacks a visible candidate')
  const firstNumberCodeCount = ['arbitration_first_number_unavailable', 'arbitration_first_number_identity_collision'].filter(code => emitted.has(code)).length
  const visibleHiddenNumberCount = [...evidence.cases.values()].filter(item => item.case_number === null).length
  const undisplayedCaseCount = denominator - BigInt(evidence.cases.size)
  if (BigInt(visibleHiddenNumberCount) + undisplayedCaseCount < BigInt(firstNumberCodeCount)) fail('policy-v3 first-number limitation population is impossible')
  if ([...evidence.cases.values()].some(item => item.case_number === null) && !emitted.has('arbitration_first_number_unavailable') && !emitted.has('arbitration_first_number_identity_collision')) fail('visible hidden case number lacks limitation evidence')
  if (PRE_RESULT_STATES.has(summary.completion_reason) || BOUND_FAILURE_REASONS.has(summary.completion_reason)) fail('invalid admitted policy-v3 completion reason')
  const expectedCompletion = COMPLETION_PRECEDENCE.find(reason => reason !== 'complete' && emitted.has(reason)) ?? 'complete'
  if (summary.completion_reason !== expectedCompletion) fail('policy-v3 arbitration completion precedence disagrees')
  for (const item of arbitrationLimitations) {
    const expectedBlock = A1_LIMITATIONS.has(item.code) ? 'arbitration_a1' : A4_LIMITATIONS.has(item.code) ? 'arbitration_a4' : null
    if (item.block_id !== expectedBlock || item.field_id !== null) fail('policy-v3 arbitration limitation linkage is invalid')
  }
}

export function validateArbitrationPolicyV3(dto: CompanyPublicH2): void {
  const branch = classifyArbitrationPolicyV3(dto)
  if (branch === null) {
    if (hasPolicyV3Marker(dto)) fail('invalid policy-v3 arbitration discriminator')
    return
  }
  if (branch === 'source_less') return
  validateBound(dto)
}
