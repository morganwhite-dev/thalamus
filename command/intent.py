"""Plain sentences that code can settle before anything else looks at them (no model, no usage):
"what should I work on", "when is lab 7 due", "I'm stuck on lab 7", "done", "yes".

`before_capture(text, tasks)` -> (label, data) or None. Labels: now | schedule | stuck | action | tiny.
It runs before the add-a-task rules, so none of these become a task card. Text must already be plain.normalize()d.
"""
from __future__ import annotations

import re

import class_qa
import plain

_LEAD = re.compile(r"^(?:(?:ok|okay|so|hey|alright|well|um|uh|and|but|please|yo|hmm|k|kk|kay|aight|alright|so+|whatever|yeah|yep|lol|haha|honestly|damn|bruh|dude|man|anyway|anyways|bored|ugh|oh|wait|alr)[,\s]+)+", re.I)
_STOP = plain.NAME_STOP


def clean(text: str) -> str:
    t = " ".join((text or "").lower().split()).strip(" ?.!,")
    t = _LEAD.sub("", t)
    if t not in ("next one please", "next please"):
        t = re.sub(r"\s+(?:please|pls|plz)$", "", t)
    t = re.sub(r"^(?:can|could|would|will) you (?:please )?(?=\S)", "", t)
    t = re.sub(r"^help[,!]? (?=i'm\b|i am\b)", "", t)
    return t.replace("what is ", "what's ").replace("i am ", "i'm ").replace("do not ", "don't ").replace("cannot ", "can't ")


def find_task(phrase, tasks):
    """The one open task her words name (plain.match_target: exact full title first, then whole words), else None."""
    kind, hit = plain.match_target(phrase, tasks)
    return hit if kind == "one" else None


# ---------------------------------------------------------------- "what should I be doing"
_T = r"(?: (?:first|next|now|right now|today|then|for today|for now|at the moment|tell me|help me|for me|first thing|after this|after that))*[,]?"
_NOW = [re.compile(r"(?:" + p + r")$") for p in [
    r"(?:what|which)(?: thing| task| one)? (?:should|do|can|could|shall|would you have) i (?:be )?(?:do|doing|work on|working on|focus on|start(?: with| on)?|tackle|knock out|get done|handle|prioriti[sz]e|attack|hit|dive into|take on|go after|get after|begin(?: with)?)" + _T,
    r"what (?:do|should) i (?:need|have) to (?:do|be doing|get done|work on)" + _T,
    r"what (?:am i|are we) (?:doing|supposed to (?:be )?(?:do|doing|work on|working on)|meant to (?:be )?(?:do|doing)|going to do)" + _T,
    r"what's (?:next|first|up next|up|the plan|the game plan|my plan|the move|on deck|the next (?:thing|task|step)|my next (?:task|thing|step|move)"
    r"|(?:my|the) (?:top |first |main |number one |#1 )?priority|the most important thing|most important)" + _T,
    r"what (?:next|now|comes next|needs doing|needs to (?:be|get) done|needs my attention)" + _T,
    r"now what|next|next task|next up|next one|next thing|hit me|what now|what next|go on|keep going",
    r"where (?:do|should) i (?:even )?(?:start|begin)" + _T,
    r"(?:tell|show) me what to (?:do|work on|start on|focus on)" + _T,
    r"give me (?:something|a task|one thing|the next thing|the next one|my next task)(?: to (?:do|work on))?" + _T,
    r"(?:i )?(?:don't|do not) know what (?:to|i should) (?:do|work on|start on|start with|be doing)" + _T,
    r"(?:what|which)(?: thing| task| one)? (?:do i|should i|do we) (?:do|work on|tackle|start|focus on|move on to|switch to) (?:after|once i'm done with|when i'm done with|when i finish) (?:this|that|it)" + _T,
    r"(?:after|once i'm done with) (?:this|that|it),? (?:then )?(?:what|what's next|what next)|then what" + _T,
    r"(?:which|what)(?: one| task)? (?:should i do|do i do|comes|goes) first",
    r"should i (?:do|start|work on|finish) .{2,60} or .{2,60}?(?: first)?",
    r"(?:plan|map out|sort out) my (?:day|afternoon|morning|evening|night)",
    r"what do you want me to do" + _T,
    r"(?:and |so )?now(?: then)?",
    r"what's the best (?:use of my time|thing (?:to do|i can do|for me to do)|use of (?:this|the) (?:hour|time)|next (?:thing|move|step))" + _T,
    r"help me (?:decide|figure out|pick|choose|plan)(?: what)?(?: to)?(?: do| work on| start| tackle)?" + _T,
    r"(?:i'm |i am )?(?:not sure|unsure|undecided|torn|confused) (?:what|where) (?:to|i should) (?:do|work on|start|tackle|begin)" + _T,
    r"let me know what (?:to|i should) (?:do|work on|start (?:with|on)|be doing|tackle)" + _T,
    r"what can i (?:knock out|get done|do|finish)" + _T,
    r"what (?:should|do) i prioriti[sz]e" + _T,
    r"what's on (?:the |my )?(?:agenda|docket|menu|deck)" + _T,
    r"what (?:do )?you (?:got|have|think i should do)(?: for me| lined up| planned| in mind)?" + _T,
    r"(?:pick|choose|decide|find)(?: something| one| a task| a thing| what)?(?: out)? for me" + _T,
    r"what (?:should|do|can) i do (?:with|for) (?:myself|my time|my (?:day|afternoon|morning|evening|night|hour|free time)|the (?:next|rest of the) (?:hour|day|afternoon|evening|night|morning)|this (?:hour|afternoon|morning|evening))",
    r"i'?m bored|i am bored|bored" + _T,
    r"what (?:should|can|could) i (?:be )?(?:do|doing|work on|working on)(?: with)? (?:right )?now" + _T,
    r"(?:i have|i've got|i got) (?:some |a little |a bit of )?(?:free )?time[, ]+(?:what|where) .{2,40}",
    r"(?:i'?m|i am) free(?: now| rn| right now)?[, ]+(?:what|where) .{2,40}",
    r"(?:i'm |i )?(?:done|finished)(?: with)?(?: that| it| this)?[,. ]+(?:so )?(?:what now|now what|what's next|what next|what should i do(?: now| next)?)",
]]


