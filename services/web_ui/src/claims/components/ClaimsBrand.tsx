type ClaimsBrandProps = {
  compact?: boolean
}

export function ClaimsBrand({ compact = false }: ClaimsBrandProps) {
  return (
    <header className={`claims-brand${compact ? ' claims-brand--compact' : ''}`}>
      <div className="claims-brand__logo" aria-hidden="true">
        <span className="claims-brand__logo-cell claims-brand__logo-cell--a" />
        <span className="claims-brand__logo-cell claims-brand__logo-cell--b" />
        <span className="claims-brand__logo-cell claims-brand__logo-cell--c" />
        <span className="claims-brand__logo-cell claims-brand__logo-cell--d" />
        <span className="claims-brand__logo-cell claims-brand__logo-cell--e" />
      </div>
      <p className="claims-brand__text">онлайн сервис подготовки досудебных претензий для бизнеса</p>
    </header>
  )
}
