import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import {
  fetchAdminClaim,
  fetchAdminClaimFiles,
  sendAdminClaimFinalResult,
  updateAdminClaimFinalText,
  updateAdminClaimStatus,
} from '../claimsAdmin/adminClaimsApi'
import { useClaimsAdminAuth } from '../claimsAdmin/useClaimsAdminAuth'
import type { AdminClaimDetails, AdminClaimFile } from '../claimsAdmin/types'
import { ApiHttpError } from '../lib/api'

export function AdminClaimDetailPage() {
  const navigate = useNavigate()
  const { id } = useParams()
  const { logout } = useClaimsAdminAuth()
  const claimId = Number(id)

  const [claim, setClaim] = useState<AdminClaimDetails | null>(null)
  const [files, setFiles] = useState<AdminClaimFile[]>([])
  const [draftFinalText, setDraftFinalText] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isSavingFinalText, setIsSavingFinalText] = useState(false)
  const [isUpdatingStatus, setIsUpdatingStatus] = useState(false)
  const [isSending, setIsSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  useEffect(() => {
    if (!Number.isInteger(claimId) || claimId <= 0) {
      setError('Некорректный claim id.')
      setIsLoading(false)
      return
    }

    let isCancelled = false
    async function loadClaimDetails() {
      try {
        setIsLoading(true)
        setError(null)
        const [claimPayload, filesPayload] = await Promise.all([
          fetchAdminClaim(claimId),
          fetchAdminClaimFiles(claimId),
        ])
        if (isCancelled) {
          return
        }
        setClaim(claimPayload)
        setDraftFinalText(claimPayload.final_text || claimPayload.generated_full_text || '')
        setFiles(filesPayload)
      } catch (loadError) {
        if (isCancelled) {
          return
        }
        handleApiError(loadError, navigate)
        if (!(loadError instanceof ApiHttpError && loadError.status === 401)) {
          setError('Не удалось загрузить детали заявки.')
        }
      } finally {
        if (!isCancelled) {
          setIsLoading(false)
        }
      }
    }

    void loadClaimDetails()
    return () => {
      isCancelled = true
    }
  }, [claimId, navigate])

  async function onLogout() {
    await logout()
    navigate('/admin/login', { replace: true })
  }

  async function onMoveToInReview() {
    if (!claim) {
      return
    }
    setIsUpdatingStatus(true)
    setError(null)
    setSuccess(null)

    try {
      const updated = await updateAdminClaimStatus(claim.id, 'in_review')
      setClaim(updated)
      setSuccess('Статус обновлён на in_review.')
    } catch (updateError) {
      if (!handleApiError(updateError, navigate)) {
        setError('Не удалось обновить статус.')
      }
    } finally {
      setIsUpdatingStatus(false)
    }
  }

  async function onSaveFinalText(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!claim) {
      return
    }
    setIsSavingFinalText(true)
    setError(null)
    setSuccess(null)

    try {
      const updated = await updateAdminClaimFinalText(claim.id, draftFinalText)
      setClaim(updated)
      setDraftFinalText(updated.final_text)
      setSuccess('Финальный текст сохранён.')
    } catch (saveError) {
      if (!handleApiError(saveError, navigate)) {
        setError('Не удалось сохранить финальный текст.')
      }
    } finally {
      setIsSavingFinalText(false)
    }
  }

  async function onSendToClient() {
    if (!claim) {
      return
    }
    setIsSending(true)
    setError(null)
    setSuccess(null)
    try {
      const updated = await sendAdminClaimFinalResult(claim.id)
      setClaim(updated)
      setSuccess('Результат отправлен клиенту, sent_at зафиксирован.')
    } catch (sendError) {
      if (!handleApiError(sendError, navigate)) {
        setError('Не удалось отправить результат клиенту.')
      }
    } finally {
      setIsSending(false)
    }
  }

  if (isLoading) {
    return (
      <main className="admin-claims-page">
        <section className="admin-claims-shell">
          <p className="admin-claims-loading">Загружаем заявку...</p>
        </section>
      </main>
    )
  }

  return (
    <main className="admin-claims-page">
      <section className="admin-claims-shell">
        <header className="admin-claims-header">
          <div>
            <h1 className="admin-claims-header__title">Claim #{claim?.id ?? '—'}</h1>
            <p className="admin-claims-header__subtitle">
              Управление статусом и финальным текстом перед отправкой клиенту.
            </p>
          </div>
          <div className="admin-claims-header__actions">
            <Link className="button button--secondary" to="/admin/claims">
              К списку заявок
            </Link>
            <button className="button button--secondary" type="button" onClick={onLogout}>
              Выйти
            </button>
          </div>
        </header>

        {claim ? (
          <section className="admin-claim-detail-grid">
            <article className="admin-claim-panel">
              <h2>Параметры заявки</h2>
              <dl className="kv">
                <dt>Status</dt>
                <dd>{claim.status}</dd>
                <dt>Generation state</dt>
                <dd>{claim.generation_state}</dd>
                <dt>Case type</dt>
                <dd>{claim.case_type || '—'}</dd>
                <dt>Client email</dt>
                <dd>{claim.client_email || '—'}</dd>
                <dt>Client phone</dt>
                <dd>{claim.client_phone || '—'}</dd>
                <dt>Paid at</dt>
                <dd>{claim.paid_at || '—'}</dd>
                <dt>Reviewed at</dt>
                <dd>{claim.reviewed_at || '—'}</dd>
                <dt>Sent at</dt>
                <dd>{claim.sent_at || '—'}</dd>
              </dl>

              <h3>Исходный текст клиента</h3>
              <pre className="admin-claim-panel__pre">{claim.input_text}</pre>

              <h3>Preview</h3>
              <pre className="admin-claim-panel__pre">{claim.generated_preview_text || '—'}</pre>
            </article>

            <article className="admin-claim-panel">
              <h2>Финализация</h2>
              <form className="form" onSubmit={onSaveFinalText}>
                <label className="label" htmlFor="admin-final-text">
                  Final text
                </label>
                <textarea
                  id="admin-final-text"
                  className="admin-claim-panel__textarea"
                  value={draftFinalText}
                  onChange={(event) => setDraftFinalText(event.target.value)}
                  rows={18}
                />
                <button className="button" type="submit" disabled={isSavingFinalText}>
                  {isSavingFinalText ? 'Сохраняем...' : 'Сохранить final_text'}
                </button>
              </form>

              <div className="admin-claim-panel__actions">
                <button
                  className="button button--secondary"
                  type="button"
                  disabled={isUpdatingStatus || claim.status !== 'paid'}
                  onClick={onMoveToInReview}
                >
                  {isUpdatingStatus ? 'Обновляем...' : 'Перевести в in_review'}
                </button>

                <button
                  className="button"
                  type="button"
                  disabled={isSending || claim.status !== 'in_review'}
                  onClick={onSendToClient}
                >
                  {isSending ? 'Отправляем...' : 'Отправить клиенту'}
                </button>
              </div>

              <h3>Файлы</h3>
              <ul className="admin-claim-files">
                {files.length === 0 ? (
                  <li>Файлы не загружены.</li>
                ) : (
                  files.map((file) => (
                    <li key={file.id}>
                      <span>{file.filename}</span>
                      <small>{file.file_role}</small>
                    </li>
                  ))
                )}
              </ul>
            </article>
          </section>
        ) : null}

        {success ? <p className="message message--success">{success}</p> : null}
        {error ? <p className="message message--error">{error}</p> : null}
      </section>
    </main>
  )
}

function handleApiError(error: unknown, navigate: (path: string, options?: { replace?: boolean }) => void): boolean {
  if (!(error instanceof ApiHttpError)) {
    return false
  }

  if (error.status === 401) {
    navigate('/admin/login', { replace: true })
    return true
  }

  if (error.status === 403) {
    navigate('/admin/login', { replace: true })
    return true
  }

  return false
}

