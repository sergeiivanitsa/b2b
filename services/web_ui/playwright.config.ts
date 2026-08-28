/* global process */
import { defineConfig, devices } from '@playwright/test'
import { loadCompanyCardV2E2EContract } from './e2e/companyCardV2/manifest'

const contract = loadCompanyCardV2E2EContract(process.env)

export default defineConfig({
  testDir: './e2e/companyCardV2',
  testMatch: '**/*.spec.ts',
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  workers: 1,
  timeout: 60_000,
  expect: {
    timeout: 10_000,
    toHaveScreenshot: {
      animations: 'disabled',
      caret: 'hide',
      scale: 'css',
      threshold: 0,
      maxDiffPixels: 0,
    },
  },
  outputDir: '.tmp/iteration25-playwright/test-results',
  snapshotPathTemplate: '{testDir}/{testFilePath}-snapshots/{arg}{ext}',
  reporter: [
    ['list'],
    ['junit', { outputFile: '.tmp/iteration25-playwright/junit.xml', includeProjectInTestName: true }],
    ['html', { outputFolder: '.tmp/iteration25-playwright/report', open: 'never' }],
  ],
  globalSetup: './e2e/companyCardV2/global-setup.ts',
  use: {
    ...devices['Desktop Chrome'],
    baseURL: contract.baseUrl,
    locale: 'ru-RU',
    timezoneId: 'UTC',
    colorScheme: 'light',
    contextOptions: { reducedMotion: 'no-preference' },
    deviceScaleFactor: 1,
    serviceWorkers: 'block',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium', channel: undefined } }],
})