def now_question(text):
    t = clean(text)
    return bool(t) and "due" not in t and any(rx.match(t) for rx in _NOW)


# ---------------------------------------------------------------- "when is X due"
_DUEQ = [
    re.compile(r"^(?:when is|when's|when are|what day is|what time is) (?P<x>.+?) due(?: again)?$"),
    re.compile(r"^is (?P<x>.+?) (?P<m>overdue|late|due)(?: today| tomorrow| yet| soon| this week)?$"),
    re.compile(r"^when do i (?:have|need) to (?:turn in|submit|finish|hand in) (?P<x>.+)$"),
    re.compile(r"^(?:what's|when's|when is) (?:the|my) (?:due date|deadline) (?:for|on|of) (?P<x>.+)$"),
]


def task_due_question(text, tasks):
    t = clean(text)
    for rx in _DUEQ:
        m = rx.match(t)
        if m:
            return find_task(m.group("x"), tasks)
    return None


# ---------------------------------------------------------------- stuck
_X = r"(?: (?:on|with|at|for|by|about))? ?(?P<x>.*)"
_STUCK_ANY = [re.compile(r"(?:" + p + r")$") for p in [          # stuck with or without a task named
    r"(?:i'm|i feel|feeling) (?:so |really |kind of |a bit |totally )?(?:stuck|overwhelmed|lost|frozen|paralyzed)" + _X,
    r"stuck" + _X,
    r"(?:i'm |i am |feeling |so |really |just )*(?:overwhelmed|lost|frozen|paralyzed|swamped|drowning|spiraling|spiralling|panicking)(?: right now| today| lately| so much| rn)?(?P<x>)",
    r"(?:i )?(?:don't|do not) know (?:where to (?:even )?start|how to (?:even )?start)(?: (?:with|on|for))?(?P<x>)",
    r"help me (?:get )?(?:started|start|begin|going)" + _X,
    r"(?:i )?(?:don't know|have no idea|have no clue|no idea|no clue|'m not sure|am not sure|not sure|can't figure out) (?:where|how) to (?:even )?(?:start|begin|get started)" + _X,
    r"(?:i )?(?:can't|cannot) (?:get started|get going|start|begin|focus|make myself start|make myself do (?:it|this))" + _X,
    r"break (?P<x>this|it|that) down(?: for me)?",
    r"(?:this|it) is (?:overwhelming|too much|a lot)(?P<x>)",
    r"give me (?:a|the|one) (?:first|tiny|small|five minute|5 minute) step" + _X,
    r"what's (?:the|a|my) (?:smallest |tiniest |very |easiest )?first step" + _X,
]]
_STUCK_NAMED = [re.compile(r"(?:" + p + r")$") for p in [        # only when the words name one of her tasks
    r"help(?: me)?(?: out)? (?:with|on) (?P<x>.+)",
    r"break down (?P<x>.+?)(?: for me)?",
    r"how (?:do|should|would) i (?:even )?(?:start|begin|approach|tackle)(?: on)? (?P<x>.+)",
    r"(?:i )?(?:don't|do not) know what to do (?:with|about|for) (?P<x>.+)",
    r"where (?:do|should) i (?:even )?(?:start|begin) (?:with|on) (?P<x>.+)",
]]


