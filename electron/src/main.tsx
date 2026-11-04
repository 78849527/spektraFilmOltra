import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { ErrorBoundary } from './components/ErrorBoundary'
import './styles/tokens.css'
import './styles/app.css'

window.addEventListener('error', (event) => {
  window.spektra?.logError(
    `[window.error] ${event.message} @ ${event.filename}:${event.lineno}:${event.colno}`,
  )
})

window.addEventListener('unhandledrejection', (event) => {
  window.spektra?.logError(`[unhandledrejection] ${String(event.reason)}`)
})

const container = document.getElementById('root')
if (!container) throw new Error('缺少根节点')

const boot = async (): Promise<void> => {
  // Browser preview only: without Electron preload there is no window.spektra,
  // so install the dev mock bridge (tree-shaken out of production builds).
  if (import.meta.env.DEV && !window.spektra) {
    const { installMockBridge } = await import('./mock/install')
    installMockBridge()
  }
  createRoot(container).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
  )
}

void boot()
