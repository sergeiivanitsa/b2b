import { apiFetchJson } from '../lib/api'
import { parseCompanyPublicH1 } from './companyReportH1Contract'
import type { CompanyPublicH1Response, CompanyReportAccepted, CompanyReportLifecycle } from './companyReportTypes'

export async function getCompanyPublicH1(inn: string, signal?: AbortSignal): Promise<CompanyPublicH1Response> {
  return parseCompanyPublicH1(await apiFetchJson<unknown>(`/company-reports/${inn}/public-h1`, { signal }))
}

export function getCompanyReportStatus(inn: string, signal?: AbortSignal): Promise<CompanyReportLifecycle> {
  return apiFetchJson<CompanyReportLifecycle>(`/company-reports/${inn}/status`, { signal })
}

export function createCompanyReport(inn: string, signal?: AbortSignal): Promise<CompanyReportAccepted> {
  return apiFetchJson<CompanyReportAccepted>('/company-reports', { method: 'POST', body: { inn }, signal })
}
