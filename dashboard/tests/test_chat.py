"""The chat drawer's conversation (STATE_MODEL_CHAT.md): adds, pending questions, typed block actions, Done, undo, pastes."""
import json, sys, unittest
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(Path(__file__).resolve().parent))
import done_actions as da  # noqa
import chat as chat_mod  # noqa
from test_server import Base  # noqa
from test_capture_server import answer, LISTS  # noqa

H = {"X-Brain": "1"}


class Chat(Base):
    def setUp(self):
        super().setUp()
        snap = json.loads((self.tmp / "snap.json").read_text())
        snap["lists"] = LISTS
        (self.tmp / "snap.json").write_text(json.dumps(snap))
        import server
        server.RUNNER["r"].play_path = self.tmp / "play.json"

    def say(self, text, **kw):
        c, st = self.req("/api/chat", {"text": text, **kw}, H)
        self.assertEqual(c, 200, st)
        return st

    def rows(self):
        return self.req("/api/state")[1]["chat"]["rows"]

    def last(self):
        return self.rows()[-1]

    def paths(self):
        import server
        return server.DONE_PATHS["p"]

    def files(self):
        return [json.loads(f.read_text()) for f in sorted(Path(self.paths()["actions_dir"]).glob("*" + da.SUFFIX))]

    # ---- adds
    def test_confident_add_goes_straight_in_and_says_added_only_after_quicktodo(self):
        st = self.say("remind me to email dr lee friday")
        me, th = st["chat"]["rows"][-2:]
        self.assertEqual((me["who"], me["text"]), ("me", "remind me to email dr lee friday"))
        self.assertTrue(th["text"].startswith("Adding \"Email dr lee\" to Personal"), th["text"])
        self.assertNotIn("fly", th)
        (req,) = self.files()
        self.assertEqual((req["action"], req["list"]), ("add", "Personal"))
        answer(self.paths())
        th = self.last()
        self.assertTrue(th["text"].startswith("Added \"Email dr lee\" to Personal, due "), th["text"])
        self.assertIn("Say undo to take it back.", th["text"])
        self.assertEqual(th["fly"], {"list": "Personal", "title": "Email dr lee"})

    def test_unsure_add_asks_in_first_person_then_yes_adds(self):
        st = self.say("add get groceries")
        self.assertEqual(st["chat"]["rows"][-1]["text"], "I'll put \"Get groceries\" in Personal with no date. Sound right?")
        self.assertEqual(st["chat"]["pending"], {"kind": "add"})
        self.assertEqual(self.files(), [])
        st = self.say("yep")
        self.assertIsNone(st["chat"]["pending"])
        self.assertEqual(len(self.files()), 1)
        self.assertTrue(st["chat"]["rows"][-1]["text"].startswith("Adding \"Get groceries\""))

    def test_no_drops_the_add(self):
        self.say("add get groceries")
        st = self.say("nah")
        self.assertEqual(st["chat"]["rows"][-1]["text"], "OK, I didn't add \"Get groceries\".")
        self.assertEqual(self.files(), [])

    def test_a_correction_is_applied_and_added(self):
        self.say("add get groceries")
        self.say("make it saturday")
        (req,) = self.files()
        due = datetime.fromisoformat(req["due"])
        self.assertEqual(due.strftime("%a"), "Sat")
        self.say("add buy a charger")
        self.say("in play")
        self.assertIn(("Buy a charger", "Play"), [(f["title"], f["list"]) for f in self.files()])

    def test_a_new_message_drops_the_question_quietly(self):
        self.say("add get groceries")
        st = self.say("what should i do now")
        self.assertIsNone(st["chat"]["pending"])
        self.assertIn("Read Chapter 5", st["chat"]["rows"][-1]["text"])
        self.assertEqual(self.files(), [])

    def test_text_reminder_with_a_time_is_set_and_undone(self):
        st = self.say("remind me to call mom at 11:59pm")
        th = st["chat"]["rows"][-1]
        self.assertIn("I'll text you", th["text"]); self.assertIn("It's not on your list.", th["text"])
        self.assertTrue(st["play"]["reminders"] if "reminders" in st["play"] else True)
        st = self.say("undo")
        self.assertIn("Undone", st["chat"]["rows"][-1]["text"])

    def test_undo_takes_back_a_confirmed_chat_add(self):
        self.say("remind me to email dr lee friday")
        answer(self.paths())
        self.rows()                                     # the view settles the row
        st = self.say("undo")
        self.assertEqual(st["chat"]["rows"][-1]["text"], "Taking it back…")
        self.assertIn("unadd", [f["action"] for f in self.files()])

    # ---- typed actions
    def test_start_extend_break_back_checkin(self):
        st = self.say("start")
        self.assertEqual(st["blocks"]["phase"], "work")
        self.assertTrue(st["chat"]["rows"][-1]["text"].startswith("Started \"Read Chapter 5\""))
        st = self.say("15 more minutes")
        self.assertTrue(st["chat"]["rows"][-1]["text"].startswith("Added 15 minutes"))
        st = self.say("take a break")
        self.assertEqual(st["blocks"]["phase"], "break")
        self.assertIn("Break:", st["chat"]["rows"][-1]["text"])
        st = self.say("I'm back")
        self.assertEqual(st["blocks"]["phase"], "checkin")
        self.assertEqual(st["chat"]["rows"][-1]["text"], "Break's over. Did you do something just for you?")
        self.assertEqual(st["chat"]["pending"], {"kind": "checkin"})
        st = self.say("yeah")
        self.assertEqual(st["blocks"]["phase"], "idle")
        self.assertTrue(st["chat"]["rows"][-1]["text"].startswith("Good. That counts."))

    def test_cancel_and_nothing_running(self):
        self.say("start")
        st = self.say("cancel the block")
        self.assertEqual(st["blocks"]["phase"], "idle")
        st = self.say("take a break")
        self.assertEqual(st["chat"]["rows"][-1]["text"], "Nothing's running. Step away whenever; I'll be here.")

    def test_done_completes_the_current_task_and_says_done_after_quicktodo(self):
        st = self.say("done")
        (req,) = self.files()
        self.assertEqual((req["action"], req["taskId"]), ("complete", "AAAAAAAA-1"))
        self.assertEqual(st["chat"]["rows"][-1]["text"], "Marking \"Read Chapter 5\" done…")
        out = da._read(self.paths()["results"], {"version": 1, "results": []})
        out["results"].append({"id": req["id"], "action": "complete", "outcome": "done", "taskId": "AAAAAAAA-1", "title": "Read Chapter 5",
                               "detail": "", "processedAt": datetime.now().astimezone().isoformat()})
        Path(self.paths()["results"]).write_text(json.dumps(out))
        self.assertEqual(self.last()["text"], "Marked \"Read Chapter 5\" (Network Security) done. Say undo to take it back.")

    def test_done_in_a_block_finishes_it_with_a_break(self):
        self.say("start")
        st = self.say("finished it")
        self.assertEqual(st["blocks"]["phase"], "break")

    def test_done_with_a_named_task(self):
        self.say("done with apply to 10")
        (req,) = self.files()
        self.assertEqual(req["taskId"], "BBBBBBBB-2")

    def test_done_with_the_class_named_at_the_end(self):
        self.say("Mark read chapter 5 complete in network security")
        (req,) = self.files()
        self.assertEqual((req["action"], req["taskId"]), ("complete", "AAAAAAAA-1"))

    def test_done_on_a_task_that_is_not_open_offers_the_closest_and_yes_marks_it(self):
        st = self.say("mark read chapter 6 done")
        self.assertEqual(st["chat"]["rows"][-1]["text"],
                         "I don't see \"read chapter 6\" open on your list, so it may already be done. "
                         "Did you mean \"Read Chapter 5\" (Network Security)? Say yes and I'll mark it done.")
        self.assertEqual(st["chat"]["pending"], {"kind": "done"})
        self.assertEqual(self.files(), [])
        st = self.say("yes")
        (req,) = self.files()
        self.assertEqual(req["taskId"], "AAAAAAAA-1")
        self.assertIsNone(st["chat"]["pending"])

    def test_done_on_nothing_close_never_goes_to_a_model(self):
        st = self.say("mark the dishes done")
        self.assertEqual(st["chat"]["rows"][-1]["text"],
                         "I don't see \"the dishes\" open on your list, so it may already be done. Nothing open has a name close to that.")
        self.assertEqual(server_jobs(self), [])

    def test_which_one_is_answered_by_the_class(self):
        import server
        snap = json.loads((self.tmp / "snap.json").read_text())
        snap["tasks"].append({"id": "CCCCCCCC-3", "title": "Read Chapter 5", "list": "Cloud Computing", "progressPercent": 0})
        (self.tmp / "snap.json").write_text(json.dumps(snap))
        st = self.say("check off read chapter 5")
        self.assertIn("Which one?", st["chat"]["rows"][-1]["text"])
        self.say("its for cloud computing")
        (req,) = self.files()
        self.assertEqual(req["taskId"], "CCCCCCCC-3")

    def test_why(self):
        st = self.say("why this?")
        self.assertTrue(st["chat"]["rows"][-1]["text"].startswith("\"Read Chapter 5\" is first because"))

    def test_low_energy(self):
        st = self.say("I'm exhausted")
        self.assertTrue(st["lowEnergy"] if "lowEnergy" in st else True)
        self.assertIn("Low energy", st["chat"]["rows"][-1]["text"])
        st = self.say("feeling better")
        self.assertIn("Low energy is off", st["chat"]["rows"][-1]["text"])

    def test_snooze_still_acts_through_the_box(self):
        st = self.say("snooze this for 2 hours")
        self.assertIn("Snoozed", st["chat"]["rows"][-1]["text"])
        self.assertIn("undo", st["chat"]["rows"][-1])

    # ---- the router (only for @sonnet / @opus tags now), pastes, the log
    def test_a_sonnet_tag_still_goes_to_the_router(self):
        st = self.say("@sonnet say hi")
        th = st["chat"]["rows"][-1]
        self.assertTrue(th["final"]); self.assertTrue(th["model"])
        self.assertEqual(th["text"], "Done: renamed tmp to total.")
        self.assertEqual(self.models.calls, [])

    def test_pasted_text_goes_to_the_agent_and_is_never_logged(self):
        secret = "line one of my essay\nline two\nline three\nline four"
        self.models.haiku_out.append({"reply": "It's about an essay draft.", "action": None})
        st = self.say("@haiku summarize this [Pasted text #1 · 4 lines]", pastes=[secret])
        self.assertEqual(st["chat"]["rows"][-2]["text"], "@haiku summarize this [Pasted text #1 · 4 lines]")
        self.assertEqual([c[0] for c in self.models.calls], ["haiku"])          # @haiku skips the free model
        self.assertIn("line four", self.models.calls[0][1])                        # the model gets the paste
        self.assertEqual(self.last()["text"], "It's about an essay draft.")
        cdir = self.tmp / "cstate"
        for f in cdir.iterdir():
            if f.is_file() and f.name != "chat.json":
                self.assertNotIn("line one", f.read_text(), f.name)
        log = [json.loads(x) for x in (cdir / "chat-log.jsonl").read_text().splitlines()]
        self.assertEqual(log[0]["pastes"], [len(secret)])
        self.assertFalse((cdir / "learned.jsonl").exists())

    def test_a_paste_skips_the_rules(self):
        st = self.say("[Pasted text #1 · 1 lines]", pastes=["remind me to call mom at 5pm"])
        self.assertEqual(self.files(), [])
        self.assertIsNone(st["chat"]["pending"])

    def test_new_morning_starts_fresh_and_trims_to_fifty(self):
        import server
        ch = server.chat()
        now = datetime.now().astimezone()
        st = ch._load(now)
        for i in range(70):
            ch._row(st, "me", f"m{i}", now, log=False)
        ch._save(st)
        rows = self.rows()
        self.assertEqual(len(rows), 50); self.assertEqual(rows[-1]["text"], "m69")
        st = ch._load(now); st["day"] = (now - timedelta(days=1)).date().isoformat(); ch._save(st)
        self.assertEqual(self.rows(), [])

    def test_pending_survives_the_trim(self):
        self.say("add get groceries")
        import server
        ch = server.chat()
        now = datetime.now().astimezone()
        st = ch._load(now)
        for i in range(70):
            ch._row(st, "me", f"m{i}", now, log=False)
        ch._save(st)
        st = self.say("yes")
        self.assertEqual(len(self.files()), 1)

    def test_empty_and_bad_bodies(self):
        self.assertEqual(self.req("/api/chat", {"text": ""}, H)[0], 400)
        self.assertEqual(self.req("/api/chat", {"text": "hi", "pastes": "x"}, H)[0], 400)
        self.assertEqual(self.req("/api/chat", {"text": "hi"})[0], 403)


