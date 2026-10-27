"""v2: guncellenmis kurallara (banka dahil 6 kural) gore disagreements.csv'yi
sifirdan, doldurulmamis olarak uretir. d3:9b ve tev1:4b karsilastirilir."""

import csv
import glob
import json

RULE_ORDER = ["acil", "fatura", "bulten", "musteri", "spam", "banka"]
WEAK_LABEL = {"fatura": {"fatura": True}, "banka": {"banka": True},
              "spam": {"spam": True}, "bulten": {"bulten": True}}
CONFIDENT_BAND = (0.85, 0.15)

results_path = sorted(glob.glob("results_v2_*.json"))[-1]
with open(results_path, encoding="utf-8") as f:
    d = json.load(f)
with open("sample_v2.json", encoding="utf-8") as f:
    records = json.load(f)

rows_by_model = {m: {r["id"]: r for r in d["per_model"][m]["noul"]} for m in d["models"]}

out_rows = []
for rec in records:
    mid = rec["id"]
    r3 = rows_by_model["d3:9b"].get(mid)
    r4 = rows_by_model["tev1:4b"].get(mid)
    if not r3 or not r3["ok"] or not r4 or not r4["ok"]:
        continue

    for rule in RULE_ORDER:
        s3 = r3["scores"].get(rule)
        s4 = r4["scores"].get(rule)
        if s3 is None or s4 is None:
            continue

        reasons = []
        if (s3 >= 0.5) != (s4 >= 0.5):
            reasons.append("model ayrışması")

        weak_expected = WEAK_LABEL.get(rec["weak_category"], {}).get(rule)
        if weak_expected is not None:
            for s in (s3, s4):
                if (s >= CONFIDENT_BAND[0] or s <= CONFIDENT_BAND[1]) and (s >= 0.5) != weak_expected:
                    reasons.append("etiketle çelişki")
                    break

        if rule == "fatura" and rec["weak_category"] is None:
            if s3 >= CONFIDENT_BAND[0] or s4 >= CONFIDENT_BAND[0]:
                reasons.append("etiketsiz fatura adayı")

        if not reasons:
            continue

        out_rows.append({
            "email_id": mid, "kural": rule, "tarih": rec["date"],
            "gonderen": "{} <{}>".format(rec["from_name"], rec["from_addr"]),
            "konu": rec["subject"],
            "govde_ilk200": rec["body_text_clean"][:200].replace("\n", " "),
            "gmail_etiketleri": "; ".join(rec["label_names"]),
            "kaynak_havuz": rec["source_category"], "zayif_kategori": rec["weak_category"],
            "zayif_etiket": weak_expected,
            "d3_9b_skor": s3, "tev1_4b_skor": s4,
            "neden_burada": "+".join(reasons),
            "_priority": (
                0 if (rec["weak_category"] == "banka" and rule == "spam" and (s3 >= 0.5 or s4 >= 0.5))
                else 1 if rule == "spam"
                else 2 if rule == "bulten"
                else 3
            ),
            "benim_cevabim": "",
        })

out_rows.sort(key=lambda r: (r["_priority"], r["kural"], r["konu"]))
for r in out_rows:
    del r["_priority"]

fieldnames = ["email_id", "kural", "tarih", "gonderen", "konu", "govde_ilk200",
              "gmail_etiketleri", "kaynak_havuz", "zayif_kategori", "zayif_etiket",
              "d3_9b_skor", "tev1_4b_skor", "neden_burada", "benim_cevabim"]

with open("disagreements.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(out_rows)

print("Yeni disagreements.csv: {} satir".format(len(out_rows)))
from collections import Counter
print("kural dagilimi:", Counter(r["kural"] for r in out_rows))
print("neden dagilimi:", Counter(r["neden_burada"] for r in out_rows))
