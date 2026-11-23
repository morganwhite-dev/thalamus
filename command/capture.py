"""Plain-language task capture for the command box (Phase 15). Plain code, no model.

`detect(text, lists, now)` returns None (not a task, send it down the normal path) or a proposal
the page shows as a confirm card. Nothing is created here. Contract: command/STATE_MODEL_CAPTURE.md.
"""
from __future__ import annotations

import re
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import class_qa  # noqa: E402
import park  # noqa: E402
import plain  # noqa: E402
import reminders_qa  # noqa: E402
import schedule_qa  # noqa: E402

QUESTION_START = re.compile(r"^\s*(what|whats|what's|when|where|why|how|who|which|is|are|does|did|can|could|should i|will|would|show|list|tell|explain|summari[sz]e|give me|help)\b", re.I)
TRIGGERS = [
    r"reminder:? ", r"reminder to ", r"write down:? ", r"set-?up (?:a |an )?(?:reminder|alarm)(?: for me)? (?:to |for |at |about )?", r"add:? (?:in |on )?",
    r"(?:create|make|add|start|set up|new) (?:me )?(?:a |an )?(?:new )?(?:task|todo|to-do|reminder|item)(?: list)?(?: to| for| about| called| named| titled|:)? ?",
    r"remind me (?:to |about )?", r"add (?:a task |a todo |an item |a reminder )?(?:to |for )?", r"put ", r"make a note (?:to |of )?",
    r"don'?t let me forget (?:to |about )?", r"don'?t forget (?:to |about )?", r"i (?:really |still |also )?(?:need|have|got|gotta|must|should|want) to ",
    r"i'?ve got to ", r"i gotta ", r"to-?do:? ", r"todo:? ", r"note to self:? ",
    r"(?:still |also )?(?:need|have|got) to ", r"i (?:should|must|better|ought to)(?: probably| really)? ", r"remember to ", r"make sure (?:i |to |that i )",
    r"(?:new )?task: ?", r"new task ", r"set (?:a |an )?(?:reminder|alarm)(?: for me)? (?:to |for |at |about )?", r"(?:text|ping|nudge|message|alert|notify) me ",
    r"i'?d like to ", r"i would like to ", r"jot (?:this |that )?down:? ", r"write (?:this |that )down:? ", r"note:? ",
    r"i keep forgetting (?:to |about )?", r"i always forget (?:to |about )?", r"i (?:forgot|keep meaning) to ",
]
POLITE = re.compile(r"^\s*(?:(?:hey|ok|okay|so|oh|also|and|please|yo|k|alright|um|uh|actually|btw)[,\s]+)*(?:(?:can|could|would|will) you (?:please )?|please |let me |let's |lets |i want you to |i need you to |go ahead and |you can |just )?", re.I)
TRIGGER_RE = re.compile(r"^\s*(?:" + "|".join(TRIGGERS) + r")", re.I)
# after "I need to ...": wanting to know something is a question, not a task
NOT_TASK_REST = re.compile(r"^(?:know|find out|figure out|understand|see (?:what|if|when|how)|learn (?:what|how|why)|ask you|hear|check (?:what|when|if))\b", re.I)
# work for a model, not a to-do: "write a cover letter for ...", "fix the bug in import.py"
MODEL_WORK = re.compile(r"^(?:write|draft|compose|generate|create|build|code|implement|refactor|debug|fix|review|rewrite|summari[sz]e|explain|translate|"
                        r"design|convert|analy[sz]e|compare|research|make)\b.*(?:\b(?:function|script|code|tests?|class|file|cover letter|letter|"
                        r"email|essay|summary|report|paragraph|schema|bug|error|regex|query|readme|docstrings?)\b|\.[a-z]{2,5}\b)", re.I)
# Coding and building are model work too, whatever the first word is: "just add unit tests for app.py", "remind me to debug the login flow".
# Only code nouns and code verbs count: "pay for my gym program", "call the clinic about tests for allergies" and "buy a python book" stay errands.
_LANGS = r"python|javascript|typescript|java|c\+\+|c#|rust|golang|swift|bash|sql|ruby|php|react|node(?:\.?js)?|flask|django|html|css|kotlin"
CODE_WORK = re.compile(
    r"\b(?:debug(?:ging)?|refactor(?:ing)?)\b"
    r"|\b(?:unit tests?|scripts?|regex(?:es)?|docstrings?|snippets?|endpoints?|apis?|repos?|repositor(?:y|ies)|codebase|compiler|algorithms?|"
    r"login (?:flow|page|form|screen)|sign-?up (?:flow|form))\b(?! (?:project|class|course|homework|assignment|exam|quiz|lab|meeting|presentation)s?\b)"
    r"|\bfunctions?\b(?= (?:to|that|for|which|in|called|named|returning)\b)|\b(?:helper|utility|util|async|recursive|lambda) functions?\b"
    r"|\b(?:build|make|create|code|develop|implement|deploy|ship|design)\b[^.]{0,30}?\b(?:website|web ?site|web ?app|app|bot|plugin|extension|landing page)s?\b"
    r"|\b\w[\w-]*\.(?:py|js|ts|tsx|jsx|java|c|cpp|h|rs|go|rb|php|swift|kt|sh|sql|html|css|json|yaml|yml|md|ipynb)\b"
    r"|\b(?:in|using|with|via) (?:" + _LANGS + r")\b"
    r"|\b(?:" + _LANGS + r") (?:script|function|program|code|app|class|module|bot|snippet)s?\b"
    r"|\btask (?:scheduler|manager|runner|queue|planner|tracker|app|system|board|automation)\b", re.I)
