import json, os, sys, tempfile, time, unittest
from datetime import datetime
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "engine"))
import pusher  # noqa


class T(unittest.TestCase):
    def log(self, text, age_h=0):
        p = Path(tempfile.mkdtemp()) / "import.log"
        p.write_text(text)
        t = time.time() - age_h * 3600
        os.utime(p, (t, t))
        return {"importLogPath": str(p)}

    def test_failure_cleared_by_later_success(self):
        c = self.log("t FAILED: A.json bad\nt A.json: 0 added, 0 updated, 3 unchanged\n")
        self.assertFalse(pusher.import_health(c, datetime.now().astimezone())["importFailed"])

    def test_latest_failure_detected(self):
        c = self.log("t A.json: 0 added\nt FAILED: A.json bad\nt B.json: ok\n")
        h = pusher.import_health(c, datetime.now().astimezone())
        self.assertTrue(h["importFailed"]); self.assertIn("A.json", h["importFailedKey"])

    def test_age(self):
        c = self.log("t A.json: ok\n", age_h=30)
        self.assertGreater(pusher.import_health(c, datetime.now().astimezone())["importAgeHours"], 29)

    def test_missing_log_is_not_failure(self):
        h = pusher.import_health({"importLogPath": "/nonexistent/x.log"}, datetime.now().astimezone())
        self.assertFalse(h["importFailed"])


    def test_checkin_stops_when_its_task_is_done(self):
        rows = [{"id": "h1", "title": "Complete tier 1", "forTask": {"title": "Complete tier 1", "list": "Network Security"}},
                {"id": "h2", "title": "stretch"}]
        def snap(tasks):
            return lambda *a, **k: {"tasks": tasks}
        orig_read, orig_cfg, orig_res = pusher.brain.read_json, pusher.brain.load_config, pusher.brain.resolve
        pusher.brain.load_config, pusher.brain.resolve = (lambda: {}), (lambda p, c: p)
        try:
            pusher.brain.read_json = snap([{"title": "Complete tier 1", "list": "Network Security"}])
            self.assertEqual([h["id"] for h in pusher.open_checkins(rows)], ["h1", "h2"])
            pusher.brain.read_json = snap([{"title": "Something else", "list": "Network Security"}])
            self.assertEqual([h["id"] for h in pusher.open_checkins(rows)], ["h2"])
            def boom(*a, **k): raise OSError("gone")
            pusher.brain.read_json = boom                      # an unreadable snapshot never ends a check-in
            self.assertEqual([h["id"] for h in pusher.open_checkins(rows)], ["h1", "h2"])
        finally:
            pusher.brain.read_json, pusher.brain.load_config, pusher.brain.resolve = orig_read, orig_cfg, orig_res


if __name__ == "__main__":
    unittest.main()