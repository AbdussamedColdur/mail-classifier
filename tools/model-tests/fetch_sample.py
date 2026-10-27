"""MailKarar - gercek e-posta orneklemesi (salt-okunur).

Planlanan dagilim (~119 e-posta):
  fatura=True   : 30  (Alisveris&Faturalar'in 10 alt etiketinden 3'er, TUM ZAMANLAR -
                        son 6 ayda bu etiketlerde hic e-posta yok, kullanici onayladi)
  spam=True     : 19  (SPAM, son 6 ay - mevcut olanin tamami)
  bulten=True   : 25  (CATEGORY_PROMOTIONS, son 6 ay, rastgele)
  birincil      : 25  (CATEGORY_PERSONAL, son 6 ay, rastgele)
  guncellemeler : 20  (CATEGORY_UPDATES, son 6 ay, rastgele - etiket beklentisi yok)

En az 10 ornek govdesi >2000 karakter olmali; yetmezse promotions/updates
havuzundan 'larger:' operatoruyle ek uzun e-posta aranip takas edilir.

Konsola gorunur: sadece ilerleme sayaci, konu/gonderen YAZDIRILMAZ (gizlilik).
Cikti: sample.json (yerel, .gitignore'da).
"""

import json
import random
import sys
import time

import gmail_client as gc

SEED = 42
LONG_BODY_MIN = 2000
LONG_BODY_TARGET = 10

FATURA_PER_LABEL = 3
SPAM_TARGET = None  # tumu
BULTEN_TARGET = 25
BIRINCIL_TARGET = 25
GUNCELLEME_TARGET = 20


def log(msg):
    print(msg, flush=True)


