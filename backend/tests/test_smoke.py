"""End-to-end check of the rule engine and API with Gmail and the model replaced by fakes.

Run from backend/: .venv\\Scripts\\python -m unittest discover -s tests -v
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app import api, classifier, config, db, engine, gmail
from app.main import app

MAILS = {
    "m1": {"from_name": "e-Fatura Bildirim", "from_addr": "bildirim@e-fatura.example", "subject": "Ekim faturanız oluşturuldu", "body": "Son ödeme 10 Kasım."},
    "m2": {"from_name": "Teknoloji Bülteni", "from_addr": "haber@bulten.example", "subject": "Haftanın öne çıkanları", "body": "Bu hafta..."},
    "m3": {"from_name": "Mehmet Demir", "from_addr": "mehmet@example.com", "subject": "Sipariş #4821 gelmedi", "body": "Dönüş bekliyorum.\n\nOn Mon, X wrote:\n> eski"},
}
CATEGORY_OF = {"m1": ("Fatura", 0.92), "m2": ("Bülten", 0.70), "m3": ("Müşteri", 0.85)}


class FakeGmail:
    def __init__(self):
        self.labels = {mid: ["INBOX", "UNREAD"] for mid in MAILS}

    def message(self, mid):
        m = MAILS[mid]
        return {**m, "id": mid, "thread_id": mid, "snippet": m["body"][:40], "received_at": db.now(), "labels": self.labels[mid]}

    def apply_ops(self, svc, labels, mid, ops):
        add = {f"L:{o[6:]}" for o in ops if o.startswith("label:")} | ({"STARRED"} if "star" in ops else set()) | {"L:İşlendi"}
        remove = ({"INBOX"} if "archive" in ops else set()) | ({"UNREAD"} if "read" in ops else set())
        have = set(self.labels[mid])
        add -= have
        remove &= have
        self.labels[mid] = sorted((have | add) - remove)
        return {"add": sorted(add), "remove": sorted(remove)}

    def revert(self, svc, mid, changes):
        self.labels[mid] = sorted((set(self.labels[mid]) - set(changes["add"])) | set(changes["remove"]))


def fake_classify(settings, content, question, options):
    keys = [o["key"] for o in options]
    if question == config.CATEGORY_QUESTION:
        mid = next(k for k, m in MAILS.items() if m["subject"] in content)
        top, p = CATEGORY_OF[mid]
        rest = (1 - p) / (len(keys) - 1)
        return classifier.Result({k: (p if k == top else rest) for k in keys}, "d3:9b", 800)
    yes = 0.9 if "Sipariş" in content else 0.1  # only m3 counts as urgent
    return classifier.Result({keys[0]: yes, keys[1]: 1 - yes}, "d3:9b", 600)


class SmokeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            mock.patch.object(db, "DATA_DIR", Path(self.tmp.name)),
            mock.patch.object(db, "DB_PATH", Path(self.tmp.name) / "t.db"),
        ]
        for p in self.patches:
            p.start()
        db.init()
        config.seed_rules()
        db.execute("INSERT INTO accounts(email, status, scopes, created_at) VALUES('ali@gmail.com', 'ok', '[]', ?)", (db.now(),))
        self.g = FakeGmail()
        for target, value in [
            ("service", lambda email: object()),
            ("list_ids", lambda svc, q, limit: list(MAILS)),
            ("fetch", lambda svc, mid: self.g.message(mid)),
            ("received_at", lambda svc, mid: db.now()),
            ("Labels", lambda svc: object()),
            ("apply_ops", self.g.apply_ops),
            ("revert", self.g.revert),
        ]:
            p = mock.patch.object(gmail, target, value)
            p.start()
            self.patches.append(p)
        p = mock.patch.object(classifier, "classify", fake_classify)
        p.start()
        self.patches.append(p)
        p = mock.patch.object(classifier, "ollama_status", lambda url: {"running": True, "version": "0.41.0", "models": ["d3:9b"]})
        p.start()
        self.patches.append(p)
        self.client = TestClient(app)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_scan_rules_queue_and_undo(self):
        c = self.client
        config.update({"dryRun": False})
        engine.scan()

        # m1 Fatura 0.92 ≥ 0.80 apply → applied; m2 Bülten 0.70 < 0.75 → queue; m3 Müşteri approve → queue, and Acil approve → queue.
        acts = {(r["email_id"], r["source"]): r["status"] for r in db.rows(
            "SELECT a.email_id, d.source, a.status FROM actions a JOIN decisions d ON d.id = a.decision_id")}
        self.assertEqual(acts, {
            ("m1", "Faturaları ayır"): "applied",
            ("m2", "Bültenleri arşivle"): "pending",
            ("m3", "Müşteri talepleri"): "pending",
            ("m3", "Acil iş e-postaları"): "pending",
        })
        self.assertNotIn("INBOX", self.g.labels["m1"])
        self.assertIn("L:Fatura", self.g.labels["m1"])

        st = c.get("/api/status").json()
        self.assertTrue(st["gmail"]["connected"])
        self.assertEqual(st["pendingCount"], 3)
        today = c.get("/api/stats/today").json()
        self.assertEqual((today["received"], today["processed"], today["pending"]), (3, 1, 3))
        cats = {i["category"]: i["count"] for i in c.get("/api/stats/categories").json()["items"]}
        self.assertEqual((cats["Fatura"], cats["Bülten"], cats["Müşteri"], cats["Spam"]), (1, 1, 1, 0))

        queue = c.get("/api/queue").json()
        self.assertEqual(len(queue), 3)
        acil = next(q for q in queue if q["source"] == "Acil iş e-postaları")
        self.assertEqual(acil["category"], "Acil")
        self.assertEqual(acil["scores"][0]["key"], "Evet")

        bulten = next(q for q in queue if q["source"] == "Bültenleri arşivle")
        self.assertEqual(c.post(f"/api/queue/{bulten['id']}/approve", json={}).json()["status"], "applied")
        self.assertNotIn("INBOX", self.g.labels["m2"])
        self.assertEqual(c.post(f"/api/queue/{acil['id']}/reject").json()["status"], "rejected")

        # Undo restores exactly the earlier labels, redo puts the change back.
        logs = c.get("/api/actions", params={"range": "today"}).json()
        fatura = next(l for l in logs if l["source"] == "Faturaları ayır")
        self.assertTrue(fatura["canUndo"])
        c.post("/api/actions/undo", json={"ids": [fatura["id"]]})
        self.assertEqual(self.g.labels["m1"], ["INBOX", "UNREAD"])
        c.post("/api/actions/redo", json={"ids": [fatura["id"]]})
        self.assertNotIn("INBOX", self.g.labels["m1"])

        csv = c.get("/api/actions.csv", params={"range": "today"})
        self.assertIn("Faturaları ayır", csv.content.decode("utf-8-sig"))

        rules = {r["name"]: r for r in c.get("/api/rules").json()}
        self.assertEqual(rules["Faturaları ayır"]["stats7d"], {"triggered": 1, "undone": 0})
        self.assertFalse(rules["Ödenmemiş faturalar"]["enabled"])

    def test_dry_run_never_touches_gmail(self):
        engine.scan()  # dryRun defaults to True
        self.assertEqual(self.g.labels["m1"], ["INBOX", "UNREAD"])
        st = db.one("SELECT a.status FROM actions a JOIN decisions d ON d.id = a.decision_id WHERE d.source = 'Faturaları ayır'")
        self.assertEqual(st["status"], "suggested")
        pending = self.client.get("/api/queue").json()[0]
        self.assertEqual(self.client.post(f"/api/queue/{pending['id']}/approve", json={}).json()["status"], "suggested")
        self.assertEqual(self.g.labels["m2"], ["INBOX", "UNREAD"])

    def test_model_down_leaves_mail_waiting(self):
        def down(*a, **k):
            raise classifier.ModelError("Ollama'ya ulaşılamıyor")
        with mock.patch.object(classifier, "classify", down):
            engine.scan()
        self.assertEqual(self.client.get("/api/status").json()["waiting"], 3)
        engine.scan()  # model back
        self.assertEqual(self.client.get("/api/status").json()["waiting"], 0)

    def test_rules_crud_and_validation(self):
        c = self.client
        r = c.post("/api/rules", json={"name": "Test", "question": "Bu bir test mi?", "threshold": 0.8, "actions": ["label:Test", "star"], "mode": "report"})
        self.assertEqual(r.status_code, 200, r.text)
        rid = r.json()["id"]
        self.assertEqual(r.json()["options"][0]["key"], "Evet")
        self.assertEqual(c.patch(f"/api/rules/{rid}", json={"threshold": 0.9}).json()["threshold"], 0.9)
        self.assertEqual(c.post("/api/rules", json={"name": "X", "question": "abc?", "threshold": 0.8, "actions": ["delete"], "mode": "apply"}).status_code, 422)
        c.delete(f"/api/rules/{rid}")
        self.assertNotIn(rid, [x["id"] for x in c.get("/api/rules").json()])

    def test_task_run(self):
        config.update({"dryRun": False})
        t = {"query": "in:inbox", "question": "Bu e-posta bir sipariş şikâyeti mi?", "threshold": 0.8,
             "options": [{"key": "Evet", "description": ""}, {"key": "Hayır", "description": ""}],
             "actions": ["label:Şikayet"], "mode": "apply", "dryRun": False}
        with mock.patch.object(engine, "start_task", lambda tid: engine._run_task(tid, engine.threading.Event())):
            tid = self.client.post("/api/tasks", json=t).json()["id"]
        task = self.client.get("/api/tasks").json()[0]
        self.assertEqual((task["id"], task["status"], task["processed"], task["passed"]), (tid, "done", 3, 1))
        self.assertIn("L:Şikayet", self.g.labels["m3"])
        self.assertEqual(len(self.client.get(f"/api/tasks/{tid}/scores").json()["scores"]), 3)

    def test_settings_validation(self):
        c = self.client
        self.assertEqual(c.put("/api/settings", json={"maxChars": 100}).status_code, 422)
        self.assertEqual(c.put("/api/settings", json={"ollamaUrl": "localhost"}).status_code, 422)
        self.assertEqual(c.put("/api/settings", json={"pollMinutes": 15}).json()["pollMinutes"], 15)


class TextTest(unittest.TestCase):
    def test_strip_quotes(self):
        from app import text
        body = "Merhaba,\nSiparişim gelmedi.\n\nOn Mon, 1 Jan 2026 Ali <a@b.c> wrote:\n> eski mesaj"
        self.assertEqual(text.strip_quotes(body), "Merhaba,\nSiparişim gelmedi.")
        tr = "Tamam.\n\n26 Eki 2026 Pzt 10:00 tarihinde Ali şunu yazdı:\n> önceki"
        self.assertEqual(text.strip_quotes(tr), "Tamam.")

    def test_d3_probability_shapes(self):
        p = classifier._probability
        self.assertEqual(p({"noul": 0.7}, "q"), 0.7)
        self.assertEqual(p({"noul": {"true": 0.2, "false": 0.8}}, "q"), 0.2)
        self.assertEqual(p({"noul": True}, "q"), 1.0)
        with self.assertRaises(classifier.ModelError):
            p({"noul": [1, 2]}, "q")


if __name__ == "__main__":
    unittest.main()
