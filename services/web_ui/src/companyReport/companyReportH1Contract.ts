import type {
  ArbitrationBlock,
  ArbitrationClaimAmount,
  BankruptcyBlock,
  CompanyPublicH1Response,
  CompanyPublicIdentity,
  DatasetId,
  FinanceBlock,
  FinanceMetric,
  LimitationCode,
  ManagementBlock,
  PublicAction,
  PublicAddress,
  PublicBlockId,
  PublicBreadcrumb,
  PublicCoverageItem,
  PublicFinanceMetricId,
  PublicInternalLink,
  PublicLimitation,
  PublicMoney,
  PublicPercentChange,
  PublicSourceItem,
  RequisitesBlock,
  TaxBlock,
} from './companyReportTypes'

const CONTRACT_ERROR_CODE = 'company_public_h1_contract_mismatch' as const

export class CompanyReportContractError extends Error {
  readonly code = CONTRACT_ERROR_CODE

  constructor() {
    super(CONTRACT_ERROR_CODE)
    this.name = 'CompanyReportContractError'
  }
}

function fail(): never {
  throw new CompanyReportContractError()
}

const rootKeys = [
  'contract_version', 'report_id', 'report_version', 'projection_scope',
  'canonical_path', 'indexable', 'checked_at', 'checked_date',
  'checked_date_display', 'identity', 'block_order', 'blocks', 'coverage',
  'sources', 'limitations', 'actions', 'breadcrumbs', 'internal_links',
] as const

const blockIds = [
  'breadcrumbs', 'identity_status', 'known_summary', 'in_page_navigation',
  'coverage_checked_at', 'requisites', 'finance', 'arbitration', 'bankruptcy',
  'tax', 'management', 'sources_limitations', 'neutral_actions', 'internal_links',
] as const satisfies readonly PublicBlockId[]

const factualBlockIds = [
  'requisites', 'finance', 'arbitration', 'bankruptcy', 'tax', 'management',
] as const

const datasetIds = [
  'counterparty', 'finance', 'arbitration', 'bankruptcy', 'tax_info',
] as const satisfies readonly DatasetId[]

const coverageStates = [
  'available', 'available_empty', 'not_found', 'not_requested', 'partial',
  'failed', 'conflict',
] as const

const financeMetricIds = [
  'total_assets', 'non_current_assets', 'current_assets', 'inventories',
  'accounts_receivable', 'cash_and_equivalents', 'equity',
  'long_term_liabilities', 'short_term_liabilities',
  'short_term_borrowings', 'accounts_payable', 'revenue', 'cost_of_sales',
  'gross_profit', 'operating_profit', 'profit_before_tax', 'net_profit',
  'net_cash_flow', 'cash_at_start', 'cash_at_end',
] as const satisfies readonly PublicFinanceMetricId[]

const limitationCodes = [
  'address_not_requested', 'address_marked_inaccurate',
  'legal_form_mapping_unknown', 'identity_status_mapping_unknown',
  'identity_status_conflict', 'finance_unit_evidence_not_passed',
  'finance_series_conflict', 'finance_dataset_not_found',
  'finance_dataset_failed', 'arbitration_identity_conflict',
  'arbitration_target_identity_incomplete', 'arbitration_unknown_currency',
  'arbitration_partial_slice', 'arbitration_malformed_records',
  'legacy_arbitration_role_detail_unavailable',
  'arbitration_dataset_not_found', 'arbitration_dataset_failed',
  'tax_schema_gate_not_passed', 'tax_operational_gate_not_passed',
  'bankruptcy_schema_gate_not_passed',
  'bankruptcy_operational_gate_not_passed',
  'management_privacy_gate_not_passed', 'management_schema_gate_not_passed',
  'management_operational_gate_not_passed',
] as const satisfies readonly LimitationCode[]

type LimitationCatalogEntry = readonly [
  PublicLimitation['block_id'],
  PublicLimitation['field_id'],
  string,
]

