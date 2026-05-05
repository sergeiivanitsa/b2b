import { describe, expect, it } from 'vitest'

import { getClaimDocumentDemoText } from './claimDocumentDemoText'

const FORBIDDEN_FRAGMENTS = [
  'ИНН',
  'Подпись',
  'Приложения',
  'Арбитражный суд',
  'требуем оплатить',
]

function expectSafeDemoText(text: string) {
  expect(text.trim()).toBeTruthy()
  expect(text.length).toBeGreaterThan(450)
  expect(text.length).toBeLessThan(900)
  expect(text).not.toContain('\n\n')
  expect(text.split(/\n+/)).toHaveLength(1)

  for (const fragment of FORBIDDEN_FRAGMENTS) {
    expect(text.toLowerCase()).not.toContain(fragment.toLowerCase())
  }
}

function expectArticle(text: string, articleNumber: string) {
  expect(text).toMatch(new RegExp(`(?:ст\\.|Статья) ${articleNumber} ГК РФ`))
}

describe('claim document demo text', () => {
  it('returns supply text with supply-specific legal basis', () => {
    const text = getClaimDocumentDemoText('supply', 101)

    expect(text).toContain('ст. 486 ГК РФ')
    expectArticle(text, '309')
    expectArticle(text, '310')
    expectSafeDemoText(text)
  })

  it('returns contract work text with contract-work-specific legal basis', () => {
    const text = getClaimDocumentDemoText('contract_work', 102)

    expect(text).toContain('ст. 702 ГК РФ')
    expectArticle(text, '309')
    expectArticle(text, '310')
    expectSafeDemoText(text)
  })

  it('returns services text with services-specific legal basis', () => {
    const text = getClaimDocumentDemoText('services', 103)

    expect(text).toContain('ст. 779 ГК РФ')
    expect(text).toContain('ст. 781 ГК РФ')
    expectArticle(text, '309')
    expectArticle(text, '310')
    expectSafeDemoText(text)
  })

  it('uses default text for unknown case type', () => {
    const text = getClaimDocumentDemoText('other', 104)

    expectArticle(text, '309')
    expectArticle(text, '310')
    expect(text).not.toContain('ст. 486 ГК РФ')
    expect(text).not.toContain('ст. 702 ГК РФ')
    expect(text).not.toContain('ст. 779 ГК РФ')
    expect(text).not.toContain('ст. 781 ГК РФ')
    expectSafeDemoText(text)
  })

  it('uses default text for null case type', () => {
    const text = getClaimDocumentDemoText(null, 105)

    expectArticle(text, '309')
    expectArticle(text, '310')
    expect(text).not.toContain('ст. 486 ГК РФ')
    expect(text).not.toContain('ст. 702 ГК РФ')
    expect(text).not.toContain('ст. 779 ГК РФ')
    expect(text).not.toContain('ст. 781 ГК РФ')
    expectSafeDemoText(text)
  })

  it('returns the same text for the same case type and claim id', () => {
    const first = getClaimDocumentDemoText(' supply ', 'claim-200')
    const second = getClaimDocumentDemoText('supply', 'claim-200')

    expect(first).toBe(second)
    expectSafeDemoText(first)
  })

  it('returns valid text for different claim ids without requiring different variants', () => {
    const first = getClaimDocumentDemoText('contract_work', 301)
    const second = getClaimDocumentDemoText('contract_work', 302)

    expect(first).toContain('ст. 702 ГК РФ')
    expect(second).toContain('ст. 702 ГК РФ')
    expectSafeDemoText(first)
    expectSafeDemoText(second)
  })

  it('returns the first variant when claim id is missing', () => {
    const text = getClaimDocumentDemoText('supply', undefined)

    expect(text).toContain('Правовое обоснование заявленных требований строится')
    expect(text).toContain('ст. 486 ГК РФ')
    expectSafeDemoText(text)
  })

  it('returns the first variant when claim id is blank', () => {
    const text = getClaimDocumentDemoText('services', '   ')

    expect(text).toContain('Правовое обоснование требований подготавливается')
    expect(text).toContain('ст. 779 ГК РФ')
    expect(text).toContain('ст. 781 ГК РФ')
    expectSafeDemoText(text)
  })

  it('keeps sampled texts as single safe paragraphs', () => {
    const sampledTexts = [
      getClaimDocumentDemoText('supply', 1),
      getClaimDocumentDemoText('supply', 2),
      getClaimDocumentDemoText('contract_work', 1),
      getClaimDocumentDemoText('contract_work', 2),
      getClaimDocumentDemoText('services', 1),
      getClaimDocumentDemoText('services', 2),
      getClaimDocumentDemoText('unknown', 1),
      getClaimDocumentDemoText(undefined, 2),
    ]

    for (const text of sampledTexts) {
      expectSafeDemoText(text)
    }
  })
})
