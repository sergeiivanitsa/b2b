import { describe, expect, it } from 'vitest'
import { formatCompactCompanyBreadcrumbLabel } from './breadcrumbPresentation'

const FORMS = [
  ['Общество с ограниченной ответственностью', 'ООО'],
  ['Акционерное общество', 'АО'],
  ['Открытое акционерное общество', 'ОАО'],
  ['Закрытое акционерное общество', 'ЗАО'],
  ['Публичное акционерное общество', 'ПАО'],
  ['Индивидуальный предприниматель', 'ИП'],
] as const

function format(
  signedLabel: string,
  shortName: string | null = null,
  legalFullName = signedLabel,
): string {
  return formatCompactCompanyBreadcrumbLabel({ signedLabel, shortName, legalFullName })
}

describe('compact Company Public H2 breadcrumb presentation', () => {
  it.each(FORMS)('compacts %s in lowercase and uppercase', (full, short) => {
    expect(format(`${full.toLocaleLowerCase('ru-RU')} «Ромашка»`)).toBe(`${short} «Ромашка»`)
    expect(format(`${full.toLocaleUpperCase('ru-RU')} «Ромашка»`)).toBe(`${short} «Ромашка»`)
  })

  it('supports the grammatical provider alias and canonicalizes an already-short alias', () => {
    expect(format('Общества с ограниченной ответственностью «Север»')).toBe('ООО «Север»')
    expect(format('пао «Маяк»')).toBe('ПАО «Маяк»')
    expect(format('ооо«Без пробела»')).toBe('ООО «Без пробела»')
  })

  it('prefers the provider short name and infers its known form from signed data first', () => {
    expect(format(
      'Общество с ограниченной ответственностью «Длинное»',
      '  «Краткое»  ',
      'Публичное акционерное общество «Длинное»',
    )).toBe('ООО «Краткое»')
  })

  it('compacts a known form already present in the provider short name', () => {
    expect(format(
      'Подписанное наименование',
      'открытое акционерное общество «Восток»',
    )).toBe('ОАО «Восток»')
  })

  it('keeps an unknown provider-authored form without guessing', () => {
    expect(format(
      'Автономная некоммерческая организация «Вектор»',
      'АНО «Вектор»',
      'Автономная некоммерческая организация «Вектор»',
    )).toBe('АНО «Вектор»')
  })

  it('falls back from an unsigned form in the label to the legal full name', () => {
    expect(format(
      '«Северный ветер»',
      null,
      'Закрытое акционерное общество «Северный ветер»',
    )).toBe('ЗАО «Северный ветер»')
  })

  it('normalizes NFC and whitespace while preserving company-name casing and quotes', () => {
    expect(format('  ООО\t«МайТех»\n')).toBe('ООО «МайТех»')
  })

  it('uses the exact Python whitespace table for SSR parity', () => {
    expect(format('Общество\u001cс\u0085ограниченной ответственностью «Вектор»'))
      .toBe('ООО «Вектор»')
    expect(format('\uFEFFООО «Вектор»')).toBe('\uFEFFООО «Вектор»')
    expect(format('ООО\uFEFF«Вектор»')).toBe('ООО\uFEFF«Вектор»')
    expect(format('ООО\u1C89Компания')).toBe('ООО\u1C89Компания')
  })

  it('does not apply Python-only Unicode case folding', () => {
    const source = 'ᲂбщество с ограниченной ответственностью «Вектор»'
    expect(format(source)).toBe(source)
  })

  it('requires an approved separator boundary after a form alias', () => {
    expect(format('ООО2 «Не форма»')).toBe('ООО2 «Не форма»')
  })
})
