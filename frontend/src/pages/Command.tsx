import { useState, type ReactNode } from 'react'
import { api } from '../api/client'
import type { Mode, Option, Preview, Task } from '../api/types'
import * as Ic from '../components/Icons'
import { Seg } from '../components/Layout'
import { useApp, usePoll } from '../lib/app'
import { MODE_LABEL, nf, opsText } from '../lib/format'

const MODES: [Mode, string][] = [
  ['report', 'Kararları kaydeder, Gmail’e dokunmaz.'],
  ['approve', 'Her karar kuyruğa düşer, siz onaylarsınız.'],
  ['apply', 'Eşiği geçenler hemen uygulanır.'],
]

const dateFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long' })

export default function Command() {
  const { status, toast, go } = useApp()
  const [query, setQuery] = useState('in:inbox newer_than:30d')
  const [preview, setPreview] = useState<Preview | null>(null)
  const [previewErr, setPreviewErr] = useState<string | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [question, setQuestion] = useState('Bu e-posta henüz ödenmemiş bir fatura içeriyor mu?')
  const [kind, setKind] = useState<'yn' | 'list'>('yn')
  const [list, setList] = useState<Option[]>([
    { key: 'Ödenmemiş', description: '' }, { key: 'Ödenmiş', description: '' }, { key: 'Fatura değil', description: '' },
  ])
  const [th, setTh] = useState(0.8)
  const [act, setAct] = useState({ label: true, labelName: 'Ödenmemiş', star: true, archive: false, read: false })
  const [mode, setMode] = useState<Mode>('approve')
  const [tasks, setTasks] = useState<Task[]>([])
  const [dryTask, setDryTask] = useState<number | null>(null)
  const [dryScores, setDryScores] = useState<number[] | null>(null)
  const [starting, setStarting] = useState(false)
  const dry = status?.dryRun ?? true

  const options: Option[] = kind === 'yn'
    ? [{ key: 'Evet', description: `Evet: ${question}` }, { key: 'Hayır', description: `Hayır, bu durum geçerli değil: ${question}` }]
    : list.filter((o) => o.key.trim())
  const ops = [act.label && act.labelName.trim() && `label:${act.labelName.trim()}`, act.star && 'star', act.archive && 'archive', act.read && 'read']
    .filter(Boolean) as string[]

  usePoll(async () => {
    try {
      const t = await api.tasks()
      setTasks(t)
      const d = t.find((x) => x.id === dryTask)
      if (d && (d.status === 'running' || dryScores === null)) setDryScores((await api.taskScores(d.id)).scores)
    } catch { /* shown by the status bar */ }
  }, 3000, [dryTask])

  const doPreview = async () => {
    setPreviewing(true)
    try { setPreview(await api.preview(query)); setPreviewErr(null) } catch (e) { setPreview(null); setPreviewErr((e as Error).message) }
    setPreviewing(false)
  }

  const start = async (dryRun: boolean) => {
    if (options.length < 2) return toast({ title: 'En az iki seçenek gerekli' })
    if (!dryRun && !ops.length && mode !== 'report') return toast({ title: 'En az bir işlem seçin' })
    setStarting(true)
    try {
      const { id } = await api.createTask({ query, question, options, threshold: th, actions: ops, mode, dryRun })
      if (dryRun) { setDryTask(id); setDryScores(null) }
      toast({ title: dryRun ? 'Kuru çalıştırma başladı' : 'Görev başladı', sub: 'İlerlemeyi aşağıdaki listeden izleyebilirsiniz.' })
    } catch (e) {
      toast({ title: 'Görev başlatılamadı', sub: (e as Error).message })
    }
    setStarting(false)
  }

  const pass = dryScores ? dryScores.filter((s) => s >= th).length : null
  const below = dryScores && pass !== null ? dryScores.length - pass : null
  const n = dryScores?.length ?? 0
  const scope = preview?.matchCount
  const eta = scope ? Math.max(1, Math.round((scope * preview!.secondsPerEmail) / 60)) : null
  const active = tasks.filter((t) => t.status === 'running').length

  return (
    <div className="page">
      <div>
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 600, letterSpacing: '-0.015em' }}>Komut</h1>
        <p style={{ margin: '2px 0 0', color: 'var(--mut)' }}>Bir Gmail aramasını seçin, d3'e her e-posta için aynı soruyu sordurun ve cevaba göre işlem yapın.</p>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-start' }}>
        <form className="card" onSubmit={(e) => e.preventDefault()} style={{ flex: '2 1 560px', minWidth: 0, padding: '20px 20px 16px' }}>
          <Step n={1}>
            <label htmlFor="q" style={{ display: 'block', fontWeight: 600, marginBottom: 2 }}>Gmail arama sorgusu</label>
            <div style={{ fontSize: 12, color: 'var(--mut)', marginBottom: 8 }}>Gmail'in arama sözdizimi geçerli. Sorgu yalnızca okunur; hiçbir şey değişmez.</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              <input id="q" type="text" className="mono field" value={query} onChange={(e) => { setQuery(e.target.value); setPreview(null) }} style={{ flex: '1 1 320px' }} />
              <button className="btn ib" type="button" onClick={doPreview} disabled={previewing || !query.trim()} style={{ height: 36 }}>{previewing ? 'Aranıyor…' : 'Önizle'}</button>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginTop: 8, fontSize: 12, minHeight: 22 }}>
              {preview && (
                <>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '2px 8px', borderRadius: 6, background: preview.matchCount ? 'var(--gnBg)' : 'var(--gyBg)', color: preview.matchCount ? 'var(--gn)' : 'var(--gy)', fontWeight: 500 }}>
                    <Ic.Check s={12} w={2.6} /><span className="num">{nf.format(preview.matchCount)}{preview.capped ? '+' : ''}</span> e-posta eşleşti
                  </span>
                  {preview.oldest && <span style={{ color: 'var(--mut)' }}>En eskisi {dateFmt.format(new Date(preview.oldest))} · {preview.alreadyProcessed}'i daha önce işlenmiş</span>}
                  {preview.capped && <span style={{ color: 'var(--mut)' }}>Bir görev en fazla 500 e-posta işler.</span>}
                </>
              )}
              {previewErr && <span className="err-text">{previewErr}</span>}
              {!preview && !previewErr && <span style={{ color: 'var(--mut)' }}>Kaç e-postanın eşleştiğini görmek için “Önizle”ye basın.</span>}
            </div>
          </Step>

          <Step n={2}>
            <label htmlFor="soru" style={{ display: 'block', fontWeight: 600, marginBottom: 2 }}>Soru</label>
            <div style={{ fontSize: 12, color: 'var(--mut)', marginBottom: 8 }}>d3 bu soruyu e-postanın gönderen, konu ve gövdesiyle birlikte değerlendirir.</div>
            <textarea id="soru" rows={2} value={question} onChange={(e) => setQuestion(e.target.value)} style={{ width: '100%', padding: '8px 10px', border: '1px solid var(--line)', borderRadius: 8, background: 'var(--card)', resize: 'vertical' }} />
          </Step>

          <Step n={3}>
            <div style={{ fontWeight: 600, marginBottom: 8 }}>Seçenekler</div>
            <div style={{ marginBottom: 10 }}>
              <Seg inset label="Seçenek türü" value={kind} onChange={setKind} items={[{ key: 'yn', label: 'Evet / Hayır' }, { key: 'list', label: 'Liste' }]} />
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
              {kind === 'yn' && options.map((o, i) => <OptChip key={o.key} k={String.fromCharCode(65 + i)}>{o.key}</OptChip>)}
              {kind === 'list' && list.map((o, i) => (
                <OptChip key={i} k={String.fromCharCode(65 + i)}>
                  <input aria-label={`Seçenek ${i + 1}`} value={o.key} maxLength={40}
                    onChange={(e) => setList((l) => l.map((x, j) => (j === i ? { ...x, key: e.target.value } : x)))}
                    style={{ width: Math.max(4, o.key.length + 1) + 'ch', border: 0, outline: 'none', background: 'transparent', fontWeight: 500, padding: 0 }} />
                  {list.length > 2 && <button type="button" aria-label="Seçeneği kaldır" onClick={() => setList((l) => l.filter((_, j) => j !== i))} style={{ border: 0, background: 'transparent', color: 'var(--mut)', padding: 0, display: 'inline-flex' }}><Ic.X s={12} /></button>}
                </OptChip>
              ))}
              {kind === 'list' && list.length < 8 && (
                <button className="ib" type="button" onClick={() => setList((l) => [...l, { key: 'Yeni seçenek', description: '' }])} style={{ height: 30, padding: '0 10px', border: '1px dashed var(--line2)', borderRadius: 7, background: 'transparent', color: 'var(--mut)', fontWeight: 500 }}>+ Seçenek ekle</button>
              )}
            </div>
          </Step>

          <Step n={4}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 2 }}>
              <label htmlFor="esik" style={{ fontWeight: 600 }}>Güven eşiği</label>
              <span className="num" style={{ marginLeft: 'auto', fontSize: 15, fontWeight: 600 }}>{th.toFixed(2)}</span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--mut)', marginBottom: 8 }}>Puanı bu değerin altında kalan kararlar uygulanmaz, Onay Kuyruğu'na düşer.</div>
            <input id="esik" type="range" min={0.5} max={0.99} step={0.01} value={th} onChange={(e) => setTh(Number(e.target.value))} style={{ width: '100%' }} />
            <div className="num" style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--mut)' }}><span>0.50</span><span>0.75</span><span>0.99</span></div>
            <div style={{ display: 'flex', height: 6, borderRadius: 3, overflow: 'hidden', marginTop: 10, background: 'var(--bar)' }}>
              {n > 0 && pass !== null && <><div style={{ background: 'var(--acc)', width: (pass / n) * 100 + '%' }} /><div style={{ background: 'var(--am)', width: (below! / n) * 100 + '%' }} /></>}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, marginTop: 6, fontSize: 12, color: 'var(--mut)' }}>
              {dryScores ? (
                <>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><span aria-hidden="true" style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--acc)' }} />Eşiği geçen <span className="num" style={{ color: 'var(--tx)', fontWeight: 600 }}>{pass}</span></span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><span aria-hidden="true" style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--am)' }} />Onaya düşecek <span className="num" style={{ color: 'var(--tx)', fontWeight: 600 }}>{below}</span></span>
                  <span>Kuru çalıştırmadaki {n} karara göre</span>
                </>
              ) : (
                <span>Eşiği geçecek ve onaya düşecek sayılar, kuru çalıştırma sonuçlarından hesaplanır.</span>
              )}
            </div>
          </Step>

          <Step n={5}>
            <div style={{ fontWeight: 600, marginBottom: 2 }}>İşlem</div>
            <div style={{ fontSize: 12, color: 'var(--mut)', marginBottom: 10 }}>Model <span style={{ color: 'var(--tx)', fontWeight: 500 }}>“{options[0]?.key ?? '—'}”</span> derse:</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 8 }}>
              <ActBox on={act.label} toggle={() => setAct({ ...act, label: !act.label })} label="Etiket ekle">
                <input aria-label="Etiket adı" className="mono" value={act.labelName} onChange={(e) => setAct({ ...act, labelName: e.target.value })} onClick={(e) => e.stopPropagation()}
                  style={{ width: 110, padding: '1px 6px', borderRadius: 4, border: 0, background: 'var(--sub)', outline: 'none' }} />
              </ActBox>
              <ActBox on={act.star} toggle={() => setAct({ ...act, star: !act.star })} label="Yıldızla" />
              <ActBox on={act.archive} toggle={() => setAct({ ...act, archive: !act.archive })} label="Arşivle" />
              <ActBox on={act.read} toggle={() => setAct({ ...act, read: !act.read })} label="Okundu işaretle" />
            </div>
          </Step>

          <Step n={6} last>
            <fieldset style={{ margin: 0, padding: 0, border: 0 }}>
              <legend style={{ padding: 0, fontWeight: 600, marginBottom: 10 }}>Mod</legend>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8 }}>
                {MODES.map(([id, desc]) => (
                  <label key={id} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', padding: 12, border: `1px solid ${mode === id ? 'var(--acc)' : 'var(--line)'}`, borderRadius: 8, background: mode === id ? 'var(--accSoft)' : 'var(--card)', cursor: 'pointer' }}>
                    <input type="radio" name="mod" checked={mode === id} onChange={() => setMode(id)} style={{ marginTop: 2 }} />
                    <span><span style={{ display: 'block', fontWeight: 500 }}>{MODE_LABEL[id]}</span><span style={{ display: 'block', fontSize: 12, color: 'var(--mut)', marginTop: 2 }}>{desc}</span></span>
                  </label>
                ))}
              </div>
            </fieldset>
          </Step>

          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, paddingTop: 14, borderTop: '1px solid var(--line)' }}>
            {dry && <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--mut)' }}><Ic.Dashed />Kuru mod açık: görev Gmail'e hiçbir şey yazmaz</span>}
            <button className="btn ib" type="button" disabled={starting || !query.trim()} onClick={() => start(true)} style={{ marginLeft: 'auto', height: 36, padding: '0 14px' }}>Kuru çalıştır</button>
            <button type="button" className="btn-p" disabled={starting || !query.trim()} onClick={() => start(false)} style={{ height: 36, padding: '0 16px' }}><Ic.Play s={13} />Görevi başlat</button>
          </div>
        </form>

        <aside aria-label="Görev özeti" className="card" style={{ flex: '1 1 280px', minWidth: 0, padding: 16 }}>
          <h2 className="h2" style={{ marginBottom: 12 }}>Görev özeti</h2>
          <dl style={{ margin: 0, display: 'grid', gridTemplateColumns: 'auto minmax(0, 1fr)', gap: '10px 14px', fontSize: 12 }}>
            <Dt>Kapsam</Dt><Dd>{scope !== undefined ? `${nf.format(scope)} e-posta` : 'Önizlenmedi'}</Dd>
            <Dt>Model</Dt><Dd>{status?.ollama.model ?? '—'} (yerel)</Dd>
            <Dt>Seçenekler</Dt><Dd>{options.map((o) => o.key).join(' / ')}</Dd>
            <Dt>Eşik</Dt><Dd>{th.toFixed(2)}</Dd>
            <Dt>İşlem</Dt><Dd>{ops.length ? opsText(ops) : 'İşlem seçilmedi'}</Dd>
            <Dt>Mod</Dt><Dd>{MODE_LABEL[mode]}</Dd>
            <Dt>Tahmini süre</Dt><Dd>{eta ? `~${eta} dk` : '—'}</Dd>
          </dl>
        </aside>
      </div>

      <section className="card" style={{ overflow: 'hidden' }}>
        <div className="sec-head">
          <h2 className="h2">Görevler</h2>
          {active > 0 && <span className="num" style={{ fontSize: 11, fontWeight: 600, padding: '1px 7px', borderRadius: 10, background: 'var(--accSoft)', color: 'var(--accTx)' }}>{active} aktif</span>}
        </div>
        {tasks.length === 0 && <div style={{ padding: '20px 16px', borderTop: '1px solid var(--line)', color: 'var(--mut)', textAlign: 'center' }}>Henüz görev başlatılmadı.</div>}
        {tasks.map((t) => <TaskRow key={t.id} t={t} onLogs={() => go('logs')} />)}
      </section>
    </div>
  )
}

