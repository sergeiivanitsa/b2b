import { describe, expect, it } from 'vitest'
// Release scripts intentionally remain Node ESM and are exercised as pure
// functions here before any filesystem-backed release check runs.
// @ts-expect-error no declaration file is emitted for the release script
import { classifyCompanyPublicH2Closures, validateCompanyPublicH2BudgetShape } from '../../scripts/company-public-h2-bundle-budget.mjs'

const entry = 'src/companyPublicH2/main.tsx'
const finance = 'src/companyPublicH2/FinanceCharts.tsx'
const arbitration = 'src/companyPublicH2/ArbitrationCharts.tsx'

describe('Company Public H2 bundle budget', () => {
  it('separates the eager closure from both lazy roots and preserves shared lazy code', () => {
    expect(classifyCompanyPublicH2Closures({
      [entry]: { file: 'assets/company-public-h2.entry0000.js', css: ['assets/company-public-h2.entry0000.css'], dynamicImports: [finance, arbitration], isEntry: true },
      [finance]: { file: 'assets/company-public-h2.finance0.js', imports: [entry, 'shared.ts'], isDynamicEntry: true },
      [arbitration]: { file: 'assets/company-public-h2.arbitrat.js', imports: [entry, 'shared.ts'], isDynamicEntry: true },
      'shared.ts': { file: 'assets/company-public-h2.shared00.js' },
    })).toEqual({
      eager: ['assets/company-public-h2.entry0000.css', 'assets/company-public-h2.entry0000.js'],
      finance: ['assets/company-public-h2.finance0.js', 'assets/company-public-h2.shared00.js'],
      arbitration: ['assets/company-public-h2.arbitrat.js', 'assets/company-public-h2.shared00.js'],
      all: ['assets/company-public-h2.arbitrat.js', 'assets/company-public-h2.entry0000.css', 'assets/company-public-h2.entry0000.js', 'assets/company-public-h2.finance0.js', 'assets/company-public-h2.shared00.js'],
    })
  })

  it('rejects a lazy root that is absent or reachable from the eager graph', () => {
    expect(() => classifyCompanyPublicH2Closures({
      [entry]: { file: 'assets/company-public-h2.entry0000.js', imports: [finance], dynamicImports: [finance, arbitration], isEntry: true },
      [finance]: { file: 'assets/company-public-h2.finance0.js', isDynamicEntry: true },
      [arbitration]: { file: 'assets/company-public-h2.arbitrat.js', isDynamicEntry: true },
    })).toThrow(/lazy asset is reachable from the eager closure/u)
  })

  it('requires an explicit consistent rationale for every positive eager delta', () => {
    const valid = {
      schema_version: 'company_public_h2_bundle_budget_v1',
      manifest_sha256: 'b'.repeat(64),
      base: {
        commit: '31b299ac88b5fac7d5c04082324fb122d63db7e7',
        manifest_sha256: '68b1f2943514dccd8fbe0eee9923088d36a11847f610ac5c3474e33e7b0898b2',
        eager_raw_bytes: 313122,
        eager_gzip_bytes: 93386,
      },
      assets: [{ path: 'assets/company-public-h2.entry0000.js', raw_bytes: 313123, gzip_bytes: 93387, sha256: 'a'.repeat(64) }],
      closures: { eager: ['assets/company-public-h2.entry0000.js'], finance: [], arbitration: [], all: ['assets/company-public-h2.entry0000.js'] },
      eager_budget: { approved_raw_bytes: 313123, approved_gzip_bytes: 93387, raw_delta: 1, gzip_delta: 1, rationale: 'Reviewed iteration-25 safe-area and layout reservation delta.' },
    }
    expect(validateCompanyPublicH2BudgetShape(valid)).toBe(valid)
    expect(() => validateCompanyPublicH2BudgetShape({ ...valid, eager_budget: { ...valid.eager_budget, rationale: '' } })).toThrow(/requires an explicit reviewed rationale/u)
    expect(() => validateCompanyPublicH2BudgetShape({ ...valid, eager_budget: { ...valid.eager_budget, raw_delta: 2 } })).toThrow(/delta is inconsistent/u)
  })
})
