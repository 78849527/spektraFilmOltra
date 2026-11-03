import { Component, type ErrorInfo, type ReactNode } from 'react'

export class ErrorBoundary extends Component<{ children: ReactNode }, { message: string | null }> {
  state: { message: string | null } = { message: null }

  componentDidCatch(error: Error, info: ErrorInfo) {
    window.spektra?.logError(`[react] ${error.stack ?? error.message}\n${info.componentStack ?? ''}`)
    this.setState({ message: error.message })
  }

  render() {
    if (this.state.message) {
      return (
        <div className="error-screen">
          <div className="section-title">界面出错</div>
          <pre>{this.state.message}</pre>
          <button className="button button-secondary" onClick={() => window.location.reload()}>
            重新载入
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
