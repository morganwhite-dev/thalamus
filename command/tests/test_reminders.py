import sys, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
HERE = Path(__file__).resolve().parent
for sub in ("..", "../../play", "../../engine", "../../push"):
    sys.path.insert(0, str(HERE / sub))
import capture, reminders_qa, play, push_logic  # noqa: E402

NOW = datetime(2026, 11, 9, 14, 0, tzinfo=timezone.utc)
CFG = {"quietHours": {"start": "22:30", "end": "07:30"}}
LISTS = ["Personal", "Internships", "Play"]


class Reminders(unittest.TestCase):
    def test_capture_modes(self):
        r = capture.detect("remind me to take a break in 30 minutes", LISTS, NOW)
        self.assertEqual((r["mode"], r["title"]), ("reminder", "Take a break")); self.assertTrue(r["due"].startswith("2026-11-09T14:30"))
        self.assertEqual(capture.detect("remind me to call mom tomorrow at 9am", LISTS, NOW)["mode"], "reminder")
        self.assertEqual(capture.detect("remind me to email Dr. Lee Friday", LISTS, NOW)["mode"], "task")   # a date but no time: stays a task
        self.assertEqual(capture.detect("add golf to my list", LISTS, NOW)["mode"], "task")
        self.assertEqual(capture.detect("remind me to stretch every morning", LISTS, NOW)["mode"], "reminder")

    def test_three_texts_four_hours_apart_and_one_undo(self):
        at = NOW.replace(hour=9, minute=0)
        st = play.apply(play.empty(), "addreminder", NOW, text="Study", at=at.isoformat())
        self.assertEqual([r["at"][11:16] for r in st["reminders"]], ["09:00", "13:00", "17:00"])
        self.assertEqual([r["followUp"] for r in st["reminders"]], [False, True, True])
        later = play.apply(play.empty(), "addreminder", NOW, text="Late", at=NOW.replace(hour=20, minute=0).isoformat())
        self.assertEqual(len(later["reminders"]), 1)                       # 12:00 and 16:00 would be tomorrow / quiet hours
        self.assertEqual(play.apply(st, "dropreminder", NOW, id=st["reminders"][-1]["id"])["reminders"], [])   # one undo takes all three

    def test_follow_up_wording(self):
        r = {"text": "Study", "followUp": True}
        self.assertEqual(push_logic.reminder_text(r, NOW, NOW), "Still on your list: Study.")

    def test_slots(self):
        self.assertEqual(push_logic.follow_slots("09:00", {}), ["09:00", "13:00", "17:00"])
        self.assertEqual(push_logic.follow_slots("17:00", {}), ["17:00", "21:00"])      # 01:00 is past quiet hours start

    def test_store_and_fire_once_without_cap_or_presence(self):
        st = play.apply(play.empty(), "addreminder", NOW, text="Take a break", at=(NOW - timedelta(minutes=1)).isoformat())
        rec = {"reminders": st["reminders"]}
        ping, s2 = push_logic.decide(rec, {"lastPingAt": NOW.isoformat()}, NOW, {}, CFG, NOW)    # capped AND watched: still sends
        self.assertEqual(ping["type"], "reminder"); self.assertEqual(ping["text"], "Reminder: Take a break.")
        self.assertIsNone(push_logic.decide(rec, s2, None, {}, CFG, NOW)[0])                       # only once
        future = play.apply(play.empty(), "addreminder", NOW, text="Later", at=(NOW + timedelta(hours=1)).isoformat())
        self.assertIsNone(push_logic.decide({"reminders": future["reminders"]}, {}, None, {}, CFG, NOW)[0])
        late = push_logic.decide(rec, {}, None, {}, CFG, NOW + timedelta(hours=2))[0]
        self.assertIn("set for", late["text"])
        done = play.apply(st, "reminderdone", NOW, ids=[r["id"] for r in st["reminders"]]); self.assertEqual(done["reminders"], [])
        with self.assertRaises(ValueError): play.apply(play.empty(), "addreminder", NOW, text="x", at="soon")

    def test_text_only_repeat_never_shows_as_a_node(self):
        st = play.apply(play.empty(), "addhabit", NOW, title="Stretch", textOnly=True, nudgeAt="08:00")
        self.assertEqual(play.view(st, [], {}, lambda t: "x", None, now=NOW)["habits"], [])
        rec = {"habits": play.habit_rows(st, NOW)}
        ping, _ = push_logic.decide(rec, {"lastPingAt": NOW.isoformat()}, NOW, {}, CFG, NOW)
        self.assertEqual(ping["text"], "Reminder: Stretch.")

    def test_questions(self):
        self.assertEqual(reminders_qa.parse("what reminders do i have"), ("list", None))
        self.assertEqual(reminders_qa.parse("cancel reminder about mom"), ("cancel", "mom"))
        self.assertIsNone(reminders_qa.parse("remind me to check my reminders at 5pm"))


if __name__ == "__main__":
    unittest.main()


class OrgChatter(unittest.TestCase):
    def test_strips_the_prompt_optimizer_mention_only(self):
        import command
        t = 'Checking first. (Your organization asks me to run a "prompt-optimizer" skill first, but it isn\'t installed here.)\n\nHere is the answer.'
        out = command.strip_org_chatter(t)
        self.assertNotIn("optimizer", out); self.assertIn("Here is the answer.", out)
        plain = "Three tips. Nothing odd."
        self.assertEqual(command.strip_org_chatter(plain), plain)
