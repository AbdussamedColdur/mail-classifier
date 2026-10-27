#!/usr/bin/env python3
"""MailKarar - d3:9b vs tev1:4b vs tev1:0.8b karsilastirma betigi.

test_d3.py temel alinmistir. Ayni 12 sahte Turkce e-posta ile uc modeli,
dort test senaryosunda (noul-TR, noul-EN, choice, govde-uzunlugu) karsilastirir.
Gmail'e dokunmaz, Ollama /v1/systemone uc noktasini kullanir.

Kullanim:
    python test_compare.py
    python test_compare.py --url http://localhost:11434
"""

import argparse
import json
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

TIMEOUT_SECONDS = 60
MODELS = ["d3:9b", "tev1:4b", "tev1:0.8b"]
BODY_MODELS_FOR_LENGTH_TEST = ["d3:9b", "tev1:4b"]
THRESHOLDS = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 0.99]

# -----------------------------------------------------------------------
# Keskinlestirilmis spam/acil olcutleri (tum modeller, tum testlerde ayni)
# -----------------------------------------------------------------------
SPAM_CRITERIA_TR = (
    "Bilinen kurum ve bankalardan gelen fatura/ekstreler spam degildir. "
    "Yalnizca kart, sifre veya kimlik bilgisi isteyen ya da sahte odul "
    "vaat eden e-postalar spam'dir."
)
ACIL_CRITERIA_TR = (
    "Pazarlama dilindeki 'sadece bugun', 'hemen' gibi ifadeler aciliyet "
    "sayilmaz. Yalnizca bir kisinin size yonelttigi sureli is talepleri acildir."
)
SPAM_CRITERIA_EN = (
    "Invoices/statements from known companies and banks are not spam. "
    "Only emails that ask for card, password, or ID information, or that "
    "promise a fake prize, are spam."
)
ACIL_CRITERIA_EN = (
    "Marketing phrases like 'today only' or 'act now' do not count as "
    "urgent. Only a time-bound work request from a person addressed to "
    "you personally is urgent."
)

RULE_ORDER = ["acil", "fatura", "bulten", "musteri", "spam"]

QUESTIONS_TR = {
    "acil": {
        "type": "noul",
        "instructions": "Bu e-posta bugun yanit gerektiren acil bir is talebi mi?",
        "criteria": {"true": ACIL_CRITERIA_TR + " Bu e-posta bu tanima uyuyor.",
                     "false": ACIL_CRITERIA_TR + " Bu e-posta bu tanima uymuyor."},
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
        "criteria": {"true": SPAM_CRITERIA_TR + " Bu e-posta bu tanima uyuyor.",
                     "false": SPAM_CRITERIA_TR + " Bu e-posta bu tanima uymuyor."},
    },
}

QUESTIONS_EN = {
    "acil": {
        "type": "noul",
        "instructions": "Is this email an urgent work request requiring a reply today?",
        "criteria": {"true": ACIL_CRITERIA_EN + " This email matches that definition.",
                     "false": ACIL_CRITERIA_EN + " This email does not match that definition."},
    },
    "fatura": {
        "type": "noul",
        "instructions": "Is this email an invoice or payment notice?",
        "criteria": {
            "true": "The email contains an invoice, e-invoice, bank statement, "
                    "payment notice, or amount owed.",
            "false": "The email is not an invoice or payment notice.",
        },
    },
    "bulten": {
        "type": "noul",
        "instructions": "Is this a newsletter or marketing email?",
        "criteria": {
            "true": "The email is a mass-sent newsletter, campaign, discount "
                    "announcement, or marketing content.",
            "false": "The email is not a newsletter or marketing content; it "
                     "is personal or transactional.",
        },
    },
    "musteri": {
        "type": "noul",
        "instructions": "Is a customer submitting an order, complaint, or support request?",
        "criteria": {
            "true": "The sender is a customer raising an order, complaint, "
                    "or support/help request.",
            "false": "The email is not a customer order/complaint/support request.",
        },
    },
    "spam": {
        "type": "noul",
        "instructions": "Is this email unwanted or phishing (spam)?",
        "criteria": {"true": SPAM_CRITERIA_EN + " This email matches that definition.",
                     "false": SPAM_CRITERIA_EN + " This email does not match that definition."},
    },
}

