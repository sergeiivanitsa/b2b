import { useMemo, useState } from 'react'

import type { CompanyUserStatsRow } from '../../companyAdmin/companyAdminApi'

type EmployeesSectionProps = {
  users: CompanyUserStatsRow[]
  isLoading: boolean
  errorMessage: string | null
  onRetry: () => void
  onUpdateLimit: (payload: {
    userId: number
    delta: number
    reason: string
  }) => Promise<boolean>
  onDetach: (userId: number) => Promise<boolean>
  isUpdatingLimitByUserId: Record<number, boolean>
  isDetachingByUserId: Record<number, boolean>
  currentUserId: number | null
  currentUserRole: string | null
}

function formatDate(value: string | null): string {
  if (!value) {
    return '-'
  }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString('ru-RU')
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat('ru-RU').format(value)
}

export function EmployeesSection({
  users,
  isLoading,
  errorMessage,
  onRetry,
  onUpdateLimit,
  onDetach,
  isUpdatingLimitByUserId,
  isDetachingByUserId,
  currentUserId,
  currentUserRole,
}: EmployeesSectionProps) {
  const [deltaByUserId, setDeltaByUserId] = useState<Record<number, string>>({})
  const [reasonByUserId, setReasonByUserId] = useState<Record<number, string>>({})
  const [validationErrorByUserId, setValidationErrorByUserId] = useState<
    Record<number, string>
  >({})

  const sortedUsers = useMemo(() => {
    return [...users].sort((left, right) => left.id - right.id)
  }, [users])

  function canManageUser(target: CompanyUserStatsRow): boolean {
    if (currentUserId != null && target.id === currentUserId) {
      return false
    }
    if (
      currentUserRole === 'admin' &&
      (target.role === 'owner' || target.role === 'admin')
    ) {
      return false
    }
    return true
  }

  async function handleLimitSubmit(user: CompanyUserStatsRow): Promise<void> {
    const deltaRaw = (deltaByUserId[user.id] ?? '').trim()
    const delta = Number(deltaRaw)
    if (!Number.isInteger(delta) || delta === 0) {
      setValidationErrorByUserId((prev) => ({
        ...prev,
        [user.id]: 'Укажите целое значение delta (не 0).',
      }))
      return
    }
    const reason = (reasonByUserId[user.id] ?? '').trim()
    if (!reason) {
      setValidationErrorByUserId((prev) => ({
        ...prev,
        [user.id]: 'Укажите причину изменения лимита.',
      }))
      return
    }
    setValidationErrorByUserId((prev) => ({ ...prev, [user.id]: '' }))
    const success = await onUpdateLimit({ userId: user.id, delta, reason })
    if (success) {
      setDeltaByUserId((prev) => ({ ...prev, [user.id]: '' }))
      setReasonByUserId((prev) => ({ ...prev, [user.id]: '' }))
    }
  }

  async function handleDetach(user: CompanyUserStatsRow): Promise<void> {
    const confirmed = window.confirm(
      `Удалить сотрудника ${user.email} из компании?`,
    )
    if (!confirmed) {
      return
    }
    setValidationErrorByUserId((prev) => ({ ...prev, [user.id]: '' }))
    await onDetach(user.id)
  }

  return (
    <section className="company-admin-section">
      <div className="company-admin-section__header">
        <h2 className="company-admin-section__title">2. Сотрудники</h2>
        <button
          type="button"
          className="button button--secondary"
          onClick={onRetry}
          disabled={isLoading}
        >
          {isLoading ? 'Обновляем...' : 'Обновить'}
        </button>
      </div>

      {isLoading && users.length === 0 ? (
        <p className="card__subtitle">Загружаем сотрудников...</p>
      ) : null}
      {errorMessage ? <p className="message message--error">{errorMessage}</p> : null}
      {!isLoading && users.length === 0 ? (
        <p className="card__subtitle">Сотрудники не найдены.</p>
      ) : null}

      {users.length > 0 ? (
        <div className="company-admin-table-wrap">
          <table className="company-admin-table">
            <thead>
              <tr>
                <th>Фамилия</th>
                <th>Имя</th>
                <th>Email</th>
                <th>Роль</th>
                <th>Дата добавления</th>
                <th>Лимит</th>
                <th>Расход за всё время</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {sortedUsers.map((user) => {
                const canManage = canManageUser(user)
                const isUpdating = Boolean(isUpdatingLimitByUserId[user.id])
                const isDetaching = Boolean(isDetachingByUserId[user.id])
                const isBusy = isUpdating || isDetaching
                const rowError = validationErrorByUserId[user.id]

                return (
                  <tr key={user.id}>
                    <td>{user.last_name ?? '-'}</td>
                    <td>{user.first_name ?? '-'}</td>
                    <td>{user.email}</td>
                    <td>{user.role}</td>
                    <td>{formatDate(user.joined_company_at)}</td>
                    <td>{formatNumber(user.remaining_credits)}</td>
                    <td>{formatNumber(user.spent_all_time)}</td>
                    <td>
                      {canManage ? (
                        <div className="company-admin-row-actions">
                          <input
                            className="input"
                            type="number"
                            step={1}
                            value={deltaByUserId[user.id] ?? ''}
                            onChange={(event) =>
                              setDeltaByUserId((prev) => ({
                                ...prev,
                                [user.id]: event.target.value,
                              }))
                            }
                            placeholder="+10 или -5"
                            disabled={isBusy}
                          />
                          <input
                            className="input"
                            type="text"
                            value={reasonByUserId[user.id] ?? ''}
                            onChange={(event) =>
                              setReasonByUserId((prev) => ({
                                ...prev,
                                [user.id]: event.target.value,
                              }))
                            }
                            placeholder="Причина"
                            disabled={isBusy}
                          />
                          <button
                            type="button"
                            className="button button--secondary"
                            onClick={() => {
                              void handleLimitSubmit(user)
                            }}
                            disabled={isBusy}
                          >
                            {isUpdating ? 'Сохраняем...' : 'Изменить лимит'}
                          </button>
                          <button
                            type="button"
                            className="button button--secondary"
                            onClick={() => {
                              void handleDetach(user)
                            }}
                            disabled={isBusy}
                          >
                            {isDetaching ? 'Удаляем...' : 'Удалить сотрудника'}
                          </button>
                          {rowError ? (
                            <p className="message message--error">{rowError}</p>
                          ) : null}
                        </div>
                      ) : (
                        <span className="hint">Недоступно по правилам роли</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}
