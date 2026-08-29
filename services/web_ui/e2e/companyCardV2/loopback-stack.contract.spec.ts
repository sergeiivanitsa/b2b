import { createHash } from 'node:crypto'
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { createServer } from 'node:http'
import type { AddressInfo } from 'node:net'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { expect, test } from '@playwright/test'
import { parseLoopbackStackPorts, startCompanyCardV2LoopbackStack } from './loopback-stack.mjs'

async function unusedLoopbackPort(): Promise<number> {
  const server = createServer()
  await new Promise<void>((resolveListen, rejectListen) => {
    server.once('error', rejectListen)
    server.listen(0, '127.0.0.1', () => { server.off('error', rejectListen); resolveListen() })
  })
  const port = (server.address() as AddressInfo).port
  await new Promise<void>((resolveClose, rejectClose) => server.close(error => error ? rejectClose(error) : resolveClose()))
  return port
}

test('requires three distinct closed TCP ports for the in-container stack', () => {
  expect(parseLoopbackStackPorts({ browserPort: '8125', productRelayPort: '8126', productTargetPort: '8127' })).toEqual({
    browserPort: 8125,
    productRelayPort: 8126,
    productTargetPort: 8127,
  })
  for (const source of [
    { browserPort: '8125', productRelayPort: '8125', productTargetPort: '8127' },
    { browserPort: '8125', productRelayPort: '8126', productTargetPort: '8126' },
    { browserPort: '0', productRelayPort: '8126', productTargetPort: '8127' },
  ]) expect(() => parseLoopbackStackPorts(source)).toThrow(/ports|port/u)
})

test('serves verified assets and relayed Product responses from one exact loopback origin', async () => {
  const temporaryRoot = await mkdtemp(join(tmpdir(), 'company-card-v2-loopback-stack-'))
  const assetDirectory = join(temporaryRoot, 'assets')
  await mkdir(assetDirectory)
  const assets = [
    { path: '/assets/company-public-h2.abcdefgh.js', media_type: 'text/javascript', bytes: 'export const proof = true\n' },
    { path: '/assets/company-public-h2.abcdefgh.css', media_type: 'text/css', bytes: '.proof { display: block; }\n' },
  ]
  for (const asset of assets) await writeFile(join(temporaryRoot, asset.path), asset.bytes, 'utf8')
  const manifestPath = join(temporaryRoot, 'public_h2_asset_manifest.json')
  await writeFile(manifestPath, JSON.stringify({
    schema_version: 'company_public_h2_asset_manifest_v1',
    public_contract_version: 'company_public_h2_v1',
    entry_js_path: assets[0].path,
    entry_css_path: assets[1].path,
    optional_chunk_paths: [],
    assets: assets.map(asset => ({
      path: asset.path,
      media_type: asset.media_type,
      sha256_hex: createHash('sha256').update(asset.bytes).digest('hex'),
    })),
  }), 'utf8')

  const product = createServer((request, response) => {
    const body = Buffer.from(`${request.method} ${request.url} host=${request.headers.host}\n`, 'utf8')
    response.writeHead(200, { 'content-length': String(body.byteLength), 'content-type': 'text/plain; charset=utf-8' })
    response.end(body)
  })
  await new Promise<void>((resolveListen, rejectListen) => {
    product.once('error', rejectListen)
    product.listen(0, '127.0.0.1', () => { product.off('error', rejectListen); resolveListen() })
  })
  const productTargetPort = (product.address() as AddressInfo).port
  let browserPort = await unusedLoopbackPort()
  while (browserPort === productTargetPort) browserPort = await unusedLoopbackPort()
  let productRelayPort = await unusedLoopbackPort()
  while (productRelayPort === browserPort || productRelayPort === productTargetPort) productRelayPort = await unusedLoopbackPort()

  let stack
  try {
    stack = await startCompanyCardV2LoopbackStack({
      browserPort, productRelayPort, productTargetHost: '127.0.0.1', productTargetPort,
      assetRoot: temporaryRoot, assetManifestPath: manifestPath,
    })
    const ready = await fetch(`${stack.origin}/__company-card-v2-e2e/ready`)
    expect(ready.status).toBe(200)
    expect(await ready.json()).toEqual({ ready: true })
    const asset = await fetch(`${stack.origin}${assets[0].path}`)
    expect(asset.status).toBe(200)
    expect(await asset.text()).toBe(assets[0].bytes)
    const relayed = await fetch(`${stack.origin}/product-proof`)
    expect(relayed.status).toBe(200)
    expect(await relayed.text()).toBe(`GET /product-proof host=127.0.0.1:${browserPort}\n`)
  } finally {
    if (stack !== undefined) await stack.close()
    await new Promise<void>((resolveClose, rejectClose) => product.close(error => error ? rejectClose(error) : resolveClose()))
    await rm(temporaryRoot, { recursive: true })
  }
})
