import sys, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from push_logic import decide

TZ = timezone(timedelta(hours=-5))
NOW = datetime(2026, 11, 5, 14, 0, tzinfo=TZ)
CFG = {}
OK = {"importAgeHours": 1, "importFailed": False}


def rec(tid="a", stale=False, queue=()):
    return {"current": {"taskId": tid, "title": "Read Chapter 5", "minutes": 60, "why": "Due today"},
            "queue": list(queue), "snapshot": {"stale": stale}}


class T(unittest.TestCase):
    def test_ping_on_transition(self):
        p, st = decide(rec(), {}, None, OK, CFG, NOW)
        self.assertEqual(p["type"], "start"); self.assertIn("Read Chapter 5", p["text"])
        self.assertEqual(st["lastPingKey"], "start:a")

    def test_repeat_suppressed(self):
        _, st = decide(rec(), {}, None, OK, CFG, NOW)
        p, _ = decide(rec(), st, None, OK, CFG, NOW + timedelta(hours=3))
        self.assertIsNone(p)

    def test_none_while_watched(self):
        p, st = decide(rec(), {}, NOW - timedelta(seconds=30), OK, CFG, NOW)
        self.assertIsNone(p); self.assertNotIn("lastPingKey", st)

    def test_old_heartbeat_means_away(self):
        p, _ = decide(rec(), {}, NOW - timedelta(minutes=10), OK, CFG, NOW)
        self.assertIsNotNone(p)

    def test_cap_not_queued(self):
        _, st = decide(rec("a"), {}, None, OK, CFG, NOW)
        p, st2 = decide(rec("b"), st, None, OK, CFG, NOW + timedelta(minutes=20))
        self.assertIsNone(p)
        p, _ = decide(rec("b"), st2, None, OK, CFG, NOW + timedelta(minutes=61))
        self.assertEqual(p["key"], "start:b")

    def test_quiet_hours(self):
        late = NOW.replace(hour=23)
        self.assertIsNone(decide(rec(), {}, None, OK, CFG, late)[0])
        early = NOW.replace(hour=6)
        self.assertIsNone(decide(rec(), {}, None, OK, CFG, early)[0])

    def test_failure_bypasses_cap_once(self):
        _, st = decide(rec("a"), {}, None, OK, CFG, NOW)
        bad = {"importAgeHours": 30}
        p, st2 = decide(rec("a"), st, None, bad, CFG, NOW + timedelta(minutes=5))
        self.assertEqual(p["type"], "failure")
        p, _ = decide(rec("a"), st2, None, bad, CFG, NOW + timedelta(minutes=10))
        self.assertIsNone(p)

    def test_failure_realerts_after_recovery(self):
        bad = {"importFailed": True, "importFailedKey": "x"}
        p, st = decide(None, {}, None, bad, CFG, NOW)
        self.assertEqual(p["type"], "failure")
        _, st = decide(None, st, None, OK, CFG, NOW + timedelta(hours=1))
        p, _ = decide(None, st, None, bad, CFG, NOW + timedelta(hours=2))
        self.assertEqual(p["type"], "failure")

    def test_failure_respects_presence(self):
        p, _ = decide(None, {}, NOW, {"importFailed": True}, CFG, NOW)
        self.assertIsNone(p)

    def test_snapshot_stale_alerts(self):
        p, _ = decide(rec(stale=True), {}, None, OK, CFG, NOW)
        self.assertEqual(p["type"], "failure")

    def test_catchup_after_gap(self):
        st = {"lastOnlineAt": (NOW - timedelta(hours=30)).isoformat()}
        p, _ = decide(rec(queue=[{"title": "x"}]), st, None, OK, CFG, NOW)
        self.assertEqual(p["type"], "catchup"); self.assertIn("Nothing's lost", p["text"])

    def test_stop_when_block_ended(self):
        blk = {"id": "b1", "title": "module 5", "endsAt": (NOW - timedelta(minutes=1)).isoformat()}
        p, _ = decide(rec(), {}, None, OK, CFG, NOW, block=blk)
        self.assertEqual(p["type"], "stop"); self.assertIn("module 5", p["text"])

    def test_block_not_ended_gives_start(self):
        blk = {"id": "b1", "endsAt": (NOW + timedelta(minutes=10)).isoformat()}
        self.assertEqual(decide(rec(), {}, None, OK, CFG, NOW, block=blk)[0]["type"], "start")

    def _brk(self, mins_ago=1, id="k1"):
        return {"id": id, "kind": "break", "title": "walk", "endsAt": (NOW - timedelta(minutes=mins_ago)).isoformat()}

    def test_breakend_pings_when_away(self):
        p, st = decide(rec(), {}, None, OK, CFG, NOW, block=self._brk())
        self.assertEqual(p["type"], "breakend"); self.assertIn("open Thalamus", p["text"])
        self.assertEqual(st["lastPingKey"], "breakend:k1")

    def test_breakend_bypasses_hourly_cap(self):
        st = {"lastPingAt": (NOW - timedelta(minutes=20)).isoformat(), "lastPingKey": "stop:old"}
        p, st2 = decide(rec(), st, None, OK, CFG, NOW, block=self._brk())
        self.assertEqual(p["type"], "breakend")
        self.assertEqual(st2["lastPingAt"], NOW.isoformat())      # and it counts toward the next cap

    def test_stop_still_capped(self):
        st = {"lastPingAt": (NOW - timedelta(minutes=20)).isoformat()}
        blk = {"id": "b1", "title": "x", "endsAt": (NOW - timedelta(minutes=1)).isoformat()}
        self.assertIsNone(decide(rec(), st, None, OK, CFG, NOW, block=blk)[0])

    def test_breakend_silent_while_dashboard_watched(self):
        self.assertIsNone(decide(rec(), {}, NOW - timedelta(seconds=10), OK, CFG, NOW, block=self._brk())[0])

    def test_breakend_respects_quiet_hours(self):
        late = NOW.replace(hour=23, minute=30)
        blk = {"id": "k1", "kind": "break", "title": "walk", "endsAt": (late - timedelta(minutes=1)).isoformat()}
        self.assertIsNone(decide(rec(), {}, None, OK, CFG, late, block=blk)[0])

    def test_breakend_not_repeated(self):
        _, st = decide(rec(), {}, None, OK, CFG, NOW, block=self._brk())
        self.assertIsNone(decide(rec(), st, None, OK, CFG, NOW + timedelta(minutes=5), block=self._brk())[0])

    def test_nothing_to_do(self):
        r = {"current": None, "queue": [], "snapshot": {"stale": False}}
        self.assertIsNone(decide(r, {}, None, OK, CFG, NOW)[0])



