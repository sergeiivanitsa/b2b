import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import publishedFixture from '../../companyReport/fixtures/company-public-h1-published.json?raw'
import { parseCompanyPublicH1 } from '../../companyReport/companyReportH1Contract'
import { CompanyReportContent } from './CompanyReportContent'

const dto = parseCompanyPublicH1(JSON.parse(publishedFixture))

function renderContent(
  props: ComponentProps<typeof CompanyReportContent>,
) {
  return render(
    <MemoryRouter>
      <CompanyReportContent {...props} />
    </MemoryRouter>,
  )
}

describe('CompanyReportContent', () => {
  afterEach(cleanup)

  it('renders an aria-busy loading shell without moving focus prematurely', () => {
    const { container } = renderContent({ view: { kind: 'loading_h1' } })
    const main = container.querySelector('main')
    expect(main?.getAttribute('aria-busy')).toBe('true')
    expect(
      screen.getByRole('heading', {
        name: 'Загружаем сведения о компании',
      }),
    ).toBeTruthy()
    expect(document.activeElement).toBe(document.body)
  })

  it('keeps one stable live region and does not announce visual poll stages', () => {
    const result = renderContent({
      view: { kind: 'pending', title: 'Проверяем компанию', cycle: 1 },
    })
    const live = result.container.querySelector('[aria-live="polite"]')
    const pendingHeading = screen.getByRole('heading', {
      name: 'Проверяем компанию',
    })
    expect(live?.textContent).toBe('Отчёт формируется.')
    expect(document.activeElement).toBe(pendingHeading)

    result.rerender(
      <MemoryRouter>
        <CompanyReportContent
          view={{
            kind: 'pending',
            title: 'Собираем сведения о должнике',
            cycle: 2,
          }}
        />
      </MemoryRouter>,
    )
    expect(result.container.querySelector('[aria-live="polite"]')).toBe(live)
    expect(live?.textContent).toBe('Отчёт формируется.')
    expect(document.activeElement).toBe(pendingHeading)
    expect(pendingHeading.textContent).toBe('Собираем сведения о должнике')
  })

  it('renders a paused delayed state with an explicit one-shot status action', () => {
    const onRetry = vi.fn()
    const result = renderContent({
      view: { kind: 'delayed', checking: false },
      onRetry,
    })
    const heading = screen.getByRole('heading', {
      name: 'Отчёт ещё формируется',
    })
    expect(document.activeElement).toBe(heading)
    expect(result.container.querySelector('main')?.hasAttribute('aria-busy')).toBe(
      false,
    )
    expect(result.container.querySelector('[aria-live="polite"]')?.textContent).toBe(
      'Отчёт ещё формируется.',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Проверить статус' }))
    expect(onRetry).toHaveBeenCalledTimes(1)

    result.rerender(
      <MemoryRouter>
        <CompanyReportContent
          view={{ kind: 'delayed', checking: true }}
          onRetry={onRetry}
        />
      </MemoryRouter>,
    )
    expect(result.container.querySelector('main')?.getAttribute('aria-busy')).toBe(
      'true',
    )
    expect(
      screen
        .getByRole('button', { name: 'Проверяем…' })
        .hasAttribute('disabled'),
    ).toBe(true)
    expect(result.container.querySelector('[aria-live="polite"]')?.textContent).toBe(
      'Проверяем статус отчёта.',
    )
  })

  it('moves focus to the sole H1 after content becomes available', () => {
    const result = renderContent({ view: { kind: 'loading_h1' } })
    result.rerender(
      <MemoryRouter>
        <CompanyReportContent view={{ kind: 'content', dto }} />
      </MemoryRouter>,
    )
    const headings = screen.getAllByRole('heading', { level: 1 })
    expect(headings).toHaveLength(1)
    expect(headings[0].textContent).toContain(dto.identity.legal_full_name)
    expect(document.activeElement).toBe(headings[0])
    const main = result.container.querySelector('main')
    expect(main?.getAttribute('data-company-contract')).toBe(
      dto.contract_version,
    )
    expect(main?.getAttribute('data-company-report-id')).toBe(dto.report_id)
    expect(main?.getAttribute('data-company-block-order')).toBe(
      dto.block_order.join(','),
    )
    expect(main?.hasAttribute('aria-busy')).toBe(false)
  })

  it('focuses safe error headings and offers retry only for retryable errors', () => {
    const onRetry = vi.fn()
    const result = renderContent({
      view: {
        kind: 'retryable_error',
        message: 'Сервис временно недоступен. Повторите позже.',
      },
      onRetry,
    })
    const heading = screen.getByRole('heading', {
      name: 'Сервис временно недоступен. Повторите позже.',
    })
    expect(document.activeElement).toBe(heading)
    fireEvent.click(screen.getByRole('button', { name: 'Повторить' }))
    expect(onRetry).toHaveBeenCalledTimes(1)

    result.rerender(
      <MemoryRouter>
        <CompanyReportContent
          view={{ kind: 'terminal_error', message: 'Публичный отчёт не найден' }}
          onRetry={onRetry}
        />
      </MemoryRouter>,
    )
    expect(screen.queryByRole('button', { name: 'Повторить' })).toBeNull()
    expect(document.activeElement).toBe(
      screen.getByRole('heading', { name: 'Публичный отчёт не найден' }),
    )
  })

  it('renders contract and invalid-route states without response details', () => {
    const result = renderContent({ view: { kind: 'contract_error' } })
    expect(
      screen.getByRole('heading', { name: 'Неподдерживаемый формат отчёта' }),
    ).toBeTruthy()
    expect(result.container.textContent).not.toContain('raw_payload')

    result.rerender(
      <MemoryRouter>
        <CompanyReportContent view={{ kind: 'invalid_route' }} />
      </MemoryRouter>,
    )
    expect(
      screen.getByRole('heading', {
        name: 'Некорректный адрес страницы компании.',
      }),
    ).toBeTruthy()
  })
})
