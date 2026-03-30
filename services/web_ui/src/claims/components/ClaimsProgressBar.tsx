type ClaimsProgressBarProps = {
  label: string
  value: number
}

export function ClaimsProgressBar({ label, value }: ClaimsProgressBarProps) {
  const normalized = normalizeProgress(value)

  return (
    <section className="claims-progress" aria-live="polite">
      <p className="claims-progress__label">
        {label} <strong>{normalized}%</strong>
      </p>
      <div className="claims-progress__track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={normalized}>
        <span className="claims-progress__fill" style={{ width: `${normalized}%` }} />
      </div>
    </section>
  )
}

function normalizeProgress(value: number): number {
  if (!Number.isFinite(value)) {
    return 0
  }
  const rounded = Math.round(value)
  if (rounded < 0) {
    return 0
  }
  if (rounded > 100) {
    return 100
  }
  return rounded
}
