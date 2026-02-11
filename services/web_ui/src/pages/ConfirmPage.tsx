import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { toUserMessage } from '../auth/errors'
import { useAuth } from '../auth/useAuth'

export function ConfirmPage() {
  const { confirmToken } = useAuth()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const tokenFromQuery = (searchParams.get('token') ?? '').trim()
  const [token, setToken] = useState(tokenFromQuery)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const attemptedAutoTokenRef = useRef<string | null>(null)

  const confirmAndContinue = useCallback(
    async (value: string) => {
      const normalizedToken = value.trim()
      if (!normalizedToken) {
        setError('Enter token to continue.')
        return
      }

      setIsSubmitting(true)
      setError(null)

      try {
        await confirmToken(normalizedToken)
        navigate('/chat', { replace: true })
      } catch (submitError) {
        setError(toUserMessage(submitError, 'Could not confirm token.'))
      } finally {
        setIsSubmitting(false)
      }
    },
    [confirmToken, navigate],
  )

  useEffect(() => {
    if (!tokenFromQuery) {
      return
    }
    if (attemptedAutoTokenRef.current === tokenFromQuery) {
      return
    }
    attemptedAutoTokenRef.current = tokenFromQuery
    void confirmAndContinue(tokenFromQuery)
  }, [confirmAndContinue, tokenFromQuery])

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await confirmAndContinue(token)
  }

  return (
    <main className="screen">
      <section className="card">
        <h1 className="card__title">Confirm sign in</h1>
        <p className="card__subtitle">
          Paste your token from email, or open this page using the magic link.
        </p>

        <form className="form" onSubmit={onSubmit}>
          <label className="label" htmlFor="token">
            Token
          </label>
          <input
            id="token"
            className="input"
            type="text"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            placeholder="Paste token here"
            autoComplete="one-time-code"
          />

          <button className="button" type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Confirming...' : 'Confirm token'}
          </button>
        </form>

        {error ? <p className="message message--error">{error}</p> : null}

        <p className="hint">
          Need another link? <Link to="/login">Go back to login</Link>.
        </p>
      </section>
    </main>
  )
}
