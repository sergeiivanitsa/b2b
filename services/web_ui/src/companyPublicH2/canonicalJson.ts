import { isStrictJsonInteger, type StrictJsonValue } from './strictJson'

export class CanonicalJsonError extends Error {}
const encoder = new TextEncoder()

function quote(value: string): string {
  let output = '"'
  for (const character of value.normalize('NFC')) {
    const code = character.codePointAt(0)!
    if (character === '"') output += '\\"'
    else if (character === '\\') output += '\\\\'
    else if (code <= 0x1f) output += `\\u${code.toString(16).padStart(4, '0')}`
    else output += character
  }
  return `${output}"`
}
function scalarCompare(left: string, right: string): number {
  const a = Array.from(left.normalize('NFC'), item => item.codePointAt(0)!)
  const b = Array.from(right.normalize('NFC'), item => item.codePointAt(0)!)
  for (let index = 0; index < Math.min(a.length, b.length); index += 1) {
    if (a[index] !== b[index]) return a[index] < b[index] ? -1 : 1
  }
  return a.length - b.length
}
function render(value: StrictJsonValue, omitProjectionDigest = false): string {
  if (value === null || typeof value === 'boolean') return String(value)
  if (typeof value === 'string') return quote(value)
  if (isStrictJsonInteger(value)) return value.token
  if (Array.isArray(value)) return `[${value.map(item => render(item)).join(',')}]`
  const entries = Object.entries(value)
    .filter(([key]) => !(omitProjectionDigest && key === 'projection_digest'))
    .map(([key, child]) => [key.normalize('NFC'), child] as const)
    .sort(([a], [b]) => scalarCompare(a, b))
  if (new Set(entries.map(([key]) => key)).size !== entries.length) throw new CanonicalJsonError('duplicate key after NFC')
  return `{${entries.map(([key, child]) => `${quote(key)}:${render(child)}`).join(',')}}`
}
export function canonicalJsonBytes(value: StrictJsonValue): Uint8Array {
  const bytes = encoder.encode(render(value, true))
  if (bytes.byteLength > 524_288) throw new CanonicalJsonError('canonical projection exceeds byte limit')
  return bytes
}
/** Full DTO bytes, including projection_digest, for the public size gate. */
export function canonicalFullProjectionBytes(value: StrictJsonValue): Uint8Array {
  const bytes = encoder.encode(render(value))
  if (bytes.byteLength > 524_288) throw new CanonicalJsonError('full canonical projection exceeds byte limit')
  return bytes
}
export async function canonicalProjectionDigest(value: StrictJsonValue, cryptoImpl: Pick<Crypto, 'subtle'> = crypto): Promise<string> {
  const bytes = canonicalJsonBytes(value)
  const input = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
  const hash = await cryptoImpl.subtle.digest('SHA-256', input)
  return [...new Uint8Array(hash)].map(byte => byte.toString(16).padStart(2, '0')).join('')
}
