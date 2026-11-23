"""Phase 15: plain-language add from the command box (capture proposal, add and take-back requests)."""
import json, sys, unittest
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(Path(__file__).resolve().parent))
import done_actions as da  # noqa
from test_server import Base  # noqa

LISTS = ["Cloud Computing", "Network Security", "Internships", "Personal", "Play"]
H = {"X-Brain": "1"}


def answer(paths, outcome="added", task_id="NEW-UUID-0001", only="add"):
    out = da._read(paths["results"], {"version": 1, "results": []})
    for f in sorted(Path(paths["actions_dir"]).glob("*" + da.SUFFIX)):
        req = json.loads(f.read_text())
        if any(r["id"] == req["id"] for r in out["results"]):
            continue
        res = outcome if req["action"] == "add" else "removed"
        out["results"].append({"id": req["id"], "action": req["action"], "outcome": res, "taskId": task_id,
                               "title": req["title"], "detail": "", "processedAt": datetime.now().astimezone().isoformat()})
    Path(paths["results"]).write_text(json.dumps(out))


class Capture(Base):
    def setUp(self):
        super().setUp()
        snap = json.loads((self.tmp / "snap.json").read_text())
        snap["lists"] = LISTS
        (self.tmp / "snap.json").write_text(json.dumps(snap))

    def paths(self):
        from server import DONE_PATHS
        return DONE_PATHS["p"]

    def files(self):
        return list(Path(self.paths()["actions_dir"]).glob("*" + da.SUFFIX))

    def test_plain_sentence_returns_a_proposal_and_writes_nothing(self):
        c, j = self.req("/api/command", {"text": "remind me to email Dr. Lee about the lab friday at 5pm"}, H)
        self.assertEqual(c, 200)
        p = j["capture"]
        self.assertEqual(p["title"], "Email Dr. Lee about the lab")
        self.assertEqual(p["list"], "Personal")
        self.assertTrue(p["due"].endswith("T17:00-05:00") or "T17:00" in p["due"])
        self.assertEqual(self.files(), [])

    def test_question_and_tagged_commands_are_not_captured(self):
        c, j = self.req("/api/command", {"text": "what's due friday?"}, H)
        self.assertEqual(c, 202)
        c, j = self.req("/api/command", {"text": "remind me to email Dr. Lee", "skipCapture": True}, H)
        self.assertEqual(c, 202)

    def test_add_writes_one_well_formed_file(self):
        c, j = self.req("/api/capture/add", {"title": "Email Dr. Lee", "list": "personal", "due": "2026-11-13T17:00-05:00"}, H)
        self.assertEqual(c, 200)
        (f,) = self.files()
        r = json.loads(f.read_text())
        self.assertEqual((r["action"], r["title"], r["list"], r["taskId"]), ("add", "Email Dr. Lee", "Personal", "new"))
        self.assertEqual(r["version"], 1)
        self.assertEqual(len(j["actions"]["pending"]), 1)

    def test_add_validation(self):
        for body in [{"title": "", "list": "Personal"}, {"title": "x" * 201, "list": "Personal"},
                     {"title": "Do it", "list": "Nonexistent"}, {"title": "Do it", "list": ""},
                     {"title": "Do it", "list": "Personal", "due": "not a date"}]:
            c, _ = self.req("/api/capture/add", body, H)
            self.assertEqual(c, 400, body)
        self.assertEqual(self.files(), [])

    def test_identical_pending_add_is_refused(self):
        body = {"title": "Email Dr. Lee", "list": "Personal", "due": None}
        self.assertEqual(self.req("/api/capture/add", body, H)[0], 200)
        self.assertEqual(self.req("/api/capture/add", body, H)[0], 409)
        self.assertEqual(len(self.files()), 1)

    def test_needs_brain_header(self):
        c, _ = self.req("/api/capture/add", {"title": "Do it", "list": "Personal"})
        self.assertEqual(c, 403)

    def test_added_result_then_undo_window(self):
        self.req("/api/capture/add", {"title": "Email Dr. Lee", "list": "Personal"}, H)
        answer(self.paths())
        c, st = self.req("/api/state")
        rec = st["actions"]["recent"][0]
        self.assertEqual((rec["outcome"], rec["undoable"], rec["taskId"]), ("added", True, "NEW-UUID-0001"))
        c, st = self.req("/api/capture/undo", {"actionId": rec["id"]}, H)
        self.assertEqual(c, 200)
        files = [json.loads(f.read_text()) for f in self.files()]
        self.assertIn(("unadd", "NEW-UUID-0001"), [(x["action"], x["taskId"]) for x in files])

    def test_cannot_take_back_a_done_or_unknown(self):
        c, _ = self.req("/api/capture/undo", {"actionId": "nope"}, H)
        self.assertEqual(c, 400)

    def test_already_exists_is_not_undoable(self):
        self.req("/api/capture/add", {"title": "Email Dr. Lee", "list": "Personal"}, H)
        answer(self.paths(), outcome="alreadyExists")
        c, st = self.req("/api/state")
        self.assertFalse(st["actions"]["recent"][0]["undoable"])
        self.assertEqual(st["actions"]["recent"][0]["text"], "That's already on your list")


if __name__ == "__main__":
    unittest.main()
