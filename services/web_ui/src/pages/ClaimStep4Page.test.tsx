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

const CLAIMS_DOCUMENT_DEMO_TEXT =
  'Полная версия документа будет доступна после оплаты. В неё входят правовое обоснование, расчет требований и итоговая просительная часть.'

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

function getHeaderParties(container: HTMLElement): {
  sender: HTMLElement
  recipient: HTMLElement
} {
  const parties = container.querySelectorAll<HTMLElement>(
    '.claims-document-header .claims-document-party',
  )
  if (parties.length !== 2) {
    throw new Error(`Expected exactly 2 header parties, got ${parties.length}`)
  }
  return { sender: parties[0], recipient: parties[1] }
}

function getPartyLine(
  party: HTMLElement,
  line: 'line1' | 'line2' | 'line3',
): string | null {
  const lineNode = party.querySelector<HTMLElement>(
    `.claims-document-party__line--${line}`,
  )
  return lineNode ? lineNode.textContent?.trim() ?? null : null
}

function getDocumentBody(container: HTMLElement): HTMLElement {
  const body = container.querySelector<HTMLElement>('.claims-document-body')
  if (!body) {
    throw new Error('Expected document body to be rendered')
  }
  return body
}

function getDocumentDemo(container: HTMLElement): HTMLElement {
  const demo = container.querySelector<HTMLElement>('.claims-document-demo')
  if (!demo) {
    throw new Error('Expected document demo zone to be rendered')
  }
  return demo
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

  it('renders full v2 rendered header as three lines per side and removes labels', async () => {
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
          creditor_name: 'Fallback Creditor',
          debtor_name: 'Fallback Debtor',
        },
        preview_header: {
          from_party: {
            kind: 'legal_entity',
            company_name: 'Legacy Sender Org',
            position_raw: 'general director',
            person_name: 'Legacy Sender Person',
            line1: 'Legacy Sender Line 1',
            line2: 'Legacy Sender Line 2',
          },
          to_party: {
            kind: 'legal_entity',
            company_name: 'Legacy Recipient Org',
            position_raw: 'director',
            person_name: 'Legacy Recipient Person',
            line1: 'Legacy Recipient Line 1',
            line2: 'Legacy Recipient Line 2',
          },
        },
        step2: {
          missing_fields: [],
        },
      },
    } as never)
    mockedGetClaimPreview.mockResolvedValue({
      generated_preview_text: 'Preview text',
      preview_requisites: {
        outgoing_number: 'б/н',
        outgoing_date: '2026-05-03',
        outgoing_date_text: '03 мая 2026 года',
      },
      preview_header: {
        format_version: 2,
        from_party: {
          kind: 'legal_entity',
          company_name: 'Sender Org',
          position_raw: 'general director',
          person_name: 'Sender Person',
          line1: 'Legacy Sender Line 1',
          line2: 'Legacy Sender Line 2',
          rendered: {
            line1: 'Rendered Sender Line 1',
            line2: 'Rendered Sender Org',
            line3: 'Rendered Sender Person',
          },
        },
        to_party: {
          kind: 'legal_entity',
          company_name: 'Recipient Org',
          position_raw: 'director',
          person_name: 'Recipient Person',
          line1: 'Legacy Recipient Line 1',
          line2: 'Legacy Recipient Line 2',
          rendered: {
            line1: 'Rendered Recipient Line 1',
            line2: 'Rendered Recipient Org',
            line3: 'Rendered Recipient Person',
          },
        },
      },
    } as never)

    const { container } = renderPage()
    await flushAsyncUpdates()

    const { sender, recipient } = getHeaderParties(container)
    expect(getPartyLine(sender, 'line1')).toBe('Rendered Sender Line 1')
    expect(getPartyLine(sender, 'line2')).toBe('Rendered Sender Org')
    expect(getPartyLine(sender, 'line3')).toBe('Rendered Sender Person')
    expect(getPartyLine(recipient, 'line1')).toBe('Rendered Recipient Line 1')
    expect(getPartyLine(recipient, 'line2')).toBe('Rendered Recipient Org')
    expect(getPartyLine(recipient, 'line3')).toBe('Rendered Recipient Person')
    expect(
      screen.getByRole('heading', { name: 'ПРЕТЕНЗИЯ' }).classList.contains(
        'claims-document-title',
      ),
    ).toBe(true)
    const requisites = screen.getByText('Исх. №: б/н от 03 мая 2026 года')
    expect(requisites.classList.contains('claims-document-requisites')).toBe(true)
    const body = getDocumentBody(container)
    expect(body.textContent).toContain('Preview text')
    expect(body.textContent).not.toContain('Исх. №')
    expect(body.textContent).not.toContain(CLAIMS_DOCUMENT_DEMO_TEXT)
    expect(body.querySelectorAll('p')).toHaveLength(1)
    const demo = getDocumentDemo(container)
    expect(demo.textContent).toContain(CLAIMS_DOCUMENT_DEMO_TEXT)
    expect(demo.closest('.claims-document-body')).toBeNull()
    expect(container.querySelector('.claims-document-header')).not.toBeNull()
    expect(container.querySelector('.claims-document-paywall')).not.toBeNull()
    expect(container.querySelector('.claims-paywall-card')).not.toBeNull()
    expect(screen.queryByText('ОТ КОГО:')).toBeNull()
    expect(screen.queryByText('КОМУ:')).toBeNull()
    expect(screen.queryByText('Legacy Sender Line 1')).toBeNull()
    expect(screen.queryByText('Legacy Recipient Line 1')).toBeNull()
  })

  it('renders preview body paragraphs separately from the frontend demo zone', async () => {
    mockedRestoreClaimFromSession.mockResolvedValue({
      claimId: 22,
      editToken: 'token-body-demo',
      claim: {
        generation_state: 'ready',
        status: 'draft',
        price_rub: 990,
        manual_review_required: false,
        client_email: null,
        normalized_data: {
          creditor_name: 'Fallback Creditor',
          debtor_name: 'Fallback Debtor',
        },
        preview_header: null,
        step2: {
          missing_fields: [],
        },
      },
    } as never)
    mockedGetClaimPreview.mockResolvedValue({
      generated_preview_text: 'Первый абзац preview body.\n\nВторой абзац preview body.',
      preview_requisites: {
        outgoing_number: 'б/н',
        outgoing_date: '2026-05-03',
        outgoing_date_text: '03 мая 2026 года',
      },
      preview_header: null,
    } as never)

    const { container } = renderPage()
    await flushAsyncUpdates()

    const body = getDocumentBody(container)
    const bodyParagraphs = Array.from(body.querySelectorAll('p')).map((node) =>
      node.textContent?.trim(),
    )
    expect(bodyParagraphs).toEqual([
      'Первый абзац preview body.',
      'Второй абзац preview body.',
    ])
    expect(body.textContent).not.toContain(CLAIMS_DOCUMENT_DEMO_TEXT)

    const demo = getDocumentDemo(container)
    expect(demo.textContent).toContain(CLAIMS_DOCUMENT_DEMO_TEXT)
    expect(demo.closest('.claims-document-body')).toBeNull()
    expect(screen.getByRole('heading', { name: 'ПРЕТЕНЗИЯ' })).toBeTruthy()
    expect(screen.getByText('Исх. №: б/н от 03 мая 2026 года')).toBeTruthy()
  })

  it('does not render extra preview paragraphs under the paywall blur', async () => {
    mockedRestoreClaimFromSession.mockResolvedValue({
      claimId: 23,
      editToken: 'token-extra-paragraph',
      claim: {
        generation_state: 'ready',
        status: 'draft',
        price_rub: 990,
        manual_review_required: false,
        client_email: null,
        normalized_data: {
          creditor_name: 'Fallback Creditor',
          debtor_name: 'Fallback Debtor',
        },
        preview_header: null,
        step2: {
          missing_fields: [],
        },
      },
    } as never)
    mockedGetClaimPreview.mockResolvedValue({
      generated_preview_text:
        'Первый абзац preview body.\n\nВторой абзац preview body.\n\nТретий абзац не должен отображаться.',
      preview_header: null,
    } as never)

    const { container } = renderPage()
    await flushAsyncUpdates()

    const body = getDocumentBody(container)
    expect(body.querySelectorAll('p')).toHaveLength(2)
    expect(body.textContent).toContain('Первый абзац preview body.')
    expect(body.textContent).toContain('Второй абзац preview body.')
    expect(body.textContent).not.toContain('Третий абзац не должен отображаться.')
    expect(screen.queryByText('Третий абзац не должен отображаться.')).toBeNull()
    expect(getDocumentDemo(container).textContent).toContain(CLAIMS_DOCUMENT_DEMO_TEXT)
    expect(container.querySelector('.claims-document-paywall')).not.toBeNull()
  })

  it('renders final preview pipeline without mixing body requisites demo and paywall', async () => {
    mockedRestoreClaimFromSession.mockResolvedValue({
      claimId: 24,
      editToken: 'token-final-pipeline',
      claim: {
        generation_state: 'ready',
        status: 'draft',
        price_rub: 990,
        manual_review_required: false,
        client_email: 'client@example.com',
        normalized_data: {
          creditor_name: 'Fallback Creditor',
          debtor_name: 'Fallback Debtor',
        },
        preview_header: null,
        step2: {
          missing_fields: [],
        },
      },
    } as never)
    mockedGetClaimPreview.mockResolvedValue({
      generated_preview_text:
        'Первый абзац настоящего preview body.\n\nВторой абзац настоящего preview body.\n\nТретий абзац не должен попасть под blur.',
      preview_requisites: {
        outgoing_number: 'б/н',
        outgoing_date: '2026-05-03',
        outgoing_date_text: '03 мая 2026 года',
      },
      preview_header: {
        format_version: 2,
        from_party: {
          kind: 'legal_entity',
          company_name: 'Sender Org',
          position_raw: 'general director',
          person_name: 'Sender Person',
          line1: 'Legacy Sender Line 1',
          line2: 'Legacy Sender Line 2',
          rendered: {
            line1: 'Rendered Sender Line 1',
            line2: 'Rendered Sender Org',
            line3: 'Rendered Sender Person',
          },
        },
        to_party: {
          kind: 'legal_entity',
          company_name: 'Recipient Org',
          position_raw: 'director',
          person_name: 'Recipient Person',
          line1: 'Legacy Recipient Line 1',
          line2: 'Legacy Recipient Line 2',
          rendered: {
            line1: 'Rendered Recipient Line 1',
            line2: 'Rendered Recipient Org',
            line3: 'Rendered Recipient Person',
          },
        },
      },
    } as never)

    const { container } = renderPage()
    await flushAsyncUpdates()

    const sheet = container.querySelector<HTMLElement>('.claims-document-sheet')
    const header = container.querySelector<HTMLElement>('.claims-document-header')
    const paywall = container.querySelector<HTMLElement>('.claims-document-paywall')
    if (!sheet || !header || !paywall) {
      throw new Error('Expected document sheet, header and paywall overlay to be rendered')
    }

    const { sender, recipient } = getHeaderParties(container)
    expect(getPartyLine(sender, 'line1')).toBe('Rendered Sender Line 1')
    expect(getPartyLine(sender, 'line2')).toBe('Rendered Sender Org')
    expect(getPartyLine(sender, 'line3')).toBe('Rendered Sender Person')
    expect(getPartyLine(recipient, 'line1')).toBe('Rendered Recipient Line 1')
    expect(getPartyLine(recipient, 'line2')).toBe('Rendered Recipient Org')
    expect(getPartyLine(recipient, 'line3')).toBe('Rendered Recipient Person')

    const title = screen.getAllByRole('heading', { name: 'ПРЕТЕНЗИЯ' })
    expect(title).toHaveLength(1)
    expect(title[0].classList.contains('claims-document-title')).toBe(true)

    const requisites = screen.getByText('Исх. №: б/н от 03 мая 2026 года')
    expect(requisites.classList.contains('claims-document-requisites')).toBe(true)

    const body = getDocumentBody(container)
    const bodyParagraphs = Array.from(body.querySelectorAll('p')).map((node) =>
      node.textContent?.trim(),
    )
    expect(bodyParagraphs).toEqual([
      'Первый абзац настоящего preview body.',
      'Второй абзац настоящего preview body.',
    ])
    expect(body.textContent).not.toContain('Третий абзац не должен попасть под blur.')
    expect(body.textContent).not.toContain('Исх. №')
    expect(body.textContent).not.toContain(CLAIMS_DOCUMENT_DEMO_TEXT)
    expect(screen.queryByText('Третий абзац не должен попасть под blur.')).toBeNull()

    const demo = getDocumentDemo(container)
    expect(demo.textContent).toContain(CLAIMS_DOCUMENT_DEMO_TEXT)
    expect(demo.closest('.claims-document-body')).toBeNull()

    expect(header.compareDocumentPosition(title[0]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(title[0].compareDocumentPosition(requisites) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(requisites.compareDocumentPosition(body) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(body.compareDocumentPosition(demo) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(sheet.contains(paywall)).toBe(true)
    expect(container.querySelector('.claims-paywall-card')).not.toBeNull()
    expect(container.querySelector('.claims-paywall-card button')).not.toBeNull()
  })

  it('renders partial v2 rendered header with optional line2/line3 safely', async () => {
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
          creditor_name: 'Fallback Creditor',
          debtor_name: 'Fallback Debtor',
        },
        preview_header: null,
        step2: {
          missing_fields: [],
        },
      },
    } as never)
    mockedGetClaimPreview.mockResolvedValue({
      generated_preview_text: 'Preview text',
      preview_header: {
        format_version: 2,
        from_party: {
          kind: 'individual_entrepreneur',
          company_name: 'Sender Company',
          position_raw: null,
          person_name: 'Sender Person',
          line1: 'Legacy Sender Line 1',
          line2: 'Legacy Sender Line 2',
          rendered: {
            line1: 'Rendered Sender Line 1',
            line2: null,
            line3: 'Rendered Sender Person',
          },
        },
        to_party: {
          kind: 'individual_entrepreneur',
          company_name: 'Recipient Company',
          position_raw: null,
          person_name: 'Recipient Person',
          line1: 'Legacy Recipient Line 1',
          line2: 'Legacy Recipient Line 2',
          rendered: {
            line1: 'Rendered Recipient Line 1',
            line2: 'Rendered Recipient Org',
            line3: null,
          },
        },
      },
    } as never)

    const { container } = renderPage()
    await flushAsyncUpdates()

    const { sender, recipient } = getHeaderParties(container)
    expect(getPartyLine(sender, 'line1')).toBe('Rendered Sender Line 1')
    expect(getPartyLine(sender, 'line2')).toBeNull()
    expect(getPartyLine(sender, 'line3')).toBe('Rendered Sender Person')
    expect(getPartyLine(recipient, 'line1')).toBe('Rendered Recipient Line 1')
    expect(getPartyLine(recipient, 'line2')).toBe('Rendered Recipient Org')
    expect(getPartyLine(recipient, 'line3')).toBeNull()
    expect(screen.queryByText(/^Исх\. №:/)).toBeNull()
  })

  it('uses strict legacy safe mapping when rendered is missing', async () => {
    mockedRestoreClaimFromSession.mockResolvedValue({
      claimId: 18,
      editToken: 'token-legacy',
      claim: {
        generation_state: 'ready',
        status: 'draft',
        price_rub: 990,
        manual_review_required: false,
        client_email: null,
        normalized_data: {
          creditor_name: 'Fallback Creditor',
          debtor_name: 'Fallback Debtor',
        },
        preview_header: null,
        step2: {
          missing_fields: [],
        },
      },
    } as never)
    mockedGetClaimPreview.mockResolvedValue({
      generated_preview_text: 'Preview text',
      preview_header: {
        from_party: {
          kind: 'legal_entity',
          company_name: 'Legacy Sender Org',
          position_raw: null,
          person_name: null,
          line1: 'Legacy Sender Line 1',
          line2: 'Legacy Sender Line 2',
        },
        to_party: {
          kind: 'legal_entity',
          company_name: 'Legacy Recipient Org',
          position_raw: null,
          person_name: null,
          line1: 'Legacy Recipient Line 1',
          line2: 'Legacy Recipient Line 2',
        },
      },
    } as never)

    const { container } = renderPage()
    await flushAsyncUpdates()

    const { sender, recipient } = getHeaderParties(container)
    expect(getPartyLine(sender, 'line1')).toBe('Legacy Sender Line 1')
    expect(getPartyLine(sender, 'line2')).toBeNull()
    expect(getPartyLine(sender, 'line3')).toBe('Legacy Sender Line 2')
    expect(getPartyLine(recipient, 'line1')).toBe('Legacy Recipient Line 1')
    expect(getPartyLine(recipient, 'line2')).toBeNull()
    expect(getPartyLine(recipient, 'line3')).toBe('Legacy Recipient Line 2')
  })

  it('uses exact local fallback for preview_header=null and removes Email fallback', async () => {
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
      generated_preview_text: 'Preview text',
      preview_header: null,
    } as never)

    const { container } = renderPage()
    await flushAsyncUpdates()

    const { sender, recipient } = getHeaderParties(container)
    expect(getPartyLine(sender, 'line1')).toBe('От руководителя')
    expect(getPartyLine(sender, 'line2')).toBe('OOO Alpha')
    expect(getPartyLine(sender, 'line3')).toBeNull()
    expect(getPartyLine(recipient, 'line1')).toBe('Руководителю')
    expect(getPartyLine(recipient, 'line2')).toBe('OOO Vector')
    expect(getPartyLine(recipient, 'line3')).toBeNull()
    expect(screen.queryByText(/Email:/)).toBeNull()
  })

  it('uses safe defaults when preview_header is null and normalized names are missing', async () => {
    mockedRestoreClaimFromSession.mockResolvedValue({
      claimId: 19,
      editToken: 'token-no-header',
      claim: {
        generation_state: 'ready',
        status: 'draft',
        price_rub: 990,
        manual_review_required: false,
        client_email: null,
        normalized_data: null,
        preview_header: null,
        step2: {
          missing_fields: [],
        },
      },
    } as never)
    mockedGetClaimPreview.mockResolvedValue({
      generated_preview_text: 'Preview text',
      preview_header: null,
    } as never)

    const { container } = renderPage()
    await flushAsyncUpdates()

    const { sender, recipient } = getHeaderParties(container)
    expect(getPartyLine(sender, 'line1')).toBe('От руководителя')
    expect(getPartyLine(sender, 'line2')).toBeNull()
    expect(getPartyLine(sender, 'line3')).toBeNull()
    expect(getPartyLine(recipient, 'line1')).toBe('Руководителю')
    expect(getPartyLine(recipient, 'line2')).toBeNull()
    expect(getPartyLine(recipient, 'line3')).toBeNull()
  })

  it('uses local fallback with only creditor_name present', async () => {
    mockedRestoreClaimFromSession.mockResolvedValue({
      claimId: 20,
      editToken: 'token-only-creditor',
      claim: {
        generation_state: 'ready',
        status: 'draft',
        price_rub: 990,
        manual_review_required: false,
        client_email: null,
        normalized_data: {
          creditor_name: 'Only Creditor LLC',
          debtor_name: null,
        },
        preview_header: null,
        step2: {
          missing_fields: [],
        },
      },
    } as never)
    mockedGetClaimPreview.mockResolvedValue({
      generated_preview_text: 'Preview text',
      preview_header: null,
    } as never)

    const { container } = renderPage()
    await flushAsyncUpdates()

    const { sender, recipient } = getHeaderParties(container)
    expect(getPartyLine(sender, 'line1')).toBe('От руководителя')
    expect(getPartyLine(sender, 'line2')).toBe('Only Creditor LLC')
    expect(getPartyLine(sender, 'line3')).toBeNull()
    expect(getPartyLine(recipient, 'line1')).toBe('Руководителю')
    expect(getPartyLine(recipient, 'line2')).toBeNull()
    expect(getPartyLine(recipient, 'line3')).toBeNull()
  })

  it('uses local fallback with only debtor_name present', async () => {
    mockedRestoreClaimFromSession.mockResolvedValue({
      claimId: 21,
      editToken: 'token-only-debtor',
      claim: {
        generation_state: 'ready',
        status: 'draft',
        price_rub: 990,
        manual_review_required: false,
        client_email: null,
        normalized_data: {
          creditor_name: null,
          debtor_name: 'Only Debtor LLC',
        },
        preview_header: null,
        step2: {
          missing_fields: [],
        },
      },
    } as never)
    mockedGetClaimPreview.mockResolvedValue({
      generated_preview_text: 'Preview text',
      preview_header: null,
    } as never)

    const { container } = renderPage()
    await flushAsyncUpdates()

    const { sender, recipient } = getHeaderParties(container)
    expect(getPartyLine(sender, 'line1')).toBe('От руководителя')
    expect(getPartyLine(sender, 'line2')).toBeNull()
    expect(getPartyLine(sender, 'line3')).toBeNull()
    expect(getPartyLine(recipient, 'line1')).toBe('Руководителю')
    expect(getPartyLine(recipient, 'line2')).toBe('Only Debtor LLC')
    expect(getPartyLine(recipient, 'line3')).toBeNull()
  })
})
