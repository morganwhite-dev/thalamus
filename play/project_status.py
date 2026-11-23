"""Project status as one plain line, read from the project folder (Phase 12j). Read-only; no model.
Contract: play/STATE_MODEL.md (12j)."""
from __future__ import annotations
import os, re, subprocess
from datetime import datetime
from pathlib import Path

MAX_LINE = 140
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".build", "DerivedData", ".next"}
MAX_FILES = 20000
DEFAULT_ROOTS = ["~/Desktop/Projects", "~/Desktop/Projects/Coding", "~/Desktop/Projects/Portfolio-Projects"]


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def ago(then, now):
    s = max(0, int((now - then).total_seconds()))
    if s < 120: return "just now"
    if s < 3600: return f"{s // 60} min ago"
    if s < 86400: return f"{s // 3600} h ago"
    d = s // 86400
    return "yesterday" if d == 1 else f"{d} days ago"


def _notes_path(notes):
    m = re.search(r"(?im)^\s*path:\s*(\S.*?)\s*$", notes or "")
    return Path(os.path.expanduser(m.group(1))) if m else None


def resolve_folder(title, notes="", path=None, roots=None):
    """(folder, how). folder is None when there is nothing safe to read."""
    explicit = Path(os.path.expanduser(path)) if path else _notes_path(notes)
    if explicit:
        return (explicit, "path") if explicit.is_dir() else (None, "bad-path")
    want = norm(title)
    if len(want) < 4:
        return None, "none"
    hits = []
    for r in roots or DEFAULT_ROOTS:
        root = Path(os.path.expanduser(r))
        try:
            for d in root.iterdir():
                n = norm(d.name)
                if d.is_dir() and not d.name.startswith(".") and n and (n == want or (len(n) >= 6 and (n in want or want in n))):
                    hits.append(d)
        except OSError:
            continue
    uniq = {h.resolve() for h in hits}
    if len(uniq) == 1:
        return next(iter(uniq)), "name"
    return None, "ambiguous" if uniq else "none"


def _git(folder, *args):
    r = subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True, timeout=5,
                       env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        raise ValueError(r.stderr.strip())
    return r.stdout


def _walk(folder, now):
    """(newest mtime, name, files changed in the last 7 days) ignoring hidden and dependency folders."""
    newest, name, week, seen = 0.0, "", 0, 0
    cutoff = now.timestamp() - 7 * 86400
    for dp, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for f in files:
            if f.startswith("."):
                continue
            seen += 1
            if seen > MAX_FILES:
                return newest, name, week
            try:
                m = os.stat(os.path.join(dp, f)).st_mtime
            except OSError:
                continue
            if m > newest: newest, name = m, f
            if m >= cutoff: week += 1
    return newest, name, week


def _fit(s):
    return s if len(s) <= MAX_LINE else s[:MAX_LINE - 3] + "..."


PHASE = re.compile(r"\b(phase|phases|step|stage|milestone|week|sprint)\s+(\d+[a-z]?)(?:\s*(?:to|-|–)\s*(\d+[a-z]?))?", re.I)
VERBS = [(("fix", "fixes", "fixed", "bug", "bugfix", "patch", "resolve"), "fixing bugs"),
         (("test", "tests"), "writing tests"),
         (("refactor", "clean", "cleanup", "tidy", "simplify"), "cleaning up the code"),
         (("doc", "docs", "readme", "comment"), "writing docs"),
         (("init", "initial", "setup", "scaffold"), "setting it up"),
         (("add", "adds", "added", "implement", "build", "create", "feat", "wire", "introduce", "new"), "building"),
         (("update", "improve", "tweak", "polish", "rename", "change"), "improving")]


def _phase(subjects):
    for sub in subjects:
        m = PHASE.search(sub)
        if m:
            return "Phase " + (m.group(3) or m.group(2)).upper().replace("PHASE", "")
    return None


