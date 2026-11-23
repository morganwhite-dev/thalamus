#!/usr/bin/env python3
"""Priority engine CLI. Reads the QuickToDo snapshot, writes state/recommendation.json.

    brain.py recommend            recompute and print the current recommendation
    brain.py pin <task>           pin to the top for today      (unpin <task>)
    brain.py snooze <task> --hours 3 | --until 2026-11-06T09:00
    brain.py skip <task>          "not this one", back tomorrow (unskip <task>)
    brain.py lowenergy on|off
    brain.py status               one-line summary of what is active

<task> is a task id (or unique prefix) or a unique piece of its title.
Overrides are the engine's own file; QuickToDo is never written.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from brain_engine import empty_overrides, parse_dt, prune_overrides, recommend

HERE = Path(__file__).resolve().parent


def load_config(path=None):
    return json.loads(Path(path or HERE / "config.json").read_text())


def resolve(p, config):
    p = Path(os.path.expanduser(config[p] if p in config else p))
    return p if p.is_absolute() else HERE / p


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        if default is not None:
            return default
        raise


def write_json_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def run(config, now=None, save_overrides=True):
    """Recompute from files. On a bad snapshot, keep the last good output and record the error."""
    now = now or datetime.now().astimezone()
    err_path = resolve("errorPath", config)
    try:
        snapshot = read_json(resolve("snapshotPath", config))
        if "tasks" not in snapshot:
            raise ValueError("snapshot has no 'tasks'")
    except (OSError, ValueError) as e:
        write_json_atomic(err_path, {"at": now.isoformat(), "error": f"snapshot unreadable: {e}"})
        raise SystemExit(f"snapshot unreadable ({e}); kept the last good recommendation")
    overrides = read_json(resolve("overridesPath", config), default=empty_overrides())
    commitments = read_json(resolve("commitmentsPath", config), default=[])
    result, pruned = recommend(snapshot, overrides, commitments, config, now)
    write_json_atomic(resolve("recommendationPath", config), result)
    if save_overrides and pruned != overrides:
        write_json_atomic(resolve("overridesPath", config), pruned)
    if err_path.exists():
        err_path.unlink()
    return result


def pick_task(snapshot, text):
    tasks = snapshot["tasks"]
    exact = [t for t in tasks if t["id"].lower().startswith(text.lower())]
    if len(exact) == 1:
        return exact[0]
    hits = [t for t in tasks if text.lower() in t["title"].lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits and not exact:
        raise SystemExit(f"no open task matches '{text}'")
    raise SystemExit("ambiguous, matches:\n" + "\n".join(f"  {t['id'][:8]}  {t['title']}" for t in (exact or hits)[:8]))


def mutate(config, fn):
    now = datetime.now().astimezone()
    snapshot = read_json(resolve("snapshotPath", config))
    ov_path = resolve("overridesPath", config)
    ov = prune_overrides(read_json(ov_path, default=empty_overrides()), {t["id"]: t for t in snapshot["tasks"]}, now)
    fn(ov, snapshot, now)
    write_json_atomic(ov_path, ov)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("recommend")
    sub.add_parser("status")
    for name in ("pin", "unpin", "skip", "unskip"):
        sub.add_parser(name).add_argument("task")
    sn = sub.add_parser("snooze")
    sn.add_argument("task")
    g = sn.add_mutually_exclusive_group(required=True)
    g.add_argument("--hours", type=float)
    g.add_argument("--until")
    sub.add_parser("lowenergy").add_argument("state", choices=["on", "off"])
    a = ap.parse_args(argv)
    config = load_config(a.config)

    if a.cmd in ("pin", "unpin", "skip", "unskip", "snooze"):
        snapshot = read_json(resolve("snapshotPath", config))
        task = pick_task(snapshot, a.task)

        def fn(ov, snap, now):
            tid, today = task["id"], now.date().isoformat()
            if a.cmd in ("pin", "unpin"):
                ov["pins"] = [p for p in ov["pins"] if p["taskId"] != tid]
                if a.cmd == "pin":
                    ov["pins"].append({"taskId": tid, "pinnedAt": now.isoformat(), "forDate": today})
            elif a.cmd in ("skip", "unskip"):
                ov["skips"] = [s for s in ov["skips"] if s["taskId"] != tid]
                if a.cmd == "skip":
                    ov["skips"].append({"taskId": tid, "forDate": today})
            else:
                if a.hours is not None and a.hours <= 0:
                    raise SystemExit("snooze needs a positive number of hours")
                until = now + timedelta(hours=a.hours) if a.hours is not None else parse_dt(a.until, now.tzinfo)
                if until is None or until <= now:
                    raise SystemExit("that time has already passed; snooze until a later time")
                ov["snoozes"] = [s for s in ov["snoozes"] if s["taskId"] != tid]
                ov["snoozes"].append({"taskId": tid, "until": until.isoformat()})
        mutate(config, fn)
        print(f"{a.cmd}: {task['title']}")
    elif a.cmd == "lowenergy":
        def fn(ov, snap, now):
            ov["mode"] = {"lowEnergy": a.state == "on", "since": now.isoformat() if a.state == "on" else None}
        mutate(config, fn)

    result = run(config)
    if a.cmd == "status":
        o = result["activeOverrides"]
        print(f"pins {o['pins']}, snoozes {o['snoozes']}, skips {o['skips']}, "
              f"low-energy {'on' if result['mode']['lowEnergy'] else 'off'}, "
              f"snapshot {'STALE' if result['snapshot']['stale'] else 'fresh'}, day {result['dayLoad']['level']}")
        return
    cur = result["current"]
    if not cur:
        print(f"Nothing to do: {result['emptyReason']}")
        return
    print(f"NOW: {cur['title']}  [{cur['list']}, ~{cur['minutes']} min]\n  {cur['why']}")
    for q in result["queue"]:
        print(f"  next: {q['title']}  ({q['category']})")
    if result["snapshot"]["stale"]:
        print("  warning: snapshot is stale; is QuickToDo running?")


if __name__ == "__main__":
    main()
