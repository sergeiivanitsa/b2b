export class StrictJsonError extends Error {}

/**
 * Exact integer token produced only by the strict parser.  A class identity is
 * deliberately used instead of a structural ``{kind, token, value}`` shape:
 * JSON objects that happen to contain similarly named fields can never be
 * mistaken for parser-owned integer tokens.
 */
export class StrictJsonIntegerToken {
  readonly kind = 'integer' as const
  readonly token: string
  readonly value: bigint

  constructor(token: string) {
    this.token = token
    this.value = BigInt(token)
    Object.freeze(this)
  }
}

export type StrictJsonInteger = StrictJsonIntegerToken
export type StrictJsonValue = null | boolean | string | StrictJsonInteger | StrictJsonArray | StrictJsonObject
export type StrictJsonArray = ReadonlyArray<StrictJsonValue>
export interface StrictJsonObject { readonly [key: string]: StrictJsonValue }

const MAX_BYTES = 786_432
const MAX_DEPTH = 80
const MAX_COLLECTION = 2_000

function isHigh(code: number) { return code >= 0xd800 && code <= 0xdbff }
function isLow(code: number) { return code >= 0xdc00 && code <= 0xdfff }

/** The parser is the only producer of integer wrappers. */
export function isStrictJsonInteger(value: StrictJsonValue | unknown): value is StrictJsonInteger {
  return value instanceof StrictJsonIntegerToken
}

export function isStrictJsonObject(value: StrictJsonValue | unknown): value is StrictJsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value) && !isStrictJsonInteger(value)
}

export function parseStrictJson(raw: string): StrictJsonValue {
  if (new TextEncoder().encode(raw).byteLength > MAX_BYTES) throw new StrictJsonError('state exceeds byte limit')
  let at = 0
  const fail = (message: string): never => { throw new StrictJsonError(`${message} at ${at}`) }
  const ws = () => {
    // ``''.includes('')`` is true; EOF must not turn whitespace skipping into
    // an infinite loop for a complete document with trailing whitespace.
    while (at < raw.length && ' \n\r\t'.includes(raw[at])) at += 1
  }
  const string = (): string => {
    if (raw[at++] !== '"') return fail('expected string')
    let result = ''
    while (at < raw.length) {
      const char = raw[at++]
      if (char === '"') {
        for (let i = 0; i < result.length; i += 1) {
          const code = result.charCodeAt(i)
          if (isHigh(code)) { if (!isLow(result.charCodeAt(i + 1))) return fail('unpaired surrogate'); i += 1 }
          else if (isLow(code)) return fail('unpaired surrogate')
        }
        // Preserve wire strings. Generic CJSON normalizes at serialization;
        // the H2 boundary rejects non-NFC payloads before digest validation.
        return result
      }
      if (char === '\\') {
        const escape = raw[at++]
        const simple: Record<string, string> = { '"': '"', '\\': '\\', '/': '/', b: '\b', f: '\f', n: '\n', r: '\r', t: '\t' }
        if (escape === 'u') {
          const hex = raw.slice(at, at + 4)
          if (!/^[0-9a-fA-F]{4}$/.test(hex)) return fail('invalid unicode escape')
          result += String.fromCharCode(Number.parseInt(hex, 16)); at += 4
        } else if (escape in simple) result += simple[escape]
        else return fail('invalid escape')
      } else {
        if (char < ' ' || char === undefined) return fail('invalid string control')
        result += char
      }
    }
    return fail('unterminated string')
  }
  const value = (depth: number): StrictJsonValue => {
    if (depth > MAX_DEPTH) return fail('maximum depth exceeded')
    ws(); const char = raw[at]
    if (char === '"') return string()
    if (char === '{') {
      at += 1; ws(); const out: Record<string, StrictJsonValue> = Object.create(null); const normalized = new Set<string>()
      if (raw[at] === '}') { at += 1; return out }
      for (let count = 0; ; count += 1) {
        if (count >= MAX_COLLECTION || raw[at] !== '"') return fail('invalid object')
        const key = string(); if (key === '__proto__' || key === 'constructor' || key === 'prototype') return fail('dangerous object key'); if (Object.hasOwn(out, key) || normalized.has(key.normalize('NFC'))) return fail('duplicate object key')
        normalized.add(key.normalize('NFC')); ws(); if (raw[at++] !== ':') return fail('missing colon')
        out[key] = value(depth + 1); ws(); if (raw[at] === '}') { at += 1; return out }
        if (raw[at++] !== ',') return fail('missing comma'); ws()
      }
    }
    if (char === '[') {
      at += 1; ws(); const out: StrictJsonValue[] = []
      if (raw[at] === ']') { at += 1; return out }
      for (;;) {
        if (out.length >= MAX_COLLECTION) return fail('collection limit exceeded')
        out.push(value(depth + 1)); ws(); if (raw[at] === ']') { at += 1; return out }
        if (raw[at++] !== ',') return fail('missing comma'); ws()
      }
    }
    for (const [token, output] of [['true', true], ['false', false], ['null', null]] as const) {
      if (raw.startsWith(token, at)) { at += token.length; return output }
    }
    const start = at
    if (raw[at] === '-') at += 1
    if (raw[at] === '0') at += 1
    else if (/[1-9]/.test(raw[at] ?? '')) while (/[0-9]/.test(raw[at] ?? '')) at += 1
    else return fail('invalid value')
    const token = raw.slice(start, at)
    if (!/^(?:0|-[1-9][0-9]*|[1-9][0-9]*)$/.test(token)) return fail('only integer JSON numbers are permitted')
    return new StrictJsonIntegerToken(token)
  }
  const output = value(0); ws(); if (at !== raw.length) fail('trailing input')
  return output
}

function quoteWireString(value: string): string {
  let output = '"'
  for (const character of value) {
    const code = character.codePointAt(0)!
    if (character === '"') output += '\\"'
    else if (character === '\\') output += '\\\\'
    else if (code <= 0x1f) output += `\\u${code.toString(16).padStart(4, '0')}`
    else output += character
  }
  return `${output}"`
}

/** Serialize a strict token tree without Number conversion or NFC rewriting. */
export function stringifyStrictJson(value: StrictJsonValue): string {
  if (value === null || typeof value === 'boolean') return String(value)
  if (typeof value === 'string') return quoteWireString(value)
  if (isStrictJsonInteger(value)) return value.token
  if (Array.isArray(value)) return `[${value.map(stringifyStrictJson).join(',')}]`
  return `{${Object.entries(value).map(([key, child]) => `${quoteWireString(key)}:${stringifyStrictJson(child)}`).join(',')}}`
}
