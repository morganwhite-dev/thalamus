"""Plain-code lookups for the command box (Phase 16): find course files by plain question. No model, no usage.

`detect(text)` -> a Query or None. `search(query, config)` -> {"answer": str, "files": [{name, rel, path}]}.
`safe_open_path(path, config)` validates a path for the Open button. Contract: command/STATE_MODEL_LOOKUP.md.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

LEAD = re.compile(r"^\s*(?:please\s+|hey\s+|can you\s+|could you\s+)?(?:do you have|do i have|have you got|is there|are there|got any|any |"
                  r"give me|get me|get (?:the|my)|send me|link(?:s)? (?:to|for)|what(?:'s| is) the link (?:to|for)|find(?: me)?|where(?:'s|s| is| are|'d i (?:put|save)| did i (?:put|save))|show(?: me)?|open(?: up)?|"
                  r"pull up|bring up|grab|locate|look for|search for|i need|need|i want|got)\b", re.I)
# only these openers start a search by file name alone; "give me ...", "do I have ...", "I need ..." must name a kind of document
FIND_LEAD = re.compile(r"^\s*(?:please\s+|hey\s+|can you\s+|could you\s+)?(?:find(?: me)?|where(?:'s|s| is| are|'d i (?:put|save)| did i (?:put|save))|show me my|open(?: up)?|"
                       r"pull up|bring up|grab|locate|look for|search for)\b", re.I)
WHEN_WORDS = re.compile(r"\b(due|overdue|deadlines?|today|tonight|tomorrow|this week|next week|this weekend)\b", re.I)
KINDS = [  # (label, words that must all be in the file name)
    ("teaching notes", ["teaching", "notes"]), ("outline notes", ["outline", "notes"]), ("study guide", ["study", "guide"]),
    ("quiz", ["quiz"]), ("syllabus", ["syllabus"]), ("slides", None), ("deck", None), ("lab", ["lab"]),
    ("assignment", ["assignment"]), ("planner", ["planner"]), ("exam", ["exam"]),
]
SLIDE_EXT = {"pptx", "ppt", "key"}
DOC_WORDS = re.compile(r"\b(notes?|slides?|deck|quiz(?:zes)?|study guide|outline|syllabus|reading|lecture|labs?|assignments?|planner|exam|module|week)\b", re.I)
COURSES = {"network security": "network", "cloud": "cloud", "cloud computing": "cloud", "cis 8088": "network", "cis 8087": "cloud"}
NUM = r"(\d{1,2})"
STOP = {"do", "you", "have", "the", "for", "and", "a", "an", "my", "of", "in", "on", "to", "any", "is", "there", "are", "me", "show", "find", "i", "class", "course"}


class Query(dict):
    pass


def _numbers(text, word):
    """Numbers after 'module'/'week': 'module 5 and 6' -> [5, 6]; 'modules 1, 2 and 3' -> [1, 2, 3]."""
    out = []
    for m in re.finditer(word + r"s?\s*((?:\d{1,2})(?:\s*(?:,|and|&|to|-)\s*\d{1,2})*)", text, re.I):
        chunk = m.group(1)
        if re.search(r"\bto\b|-", chunk):
            a, b = [int(x) for x in re.findall(r"\d{1,2}", chunk)][:2]
            out += list(range(min(a, b), max(a, b) + 1))
        else:
            out += [int(x) for x in re.findall(r"\d{1,2}", chunk)]
    return sorted(set(out))


def detect(text):
    t = (text or "").strip()
    bare = re.match(r"^\s*(?:the\s+|my\s+)?(?:teaching notes|outline notes|study guide|syllabus|quiz(?!\s+me\b)|slides|module\s*\d)", t, re.I)
    if not t or len(t) > 300 or not (LEAD.match(t) or bare) or t.endswith("?") and not LEAD.match(t):
        return None
    if WHEN_WORDS.search(t) and not re.search(r"\b(?:module|week|class|session)s?\s*\d", t, re.I):
        return None                        # "do I have a quiz this week" asks about the calendar, not for a file
    if not DOC_WORDS.search(t):
        return _generic(t)
    low = t.lower()
    kinds = [k for k in KINDS if re.search(r"\b" + re.escape(k[0]) + r"s?\b", low) or (k[0] == "slides" and "slide" in low)]
    # "teaching notes" should not also trigger plain words from shorter kinds
    labels = {k[0] for k in kinds}
    if "teaching notes" in labels or "outline notes" in labels:
        kinds = [k for k in kinds if k[0] in ("teaching notes", "outline notes")]
    course = next((v for k, v in COURSES.items() if k in low), None)
    if course == "cloud" and any(k[0] == "teaching notes" for k in kinds):
        kinds = kinds + [("annotated", ["annotated"])]        # Cloud's notes are the annotated decks
    weeks = _numbers(low, "week")
    if not weeks and course != "network":
        weeks = _numbers(low, "class") or _numbers(low, "session")      # Cloud's classes are numbered like its week folders
    modules = _numbers(low, "module")
    chapter = False
    if not modules and not weeks and _numbers(low, "chapter"):
        weeks, chapter = _numbers(low, "chapter"), True     # her notes are filed by week and module, never by chapter
    q = Query(text=t, modules=modules, weeks=weeks, kinds=kinds, course=course)
    q["chapter"] = chapter
    words = [w for w in re.findall(r"[a-z][a-z0-9']+", low) if w not in STOP]
    q["words"] = words
    if not (q["modules"] or q["weeks"] or kinds):
        return _generic(t)
    return q


GENERIC_STOP = STOP | {"find", "where", "where's", "wheres", "open", "look", "pull", "up", "search", "got", "file", "files", "folder", "document",
                       "doc", "docs", "somewhere", "about", "that", "this", "please", "can", "could", "what", "which", "all", "with", "from"}


def _generic(t):
    """Any "find/where is/do you have/open X" question: search file names for X's words (kept only if something matches)."""
    if not FIND_LEAD.match(t):
        return None
    terms = [w for w in re.findall(r"[a-z0-9][a-z0-9']+", t.lower()) if w not in GENERIC_STOP and len(w) >= 3]
    if not terms:
        return None
    return Query(text=t, modules=[], weeks=[], kinds=[], course=None, words=terms, generic=True)


