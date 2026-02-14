import { Navigate, Outlet, useParams } from 'react-router-dom'

import { resolvePostAuthRoute } from '../auth/postAuthRoute'
import { useAuth } from '../auth/useAuth'

function LoadingCard({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <main className="screen">
      <section className="card">
        <h1 className="card__title">{title}</h1>
        <p className="card__subtitle">{subtitle}</p>
      </section>
    </main>
  )
}

function useAuthGuard() {
  const { status, user } = useAuth()

  if (status === 'loading') {
    return { status: 'loading' as const, user }
  }
  if (status !== 'authenticated' || !user) {
    return { status: 'anonymous' as const, user: null }
  }
  return { status: 'authenticated' as const, user }
}

export function RequireSuperadmin() {
  const { status, user } = useAuthGuard()
  if (status === 'loading') {
    return <LoadingCard title="Checking access" subtitle="Please wait..." />
  }
  if (!user) {
    return <Navigate to="/login" replace />
  }
  if (!user.is_superadmin) {
    return <Navigate to={resolvePostAuthRoute(user)} replace />
  }
  return <Outlet />
}

export function RequireOrgAdmin() {
  const { status, user } = useAuthGuard()
  const params = useParams()
  if (status === 'loading') {
    return <LoadingCard title="Checking access" subtitle="Please wait..." />
  }
  if (!user) {
    return <Navigate to="/login" replace />
  }
  const orgId = user.org_id ?? user.company_id
  const isAdmin = user.role === 'owner' || user.role === 'admin'
  if (!orgId || !isAdmin) {
    return <Navigate to={resolvePostAuthRoute(user)} replace />
  }
  const routeOrgId = params.id ? Number(params.id) : null
  if (routeOrgId && routeOrgId !== orgId) {
    return <Navigate to={resolvePostAuthRoute(user)} replace />
  }
  return <Outlet />
}

export function RequireOnboarding() {
  const { status, user } = useAuthGuard()
  if (status === 'loading') {
    return <LoadingCard title="Checking access" subtitle="Please wait..." />
  }
  if (!user) {
    return <Navigate to="/login" replace />
  }
  if (user.is_superadmin) {
    return <Navigate to={resolvePostAuthRoute(user)} replace />
  }
  const orgId = user.org_id ?? user.company_id
  if (orgId != null) {
    return <Navigate to={resolvePostAuthRoute(user)} replace />
  }
  return <Outlet />
}
