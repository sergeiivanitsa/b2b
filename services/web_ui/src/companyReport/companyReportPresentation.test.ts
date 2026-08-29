import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import indexHtml from '../../index.html?raw'
import publishedFixture from './fixtures/company-public-h1-published.json?raw'
import { parseCompanyPublicH1 } from './companyReportH1Contract'
import {
  beginCompanyHead,
  BLOCK_LABELS,
  classifyH1Error,
  cleanupCompanyHead,
  COVERAGE_LABELS,
  DATASET_LABELS,
  displayIsoDate,
  FINANCE_LABELS,
  HEAD_KIND_ATTRIBUTE,
  HEAD_OWNER_ATTRIBUTE,
  HEAD_OWNER_VALUE,
  HEAD_PREVIOUS_LANG_ATTRIBUTE,
  isCanonicalCompanyPath,
  parseCompanyKey,
  parseCompanyRoute,
  pendingAutoPollDeadlineMs,
  RESULT_LABELS,
  ROLE_LABELS,
  setCompanyHead,
  setCompanySafeTitle,
  STATUS_LABELS,
  STATUS_AUTO_POLL_WINDOW_MS,
} from './companyReportPresentation'
import { ApiHttpError } from '../lib/api'

const dto = parseCompanyPublicH1(JSON.parse(publishedFixture))
const ownedSelector = `[${HEAD_OWNER_ATTRIBUTE}="${HEAD_OWNER_VALUE}"]`

function bootstrapSource(): string {
  const source = indexHtml.match(/<script>([\s\S]*?)<\/script>/)?.[1]
  if (!source) throw new Error('Company head bootstrap is missing')
  return source
}

function runBootstrap(pathname: string): void {
  const execute = new Function('document', 'location', bootstrapSource())
  execute(document, { pathname })
}

