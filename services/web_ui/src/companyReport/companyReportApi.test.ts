import { beforeEach, describe, expect, it, vi } from 'vitest'
import { apiFetchJson } from '../lib/api'
import { createCompanyReport, getCompanyPublicH1, getCompanyReportStatus } from './companyReportApi'
vi.mock('../lib/api', () => ({ apiFetchJson: vi.fn() }))
const api = vi.mocked(apiFetchJson)
describe('company public h1 API', () => { beforeEach(() => api.mockResolvedValue({} as never)); it('uses the exact public H1 path and forwards signal', async () => { const signal = new AbortController().signal; await expect(getCompanyPublicH1('1234567890', signal)).rejects.toMatchObject({ code: 'company_public_h1_contract_mismatch' }); expect(api).toHaveBeenCalledWith('/company-reports/1234567890/public-h1', { signal }) }); it('keeps lifecycle contracts', async () => { const signal = new AbortController().signal; await getCompanyReportStatus('1234567890', signal); await createCompanyReport('1234567890', signal); expect(api).toHaveBeenNthCalledWith(1, '/company-reports/1234567890/status', { signal }); expect(api).toHaveBeenNthCalledWith(2, '/company-reports', { method: 'POST', body: { inn: '1234567890' }, signal }) }) })
