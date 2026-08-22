import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { StrictMode } from 'react'
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  createCompanyReport,
  getCompanyPublicH1,
  getCompanyReportStatus,
} from '../companyReport/companyReportApi'
import publishedFixture from '../companyReport/fixtures/company-public-h1-published.json?raw'
import { parseCompanyPublicH1 } from '../companyReport/companyReportH1Contract'
import {
  cleanupCompanyHead,
  HEAD_KIND_ATTRIBUTE,
  HEAD_OWNER_ATTRIBUTE,
  HEAD_OWNER_VALUE,
  STATUS_POLL_INTERVAL_MS,
} from '../companyReport/companyReportPresentation'
import type {
  CompanyPublicH1Response,
  CompanyReportLifecycle,
} from '../companyReport/companyReportTypes'
import { ApiHttpError } from '../lib/api'
import { CompanyReportPage } from './CompanyReportPage'

vi.mock('../companyReport/companyReportApi', () => ({
  getCompanyPublicH1: vi.fn(),
  getCompanyReportStatus: vi.fn(),
  createCompanyReport: vi.fn(),
}))

const mockedGet = vi.mocked(getCompanyPublicH1)
const mockedStatus = vi.mocked(getCompanyReportStatus)
const mockedCreate = vi.mocked(createCompanyReport)
const companyA = parseCompanyPublicH1(JSON.parse(publishedFixture))

function companyDto(
  inn: string,
  slug: string,
  name: string,
  reportId: string,
): CompanyPublicH1Response {
  const canonicalPath = `/company/${inn}-${slug}`
  return {
    ...companyA,
    report_id: reportId,
    canonical_path: canonicalPath,
    identity: {
      ...companyA.identity,
      inn,
      legal_full_name: name,
      legal_short_name: null,
      display_name: name,
    },
    actions: [
      companyA.actions[0],
      {
        action_id: 'prepare_claim',
        label: 'Подготовить претензию',
        path: `/claims?report_id=${reportId}`,
      },
    ],
    breadcrumbs: [
      companyA.breadcrumbs[0],
      { label: name, path: canonicalPath },
    ],
  }
}

const companyB = companyDto(
  '0987654321',
  'vtoraya-kompaniya',
  'ООО Вторая компания',
  '33333333-3333-4333-8333-333333333333',
)

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve
    reject = promiseReject
  })
  return { promise, resolve, reject }
}

function NavigationHarness() {
  const location = useLocation()
  const navigate = useNavigate()
  return (
    <>
      <p data-testid="location">
        {`${location.pathname}${location.search}${location.hash}`}
      </p>
      <button type="button" onClick={() => navigate('/company/0987654321')}>
        Открыть компанию B
      </button>
      <button
        type="button"
        onClick={() => navigate(`${location.pathname}?source=test`)}
      >
        Добавить query
      </button>
      <button
        type="button"
        onClick={() => navigate(`${location.pathname}?source=other`)}
      >
        Изменить query
      </button>
      <button type="button" onClick={() => navigate(location.pathname)}>
        Убрать query
      </button>
      <button
        type="button"
        onClick={() => navigate(`${location.pathname}#finance`)}
      >
        Добавить hash
      </button>
    </>
  )
}

function PageRoutes() {
  return (
    <>
      <NavigationHarness />
      <Routes>
        <Route path="/company/:companyKey" element={<CompanyReportPage />} />
        <Route path="/claims" element={<p>Claims destination</p>} />
        <Route path="/" element={<p>Landing destination</p>} />
      </Routes>
    </>
  )
}

function renderPage(path = companyA.canonical_path, strict = false) {
  const app = (
    <MemoryRouter initialEntries={[path]}>
      <PageRoutes />
    </MemoryRouter>
  )
  return render(strict ? <StrictMode>{app}</StrictMode> : app)
}

async function flushPromises() {
  await act(async () => {
    await Promise.resolve()
  })
}

function pendingError() {
  return new ApiHttpError(409, { detail: { code: 'report_pending' } })
}

