import { cleanup, render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { restoreClaimFromSession } from '../claims/claimRestore'
import { listClaimFiles } from '../claims/claimsApi'
import { ClaimStep2Page } from './ClaimStep2Page'

vi.mock('../claims/claimRestore', () => ({
  restoreClaimFromSession: vi.fn(),
}))

vi.mock('../claims/claimsApi', () => ({
  listClaimFiles: vi.fn(),
  patchClaim: vi.fn(),
  uploadClaimFile: vi.fn(),
  getApiHttpErrorDetail: vi.fn(() => null),
}))

const mockedRestoreClaimFromSession = vi.mocked(restoreClaimFromSession)
const mockedListClaimFiles = vi.mocked(listClaimFiles)

describe('ClaimStep2Page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedRestoreClaimFromSession.mockResolvedValue({
      claimId: 12,
      editToken: 'token-1',
      claim: {
        case_type: 'supply',
        normalized_data: {
          creditor_name: 'ООО Ромашка',
          creditor_inn: '2721245963',
          debtor_name: 'ООО Вектор',
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
    mockedListClaimFiles.mockResolvedValue([])
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
})
