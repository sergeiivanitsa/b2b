import { ApiHttpError } from '../lib/api'
import type { CounterpartyFacts, FinanceFacts, FinancePeriod, SafeWarning, SignalPeriod } from './companyReportTypes'

export const STATUS_POLL_INTERVAL_MS = 3000
export const NO_DATA = 'Нет данных'
export type CompanyKeyParseResult =
  | { kind: 'plain'; inn: string }
  | { kind: 'canonical'; inn: string }
  | { error: 'invalid_company_key' }

export function parseCompanyKey(value: string | undefined): CompanyKeyParseResult {
  const key = value ?? ''
  if (/^(\d{10}|\d{12})$/.test(key)) return { kind: 'plain', inn: key }
  const match = /^(\d{10}|\d{12})-([a-z0-9]+(?:-[a-z0-9]+)*)$/.exec(key)
  return match ? { kind: 'canonical', inn: match[1] } : { error: 'invalid_company_key' }
}

export function isCanonicalCompanyPath(value: string | null | undefined, inn: string): boolean {
  if (!value?.startsWith('/company/')) return false
  const parsed = parseCompanyKey(value.slice('/company/'.length))
  return 'kind' in parsed && parsed.kind === 'canonical' && parsed.inn === inn
}

export function displayValue(value: string | number | boolean | null | undefined): string {
  return value === null || value === undefined || value === '' ? NO_DATA : String(value)
}
export function displayDate(value: string | null | undefined): string { return displayValue(value) }
export function financeUnit(unit: string | null | undefined): string { return unit === 'provider_units_unknown' || !unit ? 'Единица измерения неизвестна' : unit }
export function financePeriods(finance: FinanceFacts | null | undefined): FinancePeriod[] { return finance?.periods ?? finance?.data ?? [] }
export function companyName(counterparty: CounterpartyFacts | null | undefined, inn: string): string { return counterparty?.short_name || counterparty?.full_name || `Компания с ИНН ${inn}` }
export function safeWarnings(warnings: SafeWarning[] | null | undefined): SafeWarning[] { return warnings ?? [] }
export function signalPeriodText(period: SignalPeriod | undefined): string {
  if (!period) return NO_DATA
  if (period.kind === 'no_period') return `На ${period.as_of}`
  if (period.kind === 'date') return period.value
  if (period.kind === 'date_range') return `${period.start} — ${period.end}`
  if (period.kind === 'year') return String(period.year)
  return `${period.start_year} — ${period.end_year}`
}

const SIGNAL_LABELS: Readonly<Record<string, string>> = Object.freeze({
  'counterparty.active': 'Компания отмечена действующей', 'counterparty.dissolved': 'Компания отмечена прекратившей деятельность',
  'counterparty.long_operating_history': 'Длительный срок деятельности', 'counterparty.status_conflict': 'Противоречивые сведения о статусе',
  'finance.negative_equity': 'Отрицательный капитал', 'finance.revenue_decline': 'Снижение выручки', 'finance.net_loss': 'Чистый убыток',
  'finance.cash_shortfall': 'Недостаток денежных средств', 'finance.high_accounts_payable': 'Высокая кредиторская задолженность',
  'arbitration.high_respondent_case_count': 'Много дел в роли ответчика', 'arbitration.respondent_case_growth': 'Рост дел в роли ответчика',
  'arbitration.open_cases': 'Открытые арбитражные дела', 'arbitration.frequent_plaintiff': 'Частые обращения в суд как истец',
})
export function signalLabel(code: string): string { return SIGNAL_LABELS[code] ?? 'Сигнал требует проверки' }
export function isKnownSignal(code: string): boolean { return code in SIGNAL_LABELS }

export function safeErrorMessage(error: unknown): string {
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return 'Необходимо войти в систему.'
    if (error.status === 403) return 'Недостаточно разрешений для просмотра отчёта.'
    if (error.status === 429) return 'Слишком много запросов. Повторите позже.'
    if (error.status === 503) return 'Сервис временно недоступен. Повторите позже.'
    if (error.status === 404) return 'Отчёт не найден.'
    return 'Не удалось получить отчёт. Повторите попытку.'
  }
  return 'Не удалось подключиться к сервису. Повторите попытку.'
}
export function errorCode(error: unknown): string | null {
  if (!(error instanceof ApiHttpError) || !error.payload || typeof error.payload !== 'object') return null
  const detail = (error.payload as { detail?: unknown }).detail
  return detail && typeof detail === 'object' && typeof (detail as { code?: unknown }).code === 'string' ? (detail as { code: string }).code : null
}
