import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'

import { ApiHttpError } from '../lib/api'
import { useClaimsAdminAuth } from '../claimsAdmin/useClaimsAdminAuth'

export function AdminLoginPage() {
  const navigate = useNavigate()
  const { status, requestLink, confirmToken } = useClaimsAdminAuth()

  const [email, setEmail] = useState('')
  const [token, setToken] = useState('')
  const [isSubmittingEmail, setIsSubmittingEmail] = useState(false)
  const [isSubmittingToken, setIsSubmittingToken] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  useEffect(() => {
    setError(null)
  }, [status])

  if (status === 'authenticated') {
    return <Navigate to="/admin/claims" replace />
  }

  async function onEmailSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const normalizedEmail = email.trim().toLowerCase()
    if (!normalizedEmail) {
      setError('Введите email для входа.')
      return
    }

    setIsSubmittingEmail(true)
    setError(null)
    setSuccessMessage(null)
    try {
      await requestLink(normalizedEmail)
      setSuccessMessage(
        `Ссылка для входа отправлена на ${normalizedEmail}. Проверьте почту.`,
      )
    } catch (submitError) {
      setError(toUserMessage(submitError, 'Не удалось отправить ссылку. Повторите попытку.'))
    } finally {
      setIsSubmittingEmail(false)
    }
  }

  async function onTokenSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const normalizedToken = token.trim()
    if (!normalizedToken) {
      setError('Введите токен подтверждения.')
      return
    }

    setIsSubmittingToken(true)
    setError(null)
    setSuccessMessage(null)
    try {
      const nextStatus = await confirmToken(normalizedToken)
      if (nextStatus === 'authenticated') {
        navigate('/admin/claims', { replace: true })
        return
      }
      if (nextStatus === 'forbidden') {
        setError('Аккаунт не включён в claims-admin whitelist.')
      } else {
        setError('Не удалось подтвердить токен.')
      }
    } catch (submitError) {
      setError(toUserMessage(submitError, 'Токен недействителен или просрочен.'))
    } finally {
      setIsSubmittingToken(false)
    }
  }

  return (
    <main className="screen admin-login-screen">
      <section className="card admin-login-card">
        <h1 className="card__title">Claims Admin Login</h1>
        <p className="card__subtitle">
          Вход в claims-admin через отдельный magic-link flow.
        </p>

        <form className="form" onSubmit={onEmailSubmit}>
          <label className="label" htmlFor="admin-email">
            Email
          </label>
          <input
            id="admin-email"
            className="input"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="admin@company.ru"
            required
          />
          <button className="button" type="submit" disabled={isSubmittingEmail}>
            {isSubmittingEmail ? 'Отправляем...' : 'Запросить magic-link'}
          </button>
        </form>

        <form className="form admin-login-card__token-form" onSubmit={onTokenSubmit}>
          <label className="label" htmlFor="admin-token">
            Токен (fallback)
          </label>
          <input
            id="admin-token"
            className="input"
            type="text"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            placeholder="Вставьте токен"
          />
          <button className="button button--secondary" type="submit" disabled={isSubmittingToken}>
            {isSubmittingToken ? 'Проверяем...' : 'Подтвердить токен'}
          </button>
        </form>

        {successMessage ? <p className="message message--success">{successMessage}</p> : null}
        {error ? <p className="message message--error">{error}</p> : null}
      </section>
    </main>
  )
}

function toUserMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiHttpError) {
    if (typeof error.payload === 'object' && error.payload && 'detail' in error.payload) {
      const detail = (error.payload as { detail: unknown }).detail
      if (typeof detail === 'string' && detail.trim()) {
        return detail
      }
    }
    return fallback
  }
  if (error instanceof Error && error.message) {
    return error.message
  }
  return fallback
}

