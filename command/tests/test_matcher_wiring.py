"""The meaning matcher wired into the box (STATE_MODEL_MATCHER.md "Wiring"). A fake matcher stands in for Ollama."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_command import Base, RunResult  # noqa: E402
import command  # noqa: E402
import route_preview  # noqa: E402


class FakeMatcher:
    def __init__(self, label=None, routable=True, score=0.91):
        self.label, self.routable, self.score, self.asked = label, routable, score, []

    def classify(self, text):
        self.asked.append(text)
        if self.label is None:
            return None
        return {"label": self.label, "score": self.score, "margin": 0.1, "routable": self.routable, "top": []}


class Wired(Base):
    def use(self, m):
        self.r = command.CommandRunner(self.tmp / "cstate", router_factory=self.factory, load_config=lambda: self.config,
                                       sync=True, matcher=m)
        return m

    # a sentence no rule knows, so only the matcher can place it
    ODD = "gimme the lowdown on stuff i gotta knock out"

    def test_now_is_answered_by_the_engine_with_a_lead_line(self):
        self.use(FakeMatcher("now"))
        j = self.ask(self.ODD)
        self.assertEqual(j["status"], "done")
        self.assertTrue(j["answer"].startswith("I read that as: what should I do now."), j["answer"])
        self.assertIn("Do this now: Read Chapter 5", j["answer"])
        self.assertEqual(j["routing"], "meaning match · now 0.91 · no model")
        self.assertEqual(self.client.runs, [])
        self.assertEqual(self.client.decision_calls, 0)

    def test_schedule_answers_from_the_task_list(self):
        self.use(FakeMatcher("schedule"))
        j = self.ask(self.ODD)
        self.assertIn("I read that as a question about what's due.", j["answer"])
        self.assertTrue(j["routing"].startswith("meaning match · schedule"))
        self.assertEqual(self.client.runs, [])

    def test_reminders_lists_and_never_cancels(self):
        self.r.play_path = self.tmp / "play.json"
        m = self.use(FakeMatcher("reminders"))
        self.r.play_path = self.tmp / "play.json"
        j = self.ask(self.ODD)
        self.assertIn("I read that as: which reminders are waiting.", j["answer"])
        self.assertIn("No text reminders waiting", j["answer"])
        self.assertEqual(j["routing"], "meaning match · reminders 0.91 · no model")
        self.assertTrue(m.asked)

    def test_project_with_nothing_in_focus_asks_which(self):
        self.use(FakeMatcher("project"))
        self.r.play_path = self.tmp / "play.json"
        j = self.ask(self.ODD)
        self.assertIn("can't tell which one", j["answer"])

    def test_tiny(self):
        self.use(FakeMatcher("tiny"))
        self.assertEqual(self.ask(self.ODD)["answer"], "Got it. Ask what's next whenever you're ready.")

    def _routed(self):
        self.client.script = {"glm-5.3-flash-free": [RunResult(ok=True, text="Here is a plain answer for you.", session_id="s1")]}
        j = self.ask("explain what a subnet mask is in one sentence")
        self.assertFalse(j["routing"].startswith("meaning match"), j["routing"])
        return j

    def test_general_unsure_and_not_routable_go_to_the_router(self):
        for m in (FakeMatcher("general"), FakeMatcher(None), FakeMatcher("capture", routable=False)):
            self.use(m)
            self._routed()

    def test_rules_tags_followups_and_tasks_never_ask_the_matcher(self):
        m = self.use(FakeMatcher("tiny"))
        self.ask("what should I do now?")                 # a rule
        self.ask("@haiku explain what a subnet mask is")  # a tag
        self.ask("explain subnet masks", taskId="AAAAAAAA-1")
        self.assertEqual(m.asked, [])

    def test_a_crashing_matcher_never_takes_the_box_down(self):
        class Boom:
            def classify(self, text):
                raise RuntimeError("x")
        self.use(Boom())
        self._routed()

    def test_now_before_the_first_sync_answers_instead_of_crashing(self):
        self.use(FakeMatcher("now"))
        (self.tmp / "snap.json").unlink()
        j = self.ask(self.ODD)
        self.assertEqual(j["status"], "done")
        self.assertIn("can't read the snapshot", j["answer"])

    def test_no_matcher_by_default(self):
        self.assertIsNone(self.make().matcher)


class Preview(unittest.TestCase):
    def test_preview_matches_the_box(self):
        self.assertEqual(route_preview.decide(Wired.ODD, matcher=FakeMatcher("now")), "matcher:now")
        self.assertEqual(route_preview.decide("what should i do now", matcher=FakeMatcher("tiny")), "now")
        self.assertNotIn("matcher", route_preview.decide(Wired.ODD, matcher=FakeMatcher("general")))
        self.assertNotIn("matcher", route_preview.decide(Wired.ODD, matcher=FakeMatcher("capture", routable=False)))
        d = {}
        route_preview.decide(Wired.ODD, matcher=FakeMatcher("now", score=0.88), detail=d)
        self.assertEqual(d["score"], 0.88)


if __name__ == "__main__":
    unittest.main()
