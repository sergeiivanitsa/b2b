export type CompanyReportStatus = 'complete' | 'partial' | 'failed'

export type SafeWarning = {
  code: string
  dataset?: string | null
  message: string
}

export type SafeFailure = { code: string; message: string; retryable: boolean }

export type CompanyReportResponse = {
  report_id: string
  status: CompanyReportStatus
  started_at: string
  generated_at?: string | null
  finished_at?: string | null
  fresh_until?: string | null
  report?: PublicReportSnapshot | null
  signals?: PublicSignals | null
  scoring?: PublicScoring | null
  ai_explanation?: PublicAiExplanation | null
  failure?: SafeFailure | null
}

export type CompanyReportAccepted = { report_id: string; status: 'pending'; reused: boolean }
export type CompanyReportLifecycle = {
  report_id: string
  status: 'pending' | CompanyReportStatus
  started_at: string
  generated_at?: string | null
  finished_at?: string | null
  fresh_until?: string | null
}

export type PublicReportSnapshot = {
  status: CompanyReportStatus
  counterparty?: CounterpartyFacts | null
  finance?: FinanceFacts | null
  arbitration?: ArbitrationFacts | null
  datasets: Record<string, PublicDataset>
  completeness: Completeness
  freshness: Freshness
  warnings: SafeWarning[]
  usable_for_public_page: boolean
  usable_for_future_scoring: boolean
}

export type CounterpartyFacts = {
  short_name?: string | null; full_name?: string | null; inn?: string | null
  ogrn?: string | null; kpp?: string | null; legal_form?: string | null
  is_active?: boolean | null; status_code?: string | null; status_text?: string | null
  registration_date?: string | null; dissolved_date?: string | null
  years_from_registration?: string | number | null
  address?: { line_address?: string | null } | null
}

export type FinancePeriod = {
  year?: number | null
  total_assets?: string | null; current_assets?: string | null; cash_and_equivalents?: string | null
  equity?: string | null; accounts_payable?: string | null; revenue?: string | null; net_profit?: string | null
}
export type FinanceFacts = { latest_year?: number | null; years?: number[]; unit?: string | null; periods?: FinancePeriod[]; data?: FinancePeriod[] }
export type ArbitrationFacts = {
  total_cases?: number | null; returned_cases?: number | null; is_complete?: boolean | null
  role_summary?: Record<string, number> | null; status_summary?: Record<string, number> | null
  result_summary?: Record<string, number> | null
  claim_amounts_by_currency?: Record<string, { plaintiff?: string | null; respondent?: string | null }> | null
}
export type PublicDataset = { status: string; source_time?: { received_at: string } | null; warnings?: SafeWarning[]; failure?: SafeFailure | null }
export type Completeness = { available_count: number; required_count: number; percent: number; missing_datasets: string[]; unavailable_datasets: string[] }
export type Freshness = { generated_at: string; warnings?: SafeWarning[] }
export type PublicSignals = { signals: PublicSignal[]; warnings?: SafeWarning[] }
export type SignalPeriod =
  | { kind: 'no_period'; as_of: string }
  | { kind: 'date'; value: string }
  | { kind: 'date_range'; start: string; end: string }
  | { kind: 'year'; year: number }
  | { kind: 'year_range'; start_year: number; end_year: number }
export type PublicSignal = { code: string; category: string; direction: string; strength: string; confidence: string; period?: SignalPeriod; warnings?: SafeWarning[] }
export type PublicScoring = {
  level: string; score_points: string | null; confidence: Record<string, unknown>
  reasons: Array<{ signal_code: string; contribution?: string; category?: string; direction?: string }>
  domain_breakdown: Array<{ category: string; raw_points?: string; capped_points?: string; considered_signal_codes?: string[]; suppressed_rule_codes?: string[] }>
  warnings?: SafeWarning[]
}
export type PublicAiExplanation = {
  status: string
  explanation?: { overall_conclusion: string; recovery_factors: string[]; key_risks: string[]; urgency: string; recommended_next_step: string; limitations: string[] } | null
}
export type CompanyReportContext = { inn: string; companyName?: string; reportId?: string }
