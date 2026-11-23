"""Work blocks and the dynamic break loop. Pure state machine plus small file helpers.

    advance(state, action, ctx, config, now) -> (new_state, events)   raises ValueError if illegal
    tick(state, ctx, now, config)            -> (new_state, events)   time / task-completion driven
    view(state, ctx, config, now)            -> dict for the dashboard
    push_view(state)                         -> {id, kind, title, endsAt, ...} | None, for the pusher

`ctx` = {"rec": engine recommendation, "tasks": snapshot tasks or None, "engine": engine config}.
`tasks` is None when the snapshot could not be read; then nothing is ever treated as "done".
No model calls, no network, no writes to QuickToDo. Contract: blocks/STATE_MODEL.md.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "engine"))
sys.path.insert(0, str(HERE.parent / "play"))
import play as play_rules  # noqa: E402
from brain_engine import category_for  # noqa: E402

STATE_PATH = HERE / "state" / "blocks.json"
HISTORY_PATH = HERE / "state" / "history.jsonl"

DEFAULTS = {
    "blockMinMinutes": 10,
    "blockMaxMinutes": 50,
    "extendMinutes": 15,
    "expireHours": 8,
    "startCountdownSeconds": 3,
    "breakMinutes": {"light": 45, "normal": 25, "heavy": 10},
}
ANSWERS = {"yes", "no", "later"}
PHASES = ("idle", "starting", "work", "break", "checkin")


def cfg(config, key):
    return (config or {}).get(key, DEFAULTS[key])


def new_state():
    return {"version": 1, "phase": "idle", "block": None, "suggested": {}, "lastCheckin": None}


# ---------------------------------------------------------------- helpers

def iso(dt):
    return dt.isoformat()


def dt_of(value):
    return datetime.fromisoformat(value)


def rec_entries(rec):
    if not rec:
        return []
    return ([rec["current"]] if rec.get("current") else []) + list(rec.get("queue", []))


def play_names(engine_cfg):
    return {c["name"] for c in (engine_cfg or {}).get("categories", []) if c.get("play")}


def next_block(rec, skip=()):
    """First recommended item outside the Play categories (the engine already keeps Play out; belt and braces)."""
    for e in rec_entries(rec):
        if e.get("category") not in skip:
            return e
    return None


def _entry_from_task(task_id, tasks, engine_cfg):
    """A work-block entry for an open task that is not in the engine's short queue (Morgan picked it herself)."""
    for t in tasks or []:
        if t.get("id") == task_id and not t.get("deletedAt") and not t.get("completedAt"):
            cat = next((c["name"] for c in (engine_cfg or {}).get("categories", []) if t.get("list") in c.get("lists", [])), "Other")
            return {"taskId": t["id"], "title": t.get("title", ""), "category": cat, "minutes": int(t.get("estimatedMinutes") or 30)}
    return None


def is_low(rec):
    return bool(((rec or {}).get("mode") or {}).get("lowEnergy"))


def break_minutes(rec, config):
    level = ((rec or {}).get("dayLoad") or {}).get("level", "normal")
    table = cfg(config, "breakMinutes")
    if is_low(rec):
        table = {**table, **((config or {}).get("lowEnergy") or {}).get("breakMinutes", {})}
    return int(table.get(level, table.get("normal", 25)))


def pick_break_item(tasks, suggested, minutes, engine_cfg, now):
    """A real item from the Play list, or None. Deterministic."""
    today = now.date().isoformat()
    cands = []
    for t in tasks or []:
        if not category_for(t.get("list", ""), engine_cfg, t.get("title", "")).get("play"):
            continue
        s = suggested.get(t["id"], {})
        if s.get("did") and s.get("at", "")[:10] == today:
            continue                      # already did it today
        if play_rules.kind_min(t, engine_cfg) > minutes:
            continue                      # a game or a project does not fit a short break; light-day offers cover those
        est = t.get("estimatedMinutes")
        fits = est is None or est <= minutes
        cands.append((0 if fits else 1, 0 if fits else est, s.get("at", ""), t.get("title", ""), t))
    if not cands:
        return None
    cands.sort(key=lambda c: c[:4])
    t = cands[0][4]
    return {"taskId": t["id"], "title": t["title"], "minutes": t.get("estimatedMinutes")}


