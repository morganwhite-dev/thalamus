"""Phase 9 command box: a thin front for the Phase 1b router.

The dashboard server owns one CommandRunner. A command becomes a job that runs on a
background thread (router calls can take minutes); the page polls the job. One job at
a time. Design: command/STATE_MODEL.md.
"""
from __future__ import annotations

import json
import re
import sys
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for p in (ROOT / "engine", ROOT / "router"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
import brain  # noqa: E402
sys.path.insert(0, str(ROOT / "play"))
import play as play_store  # noqa: E402
import project_status  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lookup  # noqa: E402
import schedule_qa  # noqa: E402
import reminders_qa  # noqa: E402
import park  # noqa: E402
import intent  # noqa: E402
import acts  # noqa: E402
import class_qa  # noqa: E402
import plain  # noqa: E402
import undo as undo_mod  # noqa: E402
sys.path.insert(0, str(ROOT / "prep"))
import prep as prep_agent  # noqa: E402
from brain_engine import category_for, parse_dt  # noqa: E402

STATE_DIR = HERE / "state"
DEFAULTS = {"longChars": 600, "longLines": 12, "maxInputChars": 4000, "maxPasteChars": 24000}
MAX_JOBS = 20
MAX_RESULTS_PER_TASK = 10
MIN_TITLE_MATCH = 6
LOG_LINES = 30
STUCK_PROMPT = (
    "@free Give me one concrete first step for this task that I can do in five minutes or less. "
    "Answer in one to three short sentences, starting with a verb. No preamble, no list of later steps.\n"
    "Task: {title}\nList: {list}\n{notes}"
)


def _client_cancel(on):
    try:
        from router import opencode_client as oc
        (oc.request_cancel if on else oc.clear_cancel)()
    except Exception:
        pass


class Busy(Exception):
    pass


def now_local():
    return datetime.now().astimezone()


def iso(dt):
    return dt.isoformat(timespec="seconds")


def new_job_id(jobs, now=None):
    """The one id maker for every job kind (model jobs, instant replies, project status). Two commands in the same second
    with the same random part get a numbered suffix, so a second job can never shadow the first ("Busy" forever)."""
    now = now or now_local()
    taken = {j.get("id") for j in jobs}
    base = "cmd-" + now.strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:4]
    jid, n = base, 2
    while jid in taken:
        jid, n = f"{base}-{n}", n + 1
    return jid


def settings(config):
    return {**DEFAULTS, **(config.get("command") or {})}


def check_length(raw, config, pasted=False):
    """The input limit, checked on the raw text before any rule scans it. Raises ValueError (the page shows it).
    Pasted text from the chat (STATE_MODEL_CHAT.md) gets a larger limit: it skips the rules and goes to a model."""
    n, limit = len(str(raw or "").strip()), settings(config)["maxPasteChars" if pasted else "maxInputChars"]
    if n > limit:
        raise ValueError(f"too long ({n} characters, limit {limit})")


# ------------------------------------------------------------------ files
def _read(path, default):
    """Read JSON; a corrupt file is moved to .bad and reported (never silently dropped)."""
    try:
        return json.loads(Path(path).read_text()), None
    except FileNotFoundError:
        return default, None
    except (OSError, ValueError) as e:
        bad = Path(str(path) + ".bad")
        try:
            Path(path).replace(bad)
        except OSError:
            pass
        return default, f"{Path(path).name} was unreadable ({e}); moved to {bad.name} and reset."


def _append(path, row):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(row) + "\n")


def _tail_jsonl(path, n):
    try:
        lines = Path(path).read_text().splitlines()[-n:]
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


# ------------------------------------------------------------------ Step 0 answers (no model)
def _fmt_due(iso_s, now):
    if not iso_s:
        return "no deadline"
    d = parse_dt(iso_s, now.tzinfo)
    return d.strftime("%a %b %-d, %-I:%M %p")


