import { Navigate, Route, Routes } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import { ChatPage } from '../pages/ChatPage'
import { ConfirmPage } from '../pages/ConfirmPage'
import { InviteAcceptPage } from '../pages/InviteAcceptPage'
import { LoginPage } from '../pages/LoginPage'
import { RequireAuth } from './RequireAuth'

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
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

function HomeRedirect() {
  const { status } = useAuth()

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

  return <Navigate to={status === 'authenticated' ? '/chat' : '/login'} replace />
}

function LoginRoute() {
  const { status } = useAuth()

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
    return <Navigate to="/chat" replace />
  }

  return <LoginPage />
}
