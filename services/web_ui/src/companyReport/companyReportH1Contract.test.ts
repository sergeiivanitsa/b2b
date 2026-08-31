import { describe, expect, it } from 'vitest'
import publishedFixture from './fixtures/company-public-h1-published.json?raw'
import latestFixture from './fixtures/company-public-h1-latest-unpublished.json?raw'
import {
  CompanyReportContractError,
  parseCompanyPublicH1,
  parseReservedBankruptcyBlock,
  parseReservedInternalLink,
  parseReservedManagementBlock,
  parseReservedMoney,
  parseReservedTaxBlock,
} from './companyReportH1Contract'

type JsonObject = Record<string, unknown>

function asObject(value: unknown): JsonObject {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('test fixture node is not an object')
  }
  return value as JsonObject
}

function asArray(value: unknown): unknown[] {
  if (!Array.isArray(value)) throw new Error('test fixture node is not an array')
  return value
}

function objectAt(parent: JsonObject, key: string): JsonObject {
  return asObject(parent[key])
}

function arrayAt(parent: JsonObject, key: string): unknown[] {
  return asArray(parent[key])
}

function fixture(raw: string): JsonObject {
  const parsed: unknown = JSON.parse(raw)
  return asObject(parsed)
}

function published(): JsonObject {
  return fixture(publishedFixture)
}

function latest(): JsonObject {
  return fixture(latestFixture)
}

function blocks(value: JsonObject): JsonObject {
  return objectAt(value, 'blocks')
}

function finance(value: JsonObject): JsonObject {
  return objectAt(blocks(value), 'finance')
}

function financeMetric(value: JsonObject): JsonObject {
  return asObject(arrayAt(finance(value), 'metrics')[0])
}

function yoy(value: JsonObject): JsonObject {
  return objectAt(financeMetric(value), 'yoy')
}

function arbitration(value: JsonObject): JsonObject {
  return objectAt(blocks(value), 'arbitration')
}

function coverage(value: JsonObject): JsonObject[] {
  return arrayAt(value, 'coverage').map(asObject)
}

function sources(value: JsonObject): JsonObject[] {
  return arrayAt(value, 'sources').map(asObject)
}

function actions(value: JsonObject): JsonObject[] {
  return arrayAt(value, 'actions').map(asObject)
}

function breadcrumbs(value: JsonObject): JsonObject[] {
  return arrayAt(value, 'breadcrumbs').map(asObject)
}

function expectMismatch(value: unknown): void {
  try {
    parseCompanyPublicH1(value)
    throw new Error('expected parser mismatch')
  } catch (error) {
    expect(error).toBeInstanceOf(CompanyReportContractError)
    expect((error as CompanyReportContractError).code)
      .toBe('company_public_h1_contract_mismatch')
    expect((error as Error).message).toBe('company_public_h1_contract_mismatch')
  }
}

const allLimitations = [
  ['arbitration_dataset_failed', 'arbitration', null, 'Арбитражные сведения недоступны из-за ошибки получения или нормализации.'],
  ['arbitration_dataset_not_found', 'arbitration', null, 'Арбитражные сведения не найдены в области ответа источника; отсутствие дел не предполагается.'],
  ['arbitration_malformed_records', 'arbitration', null, 'Часть арбитражных записей пропущена из-за некорректной структуры.'],
  ['arbitration_partial_slice', 'arbitration', null, 'Показана только сохранённая часть арбитражных сведений.'],
  ['arbitration_unknown_currency', 'arbitration', 'arbitration.claim_amounts', 'Часть сумм требований не показана: валюта источника не распознана.'],
  ['arbitration_identity_conflict', 'arbitration', 'arbitration.selected_cases.attributed_role', 'Роль компании в отдельных делах не определена из-за противоречивых идентификаторов.'],
  ['arbitration_target_identity_incomplete', 'arbitration', 'arbitration.selected_cases.attributed_role', 'Роль компании в отдельных делах не определена из-за неполных идентификаторов.'],
  ['legacy_arbitration_role_detail_unavailable', 'arbitration', 'arbitration.selected_cases.attributed_role', 'Для отчёта версии 1 детализация роли по отдельным делам недоступна.'],
  ['bankruptcy_operational_gate_not_passed', 'bankruptcy', null, 'Дополнительный запрос банкротных публикаций не активирован.'],
  ['bankruptcy_schema_gate_not_passed', 'bankruptcy', null, 'Сведения о банкротных публикациях не запрашивались: схема источника не подтверждена.'],
  ['finance_dataset_failed', 'finance', null, 'Финансовые сведения недоступны из-за ошибки получения или нормализации.'],
  ['finance_dataset_not_found', 'finance', null, 'Финансовые сведения не найдены в области ответа источника; нулевые значения не предполагаются.'],
  ['finance_unit_evidence_not_passed', 'finance', 'finance.metrics.money', 'Денежные значения не показаны: единица источника не подтверждена сохранёнными доказательствами.'],
  ['finance_series_conflict', 'finance', 'finance.metrics.yoy', 'Изменение показателя не рассчитано из-за неоднозначного сопоставления периодов.'],
  ['identity_status_conflict', 'identity_status', 'identity.status_label', 'Статус компании не отображён из-за противоречивых сохранённых сведений.'],
  ['identity_status_mapping_unknown', 'identity_status', 'identity.status_label', 'Статус компании не отображён: значение отсутствует в утверждённом справочнике.'],
  ['management_operational_gate_not_passed', 'management', null, 'Дополнительные блоки руководителей и владельцев не запрашивались.'],
  ['management_privacy_gate_not_passed', 'management', null, 'Персональные сведения о руководителях не публикуются без утверждённой privacy policy.'],
  ['management_schema_gate_not_passed', 'management', null, 'Сведения о владельцах не публикуются: схема и семантика долей не подтверждены.'],
  ['address_marked_inaccurate', 'requisites', 'requisites.legal_address', 'Источник пометил юридический адрес как недостоверный.'],
  ['address_not_requested', 'requisites', 'requisites.legal_address', 'Юридический адрес не запрашивался в сохранённом отчёте.'],
  ['legal_form_mapping_unknown', 'requisites', 'requisites.legal_form', 'Организационно-правовая форма не отображена: значение отсутствует в утверждённом справочнике.'],
  ['tax_operational_gate_not_passed', 'tax', null, 'Дополнительный запрос налоговых сведений не активирован.'],
  ['tax_schema_gate_not_passed', 'tax', null, 'Налоговые сведения не запрашивались: схема источника не подтверждена.'],
] as const

