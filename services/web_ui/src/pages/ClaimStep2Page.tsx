import { useEffect, useMemo, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { restoreClaimFromSession } from '../claims/claimRestore'
import { ClaimsBrand } from '../claims/components/ClaimsBrand'
import { ClaimsProgressBar } from '../claims/components/ClaimsProgressBar'
import {
  deleteClaimFile,
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
  creditorInn: string
  debtorName: string
  debtorInn: string
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

type Step2InnErrors = {
  creditorInn: string | null
  debtorInn: string | null
}

type Step2LocationState = {
  notice?: string
  missingFields?: string[]
}

const CASE_TYPE_OPTIONS: Array<{ value: ClaimCaseType; label: string }> = [
  { value: 'supply', label: 'Р”РѕРіРѕРІРѕСЂ РїРѕСЃС‚Р°РІРєРё С‚РѕРІР°СЂР°' },
  { value: 'services', label: 'Р”РѕРіРѕРІРѕСЂ РѕРєР°Р·Р°РЅРёСЏ СѓСЃР»СѓРі' },
  { value: 'contract_work', label: 'Р”РѕРіРѕРІРѕСЂ РїРѕРґСЂСЏРґР°' },
]

const DOCUMENT_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'contract', label: 'Р”РѕРіРѕРІРѕСЂ' },
  { value: 'waybill', label: 'РќР°РєР»Р°РґРЅС‹Рµ / РЈРџР”' },
  { value: 'services_act', label: 'РђРєС‚С‹ СѓСЃР»СѓРі' },
  { value: 'acceptance_act', label: 'РђРєС‚С‹ РІС‹РїРѕР»РЅРµРЅРЅС‹С… СЂР°Р±РѕС‚' },
  { value: 'invoice', label: 'РЎС‡РµС‚Р°' },
  { value: 'payment_order', label: 'РџР»Р°С‚С‘Р¶РЅС‹Рµ РїРѕСЂСѓС‡РµРЅРёСЏ' },
  { value: 'specification', label: 'РЎРїРµС†РёС„РёРєР°С†РёСЏ' },
]

let nextPaymentRowId = 1

const STEP2_REQUIRED_BASE_FIELDS = [
  'creditor_name',
  'creditor_inn',
  'debtor_name',
  'debtor_inn',
  'contract_signed',
  'debt_amount',
  'payment_due_date',
]

const MAX_UPLOAD_FILE_SIZE_BYTES = 10 * 1024 * 1024
const MAX_UPLOAD_FILE_SIZE_MB = Math.round(MAX_UPLOAD_FILE_SIZE_BYTES / (1024 * 1024))
const ALLOWED_UPLOAD_EXTENSIONS = ['pdf', 'doc', 'docx', 'rtf', 'jpg', 'jpeg', 'png'] as const
const ALLOWED_UPLOAD_MIME_TYPES = [
  'application/pdf',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/rtf',
  'text/rtf',
  'image/jpeg',
  'image/png',
] as const
const ALLOWED_UPLOAD_EXTENSIONS_SET: ReadonlySet<string> = new Set(ALLOWED_UPLOAD_EXTENSIONS)
const ALLOWED_UPLOAD_MIME_TYPES_SET: ReadonlySet<string> = new Set(ALLOWED_UPLOAD_MIME_TYPES)
const FILE_INPUT_ACCEPT = [
  '.pdf',
  '.doc',
  '.docx',
  '.rtf',
  '.jpg',
  '.jpeg',
  '.png',
  ...ALLOWED_UPLOAD_MIME_TYPES,
].join(',')

