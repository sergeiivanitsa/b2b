import type { ReactNode } from 'react'
import type { CompanyPublicH2, PublicH2CoverageItemDto, PublicH2FinanceF1Dto, PublicH2FinanceF2Dto, PublicH2FinanceF3Dto, PublicH2FinanceF4Dto, PublicH2FinanceF5Dto, PublicH2LimitationDto, PublicH2MoneyDto } from './contractSchema'
import { moneyCompact, moneyExact, multiple, percent, per100, year } from './financePresentation'

export const FINANCE_ARTICLE_IDS = ['finance-f1', 'finance-f2', 'finance-f3', 'finance-f4', 'finance-f5'] as const
const F1_ADVISORY = 'Срок и вероятность погашения дебиторской задолженности не оцениваются.'
type FinanceBlockId = 'finance_f1' | 'finance_f2' | 'finance_f3' | 'finance_f4' | 'finance_f5'
type FactsContext = Readonly<{ coverage: PublicH2CoverageItemDto; limitations: readonly PublicH2LimitationDto[] }>

function Money({ value }: { value: PublicH2MoneyDto | null }) { return <>{value === null ? '—' : <span title={moneyExact(value)}>{moneyCompact(value)}</span>}</> }
function FactsShell({ id, title, children, context, advisory = false }: { id: string; title: string; children: ReactNode; context: FactsContext; advisory?: boolean }) {
  return <article id={id} data-h2-finance-article={id}>
    <h3>{title}</h3>
    <p data-h2-finance-coverage={context.coverage.block_id}>Покрытие представления: {context.coverage.state}.</p>
    {advisory && <p data-h2-finance-advisory="receivables_collection_unassessed">{F1_ADVISORY}</p>}
    {children}
    <section aria-label={`Ограничения финансового представления ${context.coverage.block_id}`} data-h2-finance-limitations={context.coverage.block_id}>
      <h4>Ограничения</h4>
      {context.limitations.length === 0
        ? <p>Ограничения для этого представления не указаны.</p>
        : <ul>{context.limitations.map(item => <li data-h2-finance-limitation={item.code} key={item.code}><a href={`#limitation-${item.code}`}>{item.message}</a></li>)}</ul>}
    </section>
    <div className="company-public-h2__finance-enhancement" data-h2-finance-enhancement={id} aria-hidden="true" />
  </article>
}

export function FinanceF1Facts({ view, context }: { view: PublicH2FinanceF1Dto | null; context: FactsContext }) {
  if (!view) return <FactsShell id="finance-f1" title="Ликвидность" context={context}><p>Подтверждённые финансовые данные не опубликованы.</p></FactsShell>
  return <FactsShell id="finance-f1" title="Ликвидность" context={context} advisory>
    <p>Период: <time>{year(view.year)}</time></p>
    <dl><dt>Денежные средства</dt><dd><Money value={view.cash_1250} /></dd><dt>Финансовые вложения</dt><dd><Money value={view.investments_1240} /></dd><dt>Дебиторская задолженность</dt><dd><Money value={view.receivables_1230} /></dd><dt>Краткосрочные обязательства</dt><dd><Money value={view.short_liabilities_1500} /></dd><dt>Доступно без запасов</dt><dd><Money value={view.available_without_inventory} /></dd><dt>Разница</dt><dd><Money value={view.difference} /></dd></dl>
  </FactsShell>
}

export function FinanceF2Facts({ view, context }: { view: PublicH2FinanceF2Dto | null; context: FactsContext }) {
  if (!view) return <FactsShell id="finance-f2" title="Структура финансирования" context={context}><p>Подтверждённые финансовые данные не опубликованы.</p></FactsShell>
  return <FactsShell id="finance-f2" title="Структура финансирования" context={context}><table><caption>Структура финансирования по годам</caption><thead><tr><th scope="col">Год</th><th scope="col">Собственные средства</th><th scope="col">Долг</th><th scope="col">Доля собственных средств</th><th scope="col">Доля долга</th></tr></thead><tbody>{view.periods.map(item => <tr key={year(item.year)}><th scope="row">{year(item.year)}</th><td><Money value={item.equity_1300} /></td><td><Money value={item.debt} /></td><td>{percent(item.equity_share_decimal)}</td><td>{percent(item.debt_share_decimal)}</td></tr>)}</tbody></table></FactsShell>
}