CHOICE_QUESTION = {
    "kategori": {
        "type": "choice",
        "instructions": "Bu e-posta hangi kategoriye ait?",
        "criteria": {
            "acil": ACIL_CRITERIA_TR + " Bu e-posta bu tanima uyan, bir kisinin "
                    "yonelttigi sureli bir is talebi.",
            "fatura": "Fatura, e-fatura, banka ekstresi ya da abonelik/uyelik "
                      "odeme bildirimi.",
            "musteri": "Bir musterinin siparisi, sikayeti ya da destek talebi.",
            "bulten": "Toplu gonderilen haber bulteni, kampanya ya da pazarlama icerigi.",
            "spam": SPAM_CRITERIA_TR + " Bu e-posta bu tanima uyuyor.",
            "diger": "Yukaridaki kategorilerin hicbirine tam uymayan ama "
                     "anlamli bir e-posta (ör. kargo bildirimi, kisisel mesaj, randevu).",
            "none": "E-posta anlamsiz, bos ya da hicbir kategoriye uymuyor.",
        },
    },
}

# -----------------------------------------------------------------------
# Test verisi (test_d3.py ile ayni 12 e-posta)
# -----------------------------------------------------------------------
EMAILS = [
    {
        "id": "email_01", "name": "Acil is talebi",
        "from": "mudur@sirket.com.tr", "subject": "ACIL: Bugun saat 17:00'ye kadar rapor lazim",
        "body": ("Merhaba, yarinki yonetim kurulu toplantisi icin satis "
                 "raporunun bugun saat 17:00'ye kadar bana ulasmasi gerekiyor. "
                 "Lutfen en kisa surede gonder, cok acil."),
        "expected": {"acil": True, "fatura": False, "bulten": False, "musteri": False, "spam": False},
        "expected_category": ["acil"],
    },
    {
        "id": "email_02", "name": "E-fatura bildirimi",
        "from": "efatura@elektrikdagitim.com.tr", "subject": "Ekim 2026 Donemi Elektrik Faturaniz Hazir",
        "body": ("Sayin musterimiz, Ekim 2026 donemine ait elektrik faturaniz "
                 "342,17 TL tutarindadir. Son odeme tarihi 15 Kasim 2026'dir. "
                 "Faturanizi e-Fatura portalindan goruntuleyebilirsiniz."),
        "expected": {"acil": False, "fatura": True, "bulten": False, "musteri": False, "spam": False},
        "expected_category": ["fatura"],
    },
    {
        "id": "email_03", "name": "Banka ekstresi",
        "from": "bilgi@ornekbank.com.tr", "subject": "Ekim Ayi Kredi Karti Hesap Ozetiniz Hazirlandi",
        "body": ("Degerli musterimiz, 4506 ile biten kredi kartiniza ait Ekim "
                 "ayi hesap ozetiniz hazirlanmistir. Donem borcunuz 1.245,90 TL "
                 "olup son odeme tarihi 20 Kasim 2026'dir."),
        "expected": {"acil": False, "fatura": True, "bulten": False, "musteri": False, "spam": False},
        "expected_category": ["fatura"],
    },
    {
        "id": "email_04", "name": "Musteri sikayeti",
        "from": "ayse.yilmaz@gmail.com", "subject": "Siparisim hala gelmedi - 10 gundur bekliyorum",
        "body": ("Merhaba, 12345 numarali siparisimi 10 gun once verdim ama "
                 "hala elime ulasmadi. Kargo takip numarasi da calismiyor. "
                 "Durumu ogrenebilir miyim, cok magdur oldum."),
        "expected": {"acil": False, "fatura": False, "bulten": False, "musteri": True, "spam": False},
        "expected_category": ["musteri"],
    },
    {
        "id": "email_05", "name": "Haber bulteni",
        "from": "bulten@teknolojihaberleri.com", "subject": "Bu Hafta Teknoloji Dunyasinda Neler Oldu?",
        "body": ("Haftanin one cikan teknoloji haberleri: yapay zeka "
                 "alaninda yeni gelismeler, elektrikli araclarda rekor "
                 "satislar ve daha fazlasi bu sayimizda. Iyi okumalar dileriz."),
        "expected": {"acil": False, "fatura": False, "bulten": True, "musteri": False, "spam": False},
        "expected_category": ["bulten"],
    },
    {
        "id": "email_06", "name": "Kampanya e-postasi",
        "from": "kampanya@magaza.com", "subject": "Sadece Bugun! Tum Urunlerde %40 Indirim",
        "body": ("Kacirilmayacak firsat! Bugune ozel tum urunlerde %40 "
                 "indirim firsatini yakalamak icin hemen alisverise basla. "
                 "Stoklarla sinirlidir, hemen tikla."),
        "expected": {"acil": False, "fatura": False, "bulten": True, "musteri": False, "spam": False},
        "expected_category": ["bulten"],
    },
    {
        "id": "email_07", "name": "Oltalama (phishing)",
        "from": "guvenlik@banka-dogrulama.net", "subject": "Hesabiniz Askiya Alinacak - Hemen Dogrulayin",
        "body": ("Hesabinizda supheli hareket tespit edildi. Hesabinizin "
                 "kapatilmamasi icin asagidaki baglantiya tiklayarak kart "
                 "numaranizi, son kullanma tarihini ve CVV kodunuzu 24 saat "
                 "icinde dogrulamaniz gerekmektedir: http://banka-guvenlik-dogrula.net"),
        "expected": {"acil": False, "fatura": False, "bulten": False, "musteri": False, "spam": True},
        "expected_category": ["spam"],
    },
    {
        "id": "email_08", "name": "Kargo bildirimi",
        "from": "bildirim@hizlikargo.com.tr", "subject": "Paketiniz Yola Cikti - Takip Numaraniz Hazir",
        "body": ("Siparisiniz kargoya verildi. Takip numaraniz: TR998877665. "
                 "Paketinizin yarin adresinize teslim edilmesi beklenmektedir."),
        "expected": {"acil": False, "fatura": False, "bulten": False, "musteri": False, "spam": False},
        "expected_category": ["diger", "none"],
    },
    {
        "id": "email_09", "name": "Kisisel toplanti mesaji",
        "from": "mehmet.demir@gmail.com", "subject": "Yarin kahve icelim mi?",
        "body": ("Selam, yarin ogleden sonra musait misin? Bulusup bir kahve "
                 "icerken sohbet edelim istedim, uzun zamandir gormedik "
                 "birbirimizi."),
        "expected": {"acil": False, "fatura": False, "bulten": False, "musteri": False, "spam": False},
        "expected_category": ["diger", "none"],
    },
    {
        "id": "email_10", "name": "ZOR: Fatura itirazi yapan musteri",
        "from": "fatma.kaya@hotmail.com", "subject": "Faturama Itiraz Ediyorum - Yanlis Tutar Yansitilmis",
        "body": ("Gecen ay kullanmadigim bir hizmet icin faturama 89,90 TL "
                 "ek ucret yansitilmis. Bu tutara itiraz ediyorum, lutfen "
                 "faturami inceleyip iadeyi baslatir misiniz?"),
        "expected": {"acil": False, "fatura": True, "bulten": False, "musteri": True, "spam": False},
        "expected_category": ["musteri", "fatura"],
    },
    {
        "id": "email_11", "name": "ZOR: Uyelik yenileme + indirim onerisi",
        "from": "uyelik@yayinplatformu.com", "subject": "Aboneliginiz Yarin Yenileniyor",
        "body": ("Aylik aboneliginiz yarin 49,90 TL olarak yenilenecektir. "
                 "Odeme yontemi bilginizde degisiklik yoksa ek islem "
                 "yapmaniza gerek yok. Bu arada, yillik pakete gecerek "
                 "%25 tasarruf etme firsatini da kacirmayin."),
        "expected": {"acil": False, "fatura": True, "bulten": True, "musteri": False, "spam": False},
        "expected_category": ["fatura", "bulten"],
    },
    {
        "id": "email_12", "name": "Musteri destek talebi (yazilim hatasi)",
        "from": "destek.musteri@firma.com", "subject": "Uygulamaya Giris Yapamiyorum",
        "body": ("Merhaba, uygulamaniza sifremle giris yapmaya calisiyorum "
                 "ama surekli hata aliyorum. Yardimci olabilir misiniz? "
                 "Acil bir isim icin bugun giris yapmam gerekiyor."),
        "expected": {"acil": True, "fatura": False, "bulten": False, "musteri": True, "spam": False},
        "expected_category": ["musteri", "acil"],
    },
]

