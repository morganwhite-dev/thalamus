"""Typed task actions and replies for the chat (no model, no usage). Pure functions; nothing here acts or writes.

`parse_action(text, tasks, now=None)` -> {"action", "task_id", "args"} or None.
    action: done | start | started_earlier | snooze | skip | pin | unpin | stuck | add_time | break | end_break |
            skip_break | cancel_block | low_energy_on | low_energy_off | undo
    task_id: the id of the one open task her words name, or None = the current "do this now" task.
    args: started_earlier {"minutes"}; add_time {"minutes"}; snooze {} (caller picks its default) or {"hours"} or
          {"until": "tomorrow" | iso, "dateOnly": bool}; stuck {"words"}; pin/unpin {"all": True} for "unpin everything".
    problem (pin, unpin, snooze, skip only): {"kind": none|ambiguous|bulk|past|bad_time, "phrase", "options", "split"} when the
          words clearly ask for the action but it must NOT run: the name matches no task or several, "everything", a time in
          the past or a time that can't be read. task_id is then None and the caller replies instead of acting.
Target safety: pin, unpin, snooze and skip act on the "do this now" task only when no object is named or the object is
this / it / that / the current one. A named object must match exactly one task (an exact title wins over partial matches).
`parse_reply(text, pending, now=None)` -> {"kind": yes|no|not_task|edit, ...} or None. `pending` is what the chat last asked:
    {"type": "add", "title", "list", "due", "mode", "lists"}. With no pending question it always returns None, so a bare
    "yes" keeps today's behaviour (a one-line "I don't have a question waiting" from intent.tiny).
Questions never act: "should i snooze this?" and "what did i finish today" return None. Text should be plain.normalize()d
(both functions do it again, which is harmless).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

import capture
import intent
import plain

_QUESTION = re.compile(r"^(?:what if\b|(?:should|shall|what|when|where|why|how|which|who|is|are|was|were|does|did|have|has|will|would|could|can|might|may)\s+"
                       r"(?:i|we|you|it|this|that|there|my|the|any|anything|they|he|she|everything|lab|today)|do\s+(?:i|we|you|they|he|she|there|any|anything|my))\b", re.I)
_REQUEST = re.compile(r"^(?:please\s+)?(?:can|could|would|will)\s+you\b", re.I)
_SELF = r"(?:this|it|that)(?: (?:one|task|thing|assignment))?"
_THIS = re.compile(r"^(?:" + _SELF + r"|the (?:task|thing|assignment|reading|lab|quiz|discussion|homework)|everything|for (?:today|now)|my (?:reading|lab|homework))$")
_NUMW = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
         "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "forty-five": 45, "forty five": 45, "fifty": 50,
         "sixty": 60, "half an": 0.5, "half a": 0.5, "a couple": 2, "a couple of": 2, "couple": 2, "a couple of": 2, "a few": 3, "few": 3}
_NUM = (r"(?P<n>\d{1,4}(?:\.\d{1,2})?|half an?|a couple(?: of)?|couple(?: of)?|a few|few|an?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
        r"fifteen|twenty|thirty|forty-five|forty five|forty|fifty|sixty)")
_UNIT = r"(?P<u>hours?|hrs?|h|minutes?|mins?|m|days?)\b"
_DUR = re.compile(r"\b" + _NUM + r" ?" + _UNIT, re.I)


def _minutes(m):
    w = m.group("n").lower()
    n = _NUMW.get(w, _NUMW.get(w.replace("couple of", "couple"))) if not w[:1].isdigit() else float(w)
    u = m.group("u").lower()
    return int(round(n * (1440 if u.startswith("d") else 60 if u.startswith("h") else 1)))


def _is_question(raw: str) -> bool:
    if plain.is_request(raw):
        return False                         # "hey, could you skip this?" asks me to do it
    if plain.ends_question(raw):
        return True                          # "skip this?!", "skip this? 🙂"
    r = " ".join((raw or "").lower().split())
    return bool(_QUESTION.match(r)) and r not in ("did it", "did that", "did that one")


def _task(phrase, tasks):
    """('this', None) | ('task', task) | ('none', None) for the words after a verb."""
    p = " ".join((phrase or "").split()).strip(" .,!")
    if not p or _THIS.match(p):
        return "this", None
    hit = intent.find_task(p, tasks)
    if hit:
        return "task", hit
    names = _split_names(p)
    if len(names) > 1:
        hits = [intent.find_task(n, tasks) for n in names]
        if all(hits):
            uniq = []
            for h in hits:
                if h not in uniq:
                    uniq.append(h)
            return ("tasks", uniq) if len(uniq) > 1 else ("task", uniq[0])
    return "none", None


_SELF_ONLY = re.compile(r"^(?:" + _SELF + r"|the current (?:one|task)|the one on the card|for (?:today|now)|today|now|right now)$")
_BULK = re.compile(r"^(?:everything(?: (?:today|else|on my list))?|all|all of (?:them|it|these|those|my (?:tasks|stuff|things))|"
                   r"all (?:my |the |of my )?(?:tasks|things|stuff|of them|items)|every (?:task|thing|one|single one)|everything and everyone)$")
_TRAIL = re.compile(r"\s+(?:for today|today|for now|right now|now|first thing|for the day|please)$")
ACTING = ("pin", "unpin", "snooze", "skip")


def _words(s):
    return plain.words(s)


def _exact(phrase, task):
    want = _words(phrase)
    return bool(want) and _words(task["title"]) in (want, want[1:] if want[0] in ("the", "my") else want)


def _one(phrase, tasks):
    """(kind, value, exact) for one name: ('task', task, exact?) | ('ambiguous', [tasks], False) | ('none', [], False).
    The choice is plain.match_target's (the one matcher every writer uses)."""
    kind, val = plain.match_target(phrase, tasks)
    if kind == "one":
        return "task", val, _exact(phrase, val)
    return ("ambiguous", val, False) if kind == "many" else ("none", [], False)


