import { ApiHttpError, apiFetchJson } from '../lib/api'

export type PublicClaimStep2 = {
  always_visible_fields: string[]
  conditional_visibility: {
    show_partial_payments: boolean
    show_penalty_rate: boolean
  }
  missing_fields: string[]
  derived: {
    total_paid_amount: number
    remaining_debt_amount: number | null
    overdue_days: number | null
    is_overdue: boolean | null
  }
}

export type ClaimCaseType = 'supply' | 'contract_work' | 'services'

export type ClaimNormalizedPartialPayment = {
  amount: number | string | null
  date: string | null
}

export type ClaimNormalizedData = {
  creditor_name: string | null
  creditor_inn: string | null
  debtor_name: string | null
  debtor_inn: string | null
  contract_signed: boolean | null
  contract_number: string | null
  contract_date: string | null
  debt_amount: number | string | null
  payment_due_date: string | null
  partial_payments_present: boolean | null
  partial_payments: ClaimNormalizedPartialPayment[]
  penalty_exists: boolean | null
  penalty_rate_text: string | null
  documents_mentioned: string[]
  missing_fields?: string[]
}

export type ClaimPreviewHeaderParty = {
  kind: string
  company_name: string | null
  position_raw: string | null
  person_name: string | null
  line1: string
  line2: string | null
  rendered?: ClaimPreviewHeaderRendered | null
}

export type ClaimPreviewHeaderRendered = {
  line1: string
  line2: string | null
  line3: string | null
}

export type ClaimPreviewHeader = {
  format_version?: number
  from_party: ClaimPreviewHeaderParty
  to_party: ClaimPreviewHeaderParty
}

export type ClaimPreviewRequisites = {
  outgoing_number: string
  outgoing_date: string
  outgoing_date_text: string
}

export type PublicClaimSnapshot = {
  id: number
  status: string
  generation_state: string
  manual_review_required: boolean
  price_rub: number
  input_text: string
  client_email: string | null
  case_type: ClaimCaseType | null
  normalized_data: ClaimNormalizedData | null
  preview_header?: ClaimPreviewHeader | null
  step2: PublicClaimStep2
  created_at: string | null
  updated_at: string | null
  paid_at: string | null
  reviewed_at: string | null
  sent_at: string | null
}

export type ClaimPreviewSnapshot = {
  claim_id: number
  generation_state: string
  manual_review_required: boolean
  risk_flags: string[]
  allowed_blocks: string[]
  blocked_blocks: string[]
  generated_preview_text: string
  missing_fields: string[]
  preview_header?: ClaimPreviewHeader | null
  preview_requisites?: ClaimPreviewRequisites
}

export type ClaimFileSnapshot = {
  id: number
  filename: string
  mime_type: string
  file_role: string
  uploaded_at: string | null
}

export type ClaimPatchInput = {
  case_type?: ClaimCaseType | null
  client_email?: string | null
  normalized_data?: Partial<ClaimNormalizedData>
}

export type ClaimContactInput = {
  client_email: string
}

type DetailPayload = {
  code?: string
  missing_fields?: unknown
}

export type CreateClaimResponse = {
  claim_id: number
  edit_token: string
  claim: PublicClaimSnapshot
}

export async function createClaim(inputText: string): Promise<CreateClaimResponse> {
  const normalizedInputText = inputText.trim()
  if (!normalizedInputText) {
    throw new Error('inputText is required')
  }

  return apiFetchJson<CreateClaimResponse>('/claims', {
    method: 'POST',
    body: {
      input_text: normalizedInputText,
    },
  })
}

export async function getClaim(claimId: number, editToken: string): Promise<PublicClaimSnapshot> {
  if (!Number.isInteger(claimId) || claimId <= 0) {
    throw new Error('claimId must be a positive integer')
  }

  const normalizedToken = editToken.trim()
  if (!normalizedToken) {
    throw new Error('editToken is required')
  }

  return apiFetchJson<PublicClaimSnapshot>(`/claims/${claimId}`, {
    headers: {
      'X-Claim-Edit-Token': normalizedToken,
    },
  })
}

export async function extractClaim(
  claimId: number,
  editToken: string,
): Promise<PublicClaimSnapshot> {
  return apiFetchJson<PublicClaimSnapshot>(`/claims/${normalizeClaimId(claimId)}/extract`, {
    method: 'POST',
    headers: withClaimTokenHeader(editToken),
  })
}

export async function patchClaim(
  claimId: number,
  editToken: string,
  payload: ClaimPatchInput,
): Promise<PublicClaimSnapshot> {
  return apiFetchJson<PublicClaimSnapshot>(`/claims/${normalizeClaimId(claimId)}`, {
    method: 'PATCH',
    headers: withClaimTokenHeader(editToken),
    body: payload,
  })
}

export async function uploadClaimFile(
  claimId: number,
  editToken: string,
  file: File,
): Promise<ClaimFileSnapshot> {
  if (!file) {
    throw new Error('file is required')
  }

  const formData = new FormData()
  formData.set('file', file)

  return apiFetchJson<ClaimFileSnapshot>(`/claims/${normalizeClaimId(claimId)}/files`, {
    method: 'POST',
    headers: withClaimTokenHeader(editToken),
    body: formData,
  })
}