function limitationObjects(): JsonObject[] {
  return allLimitations.map(([code, blockId, fieldId, message]) => ({
    code,
    block_id: blockId,
    field_id: fieldId,
    message,
  }))
}

const reservedMoney = {
  source_decimal: '90071992547409931234567890.123456789',
  source_unit: 'thousand_rub',
  rub_decimal: '90071992547409931234567890123.456789',
  display_value: '90 071 992 547 409 931 234 567 890 123,456789 ₽',
  unit_policy_version: 'finance_unit_v1',
}

describe('company public H1 root contract', () => {
  it('parses v1/v2 and published/latest projections into detached allowlisted objects', () => {
    const publishedInput = published()
    const latestInput = latest()
    const parsedPublished = parseCompanyPublicH1(publishedInput)
    const parsedLatest = parseCompanyPublicH1(latestInput)

    expect(parsedPublished.report_version).toBe('2')
    expect(parsedPublished.projection_scope).toBe('published')
    expect(parsedLatest.report_version).toBe('1')
    expect(parsedLatest.projection_scope).toBe('latest_unpublished')
    expect(parsedLatest.indexable).toBe(false)
    expect(parsedPublished).not.toBe(publishedInput)
    expect(parsedPublished.identity).not.toBe(publishedInput.identity)
    expect(parsedPublished.blocks.finance?.metrics[0].yoy.exact_percent).toBe('12.34')
    expect(parsedPublished.blocks.arbitration?.claim_amounts[0].exact_decimal)
      .toBe('1000.5')
  })

  it.each([
    '00000000-0000-0000-0000-000000000000',
    '00000000-0000-0000-0000-000000000001',
    'ffffffff-ffff-ffff-ffff-ffffffffffff',
  ])('accepts backend-valid canonical UUID %s', (reportId) => {
    const value = published()
    value.report_id = reportId
    actions(value)[1].path = `/claims?report_id=${reportId}`
    expect(parseCompanyPublicH1(value).report_id).toBe(reportId)
  })

  it.each([
    'not-a-uuid',
    '11111111111141118111111111111111',
    '11111111-1111-4111-8111-11111111111g',
    '11111111-1111-4111-8111-111111111111-extra',
  ])('rejects malformed UUID %s', (reportId) => {
    const value = published()
    value.report_id = reportId
    expectMismatch(value)
  })

  it('requires every exact key at root and nested levels', () => {
    const extraRoot = published()
    extraRoot.unapproved = true
    expectMismatch(extraRoot)

    const missingRoot = published()
    delete missingRoot.checked_at
    expectMismatch(missingRoot)

    const extraNested = published()
    objectAt(financeMetric(extraNested), 'yoy').unexpected = 'x'
    expectMismatch(extraNested)

    const missingNullable = published()
    delete sources(missingNullable)[0].period
    expectMismatch(missingNullable)
  })

  it.each([
    'raw_payload', 'headers', 'authorization', 'api_key', 'apikey',
    'provider_limit_metadata', 'request_id', 'endpoint', 'response_hash',
    'provider_status_code', 'http_status_code', 'result_status',
    'result_status_code', 'attempts', 'duration_ms', 'worker_token',
    'lease_expires_at', 'safe_error_type', 'raw_role', 'raw_status',
    'raw_result_type', 'source_paths', 'requested_filters', 'factual_basis',
    'evaluation_basis', 'signals', 'scoring', 'score', 'verdict',
    'probability', 'ai_explanation', 'innfl', 'contacts', 'phone', 'email',
    'website', 'social', 'fssp',
  ])('recursively rejects case-insensitive forbidden key %s', (key) => {
    const value = published()
    const nested = asObject(arrayAt(arbitration(value), 'selected_cases')[0])
    const mixedCase = key.split('').map((character, index) =>
      index % 2 === 0 ? character.toUpperCase() : character).join('')
    nested[mixedCase] = 'must not survive'
    expectMismatch(value)
  })

  it('keeps the legitimate mapped identity status_code key while its value gate is disabled', () => {
    const parsed = parseCompanyPublicH1(published())
    expect(Object.hasOwn(parsed.identity, 'status_code')).toBe(true)
    expect(parsed.identity.status_code).toBeNull()
  })

  it.each([
    ['contract_version', 'company_public_h1_v2'],
    ['report_version', '3'],
    ['projection_scope', 'draft'],
  ])('rejects unknown closed root catalog value %s', (key, invalid) => {
    const value = published()
    value[key] = invalid
    expectMismatch(value)
  })

  it('enforces latest indexability but permits a non-indexable published projection', () => {
    const invalid = latest()
    invalid.indexable = true
    expectMismatch(invalid)

    const valid = published()
    valid.indexable = false
    expect(parseCompanyPublicH1(valid).indexable).toBe(false)
  })
})

