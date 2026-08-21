import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import latestFixture from '../../companyReport/fixtures/company-public-h1-latest-unpublished.json?raw'
import publishedFixture from '../../companyReport/fixtures/company-public-h1-published.json?raw'
import publishedSsrFixture from '../../companyReport/fixtures/company-public-h1-published-ssr.html?raw'
import { parseCompanyPublicH1 } from '../../companyReport/companyReportH1Contract'
import {
  BLOCK_LABELS,
  COVERAGE_LABELS,
  DATASET_LABELS,
  displayIsoDate,
  FINANCE_LABELS,
  limitationDomId,
  RESULT_LABELS,
  ROLE_LABELS,
  STATUS_LABELS,
} from '../../companyReport/companyReportPresentation'
import { CompanyReportContent } from './CompanyReportContent'
import { CompanyReportH1Block } from './CompanyReportH1Blocks'

const published = parseCompanyPublicH1(JSON.parse(publishedFixture))
const latest = parseCompanyPublicH1(JSON.parse(latestFixture))

function publishedSsrDocument(): Document {
  return new DOMParser().parseFromString(publishedSsrFixture, 'text/html')
}

function extractedSsrFields(document: Document): Record<string, string> {
  const fields: Record<string, string> = {}
  document.querySelectorAll<HTMLElement>('[data-field]').forEach((node) => {
    const field = node.dataset.field
    const value = node.querySelector<HTMLElement>('.field-value')
    if (!field || !value) return
    if (Object.hasOwn(fields, field)) {
      throw new Error(`Duplicate SSR field: ${field}`)
    }
    fields[field] = value.textContent ?? ''
  })
  return fields
}

function expectedPublishedSsrFields(): Record<string, string> {
  const fields: Record<string, string> = {}
  const add = (field: string, value: unknown) => {
    if (value !== null && value !== undefined) fields[field] = String(value)
  }

  add('checked_at', published.checked_at)
  add('checked_date', published.checked_date)
  add('checked_date_display', published.checked_date_display)
  Object.entries(published.identity).forEach(([field, value]) =>
    add(`identity.${field}`, value),
  )
  published.coverage.forEach((item, index) => {
    for (const field of [
      'block_id',
      'dataset',
      'state',
      'total',
      'returned',
      'limit',
      'offset',
    ] as const) {
      add(`coverage.${index}.${field}`, item[field])
    }
    item.limitation_codes.forEach((code, codeIndex) =>
      add(`coverage.${index}.limitation_codes.${codeIndex}`, code),
    )
  })

  const requisites = published.blocks.requisites
  for (const field of [
    'legal_form',
    'ogrn_or_ogrnip',
    'kpp',
    'registration_date',
    'dissolved_date',
  ] as const) {
    add(`requisites.${field}`, requisites[field])
  }
  if (requisites.region) {
    Object.entries(requisites.region).forEach(([field, value]) =>
      add(`requisites.region.${field}`, value),
    )
  }
  if (requisites.legal_address) {
    Object.entries(requisites.legal_address).forEach(([field, value]) =>
      add(`requisites.legal_address.${field}`, value),
    )
  }

  published.blocks.finance?.metrics.forEach((metric, index) => {
    add(`finance.metrics.${index}.metric_id`, metric.metric_id)
    add(`finance.metrics.${index}.year`, metric.year)
    Object.entries(metric.yoy).forEach(([field, value]) =>
      add(`finance.metrics.${index}.yoy.${field}`, value),
    )
  })

  const arbitration = published.blocks.arbitration
  if (arbitration) {
    for (const field of [
      'total_cases',
      'returned_cases',
      'normalized_case_count',
      'malformed_count',
      'limit',
      'offset',
      'unattributed_count',
    ] as const) {
      add(`arbitration.${field}`, arbitration[field])
    }
    for (const [group, values] of [
      ['role_counts', arbitration.role_counts],
      ['status_counts', arbitration.status_counts],
      ['result_counts', arbitration.result_counts],
    ] as const) {
      Object.entries(values).forEach(([field, value]) =>
        add(`arbitration.${group}.${field}`, value),
      )
    }
    arbitration.claim_amounts.forEach((amount, index) => {
      Object.entries(amount).forEach(([field, value]) =>
        add(`arbitration.claim_amounts.${index}.${field}`, value),
      )
    })
    arbitration.selected_cases.forEach((caseItem, index) => {
      for (const field of [
        'case_number',
        'date_start',
        'date_update',
        'attributed_role',
      ] as const) {
        add(`arbitration.selected_cases.${index}.${field}`, caseItem[field])
      }
      if (caseItem.claim_amount) {
        Object.entries(caseItem.claim_amount).forEach(([field, value]) =>
          add(
            `arbitration.selected_cases.${index}.claim_amount.${field}`,
            value,
          ),
        )
      }
    })
  }

  published.sources.forEach((source, index) => {
    Object.entries(source).forEach(([field, value]) =>
      add(`sources.${index}.${field}`, value),
    )
  })
  published.limitations.forEach((limitation, index) => {
    Object.entries(limitation).forEach(([field, value]) =>
      add(`limitations.${index}.${field}`, value),
    )
  })
  published.actions.forEach((action, index) => {
    Object.entries(action).forEach(([field, value]) =>
      add(`actions.${index}.${field}`, value),
    )
  })
  published.breadcrumbs.forEach((breadcrumb, index) => {
    Object.entries(breadcrumb).forEach(([field, value]) =>
      add(`breadcrumbs.${index}.${field}`, value),
    )
  })
  return fields
}

