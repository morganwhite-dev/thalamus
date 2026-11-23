"""The router: Step 0 -> Step 1 -> conversation pin -> Step 2/3 -> Step 4 -> Steps 5/6."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import validator, workspace
from .classifier import Classifier, guess_task_type
from .models import Model, build_roster
from .opencode_client import OpenCodeClient, RunResult
from .rules import TIERS, bump, match_step0, next_tier, parse_override, start_tier
from .state import Audits, Conversations, RoutingLog, Usage

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: Path | None = None) -> dict:
    cfg = json.loads((path or ROOT / "config.json").read_text())
    ws = Path(cfg.get("workspace", "workspace")).expanduser()
    cfg["workspace"] = str(ws if ws.is_absolute() else ROOT / ws)
    return cfg


def ensure_claude_settings(folder: str, skills_off: list[str]) -> None:
    """Hide skills from Claude runs in `folder` via project settings (`skillOverrides`), so a
    skill like prompt-optimizer ("use on every message") doesn't run on router tasks.
    Morgan's own sessions elsewhere are unaffected. Merges into an existing file."""
    if not skills_off:
        return
    # settings.local.json, not settings.json: checked live 2026-11-05 that the CLI hides the
    # synced skill from there. OpenCode lists ~/.claude/skills through its own skill tool
    # as well; config.json's `skill` deny rules hide them there.
    p = Path(folder) / ".claude" / "settings.local.json"
    try:
        data = json.loads(p.read_text()) if p.exists() else {}
    except (OSError, json.JSONDecodeError):
        return  # never overwrite a settings file we can't read
    ov = data.setdefault("skillOverrides", {})
    if all(ov.get(s) == "off" for s in skills_off):
        return
    for s in skills_off:
        ov[s] = "off"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n")


def ensure_agent_config(folder: str, agent: str | None) -> None:
    """Define the router's OpenCode agent in `folder`'s project config (opencode.json). The
    background OpenCode server reads agents only from config files, not from the caller's
    environment (checked 2026-11-05: OPENCODE_CONFIG_CONTENT gave 'Agent not found')."""
    if not agent:
        return
    p = Path(folder) / "opencode.json"
    try:
        data = json.loads(p.read_text()) if p.exists() else {}
    except (OSError, json.JSONDecodeError):
        return  # never overwrite a config we can't read
    agents = data.setdefault("agent", {})
    if agent in agents:
        return
    data.setdefault("$schema", "https://opencode.ai/config.json")
    agents[agent] = {"mode": "primary",
                     "description": "Priority Brain router worker: does the one task it is given, then stops"}
    p.write_text(json.dumps(data, indent=2) + "\n")


def priority_engine_stub(query: str, window: str | None) -> str:
    what = "what to do now" if query == "now" else f"what's due{(' ' + window) if window else ''}"
    return f"[priority engine] understood '{what}'. The engine is built in Phase 4; no model was called."


@dataclass
class Attempt:
    model: str
    tier: str
    effort: str | None
    outcome: str                 # ok | error | rate_limit | timeout | validator_l1 | validator_l2 | empty_or_refusal
    error: str | None = None
    duration_s: float = 0.0
    validator: dict | None = None
    units: float = 0.0
    changes: dict | None = None      # files the attempt modified/created/deleted
    rolled_back: str | None = None   # stash folder if a failed attempt's edits were undone
    output_preview: str | None = None
    session_id: str | None = None

    def to_log(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if v not in (None, [], {})}
        d["duration_s"] = round(self.duration_s, 1)
        return d


@dataclass
class RouteResult:
    handled_by: str              # priority-engine | model | none
    tier: str | None = None
    model: str | None = None
    effort: str | None = None
    answer: str = ""
    outcome: str = ""            # ok | ok-after-retry | failed-needs-morgan | dry-run | step0
    reason: str = ""
    attempts: list[Attempt] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    log: dict = field(default_factory=dict)


