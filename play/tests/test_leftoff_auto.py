import json, subprocess, sys, tempfile, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
R = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(R / "play"), str(R / "engine")]
import leftoff_auto as A, play as P
from brain_engine import category_for

CFG = json.loads((R / "engine" / "config.json").read_text())
NOW = datetime.now(timezone.utc)
REC = {"dayLoad": {"level": "light", "freeMinutes": 600, "plannedMinutes": 60}, "current": {"band": "undated", "dueDate": None}, "queue": []}


def git(d, *a):
    subprocess.run(["git", "-C", str(d), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)


class AutoLeftOff(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.d = Path(self.tmp.name)
        self.repo = self.d / "proj"; self.repo.mkdir()
        git(self.repo, "init", "-q"); (self.repo / "a.py").write_text("x")
        git(self.repo, "add", "."); git(self.repo, "commit", "-qm", "add parser")
        self.hist = self.d / "history.jsonl"
        A._cache.clear()

    def tearDown(self): self.tmp.cleanup()

    def test_git_line_clean_then_dirty(self):
        self.assertEqual(A.git_line(self.repo, NOW), 'Last: "add parser" just now, all committed')
        (self.repo / "a.py").write_text("y"); (self.repo / "b.py").write_text("z")
        self.assertIn("2 files uncommitted", A.git_line(self.repo, NOW))
        self.assertIn("2 days ago", A.git_line(self.repo, NOW + timedelta(days=2, hours=1)))

    def test_bad_folders_give_none(self):
        self.assertIsNone(A.git_line(self.d / "missing", NOW))
        plain = self.d / "plain"; plain.mkdir()
        self.assertIsNone(A.git_line(plain, NOW))
        self.assertIsNone(A.git_line(None, NOW))

    def test_path_parsing(self):
        self.assertEqual(A.parse_path("Status: In progress\npath: /x/y\n"), Path("/x/y"))
        self.assertEqual(A.parse_path("path: ~/code"), Path.home() / "code")
        self.assertIsNone(A.parse_path("no folder here"))

    def test_history_fallback(self):
        at = (NOW - timedelta(days=3)).isoformat()
        self.hist.write_text(json.dumps({"type": "work_start", "title": "Zelda", "at": at}) + "\nnot json\n")
        self.assertEqual(A.last_worked("Zelda", self.hist, NOW), "Last worked 3 days ago")
        self.assertIsNone(A.last_worked("Other", self.hist, NOW))
        self.assertIsNone(A.last_worked("Zelda", self.d / "none.jsonl", NOW))

    def test_git_beats_history_and_typed_beats_both(self):
        t = {"id": "n", "title": "Traffic analyzer", "list": "Side Projects", "notes": f"path: {self.repo}"}
        self.hist.write_text(json.dumps({"type": "work_start", "title": "Traffic analyzer", "at": NOW.isoformat()}) + "\n")
        autos = A.compute([t], self.hist, NOW)
        self.assertIn("Building parser", autos["n"])
        v = P.view(P.empty(), [t], CFG, category_for, None, autos)
        self.assertTrue(v["items"][0]["leftOffAuto"])
        st = P.apply(P.empty(), "leftoff", NOW, taskId="n", text="at the pcap parser")
        v2 = P.view(st, [t], CFG, category_for, None, autos)
        self.assertEqual((v2["items"][0]["leftOff"], v2["items"][0]["leftOffAuto"]), ("at the pcap parser", False))
        o = P.offer(REC, [t], P.empty(), CFG, category_for, "idle", NOW, autos=autos)
        self.assertEqual(o["taskId"], "n"); self.assertTrue(o["leftOffAuto"]); self.assertIn("Building parser", o["leftOff"])

    def test_cache_skips_second_git_run(self):
        t = {"id": "n", "title": "p", "notes": f"path: {self.repo}"}
        clock = [0.0]
        A.compute([t], self.hist, NOW, clock=lambda: clock[0])
        (self.repo / "c.py").write_text("q")
        self.assertNotIn("unsaved", A.compute([t], self.hist, NOW, clock=lambda: clock[0])["n"])   # cached
        clock[0] = A.CACHE_SECONDS + 1
        self.assertIn("unsaved work", A.compute([t], self.hist, NOW, clock=lambda: clock[0])["n"])


if __name__ == "__main__":
    unittest.main()