def stuck_request(text, tasks):
    """(task_or_None, words) when she is stuck; None otherwise. `words` is what she named when it is not one of her
    tasks ("my taxes"): still a stuck request, answered with a first step from a free model."""
    t = clean(text)
    for rx in _STUCK_ANY:
        m = rx.match(t)
        if m:
            x = (m.group("x") or "").strip()
            if x in ("", "this", "it", "that", "this one", "here", "today", "right now"):
                return (None, "")
            hit = find_task(x, tasks)
            return (hit, "" if hit else x)
    for rx in _STUCK_NAMED:
        m = rx.match(t)
        if m:
            hit = find_task(m.group("x"), tasks)
            return (hit, "") if hit else None
    return None


# ---------------------------------------------------------------- things the buttons do
_ACTIONS = [
    ("done", r"(?:done|done done|done for now|done for today|all done for now|all done for today|all done|all finished|finished it|finished|i did it|did it|mark it done|i'm done|completed|complete)"),
    ("done", r"(?:i'm |i am |i have |i've |i )?(?:just )?(?:finished|completed|did|done with|got through)(?: with)? (?P<x>.+)"),
    ("done", r"(?:mark|check off|tick off|complete|cross off) (?P<x>.+?)(?: as)?(?: done| complete| completed| finished| off)?"),
    ("done", r"(?:i'm |i |i've |i have )?(?:just )?(?:knocked out|knock out|wrapped up|wrap up|crushed|nailed|smashed|finished up|got through|got done with|got done|handled|cleared|polished off|killed)(?: with)? (?P<x>.+)"),
    ("done", r"(?:i )?(?:just )?(?:finished|completed)|(?:i'm|i've|i have) (?:just )?(?:finished|completed)|(?:i )?(?:just )?(?:knocked|wrapped|polished|finished|got) (?:that|this|it|that one|this one)(?: out| up| off| done)?"),
    ("done", r"(?:i )?(?:knocked it out|wrapped it up|nailed it|crushed it|got it done|got that done|it's done|that's done|that one's done|its done|all set|task done|just did it|just finished|just finished it|finished that|finished that up|did that|did that one)"),
    ("snooze", r"snooze(?: (?:this|it|that))?(?: for .+| until .+| till .+| til .+)?|not now|later|maybe later|can't(?: do (?:it|this))? right now|remind me later|come back to (?:this|it) later"),
    ("skip", r"(?:not this|not this one|not that one|no)[,. ]+(?:something else|another one|another|give me something else|next one|next|a different one|pick another)|skip(?: (?:this|it|that)(?: one)?)?|not this one|something else|give me something else|pass|next one please|i don't want to do (?:this|that)(?: one)?"),
    ("unpin", r"un-?pin(?: (?P<x>.+))?"),
    ("pin", r"pin(?: (?P<x>.+))?"),
    ("pin", r"(?:move|put|bring|push|get|jump|shove) (?P<x>.+?) (?:up )?(?:to )?(?:the )?(?:very )?(?:top|front)(?: of (?:the |my )?(?:list|queue|line|pile))?(?: for today| today)?"),
    ("pin", r"(?:move|bring|put|push|get) (?P<x>.+?) up(?: to (?:the )?(?:top|front))?"),
    ("pin", r"(?:make|set) (?P<x>.+?) (?:my |the )?(?:top|first|number one|#1) priority"),
    ("snooze", r"snooze (?P<x>.+)"),
    ("skip", r"skip (?P<x>.+)"),
    ("start", r"(?:i'm |i am |im )?(?:starting|beginning|start|begin)(?: on| working on| with)? (?P<x>.+)"),
    ("start", r"let me (?:start|begin|get started|get going|do it)|(?:i'm|i am|im) ready(?: to (?:start|begin|go|work|get going))?|ready to (?:start|begin|go|work)|(?:i'm |i am |im )?(?:starting|beginning)(?: it| this| now| right now| the (?:timer|block|clock)| (?:a|the) (?:block|timer))?|(?:i'll|i will|i'm going to|i'm gonna|i'm about to) (?:start|begin)(?: now| it)?|time to (?:start|begin|work|get started)|here we go|go time|ok go|start|begin|go|let's go|let's start|let's begin|let's get started|let's get going|let's do it|ready|i'm ready|start (?:it|now|working|the timer|a block|the block|the clock)|start the (?:work )?block"),
    ("break", r"stop timer|stop the clock|end timer|take a break|(?:i )?(?:need|want|gotta have|could use) (?:a|some) (?:quick |short |little |small )?(?:break|breather|rest)|(?:i'm|i am|i'll be|imma|i'm gonna|i'm going to|gonna) (?:taking|take|going on) a (?:quick |short )?(?:break|breather)|taking a (?:quick |short )?break|brb|break please|i need a break|break time|break|pause(?: the timer| it)?|stop|stop the timer|i need to stop|give me a break|time for a break|can i take a break"),
    ("low", r"low energy(?: mode| day)?|turn (?:on|off) low energy(?: mode)?|turn low energy(?: mode)? (?:on|off)|switch (?:on|to) low energy(?: mode)?|(?:wiped(?: out)?|exhausted|drained|tired|fried|beat|dead|spent|sick|burnt out|burned out|worn out)(?: today| rn| right now)?|(?:i'm|i feel|feeling) (?:so |really |too |super )?(?:tired|exhausted|drained|sick|burnt out|burned out|wiped(?: out)?|fried|awful|beat|worn out|spent|zonked|toast|cooked|dead|not feeling (?:well|good|great|it))(?: today| right now| tonight)?|not feeling (?:it|well|good|great)(?: today| right now| tonight)?|rough day|i have no energy|no energy today"),
]
_ACTIONS = [(k, re.compile(r"(?:" + p + r")$")) for k, p in _ACTIONS]
_WHERE = {
    "done": "Press Done on {what} (on the Do this now card, or open its sector and pick it). I don't tick things off from a sentence, so a misread can never complete the wrong task.",
    "snooze": "Snooze is under Not now on the Do this now card: 1 hour, 3 hours or tomorrow.",
    "skip": "Not this one is under Not now on the Do this now card. It swaps in the next best thing, no guilt pile.",
    "pin": "Pin is under Not now on the Do this now card (or on any task you open in a sector). It keeps that task on top for today.",
    "unpin": "Unpin is Pin again on the task: open it and press Pin to turn it off.",
    "start": "Press Start on the Do this now card. A 3-2-1 runs, then the timer.",
    "break": "A break starts from the work block: press Done: take a break when you want to stop. With no block running, just step away; I'll be here.",
    "low": "Sounds like a low-energy day. Turn on Low energy (top right): shorter blocks, gentler breaks, softer wording.",
}


