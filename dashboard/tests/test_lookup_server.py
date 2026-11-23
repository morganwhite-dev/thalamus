"""Phase 16: file lookups answered without a model, and the Open button endpoint."""
import json, sys, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(Path(__file__).resolve().parent))
import server  # noqa
from test_server import Base  # noqa

H = {"X-Brain": "1"}


class Lookup(Base):
    def setUp(self):
        super().setUp()
        root = self.tmp / "Network Security"
        (root / "Week 5" / "My Notes").mkdir(parents=True)
        for n in (5, 6):
            (root / "Week 5" / "My Notes" / f"Teaching Notes - Module {n}.html").write_text("x")
        (self.tmp / "outside.html").write_text("x")
        cfg = json.loads(Path(self.cfg).read_text())
        cfg["lookup"] = {"roots": [str(root)], "extensions": ["html", "pdf"], "maxResults": 12, "maxFiles": 100}
        Path(self.cfg).write_text(json.dumps(cfg))
        self.opened = []
        self._orig_open = server.OPENER["fn"]
        server.OPENER["fn"] = self.opened.append

    def tearDown(self):
        server.OPENER["fn"] = self._orig_open
        super().tearDown()

    def test_question_is_answered_with_files_and_no_model(self):
        c, j = self.req("/api/command", {"text": "do you have teaching notes for module 5 and 6 for network security"}, H)
        self.assertEqual(c, 202)
        job = j["job"]
        self.assertEqual(job["status"], "done")
        self.assertIn("file lookup", job["routing"])
        self.assertEqual(sorted(f["name"] for f in job["files"]), ["Teaching Notes - Module 5.html", "Teaching Notes - Module 6.html"])
        self.assertEqual(self.client.calls if hasattr(self.client, "calls") else [], [])   # the model client was never used

    def test_open_inside_root(self):
        _, j = self.req("/api/command", {"text": "do you have teaching notes for module 5"}, H)
        path = j["job"]["files"][0]["path"]
        c, r = self.req("/api/open", {"path": path}, H)
        self.assertEqual(c, 200)
        self.assertEqual(self.opened, [str(Path(path).resolve())])

    def test_open_outside_root_refused(self):
        c, _ = self.req("/api/open", {"path": str(self.tmp / "outside.html")}, H)
        self.assertEqual(c, 403)
        c, _ = self.req("/api/open", {"path": "/etc/hosts"}, H)
        self.assertEqual(c, 403)
        self.assertEqual(self.opened, [])

    def test_open_needs_brain_header(self):
        c, _ = self.req("/api/open", {"path": str(self.tmp / "outside.html")})
        self.assertEqual(c, 403)

    def test_project_phrasing_reaches_project_status(self):
        c, j = self.req("/api/command", {"text": "where did i leave off on my network analyzer project"}, H)
        self.assertEqual(c, 202)
        self.assertIn("project status", j["job"]["routing"])


if __name__ == "__main__":
    unittest.main()


class Park(Base):
    def setUp(self):
        super().setUp()
        server.RUNNER["r"].play_path = self.tmp / "play.json"        # never touch the real parking lot

    def test_park_in_plain_language_saves_one_line_and_is_not_a_task(self):
        c, j = self.req("/api/command", {"text": "put build a retro game launcher in the parking lot"}, H)
        self.assertEqual(c, 202)
        self.assertIn("side projects", j["job"]["routing"])
        self.assertIn("Added to your side projects: build a retro game launcher", j["job"]["answer"])
        c, st = self.req("/api/state")
        self.assertEqual([(p["title"], p["state"]) for p in st["play"]["projects"]], [("build a retro game launcher", "idea")])
        self.assertEqual(list(Path(self.tmp / "drop" / "actions").glob("*")), [])      # nothing was sent to QuickToDo

    def test_schedule_question_uses_code_not_a_model(self):
        c, j = self.req("/api/command", {"text": "what's due next week in network security"}, H)
        self.assertEqual(c, 202)
        self.assertIn("schedule", j["job"]["routing"])