export function ClaimStep2Page() {
  const navigate = useNavigate()
  const location = useLocation()
  const locationState = (location.state || {}) as Step2LocationState

  const [claimId, setClaimId] = useState<number | null>(null)
  const [editToken, setEditToken] = useState<string>('')
  const [formState, setFormState] = useState<Step2FormState>(() => buildInitialFormState(null))
  const [missingFields, setMissingFields] = useState<string[]>(locationState.missingFields ?? [])
  const [files, setFiles] = useState<ClaimFileSnapshot[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadProgressText, setUploadProgressText] = useState<string | null>(null)
  const [deletingFileId, setDeletingFileId] = useState<number | null>(null)
  const [notice, setNotice] = useState<string | null>(locationState.notice ?? null)
  const [error, setError] = useState<string | null>(null)
  const [innErrors, setInnErrors] = useState<Step2InnErrors>({
    creditorInn: null,
    debtorInn: null,
  })

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
        setError('РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ С‡РµСЂРЅРѕРІРёРє Р·Р°СЏРІРєРё. РћР±РЅРѕРІРёС‚Рµ СЃС‚СЂР°РЅРёС†Сѓ.')
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
    () => computeCompletionPercent(formState, missingFields),
    [formState, missingFields],
  )
  const missingFieldSet = useMemo(() => new Set(missingFields), [missingFields])

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!claimId || !editToken) {
      setError('РЎРµСЃСЃРёСЏ РЅРµ РЅР°Р№РґРµРЅР°. РќР°С‡РЅРёС‚Рµ Р·Р°РЅРѕРІРѕ СЃ С€Р°РіР° 1.')
      return
    }

    const validation = validateInnFields(formState)
    setInnErrors(validation.errors)
    if (!validation.isValid) {
      setError(validation.message)
      setNotice(null)
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
      setError(detail ?? 'РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕС…СЂР°РЅРёС‚СЊ РґР°РЅРЅС‹Рµ С€Р°РіР° 2.')
    } finally {
      setIsSaving(false)
    }
  }

  async function onDeleteFile(fileId: number) {
<<<<<<< HEAD
  if (!claimId || !editToken) {
    setError('Сессия не найдена. Начните заново с шага 1.')
    return
=======
    if (!claimId || !editToken) {
      setError('Сессия не найдена. Начните заново с шага 1.')
      return
    }

    setDeletingFileId(fileId)
    setNotice(null)
    setError(null)
    try {
      await deleteClaimFile(claimId, editToken, fileId)
      const nextFiles = await listClaimFiles(claimId, editToken)
      setFiles(nextFiles)
      setNotice('Файл удалён.')
    } catch (deleteError) {
      const detail = getApiHttpErrorDetail(deleteError)
      setError(detail ?? 'Не удалось удалить файл.')
    } finally {
      setDeletingFileId(null)
    }
>>>>>>> origin/main
  }

  setDeletingFileId(fileId)
  setNotice(null)
  setError(null)
  try {
    await deleteClaimFile(claimId, editToken, fileId)
    const nextFiles = await listClaimFiles(claimId, editToken)
    setFiles(nextFiles)
    setNotice('Файл удалён.')
  } catch (deleteError) {
    const detail = getApiHttpErrorDetail(deleteError)
    setError(detail ?? 'Не удалось удалить файл.')
  } finally {
    setDeletingFileId(null)
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

  async function onFileChange(event: ChangeEvent<HTMLInputElement>) {
<<<<<<< HEAD
  if (!claimId || !editToken) {
    setError('Сессия не найдена. Начните заново с шага 1.')
    event.target.value = ''
    return
  }
=======
    if (!claimId || !editToken) {
      setError('Сессия не найдена. Начните заново с шага 1.')
      event.target.value = ''
      return
    }
>>>>>>> origin/main

    const selectedFiles = Array.from(event.target.files ?? [])
    event.target.value = ''
    if (selectedFiles.length === 0) {
      return
    }

    setIsUploading(true)
    setUploadProgressText(null)
    setNotice(null)
    setError(null)

    const uploadErrors: string[] = []
    let uploadedCount = 0

    try {
      for (const [index, file] of selectedFiles.entries()) {
        const clientValidationError = validateUploadCandidate(file)
        if (clientValidationError) {
          uploadErrors.push(clientValidationError)
          continue
        }

        setUploadProgressText(`Загружаем файл ${index + 1} из ${selectedFiles.length}: ${file.name}`)
        try {
          await uploadClaimFile(claimId, editToken, file)
          uploadedCount += 1
        } catch (uploadError) {
          const detail = getApiHttpErrorDetail(uploadError)
          uploadErrors.push(mapUploadError(detail, file.name))
        }
      }

      if (uploadedCount > 0) {
        const nextFiles = await listClaimFiles(claimId, editToken)
        setFiles(nextFiles)
        setNotice(
          uploadedCount === 1
            ? 'Файл успешно добавлен к заявке.'
            : `Успешно загружено файлов: ${uploadedCount}.`,
        )
      }

      if (uploadErrors.length > 0) {
        setError(uploadErrors.join(' '))
      }
    } finally {
      setIsUploading(false)
      setUploadProgressText(null)
    }
  }

  function onInnChange(field: 'creditorInn' | 'debtorInn', value: string) {
    const normalizedValue = normalizeInnInput(value)
    setFormState((current) => ({
      ...current,
      [field]: normalizedValue,
    }))
    setInnErrors((current) => ({
      ...current,
      [field]: null,
    }))
  }

  if (isLoading) {
    return (
      <main className="claims-page claims-page--step2">
        <section className="claims-wrap">
          <ClaimsBrand compact />
          <p className="claims-loading">Р—Р°РіСЂСѓР¶Р°РµРј РґР°РЅРЅС‹Рµ С€Р°РіР° 2...</p>
        </section>
      </main>
    )
  }

  return (
    <main className="claims-page claims-page--step2">
      <section className="claims-wrap">
        <div className="claims-topline">
          <ClaimsBrand compact />
          <p className="claims-topline__step">РЁРђР“ 2 РР— 4</p>
        </div>

        <header className="claims-step-header">
          <h1>РЈРўРћР§РќРРўР• Р”РђРќРќР«Р• Р”Р›РЇ РџР Р•РўР•РќР—РР</h1>
          <p>AI СѓР¶Рµ РїСЂРѕР°РЅР°Р»РёР·РёСЂРѕРІР°Р» РІР°С€Сѓ СЃРёС‚СѓР°С†РёСЋ. РџСЂРѕРІРµСЂСЊС‚Рµ Рё РґРѕРїРѕР»РЅРёС‚Рµ РєР»СЋС‡РµРІС‹Рµ РґР°РЅРЅС‹Рµ.</p>
          <ClaimsProgressBar label="Р“РѕС‚РѕРІРЅРѕСЃС‚СЊ РґРѕРєСѓРјРµРЅС‚Р°:" value={completionPercent} />
        </header>

        <form className="claims-step2-form" onSubmit={onSubmit}>
          <section className="claims-step2-card">
            <h2>РЎС‚РѕСЂРѕРЅС‹ СЃРїРѕСЂР°</h2>
            <div className="claims-form-grid">
              <div>
                <label htmlFor="creditor-name">Р’Р°С€Р° РєРѕРјРїР°РЅРёСЏ</label>
                <input
                  id="creditor-name"
                  type="text"
                  value={formState.creditorName}
                  onChange={(event) =>
                    setFormState((current) => ({ ...current, creditorName: event.target.value }))
                  }
                  className={isFieldMissing(missingFieldSet, 'creditor_name', formState.creditorName) ? 'is-missing' : ''}
                />
              </div>
              <div>
                <label htmlFor="debtor-name">РљРѕРјРїР°РЅРёСЏ РґРѕР»Р¶РЅРёРєР°</label>
                <input
                  id="debtor-name"
                  type="text"
                  value={formState.debtorName}
                  onChange={(event) =>
                    setFormState((current) => ({ ...current, debtorName: event.target.value }))
                  }
                  className={isFieldMissing(missingFieldSet, 'debtor_name', formState.debtorName) ? 'is-missing' : ''}
                />
              </div>
            </div>

            <div className="claims-form-grid">
              <div>
                <label htmlFor="creditor-inn">РРќРќ РєСЂРµРґРёС‚РѕСЂР°</label>
                <input
                  id="creditor-inn"
                  type="text"
                  inputMode="numeric"
                  autoComplete="off"
                  value={formState.creditorInn}
                  onChange={(event) => onInnChange('creditorInn', event.target.value)}
                  className={
                    isFieldMissing(missingFieldSet, 'creditor_inn', formState.creditorInn) || innErrors.creditorInn
                      ? 'is-missing'
                      : ''
                  }
                  placeholder="10 РёР»Рё 12 С†РёС„СЂ"
                />
              </div>
              <div>
                <label htmlFor="debtor-inn">РРќРќ РґРѕР»Р¶РЅРёРєР°</label>
                <input
                  id="debtor-inn"
                  type="text"
                  inputMode="numeric"
                  autoComplete="off"
                  value={formState.debtorInn}
                  onChange={(event) => onInnChange('debtorInn', event.target.value)}
                  className={
                    isFieldMissing(missingFieldSet, 'debtor_inn', formState.debtorInn) || innErrors.debtorInn
                      ? 'is-missing'
                      : ''
                  }
                  placeholder="10 РёР»Рё 12 С†РёС„СЂ"
                />
              </div>
            </div>


            <div className="claims-form-grid claims-form-grid--2">
              <fieldset>
                <legend>РўРёРї РґРѕРіРѕРІРѕСЂР°</legend>
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
                  <legend>Р”РѕРіРѕРІРѕСЂ РїРѕРґРїРёСЃР°РЅ?</legend>
                  <label className="claims-radio">
                    <input
                      type="radio"
                      name="contract_signed"
                      checked={formState.contractSigned === 'yes'}
                      onChange={() =>
                        setFormState((current) => ({ ...current, contractSigned: 'yes' }))
                      }
                    />
                    Р”Р°
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
                    РќРµС‚
                  </label>
                </fieldset>

                <label htmlFor="contract-number">РќРѕРјРµСЂ РґРѕРіРѕРІРѕСЂР°</label>
                <input
                  id="contract-number"
                  type="text"
                  value={formState.contractNumber}
                  onChange={(event) =>
                    setFormState((current) => ({ ...current, contractNumber: event.target.value }))
                  }
                />
                <label htmlFor="contract-date">Р”Р°С‚Р° РґРѕРіРѕРІРѕСЂР°</label>
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
                <label htmlFor="debt-amount">РћР±С‰Р°СЏ СЃСѓРјРјР° РїРѕ РґРѕРіРѕРІРѕСЂСѓ</label>
                <input
                  id="debt-amount"
                  type="text"
                  value={formState.debtAmount}
                  onChange={(event) =>
                    setFormState((current) => ({ ...current, debtAmount: event.target.value }))
                  }
                  className={isFieldMissing(missingFieldSet, 'debt_amount', formState.debtAmount) ? 'is-missing' : ''}
                  placeholder="380 000"
                />
              </div>
              <div>
                <label htmlFor="payment-due-date">РљРѕРіРґР° РґРѕР»Р¶РЅР° Р±С‹Р»Р° Р±С‹С‚СЊ РѕРїР»Р°С‚Р°</label>
                <input
                  id="payment-due-date"
                  type="date"
                  value={formState.paymentDueDate}
                  onChange={(event) =>
                    setFormState((current) => ({ ...current, paymentDueDate: event.target.value }))
                  }
                  className={isFieldMissing(missingFieldSet, 'payment_due_date', formState.paymentDueDate) ? 'is-missing' : ''}
                />
                {derived.overdueDays !== null ? (
                  <p className="claims-step2-overdue">РџСЂРѕСЃСЂРѕС‡РєР°: {derived.overdueDays} РґРЅРµР№</p>
                ) : null}
              </div>
            </div>

            <div className="claims-form-grid">
              <fieldset>
                <legend>Р‘С‹Р»Рё Р»Рё С‡Р°СЃС‚РёС‡РЅС‹Рµ РѕРїР»Р°С‚С‹?</legend>
                <label className="claims-radio">
                  <input
                    type="radio"
                    name="partial_payments_present"
                    checked={formState.partialPaymentsPresent === 'no'}
                    onChange={() =>
                      setFormState((current) => ({ ...current, partialPaymentsPresent: 'no' }))
                    }
                  />
                  РќРµС‚
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
                  Р”Р°, С‡Р°СЃС‚РёС‡РЅРѕ
                </label>
                {formState.partialPaymentsPresent === 'yes' ? (
                  <div className="claims-partial-payments">
                    {formState.partialPayments.map((row) => (
                      <div key={row.id} className="claims-partial-payments__row">
                        <input
                          type="text"
                          placeholder="РЎСѓРјРјР°"
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
                          РЈРґР°Р»РёС‚СЊ
                        </button>
                      </div>
                    ))}
                    <button type="button" onClick={addPartialPaymentRow}>
                      + Р”РћР‘РђР’РРўР¬ РћРџР›РђРўРЈ
                    </button>
                  </div>
                ) : null}
              </fieldset>

              <fieldset>
                <legend>Р•СЃС‚СЊ Р»Рё РІ РґРѕРіРѕРІРѕСЂРµ РЅРµСѓСЃС‚РѕР№РєР°?</legend>
                <label className="claims-radio">
                  <input
                    type="radio"
                    name="penalty_exists"
                    checked={formState.penaltyExists === 'yes'}
                    onChange={() =>
                      setFormState((current) => ({ ...current, penaltyExists: 'yes' }))
                    }
                  />
                  Р”Р°
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
                  РќРµС‚
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
                  РќРµ Р·РЅР°СЋ
                </label>
                {formState.penaltyExists === 'yes' ? (
                  <>
                    <label htmlFor="penalty-rate">РЎС‚Р°РІРєР° РЅРµСѓСЃС‚РѕР№РєРё</label>
                    <input
                      id="penalty-rate"
                      type="text"
                      value={formState.penaltyRateText}
                      onChange={(event) =>
                        setFormState((current) => ({ ...current, penaltyRateText: event.target.value }))
                      }
                      className={isFieldMissing(missingFieldSet, 'penalty_rate_text', formState.penaltyRateText) ? 'is-missing' : ''}
                      placeholder="0,1 % РІ РґРµРЅСЊ"
                    />
                  </>
                ) : null}
              </fieldset>
            </div>

            <section className="claims-amount-summary">
              <p>
                РС‚РѕРіРѕ РѕРїР»Р°С‡РµРЅРѕ: <strong>{formatRub(derived.totalPaidAmount)}</strong>
              </p>
              <p>
                РћСЃС‚Р°С‚РѕРє РґРѕР»РіР°:{' '}
                <strong>{derived.remainingDebtAmount === null ? 'вЂ”' : formatRub(derived.remainingDebtAmount)}</strong>
              </p>
            </section>

            <section className="claims-documents">
              <h3>РџРѕРґС‚РІРµСЂР¶РґР°СЋС‰РёРµ РґРѕРєСѓРјРµРЅС‚С‹</h3>
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
              <p className="claims-documents__hint">Р”РѕРєСѓРјРµРЅС‚С‹ РјРѕР¶РЅРѕ РїСЂРёР»РѕР¶РёС‚СЊ РїРѕР·Р¶Рµ.</p>
            </section>

            <section className="claims-file-upload">
              <h3>Загрузите все документы по вашей претензии</h3>
              <div className="claims-file-upload__form">
                <label
                  className={`claims-file-upload__pick ${isUploading ? 'is-disabled' : ''}`}
                >
                  Выбрать файл
                  <input
                    type="file"
                    accept={FILE_INPUT_ACCEPT}
                    multiple
                    onChange={onFileChange}
                    disabled={isUploading}
                    className="claims-file-upload__input"
                  />
                </label>
                <p className="claims-file-upload__hint">
                  Допустимые форматы: PDF, DOC, DOCX, RTF, JPG, JPEG, PNG. До {MAX_UPLOAD_FILE_SIZE_MB} МБ на файл.
                </p>
                {isUploading ? (
                  <p className="claims-file-upload__status">
                    {uploadProgressText ?? 'Загрузка файлов...'}
                  </p>
                ) : null}
              </div>
              {files.length > 0 ? (
                <ul className="claims-file-upload__list">
                  {files.map((file) => (
                    <li key={file.id}>
                      <div className="claims-file-upload__meta">
                        <span>{file.filename}</span>
                        <small>{file.mime_type}</small>
                      </div>
                      <button
                        type="button"
                        className="claims-file-upload__remove"
                        onClick={() => void onDeleteFile(file.id)}
                        disabled={deletingFileId === file.id || isUploading}
                      >
                        {deletingFileId === file.id ? 'Удаляем...' : 'Удалить'}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
<<<<<<< HEAD
                <p className="claims-file-upload__empty">Файлы не загружены.</p>
=======
                <p className="claims-file-upload__empty">Файлы пока не загружены.</p>
>>>>>>> origin/main
              )}
            </section>
          </section>

          <button className="claims-primary-button" type="submit" disabled={isSaving}>
            {isSaving ? 'РЎРћРҐР РђРќРЇР•Рњ...' : 'РЎР¤РћР РњРР РћР’РђРўР¬ РџР Р•РўР•РќР—РР®'}
          </button>
          <p className="claims-step2-note">
            AI РїРѕРґРіРѕС‚РѕРІРёС‚ РїСЂРµС‚РµРЅР·РёСЋ СЃ СЂР°СЃС‡С‘С‚РѕРј РЅРµСѓСЃС‚РѕР№РєРё Рё СЃСЃС‹Р»РєР°РјРё РЅР° РЅРѕСЂРјС‹ Р“Рљ Р Р¤.
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
    creditorInn: normalizeInnInput(source?.creditor_inn ?? ''),
    debtorName: source?.debtor_name ?? '',
    debtorInn: normalizeInnInput(source?.debtor_inn ?? ''),
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
      creditor_inn: normalizeInnForPayload(formState.creditorInn),
      debtor_name: normalizeOptionalField(formState.debtorName),
      debtor_inn: normalizeInnForPayload(formState.debtorInn),
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

function isFieldMissing(
  missingFieldSet: ReadonlySet<string>,
  fieldName: string,
  value: string,
): boolean {
  return missingFieldSet.has(fieldName) && normalizeOptionalField(value) === null
}

function normalizeInnInput(value: string): string {
  return value.replace(/\D+/g, '').slice(0, 12)
}

function normalizeInnForPayload(value: string): string | null {
  const normalized = normalizeInnInput(value)
  return normalized || null
}

function validateInnFields(formState: Step2FormState): {
  isValid: boolean
  message: string
  errors: Step2InnErrors
} {
  const creditorInnError = validateInnValue(formState.creditorInn, 'РРќРќ РєСЂРµРґРёС‚РѕСЂР°')
  const debtorInnError = validateInnValue(formState.debtorInn, 'РРќРќ РґРѕР»Р¶РЅРёРєР°')
  const errors: Step2InnErrors = {
    creditorInn: creditorInnError,
    debtorInn: debtorInnError,
  }

  if (creditorInnError) {
    return {
      isValid: false,
      message: creditorInnError,
      errors,
    }
  }
  if (debtorInnError) {
    return {
      isValid: false,
      message: debtorInnError,
      errors,
    }
  }

  return {
    isValid: true,
    message: '',
    errors,
  }
}

function validateInnValue(value: string, label: string): string | null {
  const normalized = normalizeInnInput(value)
  if (!normalized) {
    return `${label}: Р·Р°РїРѕР»РЅРёС‚Рµ РїРѕР»Рµ.`
  }
  if (normalized.length !== 10 && normalized.length !== 12) {
    return `${label}: РґРѕР»Р¶РЅРѕ Р±С‹С‚СЊ 10 РёР»Рё 12 С†РёС„СЂ.`
  }
  return null
}

function validateUploadCandidate(file: File): string | null {
  if (file.size <= 0) {
    return `Р¤Р°Р№Р» "${file.name}" РїСѓСЃС‚РѕР№. Р’С‹Р±РµСЂРёС‚Рµ РґСЂСѓРіРѕР№ С„Р°Р№Р».`
  }
  if (file.size > MAX_UPLOAD_FILE_SIZE_BYTES) {
    return `Р¤Р°Р№Р» "${file.name}" СЃР»РёС€РєРѕРј Р±РѕР»СЊС€РѕР№. РњР°РєСЃРёРјСѓРј ${MAX_UPLOAD_FILE_SIZE_MB} РњР‘.`
  }

  const extension = getFileExtension(file.name)
  const mimeType = file.type.trim().toLowerCase()
  const hasAllowedExtension = extension ? ALLOWED_UPLOAD_EXTENSIONS_SET.has(extension) : false
  const hasAllowedMimeType = mimeType ? ALLOWED_UPLOAD_MIME_TYPES_SET.has(mimeType) : false
  if (!hasAllowedExtension && !hasAllowedMimeType) {
    return `Р¤Р°Р№Р» "${file.name}" РёРјРµРµС‚ РЅРµРїРѕРґРґРµСЂР¶РёРІР°РµРјС‹Р№ С„РѕСЂРјР°С‚. Р Р°Р·СЂРµС€РµРЅС‹: PDF, DOC, DOCX, RTF, JPG, JPEG, PNG.`
  }
  return null
}

function getFileExtension(fileName: string): string {
  const trimmedName = fileName.trim()
  if (!trimmedName || !trimmedName.includes('.')) {
    return ''
  }
  const parts = trimmedName.split('.')
  return (parts[parts.length - 1] || '').trim().toLowerCase()
}

function mapUploadError(detail: string | null, fileName: string): string {
  if (!detail) {
    return `РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ С„Р°Р№Р» "${fileName}".`
  }
  const normalized = detail.toLowerCase()
  if (normalized.includes('unsupported mime type')) {
    return `Р¤Р°Р№Р» "${fileName}" РёРјРµРµС‚ РЅРµРїРѕРґРґРµСЂР¶РёРІР°РµРјС‹Р№ С„РѕСЂРјР°С‚. Р Р°Р·СЂРµС€РµРЅС‹: PDF, DOC, DOCX, RTF, JPG, JPEG, PNG.`
  }
  if (normalized.includes('file is too large')) {
    return `Р¤Р°Р№Р» "${fileName}" СЃР»РёС€РєРѕРј Р±РѕР»СЊС€РѕР№. РњР°РєСЃРёРјСѓРј ${MAX_UPLOAD_FILE_SIZE_MB} РњР‘.`
  }
  if (normalized.includes('file is empty')) {
    return `Р¤Р°Р№Р» "${fileName}" РїСѓСЃС‚РѕР№. Р’С‹Р±РµСЂРёС‚Рµ РґСЂСѓРіРѕР№ С„Р°Р№Р».`
  }
  return `Р¤Р°Р№Р» "${fileName}": ${detail}.`
}

function getRequiredStep2Fields(formState: Step2FormState): string[] {
  const requiredFields = [...STEP2_REQUIRED_BASE_FIELDS]
  if (formState.partialPaymentsPresent === 'yes') {
    requiredFields.push('partial_payments')
  }
  if (formState.penaltyExists === 'yes') {
    requiredFields.push('penalty_rate_text')
  }
  return requiredFields
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

function computeCompletionPercent(formState: Step2FormState, missingFields: string[]): number {
  const requiredFields = getRequiredStep2Fields(formState)
  const requiredFieldSet = new Set(requiredFields)
  const missingFieldsCount = missingFields.filter((field) => requiredFieldSet.has(field)).length
  const maxMissing = Math.max(requiredFields.length, 1)
  const ratio = Math.max(0, Math.min(1, 1 - missingFieldsCount / maxMissing))
  return Math.round(35 + ratio * 57)
}

function formatRub(value: number): string {
  return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value)} в‚Ѕ`
}
