import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import acts

T = [{"id": "a1111111", "title": "Read Chapter 5"}, {"id": "b2222222", "title": "Read Chapter 6"},
     {"id": "c3333333", "title": "Market ready todo list"}, {"id": "d4444444", "title": "Read Chapter 7"}]


def run(text, cur=None):
    calls = []
    plan = acts.parse(text, T, current_id=cur)
    out = acts.execute(plan, apply=lambda a, c: calls.append(a)) if plan else None
    return calls, out


class ActsTests(unittest.TestCase):
    def test_snooze_two_chapters_asks_which(self):
        calls, out = run("snooze read chapter 5 and 6")          # one task at a time: naming two asks, nothing moves
        self.assertEqual(calls, [])
        self.assertIsNone(out)                                  # no plan; the live box answers with "which one?" (test_live_contract)

    def test_pin_phrasings(self):
        for s in ("pin market ready todo list", "move market ready todo list to the top", "bring market ready todo list up"):
            self.assertEqual(run(s)[0], [["pin", "c3333333"]], s)

    def test_durations_and_tomorrow(self):
        self.assertEqual(run("snooze read chapter 5 for 3 hours")[0], [["snooze", "a1111111", "--hours", "3"]])
        self.assertEqual(run("snooze chapter 6 until tomorrow")[0][0][2], "--until")

    def test_current_task_and_unknown(self):
        self.assertEqual(run("snooze this", cur="d4444444")[0], [["snooze", "d4444444", "--hours", "1"]])
        calls, out = run("snooze lab 9")                 # not one of her tasks: nothing happens, and the caller says which button does it
        self.assertEqual(calls, [])
        self.assertIsNone(out)

    def test_moving_to_a_list_is_not_a_pin(self):
        self.assertIsNone(acts.parse("move market ready todo list to schoolwork", T))


if __name__ == "__main__":
    unittest.main()
