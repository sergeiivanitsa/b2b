import { useState } from 'react'
import { Link } from 'react-router-dom'

import {
  COMPANY_REPORT_LAB_VARIANTS,
  DATASET_COVERAGE_LABELS,
  YANDEX_LAB_SNAPSHOT,
  companyReportLabPath,
  scenarioAction,
  type CompanyReportLabScenario,
  type CompanyReportLabVariant,
  type CompanyReportLabView,
  type DatasetCoverage,
} from '../../companyReport/companyReportLabData'
import './companyReportLab.css'

type Props = {
  readonly variant: CompanyReportLabVariant
  readonly view: CompanyReportLabView
}

const variantNames: Readonly<Record<CompanyReportLabVariant, string>> = {
  h1: 'Единая карточка',
  h2: 'Модульное досье',
  h3: 'Доказательная проверка',
}

export function CompanyReportLab({ variant, view }: Props) {
  return (
    <div className={`cr-lab cr-lab--${variant}`} data-variant={variant}>
      <a className="cr-lab__skip" href="#cr-lab-content">Перейти к содержанию</a>
      <LabHeader variant={variant} />
      {variant === 'h1' ? <UnifiedDossier /> : null}
      {variant === 'h2' && view === 'main' ? <ModularHub /> : null}
      {variant === 'h2' && view === 'legal' ? <LegalDetail /> : null}
      {variant === 'h3' && view === 'main' ? <EvidenceCheck /> : null}
      {variant === 'h3' && view === 'profile' ? <ReferenceProfile /> : null}
      <LabFooter />
    </div>
  )
}

function LabHeader({ variant }: { readonly variant: CompanyReportLabVariant }) {
  return (
    <header className="cr-lab__topbar">
      <Link className="cr-lab__brand" to={companyReportLabPath(variant)} aria-label="CompanyReport — к началу варианта">
        <span>COMPANY</span><strong>REPORT</strong>
      </Link>
      <nav className="cr-lab__variant-switch" aria-label="Варианты страницы">
        {COMPANY_REPORT_LAB_VARIANTS.map((item) => (
          <Link key={item} to={companyReportLabPath(item)} aria-current={item === variant ? 'page' : undefined}>
            <span>{item.toUpperCase()}</span>{variantNames[item]}
          </Link>
        ))}
      </nav>
      <p className="cr-lab__prototype-mark">Прототип · данные снимка</p>
    </header>
  )
}

