import { Navigate, Outlet } from 'react-router-dom'

import { useClaimsAdminAuth } from './useClaimsAdminAuth'

export function RequireClaimsAdmin() {
  const { status } = useClaimsAdminAuth()

  if (status === 'loading') {
    return (
      <main className="screen">
        <section className="card">
          <h1 className="card__title">Checking claims admin access</h1>
          <p className="card__subtitle">Please wait...</p>
        </section>
      </main>
    )
  }

  if (status === 'anonymous') {
    return <Navigate to="/admin/login" replace />
  }

  if (status === 'forbidden') {
    return (
      <main className="screen">
        <section className="card">
          <h1 className="card__title">Access denied</h1>
          <p className="card__subtitle">
            This account is not in claims-admin whitelist.
          </p>
        </section>
      </main>
    )
  }

  return <Outlet />
}