def engine_answer(query, window, config, now=None, block=None):
    """Answer Step 0 from the priority engine. Plain code, no model call."""
    now = now or now_local()
    try:
        rec = brain.run(config, now=now, save_overrides=False)
    except (SystemExit, OSError, ValueError) as e:      # no snapshot yet (before the first sync) must not crash the box
        try:
            rec = brain.read_json(brain.resolve("recommendationPath", config), default=None)
        except (OSError, ValueError):
            rec = None
        if not rec:
            return f"The priority engine can't read the snapshot right now: {e}"
    if query == "now":
        lines = []
        if block and block.get("phase") in ("work", "starting") and block.get("block"):
            lines.append(f"You're in a block on: {block['block']['title']}. Keep going, or end it in the block panel.")
        c = rec.get("current")
        if not c:
            lines.append("Nothing to do right now. " + (rec.get("emptyReason") or ""))
            return "\n".join(lines).strip()
        lines.append(f"Do this now: {c['title']} ({c['list']}, due {_fmt_due(c.get('dueDate'), now)}, about {c['minutes']} min).")
        lines.append(f"Why: {c['why']}")
        if c.get("resources"):
            lines.append("Resources: " + c["resources"])
        nxt = [t["title"] for t in rec.get("queue", [])[:2]]
        if nxt:
            lines.append("After that: " + "; ".join(nxt) + ".")
        return "\n".join(lines)

    # what's due <window>
    try:
        tasks = brain.read_json(brain.resolve("snapshotPath", config))["tasks"]
    except (OSError, ValueError, KeyError) as e:
        return f"The priority engine can't read the snapshot right now: {e}"
    start, end, label = due_window(window, now)
    hits, missed = [], []
    for t in tasks:
        if not t.get("dueDate") or t.get("completedAt"):
            continue
        d = parse_dt(t["dueDate"], now.tzinfo)
        if d < now and label in ("today", "in the next 7 days", "this week"):
            missed.append((d, t))
        elif start <= d <= end:
            hits.append((d, t))
    hits.sort(key=lambda x: x[0])
    missed.sort(key=lambda x: x[0])
    out = []
    if hits:
        out.append(f"Due {label} ({len(hits)}):")
        out += [f"- {_fmt_due(t['dueDate'], now)}: {t['title']} ({t.get('list', '')})" for _, t in hits]
    else:
        out.append(f"Nothing due {label}.")
    if missed:
        out.append(f"Missed and still open ({len(missed)}), already at the top of the list:")
        out += [f"- {t['title']} ({t.get('list', '')})" for _, t in missed[:5]]
    return "\n".join(out)


def due_window(window, now):
    w = (window or "").lower()
    sod = now.replace(hour=0, minute=0, second=0, microsecond=0)
    eod = sod + timedelta(days=1) - timedelta(microseconds=1)
    if "tomorrow" in w:
        return sod + timedelta(days=1), eod + timedelta(days=1), "tomorrow"
    if "today" in w or "tonight" in w:
        return now, eod, "today"
    if "next week" in w:
        mon = sod + timedelta(days=7 - sod.weekday())
        return mon, mon + timedelta(days=7) - timedelta(microseconds=1), "next week"
    if "week" in w:
        sun = eod + timedelta(days=6 - sod.weekday())
        return now, sun, "this week"
    return now, now + timedelta(days=7), "in the next 7 days"


# ------------------------------------------------------------------ task matching, length, routing line
def match_task(text, tasks, explicit_id=None, block_task_id=None):
    """First match wins: explicit choice, a title in the text, the running block's task, none."""
    tasks = tasks or []
    by_id = {t["id"]: t for t in tasks}
    if explicit_id:
        if explicit_id in by_id:
            return by_id[explicit_id], "chosen"
        raise ValueError("that task is no longer open")
    found = [t for t in tasks if len(t["title"]) >= MIN_TITLE_MATCH and plain.names_title(text, t["title"])]   # whole words: "chapter 5" is not in "chapter 55"
    if found:
        # a title inside a longer title that is also named ("Read Chapter 5" in "Prep for Read Chapter 5") is part of it: the longest wins
        top = [t for t in found if not any(o is not t and len(plain.words(o["title"])) > len(plain.words(t["title"])) and plain.names_title(o["title"], t["title"])
                                           for o in found)]
        if len(top) > 1:
            return None, "tie"               # the text names two different tasks: the answer is shown and saved to neither
        return top[0], "named in the text"
    if block_task_id and block_task_id in by_id:
        return by_id[block_task_id], "running block"
    return None, None


def is_long(answer, s):
    return len(answer) > s["longChars"] or answer.count("\n") + 1 > s["longLines"]


ORG_CHATTER = re.compile(r"\(?[^()\n.]*\b(?:prompt[- ]optimizer|your organization (?:asks|requires|instructs)|organization instructions?)\b[^()\n]*?(?:\)|\.(?=\s|$))\s*", re.I)


def strip_org_chatter(text: str) -> str:
    """Models run through the Claude login sometimes mention the organization's prompt-optimizer instruction. That is noise
    in an answer, so the sentence is dropped (the setting itself belongs to the organization's admin, not to this tool)."""
    cleaned = ORG_CHATTER.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip() if cleaned != text else text


def routing_line(res):
    if res.handled_by == "priority-engine":
        return "engine · no model · step 0"
    units = (res.log or {}).get("units_this_turn", 0)
    model = (res.model or "?").split("/")[-1]
    parts = [res.tier or "?", model, f"effort {res.effort or 'none'}", res.outcome,
             f"{len(res.attempts)} attempt{'s' if len(res.attempts) != 1 else ''}", f"{units} units", res.reason]
    return " · ".join(str(p) for p in parts if p)


def failure_text(res):
    last = res.attempts[-1] if res.attempts else None
    err = (last.error or last.outcome) if last else "no attempt ran"
    tier_note = {
        "sonnet": "Sonnet and Opus never retry on their own.",
        "opus": "Sonnet and Opus never retry on their own.",
    }.get(res.tier, "The free models and Haiku were tried as the plan allows.")
    return f"It didn't work: {err}. {tier_note} Retag with @haiku, @sonnet or @opus to try another model."