function TaskRow({ t, onLogs }: { t: Task; onLogs: () => void }) {
  const { toast } = useApp()
  const [st, fg] = {
    running: ['Çalışıyor', 'var(--accTx)'],
    paused: ['Duraklatıldı', 'var(--mut)'],
    done: ['Tamamlandı', 'var(--gn)'],
    error: ['Hata: ' + (t.error ?? ''), 'var(--rd)'],
  }[t.status]
  const bar = t.status === 'running' ? 'var(--acc)' : t.status === 'done' ? 'var(--gn)' : t.status === 'error' ? 'var(--rd)' : 'var(--line2)'
  const act = async (fn: () => Promise<unknown>) => { try { await fn() } catch (e) { toast({ title: 'İşlem yapılamadı', sub: (e as Error).message }) } }
  const btn = {
    running: ['Duraklat', () => act(() => api.pauseTask(t.id))],
    paused: ['Devam et', () => act(() => api.resumeTask(t.id))],
    error: ['Tekrar dene', () => act(() => api.resumeTask(t.id))],
    done: ['Raporu aç', onLogs],
  }[t.status] as [string, () => void]
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px 20px', padding: '12px 16px', borderTop: '1px solid var(--line)' }}>
      <div style={{ flex: '1 1 260px', minWidth: 0 }}>
        <div className="ellipsis" style={{ fontWeight: 500 }}>{t.name}</div>
        <div className="mono ellipsis" style={{ color: 'var(--mut)' }}>{t.query}</div>
      </div>
      <span style={{ flex: '0 0 130px', fontSize: 12, color: 'var(--mut)' }}>{t.dryRun ? 'Kuru çalıştırma' : MODE_LABEL[t.mode]}</span>
      <div style={{ flex: '1 1 220px', minWidth: 160 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 12, marginBottom: 5 }}>
          <span className="ellipsis" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: fg, fontWeight: 500, minWidth: 0 }}><span aria-hidden="true" className="dot" style={{ background: fg }} />{st}</span>
          <span className="num" style={{ color: 'var(--mut)', whiteSpace: 'nowrap' }}>{t.processed} / {t.total || '?'}</span>
        </div>
        <div role="progressbar" aria-label={`${t.name} ilerlemesi`} aria-valuemin={0} aria-valuemax={t.total} aria-valuenow={t.processed} style={{ height: 6, borderRadius: 3, background: 'var(--bar)' }}>
          <div style={{ height: 6, borderRadius: 3, background: bar, width: t.total ? Math.round((t.processed / t.total) * 100) + '%' : '0%' }} />
        </div>
      </div>
      <div style={{ flex: '0 0 auto', display: 'flex', gap: 6 }}>
        <button className="btn ib" type="button" onClick={btn[1]} style={{ height: 32, padding: '0 10px', fontSize: 12, borderRadius: 7 }}>{btn[0]}</button>
      </div>
    </div>
  )
}

