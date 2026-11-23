"""Regression cases from the code review of the chat-phrasebook branch (each input below was reproduced as a bug)."""
import sys, time, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
for p in (HERE, HERE.parent, ROOT / "engine", ROOT / "play", ROOT / "router", ROOT / "prep"):
    sys.path.insert(0, str(p))
import phrasings as P  # noqa: E402
import typed_cases as C  # noqa: E402
import acts, capture, intent, park, plain, project_status, route_preview as R, schedule_qa, typed  # noqa: E402

TZ = timezone(timedelta(hours=-5))
NOW = datetime(2026, 11, 10, 10, 0, tzinfo=TZ)        # a Tuesday, 10 AM
NIGHT = datetime(2026, 11, 10, 20, 0, tzinfo=TZ)      # 8 PM
LISTS = R.LISTS


def d(s, now=NOW):
    return R.decide(s, tasks=P.TASKS, now=now)


class Questions(unittest.TestCase):
    def test_a_trailing_question_mark_keeps_it_a_question(self):                      # 1
        for s in ["wait, skip this?", "oh, snooze this?", "hmm, pin this?", "ok so skip this?"]:
            self.assertIsNone(typed.parse_action(s, P.TASKS, NOW), s)
            self.assertIsNone(acts.parse(plain.normalize(s), P.TASKS, current_id="t1", now=NOW), s)
            self.assertNotEqual(d(s), "action", s)
        self.assertIsNotNone(acts.parse("skip this", P.TASKS, current_id="t1", now=NOW))


class Park(unittest.TestCase):
    def test_no_idea_is_not_an_idea(self):                                            # 2
        for s in ["I had no idea about the outage", "i have no idea about that", "i got no idea for tonight", "i had a vague idea about when it ended",
                  "do you have any idea about it"]:
            self.assertIsNone(park.parse(s), s)
            self.assertNotEqual(d(s), "park", s)

    def test_real_ideas_still_park(self):
        self.assertEqual(park.parse("i had an idea for a golf swing tracker"), "a golf swing tracker")
        self.assertEqual(park.parse("i just thought of a cool idea about a budget app"), "a budget app")
        self.assertEqual(park.parse("i have another idea: a plant watering bot"), "a plant watering bot")
        self.assertEqual(park.parse("i had an idea"), "")


class OneParser(unittest.TestCase):
    def run_act(self, s, cur=None, now=NOW):
        calls = []
        plan = acts.parse(plain.normalize(s), P.TASKS, current_id=cur, now=now)
        out = acts.execute(plan, apply=lambda a, c: calls.append(a)) if plan else None
        return calls, out

    def test_snooze_with_a_time_uses_the_task_name_only(self):                         # 3
        calls, out = self.run_act("snooze lab 7 till 5pm")
        self.assertEqual(calls, [["snooze", "t2", "--until", "2026-11-10T17:00"]])
        self.assertIn("5:00 PM", out)
        calls, _ = self.run_act("push lab 7 to friday")
        self.assertEqual(calls, [["snooze", "t2", "--until", "2026-11-13T09:00"]])      # a day with no time comes back at 9 AM

    def test_live_path_and_preview_agree(self):
        for s in ["snooze lab 7 till 5pm", "pin lab 7", "skip this", "snooze read chapter 5 and 6"]:
            self.assertEqual(d(s), "action", s)
            self.assertEqual(intent.before_capture(s, P.TASKS)[0], "action", s)

    def test_undo_is_answered_with_where_the_button_is(self):
        label, data = intent.before_capture("undo that", P.TASKS)
        self.assertEqual(label, "action")
        self.assertIn("Undo", intent.action_reply(data))
        self.assertIsNone(acts.parse("undo that", P.TASKS, now=NOW))                    # never acts from a sentence
        self.assertEqual(d("undo that"), "undo")       # the box takes back its own last change first (STATE_MODEL_UNDO.md)

    def test_edit_shaped_sentences_are_not_tasks(self):
        for s in ["make it saturday", "put it in school", "call it Email Bob", "set it to friday", "move it to internships", "ok make it friday"]:
            self.assertIsNone(capture.detect(s, LISTS, NOW), s)
            self.assertNotEqual(d(s), "capture", s)

    def test_typed_replies_need_a_pending_question(self):
        for s in ["make it saturday", "yes", "put it in school"]:
            self.assertIsNone(typed.parse_reply(s, None, NOW), s)


class CodingIsNotATask(unittest.TestCase):
    def test_model_work(self):                                                         # 4
        for s in ["just add unit tests for app.py", "I need a Python script", "create a task scheduler in Python", "add a function to parse dates",
                  "make a flask app with a login page", "i need a function that sorts a list"]:
            self.assertIsNone(capture.detect(s, LISTS, NOW), s)
            self.assertNotEqual(d(s), "capture", s)

    def test_real_tasks_still_capture(self):
        for s in ["add email recruiter", "add file taxes to my list", "i need a new keyboard", "add a task to call mom"]:
            self.assertIsNotNone(capture.detect(s, LISTS, NOW), s)