def main():
    random.seed(SEED)
    service = gc.get_service()
    log("Baglanti kuruldu.")

    plan = []  # [(msg_id, source_category)]

    # --- fatura: tum zamanlar, 10 alt etiketten 3'er ---
    fatura_labels = [l for l in gc.find_labels_matching(service, "Alışveriş", "Fatura") if "/" in l["name"]]
    for lbl in fatura_labels:
        resp = service.users().messages().list(userId="me", labelIds=[lbl["id"]], maxResults=500).execute()
        ids = [m["id"] for m in resp.get("messages", [])]
        picked = random.sample(ids, min(FATURA_PER_LABEL, len(ids)))
        plan.extend((mid, "fatura") for mid in picked)
    log("fatura havuzu: {} secildi".format(sum(1 for _, c in plan if c == "fatura")))

    # --- spam: son 6 ay, tumu ---
    resp = service.users().messages().list(userId="me", labelIds=["SPAM"], q="newer_than:6m", maxResults=500).execute()
    spam_ids = [m["id"] for m in resp.get("messages", [])]
    plan.extend((mid, "spam") for mid in spam_ids)
    log("spam havuzu: {} secildi".format(len(spam_ids)))

    # --- bulten: son 6 ay, 25 rastgele ---
    resp = service.users().messages().list(userId="me", labelIds=["CATEGORY_PROMOTIONS"], q="newer_than:6m", maxResults=500).execute()
    bulten_ids_all = [m["id"] for m in resp.get("messages", [])]
    bulten_picked = random.sample(bulten_ids_all, min(BULTEN_TARGET, len(bulten_ids_all)))
    plan.extend((mid, "bulten") for mid in bulten_picked)
    log("bulten havuzu: {} secildi (toplam {})".format(len(bulten_picked), len(bulten_ids_all)))

    # --- birincil: son 6 ay, 25 rastgele ---
    resp = service.users().messages().list(userId="me", labelIds=["CATEGORY_PERSONAL"], q="newer_than:6m", maxResults=500).execute()
    birincil_ids_all = [m["id"] for m in resp.get("messages", [])]
    birincil_picked = random.sample(birincil_ids_all, min(BIRINCIL_TARGET, len(birincil_ids_all)))
    plan.extend((mid, "birincil") for mid in birincil_picked)
    log("birincil havuzu: {} secildi (toplam {})".format(len(birincil_picked), len(birincil_ids_all)))

    # --- guncellemeler: son 6 ay, 20 rastgele ---
    resp = service.users().messages().list(userId="me", labelIds=["CATEGORY_UPDATES"], q="newer_than:6m", maxResults=500).execute()
    guncelleme_ids_all = [m["id"] for m in resp.get("messages", [])]
    guncelleme_picked = random.sample(guncelleme_ids_all, min(GUNCELLEME_TARGET, len(guncelleme_ids_all)))
    plan.extend((mid, "guncellemeler") for mid in guncelleme_picked)
    log("guncellemeler havuzu: {} secildi (toplam {})".format(len(guncelleme_picked), len(guncelleme_ids_all)))

    log("\nToplam plan: {} e-posta. Icerik cekiliyor (govde konsola yazilmayacak)...".format(len(plan)))

    # etiket id -> ad haritasi (rapor icin okunabilir etiketler)
    label_map = {l["id"]: l["name"] for l in gc.list_labels(service)}

    records = []
    seen_ids = set()
    for i, (mid, category) in enumerate(plan, start=1):
        if mid in seen_ids:
            continue
        seen_ids.add(mid)
        try:
            rec = gc.get_message(service, mid, label_id_to_name=label_map)
        except Exception as e:
            log("  [{}/{}] HATA (id={}): {}".format(i, len(plan), mid, e))
            continue
        rec["source_category"] = category
        records.append(rec)
        if i % 20 == 0 or i == len(plan):
            log("  [{}/{}] cekildi".format(i, len(plan)))

    long_count = sum(1 for r in records if r["body_char_len"] > LONG_BODY_MIN)
    log("\n>2000 karakter govdesi olan e-posta sayisi: {} (hedef: >= {})".format(long_count, LONG_BODY_TARGET))

    if long_count < LONG_BODY_TARGET:
        log("Yetersiz, promotions/updates havuzundan 'larger:' ile uzun e-posta araniyor...")
        needed = LONG_BODY_TARGET - long_count
        extra_query_pools = [
            ("CATEGORY_PROMOTIONS", "bulten"),
            ("CATEGORY_UPDATES", "guncellemeler"),
        ]
        existing_ids = {r["id"] for r in records}
        added = 0
        for label_id, category in extra_query_pools:
            if added >= needed:
                break
            resp = service.users().messages().list(
                userId="me", labelIds=[label_id], q="newer_than:6m larger:8000", maxResults=50
            ).execute()
            cand_ids = [m["id"] for m in resp.get("messages", []) if m["id"] not in existing_ids]
            random.shuffle(cand_ids)
            for mid in cand_ids:
                if added >= needed:
                    break
                try:
                    rec = gc.get_message(service, mid, label_id_to_name=label_map)
                except Exception as e:
                    log("  HATA (id={}): {}".format(mid, e))
                    continue
                if rec["body_char_len"] > LONG_BODY_MIN:
                    rec["source_category"] = category + "_long"
                    records.append(rec)
                    existing_ids.add(mid)
                    added += 1
                    log("  +1 uzun govde eklendi ({} karakter, kategori={})".format(rec["body_char_len"], category))
        long_count = sum(1 for r in records if r["body_char_len"] > LONG_BODY_MIN)
        log("Guncel >2000 karakter sayisi: {}".format(long_count))

    with open("sample.json", "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    log("\nToplam kaydedilen e-posta: {}".format(len(records)))
    log("sample.json yazildi.")

    # kategori dagilimi ozeti (govde icerigi yok)
    from collections import Counter
    cat_counts = Counter(r["source_category"] for r in records)
    for cat, n in sorted(cat_counts.items()):
        print("  {:<20} {}".format(cat, n))


if __name__ == "__main__":
    main()
