export type CompanyReportLabVariant = 'h1' | 'h2' | 'h3'
export type CompanyReportLabView = 'main' | 'legal' | 'profile'
export type CompanyReportLabScenario = 'reference' | 'deal' | 'prepayment' | 'debt'
export type DatasetCoverage = 'obtained' | 'partial_slice' | 'not_requested'

export type CompanyReportLabSnapshot = {
  readonly reportId: string
  readonly generatedAt: string
  readonly generatedLabel: string
  readonly receivedLabel: string
  readonly sourceLabel: string
  readonly identity: {
    readonly shortName: string
    readonly fullName: string
    readonly inn: string
    readonly ogrn: string
    readonly kpp: string
    readonly statusCode: string
    readonly statusLabel: string
    readonly registrationDate: string
    readonly registrationLabel: string
    readonly legalForm: string
    readonly addressCoverage: DatasetCoverage
    readonly managersCoverage: DatasetCoverage
  }
  readonly completeness: {
    readonly availableRequiredDatasets: number
    readonly requiredDatasets: number
    readonly scopeNote: string
  }
  readonly taxation: {
    readonly commonMode: boolean
    readonly publicationDate: string
    readonly publicationLabel: string
  }
  readonly finance: {
    readonly coverage: DatasetCoverage
    readonly firstYear: number
    readonly lastYear: number
    readonly unit: 'provider_units_unknown'
    readonly changes: readonly {
      readonly id: 'revenue' | 'assets' | 'accounts_payable' | 'loss_magnitude'
      readonly label: string
      readonly value: string
      readonly explanation: string
    }[]
    readonly limitation: string
  }
  readonly arbitration: {
    readonly coverage: DatasetCoverage
    readonly totalCases: number
    readonly returnedCases: number
    readonly roles: readonly { readonly label: string; readonly count: number }[]
    readonly statuses: readonly { readonly label: string; readonly count: number }[]
    readonly results: readonly { readonly label: string; readonly count: number }[]
    readonly limitation: string
  }
  readonly datasets: readonly {
    readonly id: 'counterparty' | 'finance' | 'arbitration' | 'taxation' | 'address' | 'managers' | 'enforcement' | 'bankruptcy'
    readonly label: string
    readonly coverage: DatasetCoverage
    readonly answer: string
    readonly source: string
  }[]
}

type DeepReadonly<T> = T extends (...args: never[]) => unknown
  ? T
  : T extends readonly (infer Item)[]
    ? readonly DeepReadonly<Item>[]
    : T extends object
      ? { readonly [Key in keyof T]: DeepReadonly<T[Key]> }
      : T

function deepFreeze<T extends object>(value: T): DeepReadonly<T> {
  for (const nested of Object.values(value)) {
    if (nested && typeof nested === 'object' && !Object.isFrozen(nested)) {
      deepFreeze(nested)
    }
  }
  return Object.freeze(value) as DeepReadonly<T>
}

export const YANDEX_LAB_COMPANY_KEY = '7736207543-ooo-yandeks'

export const COMPANY_REPORT_LAB_VARIANTS: readonly CompanyReportLabVariant[] = Object.freeze(['h1', 'h2', 'h3'])

