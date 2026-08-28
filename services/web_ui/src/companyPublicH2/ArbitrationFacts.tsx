import type { ReactNode } from 'react'
import { classifyArbitrationPolicyV3 } from './arbitrationContractSemantics'
import {
  arbitrationCaseLabel, arbitrationCollectionLabel, arbitrationCount, arbitrationOutcomeLabel,
  arbitrationPercent, arbitrationRoleLabel, arbitrationYear,
} from './arbitrationPresentation'
import type {
  CompanyPublicH2, PublicH2ArbitrationA1Dto, PublicH2ArbitrationA2Dto, PublicH2ArbitrationA3Dto,
  PublicH2ArbitrationA4Dto, PublicH2ArbitrationA5Dto, PublicH2ArbitrationSummaryDto,
  PublicH2CoverageItemDto, PublicH2LimitationDto, PublicH2SafeCaseDetailDto,
} from './contractSchema'

export const ARBITRATION_ARTICLE_IDS = ['arbitration-a1', 'arbitration-a2', 'arbitration-a3', 'arbitration-a4', 'arbitration-a5'] as const
type ArbitrationBlockId = 'arbitration_a1' | 'arbitration_a2' | 'arbitration_a3' | 'arbitration_a4' | 'arbitration_a5'
type FactsContext = Readonly<{ coverage: PublicH2CoverageItemDto; limitations: readonly PublicH2LimitationDto[] }>

function SummaryScope({ summary }: { summary: PublicH2ArbitrationSummaryDto }) {
  return <p data-h2-arbitration-scope={summary.collection_complete ? 'complete_collection' : 'returned_slice'}>
    Охват коллекции: {arbitrationCollectionLabel(summary.collection_complete ? 'complete_collection' : 'returned_slice')}; получено {arbitrationCount(summary.rows_observed)}{summary.source_total === null ? '; общее число не подтверждено.' : <> из {arbitrationCount(summary.source_total)} дел.</>}
  </p>
}
function CaseList({ cases, label }: { cases: readonly PublicH2SafeCaseDetailDto[]; label: string }) {
  if (cases.length === 0) return null
  return <section className="company-public-h2__arbitration-details" aria-label={label}>
    <h4>{label}</h4>
    <ul>{cases.map(item => <li data-h2-case-public-id={item.case_public_id} key={item.case_public_id}>
      <strong>{arbitrationCaseLabel(item)}</strong>; публичный идентификатор: <code>{item.case_public_id}</code>; год: {arbitrationYear(item.year)}; роль: {arbitrationRoleLabel(item.role)}; исход: {arbitrationOutcomeLabel(item.outcome)}{item.amount !== null && <>; цена иска: {item.amount.display_exact}</>}{item.start_date !== null && <>; дата начала: <time>{item.start_date}</time></>}{item.update_date !== null && <>; дата обновления: <time>{item.update_date}</time></>}.
    </li>)}</ul>
  </section>
}
function FactsShell({ id, blockId, title, context, children }: { id: string; blockId: ArbitrationBlockId; title: string; context: FactsContext; children: ReactNode }) {
  return <article id={id} data-h2-arbitration-article={id}>
    <h3>{title}</h3>
    <p data-h2-arbitration-coverage={blockId}>Покрытие представления: {context.coverage.state}; {arbitrationCollectionLabel(context.coverage.population_scope)}{context.coverage.returned !== null && <>; получено {arbitrationCount(context.coverage.returned)}</>}{context.coverage.total !== null && <> из {arbitrationCount(context.coverage.total)}</>}.</p>
    {children}
    <section aria-label={`Ограничения арбитражного представления ${blockId}`} data-h2-arbitration-limitations={blockId}>
      <h4>Ограничения</h4>
      {context.limitations.length === 0
        ? <p>Ограничения для этого представления не указаны.</p>
        : <ul>{context.limitations.map(item => <li data-h2-arbitration-limitation={item.code} key={item.code}><a href={`#limitation-${item.code}`}>{item.message}</a></li>)}</ul>}
    </section>
    <div className="company-public-h2__arbitration-enhancement" data-h2-arbitration-enhancement={id} aria-hidden="true" />
  </article>
}
function unavailable(id: string, blockId: ArbitrationBlockId, title: string, context: FactsContext) {
  return <FactsShell id={id} blockId={blockId} title={title} context={context}><p>Подтверждённые арбитражные данные для этого представления не опубликованы.</p></FactsShell>
}

