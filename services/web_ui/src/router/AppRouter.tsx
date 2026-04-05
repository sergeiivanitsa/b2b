import { Navigate, Outlet, Route, Routes } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import { ClaimsAdminAuthProvider } from '../claimsAdmin/ClaimsAdminAuthProvider'
import { RequireClaimsAdmin } from '../claimsAdmin/RequireClaimsAdmin'
import { AdminAuthConfirmPage } from '../pages/AdminAuthConfirmPage'
import { AdminClaimDetailPage } from '../pages/AdminClaimDetailPage'
import { AdminClaimsListPage } from '../pages/AdminClaimsListPage'
import { AdminLoginPage } from '../pages/AdminLoginPage'
import { ChatPage } from '../pages/ChatPage'
import { ClaimStep1Page } from '../pages/ClaimStep1Page'
import { ClaimStep2Page } from '../pages/ClaimStep2Page'
import { ClaimStep3Page } from '../pages/ClaimStep3Page'
import { ClaimStep4Page } from '../pages/ClaimStep4Page'
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
      <Route path="/claims" element={<ClaimStep1Page />} />
      <Route path="/claims/step-2" element={<ClaimStep2Page />} />
      <Route path="/claims/step-3" element={<ClaimStep3Page />} />
      <Route path="/claims/step-4" element={<ClaimStep4Page />} />
      <Route path="/claims/*" element={<Navigate to="/claims" replace />} />
      <Route element={<ClaimsAdminRoutesLayout />}>
        <Route path="/admin" element={<Navigate to="/admin/login" replace />} />
        <Route path="/admin/login" element={<AdminLoginPage />} />
        <Route path="/admin/auth/confirm" element={<AdminAuthConfirmPage />} />
        <Route element={<RequireClaimsAdmin />}>
          <Route path="/admin/claims" element={<AdminClaimsListPage />} />
          <Route path="/admin/claims/:id" element={<AdminClaimDetailPage />} />
        </Route>
      </Route>
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

function ClaimsAdminRoutesLayout() {
  return (
    <ClaimsAdminAuthProvider>
      <Outlet />
    </ClaimsAdminAuthProvider>
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
