import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  fetchAdminClaim,
  fetchAdminClaims,
  fetchAdminClaimFiles,
  sendAdminClaimFinalResult,
  updateAdminClaimFinalText,
  updateAdminClaimStatus,
} from './adminClaimsApi'

describe('adminClaimsApi', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('GET /admin/claims serializes query params', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ items: [] }),
        {
          status: 200,
          headers: { 'content-type': 'application/json' },
        },
      ),
    )

    await fetchAdminClaims({
      status: 'paid',
      generation_state: 'manual_review_required',
      limit: 20,
      offset: 10,
    })

    const [path] = fetchSpy.mock.calls[0]
    expect(path).toBe(
      '/api/admin/claims?status=paid&generation_state=manual_review_required&limit=20&offset=10',
    )
  })

  it('GET /admin/claims/{id}', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 4,
          status: 'paid',
          generation_state: 'ready',
          manual_review_required: false,
          price_rub: 990,
          input_text: 'text',
          client_email: 'client@example.com',
          client_phone: null,
          case_type: 'supply',
          normalized_data: null,
          step2: {
            always_visible_fields: [],
            conditional_visibility: {
              show_partial_payments: false,
              show_penalty_rate: false,
            },
            missing_fields: [],
            derived: {
              total_paid_amount: 0,
              remaining_debt_amount: 1,
              overdue_days: 2,
              is_overdue: true,
            },
          },
          risk_flags: [],
          allowed_blocks: [],
          blocked_blocks: [],
          generation_notes: null,
          generated_preview_text: '',
          generated_full_text: '',
          final_text: '',
          summary_for_admin: null,
          review_comment: null,
          created_at: null,
          updated_at: null,
          paid_at: null,
          reviewed_at: null,
          sent_at: null,
        }),
        {
          status: 200,
          headers: { 'content-type': 'application/json' },
        },
      ),
    )

    const payload = await fetchAdminClaim(4)

    expect(payload.id).toBe(4)
    const [path] = fetchSpy.mock.calls[0]
    expect(path).toBe('/api/admin/claims/4')
  })

  it('POST /admin/claims/{id}/status', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 8,
          status: 'in_review',
          generation_state: 'ready',
          manual_review_required: false,
          price_rub: 990,
          input_text: '',
          client_email: null,
          client_phone: null,
          case_type: null,
          normalized_data: null,
          step2: {
            always_visible_fields: [],
            conditional_visibility: {
              show_partial_payments: false,
              show_penalty_rate: false,
            },
            missing_fields: [],
            derived: {
              total_paid_amount: 0,
              remaining_debt_amount: null,
              overdue_days: null,
              is_overdue: null,
            },
          },
          risk_flags: [],
          allowed_blocks: [],
          blocked_blocks: [],
          generation_notes: null,
          generated_preview_text: '',
          generated_full_text: '',
          final_text: '',
          summary_for_admin: null,
          review_comment: null,
          created_at: null,
          updated_at: null,
          paid_at: null,
          reviewed_at: null,
          sent_at: null,
        }),
        {
          status: 200,
          headers: { 'content-type': 'application/json' },
        },
      ),
    )

    const payload = await updateAdminClaimStatus(8, 'in_review')

    expect(payload.status).toBe('in_review')
    const [path, options] = fetchSpy.mock.calls[0]
    expect(path).toBe('/api/admin/claims/8/status')
    expect(options?.method).toBe('POST')
    expect(options?.body).toBe(JSON.stringify({ status: 'in_review' }))
  })

  it('POST /admin/claims/{id}/final-text', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 8,
          status: 'in_review',
          generation_state: 'ready',
          manual_review_required: false,
          price_rub: 990,
          input_text: '',
          client_email: null,
          client_phone: null,
          case_type: null,
          normalized_data: null,
          step2: {
            always_visible_fields: [],
            conditional_visibility: {
              show_partial_payments: false,
              show_penalty_rate: false,
            },
            missing_fields: [],
            derived: {
              total_paid_amount: 0,
              remaining_debt_amount: null,
              overdue_days: null,
              is_overdue: null,
            },
          },
          risk_flags: [],
          allowed_blocks: [],
          blocked_blocks: [],
          generation_notes: null,
          generated_preview_text: '',
          generated_full_text: '',
          final_text: 'final',
          summary_for_admin: null,
          review_comment: null,
          created_at: null,
          updated_at: null,
          paid_at: null,
          reviewed_at: null,
          sent_at: null,
        }),
        {
          status: 200,
          headers: { 'content-type': 'application/json' },
        },
      ),
    )

    const payload = await updateAdminClaimFinalText(8, ' final ')

    expect(payload.final_text).toBe('final')
    const [path, options] = fetchSpy.mock.calls[0]
    expect(path).toBe('/api/admin/claims/8/final-text')
    expect(options?.body).toBe(JSON.stringify({ final_text: 'final' }))
  })

  it('POST /admin/claims/{id}/send and GET files endpoints', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: 8,
            status: 'sent',
            generation_state: 'ready',
            manual_review_required: false,
            price_rub: 990,
            input_text: '',
            client_email: null,
            client_phone: null,
            case_type: null,
            normalized_data: null,
            step2: {
              always_visible_fields: [],
              conditional_visibility: {
                show_partial_payments: false,
                show_penalty_rate: false,
              },
              missing_fields: [],
              derived: {
                total_paid_amount: 0,
                remaining_debt_amount: null,
                overdue_days: null,
                is_overdue: null,
              },
            },
            risk_flags: [],
            allowed_blocks: [],
            blocked_blocks: [],
            generation_notes: null,
            generated_preview_text: '',
            generated_full_text: '',
            final_text: 'final',
            summary_for_admin: null,
            review_comment: null,
            created_at: null,
            updated_at: null,
            paid_at: null,
            reviewed_at: null,
            sent_at: null,
          }),
          {
            status: 200,
            headers: { 'content-type': 'application/json' },
          },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify([
            {
              id: 1,
              filename: 'file.pdf',
              mime_type: 'application/pdf',
              file_role: 'contract',
              uploaded_at: null,
            },
          ]),
          {
            status: 200,
            headers: { 'content-type': 'application/json' },
          },
        ),
      )

    const sendPayload = await sendAdminClaimFinalResult(8)
    const filesPayload = await fetchAdminClaimFiles(8)

    expect(sendPayload.status).toBe('sent')
    expect(filesPayload).toHaveLength(1)
    expect(fetchSpy.mock.calls[0][0]).toBe('/api/admin/claims/8/send')
    expect(fetchSpy.mock.calls[1][0]).toBe('/api/admin/claims/8/files')
  })

  it('validates claimId', async () => {
    await expect(fetchAdminClaim(0)).rejects.toThrow('claimId must be a positive integer')
  })
})

