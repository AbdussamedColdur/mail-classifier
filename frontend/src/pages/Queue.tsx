import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import type { Action } from '../api/types'
import { Bar } from '../components/Layout'
import * as Ic from '../components/Icons'
import { useApp, useAsync, usePoll } from '../lib/app'
import { opsText, score, statusBadge, when } from '../lib/format'

type Sort = 'new' | 'asc' | 'desc'

export default function Queue() {
  const { status, refreshStatus, toast } = useApp()
  const categories = useAsync(api.categoryList).data?.map((c) => c.key) ?? []
  const [items, setItems] = useState<Action[] | null>(null)
  const [filter, setFilter] = useState('Tümü')
  const [q, setQ] = useState('')
  const [sort, setSort] = useState<Sort>('new')
  const [sel, setSel] = useState<number | null>(null)
  const [checked, setChecked] = useState<Record<number, boolean>>({})
  const [newCat, setNewCat] = useState('')
  const [busy, setBusy] = useState(false)
  const dry = status?.dryRun ?? true

  // Open the first pending decision once, and only where the detail sits beside the table; below
  // 1280px it is a drawer over the table, and a closed panel must stay closed on the next poll.
  const autoOpened = useRef(false)
  const load = usePoll(async () => {
    try {
      const data = await api.queue()
      setItems(data)
      if (!autoOpened.current && data.length) {
        autoOpened.current = true
        if (window.matchMedia('(min-width: 1280px)').matches) setSel(data.find((a) => a.status === 'pending')?.id ?? null)
      }
    } catch { /* shown by the status bar */ }
  }, 15000)

  useEffect(() => {
    if (sel === null) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setSel(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [sel])

  const shown = useMemo(() => {
    const needle = q.trim().toLocaleLowerCase('tr-TR')
    const list = (items ?? []).filter((a) => (filter === 'Tümü' || a.category === filter)
      && (!needle || (a.from + ' ' + a.subject).toLocaleLowerCase('tr-TR').includes(needle)))
    if (sort === 'asc') list.sort((a, b) => a.topScore - b.topScore)
    if (sort === 'desc') list.sort((a, b) => b.topScore - a.topScore)
    return list
  }, [items, filter, q, sort])

  const run = async (fn: () => Promise<unknown>, fail: string) => {
    setBusy(true)
    try { await fn() } catch (e) { toast({ title: fail, sub: (e as Error).message }) }
    setBusy(false)
    refreshStatus()
    load()
  }

  const checkedIds = Object.keys(checked).filter((k) => checked[+k]).map(Number)
  const x = items?.find((a) => a.id === sel) ?? null
  const pendingCount = items?.filter((a) => a.status === 'pending').length ?? 0

  return (
    <div className="page fill" style={{ gap: 16 }}>
      <div className="page-head">
        <div style={{ flex: '1 1 auto' }}>
          <h1>Onay Kuyruğu</h1>
          <p>Eşiğin altında kalan ya da “Onaya gönder” modundaki kurallardan gelen kararlar</p>
        </div>
        <button className="btn ib" type="button" disabled={!checkedIds.length || busy}
          onClick={() => run(async () => { await api.bulk(checkedIds, 'reject'); setChecked({}) }, 'Reddedilemedi')}>
          Seçilenleri reddet{checkedIds.length ? ` (${checkedIds.length})` : ''}
        </button>
        <button className="btn-p" type="button" disabled={!pendingCount || busy}
          onClick={() => run(async () => {
            const r = await api.approvePassing()
            const n = Object.keys(r.results).length
            toast({ title: n ? `${n} karar ${dry ? 'önerildi' : 'uygulandı'}` : 'Eşiği geçen bekleyen karar yok' })
          }, 'Onaylanamadı')}>
          Eşiği geçenleri onayla
        </button>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
        <label className="search" style={{ flex: '0 1 280px' }}>
          <Ic.Search /><span className="sr">Ara</span>
          <input type="search" placeholder="Gönderen veya konu ara" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <div role="group" aria-label="Kategori filtresi" className="seg">
          {['Tümü', ...categories].map((c) => (
            <button key={c} type="button" aria-pressed={filter === c} onClick={() => setFilter(c)}>
              {c} <span className="num" style={{ color: 'var(--mut)' }}>{(items ?? []).filter((a) => c === 'Tümü' || a.category === c).length}</span>
            </button>
          ))}
        </div>
        <label style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--mut)' }}>Sırala
          <select className="select" value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
            <option value="new">En yeni</option>
            <option value="asc">Güven (düşük → yüksek)</option>
            <option value="desc">Güven (yüksek → düşük)</option>
          </select>
        </label>
      </div>

      <div className="q-body">
        <section aria-label="Bekleyen kararlar" className="card q-table">
          <div className="q-scroll">
            <table className="ftable">
              <thead><tr>
                <th className="c-sel"><span className="sr">Seç</span></th><th className="c-from">Gönderen</th><th>Konu</th>
                <th className="c-cat">Kategori</th><th className="c-score">Güven</th><th className="c-ops">Önerilen işlem</th>
                <th className="c-status">Durum</th><th className="c-time" style={{ textAlign: 'right' }}>Saat</th>
              </tr></thead>
              <tbody>
                {shown.map((r) => {
                  const on = r.id === sel
                  const st = statusBadge(r.status)
                  const bg = on ? 'var(--accSoft)' : 'transparent'
                  const ops = opsText(r.ops)
                  return (
                    <tr key={r.id} className="tr" onClick={() => { setSel(r.id); setNewCat('') }}>
                      <td className="c-sel" style={{ background: bg, boxShadow: on ? 'inset 2px 0 0 var(--acc)' : 'none' }} onClick={(e) => e.stopPropagation()}>
                        <input type="checkbox" aria-label={`${r.subject} kararını seç`} disabled={r.status !== 'pending'} checked={!!checked[r.id]}
                          onChange={() => setChecked((c) => ({ ...c, [r.id]: !c[r.id] }))} />
                      </td>
                      <td className="c-from" title={r.addr ? `${r.from} <${r.addr}>` : r.from} style={{ background: bg, fontWeight: 500 }}>{r.from}</td>
                      <td title={r.subject} style={{ background: bg }}><button type="button" onClick={() => setSel(r.id)} className="ellipsis" style={{ display: 'block', width: '100%', padding: 0, border: 0, background: 'transparent', textAlign: 'left' }}>{r.subject}</button></td>
                      <td className="c-cat" title={r.category} style={{ background: bg }}><span className="chip">{r.category}</span></td>
                      <td className="c-score" style={{ background: bg }}><div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span className="c-bar"><Bar value={r.topScore} width={48} /></span><span className="num" style={{ fontSize: 12, fontWeight: 600 }}>{score(r.topScore)}</span></div></td>
                      <td className="c-ops" title={ops} style={{ background: bg, fontSize: 12 }}>{ops}</td>
                      <td className="c-status" style={{ background: bg }}><span className="badge" style={{ background: st.bg, color: st.fg }}>{st.text}</span></td>
                      <td className="c-time num" style={{ background: bg, textAlign: 'right', color: 'var(--mut)', fontSize: 12 }}>{when(r.receivedAt)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          {items && shown.length === 0 && (
            <div className="empty" style={{ padding: '48px 16px' }}>
              <div aria-hidden="true" className="empty-ic" style={{ width: 44, height: 44 }}><Ic.Check s={20} w={2.2} /></div>
              <div style={{ fontWeight: 600, fontSize: 14 }}>{items.length === 0 ? 'Kuyruk boş, her şey yolunda' : 'Bu filtrelerle onay bekleyen e-posta yok'}</div>
              <div style={{ color: 'var(--mut)', maxWidth: 400 }}>{items.length === 0
                ? 'Bekleyen tüm kararlar işlendi. Eşiğin altında kalan yeni bir karar geldiğinde burada görünecek.'
                : 'Başka bir kategori seçin ya da filtreyi “Tümü” yapın.'}</div>
              <div style={{ display: 'flex', gap: 12, marginTop: 4, fontSize: 12, fontWeight: 500 }}><a href="#/logs">Son kararları gör</a><a href="#/rules">Kuralları düzenle</a></div>
            </div>
          )}
          </div>
        </section>

        {x && <button type="button" className="q-backdrop" aria-label="Ayrıntıyı kapat" onClick={() => setSel(null)} />}
        {x && (
          <aside aria-label="E-posta ayrıntısı" className="card q-detail" style={{ boxShadow: '0 8px 24px rgba(0,0,0,0.06)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '12px 16px', borderBottom: '1px solid var(--line)' }}>
              <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--mut)' }}>Ayrıntı</span>
              <span className="badge" style={{ background: statusBadge(x.status).bg, color: statusBadge(x.status).fg }}>{statusBadge(x.status).text}</span>
              <button className="ib" type="button" aria-label="Paneli kapat" onClick={() => setSel(null)} style={{ marginLeft: 'auto', width: 30, height: 30, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', border: '1px solid var(--line)', borderRadius: 7, background: 'transparent', color: 'var(--mut)' }}><Ic.X s={14} w={2} /></button>
            </div>
            <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div>
                <div style={{ fontWeight: 500 }}>{x.from} {x.addr && x.addr !== x.from && <span style={{ color: 'var(--mut)', fontWeight: 400 }}>&lt;{x.addr}&gt;</span>}</div>
                <div className="num" style={{ fontSize: 12, color: 'var(--mut)' }}>{when(x.receivedAt)} · {x.source}</div>
                <h2 style={{ margin: '10px 0 6px', fontSize: 15, fontWeight: 600, lineHeight: 1.35 }}>{x.subject}</h2>
                <p style={{ margin: 0, color: 'var(--mut)', padding: '10px 12px', background: 'var(--sub)', borderRadius: 8 }}>{x.snippet || 'Önizleme yok.'}</p>
              </div>
              <div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
                  <h3 style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>Model kararı</h3>
                  <span style={{ fontSize: 12, color: 'var(--mut)' }}>{x.model}{x.latencyMs ? ` · ${(x.latencyMs / 1000).toLocaleString('tr-TR', { maximumFractionDigits: 1 })} sn` : ''}</span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--mut)', marginBottom: 12 }}>Soru: “{x.question}”</div>
                <div role="img" aria-label={'Seçenek puanları: ' + x.scores.map((o) => `${o.key} ${score(o.score)}`).join(', ')} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {x.scores.map((o) => {
                    const top = o.key === x.topKey
                    return (
                      <div key={o.key} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span style={{ flex: '0 0 60px', fontSize: 12, fontWeight: top ? 600 : 400 }}>{o.key}</span>
                        <div style={{ position: 'relative', flex: '1 1 auto' }}>
                          <Bar value={o.score} h={14} color={top ? 'var(--acc)' : 'var(--line2)'} track="var(--sub)" />
                          <div aria-hidden="true" style={{ position: 'absolute', left: Math.round(x.applyThreshold * 100) + '%', top: -3, bottom: -3, width: 0, borderLeft: '1px dashed var(--mut)' }} />
                        </div>
                        <span className="num" style={{ flex: '0 0 36px', textAlign: 'right', fontSize: 12, fontWeight: top ? 600 : 400 }}>{score(o.score)}</span>
                      </div>
                    )
                  })}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 10, fontSize: 12, color: 'var(--mut)' }}>
                  <span aria-hidden="true" style={{ width: 10, borderTop: '1px dashed var(--mut)' }} />
                  {x.ignoreThreshold === null ? `Eşik ${score(x.applyThreshold)}` : `Eşikler ${score(x.ignoreThreshold)}–${score(x.applyThreshold)}`} · {x.topScore >= x.applyThreshold
                    ? 'eşik geçildi, kural modu onay istiyor'
                    : x.ignoreThreshold === null ? 'kategori olasılığı eşiğin altında, onaya gönderildi' : '“Evet” puanı iki eşiğin arasında, onaya gönderildi'}
                </div>
              </div>
              <div>
                <h3 style={{ margin: '0 0 8px', fontSize: 13, fontWeight: 600 }}>Önerilen işlem</h3>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {x.ops.map((op) => <span key={op} style={{ fontSize: 12, fontWeight: 500, padding: '3px 9px', borderRadius: 6, background: 'var(--accSoft)', color: 'var(--accTx)' }}>{opsText([op])}</span>)}
                </div>
              </div>
              {x.status === 'pending' && (
                <>
                  {x.kind === 'category' && (
                    <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12, fontWeight: 500 }}>Kategoriyi değiştir
                      <select className="select" value={newCat} onChange={(e) => setNewCat(e.target.value)} style={{ fontWeight: 400 }}>
                        <option value="">{x.category} (model önerisi)</option>
                        {categories.filter((c) => c !== x.category).map((c) => <option key={c} value={c}>{c}</option>)}
                      </select>
                    </label>
                  )}
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button type="button" className="btn-p" disabled={busy} onClick={() => run(() => api.approve(x.id, newCat || undefined), 'Onaylanamadı')} style={{ flex: '1 1 0', height: 38 }}><Ic.Check s={15} w={2.2} />Onayla ve {dry ? 'öner' : 'uygula'}</button>
                    <button className="btn ib" type="button" disabled={busy} onClick={() => run(() => api.reject(x.id), 'Reddedilemedi')} style={{ height: 38, padding: '0 14px', color: 'var(--rd)' }}>Reddet</button>
                  </div>
                </>
              )}
              {x.status === 'error' && <div className="err-text">{x.error}</div>}
            </div>
          </aside>
        )}
      </div>
    </div>
  )
}
