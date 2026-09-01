import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { CompanyPublicH2Page } from './CompanyPublicH2Page'
import { collectCompanyPublicH2ParityVector } from './parityVector'
import { parseCompanyPublicH2 } from './contract'
import sharedDto from '../../../../shared/fixtures/company_public_h2_contract_v1.json?raw'

afterEach(cleanup)

describe('CompanyPublicH2Page', () => {
  it('presents compact breadcrumbs without changing signed navigation or the hero title', async () => {
    const parsed = await parseCompanyPublicH2(sharedDto)
    const signedLabel = 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ «1С-Рарус Длинный»'
    const dto = {
      ...parsed.dto,
      identity: {
        ...parsed.dto.identity,
        display_name: signedLabel,
        legal_full_name: signedLabel,
        short_name: '«1С-Рарус»',
      },
      breadcrumbs: [
        parsed.dto.breadcrumbs[0],
        { ...parsed.dto.breadcrumbs[1], label: signedLabel },
      ] as const,
    }

    const { container } = render(<main id="company-public-h2-root" className="company-public-h2"><CompanyPublicH2Page dto={dto} /></main>)
    const breadcrumbs = screen.getByRole('navigation', { name: 'Хлебные крошки' })
    const home = screen.getByRole('link', { name: 'Главная' })
    const current = breadcrumbs.querySelector('[aria-current="page"]')

    expect(breadcrumbs.classList.contains('company-public-h2__breadcrumbs')).toBe(true)
    expect(breadcrumbs.querySelectorAll(':scope > ol > li')).toHaveLength(2)
    expect(home.getAttribute('href')).toBe('/')
    expect(current?.tagName).toBe('SPAN')
    expect(current?.textContent).toBe('ООО «1С-Рарус»')
    expect(container.querySelector('h1')?.textContent).toBe(signedLabel)
    expect(dto.breadcrumbs[1].label).toBe(signedLabel)
    expect(dto.breadcrumbs[1].path).toBe(parsed.dto.breadcrumbs[1].path)
  })

  it('keeps both neutral actions in approved accent treatment and CTA accessible', async () => {
    const parsed = await parseCompanyPublicH2(sharedDto)
    render(<main id="company-public-h2-root" className="company-public-h2"><CompanyPublicH2Page dto={parsed.dto} /></main>)
    expect(screen.getByRole('link', { name: 'Проверить другую компанию' }).className).toContain('accent')
    expect(screen.getByRole('link', { name: 'Подготовить претензию' }).className).toContain('accent')
    expect(screen.getByRole('link', { name: 'Создать претензию' })).toBeTruthy()
  })

  it('renders direct SSR-equivalent children, coverage links and all fixed sections', async () => {
    const parsed = await parseCompanyPublicH2(sharedDto)
    const { container } = render(<main id="company-public-h2-root" className="company-public-h2" data-contract="company_public_h2_v1" data-report-id="00000000-0000-4000-8000-000000000001"><CompanyPublicH2Page dto={parsed.dto} /></main>)
    const ids = [...container.querySelectorAll('[id]')].map(element => element.id)
    expect(ids).toEqual(expect.arrayContaining(['hero-status', 'narrative', 'narrative-title', 'in-page-navigation', 'requisites', 'finance', 'arbitration', 'sources-limitations', 'neutral-actions']))
    expect([...container.querySelectorAll('#in-page-navigation a')].map(link => [link.getAttribute('href'), link.textContent])).toEqual([
      ['#requisites', 'Реквизиты'], ['#finance', 'Финансы'], ['#arbitration', 'Арбитраж'],
    ])
    expect(container.querySelectorAll('[data-h2-coverage]').length).toBe(
      parsed.dto.coverage.reduce((count, item) => count + 1 + ['total', 'returned', 'eligible'].filter(name => item[name] !== null).length, 0),
    )
    expect([...container.querySelectorAll('[data-h2-finance-article]')].map(element => element.getAttribute('data-h2-finance-article'))).toEqual([
      'finance-f1', 'finance-f2', 'finance-f3', 'finance-f4', 'finance-f5',
    ])
    expect([...container.querySelectorAll('[data-h2-block]')].map(element => element.getAttribute('data-h2-block'))).toEqual([
      'arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4', 'arbitration_a5',
    ])
    for (const item of parsed.dto.coverage) {
      for (const code of item.limitation_codes) expect(container.querySelector(`a[href="#limitation-${code}"]`)).toBeTruthy()
    }
    expect(container.querySelector('.company-public-h2__enhancement')).toBeNull()
  })

  it('collects an ordered head, text, link, coverage and limitation vector', async () => {
    const parsed = await parseCompanyPublicH2(sharedDto)
    document.head.innerHTML = '<title>Тест</title><meta name="description" content="Описание"><meta name="robots" content="noindex,follow"><link rel="canonical" href="/company/7701234567-company">'
    const { container } = render(<main id="company-public-h2-root" className="company-public-h2" data-contract="company_public_h2_v1" data-report-id="00000000-0000-4000-8000-000000000001"><CompanyPublicH2Page dto={parsed.dto} /></main>)
    const vector = JSON.parse(collectCompanyPublicH2ParityVector(container.ownerDocument)) as { head: string[]; coverage: string[][]; limitations: string[][] }
    expect(vector.head).toEqual(['Тест', 'Описание', 'noindex,follow', '/company/7701234567-company'])
    expect(vector.coverage.map(item => item[0])).toEqual(expect.arrayContaining(['finance_f1', 'arbitration_a1']))
    expect(vector.limitations).toHaveLength(parsed.dto.limitations.length)
  })

  it('focuses and announces an enhanced in-page destination', async () => {
    const parsed = await parseCompanyPublicH2(sharedDto)
    const { container } = render(<main id="company-public-h2-root" className="company-public-h2"><CompanyPublicH2Page dto={parsed.dto} /></main>)
    fireEvent.click(screen.getByRole('link', { name: 'Реквизиты' }))
    const target = container.querySelector<HTMLElement>('#requisites')
    expect(document.activeElement).toBe(target)
    expect(target?.getAttribute('tabindex')).toBe('-1')
    expect(container.querySelector('.company-public-h2__live')?.textContent).toContain('Реквизиты')
    expect(window.location.hash).toBe('#requisites')
  })

  it('uses the fixed missing-status text instead of the internal projection scope', async () => {
    const parsed = await parseCompanyPublicH2(sharedDto)
    const dto = { ...parsed.dto, identity: { ...parsed.dto.identity, status: null } }
    render(<main id="company-public-h2-root" className="company-public-h2"><CompanyPublicH2Page dto={dto} /></main>)
    expect(screen.getByText('Статус отчёта: Статус не указан в отчёте')).toBeTruthy()
    expect(screen.queryByText(/active_publication/)).toBeNull()
  })
})
