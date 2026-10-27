import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import type { Status } from '../api/types'

export type Screen = 'panel' | 'queue' | 'command' | 'rules' | 'logs' | 'accounts' | 'settings'
export const SCREENS: Screen[] = ['panel', 'queue', 'command', 'rules', 'logs', 'accounts', 'settings']

export interface ToastMsg { title: string; sub?: string; action?: { label: string; run: () => void } }

interface AppCtx {
  status: Status | null
  /** The last /api/status request failed (null status alone may just mean "not answered yet"). */
  statusFailed: boolean
  refreshStatus: () => void
  dark: boolean
  toggleTheme: () => void
  go: (s: Screen, params?: Record<string, string>) => void
  toast: (t: ToastMsg) => void
}

export const Ctx = createContext<AppCtx>(null as unknown as AppCtx)
export const useApp = () => useContext(Ctx)

/** Hash routes like #/accounts?connected=a@b.c, so the OAuth redirect can land on a screen. */
export function parseHash(): { screen: Screen; params: URLSearchParams } {
  const [path, query] = window.location.hash.replace(/^#\/?/, '').split('?')
  const screen = (SCREENS as string[]).includes(path) ? (path as Screen) : 'panel'
  return { screen, params: new URLSearchParams(query ?? '') }
}

/** Runs `fn` now and then every `ms` while the tab is visible; returns a manual refresh. */
export function usePoll(fn: () => void | Promise<void>, ms: number, deps: unknown[] = []) {
  const ref = useRef(fn)
  ref.current = fn
  const run = useCallback(() => { void ref.current() }, [])
  useEffect(() => {
    run()
    const t = setInterval(() => { if (document.visibilityState === 'visible') run() }, ms)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return run
}

export function readPref(key: string): string | null {
  try { return localStorage.getItem(key) } catch { return null }
}

export function writePref(key: string, value: string) {
  try { localStorage.setItem(key, value) } catch { /* storage unavailable */ }
}

export function useAsync<T>(load: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const reload = useCallback(async () => {
    try {
      setData(await load())
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(() => { void reload() }, [reload])
  return { data, setData, error, reload }
}