describe('identifiers, paths and calendar strings', () => {
  it('accepts a recognized-form v2 canonical path bound to the identity INN', () => {
    const value = published()
    const canonicalPath = '/company/ooo-sintetika-1234567890'
    value.canonical_path = canonicalPath
    breadcrumbs(value)[1].path = canonicalPath

    expect(parseCompanyPublicH1(value).canonical_path).toBe(canonicalPath)
  })

  it('mirrors Python whitespace semantics without treating U+FEFF as whitespace', () => {
    const value = published()
    objectAt(value, 'identity').legal_full_name = 'ООО\uFEFFСинтетика'
    expect(parseCompanyPublicH1(value).identity.legal_full_name).toBe('ООО\uFEFFСинтетика')

    const nonCanonical = published()
    objectAt(nonCanonical, 'identity').legal_full_name = '  ООО   Синтетика  '
    expectMismatch(nonCanonical)
  })

  it.each([
    ['identity INN', (value: JsonObject) => { objectAt(value, 'identity').inn = '１２３４５６７８９０' }],
    ['identity INN length', (value: JsonObject) => { objectAt(value, 'identity').inn = '12345678901' }],
    ['KPP', (value: JsonObject) => { objectAt(blocks(value), 'requisites').kpp = '12345678A' }],
    ['OGRN', (value: JsonObject) => { objectAt(blocks(value), 'requisites').ogrn_or_ogrnip = '123456789012' }],
    ['cross-INN canonical', (value: JsonObject) => { value.canonical_path = '/company/0000000000-sinteticheskaya-kompaniya' }],
    ['uppercase slug', (value: JsonObject) => { value.canonical_path = '/company/1234567890-Sinteticheskaya' }],
    ['external canonical', (value: JsonObject) => { value.canonical_path = 'https://example.test/company/1234567890-x' }],
  ])('rejects malformed %s', (_label, mutate) => {
    const value = published()
    mutate(value)
    expectMismatch(value)
  })

  it('validates real Gregorian dates without deriving them from checked_at', () => {
    const leap = published()
    leap.checked_date = '2024-02-29'
    leap.checked_date_display = '29 февраля 2024 года'
    leap.checked_at = '2026-08-20T10:00:00.123456Z'
    expect(parseCompanyPublicH1(leap).checked_date).toBe('2024-02-29')

    for (const invalidDate of [
      '0000-01-01', '2023-02-29', '2024-02-30', '2026-04-31',
      '2026-00-01', '2026-13-01', '2026-01-00', '2026-1-01',
    ]) {
      const value = published()
      value.checked_date = invalidDate
      expectMismatch(value)
    }
  })

  it.each([
    '2023-02-29T10:00:00Z',
    '0000-01-01T00:00:00Z',
    '2026-01-01T24:00:00Z',
    '2026-01-01T23:60:00Z',
    '2026-01-01T23:59:60Z',
    '2026-01-01T23:59:59.1234567Z',
    '2026-01-01T23:59:59+00:00',
    '2026-01-01T23:59:59z',
  ])('rejects non-real or non-UTC timestamp %s', (timestamp) => {
    const value = published()
    value.checked_at = timestamp
    expectMismatch(value)
  })

  it('requires the exact checked date display string relation', () => {
    const value = published()
    value.checked_date_display = '20 Августа 2026'
    expectMismatch(value)
  })
})

