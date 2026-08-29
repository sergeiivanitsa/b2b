import { expect, test } from '@playwright/test'
import { parseListenPort, parseLoopbackOrigin } from './loopback-proxy.mjs'

test('admits only explicit IPv4 loopback Product origins', () => {
  expect(parseLoopbackOrigin('http://127.0.0.1:8125', 'product origin')).toBe('http://127.0.0.1:8125')
  for (const candidate of [
    'https://127.0.0.1:8125', 'http://localhost:8125', 'http://0.0.0.0:8125',
    'http://127.0.0.1:8125/path', 'http://user@127.0.0.1:8125', 'http://example.invalid:8125',
  ]) expect(() => parseLoopbackOrigin(candidate, 'product origin')).toThrow(/explicit http/u)
})

test('admits only a closed nonzero TCP port', () => {
  expect(parseListenPort('1')).toBe(1)
  expect(parseListenPort('65535')).toBe(65_535)
  for (const candidate of ['0', '01', '-1', '65536', '8125x', '']) expect(() => parseListenPort(candidate)).toThrow(/port/u)
})
