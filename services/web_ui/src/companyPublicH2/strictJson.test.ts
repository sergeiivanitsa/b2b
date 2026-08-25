import { describe, expect, it } from 'vitest'
import { isStrictJsonInteger, isStrictJsonObject, StrictJsonError, parseStrictJson, stringifyStrictJson } from './strictJson'

describe('strict H2 JSON', () => {
  it('keeps arbitrary integers as BigInt-backed exact tokens', () => {
    const parsed = parseStrictJson('{"count":9007199254740992}')
    expect(isStrictJsonObject(parsed)).toBe(true)
    if (!isStrictJsonObject(parsed)) throw new Error('expected object')
    expect(isStrictJsonInteger(parsed.count)).toBe(true)
    if (!isStrictJsonInteger(parsed.count)) throw new Error('expected integer')
    expect(parsed.count.token).toBe('9007199254740992')
    expect(parsed.count.value).toBe(9007199254740992n)
    expect(stringifyStrictJson(parsed)).toBe('{"count":9007199254740992}')
  })
  it('does not mistake a JSON object with integer-like field names for a parser token', () => {
    const parsed = parseStrictJson('{"kind":"integer","token":"1","value":"1"}')
    expect(isStrictJsonObject(parsed)).toBe(true)
    expect(isStrictJsonInteger(parsed)).toBe(false)
  })
  it.each(['{"x":1.0}', '{"x":1e2}', '{"x":-0}', '{"x":01}', '{"x":1,"x":2}', '{"x":"\\uD800"}'])('rejects non-profile JSON %s', raw => {
    expect(() => parseStrictJson(raw)).toThrow(StrictJsonError)
  })
  it.each(['{"__proto__":1}', '{"constructor":1}', '{"prototype":1}'])('rejects dangerous object key %s', raw => {
    expect(() => parseStrictJson(raw)).toThrow(StrictJsonError)
  })
  it('accepts a complete document followed by whitespace and reaches EOF', () => {
    expect(parseStrictJson('{"ok":true}\r\n \t')).toEqual({ ok: true })
  })
  it('preserves the wire spelling so the H2 boundary can reject non-NFC input', () => {
    const parsed = parseStrictJson('{"value":"e\\u0301"}')
    expect(parsed).toEqual({ value: 'e\u0301' })
  })
})
