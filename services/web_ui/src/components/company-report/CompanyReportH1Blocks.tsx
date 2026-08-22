import { Link } from 'react-router-dom'

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
import type {
  CompanyPublicH1Response,
  FactualBlockId,
  LimitationCode,
  PublicBlockId,
} from '../../companyReport/companyReportTypes'

function describedBy(codes: readonly LimitationCode[]): string | undefined {
  return codes.length > 0 ? codes.map(limitationDomId).join(' ') : undefined
}

function limitationsForBlock(
  dto: CompanyPublicH1Response,
  blockId: FactualBlockId,
): readonly LimitationCode[] {
  return dto.limitations
    .filter((limitation) => limitation.block_id === blockId)
    .map((limitation) => limitation.code)
}

export function CompanyReportH1Block({
  id,
  dto,
}: {
  id: PublicBlockId
  dto: CompanyPublicH1Response
}) {
  switch (id) {
    case 'breadcrumbs':
      return <Breadcrumbs dto={dto} />
    case 'identity_status':
      return <IdentityHero dto={dto} />
    case 'known_summary':
      return <KnownSummary dto={dto} />
    case 'in_page_navigation':
      return <InPageNavigation dto={dto} />
    case 'coverage_checked_at':
      return <Coverage dto={dto} />
    case 'requisites':
      return <Requisites dto={dto} />
    case 'finance':
      return dto.blocks.finance ? <Finance dto={dto} /> : null
    case 'arbitration':
      return dto.blocks.arbitration ? <Arbitration dto={dto} /> : null
    case 'sources_limitations':
      return <SourcesAndLimitations dto={dto} />
    case 'neutral_actions':
      return <NeutralActions dto={dto} />
    default:
      return null
  }
}

function Breadcrumbs({ dto }: { dto: CompanyPublicH1Response }) {
  return (
    <nav aria-label="Хлебные крошки" className="company-report-breadcrumbs">
      <ol>
        {dto.breadcrumbs.map((item, index) => (
          <li key={`${item.path}-${index}`}>
            {index === dto.breadcrumbs.length - 1 ? (
              <span aria-current="page">{item.label}</span>
            ) : (
              <Link to={item.path}>{item.label}</Link>
            )}
          </li>
        ))}
      </ol>
    </nav>
  )
}

function IdentityHero({ dto }: { dto: CompanyPublicH1Response }) {
  return (
    <header className="company-report-hero">
      <h1 tabIndex={-1} data-company-report-focus-heading>
        {dto.identity.legal_full_name} — ИНН {dto.identity.inn}
      </h1>
      {dto.identity.legal_short_name &&
      dto.identity.legal_short_name !== dto.identity.legal_full_name ? (
        <p>{dto.identity.legal_short_name}</p>
      ) : null}
      <p>
        По данным отчёта, сформированного{' '}
        <time dateTime={dto.checked_at}>{dto.checked_date_display}</time>.
      </p>
    </header>
  )
}

function factualBlocks(dto: CompanyPublicH1Response): readonly FactualBlockId[] {
  return [
    'requisites',
    ...(dto.blocks.finance ? (['finance'] as const) : []),
    ...(dto.blocks.arbitration ? (['arbitration'] as const) : []),
  ]
}

function KnownSummary({ dto }: { dto: CompanyPublicH1Response }) {
  return (
    <section className="company-report-section" aria-labelledby="company-known">
      <h2 id="company-known">Что известно</h2>
      <ul>
        {factualBlocks(dto).map((blockId) => (
          <li key={blockId}>{BLOCK_LABELS[blockId]}</li>
        ))}
      </ul>
    </section>
  )
}

function InPageNavigation({ dto }: { dto: CompanyPublicH1Response }) {
  return (
    <nav className="company-report-section" aria-label="Разделы отчёта">
      <h2>Разделы отчёта</h2>
      <ul>
        {factualBlocks(dto).map((blockId) => (
          <li key={blockId}>
            <a href={`#${blockId}`}>{BLOCK_LABELS[blockId]}</a>
          </li>
        ))}
      </ul>
    </nav>
  )
}

