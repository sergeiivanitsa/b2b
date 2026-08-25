/* Checked-in pure assertions for the iteration-22 real-browser evidence. */
const profiles = ['saved-artifact', 'deterministic-fallback', 'gate-closed', 'partial-long-limitations', 'long-public-strings']
const widths = [320, 390, 768, 1024, 1199, 1200, 1440]
const requiredChecks = [
  'http_200', 'ssr_before_takeover', 'takeover', 'unchanged_head', 'ssr_react_parity',
  'exact_binding', 'exact_links', 'one_primary_cta', 'inert_reserver', 'minimum_targets',
  'exact_coverage', 'no_chart_art', 'no_overflow', 'no_overlap', 'cta_breakpoint',
  'reduced_motion', 'network_isolated', 'no_console_errors', 'valid_distinct_profile',
  'keyboard_anchor', 'zoom_200',
]

export function assertAggregate(aggregate) {
  if (aggregate.executed !== 35 || aggregate.passed !== 35 || aggregate.failed !== 0 || aggregate.skipped !== 0) {
    throw new Error('matrix must be exactly 35 green cells')
  }
  if (JSON.stringify(aggregate.profiles) !== JSON.stringify(profiles) || JSON.stringify(aggregate.widths) !== JSON.stringify(widths)) {
    throw new Error('matrix profiles or widths differ from the approved 5x7 set')
  }
  if (!aggregate.allowed_requests) throw new Error('fixture issued an unapproved request')
  if (!Array.isArray(aggregate.coverage_ids) || aggregate.coverage_ids.length !== 13 || new Set(aggregate.coverage_ids).size !== 13) {
    throw new Error('aggregate must declare the exact 13-row coverage surface')
  }
  const keys = new Set()
  const signatures = new Map()
  for (const cell of aggregate.cells ?? []) {
    keys.add(`${cell.profile}:${cell.width}`)
    for (const name of requiredChecks) {
      if (cell.checks?.[name] !== true) throw new Error(`${cell.profile}/${cell.width}: required check failed or missing: ${name}`)
    }
    if ((cell.forbidden_requests?.length ?? 0) !== 0 || (cell.unexpected_http?.length ?? 0) !== 0
      || (cell.unexpected_statuses?.length ?? 0) !== 0
      || (cell.console_errors?.length ?? 0) !== 0 || (cell.runtime_exceptions?.length ?? 0) !== 0
      || (cell.loading_failures?.length ?? 0) !== 0) {
      throw new Error(`${cell.profile}/${cell.width}: browser isolation/error evidence is not empty`)
    }
    const signature = JSON.stringify(cell.measurements?.before?.profileSignature ?? null)
    if (signatures.has(cell.profile) && signatures.get(cell.profile) !== signature) {
      throw new Error(`${cell.profile}: profile signature changed across widths`)
    }
    signatures.set(cell.profile, signature)
  }
  if (keys.size !== 35 || signatures.size !== 5 || new Set(signatures.values()).size !== 5) {
    throw new Error('matrix cells or five observable profile signatures are incomplete')
  }
  return true
}
