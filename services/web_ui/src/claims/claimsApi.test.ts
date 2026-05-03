import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiHttpError } from '../lib/api'
import {
  createClaim,
  deleteClaimFile,
  getApiHttpErrorStatus,
  generateClaimPreview,
  getApiHttpErrorDetail,
  getClaim,
  getInsufficientDataDetail,
  uploadClaimFile,
} from './claimsApi'

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

  it('POST /claims/{id}/generate-preview sends claim edit token header', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          claim_id: 12,
          generation_state: 'ready',
          manual_review_required: false,
          risk_flags: [],
          allowed_blocks: [],
          blocked_blocks: [],
          generated_preview_text: 'preview',
          missing_fields: [],
          preview_requisites: {
            outgoing_number: 'б/н',
            outgoing_date: '2026-05-03',
            outgoing_date_text: '03 мая 2026 года',
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

    const payload = await generateClaimPreview(12, 'edit-token')

    expect(payload.claim_id).toBe(12)
    expect(payload.preview_requisites?.outgoing_number).toBe('б/н')
    expect(payload.preview_requisites?.outgoing_date).toBe('2026-05-03')
    expect(payload.preview_requisites?.outgoing_date_text).toBe('03 мая 2026 года')
    expect(fetchSpy).toHaveBeenCalledTimes(1)
    const [path, options] = fetchSpy.mock.calls[0]
    expect(path).toBe('/api/claims/12/generate-preview')
    expect(options?.method).toBe('POST')

    const headers = new Headers(options?.headers)
    expect(headers.get('X-Claim-Edit-Token')).toBe('edit-token')
  })

  it('extracts insufficient_data detail fields from api errors', () => {
    const error = new ApiHttpError(409, {
      detail: {
        code: 'insufficient_data',
        missing_fields: ['debt_amount', 'payment_due_date'],
      },
    })

    const payload = getInsufficientDataDetail(error)
    expect(payload).toEqual(['debt_amount', 'payment_due_date'])
  })

  it('extracts validation detail message from structured api errors', () => {
    const error = new ApiHttpError(422, {
      detail: [
        {
          type: 'extra_forbidden',
          loc: ['body', 'normalized_data', 'creditor_inn'],
          msg: 'Extra inputs are not permitted',
        },
      ],
    })

    const detail = getApiHttpErrorDetail(error)
    expect(detail).toBe('body.normalized_data.creditor_inn: Extra inputs are not permitted')
  })

  it('extracts status code from ApiHttpError', () => {
    const error = new ApiHttpError(413, { detail: 'file is too large' })
    expect(getApiHttpErrorStatus(error)).toBe(413)
    expect(getApiHttpErrorStatus(new Error('oops'))).toBeNull()
  })

  it('POST /claims/{id}/files sends multipart body without file_role', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 7,
          filename: 'contract.pdf',
          mime_type: 'application/pdf',
          file_role: 'supporting_document',
          uploaded_at: null,
        }),
        {
          status: 200,
          headers: {
            'content-type': 'application/json',
          },
        },
      ),
    )

    const file = new File(['%PDF-1.4'], 'contract.pdf', { type: 'application/pdf' })
    const payload = await uploadClaimFile(12, 'edit-token', file)

    expect(payload.id).toBe(7)
    expect(fetchSpy).toHaveBeenCalledTimes(1)
    const [path, options] = fetchSpy.mock.calls[0]
    expect(path).toBe('/api/claims/12/files')
    expect(options?.method).toBe('POST')
    expect(options?.body).toBeInstanceOf(FormData)
    const formData = options?.body as FormData
    const uploadedFile = formData.get('file')
    expect(uploadedFile).toBeInstanceOf(File)
    expect((uploadedFile as File).name).toBe('contract.pdf')
    expect(formData.has('file_role')).toBe(false)
  })

  it('DELETE /claims/{id}/files/{fileId} sends claim edit token header', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(null, { status: 204 }),
    )

    await deleteClaimFile(12, 'edit-token', 42)

    expect(fetchSpy).toHaveBeenCalledTimes(1)
    const [path, options] = fetchSpy.mock.calls[0]
    expect(path).toBe('/api/claims/12/files/42')
    expect(options?.method).toBe('DELETE')
    const headers = new Headers(options?.headers)
    expect(headers.get('X-Claim-Edit-Token')).toBe('edit-token')
  })
})
