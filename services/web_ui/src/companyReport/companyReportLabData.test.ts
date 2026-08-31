import { describe, expect, it } from 'vitest'

import {
  YANDEX_LAB_COMPANY_KEY,
  YANDEX_LAB_SNAPSHOT,
  companyReportLabPath,
  isYandexLabCompanyKey,
  parseCompanyReportLabVariant,
  resolveCompanyReportLabView,
  scenarioAction,
} from './companyReportLabData'

describe('companyReportLabData', () => {
  it('keeps the sanitized snapshot immutable at runtime', () => {
    expect(Object.isFrozen(YANDEX_LAB_SNAPSHOT)).toBe(true)
    expect(Object.isFrozen(YANDEX_LAB_SNAPSHOT.identity)).toBe(true)
    expect(Object.isFrozen(YANDEX_LAB_SNAPSHOT.finance.changes)).toBe(true)
    expect(Object.isFrozen(YANDEX_LAB_SNAPSHOT.arbitration.roles[0])).toBe(true)
  })

  it('contains only safe scale-independent finance presentation values', () => {
    expect(YANDEX_LAB_SNAPSHOT.finance.unit).toBe('provider_units_unknown')
    expect(YANDEX_LAB_SNAPSHOT.finance.changes.map((item) => item.value)).toEqual(['+29,1%', '+26,2%', '+25,3%', '−80,0%'])
    expect(YANDEX_LAB_SNAPSHOT.arbitration.totalCases).toBe(1448)
    expect(YANDEX_LAB_SNAPSHOT.arbitration.returnedCases).toBe(100)
  })

  it('parses only the three fixed variants and the canonical Yandex key', () => {
    expect(parseCompanyReportLabVariant('h1')).toBe('h1')
    expect(parseCompanyReportLabVariant('h2')).toBe('h2')
    expect(parseCompanyReportLabVariant('h3')).toBe('h3')
    expect(parseCompanyReportLabVariant('H1')).toBeNull()
    expect(parseCompanyReportLabVariant('h4')).toBeNull()
    expect(isYandexLabCompanyKey(YANDEX_LAB_COMPANY_KEY)).toBe(true)
    expect(isYandexLabCompanyKey('7736207543')).toBe(false)
  })

  it('allows only the approved detail route in its own hypothesis arm', () => {
    expect(resolveCompanyReportLabView('h1', YANDEX_LAB_COMPANY_KEY, companyReportLabPath('h1'))).toBe('main')
    expect(resolveCompanyReportLabView('h2', YANDEX_LAB_COMPANY_KEY, companyReportLabPath('h2', 'legal'))).toBe('legal')
    expect(resolveCompanyReportLabView('h3', YANDEX_LAB_COMPANY_KEY, companyReportLabPath('h3', 'profile'))).toBe('profile')
    expect(resolveCompanyReportLabView('h1', YANDEX_LAB_COMPANY_KEY, `${companyReportLabPath('h1')}/legal`)).toBeNull()
    expect(resolveCompanyReportLabView('h2', YANDEX_LAB_COMPANY_KEY, `${companyReportLabPath('h2')}/profile`)).toBeNull()
    expect(resolveCompanyReportLabView('h3', YANDEX_LAB_COMPANY_KEY, `${companyReportLabPath('h3')}/legal`)).toBeNull()
  })

  it('keeps non-debt actions inside the selected architecture', () => {
    expect(scenarioAction('h1', 'deal').href).toBe('#arbitration')
    expect(scenarioAction('h2', 'deal').href).toBe(companyReportLabPath('h2', 'legal'))
    expect(scenarioAction('h3', 'deal').href).toBe('#evidence-matrix')
    expect(scenarioAction('h1', 'prepayment').href).toBe('#finance')
    expect(scenarioAction('h2', 'prepayment').href).toBe('#h2-finance')
    expect(scenarioAction('h3', 'prepayment').href).toBe('#evidence-findings')
    expect(scenarioAction('h3', 'debt').href).toContain(`/claims?report_id=${YANDEX_LAB_SNAPSHOT.reportId}`)
  })
})
