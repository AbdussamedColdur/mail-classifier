"""HTTP API used by the React front end. Everything is under /api."""
from __future__ import annotations

import csv
import io
import shutil
import subprocess
import sys
from typing import Any, Literal, Optional
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field

from . import classifier, config, db, engine, gmail

router = APIRouter(prefix="/api")

Mode = Literal["report", "approve", "apply"]
KNOWN_MODELS = ["d3:4b", "d3:9b"]


# --- Serialisers ---------------------------------------------------------------------------

def _scores(raw: str) -> list[dict[str, Any]]:
    return [{"key": k, "score": v} for k, v in sorted(db.unj(raw, {}).items(), key=lambda kv: -kv[1])]


ACTION_SQL = """
SELECT a.id, a.status, a.ops, a.error, a.queued, a.created_at, a.updated_at,
       d.source, d.rule_id, d.task_id, d.category, d.question, d.scores, d.top_key, d.top_score,
       d.threshold, d.model, d.latency_ms,
       e.id AS email_id, e.from_name, e.from_addr, e.subject, e.snippet, e.received_at
FROM actions a JOIN decisions d ON d.id = a.decision_id JOIN emails e ON e.id = a.email_id
"""


def _action_out(r: dict[str, Any]) -> dict[str, Any]:
    undo_limit = db.local_midnight(engine.UNDO_DAYS)
    return {
        "id": r["id"],
        "emailId": r["email_id"],
        "from": r["from_name"] or r["from_addr"] or "",
        "addr": r["from_addr"] or "",
        "subject": r["subject"] or "(konu yok)",
        "snippet": r["snippet"] or "",
        "receivedAt": r["received_at"],
        "category": r["category"] or "Diğer",
        "question": r["question"],
        "scores": _scores(r["scores"]),
        "topKey": r["top_key"],
        "topScore": r["top_score"],
        "threshold": r["threshold"],
        "model": r["model"],
        "latencyMs": r["latency_ms"],
        "ruleId": r["rule_id"],
        "taskId": r["task_id"],
        "source": r["source"],
        "ops": db.unj(r["ops"], []),
        "status": r["status"],
        "error": r["error"],
        "createdAt": r["created_at"],
        "updatedAt": r["updated_at"],
        "canUndo": r["status"] == "applied" and r["updated_at"] >= undo_limit,
    }


def _ok(fn, *args) -> dict[str, Any]:
    """Run an engine call and turn the expected failures into HTTP errors."""
    try:
        return {"status": fn(*args)}
    except KeyError:
        raise HTTPException(404, "Kayıt bulunamadı.")
    except gmail.AuthExpired:
        raise HTTPException(409, "Gmail bağlantısı koptu. Hesaplar sayfasından yeniden bağlanın.")
    except gmail.GmailError as e:
        raise HTTPException(502, str(e))


# --- Status and panel ------------------------------------------------------------------------

@router.get("/status")
def status() -> dict[str, Any]:
    s = config.get()
    acc = db.one("SELECT * FROM accounts ORDER BY (status = 'ok') DESC, id LIMIT 1")
    ol = classifier.ollama_status(s["ollamaUrl"])
    return {
        "gmail": {
            "connected": bool(acc and acc["status"] == "ok"),
            "email": acc["email"] if acc else None,
            "status": acc["status"] if acc else "none",
            "lastSync": acc["last_sync"] if acc else None,
        },
        "ollama": {
            "running": ol["running"],
            "version": ol.get("version"),
            "url": s["ollamaUrl"],
            "model": s["model"],
            "modelInstalled": _installed(s["model"], ol["models"]),
            "error": ol.get("error"),
        },
        "dryRun": s["dryRun"],
        "lastScan": engine.state["lastScan"],
        "scanning": engine.state["scanning"],
        "lastError": engine.state["lastError"],
        "waiting": db.one("SELECT COUNT(*) AS n FROM emails WHERE processed_at IS NULL")["n"],
        "pendingCount": db.one("SELECT COUNT(*) AS n FROM actions WHERE status = 'pending'")["n"],
    }


def _installed(model: str, models: list[str]) -> bool:
    return model in models or (":" not in model and f"{model}:latest" in models)


@router.post("/scan")
def scan() -> dict[str, bool]:
    engine.scan_now()
    return {"ok": True}


@router.post("/ollama/start")
def start_ollama() -> dict[str, Any]:
    exe = shutil.which("ollama")
    if not exe:
        raise HTTPException(404, "Ollama bu bilgisayarda bulunamadı.")
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    subprocess.Popen([exe, "serve"], creationflags=flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"ok": True}