# English translations of the email content for the noul-EN test
# (subject/body translated; sender kept as-is). Order matches EMAILS.
EMAILS_EN_TEXT = [
    ("URGENT: Need the report by 5pm today",
     "Hi, I need the sales report to reach me by 5pm today for tomorrow's "
     "board meeting. Please send it as soon as possible, it's very urgent."),
    ("Your October 2026 Electricity Bill Is Ready",
     "Dear customer, your electricity bill for October 2026 is 342.17 TRY. "
     "The due date is November 15, 2026. You can view your bill on the "
     "e-invoice portal."),
    ("Your October Credit Card Statement Is Ready",
     "Dear customer, the statement for your credit card ending in 4506 has "
     "been prepared. Your balance for the period is 1,245.90 TRY, due on "
     "November 20, 2026."),
    ("My order still hasn't arrived - waiting 10 days",
     "Hello, I placed order #12345 ten days ago but it still hasn't "
     "reached me. The tracking number doesn't work either. Can you tell "
     "me the status, I'm quite upset."),
    ("What Happened in Tech This Week?",
     "This week's top tech stories: new developments in AI, record EV "
     "sales, and more in this issue. Happy reading."),
    ("Today Only! 40% Off Everything",
     "Don't miss out! Grab 40% off everything, today only. Shop now "
     "before stock runs out, click now."),
    ("Your Account Will Be Suspended - Verify Now",
     "Suspicious activity was detected on your account. To avoid account "
     "closure, click the link below and verify your card number, "
     "expiration date, and CVV within 24 hours: "
     "http://bank-security-verify.net"),
    ("Your Package Is On Its Way - Tracking Ready",
     "Your order has been shipped. Tracking number: TR998877665. Your "
     "package is expected to be delivered tomorrow."),
    ("Coffee tomorrow?",
     "Hey, are you free tomorrow afternoon? Wanted to grab a coffee and "
     "catch up, haven't seen you in a while."),
    ("Disputing My Bill - Wrong Amount Charged",
     "Last month an 89.90 TRY extra charge was added to my bill for a "
     "service I didn't use. I'm disputing this amount, could you please "
     "review my bill and start a refund?"),
    ("Your Subscription Renews Tomorrow",
     "Your monthly subscription will renew tomorrow at 49.90 TRY. No "
     "action is needed if your payment method is unchanged. By the way, "
     "don't miss the chance to save 25% by switching to the annual plan."),
    ("Can't Log Into The App",
     "Hi, I'm trying to log into your app with my password but keep "
     "getting an error. Can you help? I need to log in today for an "
     "urgent matter."),
]