function UnifiedDossier() {
  const data = YANDEX_LAB_SNAPSHOT
  return (
    <main id="cr-lab-content" className="cr-lab__main cr-lab-h1">
      <section className="cr-lab-h1__hero" aria-labelledby="cr-lab-h1-title">
        <div className="cr-lab-h1__hero-copy">
          <p className="cr-lab__eyebrow">Карточка юридического лица</p>
          <h1 id="cr-lab-h1-title">ООО «ЯНДЕКС»: реквизиты, финансы и арбитраж</h1>
          <p className="cr-lab__lead">Компания идентифицирована по ИНН {data.identity.inn}. Статус в полученном снимке — «{data.identity.statusLabel}». Ниже собраны регистрационные сведения, сопоставимая финансовая динамика и ограниченная судебная выборка.</p>
          <IdentityTokens />
        </div>
        <aside className="cr-lab-h1__snapshot" aria-label="Состояние снимка">
          <p className="cr-lab-h1__snapshot-label">Снимок сформирован</p>
          <strong>{data.generatedLabel}</strong>
          <span>{data.completeness.availableRequiredDatasets} из {data.completeness.requiredDatasets} обязательных наборов отчёта получены</span>
          <p>{data.completeness.scopeNote}</p>
        </aside>
      </section>

      <nav className="cr-lab-h1__contents" aria-label="Разделы единой карточки">
        <a href="#identity">Реквизиты</a>
        <a href="#finance">Финансовая динамика</a>
        <a href="#arbitration">Арбитраж</a>
        <a href="#sources">Источники</a>
        <a href="#next">Следующий шаг</a>
      </nav>

      <section className="cr-lab-h1__answer" aria-labelledby="h1-answer-title">
        <div>
          <p className="cr-lab__kicker">Короткий ответ</p>
          <h2 id="h1-answer-title">Что известно о компании на дату снимка</h2>
        </div>
        <p><strong>{data.identity.shortName}</strong> зарегистрировано {data.identity.registrationLabel}, имеет статус «{data.identity.statusLabel}». В финансовых данных за 2024 год выручка выросла на 29,1% к 2023 году. В арбитражном наборе указано 1 448 дел, но подробно переданы только 100 записей — распределения ниже относятся к этой частичной выборке.</p>
      </section>

      <div className="cr-lab-h1__layout">
        <div className="cr-lab-h1__flow">
          <section id="identity" className="cr-lab__section" aria-labelledby="h1-identity-title">
            <SectionHeading index="01" title="Реквизиты и точная идентификация" id="h1-identity-title" />
            <IdentityDefinitionList />
            <SourceLine dataset="counterparty" />
          </section>

          <section id="finance" className="cr-lab__section" aria-labelledby="h1-finance-title">
            <SectionHeading index="02" title="Финансовая динамика" id="h1-finance-title" />
            <p className="cr-lab__section-intro">Доступны периоды {data.finance.firstYear}–{data.finance.lastYear}. Абсолютные значения скрыты: единица измерения не закреплена в доступном контракте данных.</p>
            <FinanceChanges />
            <Limitation>{data.finance.limitation}</Limitation>
            <SourceLine dataset="finance" period="2023–2024 для сравнений" />
          </section>

          <section id="arbitration" className="cr-lab__section" aria-labelledby="h1-arbitration-title">
            <SectionHeading index="03" title="Суды и арбитраж" id="h1-arbitration-title" />
            <ArbitrationOverview />
            <Limitation>{data.arbitration.limitation}</Limitation>
            <SourceLine dataset="arbitration" />
          </section>

          <TaxSection id="h1-tax" headingId="h1-tax-title" index="04" />
          <SourcesSection />
          <ScenarioNextStep variant="h1" />
        </div>

        <aside className="cr-lab-h1__aside" aria-label="Опорные факты">
          <p className="cr-lab__kicker">Опорные факты</p>
          <dl>
            <div><dt>Статус</dt><dd>{data.identity.statusLabel}</dd></div>
            <div><dt>Дата регистрации</dt><dd>{data.identity.registrationLabel}</dd></div>
            <div><dt>Финансовый период</dt><dd>{data.finance.firstYear}–{data.finance.lastYear}</dd></div>
            <div><dt>Дел указано источником</dt><dd>{formatCount(data.arbitration.totalCases)}</dd></div>
            <div><dt>Детально передано</dt><dd>{data.arbitration.returnedCases}</dd></div>
          </dl>
          <p>Каждый вывод следует читать вместе с периодом, источником и ограничением блока.</p>
        </aside>
      </div>
    </main>
  )
}