class Speed(unittest.TestCase):
    def test_project_status_is_linear(self):                                           # 5
        for n in (400, 800, 4000):
            s = "when did i last open x" + " " * n + "\ny"
            t0 = time.perf_counter()
            self.assertIsNone(project_status.parse_intent(s))
            self.assertFalse(project_status.is_bare(s))
            self.assertLess(time.perf_counter() - t0, 0.02, n)
        t0 = time.perf_counter()
        project_status.parse_intent("when did i last open x" + " " * 3900 + "y")
        self.assertLess(time.perf_counter() - t0, 0.02)

    def test_one_line_still_parses(self):
        self.assertEqual(project_status.parse_intent("when did i last open the analyzer  project"), "analyzer")


class BadNumbers(unittest.TestCase):
    def test_invalid_times_and_sizes_return_nothing(self):                              # 6
        pend = C.PENDING
        for s in ["make it friday at 3:99", "make it in 999999999999999 days", "make it in 99999999 hours"]:
            self.assertIsNone(typed.parse_reply(s, pend, NOW), s)
        for s in ["snooze until 5:99pm", "snooze for 999999999999999999 hours"]:
            got = typed.parse_action(s, P.TASKS, NOW)                                   # recognised, refused: a reply, never an action
            self.assertTrue(got is None or (got.get("problem") and got["task_id"] is None), s)
        for s in ["remind me at 5:99pm to stretch", "call mom in 999999999999999 days", "pay rent in 99999999999 hours"]:
            capture.detect(s, LISTS, NOW)                                               # must not raise


class Tonight(unittest.TestCase):
    def test_never_a_past_time(self):                                                  # 7
        g = lambda s, now: typed.parse_action(s, P.TASKS, now)
        self.assertEqual(g("snooze until tonight", NOW)["args"]["until"], "2026-11-10T18:00-05:00")
        self.assertEqual(g("snooze until tonight", NIGHT)["args"]["until"], "2026-11-10T21:00-05:00")
        late = g("snooze until tonight", NIGHT.replace(hour=22))                        # tonight has passed: refused with a reply
        self.assertEqual((late["task_id"], late["problem"]["kind"]), (None, "past"))
        self.assertEqual(g("snooze until tonight at 9pm", NIGHT)["args"]["until"], "2026-11-10T21:00-05:00")
        self.assertEqual(g("snooze until tonight at 7pm", NIGHT)["problem"]["kind"], "past")
        self.assertEqual(g("snooze till tonight", NIGHT)["args"]["until"], "2026-11-10T21:00-05:00")


class Reminders(unittest.TestCase):
    def test_setup_a_reminder_is_a_text(self):                                          # 8
        p = capture.detect("setup a reminder for 5pm to stretch", LISTS, NOW)
        self.assertEqual((p["mode"], p["title"], p["due"][:16]), ("reminder", "Stretch", "2026-11-10T17:00"))
        again = capture.detect("set up a reminder for 5pm to stretch", LISTS, NOW)
        self.assertEqual(again["mode"], "reminder")
        a, b = (capture.detect(s, LISTS, NOW) for s in ("setup a reminder for the 15th to pay rent", "set a reminder for the 15th to pay rent"))
        self.assertEqual(a["mode"], b["mode"])


class Shorthand(unittest.TestCase):
    def test_caps_and_files_are_left_alone(self):                                       # 9
        self.assertEqual(plain.normalize("pay AAA membership dues"), "pay AAA membership dues")
        self.assertEqual(plain.normalize("open AAA.pdf"), "open AAA.pdf")
        self.assertEqual(plain.normalize("check www.example.com"), "check www.example.com")
        self.assertEqual(plain.normalize("pay aaa dues"), "pay aaa dues")
        self.assertEqual(plain.normalize("heyyy sooo plsss"), "hey so pls")
        self.assertEqual(plain.normalize("Heyyy"), "Hey")


class LookLike(unittest.TestCase):
    def test_needs_a_schedule_word(self):                                               # 10
        for s in ["What does a TCP handshake look like?", "what does a good resume look like", "what does a subnet mask look like"]:
            self.assertIsNone(schedule_qa.parse(s, None, NOW), s)
            self.assertNotEqual(d(s), "schedule", s)
        for s in ["what does my week look like", "what does tomorrow look like", "what does my day look like", "what does the week look like"]:
            self.assertIsNotNone(schedule_qa.parse(s, None, NOW), s)


class YesWords(unittest.TestCase):
    def test_all_yes_words_confirm(self):                                               # 11
        for lead in ["yes but", "yeah but", "yep, ", "okay,", "ok", "sure,", "yup but", "k", "ya"]:
            r = typed.parse_reply(f"{lead} make it friday", C.PENDING, NOW)
            self.assertTrue(r and r["confirm"], lead)
        self.assertFalse(typed.parse_reply("make it friday", C.PENDING, NOW)["confirm"])
        self.assertFalse(typed.parse_reply("so make it friday", C.PENDING, NOW)["confirm"])


if __name__ == "__main__":
    unittest.main()
