import { createServer } from 'node:http'
import type { AddressInfo } from 'node:net'
import { expect, test } from '@playwright/test'
import {
  EXPECTED_RELAY_NODE_VERSION, isPrivateDockerIPv4, parseRelayTargetHost, resolveRelayTarget,
  startCompanyCardV2Relay,
} from './loopback-relay.mjs'

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

test('admits only the two runner-owned relay target names', async () => {
  expect(EXPECTED_RELAY_NODE_VERSION).toBe('v24.18.1')
  expect(parseRelayTargetHost('127.0.0.1')).toBe('127.0.0.1')
  expect(parseRelayTargetHost('host.docker.internal')).toBe('host.docker.internal')
  expect(await resolveRelayTarget('127.0.0.1')).toBe('127.0.0.1')
  for (const candidate of [
    'localhost', '0.0.0.0', '192.168.1.1', 'example.invalid',
    'host.docker.internal.example.invalid', 'http://host.docker.internal', '',
  ]) expect(() => parseRelayTargetHost(candidate)).toThrow(/closed runner boundary/u)
})

test('accepts only private IPv4 results for the Docker host gateway name', () => {
  for (const address of ['10.0.0.1', '172.16.0.1', '172.31.255.254', '192.168.65.254']) expect(isPrivateDockerIPv4(address)).toBe(true)
  for (const address of ['127.0.0.1', '169.254.1.1', '172.32.0.1', '192.0.2.1', '8.8.8.8', '::1', '']) expect(isPrivateDockerIPv4(address)).toBe(false)
})

test('relays bytes between two distinct exact loopback ports', async () => {
  const target = createServer((request, response) => {
    const body = Buffer.from(`${request.method} ${request.url}\n`, 'utf8')
    response.writeHead(200, { 'content-length': String(body.byteLength), 'content-type': 'text/plain; charset=utf-8' })
    response.end(body)
  })
  await new Promise<void>((resolveListen, rejectListen) => {
    target.once('error', rejectListen)
    target.listen(0, '127.0.0.1', () => { target.off('error', rejectListen); resolveListen() })
  })
  const targetPort = (target.address() as AddressInfo).port
  let listenPort = await unusedLoopbackPort()
  while (listenPort === targetPort) listenPort = await unusedLoopbackPort()
  const relay = await startCompanyCardV2Relay({ listenPort, targetHost: '127.0.0.1', targetPort })
  try {
    const response = await fetch(`${relay.origin}/relay-proof`)
    expect(response.status).toBe(200)
    expect(await response.text()).toBe('GET /relay-proof\n')
  } finally {
    await relay.close()
    await new Promise<void>((resolveClose, rejectClose) => target.close(error => error ? rejectClose(error) : resolveClose()))
  }
})
