import { useState } from 'react'
import type { FormEvent } from 'react'

type Props = {
  id: string
  value: string
  compact?: boolean
  variant?: 'default' | 'card'
  placeholder?: string
  submitLabel?: string
  disabled?: boolean
  onChange: (value: string) => void
  onSubmit: (inn: string) => void
}

export function CompanyReportInnForm({
  id,
  value,
  compact = false,
  variant = 'default',
  placeholder,
  submitLabel = 'Проверить',
  disabled = false,
  onChange,
  onSubmit,
}: Props) {
  const [error, setError] = useState<string | null>(null)
  const normalized = value.replace(/\s+/g, '')

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!/^(?:[0-9]{10}|[0-9]{12})$/.test(normalized)) {
      setError('Введите ИНН из 10 или 12 цифр.')
      return
    }
    setError(null)
    onSubmit(normalized)
  }

  return (
    <form className={`company-entry-form${compact ? ' company-entry-form--compact' : ''}${variant === 'card' ? ' company-entry-form--card' : ''}`} onSubmit={submit} noValidate>
      <label htmlFor={id}>ИНН компании</label>
      <div className="company-entry-form__controls">
        <input
          id={id}
          type="text"
          inputMode="numeric"
          autoComplete="off"
          placeholder={placeholder}
          value={value}
          onChange={(event) => onChange(event.target.value.replace(/\s+/g, ''))}
          aria-describedby={`${id}-hint ${id}-status`}
          disabled={disabled}
        />
        <button type="submit" disabled={disabled}>{disabled ? 'Открываем…' : submitLabel}</button>
      </div>
      <p id={`${id}-hint`} className="company-entry-form__hint">10 или 12 цифр</p>
      <p id={`${id}-status`} className="company-entry-form__status" aria-live="polite">{error}</p>
    </form>
  )
}
