import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { useAuth } from '../auth/useAuth'
import { AppRouter } from './AppRouter'

vi.mock('../auth/useAuth', () => ({
  useAuth: vi.fn(),
}))

vi.mock('../claimsAdmin/ClaimsAdminAuthProvider', () => ({
  ClaimsAdminAuthProvider: ({ children }: { children: ReactNode }) => children,
}))

vi.mock('../claimsAdmin/RequireClaimsAdmin', async () => {
  const router = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    RequireClaimsAdmin: () => <router.Outlet />,
  }
})

vi.mock('../pages/AdminLoginPage', () => ({
  AdminLoginPage: () => <div>Admin login page</div>,
}))

vi.mock('../pages/AdminAuthConfirmPage', () => ({
  AdminAuthConfirmPage: () => <div>Admin confirm page</div>,
}))

vi.mock('../pages/AdminClaimsListPage', () => ({
  AdminClaimsListPage: () => <div>Admin claims list page</div>,
}))

vi.mock('../pages/AdminClaimDetailPage', () => ({
  AdminClaimDetailPage: () => <div>Admin claim detail page</div>,
}))

const mockedUseAuth = vi.mocked(useAuth)

function buildAnonymousAuthContext() {
  return {
    status: 'anonymous' as const,
    user: null,
    refreshWhoami: vi.fn(async () => null),
    requestLink: vi.fn(async () => undefined),
    confirmToken: vi.fn(async () => null),
    acceptInvite: vi.fn(async () => null),
    logout: vi.fn(async () => undefined),
  }
}

function renderRouter(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AppRouter />
    </MemoryRouter>,
  )
}

describe('AppRouter admin claims routes', () => {
  it('renders /admin/login route', () => {
    mockedUseAuth.mockReturnValue(buildAnonymousAuthContext())

    renderRouter('/admin/login')

    expect(screen.getByText('Admin login page')).toBeTruthy()
  })

  it('renders /admin/auth/confirm route', () => {
    mockedUseAuth.mockReturnValue(buildAnonymousAuthContext())

    renderRouter('/admin/auth/confirm?token=abc')

    expect(screen.getByText('Admin confirm page')).toBeTruthy()
  })

  it('renders /admin/claims route', () => {
    mockedUseAuth.mockReturnValue(buildAnonymousAuthContext())

    renderRouter('/admin/claims')

    expect(screen.getByText('Admin claims list page')).toBeTruthy()
  })

  it('renders /admin/claims/:id route', () => {
    mockedUseAuth.mockReturnValue(buildAnonymousAuthContext())

    renderRouter('/admin/claims/42')

    expect(screen.getByText('Admin claim detail page')).toBeTruthy()
  })
})
