import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { useAuth } from '../auth/useAuth'
import { AppRouter } from './AppRouter'

vi.mock('../auth/useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('../pages/CompanyReportPage', () => ({ CompanyReportPage: () => <h1>Company report page</h1> }))
vi.mock('../pages/CompanyLandingPage', () => ({ CompanyLandingPage: () => <h1>Company landing</h1> }))
const mockedUseAuth = vi.mocked(useAuth)
const auth = (status: 'anonymous' | 'authenticated') => ({ status, user: null, refreshWhoami: vi.fn(), requestLink: vi.fn(), confirmToken: vi.fn(), acceptInvite: vi.fn(), logout: vi.fn() })

describe('company page route', () => {
  it('redirects anonymous users through RequireAuth and saves only a company return path', () => { mockedUseAuth.mockReturnValue(auth('anonymous')); render(<MemoryRouter initialEntries={['/company/1234567890-test']}><AppRouter /></MemoryRouter>); expect(screen.getByText('Sign in')).toBeTruthy(); expect(sessionStorage.getItem('auth.company-return-target.v1')).toBe('/company/1234567890-test') })
  it('renders the company page for an authenticated user', () => { mockedUseAuth.mockReturnValue(auth('authenticated')); render(<MemoryRouter initialEntries={['/company/1234567890-test']}><AppRouter /></MemoryRouter>); expect(screen.getByRole('heading', { name: 'Company report page' })).toBeTruthy() })
  it('renders the public landing route', () => { mockedUseAuth.mockReturnValue(auth('anonymous')); render(<MemoryRouter initialEntries={['/']}><AppRouter /></MemoryRouter>); expect(screen.getByRole('heading', { name: 'Company landing' })).toBeTruthy() })
})
