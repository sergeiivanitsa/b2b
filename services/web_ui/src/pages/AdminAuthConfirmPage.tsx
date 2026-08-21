import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { useClaimsAdminAuth } from '../claimsAdmin/useClaimsAdminAuth'

export function AdminAuthConfirmPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { confirmToken } = useClaimsAdminAuth()
  const token = searchParams.get('token')?.trim() || ''
  const [statusText, setStatusText] = useState(() =>
    token ? 'Проверяем токен...' : 'Подтверждение недоступно',
  )
  const [error, setError] = useState<string | null>(() =>
    token ? null : 'Токен не найден в ссылке подтверждения.',
  )
  const isStartedRef = useRef(!token)

  useEffect(() => {
    if (isStartedRef.current) {
      return
    }
    isStartedRef.current = true

    if (!token) {
      return
    }

    ;(async () => {
      try {
        const nextStatus = await confirmToken(token)
        if (nextStatus === 'authenticated') {
          navigate('/admin/claims', { replace: true })
          return
        }
        if (nextStatus === 'forbidden') {
          setError('Доступ запрещён для этого email.')
          setStatusText('Подтверждение отклонено')
          return
        }
        setError('Сессия не создана, повторите вход.')
        setStatusText('Подтверждение не удалось')
      } catch {
        setError('Токен недействителен или срок его действия истёк.')
        setStatusText('Подтверждение не удалось')
      }
    })()
  }, [confirmToken, navigate, token])

  return (
    <main className="screen">
      <section className="card">
        <h1 className="card__title">Claims Admin Confirm</h1>
        <p className="card__subtitle">{statusText}</p>
        {error ? <p className="message message--error">{error}</p> : null}
        <p className="hint">
          <Link to="/admin/login">Вернуться к форме входа</Link>
        </p>
      </section>
    </main>
  )
}