export const YANDEX_LAB_SNAPSHOT: DeepReadonly<CompanyReportLabSnapshot> = deepFreeze({
  reportId: '09d9a067-27b2-4ea1-93ca-082708c90c01',
  generatedAt: '2026-08-09T22:02:25.322213Z',
  generatedLabel: '10 августа 2026, 08:02 (UTC+10)',
  receivedLabel: '10 августа 2026, 08:02 (UTC+10)',
  sourceLabel: 'DataNewton через CompanyReport',
  identity: {
    shortName: 'ООО «ЯНДЕКС»',
    fullName: 'Общество с ограниченной ответственностью «ЯНДЕКС»',
    inn: '7736207543',
    ogrn: '1027700229193',
    kpp: '770401001',
    statusCode: '001',
    statusLabel: 'Действует',
    registrationDate: '2000-09-14',
    registrationLabel: '14 сентября 2000',
    legalForm: 'Общество с ограниченной ответственностью',
    addressCoverage: 'not_requested',
    managersCoverage: 'not_requested',
  },
  completeness: {
    availableRequiredDatasets: 3,
    requiredDatasets: 3,
    scopeNote: 'Получены ответы по 3 из 3 обязательных наборов именно этого отчёта. Это показатель состава снимка, а не характеристика компании.',
  },
  taxation: {
    commonMode: true,
    publicationDate: '2025-12-31',
    publicationLabel: '31 декабря 2025',
  },
  finance: {
    coverage: 'obtained',
    firstYear: 2011,
    lastYear: 2024,
    unit: 'provider_units_unknown',
    changes: [
      { id: 'revenue', label: 'Выручка', value: '+29,1%', explanation: 'Изменение 2024 года к 2023 году.' },
      { id: 'assets', label: 'Активы', value: '+26,2%', explanation: 'Изменение 2024 года к 2023 году.' },
      { id: 'accounts_payable', label: 'Кредиторская задолженность', value: '+25,3%', explanation: 'Изменение 2024 года к 2023 году.' },
      { id: 'loss_magnitude', label: 'Модуль чистого убытка', value: '−80,0%', explanation: 'Чистый результат отрицательный в 2023 и 2024 годах; показано изменение модуля убытка.' },
    ],
    limitation: 'Поставщик не закрепил единицу измерения в доступном контракте. Поэтому абсолютные финансовые значения не публикуются. При обработке также обнаружены пропуски кодовых показателей и конфликт дублирующей записи; на странице оставлены только воспроизводимые сравнения.',
  },
  arbitration: {
    coverage: 'partial_slice',
    totalCases: 1448,
    returnedCases: 100,
    roles: [
      { label: 'Ответчик', count: 53 },
      { label: 'Истец', count: 16 },
      { label: 'Заявитель', count: 3 },
      { label: 'Кредитор', count: 1 },
      { label: 'Иная роль', count: 27 },
    ],
    statuses: [
      { label: 'Открыто', count: 97 },
      { label: 'Завершено', count: 3 },
    ],
    results: [
      { label: 'Иной результат', count: 64 },
      { label: 'Отказано', count: 8 },
      { label: 'Возвращено', count: 13 },
      { label: 'Удовлетворено полностью', count: 9 },
      { label: 'Не определено', count: 6 },
    ],
    limitation: 'Источник сообщил 1 448 дел, но передал для разбора 100 записей. Распределения относятся только к этой выборке, не складываются с общим числом дел и не описывают всю судебную историю. Суммы требований не показаны: выборка неполная, а обозначение валюты не закреплено в контракте.',
  },
  datasets: [
    { id: 'counterparty', label: 'Регистрационные сведения', coverage: 'obtained', answer: 'Получены наименование, ИНН, ОГРН, КПП, правовая форма, статус и дата регистрации.', source: 'counterparty' },
    { id: 'finance', label: 'Финансовая отчётность', coverage: 'obtained', answer: 'Получены периоды 2011–2024. Для показа используются только сопоставимые изменения.', source: 'finance' },
    { id: 'arbitration', label: 'Арбитраж', coverage: 'partial_slice', answer: 'Из 1 448 найденных дел для детального разбора передано 100 записей.', source: 'arbitration' },
    { id: 'taxation', label: 'Налоговый режим', coverage: 'obtained', answer: 'В регистрационном наборе получен признак общего режима с датой публикации 31 декабря 2025.', source: 'counterparty' },
    { id: 'address', label: 'Адрес', coverage: 'not_requested', answer: 'Поле не запрашивалось в этом снимке; отсутствие значения не означает отсутствие адреса.', source: 'counterparty' },
    { id: 'managers', label: 'Руководители', coverage: 'not_requested', answer: 'Поле не запрашивалось в этом снимке; отсутствие списка не означает отсутствие руководителя.', source: 'counterparty' },
    { id: 'enforcement', label: 'Исполнительные производства', coverage: 'not_requested', answer: 'Набор не входит в текущий контракт снимка; страница не делает вывода о наличии или отсутствии событий.', source: 'не предоставлен' },
    { id: 'bankruptcy', label: 'Банкротные сообщения', coverage: 'not_requested', answer: 'Набор не входит в текущий контракт снимка; страница не делает вывода о наличии или отсутствии событий.', source: 'не предоставлен' },
  ],
} satisfies CompanyReportLabSnapshot)

