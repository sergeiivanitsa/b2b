import { apiFetchJson } from '../lib/api'
import type { AdminAuthStatusResponse } from './types'
import { fetchAdminClaims } from './adminClaimsApi'

export async function requestClaimsAdminLink(email: string): Promise<AdminAuthStatusResponse> {
  const normalizedEmail = email.trim().toLowerCase()
  if (!normalizedEmail) {
    throw new Error('email is required')
  }
  return apiFetchJson<AdminAuthStatusResponse>('/admin/auth/request-link', {
    method: 'POST',
    body: { email: normalizedEmail },
  })
}

export async function confirmClaimsAdminToken(
  token: string,
): Promise<AdminAuthStatusResponse> {
  const normalizedToken = token.trim()
  if (!normalizedToken) {
    throw new Error('token is required')
  }
  return apiFetchJson<AdminAuthStatusResponse>('/admin/auth/confirm', {
    method: 'POST',
    body: { token: normalizedToken },
  })
}

export async function logoutClaimsAdminSession(): Promise<void> {
  await apiFetchJson<AdminAuthStatusResponse>('/auth/logout', {
    method: 'POST',
  })
}

export async function probeClaimsAdminSession(): Promise<void> {
  await fetchAdminClaims({ limit: 1, offset: 0 })
}

