"""Today's classes as visual suggestions (no task is created). Plain code, read-only.

From engine/inputs/commitments.json (labels "Class: <topic>") find today's sessions, then look for the matching
week folder under the course folders to offer the lecture files as "Read before class".
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

NOTE_DIRS = ("readings and lecture notes", "lecture", "readings")
OK_EXT = {".pdf", ".pptx", ".docx", ".doc", ".key", ".md", ".txt"}
STOP = {"class", "session", "test", "the", "and", "of", "for", "to", "a"}


def _words(text):
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP and not w.isdigit() and len(w) > 2]


def _week_start(p, year):
    m = re.search(r"-\s*([A-Za-z]{3})\w*\s+(\d{1,2})\b", p.name)
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)} {year}", "%b %d %Y").date()
    except ValueError:
        return None


def _week_folder(topic, course_roots, today=None):
    """Exact topic phrase in the folder name wins; otherwise most shared words, then the week closest to today."""
    want = set(_words(topic))
    cands = []
    for root in course_roots:
        for p in Path(root).expanduser().glob("Week *"):
            if p.is_dir():
                cands.append(p)
    exact = [p for p in cands if topic.lower() in p.name.lower()]
    if exact:
        return exact[0]
    best, key = None, None
    for p in cands:
        ov = len(want & set(_words(p.name)))
        if ov < max(1, len(want) // 2):
            continue
        ws = _week_start(p, today.year) if today else None
        gap = abs((ws - today).days) if ws else 999
        k = (-ov, gap)
        if key is None or k < key:
            best, key = p, k
    return best


def _files(week):
    out = []
    if not week:
        return out
    for sub in week.iterdir():
        if sub.is_dir() and any(k in sub.name.lower() for k in NOTE_DIRS):
            for f in sorted(sub.iterdir()):
                if f.is_file() and f.suffix.lower() in OK_EXT and not f.name.startswith((".", "~$")):
                    out.append({"name": f.name, "path": str(f)})
    return out


def today(commit_path, course_roots, now: datetime):
    try:
        rows = json.loads(Path(commit_path).read_text())
    except (OSError, ValueError):
        return []
    out = []
    for r in rows:
        label = str(r.get("label", ""))
        if not label.startswith("Class:"):
            continue
        try:
            st = datetime.fromisoformat(r["start"]); en = datetime.fromisoformat(r["end"])
        except (KeyError, ValueError):
            continue
        if st.astimezone(now.tzinfo).date() != now.date() or en.astimezone(now.tzinfo) < now:
            continue
        topic = label.split(":", 2)[-1].strip()
        is_test = label.lower().startswith("class: test")
        files = [] if is_test else _files(_week_folder(topic, course_roots, now.date()))
        out.append({"title": topic, "start": st.isoformat(), "end": en.isoformat(), "test": is_test, "files": files[:6]})
    return out
