"""Done / Undo requests from the dashboard to QuickToDo (Phase 10).

The dashboard never touches QuickToDo's database. It drops one small `<id>.brainaction.json`
file into the drop-folder QuickToDo already watches; QuickToDo makes the change itself
(BrainActions.swift) and writes the outcome to `actions-result.json` next to its snapshot.
This module writes requests, tracks them until a result arrives, cleans up processed files,
and builds the `actions` part of /api/state. Contract: dashboard/STATE_MODEL_DONE.md.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SUFFIX = ".brainaction.json"
UNDO_SECONDS = 120          # Undo shows for 2 minutes after QuickToDo confirms Done
WAITING_SECONDS = 20        # after this, the UI says "waiting for QuickToDo"
RECENT_KEEP = 10
RECENT_MAX_AGE = timedelta(days=1)
LOCK = threading.Lock()

OUTCOME_TEXT = {
    "done": "Done in QuickToDo",
    "alreadyDone": "It was already done",
    "blocked": "That task is waiting on another one",
    "notFound": "That task isn't in QuickToDo anymore",
    "titleMismatch": "The task's title changed, so nothing was marked done",
    "reopened": "Back on your list",
    "cannotReopen": "Couldn't undo that one",
    "invalid": "QuickToDo couldn't read the request",
    "saveFailed": "QuickToDo couldn't save the change",
    "added": "Added in QuickToDo",
    "alreadyExists": "That's already on your list",
    "noSuchList": "QuickToDo has no list with that name",
    "removed": "Removed it again",
    "cannotRemove": "Couldn't take that one back (it was changed since)",
}


class Busy(Exception):
    pass


def default_paths(snapshot_path: str | Path | None = None) -> dict:
    snap = Path(os.path.expanduser(str(snapshot_path))) if snapshot_path else None
    return {
        "actions_dir": ROOT / "drop-folder" / "actions",
        "pending": HERE / "state" / "actions.json",
        "results": (snap.parent / "actions-result.json") if snap else None,
    }


def _now() -> datetime:
    return datetime.now().astimezone()


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return d if d.tzinfo else d.astimezone()
    except ValueError:
        return None


def _read(path: Path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_atomic(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{secrets.token_hex(4)}.tmp"   # hidden + wrong suffix: QuickToDo ignores it
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _load_state(paths) -> dict:
    s = _read(paths["pending"], {})
    out = {"pending": list(s.get("pending", [])), "recent": list(s.get("recent", []))}
    if isinstance(s.get("doneDay"), dict):
        out["doneDay"] = s["doneDay"]
    return out


def _count_done(state: dict, delta: int, now: datetime) -> None:
    """Keep today's count of Dones confirmed by QuickToDo (an undo takes one back)."""
    day = now.date().isoformat()
    cur = state.get("doneDay") if isinstance(state.get("doneDay"), dict) else {}
    n = int(cur.get("n", 0)) if cur.get("date") == day else 0
    state["doneDay"] = {"date": day, "n": max(0, n + delta)}


def _results(paths) -> dict:
    if not paths.get("results"):
        return {}
    data = _read(paths["results"], {})
    return {r["id"]: r for r in data.get("results", []) if isinstance(r, dict) and r.get("id")}


def _new_id(now: datetime) -> str:
    return "act-" + now.strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(3)


def _drop(paths, req: dict) -> None:
    _write_atomic(Path(paths["actions_dir"]) / f"{req['id']}{SUFFIX}", {
        "version": 1, "id": req["id"], "action": req["action"], "taskId": req["taskId"],
        "title": req["title"], "requestedAt": req["requestedAt"], **({"undoes": req["undoes"]} if req.get("undoes") else {}),
        **({"list": req["list"], "due": req.get("due")} if req.get("action") == "add" else {}),
    })


def request_done(task_id: str, open_tasks: list | None, paths: dict, now: datetime | None = None) -> dict:
    """Queue a Done for an open snapshot task. Raises ValueError (bad request) or Busy (already pending)."""
    now = now or _now()
    task_id = str(task_id or "")
    if len(task_id) < 8:
        raise ValueError("taskId required")
    if open_tasks is None:
        raise ValueError("Can't read QuickToDo's task list right now, so nothing was marked done")
    task = next((t for t in open_tasks if t.get("id") == task_id), None)
    if task is None:
        raise ValueError("That task isn't open in QuickToDo")
    with LOCK:
        state = _load_state(paths)
        if any(p["taskId"] == task_id for p in state["pending"]):
            raise Busy("Already marking that one done")
        req = {"id": _new_id(now), "action": "complete", "taskId": task_id, "title": task.get("title", ""),
               "requestedAt": now.isoformat(timespec="seconds")}
        _drop(paths, req)
        state["pending"].append(req)
        _write_atomic(paths["pending"], state)
    return req


