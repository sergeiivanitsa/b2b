import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AuthContextValue, AuthUser } from '../auth/types'
import { useAuth } from '../auth/useAuth'
import { RequireOrgAdmin } from './RequireRole'

vi.mock('../auth/useAuth', () => ({
  useAuth: vi.fn(),
}))

const mockedUseAuth = vi.mocked(useAuth)

function buildUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 10,
    email: 'test@company.local',
    role: 'owner',
    org_id: 2,
    company_id: 2,
    is_superadmin: false,
    is_active: true,
    ...overrides,
  }
}

function buildAuthContext(
  status: AuthContextValue['status'],
  user: AuthUser | null,
): AuthContextValue {
  return {
    status,
    user,
    refreshWhoami: vi.fn(async () => user),
    requestLink: vi.fn(async () => undefined),
    confirmToken: vi.fn(async () => user),
    acceptInvite: vi.fn(async () => user),
    logout: vi.fn(async () => undefined),
  }
}

function renderRequireOrgAdmin(initialPath: string): void {
  render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route element={<RequireOrgAdmin />}>
          <Route path="/org/:id/admin" element={<div>ORG_ADMIN_ALLOWED</div>} />
        </Route>
        <Route path="/chat" element={<div>CHAT_REDIRECT</div>} />
        <Route path="/login" element={<div>LOGIN_REDIRECT</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('RequireOrgAdmin smoke', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    cleanup()
  })

  it('allows owner for matching org id', () => {
    mockedUseAuth.mockReturnValue(
      buildAuthContext(
        'authenticated',
        buildUser({ role: 'owner', org_id: 2, company_id: 2 }),
      ),
    )

    renderRequireOrgAdmin('/org/2/admin')

    expect(screen.getByText('ORG_ADMIN_ALLOWED')).toBeTruthy()
    expect(screen.queryByText('CHAT_REDIRECT')).toBeNull()
  })

  it('allows admin for matching org id', () => {
    mockedUseAuth.mockReturnValue(
      buildAuthContext(
        'authenticated',
        buildUser({ role: 'admin', org_id: 2, company_id: 2 }),
      ),
    )

    renderRequireOrgAdmin('/org/2/admin')

    expect(screen.getByText('ORG_ADMIN_ALLOWED')).toBeTruthy()
  })

  it('redirects member to /chat', () => {
    mockedUseAuth.mockReturnValue(
      buildAuthContext(
        'authenticated',
        buildUser({ role: 'member', org_id: 2, company_id: 2 }),
      ),
    )

    renderRequireOrgAdmin('/org/2/admin')

    expect(screen.getByText('CHAT_REDIRECT')).toBeTruthy()
    expect(screen.queryByText('ORG_ADMIN_ALLOWED')).toBeNull()
  })

  it('redirects when route org id does not match user org id', () => {
    mockedUseAuth.mockReturnValue(
      buildAuthContext(
        'authenticated',
        buildUser({ role: 'owner', org_id: 2, company_id: 2 }),
      ),
    )

    renderRequireOrgAdmin('/org/3/admin')

    expect(screen.getByText('CHAT_REDIRECT')).toBeTruthy()
    expect(screen.queryByText('ORG_ADMIN_ALLOWED')).toBeNull()
  })

  it('redirects anonymous user to /login', () => {
    mockedUseAuth.mockReturnValue(buildAuthContext('anonymous', null))

    renderRequireOrgAdmin('/org/2/admin')

    expect(screen.getByText('LOGIN_REDIRECT')).toBeTruthy()
    expect(screen.queryByText('ORG_ADMIN_ALLOWED')).toBeNull()
  })
})
