import json, sys, tempfile, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import blocks as B  # noqa

TZ = timezone(timedelta(hours=-5))
NOW = datetime(2026, 11, 5, 14, 0, tzinfo=TZ)
ECFG = json.loads((HERE.parent / "engine" / "config.json").read_text())


def entry(tid, title, cat="Schoolwork", minutes=30):
    return {"taskId": tid, "title": title, "category": cat, "minutes": minutes, "why": "because"}


def task(tid, title, lst="Network Security", est=None):
    return {"id": tid, "title": title, "list": lst, "estimatedMinutes": est}


def ctx(level="normal", cur=None, queue=(), tasks=()):
    rec = {"current": cur or entry("T1", "Read ch 5"), "queue": list(queue), "dayLoad": {"level": level}}
    return {"rec": rec, "tasks": list(tasks) if tasks is not None else None, "engine": ECFG}


TASKS = [task("T1", "Read ch 5"), task("P1", "Play guitar", "Play", 20), task("P2", "Long hike", "Play", 120)]


def start(c=None, now=NOW, **kw):
    kw.setdefault("countdown", 0)
    st, _ = B.advance(B.new_state(), "start_work", c or ctx(tasks=TASKS), ECFG, now, **kw)
    return st


def lowctx(level="normal", **kw):
    c = ctx(level, **kw)
    c["rec"]["mode"] = {"lowEnergy": True}
    return c


class LowEnergy(unittest.TestCase):
    def test_blocks_are_shorter(self):
        c = lowctx(cur=entry("T1", "Big", minutes=120), tasks=TASKS)
        self.assertEqual(start(c)["block"]["minutes"], 20)
        c2 = ctx(cur=entry("T1", "Big", minutes=120), tasks=TASKS)
        self.assertEqual(start(c2)["block"]["minutes"], 50)

    def test_breaks_are_gentler(self):
        for level, want_low, want_norm in (("heavy", 20, 10), ("normal", 30, 25), ("light", 45, 45)):
            self.assertEqual(B.break_minutes(lowctx(level)["rec"], ECFG), want_low)
            self.assertEqual(B.break_minutes(ctx(level)["rec"], ECFG), want_norm)


