import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const H2_ENTRY_SUFFIX = 'src/companyPublicH2/main.tsx'
const SUPPORTED_ASSET = /\.(?:js|css)$/u
const CONTENT_ADDRESSED_ASSET = /^assets\/company-public-h2\.[A-Za-z0-9_-]{8,}\.(?:js|css)$/u

function stringList(value, path) {
  if (value === undefined) return []
  if (!Array.isArray(value) || value.some(item => typeof item !== 'string')) {
    throw new Error(`${path} must be an array of strings`)
  }
  return value
}

/** Close a Vite graph without touching the filesystem. */
export function collectCompanyPublicH2AssetGraph(viteManifest) {
  if (viteManifest === null || typeof viteManifest !== 'object' || Array.isArray(viteManifest)) {
    throw new Error('Vite manifest must be an object')
  }
  const entries = Object.entries(viteManifest)
    .filter(([key, node]) => node !== null && typeof node === 'object' && !Array.isArray(node) && node.isEntry === true && key.endsWith(H2_ENTRY_SUFFIX))
    .map(([key]) => key)
  if (entries.length !== 1) throw new Error('expected exactly one Company Public H2 Vite entry')

  const entryKey = entries[0]
  const reachable = new Set()
  const dynamic = new Set()
  const visited = new Set()

  function visit(key, reachedDynamically) {
    const node = viteManifest[key]
    if (node === null || typeof node !== 'object' || Array.isArray(node)) {
      throw new Error(`missing reachable Vite manifest node ${key}`)
    }
    const visitKey = `${reachedDynamically ? 'dynamic' : 'static'}:${key}`
    if (visited.has(visitKey)) return
    visited.add(visitKey)

    if (typeof node.file !== 'string') throw new Error(`reachable Vite manifest node ${key} has no file`)
    const emitted = [node.file, ...stringList(node.css, `${key}.css`), ...stringList(node.assets, `${key}.assets`)]
    for (const file of emitted) {
      if (!SUPPORTED_ASSET.test(file)) throw new Error(`reachable H2 asset has unsupported type: ${file}`)
      reachable.add(file)
      if (reachedDynamically) dynamic.add(file)
    }
    for (const dependency of stringList(node.imports, `${key}.imports`)) visit(dependency, reachedDynamically)
    for (const dependency of stringList(node.dynamicImports, `${key}.dynamicImports`)) visit(dependency, true)
  }
  visit(entryKey, false)

  const entry = viteManifest[entryKey]
  if (!entry.file.endsWith('.js')) throw new Error('H2 entry must be JavaScript')
  const entryCss = stringList(entry.css, `${entryKey}.css`).filter(file => file.endsWith('.css'))
  if (entryCss.length !== 1) throw new Error('H2 entry must have exactly one entry CSS asset')

  // The v1 schema names one entry JS/CSS pair. Every other reachable emitted
  // file is retained in optional_chunk_paths, including a static Rollup chunk.
  const entryFiles = new Set([entry.file, entryCss[0]])
  const optional = new Set([...dynamic, ...[...reachable].filter(file => !entryFiles.has(file))])
  for (const file of entryFiles) optional.delete(file)
  for (const file of reachable) {
    if (!CONTENT_ADDRESSED_ASSET.test(file)) throw new Error(`unexpected H2 asset ${file}`)
  }
  return Object.freeze({
    entryCssFile: entryCss[0],
    entryJsFile: entry.file,
    optionalFiles: Object.freeze([...optional].sort()),
    reachableFiles: Object.freeze([...reachable].sort()),
  })
}

export async function buildCompanyPublicH2Manifest({ dist, target, verify = false }) {
  const viteManifest = JSON.parse(await readFile(resolve(dist, '.vite/manifest.json'), 'utf8'))
  const graph = collectCompanyPublicH2AssetGraph(viteManifest)
  const assets = []
  for (const basename of graph.reachableFiles) {
    const content = await readFile(resolve(dist, basename))
    const extension = basename.endsWith('.js') ? 'js' : 'css'
    const source = content.toString('utf8')
    if (/mc\.yandex|webvisor|window\.ym\s*\(|\/internal\/whoami|AuthProvider|\/company-reports\/|\/company-report-presentations/iu.test(source)) {
      throw new Error(`forbidden H2 bundle marker in ${basename}`)
    }
    assets.push({
      media_type: extension === 'js' ? 'text/javascript' : 'text/css',
      path: `/${basename}`,
      sha256_hex: createHash('sha256').update(content).digest('hex'),
    })
  }
  const output = `${JSON.stringify({
    assets,
    canonical_json_profile: 'company_public_h2_cjson_v1',
    entry_css_path: `/${graph.entryCssFile}`,
    entry_js_path: `/${graph.entryJsFile}`,
    optional_chunk_paths: graph.optionalFiles.map(file => `/${file}`),
    public_contract_version: 'company_public_h2_v1',
    schema_version: 'company_public_h2_asset_manifest_v1',
  })}\n`
  if (verify) {
    if (await readFile(target, 'utf8') !== output) throw new Error('tracked H2 asset manifest does not match build')
    return output
  }
  await mkdir(resolve(target, '..'), { recursive: true })
  await writeFile(target, output, 'utf8')
  return output
}

async function main() {
  const web = resolve(import.meta.dirname, '..')
  await buildCompanyPublicH2Manifest({
    dist: resolve(web, 'dist-company-public-h2'),
    target: resolve(web, '../product_api/src/product_api/company_reports/company_card_v2/public_h2_asset_manifest.json'),
    verify: process.argv.includes('--verify'),
  })
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main()
