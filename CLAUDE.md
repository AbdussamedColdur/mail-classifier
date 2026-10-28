# MailKarar: ajan notları

Yerel bir karar modeliyle Gmail e-postalarını sınıflandırıp etiketleyen uygulama. Kurulum, yapı ve
genel davranış README.md'de; burada yalnızca koddan okunamayan kararlar ve kurallar var.

## Testler

Her değişiklikten sonra ikisi de yeşil olmalı:

```powershell
cd backend; .\.venv\Scripts\python -m unittest discover -s tests -v
cd frontend; npm run build      # tsc + vite; tür hatası derlemeyi durdurur
```

Backend testleri Gmail'i ve modeli taklit eder. `ClassifierTest`, Ollama 0.40.11'in gerçek
`/v1/systemone` yanıt biçimlerini sahte bir sunucuya karşı sınar: yanıt biçimi değişirse önce gerçek
bir istekle doğrulayın, sonra testi güncelleyin. Arayüz değişikliğinde sayfayı geçici bir veritabanıyla
açıp bakın: boş bir klasörde `db.init()` ile yeni veritabanı açıp uydurma veri ekleyin. Asıl
`backend/data/mailkarar.db` dosyasını ve kopyasını kullanmayın; bağlı Gmail hesabının gerçek
e-postalarını içerir. Kullanıcının uygulaması 8000 portunda çalışıyor olabilir; denemeler için başka port seçin.

## Güvenlik ve varsayılanlar

- **Kuru mod varsayılan olarak açık** (`config.DEFAULTS["dryRun"]`) ve her yeni kural `dry_run = 1`
  ile başlar. Bu iki varsayılan, gerçek bir Gmail hesabına yanlışlıkla yazılmasını önleyen asıl güvencedir;
  ikisini de açık tutun.
- Gmail'in Spam klasörü hiç kullanılmaz: Tanıtım ve Oltalama etiket + arşiv alır. Spam'e taşımak
  Gmail'in filtresini eğitir ve aynı bankanın ekstrelerini de spam'e düşürebilir.
- Hesap e-postaları (doğrulama kodu, giriş uyarısı) gelen kutusunda kalır; API arşivi reddeder
  (`config.NEVER_ARCHIVE`).
- "Oltalama şüphesi" kuralı her zaman onaya gider (`mode_locked`).
- Gmail'deki eski "Alışveriş &Faturalar/…" etiketleri kullanıcının gönderen filtreleriyle çalışıyor;
  MailKarar yalnızca kendi `MailKarar/…` etiketlerine yazar.

## Kategoriler

Tek bir "choice" sorusuyla sekiz kategori; açıklamalar modelin ölçütüdür ve tek kaynakları
`backend/app/config.py` içindeki `CATEGORIES` listesidir: Banka, Fatura, Alışveriş, Hesap, Kişisel,
Bülten, Tanıtım, Diğer.

**Tanıtım ≠ banka işlemi.** Bankalar hem kampanya hem işlem e-postası gönderir. Kategori gönderene göre
değil içeriğe göre verilir: banka işlemi/ekstresi Banka, kampanyası Tanıtım. Modeller bunu ayırabiliyor
(banka işlem e-postalarında tanıtım/spam puanı en fazla 0,19). Bu ayrımı gönderen adresine dayalı bir
kuralla değiştirmeyin; Tanıtım açıklamasındaki "…tanıtım değildir; içeriğe göre karar ver" cümlesi bu
yüzden orada.

## Eşikler

Tek kaynak `config.py` (`THRESHOLD_RANGE`, `DEFAULT_IGNORE`, `STARTER_RULES`):

- Kategori kuralları yalnızca uygulama eşiği kullanır; altında kalan e-posta **onaya** düşer.
  Kullanıcı kararsız e-postaları görmek istiyor, bu yüzden kategori kurallarında görmezden gelme eşiği yok.
- Evet/hayır kuralları: "Evet" ≤ görmezden gelme (0,50) → yalnızca kayıt; arası → onay; ≥ uygulama → uygula.
- Uygulama eşikleri: etiket 0,85, arşiv 0,90, Tanıtım 0,95. Aralık 0,20–0,99.
- Komut görevleri aynı ayrımı izler: evet/hayır görevi iki eşikli; liste görevi kategori kuralı gibi
  tek eşikli, yalnızca ilk seçenek modelin en yüksek seçimi olduğunda işlem yapar.

Eşikler bilerek temkinli: uydurma 12 e-postalık testte "kararlı ama yanlış" karar çıkmadı, ama gerçek
e-postalarda fatura kuralında ≥0,85 puanla 3 hata görüldü.

## Model testlerinden çıkan kararlar

Ollama 0.40.11, `/v1/systemone`. Betikler `tools/model-tests/`. Gerçek e-posta içeren test çıktıları
`C:\Users\Coldur\MailKarar` klasöründe kalır; o klasördeki dosyaları açmayın, depoya almayın, silmeyin.