class Morning(unittest.TestCase):
    AM = NOW.replace(hour=8, minute=30)

    def lrec(self, level="light", date="2026-11-05"):
        r = rec(); r["dayLoadByDate"] = {date: level}
        return r

    def test_light_day_pings_once_with_the_text(self):
        p, st = decide(self.lrec(), {}, None, OK, CFG, self.AM)
        self.assertEqual(p["type"], "morning")
        from push_logic import DEFAULTS
        self.assertIn(p["text"], DEFAULTS["morningTexts"])
        self.assertEqual(st["morningSentOn"], "2026-11-05")
        p2, _ = decide(self.lrec(), st, None, OK, CFG, self.AM + timedelta(minutes=70))
        self.assertNotEqual((p2 or {}).get("type"), "morning")       # once a day

    def test_text_varies_by_day_but_is_stable_within_a_day(self):
        texts = set()
        for d in range(7):
            when = self.AM + timedelta(days=d)
            r = rec(); r["dayLoadByDate"] = {when.date().isoformat(): "light"}
            p, _ = decide(r, {}, None, OK, CFG, when)
            texts.add(p["text"])
            self.assertEqual(p["text"], decide(r, {}, None, OK, CFG, when + timedelta(minutes=5))[0]["text"])
        self.assertEqual(len(texts), 7)

    def test_normal_or_unknown_day_has_no_morning_ping(self):
        self.assertNotEqual((decide(self.lrec("normal"), {}, None, OK, CFG, self.AM)[0] or {}).get("type"), "morning")
        self.assertNotEqual((decide(rec(), {}, None, OK, CFG, self.AM)[0] or {}).get("type"), "morning")
        self.assertNotEqual((decide(self.lrec(date="2026-11-04"), {}, None, OK, CFG, self.AM)[0] or {}).get("type"), "morning")  # yesterday's level

    def test_window_quiet_hours_and_presence(self):
        for when in (NOW.replace(hour=7, minute=0), NOW.replace(hour=11, minute=30), NOW.replace(hour=14)):
            self.assertNotEqual((decide(self.lrec(), {}, None, OK, CFG, when)[0] or {}).get("type"), "morning")
        seen = self.AM - timedelta(seconds=30)
        self.assertNotEqual((decide(self.lrec(), {}, seen, OK, CFG, self.AM)[0] or {}).get("type"), "morning")   # dashboard open
        quiet = {"quietHours": {"start": "08:00", "end": "09:00"}}
        self.assertNotEqual((decide(self.lrec(), {}, None, OK, quiet, self.AM)[0] or {}).get("type"), "morning")

    def test_morning_ping_starts_the_hourly_cap(self):
        _, st = decide(self.lrec(), {}, None, OK, CFG, self.AM)
        p, _ = decide(self.lrec(), st, None, OK, CFG, self.AM + timedelta(minutes=10))
        self.assertIsNone(p)                                          # start ping waits out the cap


if __name__ == "__main__":
    unittest.main()


class FollowUps(unittest.TestCase):
    """A repeating text or check-in she asked for goes out up to three times a day, 4 hours apart (9, 1, 5), once per slot."""
    H = {"id": "h1", "title": "Study", "days": list(range(7)), "textOnly": True, "nudgeAt": "09:00"}

    def at(self, hh, st):
        now = NOW.replace(hour=hh, minute=5)
        ping, st2 = decide({"habits": [self.H]}, st, None, {}, CFG, now)
        return ping, st2

    def test_three_slots_one_each(self):
        st, texts = {}, []
        for hh in (9, 9, 13, 13, 17, 17, 18):
            ping, st = self.at(hh, st)
            texts.append(ping["text"] if ping else None)
        self.assertEqual(texts, ["Reminder: Study.", None, "Still on your list: Study.", None, "Still on your list: Study.", None, None])

    def test_missed_slots_are_skipped_not_replayed(self):
        ping, st = self.at(18, {})                 # Mac was off all day: one text now, not three
        self.assertEqual(ping["text"], "Reminder: Study.")
        self.assertIsNone(self.at(18, st)[0])
