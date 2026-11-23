"""Plain questions about classes and tests on the calendar ("do I have class today", "when is the midterm").
Plain code from engine/inputs/commitments.json (the class sessions the Sunday scan writes). No model."""
from __future__ import annotations

import re
from datetime import datetime

import schedule_qa

_CLASS = r"(?:class|classes|lecture|lectures|school|session)"
_TEST = r"(?:tests?|exams?|midterms?|finals?|quiz|quizzes)"
_RX = [
    ("class", re.compile(r"^(?:do|did) i (?:have|got)(?: a| any| my)? " + _CLASS + r"\b(?P<rest>.*)$")),
    ("class", re.compile(r"^(?:is|are) there(?: a| any)? " + _CLASS + r"\b(?P<rest>.*)$")),
    ("class", re.compile(r"^(?:when is|when's|when are|what time is|what time's|what time does|when does)(?: my| the)?(?: next| first)? " + _CLASS + r"\b(?P<rest>.*)$")),
    ("class", re.compile(r"^what(?:'s| is| are)?(?: my| the)?(?: next)? " + _CLASS + r"(?: schedule| times?)?\b(?P<rest>.*)$")),
    ("class", re.compile(r"^what " + _CLASS + r" do i have\b(?P<rest>.*)$")),
    ("test", re.compile(r"^(?:when is|when's|when are|what time is|what day is)(?: my| the)?(?: next| first)? " + _TEST + r"\b(?P<rest>.*)$")),
    ("test", re.compile(r"^(?:do i have|is there|are there|have i got)(?: a| an| any| my)? " + _TEST + r"\b(?P<rest>.*)$")),
    ("test", re.compile(r"^(?:any|what) " + _TEST + r"\b(?P<rest>.*)$")),
]
_TEST_LABEL = re.compile(r"\b(test|exam|midterm|mid-term|final|quiz)\b", re.I)


def parse(text):
    """('class'|'test', rest) or None. Text must be normalised; `rest` holds any window words (today, friday...)."""
    t = " ".join((text or "").lower().split()).strip(" ?.!,")
    t = re.sub(r"^(?:(?:ok|okay|so|hey|and|wait)[,\s]+)+", "", t)
    for kind, rx in _RX:
        m = rx.match(t)
        if m:
            return kind, m.group("rest")
    return None


def _fmt(c):
    s, e = c["_s"], c["_e"]
    name = re.sub(r"^Class:\s*", "", c.get("label", "Class"))
    return f"{name}, {s.strftime('%a %b %-d, %-I:%M %p')} to {e.strftime('%-I:%M %p')}"


def answer(q, commitments, now: datetime):
    """Text, or None when the calendar has nothing to say (the caller then falls through to the task list)."""
    kind, rest = q
    items = []
    for c in commitments or []:
        try:
            s, e = datetime.fromisoformat(c["start"]), datetime.fromisoformat(c["end"])
        except (KeyError, ValueError):
            continue
        is_test = bool(_TEST_LABEL.search(c.get("label", "")))
        if (kind == "test") != is_test:
            continue
        if e >= now:
            items.append(dict(c, _s=s, _e=e))
    items.sort(key=lambda c: c["_s"])
    word = "test" if kind == "test" else "class"
    win = schedule_qa.window(rest, now)
    if win:
        hits = [c for c in items if win[0] <= c["_s"] <= win[1] or (c["_s"] <= now <= c["_e"] and win[2] == "today")]
        if hits:
            return "\n".join([f"Yes, {word} {win[2]}:"] + ["- " + _fmt(c) for c in hits])
        if kind == "test" and not items:
            return None
        return f"No {word} {win[2]}." + (f" Next: {_fmt(items[0])}." if items else "")
    if not items:
        return None if kind == "test" else "No classes on the calendar from here on."
    return f"Next {word}: {_fmt(items[0])}." + (f"\nAfter that: {_fmt(items[1])}." if len(items) > 1 else "")