_SCOPE = re.compile(r"(?P<a>.+?)\s+(?:in|for|from|under|on)\s+(?:the |my )?(?P<l>.+?)(?:\s+(?:class|course|list))?"
                    r"(?P<b>\s+(?:as )?(?:done|complete|completed|finished|off))?$")


def _scope(t, tasks):
    """'mark read chapter 7 complete in network security' -> ('mark read chapter 7 complete', tasks in Network Security).
    Only when the trailing words name one of her lists; 'snooze this for 2 hours' is left alone."""
    m = _SCOPE.match(t)
    if not m:
        return t, tasks
    want = set(plain.words(m.group("l"))) - plain.NAME_STOP
    inside = [x for x in tasks or [] if want and want <= set(plain.words(x.get("list") or ""))]
    if not inside:
        return t, tasks
    return m.group("a") + (m.group("b") or ""), inside


def action_request(text, tasks):
    """(kind, task_or_None) for done/snooze/skip/pin/start/break/low-energy said as a sentence, else None."""
    if plain.is_question(text):
        return None                          # "skip this?!" and "wait, skip this?" are questions: clean() would drop the "?"
    t, tasks = _scope(clean(plain.strip_lead(text)), tasks)
    t0 = re.sub(r"\s+(?:right now|now|rn)$", "", t)
    for kind, rx in _ACTIONS:
        m = rx.match(t) or (rx.match(t0) if t0 != t else None)
        if not m:
            continue
        x = re.sub(r"\s+(?:right now|now|rn)$", "", (m.groupdict().get("x") or "").strip())
        if x and kind == "done":
            hit = find_task(x, tasks)
            if not hit and not re.fullmatch(r"(?:it|this|that|the (?:reading|lab|quiz|discussion|assignment|homework|task|thing)|everything|for (?:today|now)|my (?:reading|lab|homework))", x):
                continue                     # "did the dishes and need a new plan" is not a button press
            return kind, hit
        if x and kind == "start":
            hit = find_task(x, tasks)
            if not hit:
                continue                     # "start a new react project" is not the Start button
            return kind, hit
        return kind, (find_task(x, tasks) if x else None)
    return None