const limitationCatalog = {
  address_not_requested: [
    'requisites', 'requisites.legal_address',
    'Юридический адрес не запрашивался в сохранённом отчёте.',
  ],
  address_marked_inaccurate: [
    'requisites', 'requisites.legal_address',
    'Источник пометил юридический адрес как недостоверный.',
  ],
  legal_form_mapping_unknown: [
    'requisites', 'requisites.legal_form',
    'Организационно-правовая форма не отображена: значение отсутствует в утверждённом справочнике.',
  ],
  identity_status_mapping_unknown: [
    'identity_status', 'identity.status_label',
    'Статус компании не отображён: значение отсутствует в утверждённом справочнике.',
  ],
  identity_status_conflict: [
    'identity_status', 'identity.status_label',
    'Статус компании не отображён из-за противоречивых сохранённых сведений.',
  ],
  finance_unit_evidence_not_passed: [
    'finance', 'finance.metrics.money',
    'Денежные значения не показаны: единица источника не подтверждена сохранёнными доказательствами.',
  ],
  finance_series_conflict: [
    'finance', 'finance.metrics.yoy',
    'Изменение показателя не рассчитано из-за неоднозначного сопоставления периодов.',
  ],
  finance_dataset_not_found: [
    'finance', null,
    'Финансовые сведения не найдены в области ответа источника; нулевые значения не предполагаются.',
  ],
  finance_dataset_failed: [
    'finance', null,
    'Финансовые сведения недоступны из-за ошибки получения или нормализации.',
  ],
  arbitration_identity_conflict: [
    'arbitration', 'arbitration.selected_cases.attributed_role',
    'Роль компании в отдельных делах не определена из-за противоречивых идентификаторов.',
  ],
  arbitration_target_identity_incomplete: [
    'arbitration', 'arbitration.selected_cases.attributed_role',
    'Роль компании в отдельных делах не определена из-за неполных идентификаторов.',
  ],
  arbitration_unknown_currency: [
    'arbitration', 'arbitration.claim_amounts',
    'Часть сумм требований не показана: валюта источника не распознана.',
  ],
  arbitration_partial_slice: [
    'arbitration', null,
    'Показана только сохранённая часть арбитражных сведений.',
  ],
  arbitration_malformed_records: [
    'arbitration', null,
    'Часть арбитражных записей пропущена из-за некорректной структуры.',
  ],
  legacy_arbitration_role_detail_unavailable: [
    'arbitration', 'arbitration.selected_cases.attributed_role',
    'Для отчёта версии 1 детализация роли по отдельным делам недоступна.',
  ],
  arbitration_dataset_not_found: [
    'arbitration', null,
    'Арбитражные сведения не найдены в области ответа источника; отсутствие дел не предполагается.',
  ],
  arbitration_dataset_failed: [
    'arbitration', null,
    'Арбитражные сведения недоступны из-за ошибки получения или нормализации.',
  ],
  tax_schema_gate_not_passed: [
    'tax', null,
    'Налоговые сведения не запрашивались: схема источника не подтверждена.',
  ],
  tax_operational_gate_not_passed: [
    'tax', null,
    'Дополнительный запрос налоговых сведений не активирован.',
  ],
  bankruptcy_schema_gate_not_passed: [
    'bankruptcy', null,
    'Сведения о банкротных публикациях не запрашивались: схема источника не подтверждена.',
  ],
  bankruptcy_operational_gate_not_passed: [
    'bankruptcy', null,
    'Дополнительный запрос банкротных публикаций не активирован.',
  ],
  management_privacy_gate_not_passed: [
    'management', null,
    'Персональные сведения о руководителях не публикуются без утверждённой privacy policy.',
  ],
  management_schema_gate_not_passed: [
    'management', null,
    'Сведения о владельцах не публикуются: схема и семантика долей не подтверждены.',
  ],
  management_operational_gate_not_passed: [
    'management', null,
    'Дополнительные блоки руководителей и владельцев не запрашивались.',
  ],
} as const satisfies Record<LimitationCode, LimitationCatalogEntry>

const forbiddenKeys = new Set([
  'raw_payload', 'headers', 'authorization', 'api_key', 'apikey',
  'provider_limit_metadata', 'request_id', 'endpoint', 'response_hash',
  'provider_status_code', 'http_status_code', 'result_status',
  'result_status_code', 'attempts', 'duration_ms', 'worker_token',
  'lease_expires_at', 'safe_error_type', 'raw_role', 'raw_status',
  'raw_result_type', 'source_paths', 'requested_filters', 'factual_basis',
  'evaluation_basis', 'signals', 'scoring', 'score', 'verdict', 'probability',
  'ai_explanation', 'innfl', 'contacts', 'phone', 'email', 'website', 'social',
  'fssp',
])

const monthNumbers = [
  '01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12',
] as const

type MonthNumber = typeof monthNumbers[number]

const maximumDayByMonth: Record<MonthNumber, string> = {
  '01': '31', '02': '28', '03': '31', '04': '30', '05': '31', '06': '30',
  '07': '31', '08': '31', '09': '30', '10': '31', '11': '30', '12': '31',
}

const monthNameByNumber: Record<MonthNumber, string> = {
  '01': 'января', '02': 'февраля', '03': 'марта', '04': 'апреля',
  '05': 'мая', '06': 'июня', '07': 'июля', '08': 'августа',
  '09': 'сентября', '10': 'октября', '11': 'ноября', '12': 'декабря',
}

const bankruptcyMessageByKind = {
  debtor_intention: 'Опубликовано намерение должника обратиться в суд с заявлением о банкротстве.',
  creditor_intention: 'Опубликовано намерение кредитора обратиться в суд с заявлением о банкротстве компании.',
  unknown: 'Тип публикации не классифицирован',
} as const

const bankruptcyDisclaimer =
  'Наличие публикации не подтверждает, что заявление принято судом, возбуждено дело, компания признана банкротом или процедура продолжается сейчас.'

const taxMessageByIndicator: Record<'true' | 'false', string> = {
  false: 'Признак неоплаченной налоговой задолженности не установлен.',
  true: 'Источник передал признак неоплаченной налоговой задолженности.',
}

function exactObject(value: unknown, expectedKeys: readonly string[]): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) fail()
  const actualKeys = Object.keys(value)
  if (
    actualKeys.length !== expectedKeys.length
    || actualKeys.some((key) => !expectedKeys.includes(key))
  ) fail()
  return value as Record<string, unknown>
}

function unknownArray(value: unknown): readonly unknown[] {
  if (!Array.isArray(value)) fail()
  return value as readonly unknown[]
}

function rawString(value: unknown): string {
  if (typeof value !== 'string') fail()
  return value
}

function nonEmptyString(value: unknown): string {
  const parsed = rawString(value)
  if (parsed.length === 0) fail()
  return parsed
}

function isPythonWhitespace(character: string): boolean {
  const codePoint = character.codePointAt(0)
  if (codePoint === undefined) return false
  return (
    (codePoint >= 0x0009 && codePoint <= 0x000d)
    || (codePoint >= 0x001c && codePoint <= 0x0020)
    || codePoint === 0x0085
    || codePoint === 0x00a0
    || codePoint === 0x1680
    || (codePoint >= 0x2000 && codePoint <= 0x200a)
    || codePoint === 0x2028
    || codePoint === 0x2029
    || codePoint === 0x202f
    || codePoint === 0x205f
    || codePoint === 0x3000
  )
}

