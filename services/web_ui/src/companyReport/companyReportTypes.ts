export type CompanyReportStatus = 'complete' | 'partial' | 'failed'

export type CompanyReportAccepted = { report_id: string; status: 'pending'; reused: boolean }
export type CompanyReportLifecycle = {
  report_id: string
  status: 'pending' | CompanyReportStatus
  started_at: string
  generated_at?: string | null
  finished_at?: string | null
  fresh_until?: string | null
  public_document_path?: string | null
}

export type PublicBlockId =
  | 'breadcrumbs' | 'identity_status' | 'known_summary' | 'in_page_navigation'
  | 'coverage_checked_at' | 'requisites' | 'finance' | 'arbitration'
  | 'bankruptcy' | 'tax' | 'management' | 'sources_limitations'
  | 'neutral_actions' | 'internal_links'
export type FactualBlockId = 'requisites' | 'finance' | 'arbitration' | 'bankruptcy' | 'tax' | 'management'
export type DatasetId = 'counterparty' | 'finance' | 'arbitration' | 'bankruptcy' | 'tax_info'
export type CoverageState = 'available' | 'available_empty' | 'not_found' | 'not_requested' | 'partial' | 'failed' | 'conflict'
export type PublicFinanceMetricId =
  | 'total_assets' | 'non_current_assets' | 'current_assets' | 'inventories' | 'accounts_receivable'
  | 'cash_and_equivalents' | 'equity' | 'long_term_liabilities' | 'short_term_liabilities'
  | 'short_term_borrowings' | 'accounts_payable' | 'revenue' | 'cost_of_sales' | 'gross_profit'
  | 'operating_profit' | 'profit_before_tax' | 'net_profit' | 'net_cash_flow' | 'cash_at_start' | 'cash_at_end'
export type LimitationCode =
  | 'address_not_requested' | 'address_marked_inaccurate' | 'legal_form_mapping_unknown'
  | 'identity_status_mapping_unknown' | 'identity_status_conflict' | 'finance_unit_evidence_not_passed'
  | 'finance_series_conflict' | 'finance_dataset_not_found' | 'finance_dataset_failed'
  | 'arbitration_identity_conflict' | 'arbitration_target_identity_incomplete' | 'arbitration_unknown_currency'
  | 'arbitration_partial_slice' | 'arbitration_malformed_records' | 'legacy_arbitration_role_detail_unavailable'
  | 'arbitration_dataset_not_found' | 'arbitration_dataset_failed' | 'tax_schema_gate_not_passed'
  | 'tax_operational_gate_not_passed' | 'bankruptcy_schema_gate_not_passed' | 'bankruptcy_operational_gate_not_passed'
  | 'management_privacy_gate_not_passed' | 'management_schema_gate_not_passed' | 'management_operational_gate_not_passed'