def _same_title(kind, val, phrase):
    """True when plain.match_target found several tasks and at least one carries exactly the title her words spell out."""
    return kind == "ambiguous" and any(_exact(phrase, x) for x in val)


def _target(phrase, tasks):
    """Strict reading of the words after pin / unpin / snooze / skip.
    -> ('this', None) | ('task', task) | ('tasks', [tasks]) | ('ambiguous', {"options", "split"}) | ('bulk', None) | ('none', None)."""
    p = " ".join((phrase or "").lower().split()).strip(" .,!?")
    kind, val, exact = _one(p, tasks)
    if kind == "task" and exact:
        return "task", val                       # "Submit homework today" is a title: checked before "today" is dropped
    if _same_title(kind, val, p):
        return "ambiguous", {"options": val, "split": None}      # two open tasks with this exact title: ask, never pick one
    p = _TRAIL.sub("", p).strip(" .,!?") if p not in ("for today", "for now", "right now") else p
    if not p or _SELF_ONLY.match(p):
        return "this", None
    if _BULK.match(p):
        return "bulk", None
    kind, val, exact = _one(p, tasks)
    if kind == "task" and exact:
        return "task", val                       # the whole phrase IS a title: it wins over any other reading
    if _same_title(kind, val, p):
        return "ambiguous", {"options": val, "split": None}
    names = _split_names(p)
    split = None
    if len(names) > 1:
        parts = [_one(n, tasks) for n in names]
        if all(k == "task" for k, _, _ in parts):
            split = []
            for _, t, _ in parts:
                if t not in split:
                    split.append(t)
        elif kind == "none":
            opts = [t for k, v, _ in parts if k == "ambiguous" for t in v]
            return ("ambiguous", {"options": opts, "split": None}) if opts else ("none", None)
    if split and len(split) > 1:                 # several tasks named: one action never runs on more than one task, so ask
        whole = [] if kind == "none" else [val] if kind == "task" else list(val)
        return "ambiguous", {"options": whole, "split": split}
    if split and kind == "none":
        return "task", split[0]
    if kind == "task":
        return "task", val
    if kind == "ambiguous":
        return "ambiguous", {"options": val, "split": None}
    return "none", None


_STATEMENT = re.compile(r"\b(?:not|isn't|isnt|doesn't|doesnt|won't|wont|didn't|broken|working|works|worked|is|are|was|were|keeps?|seems?)\b")


def _act(action, phrase, tasks, explicit=True, **args):
    """The action on the task her words name, a problem reply, or None (soft wording that named nothing of hers)."""
    kind, val = _target(phrase, tasks)
    if kind == "this":
        return _out(action, **args)
    if kind in ("task", "tasks"):
        return _out(action, val, **args)
    p = " ".join((phrase or "").split()).strip(" .,!?")
    wordless = bool(p) and not plain.words(p)        # emoji or marks where a name goes: an object that cannot match, so ask
    if kind == "none" and not wordless and (not explicit or _STATEMENT.search(phrase or "")):
        return None                          # "snooze button not working": a remark about the app, not a task name
    prob = {"kind": kind, "phrase": p}
    if kind == "ambiguous":
        prob["options"] = [t["title"] for t in val["options"]][:5]
        prob["split"] = [t["title"] for t in val["split"]] if val.get("split") else None
    return _problem(action, **prob)


def _problem(action, **prob):
    return {"action": action, "task_id": None, "args": {}, "problem": prob}


def _out(action, tk=None, **args):
    if isinstance(tk, list):                 # "read chapter 5 and 6": several tasks (pin, unpin, skip, snooze only)
        out = {"action": action, "task_id": tk[0]["id"], "args": args}
        out["task_ids"] = [t["id"] for t in tk]
        return out
    return {"action": action, "task_id": (tk or {}).get("id"), "args": args}


def _split_names(x):
    parts = [p.strip() for p in re.split(r",|\band\b|&", x) if p.strip()]
    out, prefix = [], ""
    for p in parts:
        if re.fullmatch(r"\d+", p) and prefix:
            out.append(prefix + " " + p)          # "chapter 5 and 6" -> "chapter 5", "chapter 6"
            continue
        out.append(p)
        prefix = re.sub(r"\s*\d+\s*$", "", p).strip()
    return out


def _clean(raw):
    t = intent.clean(plain.strip_tail(plain.strip_lead(plain.normalize((raw or "").strip())), fluff=False))   # "skip this? 🙏" -> "skip this"
    t = re.sub(r"\bun[- ]pin", "unpin", t)
    return re.sub(r"\s+(?:for me|thanks|ty)$", "", t).strip()


# ----------------------------------------------------------------------------------------- small pieces
_UNDO = re.compile(r"^(?:oops[, ]*)?(?:undo(?: (?:that|it|this|the last (?:thing|one)|what i just did))?|take (?:that|it) back|revert(?: that| it)?|"
                   r"put (?:it|that) back|reopen (?:it|that|that one)|bring (?:it|that) back|scratch that|whoops(?: undo)?|"
                   r"(?:i )?didn't mean to(?: do that| press that)?|my bad(?:,? undo)?|never ?mind(?: that| it)?)$")