describe('exact Decimal and finance invariants', () => {
  it.each([
    ['0', '+0,0%'],
    ['1.24', '+1,2%'],
    ['1.25', '+1,3%'],
    ['9.99', '+10,0%'],
    ['-1.24', '-1,2%'],
    ['-1.25', '-1,3%'],
    ['-0.01', '-0,0%'],
    ['90071992547409931234567890.55', '+90071992547409931234567890,6%'],
  ])('validates ROUND_HALF_UP without loss for %s', (exact, display) => {
    const value = published()
    yoy(value).exact_percent = exact
    yoy(value).display_value = display
    const parsed = parseCompanyPublicH1(value)
    expect(parsed.blocks.finance?.metrics[0].yoy.exact_percent).toBe(exact)
    expect(parsed.blocks.finance?.metrics[0].yoy.display_value).toBe(display)
  })

  it.each([
    '1e2', '+1', '1.', '01', '00.1', '1.20', '-0', '-0.0',
    'NaN', 'Infinity', ' 1', '1 ', '',
  ])('rejects non-canonical Decimal %s', (invalid) => {
    const value = published()
    yoy(value).exact_percent = invalid
    expectMismatch(value)
  })

  it('rejects numeric Decimal input and server display mismatch', () => {
    const numeric = published()
    yoy(numeric).exact_percent = 12.34
    expectMismatch(numeric)

    const wrongDisplay = published()
    yoy(wrongDisplay).display_value = '+12,4%'
    expectMismatch(wrongDisplay)
  })

  it('allows signed safe years and requires adjacent YoY periods losslessly', () => {
    const negativeYears = published()
    financeMetric(negativeYears).year = -1
    yoy(negativeYears).current_year = -1
    yoy(negativeYears).previous_year = -2
    expect(parseCompanyPublicH1(negativeYears).blocks.finance?.metrics[0].year)
      .toBe(-1)

    const nonAdjacent = published()
    yoy(nonAdjacent).previous_year = 2023
    expectMismatch(nonAdjacent)
  })

  it.each([
    ['empty metrics', (value: JsonObject) => { finance(value).metrics = [] }],
    ['unit policy enabled', (value: JsonObject) => { finance(value).unit_policy_version = 'v1' }],
    ['money enabled', (value: JsonObject) => { financeMetric(value).money = reservedMoney }],
    ['YoY absent', (value: JsonObject) => { financeMetric(value).yoy = null }],
    ['unknown metric', (value: JsonObject) => { financeMetric(value).metric_id = 'ebitda' }],
    ['unknown formula', (value: JsonObject) => { yoy(value).formula_version = 'finance_yoy_v2' }],
  ])('rejects current finance violation: %s', (_label, mutate) => {
    const value = published()
    mutate(value)
    expectMismatch(value)
  })
})

describe('safe integer and arbitration invariants', () => {
  it.each([
    -1,
    1.5,
    '1',
    Number.NaN,
    Number.POSITIVE_INFINITY,
    Number.MAX_SAFE_INTEGER + 1,
  ])('rejects invalid count value %s', (invalid) => {
    const value = published()
    arbitration(value).total_cases = invalid
    expectMismatch(value)
  })

  it('rejects negative count/offset and zero or negative limits across numeric surfaces', () => {
    const mutations: Array<(value: JsonObject) => void> = [
      (value) => { arbitration(value).malformed_count = -1 },
      (value) => { arbitration(value).offset = -1 },
      (value) => { arbitration(value).limit = 0 },
      (value) => { arbitration(value).limit = -1 },
      (value) => { coverage(value)[2].total = -1 },
      (value) => { coverage(value)[2].offset = -1 },
      (value) => { coverage(value)[2].limit = 0 },
    ]
    for (const mutate of mutations) {
      const value = published()
      mutate(value)
      expectMismatch(value)
    }
  })

  it('uses lossless BigInt arbitration sums at the safe-integer boundary', () => {
    const value = published()
    const block = arbitration(value)
    const maximum = Number.MAX_SAFE_INTEGER
    block.total_cases = maximum
    block.returned_cases = maximum
    block.normalized_case_count = maximum
    block.malformed_count = 0
    const roles = objectAt(block, 'role_counts')
    roles.plaintiff = 4_503_599_627_370_496
    roles.respondent = 4_503_599_627_370_495
    roles.applicant = 0
    roles.creditor = 0
    roles.debtor = 0
    roles.other = 0
    const statuses = objectAt(block, 'status_counts')
    statuses.open = 4_503_599_627_370_496
    statuses.completed = 4_503_599_627_370_495
    statuses.unknown = 0
    const results = objectAt(block, 'result_counts')
    results.satisfied_full = 4_503_599_627_370_496
    results.refused = 4_503_599_627_370_495
    results.returned = 0
    results.undefined = 0
    results.other = 0
    coverage(value)[2].total = maximum
    coverage(value)[2].returned = maximum
    expect(parseCompanyPublicH1(value).blocks.arbitration?.normalized_case_count)
      .toBe(maximum)

    roles.respondent = 4_503_599_627_370_496
    expectMismatch(value)
  })

  it.each([
    ['role sum', (block: JsonObject) => { objectAt(block, 'role_counts').plaintiff = 9 }],
    ['returned sum', (block: JsonObject) => { block.malformed_count = 1 }],
    ['status sum', (block: JsonObject) => { objectAt(block, 'status_counts').open = 1 }],
    ['result sum', (block: JsonObject) => { objectAt(block, 'result_counts').other = 9 }],
  ])('rejects arbitration %s mismatch', (_label, mutate) => {
    const value = published()
    mutate(arbitration(value))
    expectMismatch(value)
  })

  it.each([
    ['currency', (claim: JsonObject) => { claim.currency = 'rub' }],
    ['display', (claim: JsonObject) => { claim.display_value = '1 000,5 RUB' }],
    ['aggregate role', (claim: JsonObject) => { claim.role = 'applicant' }],
    ['Decimal', (claim: JsonObject) => { claim.exact_decimal = '1000.50' }],
  ])('rejects invalid aggregate claim %s', (_label, mutate) => {
    const value = published()
    const claim = asObject(arrayAt(arbitration(value), 'claim_amounts')[0])
    mutate(claim)
    expectMismatch(value)
  })

  it('requires case claim role attribution and caps selected cases at ten', () => {
    const wrongAttributed = published()
    const selected = asObject(arrayAt(arbitration(wrongAttributed), 'selected_cases')[0])
    selected.attributed_role = 'applicant'
    expectMismatch(wrongAttributed)

    const wrongClaimRole = published()
    objectAt(
      asObject(arrayAt(arbitration(wrongClaimRole), 'selected_cases')[0]),
      'claim_amount',
    ).role = 'respondent'
    expectMismatch(wrongClaimRole)

    const tooMany = published()
    const cases = arrayAt(arbitration(tooMany), 'selected_cases')
    cases.push(structuredClone(cases[0]))
    expectMismatch(tooMany)
  })
})

