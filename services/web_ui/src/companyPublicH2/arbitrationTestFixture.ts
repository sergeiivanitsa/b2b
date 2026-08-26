import sharedDto from '../../../../shared/fixtures/company_public_h2_contract_v1.json?raw'
import { canonicalProjectionDigest } from './canonicalJson'
import { parseCompanyPublicH2 } from './contract'
import type { CompanyPublicH2 } from './contractSchema'
import { parseStrictJson } from './strictJson'

type JsonObject = { [key: string]: unknown }

function scope(eligible: number, noun: 'дел' | 'сторон', collectionNonempty = true): JsonObject {
  const shown = Math.min(eligible, 20)
  return { population_scope: 'complete_collection', source_total: collectionNonempty ? 1 : 0, rows_received: collectionNonempty ? 1 : 0, eligible_total: eligible, shown, cap: 20, label: `показано ${shown} из ${eligible} ${noun}` }
}

function safeCase(): JsonObject {
  return {
    case_public_id: 'case_000001', case_number: 'А40-1/2025', year: 2025,
    role: 'plaintiff', outcome: 'won', result_detail: null,
    amount: { source_decimal: '125.5', source_currency_id: 'RUB', display_exact: '125,5 ₽' },
    start_date: '2025-01-01', update_date: '2025-01-02', days_to_last_update: 1,
    instance_count: null, courts: [], opponents: [], public_case_url: null,
  }
}

function summary(nonempty: boolean): JsonObject {
  return {
    source_total: nonempty ? 1 : 0, rows_observed: nonempty ? 1 : 0, unique_case_count: nonempty ? 1 : 0,
    malformed_count: 0, duplicate_identical_count: 0, duplicate_conflict_count: 0,
    collection_complete: true, completion_reason: 'complete', calendar_complete: false,
    calendar_scope: 'unverified', calendar_start_year: null, calendar_end_year: null,
    calendar_evidence_version: null, observed_start_year: nonempty ? 2025 : null,
    observed_end_year: nonempty ? 2025 : null, unknown_year_count: 0, zero_years_proven: false,
  }
}

function bars(categories: readonly string[], nonempty: boolean): JsonObject[] {
  return categories.map((category, index) => ({
    category_id: category, count: nonempty && index === 0 ? 1 : 0,
    percent_decimal: nonempty ? (index === 0 ? '100' : '0') : null,
    scope: scope(nonempty && index === 0 ? 1 : 0, 'дел', nonempty),
    cases: nonempty && index === 0 ? [safeCase()] : [],
  }))
}

function arbitrationBlocks(nonempty: boolean): JsonObject {
  const commonSummary = summary(nonempty)
  const roleDetails = ['plaintiff', 'respondent', 'other', 'unattributed'].map((role, index) => ({
    role, scope: scope(nonempty && index === 0 ? 1 : 0, 'дел', nonempty), cases: nonempty && index === 0 ? [safeCase()] : [],
  }))
  return {
    arbitration_a1: {
      view_id: 'arbitration_a1_activity', summary: commonSummary,
      displayed_start_year: nonempty ? 2025 : null, displayed_end_year: nonempty ? 2025 : null,
      buckets: nonempty ? [{ year: 2025, plaintiff_count: 1, respondent_count: 0, other_count: 0, unattributed_count: 0, total_count: 1, role_details: roleDetails }] : [],
      all_time_case_count: nonempty ? 1 : 0,
    },
    arbitration_a2: { view_id: 'arbitration_a2_roles', summary: commonSummary, denominator: nonempty ? 1 : 0, bars: bars(['plaintiff', 'respondent', 'other', 'unattributed'], nonempty) },
    arbitration_a3: { view_id: 'arbitration_a3_outcomes', summary: commonSummary, denominator: nonempty ? 1 : 0, bars: bars(['won', 'lost', 'returned', 'unknown'], nonempty) },
    arbitration_a4: {
      view_id: 'arbitration_a4_case_amounts', summary: commonSummary,
      currency_groups: nonempty ? [{ source_currency_id: 'RUB', display_currency: '₽', axis: { axis_min_decimal: '0', axis_max_decimal: '125.5' }, case_geometries: [{ case_public_id: 'case_000001', geometry: { start_ratio_decimal: '0', end_ratio_decimal: '125.5' } }], scope: scope(1, 'дел'), cases: [safeCase()] }] : [],
      missing_amount_count: 0, missing_currency_count: 0,
    },
    arbitration_a5: {
      view_id: 'arbitration_a5_opponents', summary: commonSummary, scope: scope(nonempty ? 1 : 0, 'сторон', nonempty),
      groups: nonempty ? [{ opponent_public_id: 'opponent_000001', display_name: 'Сторона скрыта 1', display_kind: 'masked_unknown', case_count: 1, case_scope: scope(1, 'дел'), cases: [safeCase()] }] : [],
      cases_without_safe_opponent: 0, multi_opponent_case_count: 0,
    },
  }
}

