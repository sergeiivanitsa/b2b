import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useAuth } from '../auth/useAuth'
import { ConfirmPage } from './ConfirmPage'

vi.mock('../auth/useAuth', () => ({ useAuth: vi.fn() }))
const mockedUseAuth = vi.mocked(useAuth)

function LocationProbe() { return <p data-testid="location">{useLocation().pathname}</p> }

function renderConfirm() {
  return render(<MemoryRouter initialEntries={['/auth/confirm']}><LocationProbe /><Routes><Route path="/auth/confirm" element={<ConfirmPage />} /><Route path="/company/:companyKey" element={<p>Company route</p>} /><Route path="/chat" element={<p>Chat route</p>} /></Routes></MemoryRouter>)
}

describe('ConfirmPage company return target', () => {
  afterEach(() => { cleanup(); sessionStorage.clear(); vi.clearAllMocks() })

  it('consumes a strict return target once after confirmation', async () => {
    sessionStorage.setItem('auth.company-return-target.v1', '/company/7700000000-ooo-vektor')
    mockedUseAuth.mockReturnValue({ confirmToken: vi.fn().mockResolvedValue({ role: 'member', company_id: 1 }) } as never)
    renderConfirm()
    fireEvent.change(screen.getByLabelText('Token'), { target: { value: 'token' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirm token' }))
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/company/7700000000-ooo-vektor'))
    expect(sessionStorage.getItem('auth.company-return-target.v1')).toBeNull()
  })

  it('discards an injected invalid return target and falls back to the normal route', async () => {
    sessionStorage.setItem('auth.company-return-target.v1', 'https://example.test')
    mockedUseAuth.mockReturnValue({ confirmToken: vi.fn().mockResolvedValue({ role: 'member', company_id: 1 }) } as never)
    renderConfirm()
    fireEvent.change(screen.getByLabelText('Token'), { target: { value: 'token' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirm token' }))
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/chat'))
    expect(sessionStorage.getItem('auth.company-return-target.v1')).toBeNull()
  })
})
