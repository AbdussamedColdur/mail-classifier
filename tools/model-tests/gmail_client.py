"""MailKarar Gmail katmani - salt-okunur erisim.

Sadece https://www.googleapis.com/auth/gmail.readonly kapsamini kullanir.
Hicbir sekilde etiketleme/arsivleme/silme/gonderme yapmaz - bu modulde o
yetkilere karsilik gelen bir cagri bile yoktur.

OAuth "Masaustu uygulamasi" akisi: ilk calistirmada bir tarayici penceresi
acilir, Google hesabinizla giris yapip izin verirsiniz; token.json'a
kaydedilen yenileme jetonu sonraki calistirmalarda tekrar giris istemez.

Gereken dosya: credentials.json (proje klasorunde, Google Cloud Console'dan
indirilen "Desktop app" istemci sirri). Yoksa run.py/sample_emails.py bunu
acik bir hata mesajiyla bildirir.
"""

import base64
import html.parser
import os
import re
from email.utils import parseaddr, parsedate_to_datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
HERE = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_PATH = os.path.join(HERE, "credentials.json")
TOKEN_PATH = os.path.join(HERE, "token.json")


class CredentialsMissingError(Exception):
    pass


def get_service(credentials_path=CREDENTIALS_PATH, token_path=TOKEN_PATH):
    """Gmail API servisini dondurur (salt-okunur). token.json yoksa/gecersizse
    tarayici uzerinden OAuth akisini baslatir."""
    if not os.path.exists(credentials_path):
        raise CredentialsMissingError(
            "credentials.json bulunamadi: {}\n"
            "Google Cloud Console'dan bir 'Desktop app' OAuth istemcisi "
            "olusturup bu dosyayi proje klasorune koyun.".format(credentials_path)
        )

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


# -------------------------------------------------------------------------
# Etiketler
# -------------------------------------------------------------------------
def list_labels(service):
    """{'id': 'Label_1', 'name': 'Alisveris & Faturalar/E-Fatura', ...} seklinde
    tum etiketleri dondurur (sistem + kullanici etiketleri)."""
    resp = service.users().labels().list(userId="me").execute()
    return resp.get("labels", [])


def find_labels_matching(service, *substrings):
    """Adinda verilen alt dizgelerden herhangi birini (kucuk/buyuk harf
    duyarsiz) iceren etiketleri dondurur. Gercek etiket agacinizin nasil
    adlandirildigini varsaymadan once bunu calistirip sonucu gozden gecirin."""
    labels = list_labels(service)
    out = []
    for lbl in labels:
        name = lbl.get("name", "")
        if any(s.lower() in name.lower() for s in substrings):
            out.append(lbl)
    return out


# -------------------------------------------------------------------------
# Mesaj arama / getirme
# -------------------------------------------------------------------------
def search_message_ids(service, query, max_results=200):
    """Gmail arama sozdizimiyle (ör. 'category:promotions newer_than:6m')
    mesaj ID'lerini sayfalayarak toplar."""
    ids = []
    page_token = None
    while True:
        resp = service.users().messages().list(
            userId="me", q=query, maxResults=min(500, max_results - len(ids)),
            pageToken=page_token,
        ).execute()
        ids.extend(m["id"] for m in resp.get("messages", []))
        page_token = resp.get("nextPageToken")
        if not page_token or len(ids) >= max_results:
            break
    return ids[:max_results]


def get_message(service, msg_id, label_id_to_name=None):
    """Tek bir mesaji tam biçimde ceker ve ayristirir. Govde HTML ise duz
    metne cevrilir; govde HTML+metin hic yoksa body_text bos dizgedir."""
    msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
    headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}

    from_name, from_addr = parseaddr(headers.get("from", ""))
    subject = headers.get("subject", "(konu yok)")
    date_raw = headers.get("date", "")
    try:
        date_parsed = parsedate_to_datetime(date_raw).isoformat()
    except Exception:
        date_parsed = date_raw

    body_text, body_source = _extract_body(msg["payload"])
    cleaned = clean_body(body_text)

    label_ids = msg.get("labelIds", [])
    if label_id_to_name:
        label_names = [label_id_to_name.get(l, l) for l in label_ids]
    else:
        label_names = label_ids

    return {
        "id": msg_id,
        "thread_id": msg.get("threadId"),
        "from_name": from_name,
        "from_addr": from_addr,
        "subject": subject,
        "date": date_parsed,
        "label_ids": label_ids,
        "label_names": label_names,
        "body_text_raw": body_text,
        "body_text_clean": cleaned,
        "body_source": body_source,  # 'text/plain' veya 'text/html'
        "body_char_len": len(cleaned),
    }


def _extract_body(payload):
    """MIME agacinda text/plain tercih edilir; yoksa text/html HTML'den
    metne cevrilir. (part, kaynak_turu) yerine (metin, kaynak_turu) dondurur."""
    plain = _walk_for_mime(payload, "text/plain")
    if plain is not None:
        return plain, "text/plain"
    html_body = _walk_for_mime(payload, "text/html")
    if html_body is not None:
        return _html_to_text(html_body), "text/html"
    return "", "none"


def _walk_for_mime(payload, mime_type):
    if payload.get("mimeType") == mime_type and payload.get("body", {}).get("data"):
        data = payload["body"]["data"]
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")
    for part in payload.get("parts", []) or []:
        result = _walk_for_mime(part, mime_type)
        if result is not None:
            return result
    return None


class _TextExtractor(html.parser.HTMLParser):
    """Minimal HTML->duz metin cevirici (stdlib disinda bagimlilik yok)."""
    _SKIP_TAGS = {"script", "style", "head"}
    _BLOCK_TAGS = {"p", "br", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.chunks = []

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        elif tag in self._BLOCK_TAGS:
            self.chunks.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in self._BLOCK_TAGS:
            self.chunks.append("\n")

    def handle_data(self, data):
        if self._skip_depth == 0:
            self.chunks.append(data)

    def get_text(self):
        text = "".join(self.chunks)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n[ \t]*\n+", "\n\n", text)
        return text.strip()


def _html_to_text(html_str):
    parser = _TextExtractor()
    parser.feed(html_str)
    return parser.get_text()


# -------------------------------------------------------------------------
# Alintilanan yanit / imza temizligi (sezgisel)
# -------------------------------------------------------------------------
_QUOTE_HEADER_RE = re.compile(
    r"(^|\n)\s*("
    r"On .{3,80} wrote:"
    r"|.{3,80} tarihinde .{0,80} (yazdi|yazdı):"
    r"|-{2,}\s*Original Message\s*-{2,}"
    r"|-{2,}\s*Ilet(i|ı)len [Mm]esaj\s*-{2,}"
    r")",
    re.IGNORECASE,
)
_SIGNATURE_RE = re.compile(r"(^|\n)--\s*\n", re.MULTILINE)


def clean_body(text):
    """Alintilanan eski yanitlari, '> ' ile baslayan satirlari ve '--'
    imza ayracindan sonraki her seyi atar."""
    if not text:
        return text

    m = _QUOTE_HEADER_RE.search(text)
    if m:
        text = text[: m.start()]

    m = _SIGNATURE_RE.search(text)
    if m:
        text = text[: m.start()]

    lines = [ln for ln in text.split("\n") if not ln.lstrip().startswith(">")]
    text = "\n".join(lines)

    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def build_state(record, body_limit=2000):
    return "Gonderen: {} <{}>\nKonu: {}\nGovde: {}".format(
        record["from_name"] or record["from_addr"], record["from_addr"],
        record["subject"], record["body_text_clean"][:body_limit],
    )