@router.get("/stats/today")
def stats_today() -> dict[str, Any]:
    t0, t1, t6 = db.local_midnight(0), db.local_midnight(1), db.local_midnight(6)
    count = lambda sql, *p: db.one(sql, p)["n"]
    last_err = db.one("SELECT error FROM actions WHERE status = 'error' AND updated_at >= ? ORDER BY updated_at DESC LIMIT 1", (t0,))
    return {
        "received": count("SELECT COUNT(*) AS n FROM emails WHERE received_at >= ?", t0),
        "yesterdayReceived": count("SELECT COUNT(*) AS n FROM emails WHERE received_at >= ? AND received_at < ?", t1, t0),
        "weekReceived": count("SELECT COUNT(*) AS n FROM emails WHERE received_at >= ?", t6),
        "processed": count(
            "SELECT COUNT(*) AS n FROM emails e WHERE e.received_at >= ? AND e.processed_at IS NOT NULL AND NOT EXISTS "
            "(SELECT 1 FROM actions a WHERE a.email_id = e.id AND a.status IN ('pending', 'error'))", t0),
        "pending": count("SELECT COUNT(*) AS n FROM actions WHERE status = 'pending'"),
        "errors": count("SELECT COUNT(*) AS n FROM actions WHERE status = 'error' AND updated_at >= ?", t0),
        "lastError": last_err["error"] if last_err else None,
    }


@router.get("/stats/categories")
def stats_categories(days: int = 7) -> dict[str, Any]:
    since = db.local_midnight(max(0, days - 1))
    counts = {r["category"]: r["n"] for r in db.rows(
        "SELECT category, COUNT(*) AS n FROM emails WHERE received_at >= ? AND category IS NOT NULL GROUP BY category", (since,))}
    arch = db.one(
        "SELECT COUNT(*) AS total, SUM(a.status = 'undone') AS undone FROM actions a "
        "WHERE a.created_at >= ? AND a.ops LIKE '%\"archive\"%' AND a.status IN ('applied', 'undone')", (since,))
    items = sorted(({"category": c["key"], "count": counts.get(c["key"], 0)} for c in config.CATEGORIES), key=lambda x: -x["count"])
    return {"items": items, "archiveTotal": arch["total"] or 0, "archiveUndone": arch["undone"] or 0}


@router.get("/feed")
def feed(limit: int = 6) -> list[dict[str, Any]]:
    return [_action_out(r) for r in db.rows(
        ACTION_SQL + " WHERE a.status IN ('applied', 'suggested', 'error', 'undone') ORDER BY a.updated_at DESC, a.id DESC LIMIT ?", (limit,))]


# --- Queue -----------------------------------------------------------------------------------

@router.get("/queue")
def queue() -> list[dict[str, Any]]:
    return [_action_out(r) for r in db.rows(
        ACTION_SQL + " WHERE a.queued = 1 AND (a.status = 'pending' OR a.updated_at >= ?) ORDER BY e.received_at DESC",
        (db.local_midnight(0),))]


class ApproveIn(BaseModel):
    category: Optional[str] = None


class BulkIn(BaseModel):
    ids: list[int]
    decision: Literal["approve", "reject"]


@router.post("/queue/{action_id}/approve")
def queue_approve(action_id: int, body: ApproveIn | None = None) -> dict[str, Any]:
    return _ok(engine.approve, action_id, body.category if body else None)


@router.post("/queue/{action_id}/reject")
def queue_reject(action_id: int) -> dict[str, Any]:
    return _ok(engine.reject, action_id)


@router.post("/queue/bulk")
def queue_bulk(body: BulkIn) -> dict[str, Any]:
    fn = engine.approve if body.decision == "approve" else engine.reject
    return {"results": {i: _ok(fn, i)["status"] for i in body.ids}}


@router.post("/queue/approve-passing")
def queue_approve_passing() -> dict[str, Any]:
    ids = [r["id"] for r in db.rows(
        "SELECT a.id FROM actions a JOIN decisions d ON d.id = a.decision_id WHERE a.status = 'pending' AND d.top_score >= d.threshold")]
    return {"results": {i: _ok(engine.approve, i)["status"] for i in ids}}


# --- Logs ------------------------------------------------------------------------------------

LOG_STATUSES = ("applied", "suggested", "reported", "rejected", "undone", "error")


