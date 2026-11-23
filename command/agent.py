"""The chat agent (STATE_MODEL_AGENT.md): a free model with tools first, Haiku with the same tools as backup, nothing else.

The model sees a context card (her open tasks with short ids, lists, the current task, today's classes, the last chat
messages) and returns one JSON object: {"reply": "...", "action": null | {"tool": ..., ...}}. Plain code checks the
action before anything runs (the task exists and is open, the list is real, dates are real and not past) and never
guesses between two tasks with the same name. The chat (dashboard/chat.py) runs the checked action through the same
code the typed rules use.

Learning: a sentence a model handled, whose action passed the checks, is saved (command/state/learned.jsonl) with the
action in words that do not depend on today's ids. The same sentence again (or one the local meaning matcher scores
as the same) replays that action with no model call.
"""
from __future__ import annotations

import json
import re
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for p in (HERE, ROOT / "router"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
import plain  # noqa: E402

STATE_DIR = HERE / "state"
MAX_TASKS = 60
RECENT_ROWS = 10
FREE_TIMEOUT_S = 25
HAIKU_TIMEOUT_S = 60
LEARN_THRESHOLD = 0.90
FREE_PREFERENCE = ["deepseek-v4.1-flash-free", "hy4-flash-free", "tidepool-alpha-free", "iceman-free"]
PLAY_LISTS = {"play", "side projects", "games"}

TASK_TOOLS = {"done", "snooze", "skip", "pin", "unpin"}
TOOLS = TASK_TOOLS | {"add", "start", "break", "back", "extend", "park", "due", "find", "where"}
LEARNABLE = TASK_TOOLS | {"start", "break", "back", "extend", "due", "find", "where"}
WINDOWS = {"today", "tonight", "tomorrow", "this week", "next week", "this weekend", "overdue", "next", "this month"}

PROMPT = """You are Thalamus, the chat inside Morgan's planner. You talk in the first person, short, calm and plain. No markdown headings, no lists unless she asks.

Answer with ONE JSON object and nothing else, no code fence:
{{"reply": "<what you say to her>", "action": null}}
or with one action:
{{"reply": "<short line>", "action": {{"tool": "<tool>", ...arguments}}}}

Tools (at most one per message):
- done {{"task": "t3"}}: mark a task done
- add {{"title": "Email Dr. Lee", "list": "<one of her lists>", "due": "YYYY-MM-DDTHH:MM" or null, "remind": false}}: add a task. remind true means only text her at that time, nothing goes on a list.
- snooze {{"task": "t3", "hours": 3}} or {{"task": "t3", "until": "YYYY-MM-DDTHH:MM"}}: hide it until then
- skip {{"task": "t3"}}: not today, it comes back tomorrow
- pin {{"task": "t3"}} / unpin {{"task": "t3"}}: keep it on top today
- start {{"task": "t3"}} or {{"task": null}}: start a work block (null = the current task)
- break {{}}: stop the running block and take a break
- back {{}}: end the break
- extend {{"minutes": 15}}: more time on the running block
- park {{"idea": "..."}}: save an idea for later (not a task)
- due {{"window": "today" | "tomorrow" | "this week" | "next week" | "overdue" | "next", "list": "<list>" or null}}: what's due. I fill in the facts.
- find {{"query": "teaching notes module 5"}}: find a file on her Mac. I fill in the results.
- where {{"project": "network traffic analyzer"}}: where she left off on a project. I fill in the status.

Rules:
- Use only task ids from the list below, and only inside "action". Never show an id like t3 to her; name tasks by title and list. Never invent tasks, dates, grades or files.
- Tasks often share a name across classes (two "Read Chapter 7"). If her words could mean more than one task and nothing she said (the class, the chat so far, "this one" meaning the current task) singles one out, set action to null and ask which one, naming each with its list.
- If she asks about her tasks, deadlines, files or projects, use due, find or where instead of answering from memory. Keep the reply to a few words; I add the facts.
- Anything else (a general question, a concept from class, small talk): answer in "reply" with action null, in under about 120 words unless she asks for more. For long writing or real studying, give a short useful start and say Claude is better for the full thing.
- Dates: write them as YYYY-MM-DDTHH:MM in her local time. With no time named, use 12:00. Never a date in the past.
- If she is just chatting or thanking you, reply briefly with action null.

Now: {now}
{block}
Current task ("do this now"): {current}

Her lists: {lists}

Open tasks (id | title | list | due{flags}):
{tasks}
{play}
Today's classes and tests: {classes}

The chat so far (oldest first):
{rows}
{pending}
Her new message: {message}"""


class Problem(Exception):
    """An action that must not run. kind: model (the model got it wrong: try Haiku), ask (a question for her), say (tell her)."""

    def __init__(self, kind, text, options=None):
        super().__init__(text)
        self.kind, self.text, self.options = kind, text, options or []


def _when(dt):
    return dt.strftime("%a %b %-d, %-I:%M %p").replace(":00 ", " ")


def _due_of(t):
    try:
        return datetime.fromisoformat(str(t.get("dueDate")))
    except (TypeError, ValueError):
        return None


def norm(text):
    return " ".join(plain.words(plain.normalize(text or "")))


# ------------------------------------------------------------------ context card
def build_card(message, ctx, now):
    """(prompt text, {short id: task}). ctx: tasks, lists, current (dict or None), block (dict), classes (list of str),
    rows (chat rows, oldest first), pending (str or None)."""
    tasks = [t for t in ctx.get("tasks") or [] if t.get("id") and t.get("title")]
    want = set(plain.words(message)) - plain.NAME_STOP
    work = [t for t in tasks if (t.get("list") or "").lower() not in PLAY_LISTS]
    play = [t for t in tasks if (t.get("list") or "").lower() in PLAY_LISTS]

    def key(t):
        d = _due_of(t)
        hit = bool(want & set(plain.words(t["title"])))
        return (not hit, d is None, d.timestamp() if d else 0, t["title"])

    work = sorted(work, key=key)[:MAX_TASKS]
    idmap, lines = {}, []
    ov = ctx.get("flags") or {}
    for i, t in enumerate(work + play[:15], 1):
        sid = f"t{i}"
        idmap[sid] = t
        d = _due_of(t)
        due = _when(d.astimezone(now.tzinfo) if d.tzinfo else d) if d else "no date"
        if d and d < now:
            due += " (overdue)"
        flag = ov.get(t["id"])
        line = f"{sid} | {t['title']} | {t.get('list') or 'no list'} | {due}" + (f" | {flag}" if flag else "")
        lines.append(line)
    work_lines, play_lines = lines[:len(work)], lines[len(work):]
    cur = ctx.get("current") or {}
    cur_sid = next((k for k, v in idmap.items() if v["id"] == cur.get("taskId")), None)
    current = f"{cur_sid} {cur.get('title')}" if cur_sid else (cur.get("title") or "nothing")
    blk = ctx.get("block") or {}
    block = ""
    if blk.get("phase") in ("work", "starting"):
        block = f"A work block is running on \"{blk.get('title')}\"."
    elif blk.get("phase") == "break":
        block = "She is on a break."
    rows = []
    for r in (ctx.get("rows") or [])[-RECENT_ROWS:]:
        txt = (r.get("text") or "").strip().replace("\n", " ")
        if txt:
            rows.append(("Morgan: " if r.get("who") == "me" else "Thalamus: ") + txt[:400])
    text = PROMPT.format(
        now=now.strftime("%A %B %-d %Y, %-I:%M %p (") + now.strftime("%Y-%m-%dT%H:%M") + ")",
        block=block, current=current,
        lists=", ".join(ctx.get("lists") or []) or "(none)",
        flags=" | pinned/snoozed" if ov else "",
        tasks="\n".join(work_lines) or "(none)",
        play=("\nPlay items (for breaks, never work blocks):\n" + "\n".join(play_lines) + "\n") if play_lines else "",
        classes="; ".join(ctx.get("classes") or []) or "none",
        rows="\n".join(rows) or "(nothing yet)",
        pending=f"\nOpen question you asked her: {ctx['pending']}\n" if ctx.get("pending") else "",
        message=message,
    )
    return text, idmap


# ------------------------------------------------------------------ parsing and checks
def parse_reply(raw):
    """The model's JSON object, or None. Tolerates a code fence or words around it."""
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        obj = json.loads(s[a:b + 1])
    except ValueError:
        return None
    if not isinstance(obj, dict) or not isinstance(obj.get("reply", ""), str):
        return None
    act = obj.get("action")
    if act is not None and (not isinstance(act, dict) or act.get("tool") not in TOOLS):
        return None
    return {"reply": (obj.get("reply") or "").strip(), "action": act}


def strip_ids(reply, idmap):
    """Drop a leaked short id ("t1 AWS Intro Labs" -> "AWS Intro Labs"); the prompt says not to, models sometimes do."""
    out = re.sub(r"\(?\b(t\d{1,3})\b\)?[:.]?\s?", lambda m: "" if m.group(1) in idmap else m.group(0), reply)
    return re.sub(r" +([,.?!;])", r"\1", out).strip()


def _dt(v, now, field):
    try:
        d = datetime.fromisoformat(str(v).strip().replace(" ", "T"))
    except ValueError:
        raise Problem("model", f"bad {field} date {v!r}")
    if d.tzinfo is None:
        d = d.replace(tzinfo=now.tzinfo)
    return d


def _list_words(name):
    return set(plain.words(name or "")) - {"the", "my", "class", "course", "list"}


def check(action, idmap, ctx, message, now, chosen=False):
    """The action with real tasks and parsed values, or raises Problem. Never guesses between two same-named tasks
    (chosen=True: she just picked which one)."""
    tool = action["tool"]
    out = {"tool": tool}
    lists = ctx.get("lists") or []
    if tool in TASK_TOOLS or (tool == "start" and action.get("task")):
        sid = str(action.get("task") or "").strip()
        t = idmap.get(sid)
        if t is None:
            raise Problem("model", f"unknown task id {sid!r}")
        if not chosen:
            _not_ambiguous(t, ctx, message)
        if tool == "start" and (t.get("list") or "").lower() in PLAY_LISTS:
            raise Problem("say", "Play items are for breaks, not work blocks.")
        out["task"] = t
    if tool == "snooze":
        if action.get("until"):
            d = _dt(action["until"], now, "snooze")
            if d <= now:
                raise Problem("model", "snooze date is in the past")
            out["until"] = d
        else:
            try:
                h = float(action.get("hours") or 1)
            except (TypeError, ValueError):
                raise Problem("model", "bad hours")
            if not 0.25 <= h <= 72:
                raise Problem("say", "I can snooze something for 15 minutes up to 72 hours. Pick a time inside that.")
            out["hours"] = h
    elif tool == "add":
        title = re.sub(r"\s+", " ", str(action.get("title") or "")).strip(" .")
        if not title:
            raise Problem("model", "add without a title")
        out["title"] = title[:1].upper() + title[1:200]
        want = str(action.get("list") or "").strip().lower()
        out["list"] = next((l for l in lists if l.lower() == want), None)
        out["remind"] = bool(action.get("remind"))
        due = action.get("due")
        if due:
            d = _dt(due, now, "due")
            if d.date() < now.date():
                raise Problem("model", "due date in the past")
            out["due"] = d.strftime("%Y-%m-%dT%H:%M")
        else:
            out["due"] = None
    elif tool == "extend":
        try:
            m = int(action.get("minutes") or 15)
        except (TypeError, ValueError):
            raise Problem("model", "bad minutes")
        if not 5 <= m <= 60:
            raise Problem("say", "I can add 5 to 60 minutes at a time.")
        out["minutes"] = m
    elif tool == "park":
        idea = str(action.get("idea") or "").strip()
        if not idea:
            raise Problem("model", "park without an idea")
        out["idea"] = idea[:300]
    elif tool == "due":
        w = str(action.get("window") or "this week").strip().lower()
        out["window"] = w if w in WINDOWS else "this week"
        want = str(action.get("list") or "").strip().lower()
        out["list"] = next((l for l in lists if l.lower() == want), None)
    elif tool == "find":
        q = str(action.get("query") or "").strip()
        if not q:
            raise Problem("model", "find without a query")
        out["query"] = q[:200]
    elif tool == "where":
        p = str(action.get("project") or "").strip()
        if not p:
            raise Problem("model", "where without a project")
        out["project"] = p[:200]
    return out


def _not_ambiguous(t, ctx, message):
    """Raises Problem("ask") when another open task has the same name and nothing singles this one out."""
    same = [x for x in ctx.get("tasks") or [] if plain.words(x["title"]) == plain.words(t["title"])]
    if len(same) < 2:
        return
    cur = (ctx.get("current") or {}).get("taskId")
    blk = (ctx.get("block") or {}).get("taskId")
    if t["id"] in (cur, blk) and re.search(r"\b(this|it|this one|current)\b", message.lower()):
        return                                    # "mark this done": the task on screen
    said = set(plain.words(message))
    named = [x for x in same if _list_words(x.get("list")) and _list_words(x.get("list")) <= said]
    if len(named) == 1 and named[0] is t:
        return                                    # her words name the class, and only one copy is in it
    if not named:
        rw = set(plain.words(" ".join((r.get("text") or "") for r in (ctx.get("rows") or [])[-4:])))
        recent = [x for x in same if _list_words(x.get("list")) and _list_words(x.get("list")) <= rw]
        if len(recent) == 1 and recent[0] is t:
            return                                # the last few messages were about this class
    opts = named if len(named) > 1 else same
    lists = {x.get("list") for x in opts}

    def name(x):
        d = _due_of(x)
        due = f", due {_when(d)}" if d else ""
        return f"\"{x['title']}\" ({x.get('list') or 'no list'}{due})" if len(lists) == 1 else f"\"{x['title']}\" ({x.get('list') or 'no list'})"
    names = [name(x) for x in opts]
    lead = "Two open tasks are called that: " if len(opts) == 2 else "A few open tasks are called that: "
    raise Problem("ask", lead + (", ".join(names[:-1]) + " or " + names[-1]) + ". Which one?", options=opts)


def self_contained(text, action):
    """True when her sentence names its own target, so replaying it later means the same thing ("the second one" does not)."""
    t = action.get("task")
    if not t:
        return True
    said = set(plain.words(text)) - plain.NAME_STOP
    names = (set(plain.words(t["title"])) | _list_words(t.get("list"))) - plain.NAME_STOP
    if said & names:
        return True
    stem = lambda w: w[:4] if len(w) >= 4 else None    # "applications" names "Apply to 10"
    return bool({stem(w) for w in said} & {stem(w) for w in names} - {None})


# ------------------------------------------------------------------ learned sentences
class Learned:
    def __init__(self, path, matcher=None):
        self.path = Path(path)
        self.matcher = matcher
        self._vecs = {}
        self.lock = threading.Lock()

    def load(self):
        try:
            return [json.loads(x) for x in self.path.read_text().splitlines() if x.strip()]
        except (OSError, ValueError):
            return []

    def _write(self, rows):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(r) + "\n" for r in rows))
        tmp.replace(self.path)

    def save(self, text, action, now):
        """Store the action in words that do not depend on today's ids."""
        n = norm(text)
        if not n or action["tool"] not in LEARNABLE or (action["tool"] == "snooze" and action.get("until")):
            return                                # a dated snooze ("until Friday") would replay the wrong day
        rec = {"text": n, "tool": action["tool"], "at": now.isoformat(timespec="seconds")}
        if action.get("task"):
            rec["task"] = {"title": action["task"]["title"], "list": action["task"].get("list")}
        for k in ("hours", "minutes", "window", "list", "query", "project"):
            if action.get(k) is not None:
                rec[k] = action[k]
        with self.lock:
            rows = [r for r in self.load() if r.get("text") != n]
            rows.append(rec)
            self._write(rows[-500:])

    def forget(self, text):
        n = norm(text)
        with self.lock:
            rows = self.load()
            keep = [r for r in rows if r.get("text") != n]
            if len(keep) != len(rows):
                self._write(keep)
                return True
        return False

    def _similar(self, n, rows):
        m = self.matcher
        if m is None or not getattr(m, "_active", lambda: False)():
            return None
        try:
            need = [r["text"] for r in rows if r["text"] not in self._vecs]
            if need:
                for t, v in zip(need, m._embed(need, 3) or []):
                    self._vecs[t] = _unit(v)
            q = _unit((m._embed([n], 2) or [None])[0])
        except Exception:  # noqa: BLE001 - Ollama off or slow: no learned match, the model answers
            return None
        if q is None:
            return None
        best, score = None, 0.0
        for r in rows:
            v = self._vecs.get(r["text"])
            if v and len(v) == len(q):
                s = sum(a * b for a, b in zip(q, v))
                if s > score:
                    best, score = r, s
        return (best, score) if best and score >= LEARN_THRESHOLD else None

    def match(self, text, ctx):
        """(action dict ready for check-free dispatch, score) or None. A task must resolve to exactly one open task."""
        n = norm(text)
        rows = self.load()
        if not n or not rows:
            return None
        hit = next(((r, 1.0) for r in reversed(rows) if r.get("text") == n), None) or self._similar(n, rows)
        if not hit:
            return None
        rec, score = hit
        act = {"tool": rec["tool"]}
        if rec.get("task"):
            want = rec["task"]
            open_ = [t for t in ctx.get("tasks") or [] if plain.words(t["title"]) == plain.words(want["title"])
                     and (t.get("list") or None) == (want.get("list") or None)]
            if len(open_) != 1:
                return None
            try:
                _not_ambiguous(open_[0], ctx, text)
            except Problem:
                return None
            act["task"] = open_[0]
        for k in ("hours", "minutes", "window", "list", "query", "project"):
            if rec.get(k) is not None:
                act[k] = rec[k]
        return act, round(score, 3)


