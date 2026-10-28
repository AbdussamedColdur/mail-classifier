# MailKarar

Gmail'e gelen e-postaları yerel bir karar modeline (Ollama'da `tev1` ya da `d3`) sınıflandırtan ve sonuca göre
Gmail'de etiketleme, arşivleme, yıldızlama ya da okundu işaretleme yapan yerel bir uygulama.
E-postaların içeriği hiçbir yapay zekâ servisine gitmez; Gmail'e yalnızca Google API'si üzerinden bağlanılır.

Arayüz `design/` klasöründeki Claude Design tasarımına göre yazıldı.

## Çalıştırma

```powershell
.\start.ps1
```

İlk çalıştırmada Python ortamını ve ön yüz paketlerini kurar, ön yüzü derler ve
<http://127.0.0.1:8000> adresini açar. Sunucu yalnızca bu bilgisayardan erişilebilir (127.0.0.1).
`backend\.venv` çalışmıyorsa (başka bir bilgisayardan kopyalanmış, Python kaldırılmış) betik onu yeniden kurar.
Açılışta seçili model bir kez ısıtılır; veritabanı eski bir sürümdeyse otomatik olarak yükseltilir.

Geliştirme sırasında ön yüzü ayrı çalıştırmak için:

```powershell
cd backend; .\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
cd frontend; npm run dev      # http://127.0.0.1:5173, /api isteklerini 8000'e iletir
```

## Gereksinimler

- Python 3.10+ (3.14 ile test edildi), Node 18+
- **Ollama 0.40.11** (test edilen sürüm) ve bir karar modeli: varsayılan `ollama pull tev1:4b`,
  alternatif `d3:9b`. Karar modelleri sohbet etmez; verdiğiniz seçeneklere olasılık verir
  (`/v1/systemone`). Uygulama bir modelin karar modeli olduğunu adından değil, Ollama'nın
  `/api/tags` yanıtındaki `"decision"` yeteneğinden anlar.
  Karar modeli yoksa Ayarlar'dan yüklü herhangi bir sohbet modeli (ör. Qwen) seçilebilir; o zaman
  uygulama modelden JSON olarak seçenek başına olasılık ister.

## Gmail bağlantısı