describe('coverage, sources and limitations', () => {
  it.each([
    'available', 'available_empty', 'not_found', 'not_requested', 'partial',
    'failed', 'conflict',
  ])('accepts closed coverage state %s where the backend has no stronger relation', (state) => {
    const value = published()
    coverage(value)[1].state = state
    expect(parseCompanyPublicH1(value).coverage[1].state).toBe(state)
  })

  it('requires the exact six coverage order and dataset mapping', () => {
    const swapped = published()
    const items = arrayAt(swapped, 'coverage')
    ;[items[0], items[1]] = [items[1], items[0]]
    expectMismatch(swapped)

    const wrongDataset = published()
    coverage(wrongDataset)[4].dataset = 'bankruptcy'
    expectMismatch(wrongDataset)

    const unknownState = published()
    coverage(unknownState)[1].state = 'unknown'
    expectMismatch(unknownState)
  })

  it('requires exact current optional coverage gates and their backend order', () => {
    const mutations: Array<(items: JsonObject[]) => void> = [
      (items) => { items[3].state = 'available' },
      (items) => { items[3].total = 0 },
      (items) => { items[3].limitation_codes = ['bankruptcy_operational_gate_not_passed', 'bankruptcy_schema_gate_not_passed'] },
      (items) => { items[4].returned = 0 },
      (items) => { items[4].limitation_codes = ['tax_operational_gate_not_passed', 'tax_schema_gate_not_passed'] },
      (items) => { items[5].offset = 0 },
      (items) => { items[5].limitation_codes = ['management_schema_gate_not_passed', 'management_privacy_gate_not_passed', 'management_operational_gate_not_passed'] },
    ]
    for (const mutate of mutations) {
      const value = published()
      mutate(coverage(value))
      expectMismatch(value)
    }
  })

  it('requires every coverage code to resolve to an exact present limitation', () => {
    const value = published()
    coverage(value)[1].limitation_codes = ['finance_dataset_failed']
    expectMismatch(value)
  })

  it('accepts all 24 exact limitation catalog entries in lexical tuple order', () => {
    const value = published()
    value.limitations = limitationObjects()
    expect(parseCompanyPublicH1(value).limitations).toHaveLength(24)
  })

  it('rejects unknown, altered, duplicate and unsorted limitations', () => {
    const unknown = published()
    asObject(arrayAt(unknown, 'limitations')[0]).code = 'new_browser_limitation'
    expectMismatch(unknown)

    const altered = published()
    asObject(arrayAt(altered, 'limitations')[0]).message = 'Усиленное браузером сообщение.'
    expectMismatch(altered)

    const duplicate = published()
    const duplicateItems = arrayAt(duplicate, 'limitations')
    duplicateItems.splice(1, 0, structuredClone(duplicateItems[0]))
    expectMismatch(duplicate)

    const unsorted = published()
    const unsortedItems = arrayAt(unsorted, 'limitations')
    ;[unsortedItems[0], unsortedItems[1]] = [unsortedItems[1], unsortedItems[0]]
    expectMismatch(unsorted)
  })

  it('requires unique sources in fixed precedence with honest versions', () => {
    const v1 = published()
    v1.report_version = '1'
    sources(v1)[2].normalization_version = 'arbitration_normalizer_v1'
    expect(parseCompanyPublicH1(v1).sources[2].normalization_version)
      .toBe('arbitration_normalizer_v1')

    const wrongVersion = published()
    sources(wrongVersion)[2].normalization_version = 'arbitration_normalizer_v1'
    expectMismatch(wrongVersion)

    const duplicate = published()
    arrayAt(duplicate, 'sources').push(structuredClone(arrayAt(duplicate, 'sources')[2]))
    expectMismatch(duplicate)

    const reordered = published()
    const reorderedSources = arrayAt(reordered, 'sources')
    ;[reorderedSources[0], reorderedSources[1]] = [reorderedSources[1], reorderedSources[0]]
    expectMismatch(reordered)
  })

  it.each(['tax_info', 'bankruptcy'])('rejects impossible current source dataset %s', (dataset) => {
    const value = published()
    sources(value)[1].dataset = dataset
    expectMismatch(value)
  })

  it('rejects unknown source catalogs and invalid source dates', () => {
    const unknownDataset = published()
    sources(unknownDataset)[0].dataset = 'contacts'
    expectMismatch(unknownDataset)

    const unknownNormalizer = published()
    sources(unknownNormalizer)[0].normalization_version = 'counterparty_normalizer_v2'
    expectMismatch(unknownNormalizer)

    const invalidTimestamp = published()
    sources(invalidTimestamp)[0].received_at = '2026-02-30T00:00:00Z'
    expectMismatch(invalidTimestamp)

    const invalidEffectiveDate = published()
    sources(invalidEffectiveDate)[0].effective_at = '2025-02-29'
    expectMismatch(invalidEffectiveDate)
  })
})

