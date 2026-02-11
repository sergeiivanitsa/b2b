import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import { toUserMessage } from '../auth/errors'

export function LoginPage() {
  const { requestLink } = useAuth()
  const [email, setEmail] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const normalizedEmail = email.trim().toLowerCase()
    if (!normalizedEmail) {
      setError('Enter email to continue.')
      return
    }

    setIsSubmitting(true)
    setError(null)
    setSuccessMessage(null)

    try {
      await requestLink(normalizedEmail)
      setSuccessMessage(`Sign-in link sent to ${normalizedEmail}. Check your inbox.`)
    } catch (submitError) {
      setError(
        toUserMessage(submitError, 'Could not send sign-in link. Please try again.'),
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="screen">
      <section className="card">
        <h1 className="card__title">Sign in</h1>
        <p className="card__subtitle">Use your email to receive a magic link or token.</p>

        <form className="form" onSubmit={onSubmit}>
          <label className="label" htmlFor="email">
            Email
          </label>
          <input
            id="email"
            className="input"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
            required
          />

          <button className="button" type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Sending...' : 'Send code or link'}
          </button>
        </form>

        {successMessage ? <p className="message message--success">{successMessage}</p> : null}
        {error ? <p className="message message--error">{error}</p> : null}

        <p className="hint">
          Already have a token? <Link to="/auth/confirm">Enter it manually</Link>.
        </p>
      </section>
    </main>
  )
}
