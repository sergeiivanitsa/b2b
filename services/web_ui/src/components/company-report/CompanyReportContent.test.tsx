import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { CompanyReportResponse, PublicSignal } from '../../companyReport/companyReportTypes'
import { CompanyReportContent } from './CompanyReportContent'

const response: CompanyReportResponse = {
  report_id: '2e7e9d9f-5f3a-4d43-a8e8-2bb3c2adf6b1', status: 'complete', started_at: '2026-01-01T00:00:00Z',
  report: {
    status: 'complete', datasets: {}, usable_for_public_page: true, usable_for_future_scoring: true,
    completeness: { available_count: 3, required_count: 3, percent: 100, missing_datasets: [], unavailable_datasets: [] }, freshness: { generated_at: '2026-01-01T00:00:00Z' }, warnings: [],
    counterparty: { short_name: 'ООО Тест', inn: '1234567890', address: { line_address: 'Тестовая улица' }, status_text: 'Действует' },
    finance: { unit: 'provider_units_unknown', periods: [{ year: 2025, revenue: '123.4500', net_profit: null }] },
    arbitration: { total_cases: 2, returned_cases: 1, is_complete: true, claim_amounts_by_currency: { USD: { plaintiff: '10.00', respondent: '0.01' } } },
  },
  signals: { signals: [{ code: 'unknown.signal', category: 'financial', direction: 'neutral', strength: 'weak', confidence: 'low' }] },
  scoring: { level: 'insufficient_data', score_points: null, confidence: {}, reasons: [], domain_breakdown: [] },
}

function LocationProbe() { const location = useLocation(); return <pre>{location.search}</pre> }

describe('CompanyReportContent', () => {
  afterEach(cleanup)
  it('renders only safe fields, preserves exact decimal and unknown unit', () => {
    render(<MemoryRouter><CompanyReportContent inn="1234567890" response={{ ...response, report: { ...response.report!, raw_payload: 'secret' } as typeof response.report }} /></MemoryRouter>)
    expect(screen.getByRole('heading', { name: 'ООО Тест' })).toBeTruthy()
    expect(screen.getByText('123.4500')).toBeTruthy()
    expect(screen.getByText(/Единица измерения неизвестна/)).toBeTruthy()
    expect(screen.getAllByText('Нет данных').length).toBeGreaterThan(0)
    expect(screen.queryByText('secret')).toBeNull()
    expect(screen.queryByText('factual_basis')).toBeNull()
    expect(screen.getByText('Сигнал требует проверки')).toBeTruthy()
    expect(screen.getByText('unknown.signal')).toBeTruthy()
  })
  it('keeps machine score semantically distinct from explicit AI', () => {
    const onLoadAi = vi.fn()
    render(<MemoryRouter><CompanyReportContent inn="1234567890" response={response} onLoadAi={onLoadAi} /></MemoryRouter>)
    expect(screen.getByRole('heading', { name: 'Машинная оценка' })).toBeTruthy()
    expect(screen.getByText('Недостаточно доказательств для числовой оценки.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Показать AI-пояснение' }))
    expect(onLoadAi).toHaveBeenCalledTimes(1)
  })
  it('keeps a snapshot failure safe and offers a new report only explicitly', () => {
    const onCreate = vi.fn()
    render(<MemoryRouter><CompanyReportContent inn="1234567890" response={{ ...response, status: 'failed', failure: { code: 'snapshot_failed', message: 'Безопасная ошибка', retryable: true } }} onCreate={onCreate} /></MemoryRouter>)
    expect(screen.getByText(/Безопасная ошибка/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Создать новый отчёт' }))
    expect(onCreate).toHaveBeenCalledTimes(1)
  })
  it('renders approved partial blocks while excluding factual and evaluation bases', () => {
    const partial: CompanyReportResponse = {
      ...response,
      status: 'partial',
      report: {
        ...response.report!,
        usable_for_public_page: false,
        usable_for_future_scoring: true,
        datasets: { finance: { status: 'partial', source_time: { received_at: '2026-01-02T00:00:00Z' }, failure: { code: 'partial', message: 'Часть данных недоступна', retryable: false }, warnings: [{ code: 'finance_warning', message: 'Финансовое предупреждение' }] } },
        arbitration: { ...response.report!.arbitration!, role_summary: { respondent_count: 2 }, status_summary: { open_count: 1 }, result_summary: { returned_count: 1 } },
      },
      signals: { signals: [{ code: 'finance.net_loss', category: 'financial', direction: 'negative', strength: 'high', confidence: 'high', period: { kind: 'year', year: 2025 }, warnings: [{ code: 'signal_warning', message: 'Предупреждение сигнала' }], factual_basis: { secret: 'не показывать' } } as unknown as PublicSignal] },
      scoring: { level: 'medium', score_points: '12.00', confidence: { value: '0.80' }, reasons: [{ signal_code: 'finance.net_loss', contribution: '12.00', direction: 'negative' }], domain_breakdown: [{ category: 'financial', raw_points: '12.00', capped_points: '10.00' }] },
    }
    render(<MemoryRouter><CompanyReportContent inn="1234567890" response={partial} /></MemoryRouter>)
    expect(screen.getByText(/Часть данных недоступна/)).toBeTruthy()
    expect(screen.getByText('Финансовое предупреждение')).toBeTruthy()
    expect(screen.getByText(/respondent_count: 2/)).toBeTruthy()
    expect(screen.getByText(/open_count: 1/)).toBeTruthy()
    expect(screen.getByText(/returned_count: 1/)).toBeTruthy()
    expect(screen.getByText(/период: 2025/)).toBeTruthy()
    expect(screen.getByText('Предупреждение сигнала')).toBeTruthy()
    expect(screen.getByText('Разбивка по доменам')).toBeTruthy()
    expect(screen.queryByText('не показывать')).toBeNull()
    expect(screen.queryByText('evaluation_basis')).toBeNull()
  })
  it('passes only a minimal report identifier to the Claims route', () => {
    render(<MemoryRouter initialEntries={['/company/1234567890-test']}><Routes><Route path="/company/:key" element={<CompanyReportContent inn="1234567890" response={response} />} /><Route path="/claims" element={<LocationProbe />} /></Routes></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: 'Перейти к взысканию' }))
    expect(screen.getByText(/report_id=2e7e9d9f-5f3a-4d43-a8e8-2bb3c2adf6b1/)).toBeTruthy()
    expect(screen.queryByText(/companyReportContext/)).toBeNull()
  })
})
