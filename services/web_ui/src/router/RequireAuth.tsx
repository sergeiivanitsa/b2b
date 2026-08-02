import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import { storeCompanyReturnTarget } from '../auth/companyReturnTarget'

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
    storeCompanyReturnTarget(location.pathname)
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  return <Outlet />
}
