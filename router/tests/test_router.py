"""Offline tests: a fake OpenCode client stands in for every model, so nothing here
costs usage. Run from priority-brain/router:  python3 -m unittest -v"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from router import validator  # noqa: E402
from router.classifier import QUESTIONS as RUBRIC  # noqa: E402
from router.classifier import shortcut  # noqa: E402
from router.core import Router, load_config  # noqa: E402
from router.models import build_roster  # noqa: E402
from router.opencode_client import RunResult, parse_run_events  # noqa: E402
from router.rules import Answers, match_step0, next_tier, parse_override, start_tier  # noqa: E402

CFG = load_config()
DEF = CFG["default_effort"]
JUDGE = {n: levels for n, _, levels in validator.JUDGE_QUESTIONS + validator.CHANGE_QUESTIONS}


def raw(provider, mid, name=None, family=None, cost=0, variants=("low", "medium", "high", "xhigh", "max"),
        inputs=("text",), released=1):
    return {"providerID": provider, "id": mid, "name": name or mid, "family": family, "status": "active",
            "enabled": True, "cost": [{"input": cost, "output": cost * 5}],
            "variants": [{"id": v} for v in variants], "capabilities": {"input": list(inputs)},
            "time": {"released": released}}


LIVE = [
    raw("opencode", "glm-5.3-flash-free"),
    raw("opencode", "deepseek-v4.1-flash-free"),
    raw("opencode", "crouton-alpha-free", inputs=("text", "pdf", "image", "video")),
    raw("opencode", "big-pickle"),
    raw("opencode", "beam-free"),                       # dropped in console -> excluded by config
    raw("opencode", "pulse-alpha-free"),
    raw("ollama", "llama3.2:3b"),
    raw("claude-code", "claude-haiku-5-5", "Claude Haiku 5.5 (0.1×)", "haiku", 0.1, released=10),
    raw("claude-code", "claude-haiku-4-5", "Claude Haiku 4.5 (1×)", "haiku", 1, released=5),
    raw("claude-code", "claude-sonnet-5-5", "Claude Sonnet 5.5 (2×)", "sonnet", 2, released=10),
    raw("claude-code", "claude-opus-5-5", "Claude Opus 5.5 (4×)", "opus", 4, released=10),
    raw("claude-code", "claude-opus-5-5-fast", "Claude Opus 5.5 Fast (8×)", "opus", 8, released=11),
    raw("claude-code", "claude-fable-5-1", "Claude Fable 5.1 (10×)", "fable", 10, released=12),
    raw("claude-code", "claude-mythos-5-1", "Claude Mythos 5.1 (10×)", "mythos", 10, released=12),
]


class FakeClient:
    """Scripted OpenCode. `script` maps model id -> list of RunResults (popped in order);
    `jev` maps question name -> probability (default 0.0); `judge` likewise for layer 2."""

    def __init__(self, script=None, jev=None, judge=None, audit_json=None, jev_down=False):
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.jev = jev or {}
        self.judge = judge or {}
        self.audit_json = audit_json or {"answers_question": True, "covers_required": True, "no_invented": True,
                                         "format_tone": True, "complete": True, "score": 5, "notes": "fine"}
        self.jev_down = jev_down
        self.runs: list[tuple] = []
        self.archived: list[str] = []
        self.decision_calls = 0
        self.audits = 0

    def list_models(self):
        return LIVE

    def decisions(self, model, text, questions):
        self.decision_calls += 1
        if self.jev_down:
            raise RuntimeError("jev offline")
        out = {}
        rubric = {n: levels for n, _, levels in RUBRIC}
        for q in questions:
            if q["name"] in rubric:
                p = self.jev.get(q["name"], 0.0)
                if isinstance(p, list):          # successive readings, for the borderline re-check
                    p = p.pop(0) if len(p) > 1 else p[0]
                yes = next(v for v, _, y in rubric[q["name"]] if y)
                no = next(v for v, _, y in rubric[q["name"]] if not y)
                out[q["name"]] = {"type": "choice", "name": q["name"], "choice": yes if p >= 0.5 else no,
                                  "probabilities": [{"value": yes, "probability": p}, {"value": no, "probability": 1 - p}]}
            elif q["name"] in JUDGE:
                p = self.judge.get(q["name"], 0.95)
                good = next(v for v, _, ok in JUDGE[q["name"]] if ok)
                bad = next(v for v, _, ok in JUDGE[q["name"]] if not ok)
                out[q["name"]] = {"type": "choice", "name": q["name"], "choice": good if p >= 0.5 else bad,
                                  "probabilities": [{"value": good, "probability": p}, {"value": bad, "probability": 1 - p}]}
            else:
                out[q["name"]] = {"type": "choice", "name": q["name"], "choice": self.jev.get("task_type", "other")}
        return out

    def archive_session(self, sid):
        self.archived.append(sid)

    def generate_text(self, provider, model, prompt, variant=None, timeout=300):
        self.audits += 1
        return json.dumps(self.audit_json)

    def run(self, provider, model, prompt, variant=None, timeout=300, session_id=None, title=None, cwd=None, files=None):
        self.runs.append((f"{provider}/{model}", variant, session_id))
        queue = self.script.get(model)
        if queue:
            item = queue.pop(0)
            return item(Path(cwd)) if callable(item) else item  # callables simulate file edits
        return RunResult(ok=True, text="Done: renamed tmp to total.", session_id="ses_x")


def ok(text):
    return RunResult(ok=True, text=text, session_id="ses_1")


def fail(kind="provider", msg="boom"):
    return RunResult(ok=False, error=msg, error_kind=kind)


class Base(unittest.TestCase):
    def make(self, client, **cfg_over):
        self.tmp = tempfile.TemporaryDirectory()
        cfg = json.loads(json.dumps(CFG))
        cfg.pop("max_tier", None)        # these tests check the full tier table; the cap has its own tests
        cfg |= cfg_over
        cfg["workspace"] = str(Path(self.tmp.name) / "ws")   # never the real router/workspace
        return Router(cfg=cfg, client=client, state_dir=Path(self.tmp.name) / "state")

    def tearDown(self):
        if hasattr(self, "tmp"):
            self.tmp.cleanup()

    def log_rows(self, r):
        return r.log.tail(100)


# ---------------------------------------------------------------- models
class TestRoster(unittest.TestCase):
    def test_live_list_policy(self):
        ro = build_roster(LIVE, CFG)
        self.assertEqual([m.id for m in ro.free],
                         ["glm-5.3-flash-free", "deepseek-v4.1-flash-free", "crouton-alpha-free", "big-pickle"])
        self.assertEqual(ro.claude["haiku"].id, "claude-haiku-5-5")      # newest haiku, not 4.5
        self.assertEqual(ro.claude["opus"].id, "claude-opus-5-5")        # -fast excluded
        self.assertEqual(ro.claude["haiku"].multiplier, 0.1)              # parsed from picker name
        self.assertEqual(ro.claude["sonnet"].multiplier, 2)
        joined = " ".join(ro.excluded)
        for gone in ("beam-free", "pulse-alpha-free", "llama3.2", "fable", "mythos", "opus-5-5-fast"):
            self.assertIn(gone, joined)


# ---------------------------------------------------------------- rules
class TestStep0AndTags(unittest.TestCase):
    def test_step0(self):
        for t in ["what should I do now?", "What should I be doing right now", "what now", "whats next",
                  "what do I need to do today?"]:
            self.assertEqual(match_step0(t).query, "now", t)
        s = match_step0("what's due this week?")
        self.assertEqual((s.query, s.window), ("due", "this week"))
        self.assertIsNone(match_step0("what should I name this variable?"))
        self.assertIsNone(match_step0("fix the due date bug"))

    def test_tags(self):
        o = parse_override("@opus max design the snapshot")
        self.assertEqual((o.tier, o.effort, o.text), ("opus", "max", "design the snapshot"))
        o = parse_override("fix this @sonnet high please")
        self.assertEqual((o.tier, o.effort, o.text), ("sonnet", "high", "fix this please"))
        self.assertEqual(parse_override("@haiku rename x").effort, None)
        self.assertEqual(parse_override("@free max rename x").effort, None)
        self.assertIsNone(parse_override("email me@opus.com"))


class TestTierTable(unittest.TestCase):
    def t(self, **kw):
        d = start_tier(Answers(**kw), DEF)
        return d.tier, d.effort

    def test_rows(self):
        self.assertEqual(self.t(q4_risky=True), ("opus", "high"))
        self.assertEqual(self.t(q2_design=True), ("opus", "high"))
        self.assertEqual(self.t(q7_judgment=True), ("opus", "high"))
        self.assertEqual(self.t(q3_unclear=True, multi_file=True), ("opus", "high"))
        self.assertEqual(self.t(q1_big=True), ("sonnet", "medium"))
        self.assertEqual(self.t(q6_longform=True), ("sonnet", "medium"))
        self.assertEqual(self.t(q5_multistep=True, multi_file=True), ("sonnet", "medium"))
        self.assertEqual(self.t(q3_unclear=True), ("sonnet", "high"))       # effort +1 for Q3
        self.assertEqual(self.t(q5_multistep=True), ("haiku", "low"))
        self.assertEqual(self.t(small_spec=True), ("haiku", "low"))
        self.assertEqual(self.t(), ("free", None))

    def test_risk_beats_size(self):
        self.assertEqual(self.t(q4_risky=True, q1_big=True), ("opus", "high"))
        self.assertEqual(self.t(q1_big=True, small_spec=True), ("sonnet", "medium"))

    def test_never_skip_a_tier(self):
        self.assertEqual([next_tier(t) for t in ("free", "haiku", "sonnet")], ["haiku", "sonnet", "opus"])
        with self.assertRaises(ValueError):
            next_tier("opus")


# ---------------------------------------------------------------- classifier
class TestClassifier(Base):
    def test_shortcut_skips_jev(self):
        self.assertIsNotNone(shortcut("rename tmp to total in budget.py", 160))
        self.assertIsNone(shortcut("delete the old api key file", 160))        # risk word -> Jev
        self.assertIsNone(shortcut("rename tmp across all files", 160))         # several files -> Jev
        c = FakeClient()
        r = self.make(c)
        res = r.route("rename tmp to total in budget.py", dry_run=True)
        self.assertEqual(res.tier, "free")
        self.assertEqual(c.decision_calls, 0)

    def test_jev_answers_map_to_tier_and_cache(self):
        c = FakeClient(jev={"q1_big": 0.8, "multi_file": 0.9})
        r = self.make(c)
        a = r.route("add a snooze field to the model and the importer", dry_run=True)
        b = r.route("add a snooze field to the model and the importer", dry_run=True)
        self.assertEqual((a.tier, a.effort), ("sonnet", "medium"))
        self.assertEqual(b.tier, "sonnet")
        self.assertEqual(c.decision_calls, 1)       # second time from cache: same task, same route
        self.assertIn("[cache]", b.reason)

    def test_borderline_answer_is_rechecked_and_averaged(self):
        c = FakeClient(jev={"q1_big": [0.55, 0.30, 0.31]})     # one wobbly reading, then two clear ones
        r = self.make(c)
        res = r.route("tidy up the helper in utils module", dry_run=True)
        self.assertEqual(res.tier, "free")                       # avg 0.39 -> no, not Sonnet
        self.assertEqual(c.decision_calls, 3)
        self.assertIn("rechecked borderline", r.log.tail(1)[0]["classification"]["note"])

    def test_risk_keyword_raises_borderline_q4(self):
        c = FakeClient(jev={"q4_risky": 0.3})
        r = self.make(c)
        self.assertEqual(r.route("update the deploy script's token handling", dry_run=True).tier, "opus")

    def test_jev_down_uses_fallback_and_does_not_cache(self):
        c = FakeClient(jev_down=True)
        r = self.make(c)
        res = r.route("rotate the API keys in the deploy config and delete the old ones", dry_run=True)
        self.assertEqual(res.tier, "opus")
        self.assertIn("[fallback]", res.reason)
        self.assertFalse((Path(self.tmp.name) / "state" / "classify-cache.json").exists())


# ---------------------------------------------------------------- validator layer 1
class TestValidatorLayer1(unittest.TestCase):
    SRC = ("Lab 3 for CIS 8087 is due Nov 12 at 11:59 PM. It covers VPC peering. "
           "Late work loses 10% per day, and the lab is worth 50 points.")
    TASK = "summarize this in two sentences: " + SRC

    def l1(self, out, task=None, tt="summary", source=None, fields=None):
        return validator.layer1(task or self.TASK, out, tt, source, fields)

    def test_good_summary_passes(self):
        out = "CIS 8087 Lab 3 on VPC peering is due Nov 12 at 11:59 PM. Late work loses 10% a day."
        self.assertEqual(self.l1(out), [])

    def test_empty(self):
        self.assertEqual(self.l1("   "), ["empty output"])

    def test_refusal(self):
        self.assertIn("refusal or hedge", self.l1("I'm sorry, but as an AI I can't summarize course material."))

    def test_truncated(self):
        f = self.l1("CIS 8087 Lab 3 is due Nov 12 at 11:59 PM and covers VPC peering. Late work loses 10% of the")
        self.assertTrue(any("truncated" in x for x in f), f)
        f = self.l1("```python\ndef f():\n    return 1\n", task="write a python function f", tt="code")
        self.assertTrue(any("unclosed code fence" in x for x in f), f)

    def test_invented_facts(self):
        f = self.l1("CIS 8087 Lab 3 on VPC peering is due Nov 14 at 11:59 PM. Late work loses 10% a day.")
        self.assertTrue(any("invented facts" in x and "nov 14" in x for x in f), f)
        f = self.l1("CIS 8087 Lab 3 is due Nov 12 at 11:59 PM, worth 75 points. Late work loses 10% a day.")
        self.assertTrue(any("invented numbers" in x and "75" in x for x in f), f)

    def test_dropped_facts(self):
        f = self.l1("Lab 3 covers VPC peering and has a late penalty, so start early this week please.")
        self.assertTrue(any("key facts dropped" in x for x in f), f)

    def test_summary_length_bounds(self):
        long_out = self.SRC + " " + self.SRC
        self.assertTrue(any("not shorter" in x for x in self.l1(long_out, source=self.SRC)))
        self.assertTrue(any("one line or less" in x for x in self.l1("Lab due Nov 12.", source=self.SRC)))

    def test_wrong_format_json(self):
        task = "extract the title and due fields as JSON from: Lab 3 due Nov 12"
        self.assertTrue(any("invalid JSON" in x for x in self.l1("title: Lab 3, due: Nov 12", task, "extraction")))
        f = self.l1('{"title": "Lab 3"}', task, "extraction", fields=["title", "due"])
        self.assertTrue(any("missing required field 'due'" in x for x in f), f)
        self.assertEqual(self.l1('```json\n{"title": "Lab 3", "due": "Nov 12"}\n```', task, "extraction",
                                 fields=["title", "due"]), [])

    def test_python_must_compile(self):
        task = "write a python function that adds two numbers"
        self.assertTrue(any("does not compile" in x for x in
                            self.l1("```python\ndef add(a, b)\n    return a + b\n```", task, "code")))
        self.assertEqual(self.l1("```python\ndef add(a, b):\n    return a + b\n```", task, "code"), [])


# ---------------------------------------------------------------- Step 4 execution
class TestFreeTier(Base):
    TASK = "rename the variable tmp to total in budget.py"

    def test_first_free_model_passes(self):
        c = FakeClient()
        r = self.make(c)
        res = r.route(self.TASK)
        self.assertEqual((res.outcome, res.tier), ("ok", "free"))
        self.assertEqual(len(c.runs), 1)
        self.assertIsNone(c.runs[0][1])                      # free models run without effort

    def test_three_different_free_models_then_haiku_then_stop(self):
        c = FakeClient(script={"glm-5.3-flash-free": [fail("rate_limit", "Free usage limit reached")],
                               "deepseek-v4.1-flash-free": [ok("")],
                               "crouton-alpha-free": [ok("I'm sorry, but I can't do that.")],
                               "big-pickle": [ok("should never be called")],
                               "claude-haiku-5-5": [fail()]})
        r = self.make(c)
        res = r.route(self.TASK)
        tried = [m for m, _, _ in c.runs]
        self.assertEqual(len(set(tried[:3])), 3)                     # three different free models
        self.assertNotIn("opencode/big-pickle", tried)               # max 3 free attempts
        self.assertEqual(tried[3], "claude-code/claude-haiku-5-5")   # then one tier up
        self.assertEqual(len(tried), 4)                              # and no further
        self.assertFalse(any("sonnet" in t or "opus" in t for t in tried))
        self.assertEqual(res.outcome, "failed-needs-morgan")
        outcomes = [a.outcome for a in res.attempts]
        self.assertEqual(outcomes[:3], ["rate_limit", "validator_l1", "validator_l1"])

    def test_escalated_haiku_success(self):
        c = FakeClient(script={m: [fail()] for m in ("glm-5.3-flash-free", "deepseek-v4.1-flash-free",
                                                     "crouton-alpha-free")})
        r = self.make(c)
        res = r.route(self.TASK)
        self.assertEqual((res.outcome, res.tier), ("ok-after-escalation", "haiku"))

    def test_layer2_jev_failure_counts_as_failed_attempt(self):
        c = FakeClient(judge={"no_invented": 0.1})
        r = self.make(c)
        res = r.route(self.TASK)
        self.assertEqual(res.attempts[0].outcome, "validator_l2")
        self.assertIn("no_invented", res.attempts[0].error)

    def test_malformed_tool_call_is_a_failure(self):
        bad = RunResult(ok=True, text="done", tool_errors=1, session_id="s")
        c = FakeClient(script={"glm-5.3-flash-free": [bad]})
        r = self.make(c)
        res = r.route(self.TASK)
        self.assertEqual(res.attempts[0].outcome, "error")
        self.assertEqual(res.outcome, "ok-after-retry")

    def test_pdf_goes_to_pdf_capable_model(self):
        c = FakeClient()
        r = self.make(c)
        r.route("@free extract the due dates from this syllabus", attachments=["/tmp/syllabus.pdf"])
        self.assertEqual(c.runs[0][0], "opencode/crouton-alpha-free")


class TestClaudeTiers(Base):
    def test_haiku_one_retry_at_higher_effort(self):
        c = FakeClient(script={"claude-haiku-5-5": [fail(), fail()]})
        r = self.make(c)
        res = r.route("@haiku write a function that counts weekdays")
        self.assertEqual([v for _, v, _ in c.runs], ["low", "medium"])
        self.assertEqual(res.outcome, "failed-needs-morgan")

    def test_sonnet_and_opus_never_retry_or_escalate(self):
        for tier, model in (("sonnet", "claude-sonnet-5-5"), ("opus", "claude-opus-5-5")):
            c = FakeClient(script={model: [fail("provider", "overloaded")]})
            r = self.make(c)
            res = r.route(f"@{tier} refactor the importer")
            self.assertEqual(len(c.runs), 1, tier)
            self.assertEqual(res.outcome, "failed-needs-morgan")
            self.assertIn("overloaded", res.answer)

    def test_effort_passed_as_variant_and_logged(self):
        c = FakeClient()
        r = self.make(c)
        r.route("@opus max design the snapshot")
        self.assertEqual(c.runs[0][:2], ("claude-code/claude-opus-5-5", "max"))
        self.assertEqual(self.log_rows(r)[-1]["attempts"][0]["effort"], "max")

    def test_empty_claude_answer_is_failure(self):
        c = FakeClient(script={"claude-sonnet-5-5": [ok("  ")]})
        r = self.make(c)
        self.assertEqual(r.route("@sonnet do it").attempts[0].outcome, "empty_or_refusal")


class TestStages(Base):
    def test_haiku_failure_then_retry_reports_stages_in_order(self):
        c = FakeClient(script={"claude-haiku-5-5": [fail(), fail()]})
        r = self.make(c)
        seen = []
        r.on_stage = seen.append
        r.route("@haiku write a function that counts weekdays")
        ids = [(x["id"], x["label"]) for x in seen]
        self.assertEqual(ids[0], ("run", "Haiku (effort low)"))
        self.assertIn(("run", "Haiku (effort medium) retry"), ids)
        for x in seen:
            self.assertLess(x["lo"], x["hi"])

    def test_good_answer_reports_check_after_run(self):
        c = FakeClient(script={"claude-sonnet-5-5": [ok("fine answer here")]})
        r = self.make(c)
        seen = []
        r.on_stage = seen.append
        r.route("@sonnet explain subnet masks")
        self.assertEqual([x["id"] for x in seen][:2], ["run", "check"])

    def test_a_broken_callback_never_breaks_the_task(self):
        c = FakeClient(script={"claude-sonnet-5-5": [ok("fine answer here")]})
        r = self.make(c)
        r.on_stage = lambda st: 1 / 0
        self.assertEqual(r.route("@sonnet explain subnet masks").outcome, "ok")

    def test_no_callback_is_fine_and_step0_emits_nothing(self):
        r = self.make(FakeClient())
        seen = []
        r.on_stage = seen.append
        r.route("what should I do now?")
        self.assertEqual(seen, [])


class TestConversationPin(Base):
    def test_stays_on_one_model(self):
        c = FakeClient(jev={"q1_big": 0.9})
        r = self.make(c)
        r.route("add snooze to model and importer", conversation="c1")
        r.route("now rename tmp to total", conversation="c1")       # would be free on its own
        self.assertEqual([m for m, _, _ in c.runs], ["claude-code/claude-sonnet-5-5"] * 2)
        self.assertEqual(c.runs[1][2], "ses_x")                     # same OpenCode session
        r.route("@free rename tmp", conversation="c1")              # override wins
        self.assertTrue(c.runs[2][0].startswith("opencode/"))

    def test_finished_sessions_are_archived_but_conversation_kept(self):
        c = FakeClient(script={"glm-5.3-flash-free": [fail()]})
        r = self.make(c)
        r.route("rename tmp to total in budget.py")
        self.assertEqual(c.archived, ["ses_x"])               # failed attempt had no session; winner archived
        c2 = FakeClient(jev={"q1_big": 0.9})
        r2 = self.make(c2)
        r2.route("add snooze to model and importer", conversation="c9")
        self.assertEqual(c2.archived, [])                     # conversation session stays open


# ---------------------------------------------------------------- Step 0, audit, usage, log
class TestStep0Run(Base):
    def test_no_model_call(self):
        c = FakeClient()
        r = self.make(c)
        res = r.route("what should I do now?")
        self.assertEqual(res.handled_by, "priority-engine")
        self.assertEqual((c.runs, c.decision_calls), ([], 0))


class TestAudit(Base):
    def test_week_one_audits_everything_then_one_in_five(self):
        clock = [1_000_000.0]
        c = FakeClient()
        self.tmp = tempfile.TemporaryDirectory()
        cfg = json.loads(json.dumps(CFG)) | {"workspace": str(Path(self.tmp.name) / "ws")}
        r = Router(cfg=cfg, client=c, state_dir=Path(self.tmp.name), now=lambda: clock[0])
        for _ in range(3):
            r.route("rename tmp to total in budget.py")
        self.assertEqual(c.audits, 3)
        clock[0] += 8 * 86400
        for _ in range(10):
            r.route("rename tmp to total in budget.py")
        self.assertEqual(c.audits, 3 + 2)                    # 1 in 5 after week one
        audits = json.loads((Path(self.tmp.name) / "audits.json").read_text())
        self.assertEqual(audits["opencode/glm-5.3-flash-free"]["edit"]["n"], 5)

    def test_failed_audit_flags_but_does_not_retry(self):
        c = FakeClient(audit_json={"answers_question": True, "covers_required": False, "no_invented": True,
                                   "format_tone": True, "complete": True, "score": 2, "notes": "missed one"})
        r = self.make(c)
        res = r.route("rename tmp to total in budget.py")
        self.assertEqual(len(c.runs), 1)
        self.assertTrue(any("audit flagged" in w for w in res.warnings))

    def test_low_audit_scores_demote_a_model(self):
        c = FakeClient()
        r = self.make(c)
        for _ in range(4):
            r.audits.record("opencode/glm-5.3-flash-free", "edit", 1, False)
        self.assertNotEqual(r.rank_free("edit")[0].id, "glm-5.3-flash-free")


class TestMaxTier(Base):
    """Morgan's cap (2026-11-10): the router never runs Opus; those tasks go to Sonnet."""

    def test_config_caps_at_sonnet(self):
        self.assertEqual(CFG["max_tier"], "sonnet")

    def test_opus_decision_runs_on_sonnet_high(self):
        r = self.make(FakeClient(jev_down=True), max_tier="sonnet")
        res = r.route("rotate the API keys in the deploy config and delete the old ones", dry_run=True)
        self.assertEqual((res.tier, res.effort), ("sonnet", "high"))
        self.assertIn("capped at sonnet", res.reason)

    def test_opus_tag_keeps_its_effort_on_sonnet(self):
        r = self.make(FakeClient(), max_tier="sonnet")
        res = r.route("@opus max design the snapshot", dry_run=True)
        self.assertEqual((res.tier, res.effort), ("sonnet", "max"))
        res = r.route("@opus design the snapshot", dry_run=True)
        self.assertEqual((res.tier, res.effort), ("sonnet", "high"))

    def test_lower_tiers_untouched(self):
        r = self.make(FakeClient(), max_tier="sonnet")
        self.assertEqual(r.route("@haiku write a test", dry_run=True).tier, "haiku")
        self.assertEqual(r.route("@sonnet low tidy this", dry_run=True).effort, "low")