function canonicalSafeText(value: string): string {
  const words: string[] = []
  let word = ''
  for (const character of value.normalize('NFKC')) {
    if (isPythonWhitespace(character)) {
      if (word.length > 0) words.push(word)
      word = ''
    } else {
      word += character
    }
  }
  if (word.length > 0) words.push(word)
  return words.join(' ')
}

function safeText(value: unknown): string {
  const parsed = nonEmptyString(value)
  const canonical = canonicalSafeText(parsed)
  if (canonical !== parsed || /\p{Cc}/u.test(parsed)) fail()
  return parsed
}

function nullableRawString(value: unknown): string | null {
  return value === null ? null : rawString(value)
}

function nullableSafeText(value: unknown): string | null {
  return value === null ? null : safeText(value)
}

function booleanValue(value: unknown): boolean {
  if (typeof value !== 'boolean') fail()
  return value
}

function nullableBoolean(value: unknown): boolean | null {
  return value === null ? null : booleanValue(value)
}

function oneOf<const T extends readonly string[]>(value: unknown, allowed: T): T[number] {
  if (typeof value !== 'string' || !allowed.some((item) => item === value)) fail()
  return value as T[number]
}

function safeInteger(value: unknown): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value)) fail()
  return value
}

function nonNegativeInteger(value: unknown): number {
  const parsed = safeInteger(value)
  if (parsed < 0) fail()
  return parsed
}

function positiveInteger(value: unknown): number {
  const parsed = safeInteger(value)
  if (parsed < 1) fail()
  return parsed
}

function nullableNonNegativeInteger(value: unknown): number | null {
  return value === null ? null : nonNegativeInteger(value)
}

function nullablePositiveInteger(value: unknown): number | null {
  return value === null ? null : positiveInteger(value)
}

function asciiInn(value: unknown): string {
  const parsed = rawString(value)
  if (!/^(?:[0-9]{10}|[0-9]{12})$/.test(parsed)) fail()
  return parsed
}

function nullableAsciiOgrn(value: unknown): string | null {
  if (value === null) return null
  const parsed = rawString(value)
  if (!/^(?:[0-9]{13}|[0-9]{15})$/.test(parsed)) fail()
  return parsed
}

function nullableAsciiKpp(value: unknown): string | null {
  if (value === null) return null
  const parsed = rawString(value)
  if (!/^[0-9]{9}$/.test(parsed)) fail()
  return parsed
}

function uuid(value: unknown): string {
  const parsed = rawString(value)
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(parsed)) fail()
  return parsed
}

function isLeapYear(year: bigint): boolean {
  return year % 400n === 0n || (year % 4n === 0n && year % 100n !== 0n)
}

function parseIsoDateParts(value: unknown): readonly [string, MonthNumber, string] {
  const parsed = rawString(value)
  const match = /^([0-9]{4})-([0-9]{2})-([0-9]{2})$/.exec(parsed)
  if (match === null) fail()
  const year = match[1]
  const month = oneOf(match[2], monthNumbers)
  const day = match[3]
  const yearValue = BigInt(year)
  if (yearValue === 0n) fail()
  const maximumDay = month === '02' && isLeapYear(yearValue)
    ? '29'
    : maximumDayByMonth[month]
  if (day < '01' || day > maximumDay) fail()
  return [year, month, day]
}

function isoDate(value: unknown): string {
  const parsed = rawString(value)
  parseIsoDateParts(parsed)
  return parsed
}

function nullableDate(value: unknown): string | null {
  return value === null ? null : isoDate(value)
}

function utcTimestamp(value: unknown): string {
  const parsed = rawString(value)
  const match = /^([0-9]{4}-[0-9]{2}-[0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,6}))?Z$/.exec(parsed)
  if (match === null) fail()
  isoDate(match[1])
  if (match[2] > '23' || match[3] > '59' || match[4] > '59') fail()
  return parsed
}

function canonicalDecimal(value: unknown): string {
  const parsed = rawString(value)
  if (
    !/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/.test(parsed)
    || parsed === '-0'
    || (parsed.includes('.') && parsed.endsWith('0'))
  ) fail()
  return parsed
}

const nextDigit: Record<string, string> = {
  '0': '1', '1': '2', '2': '3', '3': '4', '4': '5',
  '5': '6', '6': '7', '7': '8', '8': '9',
}

function incrementDigits(value: string): string {
  const digits = value.split('')
  for (let index = digits.length - 1; index >= 0; index -= 1) {
    const digit = digits[index]
    if (digit === '9') {
      digits[index] = '0'
      continue
    }
    const incremented = nextDigit[digit]
    if (incremented === undefined) fail()
    digits[index] = incremented
    return digits.join('')
  }
  return `1${digits.join('')}`
}

function roundHalfUpOneDisplay(exact: string): string {
  const negative = exact.startsWith('-')
  const magnitude = negative ? exact.slice(1) : exact
  const [whole, fraction = ''] = magnitude.split('.')
  const firstFractionDigit = fraction[0] ?? '0'
  const roundingDigit = fraction[1] ?? '0'
  let keptDigits = `${whole}${firstFractionDigit}`
  if (roundingDigit >= '5') keptDigits = incrementDigits(keptDigits)
  const roundedWhole = keptDigits.slice(0, -1) || '0'
  const roundedFraction = keptDigits.slice(-1)
  return `${negative ? '-' : '+'}${roundedWhole},${roundedFraction}%`
}

