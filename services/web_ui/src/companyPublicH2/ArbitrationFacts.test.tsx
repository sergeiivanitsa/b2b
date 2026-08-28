import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { ArbitrationFacts } from './ArbitrationFacts'
import { CompanyPublicH2Page } from './CompanyPublicH2Page'
import { parseCompanyPublicH2 } from './contract'
import { arbitrationPolicyV3Raw, arbitrationSourceLessRaw } from './arbitrationTestFixture'
import legacyRaw from '../../../../shared/fixtures/company_public_h2_contract_v1.json?raw'
import maskedV3Raw from '../../../../shared/fixtures/company_public_h2_contract_v1_arbitration_masked_v3.json?raw'

afterEach(cleanup)

describe('policy-v3 arbitration factual DOM', () => {
  it('renders five ordered table-first articles with masked public identities', async () => {
    const dto = (await parseCompanyPublicH2(maskedV3Raw)).dto
    const { container } = render(<ArbitrationFacts dto={dto} />)
    const articles = [...container.querySelectorAll('[data-h2-arbitration-article]')]
    expect(articles.map(item => item.getAttribute('id'))).toEqual(['arbitration-a1', 'arbitration-a2', 'arbitration-a3', 'arbitration-a4', 'arbitration-a5'])
    expect(container.querySelectorAll('table')).toHaveLength(5)
    expect(container.querySelector('[data-h2-case-public-id="case_000001"]')).toBeTruthy()
    expect(container.querySelector('[data-h2-opponent-public-id="opponent_000001"]')?.textContent).toContain('Сторона скрыта 1')
    expect(container.textContent).toContain('−12,34 ₽')
    expect(container.textContent).not.toContain('ООО Контрагент')
    for (const blockId of ['arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4', 'arbitration_a5']) {
      expect(screen.getByRole('region', { name: `Ограничения арбитражного представления ${blockId}` })).toBeTruthy()
    }
    for (const host of container.querySelectorAll('[data-h2-arbitration-enhancement]')) {
      expect(host.getAttribute('aria-hidden')).toBe('true')
      expect(host.childElementCount).toBe(0)
    }
  })

  it('renders a known-empty collection without a synthetic year or chart', async () => {
    const dto = (await parseCompanyPublicH2(await arbitrationPolicyV3Raw(false))).dto
    const { container } = render(<ArbitrationFacts dto={dto} />)
    expect(container.querySelectorAll('[data-h2-arbitration-article]')).toHaveLength(5)
    expect(screen.getByText('Подтверждённая коллекция не содержит дел.')).toBeTruthy()
    expect(container.textContent).not.toContain(String(new Date().getUTCFullYear()))
    expect(container.querySelector('[data-h2-arbitration-chart-mark]')).toBeNull()
  })

  it('renders five honest unavailable articles for the exact source-less branch', async () => {
    const dto = (await parseCompanyPublicH2(await arbitrationSourceLessRaw('provider_error'))).dto
    const { container } = render(<ArbitrationFacts dto={dto} />)
    expect(container.querySelectorAll('[data-h2-arbitration-article]')).toHaveLength(5)
    for (const article of container.querySelectorAll('[data-h2-arbitration-article]')) {
      expect(within(article as HTMLElement).getByText(/не опубликованы/u)).toBeTruthy()
      expect(article.querySelector('[data-h2-arbitration-limitation="provider_error"]')).toBeTruthy()
    }
  })

  it('keeps the generic dense legacy corpus readable but outside policy-v3 articles', async () => {
    const dto = (await parseCompanyPublicH2(legacyRaw)).dto
    const { container } = render(<CompanyPublicH2Page dto={dto} />)
    expect(container.querySelectorAll('[data-h2-arbitration-article]')).toHaveLength(0)
    expect(container.querySelectorAll('#arbitration [data-h2-block]')).toHaveLength(5)
    expect(container.textContent).toContain('ARBITRATION A1')
  })
})
