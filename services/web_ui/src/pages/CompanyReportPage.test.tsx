import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createCompanyReport, getCompanyReport, getCompanyReportStatus } from '../companyReport/companyReportApi'
import type { CompanyReportResponse } from '../companyReport/companyReportTypes'
import { ApiHttpError } from '../lib/api'
import { CompanyReportPage } from './CompanyReportPage'

vi.mock('../companyReport/companyReportApi', () => ({ getCompanyReport: vi.fn(), getCompanyReportStatus: vi.fn(), createCompanyReport: vi.fn() }))
const mockedGet = vi.mocked(getCompanyReport); const mockedStatus = vi.mocked(getCompanyReportStatus); const mockedCreate = vi.mocked(createCompanyReport)
const completed: CompanyReportResponse = { report_id: 'r1', status: 'complete', started_at: '2026-01-01T00:00:00Z', report: { status: 'complete', datasets: {}, completeness: { available_count: 1, required_count: 1, percent: 100, missing_datasets: [], unavailable_datasets: [] }, freshness: { generated_at: '2026-01-01T00:00:00Z' }, warnings: [], usable_for_public_page: true, usable_for_future_scoring: true, counterparty: { short_name: 'Тест' } } }
function LocationProbe() {
  const location = useLocation()
  const navigate = useNavigate()
  return <><p data-testid="location">{location.pathname}</p><button type="button" onClick={() => navigate('/company/0987654321')}>Open second company</button></>
}
function renderPage(path = '/company/1234567890-test') { return render(<MemoryRouter initialEntries={[path]}><LocationProbe /><Routes><Route path="/company/:companyKey" element={<CompanyReportPage />} /></Routes></MemoryRouter>) }

