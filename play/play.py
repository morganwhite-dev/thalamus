"""Play: the deadline-free side of Thalamus (Phase 12). Pure functions plus a tiny JSON store.

Stores (brain-side only; QuickToDo is never written):
  parking lot  - one-line ideas that hit mid-task: {id, text, at}
  left off     - one line per Play task id: "where I left off"
Offers: a gentle, optional "want a N-minute go at X?" shown on light days. Never a ping, never ranked,
never remembered when ignored (no guilt pile).
Contract: play/STATE_MODEL.md.
"""
from __future__ import annotations
import hashlib
import json, os, re, tempfile
from datetime import datetime, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
from brain_engine import fmt_dur  # noqa: E402

STATE_PATH = Path(__file__).resolve().parent / "state" / "play.json"
MAX_LINE = 140
MAX_PARKED = 50


MAX_PROJECTS = 30
MAX_HABITS = 10
MAX_REMINDERS = 50
FOLLOW_COUNT = 3                       # every text she asks for: the first, then follow-ups
FOLLOW_GAP_HOURS = 4
QUIET_START = "22:30"                  # no follow-up is scheduled into quiet hours (same as push/config.json)
MAX_FRONT = 4
MAX_PLAN = 300
DEFAULT_NUDGE = "09:00"


def empty():
    return {"parking": [], "leftOff": {}, "projects": [], "offered": {}, "habits": [], "reminders": [], "front": []}


def load(path=None):
    p = Path(path or STATE_PATH)
    try:
        d = json.loads(p.read_text())
    except (OSError, ValueError):
        return empty()
    d.setdefault("parking", []); d.setdefault("leftOff", {}); d.setdefault("projects", []); d.setdefault("offered", {}); d.setdefault("habits", []); d.setdefault("reminders", []); d.setdefault("front", [])
    if d["parking"]:
        # Morgan, 2026-11-12: "any idea is a side project". Parked one-liners become not-started projects, and the
        # parking lot stays empty from now on (nothing is lost; the text is the project's title).
        for i, idea in enumerate(d["parking"]):
            d["projects"].append({"id": "proj-" + str(idea.get("id", i)).lstrip("p") + f"-{i}", "title": _line(idea.get("text")), "state": "idea",
                                  "at": idea.get("at") or ""})
        d["parking"] = []
        try:
            save(d, p)
        except OSError:
            pass
    return d


def save(state, path=None):
    p = Path(path or STATE_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent)
    with os.fdopen(fd, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, p)


def _line(text):
    t = " ".join(str(text or "").split())
    if not t:
        raise ValueError("write a line first")
    return t[:MAX_LINE]


def _h(h, salt, text):
    return hashlib.sha1(f"{h['id']}|{salt}|{text}".encode()).hexdigest()


def plan_pick(h, today=None):
    """The current item: a random one from what is left. It stays the same, day after day, until it is marked done;
    then the next random one takes over (Morgan, 2026-11-12). Seeded by the habit and how many are done, and remembered
    once chosen so adding items never changes it. Finished items are out of the cycle for good."""
    plan = h.get("plan", [])
    left = [i for i in plan if not i.get("doneAt")]
    if not left:
        return None
    keep = next((i for i in left if i["t"] == h.get("pickText")), None)
    if keep:
        return keep
    n = len(plan) - len(left)
    return min(left, key=lambda i: _h(h, n, i["t"]))


def plan_lock(h, today=None):
    """Remember the current pick before the list changes."""
    pick = plan_pick(h)
    if pick:
        h["pickDate"], h["pickText"] = today, pick["t"]


def plan_items(raw):
    """A study plan's list: a list of lines, or one text with newlines/semicolons. Numbering and bullets are stripped."""
    if isinstance(raw, str):
        raw = re.split(r"[\n;]+", raw)
    out = []
    for r in raw or []:
        t = re.sub(r"^\s*(?:\d+[.)]|[-*•])\s*", "", str(r)).strip()
        t = " ".join(t.split())[:MAX_LINE]
        if t:
            out.append({"t": t, "doneAt": None})
    return out