class TestUsageAndLog(Base):
    def test_windows_units_and_warning(self):
        clock = [2_000_000_000.0]
        c = FakeClient()
        self.tmp = tempfile.TemporaryDirectory()
        cfg = json.loads(json.dumps(CFG))
        cfg["usage_warn_limits"] = {"five_hour_units": 5, "today_units": None, "week_units": None}
        cfg.pop("max_tier", None)
        cfg["workspace"] = str(Path(self.tmp.name) / "ws")
        r = Router(cfg=cfg, client=c, state_dir=Path(self.tmp.name), now=lambda: clock[0])
        r.route("@opus design it")                    # 4
        r.route("@sonnet build it")                   # 2 -> 6 > 5
        t = r.usage.totals()
        self.assertEqual(t["five_hour"]["units"], 6)
        self.assertEqual(t["five_hour"]["top_tier"], "opus")
        self.assertEqual(t["five_hour"]["by_tier"]["sonnet"]["calls"], 1)
        self.assertTrue(any("usage warning" in w for w in r.usage.warnings()))
        clock[0] += 6 * 3600
        t = r.usage.totals()
        self.assertEqual(t["five_hour"]["units"], 0)
        self.assertEqual(t["week"]["units"], 6)
        r.route("@haiku tiny")
        self.assertAlmostEqual(r.usage.totals()["week"]["units"], 6.1)

    def test_free_calls_counted_separately(self):
        c = FakeClient(script={"glm-5.3-flash-free": [fail("rate_limit")]})
        r = self.make(c)
        r.route("rename tmp to total in budget.py")
        t = r.usage.totals()["week"]
        self.assertEqual(t["free_calls"], 2)
        self.assertEqual(t["free_by_model"]["opencode/glm-5.3-flash-free"]["rate_limited"], 1)

    def test_log_is_complete(self):
        c = FakeClient(script={"glm-5.3-flash-free": [fail("rate_limit")]})
        r = self.make(c)
        r.route("rename tmp to total in budget.py")
        row = self.log_rows(r)[-1]
        for k in ("ts", "input", "step", "tier", "model", "effort", "reason", "outcome", "attempts",
                  "classification", "units_this_turn", "usage", "task_type"):
            self.assertIn(k, row, k)
        self.assertEqual(row["attempts"][0]["outcome"], "rate_limit")
        self.assertEqual(row["classification"]["source"], "shortcut")


