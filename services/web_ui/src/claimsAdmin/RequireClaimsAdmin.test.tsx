import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import type { ClaimsAdminAuthContextValue } from './ClaimsAdminAuthProvider'
import { RequireClaimsAdmin } from './RequireClaimsAdmin'
import { useClaimsAdminAuth } from './useClaimsAdminAuth'

vi.mock('./useClaimsAdminAuth', () => ({
  useClaimsAdminAuth: vi.fn(),
}))

const mockedUseClaimsAdminAuth = vi.mocked(useClaimsAdminAuth)

function renderGuard(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/admin/login" element={<div>Admin login route</div>} />
        <Route element={<RequireClaimsAdmin />}>
          <Route path="/admin/claims" element={<div>Admin claims route</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

function buildAuthContext(
  status: ClaimsAdminAuthContextValue['status'],
): ClaimsAdminAuthContextValue {
  return {
    status,
    refreshSession: vi.fn(async () => status),
    requestLink: vi.fn(async () => undefined),
    confirmToken: vi.fn(async () => status),
    logout: vi.fn(async () => undefined),
  }
}

describe('RequireClaimsAdmin', () => {
  it('renders loading state', () => {
    mockedUseClaimsAdminAuth.mockReturnValue(buildAuthContext('loading'))

    renderGuard('/admin/claims')
    expect(screen.getByText('Checking claims admin access')).toBeTruthy()
  })

  it('redirects anonymous users to /admin/login', () => {
    mockedUseClaimsAdminAuth.mockReturnValue(buildAuthContext('anonymous'))

    renderGuard('/admin/claims')
    expect(screen.getByText('Admin login route')).toBeTruthy()
  })

  it('renders forbidden state', () => {
    mockedUseClaimsAdminAuth.mockReturnValue(buildAuthContext('forbidden'))

    renderGuard('/admin/claims')
    expect(screen.getByText('Access denied')).toBeTruthy()
  })

  it('renders outlet for authenticated users', () => {
    mockedUseClaimsAdminAuth.mockReturnValue(buildAuthContext('authenticated'))

    renderGuard('/admin/claims')
    expect(screen.getByText('Admin claims route')).toBeTruthy()
  })
})
