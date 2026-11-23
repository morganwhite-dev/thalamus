import json, sqlite3, sys, tempfile, unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import academy  # noqa: E402

CUR = {"tiers": [{"id": "tier-1", "modules": [{"id": "t1-shell", "title": "Shell navigation"}, {"id": "t1-perm", "title": "Permissions"}]},
                 {"id": "tier-2", "modules": [{"id": "t2-net", "title": "Network basics"}]}]}
NOW = datetime(2026, 11, 13, 8, 48, tzinfo=timezone.utc)


def make(rows=(), attempts=()):
    d = Path(tempfile.mkdtemp())
    (d / "content").mkdir(); (d / "data").mkdir()
    (d / "content" / "curriculum.json").write_text(json.dumps(CUR))
    db = sqlite3.connect(d / "data" / "academy.sqlite3")
    db.execute("create table progress (item_id TEXT PRIMARY KEY, status TEXT, note TEXT DEFAULT '', updated_at TEXT)")
    db.execute("create table attempts (id TEXT, item_id TEXT, score INT, total INT, answers TEXT, created_at TEXT)")
    db.executemany("insert into progress(item_id,status,updated_at) values(?,?,?)", rows)
    db.executemany("insert into attempts values(?,?,?,?,'[]',?)", attempts)
    db.commit(); db.close()
    return d


class AcademyTest(unittest.TestCase):
    def test_line_with_quiz_and_age(self):
        d = make([("t1-shell", "complete", "2026-11-13 06:48:00"), ("t1-perm", "in-progress", "2026-11-13 06:00:00")],
                 [("a", "t1-shell", 7, 10, "2026-11-13 06:48:00")])
        out = academy.compute([{"id": "x", "title": "Cyber Academy Tier 1 / Bandit"}], NOW, d)
        self.assertEqual(out["x"], "Tier 1: 1 of 2 modules done, permissions in progress, last quiz 7/10 · 2 h ago")

    def test_not_started_names_next(self):
        d = make()
        out = academy.compute([{"id": "x", "title": "Cyber Academy Tier 2 / lab"}], NOW, d)
        self.assertEqual(out["x"], "Tier 2: 0 of 1 modules done, next: network basics")

    def test_other_tasks_ignored_and_missing_data_quiet(self):
        d = make()
        self.assertEqual(academy.compute([{"id": "y", "title": "B1 LLM red team harness"}], NOW, d), {})
        self.assertEqual(academy.compute([{"id": "x", "title": "Cyber Academy Tier 1"}], NOW, Path("/nonexistent")), {})

    def test_never_writes(self):
        d = make([("t1-shell", "complete", "2026-11-13 06:48:00")])
        before = (d / "data" / "academy.sqlite3").read_bytes()
        academy.compute([{"id": "x", "title": "Cyber Academy Tier 1"}], NOW, d)
        self.assertEqual(before, (d / "data" / "academy.sqlite3").read_bytes())


if __name__ == "__main__":
    unittest.main()
