import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { restoreClaimFromSession } from '../claims/claimRestore'
import { ClaimsBrand } from '../claims/components/ClaimsBrand'
import { ClaimsProgressBar } from '../claims/components/ClaimsProgressBar'
import {
  generateClaimPreview,
  getApiHttpErrorDetail,
  getInsufficientDataDetail,
  updateClaimContact,
} from '../claims/claimsApi'

const LEFT_CHECKLIST = [
  'определил основания взыскания',
  'сформировал требование долга',
  'рассчитал период просрочки',
  'подобрал правовую базу',
  'подготовил структуру претензии',
]

const RIGHT_CHECKLIST = [
  {
    label:
      'проверенная опытным юристом и сформированная с соблюдением претензионного порядка досудебная претензия в PDF',
    done: true,
  },
  {
    label: 'редактируемая версия досудебной претензии в формате DOCX',
    done: true,
  },
  {
    label: 'сопроводительное письмо',
    done: false,
  },
  {
    label: 'таблица расчета неустойки',
    done: false,
  },
  {
    label: 'инструкция по дальнейшей работе с претензией',
    done: false,
  },
]

export function ClaimStep3Page() {
  const navigate = useNavigate()

  const [claimId, setClaimId] = useState<number | null>(null)
  const [editToken, setEditToken] = useState('')
  const [email, setEmail] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [progress, setProgress] = useState(92)

  useEffect(() => {
    let isCanceled = false

    async function loadClaim() {
      try {
        const restored = await restoreClaimFromSession()
        if (isCanceled) {
          return
        }
        if (restored.claim.generation_state === 'insufficient_data') {
          navigate('/claims/step-2', {
            replace: true,
            state: {
              missingFields: restored.claim.step2.missing_fields,
              notice: 'Для генерации нужно дозаполнить обязательные поля.',
            },
          })
          return
        }

        setClaimId(restored.claimId)
        setEditToken(restored.editToken)
        setEmail(restored.claim.client_email ?? '')
      } catch (loadError) {
        if (isCanceled) {
          return
        }
        if (loadError instanceof Error && (loadError.message === 'missing_session' || loadError.message === 'invalid_session')) {
          navigate('/claims', { replace: true })
          return
        }
        setError('Не удалось загрузить шаг 3. Обновите страницу.')
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

  const submitButtonText = useMemo(
    () => (isSubmitting ? 'ГОТОВИМ PREVIEW...' : 'ПОКАЗАТЬ ГОТОВУЮ ПРЕТЕНЗИЮ'),
    [isSubmitting],
  )

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!claimId || !editToken) {
      setError('Сессия не найдена. Вернитесь на шаг 1.')
      return
    }
    if (!email.trim()) {
      setError('Укажите email, чтобы продолжить.')
      return
    }

    setIsSubmitting(true)
    setError(null)

    try {
      await updateClaimContact(claimId, editToken, {
        client_email: email.trim(),
      })
      setProgress(96)

      await generateClaimPreview(claimId, editToken)
      setProgress(100)

      navigate('/claims/step-4')
    } catch (submitError) {
      const insufficientDataFields = getInsufficientDataDetail(submitError)
      if (insufficientDataFields) {
        navigate('/claims/step-2', {
          replace: true,
          state: {
            missingFields: insufficientDataFields,
            notice: 'Недостаточно данных для предпросмотра. Дозаполните шаг 2.',
          },
        })
        return
      }
      const detail = getApiHttpErrorDetail(submitError)
      setError(detail ?? 'Не удалось подготовить preview. Попробуйте ещё раз.')
    } finally {
      setIsSubmitting(false)
    }
  }

  if (isLoading) {
    return (
      <main className="claims-page claims-page--step3">
        <section className="claims-wrap">
          <ClaimsBrand compact />
          <p className="claims-loading">Готовим шаг 3...</p>
        </section>
      </main>
    )
  }

  return (
    <main className="claims-page claims-page--step3">
      <section className="claims-wrap">
        <div className="claims-topline">
          <ClaimsBrand compact />
          <p className="claims-topline__step">ШАГ 3 ИЗ 4</p>
        </div>

        <header className="claims-step-header">
          <h1>ГОТОВИМ ВАШУ ПРЕТЕНЗИЮ</h1>
          <p>AI уже обработал введённые данные и подготовил структуру претензии по вашему делу.</p>
          <ClaimsProgressBar label="Готовность документа:" value={progress} />
        </header>

        <section className="claims-step3-matrix">
          <article>
            <h2>По вашему делу AI-помощник:</h2>
            <ul>
              {LEFT_CHECKLIST.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </article>
          <article>
            <h2>Формируем пакет документов:</h2>
            <ul className="claims-doc-queue">
              {RIGHT_CHECKLIST.map((item) => (
                <li key={item.label} className={item.done ? 'is-done' : 'is-pending'}>
                  {item.label}
                </li>
              ))}
            </ul>
          </article>
        </section>

        <section className="claims-step3-contact">
          <h2>Куда отправить готовые документы?</h2>
          <p>На следующем шаге вы увидите готовую претензию по вашим данным</p>
          <form className="claims-step3-contact__form" onSubmit={onSubmit}>
            <input
              type="email"
              placeholder="example@company.ru"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
            <button type="submit" disabled={isSubmitting}>
              {submitButtonText}
            </button>
          </form>
          <p className="claims-step3-contact__hint">
            После проверки юристом на этот e-mail пришлем готовый пакет документов для взыскания
          </p>
        </section>

        {error ? <p className="claims-alert claims-alert--error">{error}</p> : null}
      </section>
    </main>
  )
}