async function signedRaw(value: JsonObject): Promise<string> {
  value.projection_digest = '0'.repeat(64)
  value.projection_digest = await canonicalProjectionDigest(parseStrictJson(JSON.stringify(value)))
  return JSON.stringify(value)
}

export async function arbitrationPolicyV3Raw(nonempty = true): Promise<string> {
  const value = JSON.parse(sharedDto) as JsonObject
  const sources = value.sources as JsonObject[]
  sources[2] = { ...sources[2], effective_at: null, period: null, normalization_version: 'company_card_arbitration_normalization_v2', evidence_version: 'datanewton_arbitration_registry_v2' }
  Object.assign(value.blocks as JsonObject, arbitrationBlocks(nonempty))
  for (const item of value.coverage as JsonObject[]) {
    if (typeof item.block_id === 'string' && item.block_id.startsWith('arbitration_')) Object.assign(item, { state: nonempty ? 'available' : 'available_empty', population_scope: 'complete_collection', total: nonempty ? 1 : 0, returned: nonempty ? 1 : 0, eligible: nonempty ? 1 : 0, limitation_codes: item.block_id === 'arbitration_a1' ? ['arbitration_calendar_unverified'] : [] })
  }
  value.limitations = [...(value.limitations as JsonObject[]), { code: 'arbitration_calendar_unverified', block_id: 'arbitration_a1', field_id: null, message: 'Календарная полнота арбитражных данных не подтверждена.' }]
  return signedRaw(value)
}

export async function arbitrationSourceLessRaw(reason: 'operation_gate_closed' | 'evidence_gate_closed' | 'privacy_key_unavailable' | 'provider_error' | 'provider_binding_invalid' = 'operation_gate_closed'): Promise<string> {
  const value = JSON.parse(sharedDto) as JsonObject
  value.sources = (value.sources as JsonObject[]).slice(0, 2)
  const blocks = value.blocks as JsonObject
  for (const blockId of ['arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4', 'arbitration_a5']) blocks[blockId] = null
  for (const item of value.coverage as JsonObject[]) {
    if (typeof item.block_id === 'string' && item.block_id.startsWith('arbitration_')) Object.assign(item, { state: reason === 'operation_gate_closed' || reason === 'evidence_gate_closed' ? 'gate_closed' : 'failed', population_scope: 'not_applicable', total: null, returned: null, eligible: null, limitation_codes: [reason] })
  }
  const messages = {
    operation_gate_closed: 'Сбор арбитражных данных отключён операционным ограничением.',
    evidence_gate_closed: 'Арбитражные данные недоступны до подтверждения evidence gate.',
    privacy_key_unavailable: 'Арбитражные данные недоступны из-за закрытого privacy-контура.',
    provider_error: 'Подтверждённый источник арбитражных данных временно недоступен.',
    provider_binding_invalid: 'Ответ источника не прошёл проверку привязки к отчёту.',
  } as const
  value.limitations = [...(value.limitations as JsonObject[]).filter(item => typeof item.code !== 'string' || (!item.code.startsWith('arbitration_') && !['operation_gate_closed', 'evidence_gate_closed', 'privacy_key_unavailable', 'provider_error', 'provider_binding_invalid'].includes(item.code))), { code: reason, block_id: null, field_id: null, message: messages[reason] }]
  return signedRaw(value)
}

export async function arbitrationPolicyV3Dto(nonempty = true): Promise<CompanyPublicH2> {
  return (await parseCompanyPublicH2(await arbitrationPolicyV3Raw(nonempty))).dto
}
