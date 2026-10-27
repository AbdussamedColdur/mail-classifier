import type { ReactNode } from 'react'
import { useApp, type Screen } from '../lib/app'
import { hhmm } from '../lib/format'
import * as Ic from './Icons'

const NAV: { key: Screen; label: string; icon: ReactNode }[] = [
  { key: 'panel', label: 'Panel', icon: <Ic.Grid /> },
  { key: 'queue', label: 'Onay Kuyruğu', icon: <Ic.Inbox /> },
  { key: 'command', label: 'Komut', icon: <Ic.Terminal /> },
  { key: 'rules', label: 'Kurallar', icon: <Ic.List /> },
  { key: 'logs', label: 'Kayıtlar', icon: <Ic.Doc /> },
  { key: 'accounts', label: 'Hesaplar', icon: <Ic.User /> },
  { key: 'settings', label: 'Ayarlar', icon: <Ic.Gear /> },
]

export function Nav({ current }: { current: Screen }) {
  const { go, status } = useApp()
  const pending = status?.pendingCount ?? 0
  return (
    <nav aria-label="Ana menü" style={{ flex: '1 1 220px', background: 'var(--card)', borderRight: '1px solid var(--line)', padding: '14px 10px', display: 'flex', flexDirection: 'column', gap: 2 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '4px 10px 16px' }}>
        <div aria-hidden="true" style={{ width: 26, height: 26, borderRadius: 7, background: 'var(--btn)', color: '#FFFFFF', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Ic.Mail /></div>
        <span style={{ fontWeight: 600, fontSize: 14, letterSpacing: '-0.01em' }}>MailKarar</span>
      </div>
      {NAV.map((n) => {
        const on = n.key === current
        return (
          <button key={n.key} className="nav" type="button" onClick={() => go(n.key)} aria-current={on ? 'page' : undefined}
            style={{ display: 'flex', alignItems: 'center', gap: 10, height: 34, padding: '0 10px', border: 0, borderRadius: 7, textAlign: 'left', fontWeight: 500, background: on ? 'var(--sub)' : 'transparent', color: on ? 'var(--tx)' : 'var(--mut)' }}>
            {n.icon}{n.label}
            {n.key === 'queue' && pending > 0 && <span className="num count" style={{ marginLeft: 'auto' }}>{pending}</span>}
          </button>
        )
      })}
      <div style={{ marginTop: 'auto', padding: '12px 10px 4px', fontSize: 12, color: 'var(--mut)', borderTop: '1px solid var(--line)' }}>Yerel mod — e-postalar bu cihazdan çıkmaz</div>
    </nav>
  )
}

export function DryBand() {
  const { go } = useApp()
  return (
    <div role="status" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'center', gap: 8, minHeight: 28, padding: '4px 16px', background: 'var(--gyBg)', color: 'var(--gy)', fontSize: 12, fontWeight: 500, borderBottom: '1px solid var(--line)' }}>
      <Ic.Dashed />Kuru mod: hiçbir işlem Gmail'e uygulanmıyor<button className="lk" type="button" onClick={() => go('settings')}>Ayarlar</button>
    </div>
  )
}

function Pill({ bad, label, value, okText, badText }: { bad: boolean; label: string; value: string; okText: string; badText: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 26, padding: '0 10px', border: `1px solid ${bad ? 'var(--rd)' : 'var(--line)'}`, background: bad ? 'var(--rdBg)' : 'transparent', borderRadius: 6, color: 'var(--mut)' }}>
      <span className="dot" aria-hidden="true" style={{ background: bad ? 'var(--rd)' : 'var(--gn)' }} />
      {label}: <span style={{ color: 'var(--tx)', fontWeight: 500 }}>{value}</span>{' '}
      <span style={{ color: bad ? 'var(--rd)' : 'var(--mut)', fontWeight: bad ? 600 : 400 }}>{bad ? badText : okText}</span>
    </span>
  )
}

export function StatusBar() {
  const { status, toggleTheme } = useApp()
  const g = status?.gmail
  const o = status?.ollama
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, padding: '8px 24px', borderBottom: '1px solid var(--line)', background: 'var(--card)', fontSize: 12 }}>
      {status ? (
        <>
          <Pill bad={!g?.connected} label="Gmail" value={g?.email ?? 'hesap yok'} okText="bağlı" badText={g?.status === 'expired' ? 'bağlantı koptu' : 'bağlı değil'} />
          <Pill bad={!o?.running || !o.modelInstalled} label="Ollama" value={o?.model ?? ''} okText="hazır" badText={!o?.running ? 'kapalı' : 'model yüklü değil'} />
          {status.dryRun && (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 26, padding: '0 10px', borderRadius: 6, background: 'var(--gyBg)', color: 'var(--gy)', fontWeight: 500 }}><Ic.Dashed />Kuru mod</span>
          )}
        </>
      ) : (
        <span className="err-text">Arka uca ulaşılamıyor — <span className="mono">backend</span> klasöründe sunucuyu başlatın.</span>
      )}
      <span style={{ marginLeft: 'auto', color: 'var(--mut)' }}>{status?.scanning ? 'Taranıyor…' : `Son tarama ${hhmm(status?.lastScan ?? null)}`}</span>
      <button className="ib" type="button" aria-label="Temayı değiştir" onClick={toggleTheme} style={{ width: 30, height: 30, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', border: '1px solid var(--line)', borderRadius: 7, background: 'transparent', color: 'var(--mut)' }}><Ic.Moon /></button>
    </div>
  )
}

