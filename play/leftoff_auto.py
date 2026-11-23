"""Automatic "where I left off" lines for Play items (Phase 12h). Read-only; no model; contract in play/STATE_MODEL.md."""
from __future__ import annotations
import json, os, re, subprocess, time
from datetime import datetime
from pathlib import Path
import project_status

CACHE_SECONDS = 600
GIT_TIMEOUT = 5
_cache: dict = {}


def ago(then: datetime, now: datetime) -> str:
    s = max(0, int((now - then).total_seconds()))
    if s < 3600:
        m = max(1, s // 60)
        return f"{m} min ago" if s >= 60 else "just now"
    if s < 86400:
        h = s // 3600
        return f"{h} h ago"
    d = s // 86400
    return "yesterday" if d == 1 else f"{d} days ago"


def parse_path(notes):
    m = re.search(r"(?im)^\s*path:\s*(\S.*?)\s*$", notes or "")
    return Path(os.path.expanduser(m.group(1))) if m else None


def _git(folder, *args):
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    r = subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True, timeout=GIT_TIMEOUT, env=env, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        raise ValueError(r.stderr.strip() or "git failed")
    return r.stdout


def git_line(folder, now):
    """'Last: "msg" 2 days ago, 3 files uncommitted' or None (no folder, not a repo, no commits, git missing)."""
    try:
        if not folder or not Path(folder).is_dir():
            return None
        out = _git(folder, "log", "-1", "--format=%ct%x09%s").strip()
        dirty = len([l for l in _git(folder, "status", "--porcelain").splitlines() if l.strip()])
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if not out:
        return None
    ts, _, subject = out.partition("\t")
    then = datetime.fromtimestamp(int(ts), now.tzinfo)
    subject = subject if len(subject) <= 60 else subject[:57] + "..."
    tail = "all committed" if dirty == 0 else f"{dirty} file{'s' if dirty != 1 else ''} uncommitted"
    return f'Last: "{subject}" {ago(then, now)}, {tail}'


def last_worked(title, history_path, now):
    """'Last worked 3 days ago' from the block history (work_start events with this title), or None."""
    latest = None
    try:
        with open(history_path) as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("type") == "work_start" and e.get("title") == title:
                    at = datetime.fromisoformat(e["at"])
                    latest = at if latest is None or at > latest else latest
    except OSError:
        return None
    return f"Last worked {ago(latest, now)}" if latest else None


def auto_line(task, history_path, now, roots=None):
    """Project status from its folder (git or plain files, 12j), else the block history."""
    folder, _how = project_status.resolve_folder(task.get("title", ""), task.get("notes", ""), task.get("path"), roots)
    return project_status.status_line(folder, now) or last_worked(task.get("title", ""), history_path, now)


def compute(tasks, history_path, now, clock=time.monotonic, roots=None):
    """{taskId: line} for the tasks that have one, cached per task for CACHE_SECONDS."""
    out = {}
    for t in tasks or []:
        key = (t["id"], t.get("notes") or "", t.get("title"), t.get("path"))
        hit = _cache.get(key)
        if hit and clock() - hit[0] < CACHE_SECONDS:
            line = hit[1]
        else:
            line = auto_line(t, history_path, now, roots)
            _cache[key] = (clock(), line)
        if line:
            out[t["id"]] = line
    return out
