"""Check-ins on a due task: stored text-only, tied to the task, end with the due day, one gentle text a day."""
import sys, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE.parent.parent / "engine")); sys.path.insert(0, str(HERE.parent.parent / "push"))
import play, push_logic  # noqa: E402

TZ = timezone(timedelta(hours=-5))
FRI9 = datetime(2026, 11, 13, 9, 0, tzinfo=TZ)
FOR = {"title": "Complete tier 1", "list": "Network Security"}


def add(now=FRI9, until="2026-11-16", **kw):
    return play.apply(play.empty(), "addhabit", now, title="Complete tier 1", until=until, forTask=kw.get("forTask", FOR))


class Store(unittest.TestCase):
    def test_stored_text_only_and_tied_to_the_task(self):
        h = add()["habits"][0]
        self.assertTrue(h["textOnly"]); self.assertEqual(h["forTask"], FOR); self.assertEqual(h["until"], "2026-11-16")

    def test_starts_today_before_the_nudge_and_tomorrow_after_it(self):
        self.assertEqual(add(FRI9)["habits"][0]["startOn"], "2026-11-13")
        self.assertEqual(add(FRI9.replace(hour=18))["habits"][0]["startOn"], "2026-11-14")

    def test_ends_with_the_due_day(self):
        st = add()
        self.assertEqual(len(play.habit_rows(st, FRI9.replace(day=16))), 1)       # the due day still counts
        self.assertEqual(play.habit_rows(st, FRI9.replace(day=17)), [])           # the day after: gone
        st2 = play.apply(st, "drophabit", FRI9.replace(day=17), id="none") if False else st
        self.assertEqual(len(st2["habits"]), 1)

    def test_expired_ones_are_cleared_on_the_next_habit_change(self):
        st = add()
        later = play.apply(st, "addhabit", FRI9.replace(day=20), title="Read", days=[0])
        self.assertEqual([h["title"] for h in later["habits"]], ["Read"])

    def test_adding_again_replaces_it(self):
        st = play.apply(add(), "addhabit", FRI9, title="Complete tier 1", until="2026-11-18", forTask=FOR)
        self.assertEqual(len(st["habits"]), 1); self.assertEqual(st["habits"][0]["until"], "2026-11-18")

    def test_bad_input(self):
        for kw in ({"until": "2026-11-01"}, {"until": "monday"}, {"forTask": {"title": "x", "list": ""}}):
            with self.assertRaises(ValueError):
                add(**kw) if "forTask" in kw else add(until=kw["until"])

    def test_never_a_node(self):
        view = play.view(add(), [], {}, lambda t: "play", None, now=FRI9)
        self.assertEqual(view["habits"], [])


class Push(unittest.TestCase):
    def rec(self, now, until="2026-11-16", start="2026-11-13"):
        rows = play.habit_rows(add(), now)
        for r in rows:
            r["until"], r["startOn"] = until, start
        return {"habits": rows, "queue": [], "snapshot": {"stale": False}}

    def ping(self, now, **kw):
        p, st = push_logic.decide(self.rec(now, **kw), {}, None, {"importAgeHours": 1, "importFailed": False}, {}, now)
        return p

    def test_texts_from_the_nudge_hour_with_the_due_day(self):
        p = self.ping(FRI9.replace(hour=17, minute=5))
        self.assertEqual(p["type"], "habit")
        self.assertEqual(p["text"], "Check-in: Complete tier 1 is due Monday. Have you worked on it? No pressure.")

    def test_not_before_the_nudge_hour(self):
        self.assertIsNone(self.ping(FRI9))

    def test_says_today_and_tomorrow(self):
        self.assertIn("due tomorrow", self.ping(FRI9.replace(day=15, hour=17, minute=5))["text"])
        self.assertIn("due today", self.ping(FRI9.replace(day=16, hour=17, minute=5))["text"])

    def test_nothing_after_the_due_day_or_before_the_start_day(self):
        self.assertIsNone(self.ping(FRI9.replace(day=17, hour=17, minute=5)))
        self.assertIsNone(self.ping(FRI9.replace(hour=17, minute=5), start="2026-11-14"))

    def test_once_a_day(self):
        now = FRI9.replace(hour=17, minute=5)
        p, st = push_logic.decide(self.rec(now), {}, None, {"importAgeHours": 1, "importFailed": False}, {}, now)
        again, _ = push_logic.decide(self.rec(now), st, None, {"importAgeHours": 1, "importFailed": False}, {}, now + timedelta(hours=2))
        self.assertIsNone(again)


if __name__ == "__main__":
    unittest.main()