function ModularHub() {
  const data = YANDEX_LAB_SNAPSHOT
  return (
    <main id="cr-lab-content" className="cr-lab__main cr-lab-h2">
      <nav className="cr-lab__breadcrumbs" aria-label="Хлебные крошки"><span>Компании</span><span aria-hidden="true">/</span><strong>{data.identity.shortName}</strong></nav>
      <section className="cr-lab-h2__hero" aria-labelledby="cr-lab-h2-title">
        <div>
          <p className="cr-lab__eyebrow">Модульное досье</p>
          <h1 id="cr-lab-h2-title">ООО «ЯНДЕКС»: досье компании</h1>
          <p className="cr-lab__lead">Быстрый профиль юридического лица и отдельные документы только для тем, где данных достаточно для самостоятельного ответа.</p>
        </div>
        <div className="cr-lab-h2__status-card">
          <span>Статус в снимке</span><strong>{data.identity.statusLabel}</strong>
          <small>Код {data.identity.statusCode} · обновлено {data.generatedLabel}</small>
        </div>
      </section>

      <section className="cr-lab-h2__identity" aria-labelledby="h2-identity-title" id="identity">
        <div><p className="cr-lab__kicker">Идентификация</p><h2 id="h2-identity-title">{data.identity.fullName}</h2></div>
        <IdentityTokens />
        <SourceLine dataset="counterparty" />
      </section>

      <section className="cr-lab-h2__modules" aria-labelledby="h2-modules-title">
        <div className="cr-lab-h2__modules-heading">
          <div><p className="cr-lab__kicker">Документы досье</p><h2 id="h2-modules-title">Выберите нужный контекст</h2></div>
          <p>Отдельный адрес появляется только у темы с достаточным объёмом уникальных фактов.</p>
        </div>
        <div className="cr-lab-h2__module-grid">
          <article className="cr-lab-h2__module cr-lab-h2__module--wide">
            <span className="cr-lab-h2__module-index">01</span>
            <p className="cr-lab__kicker">Самостоятельный документ</p>
            <h3>Суды и арбитраж</h3>
            <p>Доступен отдельный документ с ролями, статусами, результатами и явным описанием границ судебной выборки.</p>
            <Link to={companyReportLabPath('h2', 'legal')}>Открыть судебную выборку <span aria-hidden="true">→</span></Link>
          </article>
          <article className="cr-lab-h2__module" id="h2-finance">
            <span className="cr-lab-h2__module-index">02</span>
            <p className="cr-lab__kicker">В составе досье</p>
            <h3>Финансовая динамика</h3>
            <p><strong>+29,1%</strong> — изменение выручки в 2024 году к 2023 году.</p>
            <p className="cr-lab__muted">Краткая сопоставимая динамика остаётся в обзоре компании; отдельного финансового документа в этом варианте нет.</p>
          </article>
          <article className="cr-lab-h2__module">
            <span className="cr-lab-h2__module-index">03</span>
            <p className="cr-lab__kicker">В составе досье</p>
            <h3>Реквизиты</h3>
            <p>ИНН {data.identity.inn}, ОГРН {data.identity.ogrn}, КПП {data.identity.kpp}.</p>
            <a href="#h2-details">Сверить регистрационные данные <span aria-hidden="true">↓</span></a>
          </article>
        </div>
      </section>

      <section id="h2-details" className="cr-lab-h2__facts" aria-labelledby="h2-details-title">
        <div>
          <p className="cr-lab__kicker">Сводка</p>
          <h2 id="h2-details-title">Регистрационные и финансовые факты</h2>
          <IdentityDefinitionList />
        </div>
        <div>
          <FinanceChanges compact />
          <Limitation>{data.finance.limitation}</Limitation>
        </div>
      </section>
      <SourcesSection compact />
      <ScenarioNextStep variant="h2" />
    </main>
  )
}

