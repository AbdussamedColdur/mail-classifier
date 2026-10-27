import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { Account, CredentialsInfo } from '../api/types'
import * as Ic from '../components/Icons'
import { useApp } from '../lib/app'
import { ago, initials } from '../lib/format'

export default function Accounts({ params }: { params: URLSearchParams }) {
  const { toast, refreshStatus } = useApp()
  const [cred, setCred] = useState<CredentialsInfo | null>(null)
  const [accounts, setAccounts] = useState<Account[] | null>(null)
  const [help, setHelp] = useState(false)
  const [syncing, setSyncing] = useState<Record<number, boolean>>({})
  const [confirmCut, setConfirmCut] = useState<number | null>(null)
  const [uploadErr, setUploadErr] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const load = async () => {
    try {
      const [c, a] = await Promise.all([api.credentials(), api.accounts()])
      setCred(c); setAccounts(a)
    } catch { /* shown by the status bar */ }
  }

  useEffect(() => {
    void load()
    const connected = params.get('connected'), error = params.get('error')
    if (connected) toast({ title: `${connected} bağlandı`, sub: 'Yeni e-postalar birazdan taranacak.' })
    if (error) toast({ title: 'Hesap bağlanamadı', sub: error })
    if (connected || error) { window.history.replaceState(null, '', '#/accounts'); refreshStatus() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const upload = async (file?: File | null) => {
    if (!file) return
    try { setCred(await api.uploadCredentials(file)); setUploadErr(null) } catch (e) { setUploadErr((e as Error).message) }
    if (fileRef.current) fileRef.current.value = ''
  }

  const sync = async (a: Account) => {
    setSyncing((s) => ({ ...s, [a.id]: true }))
    try { await api.syncAccount(a.id) } catch (e) { toast({ title: 'Eşitlenemedi', sub: (e as Error).message }) }
    setTimeout(() => { setSyncing((s) => ({ ...s, [a.id]: false })); load(); refreshStatus() }, 1500)
  }

  const cut = async (a: Account) => {
    try { await api.deleteAccount(a.id); toast({ title: `${a.email} bağlantısı kesildi`, sub: 'Erişim belirteci bu cihazdan silindi.' }) } catch (e) { toast({ title: 'Bağlantı kesilemedi', sub: (e as Error).message }) }
    setConfirmCut(null); load(); refreshStatus()
  }

  const has = !!cred?.present
  return (
    <div className="page">
      <div>
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 600, letterSpacing: '-0.015em' }}>Hesaplar</h1>
        <p style={{ margin: '2px 0 0', color: 'var(--mut)' }}>Gmail hesaplarını kendi Google Cloud OAuth istemcinizle bağlayın. Kimlik bilgileri bu cihazda kalır.</p>
      </div>

      <section aria-labelledby="oauth-h" className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '14px 16px', borderBottom: '1px solid var(--line)' }}>
          <h2 id="oauth-h" className="h2">Yeni hesap bağla</h2>
          <span style={{ fontSize: 12, color: 'var(--mut)' }}>2 adım</span>
          <button className="lk" type="button" aria-expanded={help} onClick={() => setHelp(!help)} style={{ marginLeft: 'auto', fontSize: 12 }}>credentials.json nasıl alınır?</button>
        </div>
        {help && (
          <ol style={{ margin: 0, padding: '14px 16px 14px 34px', borderBottom: '1px solid var(--line)', background: 'var(--sub)', fontSize: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
            <li><a href="https://console.cloud.google.com/projectcreate" target="_blank" rel="noreferrer">Google Cloud Console</a>'da yeni bir proje oluşturun.</li>
            <li>API'ler ve Hizmetler › Kitaplık bölümünde <b>Gmail API</b>'yi bulup etkinleştirin.</li>
            <li>OAuth izin ekranında kullanıcı türü olarak <b>Harici</b>'yi seçin, bir uygulama adı girin ve kendi Gmail adresinizi <b>test kullanıcısı</b> olarak ekleyin.</li>
            <li>Kimlik bilgileri › Kimlik bilgisi oluştur › <b>OAuth istemci kimliği</b> › Uygulama türü: <b>Masaüstü uygulaması</b>. Oluşturduktan sonra JSON dosyasını indirin.</li>
            <li style={{ color: 'var(--mut)' }}>Not: Uygulama “Test” durumunda kaldıkça Google erişim iznini 7 günde bir geçersiz kılar; o zaman burada “Yeniden bağlan” demeniz yeterli.</li>
          </ol>
        )}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))' }}>
          <div style={{ padding: '18px 16px', display: 'flex', flexDirection: 'column', gap: 12, borderRight: '1px solid var(--line)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <StepMark done={has} n={1} active />
              <h3 style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>credentials.json yükle</h3>
            </div>
            <p style={{ margin: 0, fontSize: 12, color: 'var(--mut)' }}>Google Cloud Console › API'ler ve Hizmetler › Kimlik bilgileri bölümünden “Masaüstü uygulaması” türünde bir OAuth istemcisi oluşturup JSON dosyasını indirin.</p>
            <input ref={fileRef} type="file" accept=".json,application/json" hidden onChange={(e) => upload(e.target.files?.[0])} />
            {cred && !has && (
              <button className="drop" type="button" onClick={() => fileRef.current?.click()}
                onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); upload(e.dataTransfer.files?.[0]) }}
                style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, padding: '22px 16px', border: '1px dashed var(--line2)', borderRadius: 10, background: 'var(--sub)', color: 'var(--mut)' }}>
                <Ic.Upload /><span style={{ color: 'var(--tx)', fontWeight: 500 }}>Dosyayı sürükleyin ya da seçin</span><span style={{ fontSize: 12 }}>Yalnızca .json · en fazla 64 KB</span>
              </button>
            )}
            {has && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: 12, border: '1px solid var(--line)', borderRadius: 10 }}>
                <div aria-hidden="true" style={{ width: 34, height: 34, borderRadius: 8, background: 'var(--gnBg)', color: 'var(--gn)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Ic.FileOk /></div>
                <div style={{ flex: '1 1 auto', minWidth: 0 }}>
                  <div style={{ fontWeight: 500 }}>credentials.json</div>
                  <div style={{ fontSize: 12, color: 'var(--mut)' }}>Masaüstü istemcisi{cred?.projectId && <> · <span className="mono" style={{ fontSize: 11 }}>{cred.projectId}</span> projesi</>}</div>
                </div>
                <button className="btn ib" type="button" onClick={() => api.removeCredentials().then(load)} style={{ height: 32, padding: '0 10px', fontSize: 12, borderRadius: 7 }}>Kaldır</button>
              </div>
            )}
            {uploadErr && <span className="err-text">{uploadErr}</span>}
          </div>

          <div style={{ padding: '18px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <StepMark n={2} active={has} />
              <h3 style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>Google hesabıyla yetkilendir</h3>
            </div>
            <p style={{ margin: 0, fontSize: 12, color: 'var(--mut)' }}>Tarayıcıda Google onay ekranı açılır. İzin verdikten sonra erişim belirteci bu cihazda, Windows Kimlik Bilgisi Yöneticisi'nde saklanır.</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '10px 12px', borderRadius: 8, background: 'var(--sub)', fontSize: 12 }}>
              <span style={{ color: 'var(--mut)', fontWeight: 500 }}>İstenecek izinler</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Scope>gmail.modify</Scope>Okuma, arşivleme, yıldızlama</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Scope>gmail.labels</Scope>Etiket oluşturma ve düzenleme</span>
            </div>
            {has
              ? <a href={api.connectUrl} className="btn ib" style={{ alignSelf: 'flex-start', height: 40, padding: '0 16px', borderColor: 'var(--line2)', color: 'var(--tx)', textDecoration: 'none', gap: 8 }}><Ic.SignIn />Google ile bağlan</a>
              : <button type="button" disabled className="btn" style={{ alignSelf: 'flex-start', height: 40, padding: '0 16px', borderColor: 'var(--line2)', gap: 8 }}><Ic.SignIn />Google ile bağlan</button>}
            {!has && <span style={{ fontSize: 12, color: 'var(--mut)' }}>Önce 1. adımı tamamlayın.</span>}
          </div>
        </div>
      </section>

      <section aria-labelledby="acc-h" className="card" style={{ overflow: 'hidden' }}>
        <div className="sec-head">
          <h2 id="acc-h" className="h2">Bağlı hesaplar</h2>
          <span className="num" style={{ fontSize: 12, color: 'var(--mut)' }}>{accounts?.length ?? 0} hesap</span>
        </div>
        <div style={{ display: 'flex', gap: 16, padding: '6px 16px', borderTop: '1px solid var(--line)', background: 'var(--sub)', fontSize: 11, fontWeight: 500, color: 'var(--mut)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          <span style={{ flex: '1 1 240px' }}>Hesap</span>
          <span style={{ flex: '0 0 180px' }}>Durum</span>
          <span style={{ flex: '1 1 200px' }}>İzinler</span>
          <span style={{ flex: '0 0 120px' }}>Son eşitleme</span>
          <span style={{ flex: '0 0 232px', textAlign: 'right' }}>İşlemler</span>
        </div>
        {accounts?.length === 0 && <div style={{ padding: '24px 16px', borderTop: '1px solid var(--line)', textAlign: 'center', color: 'var(--mut)' }}>Henüz bağlı hesap yok.</div>}
        {accounts?.map((a) => {
          const expired = a.status === 'expired'
          const busy = syncing[a.id]
          const [st, bg, fg] = busy ? ['Eşitleniyor…', 'var(--accSoft)', 'var(--accTx)'] : expired ? ['Belirteç süresi doldu', 'var(--rdBg)', 'var(--rd)'] : ['Bağlı', 'var(--gnBg)', 'var(--gn)']
          return (
            <div key={a.id} style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '10px 16px', padding: '12px 16px', borderTop: '1px solid var(--line)' }}>
              <div style={{ flex: '1 1 240px', minWidth: 0, display: 'flex', alignItems: 'center', gap: 10 }}>
                <div aria-hidden="true" style={{ flex: 'none', width: 32, height: 32, borderRadius: '50%', background: 'var(--sub)', border: '1px solid var(--line)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 600, color: 'var(--mut)' }}>{initials(a.email)[0]}</div>
                <div style={{ minWidth: 0 }}>
                  <div className="ellipsis" style={{ fontWeight: 500 }}>{a.email}</div>
                  <div className="ellipsis" style={{ fontSize: 12, color: a.error ? 'var(--rd)' : 'var(--mut)' }}>{a.error ?? (expired ? 'Otomasyon duraklatıldı' : 'Otomasyon açık')}</div>
                </div>
              </div>
              <span style={{ flex: '0 0 180px' }}><span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 500, padding: '2px 8px', borderRadius: 6, background: bg, color: fg }}><span aria-hidden="true" style={{ width: 6, height: 6, borderRadius: '50%', background: fg }} />{st}</span></span>
              <span style={{ flex: '1 1 200px', display: 'flex', flexWrap: 'wrap', gap: 4 }}>{a.scopes.map((s) => <Scope key={s}>{s}</Scope>)}</span>
              <span className="num" style={{ flex: '0 0 120px', fontSize: 12, color: 'var(--mut)' }}>{ago(a.lastSync)}</span>
              <span style={{ flex: '0 0 232px', display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                {expired
                  ? <a className="btn ib" href={api.connectUrl} style={smallBtn}><Ic.Refresh />Yeniden bağlan</a>
                  : <button className="btn ib" type="button" disabled={busy} onClick={() => sync(a)} style={smallBtn}><Ic.Refresh />Şimdi eşitle</button>}
                {confirmCut === a.id
                  ? <button className="btn ib" type="button" onClick={() => cut(a)} style={{ ...smallBtn, color: 'var(--rd)', fontWeight: 600 }}>Emin misiniz?</button>
                  : <button className="btn ib" type="button" onClick={() => setConfirmCut(a.id)} style={{ ...smallBtn, color: 'var(--rd)' }}>Bağlantıyı kes</button>}
              </span>
            </div>
          )
        })}
      </section>
    </div>
  )
}

const smallBtn = { height: 32, padding: '0 10px', borderRadius: 7, fontSize: 12, color: 'var(--tx)', textDecoration: 'none' }

function StepMark({ n, done, active }: { n: number; done?: boolean; active?: boolean }) {
  const [bg, fg] = done ? ['var(--gnBg)', 'var(--gn)'] : active ? ['var(--btn)', '#FFFFFF'] : ['var(--sub)', 'var(--mut)']
  return <span className="num" aria-hidden="true" style={{ width: 24, height: 24, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 600, background: bg, color: fg }}>{done ? '✓' : n}</span>
}

const Scope = ({ children }: { children: string }) => <span className="mono" style={{ fontSize: 11, padding: '1px 6px', borderRadius: 4, background: 'var(--card)', border: '1px solid var(--line)' }}>{children}</span>
