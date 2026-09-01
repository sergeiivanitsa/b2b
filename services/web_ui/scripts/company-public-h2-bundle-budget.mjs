import { createHash } from 'node:crypto'
import { gzipSync } from 'node:zlib'
import { readdir, readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const SCHEMA = 'company_public_h2_bundle_budget_v1'
const ENTRY = 'src/companyPublicH2/main.tsx'
const FINANCE = 'src/companyPublicH2/FinanceCharts.tsx'
const ARBITRATION = 'src/companyPublicH2/ArbitrationCharts.tsx'
const BASE_COMMIT = '31b299ac88b5fac7d5c04082324fb122d63db7e7'
const BASE_MANIFEST_SHA256 = '68b1f2943514dccd8fbe0eee9923088d36a11847f610ac5c3474e33e7b0898b2'
const BASE_EAGER_RAW_BYTES = 313_122
const BASE_EAGER_GZIP_BYTES = 93_386
const FORBIDDEN = [
  '@playwright/test', '@axe-core/playwright', 'playwright-core', 'axe-core',
  'mc.yandex', 'webvisor', 'serviceWorker.register', 'navigator.sendBeacon',
]

function object(value, label) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${label} must be an object`)
  return value
}

function strings(value, label) {
  if (value === undefined) return []
  if (!Array.isArray(value) || value.some(item => typeof item !== 'string')) throw new Error(`${label} must be an array of strings`)
  return value
}

function emittedFiles(node, key) {
  if (typeof node.file !== 'string') throw new Error(`${key} has no emitted file`)
  return [node.file, ...strings(node.css, `${key}.css`), ...strings(node.assets, `${key}.assets`)]
}

function walk(viteManifest, rootKey, includeDynamic) {
  const files = new Set()
  const visited = new Set()
  const visit = key => {
    if (visited.has(key)) return
    visited.add(key)
    const node = object(viteManifest[key], `Vite node ${key}`)
    for (const file of emittedFiles(node, key)) files.add(file)
    for (const dependency of strings(node.imports, `${key}.imports`)) visit(dependency)
    if (includeDynamic) for (const dependency of strings(node.dynamicImports, `${key}.dynamicImports`)) visit(dependency)
  }
  visit(rootKey)
  return files
}

export function classifyCompanyPublicH2Closures(viteManifest) {
  object(viteManifest, 'Vite manifest')
  const entryNode = object(viteManifest[ENTRY], `Vite node ${ENTRY}`)
  if (entryNode.isEntry !== true) throw new Error('Company Public H2 entry is not the sole reviewed entry')
  for (const key of [FINANCE, ARBITRATION]) if (object(viteManifest[key], `Vite node ${key}`).isDynamicEntry !== true) throw new Error(`${key} is not a lazy entry`)
  const eager = walk(viteManifest, ENTRY, false)
  const all = walk(viteManifest, ENTRY, true)
  const financeRootFiles = emittedFiles(object(viteManifest[FINANCE], `Vite node ${FINANCE}`), FINANCE)
  const arbitrationRootFiles = emittedFiles(object(viteManifest[ARBITRATION], `Vite node ${ARBITRATION}`), ARBITRATION)
  if ([...financeRootFiles, ...arbitrationRootFiles].some(file => eager.has(file))) throw new Error('lazy asset is reachable from the eager closure')
  const finance = new Set([...walk(viteManifest, FINANCE, false)].filter(file => !eager.has(file)))
  const arbitration = new Set([...walk(viteManifest, ARBITRATION, false)].filter(file => !eager.has(file)))
  const classified = new Set([...eager, ...finance, ...arbitration])
  if ([...all].some(file => !classified.has(file)) || [...classified].some(file => !all.has(file))) throw new Error('H2 assets do not have a closed eager/finance/arbitration classification')
  if ([...eager].some(file => finance.has(file) || arbitration.has(file))) throw new Error('lazy asset is reachable from the eager closure')
  return Object.freeze({
    eager: Object.freeze([...eager].sort()),
    finance: Object.freeze([...finance].sort()),
    arbitration: Object.freeze([...arbitration].sort()),
    all: Object.freeze([...all].sort()),
  })
}

export function validateCompanyPublicH2BudgetShape(budget) {
  const source = object(budget, 'budget')
  const expectedKeys = ['assets', 'base', 'closures', 'eager_budget', 'manifest_sha256', 'schema_version']
  if (JSON.stringify(Object.keys(source).sort()) !== JSON.stringify(expectedKeys)) throw new Error('budget has unknown or missing keys')
  if (source.schema_version !== SCHEMA) throw new Error('unsupported bundle budget schema')
  const base = object(source.base, 'budget.base')
  if (base.commit !== BASE_COMMIT || base.manifest_sha256 !== BASE_MANIFEST_SHA256 || base.eager_raw_bytes !== BASE_EAGER_RAW_BYTES || base.eager_gzip_bytes !== BASE_EAGER_GZIP_BYTES) throw new Error('budget base identity is not the reviewed iteration-25 base')
  const assets = source.assets
  if (!Array.isArray(assets) || assets.length === 0) throw new Error('budget.assets must be nonempty')
  const paths = assets.map((asset, index) => {
    const record = object(asset, `budget.assets[${index}]`)
    if (JSON.stringify(Object.keys(record).sort()) !== JSON.stringify(['gzip_bytes', 'path', 'raw_bytes', 'sha256'].sort())) throw new Error('budget asset has unknown or missing keys')
    if (typeof record.path !== 'string' || !Number.isInteger(record.raw_bytes) || !Number.isInteger(record.gzip_bytes) || !/^[0-9a-f]{64}$/u.test(record.sha256)) throw new Error('budget asset is malformed')
    return record.path
  })
  if (new Set(paths).size !== paths.length) throw new Error('budget contains duplicate assets')
  const eager = object(source.eager_budget, 'budget.eager_budget')
  const required = ['approved_gzip_bytes', 'approved_raw_bytes', 'gzip_delta', 'rationale', 'raw_delta']
  if (JSON.stringify(Object.keys(eager).sort()) !== JSON.stringify(required.sort())) throw new Error('eager budget has unknown or missing keys')
  for (const key of ['approved_gzip_bytes', 'approved_raw_bytes', 'gzip_delta', 'raw_delta']) if (!Number.isInteger(eager[key])) throw new Error(`eager budget ${key} must be an integer`)
  if (eager.approved_raw_bytes - base.eager_raw_bytes !== eager.raw_delta || eager.approved_gzip_bytes - base.eager_gzip_bytes !== eager.gzip_delta) throw new Error('eager budget delta is inconsistent')
  if ((eager.raw_delta > 0 || eager.gzip_delta > 0) && (typeof eager.rationale !== 'string' || eager.rationale.length < 20)) throw new Error('positive eager delta requires an explicit reviewed rationale')
  return source
}

async function fileInventory(dist, closures) {
  const roleByPath = new Map()
  for (const [role, paths] of Object.entries({ eager: closures.eager, finance: closures.finance, arbitration: closures.arbitration })) {
    for (const path of paths) {
      const current = roleByPath.get(path)
      roleByPath.set(path, current ? `${current}+${role}` : role)
    }
  }
  const assets = []
  for (const path of closures.all) {
    if (!/^assets\/company-public-h2\.[A-Za-z0-9_-]{8,}\.(?:js|css)$/u.test(path)) throw new Error(`unexpected production asset path ${path}`)
    const content = await readFile(resolve(dist, path))
    const source = content.toString('utf8')
    for (const marker of FORBIDDEN) if (source.toLowerCase().includes(marker.toLowerCase())) throw new Error(`forbidden production marker ${marker} in ${path}`)
    assets.push({
      path,
      raw_bytes: content.byteLength,
      gzip_bytes: gzipSync(content, { level: 9, mtime: 0 }).byteLength,
      sha256: createHash('sha256').update(content).digest('hex'),
      role: roleByPath.get(path),
    })
  }
  const emitted = (await readdir(resolve(dist, 'assets'))).map(name => `assets/${name}`).sort()
  if (JSON.stringify(emitted) !== JSON.stringify(closures.all)) throw new Error('dist contains unknown or missing H2 assets')
  return assets
}

function assertProductManifest(productManifest, closures, assets) {
  const source = object(productManifest, 'Product H2 manifest')
  if (source.schema_version !== 'company_public_h2_asset_manifest_v1' || source.public_contract_version !== 'company_public_h2_v1') throw new Error('Product H2 manifest identity is invalid')
  if (typeof source.entry_js_path !== 'string' || typeof source.entry_css_path !== 'string') throw new Error('Product H2 entry paths are absent')
  const entryPaths = [source.entry_js_path.slice(1), source.entry_css_path.slice(1)].sort()
  if (JSON.stringify(entryPaths) !== JSON.stringify(closures.eager)) throw new Error('Product H2 eager closure differs from built bytes')
  const optional = strings(source.optional_chunk_paths, 'Product optional_chunk_paths').map(path => path.slice(1)).sort()
  const expectedOptional = [...new Set([...closures.finance, ...closures.arbitration])].sort()
  if (JSON.stringify(optional) !== JSON.stringify(expectedOptional)) throw new Error('Product H2 lazy closure differs from built bytes')
  if (!Array.isArray(source.assets) || source.assets.length !== assets.length) throw new Error('Product H2 asset inventory differs from built bytes')
  const actual = source.assets.map(item => {
    const record = object(item, 'Product asset')
    return { path: String(record.path).slice(1), sha256: record.sha256_hex, media: record.media_type }
  }).sort((left, right) => left.path.localeCompare(right.path))
  const expected = assets.map(item => ({ path: item.path, sha256: item.sha256, media: item.path.endsWith('.js') ? 'text/javascript' : 'text/css' })).sort((left, right) => left.path.localeCompare(right.path))
  if (JSON.stringify(actual) !== JSON.stringify(expected)) throw new Error('Product H2 manifest hashes differ from built bytes')
}

function budgetDocument(manifestSha256, closures, assets, baseGzipBytes, rationale) {
  const eagerAssets = assets.filter(item => closures.eager.includes(item.path))
  const eagerRaw = eagerAssets.reduce((total, item) => total + item.raw_bytes, 0)
  const eagerGzip = eagerAssets.reduce((total, item) => total + item.gzip_bytes, 0)
  return {
    assets: assets.map(({ path, raw_bytes, gzip_bytes, sha256 }) => ({ path, raw_bytes, gzip_bytes, sha256 })),
    base: { commit: BASE_COMMIT, manifest_sha256: BASE_MANIFEST_SHA256, eager_raw_bytes: BASE_EAGER_RAW_BYTES, eager_gzip_bytes: baseGzipBytes },
    closures,
    eager_budget: {
      approved_gzip_bytes: eagerGzip,
      approved_raw_bytes: eagerRaw,
      gzip_delta: eagerGzip - baseGzipBytes,
      raw_delta: eagerRaw - BASE_EAGER_RAW_BYTES,
      rationale,
    },
    manifest_sha256: manifestSha256,
    schema_version: SCHEMA,
  }
}

async function verifyOrGenerate({ generate }) {
  const web = resolve(import.meta.dirname, '..')
  const dist = resolve(web, 'dist-company-public-h2')
  const manifestPath = resolve(dist, '.vite/manifest.json')
  const manifestBytes = await readFile(manifestPath)
  const viteManifest = JSON.parse(manifestBytes.toString('utf8'))
  const manifestSource = manifestBytes.toString('utf8').toLowerCase()
  for (const marker of FORBIDDEN.slice(0, 4)) if (manifestSource.includes(marker.toLowerCase())) throw new Error(`test dependency ${marker} appears in the production module graph`)
  const closures = classifyCompanyPublicH2Closures(viteManifest)
  const assets = await fileInventory(dist, closures)
  const manifestSha256 = createHash('sha256').update(manifestBytes).digest('hex')
  const productPath = resolve(web, '../product_api/src/product_api/company_reports/company_card_v2/public_h2_asset_manifest.json')
  if (!generate) assertProductManifest(JSON.parse(await readFile(productPath, 'utf8')), closures, assets)
  const budgetPath = resolve(web, 'company-public-h2-bundle-budget.json')
  if (generate) {
    const output = budgetDocument(
      manifestSha256,
      closures,
      assets,
      BASE_EAGER_GZIP_BYTES,
      'Task 2 adds the reviewed compact breadcrumb presentation and deterministic legal-form shortening to the H2 entry; routes, signed DTO fields, the hero title, report facts, and production dependencies remain unchanged.',
    )
    return `${JSON.stringify(output, null, 2)}\n`
  }
  const budget = validateCompanyPublicH2BudgetShape(JSON.parse(await readFile(budgetPath, 'utf8')))
  if (budget.manifest_sha256 !== manifestSha256) throw new Error('Vite manifest identity differs from the reviewed budget')
  const actualAssets = assets.map(({ path, raw_bytes, gzip_bytes, sha256 }) => ({ path, raw_bytes, gzip_bytes, sha256 }))
  if (JSON.stringify(budget.assets) !== JSON.stringify(actualAssets)) throw new Error('asset bytes differ from the reviewed budget')
  if (JSON.stringify(budget.closures) !== JSON.stringify(closures)) throw new Error('bundle closures differ from the reviewed budget')
  const eagerAssets = assets.filter(item => closures.eager.includes(item.path))
  if (eagerAssets.reduce((total, item) => total + item.raw_bytes, 0) !== budget.eager_budget.approved_raw_bytes || eagerAssets.reduce((total, item) => total + item.gzip_bytes, 0) !== budget.eager_budget.approved_gzip_bytes) throw new Error('positive eager delta is not approved by the exact budget')
}

async function main() {
  const generate = process.argv.includes('--print')
  if (generate === process.argv.includes('--verify')) throw new Error('choose exactly one of --print or --verify')
  const output = await verifyOrGenerate({ generate })
  if (output !== undefined) process.stdout.write(output)
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main()