class TestFileEdits(Base):
    """Agentic attempts: the change is what gets validated, and failed edits are undone."""
    ORIG = "def monthly(items):\n    tmp = 0\n    for i in items:\n        tmp += i\n    return tmp\n"
    GOOD = "def monthly(items):\n    total = 0\n    for i in items:\n        total += i\n    return total\n"
    HALF = "def monthly(items):\n    total = 0\n    for i in items:\n        tmp += i\n    return tmp\n"

    def edit(self, body, extra=None):
        def act(cwd):
            (cwd / "budget.py").write_text(body)
            if extra:
                (cwd / extra).write_text("scratch")
            return RunResult(ok=True, text="Renamed tmp to total.", session_id="s")
        return act

    def setup_router(self, script, **kw):
        c = FakeClient(script=script, **kw)
        r = self.make(c)
        ws = Path(r.cfg["workspace"])
        (ws / "budget.py").write_text(self.ORIG)
        return c, r, ws

    def test_good_edit_passes_on_the_change(self):
        c, r, ws = self.setup_router({"glm-5.3-flash-free": [self.edit(self.GOOD)]})
        res = r.route("rename the variable tmp to total in budget.py")
        self.assertEqual(res.outcome, "ok")
        self.assertEqual(res.attempts[0].changes, {"modified": ["budget.py"]})
        self.assertEqual((ws / "budget.py").read_text(), self.GOOD)

    def test_half_rename_fails_and_is_rolled_back_before_next_attempt(self):
        seen = []
        def second(cwd):
            seen.append((cwd / "budget.py").read_text())
            (cwd / "budget.py").write_text(self.GOOD)
            return RunResult(ok=True, text="done", session_id="s")
        c, r, ws = self.setup_router({"glm-5.3-flash-free": [self.edit(self.HALF, extra="notes.tmp")],
                                      "deepseek-v4.1-flash-free": [second]})
        res = r.route("rename the variable tmp to total in budget.py")
        a0 = res.attempts[0]
        self.assertEqual(a0.outcome, "validator_l1")
        self.assertIn("undefined names: tmp", a0.error)
        self.assertEqual(seen, [self.ORIG])                       # next model saw the original file
        self.assertFalse((ws / "notes.tmp").exists())             # created file moved out ...
        self.assertTrue((Path(a0.rolled_back) / "notes.tmp").exists())   # ... to the stash, not deleted
        self.assertEqual(res.outcome, "ok-after-retry")

    def test_jev_rejects_unrequested_change(self):
        c, r, ws = self.setup_router({"glm-5.3-flash-free": [self.edit(self.GOOD)]}, judge={"only_requested": 0.05})
        res = r.route("rename the variable tmp to total in budget.py")
        self.assertEqual(res.attempts[0].outcome, "validator_l2")
        # attempt 1's extra edits are rejected and rolled back; attempts 2-3 claim "done" but
        # change nothing, which fails too, so the file is untouched
        self.assertEqual([a.outcome for a in res.attempts[:3]], ["validator_l2", "validator_l1", "validator_l1"])
        self.assertIn("no file was changed", res.attempts[1].error)
        self.assertEqual((ws / "budget.py").read_text(), self.ORIG)

    def test_undefined_names(self):
        self.assertEqual(validator.undefined_names(self.HALF), ["tmp"])
        self.assertEqual(validator.undefined_names(self.GOOD), [])
        self.assertEqual(validator.undefined_names("import os\nprint(os.sep, len([]))"), [])


