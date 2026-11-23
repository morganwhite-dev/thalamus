"""The run watcher: stall detection, overall timeout, and killing helpers that hold the pipe.
Uses tiny fake 'opencode' shell scripts; no model calls."""
import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from router.opencode_client import OpenCodeClient  # noqa: E402

EVENT = '{"type":"text","sessionID":"ses_1","part":{"text":"pong"}}'


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, body):
        p = self.dir / "fake-opencode"
        p.write_text("#!/bin/sh\n" + body + "\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
        return OpenCodeClient(str(p), str(self.dir), stall_seconds=1)

    def test_normal_run(self):
        r = self.cli(f"echo '{EVENT}'").run("p", "m", "hi", timeout=10, session_id="ses_1")
        self.assertTrue(r.ok)
        self.assertEqual(r.text, "pong")

    def test_stall_before_first_output(self):
        t = time.time()
        r = self.cli("sleep 30").run("p", "m", "hi", timeout=20, session_id="ses_1")
        self.assertLess(time.time() - t, 5)
        self.assertEqual(r.error_kind, "stall")
        self.assertIn("never started", r.error)

    def test_slow_but_talking_is_not_a_stall(self):
        r = self.cli(f"echo '{EVENT}'; sleep 2; echo '{EVENT}'").run("p", "m", "hi", timeout=10, session_id="ses_1")
        self.assertTrue(r.ok, r.error)

    def test_timeout_kills_helper_holding_pipe(self):
        # The script starts a background helper that keeps stdout open, then hangs.
        body = f"echo '{EVENT}'; (sleep 60) & sleep 60"
        t = time.time()
        r = self.cli(body).run("p", "m", "hi", timeout=2, session_id="ses_1")
        self.assertLess(time.time() - t, 8)
        self.assertEqual(r.error_kind, "timeout")


if __name__ == "__main__":
    unittest.main()
