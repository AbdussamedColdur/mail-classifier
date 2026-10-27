"""disagreements.csv'yi daraltir:
- tev1:0.8b'nin tek basina sebep oldugu satirlar (digger ikisi hemfikirken sadece o
  ayrisiyorsa, ya da etiketle celisen tek o ise) cikarilir. Skor sutunu referans
  icin kalir, ama karar mantiginda kullanilmaz.
- Onceliklendirme: 1) birincil havuzda d3:9b'nin spam=True dedigi satirlar,
  2) fatura kurali satirlari, 3) geri kalanlar.
- 'kural' ve 'neden_burada' (model ayrismasi / etiketle celiski / etiketsiz fatura adayi)
  sutunlari eklenir.
"""

import csv
import glob
import json

RULE_ORDER = ["acil", "fatura", "bulten", "musteri", "spam"]
WEAK_LABEL_RULE = {
    "fatura": {"fatura": True}, "fatura_long": {"fatura": True},
    "spam": {"spam": True}, "spam_long": {"spam": True},
    "bulten": {"bulten": True}, "bulten_long": {"bulten": True},
}
CONFIDENT_BAND = (0.85, 0.15)
UNLABELED_POOLS = {"birincil", "guncellemeler", "guncellemeler_long"}

results_path = sorted(glob.glob("results_real_*.json"))[-1]
with open(results_path, encoding="utf-8") as f:
    d = json.load(f)
with open("sample.json", encoding="utf-8") as f:
    records = json.load(f)

rows_by_model = {m: {r["id"]: r for r in d["per_model"][m]["noul_main"]} for m in d["models"]}

out_rows = []
for rec in records:
    mid = rec["id"]
    r3 = rows_by_model["d3:9b"].get(mid)
    r4 = rows_by_model["tev1:4b"].get(mid)
    r08 = rows_by_model["tev1:0.8b"].get(mid)
    if not r3 or not r3["ok"] or not r4 or not r4["ok"]:
        continue  # d3/tev1:4b olmadan karar veremeyiz

    for rule in RULE_ORDER:
        s3 = r3["scores"].get(rule)
        s4 = r4["scores"].get(rule)
        s08 = r08["scores"].get(rule) if (r08 and r08["ok"]) else None
        if s3 is None or s4 is None:
            continue

        reasons = []

        # 1) model ayrismasi: SADECE d3:9b vs tev1:4b
        if (s3 >= 0.5) != (s4 >= 0.5):
            reasons.append("model ayrışması")

        # 2) etiketle celiski: zayif etiket varsa ve d3/tev1:4b'den biri kararli+yanlissa
        weak_expected = WEAK_LABEL_RULE.get(rec["source_category"], {}).get(rule)
        if weak_expected is not None:
            for s in (s3, s4):
                if (s >= CONFIDENT_BAND[0] or s <= CONFIDENT_BAND[1]) and (s >= 0.5) != weak_expected:
                    reasons.append("etiketle çelişki")
                    break

        # 3) etiketsiz fatura adayi: etiketsiz havuzda, fatura kuralinda, d3/tev1:4b kararli True
        if rule == "fatura" and rec["source_category"] in UNLABELED_POOLS:
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
            "kaynak_havuz": rec["source_category"],
            "zayif_etiket": weak_expected,
            "d3_9b_skor": s3, "tev1_4b_skor": s4, "tev1_0.8b_skor": s08,
            "neden_burada": "+".join(reasons),
            "_priority": (
                0 if (rec["source_category"] == "birincil" and rule == "spam" and s3 >= 0.5)
                else 1 if rule == "fatura"
                else 2
            ),
            "benim_cevabim": "",
        })

out_rows.sort(key=lambda r: (r["_priority"], r["kural"], r["konu"]))
for r in out_rows:
    del r["_priority"]

fieldnames = ["email_id", "kural", "tarih", "gonderen", "konu", "govde_ilk200",
              "gmail_etiketleri", "kaynak_havuz", "zayif_etiket", "d3_9b_skor",
              "tev1_4b_skor", "tev1_0.8b_skor", "neden_burada", "benim_cevabim"]

with open("disagreements.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(out_rows)

print("Yeni disagreements.csv: {} satir (eskiden 141 idi)".format(len(out_rows)))
from collections import Counter
print("neden dagilimi:", Counter(r["neden_burada"] for r in out_rows))
print("kural dagilimi:", Counter(r["kural"] for r in out_rows))
print("ilk 6 satir (oncelik 0 - birincil/spam):")
for r in out_rows[:6]:
    print(" ", r["kural"], r["konu"][:50], r["neden_burada"])
