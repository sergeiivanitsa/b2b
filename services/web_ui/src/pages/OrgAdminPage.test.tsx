import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AuthContextValue, AuthUser } from '../auth/types'
import { useAuth } from '../auth/useAuth'
import {
  createCompanyInvite,
  detachCompanyUser,
  getCompanySummary,
  getCompanyUsersStats,
  listCompanyInvites,
  updateCompanyUserLimit,
} from '../companyAdmin/companyAdminApi'
import { OrgAdminPage } from './OrgAdminPage'

vi.mock('../auth/useAuth', () => ({
  useAuth: vi.fn(),
}))

vi.mock('../companyAdmin/companyAdminApi', () => ({
  getCompanySummary: vi.fn(),
  getCompanyUsersStats: vi.fn(),
  listCompanyInvites: vi.fn(),
  createCompanyInvite: vi.fn(),
  updateCompanyUserLimit: vi.fn(),
  detachCompanyUser: vi.fn(),
}))

const mockedUseAuth = vi.mocked(useAuth)
const mockedGetCompanySummary = vi.mocked(getCompanySummary)
const mockedGetCompanyUsersStats = vi.mocked(getCompanyUsersStats)
const mockedListCompanyInvites = vi.mocked(listCompanyInvites)
const mockedCreateCompanyInvite = vi.mocked(createCompanyInvite)
const mockedUpdateCompanyUserLimit = vi.mocked(updateCompanyUserLimit)
const mockedDetachCompanyUser = vi.mocked(detachCompanyUser)

function buildUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 1,
    email: 'owner@org.test',
    role: 'owner',
    org_id: 2,
    company_id: 2,
    is_superadmin: false,
    is_active: true,
    ...overrides,
  }
}

function buildAuthContext(user: AuthUser): AuthContextValue {
  return {
    status: 'authenticated',
    user,
    refreshWhoami: vi.fn(async () => user),
    requestLink: vi.fn(async () => undefined),
    confirmToken: vi.fn(async () => user),
    acceptInvite: vi.fn(async () => user),
    logout: vi.fn(async () => undefined),
  }
}

function renderOrgAdminPage(initialPath = '/org/2/admin'): void {
  render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/org/:id/admin" element={<OrgAdminPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('OrgAdminPage smoke', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedUseAuth.mockReturnValue(buildAuthContext(buildUser()))
    mockedGetCompanySummary.mockResolvedValue({
      company: {
        id: 2,
        name: 'Test Org',
        inn: '1234567890',
        phone: '+79990000000',
        status: 'active',
      },
      credits: {
        pool_balance: 100,
        allocated_total: 60,
        unallocated_balance: 40,
      },
      users: {
        total: 3,
        active: 3,
      },
    })
    mockedGetCompanyUsersStats.mockResolvedValue({
      users: [
        {
          id: 1,
          first_name: 'Иван',
          last_name: 'Иванов',
          email: 'owner@org.test',
          role: 'owner',
          is_active: true,
          joined_company_at: '2026-02-01T10:00:00+00:00',
          remaining_credits: 50,
          spent_all_time: 10,
        },
        {
          id: 2,
          first_name: 'Петр',
          last_name: 'Петров',
          email: 'member@org.test',
          role: 'member',
          is_active: true,
          joined_company_at: '2026-02-02T10:00:00+00:00',
          remaining_credits: 10,
          spent_all_time: 15,
        },
      ],
    })
    mockedListCompanyInvites.mockResolvedValue({
      invites: [
        {
          id: 10,
          email: 'pending@org.test',
          first_name: 'Анна',
          last_name: 'Сидорова',
          role: 'member',
          expires_at: '2026-02-20T10:00:00+00:00',
          created_at: '2026-02-19T10:00:00+00:00',
        },
      ],
    })
    mockedCreateCompanyInvite.mockResolvedValue({ status: 'ok' })
    mockedUpdateCompanyUserLimit.mockResolvedValue({
      status: 'ok',
      user: {
        id: 2,
        email: 'member@org.test',
        role: 'member',
        is_active: true,
        remaining_credits: 20,
      },
      credits: {
        pool_balance: 100,
        allocated_total: 70,
        unallocated_balance: 30,
      },
    })
    mockedDetachCompanyUser.mockResolvedValue({
      status: 'ok',
      user: {
        id: 2,
        email: 'member@org.test',
        company_id: null,
        role: 'member',
        is_active: false,
        joined_company_at: null,
      },
      released_limit: 10,
    })
  })

  afterEach(() => {
    cleanup()
  })

  it('loads /company data and renders 4 single-page sections', async () => {
    renderOrgAdminPage()

    await waitFor(() => {
      expect(mockedGetCompanySummary).toHaveBeenCalledTimes(1)
      expect(mockedGetCompanyUsersStats).toHaveBeenCalledTimes(1)
      expect(mockedListCompanyInvites).toHaveBeenCalledTimes(1)
    })

    expect(screen.getByText('1. Обзор компании и баланс')).toBeTruthy()
    expect(screen.getByText('2. Сотрудники')).toBeTruthy()
    expect(screen.getByText('3. Инвайты')).toBeTruthy()
    expect(screen.getByText('4. Статистика')).toBeTruthy()
    expect(screen.getByText('Добавить сотрудника')).toBeTruthy()
    expect(screen.getByText('Назад в чат')).toBeTruthy()
  })

  it('submits invite form and calls invite endpoint', async () => {
    renderOrgAdminPage()

    await waitFor(() => {
      expect(mockedListCompanyInvites).toHaveBeenCalledTimes(1)
    })

    fireEvent.change(screen.getByLabelText('Фамилия'), {
      target: { value: 'Смирнов' },
    })
    fireEvent.change(screen.getByLabelText('Имя'), {
      target: { value: 'Сергей' },
    })
    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'new.employee@org.test' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Добавить сотрудника' }))

    await waitFor(() => {
      expect(mockedCreateCompanyInvite).toHaveBeenCalledWith({
        email: 'new.employee@org.test',
        first_name: 'Сергей',
        last_name: 'Смирнов',
      })
    })
    await waitFor(() => {
      expect(mockedListCompanyInvites).toHaveBeenCalledTimes(2)
    })
  })
})
