import { useState, type ReactNode } from 'react'
import { api } from '../api/client'
import type { Action, CategoryStats, TodayStats } from '../api/types'
import { Bar } from '../components/Layout'
import * as Ic from '../components/Icons'
import { useApp, usePoll } from '../lib/app'
import { feedText, hhmm, initials, opsText, score, shortTime, today } from '../lib/format'

export default function Panel() {
  const { status, refreshStatus, go, toast } = useApp()
  const [stats, setStats] = useState<TodayStats | null>(null)
  const [cats, setCats] = useState<CategoryStats | null>(null)
  const [pending, setPending] = useState<Action[] | null>(null)
  const [feed, setFeed] = useState<Action[] | null>(null)
  const [decided, setDecided] = useState<Record<number, string>>({})
  const [busy, setBusy] = useState<'ol' | 'scan' | null>(null)

  const load = usePoll(async () => {
    try {
      const [s, c, q, f] = await Promise.all([api.today(), api.categories(7), api.queue(), api.feed(6)])
      setStats(s); setCats(c); setFeed(f)
      setPending(q.filter((a) => a.status === 'pending' || decided[a.id]).slice(0, 5))
    } catch { /* the status bar already reports an unreachable backend */ }
  }, 10000)

  const dry = status?.dryRun ?? true
  const decide = async (a: Action, ok: boolean) => {
    try {
      const r = ok ? await api.approve(a.id) : await api.reject(a.id)
      setDecided((d) => ({ ...d, [a.id]: r.status }))
      refreshStatus()
      load()
    } catch (e) {
      toast({ title: 'İşlem yapılamadı', sub: (e as Error).message })
    }
  }

  const undo = async (a: Action) => {
    try {
      await api.undo([a.id])
      toast({ title: `“${a.subject}” geri alındı`, sub: opsText(a.ops) + ' Gmail’den kaldırıldı', action: { label: 'Yinele', run: () => api.redo([a.id]).then(load) } })
      load()
    } catch (e) { toast({ title: 'Geri alınamadı', sub: (e as Error).message }) }
  }

  const retry = async (a: Action) => {
    try { await api.retry(a.id); load() } catch (e) { toast({ title: 'Tekrar denenemedi', sub: (e as Error).message }) }
  }

  const startModel = async () => {
    setBusy('ol')
    try { await api.startOllama() } catch (e) { toast({ title: 'Ollama başlatılamadı', sub: (e as Error).message }) }
    setTimeout(() => { setBusy(null); refreshStatus() }, 2500)
  }

  const scan = async () => {
    setBusy('scan')
    await api.scan().catch(() => undefined)
    setTimeout(() => { setBusy(null); refreshStatus(); load() }, 2000)
  }

  const ol = status?.ollama
  const olDown = !!status && (!ol?.running || !ol.modelInstalled)
  const gm = status?.gmail
  const total = cats?.items.reduce((a, c) => a + c.count, 0) ?? 0
  const max = Math.max(1, ...(cats?.items.map((c) => c.count) ?? [1]))
  const diff = stats ? stats.received - stats.yesterdayReceived : 0

  return (
    <div className="page">
      <div className="page-head">
        <div style={{ flex: '1 1 auto' }}>
          <h1>Panel</h1>
          <p>{today()} · {ol?.model ?? 'Karar modeli'} {status?.lastScan ? `son taramayı ${hhmm(status.lastScan)}'de yaptı` : 'henüz tarama yapmadı'}</p>
        </div>
        <a className="btn ib" href={api.csvUrl('7d')} style={{ color: 'var(--tx)', textDecoration: 'none' }}>Rapor indir</a>
        <button type="button" className="btn-p" onClick={scan} disabled={busy === 'scan' || !gm?.connected}>{busy === 'scan' || status?.scanning ? 'Taranıyor…' : 'Şimdi tara'}</button>
      </div>

      {olDown && (
        <section aria-label="Model durumu" className="alert">
          <div aria-hidden="true" className="alert-ic"><Ic.Chip /></div>
          <div style={{ flex: '1 1 320px', minWidth: 0 }}>
            {!ol?.running ? (
              <>
                <div style={{ fontWeight: 600, color: 'var(--rd)' }}>Ollama yanıt vermiyor</div>
                <div style={{ marginTop: 2 }}>{ol?.model} modeline <span className="mono">{ol?.url}</span> adresinden ulaşılamıyor.{' '}
                  {status!.waiting > 0 ? `Yeni gelen ${status!.waiting} e-posta sınıflandırılmayı bekliyor; ` : ''}Gmail'de hiçbir şey değişmedi.</div>
              </>
            ) : (
              <>
                <div style={{ fontWeight: 600, color: 'var(--rd)' }}>{ol.model} modeli yüklü değil</div>
                <div style={{ marginTop: 2 }}>Ollama çalışıyor ama model indirilmemiş. Terminalde <span className="mono">ollama pull {ol.model}</span> komutunu çalıştırın ya da Ayarlar'dan yüklü bir model seçin.</div>
              </>
            )}
          </div>
          <a href="#/settings" style={{ fontSize: 12, fontWeight: 500 }}>Adresi değiştir</a>
          {!ol?.running && (
            <button type="button" className="btn-p" onClick={startModel} disabled={busy === 'ol'} style={{ height: 36 }}><Ic.Play />{busy === 'ol' ? 'Başlatılıyor…' : 'Modeli başlat'}</button>
          )}
        </section>
      )}

      {status && gm?.status === 'expired' && (
        <section aria-label="Gmail bağlantısı" className="alert">
          <div aria-hidden="true" className="alert-ic"><Ic.Unlink /></div>
          <div style={{ flex: '1 1 320px', minWidth: 0 }}>
            <div style={{ fontWeight: 600, color: 'var(--rd)' }}>Gmail bağlantısı koptu</div>
            <div style={{ marginTop: 2 }}>{gm.email} için erişim izni geçersiz ya da iptal edilmiş. Etiketleme ve arşivleme duraklatıldı; yeni kararlar kuyrukta bekliyor.</div>
          </div>
          <a href="#/accounts" style={{ fontSize: 12, fontWeight: 500 }}>Hesaplara git</a>
          <a className="btn-p" href={api.connectUrl} style={{ height: 36, textDecoration: 'none' }}><Ic.Refresh />Yeniden bağlan</a>
        </section>
      )}

      {status && gm?.status === 'none' && (
        <section aria-label="Gmail bağlantısı" className="alert" style={{ background: 'var(--card)', borderColor: 'var(--line)' }}>
          <div aria-hidden="true" className="alert-ic" style={{ color: 'var(--accTx)' }}><Ic.Mail s={18} /></div>
          <div style={{ flex: '1 1 320px', minWidth: 0 }}>
            <div style={{ fontWeight: 600 }}>Henüz bağlı bir Gmail hesabı yok</div>
            <div style={{ marginTop: 2, color: 'var(--mut)' }}>credentials.json dosyanızı yükleyip Google hesabınızla yetkilendirin; ardından yeni e-postalar burada görünmeye başlar.</div>
          </div>
          <button type="button" className="btn-p" onClick={() => go('accounts')} style={{ height: 36 }}>Hesap bağla</button>
        </section>
      )}

      <div className="kpis">
        <Kpi label="Bugün gelen" value={stats?.received}
          sub={stats && <><span style={{ color: 'var(--tx)', fontWeight: 500 }}>{diff > 0 ? `↑ ${diff}` : diff < 0 ? `↓ ${-diff}` : '='}</span> {diff > 0 ? 'dünden fazla' : diff < 0 ? 'dünden az' : 'dünle aynı'} ({stats.yesterdayReceived}) · 7 günde {stats.weekReceived}</>} />
        <Kpi label="İşlenen" dot="var(--gn)" value={stats?.processed}
          sub={stats && (stats.received
            ? `Gelenlerin %${Math.round((stats.processed / stats.received) * 100)}'i · ${stats.pending} onayda, ${stats.errors} hatalı`
            : `Bugün henüz e-posta gelmedi · ${stats.pending} onayda`)} />
        <Kpi label="Onay bekleyen" dot="var(--am)" color="var(--am)" value={stats?.pending} sub={<a href="#/queue">Kuyruğu aç →</a>} />
        <Kpi label="Hata" dot="var(--rd)" color="var(--rd)" value={stats?.errors} sub={stats && (stats.lastError ?? 'Bugün hata yok')} />
      </div>

      <div className="split-2-1">
        <section className="card" style={{ minWidth: 0, overflow: 'hidden' }}>
          <div className="sec-head">
            <h2 className="h2">İşlem bekleyen e-postalar</h2>
            <span className="num count">{status?.pendingCount ?? 0}</span>
            <a href="#/queue" style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 500 }}>Tümünü gör</a>
          </div>
          <div style={{ display: 'flex', gap: 16, padding: '6px 16px', borderTop: '1px solid var(--line)', background: 'var(--sub)', fontSize: 11, fontWeight: 500, color: 'var(--mut)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            <span style={{ flex: '1 1 200px' }}>Gönderen / konu</span>
            <span style={{ flex: '0 0 150px' }}>Kategori · güven</span>
            <span style={{ flex: '0 0 170px' }}>Önerilen işlem</span>
            <span style={{ flex: '0 0 130px', textAlign: 'right' }}>Karar</span>
          </div>
          {pending && pending.length === 0 && (
            <div className="empty" style={{ borderTop: '1px solid var(--line)' }}>
              <div aria-hidden="true" className="empty-ic"><Ic.Check s={18} w={2.2} /></div>
              <div style={{ fontWeight: 600 }}>Onay bekleyen e-posta yok</div>
              <div style={{ color: 'var(--mut)', maxWidth: 360 }}>Eşiğin altında kalan yeni bir karar olduğunda burada görünecek. Son kontrol {hhmm(status?.lastScan ?? null)}.</div>
              <a href="#/rules" style={{ fontSize: 12, fontWeight: 500 }}>Kural eşiklerini gör</a>
            </div>
          )}
          {!pending && <Skeleton rows={3} />}
          {pending?.map((it) => {
            const st = decided[it.id]
            return (
              <div key={it.id} className="row" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '10px 16px', padding: '11px 16px', borderTop: '1px solid var(--line)' }}>
                <div style={{ flex: '1 1 200px', minWidth: 0, display: 'flex', gap: 10, alignItems: 'center' }}>
                  <div aria-hidden="true" style={{ flex: 'none', width: 30, height: 30, borderRadius: '50%', background: 'var(--sub)', border: '1px solid var(--line)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 600, color: 'var(--mut)' }}>{initials(it.from)}</div>
                  <div style={{ minWidth: 0 }}>
                    <div className="ellipsis" style={{ fontWeight: 500 }}>{it.from} <span className="num" style={{ color: 'var(--mut)', fontWeight: 400 }}>· {shortTime(it.receivedAt)}</span></div>
                    <div className="ellipsis" style={{ color: 'var(--mut)' }}>{it.subject}</div>
                  </div>
                </div>
                <div style={{ flex: '0 0 150px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span className="chip">{it.category}</span>
                    <span className="num" style={{ fontSize: 12, fontWeight: 600 }}>{score(it.topScore)}</span>
                  </div>
                  <Bar value={it.topScore} />
                </div>
                <div style={{ flex: '0 0 170px', fontSize: 12, fontWeight: 500 }}>{opsText(it.ops)}</div>
                <div style={{ flex: '0 0 130px', display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                  {!st && (
                    <>
                      <button className="ib" type="button" onClick={() => decide(it, true)} style={{ height: 36, padding: '0 11px', display: 'inline-flex', alignItems: 'center', gap: 5, border: '1px solid var(--line)', borderRadius: 8, background: 'var(--card)', color: 'var(--gn)', fontSize: 12, fontWeight: 600 }}><Ic.Check />{dry ? 'Öner' : 'Uygula'}</button>
                      <button className="ib" type="button" aria-label="Reddet" onClick={() => decide(it, false)} style={{ width: 36, height: 36, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', border: '1px solid var(--line)', borderRadius: 8, background: 'var(--card)', color: 'var(--rd)' }}><Ic.X /></button>
                    </>
                  )}
                  {(st === 'applied' || st === 'suggested') && <span style={{ fontSize: 12, fontWeight: 500, padding: '3px 8px', borderRadius: 6, background: 'var(--gnBg)', color: 'var(--gn)' }}>{st === 'suggested' ? 'Önerildi' : 'Uygulandı'}</span>}
                  {st === 'rejected' && <span style={{ fontSize: 12, fontWeight: 500, padding: '3px 8px', borderRadius: 6, background: 'var(--gyBg)', color: 'var(--gy)' }}>Reddedildi</span>}
                  {st === 'error' && <span style={{ fontSize: 12, fontWeight: 500, padding: '3px 8px', borderRadius: 6, background: 'var(--rdBg)', color: 'var(--rd)' }}>Hata</span>}
                </div>
              </div>
            )
          })}
        </section>

        <section className="card" style={{ minWidth: 0, padding: '14px 16px 16px' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
            <h2 className="h2">Kategori dağılımı</h2>
            <span style={{ fontSize: 12, color: 'var(--mut)' }}>7 gün</span>
            <span className="num" style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--mut)' }}>{total} e-posta</span>
          </div>
          <div role="img" aria-label={'Son 7 günde kategori dağılımı: ' + (cats?.items.map((c) => `${c.category} ${c.count}`).join(', ') ?? '')} style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 14 }}>
            {cats?.items.map((c) => (
              <div key={c.category} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ flex: '0 0 64px', fontSize: 12, color: 'var(--mut)' }}>{c.category}</span>
                <div style={{ flex: '1 1 auto' }}><Bar value={c.count / max} h={18} track="var(--sub)" /></div>
                <span className="num" style={{ flex: '0 0 64px', textAlign: 'right', fontSize: 12 }}><span style={{ fontWeight: 600 }}>{c.count}</span> <span style={{ color: 'var(--mut)' }}>%{total ? Math.round((c.count / total) * 100) : 0}</span></span>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--line)', fontSize: 12, color: 'var(--mut)' }}>
            {total && cats ? (
              <>En sık kategori <span style={{ color: 'var(--tx)', fontWeight: 500 }}>{cats.items[0].category}</span>
                {cats.archiveTotal ? `; ${cats.archiveTotal} arşivleme kararının ${cats.archiveUndone}'i geri alındı.` : '.'}</>
            ) : 'Henüz sınıflandırılan e-posta yok.'}
          </div>
        </section>
      </div>

      <section className="card" style={{ overflow: 'hidden' }}>
        <div className="sec-head">
          <h2 className="h2">Son işlemler</h2>
          <a href="#/logs" style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 500 }}>Tüm kayıtlar</a>
        </div>
        {feed && feed.length === 0 && <div style={{ padding: '20px 16px', borderTop: '1px solid var(--line)', color: 'var(--mut)', textAlign: 'center' }}>Henüz işlem yapılmadı.</div>}
        {feed?.map((f) => (
          <div key={f.id} className="row" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '6px 16px', padding: '9px 16px', borderTop: '1px solid var(--line)' }}>
            <span className="num" style={{ flex: '0 0 44px', color: 'var(--mut)', fontSize: 12 }}>{hhmm(f.updatedAt)}</span>
            <span style={{ flex: '0 0 210px', display: 'inline-flex', alignItems: 'center', gap: 8, fontWeight: 500, minWidth: 0 }}>
              <span aria-hidden="true" className="dot" style={{ background: f.status === 'error' ? 'var(--rd)' : f.status === 'applied' ? 'var(--gn)' : 'var(--gy)' }} />
              <span className="ellipsis">{feedText(f.status, f.ops, f.error)}</span>
            </span>
            <span className="ellipsis" style={{ flex: '1 1 220px', minWidth: 0 }}>{f.subject}</span>
            <span style={{ flex: '0 0 130px', fontSize: 12, color: 'var(--mut)' }}>{f.category} · <span className="num" style={{ color: 'var(--tx)' }}>{score(f.topScore)}</span></span>
            <span style={{ flex: '0 0 90px', textAlign: 'right', fontSize: 12 }}>
              {f.canUndo && <button className="lk" type="button" onClick={() => undo(f)}>Geri al</button>}
              {f.status === 'error' && <button className="lk" type="button" onClick={() => retry(f)}>Tekrar dene</button>}
              {f.status === 'suggested' && <span style={{ color: 'var(--mut)' }}>Uygulanmadı</span>}
            </span>
          </div>
        ))}
      </section>
    </div>
  )
}

function Kpi({ label, value, sub, dot, color }: { label: string; value?: number; sub?: ReactNode; dot?: string; color?: string }) {
  return (
    <div className="card" style={{ padding: '14px 16px' }}>
      <div style={{ color: 'var(--mut)', fontSize: 12, fontWeight: 500, display: 'flex', alignItems: 'center', gap: 6 }}>
        {dot && <span aria-hidden="true" className="dot" style={{ background: dot }} />}{label}
      </div>
      <div className="num" style={{ fontSize: 26, fontWeight: 600, letterSpacing: '-0.02em', marginTop: 4, color }}>{value ?? '—'}</div>
      <div style={{ fontSize: 12, color: 'var(--mut)', marginTop: 2 }}>{sub ?? ' '}</div>
    </div>
  )
}

export function Skeleton({ rows }: { rows: number }) {
  return (
    <>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} style={{ display: 'flex', gap: 12, padding: '14px 16px', borderTop: '1px solid var(--line)' }}>
          <div className="skel" style={{ width: 30, height: 30, borderRadius: '50%' }} />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div className="skel" style={{ height: 10, width: '40%' }} />
            <div className="skel" style={{ height: 10, width: '70%' }} />
          </div>
        </div>
      ))}
    </>
  )
}
