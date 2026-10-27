#!/usr/bin/env python3
"""MailKarar icin d3 karar modeli test betigi.

Ollama'nin /v1/systemone uc noktasini (gercek e-posta / Gmail'e dokunmadan)
sahte Turkce e-postalarla test eder; model cevaplarini beklenen cevaplarla
karsilastirir ve dogruluk / sure istatistikleri uretir.

Kullanim:
    python test_d3.py
    python test_d3.py --model d3:9b --url http://localhost:11434
"""

import argparse
import json
import socket
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

BODY_LIMIT = 2000
TIMEOUT_SECONDS = 60
NOUL_THRESHOLD = 0.5

# -----------------------------------------------------------------------
# Kurallar (soru seti) - her biri /v1/systemone icin tek bir "question"
# -----------------------------------------------------------------------
QUESTIONS = {
    "acil": {
        "type": "noul",
        "instructions": "Bu e-posta bugun yanit gerektiren acil bir is talebi mi?",
        "criteria": {
            "true": "E-posta, bugun icinde yanitlanmasi veya islem yapilmasi "
                    "gereken bir aciliyet bildiriyor (ör. 'acil', 'bugun', "
                    "'hemen', yaklasan bir son teslim tarihi).",
            "false": "E-posta aciliyet bildirmiyor ya da bugun yanit "
                     "gerektiren bir is talebi degil.",
        },
    },
    "fatura": {
        "type": "noul",
        "instructions": "Bu e-posta bir fatura veya odeme bildirimi mi?",
        "criteria": {
            "true": "E-posta bir fatura, e-fatura, banka ekstresi, odeme "
                    "bildirimi veya borc/tutar bilgisi iceriyor.",
            "false": "E-posta bir fatura ya da odeme bildirimi degil.",
        },
    },
    "bulten": {
        "type": "noul",
        "instructions": "Bu bir bulten ya da pazarlama e-postasi mi?",
        "criteria": {
            "true": "E-posta toplu gonderilen bir haber bulteni, kampanya, "
                    "indirim duyurusu ya da pazarlama icerigi.",
            "false": "E-posta bir bulten ya da pazarlama icerigi degil, "
                     "kisiye ozel ya da islemsel bir mesaj.",
        },
    },
    "musteri": {
        "type": "noul",
        "instructions": "Bir musteri siparis, sikayet ya da destek talebi mi iletiyor?",
        "criteria": {
            "true": "Gonderen bir musteri ve siparisiyle, sikayetiyle ya da "
                    "destek/yardim talebiyle ilgili bir konu iletiyor.",
            "false": "E-posta bir musteri siparis/sikayet/destek talebi degil.",
        },
    },
    "spam": {
        "type": "noul",
        "instructions": "Bu e-posta istenmeyen ya da oltalama amacli mi?",
        "criteria": {
            "true": "E-posta supheli bir baglanti/talep iceriyor, kimlik "
                    "veya kart bilgisi istiyor, ya da istenmeyen/oltalama "
                    "(phishing) amacli gorunuyor.",
            "false": "E-posta istenmeyen ya da oltalama amacli degil.",
        },
    },
}

RULE_ORDER = ["acil", "fatura", "bulten", "musteri", "spam"]

