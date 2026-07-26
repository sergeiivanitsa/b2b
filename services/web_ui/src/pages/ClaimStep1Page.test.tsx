import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { writeClaimSession } from '../claims/claimSession'
import { ClaimStep1Page } from './ClaimStep1Page'

vi.mock('../claims/claimsApi', () => ({
  createClaim: vi.fn(),
  createClaimFromCompanyReport: vi.fn(),
  extractClaim: vi.fn(),
  getApiHttpErrorDetail: vi.fn(() => null),
  preflightCompanyReportHandoff: vi.fn(),
}))

import {
  createClaimFromCompanyReport,
  extractClaim,
  preflightCompanyReportHandoff,
} from '../claims/claimsApi'

const reportId = '2e7e9d9f-5f3a-4d43-a8e8-2bb3c2adf6b1'
const available = {
  report_id: reportId,
  availability: 'available' as const,
  reason: null,
  prefill: { debtor_name: 'ООО Вектор', debtor_inn: '7700000000' },
  prefilled_fields: ['debtor_name', 'debtor_inn'],
}

describe('ClaimStep1Page handoff', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.sessionStorage.clear()
  })

  afterEach(() => {
    cleanup()
    window.sessionStorage.clear()
  })

  it('shows trusted prefill availability without identity in the URL', async () => {
    vi.mocked(preflightCompanyReportHandoff).mockResolvedValue(available)
    render(<MemoryRouter initialEntries={[`/claims?report_id=${reportId}`]}><ClaimStep1Page /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText(/ООО Вектор/)).toBeTruthy())
  })

  it('keeps the manual form usable when prefill is unavailable', async () => {
    vi.mocked(preflightCompanyReportHandoff).mockResolvedValue({
      report_id: reportId,
      availability: 'manual_required',
      reason: 'report_pending',
      prefill: {},
      prefilled_fields: [],
    })
    render(<MemoryRouter initialEntries={[`/claims?report_id=${reportId}`]}><ClaimStep1Page /></MemoryRouter>)
    await waitFor(() => expect(screen.getAllByRole('textbox')).toHaveLength(1))
    expect(screen.getByText(/продолжить вручную/i)).toBeTruthy()
  })

  it('shows loading and safely falls back when authenticated preflight fails', async () => {
    let rejectPreflight!: (reason: Error) => void
    vi.mocked(preflightCompanyReportHandoff).mockReturnValue(
      new Promise((_resolve, reject) => { rejectPreflight = reject }),
    )
    render(<MemoryRouter initialEntries={[`/claims?report_id=${reportId}`]}><ClaimStep1Page /></MemoryRouter>)
    expect(screen.getByRole('status').textContent).toMatch(/Проверяем реквизиты/)
    rejectPreflight(new Error('unauthorized or unavailable'))
    await waitFor(() => expect(screen.getByText(/продолжить вручную/i)).toBeTruthy())
    expect(screen.getByRole('textbox')).toBeTruthy()
  })

  it('guards a linked create synchronously against double submit', async () => {
    vi.mocked(preflightCompanyReportHandoff).mockResolvedValue(available)
    let resolveCreate!: (value: Awaited<ReturnType<typeof createClaimFromCompanyReport>>) => void
    vi.mocked(createClaimFromCompanyReport).mockReturnValue(
      new Promise((resolve) => { resolveCreate = resolve }),
    )
    vi.mocked(extractClaim).mockResolvedValue({} as never)
    render(<MemoryRouter initialEntries={[`/claims?report_id=${reportId}`]}><ClaimStep1Page /></MemoryRouter>)
    await screen.findByText(/ООО Вектор/)
    const textbox = screen.getByRole('textbox')
    fireEvent.change(textbox, { target: { value: 'Долг по договору 17' } })
    const form = textbox.closest('form')
    expect(form).not.toBeNull()
    fireEvent.submit(form!)
    fireEvent.submit(form!)
    expect(createClaimFromCompanyReport).toHaveBeenCalledTimes(1)
    resolveCreate({
      claim_id: 17,
      edit_token: 'edit-token',
      reused: false,
      claim: {} as never,
    })
    await waitFor(() => expect(extractClaim).toHaveBeenCalledTimes(1))
  })

  it('offers direct recovery for the matching source draft after refresh', async () => {
    writeClaimSession({
      claimId: 19,
      editToken: 'edit-token',
      sourceCompanyReportId: reportId,
      handoffCommandKey: 'completed-attempt',
    })
    vi.mocked(preflightCompanyReportHandoff).mockResolvedValue(available)
    render(
      <MemoryRouter initialEntries={[`/claims?report_id=${reportId}`]}>
        <Routes>
          <Route path="/claims" element={<ClaimStep1Page />} />
          <Route path="/claims/step-2" element={<p>Recovered step 2</p>} />
        </Routes>
      </MemoryRouter>,
    )
    await screen.findByText(/черновик этой компании/i)
    fireEvent.click(screen.getByRole('button', { name: /Продолжить черновик/i }))
    expect(await screen.findByText('Recovered step 2')).toBeTruthy()
    expect(createClaimFromCompanyReport).not.toHaveBeenCalled()
  })
})
