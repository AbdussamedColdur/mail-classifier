import type {
  Account, Action, Category, CategoryStats, CredentialsInfo, ModelInfo, Preview, Rule, RuleInput, Settings, Status, Task,
  TaskInput, TodayStats,
} from './types'

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message)
  }
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} }
  if (body instanceof FormData) init.body = body
  else if (body !== undefined) {
    init.body = JSON.stringify(body)
    init.headers = { 'Content-Type': 'application/json' }
  }
  let res: Response
  try {
    res = await fetch('/api' + path, init)
  } catch {
    throw new ApiError('MailKarar arka ucuna ulaşılamıyor. Sunucu çalışıyor mu?', 0)
  }
  if (!res.ok) {
    let msg = `İstek başarısız (${res.status})`
    try {
      const data = await res.json()
      if (typeof data.detail === 'string') msg = data.detail
      else if (Array.isArray(data.detail)) msg = data.detail.map((d: { msg: string }) => d.msg).join(', ')
    } catch { /* not JSON */ }
    throw new ApiError(msg, res.status)
  }
  return res.json() as Promise<T>
}

const qs = (p: Record<string, string | undefined>) => {
  const s = new URLSearchParams(Object.entries(p).filter(([, v]) => v) as [string, string][]).toString()
  return s ? '?' + s : ''
}

type Results = { results: Record<string, string> }

export const api = {
  status: () => req<Status>('GET', '/status'),
  scan: () => req('POST', '/scan'),
  startOllama: () => req('POST', '/ollama/start'),

  today: () => req<TodayStats>('GET', '/stats/today'),
  categories: (days = 7) => req<CategoryStats>('GET', `/stats/categories?days=${days}`),
  feed: (limit = 6) => req<Action[]>('GET', `/feed?limit=${limit}`),

  queue: () => req<Action[]>('GET', '/queue'),
  approve: (id: number, category?: string) => req<{ status: string }>('POST', `/queue/${id}/approve`, category ? { category } : {}),
  reject: (id: number) => req<{ status: string }>('POST', `/queue/${id}/reject`),
  bulk: (ids: number[], decision: 'approve' | 'reject') => req<Results>('POST', '/queue/bulk', { ids, decision }),
  approvePassing: () => req<Results>('POST', '/queue/approve-passing'),

  actions: (range: string, status?: string, q?: string) => req<Action[]>('GET', '/actions' + qs({ range, status, q })),
  csvUrl: (range: string, status?: string, q?: string) => '/api/actions.csv' + qs({ range, status, q }),
  undo: (ids: number[]) => req<Results>('POST', '/actions/undo', { ids }),
  redo: (ids: number[]) => req<Results>('POST', '/actions/redo', { ids }),
  retry: (id: number) => req<{ status: string }>('POST', `/actions/${id}/retry`),

  categoryList: () => req<Category[]>('GET', '/categories'),
  rules: () => req<Rule[]>('GET', '/rules'),
  createRule: (r: RuleInput) => req<Rule>('POST', '/rules', r),
  patchRule: (id: number, p: Partial<RuleInput>) => req<Rule>('PATCH', `/rules/${id}`, p),
  deleteRule: (id: number) => req('DELETE', `/rules/${id}`),

  preview: (query: string) => req<Preview>('POST', '/tasks/preview', { query }),
  createTask: (t: TaskInput) => req<{ id: number }>('POST', '/tasks', t),
  tasks: () => req<Task[]>('GET', '/tasks'),
  taskScores: (id: number) => req<{ target: string; scores: number[]; isTop: boolean[] }>('GET', `/tasks/${id}/scores`),
  pauseTask: (id: number) => req('POST', `/tasks/${id}/pause`),
  resumeTask: (id: number) => req('POST', `/tasks/${id}/resume`),

  accounts: () => req<Account[]>('GET', '/accounts'),
  credentials: () => req<CredentialsInfo>('GET', '/accounts/credentials'),
  uploadCredentials: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return req<CredentialsInfo>('POST', '/accounts/credentials', fd)
  },
  removeCredentials: () => req('DELETE', '/accounts/credentials'),
  syncAccount: (id: number) => req('POST', `/accounts/${id}/sync`),
  deleteAccount: (id: number) => req('DELETE', `/accounts/${id}`),
  connectUrl: '/api/auth/google/start',

  settings: () => req<Settings>('GET', '/settings'),
  saveSettings: (s: Partial<Settings>) => req<Settings>('PUT', '/settings', s),
  testOllama: (ollamaUrl: string) =>
    req<{ ok: boolean; version: string | null; models: string[]; decision: string[]; error: string | null }>('POST', '/settings/test-ollama', { ollamaUrl }),
  models: () => req<ModelInfo[]>('GET', '/models'),
}
