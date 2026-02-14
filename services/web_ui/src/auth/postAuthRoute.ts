import type { AuthUser } from './types'

export function resolvePostAuthRoute(user: AuthUser | null): string {
  if (!user) {
    return '/login'
  }
  if (user.is_superadmin) {
    return '/superadmin'
  }
  const orgId = user.org_id ?? user.company_id
  if (orgId == null) {
    return '/onboarding/create-org'
  }
  return '/chat'
}
