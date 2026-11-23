"""A real command box for tests: dashboard/server.py submit_command -> CommandRunner, with every write intercepted.

Nothing here touches her files: the engine config points at a temp folder, brain.main (pin, unpin, skip, snooze,
low energy) and play.save (park, left-off lines, reminders) are recorded instead of run, and the router uses the
router tests' FakeClient (no model, no usage)."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "dashboard", ROOT / "command", ROOT / "engine", ROOT / "router", ROOT / "play", ROOT / "blocks"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
import brain  # noqa: E402
import command  # noqa: E402
import play  # noqa: E402
import server  # noqa: E402
from router.core import Router, load_config as router_config  # noqa: E402

_spec = importlib.util.spec_from_file_location("router_fakes_live", ROOT / "router" / "tests" / "test_router.py")
_fakes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fakes)

LISTS = ["Cloud Computing", "Network Security", "Internships", "Security Projects", "Personal", "Play", "General"]


class LiveBox:
    """with LiveBox(tasks, current="t1") as box: out = box.send("pin lab 7"); box.writes -> [argv...]"""

    def __init__(self, tasks, current=None, lists=LISTS):
        self.tasks, self.current, self.lists = [dict(t) for t in tasks], current, list(lists)
        self.writes = []          # engine writes: ["pin", "t2"], ["snooze", "t1", "--hours", "1"], ...
        self.play_writes = []     # play store saves (park, left-off, reminders)

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        now = datetime.now().astimezone()
        tasks = [dict(t, dueDate=t.get("dueDate") or (now + timedelta(days=2)).isoformat()) for t in self.tasks]
        (tmp / "snap.json").write_text(json.dumps({"schemaVersion": 1, "generatedAt": now.isoformat(), "tasks": tasks, "lists": self.lists}))
        cfg = json.loads((ROOT / "engine" / "config.json").read_text())
        cfg.update(snapshotPath=str(tmp / "snap.json"), overridesPath=str(tmp / "ov.json"), recommendationPath=str(tmp / "rec.json"),
                   errorPath=str(tmp / "err.json"), commitmentsPath=str(tmp / "none.json"))
        self.config = cfg
        self.client = _fakes.FakeClient()

        def factory(engine_fn):
            rcfg = router_config()
            rcfg["workspace"] = str(tmp / "ws")
            return Router(cfg=rcfg, client=self.client, state_dir=tmp / "rstate", priority_engine=engine_fn)

        r = command.CommandRunner(tmp / "cstate", router_factory=factory, load_config=lambda: cfg, sync=True)
        r.play_path = tmp / "play.json"
        cur = self.current
        r._current_task_id = lambda config, ts: cur
        self._saved = {"load_config": brain.load_config, "main": brain.main, "save": play.save,
                       "runner": server.RUNNER["r"], "blocks": dict(server.BLOCKS_PATHS), "play_path": server.PLAY_PATH["p"]}
        brain.load_config = lambda path=None: cfg
        brain.main = lambda argv=None: self.writes.append(list(argv or []))
        play.save = lambda st, path=None: self.play_writes.append(st)
        server.RUNNER["r"] = r
        server.BLOCKS_PATHS.update(state=tmp / "blocks.json", history=tmp / "history.jsonl")
        server.PLAY_PATH["p"] = tmp / "play.json"
        self.runner = r
        return self

    def __exit__(self, *exc):
        brain.load_config, brain.main, play.save = self._saved["load_config"], self._saved["main"], self._saved["save"]
        server.RUNNER["r"] = self._saved["runner"]
        server.BLOCKS_PATHS.clear(); server.BLOCKS_PATHS.update(self._saved["blocks"])
        server.PLAY_PATH["p"] = self._saved["play_path"]
        self._tmp.cleanup()
        return False

    def send(self, text, **body):
        """What the page gets back: {"capture": proposal} or a job dict (answer, routing, status)."""
        self.writes.clear(); self.play_writes.clear()
        out = server.submit_command({"text": text, **body})
        return out

    @staticmethod
    def kind(out):
        if "capture" in out:
            return "capture"
        return out.get("routing") or out.get("status")
