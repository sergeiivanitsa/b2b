import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'

import { YANDEX_LAB_COMPANY_KEY, companyReportLabPath } from '../companyReport/companyReportLabData'
import { CompanyReportLabPage } from './CompanyReportLabPage'

function renderLab(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/company-lab/:variant/:companyKey" element={<CompanyReportLabPage />} />
        <Route path="/company-lab/:variant/:companyKey/:section" element={<CompanyReportLabPage />} />
        <Route path="/claims" element={<p>Claims destination</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  document.head.querySelectorAll('meta[name="robots"]').forEach((node) => node.remove())
})

describe('CompanyReportLabPage', () => {
  it.each([
    ['h1', 'ООО «ЯНДЕКС»: реквизиты, финансы и арбитраж'],
    ['h2', 'ООО «ЯНДЕКС»: досье компании'],
    ['h3', 'Проверка ООО «ЯНДЕКС»: что подтверждают данные'],
  ] as const)('renders one factual H1 and common identity for %s', (variant, heading) => {
    const { container } = renderLab(companyReportLabPath(variant))

    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(screen.getByRole('heading', { level: 1, name: heading })).toBeTruthy()
    expect(screen.getAllByText(YANDEX_LAB_COMPANY_KEY.slice(0, 10)).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/10 августа 2026, 08:02/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/DataNewton через CompanyReport/).length).toBeGreaterThan(0)
    expect(container.textContent).not.toMatch(/рейтинг|вердикт|\bAI\b/i)
    expect(document.head.querySelector('meta[name="robots"]')?.getAttribute('content')).toBe('noindex,nofollow')
  })

  it('maps every H1 contents anchor to an existing block', () => {
    const { container } = renderLab(companyReportLabPath('h1'))
    const anchors = Array.from(container.querySelectorAll<HTMLAnchorElement>('.cr-lab-h1__contents a[href^="#"]'))

    expect(anchors.length).toBeGreaterThan(3)
    for (const anchor of anchors) {
      expect(container.querySelector(anchor.getAttribute('href')!)).toBeTruthy()
    }
  })

  it('keeps the H2 hub compact and exposes no finance or management document', () => {
    const { container } = renderLab(companyReportLabPath('h2'))
    const hrefs = Array.from(container.querySelectorAll<HTMLAnchorElement>('a[href]')).map((link) => link.getAttribute('href'))

    expect(screen.queryByText('1 448')).toBeNull()
    expect(hrefs.some((href) => href?.includes('/finance'))).toBe(false)
    expect(screen.queryByRole('link', { name: /руковод/i })).toBeNull()
    expect(screen.getByRole('link', { name: /Открыть судебную выборку/ }).getAttribute('href')).toBe(companyReportLabPath('h2', 'legal'))
  })

  it('renders H2 legal as a standalone detail document with an explicit sample boundary', () => {
    const { container } = renderLab(companyReportLabPath('h2', 'legal'))

    expect(screen.getByRole('heading', { level: 1, name: 'Арбитражные дела ООО «ЯНДЕКС»' })).toBeTruthy()
    expect(screen.getAllByText(/ООО «ЯНДЕКС», ИНН 7736207543/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/10 августа 2026, 08:02/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/DataNewton через CompanyReport/).length).toBeGreaterThan(0)
    expect(screen.getAllByText('1 448').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/100 запис/).length).toBeGreaterThan(0)
    expect(Array.from(container.querySelectorAll<HTMLAnchorElement>('a[href]')).some((link) => link.getAttribute('href')?.includes('/finance'))).toBe(false)
    expect(screen.queryByRole('link', { name: /руковод/i })).toBeNull()
  })

  it('shows H3 evidence states and gates the debt action behind an explicit scenario', () => {
    renderLab(companyReportLabPath('h3'))

    expect(screen.getByRole('heading', { name: 'Что действительно есть в снимке' })).toBeTruthy()
    expect(screen.getAllByText('Получено').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Частичная выборка').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Не запрашивалось').length).toBeGreaterThan(0)
    expect(screen.getByText('Исполнительные производства')).toBeTruthy()
    expect(screen.getByText('Банкротные сообщения')).toBeTruthy()
    expect(screen.getAllByText(/Состояние контракта на 10 августа 2026/).length).toBeGreaterThan(0)
    expect(screen.getByRole('region', { name: 'Матрица доказательств по направлениям' }).getAttribute('tabindex')).toBe('0')
    expect(screen.queryByRole('link', { name: 'Проверить должника и подготовить претензию' })).toBeNull()

    fireEvent.change(screen.getByLabelText('Зачем вы открыли страницу?'), { target: { value: 'debt' } })
    expect(screen.getByRole('link', { name: 'Проверить должника и подготовить претензию' })).toBeTruthy()
  })

  it('keeps the H3 reference profile free from check-owned tax content', () => {
    renderLab(companyReportLabPath('h3', 'profile'))

    expect(screen.getByRole('heading', { level: 1, name: 'ООО «ЯНДЕКС»: профиль юридического лица' })).toBeTruthy()
    expect(screen.queryByRole('heading', { name: 'Налоговый режим' })).toBeNull()
    expect(screen.getByRole('link', { name: 'Открыть проверку' }).getAttribute('href')).toBe(companyReportLabPath('h3'))
  })

  it.each([
    `/company-lab/h4/${YANDEX_LAB_COMPANY_KEY}`,
    '/company-lab/h1/7736207543',
    `/company-lab/h1/${YANDEX_LAB_COMPANY_KEY}/legal`,
    `/company-lab/h2/${YANDEX_LAB_COMPANY_KEY}/profile`,
    `/company-lab/h3/${YANDEX_LAB_COMPANY_KEY}/legal`,
  ])('renders a safe state for invalid lab path %s', (path) => {
    renderLab(path)
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(screen.getByRole('heading', { level: 1, name: 'Этот вариант страницы недоступен' })).toBeTruthy()
    expect(document.head.querySelector('meta[name="robots"]')?.getAttribute('content')).toBe('noindex,nofollow')
  })

  it('sets and restores title and an existing robots directive', () => {
    document.title = 'Previous title'
    document.documentElement.lang = 'en'
    const robots = document.createElement('meta')
    robots.name = 'robots'
    robots.content = 'index,follow'
    document.head.append(robots)

    const { unmount } = renderLab(companyReportLabPath('h2', 'legal'))
    expect(document.title).toBe('Арбитражные дела ООО «ЯНДЕКС» | CompanyReport')
    expect(document.documentElement.lang).toBe('ru')
    expect(robots.content).toBe('noindex,nofollow')

    unmount()
    expect(document.title).toBe('Previous title')
    expect(document.documentElement.lang).toBe('en')
    expect(robots.content).toBe('index,follow')
  })
})