1. [Google Cloud Console](https://console.cloud.google.com/projectcreate)'da bir proje oluşturun.
2. API'ler ve Hizmetler › Kitaplık'tan **Gmail API**'yi etkinleştirin.
3. OAuth izin ekranında **Harici** seçin, kendi Gmail adresinizi **test kullanıcısı** olarak ekleyin.
4. Kimlik bilgileri › OAuth istemci kimliği › **Masaüstü uygulaması** oluşturup JSON'u indirin.
5. Uygulamada Hesaplar › credentials.json yükle › Google ile bağlan.

İstenen izinler `gmail.modify` ve `gmail.labels`; silme izni yoktur. Erişim belirteci Windows
Kimlik Bilgisi Yöneticisi'nde (`MailKarar` adıyla) saklanır, `credentials.json` ise `backend/data/` altında.
Google, "Test" durumundaki uygulamaların iznini 7 günde bir geçersiz kılar; o zaman Hesaplar'dan
"Yeniden bağlan" demek yeterli.

## Nasıl çalışır

- Arka plandaki tarayıcı, Ayarlar'daki aralıkla Gelen Kutusu'ndaki son 2 günün e-postalarını çeker
  (varsayılan olarak yalnızca okunmamışlar).
- Her e-posta tek bir "choice" sorusuyla sekiz kategoriden birine konur: Banka, Fatura, Alışveriş,
  Hesap, Kişisel, Bülten, Tanıtım, Diğer. Kategori açıklamaları modelin ölçütüdür (`backend/app/config.py`).
  Tanıtım, bankaların ve tanınmış şirketlerin kampanyalarını da kapsar; ama banka işlemi/ekstresi,
  fatura, sipariş ve güvenlik e-postaları gönderen aynı olsa da tanıtım sayılmaz.
- Kurallar iki türlüdür: **kategori kuralları** kategori kararına göre çalışır; **evet/hayır kuralları**
  kendi sorusunu sorar ve bir kategoriyle sınırlanabilir.
- Başlangıç kuralları: Banka, Alışveriş, Bülten ve Tanıtım → etiket + arşiv; Fatura ve Hesap → yalnızca
  etiket (Hesap e-postaları hiçbir kuralla arşivlenemez); "Acil / yanıt bekliyor" (yalnızca Kişisel'de,
  yıldız); "Oltalama şüphesi" (her zaman onaya, onaylanırsa etiket + arşiv). Gmail'in Spam klasörü hiç
  kullanılmaz: Gmail'in filtresini eğitip aynı bankanın ekstrelerini de spam'e düşürebilir.
- Eşikler:
  - **Kategori kuralları** yalnızca bir uygulama eşiği kullanır; kategori olasılığı bunun altındaysa
    e-posta Onay Kuyruğu'na düşer (kararsız e-postalar sessizce kaydedilmez).
  - **Evet/hayır kuralları** iki eşik kullanır: "Evet" ≤ görmezden gelme eşiği → yalnızca kayıt;
    arası → onay; ≥ uygulama eşiği → uygulanır. Varsayılanlar: görmezden gelme 0,50; uygulama eşiği
    etiket koyanlarda 0,85, arşivleyenlerde 0,90, Tanıtım'da 0,95.
  - **Komut görevleri** de aynı ayrımı izler: evet/hayır görevi iki eşikli; liste görevi kategori kuralı
    gibi tek eşikli ve yalnızca ilk seçenek modelin en yüksek seçimi olduğunda işlem yapar.
- Mod:
  - **Sadece raporla:** karar kaydedilir, Gmail'e dokunulmaz.
  - **Onaya gönder** ya da puan eşiğin altındaysa: Onay Kuyruğu'na düşer.
  - **Doğrudan uygula** ve puan eşiği geçtiyse: işlem hemen uygulanır.
- **Genel kuru mod** (varsayılan olarak açık) açıkken hiçbir işlem Gmail'e yazılmaz; kararlar "Önerildi"
  olarak kaydedilir. Ayrıca her kuralın kendi **kuru** bayrağı vardır (başlangıçta hepsinde açık):
  genel kuru mod kapalıyken de kuru kural yalnızca önerir. Böylece kurallar tek tek açılabilir.
- Etiketler Gmail'de `MailKarar/…` altında oluşturulur; uygulamanın dokunduğu her e-posta ayrıca
  `MailKarar/İşlendi` etiketini alır.
- Geri alma yalnızca uygulamanın gerçekten değiştirdiği etiketleri eski hâline döndürür (30 gün).
- Ollama 5xx yanıtı verirse ya da bağlantı koparsa istek 2 sn ve 5 sn arayla iki kez yeniden denenir.
  Yine olmazsa e-posta "bekliyor" durumunda kalır ve sonraki taramada baştan işlenir; bir e-postanın
  soruları ya hepsi yanıtlanınca kaydedilir ya hiç, yarım kalan karar ya da çift kayıt olmaz.
- Gmail'in 429 (çok fazla istek) yanıtında istemci bekleyip 5 kez yeniden dener.

## Yapı

```
backend/   FastAPI + SQLite (backend/data/mailkarar.db)
  app/gmail.py       OAuth, okuma, etiket değişiklikleri
  app/classifier.py  karar modelleri (/v1/systemone: noul ve choice) ve sohbet modeli yedeği
  app/engine.py      tarama, kurallar, kuyruk, geri alma, komut görevleri
  app/config.py      ayarlar, kategoriler, başlangıç kuralları, eşik varsayılanları
  app/migrate.py     veritabanı sürüm yükseltmeleri (PRAGMA user_version)
  app/api.py         /api uç noktaları
frontend/  React + TypeScript + Vite
design/    Claude Design kaynak dosyaları
tools/model-tests/   model karşılaştırma ve gerçek e-posta test betikleri (uygulamanın parçası değil)
```

Testler (Gmail ve model taklit edilerek): `cd backend; .\.venv\Scripts\python -m unittest discover -s tests -v`

## Doğrulananlar

- Ollama 0.40.11 ile `tev1:4b` ve `d3:9b` gerçek isteklerle denendi; `/v1/systemone` yanıt biçimleri
  doğrulandı ve testlerde aynen kullanılıyor:
  - evet/hayır: `{"answers": {"<ad>": {"type": "noul", "noul": 0.99}}}`
  - çok seçenek: `{"answers": {"<ad>": {"type": "choice", "choice": "Banka", "probabilities": {...}, "confidence": 0.83}}}`
    (skor olarak `probabilities` kullanılır; `confidence` en yüksek olasılıkla aynı değildir)
- Her iki model de `/api/tags`'te `"capabilities": ["decision", ...]` bildiriyor.

## Henüz doğrulanmayanlar

- Gerçek Gmail hesabıyla OAuth bağlantısı ve okuma çalışıyor; etiket yazma, arşivleme ve geri alma henüz denenmedi.
- Bülten ile Tanıtım ayrımı gerçek e-postalarda henüz doğrulanmadı.
- Yeni sekiz kategorili choice sorusunun gerçek e-postalardaki doğruluğu ölçülmedi. Doğruluk sonuçları
  (bkz. CLAUDE.md) kural başına evet/hayır sorularıyla yapılan v2 testinden; ilk turdaki choice sorusu
  eski kategorileri kullanıyordu.
