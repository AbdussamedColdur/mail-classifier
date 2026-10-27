"""User settings, fixed categories and the starter rules."""
from __future__ import annotations

import sqlite3
from typing import Any

from . import db

DEFAULTS: dict[str, Any] = {
    "model": "tev1:4b",
    "ollamaUrl": "http://localhost:11434",
    "pollMinutes": 5,
    "maxChars": 2000,
    "onlyUnread": True,
    "stripQuotes": True,
    "dryRun": True,
}

# Every new e-mail is put into exactly one of these by a single "choice" question before the
# rules run; the descriptions are the model's criteria.
CATEGORY_QUESTION = "Bu e-posta hangi kategoriye ait?"
CATEGORIES = [
    {"key": "Banka", "description": "Banka ya da yatırım hesabı hareketi, hesap ekstresi, emir gerçekleşme bildirimi ya da işlem sonuç formu"},
    {"key": "Fatura", "description": "Fatura, e-Arşiv fatura, ödeme ya da borç bildirimi, “faturanız hazır” e-postası"},
    {"key": "Alışveriş", "description": "Sipariş, kargo, bilet ya da dijital satın alma onayı"},
    {"key": "Hesap", "description": "Doğrulama kodu, giriş uyarısı, şifre değişikliği ya da hesap güvenliği bildirimi"},
    {"key": "Kişisel", "description": "Gerçek bir kişinin kendisinin yazdığı e-posta"},
    {"key": "Bülten", "description": "Abone olunan, satış amacı taşımayan içerik ya da haber bülteni"},
    {"key": "Tanıtım", "description": "Kampanya, indirim ya da ürün reklamı; bankaların ve tanınmış şirketlerin tanıtımları da dahil. "
                                      "Banka işlemi ya da ekstresi, fatura, sipariş ve güvenlik e-postaları tanıtım değildir; "
                                      "gönderene değil içeriğe göre karar ver."},
    {"key": "Diğer", "description": "Yukarıdakilerin hiçbirine uymayan e-posta"},
]
CATEGORY_KEYS = [c["key"] for c in CATEGORIES]
DESCRIPTION = {c["key"]: c["description"] for c in CATEGORIES}

# Security mail must stay in the inbox: no rule scoped to these categories may archive.
NEVER_ARCHIVE = {"Hesap"}

# Thresholds. Category rules have only an apply threshold: below it the e-mail goes to the
# approval queue, so undecided mail is always shown. Yes/no rules also have an ignore threshold:
# P(yes) ≤ ignore → only recorded; between → approval; ≥ apply → acted on.
THRESHOLD_RANGE = (0.20, 0.99)
DEFAULT_IGNORE = 0.50


def yes_no(question: str) -> list[dict[str, str]]:
    return [
        {"key": "Evet", "description": f"Evet: {question}"},
        {"key": "Hayır", "description": f"Hayır, bu durum geçerli değil: {question}"},
    ]


ACIL_Q = "Bu e-postayı yazan kişi benden bir yanıt ya da işlem bekliyor mu?"
OLTALAMA_Q = "Bu e-posta oltalama (phishing) şüphesi taşıyor mu?"

# (name, category, question, options, threshold, actions, mode, mode_locked)
# options == [] → the rule acts on the category decision itself; otherwise it asks its own
# yes/no question, only for e-mails in `category` when that is set.
STARTER_RULES: list[tuple] = [
    ("Banka hareketleri", "Banka", DESCRIPTION["Banka"], [], 0.90, ["label:Banka", "archive"], "apply", False),
    ("Faturalar", "Fatura", DESCRIPTION["Fatura"], [], 0.85, ["label:Fatura"], "apply", False),
    ("Alışveriş", "Alışveriş", DESCRIPTION["Alışveriş"], [], 0.90, ["label:Alışveriş", "archive"], "apply", False),
    ("Hesap bildirimleri", "Hesap", DESCRIPTION["Hesap"], [], 0.85, ["label:Hesap"], "apply", False),
    ("Bültenler", "Bülten", DESCRIPTION["Bülten"], [], 0.90, ["label:Bülten", "archive"], "apply", False),
    ("Tanıtımlar", "Tanıtım", DESCRIPTION["Tanıtım"], [], 0.95, ["label:Tanıtım", "archive"], "apply", False),
    ("Acil / yanıt bekliyor", "Kişisel", ACIL_Q, [
        {"key": "Evet", "description": "Yazan kişi benden bir yanıt, onay ya da işlem bekliyor ya da konu acil."},
        {"key": "Hayır", "description": "Yanıt gerektirmeyen bilgilendirme ya da selamlaşma; “son gün”, “hemen” gibi "
                                        "pazarlama ifadeleri aciliyet sayılmaz."},
    ], 0.85, ["star"], "apply", False),
    # Never Gmail's Spam folder: that trains Gmail's filter and can drag the same bank's statements along.
    ("Oltalama şüphesi", None, OLTALAMA_Q, [
        {"key": "Evet", "description": "Kart, şifre, doğrulama kodu ya da kimlik bilgisi istiyor, sahte bir bağlantıya "
                                       "yönlendiriyor ya da tanınmış bir kurumu taklit ediyor."},
        {"key": "Hayır", "description": "Oltalama belirtisi yok; bilinen bir kurumun olağan bildirimi, faturası, "
                                        "ekstresi ya da tanıtımı."},
    ], 0.90, ["label:Oltalama", "archive"], "approve", True),
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


def insert_starter(con: sqlite3.Connection, rule: tuple) -> None:
    """Starter rules begin dry: they only suggest until switched on one by one."""
    name, cat, question, options, th, actions, mode, locked = rule
    con.execute(
        "INSERT INTO rules(name, category, question, options, apply_threshold, ignore_threshold, actions, mode, mode_locked, "
        "dry_run, enabled, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?)",
        (name, cat, question, db.j(options), th, DEFAULT_IGNORE if options else None, db.j(actions), mode, int(locked), db.now()),
    )


def seed_rules() -> None:
    if db.one("SELECT 1 FROM rules LIMIT 1"):
        return
    with db.tx() as con:
        for rule in STARTER_RULES:
            insert_starter(con, rule)
