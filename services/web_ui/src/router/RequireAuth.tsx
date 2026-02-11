import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'

export function RequireAuth() {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return (
      <main className="screen">
        <section className="card">
          <h1 className="card__title">Checking session</h1>
          <p className="card__subtitle">Please wait...</p>
        </section>
      </main>
    )
  }

  if (status !== 'authenticated') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  return <Outlet />
}
