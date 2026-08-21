import { useContext } from 'react'

import {
  ClaimsAdminAuthContext,
  type ClaimsAdminAuthContextValue,
} from './ClaimsAdminAuthContext'

export function useClaimsAdminAuth(): ClaimsAdminAuthContextValue {
  const context = useContext(ClaimsAdminAuthContext)
  if (!context) {
    throw new Error('useClaimsAdminAuth must be used within ClaimsAdminAuthProvider')
  }
  return context
}