function Coverage({ dto }: { dto: CompanyPublicH1Response }) {
  return (
    <section
      className="company-report-section"
      aria-labelledby="company-coverage"
    >
      <h2 id="company-coverage">Покрытие и дата проверки</h2>
      <p>
        Дата относится к сохранённому отчёту и не является датой просмотра
        страницы.
      </p>
      <ul className="company-report-coverage">
        {dto.coverage.map((item) => (
          <li
            key={item.block_id}
            aria-describedby={describedBy(item.limitation_codes)}
          >
            <strong>{BLOCK_LABELS[item.block_id]}</strong>
            <span>{DATASET_LABELS[item.dataset]}</span>
            <span>{COVERAGE_LABELS[item.state]}</span>
            {item.total !== null ? <span>Всего: {item.total}</span> : null}
            {item.returned !== null ? (
              <span>Получено: {item.returned}</span>
            ) : null}
            {item.limit !== null ? <span>Лимит: {item.limit}</span> : null}
            {item.offset !== null ? <span>Смещение: {item.offset}</span> : null}
          </li>
        ))}
      </ul>
    </section>
  )
}

function Requisites({ dto }: { dto: CompanyPublicH1Response }) {
  const requisites = dto.blocks.requisites
  const sectionLimitations = limitationsForBlock(dto, 'requisites')
  const addressLimitations = dto.limitations
    .filter(
      (limitation) => limitation.field_id === 'requisites.legal_address',
    )
    .map((limitation) => limitation.code)
  const rows: Array<{
    label: string
    value: string | null
    describedBy?: string
  }> = [
    { label: 'ОГРН/ОГРНИП', value: requisites.ogrn_or_ogrnip },
    { label: 'КПП', value: requisites.kpp },
    {
      label: 'Дата регистрации',
      value: requisites.registration_date
        ? displayIsoDate(requisites.registration_date)
        : null,
    },
    {
      label: 'Дата прекращения деятельности',
      value: requisites.dissolved_date
        ? displayIsoDate(requisites.dissolved_date)
        : null,
    },
    { label: 'Регион', value: requisites.region?.name ?? null },
    { label: 'Код региона', value: requisites.region?.code ?? null },
    {
      label: 'Юридический адрес',
      value: requisites.legal_address?.display_line ?? null,
      describedBy: describedBy(addressLimitations),
    },
    {
      label: 'Адрес помечен источником как недостоверный',
      value:
        requisites.legal_address?.is_inaccuracy === null ||
        requisites.legal_address?.is_inaccuracy === undefined
          ? null
          : requisites.legal_address.is_inaccuracy
            ? 'Да'
            : 'Нет',
      describedBy: describedBy(addressLimitations),
    },
  ]
  const visibleRows = rows.filter((row) => row.value !== null)

  return (
    <section
      id="requisites"
      className="company-report-section"
      aria-labelledby="company-requisites"
      aria-describedby={describedBy(sectionLimitations)}
    >
      <h2 id="company-requisites">Реквизиты</h2>
      {visibleRows.length > 0 ? (
        <dl className="company-report-definition-grid">
          {visibleRows.map((row) => (
            <div key={row.label} aria-describedby={row.describedBy}>
              <dt>{row.label}</dt>
              <dd>{row.value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p>Подтверждённые реквизиты не представлены.</p>
      )}
    </section>
  )
}

function Finance({ dto }: { dto: CompanyPublicH1Response }) {
  const finance = dto.blocks.finance
  if (!finance) return null
  return (
    <section
      id="finance"
      className="company-report-section"
      aria-labelledby="company-finance"
      aria-describedby={describedBy(limitationsForBlock(dto, 'finance'))}
    >
      <h2 id="company-finance">Финансовые показатели</h2>
      <ul className="company-report-facts">
        {finance.metrics.map((metric) => (
          <li key={`${metric.metric_id}-${metric.year}`}>
            <strong>{FINANCE_LABELS[metric.metric_id]}</strong>: {' '}
            {metric.yoy.current_year} к {metric.yoy.previous_year} —{' '}
            {metric.yoy.display_value}
          </li>
        ))}
      </ul>
    </section>
  )
}

function Arbitration({ dto }: { dto: CompanyPublicH1Response }) {
  const arbitration = dto.blocks.arbitration
  if (!arbitration) return null
  const counts: Array<[string, number]> = [
    ['Всего дел в источнике', arbitration.total_cases],
    ['Получено в сохранённом ответе', arbitration.returned_cases],
    ['Нормализовано', arbitration.normalized_case_count],
    ['Некорректных записей', arbitration.malformed_count],
    ['Лимит сохранённой выборки', arbitration.limit],
    ['Смещение сохранённой выборки', arbitration.offset],
  ]
  return (
    <section
      id="arbitration"
      className="company-report-section"
      aria-labelledby="company-arbitration"
      aria-describedby={describedBy(limitationsForBlock(dto, 'arbitration'))}
    >
      <h2 id="company-arbitration">Арбитраж</h2>
      <dl className="company-report-definition-grid">
        {counts.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <Distribution
        title="Роли нормализованных карточек"
        values={arbitration.role_counts}
        labels={ROLE_LABELS}
        extra={['Не отнесено', arbitration.unattributed_count]}
      />
      <Distribution
        title="Статусы нормализованных карточек"
        values={arbitration.status_counts}
        labels={STATUS_LABELS}
      />
      <Distribution
        title="Результаты нормализованных карточек"
        values={arbitration.result_counts}
        labels={RESULT_LABELS}
      />
      {arbitration.claim_amounts.length > 0 ? (
        <>
          <h3>Суммы требований по отнесённой роли</h3>
          <ul>
            {arbitration.claim_amounts.map((amount, index) => (
              <li key={`${amount.role}-${amount.currency}-${index}`}>
                {ROLE_LABELS[amount.role]}: {amount.display_value}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {arbitration.selected_cases.length > 0 ? (
        <>
          <h3 id="company-arbitration-cases">Выбранные арбитражные дела</h3>
          <div
            className="company-report-dense"
            role="region"
            tabIndex={0}
            aria-labelledby="company-arbitration-cases"
          >
            <div className="company-report-cases">
              {arbitration.selected_cases.map((caseItem, index) => (
                <article key={`${index}:${caseItem.case_number}`}>
                  <h4>{caseItem.case_number}</h4>
                  <p>Роль: {ROLE_LABELS[caseItem.attributed_role]}</p>
                  {caseItem.date_start ? (
                    <p>Дата начала: {displayIsoDate(caseItem.date_start)}</p>
                  ) : null}
                  {caseItem.date_update ? (
                    <p>Дата обновления: {displayIsoDate(caseItem.date_update)}</p>
                  ) : null}
                  {caseItem.claim_amount ? (
                    <p>Сумма требования: {caseItem.claim_amount.display_value}</p>
                  ) : null}
                </article>
              ))}
            </div>
          </div>
        </>
      ) : null}
    </section>
  )
}

function Distribution<T extends string>({
  title,
  values,
  labels,
  extra,
}: {
  title: string
  values: Readonly<Record<T, number>>
  labels: Readonly<Record<T, string>>
  extra?: readonly [string, number]
}) {
  return (
    <>
      <h3>{title}</h3>
      <ul className="company-report-distribution">
        {(Object.keys(values) as T[]).map((key) => (
          <li key={key}>
            <span>{labels[key]}</span>
            <strong>{values[key]}</strong>
          </li>
        ))}
        {extra ? (
          <li>
            <span>{extra[0]}</span>
            <strong>{extra[1]}</strong>
          </li>
        ) : null}
      </ul>
    </>
  )
}

function SourcesAndLimitations({ dto }: { dto: CompanyPublicH1Response }) {
  return (
    <section
      className="company-report-section"
      aria-labelledby="company-sources-limitations"
    >
      <h2 id="company-sources-limitations">Источники и ограничения</h2>
      <h3>Источники сохранённого отчёта</h3>
      <ul className="company-report-sources">
        {dto.sources.map((source) => (
          <li key={source.dataset}>
            <strong>{DATASET_LABELS[source.dataset]}</strong>
            <span>
              Получено: <time dateTime={source.received_at}>{source.received_at}</time>
            </span>
            {source.effective_at ? (
              <span>Дата сведений: {source.effective_at}</span>
            ) : null}
            {source.period ? <span>Период: {source.period}</span> : null}
            <span>Нормализация: {source.normalization_version}</span>
          </li>
        ))}
      </ul>
      <h3>Ограничения</h3>
      <ul className="company-report-limitations">
        {dto.limitations.map((limitation) => (
          <li id={limitationDomId(limitation.code)} key={limitation.code}>
            {limitation.message}
          </li>
        ))}
      </ul>
    </section>
  )
}

function NeutralActions({ dto }: { dto: CompanyPublicH1Response }) {
  return (
    <nav className="company-report-actions" aria-label="Действия с отчётом">
      <h2>Действия</h2>
      {dto.actions.map((action) => (
        <Link key={action.action_id} to={action.path}>
          {action.label}
        </Link>
      ))}
    </nav>
  )
}