export async function listClaimFiles(
  claimId: number,
  editToken: string,
): Promise<ClaimFileSnapshot[]> {
  return apiFetchJson<ClaimFileSnapshot[]>(`/claims/${normalizeClaimId(claimId)}/files`, {
    headers: withClaimTokenHeader(editToken),
  })
}

export async function deleteClaimFile(
  claimId: number,
  editToken: string,
  fileId: number,
): Promise<void> {
  if (!Number.isInteger(fileId) || fileId <= 0) {
    throw new Error('fileId must be a positive integer')
  }

  await apiFetchJson<void>(`/claims/${normalizeClaimId(claimId)}/files/${fileId}`, {
    method: 'DELETE',
    headers: withClaimTokenHeader(editToken),
  })
}

export async function updateClaimContact(
  claimId: number,
  editToken: string,
  payload: ClaimContactInput,
): Promise<PublicClaimSnapshot> {
  return apiFetchJson<PublicClaimSnapshot>(`/claims/${normalizeClaimId(claimId)}/contact`, {
    method: 'POST',
    headers: withClaimTokenHeader(editToken),
    body: payload,
  })
}

export async function generateClaimPreview(
  claimId: number,
  editToken: string,
): Promise<ClaimPreviewSnapshot> {
  return apiFetchJson<ClaimPreviewSnapshot>(`/claims/${normalizeClaimId(claimId)}/generate-preview`, {
    method: 'POST',
    headers: withClaimTokenHeader(editToken),
  })
}

export async function getClaimPreview(
  claimId: number,
  editToken: string,
): Promise<ClaimPreviewSnapshot> {
  return apiFetchJson<ClaimPreviewSnapshot>(`/claims/${normalizeClaimId(claimId)}/preview`, {
    headers: withClaimTokenHeader(editToken),
  })
}

export async function payClaim(
  claimId: number,
  editToken: string,
): Promise<PublicClaimSnapshot> {
  return apiFetchJson<PublicClaimSnapshot>(`/claims/${normalizeClaimId(claimId)}/pay`, {
    method: 'POST',
    headers: withClaimTokenHeader(editToken),
  })
}

export function getInsufficientDataDetail(error: unknown): string[] | null {
  if (!(error instanceof ApiHttpError) || error.status !== 409) {
    return null
  }

  const detail = unwrapErrorDetail(error.payload)
  if (typeof detail === 'string') {
    return detail === 'insufficient_data' ? [] : null
  }
  if (!detail || typeof detail !== 'object') {
    return null
  }

  const payload = detail as DetailPayload
  if (payload.code !== 'insufficient_data') {
    return null
  }
  if (!Array.isArray(payload.missing_fields)) {
    return []
  }

  return payload.missing_fields.filter((item): item is string => typeof item === 'string')
}

export function getApiHttpErrorDetail(error: unknown): string | null {
  if (!(error instanceof ApiHttpError)) {
    return null
  }
  const detail = unwrapErrorDetail(error.payload)
  if (typeof detail === 'string') {
    return detail
  }
  if (Array.isArray(detail)) {
    const firstValidationItem = detail.find(
      (item): item is { msg?: unknown; loc?: unknown } =>
        Boolean(item) && typeof item === 'object',
    )
    if (!firstValidationItem) {
      return null
    }

    const message =
      typeof firstValidationItem.msg === 'string'
        ? firstValidationItem.msg
        : null
    const location =
      Array.isArray(firstValidationItem.loc)
        ? firstValidationItem.loc.filter((part): part is string => typeof part === 'string')
        : []

    if (message && location.length > 0) {
      return `${location.join('.')}: ${message}`
    }
    if (message) {
      return message
    }
  }
  if (detail && typeof detail === 'object') {
    const payload = detail as Record<string, unknown>
    if (typeof payload.message === 'string') {
      return payload.message
    }
    if (typeof payload.error === 'string') {
      return payload.error
    }
    if (typeof payload.code === 'string') {
      return payload.code
    }
  }
  return null
}

export function getApiHttpErrorStatus(error: unknown): number | null {
  if (!(error instanceof ApiHttpError)) {
    return null
  }
  return error.status
}

function normalizeClaimId(value: number): number {
  if (!Number.isInteger(value) || value <= 0) {
    throw new Error('claimId must be a positive integer')
  }
  return value
}

function withClaimTokenHeader(editToken: string): HeadersInit {
  const normalizedToken = editToken.trim()
  if (!normalizedToken) {
    throw new Error('editToken is required')
  }
  return {
    'X-Claim-Edit-Token': normalizedToken,
  }
}

function unwrapErrorDetail(payload: unknown): unknown {
  if (!payload || typeof payload !== 'object') {
    return payload
  }
  if (!('detail' in payload)) {
    return payload
  }
  return (payload as { detail: unknown }).detail
}
