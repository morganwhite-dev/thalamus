"""Pure routing rules (no I/O): Step 0 patterns, Step 1 tags, Step 3 tier table.
Every rule here mirrors 'Model routing' in priority-brain/CLAUDE.md."""

from __future__ import annotations

import re
from dataclasses import dataclass

TIERS = ["free", "haiku", "sonnet", "opus"]
EFFORTS = ["low", "medium", "high", "xhigh", "max"]

# ---------------------------------------------------------------- Step 0
_NOW = re.compile(
    r"^\s*(what|wat|whats|what's)\s*(should|do|can)?\s*(i|we)?\s*(be\s+)?(do|doing|work\s+on|focus\s+on)?"
    r"\s*(right\s+)?(now|next|today)\s*\??\s*$"
    r"|^\s*what\s+(do|should)\s+i\s+(need\s+to\s+)?(be\s+)?(do|doing)(\s+(right\s+)?(now|next|today))?\s*\??\s*$"
    r"|^\s*(what'?s|whats|what\s+is)\s+next\s*\??\s*$"
    r"|^\s*what\s+(am\s+i|are\s+we)\s+(supposed|meant|going)\s+to\s+(be\s+)?(do|doing|work\s+on|working\s+on)(\s+(right\s+)?(now|next|today))?\s*\??\s*$"
    r"|^\s*what\s+do\s+i\s+have\s+to\s+do(\s+(right\s+)?(now|next|today))?\s*\??\s*$"
    r"|^\s*what\s+now\s*\??\s*$",
    re.I,
)
_DUE = re.compile(r"^\s*(what'?s|whats|what\s+is|what\s+are|anything)\s+(is\s+)?due\b(?P<rest>.*)$", re.I)


@dataclass
class Step0:
    query: str          # "now" | "due"
    window: str | None  # "today", "tomorrow", "this week", ... (raw text)


def match_step0(text: str) -> Step0 | None:
    t = text.strip()
    if _NOW.match(t):
        return Step0("now", None)
    m = _DUE.match(t)
    if m:
        rest = m.group("rest").strip(" ?.!").lower()
        return Step0("due", rest or None)
    return None


# ---------------------------------------------------------------- Step 1
_TAG = re.compile(r"(?<![\w@])@(free|haiku|sonnet|opus)\b(?:\s+(low|medium|high|xhigh|max)\b)?", re.I)


@dataclass
class Override:
    tier: str
    effort: str | None   # None = tier default (free has none)
    text: str            # task with the tag removed


def parse_override(text: str) -> Override | None:
    m = _TAG.search(text)
    if not m:
        return None
    tier = m.group(1).lower()
    effort = (m.group(2) or "").lower() or None
    if tier == "free":
        effort = None  # free models run without an effort setting
    stripped = (text[: m.start()] + text[m.end():]).strip()
    stripped = re.sub(r"\s{2,}", " ", stripped)
    return Override(tier, effort, stripped)


# ---------------------------------------------------------------- Step 3
@dataclass
class Answers:
    """Rubric answers. q1..q7 are the plan's questions; the two helpers are facts
    the tier table refers to ('several files', 'small function/test from a clear spec')."""
    q1_big: bool = False          # >1 file or >~20 lines
    q2_design: bool = False       # design/architecture decision
    q3_unclear: bool = False      # cause or approach unclear
    q4_risky: bool = False        # security, payments, deleting/rewriting real data, hard to undo
    q5_multistep: bool = False    # several tool steps in a row
    q6_longform: bool = False     # long-form writing
    q7_judgment: bool = False     # reasoning-heavy priority/planning judgment
    multi_file: bool = False      # helper: more than one file
    small_spec: bool = False      # helper: small function/test from a clear spec


@dataclass
class TierDecision:
    tier: str
    effort: str | None
    rule: str


def bump(effort: str | None, cap: str = "high") -> str | None:
    """One level up, never past `cap` (xhigh/max are tag-only)."""
    if effort is None:
        return None
    i, top = EFFORTS.index(effort), EFFORTS.index(cap)
    return EFFORTS[i + 1] if i < top else effort


def start_tier(a: Answers, default_effort: dict) -> TierDecision:
    """First matching row wins, top to bottom."""
    if a.q4_risky or a.q2_design or a.q7_judgment or (a.q3_unclear and a.multi_file):
        why = [n for n, v in (("Q4 risky", a.q4_risky), ("Q2 design", a.q2_design),
                              ("Q7 judgment", a.q7_judgment),
                              ("Q3 unclear + several files", a.q3_unclear and a.multi_file)) if v]
        return TierDecision("opus", default_effort["opus"], "row 1: " + ", ".join(why))
    if a.q1_big or a.q3_unclear or a.q6_longform or (a.q5_multistep and a.multi_file):
        why = [n for n, v in (("Q1 big", a.q1_big), ("Q3 unclear", a.q3_unclear), ("Q6 long-form", a.q6_longform),
                              ("Q5 multi-step + several files", a.q5_multistep and a.multi_file)) if v]
        effort = default_effort["sonnet"]
        if a.q3_unclear:
            effort = bump(effort)
            why.append("effort +1 for Q3")
        return TierDecision("sonnet", effort, "row 2: " + ", ".join(why))
    if a.q5_multistep or a.small_spec:
        why = "Q5 multi-step, one or two files" if a.q5_multistep else "small function/test from a clear spec"
        return TierDecision("haiku", default_effort["haiku"], "row 3: " + why)
    return TierDecision("free", None, "row 4: small mundane task")


# ------------------------------------------------------------ escalation
def next_tier(tier: str) -> str:
    """One tier at a time. Never skips a tier, so nothing jumps straight to Opus."""
    i = TIERS.index(tier)
    if i + 1 >= len(TIERS):
        raise ValueError("no tier above opus")
    return TIERS[i + 1]
