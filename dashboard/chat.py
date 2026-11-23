"""The chat drawer's conversation (STATE_MODEL_CHAT.md). Plain code, no model of its own.

One store, command/state/chat.json: today's rows, one pending question, and the block state last seen. Everything she
types arrives at Chat.send; replies are first person and come back as rows. Adds and Dones go through the same requests
as the old buttons (dashboard/done_actions.py), so nothing says "Added" or "Done" before QuickToDo confirms.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "command" / "state"
DAY_START_HOUR = 4          # the chat starts fresh each morning; a late-night session does not reset at midnight
MAX_ROWS = 50
KEEP_ROWS = 120             # rows kept in the file for today (the view shows the last MAX_ROWS)
FOLLOW_MINUTES = 10
PENDING_MINUTES = 30        # a question nobody answered for this long is dropped
AGENT_STALE_MIN = 3         # an agent row still thinking after this long lost its thread (server restart): say so
MAX_PASTES = 5
MAX_PASTE_CHARS = 20000
PASTE_CHIP = re.compile(r"\[Pasted text #(\d+)(?: · \d+ lines?)?\]")

YES = re.compile(r"(?:yes|yeah|yep|yup|ya|yea|yes please|sure|sure thing|ok|okay|k|kk|ok add it|okay add it|sounds good|sounds right|"
                 r"that's right|thats right|right|correct|do it|add it|go ahead|go for it|perfect|great|looks good|good|fine|bet|"
                 r"please|please do|yes add it|yep add it|that works|works for me|confirm|confirmed|y)")
NO = re.compile(r"(?:no|nope|nah|cancel|never mind|nevermind|nvm|don't|dont|don't add it|dont add it|forget it|forget about it|"
                r"no thanks|no thank you|skip it|scratch that|leave it|not now)")
NO_DATE = re.compile(r"(?:no date|no due date|without a date|no deadline|whenever|no rush|any time|anytime)")
TITLE_FIX = re.compile(r"(?:call it|name it|rename it(?: to)?|title it|make the title|change the title to|change the name to) (.+)")
CHECK_YES = re.compile(r"(?:yes|yeah|yep|yup|ya|yea|sure|i did|i did something|did|kind of|kinda|a bit|a little|sort of)(?: .*)?")
CHECK_NO = re.compile(r"(?:no|nope|nah|i didn't|didnt|i did not|not really|not this time)(?: .*)?")
CHECK_LATER = re.compile(r"(?:not now|later|skip|skip it|maybe later|ask me later|pass)")

BEGIN_NOW = re.compile(r"(?:begin|start|go) now|skip (?:the )?countdown|(?:just )?go")
EXTEND = re.compile(r"(?:give me |add |i need |need |can i (?:get|have) )?(?:(?P<n>\d{1,2}|fifteen|ten|twenty|thirty) )?(?:more|extra) "
                    r"(?:minutes?|mins?|time)(?: please)?|(?:i need |need )?more time(?: please)?|extend(?: it| the block| the timer)?"
                    r"(?: by (?P<m>\d{1,2}) ?(?:minutes?|mins?))?|(?:add|another) (?P<k>\d{1,2}) (?:more )?(?:minutes?|mins?)|\+ ?(?P<p>\d{1,2})(?: ?min(?:utes?)?)?")
NUMS = {"ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30}
CANCEL_BLOCK = re.compile(r"cancel(?: the| this| my)?(?: block| timer| it)?|stop the (?:block|timer|clock)|end the block|scrap (?:the|this) block|"
                          r"(?:i )?(?:didn't|did not) mean to start(?: (?:it|that|this))?|never mind(?: the block)?")
SKIP_BREAK = re.compile(r"(?:done|stop|finished|i'm done|im done|stop the block|end the block)?[, ]*(?:but )?(?:no|skip(?: the)?|without a) break"
                        r"(?: please| for me)?|keep going without a break")
END_BREAK = re.compile(r"(?:i'm |im |i am )?back(?: now)?|end (?:the |my )?break|break(?:'s| is) over|(?:i'm |im )?done with (?:my |the )?break|"
                       r"(?:i'm |im |i am )?ready to (?:work|go|start)(?: again)?|let's get back to (?:it|work)|back to work|end break early")
STARTED_AGO = re.compile(r"(?:i )?(?:started|began|been working)(?: (?:on )?(?:it|this|that|working|on it|it already))?(?: about| like| around)? "
                         r"(?P<n>\d{1,3}|an?|half an?) ?(?P<u>minutes?|mins?|hours?|hrs?|hour) ago")
WHY = re.compile(r"why(?: this| this one| that| that one| is this (?:first|on top|next|the one)| this first| this task| should i do this)?")
AGAIN = re.compile(r"try (?:that )?again|again|retry|resend|send (?:it|that) again|one more time")
STOP_JOB = re.compile(r"stop|cancel|never mind|nevermind|stop thinking|cancel that|stop that")
LOW_OFF = re.compile(r"(?:turn |switch )?(?:off low energy|low energy off)(?: mode)?|turn low energy(?: mode)? off|i'm feeling better|im feeling better|"
                     r"i feel better|feeling better|normal energy|back to normal|i have energy(?: again)?")
DO_VERB = re.compile(r"(?:(?:please|pls|can you|could you|hey|ok|okay|so)\s+)*(?:keep|pin|put|move|push|bump|stick|leave|hold|drop|"
                     r"snooze|skip|mark|check off|cross off|tick off|start|begin|kick off|finish|finished|complete|completed)\b"
                     r"|.*\b(?:at|on|to) the top\b|.*\bon top\b")
READ_ONLY = {"schedule", "now", "project", "lookup", "reminders", "matcher:schedule", "matcher:now", "matcher:project",
             "matcher:reminders"}
DEAD_END = re.compile(r"I don't see a project called|More than one project matches|Nothing is in focus right now|"
                      r"I read that as a question about a project, but I can't tell which one")
LOW_ON = re.compile(r"(?:turn |switch )?(?:on low energy|low energy on)(?: mode)?|turn low energy(?: mode)? on")
_LOCK = threading.RLock()


def _or_list(xs):
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " or " + xs[-1]


def _clean(text):
    return " ".join(str(text or "").lower().replace("’", "'").split()).strip(" .!,")


def _hm(dt):
    return dt.strftime("%-I %p") if dt.minute == 0 else dt.strftime("%-I:%M %p")


def when_text(iso_s, now):
    """"today at 5 PM", "tomorrow at 9 AM", "Fri at 12 PM", "Nov 30 at 5 PM"."""
    try:
        d = datetime.fromisoformat(str(iso_s))
    except (TypeError, ValueError):
        return None
    if d.tzinfo is None:
        d = d.astimezone()
    d = d.astimezone(now.tzinfo)
    days = (d.date() - now.date()).days
    lead = ("today" if days == 0 else "tomorrow" if days == 1 else d.strftime("%a") if 1 < days < 7
            else d.strftime("%b %-d"))
    return f"{lead} at {_hm(d)}"


def mins_text(m):
    m = int(m or 0)
    return f"{m} min" if m < 60 else (f"{m // 60} h" if m % 60 == 0 else f"{m // 60} h {m % 60} min")


def day_of(now):
    return (now - timedelta(hours=DAY_START_HOUR)).date().isoformat()


def expand(text, pastes):
    """Put pasted text back where its chip sits. Unknown chip numbers stay as written."""
    def put(m):
        i = int(m.group(1)) - 1
        return pastes[i] if 0 <= i < len(pastes) else m.group(0)
    return PASTE_CHIP.sub(put, text)


class Chat:
    def __init__(self, srv, state_dir=None):
        self.srv = srv                                  # the dashboard server module (its helpers and paths)
        d = Path(state_dir or STATE_DIR)
        self.path, self.log_path = d / "chat.json", d / "chat-log.jsonl"
        self.last_pastes = []                           # memory only: "try again" after a paste can resend it
        self._ag = {}                                   # agent jobs: id -> {"cancel", "done"} (memory only)

    # ------------------------------------------------------------ store
    def _load(self, now):
        try:
            st = json.loads(self.path.read_text())
            if not isinstance(st, dict):
                raise ValueError
        except (OSError, ValueError):
            st = {}
        st.setdefault("version", 1)
        st.setdefault("rows", [])
        st.setdefault("pending", None)
        st.setdefault("seen", None)
        if st.get("day") != day_of(now):
            st["day"], st["rows"] = day_of(now), []     # a new morning: the old lines stay in chat-log.jsonl
        p = st.get("pending")
        if p and _age_min(p.get("at"), now) > PENDING_MINUTES:
            st["pending"] = None
        return st

    def _save(self, st):
        st["rows"] = st["rows"][-KEEP_ROWS:]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent)
        with os.fdopen(fd, "w") as f:
            json.dump(st, f, indent=1)
        os.replace(tmp, self.path)

    def _log(self, row, pastes=None):
        line = {"at": row["at"], "who": row["who"], "text": row.get("text", "")}
        if pastes:
            line["pastes"] = [len(p) for p in pastes]   # never the pasted words
        try:
            with open(self.log_path, "a") as f:
                f.write(json.dumps(line) + "\n")
        except OSError:
            pass

    def _row(self, st, who, text, now, log=True, **kw):
        row = {"id": "r-" + uuid.uuid4().hex[:10], "at": now.isoformat(timespec="seconds"), "who": who, "text": text,
               **{k: v for k, v in kw.items() if v is not None}}
        st["rows"].append(row)
        if log:
            self._log(row, kw.get("pastesLog"))
        row.pop("pastesLog", None)
        return row

    def _say(self, st, text, now, **kw):
        return self._row(st, "th", text, now, **kw)

    # ------------------------------------------------------------ view (called from get_state)
    def view(self, s, now=None):
        now = now or datetime.now().astimezone()
        with _LOCK:
            st = self._load(now)
            changed = self._sync_jobs(st, now) | self._sync_acts(st, s, now) | self._block_events(st, s, now)
            if changed or not self.path.exists():
                self._save(st)
        p = st.get("pending")
        return {"rows": st["rows"][-MAX_ROWS:], "pending": {"kind": p["kind"]} if p else None, "day": st["day"]}

    def _sync_jobs(self, st, now):
        changed = False
        for r in st["rows"]:
            if r.get("jobId") and not r.get("final"):
                if r["jobId"].startswith("ag-"):
                    live = self._ag.get(r["jobId"])
                    if (live is None or live["done"]) and _age_min(r["at"], now) > AGENT_STALE_MIN:
                        r.pop("stage", None)
                        r.update(final=True, text="I lost track of that one. Ask again?", tone="bad")
                        changed = True
                    continue
                j = self.srv.runner().get(r["jobId"])
                if j is None:
                    r.update(final=True, text=r.get("text") or "I lost track of that one. Ask again?", tone="bad")
                    changed = True
                    continue
                if j["status"] in ("queued", "running"):
                    stage = j.get("stage") or {}
                    if r.get("stage") != stage.get("label"):
                        r["stage"] = stage.get("label")
                        changed = True
                    continue
                self._finish_job_row(r, j)
                self._log(r)
                changed = True
        return changed

    @staticmethod
    def _finish_job_row(r, j):
        r.pop("stage", None)
        r["final"] = True
        if j["status"] == "done":
            r["text"] = j.get("answer") or "Done."
            if j.get("files"):
                r["files"] = j["files"]
            if j.get("undo") and not j["undo"].get("used"):
                r["undo"] = {"id": j["undo"]["id"], "expires": j["undo"]["expires"]}
            r["routing"] = j.get("routing")
            r["model"] = bool(j.get("routing")) and "no model" not in str(j.get("routing"))
            if j.get("savedTo"):
                r["savedTo"] = j.get("taskTitle")
        elif j["status"] == "cancelled":
            r.update(text="Stopped.", tone="dim")
        else:
            r.update(text=(j.get("error") or "That didn't work.") + " Say try again to resend it.", tone="bad")

    def _sync_acts(self, st, s, now):
        """Adds and Dones waiting on QuickToDo: settle each row when its result is in."""
        acts = (s or {}).get("actions") or {}
        pend = {a["id"]: a for a in acts.get("pending") or []}
        recent = {a["id"]: a for a in acts.get("recent") or []}
        changed = False
        for r in st["rows"]:
            a = r.get("act")
            if not a or a.get("settled"):
                continue
            if a["id"] in pend:
                if pend[a["id"]].get("waiting") and not a.get("waiting"):
                    a["waiting"] = True
                    r["text"] += " QuickToDo is opening in the background."
                    changed = True
                continue
            rec = recent.get(a["id"])
            if rec is None:
                if _age_min(r["at"], now) > 10:          # the request vanished: say so once, never claim it worked
                    a["settled"] = True
                    r.update(text=f"I couldn't confirm \"{a['title']}\" with QuickToDo. Check it there.", tone="bad")
                    changed = True
                continue
            a["settled"], a["outcome"], changed = True, rec.get("outcome"), True
            if a["kind"] == "add":
                if rec.get("outcome") == "added":
                    r["text"] = a["said"]
                    r["fly"] = {"list": a["list"], "title": a["title"]}
                    a["doneAt"] = rec.get("processedAt")
                    if a.get("checkin"):
                        a["checkinId"] = self._play_add(dict(action="addhabit", **a["checkin"]), now)
                elif rec.get("outcome") == "alreadyExists":
                    r.update(text=f"\"{a['title']}\" is already on your list, so I didn't add it again.", tone="dim")
                    self._drop_play(a.get("alsoIds"), "dropreminder")
                else:
                    r.update(text=f"QuickToDo didn't add \"{a['title']}\": {rec.get('text') or rec.get('detail') or 'no reason given'}.", tone="bad")
                    self._drop_play(a.get("alsoIds"), "dropreminder")
            elif a["kind"] == "done":
                if rec.get("outcome") == "done":
                    r["text"] = a["said"]
                    a["doneAt"] = rec.get("processedAt")
                else:
                    r.update(text=f"QuickToDo didn't mark \"{a['title']}\" done: {rec.get('text') or 'no reason given'}.", tone="bad")
            elif a["kind"] in ("unadd", "undone"):
                ok = rec.get("outcome") in ("removed", "reopened")
                r.update(text=a["said"] if ok else f"QuickToDo couldn't take that back: {rec.get('text') or 'no reason given'}.",
                         tone=None if ok else "bad")
            self._log(r)
        return changed

    def _block_events(self, st, s, now):
        b = (s or {}).get("blocks") or {}
        blk = b.get("block") or {}
        cur = {"phase": b.get("phase"), "blockId": blk.get("id"), "over": bool(b.get("over"))}
        seen, st["seen"] = st.get("seen"), cur
        if seen is None or not cur["phase"]:
            return seen != cur
        changed = seen != cur
        if cur["phase"] == "work" and cur["over"] and not (seen.get("blockId") == cur["blockId"] and seen.get("over")):
            if blk.get("overReason") == "task-done":
                self._say(st, f"\"{blk.get('title')}\" is done. Say break for a {mins_text(b.get('breakPreview') or 25)} break, "
                              f"or no break to keep going.", now)
            else:
                self._say(st, f"Time's up on \"{blk.get('title')}\". Say break, 15 more, or done.", now)
        if cur["phase"] == "checkin" and seen.get("phase") != "checkin":
            self._say(st, "Break's over. Did you do something just for you?", now)
            st["pending"] = {"kind": "checkin", "at": now.isoformat(timespec="seconds")}
        if cur["phase"] != "checkin" and (st.get("pending") or {}).get("kind") == "checkin":
            st["pending"] = None                         # answered somewhere else
        return changed

    # ------------------------------------------------------------ send
    def send(self, text, pastes=None, sector=None, now=None):
        now = now or datetime.now().astimezone()
        text = str(text or "").strip()
        pastes = [str(p) for p in (pastes or [])][:MAX_PASTES]
        if not text and not pastes:
            raise ValueError("type something first")
        if len(text) > 4000 or sum(len(p) for p in pastes) > MAX_PASTE_CHARS:
            raise ValueError("That's too long for one message.")
        if pastes and not PASTE_CHIP.search(text):
            text = (text + " " if text else "") + " ".join(f"[Pasted text #{i + 1} · {p.count(chr(10)) + 1} lines]" for i, p in enumerate(pastes))
        with _LOCK:
            st = self._load(now)
            self._row(st, "me", text, now, pastesLog=pastes or None)
            self._save(st)
        try:
            self._answer(text, pastes, sector, now)
        except Exception as e:  # noqa: BLE001 - one message must never take the chat down
            with _LOCK:
                st = self._load(now)
                self._say(st, f"Something broke on my side: {e}. Try saying it another way.", now, tone="bad")
                self._save(st)

    def _answer(self, text, pastes, sector, now):
        config = self.srv.brain.load_config()
        s = self.srv.get_state(config, chat=False)
        n = _clean(self.srv.plain.normalize(text)) if not pastes else ""
        if pastes:
            self.last_pastes = pastes
            return self._route(expand(text, pastes), now, pasted=True, shown=text, typed=text)
        with _LOCK:
            st = self._load(now)
            pend = st.get("pending")
        if pend:
            if self._answer_pending(pend, text, n, s, config, now):
                return
        if self._model_asked(now) and len(n.split()) <= 8 and not self.srv.undo.is_undo(n) and not STOP_JOB.fullmatch(n):
            return self._agent_start(text, now, learn=False)   # her answer to the question the model just asked
        if self.srv.undo.is_undo(n):
            return self._undo(s, config, now)
        if self._act(text, n, s, config, now):
            return
        return self._route(text, now, sector=sector)

    def _reply(self, text, now, **kw):
        with _LOCK:
            st = self._load(now)
            row = self._say(st, text, now, **kw)
            self._save(st)
        return row

    def _set_pending(self, pend):
        with _LOCK:
            now = datetime.now().astimezone()
            st = self._load(now)
            st["pending"] = pend
            self._save(st)

    # ------------------------------------------------------------ pending questions
    def _answer_pending(self, pend, text, n, s, config, now):
        if pend["kind"] == "checkin":
            ans = "later" if CHECK_LATER.fullmatch(n) else "no" if CHECK_NO.fullmatch(n) else "yes" if CHECK_YES.fullmatch(n) else None
            if not ans:
                return False
            self._set_pending(None)
            try:
                v = self._block("checkin", {"answer": ans}, config)
            except ValueError:
                self._reply("That check-in already closed.", now, tone="dim")
                return True
            lead = {"yes": "Good. That counts.", "no": "OK. Next break, pick one thing just for you.", "later": "OK."}[ans]
            nxt = (v or {}).get("next")
            tail = (f" Next up: \"{nxt['title']}\" ({mins_text(nxt.get('minutes'))}). Say start when you're ready."
                    if nxt else " Nothing's lined up right now. Enjoy it.")
            self._reply(lead + tail, now)
            return True
        if pend["kind"] == "done":
            tasks = self.srv.snapshot_tasks(config) or []
            by = {t["id"]: t for t in tasks}
            opts = [by[i] for i in pend.get("ids") or [] if i in by]
            if NO.fullmatch(n):
                self._set_pending(None)
                self._reply("OK, I left it alone.", now, tone="dim")
                return True
            hit = opts[0] if len(opts) == 1 and YES.fullmatch(n) else self.srv.intent.pick_option(n, opts)
            same = {o.get("list") for o in opts}
            if not hit and len(opts) > 1 and len(same) == 1 and self.srv.intent.pick_option(n, opts[:1]):
                self._reply(f"They're all in {same.pop()}. Which one? Say its name or the first one, second one…", now)
                return True                               # the question stays open
            if not hit:
                self._set_pending(None)                   # a new message; the question is dropped quietly
                return False
            self._set_pending(None)
            b = s.get("blocks") or {}
            return self._done(hit, s, b.get("phase") or "idle", b.get("block") or {}, tasks, config, now)
        if pend["kind"] == "pick":
            tasks = self.srv.snapshot_tasks(config) or []
            by = {t["id"]: t for t in tasks}
            opts = [by[i] for i in pend.get("ids") or [] if i in by]
            if NO.fullmatch(n):
                self._set_pending(None)
                self._reply("OK, I left it alone.", now, tone="dim")
                return True
            hit = self.srv.intent.pick_option(n, opts)
            self._set_pending(None)
            if not hit:
                return False
            ag = self.srv.agent_mod
            try:
                a = ag.check({**pend["action"], "task": "x"}, {"x": hit}, {"lists": self.srv.snapshot_lists(config)}, text, now, chosen=True)
            except ag.Problem as p:
                self._reply(p.text if p.kind != "model" else "That one can't be done right now.", now, tone="dim")
                return True
            self._agent_dispatch(a, None, s, config, now)
            return True
        if pend["kind"] != "add":
            self._set_pending(None)
            return False
        p = dict(pend["p"])
        if NO.fullmatch(n):
            self._set_pending(None)
            self._reply(f"OK, I didn't add \"{p['title']}\".", now, tone="dim")
            return True
        if YES.fullmatch(n):
            if not p.get("list") and p.get("mode") != "reminder":
                self._reply(self._which_list(p), now)
                return True
            self._set_pending(None)
            self._commit(p, now)
            return True
        fixed = self._apply_fix(p, text, n, now)
        if fixed is None:
            self._set_pending(None)                       # anything else is a new message; the question is dropped quietly
            return False
        p = fixed
        if p.get("mode") == "reminder" and not p.get("due"):
            self._set_pending({"kind": "add", "p": p, "at": now.isoformat(timespec="seconds")})
            self._reply(f"When should I text you about \"{p['title']}\"?", now)
            return True
        if not p.get("list") and p.get("mode") != "reminder":
            self._set_pending({"kind": "add", "p": p, "at": now.isoformat(timespec="seconds")})
            self._reply(self._which_list(p), now)
            return True
        self._set_pending(None)
        self._commit(p, now)
        return True

    def _apply_fix(self, p, text, n, now):
        """A correction to a pending add ("make it saturday", "in personal", "no date", "call it X"); None when it is not one."""
        capture = self.srv.capture
        lists = p.get("lists") or []
        t = re.sub(r"^(?:no|actually|wait|hmm|oh|and|also|but)[, ]+", "", n)
        t = re.sub(r"^(?:make it|change it to|move it to|set it (?:to|for)|put it (?:on|for)|do it|due|for|on|at|by)\s+", "", t)
        m = TITLE_FIX.fullmatch(t)
        if m:
            title = " ".join(text.split()[-len(m.group(1).split()):]).strip(" .!")   # keep her capitals
            return {**p, "title": title[:1].upper() + title[1:200]}
        if NO_DATE.fullmatch(t):
            return {**p, "due": None, "extraDue": None, "checkin": None}
        lm = re.fullmatch(r"(?:put it |move it |add it |it goes |it's |its )?(?:in|into|to|under|on)?\s*(?:my |the )?(?P<l>.+?)(?: list)?", t)
        if lm:
            want = lm.group("l")
            hit = next((l for l in lists if l.lower() == want), None)
            if not hit:
                g, h = capture.guess_list(want, lists)
                hit = g if (h or len(want.split()) <= 2) else None
            if hit:
                return {**p, "list": hit}
        due, rest = capture.parse_due(t, now)
        if due and len(rest.split()) <= 2:
            if p.get("mode") == "reminder" and not re.search(r"\d|noon|midnight|morning|evening|night|tonight", t):
                due = due[:11] + "09:00" + due[16:]
            return {**p, "due": due, "extraDue": None}
        return None

    @staticmethod
    def _which_list(p):
        lists = p.get("lists") or []
        names = ", ".join(lists[:-1]) + " or " + lists[-1] if len(lists) > 1 else (lists[0] if lists else "a list")
        return f"Which list should \"{p['title']}\" go in: {names}?"

    # ------------------------------------------------------------ adds
    def _propose(self, p, now):
        capture = self.srv.capture
        lists = p.get("lists") or []
        _, hit = capture.guess_list(p.get("text") or "", lists)
        plain_task = p.get("mode") == "task" and not (p.get("habit") or p.get("plan") or p.get("checkin") or p.get("alsoText") or p.get("hint"))
        sure_list = bool(p.get("list")) and p.get("why") in ("list from your words", "the sector you're in")
        confident = ((plain_task and sure_list and (p.get("due") or hit))
                     or (p.get("mode") == "reminder" and p.get("due") and not p.get("habit")))
        if confident:
            return self._commit(p, now)
        self._set_pending({"kind": "add", "p": p, "at": now.isoformat(timespec="seconds")})
        title, lst = p["title"], p.get("list")
        due = when_text(p["due"], now) if p.get("due") else None
        if p.get("mode") == "reminder" and not p.get("due"):
            return self._reply(f"When should I text you about \"{title}\"?", now)
        if not lst and not p.get("habit"):
            return self._reply(self._which_list(p) + (f" It's due {due}." if due else ""), now)
        if p.get("plan"):
            return self._reply(f"I'll start the study plan \"{title}\" in {lst or 'Play'}, {p['habit']['label']}, "
                               f"and nudge you around {_hm(datetime.strptime(p['habit']['nudgeAt'], '%H:%M'))}. Sound right?", now)
        if p.get("habit"):
            hb = p["habit"]
            return self._reply(f"I'll repeat \"{title}\" {hb['label']}" + (f" for {mins_text(hb['minutes'])}" if hb.get("minutes") else "")
                               + f" in {lst or 'Play'}, and nudge you around {_hm(datetime.strptime(hb['nudgeAt'], '%H:%M'))}. Sound right?", now)
        where = f"in {lst}" + (f", due {due}" if due else " with no date")
        if p.get("checkin") and due:
            return self._reply(f"I'll put \"{title}\" {where}, and check in with you {p['checkin']['label']} until then. Sound right?", now)
        if p.get("alsoText") and due:
            return self._reply(f"I'll put \"{title}\" {where}, and text you about it then. Sound right?", now)
        if p.get("hint"):
            return self._reply(f"I'll put \"{title}\" {where}. {p['hint']} Sound right?", now)
        return self._reply(f"I'll put \"{title}\" {where}. Sound right?", now)

    def _play_add(self, body, now):
        """play.apply one add; returns the new record's id (None when it failed)."""
        srv = self.srv
        try:
            before = srv.play.load(srv.PLAY_PATH["p"])
            act = body.pop("action")
            st = srv.play.apply(before, act, now, **body)
            srv.play.save(st, srv.PLAY_PATH["p"])
        except (ValueError, OSError):
            return None
        ids = lambda x: {r["id"] for k in ("reminders", "habits") for r in x.get(k, [])}
        new = sorted(ids(st) - ids(before))
        return re.sub(r"-f\d+$", "", new[-1]) if new else None

    def _drop_play(self, ids, action):
        srv = self.srv
        for i in ids or []:
            try:
                st = srv.play.apply(srv.play.load(srv.PLAY_PATH["p"]), action, datetime.now().astimezone(), id=i)
                srv.play.save(st, srv.PLAY_PATH["p"])
            except (ValueError, OSError):
                pass

    def _record_play_undo(self, before, label, now):
        srv = self.srv
        after = srv.play.load(srv.PLAY_PATH["p"])
        return srv.runner().undos.record(srv.undo.diff_play(before, after), label, None, now)

    def _commit(self, p, now):
        srv = self.srv
        title, lst = p["title"], p.get("list")
        due = p.get("due")
        if p.get("mode") == "reminder" and not p.get("habit"):
            ats = [due] + list(p.get("extraDue") or [])
            before = srv.play.load(srv.PLAY_PATH["p"])
            made = [self._play_add({"action": "addreminder", "text": title, "at": at}, now) for at in ats]
            if not any(made):
                return self._reply(f"I couldn't set that text up. Try a different time.", now, tone="bad")
            u = self._record_play_undo(before, f"Text about \"{title}\"", now)
            whens = " and ".join(w for w in (when_text(a, now) for a in ats) if w)
            return self._reply(f"I'll text you {whens} about \"{title}\". It's not on your list. Say undo to take it back.", now, undo=u)
        if p.get("habit"):
            hb = p["habit"]
            cluster = p.get("cluster") or srv.capture.CLUSTER_OF_LIST.get((lst or "play").lower(), "play")
            before = srv.play.load(srv.PLAY_PATH["p"])
            hid = self._play_add({"action": "addhabit", "title": title, "notes": p.get("notes") or "", "days": hb["days"],
                                  "nudgeAt": hb["nudgeAt"], "minutes": hb.get("minutes"), "plan": p.get("plan"), "cluster": cluster}, now)
            if not hid:
                return self._reply(f"I couldn't set up \"{title}\". It may already repeat.", now, tone="bad")
            u = self._record_play_undo(before, f"Repeating \"{title}\"", now)
            nudge = _hm(datetime.strptime(hb["nudgeAt"], "%H:%M"))
            return self._reply(f"Added \"{title}\", repeating {hb['label']} in {lst or 'Play'}. I'll nudge you around {nudge}. "
                               f"Say undo to take it back.", now, undo=u, fly={"list": lst or "Play", "title": title})
        also = []
        if p.get("alsoText") and due:
            for at in (p.get("textAt") or [due]):
                rid = self._play_add({"action": "addreminder", "text": title, "at": at}, now)
                if rid:
                    also.append(rid)
        try:
            req = srv.done_actions.request_add(title, lst, due, srv.snapshot_lists(srv.brain.load_config()), srv.done_paths(srv.brain.load_config()))
        except srv.done_actions.Busy:
            self._drop_play(also, "dropreminder")
            return self._reply(f"I'm already adding \"{title}\".", now, tone="dim")
        except ValueError as e:
            self._drop_play(also, "dropreminder")
            return self._reply(f"I couldn't add \"{title}\": {e}.", now, tone="bad")
        when = when_text(due, now)
        said = f"Added \"{title}\" to {req['list']}" + (f", due {when}" if when else "") + "."
        ci = p.get("checkin")
        if ci and due:
            said += f" I'll check in with you {ci['label']} until then."
        elif also:
            said += " I'll text you then too."
        said += " Say undo to take it back."
        act = {"kind": "add", "id": req["id"], "title": title, "list": req["list"], "said": said, "alsoIds": also}
        if ci and due:
            act["checkin"] = {"title": title, "until": ci.get("until") or due[:10], "nudgeAt": ci["nudgeAt"], "days": ci["days"],
                              "forTask": {"title": title, "list": req["list"]}}
        return self._reply(f"Adding \"{title}\" to {req['list']}…", now, act=act)

    # ------------------------------------------------------------ undo
    def _undo(self, s, config, now):
        srv = self.srv
        acts = {a["id"]: a for a in ((s.get("actions") or {}).get("recent") or [])}
        with _LOCK:
            st = self._load(now)
        mine = None
        for r in reversed(st["rows"]):
            a = r.get("act")
            if a and a["kind"] in ("add", "done") and not a.get("undone"):
                if not a.get("settled"):
                    return self._reply("QuickToDo hasn't confirmed that yet. Say undo again in a few seconds.", now, tone="dim")
                rec = acts.get(a["id"])
                if rec and rec.get("undoable"):
                    mine = (r, a, rec)
                break
        live = srv.runner().undos.newest_live(now)
        if mine and (live is None or (mine[2].get("processedAt") or "") >= live["createdAt"]):
            r, a, rec = mine
            if a.get("learn"):
                srv.agent().learned.forget(a["learn"])
            try:
                if a["kind"] == "add":
                    req = srv.done_actions.request_unadd(a["id"], srv.done_paths(config))
                    self._drop_play(a.get("alsoIds"), "dropreminder")
                    if a.get("checkinId"):
                        self._drop_play([a["checkinId"]], "drophabit")
                    said, kind = f"Took back \"{a['title']}\". It's off your list.", "unadd"
                else:
                    req = srv.done_actions.request_undo(a["id"], srv.done_paths(config))
                    said, kind = f"Reopened \"{a['title']}\".", "undone"
            except (ValueError, srv.done_actions.Busy) as e:
                return self._reply(f"I couldn't take that back: {e}.", now, tone="bad")
            with _LOCK:
                st = self._load(now)
                for x in st["rows"]:
                    if (x.get("act") or {}).get("id") == a["id"]:
                        x["act"]["undone"] = True
                self._save(st)
            return self._reply("Taking it back…", now, act={"kind": kind, "id": req["id"], "title": a["title"], "said": said})
        if live:
            src = next((x for x in st["rows"] if (x.get("undo") or {}).get("id") == live["id"] and x.get("learn")), None)
            if src:
                srv.agent().learned.forget(src["learn"])
        job = srv.runner().undo(None, "undo", config)
        return self._reply(job.get("answer") or "Nothing to undo.", now, tone=None if "Undone" in (job.get("answer") or "") else "dim")

    # ------------------------------------------------------------ typed actions
    def _block(self, action, args, config):
        result = self.srv.brain.run(config)
        return self.srv.block_step(result, config, action, args)

    def _act(self, text, n, s, config, now):
        srv = self.srv
        b = s.get("blocks") or {}
        phase, blk = b.get("phase") or "idle", b.get("block") or {}
        tasks = srv.snapshot_tasks(config) or []
        busy = (s.get("command") or {}).get("busy")
        if STOP_JOB.fullmatch(n) and self.agent_running():
            if self.cancel_agent(None):
                self._reply("OK, I stopped that.", now, tone="dim")
            else:
                self._reply("Too late to stop that one; it's already happening. Say undo after it lands.", now, tone="dim")
            return True
        if busy and STOP_JOB.fullmatch(n):
            job = next((j for j in (s.get("command") or {}).get("jobs", []) if j["status"] in ("queued", "running")), None)
            if job:
                srv.runner().cancel(job["id"])
                self._reply("OK, I stopped that.", now, tone="dim")      # under her "stop"; the thinking line reads Stopped.
                return True
        if AGAIN.fullmatch(n):
            return self._again(now)
        if WHY.fullmatch(n.rstrip("?")):
            c = s.get("current")
            self._reply(f"\"{c['title']}\" is first because {c['why'][:1].lower() + c['why'][1:]}" if c and c.get("why")
                        else "Nothing is on top right now, so there's no reason to give.", now)
            return True
        if LOW_OFF.fullmatch(n) or LOW_ON.fullmatch(n):
            on = bool(LOW_ON.fullmatch(n))
            srv.do_action({"action": "lowenergy", "state": "on" if on else "off"})
            self._reply("Low energy is on: shorter blocks, gentler breaks." if on else "Low energy is off. Normal blocks again.", now)
            return True
        if phase == "starting" and BEGIN_NOW.fullmatch(n):
            self._block("begin_now", {}, config)
            self._reply(f"Timer's running on \"{blk.get('title')}\".", now)
            return True
        if phase == "break" and END_BREAK.fullmatch(n):
            self._block("end_break", {}, config)
            return True                                   # the check-in question arrives with the next view
        if phase in ("work", "break") and SKIP_BREAK.fullmatch(n):
            if phase == "break":
                self._block("end_break", {}, config)
                return True
            self._block("skip_break", {}, config)
            self._reply(f"Stopped \"{blk.get('title')}\". No break. Say start when you want the next one.", now)
            return True
        if phase in ("starting", "work") and CANCEL_BLOCK.fullmatch(n):
            self._block("cancel", {}, config)
            self._reply(f"Cancelled the block on \"{blk.get('title')}\". Nothing was logged as done.", now)
            return True
        m = EXTEND.fullmatch(n)
        if m and phase == "work":
            k = next((g for g in (m.group("n"), m.group("m"), m.group("k"), m.group("p")) if g), None)
            mins = NUMS.get(k, None) if k and not k.isdigit() else int(k) if k else 15
            if not 5 <= mins <= 60:
                self._reply("I can add 5 to 60 minutes at a time.", now, tone="dim")
                return True
            v = self._block("extend", {"minutes": mins}, config)
            end = when_text((v.get("block") or {}).get("endsAt"), now)
            self._reply(f"Added {mins} minutes to \"{blk.get('title')}\"." + (f" New end: {end.split(' at ')[1]}." if end else ""), now)
            return True
        m = STARTED_AGO.fullmatch(n)
        if m:
            if phase != "idle":
                self._reply("A block is already going." if phase in ("work", "starting") else "Finish the break first.", now, tone="dim")
                return True
            q, u = m.group("n"), m.group("u")
            qty = 30 if q.startswith("half") else 1 if q in ("a", "an") else int(q)
            ago = qty * 60 if u.startswith("h") and not q.startswith("half") else qty
            return self._start(None, config, now, started_ago=ago)
        dn = srv.intent.done_named(n, tasks)
        if dn:
            return self._done_unclear(dn, now)
        ar = srv.intent.action_request(n, tasks)
        if not ar:
            if phase == "break" and n in ("done", "i'm done", "im done", "finished"):
                self._block("end_break", {}, config)
                return True
            return False
        kind, hit = ar
        if kind in ("snooze", "skip", "pin", "unpin"):
            return False                                  # command/acts.py does these, with its own undo
        if kind == "done":
            if phase == "break" and not hit:
                self._block("end_break", {}, config)
                return True
            return self._done(hit, s, phase, blk, tasks, config, now)
        if kind == "start":
            if phase == "break" and not hit:
                self._block("end_break", {}, config)
                return True
            if phase == "checkin":
                self._reply("First: did you do something just for you on that break? Yes, no, or not now.", now)
                return True
            if phase in ("work", "starting"):
                self._reply(f"\"{blk.get('title')}\" is already running. Say done, break, or cancel.", now, tone="dim")
                return True
            return self._start(hit, config, now)
        if kind == "break":
            if phase == "work":
                v = self._block("take_break", {}, config)
                nb = v.get("block") or {}
                sug = (nb.get("suggestion") or {}).get("title")
                self._reply(f"Stopped \"{blk.get('title')}\". Break: {mins_text(nb.get('minutes'))}."
                            + (f" Maybe: {sug}." if sug else "") + " I'll ping you when it's over.", now)
            elif phase == "break":
                self._reply("You're already on a break. Say I'm back when you're done.", now, tone="dim")
            elif phase == "starting":
                self._block("cancel", {}, config)
                self._reply("OK, I cancelled the countdown. Step away whenever.", now)
            else:
                self._reply("Nothing's running. Step away whenever; I'll be here.", now)
            return True
        if kind == "low":
            srv.do_action({"action": "lowenergy", "state": "on"})
            self._reply("Sounds like a low-energy day. I turned on Low energy: shorter blocks, gentler breaks. Say feeling better to turn it off.", now)
            return True
        return False

    def _done_unclear(self, dn, now):
        """'mark X done' where X is not exactly one open task: say so and offer the options; her next message picks one."""
        phrase, kind, opts = dn
        name = lambda o: f"\"{o['title']}\"" + (f" ({o['list']})" if o.get("list") else "")
        if kind == "many":
            lead = f"A few open tasks match \"{phrase}\": " if len(opts) > 2 else f"Two open tasks match \"{phrase}\": "
            self._set_pending({"kind": "done", "ids": [o["id"] for o in opts], "at": now.isoformat(timespec="seconds")})
            return self._reply(lead + _or_list([name(o) for o in opts]) + ". Which one?", now)
        lead = f"I don't see \"{phrase}\" open on your list, so it may already be done."
        if not opts:
            return self._reply(lead + " Nothing open has a name close to that.", now, tone="dim")
        self._set_pending({"kind": "done", "ids": [o["id"] for o in opts], "at": now.isoformat(timespec="seconds")})
        if len(opts) == 1:
            return self._reply(f"{lead} Did you mean {name(opts[0])}? Say yes and I'll mark it done.", now)
        return self._reply(f"{lead} Did you mean {_or_list([name(o) for o in opts])}? Say which one and I'll mark it done.", now)

    def _start(self, hit, config, now, started_ago=None):
        args = {"countdown": 0}
        if hit:
            args["taskId"] = hit["id"]
        if started_ago:
            args["startedAgo"] = started_ago
        try:
            v = self._block("start_work", args, config)
        except ValueError as e:
            msg = str(e)
            self._reply("There's nothing to start right now." if "nothing to start" in msg
                        else "Play items are for breaks, not work blocks." if "Play" in msg
                        else f"I couldn't start that: {msg}.", now, tone="dim")
            return True
        nb = v.get("block") or {}
        lead = f"Started \"{nb.get('title')}\" {started_ago} minutes ago" if started_ago else f"Started \"{nb.get('title')}\""
        self._reply(f"{lead}: {mins_text(nb.get('minutes'))} on the clock. Say break when you want to stop, or done when it's finished.", now)
        return True

    def _done(self, hit, s, phase, blk, tasks, config, now):
        srv = self.srv
        in_block = phase in ("work", "starting")
        cur = s.get("current") or {}
        task = (hit or ({"id": blk.get("taskId"), "title": blk.get("title")} if in_block else None)
                or ({"id": cur["taskId"], "title": cur.get("title")} if cur.get("taskId") else None))
        if not task or not task.get("id"):
            self._reply("Done with what? Say it with the name, like done with lab 7.", now)
            return True
        try:
            req = srv.done_actions.request_done(task["id"], tasks, srv.done_paths(config))
        except srv.done_actions.Busy:
            self._reply(f"I'm already marking \"{task['title']}\" done.", now, tone="dim")
            return True
        except ValueError as e:
            self._reply(f"I couldn't mark \"{task.get('title')}\" done: {e}.", now, tone="bad")
            return True
        lst = next((t.get("list") for t in tasks if t.get("id") == task["id"]), None)
        said = f"Marked \"{req['title']}\"" + (f" ({lst})" if lst else "") + " done."
        if in_block and task["id"] == blk.get("taskId") and phase == "work":
            try:
                v = self._block("take_break", {}, config)
                nb = v.get("block") or {}
                sug = (nb.get("suggestion") or {}).get("title")
                said += f" Break: {mins_text(nb.get('minutes'))}." + (f" Maybe: {sug}." if sug else "")
            except ValueError:
                pass
        elif in_block and task["id"] == blk.get("taskId"):
            try:
                self._block("cancel", {}, config)
            except ValueError:
                pass
        said += " Say undo to take it back."
        self._reply(f"Marking \"{req['title']}\" done…", now, act={"kind": "done", "id": req["id"], "title": req["title"], "said": said})
        return True

    def _again(self, now):
        with _LOCK:
            st = self._load(now)
        mine = [r for r in st["rows"] if r["who"] == "me"]
        prev = next((r for r in reversed(mine[:-1]) if not AGAIN.fullmatch(_clean(r["text"]))), None)
        if not prev:
            self._reply("There's nothing to resend yet.", now, tone="dim")
            return True
        if PASTE_CHIP.search(prev["text"]):
            if not self.last_pastes:
                self._reply("I don't keep pasted text, so paste it again.", now, tone="dim")
                return True
            self._route(expand(prev["text"], self.last_pastes), now, pasted=True, shown=prev["text"], typed=prev["text"])
            return True
        self._route(prev["text"], now)
        return True

    # ------------------------------------------------------------ everything else
    def _follow_up(self, now):
        with _LOCK:
            st = self._load(now)
        rows = [r for r in st["rows"] if r["who"] == "th"]
        last = rows[-1] if rows else None
        return bool(last and last.get("model") and _age_min(last["at"], now) <= FOLLOW_MINUTES)

    def _route(self, text, now, pasted=False, sector=None, shown=None, typed=None):
        srv = self.srv
        go = self._to_agent(text, now, pasted, sector, typed=typed)
        if go:
            return self._agent_start(go["text"], now, pasted=pasted, haiku_only=go["haiku"])
        body = {"text": text, "followUp": self._follow_up(now)}
        if pasted:
            body.update(pasted=True, skipCapture=True, shown=shown)
        if sector:
            body["sector"] = sector
        try:
            res = srv.submit_command(body)
        except srv.command.Busy:
            return self._reply("I'm still working on the last one. Give me a moment, or say stop.", now, tone="dim")
        except ValueError as e:
            return self._reply(f"I can't send that: {e}.", now, tone="bad")
        if "capture" in res:
            return self._propose(res["capture"], now)
        j = res
        if not pasted and j["status"] == "done" and DEAD_END.match(j.get("answer") or ""):
            return self._agent_start(text, now)           # a rule came up empty ("bandit stuff"): the agent reads it instead
        if j["status"] in ("queued", "running"):
            return self._reply("", now, jobId=j["id"], log=False)
        row = {"jobId": j["id"]}
        with _LOCK:
            st = self._load(now)
            r = self._say(st, "", now, log=False, **row)
            self._finish_job_row(r, j)
            self._log(r)
            self._save(st)
        return r

    # ------------------------------------------------------------ the agent (STATE_MODEL_AGENT.md)
    def _to_agent(self, text, now, pasted, sector, typed=None):
        """{"text", "haiku"} when this message goes to the agent; None when it stays on today's path (the instant
        rules, the Stuck step, prep:, or a model tag she typed)."""
        srv = self.srv
        from router import rules
        tag = rules.parse_override(typed if pasted else text)        # a tag inside pasted text is content, not a choice
        if tag:
            if tag.tier in ("free", "haiku") and tag.text:
                body = expand(tag.text, self.last_pastes) if pasted else tag.text   # the tag goes, the paste stays
                return {"text": body, "haiku": tag.tier == "haiku"}
            return None                                   # @sonnet / @opus: her explicit pick, the router as before
        if pasted:
            return {"text": text, "haiku": False}
        config = srv.brain.load_config()
        tasks = srv.snapshot_tasks(config) or []
        import route_preview
        label = route_preview.decide(text, srv.snapshot_lists(config), tasks, now,
                                     prep_parse=srv.command.prep_agent.parse_command, sector=sector, config=config,
                                     matcher=srv.runner().matcher)
        if label in ("free", "jev"):
            return {"text": text, "haiku": False}
        if label in READ_ONLY and DO_VERB.match(srv.plain.normalize(text).lower()):
            return {"text": text, "haiku": False}      # "keep lab 7 at the top today": a request to do something, not a question
        return None

    def _model_asked(self, now):
        """True when the newest Thalamus line is a model's question from the last few minutes."""
        with _LOCK:
            st = self._load(now)
        last = next((r for r in reversed(st["rows"]) if r["who"] == "th"), None)
        return bool(last and last.get("via") in ("free model", "Haiku") and (last.get("text") or "").rstrip().endswith("?")
                    and _age_min(last["at"], now) <= FOLLOW_MINUTES)

    def agent_running(self):
        return any(not v["done"] and not v["cancel"] for v in self._ag.values())

    def cancel_agent(self, jid):
        """Stop a thinking agent row (jid None = whichever is running). True when one was stopped; False when there was
        none, or it had already started acting (then the action finishes and says so)."""
        with _LOCK:
            hit = [k for k, v in self._ag.items() if (jid is None or k == jid) and not v["done"] and not v["cancel"] and not v["acting"]]
            for k in hit:
                self._ag[k]["cancel"] = True
                self._patch(lambda r, k=k: r.get("jobId") == k, final=True, text="Stopped.", tone="dim", stage=None)
        return bool(hit)

    def _patch(self, match, log=False, **kw):
        with _LOCK:
            now = datetime.now().astimezone()
            st = self._load(now)
            row = next((r for r in reversed(st["rows"]) if match(r)), None)
            if row is None:
                return None
            for k, v in kw.items():
                if v is None:
                    row.pop(k, None)
                else:
                    row[k] = v
            if log:
                self._log(row)
            self._save(st)
            return row

    def _agent_start(self, text, now, pasted=False, haiku_only=False, learn=True):
        with _LOCK:
            if self.agent_running():
                return self._reply("I'm still working on the last one. Give me a moment, or say stop.", now, tone="dim")
            jid = "ag-" + uuid.uuid4().hex[:10]
            self._ag[jid] = {"cancel": False, "done": False, "acting": False, "learn": learn and not pasted}
            st = self._load(now)
            row = self._say(st, "", now, log=False, jobId=jid, stage="thinking")
            self._save(st)
        args = (jid, text, now, pasted, haiku_only)
        if getattr(self.srv.runner(), "sync", False):
            self._agent_run(*args)
        else:
            threading.Thread(target=self._agent_run, args=args, daemon=True).start()
        return row

    def _agent_ctx(self, s, config, jid):
        srv = self.srv
        tasks = srv.snapshot_tasks(config) or []
        b = s.get("blocks") or {}
        blk = b.get("block") or {}
        with _LOCK:
            st = self._load(datetime.now().astimezone())
        rows = [r for r in st["rows"] if r.get("jobId") != jid and (r.get("text") or "").strip()]
        if rows and rows[-1]["who"] == "me":
            rows = rows[:-1]                              # her new message is shown on its own
        pend = st.get("pending")
        last_q = next((r["text"] for r in reversed(rows) if r["who"] == "th"), None) if pend else None
        classes = []
        for c in s.get("classes") or []:
            try:
                st_ = datetime.fromisoformat(c["start"])
                classes.append(f"{c['title']}{' (test)' if c.get('test') else ''} at {st_.strftime('%-I:%M %p')}")
            except (KeyError, ValueError):
                pass
        return {"tasks": tasks, "lists": srv.snapshot_lists(config) or [], "current": s.get("current") or {},
                "block": {"phase": b.get("phase"), "title": blk.get("title"), "taskId": blk.get("taskId")},
                "classes": classes, "rows": rows, "pending": last_q}

    def _agent_run(self, jid, text, now, pasted, haiku_only):
        srv = self.srv
        try:
            config = srv.brain.load_config()
            s = srv.get_state(config, chat=False)
            ctx = self._agent_ctx(s, config, jid)
            stage = lambda label: self._patch(lambda r: r.get("jobId") == jid and not r.get("final"), stage=label)
            res = srv.agent().respond(text, ctx, datetime.now().astimezone(), haiku_only=haiku_only, pasted=pasted,
                                      cancelled=lambda: self._ag[jid]["cancel"], stage=stage)
            with _LOCK:                                   # Stop and the move to acting can't cross
                if self._ag[jid]["cancel"] or res["step"] == "cancelled":
                    return                                # the row already reads Stopped.
                self._ag[jid]["acting"] = True
            self._agent_finish(jid, text, res, s, config, pasted)
        except Exception as e:  # noqa: BLE001 - one message must never take the chat down
            msg = f"Something broke on my side: {e}. Try saying it another way."
            if not self._patch(lambda r: r.get("jobId") == jid, log=True, final=True, stage=None, tone="bad", text=msg):
                self._reply(msg, datetime.now().astimezone(), tone="bad")
        finally:
            self._ag[jid]["done"] = True

    def _agent_finish(self, jid, text, res, s, config, pasted):
        now = datetime.now().astimezone()
        via = {"free": "free model", "haiku": "Haiku", "learned": "learned"}.get(res["step"], "")
        p, a = res.get("problem"), res.get("action")
        if p is None and not a:                           # an answer, a question back, or "I couldn't do that one"
            self._patch(lambda r: r.get("jobId") == jid, log=True, final=True, stage=None, text=res["reply"],
                        model=res["step"] in ("free", "haiku"), via=via or None, tone="bad" if res["step"] == "none" else None)
            return
        try:
            if p is not None:
                if p.kind == "ask":
                    raw = {k: v for k, v in (res.get("raw") or {}).items() if k != "task"}
                    kind = "done" if raw.get("tool") == "done" else "pick"
                    self._set_pending({"kind": kind, "ids": [o["id"] for o in p.options], "action": raw,
                                       "at": now.isoformat(timespec="seconds")})
                    return self._reply(p.text, now)
                return self._reply(p.text, now, tone="dim")
            ok_learn = self._ag.get(jid, {}).get("learn") and res["step"] in ("free", "haiku", "learned")
            learn = text if ok_learn and self.srv.agent_mod.self_contained(text, a) else None
            return self._agent_dispatch(a, learn, s, config, now)
        finally:
            with _LOCK:                                   # the action's own reply (already written) takes its place
                st = self._load(now)
                st["rows"] = [r for r in st["rows"] if r.get("jobId") != jid]
                self._save(st)

    def _agent_dispatch(self, a, learn_text, s, config, now):
        """Run one checked action through the code the typed rules use. learn_text: save the sentence once it worked."""
        srv = self.srv
        tool = a["tool"]
        b = s.get("blocks") or {}
        phase, blk = b.get("phase") or "idle", b.get("block") or {}
        tasks = srv.snapshot_tasks(config) or []
        task = a.get("task")
        name = (f"\"{task['title']}\"" + (f" ({task['list']})" if task.get("list") else "")) if task else ""
        ok = True
        if task and tool != "start" and not any(t["id"] == task["id"] for t in tasks):
            return self._reply(f"{name} isn't open anymore, so I left it.", now, tone="dim")
        if tool == "done":
            self._done(task, s, phase, blk, tasks, config, now)
            if learn_text:
                self._mark_learn(learn_text, kind="done")
        elif tool in ("snooze", "skip", "pin", "unpin"):
            plan = {"kind": tool, "tasks": [task], "missing": []}
            if tool == "snooze":
                if a.get("until"):
                    plan["until"], plan["untilLabel"] = a["until"].strftime("%Y-%m-%dT%H:%M"), a["until"]
                else:
                    plan["hours"] = a["hours"]
            ov_path = srv.brain.resolve("overridesPath", config)
            before = srv.undo.read_overrides(ov_path)
            try:
                said = srv.command.acts.execute(plan, config if isinstance(config, str) else None)
            except ValueError as e:
                return self._reply(f"I couldn't do that: {e}.", now, tone="bad")
            steps = srv.undo.diff_overrides(before, srv.undo.read_overrides(ov_path), [task["id"]])
            u = srv.runner().undos.record(steps, said, None, now) if steps else None
            said = said.replace(f"\"{task['title']}\"", name, 1) + (" Say undo to take it back." if u else "")
            self._reply(said, now, undo=u, learn=learn_text)
        elif tool == "start":
            ok = self._start_checked(task, s, config, now)
        elif tool == "break":
            ok = self._act("break", "break", s, config, now)
        elif tool == "back":
            if phase != "break":
                return self._reply("You're not on a break right now.", now, tone="dim")
            self._block("end_break", {}, config)
        elif tool == "extend":
            if phase != "work":
                return self._reply("Nothing's running to add time to.", now, tone="dim")
            ok = self._act(f"{a['minutes']} more minutes", f"{a['minutes']} more minutes", s, config, now)
        elif tool == "add":
            lists = srv.snapshot_lists(config) or []
            p = {"title": a["title"], "list": a.get("list"), "due": a.get("due"), "lists": lists,
                 "mode": "reminder" if a.get("remind") else "task", "text": a["title"],
                 "why": "list from your words" if a.get("list") else None}
            if p["mode"] == "reminder" and not p["due"]:
                self._set_pending({"kind": "add", "p": p, "at": now.isoformat(timespec="seconds")})
                return self._reply(f"When should I text you about \"{p['title']}\"?", now)
            if not p["list"] and p["mode"] == "task":
                self._set_pending({"kind": "add", "p": p, "at": now.isoformat(timespec="seconds")})
                return self._reply(self._which_list(p) + (f" It's due {when_text(p['due'], now)}." if p["due"] else ""), now)
            self._commit(p, now)
            learn_text = None                             # adds carry her words, so they are never replayed
        elif tool in ("park", "due", "find", "where"):
            ok = self._read_tool(a, config, now)
            learn_text = learn_text if tool != "park" else None
        if ok and learn_text:
            srv.agent().learned.save(learn_text, a, now)
        return ok

    def _mark_learn(self, text, kind):
        """Tag the newest act row of this kind with the sentence, so undoing it also forgets the sentence."""
        with _LOCK:
            st = self._load(datetime.now().astimezone())
            r = next((x for x in reversed(st["rows"]) if (x.get("act") or {}).get("kind") == kind), None)
            if r:
                r["act"]["learn"] = text
                self._save(st)

    def _start_checked(self, hit, s, config, now):
        b = s.get("blocks") or {}
        phase, blk = b.get("phase") or "idle", b.get("block") or {}
        if phase == "break" and not hit:
            self._block("end_break", {}, config)
            return True
        if phase == "checkin":
            self._reply("First: did you do something just for you on that break? Yes, no, or not now.", now)
            return False
        if phase in ("work", "starting"):
            self._reply(f"\"{blk.get('title')}\" is already running. Say done, break, or cancel.", now, tone="dim")
            return False
        return self._start(hit, config, now)

    def _read_tool(self, a, config, now):
        """park / due / find / where: the facts come from code (the same handlers as the typed sentences)."""
        srv = self.srv
        tool = a["tool"]
        if tool == "due":
            w = a["window"]
            q = ("when is my next deadline" if w == "next" else "what's overdue" if w == "overdue" else f"what's due {w}")
            text = q + (f" in {a['list']}" if a.get("list") else "")
            want = ("schedule",)
        elif tool == "find":
            text, want = f"find {a['query']}", ("lookup",)
        elif tool == "where":
            text, want = f"where did I leave off on {a['project']}", ("project",)
        else:
            text, want = f"park this idea: {a['idea']}", ("park",)
        import route_preview
        label = route_preview.decide(text, srv.snapshot_lists(config), srv.snapshot_tasks(config) or [], now, config=config)
        if label not in want:
            self._reply({"find": f"I didn't find a file matching \"{a.get('query')}\".",
                         "where": f"I couldn't find a project called \"{a.get('project')}\".",
                         }.get(tool, "I couldn't look that up. Try asking it another way."), now, tone="dim")
            return False
        try:
            j = srv.submit_command({"text": text, "skipCapture": True})
        except (ValueError, srv.command.Busy) as e:
            self._reply(f"I couldn't look that up: {e}.", now, tone="bad")
            return False
        if j.get("status") in ("queued", "running"):        # never expected (the label said a rule answers it)
            srv.runner().cancel(j["id"])
            self._reply("I couldn't look that up. Try asking it another way.", now, tone="dim")
            return False
        with _LOCK:
            st = self._load(now)
            r = self._say(st, "", now, log=False, jobId=j["id"])
            self._finish_job_row(r, j)
            self._log(r)
            self._save(st)
        return j.get("status") == "done"


def _age_min(at, now):
    try:
        return (now - datetime.fromisoformat(str(at))).total_seconds() / 60
    except (TypeError, ValueError):
        return 1e9
