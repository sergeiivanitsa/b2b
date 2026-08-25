import { useRef, useState } from 'react'

import { CompanyReportInnForm } from '../components/company-report/CompanyReportInnForm'
import { navigateToCompany } from './companyLandingNavigation'

export function CompanyLandingPage() {
  const [inn, setInn] = useState('')
  const [isNavigating, setIsNavigating] = useState(false)
  const transitionStarted = useRef(false)

  function openCompany(targetInn: string) {
    if (transitionStarted.current) return
    transitionStarted.current = true
    setIsNavigating(true)
    navigateToCompany(targetInn)
  }

  return (
    <main className="company-entry-page">
      <header className="company-entry-header">
        <div className="company-entry-brand" aria-label="Взыскание дебиторки">
          <span>ВЗЫСКАНИЕ ДЕБИТОРКИ</span>
          <small>Правовой офис по работе с контрагентами</small>
        </div>
        <nav aria-label="Основная навигация">
          <span>Как работаем</span>
          <span>Оплата</span>
          <span>Кейсы</span>
          <span>FAQ</span>
        </nav>
        <CompanyReportInnForm
          id="company-entry-header-inn"
          value={inn}
          onChange={setInn}
          onSubmit={openCompany}
          disabled={isNavigating}
          compact
          placeholder="ИНН"
          submitLabel="Проверить должника"
        />
      </header>

      <section className="company-entry-hero" aria-labelledby="company-entry-title">
        <div className="company-entry-hero__content">
          <h1 id="company-entry-title"><strong>Вернем дебиторскую задолженность под ключ</strong>{' '}<span>— с оплатой наших услуг по факту взыскания</span></h1>
          <p className="company-entry-hero__description">Проверим документы и должника, оценим шансы получить реальные деньги, подготовим претензию, иск, сопроводим суд и действия после решения.</p>
          <ul id="company-entry-benefits" className="company-entry-benefits">
            <li>Работаем без предоплаты</li>
            <li>Взыскание под ключ</li>
            <li>Ежедневное обновление статуса</li>
            <li>Гонорар взыщем с должника</li>
          </ul>
        </div>
        <section id="company-entry-check" className="company-entry-check-card" aria-label="Проверка должника по ИНН">
          <p className="company-entry-check-card__eyebrow">НАЧНИТЕ С ПРОВЕРКИ</p>
          <h2>Оцените платежеспособность должника</h2>
          <p className="company-entry-check-card__description">Проверим должника по 6 направлениям: финансы, суды, ФССП, банкротство, деятельность, имущество и скажем: что делать дальше?</p>
          <CompanyReportInnForm
            id="company-entry-hero-inn"
            value={inn}
            onChange={setInn}
            onSubmit={openCompany}
            disabled={isNavigating}
            variant="card"
            placeholder="Введите ИНН должника"
            submitLabel="Запустить проверку"
          />
          <p className="company-entry-check-card__reassurance">За 3 минуты соберём сведения о должнике, проанализируем и подготовим отчёт с оценкой рисков и рекомендациями по дальнейшим действиям</p>
        </section>
      </section>
    </main>
  )
}
