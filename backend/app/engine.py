"""Fetch new mail, run it through the rules, and apply, queue or undo the resulting actions."""
from __future__ import annotations

import logging
import threading
from typing import Any

from . import classifier, config, db, gmail, text

log = logging.getLogger("mailkarar")

SCAN_LIMIT = 50          # new messages pulled per account per scan
TASK_LIMIT = 500         # messages a single command task may touch
UNDO_DAYS = 30

_scan_lock = threading.Lock()
_wake = threading.Event()
state: dict[str, Any] = {"lastScan": None, "scanning": False, "lastError": None}


# --- Accounts -------------------------------------------------------------------------------

def accounts() -> list[dict[str, Any]]:
    return db.rows("SELECT * FROM accounts ORDER BY id")


def mark_expired(account: dict[str, Any], err: Exception) -> None:
    db.execute("UPDATE accounts SET status = 'expired', error = ? WHERE id = ?", (str(err), account["id"]))


def account_for_email(email_id: str) -> dict[str, Any]:
    acc = db.one("SELECT a.* FROM accounts a JOIN emails e ON e.account_id = a.id WHERE e.id = ?", (email_id,))
    if not acc:
        raise gmail.GmailError("Bu e-postanın hesabı artık bağlı değil.")
    return acc


def store_email(account_id: int, m: dict[str, Any]) -> dict[str, Any]:
    with db.tx() as con:
        con.execute(
            "INSERT INTO emails(id, account_id, thread_id, from_name, from_addr, subject, snippet, body, received_at, labels, fetched_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET labels = excluded.labels",
            (m["id"], account_id, m["thread_id"], m["from_name"], m["from_addr"], m["subject"], m["snippet"],
             m["body"], m["received_at"], db.j(m["labels"]), db.now()),
        )
    return db.one("SELECT * FROM emails WHERE id = ?", (m["id"],))


# --- Scanning -------------------------------------------------------------------------------

def scan_now() -> None:
    _wake.set()


def scan() -> None:
    if not _scan_lock.acquire(blocking=False):
        return
    state["scanning"] = True
    try:
        settings = config.get()
        query = "in:inbox newer_than:2d" + (" is:unread" if settings["onlyUnread"] else "")
        for acc in accounts():
            if acc["status"] != "ok":
                continue
            try:
                svc = gmail.service(acc["email"])
                known = {r["id"] for r in db.rows("SELECT id FROM emails WHERE account_id = ?", (acc["id"],))}
                for msg_id in gmail.list_ids(svc, query, SCAN_LIMIT):
                    if msg_id not in known:
                        store_email(acc["id"], gmail.fetch(svc, msg_id))
                db.execute("UPDATE accounts SET last_sync = ?, error = NULL WHERE id = ?", (db.now(), acc["id"]))
            except gmail.AuthExpired as e:
                mark_expired(acc, e)
            except gmail.GmailError as e:
                db.execute("UPDATE accounts SET error = ? WHERE id = ?", (str(e), acc["id"]))
        process_waiting(settings)
        state["lastError"] = None
    except Exception as e:  # keep the loop alive whatever happens
        log.exception("scan failed")
        state["lastError"] = str(e)
    finally:
        state["lastScan"] = db.now()
        state["scanning"] = False
        _scan_lock.release()


def scheduler() -> None:
    while True:
        scan()
        _wake.clear()
        _wake.wait(timeout=max(1, int(config.get()["pollMinutes"])) * 60)


def start() -> None:
    threading.Thread(target=scheduler, name="scan", daemon=True).start()


# --- Rules ---------------------------------------------------------------------------------

def process_waiting(settings: dict[str, Any]) -> None:
    """Classify every stored e-mail the model has not handled yet (e.g. while Ollama was down)."""
    waiting = db.rows("SELECT * FROM emails WHERE processed_at IS NULL ORDER BY received_at")
    rules = db.rows("SELECT * FROM rules WHERE enabled = 1 ORDER BY id")
    for email in waiting:
        try:
            run_rules(settings, email, rules)
        except classifier.ModelError as e:
            db.execute("UPDATE emails SET error = ? WHERE id = ?", (str(e), email["id"]))
            state["lastError"] = str(e)
            return  # the model is unavailable; try again on the next scan