export type PublicMoney = Readonly<{ source_decimal: string; source_unit: 'thousand_rub'; rub_decimal: string; display_value: string; unit_policy_version: string }>
export type PublicPercentChange = Readonly<{ exact_percent: string; display_value: string; current_year: number; previous_year: number; formula_version: 'finance_yoy_v1' }>
export type CompanyPublicIdentity = Readonly<{ legal_full_name: string; legal_short_name: string | null; display_name: string; inn: string; status_code: null; status_label: null; status_effective_at: null }>
export type PublicRegion = Readonly<{ code: string | null; name: string | null }>
export type PublicAddress = Readonly<{ display_line: string; postal_code: string | null; country: string | null; region: string | null; city: string | null; street: string | null; house: string | null; office: string | null; is_inaccuracy: boolean | null }>
export type RequisitesBlock = Readonly<{ legal_form: null; ogrn_or_ogrnip: string | null; kpp: string | null; registration_date: string | null; dissolved_date: string | null; region: PublicRegion | null; legal_address: PublicAddress | null }>
export type FinanceMetric = Readonly<{ metric_id: PublicFinanceMetricId; year: number; money: null; yoy: PublicPercentChange }>
export type FinanceBlock = Readonly<{ unit_policy_version: null; metrics: readonly FinanceMetric[] }>
export type ArbitrationClaimAmount = Readonly<{ role: 'plaintiff' | 'respondent'; currency: string; exact_decimal: string; display_value: string }>
export type PublicArbitrationCase = Readonly<{ case_number: string; date_start: string | null; date_update: string | null; attributed_role: 'plaintiff' | 'respondent' | 'applicant' | 'creditor' | 'debtor' | 'other' | 'unattributed'; claim_amount: ArbitrationClaimAmount | null }>
export type ArbitrationBlock = Readonly<{ total_cases: number; returned_cases: number; normalized_case_count: number; malformed_count: number; limit: number; offset: number; role_counts: Readonly<Record<'plaintiff' | 'respondent' | 'applicant' | 'creditor' | 'debtor' | 'other', number>>; unattributed_count: number; status_counts: Readonly<Record<'open' | 'completed' | 'unknown', number>>; result_counts: Readonly<Record<'satisfied_full' | 'refused' | 'returned' | 'undefined' | 'other', number>>; claim_amounts: readonly ArbitrationClaimAmount[]; selected_cases: readonly PublicArbitrationCase[] }>
export type BankruptcyBlock = Readonly<{ total: number; returned: number; limit: number; offset: number; typed_counts: Readonly<Record<'debtor_intention' | 'creditor_intention' | 'unknown', number>>; publications: readonly Readonly<{ safe_reference: string | null; publication_date: string | null; kind: 'debtor_intention' | 'creditor_intention' | 'unknown'; message: string; participant_role: 'debtor' | 'creditor' | 'other' | 'unknown' }>[]; disclaimer: string }>
export type TaxBlock = Readonly<{ unpaid_debt_indicator: boolean; message: string; as_of_date: string | null; records: readonly Readonly<{ record_type: string; document_date: string | null; period: string | null; amount: PublicMoney | null }>[] }>
export type ManagementBlock = Readonly<{ managers: readonly Readonly<{ name: string; role: string; appointed_at: string | null; is_inaccuracy: boolean | null }>[]; owners: readonly Readonly<{ name_or_org: string; owner_type: 'person' | 'organization'; organization_inn: string | null; organization_ogrn: string | null; share_percent_decimal: string | null; share_display: string | null; ownership_effective_at: string | null }>[] }>
export type CompanyPublicH1Blocks = Readonly<{ requisites: RequisitesBlock; finance: FinanceBlock | null; arbitration: ArbitrationBlock | null; bankruptcy: null; tax: null; management: null }>
export type PublicCoverageItem = Readonly<{ block_id: FactualBlockId; dataset: DatasetId; state: CoverageState; total: number | null; returned: number | null; limit: number | null; offset: number | null; limitation_codes: readonly LimitationCode[] }>
export type PublicSourceItem = Readonly<{ dataset: DatasetId; received_at: string; effective_at: string | null; period: string | null; normalization_version: 'counterparty_normalizer_v1' | 'finance_normalizer_v1' | 'arbitration_normalizer_v1' | 'arbitration_normalizer_v2' }>
export type PublicLimitation = Readonly<{ code: LimitationCode; block_id: PublicBlockId | null; field_id: 'identity.status_label' | 'requisites.legal_address' | 'requisites.legal_form' | 'finance.metrics.money' | 'finance.metrics.yoy' | 'arbitration.selected_cases.attributed_role' | 'arbitration.claim_amounts' | null; message: string }>
export type PublicAction = Readonly<{ action_id: 'check_another_company' | 'prepare_claim'; label: 'Проверить другую компанию' | 'Подготовить претензию'; path: string }>
export type PublicBreadcrumb = Readonly<{ label: string; path: string }>
export type PublicInternalLink = Readonly<{ label: string; path: string; relation: string }>
export type CompanyPublicH1Response = Readonly<{ contract_version: 'company_public_h1_v1'; report_id: string; report_version: '1' | '2'; projection_scope: 'published' | 'latest_unpublished'; canonical_path: string; indexable: boolean; checked_at: string; checked_date: string; checked_date_display: string; identity: CompanyPublicIdentity; block_order: readonly PublicBlockId[]; blocks: CompanyPublicH1Blocks; coverage: readonly PublicCoverageItem[]; sources: readonly PublicSourceItem[]; limitations: readonly PublicLimitation[]; actions: readonly PublicAction[]; breadcrumbs: readonly PublicBreadcrumb[]; internal_links: readonly PublicInternalLink[] }>
