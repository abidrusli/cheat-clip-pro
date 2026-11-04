import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { LanguageProvider } from './locales'
import './index.css'
import App from './App.tsx'
import PWAInstallPrompt from './components/PWAInstallPrompt.tsx'

// Register the PWA service worker for installable/offline-capable builds.
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch((err) => {
      console.warn('Service worker registration failed:', err)
    })
  })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LanguageProvider>
      <App />
      <PWAInstallPrompt />
    </LanguageProvider>
  </StrictMode>,
)
