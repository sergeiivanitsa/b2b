import { describe, expect, it } from 'vitest'

import {
  NO_DATA,
  financeUnit,
  isCanonicalCompanyPath,
  parseCompanyKey,
  signalLabel,
  signalPeriodText,
} from './companyReportPresentation'

describe('company report presentation helpers', () => {
  it('distinguishes supported plain and canonical company keys', () => {
    expect(parseCompanyKey('1234567890')).toEqual({ kind: 'plain', inn: '1234567890' })
    expect(parseCompanyKey('1234567890-company-name')).toEqual({ kind: 'canonical', inn: '1234567890' })
    expect(parseCompanyKey('123456789012-company')).toEqual({ kind: 'canonical', inn: '123456789012' })
    for (const value of ['123-company', '1234567890-Company', '1234567890-', '1234567890-company--name', '1234567890-company_name']) expect(parseCompanyKey(value)).toEqual({ error: 'invalid_company_key' })
  })
  it('accepts only a canonical path for the same INN', () => {
    expect(isCanonicalCompanyPath('/company/1234567890-company-name', '1234567890')).toBe(true)
    expect(isCanonicalCompanyPath('/company/123456789012-company-name', '1234567890')).toBe(false)
    expect(isCanonicalCompanyPath('/company/1234567890', '1234567890')).toBe(false)
    expect(isCanonicalCompanyPath('https://example.test/company/1234567890-company', '1234567890')).toBe(false)
  })
  it('preserves unavailable data and unknown finance units', () => {
    expect(financeUnit('provider_units_unknown')).toBe('Единица измерения неизвестна')
    expect(financeUnit(null)).toBe('Единица измерения неизвестна')
    expect(NO_DATA).toBe('Нет данных')
  })
  it('uses the fixed label registry and a neutral unknown fallback', () => {
    expect(signalLabel('counterparty.active')).toBe('Компания отмечена действующей')
    expect(signalLabel('counterparty.dissolved')).toBe('Компания отмечена прекратившей деятельность')
    expect(signalLabel('counterparty.long_operating_history')).toBe('Длительный срок деятельности')
    expect(signalLabel('counterparty.status_conflict')).toBe('Противоречивые сведения о статусе')
    expect(signalLabel('finance.negative_equity')).toBe('Отрицательный капитал')
    expect(signalLabel('finance.revenue_decline')).toBe('Снижение выручки')
    expect(signalLabel('finance.net_loss')).toBe('Чистый убыток')
    expect(signalLabel('finance.cash_shortfall')).toBe('Недостаток денежных средств')
    expect(signalLabel('finance.high_accounts_payable')).toBe('Высокая кредиторская задолженность')
    expect(signalLabel('arbitration.high_respondent_case_count')).toBe('Много дел в роли ответчика')
    expect(signalLabel('arbitration.respondent_case_growth')).toBe('Рост дел в роли ответчика')
    expect(signalLabel('arbitration.open_cases')).toBe('Открытые арбитражные дела')
    expect(signalLabel('arbitration.frequent_plaintiff')).toBe('Частые обращения в суд как истец')
    expect(signalLabel('unknown.signal')).toBe('Сигнал требует проверки')
  })

  it('uses the exact public signal period field names', () => {
    expect(
      signalPeriodText({
        kind: 'no_period',
        as_of: '2026-07-24T00:00:00Z',
      }),
    ).toBe('На 2026-07-24T00:00:00Z')
    expect(signalPeriodText({ kind: 'date', value: '2026-07-24' })).toBe(
      '2026-07-24',
    )
    expect(
      signalPeriodText({
        kind: 'date_range',
        start: '2020-01-01',
        end: '2026-07-24',
      }),
    ).toBe('2020-01-01 — 2026-07-24')
    expect(signalPeriodText({ kind: 'year', year: 2025 })).toBe('2025')
    expect(
      signalPeriodText({
        kind: 'year_range',
        start_year: 2024,
        end_year: 2025,
      }),
    ).toBe('2024 — 2025')
  })
})
