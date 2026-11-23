"""Plain-language questions about text reminders (no model): list them, cancel one."""
from __future__ import annotations

import re
from datetime import datetime

LIST_RE = re.compile(r"^\s*(?:what|which|show|list|any)\b.*\b(?:reminders?|reminded)\b|^\s*(?:my )?reminders\??\s*$|\bdo i have (?:any )?reminders?\b|"
                     r"^\s*(?:what|which|any) (?:texts?|pings?|nudges?) (?:are |is |do i have |have i got |am i getting )?(?:scheduled|set|waiting|coming|queued|lined up|going out|planned)\b|"
                     r"^\s*(?:show|list|see|view|check)(?: me)?(?: all)?(?: my| the)? (?:texts?|pings?|nudges?|scheduled texts)\s*$|^\s*what am i (?:getting|being) (?:texts?|pinged|reminded|nudged)(?: about)?\s*$|^\s*(?:are|is) there any (?:reminders?|texts?)\b|"
                     r"^\s*(?:when|what) (?:is|are|'s) (?:my )?next (?:reminder|text|ping|nudge)|\bdo i have any (?:texts?|pings?|nudges?|reminders?)\b", re.I)
CANCEL_RE = re.compile(r"^\s*(?:please )?(?:cancel|delete|remove|clear|forget|drop|stop)\s+(?:the |my |that |all )?(?P<a>(?:\S+ ){0,3}?)(?:reminders?|texts?)\b(?:\s+(?:about|for|to)\b)?\s*(?P<b>.*)$", re.I)


_POLITE = re.compile(r"^(?:please\s+)?(?:can|could|would|will)\s+you\s+(?:please\s+)?", re.I)


def parse(text: str):
    """('list', None) | ('cancel', query) | ('ask_cancel', query) | None. A cancel asked as a question ("cancel reminder to stretch?")
    is 'ask_cancel': the caller shows what would match and drops nothing."""
    import plain
    asked = plain.is_question(text)
    t = plain.request_body(text)            # "can you show me my reminders? 🙏" reads like "show me my reminders"
    m = CANCEL_RE.match(t)
    if m:
        return ("ask_cancel" if asked else "cancel"), (m.group("a") + " " + m.group("b")).strip(" .?!")
    if LIST_RE.search(t) and "remind me" not in t.lower():
        return "list", None
    return None


def fmt(r) -> str:
    try:
        at = datetime.fromisoformat(r["at"])
        return f"{r['text']}  ({at.strftime('%a %-I:%M %p')})"
    except (KeyError, ValueError):
        return r.get("text", "")


_STOP = frozenset(__import__("plain").NAME_STOP | {"reminder", "reminders", "text", "texts", "ping", "nudge"})


def plain_words(query):
    import plain
    return [w for w in plain.words(query) if w not in _STOP]


def pick(reminders, query):
    """The reminders her words name, by plain.match_target (the one matcher): whole words, exact text first.
    An empty or unmatchable query names none of them (never "all of them")."""
    import plain
    kind, val = plain.match_target(query, reminders, title=lambda r: r.get("text", ""), stop=_STOP)
    return [val] if kind == "one" else list(val)


def group_lines(reminders) -> list[str]:
    """One line per reminder (its follow-ups share a group): 'Study  (Tue Nov 17: 9 AM, 1 PM, 5 PM)'."""
    groups, order = {}, []
    for r in reminders:
        g = r.get("group", r.get("id"))
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append(r)
    out = []
    for g in order:
        rs = sorted(groups[g], key=lambda r: r.get("at", ""))
        try:
            ats = [datetime.fromisoformat(r["at"]) for r in rs]
            times = ", ".join(a.strftime("%-I %p") if not a.minute else a.strftime("%-I:%M %p") for a in ats)
            out.append(f"{rs[0]['text']}  ({ats[0].strftime('%a %b %-d')}: {times})")
        except (KeyError, ValueError):
            out.append(rs[0].get("text", ""))
    return out