describe('CompanyReportPage lifecycle', () => {
  beforeEach(() => { vi.clearAllMocks(); mockedGet.mockResolvedValue(completed) })
  afterEach(() => { cleanup(); vi.useRealTimers() })
  it('validates the route before fetching', () => {
    renderPage('/company/not-a-company-key')
    expect(screen.getByText('Некорректный адрес страницы компании.')).toBeTruthy()
    expect(mockedGet).not.toHaveBeenCalled()
  })
  it('performs one ordinary initial GET and no AI request', async () => {
    renderPage()
    await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1))
    expect(mockedGet.mock.calls[0]?.[1]).not.toHaveProperty('includeAiExplanation')
    expect(screen.getByRole('heading', { name: 'Тест' })).toBeTruthy()
  })
  it('starts one report only after a verified not-found response on the plain resolver', async () => {
    mockedGet.mockRejectedValueOnce(new ApiHttpError(404, { detail: { code: 'company_report_not_found' } }))
    mockedCreate.mockResolvedValue({ report_id: 'r1', status: 'pending', reused: false })
    renderPage('/company/1234567890')
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledWith('1234567890', expect.any(AbortSignal)))
  })

  it('does not start a report from a canonical 404', async () => {
    mockedGet.mockRejectedValueOnce(new ApiHttpError(404, { detail: { code: 'company_report_not_found' } }))
    renderPage('/company/1234567890-test')
    await screen.findByRole('button', { name: 'Повторить' })
    expect(mockedCreate).not.toHaveBeenCalled()
  })
  it('creates a new report from a failed response without a snapshot', async () => {
    mockedGet.mockResolvedValueOnce({ report_id: 'r1', status: 'failed', started_at: '2026-01-01T00:00:00Z', report: null, failure: { code: 'snapshot_failed', message: 'Снимок недоступен', retryable: true } })
    mockedCreate.mockResolvedValue({ report_id: 'r2', status: 'pending', reused: false })
    renderPage()
    await screen.findByRole('button', { name: 'Создать новый отчёт' })
    expect(mockedCreate).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Создать новый отчёт' }))
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1))
  })
  it('retries a failed POST with POST rather than a terminal GET', async () => {
    mockedGet.mockRejectedValueOnce(new ApiHttpError(404, { detail: { code: 'company_report_not_found' } }))
    mockedCreate.mockRejectedValueOnce(new ApiHttpError(503, { detail: { code: 'unavailable' } })).mockResolvedValueOnce({ report_id: 'r2', status: 'pending', reused: false })
    renderPage('/company/1234567890')
    await screen.findByRole('button', { name: 'Повторить' })
    expect(mockedGet).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Повторить' }))
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(2))
    expect(mockedGet).toHaveBeenCalledTimes(1)
  })
  it('renders public-safe 401 and 403 states without login redirect or job creation', async () => {
    mockedGet.mockRejectedValueOnce(new ApiHttpError(401, { detail: { code: 'unauthenticated' } }))
    renderPage('/company/1234567890')
    expect(await screen.findByRole('heading', { name: 'Не удалось открыть публичный отчёт' })).toBeTruthy()
    expect(screen.queryByRole('link', { name: 'Войти' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Повторить' })).toBeNull()
    expect(mockedCreate).not.toHaveBeenCalled()
    cleanup()
    mockedGet.mockRejectedValueOnce(new ApiHttpError(403, { detail: { code: 'forbidden' } }))
    renderPage('/company/1234567890')
    expect(await screen.findByRole('heading', { name: 'Не удалось открыть публичный отчёт' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Повторить' })).toBeNull()
    expect(mockedCreate).not.toHaveBeenCalled()
  })
  it.each([
    ['server error', new ApiHttpError(500, { detail: { code: 'internal_error' } })],
    ['network error', new Error('network')],
  ])('does not create a job after a plain-route %s', async (_label, error) => {
    mockedGet.mockRejectedValueOnce(error)
    renderPage('/company/1234567890')
    await screen.findByRole('button', { name: 'Повторить' })
    expect(mockedCreate).not.toHaveBeenCalled()
  })
  it('retries a transport GET explicitly', async () => {
    mockedGet.mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce(completed)
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Повторить' }))
    await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(2))
  })
  it('polls pending status after three seconds and refetches terminal report', async () => {
    vi.useFakeTimers()
    mockedGet.mockRejectedValueOnce(new ApiHttpError(409, { detail: { code: 'report_pending' } })).mockResolvedValueOnce(completed)
    mockedStatus.mockResolvedValue({ report_id: 'r1', status: 'complete', started_at: '2026-01-01T00:00:00Z' })
    renderPage()
    await act(async () => { await Promise.resolve() })
    expect(screen.getByText('Проверяем компанию')).toBeTruthy()
    await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
    expect(mockedStatus).toHaveBeenCalledTimes(1)
    expect(mockedGet).toHaveBeenCalledTimes(2)
  })
  it('shows deterministic report-building stages while polling', async () => {
    vi.useFakeTimers()
    mockedGet.mockRejectedValueOnce(new ApiHttpError(409, { detail: { code: 'report_pending' } }))
    mockedStatus.mockResolvedValue({ report_id: 'r1', status: 'pending', started_at: '2026-01-01T00:00:00Z' })
    renderPage('/company/1234567890')
    await act(async () => { await Promise.resolve() })
    expect(screen.getByText('Проверяем компанию')).toBeTruthy()
    await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
    expect(screen.getByText('Собираем сведения о должнике')).toBeTruthy()
    await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
    expect(screen.getByText('Анализируем данные')).toBeTruthy()
    await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
    expect(screen.getByText('Формируем отчёт')).toBeTruthy()
  })
  it('replace-redirects a plain pending resolver to its final canonical path', async () => {
    vi.useFakeTimers()
    const canonical = { ...completed, canonical_path: '/company/1234567890-test' }
    mockedGet.mockRejectedValueOnce(new ApiHttpError(409, { detail: { code: 'report_pending' } })).mockResolvedValueOnce(canonical)
    mockedStatus.mockResolvedValue({ report_id: 'r1', status: 'complete', started_at: '2026-01-01T00:00:00Z' })
    renderPage('/company/1234567890')
    await act(async () => { await Promise.resolve() })
    await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
    expect(screen.getByTestId('location').textContent).toBe('/company/1234567890-test')
    expect(mockedCreate).not.toHaveBeenCalled()
  })
  it('keeps the delayed final GET alive when terminal status stops polling', async () => {
    vi.useFakeTimers()
    let finalSignal: AbortSignal | undefined
    let resolveFinal: ((value: CompanyReportResponse) => void) | undefined
    const canonical = { ...completed, canonical_path: '/company/1234567890-test' }
    mockedGet
      .mockRejectedValueOnce(new ApiHttpError(409, { detail: { code: 'report_pending' } }))
      .mockImplementationOnce((_inn, options) => {
        finalSignal = options?.signal
        return new Promise<CompanyReportResponse>((resolve) => { resolveFinal = resolve })
      })
      .mockResolvedValue(completed)
    mockedStatus.mockResolvedValue({ report_id: 'r1', status: 'complete', started_at: '2026-01-01T00:00:00Z' })
    renderPage('/company/1234567890')
    await act(async () => { await Promise.resolve() })
    await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
    expect(mockedGet).toHaveBeenCalledTimes(2)
    expect(finalSignal?.aborted).toBe(false)
    await act(async () => {
      resolveFinal?.(canonical)
      await vi.runAllTimersAsync()
    })
    expect(screen.getByTestId('location').textContent).toBe('/company/1234567890-test')
    expect(screen.getByRole('heading', { name: 'Тест' })).toBeTruthy()
  })
  it('ignores a late response after navigating to another INN', async () => {
    let oldSignal: AbortSignal | undefined
    let resolveOld: ((value: CompanyReportResponse) => void) | undefined
    const oldReport = { ...completed, report: { ...completed.report!, counterparty: { short_name: 'Old company' } } }
    const newReport = { ...completed, report: { ...completed.report!, counterparty: { short_name: 'New company' } } }
    mockedGet
      .mockImplementationOnce((_inn, options) => {
        oldSignal = options?.signal
        return new Promise<CompanyReportResponse>((resolve) => { resolveOld = resolve })
      })
      .mockResolvedValueOnce(newReport)
    renderPage('/company/1234567890')
    await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByRole('button', { name: 'Open second company' }))
    expect(await screen.findByRole('heading', { name: 'New company' })).toBeTruthy()
    expect(oldSignal?.aborted).toBe(true)
    await act(async () => { resolveOld?.(oldReport); await Promise.resolve() })
    expect(screen.getByRole('heading', { name: 'New company' })).toBeTruthy()
    expect(screen.queryByRole('heading', { name: 'Old company' })).toBeNull()
  })
  it('keeps one poll request in flight and aborts it on unmount', async () => {
    vi.useFakeTimers()
    let signal: AbortSignal | undefined
    mockedGet.mockRejectedValueOnce(new ApiHttpError(409, { detail: { code: 'report_pending' } }))
    mockedStatus.mockImplementation((_inn, nextSignal) => {
      signal = nextSignal
      return new Promise(() => {})
    })
    const page = renderPage()
    await act(async () => { await Promise.resolve() })
    await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
    expect(mockedStatus).toHaveBeenCalledTimes(1)
    await act(async () => { await vi.advanceTimersByTimeAsync(9000) })
    expect(mockedStatus).toHaveBeenCalledTimes(1)
    page.unmount()
    expect(signal?.aborted).toBe(true)
  })
  it('loads AI only after its explicit button click and leaves machine content present', async () => {
    const withScore: CompanyReportResponse = { ...completed, scoring: { level: 'medium', score_points: '12.00', confidence: {}, reasons: [], domain_breakdown: [] } }
    mockedGet.mockResolvedValueOnce(withScore).mockResolvedValueOnce({ ...withScore, ai_explanation: { status: 'ok', explanation: { overall_conclusion: 'AI текст', recovery_factors: [], key_risks: [], urgency: 'обычная', recommended_next_step: 'проверить', limitations: [] } } })
    renderPage()
    await screen.findByRole('button', { name: 'Показать AI-пояснение' })
    expect(mockedGet).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Показать AI-пояснение' }))
    await screen.findByText('AI текст')
    expect(screen.getByRole('heading', { name: 'Машинная оценка' })).toBeTruthy()
    expect(mockedGet.mock.calls[1]?.[1]).toMatchObject({ includeAiExplanation: true })
  })
})
