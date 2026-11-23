#!/usr/bin/env python3
"""Local pusher. Run every minute by launchd while the Mac is awake.

    pusher.py            decide and send if due
    pusher.py --dry-run  print what would be sent, change nothing
    pusher.py --test     send one test notification
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "engine"))
sys.path.insert(0, str(HERE.parent / "blocks"))
import blocks  # noqa: E402
import brain  # noqa: E402
sys.path.insert(0, str(HERE.parent / "play"))
import play as play_mod  # noqa: E402
import ntfy  # noqa: E402
import sync  # noqa: E402
from push_logic import decide  # noqa: E402

STATE = HERE / "state"


def log(msg):
    STATE.mkdir(exist_ok=True)
    with open(STATE / "push.log", "a") as f:
        f.write(f"{datetime.now().astimezone().isoformat(timespec='seconds')} {msg}\n")


def read_dt(path, key):
    try:
        return datetime.fromisoformat(json.loads(Path(path).read_text())[key])
    except (OSError, ValueError, KeyError):
        return None


def import_health(config, now):
    """Age of the last import scan and whether any file's latest log line is a failure."""
    p = Path(os.path.expanduser(config.get("importLogPath", "")))
    try:
        age = (now.timestamp() - p.stat().st_mtime) / 3600
        lines = p.read_text().splitlines()[-200:]
    except OSError:
        return {"importAgeHours": None, "importFailed": False}
    latest = {}
    for ln in lines:
        m = re.search(r"(\S+\.json)", ln)
        if m:
            latest[m.group(1)] = ln
    bad = [ln for ln in latest.values() if "FAILED" in ln]
    return {"importAgeHours": age, "importFailed": bool(bad), "importFailedKey": bad[0][:60] if bad else ""}


def open_checkins(rows):
    """Drop check-ins whose task is no longer open (done in Thalamus or QuickToDo). An unreadable snapshot keeps them."""
    if not any(h.get("forTask") for h in rows):
        return rows
    try:
        tasks = brain.read_json(brain.resolve("snapshotPath", brain.load_config()))["tasks"]
    except (OSError, ValueError, KeyError, TypeError):
        return rows
    def is_open(ft):
        t, l = ft["title"].lower(), ft["list"].lower()
        return any(l == str(x.get("list", "")).lower() and t in str(x.get("title", "")).lower() for x in tasks)
    return [h for h in rows if not h.get("forTask") or is_open(h["forTask"])]


def load_block():
    """The active work block or break, projected from the blocks module's state (None when idle)."""
    state, err = blocks.load_state()
    if err:
        log(f"blocks: {err}")
    return blocks.push_view(state)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args(argv)
    config = json.loads((HERE / "config.json").read_text())
    if a.test:
        ntfy.send(config, "Brain: test", "Test notification from the Priority Brain.")
        print("sent")
        return
    now = datetime.now().astimezone()
    try:
        rec = brain.run(brain.load_config(), now, save_overrides=not a.dry_run)
    except SystemExit as e:
        log(f"engine: {e}")
        rec = None  # health check below still runs on the stale/unreadable state
        try:
            rec = brain.read_json(brain.resolve("recommendationPath", brain.load_config()))
            rec.setdefault("snapshot", {})["stale"] = True
        except (OSError, ValueError):
            pass
    old = brain.read_json(STATE / "push-state.json", default={})
    repo = HERE / "cloud-repo"
    cloud = sync.read_cloud_state(repo)  # pings the cloud sent while the Mac was off count toward the cap
    if cloud.get("lastPingAt", "") > old.get("lastPingAt", ""):
        old.update({k: cloud[k] for k in ("lastPingAt", "lastPingKey") if k in cloud})
    if cloud.get("morningSentOn", "") > old.get("morningSentOn", ""):
        old["morningSentOn"] = cloud["morningSentOn"]
    try:
        rec = dict(rec or {})
        pstate = play_mod.load()
        rec["habits"] = open_checkins(play_mod.habit_rows(pstate, now))
        rec["reminders"] = pstate.get("reminders", [])
    except Exception as e:  # habits are a bonus: never stop the other pings
        log(f"habits: {e}")
    if cloud.get("reminderSent"):
        old["reminderSent"] = sorted(set(old.get("reminderSent") or []) | set(cloud["reminderSent"]))[-200:]
    if cloud.get("habitSent"):
        merged = dict(old.get("habitSent") or {})
        for k, v in cloud["habitSent"].items():  # keep the newer day: an old cloud date must not re-arm today's nudge
            merged[k] = max(v, merged.get(k, ""))
        old["habitSent"] = merged
    st_in = dict(old)
    ping, st = decide(rec, st_in, read_dt(STATE / "presence.json", "lastSeen"),
                      import_health(config, now), config, now, load_block())
    st["lastOnlineAt"] = now.isoformat()
    if a.dry_run:
        print(json.dumps(ping, indent=2) if ping else "no ping")
        return
    if ping:
        try:
            ntfy.send(config, ping["title"], ping["text"], "high" if ping["type"] == "failure" else "default")
            log(f"sent {ping['type']} {ping['key']}")
        except Exception as e:  # not marked as sent; retried next tick
            log(f"SEND FAILED {ping['type']} {ping['key']}: {e}")
            st = dict(old, lastOnlineAt=now.isoformat())
    brain.write_json_atomic(STATE / "push-state.json", st)
    health = import_health(config, now)
    ok, msg = sync.sync(repo, sync.build_queue(rec, st, health, load_block(), config, now), now)
    note_sync(ok, msg, now)
    drop_sent_reminders(st)


def drop_sent_reminders(st):
    """A reminder that has been sent (here or by the cloud copy) leaves the store, so it never lingers."""
    try:
        ids = set(st.get("reminderSent") or [])
        ps = play_mod.load()
        gone = [r["id"] for r in ps.get("reminders", []) if r["id"] in ids]
        if gone:
            play_mod.save(play_mod.apply(ps, "reminderdone", datetime.now().astimezone(), ids=gone))
    except Exception as e:
        log(f"reminders: {e}")


def note_sync(ok, msg, now):
    """Log failures at once, 'recovered' after a failure, and a quiet 'sync ok' about every 30 minutes."""
    p = STATE / "sync-status.json"
    try:
        stt = json.loads(p.read_text())
    except (OSError, ValueError):
        stt = {}
    if not ok:
        log(f"sync: {msg}")
        stt["failing"] = True
    else:
        last = stt.get("okLoggedAt")
        gap = (now - datetime.fromisoformat(last)).total_seconds() if last else 1e9
        if stt.get("failing"):
            log("sync: recovered")
            stt["failing"] = False
            stt["okLoggedAt"] = now.isoformat()
        elif gap >= 1800:
            log("sync ok")
            stt["okLoggedAt"] = now.isoformat()
    try:
        brain.write_json_atomic(p, stt)
    except OSError:
        pass


if __name__ == "__main__":
    main()
