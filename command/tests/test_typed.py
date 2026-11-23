import sys, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import phrasings as P  # noqa: E402
import typed_cases as C  # noqa: E402
import typed  # noqa: E402

NOW = datetime(2026, 11, 10, 10, 0, tzinfo=timezone(timedelta(hours=-5)))        # a Tuesday


class Actions(unittest.TestCase):
    def test_every_phrase_gives_its_action(self):
        wrong = []
        for action, items in C.ACTIONS.items():
            for s in items:
                got = typed.parse_action(s, P.TASKS, NOW)
                if not got or got["action"] != action:
                    wrong.append((action, got and got["action"], s))
        self.assertEqual(wrong, [])

    def test_questions_and_statements_never_act(self):
        wrong = [(s, typed.parse_action(s, P.TASKS, NOW)) for s in C.NOT_ACTIONS if typed.parse_action(s, P.TASKS, NOW)]
        self.assertEqual(wrong, [])

    def test_names_the_task(self):
        g = lambda s: typed.parse_action(s, P.TASKS, NOW)
        self.assertEqual(g("mark lab 7 done")["task_id"], "t2")
        self.assertEqual(g("done")["task_id"], None)
        self.assertEqual(g("snooze lab 7 till 5pm")["task_id"], "t2")
        self.assertEqual(g("starting read chapter 5")["task_id"], "t1")
        self.assertEqual(g("i started lab 7 40 min ago")["task_id"], "t2")
        self.assertIsNone(g("mark the dishes done"))                      # not one of her tasks

    def test_args(self):
        g = lambda s: typed.parse_action(s, P.TASKS, NOW)["args"]
        self.assertEqual(g("i started 20 min ago"), {"minutes": 20})
        self.assertEqual(g("i started an hour ago"), {"minutes": 60})
        self.assertEqual(g("i started half an hour ago"), {"minutes": 30})
        self.assertEqual(g("add 15 minutes"), {"minutes": 15})
        self.assertEqual(g("add an hour"), {"minutes": 60})
        self.assertEqual(g("more time"), {"minutes": 15})
        self.assertEqual(g("snooze"), {})
        self.assertEqual(g("snooze for an hour"), {"hours": 1.0})
        self.assertEqual(g("remind me in 2 hours"), {"hours": 2.0})
        self.assertEqual(g("snooze for 30 min"), {"hours": 0.5})
        self.assertEqual(g("push it to tomorrow"), {"until": "tomorrow"})
        self.assertEqual(g("snooze lab 7 till 5pm"), {"until": "2026-11-10T17:00-05:00", "dateOnly": False})
        self.assertEqual(g("push lab 7 to friday")["until"][:10], "2026-11-13")
        self.assertTrue(g("push lab 7 to friday")["dateOnly"])
        self.assertEqual(g("unpin everything"), {"all": True})
        self.assertEqual(g("i'm stuck on my taxes"), {"words": "my taxes"})

    def test_out_of_range_minutes_do_nothing(self):
        self.assertIsNone(typed.parse_action("i started 20 hours ago", P.TASKS, NOW))
        self.assertIsNone(typed.parse_action("add 9 hours", P.TASKS, NOW))


class Replies(unittest.TestCase):
    def r(self, s, pending=C.PENDING):
        return typed.parse_reply(s, pending, NOW)

    def test_no_pending_question_changes_nothing(self):
        for s in ["yes", "no", "make it friday", "sure", "cancel"]:
            self.assertIsNone(typed.parse_reply(s, None, NOW), s)

    def test_yes_no_not_task(self):
        for s in C.YES:
            self.assertEqual(self.r(s), {"kind": "yes"}, s)
        for s in C.NO:
            self.assertEqual(self.r(s), {"kind": "no"}, s)
        for s in C.NOT_TASK:
            self.assertEqual(self.r(s), {"kind": "not_task"}, s)

    def test_edits(self):
        wrong = []
        for s, want in C.EDITS:
            got = self.r(s)
            if not got or got["kind"] != "edit":
                wrong.append((s, got)); continue
            for k, v in want.items():
                have = got["edits"].get(k)
                if k == "due" and v:
                    if not (have or "").startswith(v):
                        wrong.append((s, have))
                elif have != v:
                    wrong.append((s, k, have))
        self.assertEqual(wrong, [])

    def test_new_sentences_are_not_replies(self):
        wrong = [(s, self.r(s)) for s in C.NOT_REPLIES if self.r(s)]
        self.assertEqual(wrong, [])

    def test_time_words(self):
        self.assertEqual(self.r("5pm")["edits"]["due"][11:16], "17:00")
        self.assertEqual(self.r("friday at 3")["edits"]["due"], "2026-11-13T15:00-05:00")
        self.assertEqual(self.r("in 2 hours")["edits"]["due"], "2026-11-10T12:00-05:00")
        rem = dict(C.PENDING, mode="reminder")
        self.assertEqual(self.r("make it saturday", rem)["edits"]["due"], "2026-11-14T09:00-05:00")     # a text for a day starts at 9 AM

    def test_yes_with_a_change(self):
        got = self.r("yes but make it friday")
        self.assertEqual((got["kind"], got["confirm"], got["edits"]["due"][:10]), ("edit", True, "2026-11-13"))
        self.assertEqual(self.r("no, friday")["kind"], "edit")
        self.assertEqual(self.r("make it saturday and add it")["confirm"], True)

    def test_title_keeps_her_capitals(self):
        self.assertEqual(self.r("call it Email Dr. Lee about the lab")["edits"]["title"], "Email Dr. Lee about the lab")


if __name__ == "__main__":
    unittest.main()
