import sys, unittest
from datetime import datetime, timezone
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE.parent.parent / "engine")); sys.path.insert(0, str(HERE.parent.parent / "push"))
sys.path.insert(0, str(HERE.parent.parent / "command"))
import play, push_logic, capture  # noqa: E402

NOW = datetime(2026, 11, 9, 18, 0, tzinfo=timezone.utc)   # a Monday
CFG = {"quietHours": {"start": "22:30", "end": "07:30"}}
LISTS = ["Personal", "Internships", "Security Projects", "Play", "Network Security"]


def with_habit(days=None, done=False):
    st = play.apply(play.empty(), "addhabit", NOW, title="TryHackMe", notes="do one lab", **({"days": days} if days else {}))
    if done:
        st = play.apply(st, "habitdone", NOW, id=st["habits"][0]["id"])
    return st


class Habits(unittest.TestCase):
    def test_add_done_undo_drop(self):
        st = with_habit(); h = st["habits"][0]
        self.assertFalse(play.habit_rows(st, NOW)[0]["doneToday"])
        st = play.apply(st, "habitdone", NOW, id=h["id"])
        self.assertTrue(play.habit_rows(st, NOW)[0]["doneToday"])
        st = play.apply(st, "habitundo", NOW, id=h["id"])
        self.assertFalse(play.habit_rows(st, NOW)[0]["doneToday"])
        st = play.apply(st, "drophabit", NOW, id=h["id"]); self.assertEqual(st["habits"], [])

    def test_no_duplicates_and_bad_time(self):
        st = with_habit()
        with self.assertRaises(ValueError): play.apply(st, "addhabit", NOW, title="tryhackme")
        with self.assertRaises(ValueError): play.apply(play.empty(), "addhabit", NOW, title="x", nudgeAt="5pm")

    def test_nudge_once_after_time_not_when_done(self):
        rec = {"habits": play.habit_rows(with_habit(), NOW)}
        early = NOW.replace(hour=12)
        self.assertIsNone(push_logic.decide(rec, {}, None, {}, CFG, early)[0])
        ping, st = push_logic.decide(rec, {}, None, {}, CFG, NOW)
        self.assertEqual(ping["type"], "habit"); self.assertIn("TryHackMe", ping["text"]); self.assertIn("No pressure", ping["text"])
        again = push_logic.decide(rec, st, None, {}, CFG, NOW.replace(hour=19))[0]
        self.assertTrue(again is None or again["type"] != "habit")
        done = {"habits": play.habit_rows(with_habit(done=True), NOW)}
        self.assertIsNone(push_logic.decide(done, {}, None, {}, CFG, NOW)[0])

    def test_only_on_its_days_and_respects_presence_quiet(self):
        tue_only = {"habits": play.habit_rows(with_habit(days=[1]), NOW)}     # Monday now
        self.assertIsNone(push_logic.decide(tue_only, {}, None, {}, CFG, NOW)[0])
        rec = {"habits": play.habit_rows(with_habit(), NOW)}
        self.assertIsNone(push_logic.decide(rec, {}, NOW, {}, CFG, NOW)[0])                      # dashboard being watched
        self.assertIsNone(push_logic.decide(rec, {}, None, {}, CFG, NOW.replace(hour=23))[0])    # quiet hours

    def test_capture_general_cadences(self):
        r = capture.detect("add tryhackmes to playground. my goal is to do one practice lab a day.", LISTS, NOW)
        self.assertEqual((r["title"], r["list"], r["cluster"], r["habit"]["label"]), ("Tryhackmes", "Play", "play", "daily"))
        self.assertIn("practice lab", r["notes"])
        self.assertEqual(capture.detect("remind me to stretch every morning", LISTS, NOW)["habit"]["nudgeAt"], "08:00")
        self.assertEqual(capture.detect("I need to review flashcards twice a week", LISTS, NOW)["habit"]["days"], [0, 3])
        r = capture.detect("add apply to internships every friday at 4pm to internships", LISTS, NOW)
        self.assertEqual((r["habit"]["days"], r["habit"]["nudgeAt"], r["cluster"]), ([4], "16:00", "intern"))
        self.assertNotIn("habit", capture.detect("remind me to email Dr. Lee Friday", LISTS, NOW))
        r = capture.detect("do tryhack me for one hour a day", LISTS, NOW)          # the plain way to say it
        self.assertEqual((r["title"], r["list"], r["habit"]["minutes"], r["habit"]["label"]), ("Tryhack me", "Play", 60, "daily"))
        self.assertEqual(capture.detect("do tryhackme for 30 minutes every morning", LISTS, NOW)["habit"]["nudgeAt"], "08:00")
        self.assertEqual(capture.detect("do the dishes tonight", LISTS, NOW)["title"], "Do the dishes")
        self.assertIsNone(capture.detect("do you have teaching notes for module 5", LISTS, NOW))
        for typo in ("do tryhack me one hour. day", "do tryhackme for one hour at day", "do tryhackme one hour day", "do tryhackme 1 hour/day"):
            r = capture.detect(typo, LISTS, NOW)                                                  # typos still make a repeating item
            self.assertEqual((r["title"][:9], r["habit"]["minutes"], r["habit"]["label"]), (r["title"][:9], 60, "daily"), typo)
            self.assertNotIn("day", r["title"].lower())
        self.assertIsNone(capture.detect("what a day", LISTS, NOW))
        self.assertIsNone(capture.detect("the meeting is one hour on day two", LISTS, NOW))
        r = capture.detect("remind me monday through friday to do tryhackme for one hour a day", LISTS, NOW)
        self.assertEqual((r["title"], r["habit"]["label"], r["habit"]["minutes"], r["mode"]), ("Tryhackme", "weekdays", 60, "reminder"))
        self.assertEqual(capture.detect("do tryhackme mon-fri at 7pm", LISTS, NOW)["habit"]["nudgeAt"], "19:00")
        self.assertEqual(capture.detect("do tryhackme monday, wednesday and friday", LISTS, NOW)["habit"]["days"], [0, 2, 4])
        self.assertEqual(capture.detect("do tryhackme on tuesdays and thursdays for 45 minutes", LISTS, NOW)["habit"]["days"], [1, 3])
        self.assertNotIn("habit", capture.detect("email dr lee on friday", LISTS, NOW))
        r = capture.detect("put tryhackme for one hour a day in playground", LISTS, NOW)           # not a parked idea
        self.assertEqual((r["title"], r["list"], r["habit"]["minutes"]), ("Tryhackme", "Play", 60))
        self.assertIsNone(capture.detect("park tryhackme daily in playground", LISTS, NOW))        # explicit park stays an idea
        self.assertIsNone(capture.detect("put tryhackme in the playground", LISTS, NOW))           # no repeat: still an idea
        st = play.apply(play.empty(), "addhabit", NOW, title="TryHackMe", minutes=60)
        text = push_logic.habit_text(play.habit_rows(st, NOW)[0]); self.assertIn("want your hour for today", text)
        self.assertIsNone(capture.detect("what do I do every day?", LISTS, NOW))


if __name__ == "__main__":
    unittest.main()
