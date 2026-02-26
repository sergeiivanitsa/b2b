import { apiFetchJson } from '../lib/api'
import type { AuthUser } from './types'

type StatusResponse = {
  status: string
}

export type OnboardingOrgPayload = {
  inn: string
  phone: string
}

export type OnboardingOrgResponse = {
  org_id: number
  role: string
}

type RawAuthUser = {
  id: number
  email: string
  role: string
  org_id?: number | null
  company_id?: number | null
  is_superadmin: boolean
  is_active: boolean
  first_name?: string | null
  last_name?: string | null
  company_name?: string | null
  remaining_credits?: number | null
  company_pool_balance?: number | null
  company_allocated_total?: number | null
  company_unallocated_balance?: number | null
  effective_credits?: number | null
}

export async function fetchWhoami(): Promise<AuthUser> {
  const user = await apiFetchJson<RawAuthUser>('/internal/whoami')
  const companyId = normalizeId(user.company_id ?? user.org_id ?? null)
  const orgId = normalizeId(user.org_id ?? companyId ?? null)

  return {
    id: user.id,
    email: user.email,
    role: user.role,
    org_id: orgId,
    company_id: companyId,
    is_superadmin: user.is_superadmin,
    is_active: user.is_active,
    first_name: normalizeOptionalString(user.first_name),
    last_name: normalizeOptionalString(user.last_name),
    company_name: normalizeOptionalString(user.company_name),
    remaining_credits: normalizeRemainingCredits(user.remaining_credits),
    company_pool_balance: normalizeInteger(user.company_pool_balance),
    company_allocated_total: normalizeInteger(user.company_allocated_total),
    company_unallocated_balance: normalizeInteger(user.company_unallocated_balance),
    effective_credits: normalizeRemainingCredits(user.effective_credits),
  }
}

function normalizeId(value: number | null | undefined): number | null {
  if (typeof value !== 'number' || !Number.isInteger(value) || value <= 0) {
    return null
  }
  return value
}

function normalizeOptionalString(value: string | null | undefined): string | null {
  if (typeof value !== 'string') {
    return null
  }
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : null
}

function normalizeRemainingCredits(value: number | null | undefined): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return 0
  }
  return Math.max(0, Math.trunc(value))
}

function normalizeInteger(value: number | null | undefined): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return 0
  }
  return Math.trunc(value)
}

export async function requestMagicLink(email: string): Promise<void> {
  await apiFetchJson<StatusResponse>('/auth/request-link', {
    method: 'POST',
    body: { email },
  })
}

export async function confirmMagicToken(token: string): Promise<void> {
  await apiFetchJson<StatusResponse>('/auth/confirm', {
    method: 'POST',
    body: { token },
  })
}

export async function acceptInviteToken(token: string): Promise<void> {
  await apiFetchJson<StatusResponse>('/invites/accept', {
    method: 'POST',
    body: { token },
  })
}

export async function logoutSession(): Promise<void> {
  await apiFetchJson<StatusResponse>('/auth/logout', {
    method: 'POST',
  })
}

export async function createOrg(
  payload: OnboardingOrgPayload,
): Promise<OnboardingOrgResponse> {
  return apiFetchJson<OnboardingOrgResponse>('/onboarding/create-org', {
    method: 'POST',
    body: payload,
  })
}