# "mark X done" / "check off X" / "done with X" where X names no single open task. These are clearly a Done, so the chat
# answers itself (not open, or which one?) instead of handing the sentence to a model, which cannot tick anything off.
_DONE_NAMED = [re.compile(p + r"$") for p in (
    r"(?:please )?mark (?P<x>.+?) (?:as )?(?:done|complete|completed|finished|off)",
    r"(?:please )?(?:check|tick|cross) off (?P<x>.+)",
    r"(?:please )?(?:check|tick|cross) (?P<x>.+?) off",
    r"(?:i'm |i am |im )?(?:all )?done with (?P<x>.+)",
)]
_GENERIC = re.compile(r"(?:it|this|that|this one|that one|the (?:reading|lab|quiz|discussion|assignment|homework|task|thing)|everything|for (?:today|now)|my (?:reading|lab|homework)|(?:my |the )?break)")


def done_named(text, tasks):
    """For an explicit Done naming a task that is not exactly one open task: (phrase, "many" | "none", options), else None.
    options: the matching tasks ("many"), or up to 3 open tasks whose titles are close to the phrase ("none")."""
    if plain.is_question(text):
        return None
    t, tasks = _scope(clean(plain.strip_lead(text)), tasks)
    for rx in _DONE_NAMED:
        m = rx.match(t)
        if not m:
            continue
        x = re.sub(r"\s+(?:right now|now|rn)$", "", m.group("x").strip())
        if not x or _GENERIC.fullmatch(x):
            return None
        kind, hit = plain.match_target(x, tasks)
        if kind == "one":
            return None
        if kind == "many":
            return x, "many", hit[:4]
        import difflib
        by = {}
        for task in tasks or []:
            by.setdefault(task["title"].lower(), task)
        close = difflib.get_close_matches(x.lower(), list(by), n=6, cutoff=0.6)
        num = re.search(r"\d+", x)
        if num:                              # "chapter 6" -> chapter 7 before chapter 9
            dist = lambda c: min((abs(int(d) - int(num.group())) for d in re.findall(r"\d+", c)), default=999)
            close.sort(key=dist)
        return x, "none", [by[c] for c in close[:3]]
    return None


_ORD = {"first": 0, "1": 0, "one": 0, "second": 1, "2": 1, "two": 1, "third": 2, "3": 2, "three": 2, "fourth": 3, "4": 3, "four": 3}


def pick_option(text, options):
    """Which of `options` her reply names: a number or ordinal, "the last one", a title, or a list name ("it's for network
    security", "the cloud one"). -> the task, or None when it names none or more than one."""
    t = clean(plain.strip_lead(text))
    t = re.sub(r"^(?:it's |its |it is |the one |i mean |i meant |meant )?(?:for |in |from |under )?(?:the )?", "", t)
    t = re.sub(r"\s+(?:one|task|class|list)$", "", t).strip()
    if t in ("last", "the last"):
        return options[-1] if options else None
    i = _ORD.get(re.sub(r"^(?:number |#)", "", t))
    if i is not None:
        return options[i] if i < len(options) else None
    kind, hit = plain.match_target(t, options)
    if kind == "one":
        return hit
    want = set(plain.words(t)) - plain.NAME_STOP
    by_list = [o for o in options if want and want <= set(plain.words(o.get("list") or ""))]
    return by_list[0] if len(by_list) == 1 else None


