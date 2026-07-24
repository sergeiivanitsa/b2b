import { apiFetchJson } from '../lib/api'
import type { CompanyReportAccepted, CompanyReportLifecycle, CompanyReportResponse } from './companyReportTypes'

export function getCompanyReport(inn: string, options: { includeAiExplanation?: boolean; signal?: AbortSignal } = {}): Promise<CompanyReportResponse> {
  const suffix = options.includeAiExplanation ? '?include_ai_explanation=true' : ''
  return apiFetchJson<CompanyReportResponse>(`/company-reports/${inn}${suffix}`, { signal: options.signal })
}

export function getCompanyReportStatus(inn: string, signal?: AbortSignal): Promise<CompanyReportLifecycle> {
  return apiFetchJson<CompanyReportLifecycle>(`/company-reports/${inn}/status`, { signal })
}

export function createCompanyReport(inn: string, signal?: AbortSignal): Promise<CompanyReportAccepted> {
  return apiFetchJson<CompanyReportAccepted>('/company-reports', { method: 'POST', body: { inn }, signal })
}
