#!/usr/bin/env python3
"""Opens QuickToDo hidden when the dashboard has left it a request and it is not running (Phase 15b),
and about once an hour (or when a new import file appears) so imports and the snapshot never go stale.

launchd runs this whenever something changes in drop-folder/actions. QuickToDo itself still makes every
change (the brain never touches its database); this only makes sure the app is awake to do it.
If this script started the app and it is still hidden after the requests are answered, it quits it again.
If you opened the app yourself in the meantime (it is visible), it is left alone.
"""
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIONS = ROOT / "drop-folder" / "actions"
RESULTS = Path.home() / "Library/Containers/com.morganwhite.QuickTodo/Data/Library/Application Support/BrainSnapshot/actions-result.json"
BUNDLE_ID = "com.morganwhite.QuickTodo"
PROC = "QuickTodo"
WAIT_SECONDS = 90
SNAPSHOT = RESULTS.parent / "brain-snapshot.json"
REFRESH_AFTER_SECONDS = 50 * 60            # the hourly run refreshes a snapshot older than this
SETTLE_SECONDS = 25                        # time for the import scan and a fresh snapshot
SOURCE_GLOBS = [                           # files QuickToDo imports; newer than the snapshot means an import is waiting
    (ROOT / "drop-folder", "*_assignments.json"),
    (Path.home() / "Desktop/GSU MSIS/Network Security", "*_assignments.json"),
    (Path.home() / "Desktop/GSU MSIS/Cloud Computing and Security", "*_assignments.json"),
]


def log(msg):
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def pending_ids():
    ids = []
    for f in ACTIONS.glob("*.brainaction.json"):
        try:
            ids.append(json.loads(f.read_text())["id"])
        except (OSError, ValueError, KeyError):
            ids.append(f.name[: -len(".brainaction.json")])
    return ids


def answered():
    try:
        return {r["id"] for r in json.loads(RESULTS.read_text()).get("results", [])}
    except (OSError, ValueError):
        return set()


def running():
    return subprocess.run(["pgrep", "-x", PROC], capture_output=True).returncode == 0


def newest_app():
    installed = Path("/Applications/QuickTodo.app")
    if installed.exists():                     # an installed build wins over development builds
        return installed
    out = subprocess.run(["mdfind", f"kMDItemCFBundleIdentifier == '{BUNDLE_ID}'"], capture_output=True, text=True).stdout
    apps = [Path(p) for p in out.splitlines() if p.endswith(".app") and Path(p).exists()]
    return max(apps, key=lambda p: p.stat().st_mtime, default=None)


def is_visible():
    r = subprocess.run(["osascript", "-e", f'tell application "System Events" to get visible of process "{PROC}"'],
                       capture_output=True, text=True)
    return r.stdout.strip() != "false"      # unknown counts as visible: never quit something we are not sure about


def snapshot_age():
    try:
        return time.time() - SNAPSHOT.stat().st_mtime
    except OSError:
        return float("inf")


def refresh_reason():
    """Why the app should wake with no request waiting: a new import file, or an old snapshot. None if neither."""
    try:
        snap = SNAPSHOT.stat().st_mtime
    except OSError:
        snap = 0
    for folder, pattern in SOURCE_GLOBS:
        for f in folder.glob(pattern):
            try:
                if f.stat().st_mtime > snap:
                    return f"new import file {f.name}"
            except OSError:
                pass
    if snapshot_age() > REFRESH_AFTER_SECONDS:
        return f"snapshot is {int(snapshot_age() // 60)} min old"
    return None


def quit_if_hidden():
    time.sleep(4)                              # let it finish saving and write the snapshot
    if not is_visible():
        subprocess.run(["osascript", "-e", f'tell application "{PROC}" to quit'], check=False)
        return True
    return False


def refresh_only():
    reason = refresh_reason()
    if reason is None or running():            # already running: it imports and writes snapshots by itself
        return 0
    app = newest_app()
    if app is None:
        log("QuickToDo.app not found; cannot refresh")
        return 1
    log(f"launching {app} hidden to refresh ({reason})")
    subprocess.run(["open", "-g", "-j", str(app)], check=False)
    before = SNAPSHOT.stat().st_mtime if SNAPSHOT.exists() else 0
    deadline = time.time() + WAIT_SECONDS
    while time.time() < deadline:
        time.sleep(2)
        if SNAPSHOT.exists() and SNAPSHOT.stat().st_mtime > before:
            break
    time.sleep(SETTLE_SECONDS)                 # imports run on the first scan, after launch
    log("refreshed; quit the hidden app again" if quit_if_hidden() else "refreshed; app is visible, leaving it open")
    return 0


def main():
    ids = pending_ids()
    todo = [i for i in ids if i not in answered()]
    if not todo:
        return refresh_only()
    if running():
        log(f"QuickToDo already running; it will handle {len(todo)} request(s)")
        return 0
    app = newest_app()
    if app is None:
        log("QuickToDo.app not found; requests will wait until it is opened")
        return 1
    log(f"launching {app} hidden for {len(todo)} request(s)")
    subprocess.run(["open", "-g", "-j", str(app)], check=False)
    deadline = time.time() + WAIT_SECONDS
    while time.time() < deadline:
        time.sleep(2)
        if all(i in answered() for i in todo):
            break
    else:
        log("timed out waiting for QuickToDo to answer; leaving it running")
        return 1
    if quit_if_hidden():
        log("requests answered; quit the hidden app again")
    else:
        log("requests answered; app is visible (you opened it), leaving it open")
    return 0


if __name__ == "__main__":
    sys.exit(main())
