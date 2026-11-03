import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './styles/tokens.css'
import './styles/app.css'

const container = document.getElementById('root')
if (!container) throw new Error('缺少根节点')

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
