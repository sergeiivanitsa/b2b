import { describe, expect, it } from 'vitest'
import { CanonicalJsonError, canonicalFullProjectionBytes, canonicalProjectionDigest } from './canonicalJson'
import { parseStrictJson } from './strictJson'
import sharedVectors from '../../../../shared/fixtures/company_public_h2_cjson_v1.json?raw'

describe('company_public_h2_cjson_v1 cross-language vectors', () => {
  const vectors = JSON.parse(sharedVectors) as { profile: string; vectors: readonly { raw: string; sha256: string }[] }
  it('executes the complete closed seven-vector registry', () => {
    expect(vectors.profile).toBe('company_public_h2_cjson_v1')
    expect(vectors.vectors).toHaveLength(7)
    expect(vectors.vectors.map(item => item.raw)).toContain('{"value":123456789012345678901234567890}')
    expect(vectors.vectors.map(item => item.raw)).toContain('{"value":-123456789012345678901234567890}')
  })
  it.each(vectors.vectors)('matches Python vector $raw', async ({ raw, sha256 }) => {
    expect(await canonicalProjectionDigest(parseStrictJson(raw))).toBe(sha256)
  })

  it('counts projection_digest in the exact full-projection byte boundary', () => {
    const seed = parseStrictJson(`{"pad":"","projection_digest":"${'0'.repeat(64)}"}`)
    const padding = 524_288 - canonicalFullProjectionBytes(seed).byteLength
    const exact = parseStrictJson(`{"pad":"${'x'.repeat(padding)}","projection_digest":"${'0'.repeat(64)}"}`)
    const plusOne = parseStrictJson(`{"pad":"${'x'.repeat(padding + 1)}","projection_digest":"${'0'.repeat(64)}"}`)
    expect(canonicalFullProjectionBytes(exact)).toHaveLength(524_288)
    expect(() => canonicalFullProjectionBytes(plusOne)).toThrow(CanonicalJsonError)
  })
})