# -----------------------------------------------------------------------
# Test verisi: beklenen cevaplariyla birlikte sahte Turkce e-postalar
# -----------------------------------------------------------------------
EMAILS = [
    {
        "id": "email_01",
        "name": "Acil is talebi",
        "from": "mudur@sirket.com.tr",
        "subject": "ACIL: Bugun saat 17:00'ye kadar rapor lazim",
        "body": (
            "Merhaba, yarinki yonetim kurulu toplantisi icin satis "
            "raporunun bugun saat 17:00'ye kadar bana ulasmasi gerekiyor. "
            "Lutfen en kisa surede gonder, cok acil."
        ),
        "expected": {"acil": True, "fatura": False, "bulten": False, "musteri": False, "spam": False},
    },
    {
        "id": "email_02",
        "name": "E-fatura bildirimi",
        "from": "efatura@elektrikdagitim.com.tr",
        "subject": "Ekim 2026 Donemi Elektrik Faturaniz Hazir",
        "body": (
            "Sayin musterimiz, Ekim 2026 donemine ait elektrik faturaniz "
            "342,17 TL tutarindadir. Son odeme tarihi 15 Kasim 2026'dir. "
            "Faturanizi e-Fatura portalindan goruntuleyebilirsiniz."
        ),
        "expected": {"acil": False, "fatura": True, "bulten": False, "musteri": False, "spam": False},
    },
    {
        "id": "email_03",
        "name": "Banka ekstresi",
        "from": "bilgi@ornekbank.com.tr",
        "subject": "Ekim Ayi Kredi Karti Hesap Ozetiniz Hazirlandi",
        "body": (
            "Degerli musterimiz, 4506 ile biten kredi kartiniza ait Ekim "
            "ayi hesap ozetiniz hazirlanmistir. Donem borcunuz 1.245,90 TL "
            "olup son odeme tarihi 20 Kasim 2026'dir."
        ),
        "expected": {"acil": False, "fatura": True, "bulten": False, "musteri": False, "spam": False},
    },
    {
        "id": "email_04",
        "name": "Musteri sikayeti",
        "from": "ayse.yilmaz@gmail.com",
        "subject": "Siparisim hala gelmedi - 10 gundur bekliyorum",
        "body": (
            "Merhaba, 12345 numarali siparisimi 10 gun once verdim ama "
            "hala elime ulasmadi. Kargo takip numarasi da calismiyor. "
            "Durumu ogrenebilir miyim, cok magdur oldum."
        ),
        "expected": {"acil": False, "fatura": False, "bulten": False, "musteri": True, "spam": False},
    },
    {
        "id": "email_05",
        "name": "Haber bulteni",
        "from": "bulten@teknolojihaberleri.com",
        "subject": "Bu Hafta Teknoloji Dunyasinda Neler Oldu?",
        "body": (
            "Haftanin one cikan teknoloji haberleri: yapay zeka "
            "alaninda yeni gelismeler, elektrikli araclarda rekor "
            "satislar ve daha fazlasi bu sayimizda. Iyi okumalar dileriz."
        ),
        "expected": {"acil": False, "fatura": False, "bulten": True, "musteri": False, "spam": False},
    },
    {
        "id": "email_06",
        "name": "Kampanya e-postasi",
        "from": "kampanya@magaza.com",
        "subject": "Sadece Bugun! Tum Urunlerde %40 Indirim",
        "body": (
            "Kacirilmayacak firsat! Bugune ozel tum urunlerde %40 "
            "indirim firsatini yakalamak icin hemen alisverise basla. "
            "Stoklarla sinirlidir, hemen tikla."
        ),
        "expected": {"acil": False, "fatura": False, "bulten": True, "musteri": False, "spam": False},
    },
    {
        "id": "email_07",
        "name": "Oltalama (phishing)",
        "from": "guvenlik@banka-dogrulama.net",
        "subject": "Hesabiniz Askiya Alinacak - Hemen Dogrulayin",
        "body": (
            "Hesabinizda supheli hareket tespit edildi. Hesabinizin "
            "kapatilmamasi icin asagidaki baglantiya tiklayarak kart "
            "numaranizi, son kullanma tarihini ve CVV kodunuzu 24 saat "
            "icinde dogrulamaniz gerekmektedir: http://banka-guvenlik-dogrula.net"
        ),
        "expected": {"acil": True, "fatura": False, "bulten": False, "musteri": False, "spam": True},
    },
    {
        "id": "email_08",
        "name": "Kargo bildirimi",
        "from": "bildirim@hizlikargo.com.tr",
        "subject": "Paketiniz Yola Cikti - Takip Numaraniz Hazir",
        "body": (
            "Siparisiniz kargoya verildi. Takip numaraniz: TR998877665. "
            "Paketinizin yarin adresinize teslim edilmesi beklenmektedir."
        ),
        "expected": {"acil": False, "fatura": False, "bulten": False, "musteri": False, "spam": False},
    },
    {
        "id": "email_09",
        "name": "Kisisel toplanti mesaji",
        "from": "mehmet.demir@gmail.com",
        "subject": "Yarin kahve icelim mi?",
        "body": (
            "Selam, yarin ogleden sonra musait misin? Bulusup bir kahve "
            "icerken sohbet edelim istedim, uzun zamandir gormedik "
            "birbirimizi."
        ),
        "expected": {"acil": False, "fatura": False, "bulten": False, "musteri": False, "spam": False},
    },
    {
        "id": "email_10",
        "name": "ZOR: Fatura itirazi yapan musteri",
        "from": "fatma.kaya@hotmail.com",
        "subject": "Faturama Itiraz Ediyorum - Yanlis Tutar Yansitilmis",
        "body": (
            "Gecen ay kullanmadigim bir hizmet icin faturama 89,90 TL "
            "ek ucret yansitilmis. Bu tutara itiraz ediyorum, lutfen "
            "faturami inceleyip iadeyi baslatir misiniz?"
        ),
        "expected": {"acil": False, "fatura": True, "bulten": False, "musteri": True, "spam": False},
    },
    {
        "id": "email_11",
        "name": "ZOR: Uyelik yenileme + indirim onerisi",
        "from": "uyelik@yayinplatformu.com",
        "subject": "Aboneliginiz Yarin Yenileniyor",
        "body": (
            "Aylik aboneliginiz yarin 49,90 TL olarak yenilenecektir. "
            "Odeme yontemi bilginizde degisiklik yoksa ek islem "
            "yapmaniza gerek yok. Bu arada, yillik pakete gecerek "
            "%25 tasarruf etme firsatini da kacirmayin."
        ),
        "expected": {"acil": False, "fatura": True, "bulten": True, "musteri": False, "spam": False},
    },
    {
        "id": "email_12",
        "name": "Musteri destek talebi (yazilim hatasi)",
        "from": "destek.musteri@firma.com",
        "subject": "Uygulamaya Giris Yapamiyorum",
        "body": (
            "Merhaba, uygulamaniza sifremle giris yapmaya calisiyorum "
            "ama surekli hata aliyorum. Yardimci olabilir misiniz? "
            "Acil bir isim icin bugun giris yapmam gerekiyor."
        ),
        "expected": {"acil": True, "fatura": False, "bulten": False, "musteri": True, "spam": False},
    },
]