function sameOriginPath(value: unknown): string {
  const parsed = safeText(value)
  if (
    !parsed.startsWith('/')
    || parsed.startsWith('//')
    || parsed.includes('\\')
    || /\s/u.test(parsed)
  ) fail()
  return parsed
}

function canonicalPath(value: unknown, expectedInn: string): string {
  const parsed = rawString(value)
  const legacy = /^\/company\/([0-9]{10}|[0-9]{12})-[a-z0-9]+(?:-[a-z0-9]+)*$/.exec(parsed)
  const v2 = /^\/company\/(?:ooo|ao|oao|zao|pao|ip)-[a-z0-9]+(?:-[a-z0-9]+)*-([0-9]{10}|[0-9]{12})$/.exec(parsed)
  const inn = legacy?.[1] ?? v2?.[1]
  if (inn !== expectedInn) fail()
  return parsed
}

function auditForbiddenFields(value: unknown, seen = new WeakSet<object>()): void {
  if (value === null || typeof value !== 'object') return
  if (seen.has(value)) fail()
  seen.add(value)
  for (const [key, child] of Object.entries(value)) {
    if (forbiddenKeys.has(key.toLowerCase())) fail()
    auditForbiddenFields(child, seen)
  }
}

function parseAtBoundary<T>(value: unknown, parser: (candidate: unknown) => T): T {
  try {
    auditForbiddenFields(value)
    return parser(value)
  } catch {
    throw new CompanyReportContractError()
  }
}

function parseMoney(value: unknown): PublicMoney {
  const candidate = exactObject(value, [
    'source_decimal', 'source_unit', 'rub_decimal', 'display_value',
    'unit_policy_version',
  ])
  return {
    source_decimal: canonicalDecimal(candidate.source_decimal),
    source_unit: oneOf(candidate.source_unit, ['thousand_rub'] as const),
    rub_decimal: canonicalDecimal(candidate.rub_decimal),
    display_value: safeText(candidate.display_value),
    unit_policy_version: safeText(candidate.unit_policy_version),
  }
}

export function parseReservedMoney(value: unknown): PublicMoney {
  return parseAtBoundary(value, parseMoney)
}

function parseTaxBlock(value: unknown): TaxBlock {
  const candidate = exactObject(value, [
    'unpaid_debt_indicator', 'message', 'as_of_date', 'records',
  ])
  const unpaidDebtIndicator = booleanValue(candidate.unpaid_debt_indicator)
  const message = rawString(candidate.message)
  if (message !== taxMessageByIndicator[unpaidDebtIndicator ? 'true' : 'false']) fail()
  const records = unknownArray(candidate.records).map((record) => {
    const parsed = exactObject(record, [
      'record_type', 'document_date', 'period', 'amount',
    ])
    return {
      record_type: safeText(parsed.record_type),
      document_date: nullableDate(parsed.document_date),
      period: nullableRawString(parsed.period),
      amount: parsed.amount === null ? null : parseMoney(parsed.amount),
    }
  })
  return {
    unpaid_debt_indicator: unpaidDebtIndicator,
    message,
    as_of_date: nullableDate(candidate.as_of_date),
    records,
  }
}

export function parseReservedTaxBlock(value: unknown): TaxBlock {
  return parseAtBoundary(value, parseTaxBlock)
}

function parseBankruptcyBlock(value: unknown): BankruptcyBlock {
  const candidate = exactObject(value, [
    'total', 'returned', 'limit', 'offset', 'typed_counts', 'publications',
    'disclaimer',
  ])
  const counts = exactObject(candidate.typed_counts, [
    'debtor_intention', 'creditor_intention', 'unknown',
  ])
  const publications = unknownArray(candidate.publications).map((publication) => {
    const parsed = exactObject(publication, [
      'safe_reference', 'publication_date', 'kind', 'message',
      'participant_role',
    ])
    const kind = oneOf(parsed.kind, [
      'debtor_intention', 'creditor_intention', 'unknown',
    ] as const)
    const message = rawString(parsed.message)
    if (message !== bankruptcyMessageByKind[kind]) fail()
    return {
      safe_reference: nullableSafeText(parsed.safe_reference),
      publication_date: nullableDate(parsed.publication_date),
      kind,
      message,
      participant_role: oneOf(parsed.participant_role, [
        'debtor', 'creditor', 'other', 'unknown',
      ] as const),
    }
  })
  const disclaimer = rawString(candidate.disclaimer)
  if (disclaimer !== bankruptcyDisclaimer) fail()
  return {
    total: nonNegativeInteger(candidate.total),
    returned: nonNegativeInteger(candidate.returned),
    limit: positiveInteger(candidate.limit),
    offset: nonNegativeInteger(candidate.offset),
    typed_counts: {
      debtor_intention: nonNegativeInteger(counts.debtor_intention),
      creditor_intention: nonNegativeInteger(counts.creditor_intention),
      unknown: nonNegativeInteger(counts.unknown),
    },
    publications,
    disclaimer,
  }
}

export function parseReservedBankruptcyBlock(value: unknown): BankruptcyBlock {
  return parseAtBoundary(value, parseBankruptcyBlock)
}

