# MailKarar — tasarım kaynak dosyaları

Bu klasör, Claude Design tuvalindeki MailKarar ekranlarının kaynak kodudur.

| Dosya | Ekran |
|---|---|
| App.dc.html | Etkileşimli prototip (tüm ekranlar, ortak kuru mod) |
| Main.dc.html / MainDark.dc.html | Panel (açık / koyu) |
| Queue.dc.html | Onay Kuyruğu |
| Command.dc.html | Komut |
| Rules.dc.html | Kurallar |
| Logs.dc.html | Kayıtlar |
| Accounts.dc.html | Hesaplar |
| Settings.dc.html | Ayarlar |
| States.dc.html | Hata ve boş durumlar |
| canvas.json | Tuvaldeki yerleşim |

## Önemli

Dosyalar tasarım aracının kendi bileşen formatındadır (`<x-dc>`, `<sc-for>`, `<sc-if>`,
`{{değer}}` yer tutucuları, `DCLogic` sınıfı). Tarayıcıda doğrudan açıldığında düzgün
çalışmaz; çalışan bir ön yüz için React veya sade HTML/JS'e dönüştürülmeleri gerekir.

Doğrudan yeniden kullanılabilecek kısımlar:

- **Renk ve tema sistemi:** her dosyanın `<style>` bloğundaki `.mk` (açık) ve `.mk.dk` (koyu)
  CSS değişkenleri — `--bg`, `--card`, `--line`, `--tx`, `--mut`, `--acc`,
  durum renkleri `--gn` (bağlı/uygulandı), `--am` (onay bekliyor), `--rd` (hata), `--gy` (kuru mod).
- **Yerleşim ve bileşen işaretlemesi:** satır içi stillerle düz HTML.
- **Ekran mantığı:** her dosyanın sonundaki `renderVals()` içinde (filtreler, geri al, eşik hesabı vb.).

Tüm veriler örnek veridir; Gmail ve Ollama bağlantısı yoktur.
