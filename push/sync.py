"""Thin snapshot sync: writes cloud/queue.json (titles and times only, no notes) and pushes it.

The sync clone lives at push/cloud-repo (a private repo). Content changes sync at once; otherwise
the heartbeat (syncedAt) is refreshed every SYNC_MINUTES, so the repo is not spammed with commits.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

SYNC_MINUTES = 10
KEEP = ("taskId", "title", "category", "minutes", "why", "dueDate")


def slim(item):
    return {k: item[k] for k in KEEP if k in item}


def slim_habits(habits):
    return [{k: h[k] for k in ("id", "title", "notes", "nudgeAt", "days", "doneToday", "textOnly", "minutes", "until", "startOn") if k in h} for h in (habits or [])]


def build_queue(rec, state, health, block, config, now):
    return {
        "syncedAt": now.isoformat(),
        "generatedAt": (rec or {}).get("generatedAt"),
        "current": slim(rec["current"]) if rec and rec.get("current") else None,
        "queue": [slim(q) for q in (rec or {}).get("queue", [])],
        "snapshotStale": bool(rec and rec.get("snapshot", {}).get("stale")),
        "dayLoadByDate": (rec or {}).get("dayLoadByDate") or {},
        "importAgeHours": health.get("importAgeHours"),
        "importFailed": health.get("importFailed", False),
        "importFailedKey": health.get("importFailedKey", ""),
        "block": block,
        "push": {k: state[k] for k in ("lastPingAt", "lastPingKey", "failureAlertedFor", "morningSentOn", "habitSent", "reminderSent") if k in state},
        "reminders": [{k: r[k] for k in ("id", "text", "at") if k in r} for r in ((rec or {}).get("reminders") or [])],
        "habits": slim_habits((rec or {}).get("habits")),
        "config": {k: config[k] for k in ("capMinutes", "presenceSeconds", "quietHours", "catchupAfterHours", "staleImportHours", "timezone", "morning", "morningText", "morningTexts") if k in config},
    }


def content_key(q):
    return json.dumps({k: v for k, v in q.items() if k not in ("syncedAt", "importAgeHours")}, sort_keys=True)


def due(old, new, now):
    if not old or "syncedAt" not in old:
        return True
    if content_key(old) != content_key(new):
        return True
    return (now - datetime.fromisoformat(old["syncedAt"])).total_seconds() >= SYNC_MINUTES * 60


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60)


def sync(repo, queue, now):
    """Write and push. Returns (ok, message). Never raises: a sync problem must not stop local pings."""
    repo = Path(repo)
    if not (repo / ".git").exists():
        return False, "cloud-repo is not set up"
    qp = repo / "queue.json"
    try:
        old = json.loads(qp.read_text())
    except (OSError, ValueError):
        old = None
    if not due(old, queue, now):
        return True, "unchanged"
    git(repo, "pull", "--rebase", "-q")
    qp.write_text(json.dumps(queue, indent=2, sort_keys=True) + "\n")
    git(repo, "add", "queue.json")
    c = git(repo, "commit", "-q", "-m", "sync")
    if c.returncode:
        return False, "commit failed: " + c.stderr.strip()[:200]
    p = git(repo, "push", "-q")
    return (p.returncode == 0), ("pushed" if p.returncode == 0 else "push failed: " + p.stderr.strip()[:200])


def read_cloud_state(repo):
    try:
        return json.loads((Path(repo) / "cloud-state.json").read_text())
    except (OSError, ValueError):
        return {}
