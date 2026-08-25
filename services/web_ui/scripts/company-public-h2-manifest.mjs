import { createHash } from 'node:crypto'
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises'
import { resolve, relative, sep } from 'node:path'

const web = resolve(import.meta.dirname, '..')
const dist = resolve(web, 'dist-company-public-h2')
const target = resolve(web, '../product_api/src/product_api/company_reports/company_card_v2/public_h2_asset_manifest.json')
const files = []
async function walk(directory) { for (const item of await readdir(directory, { withFileTypes: true })) { const absolute = resolve(directory, item.name); if (item.isDirectory()) await walk(absolute); else files.push(absolute) } }
await walk(resolve(dist, 'assets'))
const assets = []
for (const file of files.sort()) {
  const basename = relative(resolve(dist, 'assets'), file).split(sep).join('/')
  if (!/^company-public-h2\.[A-Za-z0-9_-]{8,}\.(js|css)$/.test(basename)) throw new Error(`unexpected H2 asset ${basename}`)
  const content = await readFile(file); const extension = basename.endsWith('.js') ? 'js' : 'css'
  const text = extension === 'js' ? content.toString('utf8') : content.toString('utf8')
  if (/mc\.yandex|webvisor|window\.ym\s*\(|\/internal\/whoami|AuthProvider|\/company-reports\/|\/company-report-presentations/i.test(text)) throw new Error(`forbidden H2 bundle marker in ${basename}`)
  assets.push({ media_type: extension === 'js' ? 'text/javascript' : 'text/css', path: `/assets/${basename}`, sha256_hex: createHash('sha256').update(content).digest('hex') })
}
assets.sort((a, b) => a.path.localeCompare(b.path))
const js = assets.filter(asset => asset.media_type === 'text/javascript'); const css = assets.filter(asset => asset.media_type === 'text/css')
if (js.length !== 1 || css.length !== 1) throw new Error('H2 bundle must have exactly one JS and one CSS asset')
const output = `${JSON.stringify({ assets, canonical_json_profile: 'company_public_h2_cjson_v1', entry_css_path: css[0].path, entry_js_path: js[0].path, optional_chunk_paths: [], public_contract_version: 'company_public_h2_v1', schema_version: 'company_public_h2_asset_manifest_v1' })}\n`
if (process.argv.includes('--verify')) { if (await readFile(target, 'utf8') !== output) throw new Error('tracked H2 asset manifest does not match build'); process.exit(0) }
await mkdir(resolve(target, '..'), { recursive: true }); await writeFile(target, output, 'utf8')
