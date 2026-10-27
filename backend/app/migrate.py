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


def _v2_to_v3(con: sqlite3.Connection) -> None:
    """Two thresholds: the old one becomes the apply threshold; yes/no rules and tasks get an
    ignore threshold below it. Every existing rule starts dry, to be switched on one by one."""
    for table in ("rules", "tasks", "decisions"):
        con.execute(f"ALTER TABLE {table} RENAME COLUMN threshold TO apply_threshold")
    con.execute("ALTER TABLE rules ADD COLUMN ignore_threshold REAL")
    con.execute("ALTER TABLE rules ADD COLUMN dry_run INTEGER NOT NULL DEFAULT 1")
    con.execute("ALTER TABLE tasks ADD COLUMN ignore_threshold REAL NOT NULL DEFAULT 0.5")
    con.execute("ALTER TABLE decisions ADD COLUMN ignore_threshold REAL")
    below = "MIN(?, ROUND(apply_threshold - 0.05, 2))"
    con.execute(f"UPDATE rules SET ignore_threshold = {below} WHERE options != '[]'", (config.DEFAULT_IGNORE,))
    con.execute(f"UPDATE tasks SET ignore_threshold = {below}", (config.DEFAULT_IGNORE,))


def _add_missing_starters(con: sqlite3.Connection) -> None:
    """After the v1 rules were replaced, add the starter rules the user has no rule for yet."""
    taken = {r["category"] for r in con.execute("SELECT category FROM rules WHERE options = '[]' AND enabled = 1")}
    names = {r["name"] for r in con.execute("SELECT name FROM rules")}
    for rule in config.STARTER_RULES:
        name, cat, _, options = rule[:4]
        if name in names or (not options and cat in taken):
            continue  # the user already has a rule for this
        config.insert_starter(con, rule)


MIGRATIONS = {1: _v1_to_v2, 2: _v2_to_v3}


def run() -> None:
    with db.tx() as con:
        con.execute("BEGIN")  # sqlite3 would run ALTER TABLE outside a transaction; keep each upgrade all-or-nothing
        start = v = con.execute("PRAGMA user_version").fetchone()[0]
        while v < db.SCHEMA_VERSION:
            log.info("upgrading database v%d → v%d", v, v + 1)
            MIGRATIONS[v](con)
            v += 1
            con.execute(f"PRAGMA user_version = {v}")
        if start < 2:  # inserted with the latest columns, so only once every step has run
            _add_missing_starters(con)