# ------------------------------------------------------------------ runner
def default_router_factory(engine_fn):
    from router.core import Router
    return Router(priority_engine=engine_fn)


class CommandRunner:
    def __init__(self, state_dir=None, router_factory=default_router_factory, load_config=None, sync=False, matcher=None):
        self.dir = Path(state_dir or STATE_DIR)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.jobs_path = self.dir / "jobs.json"
        self.results_path = self.dir / "results.json"
        self.archive_path = self.dir / "results-archive.jsonl"
        self.log_path = self.dir / "log.jsonl"
        self.router_factory = router_factory
        self.load_config = load_config or (lambda: brain.load_config())
        self.sync = sync  # tests: run the job inline instead of on a thread
        self.prep_deps = None  # None = real fetch/render/facts; tests inject fakes
        self.prep_store = prep_agent.BatchStore(self.dir.parent.parent / "prep" / "state" / "batches.json" if state_dir is None else self.dir / "prep-batches.json")
        self.play_path = None  # None = play/state/play.json; the server and tests set it
        self.matcher = matcher  # command/matcher.Matcher or None (tests and scripts never touch Ollama unless they pass one)
        self.undos = undo_mod.UndoStore(self.dir / "undo.json")
        self.lock = threading.Lock()
        self.errors = []
        self._recover()

    # ---- persistence
    def _jobs(self):
        data, err = _read(self.jobs_path, {"jobs": []})
        if err:
            self.errors.append(err)
        return data.get("jobs", []) if isinstance(data, dict) else []

    def _save_jobs(self, jobs):
        brain.write_json_atomic(self.jobs_path, {"version": 1, "jobs": jobs[-MAX_JOBS:]})

    def _update(self, job_id, **fields):
        with self.lock:
            jobs = self._jobs()
            for j in jobs:
                if j["id"] == job_id:
                    if j.get("status") == "cancelled":
                        return dict(j)  # a cancelled job stays cancelled
                    j.update(fields)
                    self._save_jobs(jobs)
                    return dict(j)
        return None

    def _recover(self):
        """A job left queued or running by a stopped server is marked interrupted, never dropped."""
        with self.lock:
            jobs = self._jobs()
            hit = False
            for j in jobs:
                if j["status"] in ("queued", "running"):
                    j.update(status="interrupted", finishedAt=iso(now_local()),
                             error="The dashboard server stopped while this was running. Send it again if you still need it.")
                    hit = True
            if hit:
                self._save_jobs(jobs)

    # ---- submit
    def submit(self, body, tasks, block_view=None):
        """Validate and start a job. Raises ValueError (bad input) or Busy."""
        config = self.load_config()
        s = settings(config)
        kind = body.get("kind", "ask")
        pasted = bool(body.get("pasted"))
        check_length(body.get("text", ""), config, pasted)
        prep_cmd = None
        if kind not in ("ask", "stuck"):
            raise ValueError("unknown command kind")
        block_task = (block_view or {}).get("block") or {}
        block_task_id = block_task.get("taskId") if (block_view or {}).get("phase") in ("work", "starting") else None
        raw = str(body.get("text", "")).strip()
        pre, forced = None, None
        if kind == "ask" and raw and not pasted and undo_mod.is_undo(plain.normalize(raw)):       # also with a task picked under Options
            return self.undo(None, raw, config)            # "undo", "take that back": the newest chat change
        if kind == "ask" and raw and not body.get("taskId") and not pasted:
            pre = intent.before_capture(plain.normalize(raw), tasks)
        if pre:
            label, data = pre
            if label == "tiny":
                return self._instant(raw, data, "quick reply · no model")
            if label == "schedule":
                return self._instant(raw, _task_due_line(data, now_local()), "schedule · no model")
            if label == "now":
                return self._instant(raw, engine_answer("now", None, config, block=block_view), "engine · no model · step 0")
            if label == "action":
                try:
                    plan, why_not = acts.plan_or_problem(plain.normalize(raw), tasks, current_id=block_task_id or self._current_task_id(config, tasks))
                    if plan:
                        ov_path = brain.resolve("overridesPath", config)
                        before = undo_mod.read_overrides(ov_path)
                        said = acts.execute(plan)
                        steps = undo_mod.diff_overrides(before, undo_mod.read_overrides(ov_path), [t["id"] for t in plan["tasks"]])
                        return self._instant(raw, said, "buttons · no model", steps=steps)
                    return self._instant(raw, why_not or intent.action_reply(data), "buttons · no model")
                except Exception as e:  # noqa: BLE001 - a sentence must never take the box down; the card's buttons still work
                    return self._instant(raw, f"I couldn't do that from a sentence: {e}. The button on the card still works.", "buttons · no model")
            if label == "stuck":                 # "I'm stuck on lab 7": the Stuck button, said as a sentence
                if data["words"]:                 # stuck on something that is not one of her tasks: a first step, free models only
                    forced = STUCK_PROMPT.format(title=data["words"][:200], list="(not on a list)", notes="")
                else:
                    tid = (data["task"] or {}).get("id") or block_task_id or self._current_task_id(config, tasks)
                    if not tid:
                        return self._instant(raw, "Which task? Say it with the name, like: I'm stuck on lab 7.", "stuck · no model")
                    kind, body = "stuck", dict(body, taskId=tid)
        if kind == "stuck":
            tid = body.get("taskId") or block_task_id
            if not tid:
                raise ValueError("pick a task for Stuck")
            task, how = match_task("", tasks, explicit_id=str(tid))
            notes = (task.get("notes") or "").strip()
            text = STUCK_PROMPT.format(title=task["title"], list=task.get("list", ""),
                                       notes=("Notes: " + notes[:800]) if notes else "")
            shown = f"Stuck on: {task['title']}"
        else:
            text = raw if pasted else plain.normalize(raw)       # pasted text is sent as written (its spelling is the content)
            if not text:
                raise ValueError("type something first")
            limit = s["maxPasteChars" if pasted else "maxInputChars"]
            if len(text) > limit:
                raise ValueError(f"too long ({len(text)} characters, limit {limit})")
            tid = body.get("taskId") or None
            task, how = match_task(text, tasks, explicit_id=str(tid) if tid else None, block_task_id=block_task_id)
            shown = str(body.get("shown") or "pasted text")[:400] if pasted else text   # pasted words never reach jobs.json or the log
            if forced is not None:
                text = forced
            elif not pasted:
                name = project_status.parse_intent(text)
                if not name and project_status.is_bare(text):
                    focus = self._focus_project(config, tasks)
                    if focus:
                        return self._project_status(text, focus["title"], tasks, config, exact_id=focus["id"])
                    return self._instant(text, "Nothing is in focus right now. Say which project: where did I leave off on <project>.", "project status · no model")
                if name:
                    return self._project_status(text, name, tasks, config)
                idea = park.parse(text)
                if idea is not None:
                    return self._park(text, idea)
                rq = reminders_qa.parse(text)
                if rq:
                    return self._reminders(text, rq)
                cq = class_qa.parse(text)
                if cq:
                    ans = class_qa.answer(cq, _commitments(config), now_local())
                    if ans:
                        return self._instant(text, ans, "calendar · no model")
                lq = lookup.detect(text)
                if lq:
                    res = lookup.search(lq, config)
                    if res["files"] or lq["modules"] or lq["weeks"] or lq["kinds"]:
                        return self._instant(text, res["answer"], "file lookup · no model", files=res["files"])
                sq = schedule_qa.parse(text, config, now_local())
                if not sq and intent.planning_fallback(text, tasks, _lists_of(tasks)) == "schedule":
                    sq = schedule_qa.parse(text, config, now_local(), force=True)       # her schedule, said some other way
                if sq:
                    return self._instant(text, schedule_qa.answer(sq, tasks, config, now_local(), parse_dt), "schedule · no model")
                prep_cmd = prep_agent.parse_command(text)
                if prep_cmd:
                    kind = "prep"
                elif not body.get("followUp") and not body.get("taskId"):
                    meant = self._meaning(text, tasks, config, block_view)
                    if meant is not None:
                        return meant

        with self.lock:
            jobs = self._jobs()
            running = next((j for j in jobs if j["status"] in ("queued", "running")), None)
            if running:
                raise Busy(f"Busy with \"{running['input'][:60]}\". One command at a time.")
            prev = next((j for j in reversed(jobs) if j.get("conversation")), None)
            follow = bool(body.get("followUp")) and prev is not None
            jid = new_job_id(jobs)
            job = {
                "id": jid,
                "kind": kind, "status": "queued", "input": shown,
                "taskId": task["id"] if task else None, "taskTitle": task["title"] if task else None,
                "taskList": task.get("list") if task else None, "taskMatch": how,
                "conversation": prev["conversation"] if follow else None,
                "followUp": follow, "createdAt": iso(now_local()),
                **({"pasted": True} if pasted else {}),
            }
            job["conversation"] = job["conversation"] or "dash-" + job["id"]
            jobs.append(job)
            self._save_jobs(jobs)
        prev_conv = None if follow or not prev else prev["conversation"]
        args = (job, text, config, s, block_view, prev_conv, prep_cmd)
        if self.sync:
            self._run(*args)
        else:
            threading.Thread(target=self._run, args=args, daemon=True).start()
        return self.get(job["id"])

    def _meaning(self, text, tasks, config, block_view):
        """Layer 2 (STATE_MODEL_MATCHER.md "Wiring"): the rules passed, so ask the meaning matcher. Read-only labels only;
        None means "go to the router as today" (no matcher, not sure, general, a tag or a Step 0 sentence)."""
        from router import rules
        if self.matcher is None or rules.parse_override(text) or rules.match_step0(text):
            return None
        try:
            m = self.matcher.classify(text)
        except Exception:  # noqa: BLE001 - classify never raises, but the box must never fall over on it
            return None
        if not m or not m.get("routable") or m.get("label") == "general":
            return None
        label = m["label"]
        routing = f"meaning match · {label} {m.get('score')} · no model"
        if label == "now":
            return self._instant(text, "I read that as: what should I do now.\n" + engine_answer("now", None, config, block=block_view), routing)
        if label == "schedule":
            sq = schedule_qa.parse(text, config, now_local(), force=True)
            if not sq:
                return None
            return self._instant(text, "I read that as a question about what's due.\n" + schedule_qa.answer(sq, tasks, config, now_local(), parse_dt), routing)
        if label == "project":
            focus = self._named_project(text, tasks, config) or self._focus_project(config, tasks)
            if not focus:
                return self._instant(text, "I read that as a question about a project, but I can't tell which one. Say it with the name: where am I on <project>.", routing)
            job = self._project_status(text, focus["title"], tasks, config, exact_id=focus["id"], read_only=True)
            return self._lead(job, f"I read that as: where am I on {focus['title']}.", routing)
        if label == "reminders":
            return self._lead(self._reminders(text, ("list", None)), "I read that as: which reminders are waiting.", routing)
        if label == "tiny":
            return self._instant(text, "Got it. Ask what's next whenever you're ready.", routing)
        return None

    def _named_project(self, text, tasks, config):
        """The one project whose distinctive title words appear in the sentence ("how's the analyzer coming along"), else None."""
        have = set(plain.words(text))
        hits = [c for c in self._project_cands(tasks, config, play_store.load(self.play_path))
                if any(w in have for w in plain.words(c["title"]) if len(w) > 3 and w not in plain.NAME_STOP)]
        return {"id": hits[0]["id"], "title": hits[0]["title"]} if len(hits) == 1 else None

    def undo(self, undo_id, text, config=None):
        """Take back one chat change (STATE_MODEL_UNDO.md). undo_id None = the newest from the last 2 minutes.
        The reply is a finished job, like any answer."""
        config = config or self.load_config()
        now = now_local()
        shown = text or "Undo"
        e, why = self.undos.take(undo_id, now)
        if e is None:
            return self._instant(shown, why, "undo · no model")
        try:
            ok, why = undo_mod.apply(e["steps"], config, self.play_path)
        except (OSError, ValueError) as ex:
            ok, why = False, f"I couldn't undo that: {ex}"
        with self.lock:
            jobs = self._jobs()
            j = next((x for x in jobs if x["id"] == e.get("jobId")), None)
            if j is not None and j.get("undo"):
                j["undo"] = dict(j["undo"], used=True)
                self._save_jobs(jobs)
        if not ok:
            return self._instant(shown, why, "undo · no model")
        label = (e.get("label") or "").strip().rstrip(".")
        return self._instant(shown, f"Undone. I took back: {label}." if label else "Undone. It's back the way it was.", "undo · no model")

    def _lead(self, job, lead, routing=None):
        """Put a first-person lead line in front of an instant answer (and swap its routing line)."""
        with self.lock:
            jobs = self._jobs()
            j = next((x for x in jobs if x["id"] == job["id"]), None)
            if j is None:
                return job
            j["answer"] = lead + "\n" + (j.get("answer") or "")
            if routing:
                j["routing"] = routing
            self._save_jobs(jobs)
        return self.get(job["id"])

    def _current_task_id(self, config, tasks):
        """The task the engine recommends right now, if it is still open."""
        try:
            cur = (brain.read_json(brain.resolve("recommendationPath", config), default=None) or {}).get("current") or {}
        except (OSError, ValueError):
            return None
        tid = cur.get("taskId")
        return tid if tid and any(t["id"] == tid for t in tasks or []) else None

    def _focus_project(self, config, tasks):
        """The one project the engine has in focus (Security Projects), as {id, title}, or None."""
        try:
            rec = brain.read_json(brain.resolve("recommendationPath", config), default=None) or {}
        except (OSError, ValueError):
            return None
        for c in rec.get("categories", []):
            fid = c.get("focusId")
            if fid:
                t = next((x for x in tasks or [] if x["id"] == fid), None)
                if t:
                    return {"id": t["id"], "title": t["title"]}
        return None

    def _project_cands(self, tasks, config, ps):
        """Every project she could mean: Play and focus-category tasks, plus the brain's own side projects."""
        cands = [{"id": t["id"], "title": t["title"], "notes": t.get("notes", ""), "list": t.get("list")}
                 for t in tasks or []
                 if (lambda c: c.get("play") or c.get("focus"))(category_for(t.get("list", ""), config, t.get("title", "")))]
        return cands + [{"id": p["id"], "title": p["title"], "path": p.get("path")} for p in ps.get("projects", [])]

    def _project_status(self, text, name, tasks, config, exact_id=None, read_only=False):
        """"Update the status of X": read the project's folder, save one plain line, no model (12j).
        read_only: never save the line (the meaning matcher only reads)."""
        now = now_local()
        ps = play_store.load(self.play_path)
        steps = None
        cands = self._project_cands(tasks, config, ps)
        k, v = plain.match_target(name, cands, stop=plain.NAME_STOP | {"app"})     # the one matcher: whole words, exact title first
        hit, why = (v, None) if k == "one" else (None, "ambiguous" if k == "many" else "none")
        if exact_id:
            hit, why = next((c for c in cands if c["id"] == exact_id), None), None
        roots = (config.get("play") or {}).get("projectRoots")
        if not hit:
            answer = (f"More than one project matches \"{name}\". Say which one." if why == "ambiguous"
                      else f"I don't see a project called \"{name}\".")
            line = None
        else:
            folder, how = project_status.resolve_folder(hit["title"], hit.get("notes", ""), hit.get("path"), roots)
            line = project_status.status_line(folder, now)
            if line:
                if not read_only and project_status.is_update(text) and not plain.is_question(text):   # asking never freezes the automatic line; only "update ..." saves it
                    st = play_store.apply(ps, "leftoff", now, taskId=hit["id"], text=line)
                    play_store.save(st, self.play_path)
                    steps = undo_mod.diff_play(ps, st)
                answer = f"{hit['title']}: {line}"
            else:
                answer = (f"Couldn't find a folder for {hit['title']}. Add a line \"path: <folder>\" to its notes.")
        with self.lock:
            jobs = self._jobs()
            job = {"id": new_job_id(jobs, now), "kind": "ask", "status": "done",
                   "input": text, "taskId": hit["id"] if hit else None, "taskTitle": hit["title"] if hit else None,
                   "taskList": hit.get("list") if hit else None, "taskMatch": "named in the text" if hit else None,
                   "conversation": None, "followUp": False, "createdAt": iso(now), "finishedAt": iso(now), "answer": answer,
                   "routing": "project status · no model", "warnings": [], "savedTo": None, "note": None, "long": False}
            u = self.undos.record(steps, f"saved the status line for {hit['title']}" if hit else "", job["id"], now) if steps else None
            if u:
                job["undo"] = u
            jobs.append(job)
            self._save_jobs(jobs)
        self._log(job, job["routing"])
        return self.get(job["id"])

    def _reminders(self, text, rq):
        """Which text reminders are waiting, or cancel one (no model)."""
        kind, query = rq
        ps = play_store.load(self.play_path)
        pending = sorted(ps.get("reminders", []), key=lambda r: r.get("at", ""))
        if kind == "list":
            if not pending:
                return self._instant(text, "No text reminders waiting. Say, for example: remind me to call mom tomorrow at 9am.", "reminders · no model")
            lines = reminders_qa.group_lines(pending)
            return self._instant(text, f"{len(lines)} text reminder{'s' if len(lines) != 1 else ''} waiting:\n" + "\n".join("- " + x for x in lines)
                                 + "\nSay \"cancel reminder <words>\" to drop one.", "reminders · no model")
        hits = reminders_qa.pick(pending, query)
        waiting = "\n".join("- " + reminders_qa.fmt(r) for r in pending) or "- (none)"
        if kind == "ask_cancel":                     # "cancel reminder to stretch?": a question, so nothing is dropped
            if not hits:
                return self._instant(text, "I don't see a waiting reminder like that, and I didn't cancel anything. Waiting:\n" + waiting, "reminders · no model")
            return self._instant(text, "Sounds like a question, so I didn't cancel anything. Waiting:\n" + "\n".join("- " + reminders_qa.fmt(r) for r in hits)
                                 + "\nSay \"cancel reminder <words>\" to drop one.", "reminders · no model")
        if not pending:
            return self._instant(text, "No text reminders waiting, so there's nothing to cancel.", "reminders · no model")
        if not hits:                                 # unsure: list what exists and drop nothing (an empty or unknown name never matches)
            lead = "Which one?" if not reminders_qa.plain_words(query) else f"I don't see a reminder called \"{query}\", so I didn't cancel anything."
            return self._instant(text, f"{lead} Waiting:\n{waiting}\nSay \"cancel reminder <words>\" with words from one of them.", "reminders · no model")
        if len(hits) > 1:
            return self._instant(text, "That matches more than one, so I didn't cancel anything:\n" + "\n".join("- " + reminders_qa.fmt(r) for r in hits) + "\nAdd a few more words to pick one.", "reminders · no model")
        st = play_store.apply(ps, "dropreminder", now_local(), id=hits[0]["id"])
        play_store.save(st, self.play_path)
        return self._instant(text, f"Cancelled: {hits[0]['text']}", "reminders · no model", steps=undo_mod.diff_play(ps, st))

    def _park(self, text, idea):
        """"Park this idea ...": one not-started side project in Play, no model (Phase 17b; ideas became projects 2026-11-12)."""
        if not idea:
            return self._instant(text, "What's the idea? Say it after the words, like: park this idea in playground: build a retro game launcher.", "side projects · no model")
        try:
            before = play_store.load(self.play_path)
            st = play_store.apply(before, "park", now_local(), text=idea)
            play_store.save(st, self.play_path)
        except ValueError as e:
            return self._instant(text, f"Couldn't park it: {e}", "side projects · no model")
        return self._instant(text, f"Added to your side projects: {idea}\nIt's in Play as a not-started project. Undo takes it back.", "side projects · no model",
                             steps=undo_mod.diff_play(before, st))

    def _instant(self, text, answer, routing, files=None, steps=None):
        """An answer produced by plain code (no model): saved as a finished job so the page shows it like any answer.
        steps: what this answer changed (undo.diff_*), so the answer carries an Undo for 2 minutes."""
        now = now_local()
        with self.lock:
            jobs = self._jobs()
            job = {"id": new_job_id(jobs, now), "kind": "ask", "status": "done",
                   "input": text, "taskId": None, "taskTitle": None, "taskList": None, "taskMatch": None,
                   "conversation": None, "followUp": False, "createdAt": iso(now), "finishedAt": iso(now),
                   "answer": answer, "files": files or [], "routing": routing,
                   "warnings": [], "savedTo": None, "note": None, "long": False}
            u = self.undos.record(steps, (answer or "").split("\n")[0], job["id"], now) if steps else None
            if u:
                job["undo"] = u
            jobs.append(job)
            self._save_jobs(jobs)
        self._log(job, job["routing"])
        return self.get(job["id"])

    def cancel(self, job_id):
        """Stop a queued or running job: kill the model process, stop retries, mark it cancelled."""
        with self.lock:
            jobs = self._jobs()
            job = next((j for j in jobs if j["id"] == job_id), None)
            if not job:
                return None
            if job["status"] not in ("queued", "running"):
                return dict(job)
            job.update(status="cancelled", finishedAt=iso(now_local()), error="Cancelled.")
            self._save_jobs(jobs)
            out = dict(job)
        _client_cancel(True)
        return out

    def get(self, job_id):
        return next((dict(j) for j in self._jobs() if j["id"] == job_id), None)

    # ---- run (background thread)
    def _run_prep(self, job, config, cmd):
        def engine_fn(query, window):
            return engine_answer(query, window, config, block=None)
        def stage(st, jid=job["id"]):
            try: self._update(jid, stage=st, stageAt=iso(now_local()))
            except Exception: pass
        try:
            router = self.router_factory(engine_fn)
            router.on_stage = stage
            deps = self.prep_deps(router) if self.prep_deps else prep_agent.default_deps(router)
            notify = None
            if not self.prep_deps:
                def notify(title, text):
                    sys.path.insert(0, str(ROOT / "push"))
                    import ntfy
                    ntfy.send(json.loads((ROOT / "push" / "config.json").read_text()), title, text)
            answer, batch = prep_agent.run_batch(cmd, deps, store=self.prep_store,
                                                 on_progress=lambda t: stage(t), notify=notify)
        except prep_agent.PrepError as e:
            fin = self._update(job["id"], status="failed", finishedAt=iso(now_local()), error=str(e), routing="prep")
            self._log(fin, f"prep failed: {e}")
            return
        except Exception as e:
            fin = self._update(job["id"], status="failed", finishedAt=iso(now_local()),
                               error=f"Prep couldn't run: {e}", routing="prep error")
            self._log(fin, f"prep failed: {e}")
            return
        ready = sum(1 for p in batch["postings"] if p["state"] == "ready")
        fin = self._update(job["id"], status="done", finishedAt=iso(now_local()), answer=answer,
                           routing=f"prep · {ready} ready of {len(batch['postings'])} · nothing submitted", long=True)
        self._log(fin, fin["routing"])

    def _run(self, job, text, config, s, block_view, prev_conv, prep_cmd=None):
        _client_cancel(False)
        self._update(job["id"], status="running", startedAt=iso(now_local()))
        if prep_cmd:
            return self._run_prep(job, config, prep_cmd)
        try:
            def engine_fn(query, window):
                return engine_answer(query, window, config, block=block_view)
            router = self.router_factory(engine_fn)
            def on_stage(st, jid=job["id"]):  # real progress for the loading bar; never fatal
                try:
                    self._update(jid, stage=st, stageAt=iso(now_local()))
                except Exception:
                    pass
            router.on_stage = on_stage
            self._close_conversation(router, prev_conv)
            res = router.route(text, conversation=job["conversation"],
                               **({"log_input": job["input"]} if job.get("pasted") else {}))
        except Exception as e:  # router or OpenCode down: show it, never swallow
            fin = self._update(job["id"], status="failed", finishedAt=iso(now_local()),
                               error=f"The router couldn't run: {e}", routing="router error")
            self._log(fin, f"command failed: {e}")
            return
        line = routing_line(res)
        warnings = list(res.warnings)
        if res.outcome.startswith("failed"):
            fin = self._update(job["id"], status="failed", finishedAt=iso(now_local()), routing=line,
                               warnings=warnings, error=failure_text(res), answer=res.answer or "")
            self._log(fin, f"{line} · failed")
            return
        answer = strip_org_chatter(res.answer or "")
        saved = None
        if job["taskId"] and (job["kind"] == "stuck" or is_long(answer, s)):
            self._save_result(job, answer, line)
            saved = job["taskId"]
        note = None
        if not saved and is_long(answer, s):
            note = "Long answer, but no matching task, so it was not saved to a task. Pick a task in the menu to save answers like this."
        fin = self._update(job["id"], status="done", finishedAt=iso(now_local()), answer=answer,
                           routing=line, warnings=warnings, savedTo=saved, note=note,
                           long=is_long(answer, s))
        self._log(fin, line)

    def _close_conversation(self, router, conv):
        """A new standalone command ends the previous one: archive its OpenCode session (reversible)."""
        if not conv:
            return
        try:
            pin = router.convs.get(conv)
            if pin and pin.get("session_id") and hasattr(router.client, "archive_session"):
                router.client.archive_session(pin["session_id"])
            router.convs.drop(conv)
        except Exception:
            pass  # housekeeping only

    def _save_result(self, job, answer, line):
        with self.lock:
            data, err = _read(self.results_path, {})
            if err:
                self.errors.append(err)
            items = data.setdefault(job["taskId"], [])
            items.append({"jobId": job["id"], "at": iso(now_local()), "kind": job["kind"], "input": job["input"],
                          "answer": answer, "routing": line, "title": job["taskTitle"], "list": job["taskList"]})
            while len(items) > MAX_RESULTS_PER_TASK:
                _append(self.archive_path, {"taskId": job["taskId"], **items.pop(0)})
            brain.write_json_atomic(self.results_path, data)

    def _log(self, job, line):
        if not job:
            return
        what = job["input"] if len(job["input"]) <= 60 else job["input"][:57] + "..."
        _append(self.log_path, {"at": iso(now_local()), "kind": "command", "id": job["id"],
                                "text": f"cmd \"{what}\" -> {line}" + (f" · saved to {job['taskTitle']}" if job.get("savedTo") else ""),
                                "warnings": job.get("warnings") or []})

    # ---- views
    def view(self, tasks, config):
        jobs = self._jobs()
        data, err = _read(self.results_path, {})
        if err:
            self.errors.append(err)
        open_ids = {t["id"] for t in tasks or []}
        groups = {}
        for tid, items in data.items():
            if not items:
                continue
            last = items[-1]
            cat = category_for(last.get("list") or "", config, last.get("title") or "")["name"] if tid in open_ids else "Finished tasks"
            groups.setdefault(cat, []).append({"taskId": tid, "title": last.get("title"), "results": items[::-1]})
        task_menu = sorted(({"taskId": t["id"], "title": t["title"],
                             "category": category_for(t.get("list", ""), config, t["title"])["name"],
                             **({"dueDate": t["dueDate"]} if t.get("dueDate") else {}),
                             **({"list": t["list"]} if t.get("list") else {})} for t in tasks or []),
                           key=lambda t: (t["category"], t["title"].lower()))
        errors, self.errors = self.errors, []
        return {
            "busy": any(j["status"] in ("queued", "running") for j in jobs),
            "jobs": jobs[-5:][::-1],
            "results": groups,
            "tasks": task_menu,
            "errors": errors,
        }

    def mission_log(self, history_path, rec):
        rows = [_block_line(r) for r in _tail_jsonl(history_path, LOG_LINES)]
        rows += [{"at": r["at"], "kind": "command", "text": r["text"]} for r in _tail_jsonl(self.log_path, LOG_LINES)]
        rows = sorted((r for r in rows if r), key=lambda r: r["at"])[-LOG_LINES:]
        c = (rec or {}).get("current")
        rows.append({"at": iso(now_local()), "kind": "now",
                     "text": f"now: {c['title']} ({c['why']})" if c else "now: nothing eligible"})
        return rows


