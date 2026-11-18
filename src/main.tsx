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

// On a protected VPS deployment the backend answers 401 when the shared
// access cookie is missing/expired. Send the user to the login page instead of
// showing a vague API error. Local/desktop usage never hits this path.
const nativeFetch = window.fetch.bind(window)
window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const response = await nativeFetch(input, init)
  if (response.status === 401) {
    let url = ''
    if (typeof input === 'string') url = input
    else if (input instanceof URL) url = input.toString()
    else url = input.url
    if (url.startsWith('/api/') && !url.startsWith('/api/auth/')) {
      window.location.assign('/login.html')
    }
  }
  return response
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LanguageProvider>
      <App />
      <PWAInstallPrompt />
    </LanguageProvider>
  </StrictMode>,
)