class TestEventParsing(unittest.TestCase):
    def test_recovered_tool_error_is_not_a_failure(self):
        ev = [{"type": "tool_use", "part": {"tool": "edit", "state": {"status": "error", "error": "oldString not found"}}},
              {"type": "tool_use", "part": {"tool": "read", "state": {"status": "completed"}}},
              {"type": "tool_use", "part": {"tool": "edit", "state": {"status": "completed"}}},
              {"type": "text", "part": {"text": "done"}}]
        r = parse_run_events("\n".join(json.dumps(x) for x in ev))
        self.assertEqual((r.tool_errors, r.tool_calls), (0, 3))
        r = parse_run_events("\n".join(json.dumps(x) for x in ev[:1] + ev[3:]))
        self.assertEqual(r.tool_errors, 1)
        self.assertIn("oldString not found", r.tool_error_detail)

    def test_parse_success_and_plan_notice(self):
        lines = [
            {"type": "text", "sessionID": "s1", "part": {"text": "pong"}},
            {"type": "text", "sessionID": "s1", "part": {"text": "\n▌ **usage:** the Claude account \"default\" has used 75% of the 7-day window, which resets at 2026-11-06 08:00.\n"}},
            {"type": "step_finish", "sessionID": "s1", "part": {"cost": 0.005, "tokens": {"input": 2, "output": 4}}},
        ]
        r = parse_run_events("\n".join(json.dumps(x) for x in lines))
        self.assertTrue(r.ok)
        self.assertEqual(r.text, "pong")
        self.assertEqual(r.plan_notice, "75% of 7-day window, resets 2026-11-06 08:00")

    def test_parse_error(self):
        r = parse_run_events(json.dumps({"type": "error", "error": {"type": "provider.no-route",
                                                                     "message": "Model unavailable"}}), 1)
        self.assertFalse(r.ok)
        self.assertEqual(r.error_kind, "provider")


