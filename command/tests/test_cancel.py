import sys, tempfile, unittest, time, threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import command


class CancelTests(unittest.TestCase):
    def test_cancel_marks_job_and_sticks(self):
        with tempfile.TemporaryDirectory() as d:
            r = command.CommandRunner(state_dir=d, sync=True)
            from brain import write_json_atomic
            write_json_atomic(r.jobs_path, {"version": 1, "jobs": [{"id": "j1", "status": "running"}]})
            out = r.cancel("j1")
            self.assertEqual(out["status"], "cancelled")
            r._update("j1", status="done", answer="late")
            self.assertEqual(r.get("j1")["status"], "cancelled")
            self.assertIsNone(r.cancel("nope"))
            command._client_cancel(False)

    def test_done_job_not_changed(self):
        with tempfile.TemporaryDirectory() as d:
            r = command.CommandRunner(state_dir=d, sync=True)
            from brain import write_json_atomic
            write_json_atomic(r.jobs_path, {"version": 1, "jobs": [{"id": "j2", "status": "done"}]})
            self.assertEqual(r.cancel("j2")["status"], "done")


if __name__ == "__main__":
    unittest.main()