def _unit(v):
    if not isinstance(v, list) or not v:
        return None
    n = sum(x * x for x in v) ** 0.5
    return [x / n for x in v] if n > 1e-9 else None


# ------------------------------------------------------------------ model calls
class Models:
    """The two model calls the agent may make. Free: an `opencode run` session (free models refuse the stateless
    endpoint), archived after. Haiku: the stateless endpoint, low effort, counted in the usage file."""

    def __init__(self, router_cfg=None):
        if router_cfg is None:
            router_cfg = json.loads((ROOT / "router" / "config.json").read_text())
        self.cfg = router_cfg
        self._client = None
        self._roster, self._roster_at = None, 0.0

    def client(self):
        if self._client is None:
            from router.opencode_client import OpenCodeClient
            import os
            c = self.cfg
            self._client = OpenCodeClient(c["opencode_cli"], os.path.expanduser(c["workspace"]), False,
                                          c.get("permissions"), 40, c.get("opencode_agent"))
        return self._client

    def roster(self):
        if self._roster is None or time.time() - self._roster_at > 600:
            from router.models import build_roster
            self._roster = build_roster(self.client().list_models(), self.cfg)
            self._roster_at = time.time()
        return self._roster

    def free_model(self):
        ids = [m.id for m in self.roster().free]
        for want in FREE_PREFERENCE:
            if want in ids:
                return want
        return ids[0] if ids else None

    def free(self, prompt, timeout=FREE_TIMEOUT_S):
        """(text, model id) or raises RuntimeError."""
        model = self.free_model()
        if not model:
            raise RuntimeError("no free model is available")
        r = self.client().run(self.cfg["free_provider"], model, prompt, timeout=timeout, title="thalamus chat")
        if r.session_id:
            threading.Thread(target=self._archive, args=(r.session_id,), daemon=True).start()
        self._usage().record_free(model, "ok" if r.ok else (r.error_kind or "error"))
        if not r.ok:
            raise RuntimeError(r.error or "the free model failed")
        if r.tool_calls:
            raise RuntimeError("the free model tried to use a tool")
        return r.text, model

    def haiku(self, prompt, timeout=HAIKU_TIMEOUT_S):
        m = self.roster().claude.get("haiku")
        if m is None:
            raise RuntimeError("Haiku is not available")
        text = self.client().generate_text(self.cfg["claude_provider"], m.id, prompt, variant="low", timeout=timeout)
        self._usage().record_claude("haiku", m.key, m.multiplier or 0.1, "chat")
        return text, m.id

    def _archive(self, sid):
        try:
            self.client().archive_session(sid)
        except Exception:  # noqa: BLE001
            pass

    def _usage(self):
        from router.state import Usage
        return Usage(ROOT / "router" / "state", self.cfg.get("usage_warn_limits") or {})


