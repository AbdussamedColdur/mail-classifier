import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Action, ActionStatus } from '../api/types'
import * as Ic from '../components/Icons'
import { useApp } from '../lib/app'
import { opsText, score, statusBadge, when } from '../lib/format'

const RANGES = [['today', 'Bugün'], ['7d', '7 gün'], ['30d', '30 gün']] as const
const STATUSES: [ActionStatus | '', string, string][] = [
  ['', 'Tümü', 'var(--acc)'],
  ['applied', 'Uygulandı', 'var(--gn)'],
  ['rejected', 'Reddedildi', 'var(--gy)'],
  ['undone', 'Geri alındı', 'var(--line2)'],
]
const PAGE = 50

export default function Logs() {
  const { toast } = useApp()
  const [range, setRange] = useState<string>('7d')
  const [st, setSt] = useState<ActionStatus | ''>('')
  const [q, setQ] = useState('')
  const [all, setAll] = useState<Action[] | null>(null)
  const [sel, setSel] = useState<Record<number, boolean>>({})
  const [page, setPage] = useState(0)

  const load = async () => {
    try { setAll(await api.actions(range, undefined, q.trim() || undefined)) } catch (e) { toast({ title: 'Kayıtlar yüklenemedi', sub: (e as Error).message }) }
  }
  useEffect(() => {
    const t = setTimeout(load, q ? 250 : 0)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [range, q])
  useEffect(() => setPage(0), [range, q, st])

  const rows = (all ?? []).filter((r) => !st || r.status === st)
  const pages = Math.max(1, Math.ceil(rows.length / PAGE))
  const shown = rows.slice(page * PAGE, page * PAGE + PAGE)
  const selIds = Object.keys(sel).filter((k) => sel[+k]).map(Number)
  const undoable = (all ?? []).filter((r) => selIds.includes(r.id) && r.canUndo)
  const allSel = shown.length > 0 && shown.every((r) => sel[r.id])

  const undo = async (list: Action[]) => {
    if (!list.length) return
    try {
      await api.undo(list.map((r) => r.id))
      setSel({})
      const ids = list.map((r) => r.id)
      toast(list.length === 1
        ? { title: `“${list[0].subject}” geri alındı`, sub: opsText(list[0].ops) + ' Gmail’den kaldırıldı', action: { label: 'Yinele', run: () => api.redo(ids).then(load) } }
        : { title: `${list.length} işlem geri alındı`, sub: 'Etiketler ve arşivleme Gmail’de eski haline döndü', action: { label: 'Yinele', run: () => api.redo(ids).then(load) } })
      load()
    } catch (e) {
      toast({ title: 'Geri alınamadı', sub: (e as Error).message })
    }
  }

  return (
    <div className="page" style={{ gap: 16 }}>
      <div className="page-head">
        <div style={{ flex: '1 1 auto' }}>
          <h1>Kayıtlar</h1>
          <p>d3'ün verdiği her karar ve Gmail'e uygulanan her işlem. Uygulanan işlemler 30 gün boyunca geri alınabilir.</p>
        </div>
        <a className="btn ib" href={api.csvUrl(range, st || undefined, q.trim() || undefined)} style={{ color: 'var(--tx)', textDecoration: 'none' }}><Ic.Download />CSV indir</a>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
        <div role="group" aria-label="Tarih aralığı" className="seg" style={{ gap: 2 }}>
          {RANGES.map(([k, l]) => <button key={k} type="button" aria-pressed={range === k} onClick={() => setRange(k)}>{l}</button>)}
        </div>
        <div role="group" aria-label="Durum filtresi" className="seg" style={{ gap: 2 }}>
          {STATUSES.map(([k, l, dot]) => (
            <button key={l} type="button" aria-pressed={st === k} onClick={() => setSt(k)}>
              <span aria-hidden="true" className="dot" style={{ background: dot }} />{l} <span className="num" style={{ color: 'var(--mut)' }}>{(all ?? []).filter((r) => !k || r.status === k).length}</span>
            </button>
          ))}
        </div>
        <label className="search" style={{ marginLeft: 'auto', flex: '0 1 260px' }}>
          <Ic.Search /><span className="sr">Kayıtlarda ara</span>
          <input type="search" placeholder="Konu, gönderen veya kural" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
      </div>

      <section aria-label="Karar ve işlem kayıtları" className="card" style={{ overflow: 'hidden' }}>
        {selIds.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10, padding: '8px 12px', background: 'var(--accSoft)', borderBottom: '1px solid var(--line)' }}>
            <span style={{ fontWeight: 600, color: 'var(--accTx)' }}><span className="num">{selIds.length}</span> kayıt seçili</span>
            <span style={{ fontSize: 12, color: 'var(--mut)' }}>{undoable.length === selIds.length ? 'Tümü geri alınabilir' : `${undoable.length} tanesi geri alınabilir (yalnızca uygulananlar)`}</span>
            <button type="button" className="btn-p" onClick={() => undo(undoable)} disabled={!undoable.length} style={{ marginLeft: 'auto', height: 30, padding: '0 12px', fontSize: 12, borderRadius: 7 }}><Ic.Undo />Seçilenleri geri al</button>
            <button className="btn ib" type="button" onClick={() => setSel({})} style={{ height: 30, padding: '0 10px', fontSize: 12, borderRadius: 7 }}>Seçimi temizle</button>
          </div>
        )}
        <div style={{ overflowX: 'auto' }}>
          <table className="hov" style={{ width: '100%', minWidth: 900, borderCollapse: 'collapse' }}>
            <thead><tr>
              <th style={{ width: 36 }}><input type="checkbox" aria-label="Görünen tüm kayıtları seç" checked={allSel} onChange={() => setSel((s) => { const n = { ...s }; shown.forEach((r) => { n[r.id] = !allSel }); return n })} /></th>
              <th>Zaman</th><th>E-posta</th><th>Kural</th><th>Puan</th><th>İşlem</th><th>Durum</th><th style={{ textAlign: 'right' }}>Eylem</th>
            </tr></thead>
            <tbody>
              {shown.map((r) => {
                const b = statusBadge(r.status)
                const bg = sel[r.id] ? 'var(--accSoft)' : 'transparent'
                return (
                  <tr key={r.id}>
                    <td style={{ background: bg, padding: '9px 12px' }}><input type="checkbox" aria-label={`${r.subject} kaydını seç`} checked={!!sel[r.id]} onChange={() => setSel((s) => ({ ...s, [r.id]: !s[r.id] }))} /></td>
                    <td className="num" style={{ background: bg, padding: '9px 12px', whiteSpace: 'nowrap', color: 'var(--mut)', fontSize: 12 }}>{when(r.createdAt)}</td>
                    <td style={{ background: bg, padding: '9px 12px', maxWidth: 300 }}><div className="ellipsis" style={{ fontWeight: 500 }}>{r.subject}</div><div className="ellipsis" style={{ fontSize: 12, color: 'var(--mut)' }}>{r.from}</div></td>
                    <td style={{ background: bg, padding: '9px 12px', fontSize: 12, whiteSpace: 'nowrap' }}>{r.source}</td>
                    <td className="num" style={{ background: bg, padding: '9px 12px', fontWeight: 600, fontSize: 12 }}>{score(r.topScore)}</td>
                    <td style={{ background: bg, padding: '9px 12px', fontSize: 12, whiteSpace: 'nowrap' }}>{opsText(r.ops)}</td>
                    <td style={{ background: bg, padding: '9px 12px' }} title={r.error ?? undefined}><span className="badge" style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '2px 8px', background: b.bg, color: b.fg, border: `1px solid ${b.bd ?? 'transparent'}` }}>{b.text}</span></td>
                    <td style={{ background: bg, padding: '9px 12px', textAlign: 'right', fontSize: 12, whiteSpace: 'nowrap' }}>
                      {r.canUndo ? <button className="lk" type="button" onClick={() => undo([r])}>Geri al</button>
                        : r.status === 'error' ? <button className="lk" type="button" onClick={() => api.retry(r.id).then(load, (e) => toast({ title: 'Tekrar denenemedi', sub: e.message }))}>Tekrar dene</button>
                        : <span style={{ color: 'var(--mut)' }}>—</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        {all && rows.length === 0 && <div style={{ padding: '40px 16px', textAlign: 'center', color: 'var(--mut)' }}>Bu filtrelerle eşleşen kayıt yok.</div>}
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, padding: '10px 12px', fontSize: 12, color: 'var(--mut)' }}>
          <span className="num">{shown.length} kayıt gösteriliyor{rows.length > shown.length ? ` · toplam ${rows.length}` : ''}</span>
          <span style={{ marginLeft: 'auto' }}>Sayfa {page + 1} / {pages}</span>
          <button className="ib" type="button" disabled={page === 0} onClick={() => setPage(page - 1)} aria-label="Önceki sayfa" style={{ width: 30, height: 30, border: '1px solid var(--line)', borderRadius: 7, background: 'var(--card)' }}>‹</button>
          <button className="ib" type="button" disabled={page >= pages - 1} onClick={() => setPage(page + 1)} aria-label="Sonraki sayfa" style={{ width: 30, height: 30, border: '1px solid var(--line)', borderRadius: 7, background: 'var(--card)' }}>›</button>
        </div>
      </section>
    </div>
  )
}
