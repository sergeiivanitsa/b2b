/* Disposable same-origin Product/H2 asset proxy. It never accepts an external origin. */
import { createHash } from 'node:crypto'
import { createReadStream } from 'node:fs'
import { lstat, readFile, realpath } from 'node:fs/promises'
import { createServer, request as requestHttp } from 'node:http'
import { isAbsolute, resolve, sep } from 'node:path'
import { pipeline } from 'node:stream/promises'
import { parseArgs } from 'node:util'
import { fileURLToPath } from 'node:url'

const ASSET_PATH = /^\/assets\/company-public-h2\.[A-Za-z0-9_-]{8,}\.(?:js|css)$/u
const FORWARDED_REQUEST_HEADERS = ['accept', 'accept-language', 'if-modified-since', 'if-none-match', 'user-agent']
const EXCLUDED_RESPONSE_HEADERS = new Set(['connection', 'content-length', 'keep-alive', 'proxy-authenticate', 'proxy-authorization', 'te', 'trailer', 'transfer-encoding', 'upgrade'])

export function parseLoopbackOrigin(value, label) {
  let url
  try { url = new URL(value) } catch { throw new Error(`${label} must be an absolute URL`) }
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || url.port === '' || url.pathname !== '/' || url.search !== '' || url.hash !== '' || url.username !== '' || url.password !== '') {
    throw new Error(`${label} must be an explicit http://127.0.0.1:<port> origin`)
  }
  return url.origin
}

export function parseListenPort(value) {
  if (!/^[1-9][0-9]{0,4}$/u.test(value)) throw new Error('listen port must be a positive decimal integer')
  const port = Number(value)
  if (port > 65_535) throw new Error('listen port is out of range')
  return port
}

function manifestAssetMap(source) {
  if (source?.schema_version !== 'company_public_h2_asset_manifest_v1' || source.public_contract_version !== 'company_public_h2_v1' || !Array.isArray(source.assets)) throw new Error('asset manifest identity is invalid')
  const assets = new Map()
  for (const item of source.assets) {
    if (item === null || typeof item !== 'object' || !ASSET_PATH.test(item.path) || !/^[0-9a-f]{64}$/u.test(item.sha256_hex)) throw new Error('asset manifest entry is malformed')
    if (assets.has(item.path)) throw new Error('asset manifest contains a duplicate path')
    const mediaType = item.path.endsWith('.js') ? 'text/javascript; charset=utf-8' : 'text/css; charset=utf-8'
    if (item.media_type !== mediaType.split(';')[0]) throw new Error('asset manifest media type is inconsistent')
    assets.set(item.path, Object.freeze({ sha256: item.sha256_hex, mediaType }))
  }
  if (!assets.has(source.entry_js_path) || !assets.has(source.entry_css_path)) throw new Error('asset manifest entry files are absent')
  if (!Array.isArray(source.optional_chunk_paths) || source.optional_chunk_paths.some(path => !assets.has(path))) throw new Error('asset manifest lazy paths are inconsistent')
  return assets
}

export async function loadVerifiedAssets(assetRoot, assetManifestPath) {
  if (!isAbsolute(assetRoot) || !isAbsolute(assetManifestPath)) throw new Error('asset root and manifest path must be absolute')
  const root = await realpath(assetRoot)
  const manifest = JSON.parse(await readFile(assetManifestPath, 'utf8'))
  const declared = manifestAssetMap(manifest)
  const verified = new Map()
  for (const [publicPath, metadata] of declared) {
    const candidate = resolve(root, `.${publicPath}`)
    if (!candidate.startsWith(`${root}${sep}`)) throw new Error('asset path escapes the reviewed root')
    const info = await lstat(candidate)
    if (!info.isFile() || info.isSymbolicLink()) throw new Error('asset must be a regular non-symlink file')
    const bytes = await readFile(candidate)
    if (createHash('sha256').update(bytes).digest('hex') !== metadata.sha256) throw new Error('asset hash mismatch')
    verified.set(publicPath, Object.freeze({ ...metadata, absolutePath: candidate, size: bytes.byteLength }))
  }
  return Object.freeze({ root, manifest, assets: verified })
}

function writeSafeError(response, status, message) {
  const body = Buffer.from(`${message}\n`, 'utf8')
  response.writeHead(status, { 'Content-Type': 'text/plain; charset=utf-8', 'Content-Length': String(body.byteLength), 'Cache-Control': 'no-store' })
  response.end(body)
}

