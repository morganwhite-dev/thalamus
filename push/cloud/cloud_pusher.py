#!/usr/bin/env python3
"""Cloud pusher. Runs on a GitHub Actions cron. Self-contained (copy of push_logic.py + ntfy.py beside it).

Acts only when the Mac has stopped syncing (queue.json older than HANDOVER_MINUTES); while the
Mac is on, the local pusher does the work. Topic comes from the NTFY_TOPIC secret, never the repo.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from push_logic import decide  # noqa: E402

HANDOVER_MINUTES = 20


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def build(queue, own_state, now):
    """Returns (rec, state, health, block, cfg) from the synced queue, or None when the Mac is still syncing."""
    synced = datetime.fromisoformat(queue["syncedAt"])
    away_min = (now - synced).total_seconds() / 60
    if away_min < HANDOVER_MINUTES:
        return None
    rec = {"current": queue.get("current"), "queue": queue.get("queue", []),
           "dayLoadByDate": queue.get("dayLoadByDate", {}),
           "snapshot": {"stale": bool(queue.get("snapshotStale"))},
           "habits": queue.get("habits", []), "reminders": queue.get("reminders", [])}
    # Start from whichever side pinged last, so the hourly cap holds across the handover.
    st = dict(queue.get("push", {}))
    if own_state.get("lastPingAt") and own_state["lastPingAt"] > st.get("lastPingAt", ""):
        st.update({k: own_state[k] for k in ("lastPingAt", "lastPingKey") if k in own_state})
    if own_state.get("morningSentOn", "") > st.get("morningSentOn", ""):
        st["morningSentOn"] = own_state["morningSentOn"]
    if own_state.get("reminderSent"):
        st["reminderSent"] = sorted(set(st.get("reminderSent") or []) | set(own_state["reminderSent"]))[-200:]
    if own_state.get("habitSent"):
        merged = dict(st.get("habitSent") or {}); merged.update(own_state["habitSent"]); st["habitSent"] = merged
    if "failureAlertedFor" in own_state:
        st["failureAlertedFor"] = own_state["failureAlertedFor"]
    st["lastOnlineAt"] = now.isoformat()  # the cloud itself is online: no "welcome back" from here
    age = queue.get("importAgeHours")
    health = {"importAgeHours": None if age is None else age + away_min / 60,
              "importFailed": bool(queue.get("importFailed")), "importFailedKey": queue.get("importFailedKey", "")}
    # A Mac that stopped syncing for a long time is itself the incident.
    if away_min > 24 * 60:
        health["importAgeHours"] = max(health["importAgeHours"] or 0, away_min / 60)
    return rec, st, health, queue.get("block"), queue.get("config", {})


def main():
    now = datetime.now(timezone.utc).astimezone()
    queue = load_json(HERE / "queue.json", None)
    if not queue or "syncedAt" not in queue:
        print("no queue.json yet"); return
    own = load_json(HERE / "cloud-state.json", {})
    built = build(queue, own, now)
    if built is None:
        print("Mac is syncing; local pusher is in charge"); return
    rec, st, health, block, cfg = built
    if cfg.get("timezone"):  # the runner is on UTC; quiet hours are local time
        from zoneinfo import ZoneInfo
        now = now.astimezone(ZoneInfo(cfg["timezone"]))
    ping, st = decide(rec, st, None, health, cfg, now, block)
    if ping:
        import ntfy
        ntfy.send({"ntfyTopic": os.environ["NTFY_TOPIC"]}, ping["title"], ping["text"],
                  "high" if ping["type"] == "failure" else "default")
        print("sent", ping["type"], ping["key"])
    else:
        print("no ping")
    Path(HERE / "cloud-state.json").write_text(json.dumps(st, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
