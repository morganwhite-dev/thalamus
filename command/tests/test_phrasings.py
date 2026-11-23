"""Plain sentences must reach the right handler with no paid model deciding (Morgan, 2026-11-10: "speak as plainly as possible")."""
import sys, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import phrasings as P  # noqa: E402
import route_preview as R  # noqa: E402
import intent, plain, class_qa, capture  # noqa: E402

TZ = timezone(timedelta(hours=-5))
NOW = datetime(2026, 11, 10, 10, 0, tzinfo=TZ)        # a Tuesday


class Corpus(unittest.TestCase):
    def test_every_sentence_reaches_its_handler(self):
        wrong = [(want, R.decide(s, tasks=P.TASKS, now=NOW), s) for want, items in P.CASES.items() for s in items
                 if R.decide(s, tasks=P.TASKS, now=NOW) != want]
        self.assertEqual(wrong, [], f"{len(wrong)} misread")

    def test_corpus_is_big(self):
        self.assertGreater(sum(len(v) for v in P.CASES.values()), 350)


class Guards(unittest.TestCase):
    """Things the new rules must not grab."""
    def d(self, s):
        return R.decide(s, tasks=P.TASKS, now=NOW)

    def test_statements_and_requests_are_not_button_presses(self):
        for s in ["go to the gym three times a week", "start the cloud lab tomorrow", "stop procrastinating tips",
                  "pass the salt recipe ideas", "start a new react project"]:
            self.assertNotEqual(self.d(s), "action", s)

    def test_how_to_questions_are_not_stuck(self):
        for s in ["how do i start a venv", "help me with my resume", "break down the osi model", "help me understand dns"]:
            self.assertNotEqual(self.d(s), "stuck", s)

    def test_questions_never_become_tasks(self):
        for s in ["i need to know what's due friday", "remind me where i was on the analyzer", "can you explain public key encryption",
                  "call it a day", "email drafts are in my inbox", "write a function in dates.py that counts weekdays between two dates",
                  "cancel my 3pm reminder", "what should i do about my landlord"]:
            self.assertNotEqual(self.d(s), "capture", s)

    def test_now_needs_no_window(self):
        self.assertEqual(self.d("what should i do"), "now")
        self.assertEqual(self.d("what should i do tomorrow"), "schedule")
        self.assertEqual(self.d("what's next due"), "schedule")

    def test_done_with_an_unknown_thing_is_not_an_action(self):
        self.assertIsNone(intent.action_request("did the dishes and vacuumed", P.TASKS))
        self.assertEqual(intent.action_request("i finished read chapter 5", P.TASKS)[1]["id"], "t1")

    def test_stuck_names_the_task(self):
        self.assertEqual(intent.stuck_request("i'm stuck on lab 7", P.TASKS)[0]["id"], "t2")
        self.assertEqual(intent.stuck_request("i'm stuck", P.TASKS), (None, ""))
        self.assertEqual(intent.stuck_request("i'm stuck on my taxes", P.TASKS), (None, "my taxes"))   # still stuck: free first step
        self.assertIsNone(intent.stuck_request("help me with my resume", P.TASKS))

    def test_task_due_question(self):
        self.assertEqual(intent.task_due_question("when is lab 7 due", P.TASKS)["id"], "t2")
        self.assertIsNone(intent.task_due_question("when is my next deadline due", P.TASKS))