_LOW_ON = re.compile(r"^(?:low energy(?: mode| day)?|turn on low energy(?: mode)?|low energy on|(?:i'm|i feel|feeling|im) (?:so |really |too |super |kinda |kind of )?"
                     r"(?:tired|exhausted|drained|wiped|fried|burnt out|burned out|sick|awful|beat|worn out|fried)(?: today| right now| tonight)?|"
                     r"not feeling (?:it|well|good|great)(?: today| right now)?|rough day|(?:i have|i've got|got) no energy(?: today)?|no energy(?: today)?|"
                     r"(?:let's |lets |can we )?(?:go|take it) easy(?: on me)?(?: today)?|easy day|go easy on me|take it easy today)$")
_LOW_OFF = re.compile(r"^(?:turn off low energy(?: mode)?|low energy off|(?:i'm|im|i am) (?:good|ok|okay|fine|awake|better|back to normal) (?:now|again)|"
                      r"(?:i'm|im|i am) (?:feeling )?better|(?:i )?feel better(?: now)?|feeling better(?: now)?|(?:my )?energy(?:'s| is) back|"
                      r"normal mode|back to normal|full energy|(?:i )?have energy (?:now|again))$")
_BREAK_END = re.compile(r"^(?:end (?:the |my )?break|stop (?:the |my )?break|(?:the |my )?break(?:'s| is| has)? (?:over|done|up|finished)|"
                        r"i'?m back|im back|back to work|(?:i'm |i am )?(?:done|finished) with (?:the |my )?break|(?:i )?(?:finished|ended) (?:the |my )?break|"
                        r"break over|break ended|time(?:'s| is) up on (?:the |my )?break|ready to work again)$")
_BREAK_SKIP = re.compile(r"^(?:skip (?:the |my )?break|no break|no break needed|i don't need a break|don't need a break|(?:no|skip) break(?: today)?)$")
_BREAK = re.compile(r"^(?:(?:let's |lets |i'll |i will |i'm going to |going to |imma |gonna |i'm gonna |i'm about to )?take a (?:quick |short |little )?break|"
                    r"(?:i )?(?:need|want|could use) (?:a|some) (?:quick |short |little )?(?:break|breather|rest)|break(?: time| please)?|"
                    r"time for a break|(?:i'm|i am) taking a (?:quick |short )?break|pause(?: (?:the timer|it|the block))?|stop(?: here| for now| it| working| the timer| timer)?|i need to stop|i have to stop|i gotta stop|take a breather|"
                    r"(?:done|finished)[,:]? take a break|brb|give me a break)$")
_CANCEL = re.compile(r"^(?:cancel|abort|scrap|stop|end|kill|forget) (?:the |this |my )?(?:work )?(?:block|timer|session|clock)(?: please)?$|^i didn't (?:actually )?start$")
_ADD_TIME = [re.compile(p) for p in (
    r"^(?:add|extend|give me|i need|need|plus|tack on|add on|can i have|let me have)(?: the block by| it by| this by| by)? ?(?:another |some |an extra |an additional )?" + _NUM + r" ?(?:more |extra )?" + _UNIT + r"(?: more| extra| longer)?$",
    r"^" + _NUM + r" ?(?:more |extra )?" + _UNIT + r"(?: more| extra| longer)?$", r"^(?:plus|add|\+) (?P<bare>\d{1,3})$",
    r"^(?:another|an extra|plus) " + _NUM + r" ?" + _UNIT + r"$",
    r"^(?:i need |can i have |give me |let me have )?(?:more|some more|a little more|a bit more|extra) time$",
    r"^(?:extend|add time to) (?:it|the block|this|the timer)$", r"^add (?:some )?time$",
)]
_SINCE = re.compile(r"\b(?:started|began|forgot to start|forgot to hit start|(?:been|have been) (?:working|at it|on it|on this))\b")
_START_BARE = re.compile(r"^(?:ok |okay )?(?:start|begin|go|ready|i'm ready|let's go|lets go|let's start|let's begin|let's do it|lets do it|let's get started|let's get going|"
                         r"start (?:it|now|working|the timer|the block|a block|the clock|a timer)|start the (?:work )?block|"
                         r"(?:i'm |i am )?(?:starting|beginning)(?: it| this| now| right now)?|(?:i'll|i will|i'm going to|i'm gonna|i'm about to) (?:start|begin)(?: now| it)?|"
                         r"time to (?:start|begin|work|get started)|here we go|go time|ok go|get started|get going)$")
_START_X = re.compile(r"^(?:ok |okay )?(?:(?:i'm |i am |im )?(?:starting|beginning)|start(?: working on| on)?|begin(?: working on| on)?|let's (?:do|start|begin|work on)|lets (?:do|start|begin|work on)|"
                      r"(?:i'll|i will|i'm going to|i'm gonna|i'm about to) (?:start|begin|work on)|work on|time to (?:start|do|work on)|go (?:do|work on)|get started on|get going on) (?P<x>.+)$")
_DONE_BARE = re.compile(r"^(?:ok |okay )?(?:done!?|done for now|done for today|all done|all finished|finished(?: it| that| up| that up)?|(?:i'm|i am|im) (?:done|finished)|i did it|did it|did that(?: one)?|"
                        r"knocked it out|wrapped it up|nailed it|crushed it|got it done|got that done|it's done|its done|that's done|that one's done|task done|"
                        r"completed(?: it)?|complete(?: it)?|mark (?:it|this|that) (?:as )?(?:done|complete|completed|finished)|mark (?:as )?(?:done|complete|completed)|"
                        r"(?:i )?(?:just )?(?:finished|completed|did) (?:it|that|this)|check (?:it|that) off|cross (?:it|that) off|tick (?:it|that) off|i'm done with (?:it|this|that)|done with (?:it|this|that)|just did it|just finished|all set)$")
