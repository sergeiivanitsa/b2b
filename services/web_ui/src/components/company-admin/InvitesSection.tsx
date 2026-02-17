import { useState } from 'react'
import type { FormEvent } from 'react'

import type {
  CompanyInvite,
  CreateCompanyInviteInput,
} from '../../companyAdmin/companyAdminApi'

type InvitesSectionProps = {
  invites: CompanyInvite[]
  isLoading: boolean
  errorMessage: string | null
  isCreating: boolean
  onRetry: () => void
  onCreateInvite: (payload: CreateCompanyInviteInput) => Promise<boolean>
}

function formatDate(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString('ru-RU')
}

function normalizeText(value: string): string {
  return value.trim()
}

function normalizeEmail(value: string): string {
  return value.trim().toLowerCase()
}

function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)
}

export function InvitesSection({
  invites,
  isLoading,
  errorMessage,
  isCreating,
  onRetry,
  onCreateInvite,
}: InvitesSectionProps) {
  const [email, setEmail] = useState('')
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    setFormError(null)

    const normalizedEmail = normalizeEmail(email)
    const normalizedFirstName = normalizeText(firstName)
    const normalizedLastName = normalizeText(lastName)

    if (!isValidEmail(normalizedEmail)) {
      setFormError('Введите корректный email.')
      return
    }

    const success = await onCreateInvite({
      email: normalizedEmail,
      first_name: normalizedFirstName || null,
      last_name: normalizedLastName || null,
    })
    if (!success) {
      return
    }

    setEmail('')
    setFirstName('')
    setLastName('')
  }

  return (
    <section className="company-admin-section">
      <div className="company-admin-section__header">
        <h2 className="company-admin-section__title">3. Инвайты</h2>
        <button
          type="button"
          className="button button--secondary"
          onClick={onRetry}
          disabled={isLoading}
        >
          {isLoading ? 'Обновляем...' : 'Обновить'}
        </button>
      </div>

      <form className="form company-admin-inline-form" onSubmit={handleSubmit}>
        <div>
          <label className="label" htmlFor="invite-last-name">
            Фамилия
          </label>
          <input
            id="invite-last-name"
            className="input"
            type="text"
            value={lastName}
            onChange={(event) => setLastName(event.target.value)}
            placeholder="Иванов"
            autoComplete="off"
            disabled={isCreating}
          />
        </div>

        <div>
          <label className="label" htmlFor="invite-first-name">
            Имя
          </label>
          <input
            id="invite-first-name"
            className="input"
            type="text"
            value={firstName}
            onChange={(event) => setFirstName(event.target.value)}
            placeholder="Иван"
            autoComplete="off"
            disabled={isCreating}
          />
        </div>

        <div>
          <label className="label" htmlFor="invite-email">
            Email
          </label>
          <input
            id="invite-email"
            className="input"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="employee@company.ru"
            autoComplete="off"
            disabled={isCreating}
          />
        </div>

        <div className="company-admin-inline-form__actions">
          <button className="button button--secondary" type="submit" disabled={isCreating}>
            {isCreating ? 'Отправляем...' : 'Добавить сотрудника'}
          </button>
        </div>
      </form>

      {formError ? <p className="message message--error">{formError}</p> : null}
      {errorMessage ? <p className="message message--error">{errorMessage}</p> : null}

      {isLoading && invites.length === 0 ? (
        <p className="card__subtitle">Загружаем приглашения...</p>
      ) : null}
      {!isLoading && invites.length === 0 ? (
        <p className="card__subtitle">Нет активных приглашений.</p>
      ) : null}

      {invites.length > 0 ? (
        <div className="company-admin-table-wrap">
          <table className="company-admin-table">
            <thead>
              <tr>
                <th>Фамилия</th>
                <th>Имя</th>
                <th>Email</th>
                <th>Роль</th>
                <th>Создано</th>
                <th>Истекает</th>
              </tr>
            </thead>
            <tbody>
              {invites.map((invite) => (
                <tr key={invite.id}>
                  <td>{invite.last_name ?? '-'}</td>
                  <td>{invite.first_name ?? '-'}</td>
                  <td>{invite.email}</td>
                  <td>{invite.role}</td>
                  <td>{formatDate(invite.created_at)}</td>
                  <td>{formatDate(invite.expires_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}
