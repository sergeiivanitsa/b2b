import { Component, type ErrorInfo, type ReactNode } from 'react'

type Props = Readonly<{ children: ReactNode; onError: () => void }>
type State = Readonly<{ failed: boolean }>

export class ArbitrationChartErrorBoundary extends Component<Props, State> {
  state: State = { failed: false }
  static getDerivedStateFromError(): State { return { failed: true } }
  componentDidCatch(error: Error, info: ErrorInfo): void { void error; void info; this.props.onError() }
  render(): ReactNode {
    return this.state.failed
      ? <p className="company-public-h2__chart-status" role="status" aria-live="polite">Интерактивный график недоступен; фактические данные сохранены.</p>
      : this.props.children
  }
}
