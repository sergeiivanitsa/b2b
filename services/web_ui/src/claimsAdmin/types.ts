export type ClaimsAdminAuthStatus = 'loading' | 'anonymous' | 'authenticated' | 'forbidden'

export type AdminAuthStatusResponse = {
  status: string
}

export type AdminClaimsListItem = {
  id: number
  status: string
  generation_state: string
  manual_review_required: boolean
  case_type: string | null
  client_email: string | null
  price_rub: number
  has_final_text: boolean
  created_at: string | null
  updated_at: string | null
  paid_at: string | null
  reviewed_at: string | null
  sent_at: string | null
}

export type AdminClaimsListResponse = {
  items: AdminClaimsListItem[]
}

export type Step2Contract = {
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

export type AdminClaimDetails = {
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
  step2: Step2Contract
  risk_flags: string[]
  allowed_blocks: string[]
  blocked_blocks: string[]
  generation_notes: Record<string, unknown> | null
  generated_preview_text: string
  generated_full_text: string
  final_text: string
  summary_for_admin: string | null
  review_comment: string | null
  created_at: string | null
  updated_at: string | null
  paid_at: string | null
  reviewed_at: string | null
  sent_at: string | null
}

export type AdminClaimFile = {
  id: number
  filename: string
  mime_type: string
  file_role: string
  uploaded_at: string | null
}

