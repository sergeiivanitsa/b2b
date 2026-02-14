import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { createOrg } from '../auth/authApi'
import { toUserMessage } from '../auth/errors'
import { resolvePostAuthRoute } from '../auth/postAuthRoute'
import { useAuth } from '../auth/useAuth'

function sanitizeInn(value: string) {
  return value.replace(/\D/g, '')
}

function safeNextPath(value: string | null) {
  if (!value) {
    return null
  }
  if (!value.startsWith('/')) {
    return null
  }
  return value
}

export function OnboardingCreateOrgPage() {
  const { user, refreshWhoami } = useAuth()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const [inn, setInn] = useState('')
  const [phone, setPhone] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const nextPath = useMemo(
    () => safeNextPath(searchParams.get('next')),
    [searchParams],
  )

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const normalizedInn = sanitizeInn(inn)
    const normalizedPhone = phone.trim()
    if (!normalizedInn) {
      setError('Enter INN to continue.')
      return
    }
    if (!normalizedPhone) {
      setError('Enter phone number.')
      return
    }

    setIsSubmitting(true)
    setError(null)
    setSuccessMessage(null)

    try {
      await createOrg({ inn: normalizedInn, phone: normalizedPhone })
      const nextUser = await refreshWhoami()
      setSuccessMessage('Company created.')
      if (nextPath) {
        navigate(nextPath, { replace: true })
        return
      }
      navigate(resolvePostAuthRoute(nextUser), { replace: true })
    } catch (submitError) {
      setError(toUserMessage(submitError, 'Could not create company.'))
    } finally {
      setIsSubmitting(false)
    }
  }

  if (!user) {
    return (
      <main className="screen">
        <section className="card">
          <h1 className="card__title">Preparing</h1>
          <p className="card__subtitle">Checking session...</p>
        </section>
      </main>
    )
  }

  return (
    <main className="screen">
      <section className="card">
        <h1 className="card__title">Create company</h1>
        <p className="card__subtitle">
          Provide INN and phone to complete onboarding.
        </p>

        <form className="form" onSubmit={onSubmit}>
          <label className="label" htmlFor="inn">
            INN
          </label>
          <input
            id="inn"
            className="input"
            type="text"
            value={inn}
            onChange={(event) => setInn(event.target.value)}
            placeholder="10 or 12 digits"
            inputMode="numeric"
            autoComplete="off"
          />

          <label className="label" htmlFor="phone">
            Phone
          </label>
          <input
            id="phone"
            className="input"
            type="tel"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            placeholder="+7..."
            autoComplete="tel"
          />

          <button className="button" type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Creating...' : 'Create company'}
          </button>
        </form>

        {successMessage ? (
          <p className="message message--success">{successMessage}</p>
        ) : null}
        {error ? <p className="message message--error">{error}</p> : null}

        <p className="hint">
          You can return to chat after creating the company.{' '}
          <Link to="/chat">Go to chat</Link>.
        </p>
      </section>
    </main>
  )
}
