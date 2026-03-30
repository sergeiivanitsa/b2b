import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { fetchAdminClaims } from '../claimsAdmin/adminClaimsApi'
import { useClaimsAdminAuth } from '../claimsAdmin/useClaimsAdminAuth'
import type { AdminClaimsListItem } from '../claimsAdmin/types'
import { ApiHttpError } from '../lib/api'

const STATUS_FILTERS = ['', 'draft', 'preview_ready', 'paid', 'in_review', 'sent']
const GENERATION_FILTERS = ['', 'ready', 'manual_review_required', 'insufficient_data']

export function AdminClaimsListPage() {
  const navigate = useNavigate()
  const { logout } = useClaimsAdminAuth()
  const [items, setItems] = useState<AdminClaimsListItem[]>([])
  const [statusFilter, setStatusFilter] = useState('')
  const [generationStateFilter, setGenerationStateFilter] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isCancelled = false

    async function loadClaims() {
      try {
        setIsLoading(true)
        setError(null)
        const response = await fetchAdminClaims({
          status: statusFilter || undefined,
          generation_state: generationStateFilter || undefined,
          limit: 100,
          offset: 0,
        })
        if (!isCancelled) {
          setItems(response.items)
        }
      } catch (loadError) {
        if (isCancelled) {
          return
        }
        if (loadError instanceof ApiHttpError && loadError.status === 401) {
          navigate('/admin/login', { replace: true })
          return
        }
        setError('Не удалось загрузить список заявок.')
      } finally {
        if (!isCancelled) {
          setIsLoading(false)
        }
      }
    }

    void loadClaims()
    return () => {
      isCancelled = true
    }
  }, [generationStateFilter, navigate, statusFilter])

  async function onLogout() {
    await logout()
    navigate('/admin/login', { replace: true })
  }

  return (
    <main className="admin-claims-page">
      <section className="admin-claims-shell">
        <header className="admin-claims-header">
          <div>
            <h1 className="admin-claims-header__title">Claims Admin</h1>
            <p className="admin-claims-header__subtitle">
              Очередь заявок для ручной проверки и отправки клиенту.
            </p>
          </div>
          <button className="button button--secondary" type="button" onClick={onLogout}>
            Выйти
          </button>
        </header>

        <section className="admin-claims-filters">
          <label className="label" htmlFor="admin-filter-status">
            Статус
          </label>
          <select
            id="admin-filter-status"
            className="input"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            {STATUS_FILTERS.map((item) => (
              <option key={item || 'all'} value={item}>
                {item || 'Все'}
              </option>
            ))}
          </select>

          <label className="label" htmlFor="admin-filter-generation">
            Generation state
          </label>
          <select
            id="admin-filter-generation"
            className="input"
            value={generationStateFilter}
            onChange={(event) => setGenerationStateFilter(event.target.value)}
          >
            {GENERATION_FILTERS.map((item) => (
              <option key={item || 'all'} value={item}>
                {item || 'Все'}
              </option>
            ))}
          </select>
        </section>

        {isLoading ? <p className="admin-claims-loading">Загружаем заявки...</p> : null}
        {error ? <p className="message message--error">{error}</p> : null}

        {!isLoading && !error ? (
          <section className="admin-claims-table-wrap">
            <table className="admin-claims-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Status</th>
                  <th>Generation</th>
                  <th>Client email</th>
                  <th>Case type</th>
                  <th>Paid at</th>
                  <th>Updated at</th>
                </tr>
              </thead>
              <tbody>
                {items.length === 0 ? (
                  <tr>
                    <td colSpan={7}>Заявок по текущему фильтру нет.</td>
                  </tr>
                ) : (
                  items.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <Link to={`/admin/claims/${item.id}`}>#{item.id}</Link>
                      </td>
                      <td>{item.status}</td>
                      <td>{item.generation_state}</td>
                      <td>{item.client_email || '—'}</td>
                      <td>{item.case_type || '—'}</td>
                      <td>{formatDateTime(item.paid_at)}</td>
                      <td>{formatDateTime(item.updated_at)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </section>
        ) : null}
      </section>
    </main>
  )
}

function formatDateTime(value: string | null): string {
  if (!value) {
    return '—'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return new Intl.DateTimeFormat('ru-RU', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

