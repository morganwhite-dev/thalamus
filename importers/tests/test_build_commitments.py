import sys, unittest
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_commitments as c

ICS = """BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART;TZID=America/New_York:20261112T173000
DTEND;TZID=America/New_York:20261112T214500
SUMMARY:CIS 8088: Attend Class 3: Something\\, long
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=America/New_York:20261112T173000
DTEND;TZID=America/New_York:20261112T180000
SUMMARY:CIS 8087: Test 2
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=America/New_York:20261112T235900
DTEND;TZID=America/New_York:20261112T235900
SUMMARY:CIS 8088: Lab due
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20261113
DTEND;VALUE=DATE:20261114
SUMMARY:all day
END:VEVENT
END:VCALENDAR
"""
TODAY = date(2026, 11, 12)


class T(unittest.TestCase):
    def test_class_kept_deadlines_and_allday_dropped(self):
        rows = c.build(TODAY, [ICS], [])
        starts = [(r["start"], r["end"]) for r in rows]
        self.assertIn(("2026-11-12T17:30:00-05:00", "2026-11-12T21:45:00-05:00"), starts)
        self.assertFalse(any("23:59" in r["start"] for r in rows))
        self.assertEqual(rows[0]["label"], "Class: Class 3: Something, long")

    def test_work_schedule_by_weekday_and_date(self):
        work = [{"days": ["Thu"], "start": "09:00", "end": "13:00", "label": "Work"},
                {"dates": ["2026-11-14"], "start": "10:00", "end": "11:00"}]
        rows = c.build(TODAY, [], work)
        self.assertEqual(rows[0]["start"], "2026-11-12T09:00:00-05:00")  # Thursday
        self.assertIn("2026-11-14T10:00:00-05:00", [r["start"] for r in rows])
        self.assertIn("2026-11-19T09:00:00-05:00", [r["start"] for r in rows])  # next Thursday

    def test_window_limits(self):
        rows = c.build(date(2027, 3, 1), [ICS], [])
        self.assertEqual(rows, [])

    def test_engine_load_changes(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "engine"))
        import brain_engine as e
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime(2026, 11, 12, 9, 0, tzinfo=ZoneInfo("America/New_York"))
        cfg = {"workday": {"start": "09:00", "end": "21:00"}}
        free0 = e.day_load([], set(), [], cfg, now)["freeMinutes"]
        free1 = e.day_load([], set(), c.build(TODAY, [ICS], []), cfg, now)["freeMinutes"]
        self.assertEqual(free0 - free1, 210)  # 17:30 to 21:00 inside the workday window


if __name__ == "__main__":
    unittest.main()