_DONE_X = [re.compile(p) for p in (
    r"^(?:mark|check off|tick off|cross off|set|complete|finish) (?P<x>.+?)(?: as)?(?: done| complete| completed| finished| off)?$",
    r"^(?P<x>.+?) (?:is|'s|are) (?:all )?(?:done|finished|complete|completed)$",
    r"^(?:i'm |i am |i have |i've |i |we )?(?:just )?(?:finished|completed|did|done with|got through|knocked out|wrapped up|got done with|crushed|nailed|handled|cleared) (?P<x>.+)$",
    r"^(?:done|finished) with (?P<x>.+)$",
)]
_SKIP_BARE = re.compile(r"^(?:skip(?: " + _SELF + r")?|not this one|not this|something else|give me something else|show me something else|pick something else|swap (?:it|this)|"
                        r"next one please|i don't want to do (?:this|that)(?: one)?|i don't wanna do (?:this|that)(?: one)?|different one|another one|do something else|"
                        r"i'm not doing (?:this|that)|nope,? something else)$")
_PIN_BARE = re.compile(r"^(?:pin(?: " + _SELF + r")?|keep (?:this|it) on top|do (?:this|it|this one) first(?: today)?|do (?:this|it|this one) first thing|put (?:this|it) at the top|move (?:this|it) to the top|"
                       r"make (?:this|it) (?:my |the )?(?:top |first |number one )?priority|focus on (?:this|it) today|this (?:one )?(?:first|is first|goes first)(?: today)?|"
                       r"(?:this|it) (?:is|'s) the priority)$")
_PIN_X = [re.compile(p) for p in (
    r"^pin (?P<x>.+)$", r"^(?:do|put|move|bring|push|get|jump) (?P<x>.+?) (?:first(?: today)?|to the (?:very )?top|up to the top)$",
    r"^(?:move|put|bring|push|get|jump|shove) (?P<x>.+?) (?:up )?(?:to )?(?:the )?(?:very )?(?:top|front)(?: of (?:the |my )?(?:list|queue|line|pile))?(?: for today| today)?$",
    r"^(?:move|bring|put|push|get) (?P<x>.+?) up$",
    r"^(?:make|set) (?P<x>.+?) (?:my |the )?(?:top |first |number one |#1 )?priority$", r"^(?:keep|put) (?P<x>.+?) on top$", r"^focus on (?P<x>.+?) today$")]
_UNPIN = re.compile(r"^(?:unpin(?: (?P<x>.+))?|take (?:it|that|this) off the top|remove (?:the|that) pin|stop pinning(?: (?:it|this))?|unpin (?:it|this|that))$")
_SKIP_X = [re.compile(p) for p in (r"^skip (?P<x>.+)$", r"^not (?P<x>.+?)(?: today| right now)?$", r"^(?:i )?(?:don't|do not) want to do (?P<x>.+)$", r"^(?:swap out|drop) (?P<x>.+)$")]
_LATER = re.compile(r"^(?:not now|not right now|later(?: today)?|maybe later|can't(?: do (?:it|this))? right now|can't right now|not yet|remind me later|come back to (?:this|it) later|"
                    r"bug me later|ask me later|hit me up later|ask me again later|put (?:it|this) off|not feeling (?:this|it) right now|give me (?:a bit|a minute|some time))$")
_SNOOZE_VERB = re.compile(r"^(?:snooze|push|postpone|delay|put off|defer|bump|hold off on|move|reschedule)\b(?: (?P<rest>.*))?$")
_SNOOZE_AGAIN = re.compile(r"^(?:remind me(?: about (?:it|this|that))?(?: again)?|ask me again|check back|check in again|bug me|hit me up|come back to (?:this|it)|nudge me(?: again)?|ping me(?: again)?|"
                           r"circle back)\s+(?:in|after|at|around)\s+(?P<rest>.+)$")


def _snooze_args(rest, now):
    """(args, leftover words) from 'for an hour', 'till 5pm', 'to tomorrow', 'in 2 hours'."""
    r = " ".join((rest or "").split())
    m = _DUR.search(r)
    if m and not re.search(r"\bago\b", r[m.end():m.end() + 6]):
        hrs = round(_minutes(m) / 60, 2)
        if 0 < hrs <= 14 * 24:
            left = (r[:m.start()] + " " + r[m.end():]).strip()
            return {"hours": hrs}, re.sub(r"\b(?:for|in|about|around|another|after|by)\s*$", "", left).strip()
    if re.search(r"\b(?:tomorrow|tmrw)\b", r) and not capture._time_of(r):
        left = re.sub(r"\b(?:(?:until|till|til|to|for|on|by)\s+)?(?:tomorrow|tmrw)(?: morning)?\b", " ", r)
        return {"until": "tomorrow"}, left.strip()
    if re.search(r"\b(?:tonight|this evening)\b", r):
        tm = capture._time_of(r)
        if tm:
            due = now.replace(hour=tm[0], minute=tm[1], second=0, microsecond=0)
            left = r.replace(tm[2], " ", 1) if tm[2] in r else r
        else:
            due = next((c for c in (now.replace(hour=h, minute=0, second=0, microsecond=0) for h in (18, 21)) if c > now), None)
            left = r
        if due is None or due <= now:
            return {}, r                         # tonight has no future time left: never snooze into the past
        left = re.sub(r"\b(?:(?:until|till|til|to|for|at|by)\s+)?(?:tonight|this evening)\b", " ", left)
        left = re.sub(r"\b(?:until|till|til|to|for|at|by)\s*$", "", left.strip()).strip()
        return {"until": due.isoformat(timespec="minutes")}, left
    due, left = capture.parse_due(r, now)
    if due:
        date_only = not capture._time_of(r)
        left = re.sub(r"\b(?:until|till|til|to|for|by|at|on)\s*$", "", left.strip()).strip()
        return {"until": due, "dateOnly": date_only}, left
    return {}, r