- Test edilen modeller: `d3:9b`, `tev1:4b`, `tev1:0.8b`.
- `tev1:0.8b` elendi: "acil" sorusunu gerçek ve uydurma e-postalarda sistematik olarak yanlış tetikledi.
- `d3:9b` ve `tev1:4b` gerçek e-postalarda doğrulukta eşit: banka %100, spam/tanıtım ~%90, fatura ~%73
  (n=15–44; örnekler küçük, sonuçlar kesin değil). Bu sonuçlar kural başına evet/hayır sorularıyla
  ölçüldü; sekiz kategorili choice sorusu gerçek e-postalarda henüz ölçülmedi.
- **Varsayılan model `tev1:4b`**: ~2,3 sn/istek, 5,7 GB bellek, testlerde hiç çökmedi. `d3:9b`: ~2,8 sn,
  10 GB, bir kez soğuk başlangıçta CUDA hatasıyla çöktü (tekrarlanamadı) ve kısa tanıtım e-postalarında
  kararsız kalabiliyor; Ayarlar'dan seçilebilir.
- tev1 yalnızca İngilizcede test edilmiş bir model; Türkçe talimatlarla sonuçlar iyi çıktı.
- Bülten ile Tanıtım ayrımı gerçek veride henüz doğrulanmadı.
- Choice yanıtında skor olarak `probabilities` kullanılır; `confidence` en yüksek olasılıktan farklı bir değerdir.
- Karar modeli adla değil `/api/tags` içindeki `"decision"` yeteneğiyle tespit edilir.

## Veritabanı

Şema sürümü `PRAGMA user_version`. `db.SCHEMA` her zaman en son düzendir; mevcut bir veritabanı yükseltilmeden
önce `backend/data/mailkarar.db.bak-v<eski>-<tarih>` olarak yedeklenir (`db.backup`), sonra
`migrate.py` ile adım adım yükseltilir. Şemayı değiştirirken: `SCHEMA`'yı güncelleyin, `SCHEMA_VERSION`'ı
artırın, `MIGRATIONS`'a bir adım ekleyin ve `test_migration_from_v1` testini genişletin
(`tests/schema_v1.sql` donmuş v1 şemasıdır, değiştirmeyin).

## Dokunulmayacak dosyalar

Git'e girmez, içeriği okunmaz ya da değiştirilmez:

- `backend/data/credentials.json`: Google OAuth istemci sırrı.
- `backend/data/*.db`: kullanıcının yerel kayıtları (deneme için kopyasını kullanın).
- `tools/model-tests/labels.local.json`: kişisel Gmail etiket adları (biçim için `labels.example.json`).
- Erişim belirteci Windows Kimlik Bilgisi Yöneticisi'nde (`MailKarar`); `token.json` kullanılmaz.
- `start.ps1` içindeki ortam sağlık kontrolü (`Test-Venv`) ve uvicorn öncesi `$ErrorActionPreference = 'Continue'`
  satırı: ikisi de bu makinede yaşanmış hataları düzeltir.

Push etmeden önce kullanıcıya gösterin; git geçmişini yeniden yazmayın.

## Açık işler

Sıradaki adım: gerçek e-postalarla **kuru modda gözlem**. Gmail hesabı bağlı ve okuma çalışıyor; tüm
kurallar hâlâ kuru. Onay Kuyruğu'ndaki kararlara bakıp kategori açıklamalarını ve eşikleri ayarlayın,
sonra kuralları tek tek kuru moddan çıkarın.

Doğrulanmayı bekleyenler:
- Sekiz kategorili choice sorusunun gerçek e-posta doğruluğu (özellikle Bülten ile Tanıtım ayrımı).
- Gmail'e yazma ve geri alma (`gmail.apply_ops`, `gmail.revert`): ilk kural kuru moddan çıkınca
  `MailKarar/…` etiketlerini, arşivi ve 30 günlük geri almayı gerçek hesapta deneyin.

Bilinen kusurlar:
- Sunucu açıldıktan sonraki ilk `/api/status` çağrısı ~2 sn sürüyor (nedeni doğrulanmadı). Kullanıcı
  şimdilik dokunulmamasını istedi; ön yüz bu sürede "Bağlanıyor…" gösteriyor.
- İki uçlu eşik kaydırıcısı tutamacı fare gezinmesine göre seçer; dokunmatik ekranda ilk dokunuş
  üstteki tutamacı tutabilir. Gerçek bir sürüklemeyle test edilmedi.
- Evet/hayır kuralları her e-posta için bir karar kaydı bırakır (eşik altındakiler dahil); `decisions`
  tablosu için temizleme yok.
- Testlerde `StarletteDeprecationWarning` (TestClient için `httpx2` öneriyor); sonuçları etkilemiyor.