def build_state(frm, subject, body):
    truncated = body[:BODY_LIMIT]
    return "Gonderen: {}\nKonu: {}\nGovde: {}".format(frm, subject, truncated)


def call_systemone(base_url, model, state, timeout=TIMEOUT_SECONDS):
    """POST /v1/systemone. Basari: (True, payload_dict, elapsed).
    Hata: (False, {"status": int|None, "body": str, "error": str}, elapsed)."""
    url = base_url.rstrip("/") + "/v1/systemone"
    payload = {"model": model, "state": state, "questions": QUESTIONS}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            elapsed = time.monotonic() - start
            try:
                return True, {"request": payload, "response": json.loads(raw)}, elapsed
            except json.JSONDecodeError:
                return False, {
                    "request": payload,
                    "error": "Beklenmeyen yanit bicimi (gecerli JSON degil)",
                    "raw_body": raw,
                }, elapsed
    except urllib.error.HTTPError as e:
        elapsed = time.monotonic() - start
        raw = e.read().decode("utf-8", errors="replace")
        return False, {
            "request": payload,
            "error": "HTTP {}: {}".format(e.code, raw),
            "status": e.code,
            "raw_body": raw,
        }, elapsed
    except urllib.error.URLError as e:
        elapsed = time.monotonic() - start
        if isinstance(e.reason, ConnectionRefusedError) or "refused" in str(e.reason).lower():
            msg = ("Ollama'ya baglanilamadi (baglanti reddedildi). "
                   "Ollama calisiyor mu? -> 'ollama serve' ile baslatin, "
                   "ya da --url ile dogru adresi verin. Denenen adres: " + url)
        elif isinstance(e.reason, socket.timeout):
            msg = "Istek {} saniye icinde yanitlanmadi (zaman asimi).".format(timeout)
        else:
            msg = "Baglanti hatasi: {}".format(e.reason)
        return False, {"request": payload, "error": msg}, elapsed
    except socket.timeout:
        elapsed = time.monotonic() - start
        return False, {
            "request": payload,
            "error": "Istek {} saniye icinde yanitlanmadi (zaman asimi).".format(timeout),
        }, elapsed


def check_prereqs(base_url, model):
    """Baslamadan once Ollama'nin ayakta oldugunu ve modelin kurulu oldugunu dogrula."""
    version_url = base_url.rstrip("/") + "/api/version"
    tags_url = base_url.rstrip("/") + "/api/tags"

    try:
        with urllib.request.urlopen(version_url, timeout=10) as resp:
            version_info = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print("HATA: Ollama'ya ulasilamadi ({}).".format(e.reason))
        print("  -> Ollama'nin calistigindan emin olun: 'ollama serve'")
        print("  -> Denenen adres: {}".format(base_url))
        sys.exit(1)

    try:
        with urllib.request.urlopen(tags_url, timeout=10) as resp:
            tags_info = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print("HATA: /api/tags adresine ulasilamadi ({}).".format(e.reason))
        sys.exit(1)

    installed = [m["name"] for m in tags_info.get("models", [])]
    print("Ollama surumu: {}".format(version_info.get("version", "bilinmiyor")))
    print("Kurulu modeller: {}".format(", ".join(installed) if installed else "(yok)"))

    if model not in installed:
        print("HATA: '{}' modeli kurulu degil.".format(model))
        print("  -> Kurulu modeller: {}".format(", ".join(installed) if installed else "(yok)"))
        print("  -> --model argumaniyla dogru model adini verin (ör. --model d3:9b)")
        sys.exit(1)

    print("Model '{}' bulundu, teste devam ediliyor.\n".format(model))


