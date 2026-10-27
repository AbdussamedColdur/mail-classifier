#!/usr/bin/env python3
"""MailKarar - gercek e-postalarla model karsilastirmasi.

sample.json'daki 119 gercek e-postayi d3:9b / tev1:4b / tev1:0.8b ile test eder.
Sorular onceki sentetik testle BIREBIR AYNI (noul-TR 5 kural + choice-TR).
Gmail'e YAZMA islemi yoktur. Konsola govde basilmaz (sadece konu/gonderen, hata
mesajlarinda).
"""

import csv
import json
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime

TIMEOUT_SECONDS = 60
MODELS = ["d3:9b", "tev1:4b", "tev1:0.8b"]
BODY_MODELS_FOR_LENGTH_TEST = ["d3:9b", "tev1:4b"]
RULE_ORDER = ["acil", "fatura", "bulten", "musteri", "spam"]

# onceki testle birebir ayni sorular (keskinlestirilmis spam/acil ile)
SPAM_CRITERIA_TR = (
    "Bilinen kurum ve bankalardan gelen fatura/ekstreler spam degildir. "
    "Yalnizca kart, sifre veya kimlik bilgisi isteyen ya da sahte odul "
    "vaat eden e-postalar spam'dir."
)
ACIL_CRITERIA_TR = (
    "Pazarlama dilindeki 'sadece bugun', 'hemen' gibi ifadeler aciliyet "
    "sayilmaz. Yalnizca bir kisinin size yonelttigi sureli is talepleri acildir."
)

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

# kaynak kategori -> zayif dogru cevap (sadece bu alanlar icin ground truth var)
WEAK_LABEL_RULE = {
    "fatura": {"fatura": True}, "fatura_long": {"fatura": True},
    "spam": {"spam": True}, "spam_long": {"spam": True},
    "bulten": {"bulten": True}, "bulten_long": {"bulten": True},
}
WEAK_LABEL_CHOICE = {
    "fatura": "fatura", "fatura_long": "fatura",
    "spam": "spam", "spam_long": "spam",
    "bulten": "bulten", "bulten_long": "bulten",
}
# birincil havuzu icin yumusak/gurultulu beklenti (bonus olcum, ana dogrulukta kullanilmaz)
SOFT_PRIMARY_EXPECT = {"bulten": False, "spam": False}

FIXED_THRESHOLDS = {
    "spam": (0.95, 0.05),
    "acil": (0.85, 0.15), "fatura": (0.85, 0.15),
    "bulten": (0.85, 0.15), "musteri": (0.85, 0.15),
}
PREV_BAND = (0.65, 0.35)
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
        return False, {"error": "HTTP {}: {}".format(e.code, raw), "status": e.code}, elapsed
    except urllib.error.URLError as e:
        elapsed = time.monotonic() - start
        return False, {"error": "Baglanti hatasi: {}".format(e.reason)}, elapsed
    except socket.timeout:
        elapsed = time.monotonic() - start
        return False, {"error": "zaman asimi ({} sn)".format(timeout)}, elapsed


def unload_model(base_url, model):
    call_systemone(base_url, model, "x", {"q": {"type": "noul", "instructions": "x"}}, keep_alive=0)


def build_state(record, body_limit):
    return "Gonderen: {} <{}>\nKonu: {}\nGovde: {}".format(
        record["from_name"] or record["from_addr"], record["from_addr"],
        record["subject"], record["body_text_clean"][:body_limit],
    )


def run_noul(base_url, model, records, body_limit):
    """Her kayit icin 5 soruyu tek istekte gonderir. derived[rule] = {score, error}."""
    out = []
    for i, rec in enumerate(records, start=1):
        state = build_state(rec, body_limit)
        ok, result, elapsed = call_systemone(base_url, model, state, QUESTIONS_TR)
        row = {"id": rec["id"], "subject": rec["subject"], "source_category": rec["source_category"],
               "elapsed": elapsed, "ok": ok}
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


def run_choice(base_url, model, records):
    out = []
    for i, rec in enumerate(records, start=1):
        state = build_state(rec, 2000)
        ok, result, elapsed = call_systemone(base_url, model, state, CHOICE_QUESTION)
        row = {"id": rec["id"], "subject": rec["subject"], "source_category": rec["source_category"],
               "elapsed": elapsed, "ok": ok}
        if not ok:
            row["error"] = result["error"]
            log("    HATA [{}] konu='{}': {}".format(model, rec["subject"][:60], result["error"]))
        else:
            ans = result["response"].get("answers", {}).get("kategori", {})
            row["choice"] = ans.get("choice")
            row["confidence"] = ans.get("confidence")
            row["probabilities"] = ans.get("probabilities")
        out.append(row)
        if i % 30 == 0 or i == len(records):
            log("    [{}] {}/{}".format(model, i, len(records)))
    return out


