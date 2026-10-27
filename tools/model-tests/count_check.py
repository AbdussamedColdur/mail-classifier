import gmail_client as gc

service = gc.get_service()

fatura_labels = gc.find_labels_matching(service, "Alışveriş", "Fatura")
print("Fatura alt etiketleri:")
for lbl in fatura_labels:
    if "/" not in lbl["name"]:
        continue
    resp = service.users().messages().list(
        userId="me", labelIds=[lbl["id"]], q="newer_than:6m", maxResults=500
    ).execute()
    ids = resp.get("messages", [])
    more = "500+" if resp.get("nextPageToken") else str(len(ids))
    print("  {:<50} {}".format(lbl["name"], more))

print()
for name, label_id in [
    ("SPAM", "SPAM"),
    ("CATEGORY_PROMOTIONS (bulten)", "CATEGORY_PROMOTIONS"),
    ("CATEGORY_PERSONAL (birincil)", "CATEGORY_PERSONAL"),
    ("CATEGORY_UPDATES (guncellemeler)", "CATEGORY_UPDATES"),
]:
    resp = service.users().messages().list(
        userId="me", labelIds=[label_id], q="newer_than:6m", maxResults=500
    ).execute()
    ids = resp.get("messages", [])
    more = "500+" if resp.get("nextPageToken") else str(len(ids))
    print("{:<35} son 6 ay: {}".format(name, more))
