import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { restoreClaimFromSession } from '../claims/claimRestore'
import { ClaimsBrand } from '../claims/components/ClaimsBrand'
import {
  generateClaimPreview,
  getApiHttpErrorDetail,
  getClaimPreview,
  getInsufficientDataDetail,
  payClaim,
} from '../claims/claimsApi'
import { ApiHttpError } from '../lib/api'

type LoadedClaimMeta = {
  claimId: number
  editToken: string
  priceRub: number
  manualReviewRequired: boolean
  alreadyPaid: boolean
}

const PACKAGE_ITEMS = [
  'Претензия PDF, проверенная юристом',
  'Редактируемый файл DOCX',
  'Расчет долга и неустойки',
  'Перечень приложений',
  'Сопроводительное письмо',
  'Инструкция по дальнейшим действиям',
]

export function ClaimStep4Page() {
  const navigate = useNavigate()

  const [meta, setMeta] = useState<LoadedClaimMeta | null>(null)
  const [previewText, setPreviewText] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isPaying, setIsPaying] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  useEffect(() => {
    let isCanceled = false

    async function loadPreview() {
      try {
        setIsLoading(true)
        setError(null)

        const restored = await restoreClaimFromSession()
        if (isCanceled) {
          return
        }

        if (restored.claim.generation_state === 'insufficient_data') {
          navigate('/claims/step-2', {
            replace: true,
            state: {
              missingFields: restored.claim.step2.missing_fields,
              notice: 'Для preview нужно дозаполнить обязательные поля.',
            },
          })
          return
        }

        setMeta({
          claimId: restored.claimId,
          editToken: restored.editToken,
          priceRub: restored.claim.price_rub,
          manualReviewRequired: restored.claim.manual_review_required,
          alreadyPaid: restored.claim.status === 'paid' || restored.claim.status === 'in_review' || restored.claim.status === 'sent',
        })

        const loadedPreviewText = await loadPreviewText(restored.claimId, restored.editToken)
        if (!isCanceled) {
          setPreviewText(loadedPreviewText)
        }
      } catch (loadError) {
        if (isCanceled) {
          return
        }
        if (loadError instanceof Error && (loadError.message === 'missing_session' || loadError.message === 'invalid_session')) {
          navigate('/claims', { replace: true })
          return
        }

        const insufficientDataFields = getInsufficientDataDetail(loadError)
        if (insufficientDataFields) {
          navigate('/claims/step-2', {
            replace: true,
            state: {
              missingFields: insufficientDataFields,
              notice: 'Preview заблокирован до заполнения обязательных полей.',
            },
          })
          return
        }

        setError('Не удалось загрузить preview. Вернитесь на шаг 3 и повторите.')
      } finally {
        if (!isCanceled) {
          setIsLoading(false)
        }
      }
    }

    void loadPreview()
    return () => {
      isCanceled = true
    }
  }, [navigate])

  const blurredPreviewText = useMemo(() => createBlurredPreview(previewText), [previewText])
  const discountPrice = useMemo(() => {
    if (!meta) {
      return 990
    }
    return meta.priceRub
  }, [meta])

  async function onPayClick() {
    if (!meta) {
      setError('Сессия не найдена. Начните заново с шага 1.')
      return
    }

    setIsPaying(true)
    setError(null)

    try {
      await payClaim(meta.claimId, meta.editToken)
      setSuccessMessage(
        'Оплата принята. Юрист проверит финальную версию и отправит результат на ваш email.',
      )
      setMeta((current) => (current ? { ...current, alreadyPaid: true } : current))
    } catch (payError) {
      const insufficientDataFields = getInsufficientDataDetail(payError)
      if (insufficientDataFields) {
        navigate('/claims/step-2', {
          replace: true,
          state: {
            missingFields: insufficientDataFields,
            notice: 'Оплата недоступна, пока данные недостаточны для preview.',
          },
        })
        return
      }

      const detail = getApiHttpErrorDetail(payError)
      if (detail === 'already_paid_or_later_state') {
        setSuccessMessage('Заявка уже оплачена и передана в работу.')
        setMeta((current) => (current ? { ...current, alreadyPaid: true } : current))
        return
      }
      setError(detail ?? 'Не удалось провести оплату. Повторите попытку.')
    } finally {
      setIsPaying(false)
    }
  }

  if (isLoading) {
    return (
      <main className="claims-page claims-page--step4">
        <section className="claims-wrap">
          <ClaimsBrand compact />
          <p className="claims-loading">Загружаем preview...</p>
        </section>
      </main>
    )
  }

  return (
    <main className="claims-page claims-page--step4">
      <section className="claims-wrap">
        <div className="claims-topline">
          <ClaimsBrand compact />
          <p className="claims-topline__step">ШАГ 4 ИЗ 4</p>
        </div>

        <header className="claims-step-header claims-step-header--centered">
          <h1>Документы для досудебного взыскания готовы</h1>
          <p>Подготовили комплект на основе введенных вами данных</p>
        </header>

        <section className="claims-step4-layout">
          <article className="claims-preview-card">
            <div className="claims-preview-card__head">
              <span>ОТ КОГО:</span>
              <span>КОМУ:</span>
            </div>
            <h2>ПРЕТЕНЗИЯ</h2>
            <pre>{blurredPreviewText}</pre>
            <p className="claims-preview-card__paywall-note">
              Полная версия документа доступна после оплаты
            </p>
          </article>

          <aside className="claims-paywall-card">
            <h2>Что входит в пакет</h2>
            <ul>
              {PACKAGE_ITEMS.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            {meta?.manualReviewRequired ? (
              <p className="claims-paywall-card__manual-review">
                В вашем случае итоговая версия будет дополнительно проверена вручную. Это уже
                включено в стоимость.
              </p>
            ) : null}

            <section className="claims-paywall-card__trust">
              <h3>Гарантия качества</h3>
              <p>Если в документе будет ошибка по нашей вине, вернем деньги</p>
              <h3>Конфиденциальность</h3>
              <p>Данные защищены шифрованием AES-256 и обрабатываются конфиденциально</p>
            </section>

            <section className="claims-paywall-card__price">
              <p className="claims-paywall-card__old-price">5 100 ₽</p>
              <p className="claims-paywall-card__new-price">{formatRub(discountPrice)}</p>
              <button
                type="button"
                onClick={onPayClick}
                disabled={isPaying || Boolean(meta?.alreadyPaid)}
              >
                {meta?.alreadyPaid ? 'Заявка уже оплачена' : isPaying ? 'ОПЛАТА...' : 'Получить пакет документов'}
              </button>
            </section>
            <p className="claims-paywall-card__hint">
              После проверки юрист отправит документы на e-mail
            </p>
          </aside>
        </section>

        <p className="claims-step4-backlink">
          <Link to="/claims/step-2">Вернуться к уточнению данных</Link>
        </p>

        {successMessage ? <p className="claims-alert claims-alert--success">{successMessage}</p> : null}
        {error ? <p className="claims-alert claims-alert--error">{error}</p> : null}
      </section>
    </main>
  )
}

async function loadPreviewText(claimId: number, editToken: string): Promise<string> {
  try {
    const preview = await getClaimPreview(claimId, editToken)
    return preview.generated_preview_text
  } catch (previewError) {
    if (previewError instanceof ApiHttpError && previewError.status === 404) {
      const generated = await generateClaimPreview(claimId, editToken)
      return generated.generated_preview_text
    }
    throw previewError
  }
}

function createBlurredPreview(previewText: string): string {
  if (!previewText.trim()) {
    return 'Текст предпросмотра пока не готов. Вернитесь на шаг 3 и повторите генерацию.'
  }

  const lines = previewText.split('\n')
  if (lines.length <= 12) {
    return previewText
  }
  const visible = lines.slice(0, 12)
  visible.push('...')
  visible.push('████████████████████████████████████████████')
  visible.push('████████████████████████████████████████████')
  visible.push('████████████████████████████████████████████')
  return visible.join('\n')
}

function formatRub(value: number): string {
  return `${new Intl.NumberFormat('ru-RU').format(value)} ₽`
}
