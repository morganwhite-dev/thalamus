"""Cyber Academy progress as "where you left off" lines (Phase 22). Read-only; no model.

Cyber Academy keeps lesson and quiz progress in its own SQLite file. The brain only reads it
(opened read-only, never written). A Security Projects task whose title says "Cyber Academy
Tier N" gets one plain line from that tier's modules, e.g.
"Tier 1: 1 of 2 modules done, shell navigation in progress, last quiz 7/10 · 2 h ago".
Contract: play/STATE_MODEL.md (Phase 22 section).
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import leftoff_auto

ACADEMY = Path("~/Desktop/Projects/Cyber-Academy").expanduser()
TIER_RE = re.compile(r"cyber academy\s+tier\s*(\d+)", re.I)


def _load(academy: Path):
    try:
        cur = json.loads((academy / "content" / "curriculum.json").read_text(encoding="utf-8"))
        db = sqlite3.connect(f"file:{academy / 'data' / 'academy.sqlite3'}?mode=ro", uri=True, timeout=2)
    except (OSError, ValueError, sqlite3.Error):
        return None, {}, {}
    try:
        prog = {r[0]: (r[1], r[2]) for r in db.execute("select item_id, status, updated_at from progress")}
        last = {}
        for item, score, total, at in db.execute("select item_id, score, total, created_at from attempts order by created_at"):
            last[item] = (score, total, at)
    except sqlite3.Error:
        return None, {}, {}
    finally:
        db.close()
    return cur, prog, last


def _when(ts: str, now: datetime):
    try:
        d = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    return d


def tier_line(cur: dict, prog: dict, last: dict, n: int, now: datetime):
    tier = next((t for t in cur.get("tiers", []) if t.get("id") == f"tier-{n}"), None)
    mods = (tier or {}).get("modules", [])
    if not mods:
        return None
    done = [m for m in mods if prog.get(m["id"], ("", ""))[0] == "complete"]
    cur_m = [m for m in mods if prog.get(m["id"], ("", ""))[0] == "in-progress"]
    parts = [f"Tier {n}: {len(done)} of {len(mods)} modules done"]
    if cur_m:
        parts.append(f"{cur_m[0]['title'].lower()} in progress")
    elif len(done) < len(mods):
        parts.append("next: " + next(m for m in mods if m not in done)["title"].lower())
    attempts = [(last[m["id"]][2], last[m["id"]]) for m in mods if m["id"] in last]
    if attempts:
        _, (score, total, _) = max(attempts)
        parts.append(f"last quiz {score}/{total}")
    stamps = [d for d in (_when(prog[m["id"]][1], now) for m in mods if m["id"] in prog) if d]
    line = ", ".join(parts)
    if stamps:
        line += f" · {leftoff_auto.ago(max(stamps), now)}"
    return line


def compute(tasks, now: datetime, academy: Path = ACADEMY):
    """{taskId: line} for tasks that name a Cyber Academy tier. Empty if Academy data is unreadable."""
    wanted = [(t, TIER_RE.search(t.get("title", ""))) for t in tasks or []]
    wanted = [(t, m) for t, m in wanted if m]
    if not wanted:
        return {}
    cur, prog, last = _load(Path(academy))
    if cur is None:
        return {}
    out = {}
    for t, m in wanted:
        line = tier_line(cur, prog, last, int(m.group(1)), now)
        if line:
            out[t["id"]] = line
    return out