function parseManagementBlock(value: unknown): ManagementBlock {
  const candidate = exactObject(value, ['managers', 'owners'])
  const managers = unknownArray(candidate.managers).map((manager) => {
    const parsed = exactObject(manager, [
      'name', 'role', 'appointed_at', 'is_inaccuracy',
    ])
    return {
      name: safeText(parsed.name),
      role: safeText(parsed.role),
      appointed_at: nullableDate(parsed.appointed_at),
      is_inaccuracy: nullableBoolean(parsed.is_inaccuracy),
    }
  })
  const owners = unknownArray(candidate.owners).map((owner) => {
    const parsed = exactObject(owner, [
      'name_or_org', 'owner_type', 'organization_inn', 'organization_ogrn',
      'share_percent_decimal', 'share_display', 'ownership_effective_at',
    ])
    return {
      name_or_org: safeText(parsed.name_or_org),
      owner_type: oneOf(parsed.owner_type, ['person', 'organization'] as const),
      organization_inn: parsed.organization_inn === null
        ? null
        : asciiInn(parsed.organization_inn),
      organization_ogrn: nullableAsciiOgrn(parsed.organization_ogrn),
      share_percent_decimal: parsed.share_percent_decimal === null
        ? null
        : canonicalDecimal(parsed.share_percent_decimal),
      share_display: nullableRawString(parsed.share_display),
      ownership_effective_at: nullableDate(parsed.ownership_effective_at),
    }
  })
  if (managers.length === 0 && owners.length === 0) fail()
  return { managers, owners }
}

export function parseReservedManagementBlock(value: unknown): ManagementBlock {
  return parseAtBoundary(value, parseManagementBlock)
}

function parseInternalLink(value: unknown): PublicInternalLink {
  const candidate = exactObject(value, ['label', 'path', 'relation'])
  return {
    label: safeText(candidate.label),
    path: sameOriginPath(candidate.path),
    relation: safeText(candidate.relation),
  }
}

export function parseReservedInternalLink(value: unknown): PublicInternalLink {
  return parseAtBoundary(value, parseInternalLink)
}

function parseAddress(value: unknown): PublicAddress {
  const candidate = exactObject(value, [
    'display_line', 'postal_code', 'country', 'region', 'city', 'street',
    'house', 'office', 'is_inaccuracy',
  ])
  return {
    display_line: safeText(candidate.display_line),
    postal_code: nullableSafeText(candidate.postal_code),
    country: nullableSafeText(candidate.country),
    region: nullableSafeText(candidate.region),
    city: nullableSafeText(candidate.city),
    street: nullableSafeText(candidate.street),
    house: nullableSafeText(candidate.house),
    office: nullableSafeText(candidate.office),
    is_inaccuracy: nullableBoolean(candidate.is_inaccuracy),
  }
}

function parseIdentity(value: unknown): CompanyPublicIdentity {
  const candidate = exactObject(value, [
    'legal_full_name', 'legal_short_name', 'display_name', 'inn',
    'status_code', 'status_label', 'status_effective_at',
  ])
  if (
    candidate.status_code !== null
    || candidate.status_label !== null
    || candidate.status_effective_at !== null
  ) fail()
  return {
    legal_full_name: safeText(candidate.legal_full_name),
    legal_short_name: nullableSafeText(candidate.legal_short_name),
    display_name: safeText(candidate.display_name),
    inn: asciiInn(candidate.inn),
    status_code: null,
    status_label: null,
    status_effective_at: null,
  }
}

function parseRequisites(value: unknown): RequisitesBlock {
  const candidate = exactObject(value, [
    'legal_form', 'ogrn_or_ogrnip', 'kpp', 'registration_date',
    'dissolved_date', 'region', 'legal_address',
  ])
  if (candidate.legal_form !== null) fail()
  let region: RequisitesBlock['region'] = null
  if (candidate.region !== null) {
    const parsed = exactObject(candidate.region, ['code', 'name'])
    region = {
      code: nullableSafeText(parsed.code),
      name: nullableSafeText(parsed.name),
    }
  }
  return {
    legal_form: null,
    ogrn_or_ogrnip: nullableAsciiOgrn(candidate.ogrn_or_ogrnip),
    kpp: nullableAsciiKpp(candidate.kpp),
    registration_date: nullableDate(candidate.registration_date),
    dissolved_date: nullableDate(candidate.dissolved_date),
    region,
    legal_address: candidate.legal_address === null
      ? null
      : parseAddress(candidate.legal_address),
  }
}

function parsePercentChange(value: unknown): PublicPercentChange {
  const candidate = exactObject(value, [
    'exact_percent', 'display_value', 'current_year', 'previous_year',
    'formula_version',
  ])
  const exactPercent = canonicalDecimal(candidate.exact_percent)
  const displayValue = rawString(candidate.display_value)
  const currentYear = safeInteger(candidate.current_year)
  const previousYear = safeInteger(candidate.previous_year)
  if (BigInt(previousYear) !== BigInt(currentYear) - 1n) fail()
  if (displayValue !== roundHalfUpOneDisplay(exactPercent)) fail()
  return {
    exact_percent: exactPercent,
    display_value: displayValue,
    current_year: currentYear,
    previous_year: previousYear,
    formula_version: oneOf(candidate.formula_version, ['finance_yoy_v1'] as const),
  }
}

function parseCurrentFinance(value: unknown): FinanceBlock | null {
  if (value === null) return null
  const candidate = exactObject(value, ['unit_policy_version', 'metrics'])
  const metrics = unknownArray(candidate.metrics)
  if (candidate.unit_policy_version !== null || metrics.length === 0) fail()
  const parsedMetrics: FinanceMetric[] = metrics.map((metric) => {
    const parsed = exactObject(metric, ['metric_id', 'year', 'money', 'yoy'])
    if (parsed.money !== null || parsed.yoy === null) fail()
    return {
      metric_id: oneOf(parsed.metric_id, financeMetricIds),
      year: safeInteger(parsed.year),
      money: null,
      yoy: parsePercentChange(parsed.yoy),
    }
  })
  return { unit_policy_version: null, metrics: parsedMetrics }
}