def run_rules(settings: dict[str, Any], email: dict[str, Any], rules: list[dict[str, Any]]) -> None:
    content = text.for_model(email, int(settings["maxChars"]), bool(settings["stripQuotes"]))
    cat = classifier.classify(settings, content, config.CATEGORY_QUESTION, config.CATEGORIES)
    category, _ = cat.top
    db.execute("UPDATE emails SET category = ?, category_scores = ? WHERE id = ?", (category, db.j(cat.scores), email["id"]))

    for rule in rules:
        ops = db.unj(rule["actions"], [])
        if rule["category"]:
            if rule["category"] != category:
                continue
            result, question, target = cat, config.CATEGORY_QUESTION, category
        else:
            options = db.unj(rule["options"], [])
            result = classifier.classify(settings, content, rule["question"], options)
            question, target = rule["question"], options[0]["key"]
            if result.top[0] != target:
                continue
        decide(settings, email, result, question, target, rule["threshold"], ops, rule["mode"],
               rule_id=rule["id"], source=rule["name"], category=rule["category"] or _label_of(ops) or category)

    db.execute("UPDATE emails SET processed_at = ?, error = NULL WHERE id = ?", (db.now(), email["id"]))


def _label_of(ops: list[str]) -> str | None:
    return next((op.split(":", 1)[1] for op in ops if op.startswith("label:")), None)


def decide(settings, email, result: classifier.Result, question: str, target: str, threshold: float,
           ops: list[str], mode: str, *, rule_id=None, task_id=None, source: str, category: str | None) -> str:
    """Record the decision and either report it, queue it or apply it. Returns the action status."""
    score = result.scores.get(target, 0.0)
    decision_id = db.execute(
        "INSERT INTO decisions(email_id, rule_id, task_id, source, category, question, scores, top_key, top_score, threshold, model, latency_ms, created_at) "
        "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (email["id"], rule_id, task_id, source, category, question, db.j(result.scores), target, score,
         threshold, result.model, result.latency_ms, db.now()),
    )
    if mode == "report":
        status, queued = "reported", 0
    elif mode == "approve" or score < threshold:
        status, queued = "pending", 1
    else:
        status, queued = ("suggested" if settings["dryRun"] else "applied"), 0
    action_id = db.execute(
        "INSERT INTO actions(decision_id, email_id, ops, status, queued, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?)",
        (decision_id, email["id"], db.j(ops), "pending" if status == "applied" else status, queued, db.now(), db.now()),
    )
    if status == "applied":
        return apply(action_id)
    return status


# --- Applying and undoing ----------------------------------------------------------------------

def _action(action_id: int) -> dict[str, Any]:
    a = db.one("SELECT * FROM actions WHERE id = ?", (action_id,))
    if not a:
        raise KeyError(action_id)
    return a


def _set(action_id: int, status: str, **extra: Any) -> None:
    cols = ", ".join(f"{k} = ?" for k in extra)
    db.execute(f"UPDATE actions SET status = ?, updated_at = ?{', ' + cols if cols else ''} WHERE id = ?",
               (status, db.now(), *extra.values(), action_id))


def apply(action_id: int, ops: list[str] | None = None) -> str:
    a = _action(action_id)
    ops = ops if ops is not None else db.unj(a["ops"], [])
    acc = account_for_email(a["email_id"])
    try:
        svc = gmail.service(acc["email"])
        changes = gmail.apply_ops(svc, gmail.Labels(svc), a["email_id"], ops)
    except gmail.AuthExpired as e:
        mark_expired(acc, e)
        _set(action_id, "error", error="Gmail bağlantısı koptu")
        return "error"
    except gmail.GmailError as e:
        _set(action_id, "error", error=str(e))
        return "error"
    _set(action_id, "applied", ops=db.j(ops), changes=db.j(changes), error=None)
    return "applied"


def approve(action_id: int, category: str | None = None) -> str:
    a = _action(action_id)
    if a["status"] != "pending":
        return a["status"]
    ops = db.unj(a["ops"], [])
    if category:
        rule = db.one("SELECT actions FROM rules WHERE category = ? AND enabled = 1", (category,))
        ops = db.unj(rule["actions"]) if rule else [f"label:{category}"]
        db.execute("UPDATE decisions SET category = ? WHERE id = ?", (category, a["decision_id"]))
    if config.get()["dryRun"]:
        _set(action_id, "suggested", ops=db.j(ops))
        return "suggested"
    return apply(action_id, ops)


def reject(action_id: int) -> str:
    if _action(action_id)["status"] == "pending":
        _set(action_id, "rejected")
    return _action(action_id)["status"]


def undo(action_id: int) -> str:
    a = _action(action_id)
    if a["status"] != "applied":
        return a["status"]
    acc = account_for_email(a["email_id"])
    try:
        gmail.revert(gmail.service(acc["email"]), a["email_id"], db.unj(a["changes"], {}))
    except gmail.AuthExpired as e:
        mark_expired(acc, e)
        raise
    _set(action_id, "undone")
    return "undone"


def redo(action_id: int) -> str:
    if _action(action_id)["status"] != "undone":
        return _action(action_id)["status"]
    return apply(action_id)


