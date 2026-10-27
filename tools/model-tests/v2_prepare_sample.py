"""v2: mevcut sample.json'u yeni kural setine gore zayif-etiket haritasiyla
isaretler (fatura vs banka ayrimi) ve category:promotions'tan 25 YENI ek ornek
ekler (spam=True beklentisiyle, mevcut bulten havuzuyla cakismayacak sekilde).
Gmail'e yazma yoktur."""

import json
import os
import random

import gmail_client as gc

# Kisisel Gmail etiket adlari depoda tutulmaz: labels.local.json (.gitignore'da) okunur,
# bicim icin labels.example.json'a bakin.
LABELS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "labels.local.json")
if not os.path.exists(LABELS_PATH):
    raise SystemExit("labels.local.json bulunamadi: labels.example.json'u kopyalayip "
                     "kendi banka etiketlerinizle doldurun.")
with open(LABELS_PATH, encoding="utf-8") as f:
    BANKA_SUBLABELS = json.load(f)["banka_sublabels"]

with open("sample.json", encoding="utf-8") as f:
    records = json.load(f)

for rec in records:
    names = " | ".join(rec["label_names"])
    if rec["source_category"] in ("fatura", "fatura_long"):
        if any(b in names for b in BANKA_SUBLABELS):
            rec["weak_category"] = "banka"
        else:
            rec["weak_category"] = "fatura"
    elif rec["source_category"] in ("spam", "spam_long"):
        rec["weak_category"] = "spam"
    elif rec["source_category"] in ("bulten", "bulten_long"):
        rec["weak_category"] = "bulten"
    else:
        rec["weak_category"] = None  # birincil / guncellemeler - etiket yok

existing_ids = {r["id"] for r in records}

service = gc.get_service()
label_map = {l["id"]: l["name"] for l in gc.list_labels(service)}

resp = service.users().messages().list(userId="me", labelIds=["CATEGORY_PROMOTIONS"], q="newer_than:6m", maxResults=500).execute()
all_promo_ids = [m["id"] for m in resp.get("messages", []) if m["id"] not in existing_ids]

random.seed(43)  # onceki bulten secimiyle (seed=42) cakismamasi icin farkli seed
new_ids = random.sample(all_promo_ids, min(25, len(all_promo_ids)))

print("Yeni promosyon adaylari (spam=True beklentisiyle): {} secildi, havuzda {} vardi (mevcut 25 bulten haric)".format(
    len(new_ids), len(all_promo_ids)))

new_records = []
for i, mid in enumerate(new_ids, start=1):
    rec = gc.get_message(service, mid, label_id_to_name=label_map)
    rec["source_category"] = "spam_promo"
    rec["weak_category"] = "spam"
    new_records.append(rec)
    if i % 10 == 0 or i == len(new_ids):
        print("  [{}/{}] cekildi".format(i, len(new_ids)))

records.extend(new_records)

with open("sample_v2.json", "w", encoding="utf-8") as f:
    json.dump(records, f, ensure_ascii=False, indent=2)

print("\nToplam kayit: {}".format(len(records)))
from collections import Counter
print("weak_category dagilimi:", Counter(r["weak_category"] for r in records))
print("source_category dagilimi:", Counter(r["source_category"] for r in records))
