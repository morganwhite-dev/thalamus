"""Plain-language "park this idea" for the command box (Phase 17b). Plain code, no model.

`parse(text)` -> the idea text, "" (asked to park but gave no idea), or None. The idea goes to the Play parking lot (play/play.py "park").
"""
from __future__ import annotations

import re

import plain

WHERE = r"(?:the\s+|my\s+)?(?:playground|parking\s*lot|play(?:\s+side)?|idea\s*(?:box|list|pile))"
# a real idea needs a determiner ("an idea", "a great idea", "another idea"); "no idea", "any idea", "some idea" and "a vague idea" are not ideas.
# "what if I built ..." is a question (it goes to the normal route), never a parked idea.
AN_IDEA = r"(?:an?|another|one\s+more|new)\s+(?!(?:[\w-]+\s+){0,2}?(?:vague|rough|general|faint|slight|fair|clear|basic)\s+idea\b)(?:[\w-]+\s+){0,2}idea\b"
_ON = r"(?:(?:for|to|about)\b|[:,\-])"          # what joins an idea to its words: a whole word or a mark, never the start of a word
PATTERNS = [
    re.compile(r"^\s*(?:please\s+)?(?:park|stash|file|drop|put|save|add)\s+(?:this\s+|that\s+|my\s+|an?\s+)?(?:idea\b\s*)?(?:for\s+|about\s+|:)?\s*(?P<a>.+?)\s+(?:in|into|to|on|for)\s+" + WHERE + r"\s*[.!]?\s*$", re.I),
    re.compile(r"^\s*(?:please\s+)?(?:park|stash|put|save|add|file|drop)\s+(?:this\s+|that\s+|it\s+|my\s+|an?\s+)?(?:idea\b\s*)?(?:in|into|to|on)\s+" + WHERE + r"\s*[:,\-]?\s*(?P<a>.+?)\s*$", re.I),
    re.compile(r"^\s*(?:please\s+)?(?:note|log|jot|write)\s+(?:this\s+|that\s+|down\s+)?idea\b\s*" + _ON + r"?\s*(?P<a>.+?)\s*$", re.I),
    re.compile(r"^\s*(?:i\s+)?(?:just\s+)?(?:thought\s+of|came\s+up\s+with|had|got|have)\s+" + AN_IDEA + r"\s*" + _ON + r"\s*(?P<a>.+?)\s*$", re.I),
    re.compile(r"^\s*(?:i\s+)?(?:just\s+)?(?:thought\s+of|came\s+up\s+with|had|got|have)\s+" + AN_IDEA + r"\s*$", re.I),
    re.compile(r"^\s*(?:please\s+)?(?:park|stash)\b\s*(?:(?:this|that|my|an?)\b\s*)?(?:idea\b\s*)?[:,\-]?\s*(?P<a>.+?)\s*$", re.I),
    re.compile(r"^\s*(?:i\s+(?:have|got|just\s+had|just\s+thought\s+of|'ve\s+got|’ve\s+got)\s+an?\s+idea|(?:new|random|side\s+project)\s+idea|idea)\b\s*" + _ON + r"\s*(?P<a>.+?)\s*$", re.I),
    re.compile(r"^\s*" + WHERE + r"\s*[:\-]\s*(?P<a>.+?)\s*$", re.I),        # "parking lot: smart golf bag tag"
    # "thought" alone is too common ("thought i'd go out later"): only "thought: ..." or "random thought - ..." park
    re.compile(r"^\s*(?:random\s+|shower\s+)?thought\s*[:\-]\s*(?P<a>.+?)\s*$", re.I),
]
_EMPTY = {"the", "a", "an", "it", "all", "this", "that", "these", "those", "them", "everything", "something", "stuff", "things", "my", "idea", "ideas", "of", "and", "or"}
CLEAN = re.compile(r"^(?:that|to|for|about|of|:)\s+", re.I)


def parse(text):
    if "\n" in (text or "").strip():
        return None
    t = plain.squash(text)                   # one space per run: the patterns below stay fast on any input
    if not t or len(t) > 300 or plain.is_question(t):
        return None                          # "park this idea: birdhouse?!" asks; a true question never parks anything
    t = plain.request_body(t)                # "Could you park this idea: a birdhouse?" asks me to do it
    for rx in PATTERNS:
        m = rx.match(t)
        if m:
            if "a" not in m.groupdict():
                return ""
            idea = CLEAN.sub("", m.group("a").strip(" .,:-")).strip()
            if re.fullmatch(r"(?:this|that|it|an? idea|my idea|idea)", idea, re.I) or not set(plain.words(idea)) - _EMPTY:
                return ""                      # clearly "park an idea" but no idea given ("park the", "park it all"): the box asks for it
            if len(idea) >= 3:
                return idea[:140]
    return None