function normalizedText(node: Element | null): string {
  return (node?.textContent ?? '').replace(/\s+/g, ' ').trim()
}

function definitionValues(section: Element): Record<string, string> {
  return Object.fromEntries(
    Array.from(section.querySelectorAll('dl > div')).map((row) => [
      normalizedText(row.querySelector('dt')),
      normalizedText(row.querySelector('dd')),
    ]),
  )
}

function distributionValues(section: Element, index: number): Record<string, string> {
  const list = section.querySelectorAll('.company-report-distribution')[index]
  return Object.fromEntries(
    Array.from(list.querySelectorAll(':scope > li')).map((row) => [
      normalizedText(row.querySelector('span')),
      normalizedText(row.querySelector('strong')),
    ]),
  )
}

function renderBlock(id: (typeof published.block_order)[number]) {
  return render(
    <MemoryRouter>
      <CompanyReportH1Block id={id} dto={published} />
    </MemoryRouter>,
  )
}

function LocationProbe() {
  const location = useLocation()
  return <p data-testid="claims-location">{`${location.pathname}${location.search}`}</p>
}

describe('CompanyReport H1 blocks', () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
  })

  afterEach(cleanup)

  it('renders the identity and checked-date strings exactly as supplied', () => {
    renderBlock('identity_status')
    expect(
      screen.getByRole('heading', {
        level: 1,
        name: `${published.identity.legal_full_name} — ИНН ${published.identity.inn}`,
      }),
    ).toBeTruthy()
    const time = screen.getByText(published.checked_date_display)
    expect(time.tagName).toBe('TIME')
    expect(time.getAttribute('datetime')).toBe(published.checked_at)
    expect(screen.getByText(published.identity.legal_short_name!)).toBeTruthy()
  })

  it('keeps root, checked-date, identity, coverage, and requisite semantics aligned across API, SSR, and SPA', () => {
    const ssr = publishedSsrDocument()
    expect(extractedSsrFields(ssr)).toEqual(expectedPublishedSsrFields())

    const { container } = render(
      <MemoryRouter>
        <CompanyReportContent view={{ kind: 'content', dto: published }} />
      </MemoryRouter>,
    )
    const ssrMain = ssr.querySelector('main')!
    const spaMain = container.querySelector('main')!
    for (const [ssrAttribute, spaAttribute, expected] of [
      [
        'data-contract-version',
        'data-company-contract',
        published.contract_version,
      ],
      ['data-report-id', 'data-company-report-id', published.report_id],
      [
        'data-report-version',
        'data-company-report-version',
        published.report_version,
      ],
      [
        'data-projection-scope',
        'data-company-projection-scope',
        published.projection_scope,
      ],
      [
        'data-canonical-path',
        'data-company-canonical-path',
        published.canonical_path,
      ],
      [
        'data-indexable',
        'data-company-indexable',
        String(published.indexable),
      ],
      [
        'data-block-order',
        'data-company-block-order',
        published.block_order.join(','),
      ],
    ]) {
      expect(ssrMain.getAttribute(ssrAttribute)).toBe(expected)
      expect(spaMain.getAttribute(spaAttribute)).toBe(expected)
    }

    expect(
      normalizedText(ssr.querySelector('[data-field="identity.status"]')),
    ).toBe('Статус не отображён')
    expect(
      screen.getByRole('heading', {
        level: 1,
        name: `${published.identity.legal_full_name} — ИНН ${published.identity.inn}`,
      }),
    ).toBeTruthy()
    expect(
      normalizedText(
        container.querySelector('.company-report-hero > p:first-of-type'),
      ),
    ).toBe(published.identity.legal_short_name)
    const checkedTime = screen.getByText(published.checked_date_display)
    expect(checkedTime.getAttribute('datetime')).toBe(published.checked_at)

    const coverageRows = Array.from(
      container.querySelectorAll('.company-report-coverage > li'),
    )
    expect(coverageRows).toHaveLength(published.coverage.length)
    published.coverage.forEach((item, index) => {
      const text = normalizedText(coverageRows[index])
      expect(text).toContain(BLOCK_LABELS[item.block_id])
      expect(text).toContain(DATASET_LABELS[item.dataset])
      expect(text).toContain(COVERAGE_LABELS[item.state])
      for (const [label, value] of [
        ['Всего', item.total],
        ['Получено', item.returned],
        ['Лимит', item.limit],
        ['Смещение', item.offset],
      ] as const) {
        if (value !== null) expect(text).toContain(`${label}: ${value}`)
      }
    })

    const requisites = published.blocks.requisites
    const expectedRequisites: Record<string, string> = {}
    if (requisites.ogrn_or_ogrnip) {
      expectedRequisites['ОГРН/ОГРНИП'] = requisites.ogrn_or_ogrnip
    }
    if (requisites.kpp) expectedRequisites['КПП'] = requisites.kpp
    if (requisites.registration_date) {
      expectedRequisites['Дата регистрации'] = displayIsoDate(
        requisites.registration_date,
      )
    }
    if (requisites.dissolved_date) {
      expectedRequisites['Дата прекращения деятельности'] = displayIsoDate(
        requisites.dissolved_date,
      )
    }
    if (requisites.region?.name) {
      expectedRequisites['Регион'] = requisites.region.name
    }
    if (requisites.region?.code) {
      expectedRequisites['Код региона'] = requisites.region.code
    }
    if (requisites.legal_address) {
      expectedRequisites['Юридический адрес'] =
        requisites.legal_address.display_line
      if (requisites.legal_address.is_inaccuracy !== null) {
        expectedRequisites['Адрес помечен источником как недостоверный'] =
          requisites.legal_address.is_inaccuracy ? 'Да' : 'Нет'
      }
    }
    expect(definitionValues(container.querySelector('#requisites')!)).toEqual(
      expectedRequisites,
    )
  })

  it('keeps finance and arbitration facts aligned across API, SSR, and SPA, including the complete saved case slice', () => {
    const { container } = render(
      <MemoryRouter>
        <CompanyReportContent view={{ kind: 'content', dto: published }} />
      </MemoryRouter>,
    )
    const finance = published.blocks.finance!
    const financeItems = Array.from(
      container.querySelectorAll('#finance .company-report-facts > li'),
    )
    expect(financeItems).toHaveLength(finance.metrics.length)
    finance.metrics.forEach((metric, index) => {
      expect(normalizedText(financeItems[index])).toBe(
        `${FINANCE_LABELS[metric.metric_id]}: ${metric.yoy.current_year} к ${metric.yoy.previous_year} — ${metric.yoy.display_value}`,
      )
    })

    const arbitration = published.blocks.arbitration!
    const arbitrationSection = container.querySelector('#arbitration')!
    expect(definitionValues(arbitrationSection)).toEqual({
      'Всего дел в источнике': String(arbitration.total_cases),
      'Получено в сохранённом ответе': String(arbitration.returned_cases),
      Нормализовано: String(arbitration.normalized_case_count),
      'Некорректных записей': String(arbitration.malformed_count),
      'Лимит сохранённой выборки': String(arbitration.limit),
      'Смещение сохранённой выборки': String(arbitration.offset),
    })

    const roles = distributionValues(arbitrationSection, 0)
    Object.entries(arbitration.role_counts).forEach(([role, value]) => {
      expect(roles[ROLE_LABELS[role as keyof typeof ROLE_LABELS]]).toBe(
        String(value),
      )
    })
    expect(roles[ROLE_LABELS.unattributed]).toBe(
      String(arbitration.unattributed_count),
    )
    const statuses = distributionValues(arbitrationSection, 1)
    Object.entries(arbitration.status_counts).forEach(([status, value]) => {
      const label = STATUS_LABELS[status as keyof typeof STATUS_LABELS]
      expect(statuses[label]).toBe(String(value))
    })
    const results = distributionValues(arbitrationSection, 2)
    Object.entries(arbitration.result_counts).forEach(([result, value]) => {
      const label = RESULT_LABELS[result as keyof typeof RESULT_LABELS]
      expect(results[label]).toBe(String(value))
    })

    const claimHeading = Array.from(
      arbitrationSection.querySelectorAll('h3'),
    ).find((heading) => heading.textContent === 'Суммы требований по отнесённой роли')
    const claimItems = Array.from(
      claimHeading?.nextElementSibling?.querySelectorAll(':scope > li') ?? [],
    )
    expect(claimItems).toHaveLength(arbitration.claim_amounts.length)
    arbitration.claim_amounts.forEach((amount, index) => {
      expect(normalizedText(claimItems[index])).toBe(
        `${ROLE_LABELS[amount.role]}: ${amount.display_value}`,
      )
    })

    const caseArticles = Array.from(
      arbitrationSection.querySelectorAll('.company-report-cases > article'),
    )
    expect(caseArticles).toHaveLength(10)
    expect(caseArticles).toHaveLength(arbitration.selected_cases.length)
    arbitration.selected_cases.forEach((caseItem, index) => {
      const article = caseArticles[index]
      expect(normalizedText(article.querySelector('h4'))).toBe(
        caseItem.case_number,
      )
      const text = normalizedText(article)
      expect(text).toContain(`Роль: ${ROLE_LABELS[caseItem.attributed_role]}`)
      if (caseItem.date_start) {
        expect(text).toContain(
          `Дата начала: ${displayIsoDate(caseItem.date_start)}`,
        )
      }
      if (caseItem.date_update) {
        expect(text).toContain(
          `Дата обновления: ${displayIsoDate(caseItem.date_update)}`,
        )
      }
      if (caseItem.claim_amount) {
        expect(text).toContain(
          `Сумма требования: ${caseItem.claim_amount.display_value}`,
        )
      }
    })
  })

  it('keeps sources, fixed limitations, actions, and breadcrumbs aligned across API, SSR, and SPA', () => {
    const ssr = publishedSsrDocument()
    const { container } = render(
      <MemoryRouter>
        <CompanyReportContent view={{ kind: 'content', dto: published }} />
      </MemoryRouter>,
    )

    const sourceRows = Array.from(
      container.querySelectorAll('.company-report-sources > li'),
    )
    expect(sourceRows).toHaveLength(published.sources.length)
    published.sources.forEach((source, index) => {
      const text = normalizedText(sourceRows[index])
      expect(text).toContain(DATASET_LABELS[source.dataset])
      expect(text).toContain(`Получено: ${source.received_at}`)
      if (source.effective_at) {
        expect(text).toContain(`Дата сведений: ${source.effective_at}`)
      }
      if (source.period) expect(text).toContain(`Период: ${source.period}`)
      expect(text).toContain(`Нормализация: ${source.normalization_version}`)
    })

    published.limitations.forEach((limitation) => {
      expect(
        container.querySelector(`#${limitationDomId(limitation.code)}`)
          ?.textContent,
      ).toBe(limitation.message)
    })

    const spaActions = Array.from(
      container.querySelectorAll<HTMLAnchorElement>(
        '.company-report-actions > a',
      ),
    )
    const ssrActions = Array.from(
      ssr.querySelectorAll<HTMLAnchorElement>('[data-action-id]'),
    )
    expect(spaActions).toHaveLength(published.actions.length)
    expect(ssrActions).toHaveLength(published.actions.length)
    published.actions.forEach((action, index) => {
      expect(normalizedText(spaActions[index])).toBe(action.label)
      expect(spaActions[index].getAttribute('href')).toBe(action.path)
      expect(normalizedText(ssrActions[index])).toContain(action.label)
      expect(ssrActions[index].dataset.actionId).toBe(action.action_id)
      expect(ssrActions[index].getAttribute('href')).toBe(action.path)
    })

    const spaBreadcrumbs = Array.from(
      container.querySelectorAll('.company-report-breadcrumbs > ol > li'),
    )
    const ssrBreadcrumbs = Array.from(
      ssr.querySelectorAll('#breadcrumbs > ol > li'),
    )
    expect(spaBreadcrumbs).toHaveLength(published.breadcrumbs.length)
    expect(ssrBreadcrumbs).toHaveLength(published.breadcrumbs.length)
    published.breadcrumbs.forEach((breadcrumb, index) => {
      const spaItem = spaBreadcrumbs[index]
      const ssrLink = ssrBreadcrumbs[index].querySelector('a')!
      expect(normalizedText(spaItem.querySelector('a, span'))).toBe(
        breadcrumb.label,
      )
      expect(normalizedText(ssrLink)).toContain(breadcrumb.label)
      expect(ssrLink.getAttribute('href')).toBe(breadcrumb.path)
      if (index === published.breadcrumbs.length - 1) {
        expect(spaItem.querySelector('[aria-current="page"]')).toBeTruthy()
      } else {
        expect(spaItem.querySelector('a')?.getAttribute('href')).toBe(
          breadcrumb.path,
        )
      }
    })
  })

  it('renders requisites without inventing a structured address or losing false', () => {
    const { container } = renderBlock('requisites')
    expect(screen.getByText('02.01.2020')).toBeTruthy()
    expect(
      screen.getByText(published.blocks.requisites.legal_address!.display_line),
    ).toBeTruthy()
    expect(screen.getByText('Нет')).toBeTruthy()
    expect(container.textContent).not.toContain('Длинная тестовая улица,')
    expect(container.textContent).not.toContain('Организационно-правовая форма')
  })

  it('preserves backend YoY and claim displays verbatim and preserves numeric zero', () => {
    const result = renderBlock('finance')
    expect(screen.getByText(/2025 к 2024 — \+12,3%/)).toBeTruthy()
    expect(screen.queryByText('12.34')).toBeNull()

    result.rerender(
      <MemoryRouter>
        <CompanyReportH1Block id="arbitration" dto={published} />
      </MemoryRouter>,
    )
    expect(result.container.textContent).toContain(
      published.blocks.arbitration!.claim_amounts[0].display_value,
    )
    expect(screen.getAllByText('0').length).toBeGreaterThan(0)
    expect(screen.getByText('Не отнесено')).toBeTruthy()
    expect(screen.getAllByText('Иное')).toHaveLength(2)
  })

  it('renders all ten selected cases inside a labelled focusable dense region', () => {
    renderBlock('arbitration')
    const region = screen.getByRole('region', {
      name: 'Выбранные арбитражные дела',
    })
    expect(region.getAttribute('tabindex')).toBe('0')
    expect(within(region).getAllByRole('article')).toHaveLength(10)
    expect(
      within(region).getByText(
        'A40-000001-2026-синтетическое-длинное-дело',
      ),
    ).toBeTruthy()
  })

  it('renders backend-valid duplicate case numbers without React key collisions', () => {
    const duplicateNumberPayload = JSON.parse(publishedFixture) as {
      blocks: {
        arbitration: {
          selected_cases: Array<{ case_number: string }>
        }
      }
    }
    const duplicateCaseNumber =
      duplicateNumberPayload.blocks.arbitration.selected_cases[0].case_number
    duplicateNumberPayload.blocks.arbitration.selected_cases[1].case_number =
      duplicateCaseNumber
    const duplicateNumberDto = parseCompanyPublicH1(duplicateNumberPayload)
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined)

    try {
      render(
        <MemoryRouter>
          <CompanyReportH1Block id="arbitration" dto={duplicateNumberDto} />
        </MemoryRouter>,
      )

      const region = screen.getByRole('region', {
        name: 'Выбранные арбитражные дела',
      })
      const duplicateArticles = within(region)
        .getAllByRole('article')
        .filter(
          (article) =>
            within(article).queryByRole('heading', {
              level: 4,
              name: duplicateCaseNumber,
            }) !== null,
        )

      expect(duplicateArticles).toHaveLength(2)
      expect(normalizedText(duplicateArticles[0])).toContain(
        'Дата начала: 01.01.2026',
      )
      expect(normalizedText(duplicateArticles[0])).toContain(
        'Сумма требования: 1000,5 RUB',
      )
      expect(normalizedText(duplicateArticles[1])).not.toContain('Дата начала:')
      expect(normalizedText(duplicateArticles[1])).not.toContain(
        'Сумма требования:',
      )
      cleanup()
      expect(consoleError).not.toHaveBeenCalled()
    } finally {
      consoleError.mockRestore()
    }
  })

  it('connects coverage and factual sections to stable limitation messages', () => {
    const result = render(
      <MemoryRouter>
        <CompanyReportContent view={{ kind: 'content', dto: published }} />
      </MemoryRouter>,
    )
    const limitationId = limitationDomId('arbitration_partial_slice')
    const limitation = result.container.querySelector(`#${limitationId}`)
    expect(limitation?.textContent).toBe(
      'Показана только сохранённая часть арбитражных сведений.',
    )
    const coverageItem = screen
      .getByText('Доступна часть сведений')
      .closest('li')
    expect(coverageItem?.getAttribute('aria-describedby')?.split(' ')).toContain(
      limitationId,
    )
    expect(
      result.container
        .querySelector('#arbitration')
        ?.getAttribute('aria-describedby')
        ?.split(' '),
    ).toContain(limitationId)
  })

  it('renders backend block order and only approved public H1 surfaces', () => {
    const { container } = render(
      <MemoryRouter>
        <CompanyReportContent view={{ kind: 'content', dto: published }} />
      </MemoryRouter>,
    )
    const main = container.querySelector('main')!
    expect(main.getAttribute('data-company-block-order')).toBe(
      published.block_order.join(','),
    )
    const topLevel = Array.from(main.children)
      .slice(1)
      .map((node) =>
        node.querySelector('h1,h2')?.textContent ??
        node.getAttribute('aria-label'),
      )
    expect(topLevel).toEqual([
      'Хлебные крошки',
      `${published.identity.legal_full_name} — ИНН ${published.identity.inn}`,
      'Что известно',
      'Разделы отчёта',
      'Покрытие и дата проверки',
      'Реквизиты',
      'Финансовые показатели',
      'Арбитраж',
      'Источники и ограничения',
      'Действия',
    ])
    for (const forbidden of [
      'raw_payload',
      'signals',
      'score',
      'verdict',
      'probability',
      'AI-пояснение',
      'Создать новый отчёт',
      'Статус отчёта',
    ]) {
      expect(container.textContent).not.toContain(forbidden)
    }
  })

  it('does not turn unavailable latest facts into zero or an overall status', () => {
    const { container } = render(
      <MemoryRouter>
        <CompanyReportContent view={{ kind: 'content', dto: latest }} />
      </MemoryRouter>,
    )
    expect(screen.queryByRole('heading', { name: 'Финансовые показатели' })).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Арбитраж' })).toBeNull()
    expect(screen.getAllByText('Сведения не запрашивались')).toHaveLength(3)
    expect(container.textContent).not.toContain('Всего: 0')
    expect(container.textContent).not.toContain('отчёт готов')
    expect(container.textContent).not.toContain('данные неполные')
  })

  it('passes only the displayed final H1 UUID to Claims and writes no context storage', () => {
    sessionStorage.setItem('sentinel', 'session-safe')
    localStorage.setItem('sentinel', 'local-safe')
    render(
      <MemoryRouter initialEntries={[published.canonical_path]}>
        <Routes>
          <Route
            path="/company/:companyKey"
            element={<CompanyReportH1Block id="neutral_actions" dto={published} />}
          />
          <Route path="/claims" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>,
    )
    fireEvent.click(screen.getByRole('link', { name: 'Подготовить претензию' }))
    expect(screen.getByTestId('claims-location').textContent).toBe(
      `/claims?report_id=${published.report_id}`,
    )
    expect(sessionStorage.length).toBe(1)
    expect(sessionStorage.getItem('sentinel')).toBe('session-safe')
    expect(localStorage.length).toBe(1)
    expect(localStorage.getItem('sentinel')).toBe('local-safe')
  })
})
