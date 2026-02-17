import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import {
  createCompanyInvite,
  detachCompanyUser,
  getCompanySummary,
  getCompanyUsersStats,
  listCompanyInvites,
  updateCompanyUserLimit,
  type CompanyInvite,
  type CompanySummary,
  type CompanyUserStatsRow,
  type CreateCompanyInviteInput,
} from '../companyAdmin/companyAdminApi'
import {
  formatCompanyAdminError,
  formatDetachSuccess,
  formatLimitUpdateSuccess,
} from '../companyAdmin/companyAdminUx'
import { useAuth } from '../auth/useAuth'
import { CompanySummarySection } from '../components/company-admin/CompanySummarySection'
import { EmployeesSection } from '../components/company-admin/EmployeesSection'
import { InvitesSection } from '../components/company-admin/InvitesSection'
import { StatsSection } from '../components/company-admin/StatsSection'

type Banner =
  | {
      kind: 'success' | 'error'
      text: string
    }
  | null

export function OrgAdminPage() {
  const { user } = useAuth()
  const params = useParams()

  const routeOrgId = useMemo(() => {
    if (!params.id) {
      return null
    }
    const parsed = Number(params.id)
    return Number.isFinite(parsed) ? parsed : null
  }, [params.id])
  const userOrgId = user ? user.org_id ?? user.company_id : null

  const [summary, setSummary] = useState<CompanySummary | null>(null)
  const [users, setUsers] = useState<CompanyUserStatsRow[]>([])
  const [invites, setInvites] = useState<CompanyInvite[]>([])

  const [isSummaryLoading, setIsSummaryLoading] = useState(false)
  const [isUsersLoading, setIsUsersLoading] = useState(false)
  const [isInvitesLoading, setIsInvitesLoading] = useState(false)

  const [summaryError, setSummaryError] = useState<string | null>(null)
  const [usersError, setUsersError] = useState<string | null>(null)
  const [invitesError, setInvitesError] = useState<string | null>(null)

  const [isCreatingInvite, setIsCreatingInvite] = useState(false)
  const [isUpdatingLimitByUserId, setIsUpdatingLimitByUserId] = useState<
    Record<number, boolean>
  >({})
  const [isDetachingByUserId, setIsDetachingByUserId] = useState<Record<number, boolean>>({})
  const [banner, setBanner] = useState<Banner>(null)

  const loadSummary = useCallback(async (): Promise<void> => {
    setIsSummaryLoading(true)
    setSummaryError(null)
    try {
      const response = await getCompanySummary()
      setSummary(response)
    } catch (error) {
      setSummaryError(formatCompanyAdminError(error, { operation: 'summary' }))
    } finally {
      setIsSummaryLoading(false)
    }
  }, [])

  const loadUsers = useCallback(async (): Promise<void> => {
    setIsUsersLoading(true)
    setUsersError(null)
    try {
      const response = await getCompanyUsersStats()
      setUsers(response.users)
    } catch (error) {
      setUsersError(formatCompanyAdminError(error, { operation: 'usersStats' }))
    } finally {
      setIsUsersLoading(false)
    }
  }, [])

  const loadInvites = useCallback(async (): Promise<void> => {
    setIsInvitesLoading(true)
    setInvitesError(null)
    try {
      const response = await listCompanyInvites()
      setInvites(response.invites)
    } catch (error) {
      setInvitesError(formatCompanyAdminError(error, { operation: 'invitesList' }))
    } finally {
      setIsInvitesLoading(false)
    }
  }, [])

  const loadAll = useCallback(async (): Promise<void> => {
    await Promise.all([loadSummary(), loadUsers(), loadInvites()])
  }, [loadSummary, loadUsers, loadInvites])

  useEffect(() => {
    void loadAll()
  }, [loadAll])

  const handleCreateInvite = useCallback(
    async (payload: CreateCompanyInviteInput): Promise<boolean> => {
      setIsCreatingInvite(true)
      try {
        await createCompanyInvite(payload)
        setBanner({
          kind: 'success',
          text: 'Приглашение отправлено.',
        })
        await loadInvites()
        return true
      } catch (error) {
        setBanner({
          kind: 'error',
          text: formatCompanyAdminError(error, { operation: 'inviteCreate' }),
        })
        return false
      } finally {
        setIsCreatingInvite(false)
      }
    },
    [loadInvites],
  )

  const handleUpdateLimit = useCallback(
    async (payload: { userId: number; delta: number; reason: string }): Promise<boolean> => {
      const userId = payload.userId
      setIsUpdatingLimitByUserId((prev) => ({ ...prev, [userId]: true }))
      try {
        const response = await updateCompanyUserLimit(userId, {
          delta: payload.delta,
          reason: payload.reason,
        })
        setBanner({
          kind: 'success',
          text: formatLimitUpdateSuccess(response.user.remaining_credits),
        })
        await Promise.all([loadSummary(), loadUsers()])
        return true
      } catch (error) {
        setBanner({
          kind: 'error',
          text: formatCompanyAdminError(error, { operation: 'limitUpdate' }),
        })
        return false
      } finally {
        setIsUpdatingLimitByUserId((prev) => ({ ...prev, [userId]: false }))
      }
    },
    [loadSummary, loadUsers],
  )

  const handleDetach = useCallback(
    async (userId: number): Promise<boolean> => {
      setIsDetachingByUserId((prev) => ({ ...prev, [userId]: true }))
      try {
        const response = await detachCompanyUser(userId)
        setBanner({
          kind: 'success',
          text: formatDetachSuccess(response.user.email, response.released_limit),
        })
        await Promise.all([loadSummary(), loadUsers()])
        return true
      } catch (error) {
        setBanner({
          kind: 'error',
          text: formatCompanyAdminError(error, { operation: 'detach' }),
        })
        return false
      } finally {
        setIsDetachingByUserId((prev) => ({ ...prev, [userId]: false }))
      }
    },
    [loadSummary, loadUsers],
  )

  if (!user) {
    return (
      <main className="screen">
        <section className="card">
          <h1 className="card__title">Админка компании</h1>
          <p className="card__subtitle">Проверяем текущую сессию...</p>
        </section>
      </main>
    )
  }

  return (
    <main className="company-admin-page">
      <section className="company-admin-shell">
        <header className="company-admin-header">
          <div className="company-admin-header__main">
            <h1 className="company-admin-header__title">Админка компании</h1>
            <p className="company-admin-header__meta">
              Организация: {routeOrgId ?? userOrgId ?? '-'} | Пользователь: {user.email} |
              Роль: {user.role}
            </p>
          </div>
          <div className="company-admin-header__actions">
            <button
              type="button"
              className="button button--secondary"
              onClick={() => {
                void loadAll()
              }}
              disabled={isSummaryLoading || isUsersLoading || isInvitesLoading}
            >
              {isSummaryLoading || isUsersLoading || isInvitesLoading
                ? 'Обновляем...'
                : 'Обновить всё'}
            </button>
            <Link to="/chat" className="button button--secondary">
              Назад в чат
            </Link>
          </div>
        </header>

        {routeOrgId && userOrgId && routeOrgId !== userOrgId ? (
          <p className="message message--error">
            В URL указан org_id, который не совпадает с вашей компанией.
          </p>
        ) : null}

        {banner ? (
          <p
            className={
              banner.kind === 'success'
                ? 'message message--success'
                : 'message message--error'
            }
          >
            {banner.text}
          </p>
        ) : null}

        <CompanySummarySection
          summary={summary}
          isLoading={isSummaryLoading}
          errorMessage={summaryError}
          onRetry={() => {
            void loadSummary()
          }}
        />

        <EmployeesSection
          users={users}
          isLoading={isUsersLoading}
          errorMessage={usersError}
          onRetry={() => {
            void loadUsers()
          }}
          onUpdateLimit={handleUpdateLimit}
          onDetach={handleDetach}
          isUpdatingLimitByUserId={isUpdatingLimitByUserId}
          isDetachingByUserId={isDetachingByUserId}
          currentUserId={user.id}
          currentUserRole={user.role}
        />

        <InvitesSection
          invites={invites}
          isLoading={isInvitesLoading}
          errorMessage={invitesError}
          isCreating={isCreatingInvite}
          onRetry={() => {
            void loadInvites()
          }}
          onCreateInvite={handleCreateInvite}
        />

        <StatsSection
          users={users}
          summary={summary}
          isLoading={isUsersLoading || isSummaryLoading}
        />
      </section>
    </main>
  )
}