# -----------------------------------------------------------------------
# HTTP yardimcilari
# -----------------------------------------------------------------------
def call_systemone(base_url, model, state, questions, keep_alive=None, timeout=TIMEOUT_SECONDS):
    url = base_url.rstrip("/") + "/v1/systemone"
    payload = {"model": model, "state": state, "questions": questions}
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
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
                return False, {"request": payload, "error": "Beklenmeyen yanit bicimi (gecerli JSON degil)",
                                "raw_body": raw}, elapsed
    except urllib.error.HTTPError as e:
        elapsed = time.monotonic() - start
        raw = e.read().decode("utf-8", errors="replace")
        return False, {"request": payload, "error": "HTTP {}: {}".format(e.code, raw),
                        "status": e.code, "raw_body": raw}, elapsed
    except urllib.error.URLError as e:
        elapsed = time.monotonic() - start
        if isinstance(e.reason, ConnectionRefusedError) or "refused" in str(e.reason).lower():
            msg = "Ollama'ya baglanilamadi (baglanti reddedildi). 'ollama serve' ile baslatin."
        elif isinstance(e.reason, socket.timeout):
            msg = "Istek {} saniye icinde yanitlanmadi (zaman asimi).".format(timeout)
        else:
            msg = "Baglanti hatasi: {}".format(e.reason)
        return False, {"request": payload, "error": msg}, elapsed
    except socket.timeout:
        elapsed = time.monotonic() - start
        return False, {"request": payload, "error": "Istek {} saniye icinde yanitlanmadi.".format(timeout)}, elapsed