function parseClaimAmount(value: unknown): ArbitrationClaimAmount {
  const candidate = exactObject(value, [
    'role', 'currency', 'exact_decimal', 'display_value',
  ])
  const role = oneOf(candidate.role, ['plaintiff', 'respondent'] as const)
  const currency = rawString(candidate.currency)
  if (!/^[A-Z][A-Z0-9_-]{2,15}$/.test(currency)) fail()
  const exactDecimal = canonicalDecimal(candidate.exact_decimal)
  const displayValue = rawString(candidate.display_value)
  if (displayValue !== `${exactDecimal.replace('.', ',')} ${currency}`) fail()
  return {
    role,
    currency,
    exact_decimal: exactDecimal,
    display_value: displayValue,
  }
}

function sumAsBigInt(values: readonly number[]): bigint {
  return values.reduce((total, value) => total + BigInt(value), 0n)
}

function parseArbitration(value: unknown): ArbitrationBlock {
  const candidate = exactObject(value, [
    'total_cases', 'returned_cases', 'normalized_case_count',
    'malformed_count', 'limit', 'offset', 'role_counts',
    'unattributed_count', 'status_counts', 'result_counts', 'claim_amounts',
    'selected_cases',
  ])
  const roles = exactObject(candidate.role_counts, [
    'plaintiff', 'respondent', 'applicant', 'creditor', 'debtor', 'other',
  ])
  const statuses = exactObject(candidate.status_counts, [
    'open', 'completed', 'unknown',
  ])
  const results = exactObject(candidate.result_counts, [
    'satisfied_full', 'refused', 'returned', 'undefined', 'other',
  ])
  const roleCounts = {
    plaintiff: nonNegativeInteger(roles.plaintiff),
    respondent: nonNegativeInteger(roles.respondent),
    applicant: nonNegativeInteger(roles.applicant),
    creditor: nonNegativeInteger(roles.creditor),
    debtor: nonNegativeInteger(roles.debtor),
    other: nonNegativeInteger(roles.other),
  }
  const statusCounts = {
    open: nonNegativeInteger(statuses.open),
    completed: nonNegativeInteger(statuses.completed),
    unknown: nonNegativeInteger(statuses.unknown),
  }
  const resultCounts = {
    satisfied_full: nonNegativeInteger(results.satisfied_full),
    refused: nonNegativeInteger(results.refused),
    returned: nonNegativeInteger(results.returned),
    undefined: nonNegativeInteger(results.undefined),
    other: nonNegativeInteger(results.other),
  }
  const returnedCases = nonNegativeInteger(candidate.returned_cases)
  const normalizedCaseCount = nonNegativeInteger(candidate.normalized_case_count)
  const malformedCount = nonNegativeInteger(candidate.malformed_count)
  const unattributedCount = nonNegativeInteger(candidate.unattributed_count)
  const selectedCases = unknownArray(candidate.selected_cases)
  if (selectedCases.length > 10) fail()
  const parsedSelectedCases = selectedCases.map((selectedCase) => {
    const parsed = exactObject(selectedCase, [
      'case_number', 'date_start', 'date_update', 'attributed_role',
      'claim_amount',
    ])
    const attributedRole = oneOf(parsed.attributed_role, [
      'plaintiff', 'respondent', 'applicant', 'creditor', 'debtor', 'other',
      'unattributed',
    ] as const)
    const claimAmount = parsed.claim_amount === null
      ? null
      : parseClaimAmount(parsed.claim_amount)
    if (
      claimAmount !== null
      && (attributedRole !== claimAmount.role
        || (attributedRole !== 'plaintiff' && attributedRole !== 'respondent'))
    ) fail()
    return {
      case_number: nonEmptyString(parsed.case_number),
      date_start: nullableDate(parsed.date_start),
      date_update: nullableDate(parsed.date_update),
      attributed_role: attributedRole,
      claim_amount: claimAmount,
    }
  })
  if (
    sumAsBigInt(Object.values(roleCounts)) + BigInt(unattributedCount)
      !== BigInt(normalizedCaseCount)
    || BigInt(normalizedCaseCount) + BigInt(malformedCount)
      !== BigInt(returnedCases)
    || sumAsBigInt(Object.values(statusCounts)) !== BigInt(normalizedCaseCount)
    || sumAsBigInt(Object.values(resultCounts)) !== BigInt(normalizedCaseCount)
  ) fail()
  return {
    total_cases: nonNegativeInteger(candidate.total_cases),
    returned_cases: returnedCases,
    normalized_case_count: normalizedCaseCount,
    malformed_count: malformedCount,
    limit: positiveInteger(candidate.limit),
    offset: nonNegativeInteger(candidate.offset),
    role_counts: roleCounts,
    unattributed_count: unattributedCount,
    status_counts: statusCounts,
    result_counts: resultCounts,
    claim_amounts: unknownArray(candidate.claim_amounts).map(parseClaimAmount),
    selected_cases: parsedSelectedCases,
  }
}

const expectedCoverage = [
  ['requisites', 'counterparty'],
  ['finance', 'finance'],
  ['arbitration', 'arbitration'],
  ['bankruptcy', 'bankruptcy'],
  ['tax', 'tax_info'],
  ['management', 'counterparty'],
] as const