class Flow(unittest.TestCase):
    def test_start_picks_top_non_personal_and_clamps_length(self):
        c = ctx(cur=entry("PP", "Walk", "Play"), queue=[entry("T1", "Big thing", minutes=120)], tasks=TASKS)
        st = start(c)
        self.assertEqual(st["phase"], "work"); self.assertEqual(st["block"]["taskId"], "T1")
        self.assertEqual(st["block"]["minutes"], 50)
        short = start(ctx(cur=entry("T1", "x", minutes=3), tasks=TASKS))
        self.assertEqual(short["block"]["minutes"], 10)

    def test_start_rejects_personal_unknown_and_double_start(self):
        c = ctx(cur=entry("PP", "Walk", "Play"), tasks=TASKS)
        with self.assertRaises(ValueError): B.advance(B.new_state(), "start_work", c, ECFG, NOW, taskId="PP")
        with self.assertRaises(ValueError): B.advance(B.new_state(), "start_work", c, ECFG, NOW, taskId="nope")
        extra = task("T9", "Lab 7 not in the queue", "Cloud Computing", 45)
        st = start(ctx(tasks=TASKS + [extra]), taskId="T9")      # an open task outside the engine's short queue can be started
        self.assertEqual((st["block"]["taskId"], st["block"]["category"], st["block"]["minutes"]), ("T9", "Schoolwork", 45))
        with self.assertRaises(ValueError): B.advance(B.new_state(), "start_work", c, ECFG, NOW)   # nothing non-personal
        with self.assertRaises(ValueError): B.advance(start(), "start_work", ctx(tasks=TASKS), ECFG, NOW)

    def test_timer_marks_over(self):
        st = start()
        st, ev = B.tick(st, ctx(tasks=TASKS), NOW + timedelta(minutes=29), ECFG)
        self.assertIsNone(st["block"]["overAt"])
        st, ev = B.tick(st, ctx(tasks=TASKS), NOW + timedelta(minutes=31), ECFG)
        self.assertEqual(st["block"]["overReason"], "timer"); self.assertEqual(ev[0]["type"], "work_over")
        self.assertEqual(B.tick(st, ctx(tasks=TASKS), NOW + timedelta(minutes=32), ECFG)[1], [])   # idempotent

    def test_task_done_marks_over_but_unreadable_snapshot_never_does(self):
        st = start()
        gone, _ = B.tick(st, ctx(tasks=[task("OTHER", "x")]), NOW + timedelta(minutes=5), ECFG)
        self.assertEqual(gone["block"]["overReason"], "task-done")
        unknown, _ = B.tick(st, ctx(tasks=None), NOW + timedelta(minutes=5), ECFG)
        self.assertIsNone(unknown["block"]["overAt"])

    def test_extend_before_and_after_over(self):
        st = start()
        a, _ = B.advance(st, "extend", ctx(tasks=TASKS), ECFG, NOW + timedelta(minutes=10))
        self.assertEqual(a["block"]["endsAt"], (NOW + timedelta(minutes=45)).isoformat())
        late = NOW + timedelta(minutes=40)
        b, _ = B.advance(st, "extend", ctx(tasks=TASKS), ECFG, late)
        self.assertEqual(b["block"]["endsAt"], (late + timedelta(minutes=15)).isoformat())
        self.assertIsNone(b["block"]["overAt"])
        self.assertNotEqual(B.push_view(st)["id"], B.push_view(b)["id"])   # a new end can ping again
        with self.assertRaises(ValueError): B.advance(st, "extend", ctx(tasks=TASKS), ECFG, NOW, minutes=2)

    def test_break_length_follows_day_load(self):
        for level, mins in (("light", 45), ("normal", 25), ("heavy", 10)):
            c = ctx(level, tasks=TASKS)
            st, _ = B.advance(start(c), "take_break", c, ECFG, NOW + timedelta(minutes=30))
            self.assertEqual(st["block"]["minutes"], mins, level)

    def test_break_suggestion_fits_and_rotates(self):
        c = ctx("heavy", tasks=TASKS)        # 10-minute break: guitar (20) and hike (120) both exceed it
        st, ev = B.advance(start(c), "take_break", c, ECFG, NOW + timedelta(minutes=30))
        self.assertEqual(st["block"]["suggestion"]["title"], "Play guitar")   # nothing fits 10 min: the shortest wins
        c2 = ctx("light", tasks=TASKS)       # 45 minutes: guitar fits, hike does not
        st2, _ = B.advance(start(c2), "take_break", c2, ECFG, NOW + timedelta(minutes=30))
        self.assertEqual(st2["block"]["suggestion"]["title"], "Play guitar")
        # rotate: guitar was just offered, so with both fitting the other one comes next
        tasks = [task("P1", "Play guitar", "Play", 20), task("P3", "Read a novel", "Play", 30), task("T1", "Read ch 5")]
        c3 = ctx("light", tasks=tasks)
        first, _ = B.advance(start(c3), "take_break", c3, ECFG, NOW + timedelta(minutes=30))
        s = first["block"]["suggestion"]["title"]
        st3 = dict(start(c3), suggested=first["suggested"])
        second, _ = B.advance(st3, "take_break", c3, ECFG, NOW + timedelta(hours=2))
        self.assertNotEqual(s, second["block"]["suggestion"]["title"])

    def test_empty_personal_list(self):
        c = ctx(tasks=[task("T1", "Read ch 5")])
        st, _ = B.advance(start(c), "take_break", c, ECFG, NOW + timedelta(minutes=30))
        self.assertIsNone(st["block"]["suggestion"])

    def test_done_today_is_not_offered_again(self):
        c = ctx("light", tasks=TASKS)
        st, _ = B.advance(start(c), "take_break", c, ECFG, NOW + timedelta(minutes=30))
        picked = st["block"]["suggestion"]["taskId"]
        st, _ = B.advance(st, "end_break", c, ECFG, NOW + timedelta(minutes=40))
        st, _ = B.advance(st, "checkin", c, ECFG, NOW + timedelta(minutes=41), answer="yes")
        self.assertTrue(st["suggested"][picked]["did"])
        self.assertEqual(st["lastCheckin"]["answer"], "yes")
        st2, _ = B.advance(dict(st, phase="idle"), "start_work", c, ECFG, NOW + timedelta(minutes=45))
        st2, _ = B.advance(st2, "take_break", c, ECFG, NOW + timedelta(hours=1))
        self.assertNotEqual(st2["block"]["suggestion"]["taskId"], picked)

    def test_full_cycle_and_routing(self):
        c = ctx("normal", cur=entry("T1", "Read ch 5"), queue=[entry("P1", "Play guitar", "Play"), entry("I1", "Apply to 10", "Internships")], tasks=TASKS + [task("I1", "Apply to 10", "Internships")])
        st = start(c)
        st, _ = B.advance(st, "take_break", c, ECFG, NOW + timedelta(minutes=30))
        self.assertEqual(st["phase"], "break")
        st, ev = B.tick(st, c, NOW + timedelta(minutes=30 + 26), ECFG)           # break timer ends
        self.assertEqual(st["phase"], "checkin"); self.assertEqual(ev[0]["type"], "break_over")
        with self.assertRaises(ValueError): B.advance(st, "start_work", c, ECFG, NOW + timedelta(hours=1))
        with self.assertRaises(ValueError): B.advance(st, "checkin", c, ECFG, NOW + timedelta(hours=1), answer="maybe")
        st, _ = B.advance(st, "checkin", c, ECFG, NOW + timedelta(hours=1), answer="later")
        self.assertEqual(st["phase"], "idle")
        v = B.view(st, ctx("normal", cur=entry("P1", "Play guitar", "Play"), queue=[entry("I1", "Apply to 10", "Internships")], tasks=TASKS), ECFG, NOW)
        self.assertEqual(v["next"]["title"], "Apply to 10")                       # routes past Personal items

    def test_illegal_actions_leave_state_unchanged(self):
        st = B.new_state()
        for a in ("extend", "cancel", "take_break", "skip_break", "end_break", "checkin", "bogus"):
            with self.assertRaises(ValueError): B.advance(st, a, ctx(tasks=TASKS), ECFG, NOW, answer="yes")
        self.assertEqual(st, B.new_state())

    def test_skip_cancel_and_early_end(self):
        c = ctx(tasks=TASKS)
        self.assertEqual(B.advance(start(c), "skip_break", c, ECFG, NOW)[0]["phase"], "idle")
        self.assertEqual(B.advance(start(c), "cancel", c, ECFG, NOW)[0]["phase"], "idle")
        st, _ = B.advance(start(c), "take_break", c, ECFG, NOW)
        ended = B.advance(st, "end_break", c, ECFG, NOW)[0]
        self.assertEqual(ended["phase"], "checkin"); self.assertEqual(B.push_view(ended)["endsAt"], NOW.isoformat())

    def test_old_block_expires_to_idle(self):
        st = start()
        st, ev = B.tick(st, ctx(tasks=TASKS), NOW + timedelta(hours=10), ECFG)
        self.assertEqual(st["phase"], "idle"); self.assertEqual(ev[0]["type"], "expired")
        c = ctx(tasks=TASKS)
        s2, _ = B.advance(start(c), "take_break", c, ECFG, NOW)
        s2, _ = B.tick(s2, c, NOW + timedelta(hours=3), ECFG)                     # checkin
        s2, _ = B.tick(s2, c, NOW + timedelta(hours=12), ECFG)
        self.assertEqual((s2["phase"], s2["lastCheckin"]["answer"]), ("idle", "expired"))

    def test_push_view(self):
        self.assertIsNone(B.push_view(B.new_state()))
        w = B.push_view(start()); self.assertEqual((w["kind"], w["title"]), ("work", "Read ch 5"))
        c = ctx(tasks=TASKS)
        st, _ = B.advance(start(c), "take_break", c, ECFG, NOW)
        k = B.push_view(st); self.assertEqual(k["kind"], "break"); self.assertEqual(k["endsAt"], st["block"]["endsAt"])
        st, _ = B.tick(st, c, NOW + timedelta(hours=1), ECFG)                     # checkin keeps the ended break visible
        self.assertEqual(B.push_view(st)["kind"], "break")


