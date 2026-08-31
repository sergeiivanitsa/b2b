import { useEffect } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'

import { CompanyReportLab } from '../components/company-report/CompanyReportLab'
import {
  YANDEX_LAB_COMPANY_KEY,
  companyReportLabPath,
  isYandexLabCompanyKey,
  parseCompanyReportLabVariant,
  resolveCompanyReportLabView,
  type CompanyReportLabVariant,
  type CompanyReportLabView,
} from '../companyReport/companyReportLabData'

export function CompanyReportLabPage() {
  const { variant: variantParam, companyKey } = useParams<{ variant: string; companyKey: string; section?: string }>()
  const location = useLocation()
  const variant = parseCompanyReportLabVariant(variantParam)
  const view = variant && companyKey && isYandexLabCompanyKey(companyKey)
    ? resolveCompanyReportLabView(variant, companyKey, location.pathname)
    : null
  const isValid = variant !== null && view !== null && isYandexLabCompanyKey(companyKey)
  const title = isValid ? labDocumentTitle(variant, view) : 'Прототип CompanyReport недоступен'

  useLabDocumentMetadata(title)

  if (!isValid) return <InvalidLabPage />
  return <CompanyReportLab variant={variant} view={view} />
}

function InvalidLabPage() {
  return (
    <div className="cr-lab cr-lab--invalid">
      <main id="cr-lab-content" className="cr-lab__main">
        <section className="cr-lab__section" aria-labelledby="cr-lab-invalid-title">
          <p className="cr-lab__eyebrow">Исследовательский прототип</p>
          <h1 id="cr-lab-invalid-title">Этот вариант страницы недоступен</h1>
          <p>В лаборатории доступны три зафиксированные архитектуры для компании с ИНН 7736207543. Адрес не используется как публичная страница и не индексируется.</p>
          <p><Link className="cr-lab__primary-action" to={companyReportLabPath('h1')}>Открыть первый вариант</Link></p>
        </section>
      </main>
    </div>
  )
}

function labDocumentTitle(variant: CompanyReportLabVariant, view: CompanyReportLabView): string {
  if (variant === 'h1') return 'ООО «ЯНДЕКС»: реквизиты, финансы и арбитраж | CompanyReport'
  if (variant === 'h2' && view === 'legal') return 'Арбитражные дела ООО «ЯНДЕКС» | CompanyReport'
  if (variant === 'h2') return 'ООО «ЯНДЕКС»: досье компании | CompanyReport'
  if (view === 'profile') return 'ООО «ЯНДЕКС»: профиль юридического лица | CompanyReport'
  return 'Проверка ООО «ЯНДЕКС»: подтверждённые данные | CompanyReport'
}

function useLabDocumentMetadata(title: string) {
  useEffect(() => {
    const previousTitle = document.title
    const previousLang = document.documentElement.getAttribute('lang')
    const existingRobots = document.head.querySelector<HTMLMetaElement>('meta[name="robots"]')
    const robots = existingRobots ?? document.createElement('meta')
    const previousRobotsContent = existingRobots?.getAttribute('content') ?? null

    if (!existingRobots) {
      robots.name = 'robots'
      document.head.append(robots)
    }
    document.title = title
    document.documentElement.lang = 'ru'
    robots.content = 'noindex,nofollow'

    return () => {
      document.title = previousTitle
      if (previousLang === null) {
        document.documentElement.removeAttribute('lang')
      } else {
        document.documentElement.lang = previousLang
      }
      if (!existingRobots) {
        robots.remove()
      } else if (previousRobotsContent === null) {
        existingRobots.removeAttribute('content')
      } else {
        existingRobots.content = previousRobotsContent
      }
    }
  }, [title])
}

export const COMPANY_REPORT_LAB_CANONICAL_KEY = YANDEX_LAB_COMPANY_KEY
