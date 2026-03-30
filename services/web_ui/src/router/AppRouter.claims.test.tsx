import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuth } from '../auth/useAuth'
import type { AuthContextValue } from '../auth/types'
import { AppRouter } from './AppRouter'

vi.mock('../auth/useAuth', () => ({
  useAuth: vi.fn(),
}))

const mockedUseAuth = vi.mocked(useAuth)

function buildAuthContext(status: AuthContextValue['status']): AuthContextValue {
  return {
    status,
    user: null,
    refreshWhoami: vi.fn(async () => null),
    requestLink: vi.fn(async () => undefined),
    confirmToken: vi.fn(async () => null),
    acceptInvite: vi.fn(async () => null),
    logout: vi.fn(async () => undefined),
  }
}

function renderRouter(path: string): void {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AppRouter />
    </MemoryRouter>,
  )
}

describe('AppRouter claims shell', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
  })

  afterEach(() => {
    cleanup()
    sessionStorage.clear()
  })

  it('renders claims shell at /claims', () => {
    mockedUseAuth.mockReturnValue(buildAuthContext('anonymous'))

    renderRouter('/claims')

    expect(screen.getByText('Public Claims Flow')).toBeTruthy()
    expect(screen.getByText(/No active claim session/i)).toBeTruthy()
  })

  it('redirects /claims/* to /claims shell', () => {
    mockedUseAuth.mockReturnValue(buildAuthContext('anonymous'))

    renderRouter('/claims/step-unknown')

    expect(screen.getByText('Public Claims Flow')).toBeTruthy()
  })

  it('keeps root redirect behavior unchanged', () => {
    mockedUseAuth.mockReturnValue(buildAuthContext('anonymous'))

    renderRouter('/')

    expect(screen.getByText('Sign in')).toBeTruthy()
  })
})
