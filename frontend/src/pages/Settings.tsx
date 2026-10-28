import { useEffect, useState, type ReactNode } from 'react'
import { api } from '../api/client'
import type { ModelInfo, Settings as S } from '../api/types'
import { Seg, Switch } from '../components/Layout'
import { useApp } from '../lib/app'
import { nf } from '../lib/format'

const INTERVALS: [number, string][] = [[1, '1 dk'], [5, '5 dk'], [15, '15 dk'], [30, '30 dk'], [60, '1 saat']]
// From the model tests on real e-mail (Ollama 0.40.11); see CLAUDE.md.
const DESC: Record<string, string> = {
  'tev1:4b': 'Önerilen. ~2,3 sn/karar, 5,7 GB bellek; testlerde hiç çökmedi.',
  'd3:9b': 'Doğrulukta tev1:4b ile eşit. ~2,8 sn/karar, 10 GB bellek; kısa tanıtım e-postalarında kararsız kalabiliyor.',
  'tev1:0.8b': 'Önerilmez: testlerde “acil” sorusunu sistematik olarak yanlış tetikledi.',
}
const KIND_DESC = {
  decision: 'Karar modeli; seçeneklere doğrudan olasılık verir.',
  chat: 'Genel sohbet modeli; yedek yöntemle (JSON puan) çalışır, karar modellerinden yavaş ve daha az tutarlıdır.',
}
type Editable = Omit<S, 'dryRun'>
const KEYS: (keyof Editable)[] = ['model', 'ollamaUrl', 'pollMinutes', 'maxChars', 'onlyUnread', 'stripQuotes']

