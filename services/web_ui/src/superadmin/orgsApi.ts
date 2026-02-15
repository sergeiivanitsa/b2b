import { apiFetchJson } from '../lib/api'

export const ORG_STATUSES = ['active', 'pending', 'blocked', 'legacy'] as const
export type OrgStatus = (typeof ORG_STATUSES)[number]

export type SuperadminOrg = {
  id: number
  name: string
  inn: string | null
  phone: string | null
  status: OrgStatus
  created_at: string | null
}

export type ListSuperadminOrgsResponse = {
  orgs: SuperadminOrg[]
}

type ListOrgsOptions = {
  signal?: AbortSignal
}

export async function listOrgs(
  options: ListOrgsOptions = {},
): Promise<ListSuperadminOrgsResponse> {
  return apiFetchJson<ListSuperadminOrgsResponse>('/superadmin/orgs', {
    signal: options.signal,
  })
}

export type UpdateOrgStatusResponse = {
  org: {
    id: number
    name: string
    inn: string | null
    phone: string | null
    status: OrgStatus
  }
}

export async function updateOrgStatus(
  orgId: number,
  status: OrgStatus,
  options: ListOrgsOptions = {},
): Promise<UpdateOrgStatusResponse> {
  return apiFetchJson<UpdateOrgStatusResponse>(`/superadmin/orgs/${orgId}`, {
    method: 'PATCH',
    body: { status },
    signal: options.signal,
  })
}

export type CreateCompanyResponse = {
  id: number
  name: string
}

export async function createCompany(
  name: string,
  options: ListOrgsOptions = {},
): Promise<CreateCompanyResponse> {
  return apiFetchJson<CreateCompanyResponse>('/admin/companies', {
    method: 'POST',
    body: { name },
    signal: options.signal,
  })
}

export type CompanyInfo = {
  id: number
  name: string
  inn?: string | null
  phone?: string | null
  status?: string
  created_at?: string | null
}

export type CompanyLedgerEntry = {
  id: number
  delta: number
  reason: string
  created_at: string
}

export type GetCompanyResponse = {
  company: CompanyInfo
  balance: number
  last_ledger_entry: CompanyLedgerEntry | null
}

export async function getCompany(
  companyId: number,
  options: ListOrgsOptions = {},
): Promise<GetCompanyResponse> {
  return apiFetchJson<GetCompanyResponse>(`/admin/companies/${companyId}`, {
    signal: options.signal,
  })
}

export type InviteCompanyAdminResponse = {
  status: string
  token?: string
  link?: string
}

export async function inviteCompanyAdmin(
  companyId: number,
  email: string,
  options: ListOrgsOptions = {},
): Promise<InviteCompanyAdminResponse> {
  return apiFetchJson<InviteCompanyAdminResponse>(`/admin/companies/${companyId}/admins`, {
    method: 'POST',
    body: { email },
    signal: options.signal,
  })
}

export type AddCreditsInput = {
  amount: number
  reason: string
  idempotency_key: string
}

export type AddCreditsResponse = {
  status: string
  id?: number
}

export async function addCredits(
  companyId: number,
  payload: AddCreditsInput,
  options: ListOrgsOptions = {},
): Promise<AddCreditsResponse> {
  return apiFetchJson<AddCreditsResponse>(`/admin/companies/${companyId}/credits`, {
    method: 'POST',
    body: payload,
    signal: options.signal,
  })
}