def narrate(subjects, dirty, then, now):
    """Plain "where you were" sentence from commit messages (newest first). No git words."""
    phase = _phase(subjects)
    raw = subjects[0] if subjects else ""
    text = PHASE.sub("", raw).lstrip(" :-–,")
    conv = re.match(r"^\s*(\w+)(?:\([^)]*\))?!?:\s*", text)
    word = conv.group(1).lower() if conv else ""
    if conv:
        text = text[conv.end():]
    else:
        text = re.sub(r"^[^:]{1,30}:\s*", "", text)               # "Project name: "
    first = word or (re.split(r"\W+", text.lower(), maxsplit=1)[0] if text else "")
    activity = next((a for words, a in VERBS if first in words), None)
    rest = re.split(r"[:(]| - ", text, maxsplit=1)[0].strip(" ,.-")
    if first and not word:
        rest = rest.split(None, 1)[1].strip(" ,.-") if len(rest.split(None, 1)) > 1 else ""
    if word and rest.split(None, 1) and rest.split(None, 1)[0].lower() in {w for ws, _ in VERBS for w in ws}:
        rest = rest.split(None, 1)[1] if len(rest.split(None, 1)) > 1 else ""      # "feat: add X" -> "X"
    obj = rest if len(rest) <= 40 else rest[:37].rstrip() + "..."
    if activity and obj:
        if activity == "fixing bugs":
            activity = f"fixing bugs: {obj}"
        elif activity == "cleaning up the code":
            activity = f"cleaning up {obj}"
        elif activity not in ("setting it up",):
            activity = f"{activity} {obj}"
    if phase and activity:
        head = f"On {phase}, {activity}"
    elif activity:
        head = activity[0].upper() + activity[1:]
    elif phase:
        head = f"On {phase}"
    else:
        head = text if len(text) <= 60 else text[:57] + "..."
    return _fit(f"{head} · {ago(then, now)}" + (" · unsaved work" if dirty else ""))


def status_line(folder, now):
    """One plain line, or None when the folder is missing or empty."""
    if not folder or not Path(folder).is_dir():
        return None
    tz = now.tzinfo
    try:
        out = _git(folder, "log", "-5", "--format=%ct%x09%s").strip().splitlines()
        if out:
            dirty = [l[3:] for l in _git(folder, "status", "--porcelain").splitlines() if l.strip()]
            ts0 = int(out[0].partition("\t")[0])
            then = datetime.fromtimestamp(ts0, tz)
            for f in dirty:
                try:
                    then = max(then, datetime.fromtimestamp(os.stat(Path(folder) / f.strip('"').split(" -> ")[-1]).st_mtime, tz))
                except OSError:
                    pass
            return narrate([l.partition("\t")[2] for l in out], dirty, then, now)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    newest, name, week = _walk(folder, now)
    if not newest:
        return None
    then = datetime.fromtimestamp(newest, tz)
    return _fit(f"Editing {name} · {ago(then, now)} · {week} file{'s' if week != 1 else ''} changed this week")


# ---------------------------------------------------------------- command intent
INTENT = re.compile(
    r"^\s*(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?(?:(?:update|refresh|save|check|show(?: me)?|what(?:'s| is))\s+(?:the\s+)?status\s+(?:of|on|for)\s+"
    r"|status\s+(?:of|on|for)\s+|where did i leave off on\s+)(?:my\s+|the\s+)?[\"']?(?P<name>.+?)[\"']?(?:\s+project)?\s*[?.!]?\s*$", re.I)


INTENT2 = re.compile(
    r"^\s*(?:please\s+)?(?:where (?:am|was|were) i (?:at )?(?:on|with|in)\s+|where did i (?:stop|leave off) (?:on|with|in)\s+|where (?:were we|did we (?:leave off|stop)) (?:on|with|in)\s+|what did i (?:do|get done|finish|work on|change) (?:on|in|with|for)\s+|where did i (?:end up|get to|get) (?:on|with|in)\s+|how far along (?:is|are) (?:my |the )?(?=\S)|what was i (?:working on|doing)(?: (?:in|on|with))?\s+|"
    r"what(?:'s| is) (?:the )?(?:latest|progress) (?:on|with)\s+|catch me up (?:on|with)\s+|remind me where i (?:was|left off|am|stopped) (?:on|with|in)\s+|"
    r"what did i (?:do|get done|finish) last (?:on|with|in)\s+|what did i last do (?:on|with|in)\s+|progress (?:on|with)\s+|update (?:on|for)\s+|"
    r"where(?:'d| did) i (?:leave off|stop) (?:on|with|in)\s+|where am i at (?:on|with|in)\s+|fill me in on\s+|update me on\s+|what(?:'s| is) (?:going on|happening|up) with\s+|how far (?:did i get|am i|along am i) (?:on|with|in)\s+|"
    r"(?:what(?:'s| is) )?(?:the )?last thing i (?:did|worked on|touched|changed) (?:on|in|with)\s+|what was my last (?:commit|change|edit|update|save) (?:on|in|to|for|with)\s+|when did i (?:last )?(?:work on|touch|update|commit to|edit|open|look at)\s+|where did i leave\s+|where are we (?:on|with)\s+|what(?:'s| is) left (?:on|for|to do on)\s+(?=(?:my |the )?\S+\s*(?:project)?\s*[?.!]?\s*$)|status\s+)(?:my\s+|the\s+)?[\"']?(?P<name>.+?)[\"']?(?:\s+project)?\s*[?.!]?\s*$", re.I)
