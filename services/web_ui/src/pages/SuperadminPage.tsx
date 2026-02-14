import { Link } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'

export function SuperadminPage() {
  const { user } = useAuth()

  return (
    <main className="screen">
      <section className="card">
        <h1 className="card__title">Superadmin</h1>
        <p className="card__subtitle">This section is under construction.</p>
        <p className="hint">User: {user?.email ?? '-'}.</p>
        <p className="hint">
          <Link to="/chat">Back to chat</Link>.
        </p>
      </section>
    </main>
  )
}
