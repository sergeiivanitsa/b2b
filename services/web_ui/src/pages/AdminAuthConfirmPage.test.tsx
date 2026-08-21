import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import type { ClaimsAdminAuthContextValue } from '../claimsAdmin/ClaimsAdminAuthContext'
import { useClaimsAdminAuth } from '../claimsAdmin/useClaimsAdminAuth'
import { AdminAuthConfirmPage } from './AdminAuthConfirmPage'

vi.mock('../claimsAdmin/useClaimsAdminAuth', () => ({
  useClaimsAdminAuth: vi.fn(),
}))

const mockedUseClaimsAdminAuth = vi.mocked(useClaimsAdminAuth)

function authContext(
  confirmToken: ClaimsAdminAuthContextValue['confirmToken'],
): ClaimsAdminAuthContextValue {
  return {
    status: 'anonymous',
    refreshSession: vi.fn(
      async (): Promise<ClaimsAdminAuthContextValue['status']> => 'anonymous',
    ),
    requestLink: vi.fn(async () => undefined),
    confirmToken,
    logout: vi.fn(async () => undefined),
  }
}

describe('AdminAuthConfirmPage', () => {
  it('renders the missing-token state without calling confirmation', () => {
    const confirmToken = vi.fn(async () => 'authenticated' as const)
    mockedUseClaimsAdminAuth.mockReturnValue(authContext(confirmToken))

    render(
      <MemoryRouter initialEntries={['/admin/confirm']}>
        <AdminAuthConfirmPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('Подтверждение недоступно')).toBeTruthy()
    expect(screen.getByText('Токен не найден в ссылке подтверждения.')).toBeTruthy()
    expect(confirmToken).not.toHaveBeenCalled()
  })
})
