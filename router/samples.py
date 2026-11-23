"""Sample-task harness: routes about a dozen realistic tasks and prints which model handled each.

  python3 samples.py              classify only (Jev, free) - prints tier/model/effort per task
  python3 samples.py --run-free   also executes the tasks routed to the free tier (free models only)

Uses its own state folder (state/samples/) so test runs never touch the real usage counter.
'expected' is the start tier the plan's table should produce; mismatches are flagged for review."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from router.core import ROOT, Router  # noqa: E402

SAMPLES = [
    ("step0", "what should I do now?"),
    ("step0", "what's due this week?"),
    ("opus*", "@opus max design the brain-snapshot.json format"),
    ("free", "rename the variable tmp to total in budget.py"),
    ("free", "fix the syntax error on line 12 of import.py: missing closing parenthesis"),
    ("free", "write a commit message for: added auto-import manifest and heartbeat card"),
    ("free", "summarize this in two sentences: Lab 3 for CIS 8087 is due Nov 12 at 11:59 PM. It covers VPC "
             "peering and needs a screenshot of each step. Late work loses 10% per day, and the lab is worth 50 points."),
    ("haiku", "write a small Python function that counts weekdays between two dates, plus one unit test"),
    ("haiku", "run the tests in test_dates.py, fix the one failing assertion in that file, then re-run them"),
    ("sonnet", "add a snooze field to the task model, then update the importer, the dashboard view and the tests"),
    ("sonnet", "draft a one-page cover letter for a cloud security internship from my resume"),
    ("opus", "auto-import sometimes duplicates tasks after the Mac wakes from sleep and I can't tell why; "
             "investigate across the watcher and the manifest code"),
    ("opus", "rotate the API keys in the deploy config and delete the old ones"),
    ("opus", "decide how I should split this month between internship applications and security projects"),
]


FIXTURES = {
    "budget.py": "def monthly(items):\n    tmp = 0\n    for i in items:\n        tmp += i\n    return tmp\n",
    "import.py": "import json\n\n\ndef load(path):\n    with open(path) as f:\n        data = json.load(f)\n"
                 "    return data\n\n\ndef count(rows):\n    return len(rows\n",
}


def seed_workspace(ws: Path) -> None:
    """Fresh copies of the small files the free-tier samples edit (the router workspace only)."""
    ws.mkdir(parents=True, exist_ok=True)
    for name, body in FIXTURES.items():
        (ws / name).write_text(body)


def main() -> int:
    run_free = "--run-free" in sys.argv
    state = ROOT / "state" / "samples"
    if "--fresh" in sys.argv and state.exists():
        shutil.rmtree(state)
    r = Router(state_dir=state)
    if run_free:
        seed_workspace(Path(r.cfg["workspace"]))
    print(f"free pool: {', '.join(m.key for m in r.roster.free)}")
    print(f"claude:    {', '.join(f'{t}={m.key}' for t, m in r.roster.claude.items())}\n")
    rows, mismatches = [], 0
    for expected, task in SAMPLES:
        res = r.route(task, dry_run=True)
        got = "step0" if res.handled_by == "priority-engine" else res.tier
        exp = expected.rstrip("*")
        ok = got == exp
        mismatches += not ok
        rows.append((ok, exp, got, res.model or "-", res.effort or "-", res.reason, task))
        if run_free and res.tier == "free":
            ran = r.route(task)
            rows.append((ran.outcome.startswith("ok"), "  ran", ran.tier, ran.model or "-", "-",
                         f"{ran.outcome}; attempts={len(ran.attempts)}", (ran.answer or "")[:90].replace("\n", " ")))
    for ok, exp, got, model, effort, reason, task in rows:
        mark = "ok " if ok else "XX "
        print(f"{mark}{exp:>6} -> {got:<6} {model:<34} {effort:<6} {task[:70]}")
        print(f"{'':>20}{reason[:150]}")
    print(f"\n{len(SAMPLES) - mismatches}/{len(SAMPLES)} matched the expected start tier")
    totals = r.usage.totals()
    print(f"usage (samples state): week units={totals['week']['units']}, free calls={totals['week']['free_calls']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