export function ArbitrationA1Facts({ view, context }: { view: PublicH2ArbitrationA1Dto | null; context: FactsContext }) {
  if (view === null) return unavailable('arbitration-a1', 'arbitration_a1', 'Арбитражная активность по годам', context)
  return <FactsShell id="arbitration-a1" blockId="arbitration_a1" title="Арбитражная активность по годам" context={context}>
    <SummaryScope summary={view.summary} />
    {view.summary.unique_case_count.value === 0n && <p>Подтверждённая коллекция не содержит дел.</p>}
    <div className="company-public-h2__arbitration-table"><table><caption>Количество дел по наблюдаемым годам и роли компании</caption><thead><tr><th scope="col">Год</th><th scope="col">Истец</th><th scope="col">Ответчик</th><th scope="col">Иная роль</th><th scope="col">Роль не определена</th><th scope="col">Всего</th></tr></thead><tbody>{view.buckets.map(bucket => <tr key={arbitrationYear(bucket.year)}><th scope="row">{arbitrationYear(bucket.year)}</th><td>{arbitrationCount(bucket.plaintiff_count)}</td><td>{arbitrationCount(bucket.respondent_count)}</td><td>{arbitrationCount(bucket.other_count)}</td><td>{arbitrationCount(bucket.unattributed_count)}</td><td>{arbitrationCount(bucket.total_count)}</td></tr>)}</tbody></table></div>
    {view.buckets.flatMap(bucket => bucket.role_details.map(detail => <div data-h2-arbitration-detail-scope={`${arbitrationYear(bucket.year)}.${detail.role}`} key={`${arbitrationYear(bucket.year)}.${detail.role}`}><p>{arbitrationYear(bucket.year)}, {arbitrationRoleLabel(detail.role)}: {detail.scope.label}.</p><CaseList cases={detail.cases} label={`${arbitrationYear(bucket.year)} — ${arbitrationRoleLabel(detail.role)}`} /></div>))}
  </FactsShell>
}

function BarFacts({ view, context, id, blockId, title, caption }: { view: PublicH2ArbitrationA2Dto | PublicH2ArbitrationA3Dto | null; context: FactsContext; id: string; blockId: 'arbitration_a2' | 'arbitration_a3'; title: string; caption: string }) {
  if (view === null) return unavailable(id, blockId, title, context)
  const isRoles = view.view_id === 'arbitration_a2_roles'
  return <FactsShell id={id} blockId={blockId} title={title} context={context}>
    <SummaryScope summary={view.summary} />
    <p>Знаменатель: {arbitrationCount(view.denominator)} дел.</p>
    <div className="company-public-h2__arbitration-table"><table><caption>{caption}</caption><thead><tr><th scope="col">Категория</th><th scope="col">Количество</th><th scope="col">Доля</th><th scope="col">Детализация</th></tr></thead><tbody>{view.bars.map(bar => <tr key={bar.category_id}><th scope="row">{isRoles ? arbitrationRoleLabel(bar.category_id as PublicH2ArbitrationA2Dto['bars'][number]['category_id'] & ('plaintiff' | 'respondent' | 'other' | 'unattributed')) : arbitrationOutcomeLabel(bar.category_id as PublicH2ArbitrationA3Dto['bars'][number]['category_id'] & ('won' | 'lost' | 'returned' | 'unknown'))}</th><td>{arbitrationCount(bar.count)}</td><td>{arbitrationPercent(bar.percent_decimal)}</td><td>{bar.scope.label}</td></tr>)}</tbody></table></div>
    {view.bars.map(bar => <CaseList cases={bar.cases} label={`${isRoles ? 'Роль' : 'Исход'} — ${isRoles ? arbitrationRoleLabel(bar.category_id as 'plaintiff' | 'respondent' | 'other' | 'unattributed') : arbitrationOutcomeLabel(bar.category_id as 'won' | 'lost' | 'returned' | 'unknown')}`} key={bar.category_id} />)}
  </FactsShell>
}
export function ArbitrationA2Facts({ view, context }: { view: PublicH2ArbitrationA2Dto | null; context: FactsContext }) { return <BarFacts view={view} context={context} id="arbitration-a2" blockId="arbitration_a2" title="Роли компании в делах" caption="Распределение дел по роли компании" /> }
export function ArbitrationA3Facts({ view, context }: { view: PublicH2ArbitrationA3Dto | null; context: FactsContext }) { return <BarFacts view={view} context={context} id="arbitration-a3" blockId="arbitration_a3" title="Исходы дел" caption="Распределение дел по подтверждённому исходу" /> }

