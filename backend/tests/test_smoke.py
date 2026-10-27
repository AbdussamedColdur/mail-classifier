"""End-to-end check of the rule engine and API with Gmail and the model replaced by fakes.

Run from backend/: .venv\\Scripts\\python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import httpx
from fastapi.testclient import TestClient

from app import api, classifier, config, db, engine, gmail, migrate
from app.main import app

MAILS = {
    "m1": {"from_name": "e-Fatura Bildirim", "from_addr": "bildirim@e-fatura.example", "subject": "Ekim faturanız oluşturuldu", "body": "Son ödeme 10 Kasım."},
    "m2": {"from_name": "Teknoloji Bülteni", "from_addr": "haber@bulten.example", "subject": "Haftanın öne çıkanları", "body": "Bu hafta..."},
    "m3": {"from_name": "Mehmet Demir", "from_addr": "mehmet@example.com", "subject": "Sipariş #4821 gelmedi", "body": "Dönüş bekliyorum.\n\nOn Mon, X wrote:\n> eski"},
    "m4": {"from_name": "Banka Güvenlik", "from_addr": "guvenlik@banka-dogrulama.example", "subject": "Hesabınız askıya alındı", "body": "Şifrenizi bu bağlantıdan doğrulayın."},
}
CATEGORY_OF = {"m1": ("Fatura", 0.92), "m2": ("Bülten", 0.70), "m3": ("Kişisel", 0.85), "m4": ("Hesap", 0.60)}
YES_FOR = {config.ACIL_Q: "m3", config.OLTALAMA_Q: "m4"}  # any other yes/no question: m3


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
    mid = next(k for k, m in MAILS.items() if m["subject"] in content)
    if question == config.CATEGORY_QUESTION:
        top, p = CATEGORY_OF[mid]
        rest = (1 - p) / (len(keys) - 1)
        return classifier.Result({k: (p if k == top else rest) for k in keys}, "tev1:4b", 800)
    yes = 0.9 if mid == YES_FOR.get(question, "m3") else 0.1
    return classifier.Result({keys[0]: yes, keys[1]: 1 - yes}, "tev1:4b", 600)


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
        p = mock.patch.object(classifier, "ollama_status", lambda url: {"running": True, "version": "0.40.11", "models": ["tev1:4b"], "decision": ["tev1:4b"]})
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
        db.execute("UPDATE rules SET dry_run = 0")  # starter rules begin dry
        engine.scan()

        # m1 Fatura 0.92 ≥ 0.85 → label only; m2 Bülten 0.70 < 0.90 → queue; m3 Kişisel → Acil yes 0.9 ≥ 0.85
        # → star; m4 Hesap 0.60 < 0.85 → queue, and Oltalama is always sent for approval.
        acts = {(r["email_id"], r["source"]): r["status"] for r in db.rows(
            "SELECT a.email_id, d.source, a.status FROM actions a JOIN decisions d ON d.id = a.decision_id")}
        self.assertEqual(acts, {
            ("m1", "Faturalar"): "applied",
            ("m2", "Bültenler"): "pending",
            ("m3", "Acil / yanıt bekliyor"): "applied",
            ("m4", "Hesap bildirimleri"): "pending",
            ("m4", "Oltalama şüphesi"): "pending",
        })
        self.assertEqual(self.g.labels["m1"], ["INBOX", "L:Fatura", "L:İşlendi", "UNREAD"])  # Fatura is not archived
        self.assertIn("STARRED", self.g.labels["m3"])

        st = c.get("/api/status").json()
        self.assertTrue(st["gmail"]["connected"])
        self.assertEqual(st["pendingCount"], 3)
        today = c.get("/api/stats/today").json()
        self.assertEqual((today["received"], today["processed"], today["pending"]), (4, 2, 3))
        cats = {i["category"]: i["count"] for i in c.get("/api/stats/categories").json()["items"]}
        self.assertEqual(set(cats), set(config.CATEGORY_KEYS))
        self.assertEqual((cats["Fatura"], cats["Hesap"], cats["Tanıtım"]), (1, 1, 0))

        queue = {q["source"]: q for q in c.get("/api/queue").json()}
        self.assertEqual(len(queue), 3)
        olta = queue["Oltalama şüphesi"]
        self.assertEqual((olta["kind"], olta["category"], olta["scores"][0]["key"]), ("question", "Hesap", "Evet"))
        self.assertEqual(queue["Hesap bildirimleri"]["kind"], "category")

        self.assertEqual(c.post(f"/api/queue/{queue['Bültenler']['id']}/approve", json={}).json()["status"], "applied")
        self.assertNotIn("INBOX", self.g.labels["m2"])
        self.assertEqual(c.post(f"/api/queue/{olta['id']}/reject").json()["status"], "rejected")

        # Correcting the category takes that category rule's actions and fixes the e-mail's category.
        hesap = queue["Hesap bildirimleri"]["id"]
        self.assertEqual(c.post(f"/api/queue/{hesap}/approve", json={"category": "Müşteri"}).status_code, 422)
        self.assertEqual(c.post(f"/api/queue/{hesap}/approve", json={"category": "Tanıtım"}).json()["status"], "applied")
        self.assertIn("L:Tanıtım", self.g.labels["m4"])
        self.assertNotIn("INBOX", self.g.labels["m4"])
        self.assertEqual(db.one("SELECT category FROM emails WHERE id = 'm4'")["category"], "Tanıtım")

        # Undo restores exactly the earlier labels, redo puts the change back.
        logs = c.get("/api/actions", params={"range": "today"}).json()
        fatura = next(l for l in logs if l["source"] == "Faturalar")
        self.assertTrue(fatura["canUndo"])
        c.post("/api/actions/undo", json={"ids": [fatura["id"]]})
        self.assertEqual(self.g.labels["m1"], ["INBOX", "UNREAD"])
        c.post("/api/actions/redo", json={"ids": [fatura["id"]]})
        self.assertIn("L:Fatura", self.g.labels["m1"])

        csv = c.get("/api/actions.csv", params={"range": "today"})
        self.assertIn("Faturalar", csv.content.decode("utf-8-sig"))

        rules = {r["name"]: r for r in c.get("/api/rules").json()}
        self.assertEqual(rules["Faturalar"]["stats7d"], {"triggered": 1, "undone": 0})
        self.assertEqual((rules["Acil / yanıt bekliyor"]["kind"], rules["Acil / yanıt bekliyor"]["category"]), ("question", "Kişisel"))
        self.assertTrue(rules["Oltalama şüphesi"]["modeLocked"])

    def test_categories_come_from_the_backend(self):
        cats = self.client.get("/api/categories").json()
        self.assertEqual([c["key"] for c in cats], ["Banka", "Fatura", "Alışveriş", "Hesap", "Kişisel", "Bülten", "Tanıtım", "Diğer"])
        self.assertIn("tanıtım değildir", next(c for c in cats if c["key"] == "Tanıtım")["description"])

    def test_dry_run_never_touches_gmail(self):
        engine.scan()  # dryRun defaults to True
        self.assertEqual(self.g.labels["m1"], ["INBOX", "UNREAD"])
        st = db.one("SELECT a.status FROM actions a JOIN decisions d ON d.id = a.decision_id WHERE d.source = 'Faturalar'")
        self.assertEqual(st["status"], "suggested")
        pending = next(q for q in self.client.get("/api/queue").json() if q["source"] == "Bültenler")
        self.assertEqual(self.client.post(f"/api/queue/{pending['id']}/approve", json={}).json()["status"], "suggested")
        self.assertEqual(self.g.labels["m2"], ["INBOX", "UNREAD"])

    def test_model_down_leaves_mail_waiting(self):
        def down(*a, **k):
            raise classifier.ModelError("Ollama'ya ulaşılamıyor")
        with mock.patch.object(classifier, "classify", down):
            engine.scan()
        self.assertEqual(self.client.get("/api/status").json()["waiting"], 4)
        engine.scan()  # model back
        self.assertEqual(self.client.get("/api/status").json()["waiting"], 0)

    def test_model_failing_halfway_records_nothing_and_retries_whole(self):
        def category_only(settings, content, question, options):
            if question != config.CATEGORY_QUESTION:
                raise classifier.ModelError("Ollama bağlantısı koptu")
            return fake_classify(settings, content, question, options)
        with mock.patch.object(classifier, "classify", category_only):
            engine.scan()
        self.assertEqual(db.one("SELECT COUNT(*) AS n FROM decisions")["n"], 0)
        self.assertEqual(db.one("SELECT COUNT(*) AS n FROM emails WHERE processed_at IS NULL")["n"], 4)
        engine.scan()
        engine.scan()
        n = db.one("SELECT COUNT(*) AS n, COUNT(DISTINCT email_id || source) AS u FROM decisions")
        self.assertEqual((n["n"], n["u"]), (8, 8))  # every yes/no answer is recorded, also the ignored ones
        self.assertEqual(db.one("SELECT COUNT(*) AS n FROM emails WHERE processed_at IS NULL")["n"], 0)

    def test_rules_crud_and_validation(self):
        c = self.client
        r = c.post("/api/rules", json={"name": "Test", "question": "Bu bir test mi?", "applyThreshold": 0.8, "actions": ["label:Test", "star"], "mode": "report"})
        self.assertEqual(r.status_code, 200, r.text)
        rid = r.json()["id"]
        self.assertEqual(r.json()["options"][0]["key"], "Evet")
        self.assertEqual(c.patch(f"/api/rules/{rid}", json={"applyThreshold": 0.9}).json()["applyThreshold"], 0.9)
        self.assertEqual(c.post("/api/rules", json={"name": "X", "question": "abc?", "applyThreshold": 0.8, "actions": ["delete"], "mode": "apply"}).status_code, 422)
        c.delete(f"/api/rules/{rid}")
        self.assertNotIn(rid, [x["id"] for x in c.get("/api/rules").json()])

        # A yes/no question limited to one category, and a plain category rule.
        base = {"applyThreshold": 0.85, "actions": ["star"], "mode": "apply"}
        r = c.post("/api/rules", json={**base, "name": "Toplantı", "category": "Kişisel", "kind": "question", "question": "Toplantı daveti mi?"}).json()
        self.assertEqual((r["kind"], r["category"], r["options"][0]["key"]), ("question", "Kişisel", "Evet"))
        r = c.post("/api/rules", json={**base, "name": "Banka 2", "category": "Banka", "question": "Banka"}).json()
        self.assertEqual((r["kind"], r["options"]), ("category", []))
        self.assertEqual(c.post("/api/rules", json={**base, "name": "X", "kind": "category", "question": "abc"}).status_code, 422)

        # Security mail is never archived; Oltalama always waits for approval.
        hesap = c.post("/api/rules", json={**base, "name": "H", "category": "Hesap", "question": "abc", "actions": ["archive"]})
        self.assertEqual(hesap.status_code, 422)
        rules = {x["name"]: x for x in c.get("/api/rules").json()}
        self.assertEqual(c.patch(f"/api/rules/{rules['Hesap bildirimleri']['id']}", json={"actions": ["label:Hesap", "archive"]}).status_code, 422)
        olta = rules["Oltalama şüphesi"]["id"]
        self.assertEqual(c.patch(f"/api/rules/{olta}", json={"mode": "apply"}).status_code, 422)
        self.assertEqual(c.patch(f"/api/rules/{olta}", json={"applyThreshold": 0.95}).status_code, 200)

    def test_task_run(self):
        config.update({"dryRun": False})
        t = {"query": "in:inbox", "question": "Bu e-posta bir sipariş şikâyeti mi?", "applyThreshold": 0.8,
             "options": [{"key": "Evet", "description": ""}, {"key": "Hayır", "description": ""}],
             "actions": ["label:Şikayet"], "mode": "apply", "dryRun": False}
        with mock.patch.object(engine, "start_task", lambda tid: engine._run_task(tid, engine.threading.Event())):
            tid = self.client.post("/api/tasks", json=t).json()["id"]
        task = self.client.get("/api/tasks").json()[0]
        self.assertEqual((task["id"], task["status"], task["processed"], task["passed"]), (tid, "done", 4, 1))
        self.assertIn("L:Şikayet", self.g.labels["m3"])
        self.assertEqual(len(self.client.get(f"/api/tasks/{tid}/scores").json()["scores"]), 4)

    def test_migration_from_v1(self):
        # A database made before versioning: v1 layout, old starter rules, two rules the user made, a task.
        with mock.patch.object(db, "DB_PATH", Path(self.tmp.name) / "v1.db"):
            with db.tx() as con:
                con.executescript((Path(__file__).parent / "schema_v1.sql").read_text(encoding="utf-8"))
                rows = [(n, c, q, t, a, m) for n, c, q, t, a, m in migrate.V1_STARTERS if n != "Faturaları ayır"]
                rows += [("Faturaları ayır", "Fatura", "Bu e-posta bir fatura veya ödeme bildirimi mi?", 0.70, ["label:Fatura"], "apply"),  # edited
                         ("Kurumsal müşteri", "Müşteri", "Kurumsal müşteriden mi?", 0.80, ["label:Kurumsal"], "approve")]       # own rule
                for n, c, q, t, a, m in rows:
                    con.execute("INSERT INTO rules(name, category, question, options, threshold, actions, mode, enabled, created_at) "
                                "VALUES(?, ?, ?, ?, ?, ?, ?, 1, ?)", (n, c, q, db.j([] if c else config.yes_no(q)), t, db.j(a), m, db.now()))
                con.execute("INSERT INTO tasks(name, query, question, options, threshold, actions, mode, dry_run, status, created_at) "
                            "VALUES('t', 'in:inbox', 'Soru?', '[]', 0.52, '[]', 'report', 0, 'done', ?)", (db.now(),))

            db.init()
            migrate.run()
            self.assertEqual(db.version(), db.SCHEMA_VERSION)
            rules = {r["name"]: r for r in self.client.get("/api/rules").json()}
            # Untouched v1 starters are gone; the edited Fatura rule stays and no second Fatura rule is added.
            self.assertFalse({"Müşteri talepleri", "Bültenleri arşivle", "Spam temizliği", "Acil iş e-postaları", "Ödenmemiş faturalar"} & set(rules))
            f = rules["Faturaları ayır"]
            self.assertEqual((f["applyThreshold"], f["ignoreThreshold"], f["dryRun"]), (0.70, None, True))
            self.assertNotIn("Faturalar", rules)
            # A rule whose category is gone becomes a disabled yes/no rule with its own question.
            k = rules["Kurumsal müşteri"]
            self.assertEqual((k["kind"], k["category"], k["enabled"], k["options"][0]["key"]), ("question", None, False, "Evet"))
            self.assertEqual((k["applyThreshold"], k["ignoreThreshold"]), (0.80, 0.50))
            new = {n for n, *_ in config.STARTER_RULES} - {"Faturalar"}
            self.assertTrue(new <= set(rules))
            o = rules["Oltalama şüphesi"]
            self.assertEqual((o["modeLocked"], o["applyThreshold"], o["ignoreThreshold"], o["dryRun"]), (True, 0.90, 0.50, True))
            self.assertTrue(all(r["dryRun"] for r in rules.values()))
            task = self.client.get("/api/tasks").json()[0]
            self.assertEqual((task["applyThreshold"], task["ignoreThreshold"]), (0.52, 0.47))  # kept below apply
            migrate.run()  # already current: nothing changes
            self.assertEqual(len(self.client.get("/api/rules").json()), len(rules))

    def test_thresholds_and_rule_dry_flag(self):
        c = self.client
        config.update({"dryRun": False})
        # A yes/no rule acting at ≥0.95: m3 scores 0.9 → approval; the others 0.1 ≤ 0.5 → only recorded.
        rid = c.post("/api/rules", json={"name": "Sipariş", "question": "Sipariş mi?", "applyThreshold": 0.95,
                                         "actions": ["star"], "mode": "apply", "dryRun": False}).json()["id"]
        engine.scan()
        decided = {r["email_id"]: r["status"] for r in db.rows(
            "SELECT d.email_id, a.status FROM decisions d LEFT JOIN actions a ON a.decision_id = d.id WHERE d.rule_id = ?", (rid,))}
        self.assertEqual(decided, {"m1": None, "m2": None, "m3": "pending", "m4": None})

        # Starter rules are dry: even with the global dry mode off they only suggest, also when approved.
        st = db.one("SELECT a.status FROM actions a JOIN decisions d ON d.id = a.decision_id WHERE d.source = 'Faturalar'")
        self.assertEqual(st["status"], "suggested")
        bulten = next(q for q in c.get("/api/queue").json() if q["source"] == "Bültenler")
        self.assertEqual(c.post(f"/api/queue/{bulten['id']}/approve", json={}).json()["status"], "suggested")
        self.assertEqual(self.g.labels["m1"], ["INBOX", "UNREAD"])
        self.assertEqual(self.g.labels["m2"], ["INBOX", "UNREAD"])

        # Switching one rule's dry flag off lets only that rule write.
        hesap = next(q for q in c.get("/api/queue").json() if q["source"] == "Hesap bildirimleri")
        rules = {r["name"]: r for r in c.get("/api/rules").json()}
        self.assertFalse(c.patch(f"/api/rules/{rules['Hesap bildirimleri']['id']}", json={"dryRun": False}).json()["dryRun"])
        self.assertEqual(c.post(f"/api/queue/{hesap['id']}/approve", json={}).json()["status"], "applied")
        self.assertIn("L:Hesap", self.g.labels["m4"])

        # Threshold validation: ignore must stay below apply, category rules have none.
        acil = rules["Acil / yanıt bekliyor"]
        self.assertEqual(c.patch(f"/api/rules/{acil['id']}", json={"ignoreThreshold": 0.9}).status_code, 422)
        self.assertEqual(c.patch(f"/api/rules/{acil['id']}", json={"ignoreThreshold": 0.3, "applyThreshold": 0.8}).json()["ignoreThreshold"], 0.3)
        r = c.patch(f"/api/rules/{rules['Faturalar']['id']}", json={"applyThreshold": 0.9, "ignoreThreshold": 0.4}).json()
        self.assertEqual((r["applyThreshold"], r["ignoreThreshold"]), (0.9, None))
        self.assertEqual(c.patch(f"/api/rules/{acil['id']}", json={"applyThreshold": 0.1}).status_code, 422)

    def test_models_come_from_tags_with_decision_models_marked(self):
        tags = {"running": True, "version": "0.40.11", "models": ["qwen3:8b", "tev1:4b", "d3:9b"], "decision": ["tev1:4b", "d3:9b"]}
        with mock.patch.object(classifier, "ollama_status", lambda url: tags):
            got = [(m["name"], m["kind"], m["installed"]) for m in self.client.get("/api/models").json()]
            self.assertEqual(got, [("d3:9b", "decision", True), ("tev1:4b", "decision", True), ("qwen3:8b", "chat", True)])
            config.update({"model": "tev1:1b"})  # selected but not installed: still listed, flagged
            self.assertEqual(self.client.get("/api/models").json()[0], {"name": "tev1:1b", "installed": False, "kind": "decision"})
            self.assertEqual(self.client.post("/api/settings/test-ollama", json={}).json()["decision"], ["tev1:4b", "d3:9b"])

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


TAGS = {"models": [
    {"name": "tev1:4b", "capabilities": ["decision"]},
    {"name": "d3:9b", "capabilities": ["decision", "vision"]},
    {"name": "qwen3:8b", "capabilities": ["completion", "tools"]},
]}
SETTINGS = {"ollamaUrl": "http://ollama.test", "model": "tev1:4b"}
YES_NO = config.yes_no("Acil mi?")
THREE = [{"key": "Banka", "description": "Hesap hareketi"}, {"key": "Fatura", "description": ""}, {"key": "Diğer", "description": ""}]


class ClassifierTest(unittest.TestCase):
    """The real request/response shapes of Ollama 0.40.11's /v1/systemone, against a fake server."""

    def setUp(self):
        self.requests: list[tuple[str, dict]] = []
        self.replies: list = []  # popped per non-tags request: a Response, an exception or a body dict
        self.sleeps: list[float] = []
        classifier._caps.clear()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/tags":
                return httpx.Response(200, json=TAGS)
            self.requests.append((request.url.path, json.loads(request.content)))
            reply = self.replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply if isinstance(reply, httpx.Response) else httpx.Response(200, json=reply)

        self.patches = [
            mock.patch.object(classifier, "_http", httpx.Client(transport=httpx.MockTransport(handler))),
            mock.patch.object(classifier, "_sleep", self.sleeps.append),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    def test_yes_no_is_one_noul_question(self):
        self.replies = [{"model": "tev1:4b", "answers": {"q": {"type": "noul", "noul": 0.99}}}]
        r = classifier.classify(SETTINGS, "metin", "Acil mi?", YES_NO)
        self.assertAlmostEqual(r.scores["Evet"], 0.99)
        self.assertAlmostEqual(r.scores["Hayır"], 0.01)
        path, body = self.requests[0]
        self.assertEqual(path, "/v1/systemone")
        self.assertEqual(body["questions"]["q"]["type"], "noul")
        self.assertEqual(set(body["questions"]["q"]["criteria"]), {"true", "false"})

    def test_list_is_one_choice_question_scored_by_probabilities(self):
        self.replies = [{"answers": {"q": {"type": "choice", "choice": "Banka", "confidence": 0.83,
                                           "probabilities": {"Banka": 0.9, "Fatura": 0.08, "Diğer": 0.02}}}}]
        r = classifier.classify(SETTINGS, "metin", "Hangi kategori?", THREE)
        self.assertEqual(r.top, ("Banka", 0.9))
        q = self.requests[0][1]["questions"]["q"]
        self.assertEqual(len(self.requests), 1)
        self.assertEqual((q["type"], q["criteria"]["Banka"], q["criteria"]["Fatura"]), ("choice", "Hesap hareketi", "Fatura"))

    def test_capability_not_name_picks_the_endpoint(self):
        self.replies = [{"message": {"content": json.dumps({"scores": {"Evet": 0.2, "Hayır": 0.8}})}}]
        classifier.classify({**SETTINGS, "model": "qwen3:8b"}, "metin", "Acil mi?", YES_NO)
        self.assertEqual(self.requests[0][0], "/api/chat")
        self.assertTrue(classifier.is_decision_model(SETTINGS["ollamaUrl"], "d3:9b"))

    def test_unexpected_answer_is_a_model_error(self):
        for answer in ({"type": "noul", "noul": True}, {"type": "noul"}, None):
            self.replies = [{"answers": {"q": answer}}]
            with self.assertRaises(classifier.ModelError):
                classifier.classify(SETTINGS, "metin", "Acil mi?", YES_NO)
        self.replies = [{"answers": {"q": {"type": "choice", "probabilities": {"Başka": 1.0}}}}]
        with self.assertRaises(classifier.ModelError):
            classifier.classify(SETTINGS, "metin", "Hangi?", THREE)

    def test_retries_500_and_dropped_connection_twice(self):
        ok = {"answers": {"q": {"type": "noul", "noul": 0.7}}}
        self.replies = [httpx.Response(500, text="boom"), httpx.RemoteProtocolError("Server disconnected"), ok]
        self.assertAlmostEqual(classifier.classify(SETTINGS, "m", "Acil mi?", YES_NO).scores["Evet"], 0.7)
        self.assertEqual(self.sleeps, [2, 5])

        self.sleeps.clear()
        self.replies = [httpx.Response(500, text="boom")] * 3
        with self.assertRaises(classifier.ModelError):
            classifier.classify(SETTINGS, "m", "Acil mi?", YES_NO)
        self.assertEqual(self.sleeps, [2, 5])

    def test_4xx_is_not_retried(self):
        self.replies = [httpx.Response(404, json={"error": "model 'tev1:4b' not found"})]
        with self.assertRaises(classifier.ModelError):
            classifier.classify(SETTINGS, "m", "Acil mi?", YES_NO)
        self.assertEqual((len(self.requests), self.sleeps), (1, []))

    def test_warm_up_loads_the_selected_model_once(self):
        self.replies = [{"answers": {"q": {"type": "noul", "noul": 0.5}}}, {"done": True, "done_reason": "load"}]
        classifier.warm_up(SETTINGS)
        classifier.warm_up({**SETTINGS, "model": "qwen3:8b"})
        self.assertEqual([(p, b["model"]) for p, b in self.requests], [("/v1/systemone", "tev1:4b"), ("/api/generate", "qwen3:8b")])

    def test_warm_up_failure_is_only_logged(self):
        self.replies = [httpx.ConnectError("refused")] * 3
        with self.assertLogs("mailkarar", "WARNING"):
            classifier.warm_up(SETTINGS)


if __name__ == "__main__":
    unittest.main()
