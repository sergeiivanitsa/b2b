import type { CompanySummary } from '../../companyAdmin/companyAdminApi'

type CompanySummarySectionProps = {
  summary: CompanySummary | null
  isLoading: boolean
  errorMessage: string | null
  onRetry: () => void
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat('ru-RU').format(value)
}

export function CompanySummarySection({
  summary,
  isLoading,
  errorMessage,
  onRetry,
}: CompanySummarySectionProps) {
  return (
    <section className="company-admin-section">
      <div className="company-admin-section__header">
        <h2 className="company-admin-section__title">1. Обзор компании и баланс</h2>
        <button
          type="button"
          className="button button--secondary"
          onClick={onRetry}
          disabled={isLoading}
        >
          {isLoading ? 'Обновляем...' : 'Обновить'}
        </button>
      </div>

      {isLoading && !summary ? (
        <p className="card__subtitle">Загружаем обзор компании...</p>
      ) : null}

      {errorMessage ? <p className="message message--error">{errorMessage}</p> : null}

      {summary ? (
        <>
          <div className="company-admin-grid">
            <article className="company-admin-box">
              <h3 className="company-admin-box__title">Компания</h3>
              <dl className="kv">
                <dt>ID</dt>
                <dd>{summary.company.id}</dd>
                <dt>Название</dt>
                <dd>{summary.company.name}</dd>
                <dt>ИНН</dt>
                <dd>{summary.company.inn ?? '-'}</dd>
                <dt>Телефон</dt>
                <dd>{summary.company.phone ?? '-'}</dd>
                <dt>Статус</dt>
                <dd>{summary.company.status}</dd>
              </dl>
            </article>

            <article className="company-admin-box">
              <h3 className="company-admin-box__title">Кредиты компании</h3>
              <dl className="kv">
                <dt>Общий баланс (pool)</dt>
                <dd>{formatNumber(summary.credits.pool_balance)}</dd>
                <dt>Выделено сотрудникам</dt>
                <dd>{formatNumber(summary.credits.allocated_total)}</dd>
                <dt>Нераспределённый остаток</dt>
                <dd>{formatNumber(summary.credits.unallocated_balance)}</dd>
              </dl>
            </article>

            <article className="company-admin-box">
              <h3 className="company-admin-box__title">Сотрудники</h3>
              <dl className="kv">
                <dt>Всего</dt>
                <dd>{formatNumber(summary.users.total)}</dd>
                <dt>Активных</dt>
                <dd>{formatNumber(summary.users.active)}</dd>
              </dl>
            </article>
          </div>
        </>
      ) : null}
    </section>
  )
}
