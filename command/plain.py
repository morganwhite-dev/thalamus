"""Spell out the shorthand people type (tmrw, whats, im, hw) so every rule sees the same words. Plain code."""
from __future__ import annotations

import re
import unicodedata

_SWAPS = [
    (r"tmrw|tmr|tmw|tmmrw|2morrow|2mrw|tomorow|tommorow|tommorrow|tomorro", "tomorrow"),
    (r"2day|tdy", "today"), (r"2nite|tonite|2night", "tonight"), (r"hw", "homework"), (r"rn", "right now"),
    (r"wk", "week"), (r"pls|plz", "please"), (r"thx|ty|thanx", "thanks"), (r"idk", "i don't know"), (r"dunno", "don't know"),
    (r"wanna", "want to"), (r"gonna", "going to"), (r"gotta", "have to"), (r"lemme", "let me"), (r"gimme", "give me"),
    (r"u", "you"), (r"ur", "your"), (r"abt", "about"), (r"asap", "as soon as possible"),
    (r"im", "i'm"), (r"ive", "i've"), (r"dont", "don't"), (r"cant", "can't"), (r"didnt", "didn't"), (r"isnt", "isn't"),
    (r"doesnt", "doesn't"), (r"havent", "haven't"), (r"wasnt", "wasn't"), (r"shouldnt", "shouldn't"),
    (r"wut|wat|wht|whut", "what"), (r"wats|whatz|watsup", "what's"), (r"shud|shld|shuld", "should"), (r"whatchu|watchu", "what do you"),
    (r"doin", "doing"), (r"workin", "working"), (r"startin", "starting"), (r"goin", "going"), (r"gettin", "getting"), (r"lookin", "looking"),
    (r"tryna", "trying to"), (r"bc|cuz|cus|cos", "because"), (r"b4", "before"), (r"bout", "about"), (r"kinda", "kind of"), (r"sorta", "sort of"),
    (r"wknd|wkend", "weekend"), (r"msg", "message"), (r"appt|appt\.", "appointment"), (r"nxt", "next"), (r"alr", "alright"), (r"lil", "little"),
    (r"w/o", "without"), (r"w/", "with"), (r"w", "with"),
    (r"fri|fri\.", "friday"), (r"tues|tue\.", "tuesday"), (r"thurs|thur|thu\.", "thursday"), (r"weds", "wednesday"),
    (r"wont", "won't"), (r"couldnt", "couldn't"), (r"wouldnt", "wouldn't"), (r"hasnt", "hasn't"), (r"arent", "aren't"), (r"youre", "you're"),
    (r"whats", "what's"), (r"wheres", "where's"), (r"hows", "how's"), (r"whens", "when's"), (r"thats", "that's"), (r"lets", "let's"),
]
_DAYS = {'mon': 'monday', 'tue': 'tuesday', 'wed': 'wednesday', 'sat': 'saturday', 'sun': 'sunday'}
_RX = [(re.compile(r"(?<![\w@./'-])(?:" + a + r")(?![\w'-]|\.\w)", re.I), b) for a, b in _SWAPS]


_STRETCH = re.compile(r"(?<![\w@./'-])([A-Za-z][a-z]*)(?![\w@/'-]|\.\w)")


def _unstretch(m):
    w = m.group(1)
    if len(set(w.lower())) == 1 or not re.search(r"([a-z])\1{2,}", w):
        return w                      # no stretched letter, or a word made of one letter (aaa, zzz)
    return re.sub(r"([a-z])\1{2,}", r"\1", w)


# ------------------------------------------------------------------ shared guards (one per family, used before every writer)
_SPACES = re.compile(r"[^\S\n]+")
_LINES = re.compile(r" ?\n[ \n]*")
_RUNS = re.compile(r"([?!.,:;\-])(?:\s*\1){3,}")
_MIXED = re.compile(r"[?!.,:;]{4,}")
# what may follow the "?" that makes a question: more ! ? . , spaces, closing quotes or brackets, and emoji (anything that is not a letter or digit)
LEAD = re.compile(r"^(?:(?:hey|hi|hello|yo|ok|okay|so|oh|um+|uh+|hmm+|well|alright|also|and|but|actually|btw|k|kk|sorry|excuse me|thalamus)\b[,.!:;\s-]*)+", re.I)
_REQUEST = re.compile(r"^(?:please\s+)?(?:can|could|would|will)\s+you\b(?!\s+(?:be|believe|imagine|guess|tell if|explain why)\b)", re.I)


