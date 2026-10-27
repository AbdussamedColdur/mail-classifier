# MailKarar

Gmail'e gelen e-postaları yerel bir karar modeline (Ollama'da `d3`) sınıflandırtan ve sonuca göre
Gmail'de etiketleme, arşivleme, yıldızlama ya da okundu işaretleme yapan yerel bir uygulama.
E-postaların içeriği hiçbir yapay zekâ servisine gitmez; Gmail'e yalnızca Google API'si üzerinden bağlanılır.

Arayüz `design/` klasöründeki Claude Design tasarımına göre yazıldı.

## Çalıştırma

```powershell
.\start.ps1
```

İlk çalıştırmada Python ortamını ve ön yüz paketlerini kurar, ön yüzü derler ve
<http://127.0.0.1:8000> adresini açar. Sunucu yalnızca bu bilgisayardan erişilebilir (127.0.0.1).

Geliştirme sırasında ön yüzü ayrı çalıştırmak için:

```powershell
cd backend; .\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
cd frontend; npm run dev      # http://127.0.0.1:5173, /api isteklerini 8000'e iletir
```

## Gereksinimler

- Python 3.10+, Node 18+
- **Ollama 0.40.9 veya üstü** ve bir d3 modeli: `ollama pull d3:9b` (ya da daha hafif `d3:4b`).
  d3 başka bir model türü; sohbet etmez, verdiğiniz seçeneklere puan verir.
  d3 yoksa Ayarlar'dan yüklü herhangi bir sohbet modeli (ör. Qwen) seçilebilir; o zaman uygulama
  modelden JSON olarak seçenek başına olasılık ister.

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
- Her e-posta önce bir kategoriye konur (Fatura, Müşteri, Bülten, Spam, Diğer). Kategoriye bağlı
  kurallar bu karara göre, kategoriden bağımsız kurallar ise kendi evet/hayır sorularıyla çalışır.
- Bir kural tetiklendiğinde:
  - **Sadece raporla:** karar kaydedilir, Gmail'e dokunulmaz.
  - **Onaya gönder** ya da puan eşiğin altındaysa: Onay Kuyruğu'na düşer.
  - **Doğrudan uygula** ve puan eşiği geçtiyse: işlem hemen uygulanır.
- **Kuru mod** (varsayılan olarak açık) açıkken hiçbir işlem Gmail'e yazılmaz; kararlar "Önerildi" olarak kaydedilir.
- Etiketler Gmail'de `MailKarar/…` altında oluşturulur; uygulamanın dokunduğu her e-posta ayrıca
  `MailKarar/İşlendi` etiketini alır.
- Geri alma yalnızca uygulamanın gerçekten değiştirdiği etiketleri eski hâline döndürür (30 gün).
- Ollama kapalıyken gelen e-postalar bekler; model geri gelince sırayla işlenir.
- Gmail'in 429 (çok fazla istek) yanıtında istemci bekleyip 5 kez yeniden dener.

## Yapı

```
backend/   FastAPI + SQLite (backend/data/mailkarar.db)
  app/gmail.py       OAuth, okuma, etiket değişiklikleri
  app/classifier.py  d3 (/v1/systemone) ve sohbet modeli yedeği
  app/engine.py      tarama, kurallar, kuyruk, geri alma, komut görevleri
  app/api.py         /api uç noktaları
frontend/  React + TypeScript + Vite
design/    Claude Design kaynak dosyaları
```

Testler (Gmail ve model taklit edilerek): `cd backend; .\.venv\Scripts\python -m unittest discover -s tests -v`

## Henüz doğrulanmayanlar

- d3'ün `/v1/systemone` uç noktası Ollama sayfasındaki örneğe göre yazıldı; bu bilgisayardaki Ollama
  0.23.1 olduğu için gerçek modelle denenmedi. Yanıt biçimi farklıysa hata mesajı Panel'de ve
  e-postanın kaydında görünür (`classifier._probability`).
- Gerçek bir Gmail hesabıyla OAuth akışı henüz denenmedi.
