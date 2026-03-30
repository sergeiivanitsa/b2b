import { useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import { clearClaimSession, readClaimSession } from '../claims/claimSession'
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
      <Route path="/claims" element={<ClaimsPublicShell />} />
      <Route path="/claims/*" element={<Navigate to="/claims" replace />} />
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

function ClaimsPublicShell() {
  const [session, setSession] = useState(() => readClaimSession())

  function handleClearSession() {
    clearClaimSession()
    setSession(null)
  }

  return (
    <main className="claims-shell">
      <section className="claims-shell__card">
        <h1 className="claims-shell__title">Public Claims Flow</h1>
        <p className="claims-shell__subtitle">
          Public shell is mounted on <code>/claims</code>. Root <code>/</code> remains unchanged.
        </p>
        <p className="claims-shell__hint">
          Step pages and guided form UI will be implemented in the next frontend commit.
        </p>

        <section className="claims-shell__session" aria-live="polite">
          <h2 className="claims-shell__session-title">Local Session</h2>
          {session ? (
            <>
              <dl className="claims-shell__kv">
                <dt>claim_id</dt>
                <dd>{session.claimId}</dd>
                <dt>edit_token</dt>
                <dd className="claims-shell__token">{session.editToken}</dd>
              </dl>
              <button
                className="claims-shell__button claims-shell__button--secondary"
                type="button"
                onClick={handleClearSession}
              >
                Clear sessionStorage draft
              </button>
            </>
          ) : (
            <p className="claims-shell__empty">
              No active claim session in <code>sessionStorage</code>.
            </p>
          )}
        </section>
      </section>
    </main>
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
