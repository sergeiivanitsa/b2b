import { apiFetchJson } from '../lib/api'
import type {
  AdminClaimDetails,
  AdminClaimFile,
  AdminClaimsListResponse,
} from './types'

export type AdminClaimsListParams = {
  status?: string
  generation_state?: string
  limit?: number
  offset?: number
}

export async function fetchAdminClaims(
  params: AdminClaimsListParams = {},
): Promise<AdminClaimsListResponse> {
  const query = new URLSearchParams()

  const normalizedStatus = params.status?.trim()
  if (normalizedStatus) {
    query.set('status', normalizedStatus)
  }
  const normalizedGenerationState = params.generation_state?.trim()
  if (normalizedGenerationState) {
    query.set('generation_state', normalizedGenerationState)
  }

  const limit = normalizeOptionalPositiveInt(params.limit)
  const offset = normalizeOptionalNonNegativeInt(params.offset)
  if (limit !== null) {
    query.set('limit', String(limit))
  }
  if (offset !== null) {
    query.set('offset', String(offset))
  }

  const suffix = query.size ? `?${query.toString()}` : ''
  return apiFetchJson<AdminClaimsListResponse>(`/admin/claims${suffix}`)
}

export async function fetchAdminClaim(claimId: number): Promise<AdminClaimDetails> {
  return apiFetchJson<AdminClaimDetails>(`/admin/claims/${normalizeClaimId(claimId)}`)
}

export async function updateAdminClaimStatus(
  claimId: number,
  status: string,
): Promise<AdminClaimDetails> {
  const normalizedStatus = status.trim()
  if (!normalizedStatus) {
    throw new Error('status is required')
  }

  return apiFetchJson<AdminClaimDetails>(`/admin/claims/${normalizeClaimId(claimId)}/status`, {
    method: 'POST',
    body: {
      status: normalizedStatus,
    },
  })
}

export async function updateAdminClaimFinalText(
  claimId: number,
  finalText: string,
): Promise<AdminClaimDetails> {
  const normalizedText = finalText.trim()
  if (!normalizedText) {
    throw new Error('final_text is required')
  }

  return apiFetchJson<AdminClaimDetails>(`/admin/claims/${normalizeClaimId(claimId)}/final-text`, {
    method: 'POST',
    body: {
      final_text: normalizedText,
    },
  })
}

export async function sendAdminClaimFinalResult(
  claimId: number,
): Promise<AdminClaimDetails> {
  return apiFetchJson<AdminClaimDetails>(`/admin/claims/${normalizeClaimId(claimId)}/send`, {
    method: 'POST',
  })
}

export async function fetchAdminClaimFiles(claimId: number): Promise<AdminClaimFile[]> {
  return apiFetchJson<AdminClaimFile[]>(`/admin/claims/${normalizeClaimId(claimId)}/files`)
}

function normalizeClaimId(value: number): number {
  if (!Number.isInteger(value) || value <= 0) {
    throw new Error('claimId must be a positive integer')
  }
  return value
}

function normalizeOptionalPositiveInt(value: number | undefined): number | null {
  if (value === undefined) {
    return null
  }
  if (!Number.isInteger(value) || value <= 0) {
    throw new Error('limit must be a positive integer')
  }
  return value
}

function normalizeOptionalNonNegativeInt(value: number | undefined): number | null {
  if (value === undefined) {
    return null
  }
  if (!Number.isInteger(value) || value < 0) {
    throw new Error('offset must be a non-negative integer')
  }
  return value
}

