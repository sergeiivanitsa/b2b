import { createContext, useCallback, useEffect, useMemo, useState } from 'react'
import type { PropsWithChildren } from 'react'

import { ApiHttpError } from '../lib/api'
import {
  confirmClaimsAdminToken,
  logoutClaimsAdminSession,
  probeClaimsAdminSession,
  requestClaimsAdminLink,
} from './adminAuthApi'
import type { ClaimsAdminAuthStatus } from './types'

export type ClaimsAdminAuthContextValue = {
  status: ClaimsAdminAuthStatus
  refreshSession: () => Promise<ClaimsAdminAuthStatus>
  requestLink: (email: string) => Promise<void>
  confirmToken: (token: string) => Promise<ClaimsAdminAuthStatus>
  logout: () => Promise<void>
}

export const ClaimsAdminAuthContext = createContext<ClaimsAdminAuthContextValue | undefined>(
  undefined,
)

export function ClaimsAdminAuthProvider({ children }: PropsWithChildren) {
  const [status, setStatus] = useState<ClaimsAdminAuthStatus>('loading')

  const refreshSession = useCallback(async (): Promise<ClaimsAdminAuthStatus> => {
    try {
      await probeClaimsAdminSession()
      setStatus('authenticated')
      return 'authenticated'
    } catch (error) {
      if (error instanceof ApiHttpError && error.status === 403) {
        setStatus('forbidden')
        return 'forbidden'
      }
      if (error instanceof ApiHttpError && error.status === 401) {
        setStatus('anonymous')
        return 'anonymous'
      }
      setStatus('anonymous')
      throw error
    }
  }, [])

  useEffect(() => {
    let isDisposed = false

    ;(async () => {
      try {
        const nextStatus = await refreshSession()
        if (!isDisposed) {
          setStatus(nextStatus)
        }
      } catch {
        if (!isDisposed) {
          setStatus('anonymous')
        }
      }
    })()

    return () => {
      isDisposed = true
    }
  }, [refreshSession])

  const requestLink = useCallback(async (email: string) => {
    await requestClaimsAdminLink(email)
  }, [])

  const confirmToken = useCallback(
    async (token: string): Promise<ClaimsAdminAuthStatus> => {
      await confirmClaimsAdminToken(token)
      return refreshSession()
    },
    [refreshSession],
  )

  const logout = useCallback(async () => {
    try {
      await logoutClaimsAdminSession()
    } catch (error) {
      if (!(error instanceof ApiHttpError) || error.status !== 401) {
        throw error
      }
    }
    setStatus('anonymous')
  }, [])

  const value = useMemo<ClaimsAdminAuthContextValue>(
    () => ({
      status,
      refreshSession,
      requestLink,
      confirmToken,
      logout,
    }),
    [confirmToken, logout, refreshSession, requestLink, status],
  )

  return (
    <ClaimsAdminAuthContext.Provider value={value}>
      {children}
    </ClaimsAdminAuthContext.Provider>
  )
}

