"""SQLite storage. Every call opens its own connection, so worker threads can share it."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "mailkarar.db"
SCHEMA_VERSION = 3  # PRAGMA user_version; SCHEMA below is always the latest layout

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  status TEXT NOT NULL DEFAULT 'ok',          -- ok | expired
  scopes TEXT NOT NULL DEFAULT '[]',
  last_sync TEXT,
  error TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS emails (
  id TEXT PRIMARY KEY,                        -- Gmail message id
  account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  thread_id TEXT,
  from_name TEXT,
  from_addr TEXT,
  subject TEXT,
  snippet TEXT,
  body TEXT,
  received_at TEXT,
  labels TEXT NOT NULL DEFAULT '[]',
  category TEXT,
  category_scores TEXT,
  fetched_at TEXT NOT NULL,
  processed_at TEXT,
  error TEXT
);
CREATE TABLE IF NOT EXISTS rules (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  category TEXT,                              -- NULL: independent yes/no question
  question TEXT NOT NULL,
  options TEXT NOT NULL DEFAULT '[]',
  apply_threshold REAL NOT NULL,              -- score ≥ this → act (when the mode allows)
  ignore_threshold REAL,                      -- yes/no rules only: score ≤ this → just record; NULL for category rules
  actions TEXT NOT NULL,
  mode TEXT NOT NULL,                         -- report | approve | apply
  mode_locked INTEGER NOT NULL DEFAULT 0,     -- 1: the mode cannot be changed (Oltalama → always approve)
  dry_run INTEGER NOT NULL DEFAULT 1,         -- 1: only suggest, even when the global dry mode is off
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  query TEXT NOT NULL,
  question TEXT NOT NULL,
  options TEXT NOT NULL,
  apply_threshold REAL NOT NULL,
  ignore_threshold REAL NOT NULL,
  actions TEXT NOT NULL,
  mode TEXT NOT NULL,
  dry_run INTEGER NOT NULL,
  status TEXT NOT NULL,                       -- running | paused | done | error
  processed INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL DEFAULT 0,
  passed INTEGER NOT NULL DEFAULT 0,
  needs_approval INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY,
  email_id TEXT NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
  rule_id INTEGER REFERENCES rules(id) ON DELETE SET NULL,
  task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
  source TEXT NOT NULL,                       -- rule or task name at decision time
  category TEXT,
  question TEXT NOT NULL,
  scores TEXT NOT NULL,
  top_key TEXT NOT NULL,
  top_score REAL NOT NULL,
  apply_threshold REAL NOT NULL,
  ignore_threshold REAL,
  model TEXT NOT NULL,
  latency_ms INTEGER,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS actions (
  id INTEGER PRIMARY KEY,
  decision_id INTEGER NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
  email_id TEXT NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
  ops TEXT NOT NULL,
  -- pending | applied | suggested | reported | rejected | undone | error
  status TEXT NOT NULL,
  queued INTEGER NOT NULL DEFAULT 0,
  changes TEXT,                               -- label ids actually added/removed, for undo
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_actions_status ON actions(status);
CREATE INDEX IF NOT EXISTS ix_emails_received ON emails(received_at);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def local_midnight(days_ago: int = 0) -> str:
    """Local midnight `days_ago` days back, as a UTC ISO string comparable to stored times."""
    d = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    return (d - timedelta(days=days_ago)).astimezone(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    con = connect()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init() -> None:
    """Create a new database at SCHEMA_VERSION; an existing one is upgraded by migrate.run()."""
    with tx() as con:
        con.execute("PRAGMA journal_mode=WAL")
        fresh = not con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'rules'").fetchone()
        con.executescript(SCHEMA)
        if fresh:
            con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        elif con.execute("PRAGMA user_version").fetchone()[0] == 0:
            con.execute("PRAGMA user_version = 1")  # databases from before versioning


def version() -> int:
    with tx() as con:
        return con.execute("PRAGMA user_version").fetchone()[0]


def rows(sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
    with tx() as con:
        return [dict(r) for r in con.execute(sql, params).fetchall()]


def one(sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
    with tx() as con:
        r = con.execute(sql, params).fetchone()
        return dict(r) if r else None


def execute(sql: str, params: tuple | list = ()) -> int:
    """Run a write and return lastrowid."""
    with tx() as con:
        return con.execute(sql, params).lastrowid


def j(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def unj(value: str | None, default: Any = None) -> Any:
    return json.loads(value) if value else default
