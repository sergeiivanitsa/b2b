import { apiFetchJson } from '../lib/api'

type RequestOptions = {
  signal?: AbortSignal
}

export type CompanyRole = 'owner' | 'admin' | 'member'

export type CompanySummary = {
  company: {
    id: number
    name: string
    inn: string | null
    phone: string | null
    status: string
  }
  credits: {
    pool_balance: number
    allocated_total: number
    unallocated_balance: number
  }
  users: {
    total: number
    active: number
  }
}

export type CompanyUserStatsRow = {
  id: number
  first_name: string | null
  last_name: string | null
  email: string
  role: CompanyRole
  is_active: boolean
  joined_company_at: string | null
  remaining_credits: number
  spent_all_time: number
}

export type CompanyUsersStatsResponse = {
  users: CompanyUserStatsRow[]
}

export type CompanyInvite = {
  id: number
  email: string
  first_name: string | null
  last_name: string | null
  role: CompanyRole
  expires_at: string
  created_at: string
}

export type CompanyInvitesResponse = {
  invites: CompanyInvite[]
}

export type CreateCompanyInviteInput = {
  email: string
  first_name?: string | null
  last_name?: string | null
}

export type CreateCompanyInviteResponse = {
  status: 'ok'
  token?: string
  link?: string
}

export type UpdateCompanyUserLimitInput = {
  delta: number
  reason: string
}

export type UpdateCompanyUserLimitResponse = {
  status: 'ok'
  user: {
    id: number
    email: string
    role: CompanyRole
    is_active: boolean
    remaining_credits: number
  }
  credits: {
    pool_balance: number
    allocated_total: number
    unallocated_balance: number
  }
}

export type DetachCompanyUserResponse = {
  status: 'ok'
  user: {
    id: number
    email: string
    company_id: number | null
    role: CompanyRole
    is_active: boolean
    joined_company_at: string | null
  }
  released_limit: number
}

export async function getCompanySummary(
  options: RequestOptions = {},
): Promise<CompanySummary> {
  return apiFetchJson<CompanySummary>('/company/summary', {
    signal: options.signal,
  })
}

export async function getCompanyUsersStats(
  options: RequestOptions = {},
): Promise<CompanyUsersStatsResponse> {
  return apiFetchJson<CompanyUsersStatsResponse>('/company/users/stats', {
    signal: options.signal,
  })
}

export async function listCompanyInvites(
  options: RequestOptions = {},
): Promise<CompanyInvitesResponse> {
  return apiFetchJson<CompanyInvitesResponse>('/company/invites', {
    signal: options.signal,
  })
}

export async function createCompanyInvite(
  payload: CreateCompanyInviteInput,
  options: RequestOptions = {},
): Promise<CreateCompanyInviteResponse> {
  return apiFetchJson<CreateCompanyInviteResponse>('/company/invites', {
    method: 'POST',
    body: payload,
    signal: options.signal,
  })
}

export async function updateCompanyUserLimit(
  userId: number,
  payload: UpdateCompanyUserLimitInput,
  options: RequestOptions = {},
): Promise<UpdateCompanyUserLimitResponse> {
  ensurePositiveUserId(userId)
  if (!Number.isInteger(payload.delta) || payload.delta === 0) {
    throw new Error('delta must be a non-zero integer')
  }
  return apiFetchJson<UpdateCompanyUserLimitResponse>(`/company/users/${userId}/limit`, {
    method: 'PATCH',
    body: payload,
    signal: options.signal,
  })
}

export async function detachCompanyUser(
  userId: number,
  options: RequestOptions = {},
): Promise<DetachCompanyUserResponse> {
  ensurePositiveUserId(userId)
  return apiFetchJson<DetachCompanyUserResponse>(`/company/users/${userId}/detach`, {
    method: 'POST',
    signal: options.signal,
  })
}

function ensurePositiveUserId(userId: number): void {
  if (!Number.isInteger(userId) || userId <= 0) {
    throw new Error('userId must be a positive integer')
  }
}
