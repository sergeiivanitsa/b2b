import { ApiHttpError } from '../lib/api'
import type {
  CoverageState,
  DatasetId,
  FactualBlockId,
  PublicFinanceMetricId,
} from './companyReportTypes'
import type { CompanyPublicH1Response } from './companyReportTypes'

export const STATUS_POLL_INTERVAL_MS = 3000
export const STATUS_AUTO_POLL_WINDOW_MS = 3 * 60 * 1000
export const HEAD_OWNER_ATTRIBUTE = 'data-company-report-head-owner'
export const HEAD_OWNER_VALUE = 'company-report-h1-v1'
export const HEAD_KIND_ATTRIBUTE = 'data-company-report-head-kind'
export const HEAD_PREVIOUS_LANG_ATTRIBUTE = 'data-company-report-previous-lang'

export type CompanyRouteKind = 'plain' | 'canonical'
export type CompanyKeyParseResult =
  | { kind: CompanyRouteKind; inn: string }
  | { error: 'invalid_company_key' }
export type H1Operation = 'read' | 'status' | 'create'
export type H1Error = {
  kind: 'terminal' | 'retryable'
  message: string
  operation: H1Operation | null
}

export function pendingAutoPollDeadlineMs(
  firstObservedAtMs: number,
  serverStartedAt: string | null,
): number {
  const localDeadline = firstObservedAtMs + STATUS_AUTO_POLL_WINDOW_MS
  if (serverStartedAt === null) return localDeadline
  const serverStartedAtMs = Date.parse(serverStartedAt)
  return Number.isFinite(serverStartedAtMs)
    ? Math.min(localDeadline, serverStartedAtMs + STATUS_AUTO_POLL_WINDOW_MS)
    : localDeadline
}

export const BLOCK_LABELS: Readonly<Record<FactualBlockId, string>> =
  Object.freeze({
    requisites: 'Реквизиты',
    finance: 'Финансовые показатели',
    arbitration: 'Арбитраж',
    bankruptcy: 'Банкротные публикации',
    tax: 'Налоговые сведения',
    management: 'Руководители и владельцы',
  })

export const DATASET_LABELS: Readonly<Record<DatasetId, string>> = Object.freeze(
  {
    counterparty: 'Сведения о компании',
    finance: 'Финансовые сведения',
    arbitration: 'Арбитражные сведения',
    bankruptcy: 'Банкротные публикации',
    tax_info: 'Налоговые сведения',
  },
)

export const COVERAGE_LABELS: Readonly<Record<CoverageState, string>> =
  Object.freeze({
    available: 'Сведения доступны',
    available_empty:
      'Источник успешно проверен; в подтверждённой области ответа записей нет',
    not_found: 'Источник не нашёл сведения в своей области ответа',
    not_requested: 'Сведения не запрашивались',
    partial: 'Доступна часть сведений',
    failed: 'Сведения недоступны',
    conflict: 'Сведения противоречивы',
  })

export const FINANCE_LABELS: Readonly<
  Record<PublicFinanceMetricId, string>
> = Object.freeze({
  total_assets: 'Активы',
  non_current_assets: 'Внеоборотные активы',
  current_assets: 'Оборотные активы',
  inventories: 'Запасы',
  accounts_receivable: 'Дебиторская задолженность',
  cash_and_equivalents: 'Денежные средства',
  equity: 'Капитал',
  long_term_liabilities: 'Долгосрочные обязательства',
  short_term_liabilities: 'Краткосрочные обязательства',
  short_term_borrowings: 'Краткосрочные займы',
  accounts_payable: 'Кредиторская задолженность',
  revenue: 'Выручка',
  cost_of_sales: 'Себестоимость продаж',
  gross_profit: 'Валовая прибыль',
  operating_profit: 'Прибыль от продаж',
  profit_before_tax: 'Прибыль до налогообложения',
  net_profit: 'Чистая прибыль',
  net_cash_flow: 'Чистый денежный поток',
  cash_at_start: 'Денежные средства на начало периода',
  cash_at_end: 'Денежные средства на конец периода',
})

export const ROLE_LABELS = Object.freeze({
  plaintiff: 'Истец',
  respondent: 'Ответчик',
  applicant: 'Заявитель',
  creditor: 'Кредитор',
  debtor: 'Должник',
  other: 'Иное',
  unattributed: 'Не отнесено',
})

export const STATUS_LABELS = Object.freeze({
  open: 'Открытые',
  completed: 'Завершённые',
  unknown: 'Неизвестно',
})

export const RESULT_LABELS = Object.freeze({
  satisfied_full: 'Удовлетворено полностью',
  refused: 'Отказано',
  returned: 'Возвращено',
  undefined: 'Не определено',
  other: 'Иное',
})

export function parseCompanyKey(
  value: string | undefined,
): CompanyKeyParseResult {
  const key = value ?? ''
  if (/^(\d{10}|\d{12})$/.test(key)) {
    return { kind: 'plain', inn: key }
  }
  const canonical = /^(\d{10}|\d{12})-[a-z0-9]+(?:-[a-z0-9]+)*$/.exec(
    key,
  )
  return canonical
    ? { kind: 'canonical', inn: canonical[1] }
    : { error: 'invalid_company_key' }
}

