import { createContext, useCallback, useEffect, useMemo, useState } from 'react'
import type { PropsWithChildren } from 'react'

import {
  acceptInviteToken,
  confirmMagicToken,
  fetchWhoami,
  logoutSession,
  requestMagicLink,
} from './authApi'
import { isUnauthorizedError } from './errors'
import type { AuthContextValue, AuthStatus, AuthUser } from './types'

export const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: PropsWithChildren) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [user, setUser] = useState<AuthUser | null>(null)

  const refreshWhoami = useCallback(async () => {
    try {
      const nextUser = await fetchWhoami()
      setUser(nextUser)
      setStatus('authenticated')
      return nextUser
    } catch (error) {
      setUser(null)
      setStatus('anonymous')
      if (!isUnauthorizedError(error)) {
        throw error
      }
      return null
    }
  }, [])

  useEffect(() => {
    let disposed = false
    ;(async () => {
      try {
        const nextUser = await fetchWhoami()
        if (disposed) {
          return
        }
        setUser(nextUser)
        setStatus('authenticated')
      } catch {
        if (disposed) {
          return
        }
        setUser(null)
        setStatus('anonymous')
      }
    })()

    return () => {
      disposed = true
    }
  }, [])

  const requestLink = useCallback(async (email: string) => {
    await requestMagicLink(email)
  }, [])

  const confirmToken = useCallback(
    async (token: string) => {
      await confirmMagicToken(token)
      return refreshWhoami()
    },
    [refreshWhoami],
  )

  const acceptInvite = useCallback(
    async (token: string) => {
      await acceptInviteToken(token)
      return refreshWhoami()
    },
    [refreshWhoami],
  )

  const logout = useCallback(async () => {
    try {
      await logoutSession()
    } catch (error) {
      if (!isUnauthorizedError(error)) {
        throw error
      }
    }
    setUser(null)
    setStatus('anonymous')
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      refreshWhoami,
      requestLink,
      confirmToken,
      acceptInvite,
      logout,
    }),
    [acceptInvite, confirmToken, logout, refreshWhoami, requestLink, status, user],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
