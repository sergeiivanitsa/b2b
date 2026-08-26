import { Fragment } from 'react'
import type { MouseEvent } from 'react'
import type { CompanyPublicH2, PublicH2BlocksDto, PublicH2CoverageItemDto, PublicH2ViewDto } from './contractSchema'
import { text } from './presentation'
import { FinanceFacts } from './FinanceFacts'
import './CompanyPublicH2Page.css'

function CoverageRow({ item }: { item: PublicH2CoverageItemDto }) {
  const blockId = item.block_id
  const counts = (['total', 'returned', 'eligible'] as const)
    .filter(name => item[name] !== null)
    .map(name => <span data-h2-coverage={`${blockId}.${name}`} key={name}>{name}: {text(item[name])}</span>)
  return <li data-h2-coverage={blockId}><strong>{blockId}</strong>: {item.state}; охват: {item.population_scope}{counts.length > 0 && <>; {counts}</>}{item.limitation_codes.length > 0 && <>; {item.limitation_codes.map(code => <a href={`#limitation-${code}`} key={code}>Ограничение: {code}</a>)}</>}</li>
}

function BlockSurface({ blocks, prefix }: { blocks: PublicH2BlocksDto; prefix: 'finance' | 'arbitration' }) {
  const items: readonly (readonly [string, PublicH2ViewDto | null])[] = prefix === 'finance'
    ? [['finance_f1', blocks.finance_f1], ['finance_f2', blocks.finance_f2], ['finance_f3', blocks.finance_f3], ['finance_f4', blocks.finance_f4], ['finance_f5', blocks.finance_f5]]
    : [['arbitration_a1', blocks.arbitration_a1], ['arbitration_a2', blocks.arbitration_a2], ['arbitration_a3', blocks.arbitration_a3], ['arbitration_a4', blocks.arbitration_a4], ['arbitration_a5', blocks.arbitration_a5]]
  return <ul>{items.map(([blockId, value]) => {
    const viewId = value?.view_id ?? ''
    return <li data-h2-block={blockId} key={blockId}><strong>{blockId.replaceAll('_', ' ').toUpperCase()}</strong>{viewId ? `: подтверждённые данные ${viewId}` : ': данные не опубликованы'}</li>
  })}</ul>
}

function coverageById(coverage: readonly PublicH2CoverageItemDto[], id: string): PublicH2CoverageItemDto {
  const item = coverage.find(candidate => candidate.block_id === id)
  if (!item) throw new Error(`validated coverage item missing: ${id}`)
  return item
}

function activateInPageTarget(event: MouseEvent<HTMLAnchorElement>, targetId: string, label: string) {
  event.preventDefault()
  const documentRef = event.currentTarget.ownerDocument
  const target = documentRef.getElementById(targetId)
  if (!target) return
  target.setAttribute('tabindex', '-1')
  documentRef.defaultView?.history.pushState(null, '', `#${targetId}`)
  target.focus({ preventScroll: true })
  target.scrollIntoView?.({ block: 'start' })
  const live = documentRef.querySelector<HTMLElement>('.company-public-h2__live')
  if (live) live.textContent = `Раздел «${label}» открыт.`
}

