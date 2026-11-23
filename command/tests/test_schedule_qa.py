import json, sys, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "engine"))
import schedule_qa as S  # noqa
from brain_engine import parse_dt  # noqa

TZ = timezone(timedelta(hours=-5))
NOW = datetime(2026, 11, 8, 10, 0, tzinfo=TZ)        # Sunday
CFG = json.loads((HERE.parent / "engine" / "config.json").read_text())


def t(title, lst, due):
    return {"id": title, "title": title, "list": lst, "dueDate": due}


TASKS = [t("Lab 7", "Network Security", "2026-11-11T22:00:00-05:00"), t("Read Ch 7", "Network Security", "2026-11-12T17:30:00-05:00"),
         t("AWS Lab 4", "Cloud Computing", "2026-11-08T23:59:00-05:00"), t("Mid-Term", "Cloud Computing", "2026-11-06T18:30:00-05:00"),
         t("Apply: Acme", "Internships", "2026-11-15T12:00:00-05:00"), t("Golf", "Play", None)]


def ask(text):
    q = S.parse(text, CFG, NOW)
    return None if q is None else S.answer(q, TASKS, CFG, NOW, parse_dt)


class Parse(unittest.TestCase):
    def test_schedule_questions(self):
        for x in ["whats due next week in network security", "what's overdue", "how many things are due this week",
                  "when is my next deadline", "what do i have left for internships", "what's due friday"]:
            self.assertIsNotNone(S.parse(x, CFG, NOW), x)

    def test_not_schedule_questions(self):
        for x in ["what should I do now", "remind me to do homework", "do you have teaching notes for module 5",
                  "explain module 5", "what's the capital of France", "", "hi"]:
            self.assertIsNone(S.parse(x, CFG, NOW), x)


class Answers(unittest.TestCase):
    def test_next_week_in_one_class(self):
        a = ask("whats due next week in network security")
        self.assertIn("Due next week in Network Security (2)", a)
        self.assertIn("Lab 7", a); self.assertNotIn("AWS Lab 4", a)

    def test_empty_window_says_so(self):
        a = ask("what's due friday in internships")
        self.assertIn("Nothing due Friday in Internships", a)

    def test_overdue_filtered(self):
        a = ask("what's overdue in cloud")
        self.assertIn("Overdue in Cloud Computing (1)", a); self.assertIn("Mid-Term", a)
        self.assertEqual(ask("what's overdue in internships"), "Nothing overdue in Internships.")

    def test_next_deadline_and_count(self):
        self.assertIn("AWS Lab 4", ask("when is my next deadline"))
        self.assertEqual(ask("how many things are due this week"), "1 thing due this week.")

    def test_school_means_both_classes(self):
        a = ask("what's due next week for school")
        self.assertIn("Lab 7", a); self.assertNotIn("Acme", a)

    def test_left_lists_everything_open_in_topic(self):
        a = ask("what do i have left for internships")
        self.assertIn("1 with a deadline", a); self.assertIn("Acme", a)


if __name__ == "__main__":
    unittest.main()