def _log_rows(range_: str, status_: str | None, q: str | None) -> list[dict[str, Any]]:
    days = {"today": 0, "7d": 6, "30d": 29}.get(range_, 6)
    where = ["a.created_at >= ?", f"a.status IN ({','.join('?' * len(LOG_STATUSES))})"]
    params: list[Any] = [db.local_midnight(days), *LOG_STATUSES]
    if status_:
        where.append("a.status = ?")
        params.append(status_)
    if q:
        where.append("(e.subject LIKE ? OR e.from_name LIKE ? OR e.from_addr LIKE ? OR d.source LIKE ?)")
        params += [f"%{q}%"] * 4
    return [_action_out(r) for r in db.rows(ACTION_SQL + " WHERE " + " AND ".join(where) + " ORDER BY a.created_at DESC, a.id DESC", params)]


@router.get("/actions")
def actions(range: str = "7d", status: Optional[str] = None, q: Optional[str] = None) -> list[dict[str, Any]]:
    return _log_rows(range, status, q)


class IdsIn(BaseModel):
    ids: list[int]


@router.post("/actions/undo")
def actions_undo(body: IdsIn) -> dict[str, Any]:
    return {"results": {i: _ok(engine.undo, i)["status"] for i in body.ids}}


@router.post("/actions/redo")
def actions_redo(body: IdsIn) -> dict[str, Any]:
    return {"results": {i: _ok(engine.redo, i)["status"] for i in body.ids}}


@router.post("/actions/{action_id}/retry")
def actions_retry(action_id: int) -> dict[str, Any]:
    return _ok(engine.retry, action_id)


STATUS_TR = {"applied": "Uygulandı", "suggested": "Önerildi", "reported": "Raporlandı", "rejected": "Reddedildi",
             "undone": "Geri alındı", "error": "Hata", "pending": "Bekliyor"}


@router.get("/actions.csv")
def actions_csv(range: str = "7d", status: Optional[str] = None, q: Optional[str] = None) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Zaman", "Gönderen", "Adres", "Konu", "Kural", "Kategori", "Puan", "Eşik", "İşlem", "Durum", "Hata"])
    for r in _log_rows(range, status, q):
        w.writerow([r["createdAt"], r["from"], r["addr"], r["subject"], r["source"], r["category"],
                    f"{r['topScore']:.2f}", f"{r['threshold']:.2f}", " + ".join(r["ops"]), STATUS_TR.get(r["status"], r["status"]), r["error"] or ""])
    name = f"kayitlar_{db.now()[:10]}.csv"
    return Response(("﻿" + buf.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# --- Rules -----------------------------------------------------------------------------------

class RuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    category: Optional[str] = None
    question: str = Field(min_length=3, max_length=500)
    threshold: float = Field(ge=0.5, le=0.99)
    actions: list[str]
    mode: Mode
    enabled: bool = True


class RulePatch(BaseModel):
    name: Optional[str] = None
    question: Optional[str] = None
    threshold: Optional[float] = Field(default=None, ge=0.5, le=0.99)
    actions: Optional[list[str]] = None
    mode: Optional[Mode] = None
    enabled: Optional[bool] = None


def _rule_out(r: dict[str, Any]) -> dict[str, Any]:
    since = db.local_midnight(6)
    st = db.one(
        "SELECT COUNT(*) AS triggered, SUM(a.status = 'undone') AS undone FROM decisions d "
        "JOIN actions a ON a.decision_id = d.id WHERE d.rule_id = ? AND d.created_at >= ?", (r["id"], since))
    return {
        "id": r["id"], "name": r["name"], "category": r["category"], "question": r["question"],
        "options": db.unj(r["options"], []), "threshold": r["threshold"], "actions": db.unj(r["actions"], []),
        "mode": r["mode"], "enabled": bool(r["enabled"]),
        "stats7d": {"triggered": st["triggered"] or 0, "undone": st["undone"] or 0},
    }


def _valid_ops(ops: list[str]) -> list[str]:
    for op in ops:
        if not (op in ("star", "archive", "read") or (op.startswith("label:") and op[6:].strip())):
            raise HTTPException(422, f"Geçersiz işlem: {op}")
    return ops


@router.get("/rules")
def rules() -> list[dict[str, Any]]:
    return [_rule_out(r) for r in db.rows("SELECT * FROM rules ORDER BY id")]


@router.post("/rules")
def create_rule(body: RuleIn) -> dict[str, Any]:
    if body.category and body.category not in [c["key"] for c in config.CATEGORIES]:
        raise HTTPException(422, "Bilinmeyen kategori.")
    rid = db.execute(
        "INSERT INTO rules(name, category, question, options, threshold, actions, mode, enabled, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (body.name, body.category, body.question, db.j([] if body.category else config.yes_no(body.question)),
         body.threshold, db.j(_valid_ops(body.actions)), body.mode, int(body.enabled), db.now()))
    return _rule_out(db.one("SELECT * FROM rules WHERE id = ?", (rid,)))


@router.patch("/rules/{rule_id}")
def patch_rule(rule_id: int, body: RulePatch) -> dict[str, Any]:
    r = db.one("SELECT * FROM rules WHERE id = ?", (rule_id,))
    if not r:
        raise HTTPException(404, "Kural bulunamadı.")
    sets: dict[str, Any] = {}
    data = body.model_dump(exclude_none=True)
    for key in ("name", "threshold", "mode"):
        if key in data:
            sets[key] = data[key]
    if "enabled" in data:
        sets["enabled"] = int(data["enabled"])
    if "actions" in data:
        sets["actions"] = db.j(_valid_ops(data["actions"]))
    if "question" in data:
        sets["question"] = data["question"]
        if not r["category"]:
            sets["options"] = db.j(config.yes_no(data["question"]))
    if sets:
        db.execute(f"UPDATE rules SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?", (*sets.values(), rule_id))
    return _rule_out(db.one("SELECT * FROM rules WHERE id = ?", (rule_id,)))


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int) -> dict[str, bool]:
    db.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
    return {"ok": True}