# ------------------------------------------------------------------ the agent
class Agent:
    def __init__(self, models=None, state_dir=None, matcher=None):
        self.models = models                     # Models() or a fake with .free(prompt) and .haiku(prompt)
        d = Path(state_dir or STATE_DIR)
        self.log_path = d / "agent-log.jsonl"
        self.learned = Learned(d / "learned.jsonl", matcher)

    def _m(self):
        if self.models is None:
            self.models = Models()
        return self.models

    def respond(self, message, ctx, now, haiku_only=False, cancelled=lambda: False, stage=lambda s: None, pasted=False):
        """-> {"step", "model", "reply", "action" (checked) | None, "problem" (Problem) | None, "seconds", "learned"}.
        Never raises for a model failure: step "none" with a reply saying so."""
        t0 = time.time()
        out = {"step": "none", "model": None, "reply": "", "action": None, "problem": None, "learned": None}
        if not pasted and not haiku_only:
            hit = self.learned.match(message, ctx)
            if hit:
                act, score = hit
                out.update(step="learned", action=act, learned=score)
                return self._done(out, t0, message, pasted)
        prompt, idmap = build_card(message, ctx, now)
        steps = [("haiku", self._m().haiku)] if haiku_only else [("free", self._m().free), ("haiku", self._m().haiku)]
        errors = []
        for name, call in steps:
            if cancelled():
                out["step"] = "cancelled"
                return self._done(out, t0, message, pasted)
            stage("thinking" if name == "free" else "asking Haiku")
            try:
                raw, model = call(prompt)
            except Exception as e:  # noqa: BLE001 - any model failure moves on to the next step
                errors.append(f"{name}: {e}")
                continue
            obj = parse_reply(raw)
            if obj is None:
                errors.append(f"{name}: not the JSON object")
                continue
            out.update(step=name, model=model, reply=strip_ids(obj["reply"], idmap))
            if obj["action"] is None:
                if not obj["reply"]:
                    errors.append(f"{name}: empty reply")
                    continue
                return self._done(out, t0, message, pasted)
            try:
                out["action"] = check(obj["action"], idmap, ctx, message, now)
                return self._done(out, t0, message, pasted)
            except Problem as p:
                if p.kind == "model":
                    errors.append(f"{name}: {p.text}")
                    out.update(action=None, reply="")
                    continue
                out["problem"], out["raw"] = p, obj["action"]
                return self._done(out, t0, message, pasted)
        out.update(step="none", reply="I couldn't do that one. Try saying it another way.", errors=errors)
        return self._done(out, t0, message, pasted)

    def _done(self, out, t0, message, pasted):
        out["seconds"] = round(time.time() - t0, 2)
        a = out.get("action") or {}
        line = {"at": datetime.now().astimezone().isoformat(timespec="seconds"), "step": out["step"], "model": out["model"],
                "seconds": out["seconds"], "tool": a.get("tool"), "problem": getattr(out.get("problem"), "kind", None),
                "errors": out.get("errors"), "learned": out.get("learned")}
        line["text"] = f"(pasted, {len(message)} chars)" if pasted else message[:300]
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a") as f:
                f.write(json.dumps(line) + "\n")
        except OSError:
            pass
        return out