function notFoundError() {
  return new ApiHttpError(404, {
    detail: { code: 'company_report_not_found' },
  })
}

describe('CompanyReportPage lifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedGet.mockResolvedValue(companyA)
    mockedStatus.mockResolvedValue({
      report_id: 'status-default',
      status: 'pending',
      started_at: '2026-08-20T10:00:00Z',
    })
    mockedCreate.mockResolvedValue({
      report_id: 'create-default',
      status: 'pending',
      reused: false,
    })
    document.title = 'Исходный заголовок'
    document.documentElement.lang = 'en'
  })

  afterEach(() => {
    cleanup()
    cleanupCompanyHead()
    vi.useRealTimers()
  })

  it('rejects an invalid key or any query locally while keeping protective noindex', async () => {
    renderPage('/company/not-a-company')
    expect(
      screen.getByRole('heading', {
        name: 'Некорректный адрес страницы компании.',
      }),
    ).toBeTruthy()
    expect(mockedGet).not.toHaveBeenCalled()
    cleanup()

    renderPage('/company/1234567890?source=test')
    expect(
      screen.getByRole('heading', {
        name: 'Некорректный адрес страницы компании.',
      }),
    ).toBeTruthy()
    expect(mockedGet).not.toHaveBeenCalled()
    const robots = document.head.querySelector(
      `[${HEAD_OWNER_ATTRIBUTE}="${HEAD_OWNER_VALUE}"][${HEAD_KIND_ATTRIBUTE}="robots"]`,
    )
    expect(robots?.getAttribute('content')).toBe('noindex,follow')
    await flushPromises()
    expect(mockedCreate).not.toHaveBeenCalled()
    expect(mockedStatus).not.toHaveBeenCalled()
  })

  it('loads an existing canonical projection without creating or polling', async () => {
    renderPage()
    expect(
      await screen.findByRole('heading', {
        name: `${companyA.identity.legal_full_name} — ИНН ${companyA.identity.inn}`,
      }),
    ).toBeTruthy()
    expect(mockedGet).toHaveBeenCalledTimes(1)
    expect(mockedGet).toHaveBeenCalledWith(
      companyA.identity.inn,
      expect.any(AbortSignal),
    )
    expect(mockedCreate).not.toHaveBeenCalled()
    expect(mockedStatus).not.toHaveBeenCalled()
  })

  it.each([
    ['/company/1234567890', 'plain resolver'],
    ['/company/1234567890-wrong-slug', 'wrong canonical slug'],
  ])('retains one same-INN DTO across replace for %s', async (path) => {
    renderPage(path)
    await waitFor(() => {
      expect(screen.getByTestId('location').textContent).toBe(
        companyA.canonical_path,
      )
    })
    expect(
      await screen.findByRole('heading', {
        name: `${companyA.identity.legal_full_name} — ИНН ${companyA.identity.inn}`,
      }),
    ).toBeTruthy()
    expect(mockedGet).toHaveBeenCalledTimes(1)
    expect(mockedCreate).not.toHaveBeenCalled()
  })

  it('consumes retained data once and performs an ordinary read after remount', async () => {
    const first = renderPage('/company/1234567890')
    await screen.findByRole('heading', {
      name: `${companyA.identity.legal_full_name} — ИНН ${companyA.identity.inn}`,
    })
    expect(mockedGet).toHaveBeenCalledTimes(1)
    first.unmount()

    renderPage(companyA.canonical_path)
    await screen.findByRole('heading', {
      name: `${companyA.identity.legal_full_name} — ИНН ${companyA.identity.inn}`,
    })
    expect(mockedGet).toHaveBeenCalledTimes(2)
  })

  it('fails closed when a response identity or canonical path crosses INNs', async () => {
    mockedGet.mockResolvedValueOnce({
      ...companyA,
      canonical_path: companyB.canonical_path,
    })
    renderPage('/company/1234567890')
    expect(
      await screen.findByRole('heading', {
        name: 'Неподдерживаемый формат отчёта',
      }),
    ).toBeTruthy()
    expect(screen.getByTestId('location').textContent).toBe(
      '/company/1234567890',
    )
    expect(mockedGet).toHaveBeenCalledTimes(1)
    expect(mockedCreate).not.toHaveBeenCalled()
  })

  it('auto-creates exactly once for a plain exact 404 under StrictMode', async () => {
    mockedGet.mockRejectedValue(notFoundError())
    renderPage('/company/1234567890', true)
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1))
    expect(mockedCreate).toHaveBeenCalledWith(
      '1234567890',
      expect.any(AbortSignal),
    )
    expect(
      await screen.findByRole('heading', { name: 'Проверяем компанию' }),
    ).toBeTruthy()
  })

  it.each([
    [404, 'company_report_not_found'],
    [409, 'report_failed'],
    [409, 'report_not_eligible'],
    [409, 'public_projection_invalid'],
  ])('never creates from canonical HTTP %s %s', async (status, code) => {
    mockedGet.mockRejectedValueOnce(
      new ApiHttpError(status, { detail: { code } }),
    )
    renderPage(companyA.canonical_path)
    await screen.findByRole('heading')
    await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1))
    expect(mockedCreate).not.toHaveBeenCalled()
  })

  it('retries the exact failed read operation', async () => {
    mockedGet
      .mockRejectedValueOnce(new ApiHttpError(503, { detail: { code: 'busy' } }))
      .mockResolvedValueOnce(companyA)
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Повторить' }))
    await screen.findByRole('heading', {
      name: `${companyA.identity.legal_full_name} — ИНН ${companyA.identity.inn}`,
    })
    expect(mockedGet).toHaveBeenCalledTimes(2)
    expect(mockedCreate).not.toHaveBeenCalled()
    expect(mockedStatus).not.toHaveBeenCalled()
  })

  it('retries the exact failed create operation without another read', async () => {
    mockedGet.mockRejectedValueOnce(notFoundError())
    mockedCreate
      .mockRejectedValueOnce(new ApiHttpError(503, { detail: { code: 'busy' } }))
      .mockResolvedValueOnce({
        report_id: 'create-retry',
        status: 'pending',
        reused: true,
      })
    renderPage('/company/1234567890')
    fireEvent.click(await screen.findByRole('button', { name: 'Повторить' }))
    await screen.findByRole('heading', { name: 'Проверяем компанию' })
    expect(mockedGet).toHaveBeenCalledTimes(1)
    expect(mockedCreate).toHaveBeenCalledTimes(2)
    expect(mockedStatus).not.toHaveBeenCalled()
  })

  it('retries the exact failed status operation without a read or create', async () => {
    vi.useFakeTimers()
    mockedGet.mockRejectedValueOnce(pendingError())
    mockedStatus
      .mockRejectedValueOnce(new ApiHttpError(503, { detail: { code: 'busy' } }))
      .mockResolvedValueOnce({
        report_id: 'status-retry',
        status: 'pending',
        started_at: '2026-08-20T10:00:00Z',
      })
    renderPage()
    await flushPromises()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(STATUS_POLL_INTERVAL_MS)
    })
    fireEvent.click(screen.getByRole('button', { name: 'Повторить' }))
    await flushPromises()
    expect(mockedStatus).toHaveBeenCalledTimes(2)
    expect(mockedGet).toHaveBeenCalledTimes(1)
    expect(mockedCreate).not.toHaveBeenCalled()
  })

  it('uses a final H1 read after terminal status and never auto-creates from its 404', async () => {
    vi.useFakeTimers()
    mockedGet
      .mockRejectedValueOnce(notFoundError())
      .mockRejectedValueOnce(notFoundError())
    mockedCreate.mockResolvedValueOnce({
      report_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
      status: 'pending',
      reused: false,
    })
    mockedStatus.mockResolvedValueOnce({
      report_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
      status: 'failed',
      started_at: '2026-08-20T10:00:00Z',
    })
    renderPage('/company/1234567890')
    await flushPromises()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(STATUS_POLL_INTERVAL_MS)
    })
    expect(
      screen.getByRole('heading', { name: 'Публичный отчёт не найден' }),
    ).toBeTruthy()
    expect(mockedGet).toHaveBeenCalledTimes(2)
    expect(mockedStatus).toHaveBeenCalledTimes(1)
    expect(mockedCreate).toHaveBeenCalledTimes(1)
  })

  it('ignores create/status UUIDs and sends only the final H1 UUID to Claims', async () => {
    vi.useFakeTimers()
    const finalDto = companyDto(
      '1234567890',
      'final-company',
      'ООО Финальная компания',
      'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
    )
    mockedGet
      .mockRejectedValueOnce(notFoundError())
      .mockResolvedValueOnce(finalDto)
    mockedCreate.mockResolvedValueOnce({
      report_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
      status: 'pending',
      reused: true,
    })
    mockedStatus.mockResolvedValueOnce({
      report_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
      status: 'complete',
      started_at: '2026-08-20T10:00:00Z',
    })
    renderPage('/company/1234567890')
    await flushPromises()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(STATUS_POLL_INTERVAL_MS)
    })
    expect(
      screen.getByRole('heading', {
        name: `${finalDto.identity.legal_full_name} — ИНН ${finalDto.identity.inn}`,
      }),
    ).toBeTruthy()
    expect(screen.getByTestId('location').textContent).toBe(
      finalDto.canonical_path,
    )
    expect(document.body.textContent).not.toContain(
      'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    )
    expect(document.body.textContent).not.toContain(
      'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    )
    fireEvent.click(screen.getByRole('link', { name: 'Подготовить претензию' }))
    expect(screen.getByTestId('location').textContent).toBe(
      `/claims?report_id=${finalDto.report_id}`,
    )
  })

  it('keeps at most one poll in flight and aborts it on unmount', async () => {
    vi.useFakeTimers()
    const pendingStatus = deferred<CompanyReportLifecycle>()
    let pollSignal: AbortSignal | undefined
    mockedGet.mockRejectedValueOnce(pendingError())
    mockedStatus.mockImplementationOnce((_inn, signal) => {
      pollSignal = signal
      return pendingStatus.promise
    })
    const result = renderPage()
    await flushPromises()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(STATUS_POLL_INTERVAL_MS * 4)
    })
    expect(mockedStatus).toHaveBeenCalledTimes(1)
    expect(pollSignal?.aborted).toBe(false)
    result.unmount()
    expect(pollSignal?.aborted).toBe(true)
  })

  it('keeps a delayed final H1 read alive when polling cleanup runs', async () => {
    vi.useFakeTimers()
    const finalRead = deferred<CompanyPublicH1Response>()
    let finalSignal: AbortSignal | undefined
    mockedGet
      .mockRejectedValueOnce(pendingError())
      .mockImplementationOnce((_inn, signal) => {
        finalSignal = signal
        return finalRead.promise
      })
    mockedStatus.mockResolvedValueOnce({
      report_id: 'status-only',
      status: 'complete',
      started_at: '2026-08-20T10:00:00Z',
    })
    renderPage()
    await flushPromises()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(STATUS_POLL_INTERVAL_MS)
    })
    expect(mockedGet).toHaveBeenCalledTimes(2)
    expect(finalSignal?.aborted).toBe(false)
    await act(async () => finalRead.resolve(companyA))
    expect(
      screen.getByRole('heading', {
        name: `${companyA.identity.legal_full_name} — ИНН ${companyA.identity.inn}`,
      }),
    ).toBeTruthy()
  })

  it('does not let a stale poll for A clear or abort the in-flight poll for B', async () => {
    vi.useFakeTimers()
    const statusA = deferred<CompanyReportLifecycle>()
    const statusB = deferred<CompanyReportLifecycle>()
    let signalA: AbortSignal | undefined
    let signalB: AbortSignal | undefined
    mockedGet.mockImplementation(async (requestedInn) => {
      if (requestedInn === '1234567890') throw pendingError()
      if (requestedInn === '0987654321') throw pendingError()
      throw new Error('unexpected INN')
    })
    mockedStatus
      .mockImplementationOnce((_inn, signal) => {
        signalA = signal
        return statusA.promise
      })
      .mockImplementationOnce((_inn, signal) => {
        signalB = signal
        return statusB.promise
      })
    renderPage('/company/1234567890')
    await flushPromises()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(STATUS_POLL_INTERVAL_MS)
    })
    fireEvent.click(screen.getByRole('button', { name: 'Открыть компанию B' }))
    await flushPromises()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(STATUS_POLL_INTERVAL_MS)
    })
    expect(mockedStatus.mock.calls.map(([requestedInn]) => requestedInn)).toEqual([
      '1234567890',
      '0987654321',
    ])
    expect(signalA?.aborted).toBe(true)
    expect(signalB?.aborted).toBe(false)

    await act(async () => {
      statusA.resolve({
        report_id: 'stale-a',
        status: 'pending',
        started_at: '2026-08-20T10:00:00Z',
      })
      await Promise.resolve()
    })
    expect(signalB?.aborted).toBe(false)
    expect(screen.getByTestId('location').textContent).toBe(
      '/company/0987654321',
    )
  })

  it('aborts a read on query transition, starts no query calls, and ignores stale success', async () => {
    const staleRead = deferred<CompanyPublicH1Response>()
    let staleSignal: AbortSignal | undefined
    mockedGet.mockImplementationOnce((_inn, signal) => {
      staleSignal = signal
      return staleRead.promise
    })
    renderPage('/company/1234567890')
    await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByRole('button', { name: 'Добавить query' }))
    expect(staleSignal?.aborted).toBe(true)
    expect(
      screen.getByRole('heading', {
        name: 'Некорректный адрес страницы компании.',
      }),
    ).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Изменить query' }))
    await act(async () => staleRead.resolve(companyA))
    expect(mockedGet).toHaveBeenCalledTimes(1)
    expect(mockedCreate).not.toHaveBeenCalled()
    expect(mockedStatus).not.toHaveBeenCalled()
    expect(screen.getByTestId('location').textContent).toBe(
      '/company/1234567890?source=other',
    )
    expect(
      screen.getByRole('heading', {
        name: 'Некорректный адрес страницы компании.',
      }),
    ).toBeTruthy()
  })

  it('makes hash-only transitions without a new read', async () => {
    renderPage()
    await screen.findByRole('heading', {
      name: `${companyA.identity.legal_full_name} — ИНН ${companyA.identity.inn}`,
    })
    fireEvent.click(screen.getByRole('button', { name: 'Добавить hash' }))
    expect(screen.getByTestId('location').textContent).toBe(
      `${companyA.canonical_path}#finance`,
    )
    expect(mockedGet).toHaveBeenCalledTimes(1)
  })

  it('prevents every stale A outcome from changing B or starting an A POST', async () => {
    const staleA = deferred<CompanyPublicH1Response>()
    let signalA: AbortSignal | undefined
    mockedGet
      .mockImplementationOnce((_inn, signal) => {
        signalA = signal
        return staleA.promise
      })
      .mockResolvedValueOnce(companyB)
    renderPage('/company/1234567890')
    await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByRole('button', { name: 'Открыть компанию B' }))
    expect(
      await screen.findByRole('heading', {
        name: `${companyB.identity.legal_full_name} — ИНН ${companyB.identity.inn}`,
      }),
    ).toBeTruthy()
    expect(signalA?.aborted).toBe(true)
    await act(async () => staleA.reject(notFoundError()))
    expect(mockedCreate).not.toHaveBeenCalled()
    expect(screen.getByTestId('location').textContent).toBe(
      companyB.canonical_path,
    )
    expect(
      screen.getByRole('heading', {
        name: `${companyB.identity.legal_full_name} — ИНН ${companyB.identity.inn}`,
      }),
    ).toBeTruthy()
  })
})