def unload_model(base_url, model):
    """keep_alive:0 ile modeli bellekten atar (sonraki cagri soguk baslangic olur)."""
    call_systemone(base_url, model, "unload-probe", {"q": {"type": "noul", "instructions": "x"}}, keep_alive=0)


def get_ollama_ps():
    try:
        out = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=15)
        lines = [l for l in out.stdout.splitlines() if l.strip()]
    except Exception as e:
        return {"error": str(e), "raw": ""}
    if len(lines) < 2:
        return {"raw": out.stdout, "rows": []}
    rows = []
    for line in lines[1:]:
        m = re.match(
            r"^(\S+)\s+(\S+)\s+([\d.]+\s*[KMGT]?B)\s+(.+?)\s+(\d+)\s+(\S+)\s+(.+)$",
            line.strip(),
        )
        if m:
            rows.append({
                "name": m.group(1), "id": m.group(2), "size": m.group(3),
                "processor": m.group(4), "context": m.group(5),
                "runner": m.group(6), "until": m.group(7),
            })
        else:
            rows.append({"raw_line": line})
    return {"raw": out.stdout, "rows": rows}


def build_state(frm, subject, body, body_limit=2000):
    return "Gonderen: {}\nKonu: {}\nGovde: {}".format(frm, subject, body[:body_limit])


def build_state_en(frm, subject, body, body_limit=2000):
    return "From: {}\nSubject: {}\nBody: {}".format(frm, subject, body[:body_limit])


def confidently_wrong(score, threshold_band=(0.15, 0.85)):
    lo, hi = threshold_band
    return not (lo <= score <= hi)


def threshold_sweep(entries):
    """entries: list of (score, correct:bool). Her esik t icin:
    - applied_n: |score-0.5| esiginin disinda kalan (yani karar 'uygulaniyor') sayisi
    - applied_errors: bunlar arasinda yanlis olanlar
    - review_fraction: onaya dusen (uygulanmayan) oranin yuzdesi
    """
    sweep = []
    total = len(entries)
    for t in THRESHOLDS:
        lo_band = 1 - t
        applied = [(s, c) for (s, c) in entries if s >= t or s <= lo_band]
        applied_n = len(applied)
        applied_errors = sum(1 for (s, c) in applied if not c)
        review_fraction = (1 - applied_n / total) * 100 if total else 0.0
        sweep.append({
            "t": t, "applied_n": applied_n, "applied_errors": applied_errors,
            "review_fraction_pct": review_fraction,
        })
    return sweep


