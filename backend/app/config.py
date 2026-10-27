"""User settings, fixed categories and the starter rules."""
from __future__ import annotations

from typing import Any

from . import db

DEFAULTS: dict[str, Any] = {
    "model": "d3:9b",
    "ollamaUrl": "http://localhost:11434",
    "pollMinutes": 5,
    "maxChars": 2000,
    "onlyUnread": True,
    "stripQuotes": True,
    "dryRun": True,
}

# Every new e-mail is put into exactly one of these before the rules run.
CATEGORY_QUESTION = "Bu e-posta hangi kategoriye ait?"
CATEGORIES = [
    {"key": "Fatura", "description": "Fatura, ödeme bildirimi, hesap ekstresi ya da makbuz"},
    {"key": "Müşteri", "description": "Bir müşterinin sipariş, şikâyet, teklif ya da destek talebi"},
    {"key": "Bülten", "description": "Bülten, pazarlama, kampanya ya da otomatik bilgilendirme e-postası"},
    {"key": "Spam", "description": "İstenmeyen, dolandırıcılık ya da oltalama amaçlı e-posta"},
    {"key": "Diğer", "description": "Yukarıdakilerin hiçbirine uymayan kişisel ya da iş e-postası"},
]


def yes_no(question: str) -> list[dict[str, str]]:
    return [
        {"key": "Evet", "description": f"Evet: {question}"},
        {"key": "Hayır", "description": f"Hayır, bu durum geçerli değil: {question}"},
    ]


STARTER_RULES = [
    ("Faturaları ayır", "Fatura", "Bu e-posta bir fatura veya ödeme bildirimi mi?", 0.80, ["label:Fatura", "archive"], "apply", True),
    ("Müşteri talepleri", "Müşteri", "Bir müşteri sipariş, şikâyet ya da destek talebi mi iletiyor?", 0.80, ["label:Müşteri", "star"], "approve", True),
    ("Bültenleri arşivle", "Bülten", "Bu bir bülten ya da pazarlama e-postası mı?", 0.75, ["archive"], "apply", True),
    ("Spam temizliği", "Spam", "Bu e-posta istenmeyen ya da oltalama amaçlı mı?", 0.90, ["label:Spam", "archive"], "apply", True),
    ("Acil iş e-postaları", None, "Bu e-posta bugün yanıt gerektiren acil bir iş talebi mi?", 0.85, ["label:Acil", "star"], "approve", True),
    ("Ödenmemiş faturalar", None, "Bu e-posta henüz ödenmemiş bir fatura içeriyor mu?", 0.80, ["label:Ödenmemiş", "star"], "report", False),
]


def get() -> dict[str, Any]:
    stored = {r["key"]: db.unj(r["value"]) for r in db.rows("SELECT key, value FROM settings")}
    return {**DEFAULTS, **stored}


def update(values: dict[str, Any]) -> dict[str, Any]:
    with db.tx() as con:
        for key, value in values.items():
            if key in DEFAULTS:
                con.execute(
                    "INSERT INTO settings(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, db.j(value)),
                )
    return get()


def seed_rules() -> None:
    if db.one("SELECT 1 FROM rules LIMIT 1"):
        return
    with db.tx() as con:
        for name, cat, question, th, actions, mode, enabled in STARTER_RULES:
            con.execute(
                "INSERT INTO rules(name, category, question, options, threshold, actions, mode, enabled, created_at) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (name, cat, question, db.j([] if cat else yes_no(question)), th, db.j(actions), mode, int(enabled), db.now()),
            )
