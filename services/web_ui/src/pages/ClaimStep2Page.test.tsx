import { cleanup, fireEvent, render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { restoreClaimFromSession } from '../claims/claimRestore'
import { deleteClaimFile, listClaimFiles, uploadClaimFile } from '../claims/claimsApi'
import { ClaimStep2Page } from './ClaimStep2Page'

vi.mock('../claims/claimRestore', () => ({
  restoreClaimFromSession: vi.fn(),
}))

vi.mock('../claims/claimsApi', () => ({
  deleteClaimFile: vi.fn(),
  listClaimFiles: vi.fn(),
  patchClaim: vi.fn(),
  uploadClaimFile: vi.fn(),
  getApiHttpErrorDetail: vi.fn(() => null),
}))

const mockedRestoreClaimFromSession = vi.mocked(restoreClaimFromSession)
const mockedDeleteClaimFile = vi.mocked(deleteClaimFile)
const mockedListClaimFiles = vi.mocked(listClaimFiles)
const mockedUploadClaimFile = vi.mocked(uploadClaimFile)

describe('ClaimStep2Page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedRestoreClaimFromSession.mockResolvedValue({
      claimId: 12,
      editToken: 'token-1',
      claim: {
        case_type: 'supply',
        normalized_data: {
          creditor_name: 'OOO Romashka',
          creditor_inn: '2721245963',
          debtor_name: 'OOO Vector',
          debtor_inn: '1834049911',
          contract_signed: true,
          contract_number: '17',
          contract_date: '2026-01-12',
          debt_amount: 380000,
          payment_due_date: '2026-03-12',
          partial_payments_present: false,
          partial_payments: [],
          penalty_exists: false,
          penalty_rate_text: null,
          documents_mentioned: [],
          missing_fields: [],
        },
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
      },
    } as never)
    mockedDeleteClaimFile.mockResolvedValue(undefined)
    mockedListClaimFiles.mockResolvedValue([])
    mockedUploadClaimFile.mockResolvedValue({
      id: 700,
      filename: 'contract.pdf',
      mime_type: 'application/pdf',
      file_role: 'supporting_document',
      uploaded_at: null,
    })
  })

  afterEach(() => {
    cleanup()
  })

  it('renders only one creditor INN field and one debtor INN field', async () => {
    const { container } = render(
      <MemoryRouter>
        <ClaimStep2Page />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(container.querySelectorAll('input#creditor-inn')).toHaveLength(1)
      expect(container.querySelectorAll('input#debtor-inn')).toHaveLength(1)
    })
  })

  it('starts upload immediately after file selection', async () => {
    const { container } = render(
      <MemoryRouter>
        <ClaimStep2Page />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(mockedListClaimFiles).toHaveBeenCalledWith(12, 'token-1')
    })

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement | null
    expect(fileInput).toBeTruthy()
    expect(fileInput?.multiple).toBe(true)
    expect(fileInput?.accept).toContain('.pdf')

    const file = new File(['%PDF-1.4'], 'contract.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput!, { target: { files: [file] } })

    await waitFor(() => {
      expect(mockedUploadClaimFile).toHaveBeenCalledTimes(1)
      expect(mockedUploadClaimFile).toHaveBeenCalledWith(12, 'token-1', file)
    })
  })

  it('deletes uploaded file from the list', async () => {
    mockedListClaimFiles
      .mockResolvedValueOnce([
        {
          id: 501,
          filename: 'contract.pdf',
          mime_type: 'application/pdf',
          file_role: 'supporting_document',
          uploaded_at: null,
        },
      ])
      .mockResolvedValueOnce([])

    const { container } = render(
      <MemoryRouter>
        <ClaimStep2Page />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(container.querySelectorAll('.claims-file-upload__list li')).toHaveLength(1)
    })

    const removeButton = container.querySelector('.claims-file-upload__remove') as HTMLButtonElement | null
    expect(removeButton).toBeTruthy()
    fireEvent.click(removeButton!)

    await waitFor(() => {
      expect(mockedDeleteClaimFile).toHaveBeenCalledWith(12, 'token-1', 501)
    })
  })
})