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

type RawAuthUser = AuthUser & { org_id?: number | null }

export async function fetchWhoami(): Promise<AuthUser> {
  const user = await apiFetchJson<RawAuthUser>('/internal/whoami')
  return {
    ...user,
    org_id: user.org_id ?? user.company_id ?? null,
  }
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