if __name__ == "__main__":
    unittest.main()


class TestGuards(Base):
    def test_text_only_task_may_not_edit_files(self):
        def sneaky(cwd):
            (cwd / "notes.md").write_text("x")
            return RunResult(ok=True, text="feat: add auto-import manifest", session_id="s")
        c = FakeClient(script={"glm-5.3-flash-free": [sneaky]})
        r = self.make(c)
        res = r.route("write a commit message for: added auto-import manifest")
        a0 = res.attempts[0]
        self.assertEqual(a0.outcome, "validator_l1")
        self.assertIn("text-only task changed files", a0.error)
        self.assertFalse((Path(r.cfg["workspace"]) / "notes.md").exists())
        self.assertEqual(res.outcome, "ok-after-retry")

    def test_final_failure_is_undone_too(self):
        def breaks(cwd):
            (cwd / "budget.py").write_text("def broken(:\n")
            return RunResult(ok=True, text="done", session_id="s")
        c = FakeClient(script={"claude-opus-5-5": [breaks]})
        r = self.make(c)
        ws = Path(r.cfg["workspace"])
        (ws / "budget.py").write_text("x = 1\n")
        res = r.route("@opus refactor budget.py")
        self.assertEqual(res.outcome, "failed-needs-morgan")
        self.assertEqual((ws / "budget.py").read_text(), "x = 1\n")      # restored
        self.assertTrue(res.attempts[0].rolled_back)                       # failed version stashed

    def test_two_runs_cannot_share_a_folder(self):
        from router.workspace import FolderBusy, folder_lock
        c = FakeClient()
        r = self.make(c)
        with folder_lock(r.state_dir, r.cfg["workspace"]):
            with self.assertRaises(FolderBusy):
                r.route("rename tmp to total in budget.py")