function LegalDetail() {
  const data = YANDEX_LAB_SNAPSHOT
  return (
    <main id="cr-lab-content" className="cr-lab__main cr-lab-h2 cr-lab-h2--detail">
      <nav className="cr-lab__breadcrumbs" aria-label="Хлебные крошки">
        <span>Компании</span><span aria-hidden="true">/</span><Link to={companyReportLabPath('h2')}>{data.identity.shortName}</Link><span aria-hidden="true">/</span><strong>Арбитраж</strong>
      </nav>
      <section className="cr-lab-h2__detail-hero" aria-labelledby="cr-lab-h2-legal-title">
        <div>
          <p className="cr-lab__eyebrow">Отдельный документ досье</p>
          <h1 id="cr-lab-h2-legal-title">Арбитражные дела ООО «ЯНДЕКС»</h1>
          <p className="cr-lab-h2__entity-context">
            ООО «ЯНДЕКС», ИНН {data.identity.inn} · снимок от {data.generatedLabel}
          </p>
          <p className="cr-lab__lead">Источник указывает 1 448 дел. Для структурного анализа переданы 100 записей, поэтому распределения на странице описывают только эту выборку.</p>
        </div>
        <div className="cr-lab-h2__legal-number"><strong>{formatCount(data.arbitration.totalCases)}</strong><span>дел указано источником</span><small>{data.arbitration.returnedCases} записей получено детально</small></div>
      </section>
      <section className="cr-lab-h2__direct-answer" aria-labelledby="h2-legal-answer">
        <div className="cr-lab-h2__direct-question">
          <p className="cr-lab__kicker">Прямой ответ</p>
          <h2 id="h2-legal-answer">В какой роли компания участвует в переданной выборке?</h2>
        </div>
        <div className="cr-lab-h2__direct-result">
          <p>Для ООО «ЯНДЕКС», ИНН {data.identity.inn}, в 53 из 100 полученных записей указана роль ответчика, в 16 — истца, в 3 — заявителя, в 1 — кредитора. Ещё в 27 записях указана иная роль. Это не распределение по всем 1 448 делам.</p>
          <SourceLine dataset="arbitration" />
        </div>
      </section>
      <section className="cr-lab-h2__legal-grid" aria-label="Разбор судебной выборки">
        <MetricTable title="Роли компании" rows={data.arbitration.roles} />
        <MetricTable title="Статусы записей" rows={data.arbitration.statuses} />
        <MetricTable title="Результаты" rows={data.arbitration.results} />
      </section>
      <section className="cr-lab__section" aria-labelledby="h2-legal-method">
        <SectionHeading index="Метод" title="Как читать выборку" id="h2-legal-method" />
        <ol className="cr-lab__steps">
          <li><strong>Сначала общий объём.</strong><span>1 448 — число, сообщённое источником для компании.</span></li>
          <li><strong>Затем граница выборки.</strong><span>Роли, статусы и результаты рассчитаны по 100 полученным записям.</span></li>
          <li><strong>После — контекст дела.</strong><span>Сам факт участия не объясняет предмет спора и сам по себе не характеризует компанию.</span></li>
        </ol>
        <Limitation>{data.arbitration.limitation}</Limitation>
        <SourceLine dataset="arbitration" />
      </section>
      <p className="cr-lab__back"><Link to={companyReportLabPath('h2')}>← Вернуться к досье компании</Link></p>
    </main>
  )
}

