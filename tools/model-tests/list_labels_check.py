"""Tek seferlik dogrulama: OAuth baglantisini kurar, etiketleri ve her
etiketteki (yaklasik) e-posta sayisini listeler. Hicbir govde icerigi
okumaz/yazmaz, sadece labels.list ve messages.list(maxResults=1) kullanir."""

import gmail_client as gc

service = gc.get_service()
print("Baglanti kuruldu (gmail.readonly).\n")

labels = gc.list_labels(service)
print("Toplam etiket sayisi: {}\n".format(len(labels)))

rows = []
for lbl in sorted(labels, key=lambda l: l.get("name", "")):
    lbl_id = lbl["id"]
    try:
        resp = service.users().messages().list(userId="me", labelIds=[lbl_id], maxResults=1).execute()
        count = resp.get("resultSizeEstimate", "?")
    except Exception as e:
        count = "HATA: {}".format(e)
    rows.append((lbl.get("type", "?"), lbl["name"], lbl_id, count))

print("{:<8} {:<45} {:<20} {:<10}".format("Tur", "Ad", "ID", "~Adet"))
print("-" * 90)
for typ, name, lid, count in rows:
    print("{:<8} {:<45} {:<20} {:<10}".format(typ, name, lid, count))