# -----------------------------------------------------------------------
# Test calistiricilar
# -----------------------------------------------------------------------
def run_noul_test(base_url, model, questions, lang_label, body_limit=2000, state_builder=build_state):
    per_rule_entries = {r: [] for r in RULE_ORDER}  # (score, correct)
    per_rule_correct = {r: 0 for r in RULE_ORDER}
    per_rule_total = {r: 0 for r in RULE_ORDER}
    durations = []
    raw_records = []
    errors_detail = []

    for email in EMAILS:
        if state_builder is build_state_en:
            idx = EMAILS.index(email)
            subj, body = EMAILS_EN_TEXT[idx]
            state = state_builder(email["from"], subj, body, body_limit)
        else:
            state = state_builder(email["from"], email["subject"], email["body"], body_limit)

        ok, result, elapsed = call_systemone(base_url, model, state, questions)
        durations.append(elapsed)
        record = {"id": email["id"], "name": email["name"], "state": state, "elapsed": elapsed, "ok": ok}

        if not ok:
            record["error"] = result.get("error")
            record["raw"] = result
            raw_records.append(record)
            errors_detail.append({"email": email["id"], "rule": None, "error": result.get("error")})
            continue

        answers = result["response"].get("answers", {})
        record["raw"] = result
        record["derived"] = {}
        for rule in RULE_ORDER:
            ans = answers.get(rule)
            if ans is None or "noul" not in ans:
                errors_detail.append({"email": email["id"], "rule": rule, "error": "yanitta yok"})
                continue
            score = ans["noul"]
            predicted = score >= 0.5
            expected = email["expected"][rule]
            correct = predicted == expected
            per_rule_total[rule] += 1
            per_rule_entries[rule].append((score, correct))
            if correct:
                per_rule_correct[rule] += 1
            else:
                errors_detail.append({
                    "email": email["id"], "name": email["name"], "rule": rule,
                    "score": score, "expected": expected,
                    "confidently_wrong": confidently_wrong(score),
                })
            record["derived"][rule] = {"score": score, "predicted": predicted,
                                        "expected": expected, "correct": correct}
        raw_records.append(record)

    per_rule_accuracy = {
        r: (per_rule_correct[r] / per_rule_total[r] * 100 if per_rule_total[r] else None)
        for r in RULE_ORDER
    }
    overall_correct = sum(per_rule_correct.values())
    overall_total = sum(per_rule_total.values())
    overall_accuracy = (overall_correct / overall_total * 100) if overall_total else None

    sweeps = {r: threshold_sweep(per_rule_entries[r]) for r in RULE_ORDER}

    return {
        "label": lang_label, "model": model, "body_limit": body_limit,
        "durations": durations,
        "cold_start_seconds": durations[0] if durations else None,
        "warm_avg_seconds": (sum(durations[1:]) / len(durations[1:])) if len(durations) > 1 else None,
        "per_rule_accuracy": per_rule_accuracy,
        "overall_accuracy": overall_accuracy,
        "errors": errors_detail,
        "threshold_sweep": sweeps,
        "raw": raw_records,
    }


