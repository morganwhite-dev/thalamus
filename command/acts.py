"""Typed pin / unpin / snooze / skip: the same buttons as the Do this now card, said as a sentence.
Plain code, no model; the words are read by typed.parse_action (one parser). Done is deliberately NOT here (a misread must never complete the wrong task)."""
import contextlib
import io
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "engine"))
import typed  # noqa: E402


VERB = {"pin": "pin", "unpin": "unpin", "snooze": "snooze", "skip": "skip"}


def _titles(ts):
    names = [f'"{t}"' for t in ts]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]


def _list_titles(ts):
    names = [f'"{t}"' for t in ts]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def problem_text(ta):
    """One plain sentence for a typed action that must not run (typed.parse_action's "problem")."""
    p, verb = ta["problem"], VERB.get(ta["action"], ta["action"])
    k = p["kind"]
    if k == "none":
        return f"I don't see \"{p['phrase']}\" on your list, so I didn't {verb} anything. Use a few words from its title."
    if k == "ambiguous":
        if p.get("split") and not p.get("options"):
            return (f"That names more than one task: {_list_titles(p['split'])}. I only {verb} one task at a time, so I didn't {verb} anything. "
                    f"Which one?")
        if p.get("split"):
            return (f"Did you mean {_titles(p['options'] + p['split'])}? I only {verb} one task at a time, so I didn't {verb} anything yet. "
                    f"Say it with more of the title.")
        return f"\"{p['phrase']}\" could be {_titles(p['options'])}. Which one? I didn't {verb} anything yet."
    if k == "no_time":
        return "Until when? I didn't snooze anything. Say a time, like snooze until 5pm or snooze for 2 hours."
    if k == "bulk":
        return f"I only {verb} one task at a time from a sentence. Name it, or say {verb} this for the one on the card."
    if k == "past":
        return "That time has already passed, so I didn't snooze anything. Say a later time, like snooze for an hour or snooze until 5pm."
    if k == "bad_time":
        return "I couldn't read that time, so I didn't snooze anything. Try snooze for 2 hours or snooze until 5pm."
    return "I didn't change anything."


def plan_or_problem(text, tasks, current_id=None, now=None):
    """(plan, None) when the sentence is a pin / unpin / snooze / skip that may run; (None, reply) when it is one but must not
    run; (None, None) when it is not one of these. Recognition and arguments come from typed.parse_action (the one parser)."""
    now = now or datetime.now().astimezone()
    ta = typed.parse_action(text, tasks, now)
    if not ta or ta["action"] not in typed.ACTING:
        return None, None
    if ta.get("problem"):
        return None, problem_text(ta)
    kind, args = ta["action"], ta["args"]
    if args.get("all"):
        return None, "I unpin one task at a time from a sentence. Open a pinned task and press Pin to turn it off."
    by_id = {t["id"]: t for t in tasks or []}
    ids = ta.get("task_ids") or ([ta["task_id"]] if ta["task_id"] else [current_id] if current_id else [])
    picked = [by_id[i] for i in ids if i in by_id]
    if not picked:
        return None, f"There's nothing on the Do this now card, so I didn't {VERB[kind]} anything. Say which task, like {VERB[kind]} lab 7."
    plan = {"kind": kind, "tasks": picked, "missing": []}
    if kind == "snooze":
        if "hours" in args:
            plan["hours"] = args["hours"]
        elif args.get("until") == "tomorrow":
            plan["until"] = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
        elif args.get("until"):
            when = datetime.fromisoformat(args["until"])
            if args.get("dateOnly"):
                when = when.replace(hour=9, minute=0)        # a day with no time named comes back at 9 AM
            if when <= now:
                return None, problem_text({"action": "snooze", "problem": {"kind": "past"}})
            plan["until"] = when.strftime("%Y-%m-%dT%H:%M")
            plan["untilLabel"] = when
        else:
            plan["hours"] = 1
    return plan, None


def parse(text, tasks, current_id=None, now=None):
    """None, or {"kind", "tasks": [task], "missing": [], "hours"|"until"} (see plan_or_problem for the reply when it is None)."""
    return plan_or_problem(text, tasks, current_id, now)[0]


def _brain(argv, config=None):
    import brain
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            brain.main(argv + (["--config", config] if isinstance(config, str) else []))
    except SystemExit as e:
        raise ValueError(str(e.code) if e.code else "action failed")


def _list(ts):
    names = [f'"{t["title"]}"' for t in ts]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def execute(plan, config=None, apply=_brain):
    """Apply the plan and return one plain sentence saying what happened."""
    if not plan["tasks"]:
        miss = ", ".join(f'"{m}"' for m in plan["missing"])
        return f"I couldn't match {miss} to one task. Use a few more words from its title, or use Not now on its card."
    kind = plan["kind"]
    for t in plan["tasks"]:
        argv = [kind, t["id"]]
        if kind == "snooze":
            argv += ["--until", plan["until"]] if "until" in plan else ["--hours", f"{plan['hours']:g}"]
        apply(argv, config)
    names = _list(plan["tasks"])
    if kind == "pin":
        out = f"Pinned {names}. It stays on top for today."
    elif kind == "unpin":
        out = f"Unpinned {names}."
    elif kind == "skip":
        out = f"Skipped {names} for today. It comes back tomorrow."
    elif "until" in plan:
        w = plan.get("untilLabel")
        out = f"Snoozed {names} until {w.strftime('%a %b %-d, %-I:%M %p')}." if w else f"Snoozed {names} until tomorrow morning."
    else:
        h = plan["hours"]
        out = f"Snoozed {names} for {h:g} hour{'s' if h != 1 else ''}." if h >= 1 else f"Snoozed {names} for {round(h * 60)} minutes."
    if plan["missing"]:
        out += " I couldn't match " + ", ".join(f'"{m}"' for m in plan["missing"]) + "."
    return out