INTENT3 = re.compile(r"^\s*how(?:'s|s| is)\s+(?:my\s+|the\s+)?[\"']?(?P<name>.+?)[\"']?(?:\s+project)?\s+(?:going|coming along|doing)\s*[?.!]?\s*$", re.I)


BARE = re.compile(r"^\s*(?:ok(?:ay)?\s+|hey\s+|so\s+)?(?:where\s+(?:was\s+i|did\s+i\s+(?:leave\s+off|stop)|am\s+i(?:\s+at)?)|where'd\s+i\s+(?:leave\s+off|stop)|what\s+was\s+i\s+(?:last\s+)?(?:doing|working\s+on)|where\s+were\s+we|remind\s+me\s+where\s+i\s+(?:was|left\s+off|stopped)|pick\s+up\s+where\s+i\s+left\s+off|what\s+did\s+i\s+(?:do\s+last|last\s+do)|catch\s+me\s+up)(?:\s+(?:last\s+time|again|now))?\s*[?.!]?\s*$", re.I)


def is_bare(text):
    """"where was i" with no project named: means the project in focus."""
    text = text or ""
    return len(text) <= 300 and "\n" not in text and bool(BARE.match(" ".join(text.split())))


UPDATE = re.compile(r"^\s*(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?(?:update|refresh|save)\s+(?:the\s+|my\s+|its\s+)?status\b", re.I)


def is_update(text):
    """Only an explicit "update/refresh the status" saves the line; plain questions just answer, so the automatic line keeps following commits."""
    return bool(UPDATE.match(text or ""))


INTENT5 = re.compile(r"^\s*(?:my\s+|the\s+)?(?P<name>[\w -]{2,40}?)\s*[:\-]\s*(?:where (?:was|am) i|where did i (?:leave off|stop)|what(?:'s| is) the status|status|progress)\s*[?.!]?\s*$", re.I)
INTENT4 = re.compile(r"^\s*(?:my\s+|the\s+)?(?P<name>(?:[\w-]+\s+){0,3}[\w-]+?)(?:\s+project)?\s+(?:status|progress|update)\s*[?.!]?\s*$", re.I)


_NOT_A_PROJECT = re.compile(r"^(?:on |in |last |this |the )?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|yesterday|tonight|week|weekend|month|year|class|school|"
                            r"(?:morning|afternoon|evening|night)|(?:my )?(?:day|week))\b", re.I)


def parse_intent(text):
    """The project name from "update the status of X project" style commands, else None."""
    text = text or ""
    if "\n" in text or len(text) > 300:
        return None                                  # a command is one short line; anything else is for a model
    text = " ".join(text.split())                    # one space between words keeps the patterns below linear
    if not text:
        return None
    for rx in (INTENT, INTENT2, INTENT3, INTENT4, INTENT5):
        m = rx.match(text)
        if m:
            name = m.group("name").strip(" \"'")
            if _NOT_A_PROJECT.match(name):
                return None                  # "what did i do on monday" asks about a day, not a project
            return name or None
    return None


_FILLER = {"my", "the", "project", "a", "an", "app"}


def norm_words(s):
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in _FILLER}


def find_project(name, candidates):
    """candidates: [{id, title, ...}]. (best, None) | (None, 'none'|'ambiguous')."""
    want = norm(name)
    if not want:
        return None, "none"
    exact = [c for c in candidates if norm(c["title"]) == want]
    if len(exact) == 1: return exact[0], None
    part = [c for c in candidates if want in norm(c["title"]) or (len(norm(c["title"])) >= 6 and norm(c["title"]) in want)]
    if len(part) == 1: return part[0], None
    if len(part) > 1 or len(exact) > 1:
        return None, "ambiguous"
    words = norm_words(name)
    sub = [c for c in candidates if words and words <= norm_words(c["title"])]
    if len(sub) == 1:
        return sub[0], None
    return None, "ambiguous" if len(sub) > 1 else "none"
