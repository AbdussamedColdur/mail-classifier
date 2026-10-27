import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api/client'
import type { Status } from './api/types'
import { DryBand, Nav, StatusBar, Toast } from './components/Layout'
import { Ctx, parseHash, readPref, usePoll, writePref, type Screen, type ToastMsg } from './lib/app'
import Accounts from './pages/Accounts'
import Command from './pages/Command'
import Logs from './pages/Logs'
import Panel from './pages/Panel'
import Queue from './pages/Queue'
import Rules from './pages/Rules'
import Settings from './pages/Settings'

function initialDark(): boolean {
  const saved = readPref('mk-theme')
  if (saved) return saved === 'dark'
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
}

export default function App() {
  const [route, setRoute] = useState(parseHash)
  const [status, setStatus] = useState<Status | null>(null)
  // Only a failed request means the backend is unreachable; before the first answer we are still connecting.
  const [statusFailed, setStatusFailed] = useState(false)
  const [dark, setDark] = useState(initialDark)
  const [toast, setToast] = useState<ToastMsg | null>(null)
  const toastTimer = useRef<number>()

  useEffect(() => {
    const onHash = () => setRoute(parseHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    document.body.classList.toggle('dk', dark)
    writePref('mk-theme', dark ? 'dark' : 'light')
  }, [dark])

  const refreshStatus = usePoll(async () => {
    try { setStatus(await api.status()); setStatusFailed(false) } catch { setStatus(null); setStatusFailed(true) }
  }, 10000)

  const go = useCallback((s: Screen, params?: Record<string, string>) => {
    const q = params ? '?' + new URLSearchParams(params).toString() : ''
    window.location.hash = `#/${s}${q}`
  }, [])

  const showToast = useCallback((t: ToastMsg) => {
    window.clearTimeout(toastTimer.current)
    setToast(t)
    toastTimer.current = window.setTimeout(() => setToast(null), 5000)
  }, [])

  const pages: Record<Screen, JSX.Element> = {
    panel: <Panel />,
    queue: <Queue />,
    command: <Command />,
    rules: <Rules />,
    logs: <Logs />,
    accounts: <Accounts params={route.params} />,
    settings: <Settings />,
  }

  return (
    <Ctx.Provider value={{ status, statusFailed, refreshStatus, dark, toggleTheme: () => setDark((d) => !d), go, toast: showToast }}>
      <div className={dark ? 'mk dk' : 'mk'} style={{ display: 'flex', flexWrap: 'wrap', minHeight: '100vh', background: 'var(--bg)' }}>
        <Nav current={route.screen} />
        <main style={{ flex: '999 1 560px', minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          {status?.dryRun && <DryBand />}
          <StatusBar />
          <div key={route.screen}>{pages[route.screen]}</div>
        </main>
        {toast && (
          <Toast title={toast.title} sub={toast.sub} onClose={() => setToast(null)}
            action={toast.action && { label: toast.action.label, run: () => { setToast(null); toast.action!.run() } }} />
        )}
      </div>
    </Ctx.Provider>
  )
}
