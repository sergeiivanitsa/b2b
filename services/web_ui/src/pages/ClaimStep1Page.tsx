import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { ClaimsBrand } from '../claims/components/ClaimsBrand'
import { createClaim, createClaimFromCompanyReport, extractClaim, getApiHttpErrorDetail, preflightCompanyReportHandoff, type CompanyReportHandoffPreflight } from '../claims/claimsApi'
import { hasClaimSession, readClaimSession, writeClaimSession } from '../claims/claimSession'
import { clearHandoffCommandKey, readOrCreateHandoffCommandKey, reportIdFromSearch } from '../claims/companyReportHandoff'
import { ApiHttpError } from '../lib/api'

type Step1LocationState = {
  missingFields?: string[]
  notice?: string
}

const STEP_1_EXAMPLE =
  'Например: ООО «Вектор» не оплатило поставку по договору №17 от 12.01.2026 на сумму 380 000 ₽. Срок оплаты истёк 18 дней назад'

export function ClaimStep1Page() {
  const navigate = useNavigate()
  const location = useLocation()
  const state = (location.state || {}) as Step1LocationState
  const reportId = useMemo(() => reportIdFromSearch(location.search), [location.search])

  const [inputText, setInputText] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [handoff, setHandoff] = useState<CompanyReportHandoffPreflight | null>(null)
  const [handoffLoading, setHandoffLoading] = useState(Boolean(reportId))
  const submitGuard = useRef(false)
  const handoffKey = useRef<string | null>(null)

  const hasDraftSession = useMemo(() => hasClaimSession(), [])
  const matchingDraftSession = useMemo(() => {
    const session = readClaimSession()
    return Boolean(reportId && session?.sourceCompanyReportId === reportId)
  }, [reportId])
  const missingFieldsHint =
    state.missingFields && state.missingFields.length > 0
      ? `Нужно заполнить поля: ${state.missingFields.join(', ')}`
      : null

  useEffect(() => {
    let cancelled = false
    handoffKey.current = null
    if (!reportId) {
      setHandoff(null)
      setHandoffLoading(false)
      return
    }
    setHandoffLoading(true)
    setHandoff(null)
    void preflightCompanyReportHandoff(reportId)
      .then((result) => {
        if (!cancelled) setHandoff(result)
      })
      .catch(() => {
        if (!cancelled) setHandoff({ report_id: reportId, availability: 'manual_required', reason: 'prefill_unavailable', prefill: {}, prefilled_fields: [] })
      })
      .finally(() => {
        if (!cancelled) setHandoffLoading(false)
      })
    return () => { cancelled = true }
  }, [reportId])

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitGuard.current) return
    const normalizedText = inputText.trim()
    if (!normalizedText) {
      setError('Опишите ситуацию в свободной форме, чтобы продолжить.')
      return
    }

    submitGuard.current = true
    setIsSubmitting(true)
    setError(null)

    try {
      const canUseHandoff = Boolean(reportId && handoff?.availability === 'available')
      if (canUseHandoff && !handoffKey.current) handoffKey.current = readOrCreateHandoffCommandKey(reportId!)
      const created = canUseHandoff
        ? await createClaimFromCompanyReport(reportId!, normalizedText, handoffKey.current!)
        : await createClaim(normalizedText)
      writeClaimSession({
        claimId: created.claim_id,
        editToken: created.edit_token,
        sourceCompanyReportId: canUseHandoff ? reportId! : undefined,
        handoffCommandKey: canUseHandoff ? handoffKey.current! : undefined,
      })
      if (canUseHandoff) clearHandoffCommandKey(reportId!)

      try {
        await extractClaim(created.claim_id, created.edit_token)
        navigate('/claims/step-2')
      } catch (extractError) {
        if (extractError instanceof ApiHttpError && extractError.status === 502) {
          navigate('/claims/step-2', {
            state: {
              notice:
                'Автоизвлечение временно недоступно. Заполните данные вручную, это не блокирует продолжение.',
            } satisfies Step1LocationState,
          })
          return
        }
        throw extractError
      }
    } catch (submitError) {
      const detail = getApiHttpErrorDetail(submitError)
      setError(detail ?? 'Не удалось создать заявку. Повторите попытку.')
    } finally {
      submitGuard.current = false
      setIsSubmitting(false)
    }
  }

  function handleContinueDraft() {
    const session = readClaimSession()
    if (!session) {
      return
    }
    navigate('/claims/step-2')
  }

  return (
    <main className="claims-page claims-page--step1">
      <section className="claims-wrap">
        <ClaimsBrand />

        <div className="claims-hero claims-step1-first-screen">
          <div className="claims-hero__left">
            <h1 className="claims-hero__title claims-step1-first-screen__title">
              <span className="claims-step1-first-screen__title-line claims-step1-first-screen__title-line--top">ВЕРНИТЕ ДОЛГ</span>{' '}
              <span className="claims-step1-first-screen__title-line claims-step1-first-screen__title-line--middle">С КОНТРАГЕНТА</span>{' '}
              <span className="claims-step1-first-screen__title-line claims-step1-first-screen__title-line--accent">БЕЗ СУДА</span>
            </h1>
            <p className="claims-hero__lead claims-step1-first-screen__lead">
              Опишите ситуацию, и через 5 минут получите досудебную претензию с требованиями к
              должнику, расчётом неустойки и правовыми основаниями для взыскания долга
            </p>

            <section className="claims-benefits claims-step1-first-screen__benefits">
              <h2 className="claims-step1-first-screen__benefits-title">После анализа вашей ситуации AI-ассистент:</h2>
              <ul className="claims-step1-first-screen__benefits-list">
                <li>задаст важные уточняющие вопросы</li>
                <li>подготовит документ с учётом норм ГК РФ</li>
                <li>
                  финальную версию проверит опытный юрист
                  <br />
                  по претензионной работе
                </li>
              </ul>
            </section>
          </div>

          <div className="claims-hero__right claims-step1-first-screen__form-area">
            <form className="claims-step1-form claims-step1-first-screen__form" onSubmit={onSubmit}>
              {handoffLoading ? <p role="status">Проверяем реквизиты должника…</p> : null}
              {handoff?.availability === 'available' ? <p className="claims-alert claims-alert--info" role="status">Реквизиты должника заполнены из отчёта: {handoff.prefill.debtor_name || handoff.prefill.debtor_inn}.</p> : null}
              {reportId && !handoffLoading && handoff?.availability !== 'available' ? <p className="claims-alert claims-alert--info" role="status">Не удалось автоматически заполнить реквизиты. Вы можете продолжить вручную.</p> : null}
              <textarea
                id="claim-input-text"
                className="claims-step1-first-screen__textarea"
                value={inputText}
                onChange={(event) => setInputText(event.target.value)}
                placeholder="Коротко опишите ситуацию: кто должен, по какому договору, сумму долга и когда истёк срок оплаты?"
                maxLength={4000}
                required
                aria-label="Коротко опишите ситуацию"
              />
              <p className="claims-step1-form__example claims-step1-first-screen__example">{STEP_1_EXAMPLE}</p>
              <button className="claims-step1-first-screen__cta" type="submit" disabled={isSubmitting}>
                {isSubmitting ? 'СОЗДАЁМ...' : 'СОЗДАТЬ ПРЕТЕНЗИЮ'}
              </button>
            </form>
            <p className="claims-step1-footnote claims-step1-first-screen__footnote">шаг 1 из 4: описание ситуации</p>
          </div>
        </div>

        {hasDraftSession ? (
          <aside className="claims-alert claims-alert--info">
            <p>{matchingDraftSession ? 'Найден черновик этой компании. Продолжите его, чтобы не создать дубликат.' : 'Найден сохранённый черновик заявки. Можно продолжить с шага 2.'}</p>
            <button type="button" onClick={handleContinueDraft}>
              Продолжить черновик
            </button>
          </aside>
        ) : null}
        {state.notice ? <p className="claims-alert claims-alert--info">{state.notice}</p> : null}
        {missingFieldsHint ? <p className="claims-alert claims-alert--warn">{missingFieldsHint}</p> : null}
        {error ? <p className="claims-alert claims-alert--error">{error}</p> : null}
      </section>
    </main>
  )
}
