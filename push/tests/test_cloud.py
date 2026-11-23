import sys, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "cloud"))
import cloud_pusher as cp, sync  # noqa
from push_logic import decide  # noqa

TZ = timezone(timedelta(hours=-5))
NOW = datetime(2026, 11, 5, 14, 0, tzinfo=TZ)
REC = {"generatedAt": "g", "current": {"taskId": "a", "title": "Read Chapter 5", "minutes": 60, "why": "Due", "category": "Schoolwork", "notes": "SECRET"},
       "queue": [{"taskId": "b", "title": "x", "notes": "SECRET"}], "snapshot": {"stale": False}}


def q(synced, **kw):
    base = sync.build_queue(REC, {"lastPingAt": (NOW - timedelta(hours=5)).isoformat(), "lastPingKey": "start:old"},
                            {"importAgeHours": 1}, None, {}, synced)
    base.update(kw); return base


class T(unittest.TestCase):
    def test_no_notes_leave_the_laptop(self):
        self.assertNotIn("SECRET", str(q(NOW)))

    def test_cloud_idle_while_mac_syncs(self):
        self.assertIsNone(cp.build(q(NOW - timedelta(minutes=5)), {}, NOW))

    def test_cloud_acts_after_handover(self):
        rec, st, health, block, cfg = cp.build(q(NOW - timedelta(minutes=30)), {}, NOW)
        ping, _ = decide(rec, st, None, health, cfg, NOW, block)
        self.assertEqual(ping["type"], "start")

    def test_cap_holds_across_handover(self):
        qq = q(NOW - timedelta(minutes=30))
        qq["push"]["lastPingAt"] = (NOW - timedelta(minutes=10)).isoformat()
        rec, st, health, block, cfg = cp.build(qq, {}, NOW)
        self.assertIsNone(decide(rec, st, None, health, cfg, NOW, block)[0])

    def test_own_newer_ping_wins(self):
        own = {"lastPingAt": NOW.isoformat(), "lastPingKey": "start:a"}
        rec, st, health, block, cfg = cp.build(q(NOW - timedelta(minutes=30)), own, NOW)
        self.assertIsNone(decide(rec, st, None, health, cfg, NOW + timedelta(hours=2), block)[0])

    def test_long_mac_off_alerts(self):
        rec, st, health, block, cfg = cp.build(q(NOW - timedelta(hours=30)), {}, NOW)
        self.assertEqual(decide(rec, st, None, health, cfg, NOW, block)[0]["type"], "failure")

    def test_heartbeat_only_every_10_min(self):
        old = q(NOW - timedelta(minutes=3)); new = q(NOW)
        self.assertFalse(sync.due(old, new, NOW))
        self.assertTrue(sync.due(q(NOW - timedelta(minutes=11)), new, NOW))
        changed = q(NOW); changed["current"] = None
        self.assertTrue(sync.due(old, changed, NOW))


    def test_cloud_sends_morning_ping_from_last_sync_and_dedupes(self):
        am = NOW.replace(hour=8, minute=30)
        rec_ = dict(REC, dayLoadByDate={"2026-11-04": "heavy", "2026-11-05": "light"})
        qq = sync.build_queue(rec_, {}, {"importAgeHours": 1}, None, {}, am - timedelta(hours=10))
        self.assertEqual(qq["dayLoadByDate"]["2026-11-05"], "light")
        rec, st, health, block, cfg = cp.build(qq, {}, am)
        ping, st2 = decide(rec, st, None, health, cfg, am, block)
        self.assertEqual(ping["type"], "morning")
        rec, st, health, block, cfg = cp.build(qq, {"morningSentOn": "2026-11-05"}, am)   # Mac or cloud already sent it
        ping, _ = decide(rec, st, None, health, cfg, am, block)
        self.assertNotEqual((ping or {}).get("type"), "morning")


if __name__ == "__main__":
    unittest.main()


class Zone(unittest.TestCase):
    def test_quiet_hours_use_local_time(self):
        from zoneinfo import ZoneInfo
        utc_now = datetime(2026, 11, 6, 1, 14, tzinfo=timezone.utc)  # 20:14 in New York, not quiet
        local = utc_now.astimezone(ZoneInfo("America/New_York"))
        rec = {"current": {"taskId": "a", "title": "t", "minutes": 5, "why": "w"}, "queue": [], "snapshot": {"stale": False}}
        self.assertIsNone(decide(rec, {}, None, {}, {}, utc_now)[0])      # UTC clock: wrongly quiet
        self.assertIsNotNone(decide(rec, {}, None, {}, {}, local)[0])     # local clock: sends


class Drift(unittest.TestCase):
    def test_cloud_copies_match(self):
        for f in ("push_logic.py", "ntfy.py"):
            self.assertEqual((HERE / f).read_text(), (HERE / "cloud" / f).read_text(), f"cp {f} cloud/")