export default function Settings() {
  const { status, refreshStatus, toast } = useApp()
  const [saved, setSaved] = useState<S | null>(null)
  const [form, setForm] = useState<Editable | null>(null)
  const [models, setModels] = useState<ModelInfo[]>([])
  const [test, setTest] = useState<{ state: 'idle' | 'busy' | 'ok' | 'fail'; text?: string }>({ state: 'idle' })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.settings().then((s) => { setSaved(s); setForm(s) }).catch((e) => toast({ title: 'Ayarlar yüklenemedi', sub: e.message }))
    api.models().then(setModels).catch(() => setModels([]))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (!saved || !form) return <div className="page"><h1 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>Ayarlar</h1></div>

  const dirty = KEYS.some((k) => form[k] !== saved[k])
  const set = <K extends keyof Editable>(k: K, v: Editable[K]) => setForm({ ...form, [k]: v })
  const dry = saved.dryRun

  const toggleDry = async () => {
    try { const r = await api.saveSettings({ dryRun: !dry }); setSaved({ ...saved, dryRun: r.dryRun }); refreshStatus() } catch (e) { toast({ title: 'Kuru mod değiştirilemedi', sub: (e as Error).message }) }
  }

  const save = async () => {
    setSaving(true)
    try {
      const s = await api.saveSettings(form)
      setSaved(s); setForm(s); refreshStatus()
      toast({ title: 'Ayarlar kaydedildi' })
    } catch (e) { toast({ title: 'Kaydedilemedi', sub: (e as Error).message }) }
    setSaving(false)
  }

  const runTest = async () => {
    setTest({ state: 'busy' })
    try {
      const r = await api.testOllama(form.ollamaUrl)
      if (!r.ok) return setTest({ state: 'fail', text: 'Bağlanılamadı · ' + (r.error ?? 'yanıt yok') })
      setTest({ state: 'ok', text: `Bağlandı · Ollama ${r.version ?? ''} · ${r.decision.length ? 'karar modelleri: ' + r.decision.join(', ') : 'karar modeli bulunamadı'}` })
    } catch (e) { setTest({ state: 'fail', text: (e as Error).message }) }
  }

  const [testFg, testTxt] = {
    idle: status?.ollama.running ? ['var(--gn)', `Bağlı · Ollama ${status.ollama.version ?? ''}`] : ['var(--rd)', 'Bağlı değil'],
    busy: ['var(--mut)', 'Bağlantı deneniyor…'],
    ok: ['var(--gn)', test.text],
    fail: ['var(--rd)', test.text],
  }[test.state] as [string, string]

  return (
    <div className="page" style={{ gap: 16 }}>
      <div>
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 600, letterSpacing: '-0.015em' }}>Ayarlar</h1>
        <p style={{ margin: '2px 0 0', color: 'var(--mut)' }}>Tüm ayarlar bu cihazda saklanır.</p>
      </div>

      <div className="split-form">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>
      <section aria-labelledby="h-model" className="card">
        <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--line)' }}><h2 id="h-model" className="h2">Karar modeli</h2></div>
        <Row title="Model" hint="Ollama'da yüklü modeller. “Karar modeli” işaretliler (d3, tev1) önerilir; diğerleri yedek yöntemle (sohbet + JSON puan) çalışır.">
          {models.length === 0 && <span style={{ fontSize: 12, color: 'var(--mut)' }}>Ollama'ya ulaşılamadığı için model listesi alınamadı.</span>}
          <fieldset style={{ margin: 0, padding: 0, border: 0, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 8 }}>
            <legend className="sr">Model seçimi</legend>
            {models.map((m) => {
              const on = form.model === m.name
              return (
                <label key={m.name} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', padding: 12, border: `1px solid ${on ? 'var(--acc)' : 'var(--line)'}`, borderRadius: 8, background: on ? 'var(--accSoft)' : 'var(--card)', cursor: 'pointer' }}>
                  <input type="radio" name="model" checked={on} onChange={() => set('model', m.name)} style={{ marginTop: 2 }} />
                  <span style={{ flex: '1 1 auto', minWidth: 0 }}>
                    <span style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
                      <span className="mono" style={{ fontWeight: 500, fontSize: 13 }}>{m.name}</span>
                      {m.kind === 'decision' && <span className="badge" style={{ padding: '0 6px', borderRadius: 4, background: 'var(--accSoft)', color: 'var(--accTx)' }}>Karar modeli</span>}
                      {!m.installed && <span className="badge" style={{ padding: '0 6px', borderRadius: 4, background: 'var(--rdBg)', color: 'var(--rd)' }}>Yüklü değil</span>}
                    </span>
                    <span style={{ display: 'block', fontSize: 12, color: 'var(--mut)', marginTop: 3 }}>
                      {DESC[m.name] ?? KIND_DESC[m.kind]}
                      {!m.installed && <> İndirmek için: <span className="mono" style={{ fontSize: 11 }}>ollama pull {m.name}</span></>}
                    </span>
                  </span>
                </label>
              )
            })}
          </fieldset>
        </Row>
        <Row last title="Ollama adresi" htmlFor="ol" hint="Ollama sunucusunun çalıştığı adres. Başka bir makinedeyse onun yerel ağ adresini yazın.">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              <input id="ol" type="text" className="mono field" value={form.ollamaUrl} onChange={(e) => { set('ollamaUrl', e.target.value); setTest({ state: 'idle' }) }} style={{ flex: '1 1 240px' }} />
              <button className="btn ib" type="button" onClick={runTest} disabled={test.state === 'busy'} style={{ height: 36 }}>{test.state === 'busy' ? 'Deneniyor…' : 'Bağlantıyı test et'}</button>
            </div>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: testFg }}><span aria-hidden="true" className="dot" style={{ background: testFg }} />{testTxt}</span>
          </div>
        </Row>
      </section>

      <section aria-labelledby="h-gm" className="card">
        <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--line)' }}><h2 id="h-gm" className="h2">Gmail ve içerik</h2></div>
        <Row title="Kontrol aralığı" hint="Yeni e-postaların ne sıklıkla çekileceği. Kısa aralık daha çok Gmail API isteği demektir.">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ alignSelf: 'flex-start' }}>
              <Seg inset label="Kontrol aralığı" value={String(form.pollMinutes)} onChange={(v) => set('pollMinutes', Number(v))} items={INTERVALS.map(([v, l]) => ({ key: String(v), label: l }))} />
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}><input type="checkbox" checked={form.onlyUnread} onChange={() => set('onlyUnread', !form.onlyUnread)} />Yalnızca Gelen Kutusu'ndaki okunmamış e-postaları işle</label>
          </div>
        </Row>
        <Row last title="Modele gönderilecek uzunluk" htmlFor="len" hint="Konu ve gönderen her zaman gider; gövde bu sınırda kesilir. Uzun sınır daha çok bağlam, daha yavaş karar demektir.">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}><span className="num" style={{ fontSize: 15, fontWeight: 600 }}>{nf.format(form.maxChars)}</span><span style={{ color: 'var(--mut)', fontSize: 12 }}>karakter · ≈ {nf.format(Math.round(form.maxChars / 4))} token</span></div>
            <input id="len" type="range" min={500} max={8000} step={500} value={form.maxChars} onChange={(e) => set('maxChars', Number(e.target.value))} style={{ width: '100%' }} />
            <div className="num" style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--mut)' }}><span>500</span><span>4.000</span><span>8.000</span></div>
            {form.maxChars > 6000 && form.model.startsWith('d3') && <span style={{ fontSize: 12, color: 'var(--am)' }}>d3 paketleri 4.096 token bağlamla çalışır; çok uzun gövdeler kesilebilir.</span>}
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, marginTop: 4 }}><input type="checkbox" checked={form.stripQuotes} onChange={() => set('stripQuotes', !form.stripQuotes)} />Alıntılanan eski yanıtları ve imzaları çıkar</label>
          </div>
        </Row>
      </section>
      </div>

      {/* Side column: the dry-mode switch and the save bar stay in view next to the forms. */}
      <div className="side">
        <section aria-labelledby="h-dry" className="card" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '12px 20px', padding: '16px 18px', borderColor: dry ? 'var(--line2)' : 'var(--line)' }}>
          <div style={{ flex: '1 1 200px', minWidth: 0 }}>
            <h2 id="h-dry" className="h2" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>Genel kuru mod
              <span className="badge" style={{ background: dry ? 'var(--gyBg)' : 'var(--gnBg)', color: dry ? 'var(--gy)' : 'var(--gn)' }}>{dry ? 'Açık' : 'Kapalı — işlemler uygulanıyor'}</span>
            </h2>
            <p style={{ margin: '4px 0 0', color: 'var(--mut)' }}>Açıkken model kararlarını vermeye ve kaydetmeye devam eder, ama hiçbir etiket, arşiv ya da yıldız Gmail'e yazılmaz. Onay düğmeleri “Uygula” yerine “Öner” olur. Yeni kuralları denerken açık tutun. Anahtar kaydetmeyi beklemez; tüm ekranlara hemen uygulanır.</p>
          </div>
          <Switch big on={dry} label="Genel kuru mod" track="var(--gy)" onClick={toggleDry} />
        </section>

        <div className="card" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10, padding: '12px 16px' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 500, color: dirty ? 'var(--am)' : 'var(--mut)' }}><span aria-hidden="true" className="dot" style={{ background: dirty ? 'var(--am)' : 'var(--mut)' }} />{dirty ? 'Kaydedilmemiş değişiklikler var' : 'Tüm değişiklikler kaydedildi'}</span>
          <button className="btn ib" type="button" onClick={() => setForm(saved)} disabled={!dirty} style={{ marginLeft: 'auto' }}>Vazgeç</button>
          <button type="button" className="btn-p" onClick={save} disabled={!dirty || saving} style={{ padding: '0 16px' }}>{saving ? 'Kaydediliyor…' : 'Kaydet'}</button>
        </div>
      </div>
      </div>
    </div>
  )
}

function Row({ title, hint, htmlFor, last, children }: { title: string; hint: string; htmlFor?: string; last?: boolean; children: ReactNode }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px 24px', padding: '16px 18px', borderBottom: last ? undefined : '1px solid var(--line)' }}>
      <div style={{ flex: '1 1 240px' }}>
        {htmlFor ? <label htmlFor={htmlFor} style={{ fontWeight: 500 }}>{title}</label> : <div style={{ fontWeight: 500 }}>{title}</div>}
        <div style={{ fontSize: 12, color: 'var(--mut)', marginTop: 2 }}>{hint}</div>
      </div>
      <div style={{ flex: '2 1 400px', minWidth: 0 }}>{children}</div>
    </div>
  )
}
