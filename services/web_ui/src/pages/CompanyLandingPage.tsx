import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ClaimsBrand } from '../claims/components/ClaimsBrand'
import { CompanyReportInnForm } from '../components/company-report/CompanyReportInnForm'

export function CompanyLandingPage() {
  const navigate = useNavigate()
  const [inn, setInn] = useState('')
  const [isNavigating, setIsNavigating] = useState(false)
  const transitionStarted = useRef(false)

  function openCompany(targetInn: string) {
    if (transitionStarted.current) return
    transitionStarted.current = true
    setIsNavigating(true)
    navigate(`/company/${targetInn}`)
  }

  return (
    <main className="company-entry-page">
      <header className="company-entry-header">
        <ClaimsBrand compact />
        <nav aria-label="Основная навигация">
          <a href="#company-entry-benefits">Возможности</a>
          <a href="#company-entry-check">Проверить компанию</a>
          <Link to="/claims">Взыскание</Link>
          <Link to="/login">Войти</Link>
        </nav>
        <CompanyReportInnForm id="company-entry-header-inn" value={inn} onChange={setInn} onSubmit={openCompany} disabled={isNavigating} compact />
      </header>

      <section className="company-entry-hero" aria-labelledby="company-entry-title">
        <div>
          <p className="company-entry-eyebrow">CompanyReport</p>
          <h1 id="company-entry-title">Проверьте контрагента перед важной сделкой</h1>
          <p>Откройте доступные сведения о компании по ИНН и перейдите к взысканию, когда это необходимо.</p>
          <ul id="company-entry-benefits" className="company-entry-benefits">
            <li>Реквизиты компании</li>
            <li>Финансовые показатели</li>
            <li>Арбитражные сведения</li>
            <li>Следующий шаг к взысканию</li>
          </ul>
        </div>
        <section id="company-entry-check" className="company-entry-check-card" aria-label="Проверка компании по ИНН">
          <h2>Проверить компанию</h2>
          <CompanyReportInnForm id="company-entry-hero-inn" value={inn} onChange={setInn} onSubmit={openCompany} disabled={isNavigating} />
        </section>
      </section>
    </main>
  )
}
