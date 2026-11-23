import sys, tempfile, json, unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import classes


class Classes(unittest.TestCase):
    def test_today_class_gets_week_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "Cloud"
            wk = root / "Week 5 - Nov 10 - Application Security" / "1 Readings and Lecture Notes"
            wk.mkdir(parents=True)
            (wk / "Case Study.pdf").write_text("x")
            (root / "Week 3 - Oct 27 - Cloud Data Security").mkdir()
            now = datetime(2026, 11, 10, 12, 0, tzinfo=timezone(timedelta(hours=-5)))
            cp = Path(d) / "c.json"
            cp.write_text(json.dumps([{"start": "2026-11-10T17:30:00-05:00", "end": "2026-11-10T21:45:00-05:00", "label": "Class: Session 5: Application Security"},
                                      {"start": "2026-11-11T17:30:00-05:00", "end": "2026-11-11T21:45:00-05:00", "label": "Class: Other"}]))
            r = classes.today(cp, [root], now)
            self.assertEqual(len(r), 1)
            self.assertEqual([f["name"] for f in r[0]["files"]], ["Case Study.pdf"])


if __name__ == "__main__":
    unittest.main()