class Router:
    def __init__(self, cfg: dict | None = None, client=None, state_dir: Path | None = None,
                 priority_engine=priority_engine_stub, now=None, on_stage=None):
        self.on_stage = on_stage  # optional progress callback; see command/STATE_MODEL_STAGES.md
        self.cfg = cfg or load_config()
        self.client = client or OpenCodeClient(self.cfg["opencode_cli"], self.cfg["workspace"],
                                               self.cfg.get("auto_approve_tools", False),
                                               self.cfg.get("permissions"),
                                               self.cfg.get("stall_seconds", 90),
                                               self.cfg.get("opencode_agent"))
        sd = state_dir or ROOT / "state"
        self.state_dir = sd
        self.cwd = self.cfg["workspace"]  # folder models work in; route(cwd=...) can point elsewhere
        kw = {"now": now} if now else {}
        self.usage = Usage(sd, self.cfg["usage_warn_limits"], **kw)
        self.audits = Audits(sd, self.cfg["audit"]["first_week_days"], self.cfg["audit"]["sample_every"], **kw)
        self.log = RoutingLog(sd, **kw)
        self.convs = Conversations(sd)
        self.classifier = Classifier(self.client, self.cfg, sd / "classify-cache.json")
        self.priority_engine = priority_engine
        self._roster = None
        Path(self.cfg["workspace"]).mkdir(parents=True, exist_ok=True)
        ensure_agent_config(self.cfg["workspace"], self.cfg.get("opencode_agent"))
        ensure_claude_settings(self.cfg["workspace"], self.cfg.get("claude_skills_off", []))

    def _stage(self, sid: str, label: str, lo: int, hi: int) -> None:
        """Report the stage a run just entered. Progress reporting never breaks a task."""
        if not self.on_stage:
            return
        try:
            self.on_stage({"id": sid, "label": label, "lo": lo, "hi": hi})
        except Exception:
            pass

    # ------------------------------------------------------------- roster
    @property
    def roster(self):
        if self._roster is None:
            self._roster = build_roster(self.client.list_models(), self.cfg)
        return self._roster

    def claude(self, tier: str) -> Model:
        m = self.roster.claude.get(tier)
        if not m:
            raise RuntimeError(f"no {tier} model in OpenCode's live list")
        return m

    def rank_free(self, task_type: str, attachments: list[str] | None = None) -> list[Model]:
        kinds = {_kind(p) for p in attachments or []} - {"text"}
        pool = [m for m in self.roster.free if all(k in m.inputs for k in kinds)]
        hinted = {mid for k in kinds for mid in self.cfg.get("free_model_hints", {}).get(k, [])}

        def score(m: Model) -> tuple:
            s = self.audits.score(m.key, task_type) - 2 * self.log.failure_rate(m.key)
            return (m.id not in hinted, -round(s, 3))
        return sorted(pool, key=score)  # stable: ties keep OpenCode's live-list order

    # ------------------------------------------------------------- entry point
    def route(self, text: str, source: str | None = None, conversation: str | None = None,
              attachments: list[str] | None = None, fields: list[str] | None = None,
              dry_run: bool = False, cwd: str | None = None, log_input: str | None = None) -> RouteResult:
        """log_input: what the routing log records instead of the text (pasted text from the chat is never logged)."""
        self.cwd = cwd or self.cfg["workspace"]
        with workspace.folder_lock(self.state_dir, self.cwd):
            return self._route(text, source, conversation, attachments, fields, dry_run, log_input)

    def _route(self, text, source, conversation, attachments, fields, dry_run, log_input=None) -> RouteResult:
        entry: dict = {"input": (text if log_input is None else log_input)[:300], "cwd": self.cwd}
        ov = parse_override(text)

        # Step 0: not a model task
        if not ov:
            s0 = match_step0(text)
            if s0:
                answer = self.priority_engine(s0.query, s0.window)
                res = RouteResult("priority-engine", answer=answer, outcome="step0",
                                  reason=f"step 0 pattern: {s0.query}" + (f" ({s0.window})" if s0.window else ""))
                return self._finish(res, entry | {"step": 0})

        task = ov.text if ov else text
        task_type = guess_task_type(task)

        # Step 1: manual override
        if ov:
            tier = ov.tier
            effort = ov.effort or self.cfg["default_effort"][tier]
            reason = f"tag @{tier}" + (f" {ov.effort}" if ov.effort else "")
            entry["step"] = 1
            if conversation:
                self.convs.drop(conversation)  # Morgan overrode: new pin after this turn
        # conversation pin: stay on one model
        elif conversation and (pin := self.convs.get(conversation)):
            tier, effort = pin["tier"], pin["effort"]
            reason = f"conversation {conversation}: staying on {pin['model']}"
            entry["step"] = "pinned"
        # Steps 2-3: classify, then fixed table
        else:
            self._stage("classify", "Reading the task", 5, 20)
            cl = self.classifier.classify(task)
            task_type = cl.task_type
            dec = start_tier(cl.answers, self.cfg["default_effort"])
            tier, effort, reason = dec.tier, dec.effort, f"{dec.rule} [{cl.source}]"
            entry["step"] = 2
            entry["classification"] = cl.to_log()

        # Morgan's cap (2026-11-10): nothing runs above max_tier. Opus work goes to Sonnet at high effort,
        # a tagged effort (e.g. "@opus max") is kept.
        top = self.cfg.get("max_tier")
        if top in TIERS and TIERS.index(tier) > TIERS.index(top):
            tagged = ov.effort if ov else None
            tier, effort = top, tagged or "high"
            reason += f" (capped at {top})"
            entry["capped"] = True
        entry["task_type"] = task_type
        if dry_run:
            res = RouteResult("none", tier=tier, effort=effort, outcome="dry-run", reason=reason)
            res.model = self._planned_model(tier, task_type, attachments)
            return self._finish(res, entry)

        res = self._execute(task, tier, effort, reason, task_type, source, attachments, fields, conversation)
        self._archive_sessions(res, conversation)
        return self._finish(res, entry)

    def _archive_sessions(self, res: RouteResult, conversation: str | None) -> None:
        """Archive each finished OpenCode session (reversible) so router runs don't pile up in
        Morgan's OpenCode session list. A pinned conversation keeps its session open."""
        keep = (self.convs.get(conversation) or {}).get("session_id") if conversation else None
        for a in res.attempts:
            if a.session_id and a.session_id != keep and hasattr(self.client, "archive_session"):
                try:
                    self.client.archive_session(a.session_id)
                except Exception:
                    pass  # archiving is housekeeping; never fail a task over it

    # ------------------------------------------------------------- Step 4
    def _execute(self, task, tier, effort, reason, task_type, source, attachments, fields, conversation) -> RouteResult:
        prompt = task if not source else f"{task}\n\nSOURCE:\n{source}"
        pin = self.convs.get(conversation) if conversation else None
        session = pin["session_id"] if pin and pin["tier"] == tier else None
        res = RouteResult("model", tier=tier, effort=effort, reason=reason)

        if tier == "free":
            ok = self._run_free(res, task, prompt, task_type, source, attachments, fields, session)
            if ok:
                return self._pin(res, conversation)
            # all free attempts failed: one tier up, to Haiku, and no further
            esc = next_tier("free")
            res.reason += f"; {len(res.attempts)} free attempts failed, escalated one tier to {esc}"
            if self._run_claude(res, esc, self.cfg["default_effort"][esc], prompt, attachments, None, "escalation", task, task_type):
                res.outcome = "ok-after-escalation"
                return self._pin(res, conversation)
            res.outcome = "failed-needs-morgan"
            res.answer = "Free models and Haiku all failed on this small task. Stopping here (small tasks never climb above Haiku)."
            return res

        if tier == "haiku":
            if self._run_claude(res, "haiku", effort, prompt, attachments, session, "task", task, task_type):
                res.outcome = "ok"
                return self._pin(res, conversation)
            higher = bump(effort, cap="high")
            res.reason += f"; Haiku failed, one retry at effort {higher}"
            if self._run_claude(res, "haiku", higher, prompt, attachments, None, "retry", task, task_type):
                res.outcome = "ok-after-retry"
                res.effort = higher
                return self._pin(res, conversation)
            res.outcome = "failed-needs-morgan"
            res.answer = "Haiku failed twice. Stopping here; tell me how to proceed."
            return res

        # Sonnet / Opus: one attempt, never retried or escalated
        if self._run_claude(res, tier, effort, prompt, attachments, session, "task", task, task_type):
            res.outcome = "ok"
            return self._pin(res, conversation)
        res.outcome = "failed-needs-morgan"
        err = res.attempts[-1].error or res.attempts[-1].outcome
        res.answer = f"{tier.title()} failed: {err}. No automatic retry for big tasks; what should I do?"
        return res

    def _undo(self, att: Attempt, before: dict, ch: workspace.Changes) -> None:
        """Undo a failed attempt's file edits (always: before a retry, and after a final failure,
        so a failed run never leaves half-done edits in Morgan's folder). The failed version is
        kept in the stash folder for inspection."""
        stash = workspace.rollback(before, self.cwd, ch, self.state_dir / "rollback")
        if stash:
            att.changes = ch.to_log()
            att.rolled_back = str(stash)

    def _run_free(self, res, task, prompt, task_type, source, attachments, fields, session) -> bool:
        tried = 0
        for m in self.rank_free(task_type, attachments):
            if tried >= self.cfg["free_max_attempts"]:
                break
            tried += 1
            n = self.cfg["free_max_attempts"]
            band = 55 // n
            lo = 25 + (tried - 1) * band
            self._stage("run", f"Free model {tried} of {n}", lo, lo + band)
            before = workspace.snapshot(self.cwd)
            rr = self.client.run(m.provider, m.id, prompt, None, self.cfg["attempt_timeout_seconds"]["free"],
                                 session if tried == 1 else None, title="router: " + task[:60],
                                 cwd=self.cwd, files=attachments)
            ch = workspace.compare(before, self.cwd)
            self._stage("check", "Checking the answer", 85, 95)
            att = Attempt(m.key, "free", None, "ok", duration_s=rr.duration_s, output_preview=rr.text[:300],
                          session_id=rr.session_id)
            if not rr.ok:
                att.outcome, att.error = rr.error_kind or "error", rr.error
            elif rr.tool_errors:
                att.outcome, att.error = "error", f"unrecovered tool error ({rr.tool_error_detail})"
            elif not ch.any and task_type in ("edit", "code") and _names_existing_file(task, self.cwd):
                att.outcome = "validator_l1"
                att.error = "edit task on an existing file, but no file was changed"
            elif ch.any and _text_only(task, task_type):
                att.outcome, att.error = "validator_l1", "text-only task changed files: " + ", ".join(ch.modified + ch.created + ch.deleted)
            else:
                if ch.any:
                    v = validator.validate_change(self.client, self.cfg, task, rr.text, self.cwd, ch)
                else:
                    v = validator.validate(self.client, self.cfg, task, rr.text, task_type, source, fields)
                att.validator = v.to_log()
                if not v.passed:
                    att.outcome, att.error = f"validator_l{v.failed_layer}", "; ".join(v.failures)
            self.usage.record_free(m.key, att.outcome)
            res.attempts.append(att)
            if att.outcome != "ok":
                self._undo(att, before, ch)
                continue
            if ch.any:
                att.changes = ch.to_log()
            res.model, res.answer = m.key, rr.text
            res.outcome = "ok" if tried == 1 else "ok-after-retry"
            res.log["session_id"] = rr.session_id
            # Edits are audited on the change, not the chat report. The audit also sees the
            # edited files in full: shown only the diff, Haiku marked a correct syntax fix down
            # because it couldn't see the surrounding lines (live run 2026-11-05).
            self._maybe_audit(res, m, task, rr.text if not ch.any else
                              f"FILES AFTER THE CHANGE:\n{workspace.file_texts(self.cwd, ch)}\n\n"
                              f"CHANGE (unified diff):\n{ch.diff}", task_type, source)
            return True
        return False

    def _run_claude(self, res, tier, effort, prompt, attachments, session, purpose, task="", task_type="other") -> bool:
        m = self.claude(tier)
        variant = effort if effort in m.variants else None
        lo, hi = (75, 90) if purpose in ("escalation", "retry") else (25, 80)
        eff = f" (effort {variant})" if variant else ""
        self._stage("run", f"{tier.title()}{eff}" + (" retry" if purpose == "retry" else ""), lo, hi)
        before = workspace.snapshot(self.cwd)
        rr: RunResult = self.client.run(m.provider, m.id, prompt, variant,
                                        self.cfg["attempt_timeout_seconds"][tier], session,
                                        title="router: " + prompt[:60], cwd=self.cwd, files=attachments)
        ch = workspace.compare(before, self.cwd)
        self._stage("check", "Checking the answer", 85, 95)
        self.usage.record_claude(tier, m.key, m.multiplier, purpose, rr.tokens, rr.cost)
        if rr.plan_notice:
            self.usage.record_plan_notice(rr.plan_notice)
        att = Attempt(m.key, tier, variant, "ok", duration_s=rr.duration_s, units=m.multiplier,
                      output_preview=rr.text[:300], session_id=rr.session_id)
        if not rr.ok:
            att.outcome, att.error = rr.error_kind or "error", rr.error
        elif rr.tool_errors:
            att.outcome, att.error = "error", f"unrecovered tool error ({rr.tool_error_detail})"
        elif (not rr.text.strip() and not ch.any) or validator.REFUSAL.search(rr.text[:300]):
            att.outcome, att.error = "empty_or_refusal", rr.text[:120]
        elif validator.META_CHATTER.search(rr.text) and not validator.META_CHATTER.search(task):
            att.outcome, att.error = "validator_l1", "agent chatter in answer (e.g. 'plan mode')"
        elif ch.any and _text_only(task, task_type):
            att.outcome = "validator_l1"
            att.error = "text-only task changed files: " + ", ".join(ch.modified + ch.created + ch.deleted)
        elif ch.any and (bad := validator.check_changed_files(self.cwd, ch)):
            att.outcome, att.error = "validator_l1", "; ".join(bad)  # task's own check failed
        if ch.any:
            att.changes = ch.to_log()
        res.attempts.append(att)
        if att.outcome == "ok":
            res.tier, res.model, res.effort, res.answer = tier, m.key, variant, rr.text
            res.log["session_id"] = rr.session_id
            return True
        self._undo(att, before, ch)
        return False

    def _maybe_audit(self, res, m: Model, task, output, task_type, source) -> None:
        if not self.audits.should_audit():
            res.log["audit"] = "not sampled"
            return
        self._stage("audit", "Second opinion", 95, 98)
        try:
            haiku = self.claude("haiku")
            # an edit's audit is judged as source-bound (the files are the source)
            a = validator.audit(self.client, haiku, task, output, source,
                                "edit" if output.startswith("FILES AFTER THE CHANGE:") else task_type)
            self.usage.record_claude("haiku", haiku.key, haiku.multiplier, "audit")
            self.audits.record(m.key, task_type, a.get("score"), a["passed"])
            res.log["audit"] = a
            if not a["passed"]:
                res.warnings.append(f"Haiku audit flagged this answer from {m.key}: {a.get('notes', '')}")
        except Exception as e:
            res.log["audit"] = f"audit failed: {str(e)[:120]}"

    def _pin(self, res: RouteResult, conversation: str | None) -> RouteResult:
        if conversation and res.model:
            self.convs.set(conversation, res.tier, res.model, res.effort, res.log.get("session_id"))
        return res

    def _planned_model(self, tier, task_type, attachments) -> str | None:
        try:
            if tier == "free":
                ranked = self.rank_free(task_type, attachments)
                return ranked[0].key if ranked else None
            return self.claude(tier).key
        except Exception:
            return None

    # ------------------------------------------------------------- Steps 5-6
    def _finish(self, res: RouteResult, entry: dict) -> RouteResult:
        totals = self.usage.totals()
        res.warnings += self.usage.warnings(totals)
        units = round(sum(a.units for a in res.attempts), 2)
        if isinstance(res.log.get("audit"), dict):
            units = round(units + self.roster.claude["haiku"].multiplier, 2)
        res.log = self.log.write(entry | {
            "handled_by": res.handled_by, "tier": res.tier, "model": res.model, "effort": res.effort,
            "reason": res.reason, "outcome": res.outcome,
            "attempts": [a.to_log() for a in res.attempts],
            "units_this_turn": units,
            "usage": {w: totals[w]["units"] for w in ("five_hour", "today", "week")},
            "top_tier_week": totals["week"]["top_tier"],
            "plan_notice": totals.get("plan_notice"),
            "warnings": res.warnings,
            "answer_preview": res.answer[:200],
            **{k: v for k, v in res.log.items() if k in ("session_id", "audit")},
        })
        return res


TEXT_ONLY_TYPES = ("summary", "extraction", "explain", "writing", "classify")


def _text_only(task: str, task_type: str) -> bool:
    """A text answer that names no file (commit message, summary, explanation...) has no
    business editing files."""
    import re
    if task_type not in TEXT_ONLY_TYPES and not re.search(r"\bcommit message\b", task, re.I):
        return False
    return not re.search(r"[\w./-]+\.\w{1,6}\b", task)


def _names_existing_file(task: str, cwd: str) -> bool:
    """True if the task mentions a file name that exists in the working folder."""
    import re
    for name in re.findall(r"[\w./-]+\.\w{1,6}\b", task):
        if (Path(cwd) / name).is_file() or any(Path(cwd).rglob(Path(name).name)):
            return True
    return False


def _kind(path: str) -> str:
    p = path.lower()
    if p.endswith(".pdf"):
        return "pdf"
    if p.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic")):
        return "image"
    if p.endswith((".mp4", ".mov", ".webm", ".mkv")):
        return "video"
    return "text"
