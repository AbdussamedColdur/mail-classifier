"""Turn a Gmail message payload into the short text the model sees."""
from __future__ import annotations

import base64
import html
import re
from email.utils import parseaddr
from typing import Any

# A reply header ("On Mon, ... wrote:" / "... tarihinde ... şunu yazdı:") or an
# Outlook separator starts the quoted history; everything after it is dropped.
_QUOTE_START = re.compile(
    r"^(On .{5,200} wrote:|.{5,200} tarihinde .{0,200}(şunu )?yazdı:|-{2,}\s*Original Message\s*-{2,}"
    r"|-{2,}\s*Orijinal İleti\s*-{2,}|From: .+|Kimden: .+)\s*$",
    re.IGNORECASE,
)
_SIGNATURE_START = re.compile(r"^(-- ?|__+|Sent from my .+|iPhone'umdan gönderildi.*|Saygılarımla,?|Best regards,?)\s*$", re.IGNORECASE)


def header(payload: dict[str, Any], name: str) -> str:
    for h in payload.get("headers", []):
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def sender(payload: dict[str, Any]) -> tuple[str, str]:
    name, addr = parseaddr(header(payload, "From"))
    return (name or addr), addr


def _charset(part: dict[str, Any]) -> str:
    m = re.search(r'charset="?([\w.-]+)', header(part, "Content-Type"), re.IGNORECASE)
    return m.group(1) if m else "utf-8"


def _decode(part: dict[str, Any]) -> str:
    data = part.get("body", {}).get("data")
    if not data:
        return ""
    raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    try:
        return raw.decode(_charset(part), errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _walk(part: dict[str, Any]):
    yield part
    for p in part.get("parts", []) or []:
        yield from _walk(p)


def html_to_text(markup: str) -> str:
    markup = re.sub(r"(?is)<(script|style|head).*?</\1>", " ", markup)
    markup = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", markup)
    markup = re.sub(r"<[^>]+>", " ", markup)
    return html.unescape(markup)


def body(payload: dict[str, Any]) -> str:
    plain = rich = None
    for part in _walk(payload):
        mime = part.get("mimeType", "")
        if mime == "text/plain" and plain is None:
            plain = _decode(part)
        elif mime == "text/html" and rich is None:
            rich = _decode(part)
    text = plain if plain and plain.strip() else html_to_text(rich or "")
    text = re.sub(r"[ \t ]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def strip_quotes(text: str) -> str:
    kept: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if _QUOTE_START.match(s) or _SIGNATURE_START.match(s):
            break
        if s.startswith(">"):
            continue
        kept.append(line)
    return "\n".join(kept).strip() or text


def for_model(email: dict[str, Any], max_chars: int, strip: bool) -> str:
    """Sender and subject always go; the body is cut at `max_chars`."""
    content = email.get("body") or email.get("snippet") or ""
    if strip:
        content = strip_quotes(content)
    content = content[:max_chars]
    who = email.get("from_name") or ""
    if email.get("from_addr") and email["from_addr"] != who:
        who = f"{who} <{email['from_addr']}>"
    return f"Gönderen: {who}\nKonu: {email.get('subject') or ''}\n\n{content}"
