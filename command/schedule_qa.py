"""Plain-language questions about what is due or left (Phase 17). Plain code, no model, no usage.

`parse(text, config, now)` -> a Question dict or None (None = not a schedule question, use the normal route).
`answer(q, tasks, now)` -> text. Reads the same snapshot tasks the dashboard shows. Contract: command/STATE_MODEL_LOOKUP.md.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
LEAD = re.compile(r"^\s*(?:please\s+|hey\s+|ok\s+|so\s+)?(?:what|whats|what's|when|when's|whens|which|how many|how much|how busy|how's|how does|anything|any\b|"
                  r"do i have|do i need|did i|have i|am i|is there|is anything|is any|are there|list|show|tell me|give me|what do i|i need to know|i want to know|"
                  r"summari[sz]e|recap|rundown of|overview of|walk me through)\b", re.I)
SCHED = re.compile(r"\b(due|deadlines?|overdue|late|missed|miss|behind|owe|left|remaining|coming up|upcoming|on my plate|on deck|assignments?|homework|"
                   r"to do|todo|have to do|need to do|turn in|submit|exams?|tests?|midterms?|finals?|quizzes|quiz|labs?|projects?|still open|"
                   r"haven't (?:i )?(?:done|finished|started|turned in|submitted|handed in)|not (?:done|finished)|my week|the week|on my list|my day|my (?:schedule|plate|agenda)|busy|on track|"
                   r"packed|loaded|"
                   r"(?:should|can|could|do|to) (?:i )?(?:do|work on|get done|have|finish))\b", re.I)
# "what does X look like": about her plan only when X is her day, week or schedule ("what does tomorrow look like").
# "what does a tcp handshake look like for tomorrow's demo" has an outside subject: a question for the router.
_DAY = r"(?:(?:this |next )?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))"
LOOK = re.compile(r"\blook(?:s|ing)?\s+like\b", re.I)
LOOK_Q = re.compile(r"^\s*(?:(?:so|ok|okay|hey)\s+)?(?:what|how)(?:'s|s| does| do| will| would| is| should)\s+(?P<s>[^?]{1,60}?)\s+look(?:s|ing)?\s+like\b(?P<tail>[^?]{0,60})[?.! ]*$", re.I)
LOOK_SUBJ = re.compile(r"(?:it|things|everything|today|tomorrow|tonight|this week|next week|the week|the weekend|this weekend|"
                       r"the rest of (?:the|my|today|this) ?(?:day|week)?|my (?:day|week|weekend|schedule|plate|calendar|agenda|afternoon|morning|evening|night|load|workload)|" + _DAY + r")$", re.I)
LOOK_TAIL = re.compile(r"\s*(?:for (?:me|today|tomorrow|tonight|this week|next week|the week|the weekend|this weekend|" + _DAY + r"))?\s*$", re.I)


def asks_my_look(t):
    m = LOOK_Q.match(t or "")
    return bool(m and LOOK_SUBJ.match(m.group("s").strip()) and LOOK_TAIL.match(m.group("tail")))


TOPICS = [  # (regex, label, matcher on task list/category)
    (r"network security|network sec|\bcis ?8088\b|\b8088\b", "Network Security", ("list", "Network Security")),
    (r"cloud computing|cloud security|\bcloud\b|\baws\b|\bcis ?8087\b|\b8087\b", "Cloud Computing", ("list", "Cloud Computing")),
    (r"internships?|applications?|applying|jobs?\b", "Internships", ("list", "Internships")),
    (r"security projects?|portfolio projects?", "Security Projects", ("list", "Security Projects")),
    (r"\bpersonal\b|errands?", "Personal", ("list", "Personal")),
    (r"school|schoolwork|classes|class\b|homework|coursework|courses?", "school", ("category", "Schoolwork")),
]


def _sod(now):
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _eod(now):
    return _sod(now) + timedelta(days=1) - timedelta(microseconds=1)


def window(text, now):
    """(start, end, label) or None for no window."""
    w = text.lower()
    sod, eod = _sod(now), _eod(now)
    if re.search(r"\btomorrow\b", w):
        return sod + timedelta(days=1), eod + timedelta(days=1), "tomorrow"
    if re.search(r"\b(today|tonight)\b", w):
        return now, eod, "today"
    if re.search(r"\bnext week\b", w):
        mon = sod + timedelta(days=7 - sod.weekday())
        return mon, mon + timedelta(days=7) - timedelta(microseconds=1), "next week"
    if re.search(r"\bthis weekend\b", w):
        sat = sod + timedelta(days=(5 - sod.weekday()) % 7)
        return max(now, sat), sat + timedelta(days=2) - timedelta(microseconds=1), "this weekend"
    if re.search(r"\b(this week|rest of the week|the week|my week)\b", w):
        return now, eod + timedelta(days=6 - sod.weekday()), "this week"
    m = re.search(r"\b(?:in|within|over)\s+(?:the\s+)?next\s+(\d{1,2})\s+days?\b|\bnext\s+(\d{1,2})\s+days?\b|\bin\s+(\d{1,2})\s+days?\b", w)
    if m:
        n = int(next(g for g in m.groups() if g))
        return now, eod + timedelta(days=n), f"in the next {n} days"
    m = re.search(r"\b(by|on|before|for)?\s*(next\s+|this\s+)?(" + "|".join(WEEKDAYS) + r")\b", w)
    if m:
        wd = WEEKDAYS.index(m.group(3))
        delta = (wd - sod.weekday()) % 7
        if m.group(2) and m.group(2).strip() == "next" and delta < 7:
            delta += 7 if delta else 7
        elif delta == 0 and not (m.group(2) or "").strip() == "this":
            delta = 7 if now.hour >= 20 else 0       # "friday" on a Friday = today until late evening
        day = sod + timedelta(days=delta)
        label = day.strftime("%A")
        if m.group(1) == "by" or m.group(1) == "before":
            return now, day + timedelta(days=1) - timedelta(microseconds=1), f"by {label}"
        return day, day + timedelta(days=1) - timedelta(microseconds=1), label
    return None


def parse(text, config=None, now=None, force=False):
    """force=True: the caller already knows this is a question about her schedule (intent.planning_fallback)."""
    t = (text or "").strip()
    if not t or len(t) > 240 or not (force or (LEAD.match(t) and (SCHED.search(t) or asks_my_look(t)))):
        return None
    low = t.lower()
    now = now or datetime.now().astimezone()
    topic = next(((lab, m) for rx, lab, m in TOPICS if re.search(rx, low)), None)
    mode = "list"
    if re.search(r"\boverdue\b|\bmissed\b|\bmiss\b|\bbehind\b|\blate\b|\bforg[eo]t\w*\b|\bcaught up\b", low) and not re.search(r"\bforgetting\b.*\b(?:week|tomorrow|today)\b", low):
        mode = "overdue"
    elif re.search(r"\bhow many\b", low):
        mode = "count"
    elif re.search(r"\b(next|first|soonest|closest|nearest)\s+(deadline|due|thing|one|assignment|exam|test|quiz|lab)\b|\bwhat'?s next due\b|\bwhen'?s my next\b|\bwhen is my next\b", low):
        mode = "next"
    win = window(low, now)
    if not force and not win and mode == "list" and not re.search(r"\b(left|remaining|all|everything|open|on my plate|coming up|upcoming|due|homework|assignments?|haven't|not (?:done|finished)|turn in|turned in|submitted|hand in|submit|on track|the week|on my list|my day|my schedule|my plate|packed|loaded)\b", low):
        return None
    return {"text": t, "topic": topic, "mode": mode, "window": win}


def _matches(task, topic, config):
    if not topic:
        return True
    kind, val = topic[1]
    if kind == "list":
        return task.get("list") == val
    cats = {c["name"]: c for c in (config or {}).get("categories", [])}
    return task.get("list") in (cats.get(val, {}).get("lists") or [])


def _fmt(task, now, parse_dt):
    d = parse_dt(task["dueDate"], now.tzinfo)
    return f"- {d.strftime('%a %b %-d, %-I:%M %p')}: {task['title']} ({task.get('list', '')})"


def answer(q, tasks, config, now, parse_dt):
    label = q["topic"][0] if q["topic"] else None
    where = f" in {label}" if label and label != "school" else (" for school" if label == "school" else "")
    open_dated, undated = [], []
    for t in tasks or []:
        if t.get("completedAt") or not _matches(t, q["topic"], config):
            continue
        (open_dated if t.get("dueDate") else undated).append(t)
    dated = sorted(((parse_dt(t["dueDate"], now.tzinfo), t) for t in open_dated), key=lambda x: x[0])
    past = [(d, t) for d, t in dated if d < now]
    ahead = [(d, t) for d, t in dated if d >= now]
    mode, win = q["mode"], q["window"]

    if mode == "overdue":
        if not past:
            return f"Nothing overdue{where}."
        return "\n".join([f"Overdue{where} ({len(past)}):"] + [_fmt(t, now, parse_dt) for _, t in past[:10]])
    if mode == "next":
        if not ahead:
            return f"Nothing coming up{where}." + (f" ({len(past)} overdue.)" if past else "")
        return "Next due" + where + ":\n" + _fmt(ahead[0][1], now, parse_dt)
    if mode == "count":
        n = len([1 for d, _ in dated if (win[0] <= d <= win[1])]) if win else len(dated)
        span = f" {win[2]}" if win else " open"
        return f"{n} thing{'s' if n != 1 else ''} due{span}{where}." if win else f"{len(dated)} dated and {len(undated)} undated open item{'s' if len(dated) + len(undated) != 1 else ''}{where}."
    if win:
        hits = [(d, t) for d, t in dated if win[0] <= d <= win[1]]
        out = ([f"Due {win[2]}{where} ({len(hits)}):"] + [_fmt(t, now, parse_dt) for _, t in hits]) if hits else [f"Nothing due {win[2]}{where}."]
        later = [(d, t) for d, t in ahead if d > win[1]]
        if not hits and later:
            out.append("Next after that: " + _fmt(later[0][1], now, parse_dt)[2:])
        if past and win[2] in ("today", "this week", "tomorrow") and len(past):
            out.append(f"Missed and still open ({len(past)}), already at the top of the list:")
            out += [f"- {t['title']} ({t.get('list', '')})" for _, t in past[:5]]
        return "\n".join(out)
    # no window: everything still open, soonest first
    if not dated and not undated:
        return f"Nothing open{where}."
    out = [f"Open{where}: {len(dated)} with a deadline" + (f", {len(undated)} without" if undated else "") + "."]
    if past:
        out.append(f"Overdue ({len(past)}):")
        out += [_fmt(t, now, parse_dt) for _, t in past[:5]]
    if ahead:
        out.append("Coming up:")
        out += [_fmt(t, now, parse_dt) for _, t in ahead[:8]]
    return "\n".join(out)