function parseCoverage(value: unknown): readonly PublicCoverageItem[] {
  const candidates = unknownArray(value)
  if (candidates.length !== expectedCoverage.length) fail()
  const coverage = candidates.map((item, index) => {
    const candidate = exactObject(item, [
      'block_id', 'dataset', 'state', 'total', 'returned', 'limit', 'offset',
      'limitation_codes',
    ])
    const blockId = oneOf(candidate.block_id, factualBlockIds)
    const dataset = oneOf(candidate.dataset, datasetIds)
    const expected = expectedCoverage[index]
    if (blockId !== expected[0] || dataset !== expected[1]) fail()
    return {
      block_id: blockId,
      dataset,
      state: oneOf(candidate.state, coverageStates),
      total: nullableNonNegativeInteger(candidate.total),
      returned: nullableNonNegativeInteger(candidate.returned),
      limit: nullablePositiveInteger(candidate.limit),
      offset: nullableNonNegativeInteger(candidate.offset),
      limitation_codes: unknownArray(candidate.limitation_codes).map((code) =>
        oneOf(code, limitationCodes)),
    }
  })
  if (coverage[0].state !== 'available') fail()
  return coverage
}

function compareLimitation(left: PublicLimitation, right: PublicLimitation): number {
  const leftTuple = [left.block_id ?? '', left.field_id ?? '', left.code]
  const rightTuple = [right.block_id ?? '', right.field_id ?? '', right.code]
  for (let index = 0; index < leftTuple.length; index += 1) {
    if (leftTuple[index] < rightTuple[index]) return -1
    if (leftTuple[index] > rightTuple[index]) return 1
  }
  return 0
}

function parseLimitations(value: unknown): readonly PublicLimitation[] {
  const limitations = unknownArray(value).map((item) => {
    const candidate = exactObject(item, ['code', 'block_id', 'field_id', 'message'])
    const code = oneOf(candidate.code, limitationCodes)
    const expected = limitationCatalog[code]
    if (
      candidate.block_id !== expected[0]
      || candidate.field_id !== expected[1]
      || candidate.message !== expected[2]
    ) fail()
    return {
      code,
      block_id: expected[0],
      field_id: expected[1],
      message: expected[2],
    }
  })
  for (let index = 1; index < limitations.length; index += 1) {
    if (compareLimitation(limitations[index - 1], limitations[index]) >= 0) fail()
  }
  return limitations
}

const sourcePrecedence = [
  'counterparty', 'finance', 'arbitration', 'tax_info', 'bankruptcy',
] as const satisfies readonly DatasetId[]

function parseSources(
  value: unknown,
  reportVersion: CompanyPublicH1Response['report_version'],
): readonly PublicSourceItem[] {
  let previousPrecedence = -1
  return unknownArray(value).map((item) => {
    const candidate = exactObject(item, [
      'dataset', 'received_at', 'effective_at', 'period',
      'normalization_version',
    ])
    const dataset = oneOf(candidate.dataset, datasetIds)
    const normalizationVersion = oneOf(candidate.normalization_version, [
      'counterparty_normalizer_v1', 'finance_normalizer_v1',
      'arbitration_normalizer_v1', 'arbitration_normalizer_v2',
    ] as const)
    let expectedNormalization: PublicSourceItem['normalization_version']
    if (dataset === 'counterparty') {
      expectedNormalization = 'counterparty_normalizer_v1'
    } else if (dataset === 'finance') {
      expectedNormalization = 'finance_normalizer_v1'
    } else if (dataset === 'arbitration') {
      expectedNormalization = reportVersion === '2'
        ? 'arbitration_normalizer_v2'
        : 'arbitration_normalizer_v1'
    } else {
      fail()
    }
    if (normalizationVersion !== expectedNormalization) fail()
    const precedence = sourcePrecedence.indexOf(dataset)
    if (precedence <= previousPrecedence) fail()
    previousPrecedence = precedence
    return {
      dataset,
      received_at: utcTimestamp(candidate.received_at),
      effective_at: nullableDate(candidate.effective_at),
      period: nullableRawString(candidate.period),
      normalization_version: normalizationVersion,
    }
  })
}

function parseActions(value: unknown, reportId: string): readonly PublicAction[] {
  const candidates = unknownArray(value)
  if (candidates.length !== 2) fail()
  const actions = candidates.map((item) => {
    const candidate = exactObject(item, ['action_id', 'label', 'path'])
    return {
      action_id: oneOf(candidate.action_id, [
        'check_another_company', 'prepare_claim',
      ] as const),
      label: oneOf(candidate.label, [
        'Проверить другую компанию', 'Подготовить претензию',
      ] as const),
      path: rawString(candidate.path),
    }
  })
  if (
    actions[0].action_id !== 'check_another_company'
    || actions[0].label !== 'Проверить другую компанию'
    || actions[0].path !== '/'
    || actions[1].action_id !== 'prepare_claim'
    || actions[1].label !== 'Подготовить претензию'
    || actions[1].path !== `/claims?report_id=${reportId}`
  ) fail()
  return actions
}

function parseBreadcrumbs(
  value: unknown,
  displayName: string,
  expectedCanonicalPath: string,
): readonly PublicBreadcrumb[] {
  const candidates = unknownArray(value)
  if (candidates.length !== 2) fail()
  const breadcrumbs = candidates.map((item) => {
    const candidate = exactObject(item, ['label', 'path'])
    return {
      label: nonEmptyString(candidate.label),
      path: rawString(candidate.path),
    }
  })
  if (
    breadcrumbs[0].label !== 'Главная'
    || breadcrumbs[0].path !== '/'
    || breadcrumbs[1].label !== displayName
    || breadcrumbs[1].path !== expectedCanonicalPath
  ) fail()
  return breadcrumbs
}

