import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { registerSW } from 'virtual:pwa-register'   // ✅ 新增
import './index.css'
import App from './App.tsx'

registerSW({ immediate: true })                     // ✅ 新增（立即注册，方便验证）

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
