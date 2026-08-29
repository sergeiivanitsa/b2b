/* Closed TCP adapter for a browser container that must see only loopback. */
import { lookup } from 'node:dns/promises'
import { createConnection, createServer } from 'node:net'
import { resolve } from 'node:path'
import { parseArgs } from 'node:util'
import { fileURLToPath } from 'node:url'
import { parseListenPort } from './loopback-proxy.mjs'

const ALLOWED_TARGET_HOSTS = new Set(['127.0.0.1', 'host.docker.internal'])
const MAX_CONNECTIONS = 64
const IDLE_TIMEOUT_MS = 30_000
export const EXPECTED_RELAY_NODE_VERSION = 'v24.18.1'

export function parseRelayTargetHost(value) {
  if (!ALLOWED_TARGET_HOSTS.has(value)) throw new Error('relay target host is outside the closed runner boundary')
  return value
}

export function isPrivateDockerIPv4(value) {
  const octets = value.split('.').map(Number)
  if (octets.length !== 4 || octets.some(octet => !Number.isInteger(octet) || octet < 0 || octet > 255)) return false
  return octets[0] === 10
    || (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31)
    || (octets[0] === 192 && octets[1] === 168)
}

export async function resolveRelayTarget(value) {
  const host = parseRelayTargetHost(value)
  if (host === '127.0.0.1') return host
  const records = await lookup(host, { all: true, family: 4, verbatim: true })
  const addresses = [...new Set(records.map(record => record.address))]
  if (addresses.length !== 1 || !isPrivateDockerIPv4(addresses[0])) throw new Error('Docker host gateway did not resolve to one private IPv4 address')
  return addresses[0]
}

export async function startCompanyCardV2Relay({ listenPort, targetHost, targetPort }) {
  const exactListenPort = parseListenPort(String(listenPort))
  const exactTargetPort = parseListenPort(String(targetPort))
  const exactTargetHost = parseRelayTargetHost(targetHost)
  if (exactTargetHost === '127.0.0.1' && exactListenPort === exactTargetPort) throw new Error('relay cannot target its own loopback listener')
  const targetAddress = await resolveRelayTarget(exactTargetHost)
  let activeConnections = 0
  const sockets = new Set()
  const server = createServer({ allowHalfOpen: false }, incoming => {
    if (activeConnections >= MAX_CONNECTIONS) { incoming.destroy(); return }
    activeConnections += 1
    const outgoing = createConnection({ host: targetAddress, port: exactTargetPort })
    sockets.add(incoming); sockets.add(outgoing)
    incoming.setTimeout(IDLE_TIMEOUT_MS, () => incoming.destroy())
    outgoing.setTimeout(IDLE_TIMEOUT_MS, () => outgoing.destroy())
    const close = () => {
      if (!sockets.has(incoming) && !sockets.has(outgoing)) return
      sockets.delete(incoming); sockets.delete(outgoing)
      activeConnections -= 1
      incoming.destroy(); outgoing.destroy()
    }
    incoming.once('error', close); incoming.once('close', close)
    outgoing.once('error', close); outgoing.once('close', close)
    incoming.pipe(outgoing); outgoing.pipe(incoming)
  })
  server.maxConnections = MAX_CONNECTIONS
  await new Promise((resolveListen, rejectListen) => {
    server.once('error', rejectListen)
    server.listen(exactListenPort, '127.0.0.1', () => { server.off('error', rejectListen); resolveListen() })
  })
  return Object.freeze({
    origin: `http://127.0.0.1:${exactListenPort}`,
    close: () => new Promise((resolveClose, rejectClose) => {
      for (const socket of sockets) socket.destroy()
      server.close(error => error ? rejectClose(error) : resolveClose())
    }),
  })
}

async function main() {
  if (process.version !== EXPECTED_RELAY_NODE_VERSION) throw new Error('relay Node runtime differs from the digest-pinned Playwright image')
  const { values } = parseArgs({
    strict: true,
    options: {
      'listen-port': { type: 'string' },
      'target-host': { type: 'string' },
      'target-port': { type: 'string' },
    },
  })
  for (const name of ['listen-port', 'target-host', 'target-port']) if (values[name] === undefined) throw new Error(`--${name} is required`)
  const relay = await startCompanyCardV2Relay({
    listenPort: parseListenPort(values['listen-port']),
    targetHost: parseRelayTargetHost(values['target-host']),
    targetPort: parseListenPort(values['target-port']),
  })
  process.stdout.write(`Company Card v2 browser loopback relay ready: ${relay.origin}\n`)
  const stop = () => { void relay.close().finally(() => process.exit(0)) }
  process.once('SIGINT', stop)
  process.once('SIGTERM', stop)
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main()