def _roots(config):
    return [Path(os.path.expanduser(r)) for r in (config.get("lookup") or {}).get("roots", [])]


def _walk(config):
    lk = config.get("lookup") or {}
    exts = {e.lower() for e in lk.get("extensions", [])}
    budget = int(lk.get("maxFiles", 8000))
    skip = set(lk.get("skipDirs", [])) | {"node_modules", "__pycache__"}
    deadline = time.monotonic() + float(lk.get("maxSeconds", 4))
    for root in _roots(config):
        if not root.is_dir():
            continue
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in skip and not d.endswith((".app", ".xcodeproj", ".xcassets"))]
            if time.monotonic() > deadline:
                return
            for f in files:
                if f.startswith(".") or f.startswith("~$"):
                    continue
                if Path(f).suffix.lower().lstrip(".") in exts:
                    yield root, Path(dirpath) / f
                    budget -= 1
                    if budget <= 0:
                        return


def _has_module(name, n):
    return re.search(r"module\s*0*" + str(n) + r"(?!\d)", name, re.I) is not None


def _has_week(path, n):
    return re.search(r"week\s*0*" + str(n) + r"(?!\d)", path, re.I) is not None


def _kind_ok(kinds, name, ext):
    if not kinds:
        return True
    low = name.lower()
    for label, words in kinds:
        if words is None:
            if ext in SLIDE_EXT:
                return True
        elif all(w in low for w in words):
            return True
    return False


def search(q, config):
    hits = []
    for root, path in _walk(config):
        rel = str(path.relative_to(root))
        if q["course"] and q["course"] not in "/".join(rel.lower().split("/")[:-1][:2] + [root.name.lower()]):
            continue
        name = path.name
        ext = path.suffix.lower().lstrip(".")
        if q.get("generic"):
            hay = re.sub(r"[_\-.]+", " ", rel.lower())
            if not all(w in hay for w in q["words"]):
                continue
        if not _kind_ok(q["kinds"], name, ext):
            continue
        if q["modules"] and not any(_has_module(name, n) or _has_module(rel, n) for n in q["modules"]):
            continue
        if q["weeks"] and not any(_has_week(rel, n) for n in q["weeks"]):
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0
        hits.append({"name": name, "rel": rel, "path": str(path), "course": root.name, "mtime": mtime,
                     "mods": [n for n in q["modules"] if _has_module(name, n) or _has_module(rel, n)]})
    # Best first: a file whose own NAME carries the module beats one that only sits in a module folder; html/pdf before pptx
    hits.sort(key=lambda h: (0 if any(_has_module(h["name"], n) for n in q["modules"]) else 1, min(h["mods"] or [99]), -h["mtime"], len(h["rel"])))
    if q.get("generic"):
        hits.sort(key=lambda h: (-sum(w in re.sub(r"[_\-.]+", " ", h["name"].lower()) for w in q["words"]), -h["mtime"], len(h["rel"])))
    limit = int((config.get("lookup") or {}).get("maxResults", 12))
    shown = hits[:limit]
    kind = ", ".join(k[0] for k in q["kinds"]) or "files"
    def _join(label, nums):
        if not nums:
            return None
        return f"{label} " + (", ".join(map(str, nums[:-1])) + " and " + str(nums[-1]) if len(nums) > 1 else str(nums[0]))
    parts = [x for x in (_join("module", q["modules"]), _join("week", q["weeks"])) if x]
    where = " for " + " and ".join(parts) if parts else ""
    if not shown:
        hint = " Teaching notes are made in Claude from the week's slides, so ask it to make them." if any(k[0] == "teaching notes" for k in q["kinds"]) else ""
        return {"answer": f"I didn't find any {kind}{where} on your Desktop.{hint} "
                          f"I only look in {', '.join(str(r).replace(str(Path.home()), '~') for r in _roots(config)) or 'no folders (none set)'}.", "files": []}
    lines = [f"Found {len(hits)} {'match' + ('es' if len(hits) != 1 else '') if q.get('generic') else kind}{where}:" + (f" (showing {limit})" if len(hits) > limit else "")]
    if q.get("chapter"):
        lines.insert(0, "Your notes are filed by week and module, not chapter, so I looked in " + " and ".join(f"week {n}" for n in q["weeks"]) + ".")
    for h in shown:
        lines.append(f"- {h['name']}  ({Path(h['rel']).parent})")
    missing = [n for n in q["modules"] if not any(n in h["mods"] for h in hits)]
    if missing:
        lines.append("Not found: " + ", ".join(f"module {n}" for n in missing) + ".")
    return {"answer": "\n".join(lines),
            "files": [{"name": h["name"], "rel": h["rel"], "path": h["path"]} for h in shown]}


def safe_open_path(path, config):
    """The real path if it may be opened from the dashboard, else None."""
    try:
        real = Path(os.path.realpath(os.path.expanduser(str(path))))
    except (OSError, ValueError):
        return None
    exts = {e.lower() for e in (config.get("lookup") or {}).get("extensions", [])}
    if not real.is_file() or real.suffix.lower().lstrip(".") not in exts:
        return None
    for root in _roots(config):
        try:
            real.relative_to(os.path.realpath(root))
            return real
        except ValueError:
            continue
    return None
