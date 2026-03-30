import { useEffect, useMemo, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { restoreClaimFromSession } from '../claims/claimRestore'
import { ClaimsBrand } from '../claims/components/ClaimsBrand'
import { ClaimsProgressBar } from '../claims/components/ClaimsProgressBar'
import {
  getApiHttpErrorDetail,
  listClaimFiles,
  patchClaim,
  type ClaimCaseType,
  type ClaimFileSnapshot,
  type ClaimNormalizedData,
  uploadClaimFile,
} from '../claims/claimsApi'

type TriState = 'yes' | 'no' | 'unknown'

type PartialPaymentFormRow = {
  id: number
  amount: string
  date: string
}

type Step2FormState = {
  creditorName: string
  debtorName: string
  caseType: ClaimCaseType | ''
  contractSigned: TriState
  contractNumber: string
  contractDate: string
  debtAmount: string
  paymentDueDate: string
  partialPaymentsPresent: TriState
  partialPayments: PartialPaymentFormRow[]
  penaltyExists: TriState
  penaltyRateText: string
  documentsMentioned: string[]
}

type Step2LocationState = {
  notice?: string
  missingFields?: string[]
}

const CASE_TYPE_OPTIONS: Array<{ value: ClaimCaseType; label: string }> = [
  { value: 'supply', label: 'Договор поставки товара' },
  { value: 'services', label: 'Договор оказания услуг' },
  { value: 'contract_work', label: 'Договор подряда' },
]

const DOCUMENT_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'contract', label: 'Договор' },
  { value: 'waybill', label: 'Накладные / УПД' },
  { value: 'services_act', label: 'Акты услуг' },
  { value: 'acceptance_act', label: 'Акты выполненных работ' },
  { value: 'invoice', label: 'Счета' },
  { value: 'payment_order', label: 'Платёжные поручения' },
  { value: 'specification', label: 'Спецификация' },
]

const FILE_ROLE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'contract', label: 'Договор' },
  { value: 'waybill', label: 'Накладные / УПД' },
  { value: 'act', label: 'Акты' },
  { value: 'invoice', label: 'Счета' },
  { value: 'correspondence', label: 'Переписка' },
  { value: 'other', label: 'Иное' },
]

let nextPaymentRowId = 1

