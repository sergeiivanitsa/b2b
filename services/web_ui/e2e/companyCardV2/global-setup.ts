/* global process */
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { chromium } from '@playwright/test'
import { loadCompanyCardV2E2EContract } from './manifest'

const EXPECTED_PLAYWRIGHT_VERSION = '1.62.1'
const EXPECTED_CHROMIUM_REVISION = '1234'
const EXPECTED_CHROMIUM_VERSION = '151.0.7922.34'
const EXPECTED_BROWSER_NODE_VERSION = 'v24.18.1'
const FONT_FORMAT = '%{file}\t%{family}\t%{style}\t%{index}\n'

type BrowserRecord = Readonly<{ name?: unknown; revision?: unknown; browserVersion?: unknown }>

export default function globalSetup(): void {
  const contract = loadCompanyCardV2E2EContract(process.env)
  if (process.version !== EXPECTED_BROWSER_NODE_VERSION) throw new Error('browser Node runtime differs from the reviewed Playwright image')
  const webRoot = resolve(import.meta.dirname, '../..')
  const packageMetadata = JSON.parse(readFileSync(resolve(webRoot, 'node_modules/@playwright/test/package.json'), 'utf8')) as { version?: unknown }
  if (packageMetadata.version !== EXPECTED_PLAYWRIGHT_VERSION) throw new Error('unexpected @playwright/test version')

  const browserMetadata = JSON.parse(readFileSync(resolve(webRoot, 'node_modules/playwright-core/browsers.json'), 'utf8')) as { browsers?: BrowserRecord[] }
  const chromiumRecord = browserMetadata.browsers?.find(item => item.name === 'chromium')
  if (chromiumRecord?.revision !== EXPECTED_CHROMIUM_REVISION || chromiumRecord.browserVersion !== EXPECTED_CHROMIUM_VERSION) {
    throw new Error('Playwright Chromium revision does not match the reviewed browser contract')
  }
  if (!existsSync(chromium.executablePath())) {
    throw new Error('reviewed Chromium is absent; browser downloads are forbidden in the E2E gate')
  }
  const expectedFontHash = readFileSync(resolve(webRoot, '../../.github/ci/playwright-font-inventory.sha256'), 'utf8').trim()
  if (!/^[0-9a-f]{64}$/u.test(expectedFontHash)) throw new Error('committed Playwright font inventory hash is malformed')
  const fonts = spawnSync('fc-list', ['--format', FONT_FORMAT], { encoding: 'utf8', env: { ...process.env, LC_ALL: 'C' } })
  if (fonts.status !== 0 || fonts.error !== undefined) throw new Error('fc-list failed in the reviewed Playwright environment')
  const normalizedLines = fonts.stdout.replaceAll('\r\n', '\n').split('\n')
  if (normalizedLines.at(-1) === '') normalizedLines.pop()
  normalizedLines.sort((left, right) => Buffer.compare(Buffer.from(left, 'utf8'), Buffer.from(right, 'utf8')))
  const actualFontHash = createHash('sha256').update(`${normalizedLines.join('\n')}\n`, 'utf8').digest('hex')
  if (actualFontHash !== expectedFontHash) throw new Error('Playwright font inventory differs from the committed normalized hash')
  process.stdout.write(`Company Card v2 E2E contract: release=${contract.releaseSha}; profiles=${contract.profiles.length}; browser=${EXPECTED_CHROMIUM_VERSION}\n`)
}
