import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { CompanyLandingPage } from './CompanyLandingPage'
import { navigateToCompany } from './companyLandingNavigation'

afterEach(cleanup)

describe('CompanyLandingPage', () => {
  it('shares one INN value and fences double submit before full-document navigation', () => {
    render(<MemoryRouter initialEntries={['/']}><CompanyLandingPage /></MemoryRouter>)
    const inputs = screen.getAllByLabelText('ИНН компании') as HTMLInputElement[]
    fireEvent.change(inputs[0], { target: { value: '7700 000 000' } })
    expect(inputs[1].value).toBe('7700000000')
    fireEvent.submit(inputs[1].closest('form')!)
    expect(inputs[0].disabled).toBe(true)
  })

  it('uses same-origin full-document navigation for the plain resolver', () => {
    const assign = vi.fn()
    navigateToCompany('7700000000', { assign })
    expect(assign).toHaveBeenCalledOnce()
    expect(assign).toHaveBeenCalledWith('/company/7700000000')
  })

  it('renders the approved landing copy with two accessible INN forms', () => {
    render(<MemoryRouter><CompanyLandingPage /></MemoryRouter>)

    expect(screen.getByRole('heading', { name: 'Вернем дебиторскую задолженность под ключ — с оплатой наших услуг по факту взыскания' })).toBeTruthy()
    expect(screen.getByText('ВЗЫСКАНИЕ ДЕБИТОРКИ')).toBeTruthy()
    expect(screen.getAllByLabelText('ИНН компании')).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'Проверить должника' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Запустить проверку' })).toBeTruthy()
    expect(screen.queryByText('CompanyReport')).toBeNull()
  })
})