def run_choice_test(base_url, model):
    durations = []
    raw_records = []
    correct_n = 0
    total_n = 0
    conf_entries = []  # (confidence, correct) for sweep
    errors_detail = []

    for email in EMAILS:
        state = build_state(email["from"], email["subject"], email["body"])
        ok, result, elapsed = call_systemone(base_url, model, state, CHOICE_QUESTION)
        durations.append(elapsed)
        record = {"id": email["id"], "name": email["name"], "elapsed": elapsed, "ok": ok}

        if not ok:
            record["error"] = result.get("error")
            record["raw"] = result
            raw_records.append(record)
            errors_detail.append({"email": email["id"], "error": result.get("error")})
            continue

        answers = result["response"].get("answers", {})
        ans = answers.get("kategori")
        record["raw"] = result
        if ans is None or "choice" not in ans:
            record["error"] = "beklenmeyen yanit bicimi"
            errors_detail.append({"email": email["id"], "error": "answers.kategori yok"})
            raw_records.append(record)
            continue

        choice = ans["choice"]
        confidence = ans.get("confidence")
        probabilities = ans.get("probabilities")
        correct = choice in email["expected_category"]
        total_n += 1
        if correct:
            correct_n += 1
        else:
            errors_detail.append({
                "email": email["id"], "name": email["name"], "got": choice,
                "expected": email["expected_category"], "confidence": confidence,
                "probabilities": probabilities,
            })
        if confidence is not None:
            conf_entries.append((confidence, correct))

        record["derived"] = {"choice": choice, "confidence": confidence,
                              "probabilities": probabilities, "expected": email["expected_category"],
                              "correct": correct}
        raw_records.append(record)

    accuracy = (correct_n / total_n * 100) if total_n else None
    sweep = threshold_sweep(conf_entries) if conf_entries else None

    return {
        "model": model, "durations": durations,
        "cold_start_seconds": durations[0] if durations else None,
        "warm_avg_seconds": (sum(durations[1:]) / len(durations[1:])) if len(durations) > 1 else None,
        "accuracy": accuracy, "errors": errors_detail,
        "confidence_sweep": sweep, "raw": raw_records,
    }