def apply(state, action, now, **a):
    """Returns a new state. Raises ValueError on bad input."""
    st = {"parking": list(state["parking"]), "leftOff": dict(state["leftOff"]),
          "projects": [dict(p) for p in state.get("projects", [])], "offered": dict(state.get("offered", {})),
          "habits": [dict(h) for h in state.get("habits", [])], "reminders": [dict(r) for r in state.get("reminders", [])],
          "front": list(state.get("front", []))}
    iso = now.isoformat()

    def project(pid):
        for p in st["projects"]:
            if p["id"] == pid:
                return p
        raise ValueError("no such project")

    def add_project(title):
        if len(st["projects"]) >= MAX_PROJECTS:
            raise ValueError("too many projects; finish or drop a few first")
        st["projects"].append({"id": "proj-" + now.strftime("%Y%m%d%H%M%S%f"), "title": _line(title), "state": "idea", "at": iso})
    if action == "park":
        add_project(a.get("text"))              # an idea is a side project that has not started yet
    elif action == "unpark":
        before = len(st["parking"])
        st["parking"] = [p for p in st["parking"] if p["id"] != a.get("id")]
        if len(st["parking"]) == before:
            raise ValueError("no such parked idea")
    elif action == "promote":
        idea = next((p for p in st["parking"] if p["id"] == a.get("id")), None)
        if not idea:
            raise ValueError("no such parked idea")
        add_project(a.get("title") or idea["text"])
        st["parking"] = [p for p in st["parking"] if p["id"] != idea["id"]]
    elif action == "addproject":
        add_project(a.get("text"))
    elif action == "startproject":
        p = project(a.get("id"))
        p.update(state="started", touchedAt=iso)
        p.setdefault("startedAt", iso)
    elif action == "dropproject":
        project(a.get("id"))
        st["projects"] = [p for p in st["projects"] if p["id"] != a["id"]]
        st["leftOff"].pop(a["id"], None)
        st["front"] = [x for x in st["front"] if x != a["id"]]
    elif action == "setpath":
        p = project(a.get("id"))
        folder = str(a.get("path") or "").strip()
        if folder:
            p["path"] = folder[:300]
        else:
            p.pop("path", None)
    elif action == "addreminder":
        if len(st["reminders"]) >= MAX_REMINDERS:
            raise ValueError("too many pending reminders")
        try:
            at = datetime.fromisoformat(str(a.get("at")))
        except ValueError:
            raise ValueError("when should I text you?")
        if at.tzinfo is None:
            at = at.astimezone()
        base = "rem-" + now.strftime("%Y%m%d%H%M%S%f")
        limit = datetime.strptime(QUIET_START, "%H:%M").time()
        for i in range(FOLLOW_COUNT):
            t = at + timedelta(hours=FOLLOW_GAP_HOURS * i)
            if i and (t.date() != at.date() or t.time() >= limit):
                break                  # follow-ups stay on the same day and out of quiet hours
            st["reminders"].append({"id": base if not i else f"{base}-f{i}", "group": base, "followUp": bool(i),
                                    "text": _line(a.get("text")), "at": t.isoformat(), "created": iso})
    elif action == "dropreminder":
        before = len(st["reminders"])
        hit = next((r for r in st["reminders"] if r["id"] == a.get("id")), None)
        grp = (hit or {}).get("group", a.get("id"))
        st["reminders"] = [r for r in st["reminders"] if r["id"] != a.get("id") and r.get("group", r["id"]) != grp]
        if len(st["reminders"]) == before:
            raise ValueError("no such reminder")
    elif action == "reminderdone":
        gone = set(a.get("ids") or [])
        st["reminders"] = [r for r in st["reminders"] if r["id"] not in gone]
    elif action in ("addhabit", "habitdone", "habitundo", "drophabit"):
        today = now.date().isoformat()
        st["habits"] = [h for h in st["habits"] if not h.get("until") or h["until"] >= today]   # a check-in ends with its due day
        if action == "addhabit" and a.get("until"):
            # a daily check-in on a due task: text-only, no node, tied to the task by title + list
            until = str(a.get("until"))
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", until) or until < today:
                raise ValueError("check-in needs a due day that has not passed")
            ft = a.get("forTask") or {}
            ttl, lst = _line(ft.get("title")), _line(ft.get("list"))
            if not ttl or not lst:
                raise ValueError("check-in needs the task's title and list")
            at = str(a.get("nudgeAt") or DEFAULT_NUDGE)
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", at):
                raise ValueError("nudge time must look like 17:00")
            days = sorted({int(d) for d in (a.get("days") or range(7)) if str(d).isdigit() and 0 <= int(d) <= 6}) or list(range(7))
            st["habits"] = [h for h in st["habits"] if not (h.get("forTask") and h["forTask"]["title"].lower() == ttl.lower() and h["forTask"]["list"].lower() == lst.lower())]
            if len(st["habits"]) >= MAX_HABITS:
                raise ValueError("too many daily habits; drop a few first")
            start = today if now.strftime("%H:%M") < at else (now.date() + timedelta(days=1)).isoformat()
            st["habits"].append({"id": "hab-" + now.strftime("%Y%m%d%H%M%S%f"), "title": ttl, "days": days, "cluster": "play", "notes": "", "nudgeAt": at,
                                 "at": iso, "doneDates": [], "textOnly": True, "minutes": None, "until": until, "startOn": start,
                                 "forTask": {"title": ttl, "list": lst}})
            return st
        if action == "addhabit":
            if len(st["habits"]) >= MAX_HABITS:
                raise ValueError("too many daily habits; drop a few first")
            title = _line(a.get("title"))
            items = plan_items(a.get("plan")) if a.get("plan") is not None else None
            same = next((h for h in st["habits"] if h["title"].lower() == title.lower()), None)
            if same and items is not None:
                # "make a study plan for tryhackme" when a Tryhackme habit exists: the plan joins it (no second reminder)
                merged = list(same.get("plan", []))
                for i in items:
                    if i["t"].lower() not in {x["t"].lower() for x in merged}:
                        merged.append(i)
                same["plan"] = merged[:MAX_PLAN]
                return st
            if same:
                raise ValueError("already a daily habit")
            try:
                minutes = int(a.get("minutes")) if a.get("minutes") else None
            except (TypeError, ValueError):
                raise ValueError("minutes must be a number")
            if minutes is not None and not 1 <= minutes <= 600:
                raise ValueError("minutes must be between 1 and 600")
            at = str(a.get("nudgeAt") or DEFAULT_NUDGE)
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", at):
                raise ValueError("nudge time must look like 17:00")
            days = sorted({int(d) for d in (a.get("days") or range(7)) if str(d).isdigit() and 0 <= int(d) <= 6}) or list(range(7))
            cluster = str(a.get("cluster") or "play")
            if cluster not in ("school", "intern", "personal", "security", "play"):
                raise ValueError("unknown cluster")
            st["habits"].append({"id": "hab-" + now.strftime("%Y%m%d%H%M%S%f"), "title": title, "days": days, "cluster": cluster,
                                 "notes": " ".join(str(a.get("notes") or "").split())[:200], "nudgeAt": at, "at": iso, "doneDates": [],
                                 "textOnly": bool(a.get("textOnly")), "minutes": minutes,
                                 **({"plan": items[:MAX_PLAN]} if items is not None else {})})
        else:
            h = next((x for x in st["habits"] if x["id"] == a.get("id")), None)
            if not h:
                raise ValueError("no such habit")
            if action == "habitdone":
                if today not in h["doneDates"]:
                    h["doneDates"] = (h["doneDates"] + [today])[-60:]
                    nxt = plan_pick(h, today)
                    if nxt:
                        nxt["doneAt"] = today        # finished: out of the cycle for good (Undo within the day puts it back)
            elif action == "habitundo":
                h["doneDates"] = [d for d in h["doneDates"] if d != today]
                for i in h.get("plan", []):
                    if i.get("doneAt") == today:
                        i["doneAt"] = None
            else:
                st["habits"] = [x for x in st["habits"] if x["id"] != h["id"]]
                st["front"] = [x for x in st["front"] if x != h["id"]]
    elif action == "front":
        # "Show first": pinned Play items fill the visible nodes before the rest. Only a choice about what shows,
        # never a deadline or a rank.
        fid = str(a.get("id") or "")
        if not fid or fid.startswith("offer:"):
            raise ValueError("pick a Play item")
        st["front"] = [fid] + [x for x in st["front"] if x != fid]
        if len(st["front"]) > MAX_FRONT:
            raise ValueError(f"{MAX_FRONT} items already show first; take one off first")
    elif action == "unfront":
        st["front"] = [x for x in st["front"] if x != str(a.get("id") or "")]
    elif action in ("planadd", "planremove", "planskip"):
        h = next((x for x in st["habits"] if x["id"] == a.get("id")), None)
        if not h:
            raise ValueError("no such habit")
        plan = h.setdefault("plan", [])
        today = now.date().isoformat()
        plan_lock(h, today)
        if action == "planadd":
            new = plan_items(a.get("items"))
            if not new:
                raise ValueError("write at least one item first")
            if len(plan) + len(new) > MAX_PLAN:
                raise ValueError("that plan is too long")
            plan.extend(new)
        elif action == "planremove":
            try:
                plan.pop(int(a.get("index")))
            except (TypeError, ValueError, IndexError):
                raise ValueError("no such item")
        else:   # planskip ("pick another"): a different random item for today; nothing is lost
            cur = plan_pick(h, today)
            others = [i for i in plan if not i.get("doneAt") and i is not cur]
            if cur and others:
                h["pickDate"], h["pickText"] = today, min(others, key=lambda i: _h(h, "x" + str(now.microsecond), i["t"]))["t"]
    elif action == "accept":
        tid = str(a.get("taskId") or "")
        if not tid:
            raise ValueError("taskId required")
        st["offered"][tid] = iso
    elif action == "leftoff":
        tid = str(a.get("taskId") or "")
        if not tid:
            raise ValueError("taskId required")
        for p in st["projects"]:
            if p["id"] == tid:
                p["touchedAt"] = iso
        text = " ".join(str(a.get("text") or "").split())
        if text:
            st["leftOff"][tid] = {"text": text[:MAX_LINE], "at": now.isoformat()}
        else:
            st["leftOff"].pop(tid, None)
    else:
        raise ValueError("unknown play action")
    return st


