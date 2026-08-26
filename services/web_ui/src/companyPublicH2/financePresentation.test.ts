import { describe, expect, it } from 'vitest'
import { moneyCompact, moneyExact, multiple, percent, per100 } from './financePresentation'

describe('finance presentation', () => {
  it('uses server owned money strings and canonical decimal suffixes', () => {
    const value = { source_thousand_decimal: '273325', rub_decimal: '273325000', million_decimal: '273.325', display_exact: '273,325 млн ₽', display_compact: '273,3 млн ₽', unit_id: 'RUB', unit_policy_version: 'datanewton_finance_thousand_rub_v2' } as const
    expect(moneyExact(value)).toBe('273,325 млн ₽')
    expect(moneyCompact(value)).toBe('273,3 млн ₽')
    expect(percent('-12.5')).toBe('-12.5 %')
    expect(multiple('1.25')).toBe('1.25 ×')
    expect(per100('-3.2')).toBe('-3.2 ₽ из 100 ₽')
  })
})
