"""Seeded tests for the priority engine. Run: python3 -m unittest discover -s engine/tests"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import brain  # noqa: E402
from brain_engine import empty_overrides, recommend  # noqa: E402

TZ = timezone(timedelta(hours=-5))
NOW = datetime(2026, 11, 5, 14, 0, tzinfo=TZ)   # Thursday 2pm
CONFIG = json.loads((Path(__file__).resolve().parents[1] / "config.json").read_text())


def iso(dt):
    return dt.isoformat()


def task(tid, title, lst, due=None, **kw):
    t = {"id": tid, "title": title, "notes": "", "list": lst, "dueDate": iso(due) if due else None,
         "priority": "medium", "stage": "general", "estimatedMinutes": None, "dependsOnTaskID": None,
         "progressPercent": None, "startedAt": None, "rescheduleCount": 0}
    t.update(kw)
    return t


def snap(*tasks, age_hours=1, now=NOW):
    return {"schemaVersion": 1, "generatedAt": iso(now - timedelta(hours=age_hours)),
            "lists": [], "tasks": list(tasks)}


def rec(snapshot, overrides=None, commitments=None, now=NOW):
    result, ov = recommend(snapshot, overrides or empty_overrides(), commitments or [], CONFIG, now)
    return result


def order(result):
    return [e["title"] for e in ([result["current"]] if result["current"] else []) + result["queue"]]


H = lambda n: NOW + timedelta(hours=n)   # noqa: E731


class Ranking(unittest.TestCase):
    def test_nearest_deadline_beats_category(self):
        r = rec(snap(task("a", "School later", "Network Security", H(30)),
                     task("b", "Internship sooner", "Internships", H(10))))
        self.assertEqual(order(r), ["Internship sooner", "School later"])

    def test_tie_goes_to_category_order_and_says_so(self):
        due = H(20)
        r = rec(snap(task("c", "sec", "Security Projects", due),
                     task("b", "intern", "Internships", due),
                     task("a", "school", "Cloud Computing", due)))
        self.assertEqual(order(r), ["school", "intern", "sec"])
        self.assertIn("Schoolwork wins ties", r["current"]["why"])
        self.assertIn("Ranked above Internships", r["current"]["why"])

    def test_undated_after_dated_and_by_category(self):
        r = rec(snap(task("a", "personal", "Personal"), task("b", "sec", "Security Projects"),
                     task("c", "dated", "Internships", H(200))))
        self.assertEqual(order(r), ["dated", "sec", "personal"])
        self.assertIn("No deadline", r["queue"][0]["why"])

    def test_priority_then_title_break_remaining_ties(self):
        due = H(5)
        r = rec(snap(task("a", "b-low", "Cloud Computing", due, priority="low"),
                     task("b", "a-high", "Cloud Computing", due, priority="high")))
        self.assertEqual(order(r), ["a-high", "b-low"])

    def test_same_input_is_byte_identical(self):
        s = snap(task("a", "x", "Internships", H(3)), task("b", "y", "Personal"))
        self.assertEqual(json.dumps(rec(s), sort_keys=True), json.dumps(rec(s), sort_keys=True))


class Escalation(unittest.TestCase):
    def test_missed_hard_outranks_sooner_future_and_is_labeled(self):
        r = rec(snap(task("a", "future soon", "Internships", H(1)),
                     task("b", "missed", "Cloud Computing", H(-30))))
        self.assertEqual(order(r), ["missed", "future soon"])
        self.assertEqual(r["current"]["band"], "escalated")
        self.assertIn("Slipped past", r["current"]["why"])
        self.assertEqual(r["categories"][0]["escalated"], 1)

    def test_missed_soft_reflows_without_overdue_wording(self):
        r = rec(snap(task("a", "sec step", "Security Projects", H(-72))))
        c = r["current"]
        self.assertEqual(c["band"], "dated")
        self.assertIn("Carried over to today", c["why"])
        for word in ("Missed", "overdue", "Overdue", "late"):
            self.assertNotIn(word, c["why"])
        self.assertEqual(r["categories"][2]["escalated"], 0)


class Overrides(unittest.TestCase):
    def ov(self, **kw):
        o = empty_overrides()
        o.update(kw)
        return o

    def test_snooze_hides_then_returns(self):
        s = snap(task("a", "first", "Cloud Computing", H(50)), task("b", "second", "Internships", H(60)))
        o = self.ov(snoozes=[{"taskId": "a", "until": iso(H(3))}])
        self.assertEqual(rec(s, o)["current"]["title"], "second")
        later = NOW + timedelta(hours=4)
        self.assertEqual(rec(snap(*s["tasks"], now=later), o, now=later)["current"]["title"], "first")

    def test_snooze_voided_when_hard_deadline_passes(self):
        t = task("a", "due soon", "Network Security", H(1))
        o = self.ov(snoozes=[{"taskId": "a", "until": iso(H(30))}])
        self.assertTrue(rec(snap(t), o)["empty"])                # still before the deadline: hidden
        later = H(2)
        r = rec(snap(t, now=later), o, now=later)               # deadline passed: back, escalated
        self.assertEqual(r["current"]["band"], "escalated")

    def test_soft_snooze_not_voided_by_past_due(self):
        o = self.ov(snoozes=[{"taskId": "a", "until": iso(H(5))}])
        self.assertTrue(rec(snap(task("a", "soft", "Security Projects", H(-5))), o)["empty"])

    def test_skip_hides_today_and_expires(self):
        s = snap(task("a", "skipped", "Cloud Computing", H(100)), task("b", "other", "Internships", H(120)))
        o = self.ov(skips=[{"taskId": "a", "forDate": "2026-11-05"}])
        self.assertEqual(rec(s, o)["current"]["title"], "other")
        tomorrow = NOW + timedelta(days=1)
        r = rec(snap(*s["tasks"], now=tomorrow), o, now=tomorrow)
        self.assertEqual(r["current"]["title"], "skipped")
        self.assertEqual(r["activeOverrides"]["skips"], 0)

    def test_skip_keeps_only_urgent_hard_deadline(self):
        s = snap(task("a", "urgent", "Cloud Computing", H(5)), task("b", "later", "Internships", H(100)))
        o = self.ov(skips=[{"taskId": "a", "forDate": "2026-11-05"}])
        c = rec(s, o)["current"]
        self.assertEqual(c["title"], "urgent")
        self.assertIn("only urgent deadline", c["why"])

    def test_pin_beats_escalation_and_mentions_overdue(self):
        s = snap(task("a", "missed", "Cloud Computing", H(-5)), task("b", "pinned", "Personal"))
        o = self.ov(pins=[{"taskId": "b", "pinnedAt": iso(NOW), "forDate": "2026-11-05"}])
        r = rec(s, o)
        self.assertEqual(order(r), ["pinned", "missed"])
        self.assertIn("1 more needs a look", r["current"]["why"])

    def test_pin_overrides_snooze_and_skip_but_not_blocked(self):
        s = snap(task("a", "p", "Personal"), task("dep", "dep", "Personal"),
                 task("b", "blocked pin", "Personal", dependsOnTaskID="dep"))
        o = self.ov(pins=[{"taskId": "a", "pinnedAt": iso(NOW), "forDate": "2026-11-05"},
                          {"taskId": "b", "pinnedAt": iso(NOW), "forDate": "2026-11-05"}],
                    skips=[{"taskId": "a", "forDate": "2026-11-05"}])
        self.assertNotIn("blocked pin", order(rec(s, o)))
        self.assertEqual(rec(s, o)["current"]["title"], "p")

    def test_pin_expires_next_day(self):
        t = task("a", "p", "Personal")
        o = self.ov(pins=[{"taskId": "a", "pinnedAt": iso(NOW), "forDate": "2026-11-05"}])
        tomorrow = NOW + timedelta(days=1)
        self.assertEqual(rec(snap(t, now=tomorrow), o, now=tomorrow)["current"]["band"], "undated")

    def test_overrides_for_gone_tasks_are_pruned(self):
        o = self.ov(pins=[{"taskId": "gone", "pinnedAt": iso(NOW), "forDate": "2026-11-05"}],
                    snoozes=[{"taskId": "gone", "until": iso(H(5))}])
        _, pruned = recommend(snap(task("a", "x", "Personal")), o, [], CONFIG, NOW)
        self.assertEqual((pruned["pins"], pruned["snoozes"]), ([], []))

    def test_low_energy_keeps_urgent_then_shortest(self):
        s = snap(task("u", "urgent long", "Cloud Computing", H(10), estimatedMinutes=120),
                 task("l", "long", "Cloud Computing", H(60), estimatedMinutes=90),
                 task("s", "short", "Internships", H(80), estimatedMinutes=10),
                 task("m", "mid undated", "Security Projects", estimatedMinutes=30))
        o = self.ov(mode={"lowEnergy": True, "since": iso(NOW)})
        r = rec(s, o)
        self.assertEqual(order(r), ["urgent long", "short", "mid undated", "long"])
        self.assertIn("Low-energy", r["queue"][0]["why"])
        self.assertNotIn("Low-energy", r["current"]["why"])

    def test_low_energy_softens_missed_wording(self):
        s = snap(task("m", "missed one", "Cloud Computing", H(-30)))
        normal = rec(s)["current"]["why"]
        low = rec(s, self.ov(mode={"lowEnergy": True, "since": iso(NOW)}))["current"]["why"]
        self.assertIn("Slipped past", normal)
        self.assertNotIn("Slipped", low)
        self.assertIn("Past its deadline", low)

    def test_low_energy_resets_next_day(self):
        o = self.ov(mode={"lowEnergy": True, "since": iso(NOW)})
        tomorrow = NOW + timedelta(days=1)
        self.assertFalse(rec(snap(task("a", "x", "Personal"), now=tomorrow), o, now=tomorrow)["mode"]["lowEnergy"])


class DependenciesAndEmpty(unittest.TestCase):
    def test_blocked_task_never_current_unblocks_when_dep_gone(self):
        blocked = task("b", "blocked", "Cloud Computing", H(1), dependsOnTaskID="dep")
        s = snap(task("dep", "dep", "Personal"), blocked)
        self.assertEqual(rec(s)["current"]["title"], "dep")
        self.assertEqual(rec(snap(blocked))["current"]["title"], "blocked")

    def test_empty_snapshot(self):
        r = rec(snap())
        self.assertTrue(r["empty"])
        self.assertIsNone(r["current"])
        self.assertEqual(r["emptyReason"], "Nothing needs you right now. That's allowed.")

    def test_all_snoozed(self):
        o = empty_overrides()
        o["snoozes"] = [{"taskId": "a", "until": iso(H(2))}]
        r = rec(snap(task("a", "x", "Personal")), o)
        self.assertTrue(r["empty"])
        self.assertIn("parked or waiting", r["emptyReason"])

    def test_general_tasks_placed_by_title_rules(self):
        r = rec(snap(task("a", "Apply for 10 jobs", "General"), task("b", "Complete a security project", "General"),
                     task("c", "Water plants", "General")))
        cats = {e["title"]: e["category"] for e in [r["current"]] + r["queue"]}
        self.assertEqual(cats, {"Apply for 10 jobs": "Internships", "Complete a security project": "Security",
                                "Water plants": "Other"})

    def test_unmapped_list_is_never_lost(self):
        r = rec(snap(task("a", "mystery", "Errands"), task("b", "sec", "Security Projects")))
        self.assertEqual(order(r), ["sec", "mystery"])   # unmapped ranks below named categories
        self.assertEqual(r["categories"][-1]["name"], "Other")


class TimeModel(unittest.TestCase):
    def test_minutes_use_estimate_else_category_default(self):
        r = rec(snap(task("a", "est", "Cloud Computing", H(2), estimatedMinutes=25),
                     task("b", "noest", "Internships", H(3))))
        self.assertEqual((r["current"]["minutes"], r["current"]["minutesEstimated"]), (25, True))
        self.assertEqual((r["queue"][0]["minutes"], r["queue"][0]["minutesEstimated"]), (30, False))

    def test_day_load_subtracts_commitments_and_levels(self):
        s = snap(task("a", "due today", "Cloud Computing", NOW.replace(hour=23, minute=59)),
                 task("b", "tomorrow", "Cloud Computing", H(30)))
        # 14:00-24:00 = 600 free; class 15:00-17:00 = 120 off -> 480
        c = [{"start": iso(NOW.replace(hour=15)), "end": iso(NOW.replace(hour=17)), "label": "class"},
             {"start": iso(NOW.replace(hour=16)), "end": iso(NOW.replace(hour=16, minute=30)), "label": "overlap"}]
        d = rec(s, commitments=c)["dayLoad"]
        self.assertEqual((d["freeMinutes"], d["plannedMinutes"]), (480, 60))
        self.assertEqual(d["level"], "light")
        heavy = rec(snap(task("a", "big", "Cloud Computing", NOW.replace(hour=23), estimatedMinutes=400)),
                    commitments=c)["dayLoad"]
        self.assertEqual(heavy["level"], "heavy")

    def test_stale_flag(self):
        self.assertFalse(rec(snap(task("a", "x", "Personal"), age_hours=2))["snapshot"]["stale"])
        self.assertTrue(rec(snap(task("a", "x", "Personal"), age_hours=30))["snapshot"]["stale"])


class Cli(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.cfg = dict(CONFIG, snapshotPath=str(self.dir / "snap.json"),
                        commitmentsPath=str(self.dir / "c.json"),
                        overridesPath=str(self.dir / "ov.json"),
                        recommendationPath=str(self.dir / "rec.json"),
                        errorPath=str(self.dir / "err.json"))
        (self.dir / "config.json").write_text(json.dumps(self.cfg))
        self.args = ["--config", str(self.dir / "config.json")]

    def write_snap(self, *tasks):
        now = datetime.now().astimezone()
        (self.dir / "snap.json").write_text(json.dumps(snap(*tasks, now=now)))

    def test_bad_snapshot_keeps_last_good_and_flags_error(self):
        due = datetime.now().astimezone() + timedelta(days=2)
        self.write_snap(task("a-1", "good", "Cloud Computing", due))
        brain.main(self.args + ["recommend"])
        good = (self.dir / "rec.json").read_text()
        (self.dir / "snap.json").write_text("{not json")
        with self.assertRaises(SystemExit):
            brain.main(self.args + ["recommend"])
        self.assertEqual((self.dir / "rec.json").read_text(), good)
        self.assertTrue((self.dir / "err.json").exists())
        self.write_snap(task("a-1", "good", "Cloud Computing", due))
        brain.main(self.args + ["recommend"])
        self.assertFalse((self.dir / "err.json").exists())

    def test_pin_skip_snooze_lowenergy_roundtrip(self):
        far = datetime.now().astimezone() + timedelta(days=5)
        self.write_snap(task("aaaa1111", "Read module five", "Cloud Computing", far),
                        task("bbbb2222", "Apply to Acme", "Internships", far + timedelta(days=1)))
        brain.main(self.args + ["pin", "acme"])
        self.assertEqual(json.loads((self.dir / "rec.json").read_text())["current"]["title"], "Apply to Acme")
        brain.main(self.args + ["unpin", "bbbb"])
        self.assertEqual(json.loads((self.dir / "rec.json").read_text())["current"]["title"], "Read module five")
        brain.main(self.args + ["skip", "module"])
        self.assertEqual(json.loads((self.dir / "rec.json").read_text())["current"]["title"], "Apply to Acme")
        brain.main(self.args + ["unskip", "module"])
        brain.main(self.args + ["snooze", "aaaa", "--hours", "2"])
        self.assertEqual(json.loads((self.dir / "rec.json").read_text())["current"]["title"], "Apply to Acme")
        brain.main(self.args + ["lowenergy", "on"])
        self.assertTrue(json.loads((self.dir / "rec.json").read_text())["mode"]["lowEnergy"])
        with self.assertRaises(SystemExit):
            brain.main(self.args + ["pin", "nothing-matches"])


    def test_play_is_never_ranked_even_when_pinned(self):
        o = empty_overrides(); o["pins"] = [{"taskId": "g", "pinnedAt": iso(NOW), "forDate": "2026-11-05"}]
        r = rec(snap(task("g", "Golf", "Play"), task("s", "Side", "Side Projects"), task("e", "Email", "Personal")), o)
        ids = [e["taskId"] for e in ([r["current"]] if r["current"] else []) + r["queue"]]
        self.assertEqual(ids, ["e"])
        self.assertEqual([c["open"] for c in r["categories"] if c["name"] == "Play"], [2])


    def test_free_time_runs_until_midnight(self):
        r = rec(snap(task("a", "x", "Internships")), commitments=[])
        # NOW is 14:00; workday ends at 24:00 -> 10 hours
        self.assertEqual(r["dayLoad"]["freeMinutes"], 600)


    def test_estimate_rules_and_duration_format(self):
        from brain_engine import fmt_dur
        r = rec(snap(task("a", "Read Chapter 5", "Network Security", H(30)),
                     task("b", "Lab 1 - OSINT", "Network Security", H(30)),
                     task("c", "AWS Lab 4 (MFA)", "Cloud Computing", H(30)),
                     task("d", "Read Chapter 9", "Cloud Computing", H(30)),
                     task("e", "Lab 2", "Network Security", H(30), estimatedMinutes=45)))
        mins = {e["title"]: e["minutes"] for e in ([r["current"]] + r["queue"])}
        self.assertEqual((mins["Read Chapter 5"], mins["Lab 1 - OSINT"], mins["AWS Lab 4 (MFA)"]), (90, 120, 60))
        self.assertEqual(mins["Read Chapter 9"], 60)      # Cloud reading has no rule: school default
        self.assertEqual(mins["Lab 2"], 45)                # her own estimate always wins
        self.assertEqual([fmt_dur(x) for x in (45, 90, 120, 7000, 0)], ["45 min", "1 h 30 min", "2 h", "116 h 40 min", "0 min"])


    def test_day_load_by_date_has_today_and_tomorrow(self):
        r = rec(snap(task("a", "x", "Cloud Computing", NOW + timedelta(days=1, hours=2), estimatedMinutes=900)))
        d = r["dayLoadByDate"]
        self.assertEqual(sorted(d), ["2026-11-05", "2026-11-06"])
        self.assertEqual(d["2026-11-05"], "light")
        self.assertEqual(d["2026-11-06"], "heavy")       # 15 h due tomorrow against a 15 h window


    def test_security_shows_one_project_at_a_time_and_it_sticks(self):
        tasks = [task("a", "A1 pipeline", "Security Projects", notes="Status: Not started"),
                 task("b", "Detector", "Security Projects", notes="Status: Next up, not started", priority="high"),
                 task("c", "Traffic analyzer", "Security Projects", notes="Status: In progress")]
        r, ov = recommend(snap(*tasks), empty_overrides(), [], CONFIG, NOW)
        sec = [c for c in r["categories"] if c["name"] == "Security"][0]
        self.assertEqual((sec["open"], sec["later"], sec["focusId"]), (1, 2, "c"))     # already started wins
        shown = [e["taskId"] for e in ([r["current"]] if r["current"] else []) + r["queue"] if e["category"] == "Security"]
        self.assertEqual(shown, ["c"])
        self.assertIn("one project", r["current"]["why"].lower())
        tasks[2]["notes"] = "Status: Not started"                                    # sticky even if it no longer ranks first
        r2, ov2 = recommend(snap(*tasks), ov, [], CONFIG, NOW)
        self.assertEqual([c for c in r2["categories"] if c["name"] == "Security"][0]["focusId"], "c")
        self.assertEqual(ov2["focus"]["Security"], "c")
        tasks[0]["notes"] = "Status: In progress"                                      # a started project beats one that was only picked
        r2b, _ = recommend(snap(*tasks), ov2, [], CONFIG, NOW)
        self.assertEqual([c for c in r2b["categories"] if c["name"] == "Security"][0]["focusId"], "a")
        tasks[0]["notes"] = "Status: Not started"
        # skipping it swaps to the next best (the high-priority one), and finishing it moves on
        sk = dict(ov2, skips=[{"taskId": "c", "skippedAt": iso(NOW), "forDate": "2026-11-05"}])
        r3, _ = recommend(snap(*tasks), sk, [], CONFIG, NOW)
        self.assertEqual([c for c in r3["categories"] if c["name"] == "Security"][0]["focusId"], "b")
        r4, _ = recommend(snap(tasks[0], tasks[1]), ov2, [], CONFIG, NOW)
        self.assertEqual([c for c in r4["categories"] if c["name"] == "Security"][0]["focusId"], "b")


if __name__ == "__main__":
    unittest.main()
