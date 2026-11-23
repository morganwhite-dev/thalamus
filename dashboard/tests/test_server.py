import json, sys, tempfile, threading, unittest, urllib.request, urllib.error
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "engine"))
import server, brain, command  # noqa
import importlib.util
_spec = importlib.util.spec_from_file_location("router_fakes", HERE.parent / "router" / "tests" / "test_router.py")
_fakes = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_fakes)
from router.core import Router, load_config as router_config  # noqa


class FakeModels:
    """The chat agent's two model calls (command/agent.py Models). Queue outputs per step; an Exception is raised."""

    def __init__(self):
        self.free_out, self.haiku_out, self.calls = [], [], []

    def _next(self, q, step, prompt):
        self.calls.append((step, prompt))
        v = q.pop(0) if q else '{"reply": "Hi.", "action": null}'
        if callable(v):
            v = v(prompt)
        if isinstance(v, Exception):
            raise v
        return (v if isinstance(v, str) else json.dumps(v)), "fake-" + step

    def free(self, prompt):
        return self._next(self.free_out, "free", prompt)

    def haiku(self, prompt):
        return self._next(self.haiku_out, "haiku", prompt)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        now = datetime.now().astimezone()
        tasks = [
            {"id": "AAAAAAAA-1", "title": "Read Chapter 5", "list": "Network Security", "dueDate": (now - timedelta(days=1)).isoformat(), "progressPercent": 0},
            {"id": "BBBBBBBB-2", "title": "Apply to 10", "list": "Internships", "dueDate": (now + timedelta(days=2)).isoformat(), "progressPercent": 0},
        ]
        (self.tmp / "snap.json").write_text(json.dumps({"schemaVersion": 1, "generatedAt": now.isoformat(), "tasks": tasks}))
        cfg = json.loads((HERE.parent / "engine" / "config.json").read_text())
        cfg.update(snapshotPath=str(self.tmp / "snap.json"), overridesPath=str(self.tmp / "ov.json"),
                   recommendationPath=str(self.tmp / "rec.json"), errorPath=str(self.tmp / "err.json"),
                   commitmentsPath=str(self.tmp / "none.json"))
        (self.tmp / "cfg.json").write_text(json.dumps(cfg))
        self.cfg = str(self.tmp / "cfg.json")
        server.BLOCKS_PATHS.update(state=self.tmp / "blocks.json", history=self.tmp / "history.jsonl")
        server.DONE_PATHS["p"] = {"actions_dir": self.tmp / "drop" / "actions", "pending": self.tmp / "actions.json", "results": self.tmp / "actions-result.json"}
        server.PLAY_PATH["p"] = self.tmp / "play.json"
        self.client = _fakes.FakeClient()
        self.models = FakeModels()
        server.AGENT.update(a=None, models=self.models)

        def factory(engine_fn):
            rcfg = router_config(); rcfg["workspace"] = str(self.tmp / "ws")
            return Router(cfg=rcfg, client=self.client, state_dir=self.tmp / "rstate", priority_engine=engine_fn)
        server.RUNNER["r"] = command.CommandRunner(self.tmp / "cstate", router_factory=factory,
                                                   load_config=lambda: brain.load_config(), sync=True)
        self._orig = brain.load_config
        brain.load_config = lambda path=None: json.loads(Path(path or self.cfg).read_text())
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(0))
        self.port = self.httpd.server_address[1]
        self.httpd.RequestHandlerClass = server.make_handler(self.port)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        brain.load_config = self._orig
        server.BLOCKS_PATHS.update(state=None, history=None)
        server.RUNNER["r"] = None
        server.DONE_PATHS["p"] = None
        server.PLAY_PATH["p"] = None
        server.AGENT.update(a=None, models=None)
        self.httpd.shutdown()

    def req(self, path, body=None, headers=None):
        h = {"Content-Type": "application/json"}; h.update(headers or {})
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=json.dumps(body).encode() if body is not None else None, headers=h)
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())