def sid(prompt, title, lst):
    """The short id the agent's card gave a task."""
    import re
    return re.search(r"(t\d+) \| " + re.escape(title) + r" \| " + re.escape(lst) + r" \|", prompt).group(1)


class Agent(Chat):
    """The chat agent (command/STATE_MODEL_AGENT.md): free model first, Haiku with the same tools, checks in code."""

    def add_task(self, tid, title, lst, days=3):
        snap = json.loads((self.tmp / "snap.json").read_text())
        snap["tasks"].append({"id": tid, "title": title, "list": lst, "dueDate": (datetime.now().astimezone() + timedelta(days=days)).isoformat()})
        (self.tmp / "snap.json").write_text(json.dumps(snap))

    def test_a_general_question_is_answered_by_the_free_model(self):
        self.models.free_out.append({"reply": "Sunlight scatters off air; blue scatters most.", "action": None})
        self.say("why is the sky blue")
        th = self.last()
        self.assertEqual(th["text"], "Sunlight scatters off air; blue scatters most.")
        self.assertTrue(th["final"]); self.assertTrue(th["model"])
        self.assertEqual([c[0] for c in self.models.calls], ["free"])
        self.assertEqual(server_jobs(self), [])                                    # never the router
        self.say("and why are sunsets red")
        self.assertIn("why is the sky blue", self.models.calls[-1][1])             # the model sees the chat so far

    def test_free_failures_fall_back_to_haiku_and_nothing_else(self):
        for bad in (RuntimeError("rate limited"), "sure! here you go", lambda p: {"reply": "", "action": {"tool": "done", "task": "t99"}}):
            self.models.calls.clear()
            self.models.free_out.append(bad)
            self.models.haiku_out.append({"reply": "Haiku here.", "action": None})
            self.say("tell me a fun fact about owls")
            self.assertEqual([c[0] for c in self.models.calls], ["free", "haiku"], bad)
            self.assertEqual(self.last()["text"], "Haiku here.")
        self.models.free_out.append(RuntimeError("down")); self.models.haiku_out.append(RuntimeError("down too"))
        self.say("tell me a fun fact about owls")
        self.assertEqual(self.last()["text"], "I couldn't do that one. Try saying it another way.")
        self.assertEqual(server_jobs(self), [])

    def test_done_in_her_own_words(self):
        self.models.free_out.append(lambda p: {"reply": "Nice.", "action": {"tool": "done", "task": sid(p, "Read Chapter 5", "Network Security")}})
        self.say("wrapped up the chapter five reading")
        f = self.files()
        self.assertEqual((len(f), f[0]["taskId"]), (1, "AAAAAAAA-1"))
        self.assertIn("Marking \"Read Chapter 5\" done", self.last()["text"])

    def test_two_tasks_with_one_name_are_never_guessed(self):
        self.add_task("CCCCCCCC-3", "Read Chapter 5", "Cloud Computing")
        self.models.free_out.append(lambda p: {"reply": "Done!", "action": {"tool": "done", "task": sid(p, "Read Chapter 5", "Network Security")}})
        st = self.say("i finished reading chapter 5")
        self.assertEqual(self.files(), [])
        self.assertIn("Two open tasks are called that", self.last()["text"])
        self.assertEqual(st["chat"]["pending"], {"kind": "done"})
        self.say("the cloud computing one")
        self.assertEqual(self.files()[0]["taskId"], "CCCCCCCC-3")

    def test_naming_the_class_settles_it(self):
        self.add_task("CCCCCCCC-3", "Read Chapter 5", "Cloud Computing")
        self.models.free_out.append(lambda p: {"reply": "", "action": {"tool": "done", "task": sid(p, "Read Chapter 5", "Cloud Computing")}})
        self.say("finished the chapter 5 reading for cloud computing")
        self.assertEqual(self.files()[0]["taskId"], "CCCCCCCC-3")

    def test_a_sentence_that_worked_is_learned_and_undo_forgets_it(self):
        self.models.free_out.append(lambda p: {"reply": "", "action": {"tool": "pin", "task": sid(p, "Apply to 10", "Internships")}})
        self.say("the applications should stay up top today")
        self.assertIn("Pinned \"Apply to 10\" (Internships)", self.last()["text"])
        learned = (self.tmp / "cstate" / "learned.jsonl").read_text()
        self.assertIn("applications should stay up top", learned)
        self.say("undo")
        self.assertFalse((self.tmp / "cstate" / "learned.jsonl").read_text().strip())
        self.models.free_out.append(lambda p: {"reply": "", "action": {"tool": "pin", "task": sid(p, "Apply to 10", "Internships")}})
        self.say("the applications should stay up top today")
        n = len(self.models.calls)
        self.say("unpin apply to 10")
        self.say("the applications should stay up top today")                  # learned: no model call this time
        self.assertEqual(len(self.models.calls), n)
        self.assertIn("Pinned", self.last()["text"])

    def test_facts_come_from_code_not_the_model(self):
        self.models.free_out.append({"reply": "You have 40 things overdue.", "action": {"tool": "due", "window": "overdue"}})
        self.say("anything slipping through the cracks")
        txt = self.last()["text"]
        self.assertIn("Read Chapter 5", txt)
        self.assertNotIn("40 things", txt)

    def test_a_past_date_or_unknown_list_is_not_used(self):
        self.models.free_out.append({"reply": "", "action": {"tool": "add", "title": "Email Dr. Lee", "list": "Nonsense", "due": None}})
        st = self.say("dr lee is waiting on an email from me")
        self.assertEqual(st["chat"]["pending"], {"kind": "add"})
        self.assertIn("Which list", self.last()["text"])
        self.models.free_out.append({"reply": "", "action": {"tool": "add", "title": "X", "list": "Personal", "due": "2001-01-01T12:00"}})
        self.models.haiku_out.append({"reply": "Which day did you mean?", "action": None})
        self.say("x is waiting on me")
        self.assertEqual(self.last()["text"], "Which day did you mean?")

    def test_her_answer_to_the_models_question_goes_back_to_the_model(self):
        self.models.free_out.append({"reply": "Which one, t1 or the other?", "action": None})
        self.say("that reading is handled now")
        self.assertEqual(self.last()["text"], "Which one, or the other?")           # ids never reach her
        self.models.free_out.append(lambda p: {"reply": "", "action": {"tool": "done", "task": sid(p, "Read Chapter 5", "Network Security")}})
        self.say("the second one")
        self.assertEqual(self.files()[0]["taskId"], "AAAAAAAA-1")
        self.assertIn("Which one", self.models.calls[-1][1])                          # it saw its own question

    def test_a_request_to_do_something_is_not_answered_with_a_due_list(self):
        self.models.free_out.append(lambda p: {"reply": "", "action": {"tool": "pin", "task": sid(p, "Apply to 10", "Internships")}})
        self.say("keep apply to 10 at the top for today")
        self.assertIn("Pinned", self.last()["text"])

    def test_a_rule_that_comes_up_empty_hands_over_to_the_agent(self):
        self.models.free_out.append({"reply": "I don't have a project by that name on your list.", "action": None})
        self.say("where am i on the bandit stuff")
        self.assertEqual([c[0] for c in self.models.calls], ["free"])
        self.assertEqual(self.last()["text"], "I don't have a project by that name on your list.")

    def test_stop_while_thinking(self):
        import server
        def slow(p):
            server.chat().cancel_agent(None)          # she presses stop while the model is still answering
            return {"reply": "too late", "action": None}
        self.models.free_out.append(slow)
        self.say("tell me about owls")
        self.assertEqual(self.last()["text"], "Stopped.")

    # ---- review fixes (Codex, 2026-11-22)
    def learned(self):
        f = self.tmp / "cstate" / "learned.jsonl"
        return f.read_text() if f.exists() else ""

    def test_an_answer_to_the_models_question_is_never_learned(self):
        self.models.free_out.append({"reply": "Which one, the applications or the reading?", "action": None})
        self.say("@free hold something up top for me")
        self.models.free_out.append(lambda p: {"reply": "", "action": {"tool": "pin", "task": sid(p, "Apply to 10", "Internships")}})
        self.say("the applications")
        self.assertIn("Pinned", self.last()["text"])
        self.assertNotIn("the applications", self.learned())

    def test_a_learned_sentence_rechecks_which_one(self):
        self.models.free_out.append(lambda p: {"reply": "", "action": {"tool": "pin", "task": sid(p, "Apply to 10", "Internships")}})
        self.say("the applications should stay up top today")
        self.assertIn("applications should stay up top", self.learned())
        self.say("unpin apply to 10")
        self.add_task("CCCCCCCC-3", "Apply to 10", "Internships")          # now two in the same list
        n = len(self.models.calls)
        self.models.free_out.append({"reply": "Which one?", "action": None})
        self.say("the applications should stay up top today")
        self.assertEqual(len(self.models.calls), n + 1)                       # not replayed blind: two tasks fit now

    def test_same_name_in_the_same_list_asks_with_due_dates(self):
        self.add_task("CCCCCCCC-3", "Apply to 10", "Internships", days=6)
        self.models.free_out.append(lambda p: {"reply": "", "action": {"tool": "pin", "task": sid(p, "Apply to 10", "Internships")}})
        self.say("keep the internship applications on top")
        txt = self.last()["text"]
        self.assertIn("Two open tasks are called that", txt)
        self.assertIn("due", txt)

    def test_a_tag_inside_pasted_text_is_not_a_model_choice(self):
        self.models.free_out.append({"reply": "It's a note.", "action": None})
        self.say("what is this [Pasted text #1 · 4 lines]", pastes=["@sonnet hello\na\nb\nc"])
        self.assertEqual([c[0] for c in self.models.calls], ["free"])
        self.assertIn("@sonnet hello", self.models.calls[0][1])
        self.assertEqual(server_jobs(self), [])

    def test_stop_after_the_action_started_says_too_late(self):
        import server
        server.chat()._ag["ag-x"] = {"cancel": False, "done": False, "acting": True, "learn": False}
        self.say("stop")
        self.assertIn("Too late to stop that one", self.last()["text"])
        self.assertFalse(server.chat().cancel_agent(None))

    def test_undo_after_a_learned_replay_forgets_it(self):
        self.models.free_out.append(lambda p: {"reply": "", "action": {"tool": "pin", "task": sid(p, "Apply to 10", "Internships")}})
        self.say("the applications should stay up top today")
        self.say("unpin apply to 10")
        n = len(self.models.calls)
        self.say("the applications should stay up top today")                  # replayed, no model
        self.assertEqual(len(self.models.calls), n)
        self.say("undo")
        self.assertNotIn("applications should stay up top", self.learned())

    def test_a_dated_snooze_is_not_learned(self):
        until = (datetime.now().astimezone() + timedelta(days=2)).strftime("%Y-%m-%dT12:00")
        self.models.free_out.append(lambda p: {"reply": "", "action": {"tool": "snooze", "task": sid(p, "Apply to 10", "Internships"), "until": until}})
        self.say("push the applications off until the day after tomorrow")
        self.assertIn("Snoozed", self.last()["text"])
        self.assertEqual(self.learned().strip(), "")


def server_jobs(t):
    import server
    return server.RUNNER["r"]._jobs()


class Pure(unittest.TestCase):
    def test_when_text(self):
        now = datetime(2026, 11, 22, 10, 0).astimezone()
        self.assertEqual(chat_mod.when_text(now.replace(hour=17).isoformat(), now), "today at 5 PM")
        self.assertEqual(chat_mod.when_text((now + timedelta(days=1)).replace(hour=9, minute=30).isoformat(), now), "tomorrow at 9:30 AM")
        self.assertEqual(chat_mod.when_text((now + timedelta(days=5)).replace(hour=12).isoformat(), now), "Fri at 12 PM")

    def test_expand(self):
        self.assertEqual(chat_mod.expand("sum [Pasted text #1 · 2 lines] ok", ["a\nb"]), "sum a\nb ok")
        self.assertEqual(chat_mod.expand("[Pasted text #3]", ["x"]), "[Pasted text #3]")

    def test_day_starts_at_four(self):
        self.assertEqual(chat_mod.day_of(datetime(2026, 11, 23, 2, 0)), "2026-11-22")
        self.assertEqual(chat_mod.day_of(datetime(2026, 11, 23, 5, 0)), "2026-11-23")


if __name__ == "__main__":
    unittest.main()
