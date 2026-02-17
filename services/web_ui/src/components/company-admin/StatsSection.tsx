import { useMemo } from 'react'

import type {
  CompanySummary,
  CompanyUserStatsRow,
} from '../../companyAdmin/companyAdminApi'

type StatsSectionProps = {
  users: CompanyUserStatsRow[]
  summary: CompanySummary | null
  isLoading: boolean
}

type RoleStatRow = {
  role: string
  total: number
  active: number
  spentAllTime: number
  remainingCredits: number
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat('ru-RU').format(value)
}

export function StatsSection({ users, summary, isLoading }: StatsSectionProps) {
  const topBySpent = useMemo(() => {
    return [...users]
      .sort((left, right) => right.spent_all_time - left.spent_all_time)
      .slice(0, 20)
  }, [users])

  const roleStats = useMemo<RoleStatRow[]>(() => {
    const byRole = new Map<string, RoleStatRow>()
    for (const user of users) {
      const current = byRole.get(user.role) ?? {
        role: user.role,
        total: 0,
        active: 0,
        spentAllTime: 0,
        remainingCredits: 0,
      }
      current.total += 1
      if (user.is_active) {
        current.active += 1
      }
      current.spentAllTime += user.spent_all_time
      current.remainingCredits += user.remaining_credits
      byRole.set(user.role, current)
    }
    const roleOrder = ['owner', 'admin', 'member']
    return [...byRole.values()].sort((left, right) => {
      const leftOrder = roleOrder.indexOf(left.role)
      const rightOrder = roleOrder.indexOf(right.role)
      if (leftOrder !== rightOrder) {
        return leftOrder - rightOrder
      }
      return left.role.localeCompare(right.role)
    })
  }, [users])

  const totalSpent = useMemo(() => {
    return users.reduce((acc, user) => acc + user.spent_all_time, 0)
  }, [users])

  return (
    <section className="company-admin-section">
      <div className="company-admin-section__header">
        <h2 className="company-admin-section__title">4. Статистика</h2>
      </div>

      {isLoading && users.length === 0 ? (
        <p className="card__subtitle">Готовим статистику...</p>
      ) : null}

      {!isLoading && users.length === 0 ? (
        <p className="card__subtitle">Недостаточно данных для статистики.</p>
      ) : null}

      {users.length > 0 ? (
        <>
          <article className="company-admin-box">
            <h3 className="company-admin-box__title">Сводка</h3>
            <dl className="kv">
              <dt>Суммарный расход сотрудников</dt>
              <dd>{formatNumber(totalSpent)}</dd>
              <dt>Общий баланс компании (pool)</dt>
              <dd>{summary ? formatNumber(summary.credits.pool_balance) : '-'}</dd>
              <dt>Выделено сотрудникам</dt>
              <dd>{summary ? formatNumber(summary.credits.allocated_total) : '-'}</dd>
            </dl>
          </article>

          <article className="company-admin-box">
            <h3 className="company-admin-box__title">По ролям</h3>
            <div className="company-admin-table-wrap">
              <table className="company-admin-table">
                <thead>
                  <tr>
                    <th>Роль</th>
                    <th>Всего</th>
                    <th>Активных</th>
                    <th>Расход за всё время</th>
                    <th>Сумма лимитов</th>
                  </tr>
                </thead>
                <tbody>
                  {roleStats.map((row) => (
                    <tr key={row.role}>
                      <td>{row.role}</td>
                      <td>{formatNumber(row.total)}</td>
                      <td>{formatNumber(row.active)}</td>
                      <td>{formatNumber(row.spentAllTime)}</td>
                      <td>{formatNumber(row.remainingCredits)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>

          <article className="company-admin-box">
            <h3 className="company-admin-box__title">Топ сотрудников по расходу</h3>
            <div className="company-admin-table-wrap">
              <table className="company-admin-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Фамилия</th>
                    <th>Имя</th>
                    <th>Email</th>
                    <th>Роль</th>
                    <th>Расход за всё время</th>
                    <th>Текущий лимит</th>
                  </tr>
                </thead>
                <tbody>
                  {topBySpent.map((user, index) => (
                    <tr key={user.id}>
                      <td>{index + 1}</td>
                      <td>{user.last_name ?? '-'}</td>
                      <td>{user.first_name ?? '-'}</td>
                      <td>{user.email}</td>
                      <td>{user.role}</td>
                      <td>{formatNumber(user.spent_all_time)}</td>
                      <td>{formatNumber(user.remaining_credits)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        </>
      ) : null}
    </section>
  )
}