function EvidenceCheck() {
  const data = YANDEX_LAB_SNAPSHOT
  return (
    <main id="cr-lab-content" className="cr-lab__main cr-lab-h3">
      <section className="cr-lab-h3__hero" aria-labelledby="cr-lab-h3-title">
        <div className="cr-lab-h3__hero-top">
          <p className="cr-lab__eyebrow">Проверка по воспроизводимым фактам</p>
          <Link to={companyReportLabPath('h3', 'profile')}>Открыть справочный профиль</Link>
        </div>
        <h1 id="cr-lab-h3-title">Проверка ООО «ЯНДЕКС»: что подтверждают данные</h1>
        <p className="cr-lab__lead">Страница отделяет полученные факты, частичные выборки и поля, которые не запрашивались. Пустое значение никогда не заменяется нулём и не становится положительным или отрицательным выводом.</p>
        <div className="cr-lab-h3__identity-bar" id="identity">
          <div><span>ИНН</span><strong>{data.identity.inn}</strong></div>
          <div><span>ОГРН</span><strong>{data.identity.ogrn}</strong></div>
          <div><span>Статус в снимке</span><strong>{data.identity.statusLabel}</strong></div>
          <div><span>Обновлено</span><strong>{data.generatedLabel}</strong></div>
        </div>
      </section>

      <section id="evidence-matrix" className="cr-lab-h3__matrix-section" aria-labelledby="h3-matrix-title">
        <div className="cr-lab-h3__section-heading">
          <div><p className="cr-lab__kicker">Матрица доказательств</p><h2 id="h3-matrix-title">Что действительно есть в снимке</h2></div>
          <p>{data.completeness.scopeNote}</p>
        </div>
        <div
          className="cr-lab-h3__matrix-wrap"
          role="region"
          aria-label="Матрица доказательств по направлениям"
          tabIndex={0}
        >
          <table className="cr-lab-h3__matrix">
            <thead><tr><th scope="col">Область</th><th scope="col">Покрытие</th><th scope="col">Подтверждённый ответ</th><th scope="col">Основание</th></tr></thead>
            <tbody>{data.datasets.map((dataset) => (
              <tr key={dataset.id}>
                <th scope="row">{dataset.label}</th>
                <td><CoverageBadge coverage={dataset.coverage} /></td>
                <td>{dataset.answer}</td>
                <td>
                  <span className="cr-lab__source-code">{dataset.source}</span>
                  <small>
                    {dataset.coverage === 'not_requested'
                      ? `Состояние контракта на ${data.generatedLabel}`
                      : `Получено ${data.receivedLabel}`}
                  </small>
                </td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </section>

      <section id="evidence-findings" className="cr-lab-h3__findings" aria-labelledby="h3-findings-title">
        <div className="cr-lab-h3__section-heading"><div><p className="cr-lab__kicker">Проверяемые наблюдения</p><h2 id="h3-findings-title">Факты, которые можно использовать дальше</h2></div></div>
        <div className="cr-lab-h3__finding-grid">
          <article><span>Регистрация</span><strong>{data.identity.statusLabel}</strong><p>{data.identity.fullName} зарегистрировано {data.identity.registrationLabel}. Идентификаторы совпадают в одном наборе данных.</p><SourceLine dataset="counterparty" /></article>
          <article><span>Динамика 2024 к 2023</span><strong>Выручка +29,1%</strong><p>Активы +26,2%, кредиторская задолженность +25,3%. Абсолютные значения не публикуются из-за неизвестной единицы.</p><SourceLine dataset="finance" period="2023–2024" /></article>
          <article><span>Судебная выборка</span><strong>100 из 1 448</strong><p>53 записи с ролью ответчика и 16 с ролью истца. Это описание полученной части, а не всей истории.</p><SourceLine dataset="arbitration" /></article>
        </div>
      </section>

      <section className="cr-lab-h3__limits" aria-labelledby="h3-limits-title">
        <div><p className="cr-lab__kicker">Границы интерпретации</p><h2 id="h3-limits-title">Что нельзя заключить из этого снимка</h2></div>
        <ul>
          <li>Получение трёх обязательных наборов показывает комплектность отчёта, а не качество компании.</li>
          <li>Участие в судебном деле без предмета, роли и результата нельзя автоматически трактовать как негативное событие.</li>
          <li>Поля, которые не запрашивались, нельзя описывать как отсутствующие у юридического лица.</li>
          <li>Финансовые проценты показывают динамику, но без единицы нельзя публиковать абсолютные суммы.</li>
        </ul>
      </section>
      <SourcesSection compact />
      <ScenarioNextStep variant="h3" />
    </main>
  )
}

function ReferenceProfile() {
  const data = YANDEX_LAB_SNAPSHOT
  return (
    <main id="cr-lab-content" className="cr-lab__main cr-lab-h3 cr-lab-h3--profile">
      <nav className="cr-lab__breadcrumbs" aria-label="Хлебные крошки"><span>Компании</span><span aria-hidden="true">/</span><strong>{data.identity.shortName}</strong></nav>
      <section className="cr-lab-h3__profile-hero" aria-labelledby="cr-lab-h3-profile-title">
        <div><p className="cr-lab__eyebrow">Справочный профиль</p><h1 id="cr-lab-h3-profile-title">ООО «ЯНДЕКС»: профиль юридического лица</h1><p>{data.identity.fullName}</p></div>
        <div><span>Статус в снимке</span><strong>{data.identity.statusLabel}</strong><small>Код {data.identity.statusCode}</small></div>
      </section>
      <section className="cr-lab-h3__profile-grid" aria-labelledby="h3-profile-identity" id="identity">
        <div><p className="cr-lab__kicker">Точная идентификация</p><h2 id="h3-profile-identity">Регистрационные сведения</h2><IdentityDefinitionList /></div>
        <aside><p className="cr-lab__kicker">О снимке</p><dl><div><dt>Сформирован</dt><dd>{data.generatedLabel}</dd></div><div><dt>Источник</dt><dd>{data.sourceLabel}</dd></div><div><dt>Набор</dt><dd>counterparty</dd></div></dl><p>{data.completeness.scopeNote}</p></aside>
      </section>
      <section className="cr-lab-h3__profile-next" aria-labelledby="h3-profile-next-title"><div><p className="cr-lab__kicker">Нужен контекст для решения?</p><h2 id="h3-profile-next-title">Перейдите от справки к проверке доказательств</h2><p>Матрица покажет, какие сведения получены полностью, какие представлены выборкой и какие не запрашивались.</p></div><Link to={companyReportLabPath('h3')}>Открыть проверку</Link></section>
    </main>
  )
}

function IdentityTokens() {
  const identity = YANDEX_LAB_SNAPSHOT.identity
  return <dl className="cr-lab__tokens"><div><dt>ИНН</dt><dd>{identity.inn}</dd></div><div><dt>ОГРН</dt><dd>{identity.ogrn}</dd></div><div><dt>КПП</dt><dd>{identity.kpp}</dd></div></dl>
}

function IdentityDefinitionList() {
  const identity = YANDEX_LAB_SNAPSHOT.identity
  return (
    <dl className="cr-lab__definitions">
      <div><dt>Полное наименование</dt><dd>{identity.fullName}</dd></div>
      <div><dt>ИНН</dt><dd>{identity.inn}</dd></div>
      <div><dt>ОГРН</dt><dd>{identity.ogrn}</dd></div>
      <div><dt>КПП</dt><dd>{identity.kpp}</dd></div>
      <div><dt>Правовая форма</dt><dd>{identity.legalForm}</dd></div>
      <div><dt>Статус</dt><dd>{identity.statusLabel} <small>код {identity.statusCode}</small></dd></div>
      <div><dt>Дата регистрации</dt><dd><time dateTime={identity.registrationDate}>{identity.registrationLabel}</time></dd></div>
    </dl>
  )
}

function FinanceChanges({ compact = false }: { readonly compact?: boolean }) {
  return (
    <div className={`cr-lab__delta-grid${compact ? ' cr-lab__delta-grid--compact' : ''}`}>
      {YANDEX_LAB_SNAPSHOT.finance.changes.map((change) => <article key={change.id}><span>{change.label}</span><strong>{change.value}</strong><p>{change.explanation}</p></article>)}
    </div>
  )
}

function ArbitrationOverview() {
  const arbitration = YANDEX_LAB_SNAPSHOT.arbitration
  return (
    <>
      <div className="cr-lab__number-pair"><article><strong>{formatCount(arbitration.totalCases)}</strong><span>дел указано источником</span></article><article><strong>{arbitration.returnedCases}</strong><span>записей передано детально</span></article></div>
      <div className="cr-lab__metric-grid">
        <MetricTable title="Роли в 100 записях" rows={arbitration.roles} />
        <MetricTable title="Статусы в 100 записях" rows={arbitration.statuses} />
        <MetricTable title="Результаты в 100 записях" rows={arbitration.results} />
      </div>
    </>
  )
}

function MetricTable({ title, rows }: { readonly title: string; readonly rows: readonly { readonly label: string; readonly count: number }[] }) {
  return <section className="cr-lab__metric-table" aria-label={title}><h3>{title}</h3><dl>{rows.map((row) => <div key={row.label}><dt>{row.label}</dt><dd>{row.count}</dd></div>)}</dl></section>
}

function TaxSection({ id, headingId, index }: { readonly id: string; readonly headingId: string; readonly index?: string }) {
  const data = YANDEX_LAB_SNAPSHOT
  return (
    <section id={id} className="cr-lab__section" aria-labelledby={headingId}>
      <SectionHeading index={index} title="Налоговый режим" id={headingId} />
      <p>В полученных данных признак общего режима налогообложения: <strong>{data.taxation.commonMode ? 'да' : 'нет'}</strong>. Дата публикации сведений — <time dateTime={data.taxation.publicationDate}>{data.taxation.publicationLabel}</time>.</p>
      <SourceLine dataset="counterparty" period={data.taxation.publicationLabel} />
    </section>
  )
}

function SourcesSection({ compact = false }: { readonly compact?: boolean }) {
  const data = YANDEX_LAB_SNAPSHOT
  return (
    <section id="sources" className={`cr-lab__section cr-lab__sources${compact ? ' cr-lab__sources--compact' : ''}`} aria-labelledby="sources-title">
      <SectionHeading index={compact ? undefined : '05'} title="Источники и дата" id="sources-title" />
      <p>Все показанные факты взяты из сохранённого снимка CompanyReport <code>{data.reportId}</code>. Поставщик данных: {data.sourceLabel}. Наборы counterparty, finance и arbitration получены {data.receivedLabel}.</p>
      <p>Ссылки на внешние реестры не показаны: доступный контракт снимка не содержит проверенных исходящих адресов. Страница не дополняет данные догадками.</p>
    </section>
  )
}

function ScenarioNextStep({ variant }: { readonly variant: CompanyReportLabVariant }) {
  const [scenario, setScenario] = useState<CompanyReportLabScenario>('reference')
  const action = scenarioAction(variant, scenario)
  const isHash = action.href.startsWith('#')
  return (
    <section id="next" className="cr-lab__next" aria-labelledby="next-title">
      <div><p className="cr-lab__kicker">Контекстный следующий шаг</p><h2 id="next-title">Что вы хотите сделать?</h2><p>Действие меняется вместе с задачей пользователя. Сценарий задолженности не включён по умолчанию.</p></div>
      <div className="cr-lab__next-control">
        <label htmlFor="cr-lab-scenario">Зачем вы открыли страницу?</label>
        <select id="cr-lab-scenario" value={scenario} onChange={(event) => setScenario(event.target.value as CompanyReportLabScenario)}>
          <option value="reference">Найти и сверить реквизиты</option>
          <option value="deal">Проверить перед сделкой</option>
          <option value="prepayment">Оценить условия предоплаты</option>
          <option value="debt">У меня уже есть задолженность</option>
        </select>
        <p aria-live="polite">{action.detail}</p>
        {isHash ? <a className="cr-lab__primary-action" href={action.href}>{action.label}</a> : <Link className="cr-lab__primary-action" to={action.href}>{action.label}</Link>}
      </div>
    </section>
  )
}

function SourceLine({ dataset, period }: { readonly dataset: string; readonly period?: string }) {
  const data = YANDEX_LAB_SNAPSHOT
  return <p className="cr-lab__source"><span>Источник: {data.sourceLabel}</span><span>Набор: <code>{dataset}</code></span>{period ? <span>Период: {period}</span> : null}<span>Получено: {data.receivedLabel}</span></p>
}

function CoverageBadge({ coverage }: { readonly coverage: DatasetCoverage }) {
  return <span className={`cr-lab__coverage cr-lab__coverage--${coverage}`}>{DATASET_COVERAGE_LABELS[coverage]}</span>
}

function SectionHeading({ index, title, id }: { readonly index?: string; readonly title: string; readonly id: string }) {
  return <div className="cr-lab__section-heading">{index ? <span>{index}</span> : null}<h2 id={id}>{title}</h2></div>
}

function Limitation({ children }: { readonly children: string }) {
  return <div className="cr-lab__limitation"><strong>Ограничение</strong><p>{children}</p></div>
}

function LabFooter() {
  return <footer className="cr-lab__footer"><p><strong>CompanyReport</strong> · исследовательские варианты страницы проверки компании</p><p>Факты показаны на дату снимка и требуют сверки при принятии решения.</p></footer>
}

function formatCount(value: number): string {
  return new Intl.NumberFormat('ru-RU').format(value)
}