def kind_of(task, engine_cfg):
    """The Play kind a task belongs to (game, project, ...) or None. List, #tag or whole-word keyword."""
    text = f"{task.get('title', '')} {task.get('notes', '')}".lower()
    words = set(re.findall(r"[a-z0-9#]+", text))
    for k in (engine_cfg.get("play") or {}).get("kinds", []):
        if task.get("list") in k.get("lists", []) or (k.get("tag") and k["tag"] in words) \
                or words & set(k.get("match", [])):
            return k
    return None


def kind_min(task, engine_cfg):
    k = kind_of(task, engine_cfg)
    return int(k["minMinutes"]) if k else 0


def effective_minutes(task, engine_cfg):
    if task.get("generic"):
        return int(task["generic"]["minMinutes"])
    """Estimate (or the Play default), raised to the kind's minimum: a game is never a 20 minute thing."""
    base = task.get("estimatedMinutes") or (engine_cfg.get("play") or {}).get("defaultMinutes", 30)
    return max(int(base), kind_min(task, engine_cfg))


def _generic_for(t, engine_cfg):
    """Offer wording for a task: the stand-in itself, or a real item of a kind that has stand-in wording
    (a Play item tagged as a game still reads "a game session, your pick", not "Want 1 h 30 min on Video games")."""
    if t.get("generic"):
        return t["generic"]["text"]
    kind = (kind_of(t, engine_cfg) or {}).get("name")
    for g in (engine_cfg.get("play") or {}).get("generic", []):
        if g["kind"] == kind:
            return g["text"]
    return None