_WHERE_TYPED = {
    "done": "done", "start": "start", "snooze": "snooze", "skip": "skip", "pin": "pin", "break": "break", "low_energy_on": "low", "low_energy_off": "low",
    "started_earlier": "Started earlier is the clock icon on the Do this now card (I started 15 / 30 min ago), so the timer counts from when you really began.",
    "add_time": "+15 min is on the work block while a block runs.",
    "end_break": "End break is on the break screen.",
    "skip_break": "Skip break is on the break screen.",
    "cancel_block": "Cancel block is under the work block's menu while a block runs.",
    "undo": "Undo shows up on the status line for 2 minutes after you press Done. Press it there; I don't undo from a sentence.",
    "stuck": "I'm stuck is on the Do this now card. It breaks the task into a five-minute first step.",
}


def action_reply(kind, task=None):
    """The sentence that says which button does this. Takes (kind, task), the (kind, task) tuple action_request returns,
    or the dict typed.parse_action returns."""
    if isinstance(kind, tuple):
        kind, task = kind
    if isinstance(kind, dict):
        task_id, act = kind.get("task_id"), kind["action"]
        what = "the task"
        key = _WHERE_TYPED.get(act, act)
        if key in _WHERE:
            return _WHERE[key].format(what=what)
        return key
    what = f"\"{task['title']}\"" if task else "the task"
    return _WHERE.get(kind, _WHERE_TYPED.get(kind, "")).format(what=what) or "That one is a button on the Do this now card."


# ---------------------------------------------------------------- too little to act on
_GREET = {"hi", "hello", "hey", "yo", "sup", "good morning", "morning", "good evening", "good night", "hey there", "hi there"}
_THANKS = {"thanks", "thank you", "thanks a lot", "thank you so much", "cool thanks", "ok thanks", "great thanks", "perfect thanks", "appreciate it"}
_FILLER = {"yes", "no", "ok", "okay", "k", "kk", "sure", "yep", "yeah", "nope", "nah", "lol", "nvm", "never mind", "nevermind", "cool", "nice",
           "ok cool", "i don't know", "hm", "alright", "bet", "fine", "good", "ok good", "oh", "oh ok", "ah", "wow", "sounds good", "got it thanks",
           "cool cool", "sure thing", "no thanks", "no thank you", "nah thanks", "all good", "i'm good", "never mind thanks", "true", "right", "yup", "ya", "mhm", "uh", "um", "meh", "ugh", "haha", "lmao", "omg", "oops", "wait", "hold on",
           "yea", "great", "perfect", "got it", "that one", "this one", "the first one", "the second one", "the last one", "first one", "second one",
           "idc", "whatever", "hmm", "huh", "what", "why", "test", "testing"}


_HELP = re.compile(r"(?:help|i need help|help me|what can (?:you|i) (?:do|ask|say|type)(?: here)?|how does this (?:work|thing work)|what do i (?:type|say)|"
                   r"what can i ask you|how do i use (?:this|you|thalamus)|commands|what are the commands|what do you do)$")
HELP_TEXT = ("Just say it plainly. A few things I answer straight away, no model:\n"
             "- what should I work on · what's due friday · am I behind · when is lab 7 due · do I have class today\n"
             "- remind me to call mom at 5 · I need to email Dr. Lee friday · do tryhackme an hour a day\n"
             "- where was I on the analyzer · find my resume · idea: a golf swing tracker · I'm stuck on lab 7\n"
             "Anything else goes to a model, starting with the free ones.")


def tiny(text):
    """A reply with nothing to act on. Returns the answer to show, or None."""
    raw = " ".join((text or "").lower().split()).strip(" ?.!,")
    if _HELP.match(raw):
        return HELP_TEXT
    if raw in _GREET:
        return "Hi. Ask what to do now, ask what's due, or tell me something to remember."
    if raw in _THANKS:
        return "Anytime."
    if not re.search(r"[a-z0-9]", raw) or raw in _FILLER or re.fullmatch(r"(?:number |no\.? ?|option |#)?\d{1,3}", raw):
        return ("I don't have a question waiting for that answer. Say the whole thing in one go, like "
                "\"what's due friday\", \"where was I on the analyzer\" or \"remind me to call mom at 5\".")
    return None


