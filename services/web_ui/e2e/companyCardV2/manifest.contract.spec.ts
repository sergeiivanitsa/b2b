import { expect, test } from '@playwright/test'
import { parseCompanyCardV2E2EManifest, PROFILE_IDS } from './manifest'

function manifest(): Record<string, unknown> {
  return {
    schema_version: 'company_card_v2_e2e_manifest_v1',
    release_sha: 'a'.repeat(40),
    routes: { robots_path: '/robots.txt', sitemap_index_path: '/sitemaps/index.xml' },
    profiles: PROFILE_IDS.map((profileId, index) => ({
      profile_id: profileId,
      canonical_path: `/company/${7700000000 + index}-synthetic-${index}`,
      wrong_slug_path: `/company/${7700000000 + index}-wrong-${index}`,
      expected_report_id: `0000000${index}-0000-4000-8000-00000000000${index}`,
      expected_indexable: index % 2 === 0,
      expected_lazy_hosts: ['finance-f1'],
      expected_visible_text: [`synthetic profile ${index}`],
      forbidden_visible_text: [`forbidden synthetic token ${index}`],
      lazy_failure_chunk: profileId === 'lazy_failure_v1' ? 'finance' : null,
    })),
  }
}

test('accepts exactly the bounded five-profile contract', () => {
  const parsed = parseCompanyCardV2E2EManifest(JSON.stringify(manifest()), 'http://127.0.0.1:8125')
  expect(parsed.profiles.map(profile => profile.profile_id)).toEqual(PROFILE_IDS)
  expect(parsed.releaseSha).toBe('a'.repeat(40))
})

test('rejects unknown keys, stale profile order and non-canonical paths', () => {
  const unknown = manifest()
  unknown.extra = true
  expect(() => parseCompanyCardV2E2EManifest(JSON.stringify(unknown), 'http://127.0.0.1:8125')).toThrow(/unknown or missing keys/u)

  const wrongOrder = manifest()
  const profiles = wrongOrder.profiles as Record<string, unknown>[]
  ;[profiles[0], profiles[1]] = [profiles[1], profiles[0]]
  expect(() => parseCompanyCardV2E2EManifest(JSON.stringify(wrongOrder), 'http://127.0.0.1:8125')).toThrow(/closed order/u)

  const badPath = manifest()
  ;(badPath.profiles as Record<string, unknown>[])[0].canonical_path = 'https://example.invalid/company/1'
  expect(() => parseCompanyCardV2E2EManifest(JSON.stringify(badPath), 'http://127.0.0.1:8125')).toThrow(/same-origin path/u)
})

test('rejects BOM, oversized input, duplicate identities and invalid lazy failure mode', () => {
  expect(() => parseCompanyCardV2E2EManifest(`\uFEFF${JSON.stringify(manifest())}`, 'http://127.0.0.1:8125')).toThrow(/too large or has a BOM/u)
  expect(() => parseCompanyCardV2E2EManifest(' '.repeat(1_048_577), 'http://127.0.0.1:8125')).toThrow(/too large/u)

  const duplicate = manifest()
  const profiles = duplicate.profiles as Record<string, unknown>[]
  profiles[1].expected_report_id = profiles[0].expected_report_id
  expect(() => parseCompanyCardV2E2EManifest(JSON.stringify(duplicate), 'http://127.0.0.1:8125')).toThrow(/must be unique/u)

  const invalidFailure = manifest()
  ;(invalidFailure.profiles as Record<string, unknown>[]).at(-1)!.lazy_failure_chunk = null
  expect(() => parseCompanyCardV2E2EManifest(JSON.stringify(invalidFailure), 'http://127.0.0.1:8125')).toThrow(/must select one lazy chunk/u)
})

test('rejects Docker gateway, localhost and external manifest origins', () => {
  for (const baseUrl of [
    'http://host.docker.internal:8125', 'http://localhost:8125',
    'http://192.168.65.254:8125', 'https://127.0.0.1:8125',
  ]) expect(() => parseCompanyCardV2E2EManifest(JSON.stringify(manifest()), baseUrl)).toThrow(/explicit http/u)
})