def _kind_allows(t, engine_cfg, light, now):
    """Light-day gate (unless the kind says anyDay) and an optional "before HH:MM" cut-off (golf: daylight)."""
    k = kind_of(t, engine_cfg) or ((t.get("generic") or {}) and next(
        (x for x in (engine_cfg.get("play") or {}).get("kinds", []) if x["name"] == t["generic"]["kind"]), None))
    if not (light or (k or {}).get("anyDay")):
        return False
    before = (k or {}).get("before")
    if before:
        h, m = before.split(":")
        if (now.hour, now.minute) >= (int(h), int(m)):
            return False
    return True


def play_tasks(tasks, engine_cfg, category_for):
    return [t for t in tasks or [] if category_for(t.get("list", ""), engine_cfg, t.get("title", "")).get("play")]


def offer(rec, tasks, state, engine_cfg, category_for, block_phase, now, suggested=None, autos=None):
    """One optional offer or None. Only when idle, the day is light, and no hard deadline is within 24h."""
    if block_phase != "idle" or not rec:
        return None
    light = ((rec.get("dayLoad") or {}).get("level")) == "light"
    cur = rec.get("current")
    if cur and cur.get("band") == "escalated":
        return None
    horizon = now.timestamp() + 24 * 3600
    for e in ([cur] if cur else []) + list(rec.get("queue", [])):
        if e.get("band") in ("escalated", "pinned") or (e.get("dueDate") and datetime.fromisoformat(e["dueDate"]).timestamp() <= horizon):
            return None
    cands = play_tasks(tasks, engine_cfg, category_for)
    cands += [{"id": p["id"], "title": p["title"], "list": "Side Projects", "estimatedMinutes": 60, "notes": "#project"}
              for p in state.get("projects", []) if p.get("state") == "started"]
    # Generic offers (e.g. "a game session") stand in when she has no item of that kind: she picks the game herself.
    for g in (engine_cfg.get("play") or {}).get("generic", []):
        if not any((kind_of(t, engine_cfg) or {}).get("name") == g["kind"] for t in cands):
            cands.append({"id": g["id"], "title": g["title"], "estimatedMinutes": g["minMinutes"], "list": "", "generic": g})
    dl = rec.get("dayLoad") or {}
    left = (dl.get("freeMinutes") or 0) - (dl.get("plannedMinutes") or 0)
    cands = [t for t in cands if effective_minutes(t, engine_cfg) <= left      # must fit what is left of today
             and _kind_allows(t, engine_cfg, light, now)]
    if not cands:
        return None
    rot = lambda i: max((state["leftOff"].get(i) or {}).get("at", ""), state.get("offered", {}).get(i, ""))
    cands.sort(key=lambda t: (rot(t["id"]), bool(t.get("generic")), t.get("title", "")))  # longest untouched first; real beats generic on a tie
    t = cands[0]
    mins = effective_minutes(t, engine_cfg)
    lo = state["leftOff"].get(t["id"])
    auto = (autos or {}).get(t["id"])
    if (kind_of(t, engine_cfg) or {}).get("name") != "project":
        lo = auto = None                          # golf and games never carry a left-off line
    return {"taskId": t["id"], "title": t["title"], "minutes": mins, "kind": (kind_of(t, engine_cfg) or {}).get("name"),
            "leftOff": lo["text"] if lo else auto, "leftOffAuto": bool(not lo and auto),
            "text": (_generic_for(t, engine_cfg).format(m=fmt_dur(mins)) if _generic_for(t, engine_cfg)
                     else f"Want about {fmt_dur(mins)} on {t['title']}? Totally optional.")}