describe('root disabled gates and relational manifests', () => {
  it('requires all current status, legal-form, money, optional-block and link gates', () => {
    const mutations: Array<(value: JsonObject) => void> = [
      (value) => { objectAt(value, 'identity').status_code = 'ACTIVE' },
      (value) => { objectAt(value, 'identity').status_label = 'Действует' },
      (value) => { objectAt(value, 'identity').status_effective_at = '2026-01-01' },
      (value) => { objectAt(blocks(value), 'requisites').legal_form = 'ООО' },
      (value) => { blocks(value).tax = { unpaid_debt_indicator: false } },
      (value) => { blocks(value).bankruptcy = {} },
      (value) => { blocks(value).management = {} },
      (value) => { value.internal_links = [{ label: 'Связь', path: '/company/x', relation: 'related' }] },
    ]
    for (const mutate of mutations) {
      const value = published()
      mutate(value)
      expectMismatch(value)
    }
  })

  it('requires block order calculated only from parsed current factual blocks', () => {
    const wrongOrder = published()
    const order = arrayAt(wrongOrder, 'block_order')
    ;[order[5], order[6]] = [order[6], order[5]]
    expectMismatch(wrongOrder)

    const duplicate = published()
    arrayAt(duplicate, 'block_order')[5] = 'coverage_checked_at'
    expectMismatch(duplicate)

    const unknown = published()
    arrayAt(unknown, 'block_order')[5] = 'contacts'
    expectMismatch(unknown)

    const nullableMismatch = published()
    blocks(nullableMismatch).finance = null
    expectMismatch(nullableMismatch)
  })

  it('requires exact action order, labels, same-report claim path and breadcrumbs', () => {
    const actionOrder = published()
    const actionItems = arrayAt(actionOrder, 'actions')
    ;[actionItems[0], actionItems[1]] = [actionItems[1], actionItems[0]]
    expectMismatch(actionOrder)

    const actionLabel = published()
    actions(actionLabel)[1].label = 'Создать претензию'
    expectMismatch(actionLabel)

    const crossReport = published()
    actions(crossReport)[1].path = '/claims?report_id=00000000-0000-0000-0000-000000000000'
    expectMismatch(crossReport)

    const breadcrumbHome = published()
    breadcrumbs(breadcrumbHome)[0].path = '/home'
    expectMismatch(breadcrumbHome)

    const breadcrumbCompany = published()
    breadcrumbs(breadcrumbCompany)[1].label = 'Другая компания'
    expectMismatch(breadcrumbCompany)

    const breadcrumbPath = published()
    breadcrumbs(breadcrumbPath)[1].path = '/company/1234567890-other'
    expectMismatch(breadcrumbPath)
  })
})