_BAD_WHEN = re.compile(r"\b(?:until|till|til|for|in|to|at|by)\s+\S*\d|\d{1,2}:\d{2}|\d ?(?:am|pm)\b")
_DANGLING = re.compile(r"(?:^|\s)(?:until|till|til|for|by|at|to|on|in|within|around|before|after)(?:\s+(?:the|a|an|my|this|that|next))*$")   # a time word with no time after it
_TIME_CONN = re.compile(r"\b(?:until|till|til|within|around|before|after)\b")      # a time connector with words after it that were not a time
_SNOOZE_EXPLICIT = ("snooze", "postpone", "defer", "delay", "put")       # "put off": a snooze whatever follows


def _when_problem(args, now):
    """'past' when the snooze would end at or before now, else None."""
    if "hours" in args:
        return None if args["hours"] > 0 else "past"
    u = args.get("until")
    if not u or u == "tomorrow":
        return None
    when = datetime.fromisoformat(u)
    if args.get("dateOnly"):
        when = when.replace(hour=9, minute=0)               # a day with no time named means 9 AM (acts.parse does the same)
    return "past" if when <= now else None


def _snooze(t, tasks, now):
    if _LATER.match(t):
        return _out("snooze")
    m = _SNOOZE_AGAIN.match(t)
    if m:
        args, left = _snooze_args(m.group("rest"), now)
        if args and not left.strip(" .,"):
            bad = _when_problem(args, now)
            return _problem("snooze", kind=bad, phrase=m.group("rest")) if bad else _out("snooze", **args)
        return None
    t = re.sub(r"^put ([a-z0-9 ]+?) off (?=till|until|to|for|until)", r"put off \1 ", t)
    m = _SNOOZE_VERB.match(t)
    if not m:
        return None
    rest = m.group("rest") or ""
    verb = t.split()[0]
    explicit = verb in _SNOOZE_EXPLICIT
    if verb in ("move", "reschedule") and not re.search(r"\b(?:to|till|until|til|by)\b", rest):
        return None
    rest_c = " ".join(rest.split()).strip(" .,!?")
    if explicit and rest_c and not _SELF_ONLY.match(rest_c):
        k, whole, exact = _one(rest_c, tasks)
        if k == "task" and exact:
            return _out("snooze", whole)             # "snooze Lab 7 Friday" when "Lab 7 Friday" is a task: the full title wins
        if _same_title(k, whole, rest_c):
            return _problem("snooze", kind="ambiguous", phrase=rest_c, options=[t["title"] for t in whole][:5], split=None)
    else:
        k, whole = None, None
    args, left = _snooze_args(re.sub(r"\b(?:to|until|till|til)\b(?= (?:tomorrow|tmrw|\d|noon|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday))", "till", rest), now)
    if not args and explicit and re.match(r"(?:until|till|til|to|for)\s+(?:tonight|this evening)\b", left.strip(" .,!?")):
        return _problem("snooze", kind="past", phrase=rest)       # tonight has no time left
    if not args and _BAD_WHEN.search(left):
        return _problem("snooze", kind="bad_time", phrase=rest) if explicit else None   # "until 5:99pm", "for 99999 hours"
    if verb in ("push", "move", "bump", "reschedule") and not args:
        return None                     # "push lab 7" with no when is not a snooze
    bad = _when_problem(args, now)
    if bad:
        return _problem("snooze", kind=bad, phrase=rest) if explicit or args else None
    if not args and explicit and (_DANGLING.search(left.strip(" .,!?")) or _TIME_CONN.search(left)):
        return _problem("snooze", kind="no_time", phrase=rest)      # "snooze lab 7 in", "snooze this to", "snooze until sunrise": a time word with no time: ask
    target = re.sub(r"\b(?:for|to|until|till|til|by|at|on)\s*$", "", left).strip()
    out = _act("snooze", target, tasks, explicit=explicit, **args)
    if args and k == "task" and out and not out.get("problem") and out.get("task_id") and out["task_id"] != whole["id"]:
        # "snooze lab 7 friday": "Lab 7 Friday prep" (whole words) or "Lab 7" until Friday? Truly two readings: ask
        other = next((x for x in tasks if x["id"] == out["task_id"]), {})
        return _problem("snooze", kind="ambiguous", phrase=rest_c, options=[whole["title"], other.get("title", "")], split=None)
    return out


# every verb that names a task to act on, by what it does (the object after it is read by _target, never skipped)
_ACT_VERB = re.compile(r"^(?:(?P<pin>pin)|(?P<unpin>un[- ]?pin)|(?P<skip>skip|swap out|drop|not|i don't want to do)|"
                       r"(?P<snooze>snooze|postpone|delay|defer|put off|hold off on|bump))\b(?P<x>.*)$", re.I)