function checkedDateDisplay(value: unknown, checkedDate: string): string {
  const display = rawString(value)
  const [year, month, day] = parseIsoDateParts(checkedDate)
  const displayDay = day.startsWith('0') ? day.slice(1) : day
  const displayYear = year.replace(/^0+/, '')
  if (display !== `${displayDay} ${monthNameByNumber[month]} ${displayYear} года`) fail()
  return display
}

function expectedBlockOrder(
  finance: FinanceBlock | null,
  arbitration: ArbitrationBlock | null,
): readonly PublicBlockId[] {
  const factual: PublicBlockId[] = ['requisites']
  if (finance !== null) factual.push('finance')
  if (arbitration !== null) factual.push('arbitration')
  const expected: PublicBlockId[] = [
    'breadcrumbs', 'identity_status', 'known_summary',
  ]
  if (factual.length >= 2) expected.push('in_page_navigation')
  expected.push(
    'coverage_checked_at', ...factual, 'sources_limitations', 'neutral_actions',
  )
  return expected
}

function parseRoot(value: unknown): CompanyPublicH1Response {
  const candidate = exactObject(value, rootKeys)
  const contractVersion = oneOf(candidate.contract_version, ['company_public_h1_v1'] as const)
  const reportId = uuid(candidate.report_id)
  const reportVersion = oneOf(candidate.report_version, ['1', '2'] as const)
  const projectionScope = oneOf(candidate.projection_scope, [
    'published', 'latest_unpublished',
  ] as const)
  const indexable = booleanValue(candidate.indexable)
  if (projectionScope === 'latest_unpublished' && indexable) fail()
  const identity = parseIdentity(candidate.identity)
  const parsedCanonicalPath = canonicalPath(candidate.canonical_path, identity.inn)
  const checkedAt = utcTimestamp(candidate.checked_at)
  const checkedDate = isoDate(candidate.checked_date)
  const parsedCheckedDateDisplay = checkedDateDisplay(
    candidate.checked_date_display,
    checkedDate,
  )
  const blockCandidates = exactObject(candidate.blocks, [
    'requisites', 'finance', 'arbitration', 'bankruptcy', 'tax', 'management',
  ])
  if (
    blockCandidates.bankruptcy !== null
    || blockCandidates.tax !== null
    || blockCandidates.management !== null
  ) fail()
  const requisites = parseRequisites(blockCandidates.requisites)
  const finance = parseCurrentFinance(blockCandidates.finance)
  const arbitration = blockCandidates.arbitration === null
    ? null
    : parseArbitration(blockCandidates.arbitration)
  const coverage = parseCoverage(candidate.coverage)
  const optionalGateCodes: readonly (readonly LimitationCode[])[] = [
    ['bankruptcy_schema_gate_not_passed', 'bankruptcy_operational_gate_not_passed'],
    ['tax_schema_gate_not_passed', 'tax_operational_gate_not_passed'],
    [
      'management_privacy_gate_not_passed', 'management_schema_gate_not_passed',
      'management_operational_gate_not_passed',
    ],
  ]
  for (let index = 0; index < optionalGateCodes.length; index += 1) {
    const item = coverage[index + 3]
    const expectedCodes = optionalGateCodes[index]
    if (
      item.state !== 'not_requested'
      || item.total !== null
      || item.returned !== null
      || item.limit !== null
      || item.offset !== null
      || item.limitation_codes.length !== expectedCodes.length
      || item.limitation_codes.some((code, codeIndex) => code !== expectedCodes[codeIndex])
    ) fail()
  }
  const limitations = parseLimitations(candidate.limitations)
  const presentLimitationCodes = new Set(limitations.map((item) => item.code))
  if (
    coverage.some((item) => item.limitation_codes.some((code) =>
      !presentLimitationCodes.has(code)))
  ) fail()
  const sources = parseSources(candidate.sources, reportVersion)
  const actions = parseActions(candidate.actions, reportId)
  const breadcrumbs = parseBreadcrumbs(
    candidate.breadcrumbs,
    identity.display_name,
    parsedCanonicalPath,
  )
  if (unknownArray(candidate.internal_links).length !== 0) fail()
  const parsedBlockOrder = unknownArray(candidate.block_order).map((item) =>
    oneOf(item, blockIds))
  const requiredBlockOrder = expectedBlockOrder(finance, arbitration)
  if (
    parsedBlockOrder.length !== requiredBlockOrder.length
    || parsedBlockOrder.some((item, index) => item !== requiredBlockOrder[index])
  ) fail()
  return {
    contract_version: contractVersion,
    report_id: reportId,
    report_version: reportVersion,
    projection_scope: projectionScope,
    canonical_path: parsedCanonicalPath,
    indexable,
    checked_at: checkedAt,
    checked_date: checkedDate,
    checked_date_display: parsedCheckedDateDisplay,
    identity,
    block_order: requiredBlockOrder,
    blocks: {
      requisites,
      finance,
      arbitration,
      bankruptcy: null,
      tax: null,
      management: null,
    },
    coverage,
    sources,
    limitations,
    actions,
    breadcrumbs,
    internal_links: [],
  }
}

export function parseCompanyPublicH1(value: unknown): CompanyPublicH1Response {
  return parseAtBoundary(value, parseRoot)
}