def _question_marks() -> str:
    """Every character Unicode calls a question mark (Arabic "؟", Greek ";", Armenian, Ethiopic, reversed, double, full-width...), except
    the opening Spanish "¿". Found once, by name, so none is missed."""
    out = []
    for cp in range(0x2FFFF):
        if cp != 0xBF and "QUESTION MARK" in unicodedata.name(chr(cp), ""):
            out.append(chr(cp))
    return "".join(out)


_QMARKS = re.compile("[" + re.escape(_question_marks()) + "]")
_OPEN_Q = re.compile(r"\u00bf(?=[^\w]*$)")                     # a Spanish "¿" with no letter after it is a question mark at the end


def fold(text: str) -> str:
    """Every question mark in any script becomes "?", then NFKC folds every full-width or compatibility form once ("？" -> "?",
    "ｓｋｉｐ" -> "skip", "：" -> ":"). squash() starts with this, and every rule reads squashed or normalized text, so no rule
    ever sees a question mark it does not know."""
    t = _OPEN_Q.sub("?", _QMARKS.sub("?", text or ""))
    return unicodedata.normalize("NFKC", t)


# a word is letters and digits; "c++", "c#", "f#" (up to three letters, then + or #) and ".net" (a dot that starts a word) keep their symbols
_WORD = re.compile(r"(?<![^\W_])\.[^\W_]+|[^\W\d_]{1,3}(?:\+\+|\+|#)(?![^\W_])|[^\W_]+")


def words(text: str) -> list[str]:
    """The words of a name, compared on their real characters (NFKC, casefolded): 'Lab 7' -> ['lab', '7'], '買い物' -> ['買い物']."""
    return _WORD.findall(unicodedata.normalize("NFKC", text or "").casefold())


def squash(text: str) -> str:
    """One space for every run of spaces or tabs, one newline for every run of blank lines, and a run of the same mark cut to three.
    Every rule sees this shape, so no pattern can be made slow by a long run of spaces or punctuation."""
    t = _SPACES.sub(" ", fold(text))
    t = _LINES.sub("\n", t)
    t = _RUNS.sub(lambda m: m.group(1) * 3, t)
    return _MIXED.sub(lambda m: "?!" if "?" in m.group(0) else m.group(0)[:3], t).strip()


def strip_lead(text: str) -> str:
    """'hey, could you skip this?' -> 'could you skip this?' (greetings and filler words in front)."""
    t = squash(text)
    return LEAD.sub("", t, count=1).strip() or t


def is_request(text: str) -> bool:
    """'could you skip this?', 'hey, can you pin this?!', 'please would you snooze it': a polite request, which acts."""
    return bool(_REQUEST.match(strip_lead(text)))


def _qmark(t: str) -> int:
    """Index of the "?" that makes t a question, or -1. The tail after the last letter or digit is read once from the right
    (linear in the length, whatever marks it holds): a "?" anywhere in that tail makes a question ('skip this?!', 'this? 🙂', 'this?"')."""
    i = len(t)
    while i and not (t[i - 1].isalnum() or t[i - 1] == "_"):
        i -= 1
    return t.find("?", i)


def ends_question(text: str) -> bool:
    """A question mark at the end, with any mix of ! . spaces, emoji or closing quotes after it ('skip this?!', 'skip this? 🙂', 'skip this?"')."""
    t = squash(text)
    return bool(t) and _qmark(t) >= 0


def is_question(text: str) -> bool:
    """A true question: question-shaped at the end and not a polite request. A true question never writes anything."""
    return ends_question(text) and not is_request(text)


def strip_question(text: str) -> str:
    """'skip this?! 🙂' -> 'skip this' (the question tail removed)."""
    t = squash(text)
    q = _qmark(t)
    return t[:q].rstrip(" .,!") if q >= 0 else t


_POLITE = re.compile(r"^(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+|kindly\s+)?", re.I)
_TAIL_FLUFF = re.compile(r"(?:[\s,]+(?:please|pls|plz|thanks|thank you|ty|for me))+$", re.I)


