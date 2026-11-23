"""Undo for what the chat changes (STATE_MODEL_UNDO.md). The real engine and play code write to a temp folder."""
import json
import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_command import Base  # noqa: E402
import brain  # noqa: E402
import command  # noqa: E402
import play as play_store  # noqa: E402
import undo  # noqa: E402


class Undo(Base):
    def setUp(self):
        super().setUp()
        self._load = brain.load_config
        brain.load_config = lambda path=None: self.config      # acts -> brain.main writes the temp overrides, never hers
        self.r.play_path = self.tmp / "play.json"
        self.r._current_task_id = lambda config, ts: None

    def tearDown(self):
        brain.load_config = self._load
        super().tearDown()

    def ov(self):
        p = self.tmp / "ov.json"
        return json.loads(p.read_text()) if p.exists() else {}

    def snoozed(self):
        return [s["taskId"] for s in self.ov().get("snoozes", [])]

    def test_snooze_then_typed_undo(self):
        j = self.ask("snooze read chapter 5 for 2 hours")
        self.assertIn("Snoozed", j["answer"])
        self.assertTrue(j["undo"]["id"].startswith("u-"))
        self.assertEqual(self.snoozed(), ["AAAAAAAA-1"])
        u = self.ask("undo")
        self.assertTrue(u["answer"].startswith("Undone. I took back: Snoozed"), u["answer"])
        self.assertEqual(self.snoozed(), [])
        self.assertTrue(self.r.get(j["id"])["undo"]["used"])
        self.assertEqual(self.ask("undo that")["answer"], "Nothing the box changed in the last 2 minutes. To take back a Done, press Undo on the status line.")

    def test_pin_undo_by_id_once(self):
        j = self.ask("pin read chapter 5")
        self.assertEqual([p["taskId"] for p in self.ov().get("pins", [])], ["AAAAAAAA-1"])
        self.assertIn("Undone", self.r.undo(j["undo"]["id"], "Undo")["answer"])
        self.assertEqual(self.ov().get("pins"), [])
        self.assertEqual(self.r.undo(j["undo"]["id"], "Undo")["answer"], "That's already undone.")

    def test_undo_puts_back_an_earlier_snooze(self):
        self.ask("snooze read chapter 5 for 1 hour")
        first = self.ov()["snoozes"][0]
        self.ask("snooze read chapter 5 for 3 hours")
        self.ask("undo")
        self.assertEqual(self.ov()["snoozes"], [first])

    def test_changed_since_is_left_alone(self):
        self.ask("skip read chapter 5")
        ov = self.ov()
        ov["skips"][0]["forDate"] = "2099-01-01"            # a button changed it after the chat did
        (self.tmp / "ov.json").write_text(json.dumps(ov))
        self.assertEqual(self.ask("undo")["answer"], "That changed since, so I left it alone.")
        self.assertEqual(self.ov()["skips"][0]["forDate"], "2099-01-01")

    def test_expired_after_two_minutes(self):
        j = self.ask("pin read chapter 5")
        real = command.now_local
        command.now_local = lambda: real() + timedelta(minutes=3)
        try:
            self.assertEqual(self.r.undo(j["undo"]["id"], "Undo")["answer"], "That was more than 2 minutes ago, so I left it alone.")
            self.assertEqual(self.ask("undo")["answer"], "Nothing the box changed in the last 2 minutes. To take back a Done, press Undo on the status line.")
        finally:
            command.now_local = real
        self.assertEqual(len(self.ov()["pins"]), 1)

    def test_park_then_undo(self):
        j = self.ask("park this idea in playground: a golf swing tracker")
        self.assertIn("undo", j)
        self.assertEqual([p["title"] for p in play_store.load(self.r.play_path)["projects"]], ["a golf swing tracker"])
        self.ask("undo")
        self.assertEqual(play_store.load(self.r.play_path)["projects"], [])

    def test_undo_park_frees_its_show_first_slot(self):
        self.ask("park this idea in playground: a golf swing tracker")
        st = play_store.load(self.r.play_path)
        pid = st["projects"][0]["id"]
        play_store.save(play_store.apply(st, "front", command.now_local(), id=pid), self.r.play_path)
        self.assertIn(pid, play_store.load(self.r.play_path)["front"])
        self.ask("undo")
        self.assertEqual(play_store.load(self.r.play_path)["front"], [])

    def test_typed_undo_works_with_a_task_picked(self):
        self.ask("snooze read chapter 5 for 2 hours")
        self.assertIn("Undone", self.ask("undo", taskId="AAAAAAAA-1")["answer"])
        self.assertEqual(self.snoozed(), [])

    def test_cancel_reminder_then_undo(self):
        now = command.now_local()
        st = play_store.apply(play_store.load(self.r.play_path), "addreminder", now, text="call mom", at=(now + timedelta(hours=2)).isoformat())
        play_store.save(st, self.r.play_path)
        before = play_store.load(self.r.play_path)["reminders"]
        j = self.ask("cancel reminder call mom")
        self.assertIn("Cancelled", j["answer"])
        self.assertEqual(play_store.load(self.r.play_path)["reminders"], [])
        self.ask("undo")
        self.assertEqual(play_store.load(self.r.play_path)["reminders"], before)

    def test_reading_never_gets_an_undo(self):
        self.assertNotIn("undo", self.ask("what should I do now?"))

    def test_undo_phrases(self):
        for s in ("undo", "Undo that.", "take that back", "undo my last change please"):
            self.assertTrue(undo.is_undo(s), s)
        for s in ("how do I undo a git commit", "undo the lab submission", "i need to undo something"):
            self.assertFalse(undo.is_undo(s), s)


if __name__ == "__main__":
    unittest.main()
