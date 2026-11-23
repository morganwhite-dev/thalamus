"""Which handler would take a sentence typed in the command box? Plain code, no model, nothing is written.

Mirrors the real order: dashboard/server.py submit_command (capture first), then CommandRunner.submit in
command/command.py, then the router's Step 0, tags and keyword shortcut (router/router). Keep the three in step.
Used by command/tests/test_phrasings.py and for audits:  python3 command/route_preview.py "what should i work on"
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for p in (HERE, ROOT / "engine", ROOT / "router", ROOT / "play", ROOT / "prep"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
import capture  # noqa: E402
import class_qa  # noqa: E402
import lookup  # noqa: E402
import park  # noqa: E402
import project_status  # noqa: E402
import reminders_qa  # noqa: E402
import schedule_qa  # noqa: E402
import intent  # noqa: E402
import plain  # noqa: E402
import undo  # noqa: E402
from router import classifier, rules  # noqa: E402

LISTS = ["Cloud Computing", "Network Security", "Internships", "Security Projects", "Personal", "Play", "General"]


def decide(text, lists=None, tasks=None, now=None, prep_parse=None, sector=None, config=None, matcher=None, detail=None):
    """One label: undo | capture | project | park | reminders | lookup | schedule | now | stuck | action | tiny | prep |
    tag | free (keyword shortcut, free model) | jev (the classifier model decides the tier).
    `sector` is the open sector, as the dashboard sends it (inside a sector a plain statement can be a task).
    `config` (the engine config) lets a generic file find be checked against the real folders, as the live box does:
    with no file found it falls through. Without it a generic find is reported as "lookup".
    `matcher` (command/matcher.Matcher): asked at the same point as the live box, after the rules, tags and Step 0. A routed
    read-only label is returned as "matcher:<label>"; when `detail` is a dict it gets the matcher's score.
    Without a matcher the answer is what the rules alone decide."""
    now = now or datetime.now().astimezone()
    lists = LISTS if lists is None else lists
    tasks = tasks or []
    t = plain.normalize((text or "").strip())
    if undo.is_undo(t):
        return "undo"
    pre = intent.before_capture(t, tasks)
    if pre:
        return pre[0]
    if capture.detect(t, lists, now, sector=sector, tasks=tasks):
        return "capture"
    if project_status.parse_intent(t) or project_status.is_bare(t):
        return "project"
    if park.parse(t) is not None:
        return "park"
    if reminders_qa.parse(t):
        return "reminders"
    if class_qa.parse(t):
        return "schedule"      # classes and tests on the calendar (falls through to the task list when it has nothing)
    lq = lookup.detect(t)
    if lq and (lq["modules"] or lq["weeks"] or lq["kinds"]):
        return "lookup"
    if lq and lq.get("generic") and (config is None or lookup.search(lq, config)["files"]):
        return "lookup"        # a generic find only answers when a file matches; otherwise it falls through
    if schedule_qa.parse(t, None, now) or intent.planning_fallback(t, tasks, lists) == "schedule":
        return "schedule"
    if prep_parse and prep_parse(t):
        return "prep"
    if rules.parse_override(t):
        return "tag"
    if rules.match_step0(t):
        return "now"
    if matcher is not None:
        m = matcher.classify(t)
        if m and m.get("routable") and m.get("label") != "general" and (
                m["label"] != "schedule" or schedule_qa.parse(t, config, now, force=True)):
            if isinstance(detail, dict):
                detail.update(score=m.get("score"), margin=m.get("margin"))
            return "matcher:" + m["label"]
    if classifier.shortcut(t, 220) is not None:
        return "free"
    return "jev"


if __name__ == "__main__":
    args = sys.argv[1:]
    m = None
    if args[:1] == ["--matcher"]:         # also ask the local meaning matcher (Ollama), as the live box does
        import matcher as matcher_mod
        args = args[1:]
        m = matcher_mod.Matcher()
        m.wait_loaded(60)
        m.cfg["timeout_ms"] = max(m.cfg["timeout_ms"], 2000)   # a cold model is slow on the first call; the box keeps 300 ms
    for s in args:
        d = {}
        import prep as prep_agent
        label = decide(s, matcher=m, detail=d, prep_parse=prep_agent.parse_command)
        print(f"{label + (' ' + str(d['score']) if d else ''):22} {s}")