class Countdown(unittest.TestCase):
    def test_default_countdown_then_work_begins_on_time(self):
        c = ctx(tasks=TASKS)
        st, ev = B.advance(B.new_state(), "start_work", c, ECFG, NOW)
        self.assertEqual(st["phase"], "starting"); self.assertEqual(ev[0]["type"], "work_countdown")
        self.assertEqual(st["block"]["startsAt"], (NOW + timedelta(seconds=3)).isoformat())   # the 3-2-1
        self.assertIsNone(B.push_view(st))                                   # nothing to ping about yet
        st, ev = B.tick(st, c, NOW + timedelta(seconds=2), ECFG)
        self.assertEqual((st["phase"], ev), ("starting", []))
        st, ev = B.tick(st, c, NOW + timedelta(seconds=4), ECFG)
        self.assertEqual(st["phase"], "work"); self.assertEqual(ev[0]["via"], "countdown")
        self.assertEqual(st["block"]["startedAt"], (NOW + timedelta(seconds=3)).isoformat())   # clock starts at the countdown end
        self.assertEqual(st["block"]["endsAt"], (NOW + timedelta(seconds=3, minutes=30)).isoformat())
        v = B.view(st, c, ECFG, NOW + timedelta(seconds=3 + 125))
        self.assertEqual(v["elapsedSeconds"], 125)                           # elapsed timer counts from the clock start
        v = B.view(st, c, ECFG, NOW + timedelta(minutes=40))
        self.assertGreater(v["elapsedSeconds"], 30 * 60)                     # keeps counting past the planned end
        self.assertIsNone(B.view(B.new_state(), c, ECFG, NOW)["elapsedSeconds"])
        done, ev = B.advance(st, "take_break", c, ECFG, NOW + timedelta(seconds=3 + 600))
        self.assertEqual(ev[0]["workedSeconds"], 600)

    def test_custom_and_zero_countdown(self):
        c = ctx(tasks=TASKS)
        self.assertEqual(B.advance(B.new_state(), "start_work", c, ECFG, NOW, countdown=0)[0]["phase"], "work")
        st, _ = B.advance(B.new_state(), "start_work", c, ECFG, NOW, countdown=60)
        self.assertEqual(st["block"]["startsAt"], (NOW + timedelta(seconds=60)).isoformat())
        for bad in (-1, 5000):
            with self.assertRaises(ValueError): B.advance(B.new_state(), "start_work", c, ECFG, NOW, countdown=bad)
        cfg2 = dict(ECFG, startCountdownSeconds=0)
        self.assertEqual(B.advance(B.new_state(), "start_work", c, cfg2, NOW)[0]["phase"], "work")

    def test_begin_now_and_cancel(self):
        c = ctx(tasks=TASKS)
        st, _ = B.advance(B.new_state(), "start_work", c, ECFG, NOW)
        t = NOW + timedelta(seconds=1)
        w, ev = B.advance(st, "begin_now", c, ECFG, t)
        self.assertEqual((w["phase"], w["block"]["startedAt"]), ("work", t.isoformat()))
        self.assertEqual(w["block"]["endsAt"], (t + timedelta(minutes=30)).isoformat())
        self.assertEqual(B.advance(st, "cancel", c, ECFG, t)[0]["phase"], "idle")
        for a in ("take_break", "skip_break", "extend", "end_break", "checkin"):
            with self.assertRaises(ValueError): B.advance(st, a, c, ECFG, t, answer="yes")
        with self.assertRaises(ValueError): B.advance(B.new_state(), "begin_now", c, ECFG, t)

    def test_task_gone_during_countdown_cancels(self):
        st, _ = B.advance(B.new_state(), "start_work", ctx(tasks=TASKS), ECFG, NOW)
        st, ev = B.tick(st, ctx(tasks=[task("X", "other")]), NOW + timedelta(seconds=1), ECFG)
        self.assertEqual((st["phase"], ev[0]["type"]), ("idle", "work_cancel"))
        st2, _ = B.advance(B.new_state(), "start_work", ctx(tasks=TASKS), ECFG, NOW)
        self.assertEqual(B.tick(st2, ctx(tasks=None), NOW + timedelta(seconds=1), ECFG)[0]["phase"], "starting")

    def test_late_tick_after_countdown_goes_straight_over(self):
        st, _ = B.advance(B.new_state(), "start_work", ctx(tasks=TASKS), ECFG, NOW)
        st, ev = B.tick(st, ctx(tasks=TASKS), NOW + timedelta(hours=1), ECFG)       # server was off the whole time
        self.assertEqual((st["phase"], st["block"]["overReason"]), ("work", "timer"))
        self.assertEqual([e["type"] for e in ev], ["work_start", "work_over"])

    def test_stale_countdown_expires(self):
        st, _ = B.advance(B.new_state(), "start_work", ctx(tasks=TASKS), ECFG, NOW)
        self.assertEqual(B.tick(st, ctx(tasks=TASKS), NOW + timedelta(hours=12), ECFG)[0]["phase"], "idle")