export function ArbitrationA4Facts({ view, context }: { view: PublicH2ArbitrationA4Dto | null; context: FactsContext }) {
  if (view === null) return unavailable('arbitration-a4', 'arbitration_a4', 'Цена исков в рублях', context)
  const group = view.currency_groups[0]
  return <FactsShell id="arbitration-a4" blockId="arbitration_a4" title="Цена исков в рублях" context={context}>
    <SummaryScope summary={view.summary} />
    <p>Без цены иска: {arbitrationCount(view.missing_amount_count)}; без обозначения валюты: {arbitrationCount(view.missing_currency_count)}.</p>
    {group === undefined ? <p>Подтверждённые цены исков в рублях отсутствуют.</p> : <><p>{group.scope.label}.</p><div className="company-public-h2__arbitration-table"><table><caption>Цена иска в рублях по делам</caption><thead><tr><th scope="col">Дело</th><th scope="col">Год</th><th scope="col">Роль</th><th scope="col">Исход</th><th scope="col">Цена иска</th></tr></thead><tbody>{group.cases.map(item => <tr data-h2-case-public-id={item.case_public_id} key={item.case_public_id}><th scope="row">{arbitrationCaseLabel(item)}<br/><code>{item.case_public_id}</code></th><td>{arbitrationYear(item.year)}</td><td>{arbitrationRoleLabel(item.role)}</td><td>{arbitrationOutcomeLabel(item.outcome)}</td><td>{item.amount?.display_exact ?? '—'}</td></tr>)}</tbody></table></div></>}
  </FactsShell>
}

export function ArbitrationA5Facts({ view, context }: { view: PublicH2ArbitrationA5Dto | null; context: FactsContext }) {
  if (view === null) return unavailable('arbitration-a5', 'arbitration_a5', 'Противоположные стороны', context)
  return <FactsShell id="arbitration-a5" blockId="arbitration_a5" title="Противоположные стороны" context={context}>
    <SummaryScope summary={view.summary} />
    <p>{view.scope.label}. Одно дело может относиться к нескольким скрытым сторонам; сумма по группам поэтому может быть больше числа дел.</p>
    <p>Без безопасно выделенной противоположной стороны: {arbitrationCount(view.cases_without_safe_opponent)}; с несколькими сторонами: {arbitrationCount(view.multi_opponent_case_count)}.</p>
    <div className="company-public-h2__arbitration-table"><table><caption>Скрытые противоположные стороны по количеству дел</caption><thead><tr><th scope="col">Сторона</th><th scope="col">Количество дел</th><th scope="col">Детализация</th></tr></thead><tbody>{view.groups.map(group => <tr data-h2-opponent-public-id={group.opponent_public_id} key={group.opponent_public_id}><th scope="row">{group.display_name}<br/><code>{group.opponent_public_id}</code></th><td>{arbitrationCount(group.case_count)}</td><td>{group.case_scope.label}</td></tr>)}</tbody></table></div>
    {view.groups.map(group => <CaseList cases={group.cases} label={group.display_name} key={group.opponent_public_id} />)}
  </FactsShell>
}

function contextFor(dto: CompanyPublicH2, blockId: ArbitrationBlockId): FactsContext {
  const coverage = dto.coverage.find(item => item.block_id === blockId)
  if (coverage === undefined) throw new Error(`validated arbitration coverage missing: ${blockId}`)
  const limitations = coverage.limitation_codes.map(code => dto.limitations.find(item => item.code === code))
  if (limitations.some(item => item === undefined)) throw new Error(`validated arbitration limitation missing: ${blockId}`)
  return { coverage, limitations: limitations as readonly PublicH2LimitationDto[] }
}

export function ArbitrationFacts({ dto }: { dto: CompanyPublicH2 }) {
  if (classifyArbitrationPolicyV3(dto) === null) return null
  return <>
    <ArbitrationA1Facts view={dto.blocks.arbitration_a1} context={contextFor(dto, 'arbitration_a1')} />
    <ArbitrationA2Facts view={dto.blocks.arbitration_a2} context={contextFor(dto, 'arbitration_a2')} />
    <ArbitrationA3Facts view={dto.blocks.arbitration_a3} context={contextFor(dto, 'arbitration_a3')} />
    <ArbitrationA4Facts view={dto.blocks.arbitration_a4} context={contextFor(dto, 'arbitration_a4')} />
    <ArbitrationA5Facts view={dto.blocks.arbitration_a5} context={contextFor(dto, 'arbitration_a5')} />
  </>
}
