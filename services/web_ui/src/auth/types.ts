export type AuthStatus = 'loading' | 'authenticated' | 'anonymous'

export type AuthUser = {
  id: number
  email: string
  role: string
  company_id: number | null
  is_active: boolean
}

export type AuthContextValue = {
  status: AuthStatus
  user: AuthUser | null
  refreshWhoami: () => Promise<void>
  requestLink: (email: string) => Promise<void>
  confirmToken: (token: string) => Promise<void>
  acceptInvite: (token: string) => Promise<void>
  logout: () => Promise<void>
}