function F3Panel({ label, points, summary, metric }: { label: string; points: PublicH2FinanceF3Dto['points']; summary: PublicH2FinanceF3Dto['revenue_summary']; metric: 'revenue' | 'assets' }) {
  return <section aria-label={label}><h4>{label}</h4><table><caption>{label} по годам</caption><thead><tr><th scope="col">Год</th><th scope="col">Значение</th><th scope="col">Изменение год к году</th></tr></thead><tbody>{points.map(point => { const value = metric === 'revenue' ? point.revenue_2110 : point.assets_1600; const yoy = metric === 'revenue' ? point.revenue_yoy_decimal : point.assets_yoy_decimal; return <tr key={year(point.year)}><th scope="row">{year(point.year)}</th><td><Money value={value} /></td><td>{percent(yoy)}</td></tr> })}</tbody></table><p>Изменение за период: <Money value={summary.change} />; мультипликатор: {multiple(summary.multiple_decimal)}</p></section>
}
export function FinanceF3Facts({ view, context }: { view: PublicH2FinanceF3Dto | null; context: FactsContext }) {
  if (!view) return <FactsShell id="finance-f3" title="Выручка и активы" context={context}><p>Подтверждённые финансовые данные не опубликованы.</p></FactsShell>
  return <FactsShell id="finance-f3" title="Выручка и активы" context={context}><F3Panel label="Выручка" points={view.points} summary={view.revenue_summary} metric="revenue" /><F3Panel label="Активы" points={view.points} summary={view.assets_summary} metric="assets" /></FactsShell>
}

export function FinanceF4Facts({ view, context }: { view: PublicH2FinanceF4Dto | null; context: FactsContext }) {
  if (!view) return <FactsShell id="finance-f4" title="Прибыль на 100 рублей выручки" context={context}><p>Подтверждённые финансовые данные не опубликованы.</p></FactsShell>
  return <FactsShell id="finance-f4" title="Прибыль на 100 рублей выручки" context={context}><p>Период: <time>{year(view.year)}</time></p><dl><dt>Выручка</dt><dd>{per100(view.revenue_per_100_decimal)}</dd><dt>Валовая прибыль</dt><dd>{per100(view.gross_per_100_decimal)}</dd><dt>Прибыль от продаж</dt><dd>{per100(view.operating_per_100_decimal)}</dd><dt>Чистая прибыль</dt><dd>{per100(view.net_per_100_decimal)}</dd></dl></FactsShell>
}

export function FinanceF5Facts({ view, context }: { view: PublicH2FinanceF5Dto | null; context: FactsContext }) {
  if (!view) return <FactsShell id="finance-f5" title="Финансовые показатели по годам" context={context}><p>Подтверждённые финансовые данные не опубликованы.</p></FactsShell>
  return <FactsShell id="finance-f5" title="Финансовые показатели по годам" context={context}><div className="company-public-h2__finance-table"><table><caption>Финансовые показатели по годам</caption><thead><tr><th scope="col">Показатель</th>{view.years.map(item => <th scope="col" key={year(item)}>{year(item)}</th>)}</tr></thead><tbody>{view.rows.map(row => <tr key={row.metric_id}><th scope="row">{row.label}</th>{row.cells.map(cell => <td key={year(cell.year)}><Money value={cell.value} /></td>)}</tr>)}</tbody></table></div></FactsShell>
}

function contextFor(dto: CompanyPublicH2, blockId: FinanceBlockId): FactsContext {
  const coverage = dto.coverage.find(item => item.block_id === blockId)
  if (!coverage) throw new Error(`validated finance coverage missing: ${blockId}`)
  const codes = [...coverage.limitation_codes]
  if (blockId === 'finance_f1' && dto.blocks.finance_f1 !== null && dto.limitations.some(item => item.code === 'receivables_collection_unassessed') && !codes.includes('receivables_collection_unassessed')) {
    codes.push('receivables_collection_unassessed')
  }
  return { coverage, limitations: codes.map(code => dto.limitations.find(item => item.code === code)!) }
}

export function FinanceFacts({ dto }: { dto: CompanyPublicH2 }) {
  return <>
    <FinanceF1Facts view={dto.blocks.finance_f1} context={contextFor(dto, 'finance_f1')} />
    <FinanceF2Facts view={dto.blocks.finance_f2} context={contextFor(dto, 'finance_f2')} />
    <FinanceF3Facts view={dto.blocks.finance_f3} context={contextFor(dto, 'finance_f3')} />
    <FinanceF4Facts view={dto.blocks.finance_f4} context={contextFor(dto, 'finance_f4')} />
    <FinanceF5Facts view={dto.blocks.finance_f5} context={contextFor(dto, 'finance_f5')} />
  </>
}