def strip_tail(text: str, fluff: bool = True) -> str:
    """Trailing marks, emoji and (fluff=True) "please" / "thanks" off the end: 'skip this? 🙏' -> 'skip this', 'pin lab 7 please 🙂' -> 'pin lab 7'."""
    t = squash(text)
    i = len(t)
    while i and not (t[i - 1].isalnum() or t[i - 1] in "_)]\"'”’+#%*"):
        i -= 1
    t = t[:i].rstrip(" \"'”’")
    return (_TAIL_FLUFF.sub("", t).strip() or t) if fluff else t


def request_body(text: str) -> str:
    """What a polite request asks for: greetings, "could you (please)" and the tail marks and "please" removed.
    'Hey, could you please park this idea: a birdhouse? 🙏' -> 'park this idea: a birdhouse'. Use it only after is_question()
    said no (a true question never acts)."""
    t = strip_lead(text)
    t = _POLITE.sub("", t, count=1).strip() or t
    return strip_tail(t)


# ------------------------------------------------------------------ the one target matcher (every writer that picks by name uses it)
NAME_STOP = frozenset({"the", "a", "an", "my", "this", "that", "on", "for", "with", "of", "to", "in", "about", "me", "it", "project", "task",
                       "assignment", "one", "thing", "please", "is", "be"})


def match_target(phrase, items, title=lambda x: x["title"], stop=NAME_STOP):
    """Pick what her words name. -> ("one", item) | ("many", [items]) | ("none", []).
    Words are compared whole, on NFKC + casefolded text ('textbook' is not 'text' + 'book', '买东西' is not '買い物').
    1. Nothing matchable (empty, only marks or emoji, only stop words): never matches, never "all of them".
    2. An exact full title wins (a leading "the" / "my" may be left off), checked before any word is dropped.
    3. Else every content word must be a whole word of the title: one hit is the target, several are the options to ask about."""
    want = words(phrase)
    if not want:
        return "none", []
    items = list(items or [])
    bare = want[1:] if len(want) > 1 and want[0] in ("the", "my") else want
    exact = [x for x in items if words(title(x)) in (want, bare)]
    if exact:
        return ("one", exact[0]) if len(exact) == 1 else ("many", exact)
    ws = {w for w in want if w not in stop}
    if not ws:
        return "none", []
    hits = [x for x in items if ws <= set(words(title(x)))]
    if not hits:
        return "none", []
    return ("one", hits[0]) if len(hits) == 1 else ("many", hits)


def names_title(text, title) -> bool:
    """True when the whole title appears in the text as whole words, in order ('read chapter 5' is not in 'read chapter 55')."""
    want, have = words(title), words(text)
    n = len(want)
    return bool(n) and any(have[i:i + n] == want for i in range(len(have) - n + 1))


def normalize(text: str) -> str:
    """Same sentence with shorthand spelled out. Tags (@free), paths and file names are left alone."""
    t = squash(text)
    if len(t) > 400 or "\n" in t:
        return t                      # long or multi-line input is material for a model, not a command
    for rx, b in _RX:
        t = rx.sub(lambda m, b=b: (b.capitalize() if m.group(0)[:1].isupper() else b), t)
    t = re.sub(r"\bi'?ll (need|have) to\b", r"i \1 to", t, flags=re.I)
    t = re.sub(r"(?<=\s)2(?=\s+(?:do|work|start|be|get|call|email|buy|pay|finish|submit|study|go|take|text|send|make|apply|focus|tackle)\b)", "to", t)
    t = re.sub(r"\b(on|by|this|next|every|until|till|before|for|than) (mon|tue|wed|sat|sun)\b\.?", lambda m: m.group(1) + " " + _DAYS[m.group(2).lower()], t, flags=re.I)
    t = re.sub(r"\b(what|where|who|how|why|when|you|they|we|which) r\b", r"\1 are", t, flags=re.I)
    t = re.sub(r"\b(why|what) y\b", r"\1 why", t, flags=re.I)
    t = _STRETCH.sub(_unstretch, t)                                  # "heyyy", "plsss"; not AAA, AAA.pdf or a4444
    if len(t.split()) >= 3:
        t = re.sub(r"[\s,]+(?:lol|lmao|haha|hahaha|lolol|thanks|thank you)[.!]*$", "", t, flags=re.I)
    return t