def parse_action(text, tasks, now=None):
    now = now or datetime.now().astimezone()
    raw = (text or "").strip()
    if not raw or len(raw) > 160 or "\n" in raw or _is_question(raw):
        return None
    t = _clean(raw).strip(" .!,")
    if not t:
        return None
    m = _ACT_VERB.match(intent.clean(plain.strip_lead(plain.normalize(raw))))
    if m:                                    # "pin 🛒", "un-pin 🛒", "postpone 🛒": emoji or marks where a name goes is an unmatchable name, not "this"
        extra = m.group("x").strip(" .,!?")
        if extra and not plain.words(extra):
            return _problem(next(k for k in ("pin", "unpin", "skip", "snooze") if m.group(k)), kind="none", phrase=extra)
    if _UNDO.match(t):
        return _out("undo")
    if _LOW_OFF.match(t):
        return _out("low_energy_off")
    if _LOW_ON.match(t):
        return _out("low_energy_on")
    if _BREAK_SKIP.match(t):
        return _out("skip_break")
    if _BREAK_END.match(t):
        return _out("end_break")
    if _CANCEL.match(t):
        return _out("cancel_block")
    for rx in _ADD_TIME:
        m = rx.match(t)
        if m:
            mins = int(m.group("bare")) if m.groupdict().get("bare") else _minutes(m) if m.groupdict().get("n") else 15
            return _out("add_time", minutes=mins) if 1 <= mins <= 240 else None
    m = _SINCE.search(t)
    if m and _DUR.search(t):
        mm = _DUR.search(t)
        if mm:
            mins = _minutes(mm)
            if 1 <= mins <= 720:
                x = re.sub(r"\b(?:i |i've |ive |we )?(?:started|began|have been working on|been working on|been working|have been at|been at|forgot to start|forgot to hit start)\b|\bfor\b|\bago\b|[.,]", " ", (t[:mm.start()] + " " + t[mm.end():]))
                x = re.sub(r"\b(?:it|this|that|working|at|on|and|i|about|around)\b", " ", x)
                kind, tk = _task(x, tasks)
                if kind in ("this", "task"):
                    return _out("started_earlier", tk, minutes=mins)
        return None
    if _BREAK.match(t):
        return _out("break")
    if _START_BARE.match(t):
        return _out("start")
    m = _START_X.match(t)
    if m:
        kind, tk = _task(m.group("x"), tasks)
        if kind == "task":
            return _out("start", tk)
        if kind == "this":
            return _out("start")
    if _DONE_BARE.match(t):
        return _out("done")
    for rx in _DONE_X:
        m = rx.match(t)
        if m:
            kind, tk = _task(m.group("x"), tasks)
            if kind == "task":
                return _out("done", tk)
            if kind == "this" and not re.fullmatch(r"everything|for (?:today|now)", m.group("x").strip()):
                return _out("done")
    m = _UNPIN.match(t)
    if m:
        x = (m.groupdict().get("x") or "").strip()
        if x in ("all", "everything", "all of them", "all my tasks"):
            return _out("unpin", all=True)
        return _act("unpin", x, tasks)
    if _PIN_BARE.match(t):
        return _out("pin")
    for i, rx in enumerate(_PIN_X):
        m = rx.match(t)
        if m:
            got = _act("pin", m.group("x"), tasks, explicit=(i == 0))      # "pin X" names a task; "do X first" may not
            if got:
                return got
    if _SKIP_BARE.match(t):
        return _out("skip")
    sn = _snooze(t, tasks, now)
    if sn:
        return sn
    for i, rx in enumerate(_SKIP_X):
        m = rx.match(t)
        if m:
            got = _act("skip", m.group("x"), tasks, explicit=(i == 0))
            if got:
                return got
    st = intent.stuck_request(t, tasks)
    if st:
        return _out("stuck", st[0], words=st[1])
    return None


_ASK_LEAD = re.compile(r"^(?:(?:wait|oh|hmm+|ok|okay|so|um|uh|hey|actually)[, ]+)*(?:should i|shall i|can i|could i|what if i|maybe i should|"
                       r"is it ok (?:if i|to)|would it be ok (?:if i|to))?\s*")


def question_offer(text, tasks, now=None):
    """A reply for an action asked as a question ("skip this?", "should i snooze this?", "what if i skip lab 7"), else None.
    It never acts: it says how to ask for it plainly."""
    raw = plain.squash(text)
    r = raw.lower()
    if not raw or len(raw) > 160 or plain.is_request(raw) or not _is_question(raw):
        return None
    bare_q = plain.strip_question(r)
    core = _ASK_LEAD.sub("", bare_q, count=1).strip()
    if not core or core == bare_q:
        if not plain.ends_question(r):
            return None                      # "is this pinned" with no "?" is left for the other rules
    ta = parse_action(core, tasks, now)
    if not ta or ta.get("problem") or ta["action"] not in ACTING:
        return None                          # "should i take a break?" is advice: it keeps going to the normal route
    return f'Sounds like a question, so I left it alone. If you want me to do it, say "{core}".'


# ----------------------------------------------------------------------------------------- replies
_YES2 = re.compile(r"^(?:yes|yeah|yea|yep|yup|ya|sure|ok|okay|k|kk)(?:[, ]+(?:please|do it|add it|save it|go ahead|thanks|that's right|that works|sounds good|sure|perfect|looks good|for sure|thing))+$")
_YES = re.compile(r"^(?:yes|yeah|yea|yep|yup|ya|sure|ok|okay|k|kk|absolutely|definitely|correct|right|fine|good|great|perfect|confirm|affirmative|bet|"
                  r"sounds good|looks good|looks right|that's right|that's correct|that works|works for me|go ahead|go for it|do it|add it|save it|yes please|"
                  r"sure thing|for sure|please do|yes add it|yep add it|ok add it|okay add it|yes do it|ok do it|okay do it|yeah add it|yeah do it|yes that's right|"
                  r"yes sounds good|ok sounds good|okay sounds good|yeah sure|sure add it|sure do it|sounds right|good to go|ship it|make it so|👍)$")