async function proxyProduct(request, response, productOrigin, publicOrigin) {
  if (request.method !== 'GET' && request.method !== 'HEAD') { writeSafeError(response, 405, 'method not allowed'); return }
  const target = new URL(request.url ?? '/', productOrigin)
  if (target.origin !== productOrigin) { writeSafeError(response, 400, 'invalid request target'); return }
  const headers = { host: new URL(publicOrigin).host }
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers[name]
    if (typeof value === 'string') headers[name] = value
  }
  const upstream = await new Promise((resolveUpstream, rejectUpstream) => {
    const upstreamRequest = requestHttp(target, { method: request.method, headers, signal: AbortSignal.timeout(15_000) }, resolveUpstream)
    upstreamRequest.once('error', rejectUpstream)
    upstreamRequest.end()
  })
  const responseHeaders = {}
  for (const [name, value] of Object.entries(upstream.headers)) {
    if (value !== undefined && !EXCLUDED_RESPONSE_HEADERS.has(name.toLowerCase())) responseHeaders[name] = value
  }
  const location = upstream.headers.location
  if (location !== undefined) {
    const redirect = new URL(location, productOrigin)
    if (redirect.origin !== productOrigin && redirect.origin !== publicOrigin) throw new Error('Product emitted an external redirect')
    responseHeaders.location = `${publicOrigin}${redirect.pathname}${redirect.search}${redirect.hash}`
  }
  if (upstream.headers['content-length'] !== undefined) responseHeaders['content-length'] = upstream.headers['content-length']
  response.writeHead(upstream.statusCode ?? 502, responseHeaders)
  if (request.method === 'HEAD') {
    upstream.resume()
    response.end()
    return
  }
  await pipeline(upstream, response)
}

export async function startCompanyCardV2Proxy({ listenPort, publicPort, productOrigin, assetRoot, assetManifestPath }) {
  const exactListenPort = parseListenPort(String(listenPort))
  const exactPublicPort = parseListenPort(String(publicPort))
  const exactProductOrigin = parseLoopbackOrigin(productOrigin, 'product origin')
  const verified = await loadVerifiedAssets(assetRoot, assetManifestPath)
  const listenOrigin = `http://127.0.0.1:${exactListenPort}`
  const publicOrigin = `http://127.0.0.1:${exactPublicPort}`
  const server = createServer((request, response) => {
    void (async () => {
      const parsed = new URL(request.url ?? '/', publicOrigin)
      if (parsed.origin !== publicOrigin) { writeSafeError(response, 400, 'invalid request target'); return }
      if (parsed.pathname === '/__company-card-v2-e2e/ready') {
        if (request.method !== 'GET' || parsed.search !== '') { writeSafeError(response, 405, 'method not allowed'); return }
        const body = Buffer.from('{"ready":true}\n', 'utf8')
        response.writeHead(200, { 'Content-Type': 'application/json', 'Content-Length': String(body.byteLength), 'Cache-Control': 'no-store' })
        response.end(body)
        return
      }
      const asset = verified.assets.get(parsed.pathname)
      if (asset !== undefined) {
        if ((request.method !== 'GET' && request.method !== 'HEAD') || parsed.search !== '') { writeSafeError(response, 405, 'method not allowed'); return }
        response.writeHead(200, { 'Content-Type': asset.mediaType, 'Content-Length': String(asset.size), 'Cache-Control': 'public, max-age=31536000, immutable', ETag: `"${asset.sha256}"` })
        if (request.method === 'HEAD') response.end()
        else createReadStream(asset.absolutePath).pipe(response)
        return
      }
      if (ASSET_PATH.test(parsed.pathname)) { writeSafeError(response, 404, 'asset not declared'); return }
      await proxyProduct(request, response, exactProductOrigin, publicOrigin)
    })().catch(() => { if (!response.headersSent) writeSafeError(response, 502, 'loopback upstream unavailable'); else response.destroy() })
  })
  await new Promise((resolveListen, rejectListen) => {
    server.once('error', rejectListen)
    server.listen(exactListenPort, '127.0.0.1', () => { server.off('error', rejectListen); resolveListen() })
  })
  return Object.freeze({
    origin: listenOrigin,
    publicOrigin,
    close: () => new Promise((resolveClose, rejectClose) => server.close(error => error ? rejectClose(error) : resolveClose())),
  })
}

async function main() {
  const { values } = parseArgs({
    strict: true,
    options: {
      'asset-manifest': { type: 'string' },
      'asset-root': { type: 'string' },
      'listen-port': { type: 'string' },
      'product-origin': { type: 'string' },
      'public-port': { type: 'string' },
    },
  })
  for (const name of ['asset-manifest', 'asset-root', 'listen-port', 'product-origin', 'public-port']) if (values[name] === undefined) throw new Error(`--${name} is required`)
  const proxy = await startCompanyCardV2Proxy({
    listenPort: parseListenPort(values['listen-port']),
    publicPort: parseListenPort(values['public-port']),
    productOrigin: parseLoopbackOrigin(values['product-origin'], 'product origin'),
    assetRoot: values['asset-root'],
    assetManifestPath: values['asset-manifest'],
  })
  process.stdout.write(`Company Card v2 loopback proxy ready: ${proxy.origin}; public=${proxy.publicOrigin}\n`)
  const stop = () => { void proxy.close().finally(() => process.exit(0)) }
  process.once('SIGINT', stop)
  process.once('SIGTERM', stop)
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main()