function Step({ n, last, children }: { n: number; last?: boolean; children: ReactNode }) {
  return (
    <div style={{ display: 'flex', gap: 14 }}>
      <div aria-hidden="true" style={{ flex: 'none', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <span className="num" style={{ width: 24, height: 24, borderRadius: '50%', background: 'var(--btn)', color: '#FFFFFF', fontSize: 12, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{n}</span>
        {!last && <span style={{ flex: '1 1 auto', width: 1, background: 'var(--line)', margin: '4px 0' }} />}
      </div>
      <div style={{ flex: '1 1 auto', minWidth: 0, paddingBottom: last ? 18 : 22 }}>{children}</div>
    </div>
  )
}

function OptChip({ k, children }: { k: string; children: ReactNode }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 30, padding: '0 10px', border: '1px solid var(--line2)', borderRadius: 7, fontWeight: 500 }}>
      <span className="num" style={{ fontSize: 11, color: 'var(--mut)' }}>{k}</span>{children}
    </span>
  )
}

function ActBox({ on, toggle, label, children }: { on: boolean; toggle: () => void; label: string; children?: ReactNode }) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: 10, minHeight: 44, padding: '8px 12px', border: `1px solid ${on ? 'var(--acc)' : 'var(--line)'}`, borderRadius: 8, background: on ? 'var(--accSoft)' : 'var(--card)' }}>
      <input type="checkbox" checked={on} onChange={toggle} /><span style={{ flex: '1 1 auto' }}>{label}</span>{children}
    </label>
  )
}

const Dt = ({ children }: { children: ReactNode }) => <dt style={{ color: 'var(--mut)' }}>{children}</dt>
const Dd = ({ children }: { children: ReactNode }) => <dd className="num" style={{ margin: 0, fontWeight: 500 }}>{children}</dd>