export function CompanyPublicH2Page({ dto }: { dto: CompanyPublicH2 }) {
  const { identity, narrative, blocks, coverage, sources, limitations, primary_claim_cta: cta } = dto
  const { requisites } = blocks
  const { additional_activities: activities, tax_modes: taxModes, managers, owners, employees, tax_authority: taxAuthority, charter_capital: capital, address } = requisites
  const [checkAnotherAction, prepareClaimAction] = dto.actions
  const [homeBreadcrumb, currentBreadcrumb] = dto.breadcrumbs
  const optionalIdentity: readonly [string, string][] = [
    ['Краткое наименование', identity.short_name ?? ''], ['ОГРН', identity.ogrn ?? ''],
    ['КПП', identity.kpp ?? ''], ['Дата регистрации', identity.registration_date ?? ''],
    ['Дата прекращения деятельности', identity.dissolution_date ?? ''],
  ]

  return <>
    <nav aria-label="Хлебные крошки"><ol><li><a href={homeBreadcrumb.path}>{homeBreadcrumb.label}</a></li><li aria-current="page">{currentBreadcrumb.label}</li></ol></nav>
    <header id="hero-status"><p>Статус отчёта: {identity.status?.label || 'Статус не указан в отчёте'}</p>{identity.status?.effective_date && <p>Дата статуса: <time>{identity.status.effective_date}</time></p>}<h1 data-h2-field="identity.display_name">{identity.display_name}</h1><p>Дата составления отчёта: <time dateTime={dto.checked_at}>{dto.checked_date_display}</time></p><p>Идентификатор отчёта: <code data-h2-field="report_id">{dto.report_id}</code></p></header>
    <section id="narrative" aria-labelledby="narrative-title"><h2 id="narrative-title">{narrative.mode === 'artifact' ? 'Описание деятельности' : 'Описание деятельности — подтверждённый шаблон'}</h2><p data-h2-field="narrative.description">{narrative.description}</p><h3>Покрытие описания</h3><ul><CoverageRow item={coverageById(coverage, 'narrative')} /></ul></section>
    <nav id="in-page-navigation" aria-label="Разделы отчёта"><ol><li><a href="#requisites" onClick={event => activateInPageTarget(event, 'requisites', 'Реквизиты')}>Реквизиты</a></li><li><a href="#finance" onClick={event => activateInPageTarget(event, 'finance', 'Финансы')}>Финансы</a></li><li><a href="#arbitration" onClick={event => activateInPageTarget(event, 'arbitration', 'Арбитраж')}>Арбитраж</a></li></ol></nav>
    <section id="requisites"><h2>Реквизиты</h2><dl><dt>Полное наименование</dt><dd>{identity.legal_full_name}</dd><dt>ИНН</dt><dd data-h2-field="identity.inn">{identity.inn}</dd>{optionalIdentity.map(([label, value]) => value && <Fragment key={label}><dt>{label}</dt><dd>{value}</dd></Fragment>)}{address?.display && <><dt>Адрес</dt><dd>{address.display}</dd></>}{requisites.legal_form?.label && <><dt>Организационно-правовая форма</dt><dd>{requisites.legal_form.label}</dd></>}{requisites.primary_activity?.label && <><dt>Основной вид деятельности</dt><dd>{requisites.primary_activity.label}</dd></>}{capital?.display_exact && <><dt>Уставный капитал</dt><dd>{capital.display_exact}</dd></>}</dl>{taxModes.length > 0 && <><h3>Налоговые режимы</h3><ul>{taxModes.map(item => <li key={item.mode_id}>{item.label}</li>)}</ul></>}{activities.length > 0 && <><h3>Дополнительные виды деятельности</h3><ul>{activities.map(item => <li key={item.code}>{item.label}</li>)}</ul></>}{managers.length > 0 && <><h3>Руководители</h3><ul>{managers.map(item => <li key={item.name}>{item.name} — {item.role}</li>)}</ul></>}{owners.length > 0 && <><h3>Владельцы</h3><ul>{owners.map(item => <li key={item.display_name}>{item.display_name}</li>)}</ul></>}{employees && <p>Численность: {text(employees.count)} ({employees.period})</p>}{taxAuthority?.label && <p>Налоговый орган: {taxAuthority.label}</p>}<h3>Покрытие реквизитов</h3><ul><CoverageRow item={coverageById(coverage, 'requisites')} /></ul></section>
    <section id="finance"><h2>Финансы</h2><h3>Покрытие</h3><ul>{['finance_f1', 'finance_f2', 'finance_f3', 'finance_f4', 'finance_f5'].map(id => <CoverageRow item={coverageById(coverage, id)} key={id} />)}</ul><FinanceFacts dto={dto} /></section>
    <section id="arbitration"><h2>Арбитраж</h2><h3>Покрытие</h3><ul>{['arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4', 'arbitration_a5'].map(id => <CoverageRow item={coverageById(coverage, id)} key={id} />)}</ul><BlockSurface blocks={blocks} prefix="arbitration" /></section>
    <section id="sources-limitations"><h2>Источники и ограничения</h2><h3>Покрытие раздела</h3><ul><CoverageRow item={coverageById(coverage, 'sources_limitations')} /></ul><h3>Источники</h3><ul>{sources.map(source => <li data-h2-field={`sources.${source.dataset}`} key={source.dataset}>{source.dataset} — {source.received_at}{source.effective_at && `; дата актуальности: ${source.effective_at}`}{source.period && `; период: ${source.period}`}</li>)}</ul><h3>Ограничения</h3><ul>{limitations.map(item => <li data-h2-limitation={item.code} data-h2-limitation-block={item.block_id ?? ''} data-h2-limitation-field={item.field_id ?? ''} id={`limitation-${item.code}`} key={item.code}>{item.message}</li>)}</ul></section>
    <section id="neutral-actions"><h2>Действия</h2><a className="company-public-h2__button company-public-h2__button--accent" href={checkAnotherAction.path}>{checkAnotherAction.label}</a><a className="company-public-h2__button company-public-h2__button--accent" href={prepareClaimAction.path}>{prepareClaimAction.label}</a></section>
    <aside className="company-public-h2__cta" aria-label="Подготовка претензии"><h2>{cta.heading}</h2><p className="company-public-h2__cta-copy">{cta.desktop_copy}</p><a className="company-public-h2__button company-public-h2__button--accent" href={cta.path} onClick={() => { const live = document.querySelector<HTMLElement>('.company-public-h2__live'); if (live) live.textContent = 'Переход к подготовке претензии.' }}>{cta.button_label}</a></aside>
    <div className="company-public-h2__cta-reserver" inert aria-hidden="true"/><p className="company-public-h2__live" role="status" aria-live="polite"/>
  </>
}
