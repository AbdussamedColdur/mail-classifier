import { useState } from 'react'
import { api } from '../api/client'
import type { Category, CategoryStats, Mode, Rule, RuleInput, RuleKind } from '../api/types'
import * as Ic from '../components/Icons'
import { Bar, Seg, Switch, ThresholdSlider, thText } from '../components/Layout'
import { useApp, useAsync, usePoll } from '../lib/app'
import { MODE_COLORS, MODE_LABEL, opsText } from '../lib/format'

const TABS = ['Tümü', 'Etkin', 'Kapalı', 'Dikkat'] as const
const scopeText = (r: Rule) => (r.kind === 'category' ? 'Kategori: ' + r.category : r.category ? `Evet/hayır · yalnızca ${r.category}` : 'Kategoriden bağımsız')
const ratio = (r: Rule) => (r.stats7d.triggered ? r.stats7d.undone / r.stats7d.triggered : 0)
const needsCare = (r: Rule) => r.enabled && r.stats7d.triggered > 0 && ratio(r) >= 0.2

export default function Rules() {
  const { toast } = useApp()
  const categories = useAsync(api.categoryList).data ?? []
  const [rules, setRules] = useState<Rule[] | null>(null)
  const [cats, setCats] = useState<CategoryStats | null>(null)
  const [tab, setTab] = useState<(typeof TABS)[number]>('Tümü')
  const [editing, setEditing] = useState<Rule | 'new' | null>(null)
  const [menu, setMenu] = useState<number | null>(null)
  const [confirmDel, setConfirmDel] = useState<number | null>(null)

  const load = usePoll(async () => {
    try {
      const [r, c] = await Promise.all([api.rules(), api.categories(7)])
      setRules(r); setCats(c)
    } catch { /* shown by the status bar */ }
  }, 30000)

  const patch = async (r: Rule, p: Partial<RuleInput>) => {
    try {
      const updated = await api.patchRule(r.id, p)
      setRules((rs) => rs?.map((x) => (x.id === r.id ? updated : x)) ?? null)
    } catch (e) { toast({ title: 'Kural güncellenemedi', sub: (e as Error).message }) }
  }

  const remove = async (r: Rule) => {
    try { await api.deleteRule(r.id); toast({ title: `“${r.name}” silindi` }); load() } catch (e) { toast({ title: 'Silinemedi', sub: (e as Error).message }) }
    setMenu(null); setConfirmDel(null)
  }

  const all = rules ?? []
  const pass: Record<(typeof TABS)[number], (r: Rule) => boolean> = { 'Tümü': () => true, 'Etkin': (r) => r.enabled, 'Kapalı': (r) => !r.enabled, 'Dikkat': needsCare }
  const trig = all.reduce((a, r) => a + r.stats7d.triggered, 0)
  const undone = all.reduce((a, r) => a + r.stats7d.undone, 0)
  const classified = cats?.items.reduce((a, c) => a + c.count, 0) ?? 0

  return (
    <div className="page" style={{ gap: 16 }}>
      <div className="page-head">
        <div style={{ flex: '1 1 auto' }}>
          <h1>Kurallar</h1>
          <p>Her gelen e-posta etkin kurallardan geçer; karar modeli her kuralın sorusunu yanıtlar ve eşiği geçen işlem uygulanır.</p>
        </div>
        <button type="button" className="btn-p" onClick={() => setEditing('new')}><Ic.Plus />Yeni kural</button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
        <Stat label="Etkin kural" value={all.filter((r) => r.enabled).length} unit={`/ ${all.length}`} />
        <Stat label="Sınıflandırılan · 7 gün" value={classified} unit="e-posta" sub={cats?.items.filter((c) => c.count).map((c) => `${c.category} ${c.count}`).join(' · ')} />
        <Stat label="Geri alınan · 7 gün" value={undone} unit={trig ? `%${Math.round((undone / trig) * 100)}` : ''} />
        <div className="card" style={{ background: 'var(--amBg)', padding: '12px 16px' }}>
          <div style={{ fontSize: 12, color: 'var(--am)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}><Ic.Warn />Dikkat isteyen</div>
          <div className="num" style={{ fontSize: 22, fontWeight: 600, marginTop: 2, color: 'var(--am)' }}>{all.filter(needsCare).length} <span style={{ fontSize: 13, fontWeight: 400 }}>kural</span></div>
        </div>
      </div>

      {editing && <RuleEditor rule={editing === 'new' ? null : editing} categories={categories} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load() }} />}

      <div role="group" aria-label="Kural filtresi" className="seg" style={{ alignSelf: 'flex-start' }}>
        {TABS.map((t) => (
          <button key={t} type="button" aria-pressed={tab === t} onClick={() => setTab(t)}>{t} <span className="num" style={{ color: 'var(--mut)' }}>{all.filter(pass[t]).length}</span></button>
        ))}
      </div>

      <section aria-label="Kural listesi" className="card" style={{ overflow: 'visible' }}>
        <div style={{ display: 'flex', gap: 16, padding: '7px 16px', background: 'var(--sub)', borderBottom: '1px solid var(--line)', borderRadius: '10px 10px 0 0', fontSize: 11, fontWeight: 500, color: 'var(--mut)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          <span style={{ flex: '0 0 44px' }}>Etkin</span>
          <span style={{ flex: '1 1 300px' }}>Kural / soru</span>
          <span style={{ flex: '0 0 80px' }}>Eşik</span>
          <span style={{ flex: '0 0 160px' }}>İşlem</span>
          <span style={{ flex: '0 0 130px' }}>Mod</span>
          <span style={{ flex: '0 0 44px' }} title="Kuru: Gmail'e yazmaz, yalnızca önerir">Kuru</span>
          <span style={{ flex: '0 0 170px' }}>Son 7 gün</span>
          <span style={{ flex: '0 0 32px' }} />
        </div>
        {rules && all.filter(pass[tab]).length === 0 && <div style={{ padding: '24px 16px', textAlign: 'center', color: 'var(--mut)' }}>Bu filtrede kural yok.</div>}
        {all.filter(pass[tab]).map((r) => {
          const warn = needsCare(r)
          const op = r.enabled ? 1 : 0.5
          const [mBg, mFg] = MODE_COLORS[r.mode]
          const next = Math.min(0.95, r.applyThreshold + 0.1)
          const uFg = warn ? 'var(--am)' : 'var(--mut)'
          return (
            <div key={r.id} className="row" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '10px 16px', padding: '12px 16px', borderBottom: '1px solid var(--line)', position: 'relative' }}>
              <span style={{ flex: '0 0 44px' }}><Switch on={r.enabled} label={r.name + (r.enabled ? ' kuralını kapat' : ' kuralını aç')} onClick={() => patch(r, { enabled: !r.enabled })} /></span>
              <div style={{ flex: '1 1 300px', minWidth: 0, opacity: op }}>
                <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontWeight: 600 }}>{r.name}</span>
                  <span style={{ fontSize: 11, fontWeight: 500, padding: '0 6px', border: '1px solid var(--line2)', borderRadius: 4, color: 'var(--mut)' }}>{scopeText(r)}</span>
                </div>
                <div className="ellipsis" style={{ color: 'var(--mut)' }}>“{r.question}”</div>
              </div>
              <span className="num" title={r.ignoreThreshold === null ? 'Uygulama eşiği' : 'Görmezden gelme – uygulama eşiği'} style={{ flex: '0 0 80px', fontWeight: 600, opacity: op }}>{thText(r.applyThreshold, r.ignoreThreshold)}</span>
              <span style={{ flex: '0 0 160px', fontSize: 12, fontWeight: 500, opacity: op }}>{opsText(r.actions)}</span>
              <span style={{ flex: '0 0 130px', opacity: op }}><span className="badge" style={{ padding: '2px 8px', background: mBg, color: mFg }}>{MODE_LABEL[r.mode]}</span></span>
              <span style={{ flex: '0 0 44px', opacity: op }}><Switch on={r.dryRun} label={r.name + (r.dryRun ? ' kuralının kuru modunu kapat' : ' kuralını kuru moda al')} onClick={() => patch(r, { dryRun: !r.dryRun })} /></span>
              <div style={{ flex: '0 0 170px', opacity: op }}>
                {r.stats7d.triggered > 0 ? (
                  <>
                    <div style={{ fontSize: 12 }}><span className="num" style={{ fontWeight: 600 }}>{r.stats7d.triggered}</span> <span style={{ color: 'var(--mut)' }}>tetiklenme ·</span> <span className="num" style={{ fontWeight: 600, color: uFg }}>{r.stats7d.undone}</span> <span style={{ color: uFg }}>geri alındı</span></div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 5 }}>
                      <div style={{ flex: '1 1 auto' }}><Bar value={Math.max(0.02, ratio(r))} color={warn ? 'var(--am)' : 'var(--line2)'} /></div>
                      <span className="num" style={{ fontSize: 11, color: uFg, fontWeight: warn ? 600 : 400 }}>%{Math.round(ratio(r) * 100)}</span>
                    </div>
                  </>
                ) : <span style={{ fontSize: 12, color: 'var(--mut)' }}>{r.enabled ? 'Son 7 günde tetiklenmedi' : 'Kapalıyken tetiklenmedi'}</span>}
              </div>
              <span style={{ flex: '0 0 32px', position: 'relative' }}>
                <button className="ib" type="button" aria-label={r.name + ' için seçenekler'} aria-expanded={menu === r.id} onClick={() => { setMenu(menu === r.id ? null : r.id); setConfirmDel(null) }}
                  style={{ width: 32, height: 32, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', border: '1px solid transparent', borderRadius: 7, background: 'transparent', color: 'var(--mut)' }}><Ic.Dots /></button>
                {menu === r.id && (
                  <div role="menu" className="card" style={{ position: 'absolute', right: 0, top: 36, zIndex: 5, minWidth: 170, padding: 4, boxShadow: '0 8px 24px rgba(0,0,0,0.12)' }}>
                    <button role="menuitem" type="button" className="nav" onClick={() => { setEditing(r); setMenu(null) }} style={menuItem}>Düzenle</button>
                    {confirmDel === r.id
                      ? <button role="menuitem" type="button" className="nav" onClick={() => remove(r)} style={{ ...menuItem, color: 'var(--rd)', fontWeight: 600 }}>Silmeyi onayla</button>
                      : <button role="menuitem" type="button" className="nav" onClick={() => setConfirmDel(r.id)} style={{ ...menuItem, color: 'var(--rd)' }}>Sil</button>}
                  </div>
                )}
              </span>
              {warn && (
                <div style={{ flex: '1 1 100%', display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px 12px', marginLeft: 60, padding: '8px 12px', borderRadius: 8, background: 'var(--amBg)', color: 'var(--am)', fontSize: 12 }}>
                  <Ic.Warn s={14} />
                  <span style={{ flex: '1 1 280px', fontWeight: 500 }}>Bu kuralın kararlarının %{Math.round(ratio(r) * 100)}'i geri alındı. Eşiği {next.toFixed(2)}'e yükseltmeyi ya da modu “Onaya gönder” yapmayı düşünün.</span>
                  <button type="button" onClick={() => patch(r, { applyThreshold: Number(next.toFixed(2)) })} style={warnBtn}>Eşiği {next.toFixed(2)} yap</button>
                  {r.mode !== 'approve' && !r.modeLocked && <button type="button" onClick={() => patch(r, { mode: 'approve' })} style={warnBtn}>Onaya gönder</button>}
                </div>
              )}
            </div>
          )
        })}
      </section>
    </div>
  )
}