def prune_suggested(suggested, tasks, now):
    if tasks is None:
        return suggested
    open_ids = {t["id"] for t in tasks}
    cutoff = iso(now - timedelta(days=14))
    return {k: v for k, v in suggested.items() if k in open_ids or v.get("at", "") >= cutoff}


def make_id(kind, now):
    return f"{kind}-{now.strftime('%Y%m%d%H%M%S')}"


def event(now, type_, **kw):
    return {"at": iso(now), "type": type_, **kw}


def begin(st, at):
    """starting -> work: the clock starts at `at`."""
    b = st["block"]
    st["phase"] = "work"
    b.update(startedAt=iso(at), endsAt=iso(at + timedelta(minutes=b["minutes"])))


# ---------------------------------------------------------------- tick

def tick(state, ctx, now, config=None):
    """Move on anything time or task-completion decided. Idempotent."""
    st = deepcopy(state)
    ev = []
    b = st.get("block")
    if st["phase"] == "idle" or not b:
        return st, ev
    expire = timedelta(hours=cfg(config, "expireHours"))
    ends = dt_of(b["endsAt"])
    if now >= ends + expire:
        ev.append(event(now, "expired", kind=b["kind"], id=b["id"]))
        st.update(phase="idle", block=None)
        if state["phase"] == "checkin":
            st["lastCheckin"] = {"at": iso(now), "answer": "expired"}
        return st, ev
    if st["phase"] == "starting":
        tasks = ctx.get("tasks")
        if tasks is not None and b["taskId"] not in {t["id"] for t in tasks}:
            ev.append(event(now, "work_cancel", id=b["id"], reason="task-done"))     # finished or removed before it began
            st.update(phase="idle", block=None)
            return st, ev
        if now >= dt_of(b["startsAt"]):
            begin(st, dt_of(b["startsAt"]))
            ev.append(event(now, "work_start", id=b["id"], title=b["title"], minutes=b["minutes"], via="countdown"))
    if st["phase"] == "work" and not b.get("overAt"):
        tasks = ctx.get("tasks")
        if tasks is not None and b["taskId"] not in {t["id"] for t in tasks}:
            b.update(overAt=iso(now), overReason="task-done")
            ev.append(event(now, "work_over", id=b["id"], reason="task-done", title=b["title"]))
        elif now >= ends:
            b.update(overAt=iso(ends), overReason="timer")
            ev.append(event(now, "work_over", id=b["id"], reason="timer", title=b["title"]))
    elif st["phase"] == "break" and now >= ends:
        st["phase"] = "checkin"
        b["endedAt"] = b["endsAt"]
        ev.append(event(now, "break_over", id=b["id"], reason="timer"))
    return st, ev


# ---------------------------------------------------------------- advance

def _need(state, *phases):
    if state["phase"] not in phases:
        raise ValueError(f"can't do that while the phase is '{state['phase']}'")


