import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createClaim, getClaim } from './claimsApi'

describe('claimsApi', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('POST /claims uses normalized input_text', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          claim_id: 12,
          edit_token: 'token-1',
          claim: {
            id: 12,
            status: 'draft',
            generation_state: 'insufficient_data',
            manual_review_required: false,
            price_rub: 990,
            input_text: 'Text',
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
            created_at: null,
            updated_at: null,
            paid_at: null,
            reviewed_at: null,
            sent_at: null,
          },
        }),
        {
          status: 200,
          headers: {
            'content-type': 'application/json',
          },
        },
      ),
    )

    const payload = await createClaim('  Text  ')

    expect(payload.claim_id).toBe(12)
    expect(fetchSpy).toHaveBeenCalledTimes(1)
    const [path, options] = fetchSpy.mock.calls[0]
    expect(path).toBe('/api/claims')
    expect(options?.method).toBe('POST')
    expect(options?.credentials).toBe('include')
    expect(options?.body).toBe(JSON.stringify({ input_text: 'Text' }))
  })

  it('GET /claims/{id} sends claim edit token header', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 12,
          status: 'draft',
          generation_state: 'insufficient_data',
          manual_review_required: false,
          price_rub: 990,
          input_text: 'Text',
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
          created_at: null,
          updated_at: null,
          paid_at: null,
          reviewed_at: null,
          sent_at: null,
        }),
        {
          status: 200,
          headers: {
            'content-type': 'application/json',
          },
        },
      ),
    )

    const payload = await getClaim(12, 'edit-token')

    expect(payload.id).toBe(12)
    expect(fetchSpy).toHaveBeenCalledTimes(1)
    const [path, options] = fetchSpy.mock.calls[0]
    expect(path).toBe('/api/claims/12')

    const headers = new Headers(options?.headers)
    expect(headers.get('X-Claim-Edit-Token')).toBe('edit-token')
  })

  it('validates empty create payload', async () => {
    await expect(createClaim('   ')).rejects.toThrow('inputText is required')
  })

  it('validates token for getClaim', async () => {
    await expect(getClaim(0, 'token')).rejects.toThrow('claimId must be a positive integer')
    await expect(getClaim(1, '   ')).rejects.toThrow('editToken is required')
  })
})
