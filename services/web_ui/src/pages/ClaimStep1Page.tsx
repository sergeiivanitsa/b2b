import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { ClaimsBrand } from '../claims/components/ClaimsBrand'
import { createClaim, extractClaim, getApiHttpErrorDetail } from '../claims/claimsApi'
import { hasClaimSession, readClaimSession, writeClaimSession } from '../claims/claimSession'
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

  const [inputText, setInputText] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const hasDraftSession = useMemo(() => hasClaimSession(), [])
  const missingFieldsHint =
    state.missingFields && state.missingFields.length > 0
      ? `Нужно заполнить поля: ${state.missingFields.join(', ')}`
      : null

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const normalizedText = inputText.trim()
    if (!normalizedText) {
      setError('Опишите ситуацию в свободной форме, чтобы продолжить.')
      return
    }

    setIsSubmitting(true)
    setError(null)

    try {
      const created = await createClaim(normalizedText)
      writeClaimSession({
        claimId: created.claim_id,
        editToken: created.edit_token,
      })

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

        <div className="claims-hero">
          <div className="claims-hero__left">
            <h1 className="claims-hero__title">
              ВЕРНИТЕ ДОЛГ С КОНТРАГЕНТА <span>БЕЗ СУДА</span>
            </h1>
            <p className="claims-hero__lead">
              Опишите ситуацию, и через 5 минут получите досудебную претензию с требованиями к
              должнику, расчётом неустойки и правовыми основаниями для взыскания долга
            </p>

            <section className="claims-benefits">
              <h2>После анализа вашей ситуации AI-ассистент:</h2>
              <ul>
                <li>задаст важные уточняющие вопросы</li>
                <li>подготовит документ с учётом норм ГК РФ</li>
                <li>финальную версию проверит опытный юрист по претензионной работе</li>
              </ul>
            </section>
          </div>

          <div className="claims-hero__right">
            <form className="claims-step1-form" onSubmit={onSubmit}>
              <label htmlFor="claim-input-text">Коротко опишите ситуацию:</label>
              <textarea
                id="claim-input-text"
                value={inputText}
                onChange={(event) => setInputText(event.target.value)}
                placeholder="кто должен, по какому договору, сумму долга и когда истёк срок оплаты?"
                maxLength={4000}
                required
              />
              <p className="claims-step1-form__example">{STEP_1_EXAMPLE}</p>
              <button type="submit" disabled={isSubmitting}>
                {isSubmitting ? 'СОЗДАЁМ...' : 'СОЗДАТЬ ПРЕТЕНЗИЮ'}
              </button>
            </form>
            <p className="claims-step1-footnote">шаг 1 из 4: описание ситуации</p>
          </div>
        </div>

        {hasDraftSession ? (
          <aside className="claims-alert claims-alert--info">
            <p>Найден сохранённый черновик заявки. Можно продолжить с шага 2.</p>
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