export function Toast({ title, sub, action, onClose }: { title: string; sub?: string; action?: { label: string; run: () => void }; onClose: () => void }) {
  return (
    <div role="status" aria-live="polite" style={{ position: 'fixed', right: 24, bottom: 24, zIndex: 10, display: 'flex', alignItems: 'center', gap: 12, maxWidth: 440, padding: '10px 10px 10px 14px', borderRadius: 10, background: 'var(--inv)', color: 'var(--invTx)', boxShadow: '0 10px 30px rgba(0,0,0,0.22)' }}>
      <Ic.Undo s={16} />
      <div style={{ flex: '1 1 auto', minWidth: 0 }}>
        <div style={{ fontWeight: 600 }}>{title}</div>
        {sub && <div style={{ fontSize: 12, color: 'var(--invMut)' }}>{sub}</div>}
      </div>
      {action && <button type="button" onClick={action.run} style={{ flex: 'none', height: 30, padding: '0 10px', border: 0, borderRadius: 6, background: 'transparent', color: 'var(--invAcc)', fontSize: 12, fontWeight: 600 }}>{action.label}</button>}
      <button type="button" aria-label="Bildirimi kapat" onClick={onClose} style={{ flex: 'none', width: 30, height: 30, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', border: 0, borderRadius: 6, background: 'transparent', color: 'var(--invMut)' }}><Ic.X s={14} w={2} /></button>
    </div>
  )
}

export function Switch({ on, onClick, label, track = 'var(--btn)', big = false }: { on: boolean; onClick: () => void; label: string; track?: string; big?: boolean }) {
  const w = big ? 44 : 34, h = big ? 24 : 20, k = big ? 18 : 16, pad = big ? 3 : 2
  return (
    <button type="button" role="switch" aria-checked={on} aria-label={label} onClick={onClick} className="switch"
      style={{ width: w, height: h, borderRadius: h / 2, background: on ? track : 'var(--line2)' }}>
      <span aria-hidden="true" style={{ top: pad, width: k, height: k, left: on ? w - k - pad : pad }} />
    </button>
  )
}

export function Seg<T extends string>({ items, value, onChange, label, inset }: { items: { key: T; label: ReactNode }[]; value: T; onChange: (v: T) => void; label: string; inset?: boolean }) {
  return (
    <div role="group" aria-label={label} className={inset ? 'seg inset' : 'seg'}>
      {items.map((it) => (
        <button key={it.key} type="button" aria-pressed={value === it.key} onClick={() => onChange(it.key)}>{it.label}</button>
      ))}
    </div>
  )
}

export const TH_MIN = 0.2
export const TH_MAX = 0.99
const r2 = (v: number) => Math.round(v * 100) / 100

/**
 * Apply threshold alone (category rules: below it → approval) or an ignore–apply range (yes/no:
 * ≤ ignore → recorded only, between → approval, ≥ apply → acted on). The track shows the zones.
 */
export function ThresholdSlider({ apply, ignore, onChange, id }: { apply: number; ignore: number | null; onChange: (apply: number, ignore: number | null) => void; id?: string }) {
  const at = (v: number) => ((v - TH_MIN) / (TH_MAX - TH_MIN)) * 100 + '%'
  const low = ignore ?? TH_MIN
  return (
    <div className="th">
      <div className="th-track" aria-hidden="true">
        {ignore !== null && <div style={{ left: 0, width: at(ignore), background: 'var(--line2)' }} />}
        <div style={{ left: at(low), right: `calc(100% - ${at(apply)})`, background: 'var(--am)' }} />
        <div style={{ left: at(apply), right: 0, background: 'var(--acc)' }} />
      </div>
      {ignore !== null && (
        <input type="range" className="th-ignore" aria-label="Görmezden gelme eşiği" min={TH_MIN} max={TH_MAX} step={0.01} value={ignore}
          onChange={(e) => onChange(apply, Math.min(r2(Number(e.target.value)), r2(apply - 0.01)))} />
      )}
      <input id={id} type="range" aria-label="Uygulama eşiği" min={TH_MIN} max={TH_MAX} step={0.01} value={apply}
        onChange={(e) => onChange(Math.max(r2(Number(e.target.value)), ignore === null ? TH_MIN : r2(ignore + 0.01)), ignore)} />
    </div>
  )
}

/** "0.85" for a category rule, "0.50–0.85" for a yes/no one. */
export const thText = (apply: number, ignore: number | null) => (ignore === null ? apply.toFixed(2) : `${ignore.toFixed(2)}–${apply.toFixed(2)}`)

/** Thin score bar used across the panel, queue and detail views. */
export function Bar({ value, h = 4, color = 'var(--acc)', track = 'var(--bar)', width }: { value: number; h?: number; color?: string; track?: string; width?: number | string }) {
  return (
    <div style={{ height: h, borderRadius: h / 2, background: track, width, flex: width ? 'none' : undefined }}>
      <div style={{ height: h, borderRadius: h / 2, background: color, width: Math.round(Math.max(0, Math.min(1, value)) * 100) + '%' }} />
    </div>
  )
}