def advance(state, action, ctx, config, now, **args):
    state, ev = tick(state, ctx, now, config)          # settle anything pending first
    st = deepcopy(state)
    rec, tasks, ecfg = ctx.get("rec"), ctx.get("tasks"), ctx.get("engine") or {}
    b = st.get("block")

    if action == "start_work":
        if st["phase"] == "checkin":
            raise ValueError("answer the check-in first (Not now is fine)")
        _need(st, "idle")
        entries = rec_entries(rec)
        want = args.get("taskId")
        pick = next((e for e in entries if e["taskId"] == want), None) if want else next_block(rec, play_names(ctx.get("engine")))
        if want and not pick:
            pick = _entry_from_task(want, tasks, ecfg)      # any open task can be started, not only the recommended five
        if want and not pick:
            raise ValueError("that task isn't open any more")
        if not pick:
            raise ValueError("nothing to start: no eligible task")
        if pick.get("category") in play_names(ctx.get("engine")):
            raise ValueError("Play items are for breaks, not work blocks")
        top = cfg(config, "blockMaxMinutes")
        if is_low(rec):
            top = min(top, int(((config or {}).get("lowEnergy") or {}).get("blockMaxMinutes", top)))
        mins = max(cfg(config, "blockMinMinutes"), min(int(pick.get("minutes") or 30), top))
        lead = int(args["countdown"]) if args.get("countdown") is not None else cfg(config, "startCountdownSeconds")
        if not 0 <= lead <= 1800:
            raise ValueError("countdown must be 0 to 1800 seconds")
        ago = args.get("startedAgo")             # "I forgot to press Start": the clock begins N minutes in the past
        if ago is not None:
            ago = int(ago)
            if not 1 <= ago <= 720:
                raise ValueError("started earlier: 1 to 720 minutes ago")
            lead = 0
        st["phase"] = "starting"
        st["block"] = {"id": make_id("work", now), "kind": "work", "taskId": pick["taskId"], "title": pick["title"],
                       "category": pick.get("category"), "startsAt": iso(now + timedelta(seconds=lead)),
                       "startedAt": None, "endsAt": iso(now + timedelta(seconds=lead, minutes=mins)),
                       "minutes": mins, "ext": 0, "overAt": None, "overReason": None}
        ev.append(event(now, "work_countdown", id=st["block"]["id"], title=pick["title"], seconds=lead))
        if ago:
            at = now - timedelta(minutes=ago)
            st["block"]["startsAt"] = iso(at)
            begin(st, at)
            ev.append(event(now, "work_start", id=st["block"]["id"], title=pick["title"], minutes=mins,
                            via="forgot-to-start", agoMinutes=ago))
        elif lead == 0:
            begin(st, now)
            ev.append(event(now, "work_start", id=st["block"]["id"], title=pick["title"], minutes=mins, via="immediate"))
    elif action == "begin_now":
        _need(st, "starting")
        begin(st, now)
        ev.append(event(now, "work_start", id=b["id"], title=b["title"], minutes=b["minutes"], via="skipped-countdown"))

    elif action == "extend":
        _need(st, "work")
        m = int(args.get("minutes") or cfg(config, "extendMinutes"))
        if not 5 <= m <= 60:
            raise ValueError("extend by 5 to 60 minutes")
        # Already over: the extra time starts now. Still running: it is added to the end.
        new_end = now + timedelta(minutes=m) if b.get("overAt") else dt_of(b["endsAt"]) + timedelta(minutes=m)
        b.update(endsAt=iso(new_end), ext=b.get("ext", 0) + 1, overAt=None, overReason=None, minutes=b["minutes"] + m)
        ev.append(event(now, "work_extend", id=b["id"], minutes=m))

    elif action == "cancel":
        _need(st, "starting", "work")
        ev.append(event(now, "work_cancel", id=b["id"]))
        st.update(phase="idle", block=None)

    elif action == "skip_break":
        _need(st, "work")
        ev.append(event(now, "work_end", id=b["id"], title=b["title"], next="no-break", workedSeconds=elapsed_seconds(b, now)))
        st.update(phase="idle", block=None)

    elif action == "take_break":
        _need(st, "work")
        mins = break_minutes(rec, config)
        item = pick_break_item(tasks, st["suggested"], mins, ecfg, now)
        if item:
            st["suggested"][item["taskId"]] = {"at": iso(now), "did": None}
        ev.append(event(now, "work_end", id=b["id"], title=b["title"], next="break", workedSeconds=elapsed_seconds(b, now)))
        st["phase"] = "break"
        st["block"] = {"id": make_id("break", now), "kind": "break", "workTitle": b["title"], "startedAt": iso(now),
                       "endsAt": iso(now + timedelta(minutes=mins)), "minutes": mins, "suggestion": item,
                       "dayLevel": ((rec or {}).get("dayLoad") or {}).get("level"), "endedAt": None}
        ev.append(event(now, "break_start", id=st["block"]["id"], minutes=mins,
                        suggestion=item["title"] if item else None))

    elif action == "end_break":
        _need(st, "break")
        st["phase"] = "checkin"
        b["endedAt"] = b["endsAt"] = iso(now)       # the pusher sees the real end, not the planned one
        ev.append(event(now, "break_over", id=b["id"], reason="early"))

    elif action == "checkin":
        _need(st, "checkin")
        ans = args.get("answer")
        if ans not in ANSWERS:
            raise ValueError("answer must be yes, no or later")
        sug = b.get("suggestion")
        if ans == "yes" and sug and sug["taskId"] in st["suggested"]:
            st["suggested"][sug["taskId"]]["did"] = True
        st["lastCheckin"] = {"at": iso(now), "answer": ans, "suggestion": sug["title"] if sug else None}
        ev.append(event(now, "checkin", id=b["id"], answer=ans, suggestion=sug["title"] if sug else None))
        st.update(phase="idle", block=None)
        st["suggested"] = prune_suggested(st["suggested"], tasks, now)

    else:
        raise ValueError("unknown block action")
    return st, ev