_NO = re.compile(r"^(?:no|nope|nah|naw|cancel|don't|dont|do not|never ?mind|nvm|forget it|skip it|no thanks|no thank you|nope cancel|no cancel|stop|scratch that|"
                 r"don't add it|dont add it|do not add it|not that|no don't|leave it|drop it|ignore that|i changed my mind|changed my mind|cancel that|cancel it|"
                 r"no don't add it|never mind that|nah forget it|nope forget it|no thanks cancel|not now|not right now)$")
_NOT_TASK = re.compile(r"^(?:no,? )?(?:not a task|that's not a task|thats not a task|it's not a task|it's a question|that's a question|just a question|i was asking|i'm asking|"
                       r"just asking|that was a question|it was a question|i'm just asking|ask it instead|answer it instead|that wasn't a task|not a reminder|ask instead)$")
_TEXT_ONLY = re.compile(r"\b(?:text me instead|just text me|make it a text|text only|only text me|reminder only|just a reminder|as a text|send (?:it )?as a text|just remind me|"
                        r"make it a reminder|text me not a task|a text instead|make that a text)\b")
_ALSO_TEXT = re.compile(r"\b(?:also text me|text me too|and text me|and remind me|also remind me|plus a text|text me about it too|with texts?|and nudge me|and text me about it)\b")
_TASK_ONLY = re.compile(r"\b(?:make it a task|a task instead|just a task|task only|no texts?|don't text me|dont text me|without (?:a )?texts?|no reminder|no nudges?|make it a task not a text)\b")
_NO_DATE = re.compile(r"\b(?:no (?:due )?date|no deadline|without a (?:due )?date|no due date|remove (?:the )?(?:due )?date|drop (?:the )?(?:due )?date|undated|whenever|any ?time|clear (?:the )?(?:due )?date|no time)\b")
_TITLE = [re.compile(p, re.I) for p in (
    r"^(?:call|name|title|label|rename) (?:it|this|that)(?: to| as)?:? (?P<t>.+)$", r"^(?:change|set|make) (?:the )?(?:title|name)(?: of (?:it|this))? (?:to|as|:)\s*(?P<t>.+)$",
    r"^(?:make|let) (?:it|this) (?:say|read) (?P<t>.+)$", r"^(?:it|this) should (?:say|be called|read) (?P<t>.+)$", r"^(?:title|name):\s*(?P<t>.+)$",
    r"^rename (?:it )?(?:to )(?P<t>.+)$", r"^(?:actually,? )?(?:it'?s|its) called (?P<t>.+)$", r"^(?:no,? )?(?:it should be|make that|change it to) (?:called |titled |named )?[\"“](?P<t>[^\"”]+)[\"”]$",
)]
_DATE_FILLER = set("""make it change to due by on for how about what actually instead can you please the date time move set push at is be let's say lets
just no but then a an and my that this one day i want i'd like need needs should could would put it's its that's maybe or""".split())
_LIST_ALIASES = [
    (r"\b(?:personal|errands?|life admin|adulting)\b", "Personal"), (r"\b(?:play|playground|fun|side projects?|games?)\b", "Play"),
    (r"\binternships?\b", "Internships"), (r"\bsecurity projects?\b", "Security Projects"), (r"\bsecurity\b", "Security Projects"),
    (r"\bcloud(?: computing)?\b", "Cloud Computing"), (r"\bnetwork(?: security)?\b", "Network Security"),
]
_LIST_WORDS = re.compile(r"\b(?:in|into|to|under|for|as|list|it's|its|put|file|move|goes|go|belongs|thing|stuff|not|school|schoolwork|class|homework|personal|errands?|play|playground|fun|internships?|security projects?|security|cloud(?: computing)?|network(?: security)?|side projects?|games?)\b")
_SCHOOL = re.compile(r"\b(?:school|schoolwork|class|classes|homework|coursework|course)\b")


def _pending_lists(pending):
    return list((pending or {}).get("lists") or [])


def _find_list(text, lists):
    """The list she names (a real list name, an alias, or school -> ask), ignoring any 'not X' parts. -> name | "school" | None."""
    low = re.sub(r"\bnot (?:in |to |the )?(?:[a-z]+ ){0,2}[a-z]+", " ", text.lower())      # "personal not school": keep what is not negated
    if low.strip() == "" or not re.search(r"[a-z]", low):
        return None
    name, _hit = capture.guess_list(low, lists) if lists else (None, None)
    if name and re.search(r"\b" + re.escape(name.lower()) + r"\b", low):
        return name
    for pat, want in _LIST_ALIASES:
        if re.search(pat, low):
            real = next((l for l in lists if l.lower() == want.lower()), None)
            return real or (want if not lists else None)
    if _SCHOOL.search(low):
        return "school"
    return None


def _at_hour(rest, due_iso, now, pending):
    """'friday at 3': capture finds the date; a bare 'at 3' / 'at 3:30' is read as afternoon for 1 to 7, morning for 8 to 11."""
    m = re.search(r"\b(?:at|@) ?(\d{1,2})(?::(\d{2}))?\b(?! ?(?:am|pm))", rest, re.I)
    if not m:
        return due_iso, rest
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if mi > 59:
        return "invalid", rest
    if not 0 < h <= 12:
        return due_iso, rest
    h = h + 12 if 1 <= h <= 7 else (12 if h == 12 else h)
    base = datetime.fromisoformat(due_iso) if due_iso else now
    d = base.replace(hour=h, minute=mi, second=0, microsecond=0)
    if not due_iso and d < now:
        d += timedelta(days=1)
    return d.isoformat(timespec="minutes"), (rest[:m.start()] + " " + rest[m.end():])


