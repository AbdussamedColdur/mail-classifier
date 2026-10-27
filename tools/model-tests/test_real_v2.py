#!/usr/bin/env python3
"""MailKarar v2 - guncellenmis kurallar (banka kurali eklendi, spam/bulten/fatura
olcutleri yeniden tanimlandi). Sadece d3:9b ve tev1:4b. sample_v2.json (144 e-posta)
uzerinde calisir. Gmail'e dokunmaz, konsola govde basmaz."""

import json
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime

MODELS = ["d3:9b", "tev1:4b"]
TIMEOUT_SECONDS = 60
RULE_ORDER = ["acil", "fatura", "bulten", "musteri", "spam", "banka"]

QUESTIONS_TR = {
    "acil": {
        "type": "noul",
        "instructions": "Bu e-posta bugun yanit gerektiren acil bir is talebi mi?",
        "criteria": {
            "true": "Pazarlama dilindeki 'sadece bugun', 'hemen' gibi ifadeler "
                    "aciliyet sayilmaz. Yalnizca bir kisinin size yonelttigi sureli "
                    "is talepleri acildir. Bu e-posta bu tanima uyuyor.",
            "false": "Pazarlama dilindeki 'sadece bugun', 'hemen' gibi ifadeler "
                     "aciliyet sayilmaz. Yalnizca bir kisinin size yonelttigi sureli "
                     "is talepleri acildir. Bu e-posta bu tanima uymuyor.",
        },
    },
    "fatura": {
        "type": "noul",
        "instructions": "Bu e-posta bir fatura veya odeme bildirimi mi?",
        "criteria": {
            "true": "Fatura, e-Arsiv fatura, odeme veya borc bildirimi, "
                    "'faturaniz hazir' e-postalari.",
            "false": "E-posta bir fatura, e-Arsiv fatura ya da odeme/borc "
                     "bildirimi degil.",
        },
    },
    "bulten": {
        "type": "noul",
        "instructions": "Bu bir bulten ya da haber e-postasi mi?",
        "criteria": {
            "true": "Abone olunan, satis amaci tasimayan icerik/haber bulteni.",
            "false": "Abone olunan, satis amaci tasimayan bir icerik/haber bulteni "
                     "degil. Agirlikli olarak kampanya iceriyorsa bulten degil, spam'dir.",
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
        "instructions": "Bu e-posta spam mi?",
        "criteria": {
            "true": "Bir urun veya hizmeti satmaya ya da tanitmaya calisan e-posta "
                    "(kampanya, indirim, urun reklami, size ozel teklif) - bankalarin "
                    "ve taninmis sirketlerin tanitimlari dahil. Kart, sifre veya kimlik "
                    "bilgisi isteyen ya da sahte odul vaat eden e-postalar da spam'dir.",
            "false": "SPAM DEGILDIR: banka hesap hareketi, ekstre, islem sonucu, emir "
                     "gerceklesme, fatura, kargo/siparis bildirimi, guvenlik ve giris "
                     "dogrulama e-postalari - gonderen bir tanitim da gonderen bir "
                     "sirket olsa bile. Karari gonderene degil icerige gore ver.",
        },
    },
    "banka": {
        "type": "noul",
        "instructions": "Bu e-posta banka veya yatirim hesabiyla ilgili bir islem bildirimi mi?",
        "criteria": {
            "true": "Hesap hareketi, ekstre, emir gerceklesme, islem sonuc formu, "
                    "hesap bilgilendirme gibi banka/yatirim hesabi islem bildirimi.",
            "false": "Banka veya yatirim hesabiyla ilgili bir islem bildirimi degil.",
        },
    },
}

WEAK_LABEL = {
    "fatura": {"fatura": True},
    "banka": {"banka": True},
    "spam": {"spam": True},
    "bulten": {"bulten": True},
}

FIXED_THRESHOLDS = {
    "spam": (0.95, 0.05),
    "acil": (0.85, 0.15), "fatura": (0.85, 0.15),
    "bulten": (0.85, 0.15), "musteri": (0.85, 0.15), "banka": (0.85, 0.15),
}
CONFIDENT_BAND = (0.85, 0.15)


def log(msg):
    print(msg, flush=True)


def call_systemone(base_url, model, state, questions, keep_alive=None, timeout=TIMEOUT_SECONDS):
    url = base_url.rstrip("/") + "/v1/systemone"
    payload = {"model": model, "state": state, "questions": questions}
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            elapsed = time.monotonic() - start
            try:
                return True, {"response": json.loads(raw)}, elapsed
            except json.JSONDecodeError:
                return False, {"error": "gecersiz JSON", "raw_body": raw}, elapsed
    except urllib.error.HTTPError as e:
        elapsed = time.monotonic() - start
        raw = e.read().decode("utf-8", errors="replace")
        return False, {"error": "HTTP {}: {}".format(e.code, raw)}, elapsed
    except urllib.error.URLError as e:
        elapsed = time.monotonic() - start
        return False, {"error": "Baglanti hatasi: {}".format(e.reason)}, elapsed
    except socket.timeout:
        elapsed = time.monotonic() - start
        return False, {"error": "zaman asimi ({} sn)".format(timeout)}, elapsed


def unload_model(base_url, model):
    call_systemone(base_url, model, "x", {"q": {"type": "noul", "instructions": "x"}}, keep_alive=0)


def build_state(record, body_limit=2000):
    return "Gonderen: {} <{}>\nKonu: {}\nGovde: {}".format(
        record["from_name"] or record["from_addr"], record["from_addr"],
        record["subject"], record["body_text_clean"][:body_limit],
    )


def run_noul(base_url, model, records):
    out = []
    for i, rec in enumerate(records, start=1):
        state = build_state(rec)
        ok, result, elapsed = call_systemone(base_url, model, state, QUESTIONS_TR)
        row = {"id": rec["id"], "subject": rec["subject"], "source_category": rec["source_category"],
               "weak_category": rec["weak_category"], "elapsed": elapsed, "ok": ok}
        if not ok:
            row["error"] = result["error"]
            log("    HATA [{}] konu='{}': {}".format(model, rec["subject"][:60], result["error"]))
        else:
            answers = result["response"].get("answers", {})
            row["scores"] = {r: answers.get(r, {}).get("noul") for r in RULE_ORDER}
        out.append(row)
        if i % 30 == 0 or i == len(records):
            log("    [{}] {}/{}".format(model, i, len(records)))
    return out


def threshold_eval(entries, hi, lo):
    applied = [(s, c) for s, c in entries if s >= hi or s <= lo]
    errors = sum(1 for s, c in applied if not c)
    review_pct = (1 - len(applied) / len(entries)) * 100 if entries else 0.0
    return {"applied_n": len(applied), "applied_errors": errors, "review_pct": review_pct, "total": len(entries)}


def accuracy_for_pool(rows, rule, weak_cat):
    entries = []
    for row in rows:
        if not row["ok"] or row["weak_category"] != weak_cat:
            continue
        score = row["scores"].get(rule)
        if score is None:
            continue
        expected = WEAK_LABEL[weak_cat][rule]
        entries.append((score, (score >= 0.5) == expected))
    correct = sum(1 for _, c in entries if c)
    total = len(entries)
    return (correct / total * 100 if total else None), total, entries


def main():
    base_url = "http://localhost:11434"
    with open("sample_v2.json", encoding="utf-8") as f:
        records = json.load(f)
    log("sample_v2.json yuklendi: {} e-posta".format(len(records)))

    results = {"generated_at": datetime.now().isoformat(), "models": MODELS, "per_model": {}}

    for model in MODELS:
        log("\n=== MODEL: {} ===".format(model))
        unload_model(base_url, model)
        time.sleep(1)
        rows = run_noul(base_url, model, records)
        unload_model(base_url, model)
        durations = [r["elapsed"] for r in rows]
        results["per_model"][model] = {
            "noul": rows,
            "timing": {"avg_seconds": sum(durations) / len(durations) if durations else None,
                       "worst_seconds": max(durations) if durations else None,
                       "total_seconds": sum(durations) if durations else None},
        }

    analysis = {"per_model_rule_accuracy": {}, "threshold_eval": {}}
    pool_map = {"fatura": "fatura", "banka": "banka", "spam": "spam", "bulten": "bulten"}
    for model in MODELS:
        rows = results["per_model"][model]["noul"]
        analysis["per_model_rule_accuracy"][model] = {}
        analysis["threshold_eval"][model] = {}
        for rule, weak_cat in pool_map.items():
            acc, total, entries = accuracy_for_pool(rows, rule, weak_cat)
            analysis["per_model_rule_accuracy"][model][rule] = {"accuracy": acc, "n": total}
            hi, lo = FIXED_THRESHOLDS[rule]
            analysis["threshold_eval"][model][rule] = threshold_eval(entries, hi, lo)

    results["analysis"] = analysis

    out_name = "results_v2_{}.json".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    with open(out_name, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    log("\nSonuclar kaydedildi: {}".format(out_name))


if __name__ == "__main__":
    main()