# -----------------------------------------------------------------------
# Rapor yardimcilari
# -----------------------------------------------------------------------
def print_header(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def summarize_errors(errors_detail):
    confident = sum(1 for e in errors_detail if e.get("confidently_wrong"))
    uncertain = sum(1 for e in errors_detail if "confidently_wrong" in e and not e.get("confidently_wrong"))
    return confident, uncertain


def main():
    parser = argparse.ArgumentParser(description="MailKarar model karsilastirma betigi (d3:9b / tev1:4b / tev1:0.8b)")
    parser.add_argument("--url", default="http://localhost:11434", help="Ollama adresi")
    args = parser.parse_args()
    base_url = args.url

    # on kosul dogrulama
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/api/tags", timeout=10) as resp:
            tags = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print("HATA: Ollama'ya ulasilamadi ({}).".format(e.reason))
        sys.exit(1)

    installed = {m["name"]: m for m in tags.get("models", [])}
    for model in MODELS:
        if model not in installed:
            print("HATA: '{}' modeli kurulu degil. 'ollama pull {}' calistirin.".format(model, model))
            sys.exit(1)
        caps = installed[model]["details"]
        print("Model bulundu: {} (capabilities: {})".format(model, installed[model].get("capabilities")))

    results = {"generated_at": datetime.now().isoformat(), "url": base_url, "models": MODELS, "tests": {}}
    ps_snapshots = {}

    for model in MODELS:
        print_header("MODEL: {}".format(model))
        print("Soguk baslangic icin model bellekten atiliyor (keep_alive:0)...")
        unload_model(base_url, model)
        time.sleep(1)

        print("[1/3+] noul - Turkce talimat/olcut")
        r_tr = run_noul_test(base_url, model, QUESTIONS_TR, "noul_tr")
        print("  ilk istek (soguk): {:.2f} sn | sicak ortalama: {:.2f} sn | genel dogruluk: {:.1f}%".format(
            r_tr["cold_start_seconds"] or 0, r_tr["warm_avg_seconds"] or 0, r_tr["overall_accuracy"] or 0))

        print("[2/3+] noul - Ingilizce talimat/olcut (e-posta metni Turkce)")
        r_en = run_noul_test(base_url, model, QUESTIONS_EN, "noul_en", state_builder=build_state_en)
        print("  sicak ortalama: {:.2f} sn | genel dogruluk: {:.1f}%".format(
            r_en["warm_avg_seconds"] or r_en["cold_start_seconds"] or 0, r_en["overall_accuracy"] or 0))

        print("[3/3+] choice - tek kategori sorusu")
        r_choice = run_choice_test(base_url, model)
        print("  sicak ortalama: {:.2f} sn | dogruluk: {:.1f}%".format(
            r_choice["warm_avg_seconds"] or r_choice["cold_start_seconds"] or 0, r_choice["accuracy"] or 0))

        body_length_results = {}
        if model in BODY_MODELS_FOR_LENGTH_TEST:
            for length in (800, 1500, 2000):
                print("[govde={}] noul - Turkce".format(length))
                r_len = run_noul_test(base_url, model, QUESTIONS_TR, "noul_tr_len{}".format(length), body_limit=length)
                body_length_results[str(length)] = r_len
                print("  dogruluk: {:.1f}% | ortalama sure: {:.2f} sn".format(
                    r_len["overall_accuracy"] or 0,
                    (sum(r_len["durations"]) / len(r_len["durations"])) if r_len["durations"] else 0))

        ps = get_ollama_ps()
        ps_snapshots[model] = ps
        for row in ps.get("rows", []):
            if row.get("name") == model or (row.get("raw_line") and model in row["raw_line"]):
                print("  ollama ps -> {}".format(row))

        print("Model testleri bitti, bellekten atiliyor...")
        unload_model(base_url, model)

        results["tests"][model] = {
            "noul_tr": r_tr, "noul_en": r_en, "choice": r_choice,
            "body_length": body_length_results,
        }

    results["ollama_ps_snapshots"] = ps_snapshots

    # ------------------- konsol ozet tablolari -------------------
    print_header("OZET: Model x Test Dogrulugu")
    print("{:<10} {:<12} {:<12} {:<10}".format("Model", "noul-TR", "noul-EN", "choice"))
    for model in MODELS:
        t = results["tests"][model]
        print("{:<10} {:<12.1f} {:<12.1f} {:<10.1f}".format(
            model, t["noul_tr"]["overall_accuracy"] or 0,
            t["noul_en"]["overall_accuracy"] or 0, t["choice"]["accuracy"] or 0))

    print_header("OZET: Kural Basina Dogruluk (noul-TR)")
    print("{:<10} " + "".join("{:<10}".format(r) for r in RULE_ORDER))
    header = "{:<10} ".format("Model") + "".join("{:<10}".format(r) for r in RULE_ORDER)
    print(header)
    for model in MODELS:
        acc = results["tests"][model]["noul_tr"]["per_rule_accuracy"]
        row = "{:<10} ".format(model) + "".join("{:<10.1f}".format(acc[r] or 0) for r in RULE_ORDER)
        print(row)

    print_header("OZET: Yanlislarin Kararlilik Dagilimi (noul-TR)")
    print("{:<10} {:<20} {:<20}".format("Model", "Kararsiz(0.15-0.85)", "Kararli ama Yanlis"))
    for model in MODELS:
        errs = results["tests"][model]["noul_tr"]["errors"]
        confident = sum(1 for e in errs if e.get("confidently_wrong"))
        uncertain = sum(1 for e in errs if "confidently_wrong" in e and not e.get("confidently_wrong"))
        print("{:<10} {:<20} {:<20}".format(model, uncertain, confident))

    print_header("OZET: Govde Uzunlugu Etkisi (noul-TR, sadece d3:9b ve tev1:4b)")
    for model in BODY_MODELS_FOR_LENGTH_TEST:
        bl = results["tests"][model]["body_length"]
        print(" {}:".format(model))
        for length in ("800", "1500", "2000"):
            r = bl.get(length)
            if r:
                print("   {} karakter -> dogruluk {:.1f}%, ortalama sure {:.2f} sn".format(
                    length, r["overall_accuracy"] or 0,
                    (sum(r["durations"]) / len(r["durations"])) if r["durations"] else 0))

    print_header("OZET: Bellek (ollama ps, test sonunda / model hala sicakken)")
    for model, ps in ps_snapshots.items():
        for row in ps.get("rows", []):
            if "raw_line" not in row:
                print("  {}: {} ({})".format(row["name"], row["size"], row["processor"]))

    out_name = "results_compare_{}.json".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    with open(out_name, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nTum ham sonuclar kaydedildi: {}".format(out_name))


if __name__ == "__main__":
    main()
