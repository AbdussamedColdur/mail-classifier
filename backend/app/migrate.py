"""Upgrade an existing database one schema version at a time (PRAGMA user_version)."""
from __future__ import annotations

import logging
import sqlite3

from . import config, db

log = logging.getLogger("mailkarar")

# The v1 starter rules exactly as they were seeded: (name, category, question, threshold, actions, mode).
V1_STARTERS = [
    ("Faturaları ayır", "Fatura", "Bu e-posta bir fatura veya ödeme bildirimi mi?", 0.80, ["label:Fatura", "archive"], "apply"),
    ("Müşteri talepleri", "Müşteri", "Bir müşteri sipariş, şikâyet ya da destek talebi mi iletiyor?", 0.80, ["label:Müşteri", "star"], "approve"),
    ("Bültenleri arşivle", "Bülten", "Bu bir bülten ya da pazarlama e-postası mı?", 0.75, ["archive"], "apply"),
    ("Spam temizliği", "Spam", "Bu e-posta istenmeyen ya da oltalama amaçlı mı?", 0.90, ["label:Spam", "archive"], "apply"),
    ("Acil iş e-postaları", None, "Bu e-posta bugün yanıt gerektiren acil bir iş talebi mi?", 0.85, ["label:Acil", "star"], "approve"),
    ("Ödenmemiş faturalar", None, "Bu e-posta henüz ödenmemiş bir fatura içeriyor mu?", 0.80, ["label:Ödenmemiş", "star"], "report"),
]


def _v1_to_v2(con: sqlite3.Connection) -> None:
    """Eight new categories. Untouched v1 starter rules are replaced by the new ones; a rule the
    user made or edited is kept, and if its category no longer exists (Müşteri, Spam) it becomes
    a disabled yes/no rule with its own question, for the user to review."""
    con.execute("ALTER TABLE rules ADD COLUMN mode_locked INTEGER NOT NULL DEFAULT 0")
    untouched = {(n, c, q, t, tuple(a), m) for n, c, q, t, a, m in V1_STARTERS}
    for r in con.execute("SELECT * FROM rules").fetchall():
        key = (r["name"], r["category"], r["question"], r["threshold"], tuple(db.unj(r["actions"], [])), r["mode"])
        if key in untouched:
            con.execute("DELETE FROM rules WHERE id = ?", (r["id"],))
        elif r["category"] and r["category"] not in config.CATEGORY_KEYS:
            con.execute("UPDATE rules SET category = NULL, options = ?, enabled = 0 WHERE id = ?",
                        (db.j(config.yes_no(r["question"])), r["id"]))
            log.info("rule %r: category %s no longer exists, turned into a disabled yes/no rule", r["name"], r["category"])

    taken = {r["category"] for r in con.execute("SELECT category FROM rules WHERE options = '[]' AND enabled = 1")}
    names = {r["name"] for r in con.execute("SELECT name FROM rules")}
    for rule in config.STARTER_RULES:
        name, cat, _, options = rule[:4]
        if name in names or (not options and cat in taken):
            continue  # the user already has a rule for this
        config.insert_starter(con, rule)


MIGRATIONS = {1: _v1_to_v2}


def run() -> None:
    with db.tx() as con:
        con.execute("BEGIN")  # sqlite3 would run ALTER TABLE outside a transaction; keep each upgrade all-or-nothing
        v = con.execute("PRAGMA user_version").fetchone()[0]
        while v < db.SCHEMA_VERSION:
            log.info("upgrading database v%d → v%d", v, v + 1)
            MIGRATIONS[v](con)
            v += 1
            con.execute(f"PRAGMA user_version = {v}")
