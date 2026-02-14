import { Navigate, Route, Routes } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import { ChatPage } from '../pages/ChatPage'
import { ConfirmPage } from '../pages/ConfirmPage'
import { InviteAcceptPage } from '../pages/InviteAcceptPage'
import { LoginPage } from '../pages/LoginPage'
import { OnboardingCreateOrgPage } from '../pages/OnboardingCreateOrgPage'
import { OrgAdminPage } from '../pages/OrgAdminPage'
import { SuperadminPage } from '../pages/SuperadminPage'
import { resolvePostAuthRoute } from '../auth/postAuthRoute'
import { RequireAuth } from './RequireAuth'
import { RequireOnboarding, RequireOrgAdmin, RequireSuperadmin } from './RequireRole'

export function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<HomeRedirect />} />
      <Route path="/login" element={<LoginRoute />} />
      <Route path="/auth/confirm" element={<ConfirmPage />} />
      <Route path="/invites/accept" element={<InviteAcceptPage />} />
      <Route element={<RequireAuth />}>
        <Route path="/chat" element={<ChatPage />} />
      </Route>
      <Route element={<RequireAuth />}>
        <Route element={<RequireOnboarding />}>
          <Route path="/onboarding/create-org" element={<OnboardingCreateOrgPage />} />
        </Route>
        <Route element={<RequireOrgAdmin />}>
          <Route path="/org/:id/admin" element={<OrgAdminPage />} />
        </Route>
        <Route element={<RequireSuperadmin />}>
          <Route path="/superadmin" element={<SuperadminPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

function HomeRedirect() {
  const { status, user } = useAuth()

  if (status === 'loading') {
    return (
      <main className="screen">
        <section className="card">
          <h1 className="card__title">Loading</h1>
          <p className="card__subtitle">Checking current session...</p>
        </section>
      </main>
    )
  }

  return (
    <Navigate
      to={status === 'authenticated' ? resolvePostAuthRoute(user) : '/login'}
      replace
    />
  )
}

function LoginRoute() {
  const { status, user } = useAuth()

  if (status === 'loading') {
    return (
      <main className="screen">
        <section className="card">
          <h1 className="card__title">Loading</h1>
          <p className="card__subtitle">Checking current session...</p>
        </section>
      </main>
    )
  }

  if (status === 'authenticated') {
    return <Navigate to={resolvePostAuthRoute(user)} replace />
  }

  return <LoginPage />
}