export function parseCompanyRoute(
  value: string | undefined,
  search: string,
): CompanyKeyParseResult {
  return search.length === 0
    ? parseCompanyKey(value)
    : { error: 'invalid_company_key' }
}

export function isCanonicalCompanyPath(
  value: string | null | undefined,
  inn: string,
): boolean {
  if (!value?.startsWith('/company/')) return false
  const parsed = parseCompanyKey(value.slice('/company/'.length))
  return (
    'kind' in parsed && parsed.kind === 'canonical' && parsed.inn === inn
  )
}

export function displayIsoDate(value: string): string {
  return `${value.slice(8, 10)}.${value.slice(5, 7)}.${value.slice(0, 4)}`
}

export function limitationDomId(code: string): string {
  return `company-report-limitation-${code}`
}

export function classifyH1Error(
  error: unknown,
  operation: H1Operation,
): H1Error {
  if (error instanceof ApiHttpError) {
    const code = errorCode(error)
    if (error.status === 429) {
      return {
        kind: 'retryable',
        message: 'Слишком много запросов. Повторите позже.',
        operation,
      }
    }
    if (error.status === 503) {
      return {
        kind: 'retryable',
        message: 'Сервис временно недоступен. Повторите позже.',
        operation,
      }
    }
    if (code === 'report_failed') {
      return {
        kind: 'terminal',
        message: 'Отчёт не сформирован',
        operation: null,
      }
    }
    if (
      code === 'report_not_eligible' ||
      code === 'public_projection_invalid'
    ) {
      return {
        kind: 'terminal',
        message: 'Публичный отчёт недоступен',
        operation: null,
      }
    }
    if (error.status === 404) {
      return {
        kind: 'terminal',
        message: 'Публичный отчёт не найден',
        operation: null,
      }
    }
    if (
      error.status === 401 ||
      error.status === 403 ||
      error.status === 409
    ) {
      return {
        kind: 'terminal',
        message: 'Публичный отчёт недоступен',
        operation: null,
      }
    }
  }
  return {
    kind: 'retryable',
    message: 'Не удалось подключиться к сервису. Повторите попытку.',
    operation,
  }
}

export function errorCode(error: unknown): string | null {
  if (
    !(error instanceof ApiHttpError) ||
    !error.payload ||
    typeof error.payload !== 'object'
  ) {
    return null
  }
  const detail = (error.payload as { detail?: unknown }).detail
  return detail &&
    typeof detail === 'object' &&
    typeof (detail as { code?: unknown }).code === 'string'
    ? (detail as { code: string }).code
    : null
}

type SavedHead = { title: string; lang: string }

let savedHead: SavedHead | null = null

function ownedSelector(kind?: 'robots' | 'canonical'): string {
  const owner = `[${HEAD_OWNER_ATTRIBUTE}="${HEAD_OWNER_VALUE}"]`
  return kind ? `${owner}[${HEAD_KIND_ATTRIBUTE}="${kind}"]` : owner
}

function removeOwned(kind: 'robots' | 'canonical'): void {
  document.head
    .querySelectorAll(ownedSelector(kind))
    .forEach((node) => node.remove())
}

function takeOne(
  kind: 'robots' | 'canonical',
  tag: 'meta' | 'link',
): HTMLMetaElement | HTMLLinkElement {
  const nodes = Array.from(document.head.querySelectorAll(ownedSelector(kind)))
  const expectedTag = tag.toUpperCase()
  const existing = nodes.find((node) => node.tagName === expectedTag)
  nodes.forEach((node) => {
    if (node !== existing) node.remove()
  })
  const result = existing ?? document.createElement(tag)
  result.setAttribute(HEAD_OWNER_ATTRIBUTE, HEAD_OWNER_VALUE)
  result.setAttribute(HEAD_KIND_ATTRIBUTE, kind)
  if (!result.parentElement) document.head.append(result)
  return result as HTMLMetaElement | HTMLLinkElement
}

function ensureCompanyHead(): void {
  if (!savedHead) {
    savedHead = {
      title: document.title,
      lang:
        document.documentElement.getAttribute(HEAD_PREVIOUS_LANG_ATTRIBUTE) ??
        document.documentElement.lang,
    }
  }
  document.documentElement.lang = 'ru'
  const robots = takeOne('robots', 'meta') as HTMLMetaElement
  robots.name = 'robots'
  robots.content = 'noindex,follow'
}

export function beginCompanyHead(): void {
  ensureCompanyHead()
  removeOwned('canonical')
}

export function setCompanyHead(dto: CompanyPublicH1Response): void {
  ensureCompanyHead()
  document.title = `${dto.identity.display_name} — ИНН ${dto.identity.inn}`
  const canonical = takeOne('canonical', 'link') as HTMLLinkElement
  canonical.rel = 'canonical'
  canonical.setAttribute('href', dto.canonical_path)
}

export function setCompanySafeTitle(title: string): void {
  beginCompanyHead()
  document.title = title
}

export function cleanupCompanyHead(): void {
  document.head
    .querySelectorAll(ownedSelector())
    .forEach((node) => node.remove())
  if (savedHead) {
    document.title = savedHead.title
    document.documentElement.lang = savedHead.lang
    savedHead = null
  }
  document.documentElement.removeAttribute(HEAD_PREVIOUS_LANG_ATTRIBUTE)
}
