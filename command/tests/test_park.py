import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import park  # noqa
import capture  # noqa


class Park(unittest.TestCase):
    def test_ideas(self):
        cases = {
            "park this idea in playground: build a retro game launcher": "build a retro game launcher",
            "park a tool that sorts my screenshots in the playground": "tool that sorts my screenshots",
            "i have an idea for a golf swing tracker": "a golf swing tracker",
            "idea: local weather widget": "local weather widget",
            "put build a bot in the parking lot": "build a bot",
            "park: try a pi-hole at home": "try a pi-hole at home",
        }
        for text, want in cases.items():
            self.assertEqual(park.parse(text), want, text)

    def test_asked_to_park_but_gave_no_idea(self):
        self.assertEqual(park.parse("park this idea in playground"), "")

    def test_not_ideas(self):
        for t in ["save my notes", "how do I park a car", "what idea should I try?", "park", "", "remind me to email Dr. Lee"]:
            self.assertIsNone(park.parse(t), t)

    def test_an_idea_is_never_captured_as_a_task(self):
        self.assertIsNone(capture.detect("put build a bot in the parking lot", ["Personal"]))
        self.assertIsNone(capture.detect("put this idea in the playground: retro launcher", ["Personal"]))


if __name__ == "__main__":
    unittest.main()