describe('CompanyReport presentation policy', () => {
  beforeEach(() => {
    cleanupCompanyHead()
    document.head.innerHTML = '<title>Исходный заголовок</title>'
    document.documentElement.lang = 'en'
    document.documentElement.removeAttribute(HEAD_PREVIOUS_LANG_ATTRIBUTE)
  })

  afterEach(() => {
    cleanupCompanyHead()
    vi.restoreAllMocks()
  })

  it('parses only strict plain/canonical keys and rejects non-empty queries', () => {
    expect(parseCompanyKey('1234567890')).toEqual({
      kind: 'plain',
      inn: '1234567890',
    })
    expect(parseCompanyKey('123456789012-safe-name')).toEqual({
      kind: 'canonical',
      inn: '123456789012',
    })
    for (const key of [
      undefined,
      '123456789',
      '１２３４５６７８９０',
      '1234567890-Safe',
      '1234567890-safe_name',
      '1234567890-safe-',
    ]) {
      expect(parseCompanyKey(key)).toEqual({ error: 'invalid_company_key' })
    }
    expect(parseCompanyRoute('1234567890-safe', '?source=test')).toEqual({
      error: 'invalid_company_key',
    })
    expect(parseCompanyRoute('1234567890-safe', '')).toMatchObject({
      kind: 'canonical',
    })
  })

  it('accepts only a canonical path for the exact requested INN', () => {
    expect(
      isCanonicalCompanyPath('/company/1234567890-safe-name', '1234567890'),
    ).toBe(true)
    expect(
      isCanonicalCompanyPath('/company/0987654321-safe-name', '1234567890'),
    ).toBe(false)
    expect(
      isCanonicalCompanyPath(
        '/company/1234567890-safe-name?leak=1',
        '1234567890',
      ),
    ).toBe(false)
    expect(
      isCanonicalCompanyPath('https://example.test/company/1234567890-safe', '1234567890'),
    ).toBe(false)
  })

  it('formats ISO dates by string slicing and is browser-timezone independent', () => {
    const dateSpy = vi.spyOn(Intl, 'DateTimeFormat')
    expect(displayIsoDate('2026-01-02')).toBe('02.01.2026')
    expect(displayIsoDate('1970-01-01')).toBe('01.01.1970')
    expect(dateSpy).not.toHaveBeenCalled()
  })

  it('bounds automatic polling by the earlier server or route-local deadline', () => {
    const firstObservedAtMs = Date.parse('2026-08-20T10:02:00Z')
    expect(
      pendingAutoPollDeadlineMs(
        firstObservedAtMs,
        '2026-08-20T10:00:00Z',
      ),
    ).toBe(Date.parse('2026-08-20T10:00:00Z') + STATUS_AUTO_POLL_WINDOW_MS)
    expect(
      pendingAutoPollDeadlineMs(
        firstObservedAtMs,
        '2026-08-20T10:10:00Z',
      ),
    ).toBe(firstObservedAtMs + STATUS_AUTO_POLL_WINDOW_MS)
    expect(pendingAutoPollDeadlineMs(firstObservedAtMs, null)).toBe(
      firstObservedAtMs + STATUS_AUTO_POLL_WINDOW_MS,
    )
    expect(pendingAutoPollDeadlineMs(firstObservedAtMs, 'not-an-iso-date')).toBe(
      firstObservedAtMs + STATUS_AUTO_POLL_WINDOW_MS,
    )
  })

  it('provides a closed Russian label for every reachable catalog value', () => {
    expect(Object.keys(BLOCK_LABELS)).toEqual([
      'requisites',
      'finance',
      'arbitration',
      'bankruptcy',
      'tax',
      'management',
    ])
    expect(Object.keys(DATASET_LABELS)).toEqual([
      'counterparty',
      'finance',
      'arbitration',
      'bankruptcy',
      'tax_info',
    ])
    expect(Object.keys(COVERAGE_LABELS)).toEqual([
      'available',
      'available_empty',
      'not_found',
      'not_requested',
      'partial',
      'failed',
      'conflict',
    ])
    expect(Object.keys(FINANCE_LABELS)).toHaveLength(20)
    expect(ROLE_LABELS.unattributed).toBe('Не отнесено')
    expect(STATUS_LABELS.completed).toBe('Завершённые')
    expect(RESULT_LABELS.undefined).toBe('Не определено')
  })

  it('classifies terminal and retryable failures without exposing payload text', () => {
    expect(
      classifyH1Error(
        new ApiHttpError(429, { detail: { message: 'secret' } }),
        'status',
      ),
    ).toEqual({
      kind: 'retryable',
      message: 'Слишком много запросов. Повторите позже.',
      operation: 'status',
    })
    expect(
      classifyH1Error(
        new ApiHttpError(409, { detail: { code: 'report_failed' } }),
        'read',
      ),
    ).toEqual({
      kind: 'terminal',
      message: 'Отчёт не сформирован',
      operation: null,
    })
    expect(
      classifyH1Error(
        new ApiHttpError(409, { detail: { code: 'unknown_conflict' } }),
        'read',
      ).kind,
    ).toBe('terminal')
    expect(classifyH1Error(new Error('raw network detail'), 'create')).toEqual({
      kind: 'retryable',
      message: 'Не удалось подключиться к сервису. Повторите попытку.',
      operation: 'create',
    })
  })

  it('runs the inline bootstrap before telemetry only for a strict company path', () => {
    const bootstrap = bootstrapSource()
    expect(indexHtml.indexOf(bootstrap)).toBeLessThan(indexHtml.indexOf('ym(108400392'))
    expect(bootstrap).not.toMatch(/\b(?:fetch|XMLHttpRequest|sendBeacon|console|ym)\b/)

    runBootstrap('/')
    expect(document.documentElement.lang).toBe('en')
    expect(document.head.querySelectorAll(ownedSelector)).toHaveLength(0)

    runBootstrap('/company/1234567890-safe-name')
    expect(document.documentElement.lang).toBe('ru')
    expect(
      document.documentElement.getAttribute(HEAD_PREVIOUS_LANG_ATTRIBUTE),
    ).toBe('en')
    const robots = document.head.querySelectorAll(
      `${ownedSelector}[${HEAD_KIND_ATTRIBUTE}="robots"]`,
    )
    expect(robots).toHaveLength(1)
    expect(robots[0].getAttribute('content')).toBe('noindex,follow')
  })

  it('adopts one bootstrap robots owner, stays noindex, and owns one canonical', () => {
    runBootstrap('/company/1234567890-safe-name')
    const bootstrapRobots = document.head.querySelector(ownedSelector)
    const duplicate = bootstrapRobots?.cloneNode(true)
    if (duplicate) document.head.append(duplicate)
    const foreignRobots = document.createElement('meta')
    foreignRobots.name = 'robots'
    foreignRobots.content = 'index,follow'
    document.head.append(foreignRobots)

    beginCompanyHead()
    const ownedRobots = document.head.querySelectorAll(
      `${ownedSelector}[${HEAD_KIND_ATTRIBUTE}="robots"]`,
    )
    expect(ownedRobots).toHaveLength(1)
    expect(ownedRobots[0]).toBe(bootstrapRobots)
    expect(ownedRobots[0].getAttribute('content')).toBe('noindex,follow')

    setCompanyHead(dto)
    setCompanyHead(dto)
    expect(document.title).toBe('ООО Синтетика — ИНН 1234567890')
    expect(document.documentElement.lang).toBe('ru')
    expect(document.head.querySelectorAll(ownedSelector)).toHaveLength(2)
    const canonical = document.head.querySelector(
      `link${ownedSelector}[${HEAD_KIND_ATTRIBUTE}="canonical"]`,
    )
    expect(canonical?.getAttribute('href')).toBe(dto.canonical_path)
    expect(ownedRobots[0].getAttribute('content')).toBe('noindex,follow')
    expect(foreignRobots.isConnected).toBe(true)
  })

  it('removes stale canonical in safe states and restores pre-bootstrap title/lang', () => {
    runBootstrap('/company/1234567890-safe-name')
    setCompanyHead(dto)
    setCompanySafeTitle('Публичный отчёт недоступен')
    expect(document.title).toBe('Публичный отчёт недоступен')
    expect(
      document.head.querySelector(
        `${ownedSelector}[${HEAD_KIND_ATTRIBUTE}="canonical"]`,
      ),
    ).toBeNull()
    expect(
      document.head.querySelector(
        `${ownedSelector}[${HEAD_KIND_ATTRIBUTE}="robots"]`,
      )?.getAttribute('content'),
    ).toBe('noindex,follow')

    cleanupCompanyHead()
    expect(document.title).toBe('Исходный заголовок')
    expect(document.documentElement.lang).toBe('en')
    expect(document.head.querySelectorAll(ownedSelector)).toHaveLength(0)
    expect(
      document.documentElement.hasAttribute(HEAD_PREVIOUS_LANG_ATTRIBUTE),
    ).toBe(false)
  })
})
