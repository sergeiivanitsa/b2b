import { Link, useParams } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'

export function OrgAdminPage() {
  const { user } = useAuth()
  const params = useParams()
  const orgId = params.id

  return (
    <main className="screen">
      <section className="card">
        <h1 className="card__title">Company admin</h1>
        <p className="card__subtitle">
          This section is under construction. Organization: {orgId ?? '-'}.
        </p>
        <p className="hint">
          User: {user?.email ?? '-'}. Role: {user?.role ?? '-'}.
        </p>
        <p className="hint">
          <Link to="/chat">Back to chat</Link>.
        </p>
      </section>
    </main>
  )
}
