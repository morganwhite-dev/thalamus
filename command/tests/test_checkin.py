"""A due task that also wants daily check-ins: one sentence, one task, one check-in tied to it."""
import sys, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import capture as C  # noqa

TZ = timezone(timedelta(hours=-5))
NOW = datetime(2026, 11, 13, 9, 0, tzinfo=TZ)           # a Friday
LISTS = ["Cloud Computing", "Network Security", "Internships", "Security Projects", "Personal", "Play"]


class CheckIn(unittest.TestCase):
    def test_her_sentence(self):
        p = C.detect("add complete tier 1 by monday, check in with me every day", LISTS, NOW)
        self.assertEqual(p["title"], "Complete tier 1")
        self.assertEqual(p["due"][:10], "2026-11-16")
        self.assertEqual(p["mode"], "task")
        self.assertNotIn("habit", p)
        self.assertEqual(p["checkin"]["until"], "2026-11-16")
        self.assertEqual(p["checkin"]["label"], "daily")
        self.assertEqual(p["checkin"]["nudgeAt"], "09:00")

    def test_other_wordings(self):
        for s in ["complete tier 1 due monday and remind me every day until then",
                  "remind me to work on tier 1 every day until monday",
                  "complete tier 1 every day until monday and check in with me",
                  "complete tier 1 by monday, nudge me daily"]:
            p = C.detect(s, LISTS, NOW)
            self.assertTrue(p and p.get("checkin"), s)
            self.assertEqual(p["checkin"]["until"], "2026-11-16", s)
            self.assertIn("tier 1", p["title"].lower(), s)       # the 1 stays in the name

    def test_list_from_words_or_sector(self):
        self.assertEqual(C.detect("complete tier 1 by monday, nudge me daily in network security", LISTS, NOW)["list"], "Network Security")
        self.assertEqual(C.detect("complete tier 1 by monday, check in with me every day", LISTS, NOW, sector="personal")["list"], "Personal")

    def test_a_time_next_to_the_day_is_the_due_time(self):
        p = C.detect("finish the lab by friday at 5pm and check in with me every day", LISTS, NOW)
        self.assertEqual(p["due"][:16], "2026-11-20T17:00")
        self.assertEqual(p["checkin"]["nudgeAt"], "09:00")

    def test_no_due_date_stays_a_repeat(self):
        p = C.detect("remind me to stretch every day", LISTS, NOW)
        self.assertTrue(p["habit"]); self.assertNotIn("checkin", p)

    def test_no_check_in_wording_stays_a_repeat(self):
        p = C.detect("work on wargames every day", LISTS, NOW)
        self.assertTrue(p["habit"]); self.assertNotIn("checkin", p)

    def test_plain_due_task_has_no_checkin(self):
        p = C.detect("add complete tier 1 by monday", LISTS, NOW)
        self.assertNotIn("checkin", p); self.assertTrue(p["due"])

    def test_nudge_until_then_defaults_to_daily(self):
        p = C.detect("complete tier 1 by monday, nudge me until then", LISTS, NOW)
        self.assertEqual(p["title"], "Complete tier 1")
        self.assertEqual(p["checkin"]["label"], "daily"); self.assertEqual(p["checkin"]["until"], "2026-11-16")
        p = C.detect("complete tier 1 by monday, check in with me", LISTS, NOW)
        self.assertTrue(p["checkin"])

    def test_wording_never_stays_in_the_title(self):
        p = C.detect("complete blah blah nudge me until then", LISTS, NOW)
        self.assertEqual(p["title"], "Complete blah blah")
        self.assertNotIn("checkin", p); self.assertIsNone(p["due"]); self.assertIn("due date", p["hint"])
        p = C.detect("complete blah blah and check in with me", LISTS, NOW)
        self.assertEqual(p["title"], "Complete blah blah"); self.assertIn("hint", p)

    def test_a_one_time_nudge_is_still_a_reminder(self):
        p = C.detect("nudge me friday at 5pm to submit the lab", LISTS, NOW)
        self.assertNotIn("checkin", p); self.assertNotIn("hint", p); self.assertEqual(p["mode"], "reminder")

    def test_number_in_a_name_is_kept_in_plain_repeats(self):
        self.assertEqual(C.detect("read lab 1 every day", LISTS, NOW)["title"], "Read lab 1")


if __name__ == "__main__":
    unittest.main()
