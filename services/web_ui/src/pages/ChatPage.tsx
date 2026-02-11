import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { toUserMessage } from '../auth/errors'
import { useAuth } from '../auth/useAuth'

export function ChatPage() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onLogout() {
    setIsSubmitting(true)
    setError(null)
    try {
      await logout()
      navigate('/login', { replace: true })
    } catch (logoutError) {
      setError(toUserMessage(logoutError, 'Could not log out right now.'))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="screen">
      <section className="card">
        <h1 className="card__title">Chat page (stub)</h1>
        <p className="card__subtitle">
          Session is active. Next commit adds full chat UI and message history.
        </p>

        <dl className="kv">
          <dt>id</dt>
          <dd>{user?.id ?? '-'}</dd>
          <dt>email</dt>
          <dd>{user?.email ?? '-'}</dd>
          <dt>role</dt>
          <dd>{user?.role ?? '-'}</dd>
          <dt>company_id</dt>
          <dd>{user?.company_id ?? '-'}</dd>
          <dt>is_active</dt>
          <dd>{String(user?.is_active ?? false)}</dd>
        </dl>

        <button className="button button--secondary" onClick={onLogout} disabled={isSubmitting}>
          {isSubmitting ? 'Logging out...' : 'Logout'}
        </button>

        {error ? <p className="message message--error">{error}</p> : null}
      </section>
    </main>
  )
}
