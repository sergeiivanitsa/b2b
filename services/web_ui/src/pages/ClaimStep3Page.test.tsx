import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { restoreClaimFromSession } from '../claims/claimRestore'
import {
  generateClaimPreview,
  getApiHttpErrorDetail,
  getInsufficientDataDetail,
  updateClaimContact,
} from '../claims/claimsApi'
import { ClaimStep3Page } from './ClaimStep3Page'

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
  getInsufficientDataDetail: vi.fn(() => null),
  updateClaimContact: vi.fn(),
}))

const mockedRestoreClaimFromSession = vi.mocked(restoreClaimFromSession)
const mockedGenerateClaimPreview = vi.mocked(generateClaimPreview)
const mockedGetApiHttpErrorDetail = vi.mocked(getApiHttpErrorDetail)
const mockedGetInsufficientDataDetail = vi.mocked(getInsufficientDataDetail)
const mockedUpdateClaimContact = vi.mocked(updateClaimContact)

const STEP3_EXPECTED_DOCUMENTS = [
  {
    id: 'pdf_claim',
    label:
      'проверенная опытным юристом и сформированная с соблюдением претензионного порядка досудебная претензия в PDF',
  },
  {
    id: 'docx_claim',
    label: 'редактируемая версия досудебной претензии в формате DOCX',
  },
  {
    id: 'cover_letter',
    label: 'сопроводительное письмо',
  },
  {
    id: 'penalty_table',
    label: 'таблица расчета неустойки',
  },
  {
    id: 'instructions',
    label: 'инструкция по дальнейшей работе с претензией',
  },
] as const

async function flushAsyncUpdates(): Promise<void> {
  await act(async () => {
    await Promise.resolve()
  })
  await act(async () => {
    await Promise.resolve()
  })
}

describe('ClaimStep3Page', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    mockedNavigate.mockReset()
    mockedRestoreClaimFromSession.mockResolvedValue({
      claimId: 12,
      editToken: 'token-1',
      claim: {
        generation_state: 'preview_ready',
        client_email: null,
        step2: {
          missing_fields: [],
        },
      },
    } as never)
    mockedUpdateClaimContact.mockResolvedValue({} as never)
    mockedGenerateClaimPreview.mockResolvedValue({} as never)
    mockedGetInsufficientDataDetail.mockReturnValue(null)
    mockedGetApiHttpErrorDetail.mockReturnValue(null)
  })

  afterEach(() => {
    cleanup()
    vi.clearAllTimers()
    vi.useRealTimers()
  })

  it('renders all step 3 documents, starts with loading status, and completes without restart on rerender', async () => {
    const { container } = render(<ClaimStep3Page />)

    expect(screen.getByText('Готовим шаг 3...')).toBeTruthy()
    expect(container.querySelectorAll('li[data-doc-id]').length).toBe(0)

    await flushAsyncUpdates()

    expect(screen.getByText('Формируем пакет документов:')).toBeTruthy()
    expect(container.querySelectorAll('li[data-doc-id]').length).toBe(5)

    for (const document of STEP3_EXPECTED_DOCUMENTS) {
      expect(screen.getByText(document.label)).toBeTruthy()
      const item = container.querySelector(
        `li[data-doc-id="${document.id}"]`,
      ) as HTMLLIElement | null
      expect(item).toBeTruthy()
      expect(item?.getAttribute('data-status')).toBe('loading')
    }

    act(() => {
      vi.advanceTimersByTime(4500)
    })

    for (const document of STEP3_EXPECTED_DOCUMENTS) {
      const item = container.querySelector(
        `li[data-doc-id="${document.id}"]`,
      ) as HTMLLIElement | null
      expect(item?.getAttribute('data-status')).toBe('done')
    }

    const emailInput = container.querySelector('input[type="email"]') as HTMLInputElement
    fireEvent.change(emailInput, { target: { value: 'qa@example.com' } })

    for (const document of STEP3_EXPECTED_DOCUMENTS) {
      const item = container.querySelector(
        `li[data-doc-id="${document.id}"]`,
      ) as HTMLLIElement | null
      expect(item?.getAttribute('data-status')).toBe('done')
    }
  })

  it('submits successfully before queue completion and keeps submit flow unchanged', async () => {
    const { container } = render(<ClaimStep3Page />)

    await flushAsyncUpdates()

    const loadingItems = container.querySelectorAll('li[data-doc-id][data-status="loading"]')
    expect(loadingItems.length).toBe(5)

    const emailInput = container.querySelector('input[type="email"]') as HTMLInputElement
    fireEvent.change(emailInput, { target: { value: 'client@example.com' } })

    const submitButton = screen.getByRole('button', {
      name: 'ПОКАЗАТЬ ГОТОВУЮ ПРЕТЕНЗИЮ',
    })
    fireEvent.click(submitButton)

    await flushAsyncUpdates()

    expect(mockedUpdateClaimContact).toHaveBeenCalledTimes(1)
    expect(mockedUpdateClaimContact).toHaveBeenCalledWith(12, 'token-1', {
      client_email: 'client@example.com',
    })
    expect(mockedGenerateClaimPreview).toHaveBeenCalledTimes(1)
    expect(mockedGenerateClaimPreview).toHaveBeenCalledWith(12, 'token-1')
    expect(mockedNavigate).toHaveBeenCalledWith('/claims/step-4')
  })
})
