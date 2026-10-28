"""Gmail access: OAuth with the user's own desktop client, reading and label changes."""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

import keyring
from keyring.errors import PasswordDeleteError
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from . import db, text

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
]
CRED_PATH = db.DATA_DIR / "credentials.json"
KEYRING_SERVICE = "MailKarar"
LABEL_ROOT = "MailKarar"
PROCESSED_LABEL = f"{LABEL_ROOT}/İşlendi"
RETRIES = 5  # googleapiclient backs off on 429 and 5xx between these

# Google may grant more scopes than asked (ones the same OAuth client got earlier, e.g. gmail.readonly
# from tools/model-tests) or fewer (the user unticks one on the consent screen). oauthlib then raises
# 'Scope has changed from "…" to "…"'. Accept the token and check the required scopes in finish_flow.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")


class AuthExpired(Exception):
    """The stored token is missing, revoked or can no longer be refreshed."""


class GmailError(Exception):
    pass


# --- OAuth client (credentials.json) -------------------------------------------------

def credentials_info() -> dict[str, Any]:
    if not CRED_PATH.exists():
        return {"present": False}
    cfg = json.loads(CRED_PATH.read_text(encoding="utf-8"))
    inner = cfg.get("installed") or {}
    return {"present": True, "projectId": inner.get("project_id"), "clientType": "installed"}


def save_credentials(raw: bytes) -> dict[str, Any]:
    if len(raw) > 64 * 1024:
        raise ValueError("Dosya 64 KB'den büyük.")
    try:
        cfg = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("Geçerli bir JSON dosyası değil.")
    if "installed" not in cfg:
        if "web" in cfg:
            raise ValueError("Bu bir “Web uygulaması” istemcisi. “Masaüstü uygulaması” türünde istemci oluşturun.")
        raise ValueError("Dosyada OAuth istemci bilgisi bulunamadı.")
    for key in ("client_id", "client_secret"):
        if not cfg["installed"].get(key):
            raise ValueError(f"Dosyada {key} eksik.")
    db.DATA_DIR.mkdir(exist_ok=True)
    CRED_PATH.write_bytes(raw)
    return credentials_info()


def remove_credentials() -> None:
    CRED_PATH.unlink(missing_ok=True)


# --- Authorization flow ----------------------------------------------------------------

_flows: dict[str, Flow] = {}
_flows_lock = threading.Lock()


def start_flow(redirect_uri: str) -> str:
    if not CRED_PATH.exists():
        raise ValueError("Önce credentials.json yükleyin.")
    cfg = json.loads(CRED_PATH.read_text(encoding="utf-8"))
    flow = Flow.from_client_config(cfg, scopes=SCOPES, redirect_uri=redirect_uri, autogenerate_code_verifier=True)
    url, state = flow.authorization_url(access_type="offline", prompt="consent")
    with _flows_lock:
        _flows[state] = flow
    return url


def finish_flow(state: str, code: str) -> str:
    with _flows_lock:
        flow = _flows.pop(state, None)
    if flow is None:
        raise ValueError("Yetkilendirme oturumu bulunamadı ya da süresi doldu. Yeniden deneyin.")
    flow.fetch_token(code=code)
    creds = flow.credentials
    granted_full = list(creds.granted_scopes or creds.scopes or [])
    missing = [s.rsplit("/", 1)[-1] for s in SCOPES if s not in granted_full]
    if missing:
        raise ValueError(f"Google onay ekranında gerekli izinler verilmedi: {', '.join(missing)}. "
                         "Yeniden bağlanıp tüm kutuları işaretleyin.")
    svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
    email = svc.users().getProfile(userId="me").execute()["emailAddress"]
    _store(email, creds)
    granted = [s.rsplit("/", 1)[-1] for s in granted_full]
    with db.tx() as con:
        con.execute(
            "INSERT INTO accounts(email, status, scopes, created_at) VALUES(?, 'ok', ?, ?) "
            "ON CONFLICT(email) DO UPDATE SET status = 'ok', scopes = excluded.scopes, error = NULL",
            (email, db.j(granted), db.now()),
        )
    return email


def forget(email: str) -> None:
    try:
        keyring.delete_password(KEYRING_SERVICE, email)
    except PasswordDeleteError:
        pass


# --- Tokens (Windows Credential Manager via keyring) --------------------------------------

def _store(email: str, creds: Credentials) -> None:
    keyring.set_password(KEYRING_SERVICE, email, creds.to_json())


