"""Quality validator for free-model output.

Layer 1: deterministic, instant, free (empty, refusal, length bounds, format, truncation, grounding).
Layer 2: Jev rubric grading, free. Any 'no' fails.
Layer 3: Haiku audit by sampling (0.1x). Never retries; scores feed model ranking.
Failing layer 1 or 2 counts as a failed attempt."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

REFUSAL = re.compile(
    r"\b(i can'?t|i cannot|i'?m unable|i am unable|i'?m not able|i won'?t be able|as an ai\b|as a language model|"
    r"i'?m sorry,? but|unable to (help|assist|comply)|i do not have access|i don'?t have access)", re.I)
# Agent chatter that leaked into an answer (seen live 2026-11-05: OpenCode's plan agent
# appended "I'm in Plan mode now..." and "Waiting for you to confirm the model switch").
META_CHATTER = re.compile(
    r"\b(plan mode|mode reminder|system[- ]reminder|switch agents|confirm the model switch|"
    r"nothing new came in|waiting for you to confirm)\b", re.I)
MONTHS = {m: m[:3] for m in ["january", "february", "march", "april", "may", "june", "july", "august",
                             "september", "october", "november", "december"]}
MONTHS["sept"] = "sep"
DATE_RE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?)\b", re.I)
TIME_RE = re.compile(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", re.I)
CODE_RE = re.compile(r"\b[A-Z]{2,5}\s?\d{3,4}\b")          # course codes like CIS 8087
NUM_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?%?(?![\w])")  # standalone numbers
FENCE_RE = re.compile(r"```(\w+)?\n(.*?)```", re.S)

# The plan's five rubric questions, asked as described choices (calibration test 2026-11-05:
# choices flagged a wrong date, an invented requirement and unrelated code edits at
# confidence 1.0). (name, question, [(value, description, passes)])
JUDGE_QUESTIONS = [
    ("answers_question", "Does OUTPUT respond to what TASK asked?", [
        ("on_task", "it addresses the request", True),
        ("off_task", "it refuses, hedges, or does something other than what was asked", False)]),
    ("covers_required", "Does OUTPUT do everything TASK asked?", [
        ("fully", "every requested item is done", True),
        ("partly", "some requested item is missing or only half done", False),
        ("no", "it does not do the task", False)]),
    ("no_invented", "Compared with TASK and its source text, does OUTPUT contain invented or changed details?", [
        ("faithful", "every fact in OUTPUT is in the task or source, unchanged, and there are no unrequested changes", True),
        ("changed_or_invented", "OUTPUT changes a fact (date, number, name), adds something not in the source, "
                                "or makes changes nobody asked for", False)]),
    ("format_tone", "Is OUTPUT in the format and tone TASK asked for?", [
        ("matches", "format and tone fit the request (or none was specified)", True),
        ("wrong_format", "wrong format, length or tone for what was asked", False)]),
    ("complete", "Is OUTPUT complete?", [
        ("complete", "it ends properly", True),
        ("cut_off", "it stops part-way, mid-sentence or mid-code", False)]),
]


# Task types whose answer must stay faithful to a source (the task text or SOURCE).
SOURCE_BOUND_TYPES = ("summary", "extraction", "edit")


def is_generative(task_type: str, source: str | None) -> bool:
    """True when the model is asked to come up with new content (tips, a first step, an
    explanation) rather than restate a source. 'Invented details' has no meaning there:
    every good answer adds content the task lacks. Calibration 2026-11-05: Jev gave clean,
    correct study tips and a correct first step no_invented = 0.34-0.37 while passing the
    other four questions at 0.96-1.0; a wrong answer still failed the other four at 0-0.02."""
    return source is None and task_type not in SOURCE_BOUND_TYPES


def judge_questions(task_type: str, source: str | None) -> list:
    if is_generative(task_type, source):
        return [q for q in JUDGE_QUESTIONS if q[0] != "no_invented"]
    return JUDGE_QUESTIONS


@dataclass
class Verdict:
    passed: bool
    failed_layer: int | None = None
    failures: list[str] = field(default_factory=list)
    layer2: dict = field(default_factory=dict)

    def to_log(self) -> dict:
        return {"passed": self.passed, "failed_layer": self.failed_layer, "failures": self.failures,
                "layer2": self.layer2}


# ----------------------------------------------------------------- helpers
def _norm(s: str) -> str:
    s = s.lower().replace(".", "")
    for full, short in MONTHS.items():
        s = re.sub(rf"\b{full}\b", short, s)
    s = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", s)
    s = re.sub(r"\s+", " ", s)
    return s.replace(" pm", "pm").replace(" am", "am").replace(":00", "")


def key_facts(text: str) -> set[str]:
    facts = set()
    for rx in (DATE_RE, TIME_RE, CODE_RE):
        facts |= {_norm(m.group(0)) for m in rx.finditer(text)}
    return facts


def numbers(text: str) -> set[str]:
    return {m.group(0) for m in NUM_RE.finditer(text)}


def strip_fences(text: str) -> str:
    m = FENCE_RE.search(text)
    return m.group(2).strip() if m else text.strip()


def expected_format(task: str) -> str | None:
    t = task.lower()
    if re.search(r"\bjson\b", t):
        return "json"
    if re.search(r"\b(python|\.py)\b", t) and re.search(r"\b(write|fix|function|script|code)\b", t):
        return "python"
    return None


def required_fields(task: str) -> list[str]:
    m = re.search(r"\b(?:fields?|keys?)\s*[:(]?\s*([\w\s,`'\"]+?)(?:\)|\.|$)", task, re.I)
    if not m:
        return []
    parts = re.split(r",|\band\b", m.group(1))
    return [p.strip(" `'\"") for p in parts if p.strip(" `'\"") and len(p.strip()) < 40]


# ----------------------------------------------------------------- layer 1
def layer1(task: str, output: str, task_type: str, source: str | None = None, fields: list[str] | None = None) -> list[str]:
    fails: list[str] = []
    out = output.strip()
    if not out:
        return ["empty output"]
    if REFUSAL.search(out[:300]):
        fails.append("refusal or hedge")
    if META_CHATTER.search(out) and not META_CHATTER.search(task):
        fails.append("agent chatter in answer (e.g. 'plan mode')")

    src =source if source is not None else task
    # length bounds by task type
    if task_type == "summary":
        if source and len(out) >= len(source.strip()):
            fails.append("summary is not shorter than its source")
        if len(out) < 40:
            fails.append("summary is one line or less")
    elif task_type in ("explain", "writing") and len(out) < 20:
        fails.append(f"{task_type} output too short")

    # format
    fmt = expected_format(task)
    if fmt == "json":
        try:
            obj = json.loads(strip_fences(out))
            need = fields if fields is not None else required_fields(task)
            rows = obj if isinstance(obj, list) else [obj]
            for f in need:
                if not all(isinstance(r, dict) and f in r for r in rows):
                    fails.append(f"JSON missing required field '{f}'")
                    break
        except json.JSONDecodeError as e:
            fails.append(f"invalid JSON ({e.msg})")
    elif fmt == "python":
        blocks = [b for lang, b in FENCE_RE.findall(out) if (lang or "python").lower() in ("python", "py")]
        code = blocks[0] if blocks else out
        try:
            compile(code, "<output>", "exec")
        except SyntaxError as e:
            fails.append(f"python does not compile (line {e.lineno}: {e.msg})")

    # truncation
    if out.count("```") % 2 == 1:
        fails.append("truncated (unclosed code fence)")
    elif re.search(r"(,|:|\(|\[|\{|\band|\bthe|\bto|\bof|-)\s*$", out, re.I) and len(out) > 60:
        fails.append("truncated (ends mid-sentence)")
    elif task_type in ("summary", "explain", "writing") and len(out) > 60 and not fmt \
            and not re.search(r"[.!?)\]\"'`*:]\s*$", out):
        fails.append("truncated (prose with no closing punctuation)")

    # grounding (source-bound task types)
    if task_type in ("summary", "extraction", "edit"):
        src_facts, out_facts = key_facts(src), key_facts(out)
        invented = sorted(f for f in out_facts if f not in src_facts)
        if invented:
            fails.append("invented facts not in source: " + ", ".join(invented[:5]))
        invented_nums = sorted(n for n in numbers(out) - numbers(src) if len(n.rstrip("%")) >= 2)
        if invented_nums and not invented:
            fails.append("invented numbers not in source: " + ", ".join(invented_nums[:5]))
        # only summaries must keep key facts; an extraction picks just the requested fields
        if task_type == "summary" and src_facts:
            missing = sorted(src_facts - out_facts)
            allowed = 0 if len(src_facts) <= 5 else int(len(src_facts) * 0.4)
            if len(missing) > allowed:
                fails.append("key facts dropped: " + ", ".join(missing[:5]))
    return fails


# ----------------------------------------------------------------- layer 2
def layer2(client, classifier_cfg: dict, task: str, output: str, source: str | None = None,
           task_type: str = "summary") -> tuple[list[str], dict]:
    """Jev grades a text answer. Returns (failures, probabilities). If Jev is down the layer
    is recorded as skipped, not passed. Generative tasks skip the 'invented details' question."""
    body = f"TASK:\n{task}\n\n" + (f"SOURCE:\n{source}\n\n" if source else "") + f"OUTPUT:\n{output}"
    return _ask_judge(client, classifier_cfg, body, judge_questions(task_type, source))


def _ask_judge(client, classifier_cfg: dict, body: str, questions: list) -> tuple[list[str], dict]:
    qs = [{"type": "choice", "name": n, "instructions": q,
           "choices": [{"value": v, "description": d} for v, d, _ in levels]} for n, q, levels in questions]
    try:
        ans = client.decisions({"id": classifier_cfg["id"], "providerID": classifier_cfg["providerID"]}, body, qs)
    except Exception as e:
        return [], {"skipped": str(e)[:160]}
    thr = classifier_cfg.get("yes_threshold", 0.5)
    probs, fails = {}, []
    for n, _, levels in questions:
        a = ans.get(n, {})
        if a.get("type") != "choice":
            probs[n] = None
            continue
        good = {v for v, _, ok in levels if ok}
        p = sum(x["probability"] for x in a.get("probabilities", []) if x["value"] in good)
        probs[n] = round(p, 3)
        if p < thr:
            fails.append(f"Jev: '{n}' = {a.get('choice')} (p_pass={p:.2f})")
    return fails, probs


def validate(client, cfg: dict, task: str, output: str, task_type: str, source: str | None = None,
             fields: list[str] | None = None, use_jev: bool = True) -> Verdict:
    f1 = layer1(task, output, task_type, source, fields)
    if f1:
        return Verdict(False, 1, f1)
    if not use_jev:
        return Verdict(True)
    f2, probs = layer2(client, cfg["classifier"], task, output, source, task_type)
    if f2:
        return Verdict(False, 2, f2, probs)
    return Verdict(True, None, [], probs)


# ----------------------------------------------------------------- agentic changes
def undefined_names(code: str) -> list[str]:
    """Names read inside a function that are never assigned, imported, a parameter, a
    module-level name or a builtin. Catches half-done renames (e.g. `tmp += i` after
    `tmp` became `total`), which compile fine."""
    import ast
    import builtins
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    module_names = set(dir(builtins))
    # `x += 1` needs x to exist already, so its target counts as a read, not a definition
    aug_targets = {id(n.target) for n in ast.walk(tree) if isinstance(n, ast.AugAssign)}
    aug_reads = {n.target.id for n in ast.walk(tree) if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name)}
    for node in ast.walk(tree):
        if id(node) in aug_targets:
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            module_names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            module_names |= {(a.asname or a.name).split(".")[0] for a in node.names}
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            module_names.add(node.id)
        elif isinstance(node, ast.arg):
            module_names.add(node.arg)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            module_names |= set(node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            module_names.add(node.name)
    loads = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)} | aug_reads
    return sorted(loads - module_names)


def check_changed_files(root, changes) -> list[str]:
    from pathlib import Path
    fails = []
    if changes.deleted:
        fails.append("deleted files: " + ", ".join(changes.deleted[:5]))
    for name in changes.modified + changes.created:
        p = Path(root) / name
        try:
            text = p.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        if name.endswith(".py"):
            try:
                compile(text, name, "exec")
            except SyntaxError as e:
                fails.append(f"{name} does not compile (line {e.lineno}: {e.msg})")
                continue
            undef = undefined_names(text)
            if undef:
                fails.append(f"{name} uses undefined names: {', '.join(undef[:5])}")
        elif name.endswith(".json"):
            try:
                json.loads(text)
            except json.JSONDecodeError as e:
                fails.append(f"{name} is not valid JSON ({e.msg})")
    return fails


def validate_change(client, cfg: dict, task: str, report: str, root, changes, use_jev: bool = True) -> Verdict:
    """For attempts that edited files: the deliverable is the change, not the chat text."""
    f1 = check_changed_files(root, changes)
    if report.strip() and REFUSAL.search(report[:300]):
        f1.append("refusal or hedge in report")
    if f1:
        return Verdict(False, 1, f1)
    if not use_jev:
        return Verdict(True)
    # Calibration 2026-11-05: Jev judged a correct rename "invented" when shown the model's
    # report next to the diff (p_pass 0.14-0.46). Shown the diff alone with these two
    # questions, it passed the correct rename at 1.0 and caught unrelated edits at 1.0.
    body = f"TASK:\n{task}\n\nCHANGE (unified diff of the files):\n{changes.diff}"
    f2, probs = _ask_judge(client, cfg["classifier"], body, CHANGE_QUESTIONS)
    if f2:
        return Verdict(False, 2, f2, probs)
    return Verdict(True, None, [], probs)


CHANGE_QUESTIONS = [
    ("only_requested", "Does the CHANGE include edits that TASK did not ask for?", [
        ("only_requested", "every edited line is part of what TASK asked", True),
        ("extra_edits", "some edits go beyond what TASK asked", False)]),
    ("covers_required", "Does the CHANGE do everything TASK asked?", [
        ("fully", "every requested edit is made", True),
        ("partly", "some requested edit is missing", False),
        ("no", "it does not do the task", False)]),
]


# ----------------------------------------------------------------- layer 3
AUDIT_PROMPT = """You are auditing an answer another AI model gave. Judge it against what the TASK literally asks.
Mark a key false only for a clear failure: the answer is wrong, skips something the task required, states invented
facts, ignores a requested format, or is cut off. Do not mark a key false for style, wording, a reasonable reading of
the task, or small extras that still satisfy it. When in doubt, mark it true.
Reply with JSON only, no prose, with these keys:
{{"answers_question": true|false, "covers_required": true|false, "no_invented": true|false,
 "format_tone": true|false, "complete": true|false, "score": 0-5, "notes": "<one short sentence>"}}

TASK:
{task}
{source_block}
ANSWER:
{output}
"""


def audit(client, haiku_model, task: str, output: str, source: str | None = None,
          task_type: str = "summary") -> dict:
    generative = is_generative(task_type, source)
    prompt = AUDIT_PROMPT.format(task=task, output=output,
                                 source_block=f"\nSOURCE:\n{source}\n" if source else "")
    if generative:
        prompt += ("\nThe task asks for new content, so adding content beyond the task is expected: "
                   "set no_invented to true unless the answer states false facts.\n")
    raw = client.generate_text(haiku_model.provider, haiku_model.id, prompt, variant="low")
    try:
        data = json.loads(strip_fences(raw))
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(m.group(0)) if m else {"score": None, "notes": "unparseable audit: " + raw[:100]}
    keys = [q[0] for q in judge_questions(task_type, source)]
    data["passed"] = all(data.get(k) is True for k in keys)
    return data
