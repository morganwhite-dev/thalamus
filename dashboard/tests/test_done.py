"""Phase 10: Done / Undo requests from the dashboard to QuickToDo (dashboard/done_actions.py + endpoints)."""
import json, sys, unittest
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(Path(__file__).resolve().parent))
import done_actions as da  # noqa
from test_server import Base  # noqa


def fake_quicktodo(paths, outcome="done", when=None):
    """Stands in for BrainActions.swift: answers every request file with a result."""
    out = da._read(paths["results"], {"version": 1, "results": []})
    for f in sorted(Path(paths["actions_dir"]).glob("*" + da.SUFFIX)):
        req = json.loads(f.read_text())
        if any(r["id"] == req["id"] for r in out["results"]):
            continue
        out["results"].append({"id": req["id"], "action": req["action"], "outcome": outcome if req["action"] == "complete" else "reopened",
                               "taskId": req["taskId"], "title": req["title"], "detail": "",
                               "processedAt": (when or datetime.now().astimezone()).isoformat()})
    Path(paths["results"]).write_text(json.dumps(out))


class Endpoints(Base):
    def paths(self):
        from server import DONE_PATHS
        return DONE_PATHS["p"]

    def test_done_writes_one_request_file_and_shows_pending(self):
        c, j = self.req("/api/done", {"taskId": "AAAAAAAA-1"}, {"X-Brain": "1"})
        self.assertEqual(c, 200)
        files = list(Path(self.paths()["actions_dir"]).glob("*" + da.SUFFIX))
        self.assertEqual(len(files), 1)
        req = json.loads(files[0].read_text())
        self.assertEqual((req["version"], req["action"], req["taskId"], req["title"]), (1, "complete", "AAAAAAAA-1", "Read Chapter 5"))
        self.assertEqual([p["taskId"] for p in j["actions"]["pending"]], ["AAAAAAAA-1"])

    def test_second_done_on_same_task_is_refused(self):
        self.req("/api/done", {"taskId": "AAAAAAAA-1"}, {"X-Brain": "1"})
        c, j = self.req("/api/done", {"taskId": "AAAAAAAA-1"}, {"X-Brain": "1"})
        self.assertEqual(c, 409)
        self.assertEqual(len(list(Path(self.paths()["actions_dir"]).glob("*" + da.SUFFIX))), 1)

    def test_unknown_task_and_missing_header_refused(self):
        c, _ = self.req("/api/done", {"taskId": "ZZZZZZZZ-9"}, {"X-Brain": "1"})
        self.assertEqual(c, 400)
        c, _ = self.req("/api/done", {"taskId": "AAAAAAAA-1"})
        self.assertEqual(c, 403)
        c, _ = self.req("/api/done", {"taskId": "AAAAAAAA-1"}, {"X-Brain": "1", "Host": "evil.example:80"})
        self.assertEqual(c, 403)
        self.assertFalse(Path(self.paths()["actions_dir"]).exists() and any(Path(self.paths()["actions_dir"]).iterdir()))

    def test_result_moves_to_recent_cleans_file_and_allows_undo(self):
        self.req("/api/done", {"taskId": "AAAAAAAA-1"}, {"X-Brain": "1"})
        fake_quicktodo(self.paths())
        c, j = self.req("/api/state")
        self.assertEqual(j["actions"]["pending"], [])
        r = j["actions"]["recent"][0]
        self.assertEqual((r["outcome"], r["text"], r["undoable"]), ("done", "Done in QuickToDo", True))
        self.assertEqual(list(Path(self.paths()["actions_dir"]).glob("*" + da.SUFFIX)), [], "processed file deleted")
        c, j = self.req("/api/undo-done", {"actionId": r["id"]}, {"X-Brain": "1"})
        self.assertEqual(c, 200)
        req = json.loads(next(Path(self.paths()["actions_dir"]).glob("*" + da.SUFFIX)).read_text())
        self.assertEqual((req["action"], req["undoes"]), ("reopen", r["id"]))
        c, j = self.req("/api/undo-done", {"actionId": r["id"]}, {"X-Brain": "1"})
        self.assertEqual(c, 400, "can't undo twice")

    def test_done_today_counts_confirmed_dones_and_undo_takes_one_back(self):
        c, j = self.req("/api/state")
        self.assertEqual(j["actions"]["doneToday"], 0)
        self.req("/api/done", {"taskId": "AAAAAAAA-1"}, {"X-Brain": "1"})
        c, j = self.req("/api/state")
        self.assertEqual(j["actions"]["doneToday"], 0)  # not until QuickToDo confirms
        fake_quicktodo(self.paths())
        c, j = self.req("/api/state")
        self.assertEqual(j["actions"]["doneToday"], 1)
        self.req("/api/undo-done", {"actionId": j["actions"]["recent"][0]["id"]}, {"X-Brain": "1"})
        fake_quicktodo(self.paths())
        c, j = self.req("/api/state")
        self.assertEqual(j["actions"]["doneToday"], 0)

    def test_done_today_resets_on_a_new_day(self):
        st = {"pending": [], "recent": [], "doneDay": {"date": "2000-01-01", "n": 4}}
        self.assertEqual(da.view(st, datetime.now().astimezone())["doneToday"], 0)

    def test_blocked_outcome_is_reported_and_not_undoable(self):
        self.req("/api/done", {"taskId": "AAAAAAAA-1"}, {"X-Brain": "1"})
        fake_quicktodo(self.paths(), outcome="blocked")
        _, j = self.req("/api/state")
        r = j["actions"]["recent"][0]
        self.assertEqual((r["text"], r["undoable"]), ("That task is waiting on another one", False))


class Module(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self.p = {"actions_dir": self.tmp / "a", "pending": self.tmp / "s.json", "results": self.tmp / "r.json"}
        self.tasks = [{"id": "AAAAAAAA-1", "title": "Read Chapter 5"}]

    def test_undo_window_closes(self):
        now = datetime.now().astimezone()
        req = da.request_done("AAAAAAAA-1", self.tasks, self.p, now)
        fake_quicktodo(self.p, when=now)
        da.sync(self.p, now)
        with self.assertRaises(ValueError):
            da.request_undo(req["id"], self.p, now + timedelta(seconds=da.UNDO_SECONDS + 1))

    def test_waiting_flag_after_a_while(self):
        now = datetime.now().astimezone()
        da.request_done("AAAAAAAA-1", self.tasks, self.p, now)
        self.assertFalse(da.sync(self.p, now)["pending"][0]["waiting"])
        self.assertTrue(da.sync(self.p, now + timedelta(seconds=da.WAITING_SECONDS + 1))["pending"][0]["waiting"])

    def test_unreadable_snapshot_refuses(self):
        with self.assertRaises(ValueError):
            da.request_done("AAAAAAAA-1", None, self.p)

    def test_request_file_is_atomic_and_hidden_temp_is_gone(self):
        da.request_done("AAAAAAAA-1", self.tasks, self.p)
        names = [f.name for f in (self.tmp / "a").iterdir()]
        self.assertEqual(len(names), 1)
        self.assertTrue(names[0].endswith(da.SUFFIX))


if __name__ == "__main__":
    unittest.main()