const menuItem = { display: 'block', width: '100%', textAlign: 'left' as const, height: 32, padding: '0 10px', border: 0, borderRadius: 6, background: 'transparent', fontWeight: 500 }
const warnBtn = { height: 28, padding: '0 10px', border: '1px solid var(--am)', borderRadius: 6, background: 'transparent', color: 'var(--am)', fontSize: 12, fontWeight: 600 }

function Stat({ label, value, unit, sub }: { label: string; value: number; unit?: string; sub?: string }) {
  return (
    <div className="card" style={{ padding: '12px 16px' }}>
      <div style={{ fontSize: 12, color: 'var(--mut)', fontWeight: 500 }}>{label}</div>
      <div className="num" style={{ fontSize: 22, fontWeight: 600, marginTop: 2 }}>{value} <span style={{ fontSize: 13, color: 'var(--mut)', fontWeight: 400 }}>{unit}</span></div>
      {sub && <div className="num" style={{ fontSize: 11, color: 'var(--mut)', marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

function RuleEditor({ rule, categories, onClose, onSaved }: { rule: Rule | null; categories: Category[]; onClose: () => void; onSaved: () => void }) {
  const { toast } = useApp()
  const labelOf = (ops: string[]) => ops.find((o) => o.startsWith('label:'))?.slice(6) ?? ''
  const [name, setName] = useState(rule?.name ?? '')
  const [category, setCategory] = useState<string>(rule?.category ?? '')
  const [kind, setKind] = useState<RuleKind>(rule?.kind ?? 'question')
  const [question, setQuestion] = useState(rule?.question ?? '')
  const [th, setTh] = useState({ apply: rule?.applyThreshold ?? 0.85, ignore: rule?.ignoreThreshold ?? 0.5 })
  const [dry, setDry] = useState(rule?.dryRun ?? true)
  const [mode, setMode] = useState<Mode>(rule?.mode ?? 'approve')
  const [label, setLabel] = useState(labelOf(rule?.actions ?? ['label:']))
  const [flags, setFlags] = useState({
    label: rule ? !!labelOf(rule.actions) : true,
    star: rule?.actions.includes('star') ?? false,
    archive: rule?.actions.includes('archive') ?? false,
    read: rule?.actions.includes('read') ?? false,
  })
  const [saving, setSaving] = useState(false)

  // Without a category a rule can only ask its own question.
  const effKind: RuleKind = category ? kind : 'question'
  const noArchive = categories.some((c) => c.key === category && c.neverArchive)
  const ops = [flags.label && label.trim() && `label:${label.trim()}`, flags.star && 'star', flags.archive && !noArchive && 'archive', flags.read && 'read'].filter(Boolean) as string[]

  const save = async () => {
    setSaving(true)
    try {
      const body = { name: name.trim(), question: question.trim(), applyThreshold: th.apply,
        ignoreThreshold: effKind === 'question' ? th.ignore : null, actions: ops, mode, dryRun: dry }
      if (rule) await api.patchRule(rule.id, body)
      else await api.createRule({ ...body, category: category || null, kind: effKind, enabled: true })
      onSaved()
    } catch (e) {
      toast({ title: 'Kural kaydedilemedi', sub: (e as Error).message })
    }
    setSaving(false)
  }

  const box = (k: keyof typeof flags, text: string, disabled = false) => {
    const on = flags[k] && !disabled
    return (
      <label title={disabled ? `${category} e-postaları arşivlenemez` : undefined} style={{ display: 'flex', alignItems: 'center', gap: 8, height: 34, padding: '0 10px', border: `1px solid ${on ? 'var(--acc)' : 'var(--line)'}`, borderRadius: 8, background: on ? 'var(--accSoft)' : 'var(--card)', opacity: disabled ? 0.5 : 1 }}>
        <input type="checkbox" checked={on} disabled={disabled} onChange={() => setFlags({ ...flags, [k]: !flags[k] })} />{text}
      </label>
    )
  }

  return (
    <section className="card" aria-label={rule ? 'Kuralı düzenle' : 'Yeni kural'} style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <h2 className="h2">{rule ? `“${rule.name}” kuralını düzenle` : 'Yeni kural'}</h2>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
        <label style={{ flex: '1 1 220px', display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12, fontWeight: 500 }}>Ad
          <input type="text" className="field" value={name} onChange={(e) => setName(e.target.value)} style={{ background: 'var(--card)' }} />
        </label>
        <label style={{ flex: '1 1 220px', display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12, fontWeight: 500 }}>Kapsam
          <select className="select" value={category} disabled={!!rule} onChange={(e) => setCategory(e.target.value)} style={{ height: 36, fontWeight: 400 }}>
            <option value="">Tüm e-postalar (evet/hayır sorusu)</option>
            {categories.map((c) => <option key={c.key} value={c.key}>Kategori: {c.key}</option>)}
          </select>
        </label>
      </div>
      {category && (
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10, fontSize: 12 }}>
          <Seg inset label="Kural türü" value={effKind} onChange={(k) => { if (!rule) setKind(k) }}
            items={[{ key: 'category', label: 'Kategori kararına göre' }, { key: 'question', label: 'Bu kategoride evet/hayır sor' }]} />
          <span style={{ color: 'var(--mut)' }}>{effKind === 'category'
            ? `E-posta ${category} olarak sınıflandırılınca işlem yapılır.`
            : `Yalnızca ${category} e-postalarında aşağıdaki soru sorulur.`}</span>
        </div>
      )}
      <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12, fontWeight: 500 }}>
        {effKind === 'category' ? 'Açıklama (kategori kararında kullanılmaz, listede görünür)' : 'Soru (karar modeli evet/hayır olarak yanıtlar)'}
        <textarea rows={2} value={question} onChange={(e) => setQuestion(e.target.value)} style={{ padding: '8px 10px', border: '1px solid var(--line)', borderRadius: 8, background: 'var(--card)', resize: 'vertical', fontWeight: 400 }} />
      </label>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-end' }}>
        <div role="group" aria-label="Eşikler" style={{ flex: '1 1 280px', display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12, fontWeight: 500 }}>
          <span style={{ display: 'flex' }}>{effKind === 'question' ? 'Eşikler' : 'Uygulama eşiği'}
            <span className="num" style={{ marginLeft: 'auto', fontWeight: 600 }}>{thText(th.apply, effKind === 'question' ? th.ignore : null)}</span></span>
          <ThresholdSlider apply={th.apply} ignore={effKind === 'question' ? th.ignore : null}
            onChange={(apply, ignore) => setTh({ apply, ignore: ignore ?? th.ignore })} />
          <span style={{ fontWeight: 400, color: 'var(--mut)' }}>{effKind === 'question'
            ? `“Evet” ≤ ${th.ignore.toFixed(2)} yalnızca kaydedilir · arası onaya düşer · ≥ ${th.apply.toFixed(2)} uygulanır`
            : `Kategori olasılığı ${th.apply.toFixed(2)} altındaysa onaya düşer, üstündeyse uygulanır`}</span>
        </div>
        <label style={{ flex: '1 1 200px', display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12, fontWeight: 500 }}>Mod
          <select className="select" value={mode} disabled={rule?.modeLocked} title={rule?.modeLocked ? 'Bu kuralın modu sabittir' : undefined} onChange={(e) => setMode(e.target.value as Mode)} style={{ height: 36, fontWeight: 400 }}>
            {(Object.keys(MODE_LABEL) as Mode[]).map((m) => <option key={m} value={m}>{MODE_LABEL[m]}</option>)}
          </select>
        </label>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', fontSize: 12 }}>
        {box('label', 'Etiket')}
        <input type="text" aria-label="Etiket adı" className="mono field" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Etiket adı" style={{ height: 34, width: 140 }} />
        {box('star', 'Yıldızla')}
        {box('archive', 'Arşivle', noArchive)}
        {box('read', 'Okundu işaretle')}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, marginRight: 'auto', fontSize: 12 }}>
          <Switch on={dry} label="Kuru" onClick={() => setDry(!dry)} />
          <span><span style={{ fontWeight: 500 }}>Kuru</span> <span style={{ color: 'var(--mut)' }}>— genel kuru mod kapalıyken de Gmail'e yazmaz, yalnızca önerir</span></span>
        </span>
        <button type="button" className="btn ib" onClick={onClose}>Vazgeç</button>
        <button type="button" className="btn-p" disabled={saving || !name.trim() || question.trim().length < 3} onClick={save}>{saving ? 'Kaydediliyor…' : 'Kaydet'}</button>
      </div>
    </section>
  )
}