BLOCK_WORDS = {
    "work_countdown": "block countdown", "work_start": "block started", "work_cancel": "block cancelled",
    "work_over": "block time up", "work_extend": "block extended", "work_end": "block done",
    "break_start": "break started", "break_over": "break over", "checkin": "check-in", "expired": "closed overnight",
}


def _lists_of(tasks):
    return sorted({t.get("list") for t in tasks or [] if t.get("list")})


def _commitments(config):
    cp = Path(config.get("commitmentsPath", "inputs/commitments.json"))
    try:
        data = json.loads((cp if cp.is_absolute() else ROOT / "engine" / cp).read_text())
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _task_due_line(task, now):
    """"When is lab 7 due": one line from the snapshot."""
    where = f" ({task['list']})" if task.get("list") else ""
    if not task.get("dueDate"):
        return f"{task['title']}{where} has no due date."
    d = parse_dt(task["dueDate"], now.tzinfo)
    when = d.strftime("%a %b %-d, %-I:%M %p")
    return f"{task['title']}{where}: " + (f"was due {when}. Still open; one small piece at a time." if d < now else f"due {when}.")


def _block_line(r):
    if not r.get("at"):
        return None
    word = BLOCK_WORDS.get(r.get("type"), (r.get("type") or "block").replace("_", " "))
    extra = r.get("title") or r.get("answer") or ""
    return {"at": r["at"], "kind": "block", "text": f"{word}: {extra}" if extra else word}