# ---------------------------------------------------------------- catch-all for questions about her own day
# A sentence made only of everyday words plus her own task and list names is about her plan, however it is phrased.
# Anything with an outside word in it ("python", "subnet", "mom") is left for the other rules.
_FUNC = set("""what whats what's which who where when why how is are am was were be been do does did doing done have has had having can could should
would will shall may might must i i'm i've i'd me my mine myself you your we our it its that this these those the a an and or but so if then than of on
in at to for from with about into over by up out off as not no any some all one ones thing things stuff something anything everything nothing task tasks
work list plan plans day today now right currently moment hour hours minute minutes min mins time free bit while little lot much many more most least
just only also really actually even still already yet again ok okay please tell show give let lets let's there here go going get got getting put
make take keep know think want need needs like feel feels look looks say said best good better great new other another else kind sort way
game come comes goes sat down sitting back home ready working works worked tonight morning afternoon evening later soon quick quickly long short big small real main top whole half next last
school class classes homework assignment assignments lab labs reading project projects internship internships application applications
security personal play errand errands on-deck okay?""".split())
_STRONG = set("""urgent urgently priority priorities prioritize prioritise important first next start started starting begin beginning tackle focus
energy attention pressing critical biggest top step steps supposed knock handle recommend suggest order move""".split())
_SCHEDW = set("""due deadline deadlines behind late overdue forgetting forgot forget forgotten miss missed missing calendar plate coming upcoming left
remaining open tomorrow week weekend month monday tuesday wednesday thursday friday saturday sunday schedule scheduled owe pending outstanding far
busy load loaded packed swamped slammed caught exam exams test tests quiz quizzes midterm midterms final finals""".split())


_IMPERATIVE = {"start", "starting", "begin", "beginning", "finish", "complete", "mark", "pin", "skip", "snooze", "go", "let", "lets", "let's", "work", "read",
               "write", "study", "check", "cross", "tick", "put", "move", "bring", "stop", "pause", "take", "make", "set", "call", "name", "rename", "change", "switch"}


def planning_fallback(text, tasks, lists=None):
    """'now' | 'schedule' | None for a short question about her own plan that no specific rule matched."""
    t = clean(text)
    ws = re.findall(r"[a-z0-9']+", t)
    if not 2 <= len(ws) <= 16:
        return None
    own = set()
    for name in [x["title"] for x in tasks or []] + list(lists or []):
        own |= set(re.findall(r"[a-z0-9']+", name.lower()))
    if any(w not in _FUNC and w not in _STRONG and w not in _SCHEDW and w not in own and not w.isdigit() for w in ws):
        return None
    if ws[0] in _IMPERATIVE or re.match(r"i (?:need|have|got|want|gotta|should|must|'d like) to (?!know|figure|decide|see)", t):
        return None                          # a command or statement ("start lab 7", "i need to start ..."), not a question about her plan
    if any(w in _SCHEDW for w in ws) or re.match(r"(?:when|how many|how much)\b", t):
        return "schedule"
    if any(w in _STRONG for w in ws) or re.search(r"\b(?:should i|i should|do i|can i|could i|to) (?:do|work on|be doing)\b", t):
        return "now"
    return None


def schedule_question(text, tasks=None, lists=None, now=None) -> bool:
    """The one schedule detector: a question about her classes, deadlines or day. The no-sector route and the open-sector
    capture rule both call this, so a schedule question asked in a sector is never a task."""
    import schedule_qa
    return bool(class_qa.parse(text) or schedule_qa.parse(text, None, now) or task_due_question(text, tasks or [])
                or planning_fallback(text, tasks, lists) == "schedule")


def before_capture(text, tasks, now=None):
    msg = tiny(text)
    if msg:
        return "tiny", msg
    import capture                           # lazy: capture imports modules that import this one
    freq = capture.frequency_problem(text)
    if freq:
        return "tiny", freq                  # "stretch 0 times a week": ask for a real number, never default to daily
    task = task_due_question(text, tasks)
    if task:
        return "schedule", task
    if now_question(text):
        return "now", None
    st = stuck_request(text, tasks)
    if st:
        return "stuck", {"task": st[0], "words": st[1]}
    import typed                             # lazy: typed imports this module
    offer = typed.question_offer(text, tasks, now)
    if offer:
        return "tiny", offer                 # "skip this?": a question, answered without acting
    act = typed.parse_action(text, tasks, now) or action_request(text, tasks)    # typed is the one parser; the old rules only add a "which button" reply
    if act:
        return "action", act
    fb = None if class_qa.parse(text) else planning_fallback(text, tasks)
    if fb == "now":
        return "now", None
    return None
