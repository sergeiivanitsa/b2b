import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { toUserMessage } from '../auth/errors'
import { resolvePostAuthRoute } from '../auth/postAuthRoute'
import { useAuth } from '../auth/useAuth'

export function InviteAcceptPage() {
  const { acceptInvite } = useAuth()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const tokenFromQuery = (searchParams.get('token') ?? '').trim()
  const [token, setToken] = useState(tokenFromQuery)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const attemptedAutoTokenRef = useRef<string | null>(null)

  const acceptAndContinue = useCallback(
    async (value: string) => {
      const normalizedToken = value.trim()
      if (!normalizedToken) {
        setError('Enter invite token to continue.')
        return
      }

      setIsSubmitting(true)
      setError(null)

      try {
        const nextUser = await acceptInvite(normalizedToken)
        navigate(resolvePostAuthRoute(nextUser), { replace: true })
      } catch (submitError) {
        setError(toUserMessage(submitError, 'Could not accept invite.'))
      } finally {
        setIsSubmitting(false)
      }
    },
    [acceptInvite, navigate],
  )

  useEffect(() => {
    if (!tokenFromQuery) {
      return
    }
    if (attemptedAutoTokenRef.current === tokenFromQuery) {
      return
    }
    attemptedAutoTokenRef.current = tokenFromQuery
    void acceptAndContinue(tokenFromQuery)
  }, [acceptAndContinue, tokenFromQuery])

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await acceptAndContinue(token)
  }

  return (
    <main className="screen">
      <section className="card">
        <h1 className="card__title">Accept invite</h1>
        <p className="card__subtitle">
          Paste the invite token from email, or open this page from the invite link.
        </p>

        <form className="form" onSubmit={onSubmit}>
          <label className="label" htmlFor="invite-token">
            Invite token
          </label>
          <input
            id="invite-token"
            className="input"
            type="text"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            placeholder="Paste invite token here"
          />

          <button className="button" type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Accepting...' : 'Accept invite'}
          </button>
        </form>

        {error ? <p className="message message--error">{error}</p> : null}

        <p className="hint">
          Need a fresh sign-in link? <Link to="/login">Go to login</Link>.
        </p>
      </section>
    </main>
  )
}
