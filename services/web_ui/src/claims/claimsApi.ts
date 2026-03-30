import { apiFetchJson } from '../lib/api'

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

export type PublicClaimSnapshot = {
  id: number
  status: string
  generation_state: string
  manual_review_required: boolean
  price_rub: number
  input_text: string
  client_email: string | null
  client_phone: string | null
  case_type: string | null
  normalized_data: Record<string, unknown> | null
  step2: PublicClaimStep2
  created_at: string | null
  updated_at: string | null
  paid_at: string | null
  reviewed_at: string | null
  sent_at: string | null
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
