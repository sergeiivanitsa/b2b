import { describe, expect, it } from 'vitest'
import { arbitrationPolicyV3Dto } from './arbitrationTestFixture'
import { arbitrationCaseLabel, arbitrationCollectionLabel, arbitrationCount, arbitrationOutcomeLabel, arbitrationPercent, arbitrationRoleLabel, arbitrationYear } from './arbitrationPresentation'

describe('arbitration literal presentation', () => {
  it('uses only contract values and fixed Russian labels', async () => {
    const dto = await arbitrationPolicyV3Dto()
    const item = dto.blocks.arbitration_a4!.currency_groups[0].cases[0]
    expect(arbitrationRoleLabel('respondent')).toBe('Ответчик')
    expect(arbitrationOutcomeLabel('returned')).toBe('Возвращено')
    expect(arbitrationCount(dto.blocks.arbitration_a2!.denominator)).toBe('1')
    expect(arbitrationPercent('12.500001')).toBe('12.500001 %')
    expect(arbitrationYear(item.year)).toBe('2025')
    expect(arbitrationCaseLabel(item)).toBe('А40-1/2025')
    expect(arbitrationCollectionLabel('returned_slice')).toBe('Полученная часть коллекции')
  })

  it('does not invent values for contract nulls', () => {
    expect(arbitrationCount(null)).toBe('—')
    expect(arbitrationPercent(null)).toBe('—')
    expect(arbitrationYear(null)).toBe('Год не указан')
  })
})
