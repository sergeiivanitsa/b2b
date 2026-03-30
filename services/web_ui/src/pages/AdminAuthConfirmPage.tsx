import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { useClaimsAdminAuth } from '../claimsAdmin/useClaimsAdminAuth'

export function AdminAuthConfirmPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { confirmToken } = useClaimsAdminAuth()
  const [statusText, setStatusText] = useState('Проверяем токен...')
  const [error, setError] = useState<string | null>(null)
  const isStartedRef = useRef(false)

  useEffect(() => {
    if (isStartedRef.current) {
      return
    }
    isStartedRef.current = true

    const token = searchParams.get('token')?.trim() || ''
    if (!token) {
      setError('Токен не найден в ссылке подтверждения.')
      setStatusText('Подтверждение недоступно')
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
  }, [confirmToken, navigate, searchParams])

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

