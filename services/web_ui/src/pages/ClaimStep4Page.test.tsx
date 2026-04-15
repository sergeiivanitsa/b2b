import { act, cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { restoreClaimFromSession } from '../claims/claimRestore'
import {
  generateClaimPreview,
  getClaimPreview,
  getInsufficientDataDetail,
  payClaim,
} from '../claims/claimsApi'
import { ApiHttpError } from '../lib/api'
import { ClaimStep4Page } from './ClaimStep4Page'

const mockedNavigate = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockedNavigate,
  }
})

vi.mock('../claims/claimRestore', () => ({
  restoreClaimFromSession: vi.fn(),
}))

vi.mock('../claims/claimsApi', () => ({
  generateClaimPreview: vi.fn(),
  getApiHttpErrorDetail: vi.fn(() => null),
  getClaimPreview: vi.fn(),
  getInsufficientDataDetail: vi.fn(() => null),
  payClaim: vi.fn(),
}))

const mockedRestoreClaimFromSession = vi.mocked(restoreClaimFromSession)
const mockedGenerateClaimPreview = vi.mocked(generateClaimPreview)
const mockedGetClaimPreview = vi.mocked(getClaimPreview)
const mockedGetInsufficientDataDetail = vi.mocked(getInsufficientDataDetail)
const mockedPayClaim = vi.mocked(payClaim)

async function flushAsyncUpdates(): Promise<void> {
  await act(async () => {
    await Promise.resolve()
  })
  await act(async () => {
    await Promise.resolve()
  })
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ClaimStep4Page />
    </MemoryRouter>,
  )
}

describe('ClaimStep4Page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedNavigate.mockReset()
    mockedGetInsufficientDataDetail.mockReturnValue(null)
    mockedPayClaim.mockResolvedValue({} as never)
  })

  afterEach(() => {
    cleanup()
  })

  it('renders backend-provided header fields for legal entities', async () => {
    mockedRestoreClaimFromSession.mockResolvedValue({
      claimId: 12,
      editToken: 'token-1',
      claim: {
        generation_state: 'ready',
        status: 'draft',
        price_rub: 990,
        manual_review_required: false,
        client_email: 'client@example.com',
        normalized_data: {
          creditor_name: 'ООО «Альфа»',
          debtor_name: 'ООО «Вектор»',
        },
        preview_header: {
          from_party: {
            kind: 'legal_entity',
            company_name: 'ООО «Альфа»',
            position_raw: 'генеральный директор',
            person_name: 'Петров Петр Петрович',
            line1: 'Генерального директора ООО «Альфа»',
            line2: 'Петров Петр Петрович',
          },
          to_party: {
            kind: 'legal_entity',
            company_name: 'ООО «Вектор»',
            position_raw: 'директор',
            person_name: 'Иванов Иван Иванович',
            line1: 'Директору ООО «Вектор»',
            line2: 'Иванов Иван Иванович',
          },
        },
        step2: {
          missing_fields: [],
        },
      },
    } as never)
    mockedGetClaimPreview.mockResolvedValue({
      generated_preview_text: 'Текст предпросмотра',
      preview_header: {
        from_party: {
          kind: 'legal_entity',
          company_name: 'ООО «Альфа»',
          position_raw: 'генеральный директор',
          person_name: 'Петров Петр Петрович',
          line1: 'Генерального директора ООО «Альфа»',
          line2: 'Петров Петр Петрович',
        },
        to_party: {
          kind: 'legal_entity',
          company_name: 'ООО «Вектор»',
          position_raw: 'директор',
          person_name: 'Иванов Иван Иванович',
          line1: 'Директору ООО «Вектор»',
          line2: 'Иванов Иван Иванович',
        },
      },
    } as never)

    renderPage()
    await flushAsyncUpdates()

    expect(screen.getByText('Генерального директора ООО «Альфа»')).toBeTruthy()
    expect(screen.getByText('Петров Петр Петрович')).toBeTruthy()
    expect(screen.getByText('Директору ООО «Вектор»')).toBeTruthy()
    expect(screen.getByText('Иванов Иван Иванович')).toBeTruthy()
  })

  it('renders backend-provided header fields for IP', async () => {
    mockedRestoreClaimFromSession.mockResolvedValue({
      claimId: 15,
      editToken: 'token-ip',
      claim: {
        generation_state: 'ready',
        status: 'draft',
        price_rub: 990,
        manual_review_required: false,
        client_email: null,
        normalized_data: {
          creditor_name: 'ИП Петров',
          debtor_name: 'ИП Иванов',
        },
        preview_header: null,
        step2: {
          missing_fields: [],
        },
      },
    } as never)
    mockedGetClaimPreview.mockResolvedValue({
      generated_preview_text: 'Текст предпросмотра',
      preview_header: {
        from_party: {
          kind: 'individual_entrepreneur',
          company_name: 'ИП Петров',
          position_raw: null,
          person_name: 'Петров Петр Петрович',
          line1: 'Индивидуального предпринимателя',
          line2: 'Петров Петр Петрович',
        },
        to_party: {
          kind: 'individual_entrepreneur',
          company_name: 'ИП Иванов',
          position_raw: null,
          person_name: 'Иванов Иван Иванович',
          line1: 'Индивидуальному предпринимателю',
          line2: 'Иванов Иван Иванович',
        },
      },
    } as never)

    renderPage()
    await flushAsyncUpdates()

    expect(screen.getByText('Индивидуального предпринимателя')).toBeTruthy()
    expect(screen.getByText('Индивидуальному предпринимателю')).toBeTruthy()
  })

  it('falls back to legacy header rendering when backend header is absent', async () => {
    mockedRestoreClaimFromSession.mockResolvedValue({
      claimId: 16,
      editToken: 'token-fallback',
      claim: {
        generation_state: 'ready',
        status: 'draft',
        price_rub: 990,
        manual_review_required: false,
        client_email: 'client@example.com',
        normalized_data: {
          creditor_name: 'OOO Alpha',
          debtor_name: 'OOO Vector',
        },
        preview_header: null,
        step2: {
          missing_fields: [],
        },
      },
    } as never)
    mockedGetClaimPreview.mockRejectedValueOnce(new ApiHttpError(404, { detail: 'not found' }))
    mockedGenerateClaimPreview.mockResolvedValue({
      generated_preview_text: 'Текст предпросмотра',
      preview_header: null,
    } as never)

    renderPage()
    await flushAsyncUpdates()

    expect(screen.getByText('OOO Alpha')).toBeTruthy()
    expect(screen.getByText('Email: client@example.com')).toBeTruthy()
    expect(screen.getByText('OOO Vector')).toBeTruthy()
  })
})