# writing work for a model, read from the VERB of the work: "draft an email to the hiring manager", "write my essay", "rewrite my bio".
# With a day named it is homework to remember, so it stays a task ("remind me to write my essay friday").
WRITING_VERB = re.compile(r"^(?:(?:help me|i need to|need to|have to)\s+)?(?:draft|write|compose|rewrite|re-write|proofread|polish|edit|word|reword|phrase|rephrase)\b", re.I)
WRITING_NOUN = re.compile(r"\b(?:cover letters?|letters?|essays?|resumes?|cvs?|e-?mails?|messages?|notes?|posts?|bios?|summar(?:y|ies)|reports?|paragraphs?|"
                          r"outlines?|speech(?:es)?|captions?|tweets?|threads?|proposals?|statements?|abstracts?|replies|reply|responses?|blurbs?|"
                          r"descriptions?|intros?|introductions?|toasts?|eulog(?:y|ies)|articles?|blog|drafts?|pitch(?:es)?|scripts?)\b", re.I)
WRITING_WORK = re.compile(r"\b(?:draft|write|compose|rewrite)\b[^.]{0,30}?\b(?:cover letters?|essays?|resumes?)\b", re.I)
# errand verbs: "buy a book about algorithms", "order a usb drive for my scripts" are errands whatever nouns follow
ERRAND_VERB = re.compile(r"^(?:buy|pay|order|pick up|return|mail|drop off|renew|book|cancel|refill|rsvp|venmo|print|sign up for|register for|"
                         r"go to|stop by|swing by|drop by)\b", re.I)


def _payload(t: str) -> str:
    """The work itself: the words after any task trigger ("add ", "remind me to ", "i need to ")."""
    return TRIGGER_RE.sub("", (t or "").strip(), count=1).strip()


def _writing_work(t: str) -> bool:
    """Writing for a model. With a day or a clock time named it is something to remember ("set a reminder to draft an email at 7am")."""
    w = _payload(t)
    hit = bool(WRITING_WORK.search(w)) or (bool(WRITING_VERB.match(w)) and bool(WRITING_NOUN.search(w)))
    return hit and not _has_date_word(t) and not _time_of(t) and not rel_found(t)


FREQ = re.compile(r"\b(\d{1,6}|zero|no)\s*(?:times?|x)\s*(?:a|per|each|every|/)\s*(week|wk|day)\b", re.I)
FREQ_STATEMENT = re.compile(r"^\s*(?:i|i'm|im|i've|we|it|it's|its|that|there|he|she|they|you|this is|what|how|why|when|where|who|which|is|are|do|does|did|can|could|should|would)\b", re.I)


def frequency_problem(text: str):
    """A reply when a repeat asks for a number of times no week (1 to 7) or day (1 to 24) can hold, else None.
    "study plan for stretch 0 times a week" never becomes a daily habit. Statements and questions are left alone."""
    t = plain.squash(text).split("\n", 1)[0].strip()      # a plan has its frequency on the first line: "study plan for stretch 0 times a week:" + bullets
    if not t or len(t) > 400 or plain.is_question(t) or FREQ_STATEMENT.match(plain.request_body(t)):
        return None
    for m in FREQ.finditer(t):
        n = 0 if m.group(1).lower() in ("zero", "no") else int(m.group(1))
        if m.group(2).lower().startswith("w") and not 1 <= n <= 7:
            return "How many times a week? Say a number from 1 to 7, like stretch 3 times a week. I didn't add anything."
        if m.group(2).lower() == "day" and not 1 <= n <= 24:
            return "How many times a day? Say a number from 1 to 24, like stretch 2 times a day. I didn't add anything."
    return None


def _code_work(t: str) -> bool:
    """Coding work, judged by the verb: code nouns after an errand verb ("buy a book about algorithms") are still an errand."""
    w = _payload(t)
    return bool(CODE_WORK.search(w)) and not ERRAND_VERB.match(w)


def is_model_work(t: str) -> bool:
    return bool(MODEL_WORK.match(t) or _code_work(t) or _writing_work(t))


# her own edit words for a card she already sees ("make it saturday", "put it in school", "call it ..."): never a new task
EDIT_SHAPED = re.compile(r"^\s*(?:(?:ok|okay|so|actually|yeah|yes|no|please|and|but|just)[,\s]+)*(?:make|set|put|move|push|call|name|rename|title|label|change|file|switch)\s+"
                         r"(?:it\b(?!')|that(?=\s*$|\s+(?:to|in|into|on|under|for|at|by|as|due|until|till|next|this|tomorrow|today|tonight)\b))", re.I)

NEED_A = re.compile(r"^(?:i )?need (?:a|an|some|new)\s+\S+(?:\s+\S+){0,3}\s*$", re.I)
NEED_NOT = re.compile(r"\b(?:script|function|program|code|snippet|regex|query|python|javascript|java|sql|bash|api|algorithm|tutorial|break|breather|minute|second|nap|rest|hint|tip|tips|idea|ideas|help|explanation|example|examples|summary|answer|answers|plan|letter|hug|drink|vacation|day off|moment|sec|clue|reason|way|explanation)\b", re.I)
# errands that are a task even with no date: "call mom", "pay the electric bill"
ERRAND = re.compile(r"^(?:email|call|text|buy|pay|renew|book|schedule|order|pick up|return|mail|drop off|sign up for|register for|print|cancel|"
                    r"reschedule|refill|rsvp|venmo|message|dm|go to|stop by|swing by|drop by)\s+(?!me\b|it\b|this\b|that\b|them\b|us\b|where\b)\S", re.I)
ACTION_VERBS = ("complete", "wrap up", "knock out", "handle", "email", "call", "text", "buy", "pay", "renew", "submit", "finish", "schedule", "book", "send", "order",
                "pick up", "apply", "clean", "fix", "write", "study", "do", "start", "begin", "review", "prep", "prepare", "turn in", "get", "grab", "take", "bring", "make", "visit", "meet", "attend", "watch", "practice", "go", "run", "walk", "work on", "stretch", "meditate", "exercise", "workout", "read", "return", "cancel", "sign up", "register", "print", "mail", "drop off")