def retry(action_id: int) -> str:
    if _action(action_id)["status"] != "error":
        return _action(action_id)["status"]
    if config.get()["dryRun"]:
        _set(action_id, "suggested", error=None)
        return "suggested"
    return apply(action_id)


# --- Command tasks -------------------------------------------------------------------------------

_task_flags: dict[int, threading.Event] = {}


def first_account() -> dict[str, Any]:
    acc = db.one("SELECT * FROM accounts WHERE status = 'ok' ORDER BY id LIMIT 1")
    if not acc:
        raise gmail.GmailError("Bağlı bir Gmail hesabı yok.")
    return acc


def preview(query: str) -> dict[str, Any]:
    acc = first_account()
    svc = gmail.service(acc["email"])
    ids = gmail.list_ids(svc, query, TASK_LIMIT)
    known = {r["id"] for r in db.rows(
        "SELECT DISTINCT email_id AS id FROM decisions WHERE email_id IN (%s)" % ",".join("?" * len(ids)), ids)} if ids else set()
    return {
        "matchCount": len(ids),
        "capped": len(ids) >= TASK_LIMIT,
        "oldest": gmail.received_at(svc, ids[-1]) if ids else None,
        "alreadyProcessed": len(known),
    }


def start_task(task_id: int) -> None:
    stop = threading.Event()
    _task_flags[task_id] = stop
    threading.Thread(target=_run_task, args=(task_id, stop), name=f"task-{task_id}", daemon=True).start()


def pause_task(task_id: int) -> None:
    if task_id in _task_flags:
        _task_flags[task_id].set()


def _run_task(task_id: int, stop: threading.Event) -> None:
    t = db.one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    settings = {**config.get(), "dryRun": bool(t["dry_run"]) or config.get()["dryRun"]}
    options = db.unj(t["options"])
    ops = db.unj(t["actions"])
    db.execute("UPDATE tasks SET status = 'running', error = NULL WHERE id = ?", (task_id,))
    try:
        acc = first_account()
        svc = gmail.service(acc["email"])
        ids = gmail.list_ids(svc, t["query"], TASK_LIMIT)
        done = {r["email_id"] for r in db.rows("SELECT email_id FROM decisions WHERE task_id = ?", (task_id,))}
        db.execute("UPDATE tasks SET total = ? WHERE id = ?", (len(ids), task_id))
        for msg_id in ids:
            if stop.is_set():
                db.execute("UPDATE tasks SET status = 'paused' WHERE id = ?", (task_id,))
                return
            if msg_id in done:
                continue
            email = db.one("SELECT * FROM emails WHERE id = ?", (msg_id,)) or store_email(acc["id"], gmail.fetch(svc, msg_id))
            content = text.for_model(email, int(settings["maxChars"]), bool(settings["stripQuotes"]))
            result = classifier.classify(settings, content, t["question"], options)
            target = options[0]["key"]
            if result.top[0] == target:
                status = decide(settings, email, result, t["question"], target, t["threshold"], ops, t["mode"],
                                task_id=task_id, source=t["name"], category=_label_of(ops) or email.get("category"))
                col = "needs_approval" if status == "pending" else "passed"
                db.execute(f"UPDATE tasks SET {col} = {col} + 1 WHERE id = ?", (task_id,))
            else:
                # Still keep the scores so the threshold preview can use them.
                db.execute(
                    "INSERT INTO decisions(email_id, task_id, source, question, scores, top_key, top_score, threshold, model, latency_ms, created_at) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (email["id"], task_id, t["name"], t["question"], db.j(result.scores), result.top[0], result.top[1],
                     t["threshold"], result.model, result.latency_ms, db.now()))
            db.execute("UPDATE tasks SET processed = processed + 1 WHERE id = ?", (task_id,))
        db.execute("UPDATE tasks SET status = 'done' WHERE id = ?", (task_id,))
    except (gmail.GmailError, gmail.AuthExpired, classifier.ModelError) as e:
        db.execute("UPDATE tasks SET status = 'error', error = ? WHERE id = ?", (str(e), task_id))
    except Exception as e:
        log.exception("task %s failed", task_id)
        db.execute("UPDATE tasks SET status = 'error', error = ? WHERE id = ?", (str(e), task_id))
    finally:
        _task_flags.pop(task_id, None)


def resume_interrupted_tasks() -> None:
    """Tasks left 'running' by a previous process are marked paused so the user can continue them."""
    db.execute("UPDATE tasks SET status = 'paused' WHERE status = 'running'")


def avg_latency_ms() -> int:
    r = db.one("SELECT AVG(latency_ms) AS ms FROM (SELECT latency_ms FROM decisions ORDER BY id DESC LIMIT 50)")
    return int(r["ms"]) if r and r["ms"] else 1000