class TestSessionPermissions(unittest.TestCase):
    def test_new_sessions_carry_config_rules(self):
        from router.opencode_client import OpenCodeClient
        sent = {}
        c = OpenCodeClient("/bin/false", "/tmp/ws", permissions=CFG["permissions"])
        c._api = lambda op, data=None, timeout=120: sent.update({op: data}) or {"data": {"id": "ses_new"}}
        self.assertEqual(c.create_session("/tmp/ws", "router: t"), "ses_new")
        body = sent["session.create"]
        self.assertEqual(body["location"], {"directory": "/tmp/ws"})
        rules = {(r["action"], r["resource"], r["effect"]) for r in body["permissions"]}
        for must in [("edit", "/*", "deny"), ("edit", "../*", "deny"), ("shell", "rm *", "deny"),
                     ("shell", "*git push*", "deny"), ("read", "*.env", "deny")]:
            self.assertIn(must, rules)


class TestGenerativeAndChatter(Base):
    """2026-11-05 fixes: generative answers skip 'invented details'; agent chatter fails;
    router runs name their own OpenCode agent instead of falling back to plan."""

    TIPS = "@free list 15 short study tips for Read Chapter 6, one tip per line, no intro"

    def test_generative_answer_not_failed_for_invented(self):
        c = FakeClient(judge={"no_invented": 0.05})          # Jev's old misfire on new content
        r = self.make(c)
        res = r.route(self.TIPS)
        self.assertEqual((res.outcome, res.tier), ("ok", "free"))
        self.assertEqual(len(c.runs), 1)
        self.assertNotIn("no_invented", res.attempts[0].validator["layer2"])

    def test_source_bound_answer_still_checked_for_invented(self):
        summ = ok("Lab 3 is due Friday, and students must bring a laptop to class.")
        free = ("glm-5.3-flash-free", "deepseek-v4.1-flash-free", "crouton-alpha-free", "big-pickle")
        c = FakeClient(judge={"no_invented": 0.05}, script={m: [summ] for m in free})
        r = self.make(c)
        src = ("Lab 3 is due Friday. Every student must bring a laptop to class that day, because the lab "
               "runs on your own machine and the room has no spare computers.")
        res = r.route("@free summarize this text", source=src)
        free_attempts = [a for a in res.attempts if a.tier == "free"]
        self.assertTrue(free_attempts)
        self.assertTrue(all(a.outcome == "validator_l2" and "no_invented" in a.error for a in free_attempts),
                        [(a.outcome, a.error) for a in free_attempts])

    def test_question_sets(self):
        names = lambda tt, src: [q[0] for q in validator.judge_questions(tt, src)]  # noqa: E731
        self.assertNotIn("no_invented", names("writing", None))
        self.assertNotIn("no_invented", names("other", None))
        self.assertIn("no_invented", names("summary", None))
        self.assertIn("no_invented", names("writing", "some source"))

    def test_plan_mode_chatter_fails_layer1(self):
        f = validator.layer1("give me one first step", "Open chapter 6 and skim the headings.\n"
                             "I'm in Plan mode now, so I won't create or edit any files.", "other")
        self.assertTrue(any("agent chatter" in x for x in f), f)

    def test_plan_mode_chatter_fails_claude_attempt(self):
        c = FakeClient(script={"claude-haiku-5-5": [ok("Haiku 5.5 is set. Waiting for you to confirm the model switch."),
                                                    ok("pong")]})
        r = self.make(c)
        res = r.route("@haiku reply with the word pong")
        self.assertEqual([a.outcome for a in res.attempts], ["validator_l1", "ok"])
        self.assertEqual(res.answer, "pong")

    def test_workspace_gets_router_agent(self):
        from router.opencode_client import agent_defined
        r = self.make(FakeClient())
        self.assertTrue(agent_defined(r.cfg["workspace"], "router"))

    def test_existing_opencode_json_kept(self):
        from router.core import ensure_agent_config
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "opencode.json").write_text(json.dumps({"model": "x", "agent": {"other": {}}}))
            ensure_agent_config(d, "router")
            data = json.loads((Path(d) / "opencode.json").read_text())
            self.assertEqual(data["model"], "x")
            self.assertIn("other", data["agent"])
            self.assertEqual(data["agent"]["router"]["mode"], "primary")

    def test_client_passes_agent_only_where_defined(self):
        from router import opencode_client as oc
        seen = []
        orig = oc._run_watched
        oc._run_watched = lambda cmd, *a, **k: (seen.append(cmd), ("", 0, None))[1]
        try:
            with tempfile.TemporaryDirectory() as d:
                cl = oc.OpenCodeClient("opencode-cli", d, agent="router")
                cl.run("opencode", "m", "hi", session_id="ses_1")
                self.assertNotIn("--agent", seen[-1])
                (Path(d) / "opencode.json").write_text(json.dumps({"agent": {"router": {"mode": "primary"}}}))
                cl.run("opencode", "m", "hi", session_id="ses_1")
                self.assertEqual(seen[-1][seen[-1].index("--agent") + 1], "router")
        finally:
            oc._run_watched = orig

    def test_config_workspace_outside_priority_brain(self):
        self.assertNotIn("priority-brain", Path(CFG["workspace"]).resolve().parts)


class TestSkillsOff(unittest.TestCase):
    def test_prompt_optimizer_hidden_for_router_runs(self):
        from router.core import ensure_claude_settings
        self.assertIn({"action": "skill", "resource": "prompt-optimizer", "effect": "deny"}, CFG["permissions"])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".claude" / "settings.local.json"
            p.parent.mkdir()
            p.write_text(json.dumps({"model": "haiku"}))
            ensure_claude_settings(d, CFG["claude_skills_off"])
            data = json.loads(p.read_text())
            self.assertEqual(data["model"], "haiku")                       # merged, not replaced
            self.assertEqual(data["skillOverrides"]["prompt-optimizer"], "off")