def accuracy_for_pool(noul_rows, records_by_id, rule, categories):
    correct, total, entries = 0, 0, []
    for row in noul_rows:
        if not row["ok"] or row["source_category"] not in categories:
            continue
        score = row["scores"].get(rule)
        if score is None:
            continue
        expected = WEAK_LABEL_RULE[row["source_category"]][rule]
        pred = score >= 0.5
        total += 1
        correct += int(pred == expected)
        entries.append((score, pred == expected))
    return (correct / total * 100 if total else None), total, entries


def threshold_eval(entries, hi, lo):
    """entries: list of (score, correct). uygula: skor>=hi veya skor<=lo."""
    applied = [(s, c) for s, c in entries if s >= hi or s <= lo]
    errors = sum(1 for s, c in applied if not c)
    review_pct = (1 - len(applied) / len(entries)) * 100 if entries else 0.0
    return {"applied_n": len(applied), "applied_errors": errors, "review_pct": review_pct, "total": len(entries)}


def main():
    base_url = "http://localhost:11434"
    with open("sample.json", encoding="utf-8") as f:
        records = json.load(f)
    records_by_id = {r["id"]: r for r in records}
    log("sample.json yuklendi: {} e-posta".format(len(records)))

    results = {"generated_at": datetime.now().isoformat(), "models": MODELS, "per_model": {}}

    for model in MODELS:
        log("\n=== MODEL: {} ===".format(model))
        unload_model(base_url, model)
        time.sleep(1)

        log("  noul-TR (govde=2000, ana test)")
        noul_main = run_noul(base_url, model, records, 2000)

        log("  choice-TR")
        choice_main = run_choice(base_url, model, records)

        body_length = {}
        if model in BODY_MODELS_FOR_LENGTH_TEST:
            for length in (800, 1500):
                log("  noul-TR (govde={})".format(length))
                body_length[str(length)] = run_noul(base_url, model, records, length)
            body_length["2000"] = noul_main

        unload_model(base_url, model)

        all_durations = ([r["elapsed"] for r in noul_main] + [r["elapsed"] for r in choice_main]
                          + [r["elapsed"] for ln in body_length for r in body_length[ln] if ln != "2000"])

        results["per_model"][model] = {
            "noul_main": noul_main, "choice_main": choice_main, "body_length": body_length,
            "timing": {
                "avg_seconds": sum(all_durations) / len(all_durations) if all_durations else None,
                "worst_seconds": max(all_durations) if all_durations else None,
                "total_seconds": sum(all_durations) if all_durations else None,
                "n_requests": len(all_durations),
            },
        }

    # ---------------- analiz ----------------
    analysis = {"per_model_rule_accuracy": {}, "threshold_eval": {}, "confident_wrong": {},
                "body_length_effect": {}, "errors": {}}

    for model in MODELS:
        pm = results["per_model"][model]
        analysis["per_model_rule_accuracy"][model] = {}
        analysis["threshold_eval"][model] = {}
        pool_map = {"fatura": ["fatura", "fatura_long"], "spam": ["spam", "spam_long"], "bulten": ["bulten", "bulten_long"]}
        for rule, cats in pool_map.items():
            acc, total, entries = accuracy_for_pool(pm["noul_main"], records_by_id, rule, cats)
            analysis["per_model_rule_accuracy"][model][rule] = {"accuracy": acc, "n": total}
            hi, lo = FIXED_THRESHOLDS[rule]
            analysis["threshold_eval"][model][rule] = {
                "fixed": threshold_eval(entries, hi, lo),
                "prev_0.35_0.65": threshold_eval(entries, PREV_BAND[0], PREV_BAND[1]),
            }

        # birincil bonus: bulten/spam false positive rate
        fp = {"bulten": [0, 0], "spam": [0, 0]}
        for row in pm["noul_main"]:
            if not row["ok"] or row["source_category"] != "birincil":
                continue
            for rule in ("bulten", "spam"):
                score = row["scores"].get(rule)
                if score is None:
                    continue
                fp[rule][1] += 1
                if score >= 0.5:
                    fp[rule][0] += 1
        analysis["per_model_rule_accuracy"][model]["birincil_bonus_false_positive"] = {
            rule: {"false_positive_n": fp[rule][0], "total": fp[rule][1]} for rule in fp
        }

        # kararli ama yanlis (CONFIDENT_BAND, tum ground-truth havuzlari)
        cw = []
        for row in pm["noul_main"]:
            if not row["ok"] or row["source_category"] not in WEAK_LABEL_RULE:
                continue
            expected_map = WEAK_LABEL_RULE[row["source_category"]]
            for rule, expected in expected_map.items():
                score = row["scores"].get(rule)
                if score is None:
                    continue
                if score >= CONFIDENT_BAND[0] or score <= CONFIDENT_BAND[1]:
                    pred = score >= 0.5
                    if pred != expected:
                        cw.append({"id": row["id"], "subject": row["subject"], "rule": rule,
                                   "score": score, "expected": expected, "category": row["source_category"]})
        analysis["confident_wrong"][model] = cw

        # govde uzunlugu etkisi
        if model in BODY_MODELS_FOR_LENGTH_TEST:
            bl_summary = {}
            for length, rows in pm["body_length"].items():
                accs = {}
                for rule, cats in pool_map.items():
                    acc, total, _ = accuracy_for_pool(rows, records_by_id, rule, cats)
                    accs[rule] = {"accuracy": acc, "n": total}
                durations = [r["elapsed"] for r in rows if r["ok"]]
                bl_summary[length] = {
                    "rule_accuracy": accs,
                    "avg_seconds": sum(durations) / len(durations) if durations else None,
                    "n_errors": sum(1 for r in rows if not r["ok"]),
                }
            analysis["body_length_effect"][model] = bl_summary

        analysis["errors"][model] = [
            {"id": r["id"], "subject": r["subject"], "category": r["source_category"], "error": r["error"]}
            for r in pm["noul_main"] if not r["ok"]
        ] + [
            {"id": r["id"], "subject": r["subject"], "category": r["source_category"], "error": r["error"]}
            for r in pm["choice_main"] if not r["ok"]
        ]

    results["analysis"] = analysis

    out_name = "results_real_{}.json".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    with open(out_name, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    log("\nSonuclar kaydedildi: {}".format(out_name))

    # ---------------- disagreements.csv ----------------
    log("disagreements.csv olusturuluyor...")
    label_map_cache = {r["id"]: r for r in records}
    rows_by_model = {m: {r["id"]: r for r in results["per_model"][m]["noul_main"]} for m in MODELS}

    with open("disagreements.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["email_id", "rule", "tarih", "gonderen", "konu", "govde_ilk200",
                          "gmail_etiketleri", "zayif_etiket", "d3_9b_skor", "tev1_4b_skor",
                          "tev1_0.8b_skor", "sebep", "benim_cevabim"])
        n_written = 0
        for rec in records:
            mid = rec["id"]
            scores = {}
            for m in MODELS:
                row = rows_by_model[m].get(mid)
                scores[m] = row["scores"] if row and row.get("ok") else None
            for rule in RULE_ORDER:
                vals = {m: (scores[m].get(rule) if scores[m] else None) for m in MODELS}
                if any(v is None for v in vals.values()):
                    continue
                preds = {m: v >= 0.5 for m, v in vals.items()}
                disagree = len(set(preds.values())) > 1

                weak_expected = WEAK_LABEL_RULE.get(rec["source_category"], {}).get(rule)
                label_conflict = False
                if weak_expected is not None:
                    for v in vals.values():
                        if (v >= CONFIDENT_BAND[0] or v <= CONFIDENT_BAND[1]) and (v >= 0.5) != weak_expected:
                            label_conflict = True
                            break

                if not disagree and not label_conflict:
                    continue

                reason_parts = []
                if disagree:
                    reason_parts.append("model_anlasmazligi")
                if label_conflict:
                    reason_parts.append("etiket_celismesi")

                writer.writerow([
                    mid, rule, rec["date"], "{} <{}>".format(rec["from_name"], rec["from_addr"]),
                    rec["subject"], rec["body_text_clean"][:200].replace("\n", " "),
                    "; ".join(rec["label_names"]), weak_expected,
                    vals["d3:9b"], vals["tev1:4b"], vals["tev1:0.8b"],
                    "+".join(reason_parts), "",
                ])
                n_written += 1
    log("disagreements.csv yazildi: {} satir".format(n_written))


if __name__ == "__main__":
    main()
