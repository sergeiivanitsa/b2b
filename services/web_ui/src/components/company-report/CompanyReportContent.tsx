import { useEffect, useRef } from 'react'

import type { CompanyPublicH1Response } from '../../companyReport/companyReportTypes'
import { CompanyReportH1Block } from './CompanyReportH1Blocks'

export type CompanyReportView =
  | { kind: 'loading_h1' }
  | { kind: 'pending'; title: string; cycle: number }
  | { kind: 'content'; dto: CompanyPublicH1Response }
  | { kind: 'terminal_error'; message: string }
  | { kind: 'retryable_error'; message: string }
  | { kind: 'contract_error' }
  | { kind: 'invalid_route' }

type CompanyReportContentProps = {
  view: CompanyReportView
  onRetry?: () => void
}

function liveAnnouncement(view: CompanyReportView): string {
  switch (view.kind) {
    case 'loading_h1':
      return 'Загружаем сведения о компании.'
    case 'pending':
      return 'Отчёт формируется.'
    case 'content':
      return 'Сведения о компании загружены.'
    case 'contract_error':
      return 'Формат отчёта не поддерживается.'
    case 'invalid_route':
      return 'Адрес страницы компании некорректен.'
    case 'terminal_error':
    case 'retryable_error':
      return view.message
  }
}

export function CompanyReportContent({
  view,
  onRetry,
}: CompanyReportContentProps) {
  const mainRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (view.kind === 'loading_h1') return
    mainRef.current
      ?.querySelector<HTMLElement>('[data-company-report-focus-heading]')
      ?.focus()
  }, [view.kind])

  const busy = view.kind === 'loading_h1' || view.kind === 'pending'
  const contentAttributes =
    view.kind === 'content'
      ? {
          'data-company-contract': view.dto.contract_version,
          'data-company-report-id': view.dto.report_id,
          'data-company-report-version': view.dto.report_version,
          'data-company-projection-scope': view.dto.projection_scope,
          'data-company-canonical-path': view.dto.canonical_path,
          'data-company-indexable': String(view.dto.indexable),
          'data-company-block-order': view.dto.block_order.join(','),
        }
      : {}

  return (
    <main
      ref={mainRef}
      className="company-report-page"
      aria-busy={busy || undefined}
      {...contentAttributes}
    >
      <p
        className="company-report-live"
        aria-live="polite"
        aria-atomic="true"
      >
        {liveAnnouncement(view)}
      </p>
      {view.kind === 'content' ? (
        view.dto.block_order.map((id) => (
          <CompanyReportH1Block key={id} id={id} dto={view.dto} />
        ))
      ) : (
        <CompanyReportState view={view} onRetry={onRetry} />
      )}
    </main>
  )
}

function CompanyReportState({
  view,
  onRetry,
}: {
  view: Exclude<CompanyReportView, { kind: 'content' }>
  onRetry?: () => void
}) {
  const state =
    view.kind === 'loading_h1'
      ? [
          'Загружаем сведения о компании',
          'Получаем доступную информацию о компании.',
        ]
      : view.kind === 'pending'
        ? [view.title, 'Отчёт формируется. Это может занять несколько минут.']
        : view.kind === 'contract_error'
          ? ['Неподдерживаемый формат отчёта', 'Сведения временно недоступны.']
          : view.kind === 'invalid_route'
            ? [
                'Некорректный адрес страницы компании.',
                'Проверьте адрес и повторите попытку.',
              ]
            : [view.message, '']

  return (
    <section className="company-report-state">
      <h1 tabIndex={-1} data-company-report-focus-heading>
        {state[0]}
      </h1>
      {state[1] ? <p>{state[1]}</p> : null}
      {view.kind === 'retryable_error' && onRetry ? (
        <button type="button" onClick={onRetry}>
          Повторить
        </button>
      ) : null}
    </section>
  )
}