PROJECT_PHRASE = re.compile(r"^\s*(?:please\s+)?(?:do|work on|build|make|start|finish|code|create)\s+.{2,120}\bprojects?\b\s*[.!]?\s*$", re.I)
COURSE_WORDS = re.compile(r"\b(network security|cloud computing|internships?|security projects?|side projects?|playground)\b", re.I)
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
MONTH_RE = "|".join(m[:3] + (r"(?:" + m[3:] + ")?" if len(m) > 3 else "") for m in MONTHS)
KEYWORD_LISTS = [
    (r"\b(internship|apply|application|resume|cover letter)\b", "Internships"),
    (r"\bsecurity project\b", "Security Projects"),
    (r"\b(golf|games?|gaming|steam|xbox|ps5)\b", "Play"),
    (r"\bprojects?\b", "Side Projects"),
    (r"\b(email|call|text|renew|pay|buy|appointment|bill|pick up|drop off|mail|return|dentist|doctor|groceries)\b", "Personal"),
]


CLUSTER_OF_LIST = {"play": "play", "side projects": "play", "games": "play", "personal": "personal", "internships": "intern",
                   "security projects": "security", "network security": "school", "cloud computing": "school", "general": "personal"}
SPACED = {1: [0], 2: [0, 3], 3: [0, 2, 4], 4: [0, 1, 3, 4], 5: [0, 1, 2, 3, 4], 6: [0, 1, 2, 3, 4, 5], 7: [0, 1, 2, 3, 4, 5, 6]}
NUMWORDS = {"one": 1, "once": 1, "two": 2, "twice": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7}
DAYPART_TIME = {"morning": "08:00", "evening": "18:00", "night": "20:00"}
DEFAULT_NUDGE = "09:00"


def _dow(name: str) -> int:
    return next(i for i, d in enumerate(WEEKDAYS) if d.startswith(name[:3]))


def parse_cadence(text: str):
    """Recurring phrases -> {days, nudgeAt, phrase} or None. General: any wording of daily, weekly, N a week, weekdays or a named day."""
    low = text.lower()
    day_re = "|".join(WEEKDAYS)
    days, phrase = None, None
    any_day = r"(?:mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:r(?:s(?:day)?)?)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)"
    # "monday through friday", "mon-fri", "tuesday to thursday"
    rng = re.search(r"\b(?:(?:every|each|on|from) )?(" + any_day + r") ?(?:through|thru|to|until|-|–) ?(" + any_day + r")\b", low)
    if rng:
        a, b = _dow(rng.group(1)), _dow(rng.group(2))
        days = [d % 7 for d in range(a, b + 1)] if a <= b else [d % 7 for d in range(a, b + 8)]
        phrase = rng.group(0)
    if days is None:
        # "monday, wednesday and friday", "mon/wed/fri" (two or more day names make a pattern)
        lst = re.search(r"\b(?:(?:every|each|on) )?" + any_day + r"(?:s)?(?:(?:,| and|/|&| \+)+ ?" + any_day + r"(?:s)?)+\b", low)
        if lst:
            names = re.findall(any_day, lst.group(0))
            days, phrase = sorted({_dow(n) for n in names}), lst.group(0)
    m = re.search(r"\b(?:every|each) (" + day_re + r")s?\b|\b(" + day_re + r")s\b", low) if days is None else None
    if m:
        days, phrase = [WEEKDAYS.index(m.group(1) or m.group(2))], m.group(0)
    if days is None:
        m = re.search(r"\bweekdays\b|\bevery weekday\b", low)
        if m: days, phrase = [0, 1, 2, 3, 4], m.group(0)
    if days is None:
        m = re.search(r"\bweekends?\b(?!\s+(?:trip|plans))", low) if re.search(r"\b(?:every|each) weekend\b|\bon weekends\b", low) else None
        if m: days, phrase = [5, 6], m.group(0)
    if days is None:
        m = re.search(r"\b(one|once|two|twice|three|four|five|six|seven|a couple(?: of)?|a few|\d+)(?: ?times?| ?x| days?)? ?(?:a|per|each|every|/) ?(?:week|wk)\b|\b(twice|once|two times|three times) weekly\b|\bweekly\b|\bevery week\b|\bonce a week\b", low)
        if m:
            key = (m.group(1) or m.group(2) or "one").split()[0] if (m.group(1) or m.group(2)) else "one"
            if m.group(1) and m.group(1).startswith("a couple"): key = "two"
            elif m.group(1) == "a few": key = "three"
            elif m.group(2): key = {"two times": "two", "three times": "three"}.get(m.group(2), m.group(2))
            elif m.group(1): key = m.group(1)
            n = NUMWORDS.get(key) or (int(key) if key.isdigit() and len(key) <= 3 else 0)
            if not 1 <= n <= 7:
                return None                # "0 times a week", "99 times a week": not a repeat I can lay out on a week
            days, phrase = SPACED[n], m.group(0)
    part = None
    if days is None:
        m = re.search(r"\b(?:every|each) (morning|evening|night)\b", low)
        if m: days, phrase, part = list(range(7)), m.group(0), m.group(1)
    if days is None:
        m = re.search(r"\b(?:daily|every ?day|each day|(?:one|once|1|twice|two times|2 times|three times|3 times|\d+ times|\d+x) (?:a|per|each|every) day|(?<!it )(?<!what )(?<!such )(?<!quite )a day|per day|every single day)\b", low)
        if m:
            days, phrase = list(range(7)), m.group(0)
            # "tier 1 every day": the 1 belongs to the name (tier, chapter, lab...), not to "once a day"
            if re.match(r"(?:1|one) (?:a|per|each|every) day$", phrase) and re.search(
                    r"\b(?:tier|chapter|ch|lab|module|week|step|part|level|section|unit|lesson|room|page|problem|question|hw|homework|assignment|project|phase|exam|test|quiz|class|session|round|stage|task|item|number|no|#)\s*$", low[:m.start()]):
                phrase = phrase.split(None, 1)[1]
    if days is None and parse_duration(text):
        # a length followed by "day", however it was typed: "one hour. day", "1 hour/day", "an hour at day"
        m = re.search(r"(?:hours?|hrs?|\bh|minutes?|mins?)(\W{0,3}(?:(?:an?|at|per|each|every|one|1) ?)?day\b)", low)
        if m:
            days, phrase = list(range(7)), m.group(1)
    if days is None:
        return None
    tm = _time_of(text)
    nudge = DEFAULT_NUDGE
    if tm:
        nudge = f"{tm[0]:02d}:{tm[1]:02d}"
    elif part:
        nudge = DAYPART_TIME[part]
    return {"days": days, "nudgeAt": nudge, "phrase": phrase, "label": cadence_label(days)}


