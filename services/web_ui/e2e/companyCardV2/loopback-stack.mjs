/* One-process owner for the browser-loopback relay and same-origin H2 proxy. */
import { resolve } from 'node:path'
import { parseArgs } from 'node:util'
import { fileURLToPath } from 'node:url'
import { EXPECTED_RELAY_NODE_VERSION, parseRelayTargetHost, startCompanyCardV2Relay } from './loopback-relay.mjs'
import { parseListenPort, parseLoopbackOrigin, startCompanyCardV2Proxy } from './loopback-proxy.mjs'

export function parseLoopbackStackPorts({ browserPort, productRelayPort, productTargetPort }) {
  const parsed = Object.freeze({
    browserPort: parseListenPort(String(browserPort)),
    productRelayPort: parseListenPort(String(productRelayPort)),
    productTargetPort: parseListenPort(String(productTargetPort)),
  })
  if (new Set(Object.values(parsed)).size !== 3) throw new Error('loopback stack ports must be distinct')
  return parsed
}

export async function startCompanyCardV2LoopbackStack({
  browserPort, productRelayPort, productTargetHost, productTargetPort,
  assetRoot, assetManifestPath,
}) {
  const ports = parseLoopbackStackPorts({ browserPort, productRelayPort, productTargetPort })
  const targetHost = parseRelayTargetHost(productTargetHost)
  const relay = await startCompanyCardV2Relay({
    listenPort: ports.productRelayPort,
    targetHost,
    targetPort: ports.productTargetPort,
  })
  let proxy
  try {
    proxy = await startCompanyCardV2Proxy({
      listenPort: ports.browserPort,
      publicPort: ports.browserPort,
      productOrigin: parseLoopbackOrigin(relay.origin, 'relayed Product origin'),
      assetRoot,
      assetManifestPath,
    })
  } catch (error) {
    await relay.close()
    throw error
  }
  let closing
  return Object.freeze({
    origin: proxy.publicOrigin,
    close: () => {
      closing ??= (async () => {
        try {
          await proxy.close()
        } finally {
          await relay.close()
        }
      })()
      return closing
    },
  })
}

async function main() {
  if (process.version !== EXPECTED_RELAY_NODE_VERSION) throw new Error('loopback stack Node runtime differs from the digest-pinned Playwright image')
  const { values } = parseArgs({
    strict: true,
    options: {
      'asset-manifest': { type: 'string' },
      'asset-root': { type: 'string' },
      'browser-port': { type: 'string' },
      'product-relay-port': { type: 'string' },
      'product-target-host': { type: 'string' },
      'product-target-port': { type: 'string' },
    },
  })
  for (const name of [
    'asset-manifest', 'asset-root', 'browser-port', 'product-relay-port',
    'product-target-host', 'product-target-port',
  ]) if (values[name] === undefined) throw new Error(`--${name} is required`)
  const stack = await startCompanyCardV2LoopbackStack({
    browserPort: values['browser-port'],
    productRelayPort: values['product-relay-port'],
    productTargetHost: values['product-target-host'],
    productTargetPort: values['product-target-port'],
    assetRoot: values['asset-root'],
    assetManifestPath: values['asset-manifest'],
  })
  process.stdout.write(`Company Card v2 browser loopback stack ready: ${stack.origin}\n`)
  let stopping = false
  const stop = () => {
    if (stopping) return
    stopping = true
    void stack.close().then(() => process.exit(0), () => process.exit(1))
  }
  process.once('SIGINT', stop)
  process.once('SIGTERM', stop)
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main()