def _edit_date(text, now, pending):
    """A due date or time from words that are nothing but a date edit. -> iso | None."""
    low = " ".join(text.lower().split())
    rel = re.search(r"\bin (\d{1,6}) ?(minutes?|mins?|hours?|hrs?|days?)\b", low)
    if rel:
        n = int(rel.group(1)); u = rel.group(2)
        if n > 100000:
            return None
        delta = timedelta(days=n) if u.startswith("d") else timedelta(hours=n) if u.startswith("h") else timedelta(minutes=n)
        rest = (low[:rel.start()] + " " + low[rel.end():])
        if all(w in _DATE_FILLER for w in re.findall(r"[a-z']+", rest)):
            return (now + delta).replace(second=0, microsecond=0).isoformat(timespec="minutes")
        return None
    due, rest = capture.parse_due(low, now)
    had_clock = bool(capture._time_of(low)) or bool(re.search(r"\b(?:at|@) ?\d", low))
    due2, rest = _at_hour(rest, due, now, pending)
    if due2 == "invalid" or not due2:
        return None
    if any(w not in _DATE_FILLER for w in re.findall(r"[a-z']+", rest)):
        return None                       # other words in it: a new sentence, not an edit
    if (pending or {}).get("mode") == "reminder" and not had_clock:
        due2 = due2[:11] + "09:00" + due2[16:]
    return due2


_INTERJECT = re.compile(r"^(?:(?:hey|oh|well|um+|uh+|hmm+|so)[,.! ]+)+", re.I)


def parse_reply(text, pending, now=None):
    """What a typed reply means for the question the chat last asked. None when there is no pending question
    or the words are a new sentence (the caller then routes it like any other)."""
    if not pending or pending.get("type") != "add":
        return None
    now = now or datetime.now().astimezone()
    raw = " ".join((text or "").split())
    if not raw or len(raw) > 200 or "\n" in raw:
        return None
    t = _INTERJECT.sub("", plain.normalize(raw)) or plain.normalize(raw)      # "hey, yeah but make it friday" answers like "yeah but ..."
    low = intent.clean(t).strip(" .!,")
    low = re.sub(r"\s+(?:please|thanks)$", "", low)
    asked = plain.is_question(raw)
    if asked and (_YES.match(low) or _YES2.match(low) or _NO.match(low)):
        return None                          # "yes?" is a question back, not an answer
    if _YES.match(low) or _YES2.match(low):
        return {"kind": "yes"}
    if _NOT_TASK.match(low):
        return {"kind": "not_task"}
    if _NO.match(low):
        return {"kind": "no"}
    keep_no = bool(_NO_DATE.search(low) or _TASK_ONLY.search(low))      # "no date" and "no texts" are edits, not a "no"
    lead = r"(?:(?:yes|yeah|yea|yep|yup|ya|sure|ok|okay|k|kk" + ("" if keep_no else "|no|nope|nah") + r")\b[,.! ]+(?:but |and |just |though )?)"
    lead_yes = bool(re.match(r"^(?:yes|yeah|yea|yep|yup|ya|sure|ok|okay|k|kk)\b[,.! ]+", " ".join(t.lower().split())))   # intent.clean() strips some of these words, so read the untouched text
    lead_no = (not keep_no) and bool(re.match(r"^(?:no|nope|nah)\b[,.! ]+", low))
    body = re.sub("^" + lead, "", low).strip()
    body_raw = re.sub("^" + lead, "", t, flags=re.I).strip()
    tail = r"[,.]?\s*\b(?:and |then )?(?:add it|do it|save it|go ahead)\s*$"
    confirm = (lead_yes or bool(re.search(tail, body))) and not asked      # a question-shaped reply is never a confirmation
    body = re.sub(tail, "", body).strip(" ,.")
    body_raw = re.sub(tail, "", body_raw, flags=re.I).strip(" ,.")
    if not body or (asked and not _TEXT_ONLY.search(body)):
        return None
    for rx in _TITLE:                       # first: "call it Email Dr. Lee about the lab" keeps her capitals and any date words in it
        m = rx.match(body_raw)
        if m:
            title = " ".join(m.group("t").split()).strip(" .\"“”")
            if 2 <= len(title) <= 200:
                return {"kind": "edit", "edits": {"title": title}, "confirm": confirm}
    edits = {}
    rest = body
    if _TEXT_ONLY.search(rest):
        edits["mode"] = "reminder"; rest = _TEXT_ONLY.sub(" ", rest)
    elif _ALSO_TEXT.search(rest):
        edits["alsoText"] = True; rest = _ALSO_TEXT.sub(" ", rest)
    elif _TASK_ONLY.search(rest):
        edits["mode"] = "task"; edits["alsoText"] = False; rest = _TASK_ONLY.sub(" ", rest)
    if _NO_DATE.search(rest):
        edits["due"] = None; edits["clearDue"] = True; rest = _NO_DATE.sub(" ", rest)
    pick = _find_list(rest, _pending_lists(pending))
    if pick:
        if pick == "school":
            edits["listHint"] = "school"
        else:
            edits["list"] = pick
        rest = _LIST_WORDS.sub(" ", rest)
    d = _edit_date(rest, now, pending)
    if d:
        edits["due"] = d
        rest = ""
    if not edits:
        return {"kind": "no"} if lead_no and not body else None
    if [w for w in re.findall(r"[a-z']+", rest) if w not in _DATE_FILLER]:
        return None                         # words nothing above explained: a new sentence, not an edit
    return {"kind": "edit", "edits": edits, "confirm": confirm}