def rel_found(t: str):
    return re.search(r"\bin \d{1,6} ?(?:minutes?|mins?|hours?|hrs?)\b", t, re.I)


DURATION_RE = re.compile(r"\b(?:for |about |around )?(half an|half a|an|a|one|two|three|four|\d{1,4}(?:\.\d{1,2})?) ?(hours?|hrs?|h|minutes?|mins?|min)\b(?! (?:before|after|ago))", re.I)
NUMBER = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "half an": 0.5, "half a": 0.5}


def parse_duration(text: str):
    """'for one hour', '30 minutes', 'half an hour' -> (minutes, matched phrase) or None."""
    m = DURATION_RE.search(text)
    if not m:
        return None
    word = m.group(1).lower()
    n = NUMBER.get(word)
    if n is None:
        n = float(word)
    mins = int(round(n * (60 if m.group(2).lower().startswith("h") else 1)))
    return (mins, m.group(0)) if 1 <= mins <= 600 else None


def cadence_label(days):
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    d = sorted(days)
    if d == list(range(7)): return "daily"
    if d == [0, 1, 2, 3, 4]: return "weekdays"
    if d == [5, 6]: return "weekends"
    return " · ".join(names[i] for i in d)


def split_notes(text: str):
    """'add X to playground. my goal is Y' -> ('add X to playground', 'my goal is Y')."""
    m = re.search(r"(?<=[a-z0-9\)])[.!]\s+(?=(?:my |the |our )?(?:goal|target|aim)\b|i want|i'd like|i would like|note\b|i'm trying|i am trying)", text.strip(), re.I)
    if not m:
        return text.strip(), ""
    return text.strip()[:m.start()], text.strip()[m.end():].strip().rstrip(".")


DO_QUESTION = re.compile(r"^\s*do (?:you|i|we|they|he|she|it|there|any|my|these|those)\b", re.I)   # "do you have..." is a question; "do tryhackme daily" is not


def _is_question(text: str) -> bool:
    t = text.strip()
    return plain.ends_question(t) or bool(QUESTION_START.match(t)) or bool(DO_QUESTION.match(t))


def _has_date_word(t: str) -> bool:
    return bool(re.search(r"\b(?:1[0-2]|0?[1-9])/(?:3[01]|[12]\d|0?[1-9])\b|\b(today|tonight|tomorrow|this weekend|next week|in \d+ (?:day|week)s?|" + "|".join(WEEKDAYS) + r"|(?:" + MONTH_RE + r")\.? \d{1,2}|\d{1,2}(?:st|nd|rd|th)? of (?:" + MONTH_RE + r"))\b", t, re.I))


def unpolite(text: str) -> str:
    """'can you remind me to ...?' -> 'remind me to ...' (only when what follows is a task trigger)."""
    t = plain.squash(text)
    core = POLITE.sub("", t, count=1)
    if core != t and TRIGGER_RE.match(core):
        return plain.strip_question(core)
    return t


PLAN_RE = re.compile(
    r"^\s*(?:please\s+)?(?:(?:make|create|build|set up|start|write|add|give)\s+(?:me\s+)?(?:a|an|my)?\s*)?"
    r"(?:(?:(?:study|learning|practice|daily|reading|training)\s+)?plan\s+(?:for|to (?:learn|study|do|work through))\s+(?P<a>[^:\n]+?)"
    r"|(?P<b>[^:\n]+?)\s+(?:study |learning |practice |daily )?plan(?P<tr>(?:\s+(?:every|each|daily|for|per|a)\b[^:\n]*)?))\s*(?::|\n|\s-\s|$)(?P<rest>.*)$", re.I | re.S)


def parse_plan(text: str):
    """'study plan for tryhackme: room a, room b' -> {name, items, cadence, minutes} or None.
    The list after the colon may be separated by newlines, semicolons or commas; numbering is stripped."""
    t = unpolite((text or "").strip())
    m = PLAN_RE.match(t)
    if not m or _is_question(t):
        return None
    head = ((m.group("a") or m.group("b") or "") + " " + (m.group("tr") or "")).strip()
    if not head or len(head.split()) > 8 or re.match(r"(?:the|my|a|an|your)$", head, re.I) or re.match(r"(?:i|we|you|it|this|that|what|there)\b", head, re.I):
        return None
    rest0 = (m.group("rest") or "").strip()
    if not rest0 and not re.search(r"\b(?:study|learning|practice|training|reading)\s+plan\b", t, re.I):
        return None                        # "plan for friday" is not a study plan; a bare plan needs the word study or a list
    cad = parse_cadence(head)
    dur = parse_duration(head)
    name = head
    if cad and cad["phrase"]:
        name = _strip(name, cad["phrase"])
    if dur:
        name = _strip(name, dur[1])
    name = re.sub(r"\b(?:a|per|each|every) day\b|\bdaily\b|\beveryday\b", " ", name, flags=re.I)
    name = re.sub(r"\b(?:please|a|an|my|the|study|learning|practice)\s*$", "", " ".join(name.split()), flags=re.I).strip(" ,.-")
    if len(name) < 2:
        return None
    rest = m.group("rest") or ""
    rest = re.sub(r"(?<=\S)\s+(?=\d+[.)]\s)", "\n", rest)         # "1. a 2. b" on one line
    raw = re.split(r"[\n;]+", rest) if re.search(r"[\n;]", rest) else re.split(r",|\bthen\b", rest)
    items = []
    for r in raw:
        r = re.sub(r"^\s*(?:\d+[.)]|[-*•])\s*", "", r).strip(" .")
        if r:
            items.append(r[:140])
    return {"name": name[:80], "items": items[:300], "cad": cad, "minutes": dur[0] if dur else None}


