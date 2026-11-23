"""Step 2: rubric classification.

Order: (a) cache (same text -> same answers, so routing is repeatable),
(b) cheap keyword/size shortcut that can settle obvious small tasks with no model call,
(c) Jev answers the yes/no rubric, (d) if Jev is unreachable, keyword fallback
answers the rubric conservatively and the log says so.
Plain code (rules.start_tier) turns answers into a tier; Jev never picks the tier."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .rules import Answers

TASK_TYPES = ["edit", "code", "summary", "extraction", "explain", "writing", "classify", "other"]

# Each rubric question is asked as a choice with described levels; the levels marked True
# mean "yes". Tested 2026-11-05: Jev's yes/no predicates hovered near 0.5 on borderline tasks
# (e.g. Q1 0.55 for one small function, Q2 0.64 for "add a field"), while described choices
# came back at 0.97-1.0 and matched the intended answers.
# (name, question, [(value, description, counts_as_yes)])
QUESTIONS = [
    ("q1_big", "How much code or text must be written or changed to do this task?", [
        ("tiny", "one line or a rename, a commit message, a short answer", False),
        ("small", "one file, under about 20 lines, e.g. one small function and a short test", False),
        ("medium", "several files, or more than about 20 lines", True),
        ("large", "many files or a substantial feature", True)]),
    ("q2_design", "How much design or architecture choice does the task leave to the assistant?", [
        ("none", "the request says what to build; just follow it or an existing pattern", False),
        ("some", "small local choices only, like naming or a helper's signature", False),
        ("major", "the assistant must choose a schema, data format, structure or approach", True)]),
    ("q3_unclear", "How clear are the cause of the problem and the right approach?", [
        ("clear", "the user says what to do; the approach is obvious", False),
        ("mostly_clear", "only minor details to work out", False),
        ("unclear", "the cause or approach is unknown and needs investigation, or the request is ambiguous", True)]),
    ("q4_risky", "What happens if this task is done wrong?", [
        ("low_risk", "easy to undo; no security, credentials, payments, deployment or real data at stake", False),
        ("high_risk", "touches security, authentication, credentials, payments or deployment, or deletes or "
                      "rewrites real data, or is otherwise hard to undo", True)]),
    ("q5_multistep", "How many tool steps does the task need?", [
        ("one_step", "answer or write it in one go, or make one edit", False),
        ("several_steps", "several tool steps in a row, such as run, edit, then test", True)]),
    ("q6_longform", "What kind of output is requested?", [
        ("code", "code or config", False),
        ("short_text", "a short answer, message, list or short summary", False),
        ("long_prose", "a letter or cover letter, essay, report, study notes or study material, or a summary over a page", True)]),
    ("q7_judgment", "What kind of thinking does the task need?", [
        ("mechanical", "following instructions: editing, writing code or text, looking something up", False),
        ("judgment", "weighing priorities, planning someone's time, or making a personal or strategic decision", True)]),
    # "involve", not "change": an investigation reads several files but may change none, and
    # the old wording split Jev 0.47-0.61 on the sleep/wake bug task; this reads 1.0 every time.
    ("multi_file", "How many files does the task involve, counting files it must read or investigate "
                   "as well as files it changes?", [
        ("none", "no files; an answer from the text given", False),
        ("one", "exactly one file", False),
        ("several", "two or more files", True)]),
    ("small_spec", "Is the task to write one small function, script or test from a clearly stated spec?", [
        ("yes", "one small, clearly specified function, script or test", True),
        ("no", "anything else", False)]),
]

RISK = re.compile(
    r"\b(password|credential|secret|api[ _-]?key|token|auth\w*|log ?in|oauth|payment|billing|invoice|stripe|paypal|"
    r"delete|remove all|drop|truncate|wipe|purge|migrat\w*|force[ -]?push|deploy\w*|production|prod|"
    r"security|vulnerab\w*|encrypt\w*|permission\w*|sudo|rm -rf|chmod|firewall|bank)\b",
    re.I,
)
MUNDANE = re.compile(
    r"^\s*(please\s+)?(rename|fix (the |a |this )?(typo|syntax|indent\w*|spelling)|reformat|format|lint|"
    r"write (a |the )?commit message|commit message for|summari[sz]e|tl;?dr|explain|define|what does|what is|"
    r"translate|tag|categori[sz]e|classify|extract|convert|spell[- ]?check|capitali[sz]e|sort|alphabeti[sz]e|"
    r"shorten|reword|proofread|count)\b",
    re.I,
)
# An ordinary question or small ask ("what is a subnet mask", "how do I undo a git commit", "give me 5 name ideas").
# The answer is text, so risk words like "security" or "delete" in the question do not make it risky.
ASK = re.compile(
    r"^\s*(?:(?:ok|okay|so|hey|please|quick question)[,:\s]+)*(?:what|what's|whats|who|who's|when|where|why|how|which|is|are|was|were|does|do|did|can|could|would|will|"
    r"explain|define|describe|tell me|give me|list|name|translate|spell|quiz me|test me|teach me|show me how|help me understand|i don't understand|i dont understand|"
    r"eli5|remind me (?:what|how)|compare|difference between|what's the difference|pros and cons|break down|walk me through|suggest|recommend)\b", re.I)
SMALL_WRITE = re.compile(r"^\s*(?:please\s+)?(?:write|draft|give)(?: me)? (?:a |an )?(?:short|quick|brief|one[- ]line|two[- ]sentence|1[- ]line|polite)\b", re.I)
# Signs the "question" is really work on her own files or a personal decision: these still go to the classifier.
WORK = re.compile(
    r"\b(?:refactor|implement|debug|deploy|migrate|rewrite|redesign|architect\w*|schema|pipeline|codebase|repo(?:sitory)?|pull request|"
    r"(?:write|draft|compose|create|make|generate|tailor|rewrite|edit|review|fix|improve|update|polish)\b.{0,60}\b(?:cover letter|essay|report|study guide|write[- ]up|resume)|"
    r"my (?:code|script|app|server|build|tests?|program|function|repo|project|import|job|launchd|cron|dashboard|site|website|laptop|mac)|this (?:file|code|error|bug|repo|function|script|stack trace|log)|"
    r"keeps? (?:failing|crashing|breaking)|isn't working|not working|doesn't work|won't (?:run|start|build)|should i (?:take|accept|quit|drop|switch|major|move|apply)|"
    r"plan my (?:week|month|semester|career)|prioriti[sz]e)\b|\b[\w-]+\.(?:py|js|ts|swift|json|html|css|sh|md|ya?ml|sql|csv)\b", re.I)
MULTI_Q = re.compile(r"\b(across|all (the )?(files|modules)|codebase|repo(sitory)?|project-wide|and then)\b", re.I)
MULTI = re.compile(r"\b(files|across|everywhere|all (the )?(files|modules)|codebase|repo(sitory)?|project-wide|and then)\b", re.I)


@dataclass
class Classification:
    answers: Answers
    task_type: str
    source: str                      # cache | shortcut | jev | fallback
    probabilities: dict = field(default_factory=dict)
    note: str = ""

    def to_log(self) -> dict:
        return {"source": self.source, "task_type": self.task_type, "answers": asdict(self.answers),
                "probabilities": self.probabilities, "note": self.note}


def guess_task_type(text: str) -> str:
    t = text.lower()
    table = [
        ("summary", r"\b(summari[sz]e|tl;?dr|recap)\b"),
        ("extraction", r"\b(extract|pull out|list the (dates|names|fields)|parse)\b"),
        ("classify", r"\b(tag|categori[sz]e|classify|label)\b"),
        ("explain", r"\b(explain|what does|what is|define|why does)\b"),
        ("writing", r"\b(letter|email|essay|cover letter|study guide|notes|write up|draft)\b"),
        ("edit", r"\b(rename|typo|syntax|format|lint|reword|proofread|indent)\b"),
        ("code", r"\b(function|script|test|class|bug|refactor|implement|code|\.py|\.js|\.swift)\b"),
    ]
    for name, pat in table:
        if re.search(pat, t):
            return name
    return "other"


def shortcut(text: str, max_chars: int) -> Answers | None:
    """Settle obvious small tasks without Jev. Only ever answers 'all no' (free tier);
    anything with a risk word, several files or length goes to Jev."""
    if len(text) > max_chars or "\n" in text.strip():
        return None
    if (ASK.match(text) or text.strip().endswith("?")) and not WORK.search(text) and not MULTI_Q.search(text):
        return Answers()                  # a plain question: free tier, whatever topic words it contains
    if RISK.search(text) or MULTI.search(text):
        return None
    if MUNDANE.search(text) or (SMALL_WRITE.match(text) and not WORK.search(text)):
        return Answers()
    return None


def fallback_answers(text: str) -> Answers:
    """Used only if Jev is unreachable. Leans toward the higher tier on risk."""
    t = text.lower()
    has = lambda p: re.search(p, t) is not None  # noqa: E731
    multi = bool(MULTI.search(text))
    return Answers(
        q1_big=multi or len(text) > 600,
        q2_design=has(r"\b(design|architect\w*|schema|structure|data model|approach for)\b"),
        q3_unclear=has(r"\b(why|debug|flaky|intermittent|figure out|investigate|not sure|unclear|randomly)\b"),
        q4_risky=bool(RISK.search(text)),
        q5_multistep=has(r"\b(run|test|build)\b.*\b(fix|edit|update|change)\b|\band then\b"),
        q6_longform=has(r"\b(cover letter|letter|essay|study guide|study notes|report|write[- ]up)\b"),
        q7_judgment=has(r"\b(prioriti[sz]e|should i|plan my|which (one )?first|decide)\b"),
        multi_file=multi,
        small_spec=has(r"\b(write|add) (a |one )?(small )?(function|helper|test|script)\b"),
    )


class Classifier:
    def __init__(self, client, cfg: dict, cache_path: Path):
        self.client = client
        self.cfg = cfg
        self.cache_path = cache_path

    def _load_cache(self) -> dict:
        try:
            return json.loads(self.cache_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_cache(self, cache: dict) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(cache, indent=1))

    def classify(self, text: str) -> Classification:
        key = hashlib.sha256(text.strip().encode()).hexdigest()
        cache = self._load_cache()
        if key in cache:
            c = cache[key]
            return Classification(Answers(**c["answers"]), c["task_type"], "cache", c.get("probabilities", {}),
                                  note=f"first classified by {c['source']}")

        sc = shortcut(text, self.cfg.get("shortcut_max_chars", 160))
        if sc is not None:
            result = Classification(sc, guess_task_type(text), "shortcut", note="plain question or small mundane ask, short")
        else:
            try:
                result = self._ask_jev(text)
            except Exception as e:  # network, rate limit, model gone
                return Classification(fallback_answers(text), guess_task_type(text), "fallback",
                                      note=f"Jev unavailable ({str(e)[:120]}); keyword fallback, not cached")

        cache[key] = {"answers": asdict(result.answers), "task_type": result.task_type,
                      "probabilities": result.probabilities, "source": result.source}
        self._save_cache(cache)
        return result

    def _ask_jev(self, text: str) -> Classification:
        cl = self.cfg["classifier"]
        qs = [{"type": "choice", "name": n, "instructions": q,
               "choices": [{"value": v, "description": d} for v, d, _ in levels]} for n, q, levels in QUESTIONS]
        qs.append({"type": "choice", "name": "task_type", "instructions": "What kind of task is this?",
                   "choices": [{"value": v} for v in TASK_TYPES]})
        model = {"id": cl["id"], "providerID": cl["providerID"]}
        prompt = "A user typed this task for an AI assistant:\n\n" + text
        ans = self.client.decisions(model, prompt, qs)
        thr = cl.get("yes_threshold", 0.5)
        band = cl.get("recheck_band", 0.1)

        def p_yes(answer, levels) -> float | None:
            if answer.get("type") != "choice":
                return None
            yes_values = {v for v, _, y in levels if y}
            return sum(p["probability"] for p in answer.get("probabilities", []) if p["value"] in yes_values)

        # Borderline answers (within `band` of the threshold) are asked twice more and averaged,
        # so one wobbly reading can't flip the tier. Jev is free, so this costs nothing.
        levels_by = {n: lv for n, _, lv in QUESTIONS}
        samples = {n: [p] for n in levels_by if (p := p_yes(ans.get(n, {}), levels_by[n])) is not None}
        borderline = [n for n, ps in samples.items() if abs(ps[0] - thr) < band]
        if borderline:
            again = [q for q in qs if q["name"] in borderline]
            for _ in range(2):
                try:
                    extra = self.client.decisions(model, prompt, again)
                except Exception:
                    break
                for n in borderline:
                    p = p_yes(extra.get(n, {}), levels_by[n])
                    if p is not None:
                        samples[n].append(p)

        probs, vals, errors = {}, {}, []
        fb = fallback_answers(text)
        for n, _, levels in QUESTIONS:
            if n in samples:
                avg = sum(samples[n]) / len(samples[n])
                probs[n] = round(avg, 3)
                vals[n] = avg >= thr
            else:  # one question errored: use the keyword answer for that one only
                errors.append(n)
                vals[n] = getattr(fb, n)
        # Safety net: a risk keyword can only raise Q4, never lower it.
        if RISK.search(text) and not vals["q4_risky"] and probs.get("q4_risky", 0) >= 0.25:
            vals["q4_risky"] = True
            errors.append("q4 raised by risk keyword (p>=0.25)")
        tt = ans.get("task_type", {})
        task_type = tt.get("choice") if tt.get("type") == "choice" else guess_task_type(text)
        notes = []
        if borderline:
            notes.append("rechecked borderline: " + ", ".join(
                f"{n} {[round(p, 2) for p in samples[n]]}" for n in borderline))
        if errors:
            notes.append("per-question fallback: " + ", ".join(errors))
        note = "; ".join(notes)
        return Classification(Answers(**vals), task_type, "jev", probs, note)