class T(Base):
    def test_state(self):
        c, j = self.req("/api/state")
        self.assertEqual(c, 200); self.assertEqual(j["current"]["title"], "Read Chapter 5"); self.assertIn("serverTime", j)

    def test_habit_through_the_api_and_capture(self):
        H = {"X-Brain": "1"}
        snap = json.loads((self.tmp / "snap.json").read_text()); snap["lists"] = ["Network Security", "Internships", "Play"]
        (self.tmp / "snap.json").write_text(json.dumps(snap))
        c, j = self.req("/api/command", {"text": "add tryhackme to playground. my goal is to do one practice lab a day."}, H)
        cap = j["capture"]; self.assertEqual((cap["list"], cap["habit"]["label"]), ("Play", "daily"))
        c, j = self.req("/api/play", {"action": "addhabit", "title": cap["title"], "notes": cap["notes"], "days": cap["habit"]["days"], "nudgeAt": cap["habit"]["nudgeAt"], "cluster": "play"}, H)
        self.assertEqual(c, 200); h = j["play"]["habits"][0]
        self.assertEqual((h["cadence"], h["doneToday"], h["cluster"]), ("daily", False, "play"))
        self.assertEqual(j["created"], h["id"])
        c, j = self.req("/api/play", {"action": "habitdone", "id": h["id"]}, H)
        self.assertTrue(j["play"]["habits"][0]["doneToday"])
        c, j = self.req("/api/play", {"action": "addhabit", "title": "x", "cluster": "nope"}, H); self.assertEqual(c, 400)
        c, j = self.req("/api/play", {"action": "drophabit", "id": h["id"]}, H); self.assertEqual(j["play"]["habits"], [])

    def test_reminder_created_id_and_undo(self):
        H = {"X-Brain": "1"}
        at = (datetime.now().astimezone() + timedelta(hours=2)).isoformat()
        c, j = self.req("/api/play", {"action": "addreminder", "text": "call mom", "at": at}, H)
        self.assertEqual(c, 200); rid = j["created"]; self.assertEqual(j["play"]["reminders"][0]["id"], rid)
        c, j = self.req("/api/play", {"action": "dropreminder", "id": rid}, H)
        self.assertEqual(j["play"]["reminders"], []); self.assertNotIn("created", j)
        c, j = self.req("/api/play", {"action": "addreminder", "text": "x", "at": "soon"}, H); self.assertEqual(c, 400)

    def test_pin_then_skip(self):
        c, j = self.req("/api/action", {"action": "pin", "taskId": "BBBBBBBB-2"}, {"X-Brain": "1"})
        self.assertEqual(j["current"]["title"], "Apply to 10"); self.assertEqual(j["current"]["band"], "pinned")
        c, j = self.req("/api/action", {"action": "unpin", "taskId": "BBBBBBBB-2"}, {"X-Brain": "1"})
        self.assertEqual(j["current"]["title"], "Read Chapter 5")
        c, j = self.req("/api/action", {"action": "skip", "taskId": "AAAAAAAA-1"}, {"X-Brain": "1"})
        self.assertEqual(j["current"]["title"], "Read Chapter 5")  # missed hard deadline stays (engine rule)
        c, j = self.req("/api/action", {"action": "skip", "taskId": "BBBBBBBB-2"}, {"X-Brain": "1"})
        self.assertEqual(j["queue"], [])

    def test_snooze_and_lowenergy(self):
        c, j = self.req("/api/action", {"action": "snooze", "taskId": "BBBBBBBB-2", "hours": 3}, {"X-Brain": "1"})
        self.assertEqual(c, 200); self.assertEqual(j["activeOverrides"]["snoozes"], 1)
        c, j = self.req("/api/action", {"action": "snooze", "taskId": "BBBBBBBB-2", "until": "tomorrow"}, {"X-Brain": "1"})
        self.assertEqual(c, 200)
        c, j = self.req("/api/action", {"action": "lowenergy", "state": "on"}, {"X-Brain": "1"})
        self.assertTrue(j["mode"]["lowEnergy"])

    def test_rejects(self):
        self.assertEqual(self.req("/api/action", {"action": "pin", "taskId": "BBBBBBBB-2"})[0], 403)  # no header
        self.assertEqual(self.req("/api/action", {"action": "pin", "taskId": "BBBBBBBB-2"}, {"X-Brain": "1", "Host": "evil.com"})[0], 403)
        self.assertEqual(self.req("/api/action", {"action": "rm"}, {"X-Brain": "1"})[0], 400)
        self.assertEqual(self.req("/api/action", {"action": "pin", "taskId": "ZZZZZZZZZZ"}, {"X-Brain": "1"})[0], 400)
        self.assertEqual(self.req("/api/action", {"action": "snooze", "taskId": "BBBBBBBB-2", "hours": 9999}, {"X-Brain": "1"})[0], 400)

    def test_bad_snapshot_keeps_last_good(self):
        self.req("/api/state")
        (self.tmp / "snap.json").write_text("{broken")
        c, j = self.req("/api/state")
        self.assertEqual(c, 200); self.assertTrue(j["error"]); self.assertEqual(j["current"]["title"], "Read Chapter 5")

    def test_presence(self):
        server.PRESENCE_PATH = self.tmp / "presence.json"
        self.assertEqual(self.req("/api/presence", {})[0], 403)  # no header
        self.assertEqual(self.req("/api/presence", {}, {"X-Brain": "1", "Host": "evil.com"})[0], 403)
        self.assertFalse((self.tmp / "presence.json").exists())
        self.assertEqual(self.req("/api/presence", {}, {"X-Brain": "1"})[0], 200)
        seen = datetime.fromisoformat(json.loads((self.tmp / "presence.json").read_text())["lastSeen"])
        self.assertLess((datetime.now().astimezone() - seen).total_seconds(), 5)

    def block(self, action, **kw):
        return self.req("/api/block", dict(action=action, **kw), {"X-Brain": "1"})

    def test_block_cycle(self):
        c, j = self.req("/api/state")
        self.assertEqual(j["blocks"]["phase"], "idle"); self.assertEqual(j["blocks"]["next"]["title"], "Read Chapter 5")
        c, j = self.block("start_work")
        self.assertEqual((c, j["blocks"]["phase"]), (200, "starting"))
        c, j = self.block("begin_now")
        self.assertEqual((c, j["blocks"]["phase"]), (200, "work"))
        c, j = self.block("take_break")
        self.assertEqual(j["blocks"]["phase"], "break"); self.assertIsNone(j["blocks"]["block"]["suggestion"])
        c, j = self.block("end_break")
        self.assertEqual(j["blocks"]["phase"], "checkin")
        c, j = self.block("checkin", answer="yes")
        self.assertEqual(j["blocks"]["phase"], "idle"); self.assertEqual(j["blocks"]["lastCheckin"]["answer"], "yes")
        types = [json.loads(x)["type"] for x in (self.tmp / "history.jsonl").read_text().splitlines()]
        self.assertEqual(types, ["work_countdown", "work_start", "work_end", "break_start", "break_over", "checkin"])

    def test_play_park_leftoff_and_state(self):
        H = {"X-Brain": "1"}
        c, j = self.req("/api/play", {"action": "park", "text": "try scapy"}, H)
        self.assertEqual(c, 200); self.assertEqual(j["play"]["projects"][0]["title"], "try scapy")
        self.assertEqual(j["play"]["projects"][0]["state"], "idea"); self.assertEqual(j["play"]["parking"], [])
        c, j = self.req("/api/play", {"action": "dropproject", "id": j["play"]["projects"][0]["id"]}, H)
        self.assertEqual(j["play"]["projects"], [])
        c, j = self.req("/api/play", {"action": "park", "text": ""}, H)
        self.assertEqual(c, 400)
        c, j = self.req("/api/play", {"action": "park", "text": "x"})
        self.assertEqual(c, 403)                                   # no X-Brain header
        self.assertIsNone(self.req("/api/state")[1]["play"]["offer"])   # a late missed deadline: no offers

    def test_left_off_map_covers_focus_projects_and_auto_lines(self):
        import subprocess
        repo = self.tmp / "repo"; repo.mkdir()
        run = lambda *a: subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)
        run("init", "-q"); (repo / "a.py").write_text("x"); run("add", "."); run("commit", "-qm", "Phase 4: add parser")
        snap = json.loads((self.tmp / "snap.json").read_text())
        snap["tasks"].append({"id": "SEC-1", "title": "Traffic analyzer", "list": "Security Projects", "notes": f"path: {repo}"})
        (self.tmp / "snap.json").write_text(json.dumps(snap))
        lo = self.req("/api/state")[1]["leftOff"]
        self.assertEqual(lo["SEC-1"], {"text": "On Phase 4, building parser · just now", "auto": True})
        self.req("/api/play", {"action": "leftoff", "taskId": "SEC-1", "text": "stuck on the pcap parser"}, {"X-Brain": "1"})
        self.assertEqual(self.req("/api/state")[1]["leftOff"]["SEC-1"], {"text": "stuck on the pcap parser", "auto": False})
        self.assertNotIn("AAAAAAAA-1", lo)                          # school tasks never get a project line

    def test_block_task_done_ends_block(self):
        self.block("start_work", countdown=0)
        snap = json.loads((self.tmp / "snap.json").read_text())
        snap["tasks"] = [t for t in snap["tasks"] if t["id"] != "AAAAAAAA-1"]
        (self.tmp / "snap.json").write_text(json.dumps(snap))
        c, j = self.req("/api/state")
        self.assertTrue(j["blocks"]["over"]); self.assertEqual(j["blocks"]["block"]["overReason"], "task-done")

    def test_block_rejects(self):
        self.assertEqual(self.req("/api/block", {"action": "start_work"})[0], 403)
        self.assertEqual(self.req("/api/block", {"action": "start_work"}, {"X-Brain": "1", "Host": "evil.com"})[0], 403)
        self.assertEqual(self.block("bogus")[0], 400)
        self.assertEqual(self.block("take_break")[0], 400)           # nothing running
        self.assertEqual(self.block("checkin", answer="yes")[0], 400)
        self.assertFalse((self.tmp / "blocks.json").exists())        # illegal actions write nothing

    def test_corrupt_block_state_resets_with_banner(self):
        (self.tmp / "blocks.json").write_text("garbage")
        c, j = self.req("/api/state")
        self.assertEqual(c, 200); self.assertEqual(j["blocks"]["phase"], "idle"); self.assertIn("reset", j["blocks"]["error"])
        self.assertTrue((self.tmp / "blocks.json.bad").exists())

    def test_command_engine_answer(self):
        c, j = self.req("/api/command", {"text": "what should I do now"}, {"X-Brain": "1"})
        self.assertEqual(c, 202); self.assertEqual(j["job"]["status"], "done")
        self.assertIn("Read Chapter 5", j["job"]["answer"]); self.assertEqual(self.client.runs, [])
        c, g = self.req("/api/command/" + j["job"]["id"])
        self.assertEqual((c, g["job"]["id"]), (200, j["job"]["id"]))
        c, s = self.req("/api/state")
        self.assertEqual(s["command"]["jobs"][0]["id"], j["job"]["id"])
        self.assertEqual(s["missionLog"][-1]["kind"], "now")
        self.assertIn("engine · no model", s["missionLog"][-2]["text"])

    def test_command_tagged_routed(self):
        c, j = self.req("/api/command", {"text": "@haiku say hi to Apply to 10 please"}, {"X-Brain": "1"})
        self.assertEqual(c, 202); self.assertIn("haiku · claude-haiku-5-5", j["job"]["routing"])
        self.assertEqual((j["job"]["taskMatch"], j["job"]["taskId"]), ("named in the text", "BBBBBBBB-2"))

    def test_command_security(self):
        body = {"text": "@haiku hi"}
        self.assertEqual(self.req("/api/command", body)[0], 403)                                   # no X-Brain
        self.assertEqual(self.req("/api/command", body, {"X-Brain": "1", "Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.req("/api/command", body, {"X-Brain": "1", "Host": "evil.example:80"})[0], 403)
        self.assertEqual(self.req("/api/command/x", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.req("/api/command", {"text": "x" * 5000}, {"X-Brain": "1"})[0], 400)
        self.assertEqual(self.req("/api/command", {"text": "x" * 20000}, {"X-Brain": "1"})[0], 413)
        self.assertEqual(self.req("/api/command", body, {"X-Brain": "1", "Origin": f"http://127.0.0.1:{self.port}"})[0], 202)
        self.assertEqual(self.client.runs and self.client.runs[0][0], "claude-code/claude-haiku-5-5")

    def test_command_busy(self):
        r = server.RUNNER["r"]; r._save_jobs([{"id": "x", "status": "running", "input": "slow", "conversation": "c"}])
        c, j = self.req("/api/command", {"text": "@haiku hi"}, {"X-Brain": "1"})
        self.assertEqual(c, 409); self.assertIn("One command at a time", j["error"])

    def test_refuses_non_local_bind(self):
        old = sys.argv
        sys.argv = ["server.py", "--host", "0.0.0.0", "--port", "1"]
        try:
            with self.assertRaises(SystemExit) as cm:
                server.main()
            self.assertIn("non-local", str(cm.exception))
        finally:
            sys.argv = old

    def test_page(self):
        r = urllib.request.urlopen(f"http://127.0.0.1:{self.port}/")
        self.assertIn(b"PRIORITY BRAIN", r.read())


if __name__ == "__main__":
    unittest.main()