def looks_like_task(text: str) -> bool:
    if parse_plan(text):
        return True                        # "study plan for tryhackme: ..." sets up a repeating plan

    t = unpolite(text)
    if re.match(r"\s*remind me (?:where|what|how far|which)\b", t, re.I) or reminders_qa.parse(t):
        return False                       # "remind me where I was" asks; "cancel reminder ..." manages reminders
    tm = TRIGGER_RE.match(t)
    if tm and NOT_TASK_REST.match(t[tm.end():]):
        return False                       # "I need to know what's due friday"
    if park.parse(t) is not None:
        # "put tryhackme for one hour a day in the playground" repeats, so it is a repeating item, not a parked idea.
        # Only an explicit "park ..." or "idea: ..." stays an idea.
        if not (parse_cadence(t) and not re.match(r"\s*(?:park\b|idea\b)", t, re.I) and not _is_question(t)):
            return False
    if not t or len(t) > 240 or "\n" in t or _is_question(t):
        return False
    if EDIT_SHAPED.match(t) or _code_work(t) or _writing_work(t):
        return False                       # an edit of a card, or coding or writing work (checked after "remind me to"): not a to-do
    if TRIGGER_RE.match(t):
        return True
    if NEED_A.match(t) and not NEED_NOT.search(t) and not MODEL_WORK.match(t):
        return True                        # "need a haircut", "i need a new keyboard"
    if MODEL_WORK.match(t):
        return False                       # "write a function ... weekdays ..." is a job for a model, not a repeating item
    if parse_cadence(t):
        return True                        # "do tryhackme for one hour a day": anything said with a repeat is a repeating item
    low = t.lower()
    if ERRAND.match(t) and len(t.split()) >= 2 and not re.search(r"\b(?:is|are|was|were|has|have|had|will be)\b", low):
        return True                        # "call mom", but not a statement like "email drafts are in my inbox"
    if PROJECT_PHRASE.match(t):
        return True                        # "do giannas bday python project": a project to remember, never a job for a model
    starts = any(low.startswith(v + " ") for v in ACTION_VERBS)
    return starts and (_has_date_word(t) or bool(COURSE_WORDS.search(t)) or bool(CHECKIN_STRICT.search(t)))   # "complete the lab, check in with me"


def _time_of(t: str):
    """Returns (hour, minute, matched_text) or None."""
    m = re.search(r"\b(?:at |by |@ ?)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", t, re.I)
    if m:
        h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower()
        if 1 <= h <= 12 and mi <= 59:
            return (h % 12) + (12 if ap == "pm" else 0), mi, m.group(0)
    m = re.search(r"\b(?:at |by )?(noon|midnight)\b", t, re.I)
    if m:
        return (12 if m.group(1).lower() == "noon" else 23), (0 if m.group(1).lower() == "noon" else 59), m.group(0)
    m = re.search(r"\bat (\d{1,2}):(\d{2})\b", t, re.I)
    if m and int(m.group(1)) < 24 and int(m.group(2)) <= 59:
        return int(m.group(1)), int(m.group(2)), m.group(0)
    return None


