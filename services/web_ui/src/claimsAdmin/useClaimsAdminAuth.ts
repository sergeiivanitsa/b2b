import { useContext } from 'react'

import {
  ClaimsAdminAuthContext,
  type ClaimsAdminAuthContextValue,
} from './ClaimsAdminAuthProvider'

export function useClaimsAdminAuth(): ClaimsAdminAuthContextValue {
  const context = useContext(ClaimsAdminAuthContext)
  if (!context) {
    throw new Error('useClaimsAdminAuth must be used within ClaimsAdminAuthProvider')
  }
  return context
}

