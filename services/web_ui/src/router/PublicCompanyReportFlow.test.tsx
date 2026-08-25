import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuth } from '../auth/useAuth'
import {
  createCompanyReport,
  getCompanyPublicH1,
  getCompanyReportStatus,
} from '../companyReport/companyReportApi'
import publishedFixture from '../companyReport/fixtures/company-public-h1-published.json?raw'
import { parseCompanyPublicH1 } from '../companyReport/companyReportH1Contract'
import {
  cleanupCompanyHead,
  HEAD_OWNER_ATTRIBUTE,
  HEAD_OWNER_VALUE,
} from '../companyReport/companyReportPresentation'
import { AppRouter } from './AppRouter'
import { navigateToCompany } from '../pages/companyLandingNavigation'

vi.mock('../auth/useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('../companyReport/companyReportApi', () => ({
  createCompanyReport: vi.fn(),
  getCompanyPublicH1: vi.fn(),
  getCompanyReportStatus: vi.fn(),
}))
vi.mock('../pages/companyLandingNavigation', () => ({ navigateToCompany: vi.fn() }))

const mockedUseAuth = vi.mocked(useAuth)
const mockedGet = vi.mocked(getCompanyPublicH1)
const mockedCreate = vi.mocked(createCompanyReport)
const mockedStatus = vi.mocked(getCompanyReportStatus)
const mockedNavigate = vi.mocked(navigateToCompany)
const dto = parseCompanyPublicH1(JSON.parse(publishedFixture))

function LocationProbe() {
  const location = useLocation()
  return <p data-testid="location">{`${location.pathname}${location.search}`}</p>
}

describe('public CompanyReport flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedUseAuth.mockReturnValue({
      status: 'anonymous',
      user: null,
      refreshWhoami: vi.fn(),
      requestLink: vi.fn(),
      confirmToken: vi.fn(),
      acceptInvite: vi.fn(),
      logout: vi.fn(),
    })
    mockedGet.mockResolvedValue(dto)
    document.title = 'Публичная главная'
    document.documentElement.lang = 'en'
  })

  afterEach(() => {
    cleanup()
    cleanupCompanyHead()
  })

  it('hands off from landing with one document navigation and no factual SPA read', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <LocationProbe />
        <AppRouter />
      </MemoryRouter>,
    )

    fireEvent.change(screen.getAllByLabelText('ИНН компании')[0], {
      target: { value: dto.identity.inn },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Проверить должника' }))
    expect(mockedNavigate).toHaveBeenCalledOnce()
    expect(mockedNavigate).toHaveBeenCalledWith(dto.identity.inn)
    expect(screen.getByTestId('location').textContent).toBe('/')
    expect(mockedGet).not.toHaveBeenCalled()
    expect(mockedCreate).not.toHaveBeenCalled()
    expect(mockedStatus).not.toHaveBeenCalled()
    expect(screen.queryByText('Sign in')).toBeNull()
  })

  it('cleans only owned company metadata when returning to the landing', async () => {
    const foreign = document.createElement('meta')
    foreign.name = 'description'
    foreign.content = 'foreign metadata'
    document.head.append(foreign)
    render(
      <MemoryRouter initialEntries={[dto.canonical_path]}>
        <LocationProbe />
        <AppRouter />
      </MemoryRouter>,
    )
    await screen.findByRole('heading', {
      name: `${dto.identity.legal_full_name} — ИНН ${dto.identity.inn}`,
    })
    expect(
      document.head.querySelectorAll(
        `[${HEAD_OWNER_ATTRIBUTE}="${HEAD_OWNER_VALUE}"]`,
      ),
    ).toHaveLength(2)

    fireEvent.click(
      screen.getByRole('link', { name: 'Проверить другую компанию' }),
    )
    await waitFor(() => {
      expect(screen.getByTestId('location').textContent).toBe('/')
    })
    expect(
      document.head.querySelectorAll(
        `[${HEAD_OWNER_ATTRIBUTE}="${HEAD_OWNER_VALUE}"]`,
      ),
    ).toHaveLength(0)
    expect(document.title).toBe('Публичная главная')
    expect(document.documentElement.lang).toBe('en')
    expect(foreign.isConnected).toBe(true)
  })
})