def main():
    parser = argparse.ArgumentParser(description="MailKarar d3 karar modeli test betigi")
    parser.add_argument("--model", default="d3:9b", help="Ollama model adi (varsayilan: d3:9b)")
    parser.add_argument("--url", default="http://localhost:11434", help="Ollama adresi")
    args = parser.parse_args()

    check_prereqs(args.url, args.model)

    all_results = []
    per_rule_correct = {r: 0 for r in RULE_ORDER}
    per_rule_total = {r: 0 for r in RULE_ORDER}
    overall_correct = 0
    overall_total = 0
    durations = []

    print("{:<4} {:<42} {:<8} {:<9} {:<8} {:<6} {:<6}".format(
        "No", "E-posta / Kural", "Model", "Skor", "Beklenen", "Dogru", "Sure(s)"))
    print("-" * 95)

    for idx, email in enumerate(EMAILS, start=1):
        state = build_state(email["from"], email["subject"], email["body"])
        ok, result, elapsed = call_systemone(args.url, args.model, state)
        durations.append(elapsed)

        record = {
            "id": email["id"],
            "name": email["name"],
            "state": state,
            "expected": email["expected"],
            "elapsed_seconds": elapsed,
            "ok": ok,
        }

        if not ok:
            print("{:<4} {:<42} HATA: {}".format(idx, email["name"], result.get("error")))
            if "raw_body" in result:
                print("      Ham yanit: {}".format(result["raw_body"]))
            record["error"] = result.get("error")
            record["raw"] = result
            all_results.append(record)
            continue

        response = result["response"]
        answers = response.get("answers")
        if not isinstance(answers, dict):
            print("{:<4} {:<42} HATA: beklenmeyen yanit bicimi".format(idx, email["name"]))
            print("      Ham yanit: {}".format(json.dumps(response, ensure_ascii=False)))
            record["error"] = "answers alani yok/gecersiz"
            record["raw"] = result
            all_results.append(record)
            continue

        record["raw"] = result
        record["derived"] = {}

        first_row = True
        for rule in RULE_ORDER:
            ans = answers.get(rule)
            if ans is None or "noul" not in ans:
                print("{:<4} {:<42} HATA: '{}' sorusu yanitta yok".format(idx, email["name"], rule))
                continue

            score = ans["noul"]
            predicted = score >= NOUL_THRESHOLD
            expected = email["expected"][rule]
            correct = predicted == expected
            confidence = abs(score - 0.5) * 2  # 0 = kararsiz, 1 = tam emin

            per_rule_total[rule] += 1
            overall_total += 1
            if correct:
                per_rule_correct[rule] += 1
                overall_correct += 1

            record["derived"][rule] = {
                "score": score, "predicted": predicted,
                "expected": expected, "correct": correct, "confidence": confidence,
            }

            is_first = first_row
            label = "{:<4} {:<42}".format(idx, email["name"]) if is_first else " " * 46
            first_row = False
            print("{} {:<8} {:<9.3f} {:<8} {:<6} {:<6.2f}".format(
                label, rule, score, str(expected), "OK" if correct else "YANLIS",
                elapsed if is_first else 0.0))

        all_results.append(record)

    print("-" * 95)
    print("\nKural basina dogruluk:")
    for rule in RULE_ORDER:
        total = per_rule_total[rule]
        correct = per_rule_correct[rule]
        pct = (correct / total * 100) if total else 0.0
        print("  {:<10} {}/{} ({:.1f}%)".format(rule, correct, total, pct))

    overall_pct = (overall_correct / overall_total * 100) if overall_total else 0.0
    print("\nGenel dogruluk: {}/{} ({:.1f}%)".format(overall_correct, overall_total, overall_pct))

    if durations:
        first = durations[0]
        rest = durations[1:]
        avg_rest = sum(rest) / len(rest) if rest else first
        print("\nIlk istek suresi (model yukleme dahil): {:.2f} sn".format(first))
        print("Sonraki istekler ortalama suresi: {:.2f} sn".format(avg_rest))
        print("Tum istekler ortalama suresi: {:.2f} sn".format(sum(durations) / len(durations)))

    out_name = "results_{}.json".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    with open(out_name, "w", encoding="utf-8") as f:
        json.dump({
            "model": args.model,
            "url": args.url,
            "timestamp": datetime.now().isoformat(),
            "overall_accuracy": overall_pct,
            "per_rule_accuracy": {
                r: (per_rule_correct[r] / per_rule_total[r] * 100 if per_rule_total[r] else None)
                for r in RULE_ORDER
            },
            "durations_seconds": durations,
            "results": all_results,
        }, f, ensure_ascii=False, indent=2)
    print("\nHam istek/yanitlar kaydedildi: {}".format(out_name))


if __name__ == "__main__":
    main()
