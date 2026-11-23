"""Contract tests on the LIVE path: dashboard/server.py submit_command -> CommandRunner.submit, every write intercepted
(see live_box.py). The unit tests for typed.py and acts.py did not catch crashes and wrong targets that only show up
here, so every action table and every must-not-act sentence runs through the real entry point."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
for p in (HERE, HERE.parent, ROOT / "engine", ROOT / "play", ROOT / "router", ROOT / "prep"):
    sys.path.insert(0, str(p))
from live_box import LISTS, LiveBox  # noqa: E402
import phrasings as P  # noqa: E402
import typed_cases as C  # noqa: E402
import acts, capture, intent, plain, route_preview as R, typed  # noqa: E402

CUR = "t1"                                                    # "Read Chapter 5" is on the Do this now card
ACTING = ("pin", "unpin", "snooze", "skip")                   # the only typed actions that write
MULTI = P.TASKS + [{"id": "t7", "title": "Lab 7", "list": "Network Security"},
                   {"id": "t8", "title": "Read Chapter 6", "list": "Network Security"},
                   {"id": "t9", "title": "Prep for Lab 7 and Read Chapter 6", "list": "Network Security"}]
TZ = timezone(timedelta(hours=-5))
TEN_AM = datetime(2026, 11, 10, 10, 0, tzinfo=TZ)

# Inputs from the reviews that must never write anything (engine overrides or the Play store).
MUST_NOT_ACT = [
    "pin missing chore", "skip this?", "snooze until 5:99pm", "snooze everything", "skip everything", "skip all", "snooze all of them",
    "wake me at 7am", "should i skip this?", "should i snooze this?", "what if I skip this", "is this pinned", "is this one done?",
    "wait, skip this?", "oh, snooze this?", "what if I built a birdhouse?", "I had some idea about X", "i had any idea about the bug",
    "I had no idea about the outage", "snooze for 999999999999999999 hours", "unpin everything", "snooze button not working",
    "add build a website with login", "remind me to debug the login flow", "remind me to draft a cover letter",
    "what does a tcp handshake look like today", "yes?", "hey, yeah but make it friday",
]
EXTRA_ACT = {                                                 # sentence -> engine writes, with P.TASKS and CUR
    "un-pin lab 7": [["unpin", "t2"]], "unpin lab 7": [["unpin", "t2"]], "pin lab 7": [["pin", "t2"]],
    "skip the lab": [["skip", "t2"]], "can you skip this": [["skip", "t1"]], "can you skip this?": [["skip", "t1"]],
    "could you snooze this for an hour?": [["snooze", "t1", "--hours", "1"]], "please pin this": [["pin", "t1"]],
    "snooze for six hours": [["snooze", "t1", "--hours", "6"]], "snooze for two days": [["snooze", "t1", "--hours", "48"]],
    "snooze for a few hours": [["snooze", "t1", "--hours", "3"]], "snooze for a couple hours": [["snooze", "t1", "--hours", "2"]],
    "snooze this for twelve hours": [["snooze", "t1", "--hours", "12"]], "snooze it for 3 hours": [["snooze", "t1", "--hours", "3"]],
    "skip it": [["skip", "t1"]], "snooze lab 7 for an hour": [["snooze", "t2", "--hours", "1"]],
}


def all_sentences():
    out = [s for items in C.ACTIONS.values() for s in items] + list(C.NOT_ACTIONS) + MUST_NOT_ACT + list(EXTRA_ACT)
    for items in P.CASES.values():
        out += items
    seen, uniq = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


def expected_ids(s, tasks, cur=CUR):
    """The task ids a typed action may write to, or [] when it must not write."""
    ta = typed.parse_action(plain.normalize(s), tasks)
    if not ta or ta["action"] not in ACTING or ta.get("problem") or ta["args"].get("all"):
        return []
    return ta.get("task_ids") or [ta["task_id"] or cur]


class LiveContract(unittest.TestCase):
    def test_a_every_table_sentence_runs_without_error(self):
        broken = []
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in all_sentences():
                try:
                    out = box.send(s)
                except Exception as e:                  # noqa: BLE001 - the contract is "never raises"
                    broken.append((s, f"{type(e).__name__}: {e}"))
                    continue
                if out.get("status") == "error":
                    broken.append((s, out.get("error")))
        self.assertEqual(broken, [])

    def test_a_must_not_act_sentences_write_nothing(self):
        wrote = []
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in list(C.NOT_ACTIONS) + MUST_NOT_ACT:
                box.send(s)
                if box.writes or box.play_writes:
                    wrote.append((s, box.writes, len(box.play_writes)))
        self.assertEqual(wrote, [])

    def test_b_preview_action_sentences_act_on_the_right_task_or_reply(self):
        wrong = []
        for tasks in (P.TASKS, MULTI):
            with LiveBox(tasks, current=CUR) as box:
                for s in all_sentences():
                    if R.decide(s, tasks=tasks) != "action":
                        continue
                    out = box.send(s)
                    if "capture" in out or not (out.get("answer") or "").strip():
                        wrong.append((s, "no reply"))
                        continue
                    want = expected_ids(s, tasks)
                    got = [w[1] for w in box.writes]
                    if got and sorted(got) != sorted(want):
                        wrong.append((s, got, want))
                    if want and not got:
                        wrong.append((s, "expected a write", want))
        self.assertEqual(wrong, [])

    def test_named_actions_write_exactly_this(self):
        wrong = []
        with LiveBox(P.TASKS, current=CUR) as box:
            for s, want in EXTRA_ACT.items():
                box.send(s)
                if box.writes != want:
                    wrong.append((s, box.writes, want))
        self.assertEqual(wrong, [])


class Targets(unittest.TestCase):
    def test_no_match_and_bulk_reply_without_acting(self):
        with LiveBox(P.TASKS, current=CUR) as box:
            out = box.send("pin missing chore")
            self.assertEqual(box.writes, [])
            self.assertIn("missing chore", out["answer"])
            for s in ("snooze everything", "skip all"):
                out = box.send(s)
                self.assertEqual(box.writes, [], s)
                self.assertIn("one task at a time", out["answer"], s)

    def test_a_vague_name_lists_the_options(self):
        with LiveBox(MULTI, current=CUR) as box:
            out = box.send("skip the lab")
            self.assertEqual(box.writes, [])
            self.assertIn("Lab 7", out["answer"])

    def test_several_tasks_prefer_an_exact_title_else_ask(self):
        with LiveBox(MULTI, current=CUR) as box:
            out = box.send("pin lab 7 and read chapter 6")
            self.assertEqual(box.writes, [])
            self.assertIn("Prep for Lab 7 and Read Chapter 6", out["answer"])
            box.send("pin prep for lab 7 and read chapter 6")
            self.assertEqual(box.writes, [["pin", "t9"]])
            box.send("pin lab 7")
            self.assertEqual(box.writes, [["pin", "t7"]])                  # "Lab 7" is an exact title
        with LiveBox(P.TASKS + [{"id": "t8", "title": "Read Chapter 6", "list": "Network Security"}], current=CUR) as box:
            out = box.send("snooze read chapter 5 and 6")                 # two tasks named: ask which, never act on both
            self.assertEqual(box.writes, [])
            self.assertIn("Read Chapter 6", out["answer"])

    def test_questions_reply_and_requests_act(self):
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in ("skip this?", "should i skip this?", "wait, skip this?", "what if i skip this"):
                out = box.send(s)
                self.assertEqual(box.writes, [], s)
                self.assertTrue((out.get("answer") or "").strip(), s)
            box.send("could you snooze this for an hour?")
            self.assertEqual(box.writes, [["snooze", "t1", "--hours", "1"]])


class Times(unittest.TestCase):
    def test_past_until_is_refused(self):
        for s in ("snooze until today", "snooze till 8am today", "snooze until 9:30am today"):
            ta = typed.parse_action(s, P.TASKS, TEN_AM)
            self.assertTrue(ta and ta.get("problem"), s)
            plan, msg = acts.plan_or_problem(s, P.TASKS, current_id=CUR, now=TEN_AM)
            self.assertIsNone(plan, s)
            self.assertIn("later time", msg, s)
        self.assertEqual(typed.parse_action("snooze until 5pm", P.TASKS, TEN_AM)["args"]["until"], "2026-11-10T17:00-05:00")
        plan, _ = acts.plan_or_problem("snooze until 9am", P.TASKS, current_id=CUR, now=TEN_AM)   # 9 AM has passed: tomorrow's
        self.assertTrue(plan and plan["until"].startswith("2026-11-11T09:00"), plan)

    def test_bad_time_replies(self):
        plan, msg = acts.plan_or_problem("snooze until 5:99pm", P.TASKS, current_id=CUR, now=TEN_AM)
        self.assertIsNone(plan)
        self.assertIn("couldn't read that time", msg)

    def test_engine_refuses_a_past_until(self):
        import brain
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            now = datetime.now().astimezone()
            (d / "snap.json").write_text(json.dumps({"schemaVersion": 1, "generatedAt": now.isoformat(),
                                                     "tasks": [{"id": "AAAAAAAA-1", "title": "Read", "list": "Personal"}]}))
            cfg = json.loads((ROOT / "engine" / "config.json").read_text())
            cfg.update(snapshotPath=str(d / "snap.json"), overridesPath=str(d / "ov.json"), recommendationPath=str(d / "rec.json"),
                       errorPath=str(d / "err.json"), commitmentsPath=str(d / "none.json"))
            (d / "cfg.json").write_text(json.dumps(cfg))
            past = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
            with self.assertRaises(SystemExit):
                brain.main(["--config", str(d / "cfg.json"), "snooze", "AAAAAAAA-1", "--until", past])
            with self.assertRaises(SystemExit):
                brain.main(["--config", str(d / "cfg.json"), "snooze", "AAAAAAAA-1", "--hours", "0"])
            self.assertFalse((d / "ov.json").exists())
            later = (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
            brain.main(["--config", str(d / "cfg.json"), "snooze", "AAAAAAAA-1", "--until", later])
            self.assertEqual(len(json.loads((d / "ov.json").read_text())["snoozes"]), 1)


class Capture(unittest.TestCase):
    def test_coding_and_writing_work_are_not_tasks(self):
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in ("add build a website with login", "remind me to debug the login flow", "remind me to draft a cover letter",
                      "add a function to parse dates", "remind me to refactor the repo", "add write my essay draft"):
                self.assertNotIn("capture", box.send(s), s)
                self.assertNotEqual(R.decide(s), "capture", s)

    def test_errands_still_capture(self):
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in ("pay for my gym program", "call the clinic about tests for allergies", "buy a python book", "email the task force",
                      "call about the test results", "call mom", "put this year's tax forms on my list", "remind me to update my resume",
                      "go to class with sam friday"):
                self.assertIn("capture", box.send(s), s)
                self.assertEqual(R.decide(s), "capture", s)

    def test_edit_shaped_needs_it_or_that(self):
        for s in ("make it saturday", "set it to friday", "move it to internships", "call it Email Bob", "rename that to X", "put it in school"):
            self.assertIsNone(capture.detect(s, R.LISTS), s)
        self.assertIsNotNone(capture.detect("put this year's tax forms on my list", R.LISTS))

    def test_reminder_wording(self):
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in ("reminder for 5pm to stretch", "setup a reminder for 5pm to stretch"):
                p = box.send(s)["capture"]
                self.assertEqual((p["mode"], p["title"]), ("reminder", "Stretch"), s)
            p = box.send("wake me at 7am")["capture"]
            self.assertEqual((p["mode"], p["title"], p["due"][11:16]), ("reminder", "Wake up", "07:00"))
            self.assertEqual(box.writes, [])

    def test_sector_open_runs_the_same_pre_capture_rules(self):
        with LiveBox(P.TASKS, current=CUR) as box:
            out = box.send("analyzer status", sector="security")
            self.assertNotIn("capture", out)
            self.assertIn("project status", out.get("routing", ""))
            self.assertEqual(R.decide("analyzer status", sector="security"), "project")
            for s in ("I had no idea about the outage", "idea: a plant bot", "where did i leave off on the analyzer", "skip this"):
                self.assertNotIn("capture", box.send(s, sector="personal"), s)
                self.assertNotEqual(R.decide(s, sector="personal"), "capture", s)
            self.assertIn("capture", box.send("buy stamps", sector="personal"))
            self.assertEqual(R.decide("buy stamps", sector="personal"), "capture")


class Routing(unittest.TestCase):
    def test_look_like_needs_a_schedule_subject(self):
        with LiveBox(P.TASKS, current=CUR) as box:
            out = box.send("what does a tcp handshake look like today")
            self.assertNotIn("schedule", out.get("routing", ""))
        self.assertNotEqual(R.decide("what does a tcp handshake look like today"), "schedule")
        for s in ("what does my week look like", "what does my day look like", "what does my schedule look like for friday", "what does tomorrow look like"):
            self.assertEqual(R.decide(s), "schedule", s)

    def test_park_needs_idea_wording(self):
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in ("what if I built a birdhouse?", "what if i built a golf swing tracker", "I had some idea about X", "I had no idea about the outage",
                      "i had any idea about it", "thought i'd go out later"):
                box.send(s)
                self.assertEqual(box.play_writes, [], s)
            for s in ("idea: a birdhouse", "i have an idea for a birdhouse", "park this: a birdhouse", "put a birdhouse in the parking lot"):
                box.send(s)
                self.assertEqual(len(box.play_writes), 1, s)


class Replies(unittest.TestCase):
    def test_lead_words_and_question_marks(self):
        r = typed.parse_reply("hey, yeah but make it friday", C.PENDING, TEN_AM)
        self.assertTrue(r and r["kind"] == "edit" and r["confirm"])
        self.assertIsNone(typed.parse_reply("yes?", C.PENDING, TEN_AM))
        self.assertIsNone(typed.parse_reply("ok?", C.PENDING, TEN_AM))
        self.assertEqual(typed.parse_reply("yes", C.PENDING, TEN_AM), {"kind": "yes"})


if __name__ == "__main__":
    unittest.main()


class EdgeCases(unittest.TestCase):
    def test_code_work_pattern_has_no_backspace(self):
        import capture
        self.assertNotIn("\x08", capture.CODE_WORK.pattern)
        self.assertIsNotNone(capture.detect("go to class with sam friday", LISTS))

    def test_questions_and_remarks_about_actions_reply_without_acting(self):
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in ("is this pinned?", "skip this?", "should i snooze this?", "what if i skip lab 7", "snooze button not working"):
                out = box.send(s)
                self.assertEqual(box.writes, [], s)
                self.assertNotIn("capture", out, s)
            self.assertIn("question", box.send("skip this?")["answer"])

    def test_dated_writing_and_course_words_are_still_tasks(self):
        import capture
        d = capture.detect("remind me to write my essay friday", LISTS)
        self.assertEqual(d and d["title"], "Write my essay")
        d = capture.detect("remind me to email prof about the api project tomorrow", LISTS)
        self.assertEqual(d and d["title"], "Email prof about the api project")
        self.assertIsNone(capture.detect("remind me to fix the api", LISTS))


class JobIds(unittest.TestCase):
    def test_two_commands_in_one_second_never_share_an_id(self):
        import command as cmd
        ids = iter(["aaaa" * 8, "aaaa" * 8, "bbbb" * 8])
        real = cmd.uuid.uuid4

        class U:
            def __init__(self, h):
                self.hex = h
        with LiveBox(P.TASKS, current=CUR) as box:
            cmd.uuid.uuid4 = lambda: U(next(ids))
            try:
                a = box.send("what's a vlan")
                b = box.send("what's a subnet")
            finally:
                cmd.uuid.uuid4 = real
            self.assertNotEqual(a["id"], b["id"])
            self.assertEqual(b["status"], "done", b)


# ------------------------------------------------------------------------------------------- round 3 (Codex re-check at 9296bc2)
REMINDERS = '{"reminders": [{"id": "r1", "text": "stretch", "at": "2099-12-01T09:00-05:00"}], "projects": []}'
CJK = P.TASKS + [{"id": "tj", "title": "買い物", "list": "Personal"}]
LAB_FRI = P.TASKS + [{"id": "ta", "title": "Lab 7", "list": "Network Security"}, {"id": "tb", "title": "Lab 7 Friday", "list": "Network Security"}]
TWO = P.TASKS + [{"id": "t7", "title": "Lab 7", "list": "Network Security"}, {"id": "t8", "title": "Read Chapter 6", "list": "Network Security"}]


class Round3Questions(unittest.TestCase):
    QUESTIONS = ["skip this?!", "add buy milk?!", "park this idea: birdhouse?!", "cancel reminder to stretch?",
                 "update the status of network traffic analyzer?", "skip this? 🙂", "pin this ?!.", 'snooze this?"', "skip this ?? !!",
                 "remind me to call mom?!", "idea: a birdhouse?!", "delete my reminder about stretch?", "pin lab 7?!"]

    def test_is_question_shapes(self):
        for s in ("skip this?", "skip this?!", "skip this ?!.", "skip this? 🙂", 'did he say "skip this?"', "ok?!!", "hm? ", "skip this?”"):
            self.assertTrue(plain.is_question(s), s)
        for s in ("skip this", "could you skip this?", "hey, could you skip this?", "Hey, could you skip this?", "please can you pin this?!",
                  "what? no, skip this", ""):
            self.assertFalse(plain.is_question(s), s)

    def test_questions_never_write_on_the_live_path(self):
        wrote = []
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in self.QUESTIONS:
                box.runner.play_path.write_text(REMINDERS)
                out = box.send(s)
                if box.writes or box.play_writes or "capture" in out:
                    wrote.append((s, box.writes, len(box.play_writes), "capture" in out))
                self.assertTrue((out.get("answer") or out.get("capture") or "") != "", s)
        self.assertEqual(wrote, [])

    def test_polite_request_after_a_greeting_acts(self):
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in ("Hey, could you skip this?", "hey could you skip this?", "ok so can you skip this?", "hi, would you skip this?!"):
                box.send(s)
                self.assertEqual(box.writes, [["skip", "t1"]], s)

    def test_question_reply_is_never_a_confirmation(self):
        for s in ("yeah but just text me?", "yes, make it friday?", "ok add it?!", "yes?!"):
            r = typed.parse_reply(s, C.PENDING, TEN_AM)
            self.assertFalse(r and (r.get("kind") == "yes" or r.get("confirm")), (s, r))


class Round3Targets(unittest.TestCase):
    def test_several_tasks_named_ask_and_write_nothing(self):
        for tasks in (TWO, MULTI):
            with LiveBox(tasks, current=CUR) as box:
                for s in ("pin lab 7 and read chapter 6", "snooze read chapter 5 and 6", "skip lab 7, read chapter 6", "unpin lab 7 & read chapter 6"):
                    out = box.send(s)
                    self.assertEqual(box.writes, [], (s, out.get("answer")))
                    self.assertIn("Read Chapter 6", out.get("answer", ""), s)

    def test_non_ascii_names_compare_on_real_characters(self):
        with LiveBox(CJK, current=CUR) as box:
            out = box.send("pin 买东西")
            self.assertEqual(box.writes, [])
            self.assertIn("买东西", out["answer"])
            box.send("pin 買い物")
            self.assertEqual(box.writes, [["pin", "tj"]])
        self.assertIsNone(intent.find_task("！！", CJK))          # no letters left: an empty name never matches
        self.assertIsNone(intent.find_task("买东西", CJK))
        self.assertEqual((intent.find_task("買い物", CJK) or {}).get("id"), "tj")

    def test_snooze_needs_a_readable_time(self):
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in ("snooze until", "snooze till", "snooze this until", "snooze for", "snooze lab 7 until", "postpone until"):
                out = box.send(s)
                self.assertEqual(box.writes, [], s)
                self.assertIn("time", out["answer"].lower(), s)

    def test_exact_full_title_wins_over_a_date_split(self):
        with LiveBox(LAB_FRI, current=CUR) as box:
            box.send("snooze Lab 7 Friday")
            self.assertEqual(box.writes, [["snooze", "tb", "--hours", "1"]])
            box.send("snooze Lab 7 until Friday")
            self.assertEqual([w[:3] for w in box.writes], [["snooze", "ta", "--until"]])
        amb = P.TASKS + [{"id": "ta", "title": "Lab 7", "list": "Network Security"}, {"id": "tc", "title": "Lab 7 Friday prep", "list": "Network Security"}]
        with LiveBox(amb, current=CUR) as box:
            out = box.send("snooze lab 7 friday")
            self.assertEqual(box.writes, [])
            self.assertIn("Lab 7 Friday prep", out["answer"])


class Round3Routes(unittest.TestCase):
    def test_schedule_questions_answer_the_same_with_a_sector_open(self):
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in ("any exams today", "anything due tomorrow", "is there a quiz this week", "any labs left", "do i have class today"):
                closed = R.decide(s, tasks=P.TASKS)
                for sec in ("personal", "school", "play", "security", "intern"):
                    self.assertNotIn("capture", box.send(s, sector=sec), (s, sec))
                    self.assertEqual(R.decide(s, tasks=P.TASKS, sector=sec), closed, (s, sec))

    def test_general_knowledge_look_like_is_not_a_schedule(self):
        for s in ("what does a TCP handshake look like for tomorrow's demo?", "what does a tcp handshake look like for tomorrow",
                  "what does a subnet mask look like for my class"):
            self.assertNotEqual(R.decide(s), "schedule", s)
            with LiveBox(P.TASKS, current=CUR) as box:
                self.assertNotIn("schedule", box.send(s).get("routing", ""), s)
        for s in ("what does tomorrow look like", "what does my week look like", "what does my schedule look like for friday",
                  "what's it look like for tomorrow", "what does today look like?"):
            self.assertEqual(R.decide(s), "schedule", s)

    def test_writing_work_by_verb_and_errands_by_verb(self):
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in ("add draft an email to the hiring manager", "remind me to write a thank you note to the recruiter",
                      "add compose a linkedin post about my internship", "add rewrite my bio"):
                self.assertNotIn("capture", box.send(s), s)
                self.assertNotEqual(R.decide(s), "capture", s)
            for s in ("buy a book about algorithms", "order a usb drive for my scripts", "pay for the api course", "email the recruiter"):
                self.assertIn("capture", box.send(s), s)
                self.assertEqual(R.decide(s), "capture", s)

    def test_preview_follows_the_live_fallback_for_generic_lookups(self):
        s = "can you show me my reminders?"
        with LiveBox(P.TASKS, current=CUR) as box:
            out = box.send(s)
        self.assertEqual(R.decide(s), "reminders")
        self.assertIn("reminders", out["routing"])
        cfg = {"lookup": {"roots": [], "extensions": ["pdf"]}}
        self.assertNotEqual(R.decide("find my birdhouse plans", config=cfg), "lookup")


class Round3Robust(unittest.TestCase):
    BAD_NUMBERS = ["add stretch 0 times a week", "add stretch 99 times a week", "study plan for stretch " + "9" * 310 + " hours: warm up",
                   "snooze for " + "9" * 310 + " hours", "add read " + "9" * 400 + " minutes a day", "remind me in " + "9" * 50 + " hours to stretch",
                   "i started " + "9" * 320 + " minutes ago", "add " + "9" * 320 + " more minutes", "do tryhackme " + "9" * 320 + " times a week"]

    def test_bad_numbers_reply_without_raising(self):
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in self.BAD_NUMBERS:
                out = box.send(s)
                self.assertNotEqual(out.get("status"), "error", s)
                self.assertEqual(box.writes, [], s)

    ADVERSARIAL = [
        "create a" + " " * 3900 + "milk", "park" + " " * 240 + "?!", "remind me to " + " " * 1990 + "x", "pin " + "lab " * 500,
        "skip" + "?!" * 1000, "a" + "." * 2000, "x" * 2000, "study plan for" + " " * 2000 + "x:", "i have an idea " + "for " * 500,
        "a," * 1000, "add\t" * 500 + "milk", "park this idea" + ":" * 1000, 'call it "' + "a" * 1990, "snooze for " + "9" * 2000 + " hours",
        "add " + "- " * 1000, "do " * 700, "pin " + "x and " * 400, "study plan for x:" + "\n   " * 500, "remind me to" + " \t " * 600 + "?",
        "what " * 400 + "is due", "hey, " * 400 + "skip this", "idea" + " -" * 900, "snooze until " + "tomorrow " * 200,
        "cancel " + "the " * 600 + "reminder", "where did i leave off on " + "x " * 900, "find " + "my " * 900 + "resume",
    ]

    def test_every_rule_is_fast_on_adversarial_input(self):
        import time
        import class_qa, lookup, park, reminders_qa, schedule_qa, project_status
        pend = dict(C.PENDING)
        rules = {
            "normalize": plain.normalize, "is_question": plain.is_question, "capture": lambda s: capture.detect(s, LISTS),
            "capture.sector": lambda s: capture.detect(s, LISTS, sector="personal"), "park": park.parse,
            "typed.action": lambda s: typed.parse_action(s, P.TASKS), "typed.reply": lambda s: typed.parse_reply(s, pend),
            "typed.offer": lambda s: typed.question_offer(s, P.TASKS), "before_capture": lambda s: intent.before_capture(s, P.TASKS),
            "reminders": reminders_qa.parse, "schedule": lambda s: schedule_qa.parse(s, None), "class": class_qa.parse, "lookup": lookup.detect,
            "project": project_status.parse_intent, "project.bare": project_status.is_bare, "planning": lambda s: intent.planning_fallback(s, P.TASKS, LISTS),
            "acts": lambda s: acts.plan_or_problem(s, P.TASKS, current_id=CUR), "preview": lambda s: R.decide(s, tasks=P.TASKS),
        }
        slow = []
        for s in self.ADVERSARIAL:
            for x in (s, plain.normalize(s)):
                for name, fn in rules.items():
                    t0 = time.perf_counter()
                    try:
                        fn(x)
                    except Exception as e:                      # noqa: BLE001 - the contract is "never raises"
                        slow.append((name, x[:30], type(e).__name__))
                    dt = (time.perf_counter() - t0) * 1000
                    if dt > 50:
                        slow.append((name, x[:30], round(dt)))
        self.assertEqual(slow, [])

    def test_adversarial_input_on_the_live_path(self):
        import time
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in self.ADVERSARIAL:
                t0 = time.perf_counter()
                out = box.send(s)
                self.assertLess(time.perf_counter() - t0, 1.0, s[:30])
                self.assertNotEqual(out.get("status"), "error", s[:30])


class Round3JobIds(unittest.TestCase):
    def test_instant_and_project_jobs_never_share_an_id(self):
        import command as cmd
        real = cmd.uuid.uuid4

        class U:
            hex = "aaaa" * 8
        with LiveBox(P.TASKS, current=CUR) as box:
            cmd.uuid.uuid4 = lambda: U()
            try:
                seen = set()
                for s in ("hello", "thanks", "where was i on the network traffic analyzer", "how's the network traffic analyzer going", "hi"):
                    jid = None
                    try:
                        jid = box.send(s)["id"]
                    finally:
                        pass
                    self.assertNotIn(jid, seen, s)
                    seen.add(jid)
            finally:
                cmd.uuid.uuid4 = real


# ------------------------------------------------------------------ round 4: when a rule is not sure, it replies or falls through; it never writes
REM2 = ('{"reminders": [{"id": "r1", "text": "stretch", "at": "2099-12-01T09:00-05:00"},'
        ' {"id": "r2", "text": "Return book order", "at": "2099-12-01T09:00-05:00"}], "projects": []}')
REM1 = '{"reminders": [{"id": "r1", "text": "stretch", "at": "2099-12-01T09:00-05:00"}], "projects": []}'
HOMEWORK = CJK + [{"id": "h1", "title": "Submit homework", "list": "Personal"}, {"id": "h2", "title": "Submit homework today", "list": "Personal"}]


class Round4SharedMatcher(unittest.TestCase):
    def test_match_target_rules(self):
        items = [{"title": "stretch"}, {"title": "Return book order"}, {"title": "買い物"}, {"title": "Submit homework"}, {"title": "Submit homework today"}]
        self.assertEqual(plain.match_target("买东西", items), ("none", []))
        self.assertEqual(plain.match_target("textbook order", items), ("none", []))
        self.assertEqual(plain.match_target("", items), ("none", []))
        self.assertEqual(plain.match_target("！！ 🙏", items), ("none", []))
        self.assertEqual(plain.match_target("ＳＴＲＥＴＣＨ", items)[1]["title"], "stretch")          # full-width letters fold
        self.assertEqual(plain.match_target("Submit homework today", items)[1]["title"], "Submit homework today")
        self.assertEqual(plain.match_target("submit homework", items)[1]["title"], "Submit homework")
        kind, opts = plain.match_target("homework", items)
        self.assertEqual((kind, len(opts)), ("many", 2))
        self.assertEqual(plain.match_target("book", items)[1]["title"], "Return book order")

    def test_reminder_cancel_never_deletes_an_unrelated_reminder(self):
        with LiveBox(P.TASKS, current=CUR) as box:
            box.runner.play_path.write_text(REM2)
            box.send("Could you cancel the textbook order?")                    # "textbook" is not "text" + "book": not a reminder at all
            self.assertEqual(box.play_writes, [])
            for s in ("cancel reminder to 买东西", "cancel my reminder", "cancel reminder about 🙏", "could you cancel the textbook reminder?",
                      "delete the reminder to strech", "cancel reminder to stretch my legs", "cancel the text about books"):
                box.runner.play_path.write_text(REM2)
                out = box.send(s)
                self.assertEqual(box.play_writes, [], s)
                self.assertIn("stretch", out["answer"], s)                       # it lists what exists
            box.runner.play_path.write_text(REM1)
            out = box.send("cancel my reminder")                                 # one waiting reminder, still not named: nothing dropped
            self.assertEqual(box.play_writes, [], out["answer"])
            box.runner.play_path.write_text(REM2)
            box.send("cancel reminder to stretch")
            self.assertEqual([r["id"] for r in box.play_writes[0]["reminders"]], ["r2"])
            box.runner.play_path.write_text(REM2)
            box.send("Could you cancel the reminder about the book order? 🙏")
            self.assertEqual([r["id"] for r in box.play_writes[0]["reminders"]], ["r1"])


class Round4FullWidth(unittest.TestCase):
    QUESTIONS = ["pin 買い物？", "cancel reminder to stretch？", "update the status of network traffic analyzer？", "skip this？！", "pin lab 7？",
                 "snooze this？", "park this idea： birdhouse？", "add buy milk？", "remind me to call mom？", "unpin lab 7？！", "ｓｋｉｐ ｔｈｉｓ？"]

    def test_full_width_question_marks_never_write(self):
        wrote = []
        with LiveBox(CJK, current=CUR) as box:
            for s in self.QUESTIONS:
                box.runner.play_path.write_text(REM1)
                out = box.send(s)
                if box.writes or box.play_writes or "capture" in out:
                    wrote.append((s, box.writes, len(box.play_writes), "capture" in out))
        self.assertEqual(wrote, [])

    def test_full_width_question_reply_is_never_a_confirmation(self):
        for s in ("yes, make it friday？", "ok add it？！", "yes？", "yeah but just text me？"):
            r = typed.parse_reply(s, C.PENDING, TEN_AM)
            self.assertFalse(r and (r.get("kind") == "yes" or r.get("confirm")), (s, r))
        self.assertTrue(plain.is_question("skip this？"))
        self.assertTrue(plain.is_question("skip this ？！ 🙂"))


class Round4ProjectStatus(unittest.TestCase):
    def test_only_an_explicit_status_update_saves(self):
        import project_status
        for s in ("update me on the network traffic analyzer", "update on the network traffic analyzer", "update for the analyzer",
                  "how's the network traffic analyzer going", "where am i on the network traffic analyzer", "refresh me on the analyzer"):
            self.assertFalse(project_status.is_update(s), s)
        for s in ("update the status of network traffic analyzer", "refresh the status of the analyzer", "please update the status on the analyzer",
                  "save the status of the analyzer", "could you update the status of the analyzer"):
            self.assertTrue(project_status.is_update(s), s)
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in ("update me on the network traffic analyzer", "update on the network traffic analyzer", "fill me in on the network traffic analyzer"):
                box.send(s)
                self.assertEqual(box.play_writes, [], s)


class Round4Park(unittest.TestCase):
    def test_park_words_need_word_boundaries(self):
        import park
        for s in ("parking permit renewal", "parkour lessons saturday", "stashed the keys", "ideator review", "ideas to fix later",
                  "ideally finish lab 7", "i have an ideal plan for today", "thoughtful note: buy flowers"):
            self.assertIsNone(park.parse(s), s)
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in ("parking permit renewal", "parkour lessons saturday", "ideator review"):
                box.send(s)
                self.assertEqual(box.play_writes, [], s)
        self.assertEqual(park.parse("park a birdhouse"), "birdhouse")
        self.assertEqual(park.parse("idea: a birdhouse"), "a birdhouse")


class Round4Targets(unittest.TestCase):
    def test_exact_full_title_wins_before_date_words_are_stripped(self):
        with LiveBox(HOMEWORK, current=CUR) as box:
            for verb in ("pin", "skip", "unpin"):
                box.send(f"{verb} Submit homework today")
                self.assertEqual(box.writes, [[verb, "h2"]], verb)
                box.send(f"{verb} Submit homework")
                self.assertEqual(box.writes, [[verb, "h1"]], verb)
            out = box.send("pin homework")
            self.assertEqual(box.writes, [], out["answer"])

    def test_actions_against_unlisted_names_write_nothing(self):
        with LiveBox(HOMEWORK, current=CUR) as box:
            for s in ("pin 买东西", "snooze 买东西 for an hour", "skip submit", "pin homework today please 🙂", "pin 買", "skip 買い物 and 买东西",
                      "pin read chapter 55", "skip lab 77", "unpin 🙏 homework"):
                out = box.send(s)
                self.assertEqual(box.writes, [], (s, out.get("answer")))


class Round4Snooze(unittest.TestCase):
    def test_dangling_time_word_asks_until_when(self):
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in ("snooze at", "snooze this to", "snooze this on", "snooze it till", "snooze lab 7 at", "snooze this by", "postpone this to",
                      "snooze this until", "snooze for", "snooze this at ", "snooze it on."):
                out = box.send(s)
                self.assertEqual(box.writes, [], s)
                self.assertIn("until when", out["answer"].lower(), s)


class Round4Frequency(unittest.TestCase):
    def test_out_of_range_frequency_asks_and_never_defaults_to_daily(self):
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in ("study plan for stretch 0 times a week: warm up", "add stretch 0 times a week", "add stretch 9 times a week",
                      "stretch 0 times a day", "study plan for stretch 12 times a week: warm up, cool down", "add read 0 times a day"):
                for sec in (None, "personal"):
                    out = box.send(s, sector=sec) if sec else box.send(s)
                    self.assertNotIn("capture", out, (s, sec))
                    self.assertIn("how many times", out["answer"].lower(), (s, sec))
                    self.assertEqual(R.decide(s, sector=sec), "tiny", (s, sec))
            self.assertIn("capture", box.send("add stretch 3 times a week"))


class Round4SectorSchedule(unittest.TestCase):
    def test_schedule_questions_never_become_tasks_in_a_sector(self):
        bad = []
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in P.CASES["schedule"] + ["upcoming deadlines", "deadlines this week", "my deadlines", "upcoming exams"]:
                closed = R.decide(s, tasks=P.TASKS)
                for sec in ("personal", "play"):
                    if R.decide(s, tasks=P.TASKS, sector=sec) != closed or "capture" in box.send(s, sector=sec):
                        bad.append((s, sec))
        self.assertEqual(bad, [])


class Round4Polite(unittest.TestCase):
    def test_polite_requests_work(self):
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in ("Could you please skip this? 🙏", "could you skip this please 🙂", "please skip this 🙏", "can you pin this please?"):
                box.send(s)
                self.assertEqual(len(box.writes), 1, s)
                self.assertEqual(box.writes[0][1], "t1", s)
            box.runner.play_path.write_text(REM1)
            out = box.send("Could you park this idea: a birdhouse?")
            self.assertEqual(len(box.play_writes), 1, out.get("answer"))
            out = box.send("Could you set a reminder to draft an email at 7am?")
            self.assertIn("capture", out)
            self.assertEqual(out["capture"]["mode"], "reminder")
            self.assertNotIn("capture", box.send("remind me to draft a cover letter"))       # writing work with no time stays model work


class Round4Long(unittest.TestCase):
    def test_length_limit_runs_before_any_scan(self):
        import time
        s = "?)" * 7999 + "x"
        t0 = time.perf_counter()
        self.assertFalse(plain.is_question(s))
        self.assertLess(time.perf_counter() - t0, 0.05)
        with LiveBox(P.TASKS, current=CUR) as box:
            t0 = time.perf_counter()
            with self.assertRaises(ValueError):
                box.send(s)
            self.assertLess(time.perf_counter() - t0, 0.2)
        for s in ("?" * 3999 + "x", "?)" * 1999 + "x", "x" + " ?" * 1999):
            t0 = time.perf_counter()
            plain.is_question(s); plain.strip_question(s)
            self.assertLess(time.perf_counter() - t0, 0.05, s[:10])


class Round4Sweep(unittest.TestCase):
    """Holes the round 4 sweep found: a name made only of emoji, and a parked "idea" with no words in it."""

    def test_emoji_where_a_name_goes_writes_nothing(self):
        with LiveBox(CJK, current=CUR) as box:
            for s in ("pin 🛒", "skip 🙏", "unpin 🙏🙏", "snooze 🛒"):
                out = box.send(s)
                self.assertEqual(box.writes, [], (s, out.get("answer")))
            box.send("skip this 🙏")
            self.assertEqual(box.writes, [["skip", "t1"]])

    def test_an_idea_needs_words(self):
        import park
        for s in ("park the", "park it all", "park everything please", "park this idea: it"):
            self.assertEqual(park.parse(s), "", s)
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in ("park the", "park it all"):
                box.send(s)
                self.assertEqual(box.play_writes, [], s)

    def test_save_and_polite_status_updates_are_status_commands(self):
        import project_status
        for s in ("save the status of network traffic analyzer", "could you update the status of the analyzer"):
            self.assertEqual(R.decide(s), "project", s)
            self.assertTrue(project_status.is_update(s), s)


REM_NIGHT = ('{"reminders": [{"id": "r1", "text": "Pack for tonight", "at": "2099-12-01T09:00-05:00"},'
             ' {"id": "r2", "text": "Night", "at": "2099-12-01T09:00-05:00"}], "projects": []}')
DUP_HW = HOMEWORK + [{"id": "h3", "title": "Submit homework today", "list": "Personal"}]
C_TASKS = P.TASKS + [{"id": "c1", "title": "Read C basics", "list": "Play"}, {"id": "c2", "title": "Read C++ basics", "list": "Play"}]


class Round5(unittest.TestCase):
    def test_1_cancel_connector_words_need_word_boundaries(self):
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in ("delete reminder tomorrow", "cancel the reminder todo", "cancel reminder forever", "cancel text topic"):
                box.runner.play_path.write_text(REM_NIGHT)
                out = box.send(s)
                self.assertEqual(box.play_writes, [], (s, out["answer"]))
            box.runner.play_path.write_text(REM_NIGHT)
            box.send("cancel reminder tonight")                       # "tonight" is a whole word of "Pack for tonight", never "to" + "night"
            self.assertEqual([r["id"] for r in box.play_writes[0]["reminders"]], ["r2"])
            box.runner.play_path.write_text(REM_NIGHT)
            box.send("cancel reminder to Night")
            self.assertEqual([r["id"] for r in box.play_writes[0]["reminders"]], ["r1"])
            box.runner.play_path.write_text(REM_NIGHT)
            box.send("cancel reminder for Pack for tonight")
            self.assertEqual([r["id"] for r in box.play_writes[0]["reminders"]], ["r2"])

    def test_2_every_unicode_question_mark_is_a_question(self):
        import unicodedata
        marks = [chr(c) for c in range(0x3000) if "QUESTION MARK" in unicodedata.name(chr(c), "") and chr(c) != "¿"] + [";"]
        self.assertIn("؟", marks)
        with LiveBox(P.TASKS, current=CUR) as box:
            for q in marks:
                self.assertTrue(plain.is_question(f"pin this{q}"), repr(q))
                for s in (f"cancel reminder to stretch{q}", f"pin this{q}", f"skip this{q}", f"snooze this{q}", f"add buy milk{q}"):
                    box.runner.play_path.write_text(REM1)
                    out = box.send(s)
                    self.assertEqual((box.writes, box.play_writes, "capture" in out), ([], [], False), (s, out.get("answer")))
            self.assertTrue(plain.is_question("¿pin this?"))
            self.assertFalse(plain.is_question("¿cómo estás"))

    def test_3_several_exact_title_matches_ask(self):
        with LiveBox(DUP_HW, current=CUR) as box:
            for verb in ("pin", "unpin", "skip"):
                out = box.send(f"{verb} Submit homework today")
                self.assertEqual(box.writes, [], (verb, out["answer"]))
            out = box.send("snooze Submit homework today for an hour")
            self.assertEqual(box.writes, [], out["answer"])
            out = box.send("snooze Submit homework today")
            self.assertEqual(box.writes, [], out["answer"])
            box.send("pin Submit homework")
            self.assertEqual(box.writes, [["pin", "h1"]])                        # one exact title still acts

    def test_4_symbol_titles_keep_their_symbols_and_ties_save_nowhere(self):
        self.assertEqual(plain.words("Read C++ basics, F#, .NET and C#"), ["read", "c++", "basics", "f#", ".net", "and", "c#"])
        self.assertEqual(plain.words("file.txt chapter 5+"), ["file", "txt", "chapter", "5"])
        self.assertTrue(plain.names_title("Explain Read C basics in detail", "Read C basics"))
        self.assertFalse(plain.names_title("Explain Read C++ basics in detail", "Read C basics"))
        import command as cmd
        self.assertEqual(cmd.match_task("Explain Read C basics in detail", C_TASKS)[0]["id"], "c1")
        self.assertEqual(cmd.match_task("Explain Read C++ basics in detail", C_TASKS)[0]["id"], "c2")
        self.assertEqual(cmd.match_task("compare Read C basics with Read C++ basics", C_TASKS)[0], None)   # a tie: no task
        self.assertEqual(plain.match_target("c basics", C_TASKS)[1]["id"], "c1")
        self.assertEqual(plain.match_target("c++ basics", C_TASKS)[1]["id"], "c2")
        with LiveBox(C_TASKS, current=CUR) as box:
            out = box.send("Explain Read C basics in detail")
            self.assertEqual(out.get("taskId"), "c1")
            out = box.send("Compare Read C basics with Read C++ basics in detail")
            self.assertFalse(out.get("taskId"), out.get("taskId"))

    def test_5_every_action_verb_with_an_emoji_object_asks(self):
        verbs = ["pin", "unpin", "un-pin", "un pin", "snooze", "postpone", "delay", "defer", "put off", "hold off on", "skip", "swap out", "drop", "bump"]
        verbs += ["do {} first", "keep {} on top", "focus on {} today", "move {} to the top", "make {} priority", "not {}", "i don't want to do {}"]
        sentences = []
        for v in verbs:
            for obj in ("🛒", "🛒🛒", "🙏"):
                sentences.append(v.format(obj) if "{}" in v else f"{v} {obj}")
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in sentences:
                out = box.send(s)
                self.assertEqual(box.writes, [], (s, out.get("answer")))
                self.assertNotIn("capture", out, s)
            for s in ("un-pin 🛒", "postpone 🛒", "snooze 🛒 for an hour", "unpin 🛒", "skip 🛒"):
                self.assertIn("which", box.send(s)["answer"].lower() + "which", s)
            box.send("un-pin this 🙏")
            self.assertEqual(box.writes, [["unpin", "t1"]])

    def test_6_a_time_phrase_that_cannot_be_read_asks_until_when(self):
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in ("snooze Lab 7 in", "snooze lab 7 within", "snooze this after", "snooze this around", "snooze lab 7 in the",
                      "snooze lab 7 until whenever", "snooze lab 7 until sunrise", "snooze this before", "snooze it within a"):
                out = box.send(s)
                self.assertEqual(box.writes, [], (s, out["answer"]))
                self.assertIn("until when", out["answer"].lower(), s)
            box.send("snooze lab 7")                                            # no time words at all: the default
            self.assertEqual(len(box.writes), 1)

    def test_7_multiline_plan_with_a_bad_frequency_asks(self):
        with LiveBox(P.TASKS, current=CUR) as box:
            for s in ("study plan for stretch 0 times a week:\n- warm up\n- cool down", "study plan for stretch 9 times a week:\n- warm up",
                      "study plan for stretch 0 times a day:\n- warm up"):
                for sec in (None, "personal"):
                    out = box.send(s, sector=sec) if sec else box.send(s)
                    self.assertNotIn("capture", out, (s, sec))
                    self.assertIn("how many times", out["answer"].lower(), (s, sec))