export function ClaimStep2Page() {
  const navigate = useNavigate()
  const location = useLocation()
  const locationState = (location.state || {}) as Step2LocationState

  const [claimId, setClaimId] = useState<number | null>(null)
  const [editToken, setEditToken] = useState<string>('')
  const [formState, setFormState] = useState<Step2FormState>(() => buildInitialFormState(null))
  const [missingFields, setMissingFields] = useState<string[]>(locationState.missingFields ?? [])
  const [files, setFiles] = useState<ClaimFileSnapshot[]>([])
  const [fileRole, setFileRole] = useState('contract')
  const [fileToUpload, setFileToUpload] = useState<File | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [notice, setNotice] = useState<string | null>(locationState.notice ?? null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isCanceled = false

    async function loadClaim() {
      try {
        setIsLoading(true)
        setError(null)
        const restored = await restoreClaimFromSession()
        const loadedFiles = await listClaimFiles(restored.claimId, restored.editToken)
        if (isCanceled) {
          return
        }

        setClaimId(restored.claimId)
        setEditToken(restored.editToken)
        setMissingFields(restored.claim.step2.missing_fields)
        setFormState(buildInitialFormState(restored.claim.normalized_data, restored.claim.case_type))
        setFiles(loadedFiles)
      } catch (loadError) {
        if (isCanceled) {
          return
        }
        if (loadError instanceof Error && (loadError.message === 'missing_session' || loadError.message === 'invalid_session')) {
          navigate('/claims', { replace: true })
          return
        }
        setError('Не удалось загрузить черновик заявки. Обновите страницу.')
      } finally {
        if (!isCanceled) {
          setIsLoading(false)
        }
      }
    }

    void loadClaim()
    return () => {
      isCanceled = true
    }
  }, [navigate])

  const derived = useMemo(() => computeDerivedValues(formState), [formState])
  const completionPercent = useMemo(
    () => computeCompletionPercent(missingFields.length),
    [missingFields.length],
  )
  const missingFieldSet = useMemo(() => new Set(missingFields), [missingFields])

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!claimId || !editToken) {
      setError('Сессия не найдена. Начните заново с шага 1.')
      return
    }

    setIsSaving(true)
    setError(null)
    setNotice(null)

    try {
      const snapshot = await patchClaim(claimId, editToken, buildPatchPayload(formState))
      setMissingFields(snapshot.step2.missing_fields)
      navigate('/claims/step-3')
    } catch (saveError) {
      const detail = getApiHttpErrorDetail(saveError)
      setError(detail ?? 'Не удалось сохранить данные шага 2.')
    } finally {
      setIsSaving(false)
    }
  }

  async function onUploadFile() {
    if (!claimId || !editToken) {
      setError('Сессия не найдена. Начните заново с шага 1.')
      return
    }
    if (!fileToUpload) {
      setError('Выберите файл для загрузки.')
      return
    }

    setIsUploading(true)
    setError(null)
    try {
      await uploadClaimFile(claimId, editToken, fileToUpload, fileRole)
      const nextFiles = await listClaimFiles(claimId, editToken)
      setFiles(nextFiles)
      setFileToUpload(null)
      setNotice('Файл успешно добавлен к заявке.')
    } catch (uploadError) {
      const detail = getApiHttpErrorDetail(uploadError)
      setError(detail ?? 'Не удалось загрузить файл.')
    } finally {
      setIsUploading(false)
    }
  }

  function toggleDocument(documentCode: string) {
    setFormState((current) => {
      const exists = current.documentsMentioned.includes(documentCode)
      const next = exists
        ? current.documentsMentioned.filter((item) => item !== documentCode)
        : [...current.documentsMentioned, documentCode]
      return {
        ...current,
        documentsMentioned: next,
      }
    })
  }

  function updatePartialPayment(id: number, key: 'amount' | 'date', value: string) {
    setFormState((current) => ({
      ...current,
      partialPayments: current.partialPayments.map((row) =>
        row.id === id ? { ...row, [key]: value } : row,
      ),
    }))
  }

  function addPartialPaymentRow() {
    setFormState((current) => ({
      ...current,
      partialPayments: [
        ...current.partialPayments,
        {
          id: nextPaymentRowId++,
          amount: '',
          date: '',
        },
      ],
    }))
  }

  function removePartialPaymentRow(id: number) {
    setFormState((current) => ({
      ...current,
      partialPayments: current.partialPayments.filter((row) => row.id !== id),
    }))
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null
    setFileToUpload(file)
  }

  if (isLoading) {
    return (
      <main className="claims-page claims-page--step2">
        <section className="claims-wrap">
          <ClaimsBrand compact />
          <p className="claims-loading">Загружаем данные шага 2...</p>
        </section>
      </main>
    )
  }

  return (
    <main className="claims-page claims-page--step2">
      <section className="claims-wrap">
        <div className="claims-topline">
          <ClaimsBrand compact />
          <p className="claims-topline__step">ШАГ 2 ИЗ 4</p>
        </div>

        <header className="claims-step-header">
          <h1>УТОЧНИТЕ ДАННЫЕ ДЛЯ ПРЕТЕНЗИИ</h1>
          <p>AI уже проанализировал вашу ситуацию. Проверьте и дополните ключевые данные.</p>
          <ClaimsProgressBar label="Готовность документа:" value={completionPercent} />
        </header>

        <form className="claims-step2-form" onSubmit={onSubmit}>
          <section className="claims-step2-card">
            <h2>Стороны спора</h2>
            <div className="claims-form-grid">
              <div>
                <label htmlFor="creditor-name">Ваша компания</label>
                <input
                  id="creditor-name"
                  type="text"
                  value={formState.creditorName}
                  onChange={(event) =>
                    setFormState((current) => ({ ...current, creditorName: event.target.value }))
                  }
                  className={missingFieldSet.has('creditor_name') ? 'is-missing' : ''}
                />
              </div>
              <div>
                <label htmlFor="debtor-name">Компания должника</label>
                <input
                  id="debtor-name"
                  type="text"
                  value={formState.debtorName}
                  onChange={(event) =>
                    setFormState((current) => ({ ...current, debtorName: event.target.value }))
                  }
                  className={missingFieldSet.has('debtor_name') ? 'is-missing' : ''}
                />
              </div>
            </div>

            <div className="claims-form-grid claims-form-grid--2">
              <fieldset>
                <legend>Тип договора</legend>
                {CASE_TYPE_OPTIONS.map((option) => (
                  <label key={option.value} className="claims-radio">
                    <input
                      type="radio"
                      name="case_type"
                      checked={formState.caseType === option.value}
                      onChange={() =>
                        setFormState((current) => ({ ...current, caseType: option.value }))
                      }
                    />
                    {option.label}
                  </label>
                ))}
              </fieldset>

              <div className="claims-fields-stack">
                <fieldset>
                  <legend>Договор подписан?</legend>
                  <label className="claims-radio">
                    <input
                      type="radio"
                      name="contract_signed"
                      checked={formState.contractSigned === 'yes'}
                      onChange={() =>
                        setFormState((current) => ({ ...current, contractSigned: 'yes' }))
                      }
                    />
                    Да
                  </label>
                  <label className="claims-radio">
                    <input
                      type="radio"
                      name="contract_signed"
                      checked={formState.contractSigned === 'no'}
                      onChange={() =>
                        setFormState((current) => ({ ...current, contractSigned: 'no' }))
                      }
                    />
                    Нет
                  </label>
                </fieldset>

                <label htmlFor="contract-number">Номер договора</label>
                <input
                  id="contract-number"
                  type="text"
                  value={formState.contractNumber}
                  onChange={(event) =>
                    setFormState((current) => ({ ...current, contractNumber: event.target.value }))
                  }
                />
                <label htmlFor="contract-date">Дата договора</label>
                <input
                  id="contract-date"
                  type="date"
                  value={formState.contractDate}
                  onChange={(event) =>
                    setFormState((current) => ({ ...current, contractDate: event.target.value }))
                  }
                />
              </div>
            </div>

            <div className="claims-form-grid">
              <div>
                <label htmlFor="debt-amount">Общая сумма по договору</label>
                <input
                  id="debt-amount"
                  type="text"
                  value={formState.debtAmount}
                  onChange={(event) =>
                    setFormState((current) => ({ ...current, debtAmount: event.target.value }))
                  }
                  className={missingFieldSet.has('debt_amount') ? 'is-missing' : ''}
                  placeholder="380 000"
                />
              </div>
              <div>
                <label htmlFor="payment-due-date">Когда должна была быть оплата</label>
                <input
                  id="payment-due-date"
                  type="date"
                  value={formState.paymentDueDate}
                  onChange={(event) =>
                    setFormState((current) => ({ ...current, paymentDueDate: event.target.value }))
                  }
                  className={missingFieldSet.has('payment_due_date') ? 'is-missing' : ''}
                />
                {derived.overdueDays !== null ? (
                  <p className="claims-step2-overdue">Просрочка: {derived.overdueDays} дней</p>
                ) : null}
              </div>
            </div>

            <div className="claims-form-grid">
              <fieldset>
                <legend>Были ли частичные оплаты?</legend>
                <label className="claims-radio">
                  <input
                    type="radio"
                    name="partial_payments_present"
                    checked={formState.partialPaymentsPresent === 'no'}
                    onChange={() =>
                      setFormState((current) => ({ ...current, partialPaymentsPresent: 'no' }))
                    }
                  />
                  Нет
                </label>
                <label className="claims-radio">
                  <input
                    type="radio"
                    name="partial_payments_present"
                    checked={formState.partialPaymentsPresent === 'yes'}
                    onChange={() =>
                      setFormState((current) => ({ ...current, partialPaymentsPresent: 'yes' }))
                    }
                  />
                  Да, частично
                </label>
                {formState.partialPaymentsPresent === 'yes' ? (
                  <div className="claims-partial-payments">
                    {formState.partialPayments.map((row) => (
                      <div key={row.id} className="claims-partial-payments__row">
                        <input
                          type="text"
                          placeholder="Сумма"
                          value={row.amount}
                          onChange={(event) =>
                            updatePartialPayment(row.id, 'amount', event.target.value)
                          }
                        />
                        <input
                          type="date"
                          value={row.date}
                          onChange={(event) =>
                            updatePartialPayment(row.id, 'date', event.target.value)
                          }
                        />
                        <button type="button" onClick={() => removePartialPaymentRow(row.id)}>
                          Удалить
                        </button>
                      </div>
                    ))}
                    <button type="button" onClick={addPartialPaymentRow}>
                      + ДОБАВИТЬ ОПЛАТУ
                    </button>
                  </div>
                ) : null}
              </fieldset>

              <fieldset>
                <legend>Есть ли в договоре неустойка?</legend>
                <label className="claims-radio">
                  <input
                    type="radio"
                    name="penalty_exists"
                    checked={formState.penaltyExists === 'yes'}
                    onChange={() =>
                      setFormState((current) => ({ ...current, penaltyExists: 'yes' }))
                    }
                  />
                  Да
                </label>
                <label className="claims-radio">
                  <input
                    type="radio"
                    name="penalty_exists"
                    checked={formState.penaltyExists === 'no'}
                    onChange={() =>
                      setFormState((current) => ({ ...current, penaltyExists: 'no' }))
                    }
                  />
                  Нет
                </label>
                <label className="claims-radio">
                  <input
                    type="radio"
                    name="penalty_exists"
                    checked={formState.penaltyExists === 'unknown'}
                    onChange={() =>
                      setFormState((current) => ({ ...current, penaltyExists: 'unknown' }))
                    }
                  />
                  Не знаю
                </label>
                {formState.penaltyExists === 'yes' ? (
                  <>
                    <label htmlFor="penalty-rate">Ставка неустойки</label>
                    <input
                      id="penalty-rate"
                      type="text"
                      value={formState.penaltyRateText}
                      onChange={(event) =>
                        setFormState((current) => ({ ...current, penaltyRateText: event.target.value }))
                      }
                      className={missingFieldSet.has('penalty_rate_text') ? 'is-missing' : ''}
                      placeholder="0,1 % в день"
                    />
                  </>
                ) : null}
              </fieldset>
            </div>

            <section className="claims-amount-summary">
              <p>
                Итого оплачено: <strong>{formatRub(derived.totalPaidAmount)}</strong>
              </p>
              <p>
                Остаток долга:{' '}
                <strong>{derived.remainingDebtAmount === null ? '—' : formatRub(derived.remainingDebtAmount)}</strong>
              </p>
            </section>

            <section className="claims-documents">
              <h3>Подтверждающие документы</h3>
              <div className="claims-documents__grid">
                {DOCUMENT_OPTIONS.map((option) => (
                  <label key={option.value} className="claims-check">
                    <input
                      type="checkbox"
                      checked={formState.documentsMentioned.includes(option.value)}
                      onChange={() => toggleDocument(option.value)}
                    />
                    {option.label}
                  </label>
                ))}
              </div>
              <p className="claims-documents__hint">Документы можно приложить позже.</p>
            </section>

            <section className="claims-file-upload">
              <h3>Загрузка файлов</h3>
              <div className="claims-file-upload__form">
                <select
                  value={fileRole}
                  onChange={(event) => setFileRole(event.target.value)}
                  aria-label="Тип файла"
                >
                  {FILE_ROLE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <input type="file" onChange={onFileChange} />
                <button type="button" onClick={onUploadFile} disabled={isUploading}>
                  {isUploading ? 'Загрузка...' : 'Добавить файл'}
                </button>
              </div>
              {files.length > 0 ? (
                <ul className="claims-file-upload__list">
                  {files.map((file) => (
                    <li key={file.id}>
                      <span>{file.filename}</span>
                      <small>{file.file_role}</small>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="claims-file-upload__empty">Файлы пока не загружены.</p>
              )}
            </section>
          </section>

          <button className="claims-primary-button" type="submit" disabled={isSaving}>
            {isSaving ? 'СОХРАНЯЕМ...' : 'СФОРМИРОВАТЬ ПРЕТЕНЗИЮ'}
          </button>
          <p className="claims-step2-note">
            AI подготовит претензию с расчётом неустойки и ссылками на нормы ГК РФ.
          </p>
        </form>

        {notice ? <p className="claims-alert claims-alert--info">{notice}</p> : null}
        {error ? <p className="claims-alert claims-alert--error">{error}</p> : null}
      </section>
    </main>
  )
}

function buildInitialFormState(
  normalizedData: ClaimNormalizedData | null,
  caseType?: ClaimCaseType | null,
): Step2FormState {
  const source = normalizedData
  const partialPayments = source?.partial_payments ?? []

  const rows =
    partialPayments.length > 0
      ? partialPayments.map((item) => ({
          id: nextPaymentRowId++,
          amount: item.amount === null ? '' : String(item.amount),
          date: item.date ?? '',
        }))
      : [{ id: nextPaymentRowId++, amount: '', date: '' }]

  return {
    creditorName: source?.creditor_name ?? '',
    debtorName: source?.debtor_name ?? '',
    caseType: caseType ?? '',
    contractSigned: boolToTri(source?.contract_signed),
    contractNumber: source?.contract_number ?? '',
    contractDate: source?.contract_date ?? '',
    debtAmount: source?.debt_amount === null || source?.debt_amount === undefined ? '' : String(source.debt_amount),
    paymentDueDate: source?.payment_due_date ?? '',
    partialPaymentsPresent: boolToTri(source?.partial_payments_present),
    partialPayments: rows,
    penaltyExists: boolToTri(source?.penalty_exists),
    penaltyRateText: source?.penalty_rate_text ?? '',
    documentsMentioned: source?.documents_mentioned ?? [],
  }
}

function buildPatchPayload(formState: Step2FormState) {
  const partialPayments =
    formState.partialPaymentsPresent === 'yes'
      ? formState.partialPayments
          .map((row) => ({
            amount: normalizeOptionalField(row.amount),
            date: normalizeOptionalField(row.date),
          }))
          .filter((row) => row.amount !== null || row.date !== null)
      : []

  return {
    case_type: formState.caseType || null,
    normalized_data: {
      creditor_name: normalizeOptionalField(formState.creditorName),
      debtor_name: normalizeOptionalField(formState.debtorName),
      contract_signed: triToBool(formState.contractSigned),
      contract_number: normalizeOptionalField(formState.contractNumber),
      contract_date: normalizeOptionalField(formState.contractDate),
      debt_amount: normalizeOptionalField(formState.debtAmount),
      payment_due_date: normalizeOptionalField(formState.paymentDueDate),
      partial_payments_present: triToBool(formState.partialPaymentsPresent),
      partial_payments: partialPayments,
      penalty_exists: triToBool(formState.penaltyExists),
      penalty_rate_text:
        formState.penaltyExists === 'yes' ? normalizeOptionalField(formState.penaltyRateText) : null,
      documents_mentioned: formState.documentsMentioned,
    },
  }
}

function computeDerivedValues(formState: Step2FormState) {
  const debtAmount = parseAmount(formState.debtAmount)
  const totalPaid = formState.partialPayments.reduce((total, row) => {
    const parsed = parseAmount(row.amount)
    return parsed === null ? total : total + parsed
  }, 0)

  let remainingDebtAmount: number | null = null
  if (debtAmount !== null) {
    remainingDebtAmount = Math.max(debtAmount - totalPaid, 0)
  }

  let overdueDays: number | null = null
  if (formState.paymentDueDate) {
    const dueDate = new Date(formState.paymentDueDate)
    if (!Number.isNaN(dueDate.getTime())) {
      const diffMs = Date.now() - dueDate.getTime()
      overdueDays = Math.max(Math.floor(diffMs / 86_400_000), 0)
    }
  }

  return {
    totalPaidAmount: totalPaid,
    remainingDebtAmount,
    overdueDays,
  }
}

function parseAmount(value: string): number | null {
  const normalized = value
    .trim()
    .replace(/\s+/g, '')
    .replace(',', '.')
    .replace(/[^\d.\-]/g, '')
  if (!normalized) {
    return null
  }
  const parsed = Number(normalized)
  if (!Number.isFinite(parsed)) {
    return null
  }
  return parsed
}

function normalizeOptionalField(value: string): string | null {
  const normalized = value.trim()
  return normalized || null
}

function boolToTri(value: boolean | null | undefined): TriState {
  if (value === true) {
    return 'yes'
  }
  if (value === false) {
    return 'no'
  }
  return 'unknown'
}

function triToBool(value: TriState): boolean | null {
  if (value === 'yes') {
    return true
  }
  if (value === 'no') {
    return false
  }
  return null
}

function computeCompletionPercent(missingFieldsCount: number): number {
  const maxMissing = 8
  const ratio = Math.max(0, Math.min(1, 1 - missingFieldsCount / maxMissing))
  return Math.round(35 + ratio * 57)
}

function formatRub(value: number): string {
  return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value)} ₽`
}