describe('detached reserved DTO parsers', () => {
  it('parses exact money without converting protected Decimal or display strings', () => {
    const parsed = parseReservedMoney(reservedMoney)
    expect(parsed.source_decimal).toBe(reservedMoney.source_decimal)
    expect(parsed.rub_decimal).toBe(reservedMoney.rub_decimal)
    expect(parsed.display_value).toBe(reservedMoney.display_value)
    expect(parsed).not.toBe(reservedMoney)
  })

  it.each(['1.0', '01', '-0', '1e3', 1])('rejects reserved money Decimal %s', (invalid) => {
    expect(() => parseReservedMoney({ ...reservedMoney, source_decimal: invalid }))
      .toThrow(CompanyReportContractError)
  })

  it('parses reserved tax false/true message catalogs and nested money', () => {
    const falseBlock = {
      unpaid_debt_indicator: false,
      message: 'Признак неоплаченной налоговой задолженности не установлен.',
      as_of_date: '2024-02-29',
      records: [{
        record_type: 'synthetic_record',
        document_date: null,
        period: '',
        amount: reservedMoney,
      }],
    }
    expect(parseReservedTaxBlock(falseBlock).records[0].period).toBe('')
    const trueBlock = {
      ...falseBlock,
      unpaid_debt_indicator: true,
      message: 'Источник передал признак неоплаченной налоговой задолженности.',
    }
    expect(parseReservedTaxBlock(trueBlock).unpaid_debt_indicator).toBe(true)
    expect(() => parseReservedTaxBlock({ ...trueBlock, message: falseBlock.message }))
      .toThrow(CompanyReportContractError)
  })

  it('rejects malformed reserved tax record topology and scalars', () => {
    const block = {
      unpaid_debt_indicator: false,
      message: 'Признак неоплаченной налоговой задолженности не установлен.',
      as_of_date: null,
      records: [{
        record_type: 'synthetic_record', document_date: '2024-02-29',
        period: '2024', amount: null,
      }],
    }
    const mutations: Array<(value: typeof block) => void> = [
      (value) => { delete (value.records[0] as Partial<typeof value.records[0]>).period },
      (value) => { Object.assign(value.records[0], { extra: true }) },
      (value) => { value.records[0].record_type = '  non canonical  ' },
      (value) => { value.records[0].document_date = '2023-02-29' },
    ]
    for (const mutate of mutations) {
      const value = structuredClone(block)
      mutate(value)
      expect(() => parseReservedTaxBlock(value)).toThrow(CompanyReportContractError)
    }
    expect(() => parseReservedTaxBlock({ ...block, records: {} }))
      .toThrow(CompanyReportContractError)
  })

  it('parses reserved bankruptcy catalogs and exact disclaimer', () => {
    const block = {
      total: 3,
      returned: 3,
      limit: 10,
      offset: 0,
      typed_counts: { debtor_intention: 1, creditor_intention: 1, unknown: 1 },
      publications: [
        {
          safe_reference: 'synthetic-1', publication_date: '2024-02-29',
          kind: 'debtor_intention',
          message: 'Опубликовано намерение должника обратиться в суд с заявлением о банкротстве.',
          participant_role: 'debtor',
        },
        {
          safe_reference: null, publication_date: null,
          kind: 'creditor_intention',
          message: 'Опубликовано намерение кредитора обратиться в суд с заявлением о банкротстве компании.',
          participant_role: 'creditor',
        },
        {
          safe_reference: 'synthetic-3', publication_date: '2025-01-01',
          kind: 'unknown', message: 'Тип публикации не классифицирован',
          participant_role: 'unknown',
        },
      ],
      disclaimer: 'Наличие публикации не подтверждает, что заявление принято судом, возбуждено дело, компания признана банкротом или процедура продолжается сейчас.',
    }
    expect(parseReservedBankruptcyBlock(block).publications).toHaveLength(3)
    expect(() => parseReservedBankruptcyBlock({ ...block, limit: 0 }))
      .toThrow(CompanyReportContractError)
    expect(() => parseReservedBankruptcyBlock({ ...block, disclaimer: 'Банкротство подтверждено.' }))
      .toThrow(CompanyReportContractError)
    const wrongMessage = structuredClone(block)
    wrongMessage.publications[0].message = 'Иное сообщение'
    expect(() => parseReservedBankruptcyBlock(wrongMessage))
      .toThrow(CompanyReportContractError)
  })

  it('rejects malformed reserved bankruptcy nested keys, enums, dates and counters', () => {
    const block = {
      total: 1,
      returned: 1,
      limit: 1,
      offset: 0,
      typed_counts: { debtor_intention: 0, creditor_intention: 0, unknown: 1 },
      publications: [{
        safe_reference: 'synthetic', publication_date: '2025-01-01',
        kind: 'unknown', message: 'Тип публикации не классифицирован',
        participant_role: 'unknown',
      }],
      disclaimer: 'Наличие публикации не подтверждает, что заявление принято судом, возбуждено дело, компания признана банкротом или процедура продолжается сейчас.',
    }
    const invalidValues: unknown[] = []
    const missing = structuredClone(block)
    delete (missing.publications[0] as Partial<typeof missing.publications[0]>).safe_reference
    invalidValues.push(missing)
    const extra = structuredClone(block)
    Object.assign(extra.publications[0], { internal_id: 'hidden' })
    invalidValues.push(extra)
    const kind = structuredClone(block)
    kind.publications[0].kind = 'court_decision'
    invalidValues.push(kind)
    const role = structuredClone(block)
    role.publications[0].participant_role = 'plaintiff'
    invalidValues.push(role)
    const date = structuredClone(block)
    date.publications[0].publication_date = '2025-02-29'
    invalidValues.push(date)
    const count = structuredClone(block)
    count.typed_counts.unknown = -1
    invalidValues.push(count)
    const unsafe = structuredClone(block)
    unsafe.total = Number.MAX_SAFE_INTEGER + 1
    invalidValues.push(unsafe)
    for (const invalid of invalidValues) {
      expect(() => parseReservedBankruptcyBlock(invalid))
        .toThrow(CompanyReportContractError)
    }
  })

  it('parses non-empty reserved management with canonical owner share', () => {
    const block = {
      managers: [{
        name: 'Синтетический руководитель', role: 'Руководитель',
        appointed_at: '2024-02-29', is_inaccuracy: null,
      }],
      owners: [{
        name_or_org: 'ООО Синтетический владелец', owner_type: 'organization',
        organization_inn: '000000000000',
        organization_ogrn: '000000000000000',
        share_percent_decimal: '33.3333333333333333333333333',
        share_display: '', ownership_effective_at: null,
      }],
    }
    const parsed = parseReservedManagementBlock(block)
    expect(parsed.owners[0].share_percent_decimal)
      .toBe('33.3333333333333333333333333')
    expect(() => parseReservedManagementBlock({ managers: [], owners: [] }))
      .toThrow(CompanyReportContractError)
    const badShare = structuredClone(block)
    badShare.owners[0].share_percent_decimal = '33.330'
    expect(() => parseReservedManagementBlock(badShare))
      .toThrow(CompanyReportContractError)
    const badInn = structuredClone(block)
    badInn.owners[0].organization_inn = '００００００００００００'
    expect(() => parseReservedManagementBlock(badInn))
      .toThrow(CompanyReportContractError)
  })

  it('accepts managers-only and owners-only reserved management', () => {
    const manager = {
      name: 'Синтетический руководитель', role: 'Руководитель',
      appointed_at: null, is_inaccuracy: false,
    }
    const owner = {
      name_or_org: 'ООО Синтетический владелец', owner_type: 'organization',
      organization_inn: '0000000000', organization_ogrn: '0000000000000',
      share_percent_decimal: null, share_display: null,
      ownership_effective_at: '2024-02-29',
    }
    expect(parseReservedManagementBlock({ managers: [manager], owners: [] }).managers)
      .toHaveLength(1)
    expect(parseReservedManagementBlock({ managers: [], owners: [owner] }).owners)
      .toHaveLength(1)
  })

  it('rejects malformed reserved manager and owner topology/scalars', () => {
    const block = {
      managers: [{
        name: 'Синтетический руководитель', role: 'Руководитель',
        appointed_at: '2024-02-29', is_inaccuracy: null,
      }],
      owners: [{
        name_or_org: 'ООО Синтетический владелец', owner_type: 'organization',
        organization_inn: '0000000000', organization_ogrn: '0000000000000',
        share_percent_decimal: '50', share_display: '50%',
        ownership_effective_at: null,
      }],
    }
    const invalidValues: unknown[] = []
    const missingManagerKey = structuredClone(block)
    delete (missingManagerKey.managers[0] as Partial<typeof missingManagerKey.managers[0]>).role
    invalidValues.push(missingManagerKey)
    const extraManagerKey = structuredClone(block)
    Object.assign(extraManagerKey.managers[0], { innfl: 'hidden' })
    invalidValues.push(extraManagerKey)
    const managerDate = structuredClone(block)
    managerDate.managers[0].appointed_at = '2023-02-29'
    invalidValues.push(managerDate)
    const managerBoolean = structuredClone(block)
    asObject(managerBoolean.managers[0]).is_inaccuracy = 'false'
    invalidValues.push(managerBoolean)
    const managerText = structuredClone(block)
    managerText.managers[0].name = '  non canonical  '
    invalidValues.push(managerText)
    const missingOwnerKey = structuredClone(block)
    delete (missingOwnerKey.owners[0] as Partial<typeof missingOwnerKey.owners[0]>).owner_type
    invalidValues.push(missingOwnerKey)
    const extraOwnerKey = structuredClone(block)
    Object.assign(extraOwnerKey.owners[0], { person_identifier: 'hidden' })
    invalidValues.push(extraOwnerKey)
    const ownerType = structuredClone(block)
    ownerType.owners[0].owner_type = 'state'
    invalidValues.push(ownerType)
    const ownerOgrn = structuredClone(block)
    ownerOgrn.owners[0].organization_ogrn = '000000000000A'
    invalidValues.push(ownerOgrn)
    for (const invalid of invalidValues) {
      expect(() => parseReservedManagementBlock(invalid))
        .toThrow(CompanyReportContractError)
    }
  })

  it('parses only same-origin reserved internal links', () => {
    const link = { label: 'Связанная компания', path: '/company/0000000000-related?from=h1', relation: 'related' }
    expect(parseReservedInternalLink(link)).toEqual(link)
    for (const path of [
      'https://example.test/company/0000000000-x',
      '//example.test/company/0000000000-x',
      '/company\\0000000000-x',
      '/company/0000000000-x with-space',
    ]) {
      expect(() => parseReservedInternalLink({ ...link, path }))
        .toThrow(CompanyReportContractError)
    }
  })

  it('applies exact nested keys and recursive forbidden audit to detached parsers', () => {
    expect(() => parseReservedMoney({ ...reservedMoney, extra: true }))
      .toThrow(CompanyReportContractError)
    expect(() => parseReservedInternalLink({
      label: 'Связь', path: '/safe', relation: 'related', HeAdErS: {},
    })).toThrow(CompanyReportContractError)
  })
})

describe('safe error surface', () => {
  it('never exposes payload, INN, company name or failure reason', () => {
    const value = published()
    objectAt(value, 'identity').legal_full_name = 'СЕКРЕТНОЕ ИМЯ'
    value.raw_payload = { token: 'СЕКРЕТНЫЙ ТОКЕН' }
    try {
      parseCompanyPublicH1(value)
      throw new Error('expected parser mismatch')
    } catch (error) {
      expect(error).toBeInstanceOf(CompanyReportContractError)
      const message = (error as Error).message
      expect(message).toBe('company_public_h1_contract_mismatch')
      expect(message).not.toContain('СЕКРЕТ')
      expect(message).not.toContain('1234567890')
    }
  })
})