# --- Command tasks -----------------------------------------------------------------------------

class PreviewIn(BaseModel):
    query: str = Field(min_length=1)


class Option(BaseModel):
    key: str = Field(min_length=1, max_length=40)
    description: str = ""


class TaskIn(BaseModel):
    query: str = Field(min_length=1)
    question: str = Field(min_length=3, max_length=500)
    options: list[Option] = Field(min_length=2, max_length=8)
    threshold: float = Field(ge=0.5, le=0.99)
    actions: list[str]
    mode: Mode
    dryRun: bool = False


def _task_out(t: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": t["id"], "name": t["name"], "query": t["query"], "question": t["question"],
        "options": db.unj(t["options"]), "threshold": t["threshold"], "actions": db.unj(t["actions"]),
        "mode": t["mode"], "dryRun": bool(t["dry_run"]), "status": t["status"],
        "processed": t["processed"], "total": t["total"], "passed": t["passed"],
        "needsApproval": t["needs_approval"], "error": t["error"], "createdAt": t["created_at"],
    }


@router.post("/tasks/preview")
def task_preview(body: PreviewIn) -> dict[str, Any]:
    try:
        return {**engine.preview(body.query), "secondsPerEmail": engine.avg_latency_ms() / 1000}
    except gmail.AuthExpired:
        raise HTTPException(409, "Gmail bağlantısı koptu.")
    except gmail.GmailError as e:
        raise HTTPException(502, str(e))


@router.post("/tasks")
def create_task(body: TaskIn) -> dict[str, Any]:
    options = [o.model_dump() for o in body.options]
    for o in options:
        o["description"] = o["description"] or o["key"]
    name = body.question if len(body.question) <= 48 else body.question[:47] + "…"
    mode = "report" if body.dryRun else body.mode
    tid = db.execute(
        "INSERT INTO tasks(name, query, question, options, threshold, actions, mode, dry_run, status, created_at) "
        "VALUES(?, ?, ?, ?, ?, ?, ?, ?, 'running', ?)",
        (name, body.query, body.question, db.j(options), body.threshold, db.j(_valid_ops(body.actions)), mode, int(body.dryRun), db.now()))
    engine.start_task(tid)
    return {"id": tid}


