import type { ActionStatus, Mode } from '../api/types'

/** ["label:Fatura", "archive"] → "Etiket: Fatura + Arşivle", as written in the design. */
export function opsText(ops: string[]): string {
  if (!ops.length) return 'İşlem yok'
  const labels = ops.filter((o) => o.startsWith('label:')).map((o) => o.slice(6))
  const rest = ops.filter((o) => !o.startsWith('label:')).map((o) => ({ star: 'Yıldız', archive: 'Arşivle', read: 'Okundu' }[o] ?? o))
  return [labels.length ? 'Etiket: ' + labels.join(', ') : '', ...rest].filter(Boolean).join(' + ')
}

/** Past-tense line for the panel feed. */
export function feedText(status: ActionStatus, ops: string[], error: string | null): string {
  if (status === 'error') return 'Hata: ' + (error ?? 'bilinmiyor')
  if (status === 'suggested') return 'Kuru mod: ' + opsText(ops)
  if (status === 'undone') return 'Geri alındı: ' + opsText(ops)
  if (ops.length === 1 && ops[0] === 'archive') return 'Arşivlendi'
  return opsText(ops)
}

export const MODE_LABEL: Record<Mode, string> = {
  report: 'Sadece raporla',
  approve: 'Onaya gönder',
  apply: 'Doğrudan uygula',
}

export const MODE_COLORS: Record<Mode, [string, string]> = {
  report: ['var(--gyBg)', 'var(--gy)'],
  approve: ['var(--amBg)', 'var(--am)'],
  apply: ['var(--gnBg)', 'var(--gn)'],
}

export function statusBadge(s: ActionStatus): { text: string; bg: string; fg: string; bd?: string } {
  switch (s) {
    case 'pending': return { text: 'Bekliyor', bg: 'var(--amBg)', fg: 'var(--am)' }
    case 'applied': return { text: 'Uygulandı', bg: 'var(--gnBg)', fg: 'var(--gn)' }
    case 'suggested': return { text: 'Önerildi', bg: 'var(--gnBg)', fg: 'var(--gn)' }
    case 'reported': return { text: 'Raporlandı', bg: 'var(--gyBg)', fg: 'var(--gy)' }
    case 'rejected': return { text: 'Reddedildi', bg: 'var(--gyBg)', fg: 'var(--gy)' }
    case 'undone': return { text: 'Geri alındı', bg: 'transparent', fg: 'var(--mut)', bd: 'var(--line2)' }
    case 'error': return { text: 'Hata', bg: 'var(--rdBg)', fg: 'var(--rd)' }
  }
}

export const score = (v: number) => v.toFixed(2)
export const pct = (v: number) => Math.round(v * 100) + '%'

const timeFmt = new Intl.DateTimeFormat('tr-TR', { hour: '2-digit', minute: '2-digit' })
const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short' })
const longDay = new Intl.DateTimeFormat('tr-TR', { weekday: 'long', day: 'numeric', month: 'long' })

export const hhmm = (iso: string | null) => (iso ? timeFmt.format(new Date(iso)) : '—')
export const today = () => longDay.format(new Date()).replace(/^\w/, (c) => c.toLocaleUpperCase('tr-TR'))

function dayDiff(iso: string): number {
  const d = new Date(iso)
  const a = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const n = new Date()
  const b = new Date(n.getFullYear(), n.getMonth(), n.getDate()).getTime()
  return Math.round((b - a) / 86400000)
}

/** "Bugün 14:32", "Dün 18:05", "22 Eki 09:12". */
export function when(iso: string): string {
  const diff = dayDiff(iso)
  const t = timeFmt.format(new Date(iso))
  if (diff === 0) return 'Bugün ' + t
  if (diff === 1) return 'Dün ' + t
  return dayFmt.format(new Date(iso)) + ' ' + t
}

/** Time for today's items, short date otherwise. */
export const shortTime = (iso: string) => (dayDiff(iso) === 0 ? timeFmt.format(new Date(iso)) : dayFmt.format(new Date(iso)))

export function ago(iso: string | null): string {
  if (!iso) return '—'
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'Az önce'
  if (s < 3600) return `${Math.floor(s / 60)} dk önce`
  if (s < 86400) return `${Math.floor(s / 3600)} saat önce`
  return `${Math.floor(s / 86400)} gün önce`
}

export function initials(name: string): string {
  const parts = name.replace(/[<>"@.]/g, ' ').trim().split(/\s+/).filter(Boolean)
  return ((parts[0]?.[0] ?? '?') + (parts[1]?.[0] ?? '')).toLocaleUpperCase('tr-TR')
}

export const nf = new Intl.NumberFormat('tr-TR')
