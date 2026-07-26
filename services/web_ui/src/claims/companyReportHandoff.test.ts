import { describe, expect, it, vi } from 'vitest'

import { clearHandoffCommandKey, companyReportPath, createHandoffCommandKey, readOrCreateHandoffCommandKey, reportIdFromSearch } from './companyReportHandoff'

describe('company report handoff URL helpers', () => {
  it('accepts only a minimal UUID report identifier', () => {
    expect(reportIdFromSearch('?report_id=2e7e9d9f-5f3a-4d43-a8e8-2bb3c2adf6b1')).toBe('2e7e9d9f-5f3a-4d43-a8e8-2bb3c2adf6b1')
    expect(reportIdFromSearch('?report_id=ООО%20Вектор&inn=7700000000')).toBeNull()
  })

  it('makes a safe company backlink only from debtor INN', () => {
    expect(companyReportPath('2e7e9d9f-5f3a-4d43-a8e8-2bb3c2adf6b1', '7700000000')).toBe('/company/7700000000')
    expect(companyReportPath('2e7e9d9f-5f3a-4d43-a8e8-2bb3c2adf6b1', '770000000000000000')).toBeNull()
    expect(companyReportPath('2e7e9d9f-5f3a-4d43-a8e8-2bb3c2adf6b1', '7700000000-extra')).toBeNull()
    expect(companyReportPath('2e7e9d9f-5f3a-4d43-a8e8-2bb3c2adf6b1', 'extra-770000000000')).toBeNull()
    expect(companyReportPath(null, '7700000000')).toBeNull()
  })

  it('creates a fresh command key', () => {
    vi.spyOn(crypto, 'randomUUID').mockReturnValue('2e7e9d9f-5f3a-4d43-a8e8-2bb3c2adf6b1')
    expect(createHandoffCommandKey()).toBe('2e7e9d9f-5f3a-4d43-a8e8-2bb3c2adf6b1')
  })

  it('persists a command key before a retry or refresh', () => {
    vi.spyOn(crypto, 'randomUUID').mockReturnValue('2e7e9d9f-5f3a-4d43-a8e8-2bb3c2adf6b1')
    expect(readOrCreateHandoffCommandKey('report-1')).toBe('2e7e9d9f-5f3a-4d43-a8e8-2bb3c2adf6b1')
    expect(readOrCreateHandoffCommandKey('report-1')).toBe('2e7e9d9f-5f3a-4d43-a8e8-2bb3c2adf6b1')
  })

  it('rotates the command key only after the completed attempt is cleared', () => {
    vi.spyOn(crypto, 'randomUUID')
      .mockReturnValueOnce('2e7e9d9f-5f3a-4d43-a8e8-2bb3c2adf6b1')
      .mockReturnValueOnce('9f7e9d9f-5f3a-4d43-a8e8-2bb3c2adf6b2')
    expect(readOrCreateHandoffCommandKey('report-2')).toBe('2e7e9d9f-5f3a-4d43-a8e8-2bb3c2adf6b1')
    clearHandoffCommandKey('report-2')
    expect(readOrCreateHandoffCommandKey('report-2')).toBe('9f7e9d9f-5f3a-4d43-a8e8-2bb3c2adf6b2')
  })
})
