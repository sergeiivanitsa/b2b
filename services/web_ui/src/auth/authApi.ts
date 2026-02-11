import { apiFetchJson } from '../lib/api'
import type { AuthUser } from './types'

type StatusResponse = {
  status: string
}

export async function fetchWhoami(): Promise<AuthUser> {
  return apiFetchJson<AuthUser>('/internal/whoami')
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
