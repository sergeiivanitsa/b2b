import { createContext } from 'react'

import type { ClaimsAdminAuthStatus } from './types'

export type ClaimsAdminAuthContextValue = {
  status: ClaimsAdminAuthStatus
  refreshSession: () => Promise<ClaimsAdminAuthStatus>
  requestLink: (email: string) => Promise<void>
  confirmToken: (token: string) => Promise<ClaimsAdminAuthStatus>
  logout: () => Promise<void>
}

export const ClaimsAdminAuthContext = createContext<
  ClaimsAdminAuthContextValue | undefined
>(undefined)