def request_add(title: str, list_name: str, due: str | None, known_lists: list | None, paths: dict,
                now: datetime | None = None) -> dict:
    """Queue a new task for QuickToDo to create (Phase 15). The list must already exist; the due date is optional."""
    now = now or _now()
    title = " ".join(str(title or "").split())
    if not 1 <= len(title) <= 200:
        raise ValueError("Give the task a title (up to 200 characters)")
    if known_lists is None:
        raise ValueError("Can't read QuickToDo's lists right now, so nothing was added")
    match = next((l for l in known_lists if l.casefold() == str(list_name or "").strip().casefold()), None)
    if match is None:
        raise ValueError("Pick one of your existing lists")
    if due:
        d = _parse(str(due))
        if d is None:
            raise ValueError("That due date didn't make sense")
        due = d.isoformat(timespec="seconds")      # QuickToDo's ISO8601 decoder needs the seconds
    with LOCK:
        state = _load_state(paths)
        if any(p.get("action") == "add" and p["title"].casefold() == title.casefold() and p.get("list") == match
               and p.get("due") == due for p in state["pending"]):
            raise Busy("Already adding that one")
        req = {"id": _new_id(now), "action": "add", "taskId": "new", "title": title, "list": match, "due": due,
               "requestedAt": now.isoformat(timespec="seconds")}
        _drop(paths, req)
        state["pending"].append(req)
        _write_atomic(paths["pending"], state)
    return req


def request_unadd(action_id: str, paths: dict, now: datetime | None = None) -> dict:
    """Take back a task added here, within the undo window (QuickToDo moves it to Trash if untouched)."""
    now = now or _now()
    with LOCK:
        state = _load_state(paths)
        added = next((r for r in state["recent"] if r["id"] == action_id), None)
        if not added or added.get("action") != "add" or added.get("outcome") != "added":
            raise ValueError("Only a task added here can be taken back")
        if not _undoable(added, state, now):
            raise ValueError("Too late to undo here; delete it in QuickToDo")
        req = {"id": _new_id(now), "action": "unadd", "taskId": added["taskId"], "title": added.get("title", ""),
               "requestedAt": now.isoformat(timespec="seconds"), "undoes": action_id}
        _drop(paths, req)
        state["pending"].append(req)
        _write_atomic(paths["pending"], state)
    return req


def request_undo(action_id: str, paths: dict, now: datetime | None = None) -> dict:
    """Queue a reopen for a Done made here, within the undo window."""
    now = now or _now()
    with LOCK:
        state = _load_state(paths)
        done = next((r for r in state["recent"] if r["id"] == action_id), None)
        if not done or done.get("action") != "complete" or done.get("outcome") != "done":
            raise ValueError("Only a Done made here can be undone")
        if not _undoable(done, state, now):
            raise ValueError("Too late to undo here; reopen it in QuickToDo")
        req = {"id": _new_id(now), "action": "reopen", "taskId": done["taskId"], "title": done.get("title", ""),
               "requestedAt": now.isoformat(timespec="seconds"), "undoes": action_id}
        _drop(paths, req)
        state["pending"].append(req)
        _write_atomic(paths["pending"], state)
    return req


def _undoable(r: dict, state: dict, now: datetime) -> bool:
    if (r.get("action"), r.get("outcome")) not in (("complete", "done"), ("add", "added")):
        return False
    at = _parse(r.get("processedAt"))
    if not at or (now - at).total_seconds() > UNDO_SECONDS:
        return False
    undone = any(x.get("undoes") == r["id"] for x in state["pending"] + state["recent"])
    return not undone


def sync(paths: dict, now: datetime | None = None) -> dict:
    """Match pending requests to QuickToDo's results, clean up processed files, return the view."""
    now = now or _now()
    with LOCK:
        state = _load_state(paths)
        results = _results(paths)
        changed = False
        still = []
        for p in state["pending"]:
            r = results.get(p["id"])
            if r is None:
                still.append(p)
                continue
            state["recent"].append({**p, "taskId": r.get("taskId") or p["taskId"], "outcome": r.get("outcome"), "detail": r.get("detail", ""),
                                    "processedAt": r.get("processedAt")})
            if (p.get("action"), r.get("outcome")) == ("complete", "done"):
                _count_done(state, 1, now)
            elif (p.get("action"), r.get("outcome")) == ("reopen", "reopened"):
                _count_done(state, -1, now)
            changed = True
        state["pending"] = still
        # Delete request files QuickToDo has processed (ours, in our folder only).
        adir = Path(paths["actions_dir"])
        if adir.is_dir():
            for f in adir.glob("*" + SUFFIX):
                if f.name[: -len(SUFFIX)] in results:
                    try:
                        f.unlink()
                    except OSError:
                        pass
        keep = [r for r in state["recent"] if (_parse(r.get("processedAt")) or now) >= now - RECENT_MAX_AGE][-RECENT_KEEP:]
        if keep != state["recent"]:
            state["recent"], changed = keep, True
        if changed:
            _write_atomic(paths["pending"], state)
        return view(state, now)


def view(state: dict, now: datetime) -> dict:
    pending = [{**p, "waiting": (now - (_parse(p["requestedAt"]) or now)).total_seconds() > WAITING_SECONDS} for p in state["pending"]]
    recent = []
    for r in state["recent"]:
        recent.append({**r, "text": OUTCOME_TEXT.get(r.get("outcome"), r.get("detail") or "Done"),
                       "undoable": _undoable(r, state, now)})
    dd = state.get("doneDay") or {}
    done_today = int(dd.get("n", 0)) if dd.get("date") == now.date().isoformat() else 0
    return {"pending": pending, "recent": list(reversed(recent)), "doneToday": done_today}
