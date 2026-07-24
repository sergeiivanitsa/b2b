import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiFetchJson } from '../lib/api'
import { createCompanyReport, getCompanyReport, getCompanyReportStatus } from './companyReportApi'

vi.mock('../lib/api', () => ({ apiFetchJson: vi.fn() }))
const mockedApiFetchJson = vi.mocked(apiFetchJson)

describe('company report API', () => {
  beforeEach(() => mockedApiFetchJson.mockResolvedValue({} as never))
  it('uses an ordinary GET without an AI query by default', async () => {
    const signal = new AbortController().signal
    await getCompanyReport('1234567890', { signal })
    expect(mockedApiFetchJson).toHaveBeenCalledWith('/company-reports/1234567890', { signal })
  })
  it('uses the AI query only when explicitly opted in', async () => {
    await getCompanyReport('1234567890', { includeAiExplanation: true })
    expect(mockedApiFetchJson).toHaveBeenCalledWith('/company-reports/1234567890?include_ai_explanation=true', { signal: undefined })
  })
  it('gets lifecycle status with its abort signal', async () => {
    const signal = new AbortController().signal
    await getCompanyReportStatus('1234567890', signal)
    expect(mockedApiFetchJson).toHaveBeenCalledWith('/company-reports/1234567890/status', { signal })
  })
  it('creates a report only through JSON POST with the INN body', async () => {
    const signal = new AbortController().signal
    await createCompanyReport('1234567890', signal)
    expect(mockedApiFetchJson).toHaveBeenCalledWith('/company-reports', { method: 'POST', body: { inn: '1234567890' }, signal })
  })
})
