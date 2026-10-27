export type Mode = 'report' | 'approve' | 'apply'
export type ActionStatus = 'pending' | 'applied' | 'suggested' | 'reported' | 'rejected' | 'undone' | 'error'

export interface Status {
  gmail: { connected: boolean; email: string | null; status: 'ok' | 'expired' | 'none'; lastSync: string | null }
  ollama: { running: boolean; version: string | null; url: string; model: string; modelInstalled: boolean; error: string | null }
  dryRun: boolean
  lastScan: string | null
  scanning: boolean
  lastError: string | null
  waiting: number
  pendingCount: number
}

export interface TodayStats {
  received: number
  yesterdayReceived: number
  weekReceived: number
  processed: number
  pending: number
  errors: number
  lastError: string | null
}

export interface CategoryStats {
  items: { category: string; count: number }[]
  archiveTotal: number
  archiveUndone: number
}

export interface Score { key: string; score: number }

export interface Action {
  id: number
  emailId: string
  from: string
  addr: string
  subject: string
  snippet: string
  receivedAt: string
  category: string
  /** category: the decision is the e-mail's category; question: a rule's own yes/no question */
  kind: RuleKind
  question: string
  scores: Score[]
  topKey: string
  topScore: number
  threshold: number
  model: string
  latencyMs: number | null
  ruleId: number | null
  taskId: number | null
  source: string
  ops: string[]
  status: ActionStatus
  error: string | null
  createdAt: string
  updatedAt: string
  canUndo: boolean
}

export interface Option { key: string; description: string }

export interface Category { key: string; description: string; neverArchive: boolean }

export type RuleKind = 'category' | 'question'

export interface Rule {
  id: number
  name: string
  /** For a question rule: ask only in this category (null: every e-mail). */
  category: string | null
  kind: RuleKind
  question: string
  options: Option[]
  threshold: number
  actions: string[]
  mode: Mode
  modeLocked: boolean
  enabled: boolean
  stats7d: { triggered: number; undone: number }
}

export type RuleInput = Omit<Rule, 'id' | 'options' | 'stats7d' | 'modeLocked'>

export interface Task {
  id: number
  name: string
  query: string
  question: string
  options: Option[]
  threshold: number
  actions: string[]
  mode: Mode
  dryRun: boolean
  status: 'running' | 'paused' | 'done' | 'error'
  processed: number
  total: number
  passed: number
  needsApproval: number
  error: string | null
  createdAt: string
}

export interface TaskInput {
  query: string
  question: string
  options: Option[]
  threshold: number
  actions: string[]
  mode: Mode
  dryRun: boolean
}

export interface Preview {
  matchCount: number
  capped: boolean
  oldest: string | null
  alreadyProcessed: number
  secondsPerEmail: number
}

export interface Account {
  id: number
  email: string
  status: 'ok' | 'expired'
  scopes: string[]
  lastSync: string | null
  error: string | null
}

export interface CredentialsInfo { present: boolean; projectId?: string; clientType?: string }

export interface Settings {
  model: string
  ollamaUrl: string
  pollMinutes: number
  maxChars: number
  onlyUnread: boolean
  stripQuotes: boolean
  dryRun: boolean
}

export interface ModelInfo { name: string; installed: boolean; kind: 'd3' | 'chat' }
