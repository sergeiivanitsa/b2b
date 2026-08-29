import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { FinanceFacts } from './FinanceFacts'
import { parseCompanyPublicH2 } from './contract'
import fixture from '../../../../shared/fixtures/company_public_h2_contract_v1.json?raw'

afterEach(cleanup)

describe('FinanceFacts', () => {
  it('renders factual semantic tables and separate F3 panels without a chart dependency', async () => {
    const dto = (await parseCompanyPublicH2(fixture)).dto
    render(<FinanceFacts dto={dto} />)
    expect(screen.getByRole('heading', { name: 'Ликвидность' })).toBeTruthy()
    expect(screen.getByRole('table', { name: 'Структура финансирования по годам' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Выручка' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Активы' })).toBeTruthy()
    expect(screen.getByRole('table', { name: 'Финансовые показатели по годам' })).toBeTruthy()
    expect(document.querySelectorAll('[data-h2-finance-enhancement]').length).toBe(5)
    expect(document.querySelectorAll('[data-h2-finance-coverage]').length).toBe(5)
    for (const blockId of ['finance_f1', 'finance_f2', 'finance_f3', 'finance_f4', 'finance_f5']) {
      expect(screen.getByRole('region', { name: `Ограничения финансового представления ${blockId}` })).toBeTruthy()
    }
    expect(screen.getByText('Срок и вероятность погашения дебиторской задолженности не оцениваются.')).toBeTruthy()
  })

  it('keeps a null article factual and renders its referenced limitations', async () => {
    const dto = (await parseCompanyPublicH2(fixture)).dto
    const limitation = { code: 'finance_missing', block_id: 'finance_f2', field_id: null, message: 'Сохранённые данные для представления отсутствуют.' } as const
    const missingDto = {
      ...dto,
      blocks: { ...dto.blocks, finance_f2: null },
      coverage: dto.coverage.map(item => item.block_id === 'finance_f2' ? { ...item, state: 'missing' as const, limitation_codes: [limitation.code] } : item),
      limitations: [...dto.limitations, limitation],
    }
    const { container } = render(<FinanceFacts dto={missingDto} />)
    const article = container.querySelector<HTMLElement>('#finance-f2')!
    expect(within(article).getByText('Подтверждённые финансовые данные не опубликованы.')).toBeTruthy()
    expect(within(article).getByRole('link', { name: limitation.message }).getAttribute('href')).toBe('#limitation-finance_missing')
    expect(article.querySelector('[data-h2-finance-enhancement]')?.childElementCount).toBe(0)
  })
})