# ---------------------------------------------------------------- views

def elapsed_seconds(b, now):
    """Time worked so far on a running block (counts on past the planned end until you act)."""
    if not b or not b.get("startedAt"):
        return 0
    return max(0, int((now - dt_of(b["startedAt"])).total_seconds()))


def view(state, ctx, config, now):
    rec = ctx.get("rec")
    out = {"phase": state["phase"], "block": state.get("block"), "lastCheckin": state.get("lastCheckin"),
           "over": bool(state.get("block") and state["phase"] == "work" and state["block"].get("overAt")),
           "next": None, "breakPreview": None}
    out["elapsedSeconds"] = elapsed_seconds(state.get("block"), now) if state["phase"] == "work" else None
    if state["phase"] == "idle":
        out["next"] = next_block(rec, play_names(ctx.get("engine")))
    if state["phase"] == "work":
        out["breakPreview"] = break_minutes(rec, config)
    if state["phase"] == "checkin":
        out["next"] = next_block(rec, play_names(ctx.get("engine")))
    return out


def push_view(state):
    """What the pusher needs: the thing that will end, when, and its id. None when idle."""
    b = (state or {}).get("block")
    if not b or state.get("phase") in ("idle", "starting"):
        return None      # a block that has not begun has nothing to end
    if b["kind"] == "work":
        return {"id": f"{b['id']}.{b.get('ext', 0)}", "kind": "work", "title": b["title"], "endsAt": b["endsAt"]}
    return {"id": b["id"], "kind": "break", "title": (b.get("suggestion") or {}).get("title") or "break",
            "endsAt": b["endsAt"]}


# ---------------------------------------------------------------- files

def write_json_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def load_state(path=None):
    """Returns (state, error). A corrupt file is set aside as .bad and the state resets to idle."""
    path = Path(path or STATE_PATH)
    try:
        st = json.loads(path.read_text())
        if not isinstance(st, dict) or st.get("phase") not in PHASES:
            raise ValueError("unexpected contents")
        base = new_state()
        base.update(st)
        return base, None
    except FileNotFoundError:
        return new_state(), None
    except (OSError, ValueError) as e:
        try:
            os.replace(path, str(path) + ".bad")
        except OSError:
            pass
        return new_state(), f"Block state was unreadable and was reset ({e}). The old file is kept as blocks.json.bad."


def save_state(state, path=None):
    write_json_atomic(path or STATE_PATH, state)


def append_history(events, path=None):
    if not events:
        return
    path = Path(path or HISTORY_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        for e in events:
            f.write(json.dumps(e, sort_keys=True) + "\n")