export const DATASET_COVERAGE_LABELS: Readonly<Record<DatasetCoverage, string>> = Object.freeze({
  obtained: 'Получено',
  partial_slice: 'Частичная выборка',
  not_requested: 'Не запрашивалось',
})

export function parseCompanyReportLabVariant(value: string | undefined): CompanyReportLabVariant | null {
  return value === 'h1' || value === 'h2' || value === 'h3' ? value : null
}

export function isYandexLabCompanyKey(value: string | undefined): boolean {
  return value === YANDEX_LAB_COMPANY_KEY
}

export function resolveCompanyReportLabView(
  variant: CompanyReportLabVariant,
  companyKey: string,
  pathname: string,
): CompanyReportLabView | null {
  const parts = pathname.replace(/\/+$/, '').split('/').filter(Boolean)
  if (parts.length < 3 || parts[0] !== 'company-lab' || parts[1] !== variant || parts[2] !== companyKey) return null
  if (parts.length === 3) return 'main'
  if (parts.length !== 4) return null
  if (variant === 'h2' && parts[3] === 'legal') return 'legal'
  if (variant === 'h3' && parts[3] === 'profile') return 'profile'
  return null
}

export function companyReportLabPath(variant: CompanyReportLabVariant, view: CompanyReportLabView = 'main'): string {
  const base = `/company-lab/${variant}/${YANDEX_LAB_COMPANY_KEY}`
  if (variant === 'h2' && view === 'legal') return `${base}/legal`
  if (variant === 'h3' && view === 'profile') return `${base}/profile`
  return base
}

export function scenarioAction(variant: CompanyReportLabVariant, scenario: CompanyReportLabScenario): { readonly label: string; readonly detail: string; readonly href: string } {
  if (scenario === 'deal') {
    if (variant === 'h2') return { label: 'Открыть судебную выборку', detail: 'Сверьте роль компании и границы выборки до согласования условий сделки.', href: companyReportLabPath('h2', 'legal') }
    if (variant === 'h3') return { label: 'Проверить матрицу данных', detail: 'Сначала отделите полученные факты от частичных и незапрошенных данных.', href: '#evidence-matrix' }
    return { label: 'Перейти к арбитражу', detail: 'Сверьте роль компании и границы выборки до согласования условий сделки.', href: '#arbitration' }
  }
  if (scenario === 'prepayment') {
    if (variant === 'h2') return { label: 'Открыть финансовую сводку', detail: 'Сопоставимая динамика остаётся внутри обзора компании.', href: '#h2-finance' }
    if (variant === 'h3') return { label: 'Открыть финансовое наблюдение', detail: 'Проверьте факт и его ограничение перед фиксацией условий предоплаты.', href: '#evidence-findings' }
    return { label: 'Открыть финансовую динамику', detail: 'Сверьте период и ограничение финансового блока перед фиксацией условий предоплаты.', href: '#finance' }
  }
  if (scenario === 'debt') return { label: 'Проверить должника и подготовить претензию', detail: 'Перейдите в отдельный сценарий взыскания с уже заполненными реквизитами компании.', href: `/claims?report_id=${YANDEX_LAB_SNAPSHOT.reportId}` }
  return { label: 'Перейти к реквизитам', detail: 'Сверьте ИНН, ОГРН, КПП и статус юридического лица.', href: '#identity' }
}