def _creds(email: str) -> Credentials:
    data = keyring.get_password(KEYRING_SERVICE, email)
    if not data:
        raise AuthExpired("Bu hesap için kayıtlı erişim izni yok.")
    creds = Credentials.from_authorized_user_info(json.loads(data), SCOPES)
    if not creds.valid:
        if not creds.refresh_token:
            raise AuthExpired("Erişim izninin süresi doldu.")
        try:
            creds.refresh(Request())
        except RefreshError as e:
            raise AuthExpired(f"Erişim izni yenilenemedi: {e}") from e
        _store(email, creds)
    return creds


def service(email: str):
    return build("gmail", "v1", credentials=_creds(email), cache_discovery=False)


def run(request) -> Any:
    try:
        return request.execute(num_retries=RETRIES)
    except RefreshError as e:
        raise AuthExpired(str(e)) from e
    except HttpError as e:
        if e.resp.status == 401:
            raise AuthExpired("Gmail erişimi reddedildi (401).") from e
        if e.resp.status == 429:
            raise GmailError("Gmail API sınırı (429)") from e
        raise GmailError(f"Gmail API {e.resp.status}: {e.reason}") from e


# --- Reading -------------------------------------------------------------------------------

def list_ids(svc, query: str, limit: int) -> list[str]:
    ids: list[str] = []
    token = None
    while len(ids) < limit:
        resp = run(svc.users().messages().list(userId="me", q=query, maxResults=min(500, limit - len(ids)), pageToken=token))
        ids += [m["id"] for m in resp.get("messages", [])]
        token = resp.get("nextPageToken")
        if not token:
            break
    return ids


def fetch(svc, msg_id: str) -> dict[str, Any]:
    msg = run(svc.users().messages().get(userId="me", id=msg_id, format="full"))
    payload = msg.get("payload", {})
    name, addr = text.sender(payload)
    received = datetime.fromtimestamp(int(msg.get("internalDate", "0")) / 1000, tz=timezone.utc)
    return {
        "id": msg["id"],
        "thread_id": msg.get("threadId"),
        "from_name": name,
        "from_addr": addr,
        "subject": text.header(payload, "Subject"),
        "snippet": text.html_to_text(msg.get("snippet", "")),
        "body": text.body(payload),
        "received_at": received.isoformat(timespec="seconds"),
        "labels": msg.get("labelIds", []),
    }


def received_at(svc, msg_id: str) -> str:
    msg = run(svc.users().messages().get(userId="me", id=msg_id, format="minimal"))
    return datetime.fromtimestamp(int(msg.get("internalDate", "0")) / 1000, tz=timezone.utc).isoformat(timespec="seconds")


def current_labels(svc, msg_id: str) -> list[str]:
    return run(svc.users().messages().get(userId="me", id=msg_id, format="minimal")).get("labelIds", [])


# --- Changing ------------------------------------------------------------------------------

class Labels:
    """Label name → id lookup that creates missing MailKarar/* labels on demand."""

    def __init__(self, svc):
        self.svc = svc
        self.by_name = {l["name"]: l["id"] for l in run(svc.users().labels().list(userId="me")).get("labels", [])}

    def id(self, name: str) -> str:
        if name not in self.by_name:
            if "/" in name:
                self.id(name.rsplit("/", 1)[0])  # Gmail nests a label only under an existing parent
            created = run(self.svc.users().labels().create(
                userId="me", body={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"}))
            self.by_name[name] = created["id"]
        return self.by_name[name]


def label_name(op: str) -> str:
    return f"{LABEL_ROOT}/{op.split(':', 1)[1].strip()}"


def apply_ops(svc, labels: Labels, msg_id: str, ops: list[str]) -> dict[str, list[str]]:
    """Apply ops and return only the label ids that really changed, so undo restores the prior state."""
    have = set(current_labels(svc, msg_id))
    add: set[str] = set()
    remove: set[str] = set()
    for op in ops:
        if op.startswith("label:"):
            add.add(labels.id(label_name(op)))
        elif op == "star":
            add.add("STARRED")
        elif op == "archive":
            remove.add("INBOX")
        elif op == "read":
            remove.add("UNREAD")
    add.add(labels.id(PROCESSED_LABEL))
    add -= have
    remove &= have
    if add or remove:
        run(svc.users().messages().modify(userId="me", id=msg_id, body={"addLabelIds": sorted(add), "removeLabelIds": sorted(remove)}))
    return {"add": sorted(add), "remove": sorted(remove)}


def revert(svc, msg_id: str, changes: dict[str, list[str]]) -> None:
    if changes.get("add") or changes.get("remove"):
        run(svc.users().messages().modify(
            userId="me", id=msg_id, body={"addLabelIds": changes.get("remove", []), "removeLabelIds": changes.get("add", [])}))