def visible_items(tasks, engine_cfg, category_for):
    """Everything in the Play lists is shown except golf and games, which stay offers-only (Morgan, 2026-11-07).
    A plain task she moved into Play (no kind) is shown too, so a move in QuickToDo is visible in Thalamus."""
    return [t for t in play_tasks(tasks, engine_cfg, category_for) if (kind_of(t, engine_cfg) or {}).get("name") not in ("golf", "game")]


def habit_rows(state, now):
    """One row per daily habit. No streaks and no counts of misses: only whether today's one is done."""
    today = now.date().isoformat()
    wd = now.weekday()
    rows = []
    for h in state.get("habits", []):
        if h.get("until") and h["until"] < today:
            continue                                  # a check-in ends with its due day
        plan = h.get("plan")
        row = {"id": h["id"], "title": h["title"], "notes": h.get("notes", ""), "nudgeAt": h.get("nudgeAt", DEFAULT_NUDGE),
               "days": h.get("days", list(range(7))), "cadence": cadence_label(h.get("days", list(range(7)))), "cluster": h.get("cluster", "play"),
               "dueToday": wd in h.get("days", list(range(7))), "doneToday": today in h.get("doneDates", []),
               "textOnly": bool(h.get("textOnly")), "minutes": h.get("minutes")}
        if plan is not None:
            left = [i for i in plan if not i.get("doneAt")]
            todays = next((i for i in plan if i.get("doneAt") == today), None) if row["doneToday"] else plan_pick(h, today)
            row.update(base=h["title"], planToday=todays["t"] if todays else None, planDone=len(plan) - len(left), planTotal=len(plan),
                       plan=[{"t": i["t"], "done": bool(i.get("doneAt"))} for i in plan])
            if todays:
                row["title"] = f"{h['title']}: {todays['t']}"      # the node and the reminder text name today's item
        if h.get("until"):
            row.update(until=h["until"], startOn=h.get("startOn", today), forTask=h.get("forTask"))
        rows.append(row)
    return rows


def cadence_label(days):
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    d = sorted(days)
    if d == list(range(7)): return "daily"
    if d == [0, 1, 2, 3, 4]: return "weekdays"
    if d == [5, 6]: return "weekends"
    return " · ".join(names[i] for i in d)


def view(state, tasks, engine_cfg, category_for, offer_value, autos=None, now=None):
    """A typed left-off line wins over the automatic one (`leftOffAuto` marks automatic)."""
    autos = autos or {}
    typed = lambda t: (state["leftOff"].get(t["id"]) or {}).get("text")
    line = lambda i, extra: {**extra, "leftOff": typed({"id": i}) or autos.get(i), "leftOffAuto": bool(not typed({"id": i}) and autos.get(i))}
    items = [line(t["id"], {"taskId": t["id"], "title": t["title"], "list": t["list"]}) for t in visible_items(tasks, engine_cfg, category_for)]
    projects = [line(p["id"], {"id": p["id"], "title": p["title"], "state": p["state"], "touchedAt": p.get("touchedAt")})
                for p in state.get("projects", [])]
    habits = [h for h in habit_rows(state, now or datetime.now().astimezone()) if not h["textOnly"]]   # text-only repeats never show as nodes
    return {"items": items, "projects": projects, "habits": habits, "reminders": state.get("reminders", []), "count": len(items) + len(projects) + len(habits),
            "parking": state["parking"], "offer": offer_value, "front": list(state.get("front", []))}
