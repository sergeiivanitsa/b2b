export type AuthStatus = 'loading' | 'authenticated' | 'anonymous'

export type AuthUser = {
  id: number
  email: string
  role: string
  org_id: number | null
  company_id: number | null
  is_superadmin: boolean
  is_active: boolean
  first_name?: string | null
  last_name?: string | null
  company_name?: string | null
  remaining_credits?: number
}

export type AuthContextValue = {
  status: AuthStatus
  user: AuthUser | null
  refreshWhoami: () => Promise<AuthUser | null>
  requestLink: (email: string) => Promise<void>
  confirmToken: (token: string) => Promise<AuthUser | null>
  acceptInvite: (token: string) => Promise<AuthUser | null>
  logout: () => Promise<void>
}