@router.get("/tasks")
def tasks(limit: int = 8) -> list[dict[str, Any]]:
    return [_task_out(t) for t in db.rows("SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (limit,))]


@router.get("/tasks/{task_id}/scores")
def task_scores(task_id: int) -> dict[str, Any]:
    t = db.one("SELECT options FROM tasks WHERE id = ?", (task_id,))
    if not t:
        raise HTTPException(404, "Görev bulunamadı.")
    target = db.unj(t["options"])[0]["key"]
    scores = [db.unj(r["scores"], {}).get(target, 0.0) for r in db.rows("SELECT scores FROM decisions WHERE task_id = ?", (task_id,))]
    return {"target": target, "scores": scores}


@router.post("/tasks/{task_id}/pause")
def task_pause(task_id: int) -> dict[str, bool]:
    engine.pause_task(task_id)
    return {"ok": True}


@router.post("/tasks/{task_id}/resume")
def task_resume(task_id: int) -> dict[str, bool]:
    t = db.one("SELECT status FROM tasks WHERE id = ?", (task_id,))
    if not t:
        raise HTTPException(404, "Görev bulunamadı.")
    if t["status"] in ("paused", "error"):
        engine.start_task(task_id)
    return {"ok": True}


# --- Accounts and OAuth --------------------------------------------------------------------------

@router.get("/accounts")
def accounts_list() -> list[dict[str, Any]]:
    return [{"id": a["id"], "email": a["email"], "status": a["status"], "scopes": db.unj(a["scopes"], []),
             "lastSync": a["last_sync"], "error": a["error"]} for a in engine.accounts()]


@router.get("/accounts/credentials")
def credentials_get() -> dict[str, Any]:
    return gmail.credentials_info()


@router.post("/accounts/credentials")
async def credentials_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    try:
        return gmail.save_credentials(await file.read())
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.delete("/accounts/credentials")
def credentials_delete() -> dict[str, bool]:
    gmail.remove_credentials()
    return {"ok": True}


@router.get("/auth/google/start")
def auth_start(request: Request) -> RedirectResponse:
    host = request.headers.get("host", "127.0.0.1:8000")
    try:
        url = gmail.start_flow(f"http://{host}/api/auth/google/callback")
    except ValueError as e:
        return RedirectResponse(f"/#/accounts?error={_q(str(e))}")
    return RedirectResponse(url)


@router.get("/auth/google/callback")
def auth_callback(state: str = "", code: str = "", error: str = "") -> RedirectResponse:
    if error:
        return RedirectResponse(f"/#/accounts?error={_q('Google izni verilmedi: ' + error)}")
    try:
        email = gmail.finish_flow(state, code)
    except Exception as e:
        return RedirectResponse(f"/#/accounts?error={_q(str(e))}")
    engine.scan_now()
    return RedirectResponse(f"/#/accounts?connected={_q(email)}")


def _q(s: str) -> str:
    return quote(s[:300])


@router.post("/accounts/{account_id}/sync")
def account_sync(account_id: int) -> dict[str, bool]:
    acc = db.one("SELECT * FROM accounts WHERE id = ?", (account_id,))
    if not acc:
        raise HTTPException(404, "Hesap bulunamadı.")
    try:
        gmail.service(acc["email"])
    except gmail.AuthExpired as e:
        engine.mark_expired(acc, e)
        raise HTTPException(409, "Erişim izni geçersiz. Yeniden bağlanın.")
    db.execute("UPDATE accounts SET status = 'ok', error = NULL WHERE id = ?", (account_id,))
    engine.scan_now()
    return {"ok": True}


@router.delete("/accounts/{account_id}")
def account_delete(account_id: int) -> dict[str, bool]:
    acc = db.one("SELECT * FROM accounts WHERE id = ?", (account_id,))
    if acc:
        gmail.forget(acc["email"])
        db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    return {"ok": True}


# --- Settings -------------------------------------------------------------------------------------

class SettingsIn(BaseModel):
    model: Optional[str] = None
    ollamaUrl: Optional[str] = None
    pollMinutes: Optional[int] = Field(default=None, ge=1, le=60)
    maxChars: Optional[int] = Field(default=None, ge=500, le=8000)
    onlyUnread: Optional[bool] = None
    stripQuotes: Optional[bool] = None
    dryRun: Optional[bool] = None


class OllamaTestIn(BaseModel):
    ollamaUrl: Optional[str] = None


@router.get("/settings")
def settings_get() -> dict[str, Any]:
    return config.get()


@router.put("/settings")
def settings_put(body: SettingsIn) -> dict[str, Any]:
    data = body.model_dump(exclude_none=True)
    if "ollamaUrl" in data and not data["ollamaUrl"].startswith(("http://", "https://")):
        raise HTTPException(422, "Adres http:// ya da https:// ile başlamalı.")
    before = config.get()
    after = config.update(data)
    if after["pollMinutes"] != before["pollMinutes"]:
        engine.scan_now()
    return after


@router.post("/settings/test-ollama")
def settings_test(body: OllamaTestIn) -> dict[str, Any]:
    s = config.get()
    st = classifier.ollama_status(body.ollamaUrl or s["ollamaUrl"])
    return {"ok": st["running"], "version": st.get("version"), "models": st["models"], "error": st.get("error")}


@router.get("/models")
def models() -> list[dict[str, Any]]:
    st = classifier.ollama_status(config.get()["ollamaUrl"])
    names = KNOWN_MODELS + [m for m in st["models"] if m not in KNOWN_MODELS and not m.startswith("d3:latest")]
    return [{"name": n, "installed": _installed(n, st["models"]) or (n == "d3:4b" and "d3:latest" in st["models"]),
             "kind": "d3" if n.startswith("d3") else "chat"} for n in names]
