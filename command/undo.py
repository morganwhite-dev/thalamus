"""Undo for what the chat changes (STATE_MODEL_UNDO.md). Plain code, no model.

A change is recorded as steps, one per record it touched, each with the record's value before and after:
    {"store": "overrides", "coll": "pins"|"skips"|"snoozes", "id": taskId, "before": entry|None, "after": entry|None}
    {"store": "play", "coll": "projects"|"reminders"|"leftOff", "id": recordId, "before": rec|None, "after": rec|None}
Undo puts every `before` back, but only when every record still holds its `after` (nothing changed since).
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

WINDOW = timedelta(minutes=2)
KEEP = timedelta(minutes=10)
OV_COLLS = ("pins", "skips", "snoozes")
PLAY_COLLS = ("projects", "reminders", "habits")
UNDO_RE = re.compile(r"^(?:please\s+)?(?:undo(?:\s+(?:that|it|this|(?:the|my) last (?:one|thing|change|action)))?|take (?:that|it) back|reverse that)(?:\s+please)?$", re.I)
_LOCK = threading.Lock()


def is_undo(text) -> bool:
    return bool(UNDO_RE.match(" ".join(str(text or "").split()).strip(" .!")))


# ---------------------------------------------------------------- recording
def _by_task(ov, coll):
    return {e.get("taskId"): e for e in (ov or {}).get(coll, []) if isinstance(e, dict) and e.get("taskId")}


def diff_overrides(before, after, ids):
    """Only the tasks the chat acted on (`ids`): writing overrides also prunes expired entries of other tasks."""
    steps = []
    for coll in OV_COLLS:
        b, a = _by_task(before, coll), _by_task(after, coll)
        for tid in sorted((set(b) | set(a)) & set(ids)):
            if b.get(tid) != a.get(tid):
                steps.append({"store": "overrides", "coll": coll, "id": tid, "before": b.get(tid), "after": a.get(tid)})
    return steps


def diff_play(before, after):
    steps = []
    for coll in PLAY_COLLS:
        b = {r["id"]: r for r in (before or {}).get(coll, []) if isinstance(r, dict) and r.get("id")}
        a = {r["id"]: r for r in (after or {}).get(coll, []) if isinstance(r, dict) and r.get("id")}
        for rid in sorted(set(b) | set(a)):
            if b.get(rid) != a.get(rid) and (rid not in b or rid not in a):   # added or removed; a touchedAt bump is not the change
                steps.append({"store": "play", "coll": coll, "id": rid, "before": b.get(rid), "after": a.get(rid)})
    b, a = (before or {}).get("leftOff", {}), (after or {}).get("leftOff", {})
    for tid in sorted(set(b) | set(a)):
        if b.get(tid) != a.get(tid):
            steps.append({"store": "play", "coll": "leftOff", "id": tid, "before": b.get(tid), "after": a.get(tid)})
    return steps


class UndoStore:
    """command/state/undo.json. One entry per chat change; used once; 2 minutes."""

    def __init__(self, path):
        self.path = Path(path)

    def _load(self):
        try:
            d = json.loads(self.path.read_text())
            return d.get("entries", []) if isinstance(d, dict) else []
        except (OSError, ValueError):
            return []

    def _save(self, entries, now):
        keep = [e for e in entries if _at(e.get("createdAt"), now) > now - KEEP]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent)
        with os.fdopen(fd, "w") as f:
            json.dump({"version": 1, "entries": keep}, f, indent=2)
        os.replace(tmp, self.path)

    def record(self, steps, label, job_id, now):
        """Store an entry and return {id, expires}, or None when nothing changed."""
        if not steps:
            return None
        with _LOCK:
            entries = self._load()
            e = {"id": "u-" + uuid.uuid4().hex[:10], "jobId": job_id, "label": label, "createdAt": now.isoformat(),
                 "expires": (now + WINDOW).isoformat(), "used": False, "steps": steps}
            entries.append(e)
            self._save(entries, now)
        return {"id": e["id"], "expires": e["expires"]}

    def newest_live(self, now):
        """The newest entry still inside its 2 minutes and not used, or None (the chat compares it with its own adds and Dones)."""
        live = [e for e in self._load() if not e.get("used") and _at(e.get("expires"), now) > now]
        return live[-1] if live else None

    def take(self, undo_id, now):
        """The entry to undo (marked used), or (None, reason). undo_id None = the newest live one."""
        with _LOCK:
            entries = self._load()
            live = [e for e in entries if not e.get("used") and _at(e.get("expires"), now) > now]
            if undo_id is None:
                e = live[-1] if live else None
                if e is None:
                    return None, "Nothing the box changed in the last 2 minutes. To take back a Done, press Undo on the status line."
            else:
                e = next((x for x in entries if x.get("id") == undo_id), None)
                if e is None:
                    return None, "I can't find that change anymore, so I left everything alone."
                if e.get("used"):
                    return None, "That's already undone."
                if e not in live:
                    return None, "That was more than 2 minutes ago, so I left it alone."
            e["used"] = True
            self._save(entries, now)
            return e, None


def _at(s, now):
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return now - KEEP - KEEP


# ---------------------------------------------------------------- applying
def read_overrides(path):
    """The engine's overrides file as a dict ({} when it does not exist yet or cannot be read)."""
    try:
        d = json.loads(Path(path).read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _current(step, ov, ps):
    if step["store"] == "overrides":
        return _by_task(ov, step["coll"]).get(step["id"])
    if step["coll"] == "leftOff":
        return (ps.get("leftOff") or {}).get(step["id"])
    return next((r for r in ps.get(step["coll"], []) if r.get("id") == step["id"]), None)


def _put(step, ov, ps):
    if step["store"] == "overrides":
        ov[step["coll"]] = [e for e in ov.get(step["coll"], []) if e.get("taskId") != step["id"]]
        if step["before"] is not None:
            ov[step["coll"]].append(step["before"])
    elif step["coll"] == "leftOff":
        ps.setdefault("leftOff", {}).pop(step["id"], None)
        if step["before"] is not None:
            ps["leftOff"][step["id"]] = step["before"]
    else:
        ps[step["coll"]] = [r for r in ps.get(step["coll"], []) if r.get("id") != step["id"]]
        if step["before"] is not None:
            ps[step["coll"]].append(step["before"])
        else:                                   # a parked idea pinned with Show first since: free its slot too
            ps["front"] = [x for x in ps.get("front", []) if x != step["id"]]


def apply(steps, config, play_path=None):
    """Put every `before` back. -> (True, None) or (False, why). Checks every record first; writes nothing on a mismatch."""
    import brain
    from brain_engine import empty_overrides
    import play as play_store
    need_ov = any(s["store"] == "overrides" for s in steps)
    need_play = any(s["store"] == "play" for s in steps)
    ov_path = brain.resolve("overridesPath", config) if need_ov else None
    ov = (read_overrides(ov_path) or empty_overrides()) if need_ov else {}
    ps = play_store.load(play_path) if need_play else {}
    for s in steps:
        if _current(s, ov, ps) != s["after"]:
            return False, "That changed since, so I left it alone."
    for s in steps:
        _put(s, ov, ps)
    if need_ov:
        brain.write_json_atomic(ov_path, ov)
    if need_play:
        play_store.save(ps, play_path)
    return True, None
