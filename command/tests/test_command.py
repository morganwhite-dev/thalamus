"""Offline tests for the command box. The real router runs against the router's own
FakeClient, so nothing here calls a model or costs usage.
Run from priority-brain:  python3 -m unittest discover -s command/tests"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "command", ROOT / "engine", ROOT / "router"):
    sys.path.insert(0, str(p))
import command  # noqa: E402
from router.core import Router, load_config as router_config  # noqa: E402
from router.opencode_client import RunResult  # noqa: E402
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location("router_fakes", ROOT / "router" / "tests" / "test_router.py")
_fakes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fakes)
FakeClient = _fakes.FakeClient

LONG = "\n".join(f"Step {i}: do a specific thing about the essay outline." for i in range(20))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmpd = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmpd.name)
        now = datetime.now().astimezone()
        self.tasks = [
            {"id": "AAAAAAAA-1", "title": "Read Chapter 5", "list": "Network Security", "dueDate": (now - timedelta(days=1)).isoformat()},
            {"id": "BBBBBBBB-2", "title": "Write the essay outline", "list": "Cloud Computing", "dueDate": (now + timedelta(hours=1)).isoformat(), "notes": "Use the rubric."},
            {"id": "CCCCCCCC-3", "title": "Apply to 10 internships", "list": "Internships", "dueDate": (now + timedelta(days=3)).isoformat()},
            {"id": "DDDDDDDD-4", "title": "Lab", "list": "Network Security"},
        ]
        (self.tmp / "snap.json").write_text(json.dumps({"schemaVersion": 1, "generatedAt": now.isoformat(), "tasks": self.tasks}))
        cfg = json.loads((ROOT / "engine" / "config.json").read_text())
        cfg.update(snapshotPath=str(self.tmp / "snap.json"), overridesPath=str(self.tmp / "ov.json"),
                   recommendationPath=str(self.tmp / "rec.json"), errorPath=str(self.tmp / "err.json"),
                   commitmentsPath=str(self.tmp / "none.json"))
        self.config = cfg
        self.client = FakeClient()
        self.routers = []

        def factory(engine_fn):
            rcfg = router_config()
            rcfg["workspace"] = str(self.tmp / "ws")
            r = Router(cfg=rcfg, client=self.client, state_dir=self.tmp / "rstate", priority_engine=engine_fn)
            self.routers.append(r)
            return r
        self.factory = factory
        self.r = self.make()

    def make(self):
        return command.CommandRunner(self.tmp / "cstate", router_factory=self.factory, load_config=lambda: self.config, sync=True)

    def tearDown(self):
        self.tmpd.cleanup()

    def ask(self, text, **kw):
        return self.r.submit({"text": text, **kw}, self.tasks)


class TestStep0(Base):
    def test_now_answered_by_engine_no_model(self):
        j = self.ask("what should I do now?")
        self.assertEqual(j["status"], "done")
        self.assertIn("Do this now: Read Chapter 5", j["answer"])
        self.assertIn("Why:", j["answer"])
        self.assertEqual(j["routing"], "engine · no model · step 0")
        self.assertEqual(self.client.runs, [])
        self.assertEqual(self.client.decision_calls, 0)

    def test_due_today_lists_window_and_missed(self):
        j = self.ask("what's due today")
        self.assertIn("Write the essay outline", j["answer"])
        self.assertIn("Missed and still open", j["answer"])
        self.assertNotIn("Apply to 10", j["answer"])
        self.assertEqual(self.client.runs, [])

    def test_due_windows(self):
        now = datetime(2026, 11, 5, 21, 0).astimezone()   # a Thursday
        s, e, label = command.due_window("this week", now)
        self.assertEqual((label, e.weekday(), e.hour), ("this week", 6, 23))
        s, e, label = command.due_window("tomorrow", now)
        self.assertEqual((label, s.day), ("tomorrow", 6))
        self.assertEqual(command.due_window("soon", now)[2], "in the next 7 days")

    def test_now_mentions_running_block(self):
        bv = {"phase": "work", "block": {"taskId": "CCCCCCCC-3", "title": "Apply to 10 internships"}}
        j = self.r.submit({"text": "what should I do now"}, self.tasks, bv)
        self.assertIn("You're in a block on: Apply to 10 internships", j["answer"])


class TestRouted(Base):
    def test_tagged_goes_to_that_tier_with_routing_line(self):
        j = self.ask("@haiku explain what a subnet mask is")
        self.assertEqual(j["status"], "done")
        self.assertTrue(j["routing"].startswith("haiku · claude-haiku-5-5 · effort low · ok · 1 attempt"))
        self.assertIn("tag @haiku", j["routing"])
        self.assertEqual(self.client.runs[0][0], "claude-code/claude-haiku-5-5")

    def test_job_records_the_routers_last_stage(self):
        j = self.ask("@haiku explain what a subnet mask is")
        self.assertEqual(j["stage"]["id"], "check")
        self.assertTrue(j["stageAt"])
        self.assertEqual(self.r.get(j["id"])["stage"]["id"], "check")

    def test_step0_has_no_stage(self):
        self.assertNotIn("stage", self.ask("what should I do now?"))

    def test_untagged_is_classified(self):
        self.client.script = {"glm-5.3-flash-free": [RunResult(ok=True, text="A subnet mask splits an IP address into network and host parts.", session_id="s1")]}
        j = self.ask("explain what a subnet mask is in one sentence")
        self.assertEqual(j["status"], "done")
        self.assertTrue(j["routing"].startswith("free · "), j["routing"])
        self.assertTrue(self.client.runs)

    def test_failed_big_tier_shows_error_no_retry(self):
        self.client.script = {"claude-sonnet-5-5": [RunResult(ok=False, error="rate limited", error_kind="rate_limit")]}
        j = self.ask("@sonnet draft a plan for the essay")
        self.assertEqual(j["status"], "failed")
        self.assertIn("rate", j["error"])
        self.assertIn("never retry", j["error"])
        self.assertEqual(len(self.client.runs), 1)

    def test_router_crash_is_reported(self):
        def boom(fn):
            raise RuntimeError("OpenCode is not running")
        self.r.router_factory = boom
        j = self.ask("@haiku hi there friend")
        self.assertEqual(j["status"], "failed")
        self.assertIn("OpenCode is not running", j["error"])

    def test_one_job_at_a_time(self):
        jobs = self.r._jobs()
        jobs.append({"id": "x", "status": "running", "input": "slow thing", "conversation": "c"})
        self.r._save_jobs(jobs)
        with self.assertRaises(command.Busy):
            self.ask("@haiku another")

    def test_interrupted_on_restart(self):
        self.r._save_jobs([{"id": "x", "status": "running", "input": "slow", "conversation": "c"}])
        r2 = self.make()
        self.assertEqual(r2.get("x")["status"], "interrupted")

    def test_input_limits(self):
        with self.assertRaises(ValueError):
            self.ask("   ")
        with self.assertRaises(ValueError):
            self.ask("x" * 5000)
        with self.assertRaises(ValueError):
            self.r.submit({"kind": "weird"}, self.tasks)


class TestResults(Base):
    def test_task_matching_order(self):
        t, how = command.match_task("help with Write the essay outline", self.tasks, block_task_id="CCCCCCCC-3")
        self.assertEqual((t["id"], how), ("BBBBBBBB-2", "named in the text"))
        t, how = command.match_task("help", self.tasks, explicit_id="AAAAAAAA-1")
        self.assertEqual(how, "chosen")
        t, how = command.match_task("anything", self.tasks, block_task_id="CCCCCCCC-3")
        self.assertEqual(how, "running block")
        t, how = command.match_task("the Lab", self.tasks)   # short titles never match by text
        self.assertIsNone(t)
        with self.assertRaises(ValueError):
            command.match_task("x", self.tasks, explicit_id="gone")

    def test_long_answer_saved_to_matching_task(self):
        self.client.script = {"claude-haiku-5-5": [RunResult(ok=True, text=LONG, session_id="s")]}
        j = self.ask("@haiku plan the steps for Write the essay outline")
        self.assertEqual(j["savedTo"], "BBBBBBBB-2")
        v = self.r.view(self.tasks, self.config)
        group = v["results"]["Schoolwork"][0]
        self.assertEqual(group["title"], "Write the essay outline")
        self.assertEqual(group["results"][0]["answer"], LONG)

    def test_short_answer_not_saved(self):
        j = self.ask("@haiku one word for Write the essay outline")
        self.assertIsNone(j["savedTo"])
        self.assertEqual(self.r.view(self.tasks, self.config)["results"], {})

    def test_long_without_task_has_note(self):
        self.client.script = {"claude-haiku-5-5": [RunResult(ok=True, text=LONG, session_id="s")]}
        j = self.ask("@haiku give me twenty steps")
        self.assertIsNone(j["savedTo"])
        self.assertIn("not saved", j["note"])

    def test_stuck_uses_free_prompt_and_always_saves(self):
        self.client.script = {"glm-5.3-flash-free": [RunResult(ok=True, text="Open the rubric and write the essay's first heading.", session_id="s")]}
        j = self.r.submit({"kind": "stuck", "taskId": "BBBBBBBB-2"}, self.tasks)
        self.assertEqual(j["status"], "done", j)
        self.assertEqual(j["savedTo"], "BBBBBBBB-2")
        self.assertTrue(j["routing"].startswith("free · "), j["routing"])
        self.assertIn("tag @free", j["routing"])
        self.assertEqual(j["input"], "Stuck on: Write the essay outline")

    def test_stuck_defaults_to_block_task(self):
        bv = {"phase": "work", "block": {"taskId": "CCCCCCCC-3", "title": "Apply to 10 internships"}}
        j = self.r.submit({"kind": "stuck"}, self.tasks, bv)
        self.assertEqual(j["taskId"], "CCCCCCCC-3")
        with self.assertRaises(ValueError):
            self.r.submit({"kind": "stuck"}, self.tasks)

    def test_stuck_said_as_a_sentence(self):
        self.client.script = {"glm-5.3-flash-free": [RunResult(ok=True, text="Open the rubric and write the essay's first heading.", session_id="s")]}
        j = self.r.submit({"text": "im stuck on the essay outline"}, self.tasks)          # names her task: same as the Stuck button
        self.assertEqual((j["kind"], j["taskId"]), ("stuck", "BBBBBBBB-2"), j)
        self.assertIn("tag @free", j["routing"])

    def test_stuck_on_something_not_on_a_list_stays_on_free_models(self):
        self.client.script = {"glm-5.3-flash-free": [RunResult(ok=True, text="Find last year's return and put it on the desk.", session_id="s")]}
        j = self.r.submit({"text": "i'm stuck on my taxes"}, self.tasks)
        self.assertEqual(j["status"], "done", j)
        self.assertIn("tag @free", j["routing"])
        self.assertEqual(j["input"], "i'm stuck on my taxes")

    def test_plain_sentences_answered_without_a_model(self):
        for text, routing in [("yes", "quick reply · no model"), ("done", "buttons · no model"), ("help", "quick reply · no model")]:
            j = self.r.submit({"text": text}, self.tasks)
            self.assertEqual((j["status"], j["routing"]), ("done", routing), text)

    def test_cap_moves_old_results_to_archive(self):
        for i in range(12):
            self.client.script = {"claude-haiku-5-5": [RunResult(ok=True, text=LONG + str(i), session_id="s")]}
            self.ask("@haiku again for Write the essay outline")
        items = json.loads((self.tmp / "cstate" / "results.json").read_text())["BBBBBBBB-2"]
        self.assertEqual(len(items), 10)
        self.assertEqual(len((self.tmp / "cstate" / "results-archive.jsonl").read_text().splitlines()), 2)

    def test_finished_task_results_kept(self):
        self.client.script = {"claude-haiku-5-5": [RunResult(ok=True, text=LONG, session_id="s")]}
        self.ask("@haiku plan Write the essay outline")
        v = self.r.view([t for t in self.tasks if t["id"] != "BBBBBBBB-2"], self.config)
        self.assertIn("Finished tasks", v["results"])

    def test_task_menu_carries_due_dates(self):
        menu = {t["taskId"]: t for t in self.r.view(self.tasks, self.config)["tasks"]}
        self.assertEqual(menu["AAAAAAAA-1"]["dueDate"], self.tasks[0]["dueDate"])
        self.assertNotIn("dueDate", menu["DDDDDDDD-4"])
        self.assertEqual(menu["AAAAAAAA-1"]["list"], "Network Security")  # the subject travels with every task

    def test_corrupt_results_reset_with_error(self):
        (self.tmp / "cstate" / "results.json").write_text("{nope")
        v = self.r.view(self.tasks, self.config)
        self.assertTrue(any("unreadable" in e for e in v["errors"]))
        self.assertTrue((self.tmp / "cstate" / "results.json.bad").exists())


class TestConversationAndLog(Base):
    def test_follow_up_reuses_conversation(self):
        a = self.ask("@haiku explain subnet masks briefly")
        b = self.ask("and give an example", followUp=True)
        self.assertEqual(a["conversation"], b["conversation"])
        self.assertIn("staying on", b["routing"])
        c = self.ask("@haiku something new entirely")
        self.assertNotEqual(c["conversation"], a["conversation"])
        self.assertIn("ses_x", self.client.archived)  # previous conversation's session archived

    def test_mission_log_merges_and_ends_on_now(self):
        hist = self.tmp / "history.jsonl"
        hist.write_text(json.dumps({"at": "2026-11-05T09:00:00-05:00", "type": "work_start", "title": "Read Chapter 5"}) + "\n")
        self.ask("@haiku hello there my friend")
        rec = {"current": {"title": "Read Chapter 5", "why": "Missed deadline"}}
        log = self.r.mission_log(hist, rec)
        self.assertEqual(log[0]["text"], "block started: Read Chapter 5")
        self.assertEqual(log[-2]["kind"], "command")
        self.assertIn("haiku · claude-haiku-5-5", log[-2]["text"])
        self.assertEqual(log[-1], {**log[-1], "kind": "now", "text": "now: Read Chapter 5 (Missed deadline)"})


class TestProjectStatus(Base):
    def setUp(self):
        super().setUp()
        import subprocess
        self.repo = self.tmp / "Analyzer"; self.repo.mkdir()
        for a in (("init", "-q"),):
            subprocess.run(["git", "-C", str(self.repo), *a], check=True, capture_output=True)
        (self.repo / "a.py").write_text("x")
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "add parser"], check=True, capture_output=True)
        self.tasks.append({"id": "SSSSSSSS-5", "title": "Traffic analyzer", "list": "Security Projects", "notes": f"path: {self.repo}"})
        self.tasks.append({"id": "SSSSSSSS-6", "title": "Mystery project", "list": "Side Projects"})
        self.r.play_path = self.tmp / "play.json"

    def test_update_status_reads_folder_saves_line_no_model(self):
        j = self.ask("update the status of Traffic analyzer project")
        self.assertEqual(j["status"], "done")
        self.assertIn("Traffic analyzer: Building parser · just now", j["answer"])
        self.assertEqual(j["routing"], "project status · no model")
        self.assertEqual((self.client.runs, self.client.decision_calls), ([], 0))
        saved = json.loads((self.tmp / "play.json").read_text())["leftOff"]["SSSSSSSS-5"]["text"]
        self.assertTrue(saved.startswith("Building parser"))

    def test_no_folder_and_unknown_project_say_so(self):
        j = self.ask("update the status of Mystery project")
        self.assertIn("Couldn't find a folder", j["answer"]); self.assertIn("path:", j["answer"])
        self.assertIn("don't see a project", self.ask("status of banana")["answer"])


if __name__ == "__main__":
    unittest.main()
