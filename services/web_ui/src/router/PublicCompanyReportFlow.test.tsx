import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuth } from '../auth/useAuth'
import { getCompanyReport } from '../companyReport/companyReportApi'
import type { CompanyReportResponse } from '../companyReport/companyReportTypes'
import { AppRouter } from './AppRouter'

vi.mock('../auth/useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('../companyReport/companyReportApi', () => ({
  createCompanyReport: vi.fn(),
  getCompanyReport: vi.fn(),
  getCompanyReportStatus: vi.fn(),
}))

const mockedUseAuth = vi.mocked(useAuth)
const mockedGetCompanyReport = vi.mocked(getCompanyReport)
const completed: CompanyReportResponse = {
  report_id: 'report-1',
  status: 'complete',
  started_at: '2026-01-01T00:00:00Z',
  canonical_path: '/company/7700000000-test-company',
  report: {
    status: 'complete',
    datasets: {},
    completeness: {
      available_count: 1,
      required_count: 1,
      percent: 100,
      missing_datasets: [],
      unavailable_datasets: [],
    },
    freshness: { generated_at: '2026-01-01T00:00:00Z' },
    warnings: [],
    usable_for_public_page: true,
    usable_for_future_scoring: true,
    counterparty: { short_name: 'Тестовая компания' },
  },
}

function LocationProbe() {
  return <p data-testid="location">{useLocation().pathname}</p>
}

describe('public CompanyReport flow', () => {
  beforeEach(() => {
    mockedUseAuth.mockReturnValue({
      status: 'anonymous',
      user: null,
      refreshWhoami: vi.fn(),
      requestLink: vi.fn(),
      confirmToken: vi.fn(),
      acceptInvite: vi.fn(),
      logout: vi.fn(),
    })
    mockedGetCompanyReport.mockResolvedValue(completed)
  })
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('opens and loads a company report from the landing without login', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <LocationProbe />
        <AppRouter />
      </MemoryRouter>,
    )

    fireEvent.change(screen.getAllByLabelText('ИНН компании')[0], {
      target: { value: '7700000000' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Проверить должника' }))

    await waitFor(() => {
      expect(mockedGetCompanyReport).toHaveBeenCalledWith(
        '7700000000',
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      )
      expect(screen.getByTestId('location').textContent).toBe(
        '/company/7700000000-test-company',
      )
    })
    expect(
      await screen.findByRole('heading', { name: 'Тестовая компания' }),
    ).toBeTruthy()
    expect(screen.queryByText('Sign in')).toBeNull()
  })
})