def _date_of(t: str, now: datetime):
    """Returns (date, matched_text) or None. Date only; time is applied separately."""
    today = now.date()
    low = t.lower()
    m = re.search(r"\b(?:by |on |before |due |for )?(today|tonight)\b", low)
    if m:
        return today, m.group(0)
    m = re.search(r"\b(?:by |on |before |due |for )?tomorrow\b", low)
    if m:
        return today + timedelta(days=1), m.group(0)
    m = re.search(r"\b(?:by |on |before |due |for )?this weekend\b", low)
    if m:
        return today + timedelta(days=(5 - today.weekday()) % 7), m.group(0)
    m = re.search(r"\b(?:by |on |before |due |for )?next week\b", low)
    if m:
        return today + timedelta(days=7 - today.weekday()), m.group(0)
    m = re.search(r"\bin (\d{1,4}) (day|week)s?\b", low)
    if m:
        return today + timedelta(days=int(m.group(1)) * (7 if m.group(2) == "week" else 1)), m.group(0)
    m = re.search(r"\b(?:by |on |before |due |for )?(next |this )?(" + "|".join(WEEKDAYS) + r")\b", low)
    if m:
        wd = WEEKDAYS.index(m.group(2))
        delta = (wd - today.weekday()) % 7
        if m.group(1) == "next " and delta < 7:
            delta += 7 if delta else 7
        if delta == 0 and m.group(1) != "this ":
            delta = 7                      # "Friday" said on a Friday means next Friday
        return today + timedelta(days=delta), m.group(0)
    m = re.search(r"\b(?:by |on |before |due |for )?the (3[01]|[12]\d|[1-9])(?:st|nd|rd|th)\b(?! of)", low)
    if m:
        day = int(m.group(1))
        for add in (0, 1, 2):
            mon = (today.month - 1 + add) % 12 + 1
            yr = today.year + ((today.month - 1 + add) // 12)
            try:
                d = today.replace(year=yr, month=mon, day=day)
            except ValueError:
                continue
            if d >= today:
                return d, m.group(0)
    m = re.search(r"\b(?:by |on |before |due |for )?(1[0-2]|0?[1-9])/(3[01]|[12]\d|0?[1-9])\b", low)
    if m:
        try:
            d = today.replace(month=int(m.group(1)), day=int(m.group(2)))
        except ValueError:
            return None
        if d < today:
            d = d.replace(year=d.year + 1)
        return d, m.group(0)
    m = re.search(r"\b(?:by |on |before |due |for )?(" + MONTH_RE + r")\.? (\d{1,2})(?:st|nd|rd|th)?\b", low)
    if m:
        mon = next(i for i, name in enumerate(MONTHS, 1) if name.startswith(m.group(1)[:3]))
        day = int(m.group(2))
        try:
            d = today.replace(month=mon, day=day)
        except ValueError:
            return None
        if d < today:
            d = d.replace(year=d.year + 1)
        return d, m.group(0)
    return None


def _strip(text: str, piece: str) -> str:
    i = text.lower().find(piece.lower())
    return (text[:i] + " " + text[i + len(piece):]) if i >= 0 else text


ALSO_TEXT = re.compile(r"[\s,]*\b(?:and|&|plus|then)\s+(?:also\s+)?(?:remind|text|ping|nudge) me\b(?: (?:about it|of it|then|too))?|[\s,]*\balso (?:remind|text|ping|nudge) me\b(?: (?:about it|of it|then|too))?", re.I)
_EXTRA_DAYS: list = []                 # extra dates from "tomorrow and wednesday", set by the last parse_due call


def parse_due(text: str, now: datetime):
    """Returns (iso_due_or_None, text_without_the_date_and_time_words).
    "tomorrow and wednesday" keeps the earliest day as the due date; the later ones go to _EXTRA_DAYS."""
    rest = text
    _EXTRA_DAYS.clear()
    d = _date_of(rest, now)
    if d:
        found = [d]
        rest2 = _strip(rest, d[1])
        for _ in range(4):
            nxt = None
            # a connector directly followed by another date phrase
            for cm in re.finditer(r"\s*(?:,|&|\band\b|\bthen\b|\bplus\b)\s+", rest2, re.I):
                tail = rest2[cm.end():]
                d2 = _date_of(tail, now)
                if d2 and tail.lower().startswith(d2[1].lower()):
                    nxt = (d2, cm.start(), cm.end() + len(d2[1]))
                    break
            if not nxt:
                break
            found.append(nxt[0])
            rest2 = (rest2[:nxt[1]] + " " + rest2[nxt[2]:])
        if len(found) > 1:
            found.sort(key=lambda x: x[0])
            _EXTRA_DAYS.extend(x[0] for x in found[1:])
            d = found[0]
        rest = rest2
    tm = _time_of(rest)
    if tm:
        rest = _strip(rest, tm[2])
    if not d and not tm:
        return None, text
    hour, minute = (tm[0], tm[1]) if tm else (12, 0)
    date = d[0] if d else now.date()
    try:
        due = datetime(date.year, date.month, date.day, hour, minute, tzinfo=now.tzinfo)
    except (ValueError, OverflowError):
        return None, text
    if not d and tm and due < now:
        due += timedelta(days=1)          # a bare time already past today means tomorrow
    return due.isoformat(timespec="minutes"), rest


def guess_list(text: str, lists: list[str]):
    low = text.lower()
    for name in sorted(lists, key=len, reverse=True):
        if re.search(r"\b" + re.escape(name.lower()) + r"\b", low):
            return name, name
    if re.search(r"\bplayground\b|\bside projects?\b", low):
        hit = next((l for l in lists if l.lower() == "play"), None)
        if hit:
            return hit, "playground"
    for pat, want in KEYWORD_LISTS:
        if re.search(pat, low):
            hit = next((l for l in lists if l.lower() == want.lower()), None)
            if hit:
                return hit, None
    if PROJECT_PHRASE.match(text):
        hit = next((l for l in lists if l.lower() in ("side projects", "play")), None)
        if hit:
            return hit, None               # no Side Projects list yet: projects still land in Play
    return None, None


# The list a task joins when its sector is open and the words name no list. Only sectors with one clear home:
# Schoolwork has two course lists, so it keeps asking.
DEFAULT_LIST_OF_CLUSTER = {"play": "Play", "personal": "Personal", "intern": "Internships", "security": "Security Projects"}


def _sector_default(sector: str | None, lists: list[str]) -> str | None:
    want = DEFAULT_LIST_OF_CLUSTER.get(str(sector or "").lower())
    if not want:
        return None
    return next((l for l in lists if l.lower() == want.lower()), None)


def _clean_title(text: str, list_name_hit: str | None, strip_do: bool = False) -> str:
    t = " ".join(text.split())
    t = TRIGGER_RE.sub("", t, count=1)
    t = re.sub(r"^(?:to )(?=do\b)", "", t, flags=re.I) if strip_do else t
    t = re.sub(r"^\s*(?:(?:at|by|on|for)\s+)?(?:to|about|that i(?: need to| should)?)\s+(?=\S)", "", t, flags=re.I) if not strip_do else t
    if strip_do:
        t = re.sub(r"^(?:please )?(?:i want to |i'd like to |let's |lets )?do (?=\S)", "", t, flags=re.I)
    t = re.sub(r"\s+(?:for|about|around)\s*$", "", t, flags=re.I)
    t = re.sub(r"\b(?:to|on|in|onto) (?:my |the )?(?:to-?do |task )?(?:list|todo|to-do)\b", " ", t, flags=re.I)
    t = re.sub(r"\bfor (?:my |the )?(?:to-?do )?list\b", " ", t, flags=re.I)
    t = re.sub(r"\bto my list\b", " ", t, flags=re.I)
    t = re.sub(r"\b(?:in|to|for|on|into) (?:my |the )?(?:playground|side projects?)\b", " ", t, flags=re.I)
    if list_name_hit:
        t = re.sub(r"\b(?:in|to|for|on) (?:my |the )?" + re.escape(list_name_hit) + r"(?: list)?\b", " ", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" ,.;:-")
    t = re.sub(r"\b(by|on|before|due|for|at)$", "", t, flags=re.I).strip(" ,.;:-")
    return (t[:1].upper() + t[1:]) if t else ""


def _plan_proposal(pl, text, lists):
    days = (pl["cad"] or {}).get("days") or list(range(7))
    label = (pl["cad"] or {}).get("label") or "daily"
    play = next((l for l in lists if l.lower() == "play"), None)
    return {"id": "cap-" + uuid.uuid4().hex[:8], "text": text, "title": pl["name"][:1].upper() + pl["name"][1:], "list": play, "due": None,
            "lists": list(lists), "why": "a study plan repeats and lives in Play unless you pick another list", "notes": "", "mode": "task",
            "habit": {"days": days, "nudgeAt": (pl["cad"] or {}).get("nudgeAt") or "17:00", "label": label, "minutes": pl["minutes"]},
            "plan": pl["items"], "cluster": "play"}


# "complete tier 1 by monday, check in with me every day": a due task that also wants daily check-ins until then
CHECKIN_WORDS = re.compile(r"\bcheck(?:ing)?[- ]?(?:in|up)(?: with| on)? me\b|\bremind(?:s|ing)? me\b|\b(?:nudge|ping|text) me\b|\bkeep me honest\b|"
                           r"\buntil (?:then|it'?s done|it is done)\b|\bbefore (?:then|it'?s due|it is due)\b", re.I)
CHECKIN_PHRASE = re.compile(r"[,;]?\s*(?:and |but |also |then )?(?:please )?(?:(?:remind|check in with|check up on|check on|nudge|ping|text) me|"
                            r"keep (?:reminding|checking in with|nudging) me|check(?:ing)?[- ]?(?:in|up)(?: with| on)? me|keep me honest)"
                            r"(?: about it| on it| on me)?", re.I)
UNTIL_PHRASE = re.compile(r"\b(?:until (?:then|it'?s done|it is done|i(?:'m| am) done)|before (?:then|it'?s due|it is due|the deadline))\b", re.I)


# wording that asks for check-ins by itself, with no "every day" needed ("nudge me until then", "check in with me")
CHECKIN_STRICT = re.compile(r"\bcheck(?:ing)?[- ]?(?:in|up)(?: with| on)? me\b|\bkeep me honest\b|"
                            r"\buntil (?:then|it'?s done|it is done)\b|\bbefore (?:then|it'?s due|it is due)\b", re.I)
NO_DUE_HINT = "No due date, so no check-ins yet. Say when it's due (by friday) and I'll check in daily."


def checkin_split(head: str, now: datetime):
    """(cadence, due, rest) when a sentence has a due date and asks for check-ins (a daily rhythm is the default); else None."""
    cad = parse_cadence(head)
    if cad and not CHECKIN_WORDS.search(head):
        return None
    if not cad:
        if not CHECKIN_STRICT.search(head):
            return None
        cad = {"days": list(range(7)), "nudgeAt": DEFAULT_NUDGE, "phrase": None, "label": "daily"}
    rest = _strip(head, cad["phrase"]) if cad["phrase"] else head
    rest = re.sub(r"\b(?:a|per|each|every) day\b|\bdaily\b", " ", rest, flags=re.I)
    rest = CHECKIN_PHRASE.sub(" ", rest)
    rest = UNTIL_PHRASE.sub(" ", rest)
    rest = re.sub(r"\buntil\b", "by", rest, flags=re.I)
    due, rest2 = parse_due(rest, now)
    if not due:
        return None
    if _time_of(head):                      # a time next to a due day is the due time; the nudge keeps its usual hour
        cad = dict(cad, nudgeAt=DEFAULT_NUDGE)
    return cad, due, rest2


WAKE = re.compile(r"^\s*(?:please\s+)?wake me(?: up)?(?=\s+(?:at|by|around|tomorrow|in)\b)", re.I)     # "wake me at 7am": a text, never a snooze
# a remark, not a to-do, even inside an open sector: "I had no idea about the outage", "it keeps crashing"
# a question said without a "?": "any exams today", "anything due tomorrow", "is there a quiz"
ASKS = re.compile(r"^\s*(?:any|anything|is there|are there|do i|did i|have i|am i|got any|how many|how much)\b", re.I)
STATEMENT_START = re.compile(r"^\s*(?:i|i'm|im|i've|i'd|i was|we|we're|it|it's|its|that|that's|there|there's|he|she|they|you|this is)\b", re.I)


def _asks_project_status(text: str) -> bool:
    """Where-was-I and status questions belong to play/project_status.py (the same rule the runner applies after capture)."""
    play_dir = str(Path(__file__).resolve().parent.parent / "play")
    if play_dir not in sys.path:
        sys.path.append(play_dir)
    import project_status
    t = unpolite(text)
    return bool(project_status.parse_intent(t) or project_status.is_bare(t))


def _schedule_question(text, tasks, lists, now):
    import intent                            # lazy: intent imports capture lazily too
    return intent.schedule_question(text, tasks, lists, now)


def detect(text: str, lists: list[str], now: datetime | None = None, sector: str | None = None, tasks: list | None = None):
    """A proposal dict, or None when this is not a task.

    `sector` is the cluster id of the sector she has open (e.g. "personal"): when her words name no list,
    the task goes to that sector's own list, so typing inside Personal files into Personal."""
    now = now or datetime.now().astimezone()
    _EXTRA_DAYS.clear()
    text = plain.squash(text)                # one space per run: no rule below can be slowed by a long run of spaces
    if not text or len(text) > 4000 or plain.is_question(text):
        return None                          # a true question never becomes a task ("add buy milk?!")
    if frequency_problem(text):
        return None                          # "0 times a week": the box asks for a real number (intent.before_capture)
    if _asks_project_status(text):
        return None                          # "analyzer status", even inside an open sector, is a project question first
    text = WAKE.sub("remind me to wake up", text, count=1)
    pl = parse_plan(text)
    if pl:
        return _plan_proposal(pl, text, lists)
    if not looks_like_task(text):
        # Inside any open sector, a plain statement is a task: no "add ..." needed (Schoolwork asks which course list).
        t0 = unpolite(text)
        bare = (str(sector or "").lower() in ("school", "intern", "personal", "security", "play") and t0 and len(t0) <= 120 and "\n" not in t0 and not _is_question(t0)
                and not is_model_work(t0) and not EDIT_SHAPED.match(t0) and park.parse(t0) is None and not reminders_qa.parse(t0)
                and not STATEMENT_START.match(t0) and not ASKS.match(t0)
                and not _schedule_question(t0, tasks, lists, now)     # the same detector as with no sector open: "upcoming deadlines"
                and not re.match(r"\s*remind me (?:where|what|how far|which)\b", t0, re.I))
        if not bare:
            return None
    text = unpolite(text)
    head, tail = split_notes(text)
    cad = parse_cadence(text)
    guess, hit = guess_list(text, lists)
    sector_default = _sector_default(sector, lists) if not guess else None
    if sector_default:
        guess, hit = sector_default, None
    ci = checkin_split(head, now)
    hint = None
    if ci:
        due, rest = ci[1], ci[2]
    elif cad:
        cad_in_head = parse_cadence(head)
        dur = parse_duration(head) or parse_duration(tail)
        rest = _strip(head, cad_in_head["phrase"]) if cad_in_head and cad_in_head["phrase"] else head
        if dur and dur[1].lower() in rest.lower():
            rest = _strip(rest, dur[1])
        cad_in_rest = parse_cadence(rest)
        rest = _strip(rest, cad_in_rest["phrase"]) if cad_in_rest else rest
        rest = re.sub(r"\b(?:a|per|each|every) day\b|\bdaily\b", " ", rest, flags=re.I)      # "...monday to friday for an hour a day"
        due = None
        if cad_in_head and _time_of(rest):
            rest = _strip(rest, _time_of(rest)[2])
    else:
        rel = re.search(r"\bin (\d{1,6}) ?(minutes?|mins?|hours?|hrs?)\b", head, re.I)
        if rel:
            n = int(rel.group(1)); mins = n * (60 if rel.group(2).lower().startswith("h") else 1)
            due = (now + timedelta(minutes=mins)).replace(second=0, microsecond=0).isoformat(timespec="minutes")
            rest = _strip(head, rel.group(0))
        else:
            due, rest = parse_due(head, now)
    if not ci and not cad and CHECKIN_STRICT.search(rest):
        # check-in wording with nothing to count down to: never leave it in the title, and say why nothing was set up
        rest = UNTIL_PHRASE.sub(" ", CHECKIN_PHRASE.sub(" ", rest))
        hint = None if due else NO_DUE_HINT
    timed = (bool(cad) and not ci) or bool(rel_found(head)) or bool(_time_of(head))
    title = _clean_title(rest, hit, strip_do=bool(cad) and not ci)
    if len(title) < 2:
        return None
    out = {
        "id": "cap-" + uuid.uuid4().hex[:8], "text": text, "title": title[:200], "list": guess, "due": due,
        "lists": list(lists), "why": ("the sector you're in" if sector_default else "list from your words" if guess else "pick a list"),
        "notes": (tail[:200] if not _EXTRA_DAYS else ("Also on " + ", ".join(x.strftime("%a %b %d") for x in _EXTRA_DAYS) + ("\n" + tail if tail else ""))[:200]),
        "mode": "reminder" if (re.match(r"\s*(?:please )?(?:remind me|reminder\b|(?:text|ping|nudge|message|alert|notify) me|set(?:[- ]?up)? (?:a |an )?(?:reminder|alarm))", text, re.I) and (timed or (due and _EXTRA_DAYS and re.match(r"\s*(?:please )?remind me\b", text, re.I)))) else "task",
    }
    also = ALSO_TEXT.search(out["title"]) or ALSO_TEXT.search(rest or "")
    if also and out["mode"] == "task":
        out["alsoText"] = True               # "add X and remind me": the task AND a text on the due day(s)
        if due:                              # the texts go out on the due day(s); a day with no time named starts at 9 AM
            hh = due if (_time_of(head) or rel_found(head)) else due[:11] + "09:00" + due[16:]
            out["textAt"] = [hh]
        out["title"] = " ".join(ALSO_TEXT.sub(" ", out["title"]).split()).strip(" ,.;:-") or out["title"]
    if out["mode"] == "reminder" and due and not _time_of(head) and not rel_found(head):
        due = out["due"] = due[:11] + "09:00" + due[16:]          # a text for a day (no time given) starts at 9 AM; follow-ups come from play.apply
    if _EXTRA_DAYS and due:
        t0 = datetime.fromisoformat(due)
        out["extraDue"] = [datetime(x.year, x.month, x.day, t0.hour, t0.minute, tzinfo=t0.tzinfo).isoformat(timespec="minutes") for x in _EXTRA_DAYS]
        if out.get("textAt"):
            t1 = datetime.fromisoformat(out["textAt"][0])
            out["textAt"] += [datetime(x.year, x.month, x.day, t1.hour, t1.minute, tzinfo=t1.tzinfo).isoformat(timespec="minutes") for x in _EXTRA_DAYS]
        if out["mode"] == "reminder":
            out["notes"] = tail[:200]
    if hint:
        out["hint"] = hint
    if ci:
        out["checkin"] = {"days": ci[0]["days"], "nudgeAt": ci[0]["nudgeAt"], "label": ci[0]["label"], "until": due[:10]}
    elif cad:
        out["habit"] = {"days": cad["days"], "nudgeAt": cad["nudgeAt"], "label": cad["label"], "minutes": dur[0] if dur else None}
        if not guess:
            out["list"] = next((l for l in lists if l.lower() == "play"), None)
            out["why"] = "repeating items live in Play unless you pick another list"
        out["cluster"] = CLUSTER_OF_LIST.get((out["list"] or "play").lower(), "play")
    return out