class MoreGuards(unittest.TestCase):
    def d(self, s):
        return R.decide(s, tasks=P.TASKS, now=NOW)

    def test_wants_that_are_not_errands(self):
        for s in ["i need a cover letter template", "need a better explanation of tcp", "i need a hint", "i need a new idea for my project", "need a plan for the week",
                  "i need a break", "i need a minute"]:
            self.assertNotEqual(self.d(s), "capture", s)

    def test_days_are_not_projects(self):
        for s in ["what did i do on monday", "what did i do last week", "what did i do in class", "what did i do today"]:
            self.assertNotEqual(self.d(s), "project", s)

    def test_start_needs_one_of_her_tasks(self):
        for s in ["starting salary for a soc analyst", "begin with the basics of tcp", "start the cloud lab tomorrow"]:
            self.assertNotEqual(self.d(s), "action", s)
        self.assertEqual(self.d("starting lab 7 now"), "action")

    def test_the_fifth(self):
        p = capture.detect("pay rent by the 5th", R.LISTS, NOW)
        self.assertTrue(p["due"].startswith("2026-12-05"), p)
        self.assertEqual(p["title"], "Pay rent")
        self.assertTrue(capture.detect("setup a reminder for the 15th to pay rent", R.LISTS, NOW)["due"].startswith("2026-11-15"))

    def test_questions_are_still_questions(self):
        for s in ["should i snooze this?", "what did i finish today", "is lab 7 done?", "when is my break", "what should i do about my landlord"]:
            self.assertNotIn(self.d(s), ("action", "capture"), s)


class Shorthand(unittest.TestCase):
    def test_spelled_out(self):
        self.assertEqual(plain.normalize("whats due tmrw"), "what's due tomorrow")
        self.assertEqual(plain.normalize("im stuck on my hw rn"), "i'm stuck on my homework right now")
        self.assertEqual(plain.normalize("Ill need to print it"), "i need to print it")
        self.assertEqual(plain.normalize("wut shud i do rn lol"), "what should i do right now")
        self.assertEqual(plain.normalize("whats due fri w my hw"), "what's due friday with my homework")
        self.assertEqual(plain.normalize("dunno what 2 do"), "don't know what to do")
        self.assertEqual(plain.normalize("heyyy"), "hey")

    def test_left_alone(self):
        for s in ["@free rename u to user in main.py", "open hw.pdf", "fix the typo in im.py"]:
            self.assertIn(s.split()[-1], plain.normalize(s))
        self.assertEqual(plain.normalize("@free hi"), "@free hi")

    def test_capture_title_from_shorthand(self):
        p = capture.detect(plain.normalize("can u remind me to call mom tmrw at 5pm?"), R.LISTS, NOW)
        self.assertEqual(p["title"], "Call mom")
        self.assertEqual(p["mode"], "reminder")
        self.assertTrue(p["due"].startswith("2026-11-11T17:00"))
        self.assertEqual(capture.detect("text me at 9am to take my meds", R.LISTS, NOW)["title"], "Take my meds")
        self.assertEqual(capture.detect("set a reminder for 5pm to stretch", R.LISTS, NOW)["title"], "Stretch")


class Calendar(unittest.TestCase):
    C = [{"start": "2026-11-10T17:30:00-05:00", "end": "2026-11-10T21:45:00-05:00", "label": "Class: Session 5: Cloud Application Security"},
         {"start": "2026-11-10T17:30:00-05:00", "end": "2026-11-10T18:00:00-05:00", "label": "Class: Test 4: Cloud Platform"},
         {"start": "2026-11-12T17:30:00-05:00", "end": "2026-11-12T21:45:00-05:00", "label": "Class: Class 5: Agentic AI"}]

    def a(self, s):
        return class_qa.answer(class_qa.parse(s), self.C, NOW)

    def test_class_today_and_next(self):
        self.assertIn("Yes, class today", self.a("do i have class today"))
        self.assertIn("Session 5", self.a("when is my next class"))
        self.assertIn("No class tomorrow", self.a("do i have class tomorrow"))

    def test_tests_come_from_the_calendar_or_fall_through(self):
        self.assertIn("Test 4", self.a("when is the test"))
        self.assertIsNone(class_qa.answer(class_qa.parse("when is the midterm"), [], NOW))

    def test_not_a_class_question(self):
        self.assertIsNone(class_qa.parse("what is a class in python"))


if __name__ == "__main__":
    unittest.main()