class Files(unittest.TestCase):
    def test_roundtrip_and_corrupt_recovery(self):
        d = Path(tempfile.mkdtemp()); p = d / "blocks.json"
        self.assertEqual(B.load_state(p), (B.new_state(), None))
        B.save_state(start(), p)
        self.assertEqual(B.load_state(p)[0]["phase"], "work")
        p.write_text("{not json")
        st, err = B.load_state(p)
        self.assertEqual(st["phase"], "idle"); self.assertIn("reset", err)
        self.assertTrue((d / "blocks.json.bad").exists())
        p.write_text('{"phase": "weird"}')
        self.assertIsNotNone(B.load_state(p)[1])

    def test_history_appends(self):
        h = Path(tempfile.mkdtemp()) / "h.jsonl"
        B.append_history([{"a": 1}], h); B.append_history([{"b": 2}], h); B.append_history([], h)
        self.assertEqual(len(h.read_text().splitlines()), 2)


class BreakSkipsLongKinds(unittest.TestCase):
    def test_game_and_project_do_not_fit_a_short_break(self):
        tasks = [task("G", "Zelda", "Games"), task("S", "Traffic analyzer", "Side Projects"), task("W", "Walk", "Play", 15)]
        pick = B.pick_break_item(tasks, {}, 25, ECFG, NOW)
        self.assertEqual(pick["taskId"], "W")
        self.assertIsNone(B.pick_break_item(tasks[:2], {}, 25, ECFG, NOW))


class ForgotToStart(unittest.TestCase):
    def test_started_earlier_backdates_the_clock(self):
        st, ev = B.advance(B.new_state(), "start_work", ctx(tasks=TASKS), ECFG, NOW, startedAgo=20)
        self.assertEqual(st["phase"], "work")
        self.assertEqual(B.elapsed_seconds(st["block"], NOW), 20 * 60)
        self.assertEqual(ev[-1]["via"], "forgot-to-start")
        self.assertEqual(ev[-1]["agoMinutes"], 20)

    def test_long_ago_is_over_on_next_tick_and_bad_values_rejected(self):
        st, _ = B.advance(B.new_state(), "start_work", ctx(tasks=TASKS), ECFG, NOW, startedAgo=300)
        st, ev = B.tick(st, ctx(tasks=TASKS), NOW, ECFG)
        self.assertTrue(st["block"]["overAt"])
        for bad in (0, 721, -5):
            with self.assertRaises(ValueError):
                B.advance(B.new_state(), "start_work", ctx(tasks=TASKS), ECFG, NOW, startedAgo=bad)


if __name__ == "__main__":
    unittest.main()
