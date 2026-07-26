const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const COMMAND_KEY_PREFIX = 'claims.company-report-handoff.command.v1.'

export function reportIdFromSearch(search: string): string | null {
  const value = new URLSearchParams(search).get('report_id')?.trim() ?? ''
  return UUID_RE.test(value) ? value.toLowerCase() : null
}

export function companyReportPath(reportId: string | null, inn: string | null): string | null {
  if (!reportId || !inn || !/^(?:\d{10}|\d{12})$/.test(inn)) return null
  // The public company route is INN based; no report data is placed in the URL.
  return `/company/${inn}`
}

export function createHandoffCommandKey(): string {
  return crypto.randomUUID()
}

export function readOrCreateHandoffCommandKey(reportId: string): string {
  const storage = getSessionStorage()
  const key = `${COMMAND_KEY_PREFIX}${reportId}`
  const current = storage?.getItem(key)?.trim()
  if (current) return current
  const created = createHandoffCommandKey()
  storage?.setItem(key, created)
  return created
}

export function clearHandoffCommandKey(reportId: string): void {
  getSessionStorage()?.removeItem(`${COMMAND_KEY_PREFIX}${reportId}`)
}

function getSessionStorage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.sessionStorage
  } catch {
    return null
  }
}
