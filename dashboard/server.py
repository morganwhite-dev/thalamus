#!/usr/bin/env python3
"""Plain dashboard server. Localhost only. Reuses the engine; owns no state.

    python3 dashboard/server.py [--port 8765]
"""
from __future__ import annotations

import argparse
import contextlib
import io
import re
import json
import sys
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "engine"))
sys.path.insert(0, str(HERE.parent / "blocks"))
sys.path.insert(0, str(HERE.parent / "command"))
sys.path.insert(0, str(HERE.parent / "play"))
import blocks  # noqa: E402
import command  # noqa: E402
import done_actions  # noqa: E402
import chat as chat_mod  # noqa: E402
import agent as agent_mod  # noqa: E402
import capture  # noqa: E402
import intent  # noqa: E402
import plain  # noqa: E402
import undo  # noqa: E402
import lookup  # noqa: E402
import play  # noqa: E402
import leftoff_auto  # noqa: E402
import academy  # noqa: E402
import brain  # noqa: E402
from brain_engine import category_for  # noqa: E402
import threading  # noqa: E402

ACTIONS = {"pin", "unpin", "skip", "unskip", "snooze", "lowenergy"}
PLAY_PATH = {"p": None}   # None = play/state/play.json; tests point this at a temp dir
PRESENCE_PATH = HERE.parent / "push" / "state" / "presence.json"
BLOCK_ACTIONS = {"start_work", "begin_now", "extend", "cancel", "skip_break", "take_break", "end_break", "checkin"}
BLOCKS_LOCK = threading.Lock()
BLOCKS_PATHS = {"state": None, "history": None}   # None = module defaults; tests point these at a temp dir
LOCAL_HOSTS = ("127.0.0.1", "localhost")
MAX_BODY = 16384
MAX_CHAT_BODY = 131072     # /api/chat carries pasted text (STATE_MODEL_CHAT.md); the chat checks its own limits
CHAT = {"c": None}
RUNNER = {"r": None}   # CommandRunner, created lazily (tests swap in one with a fake router)
DONE_PATHS = {"p": None}   # None = derived from the snapshot path; tests point this at a temp dir


def make_matcher():
    """The meaning matcher (STATE_MODEL_MATCHER.md), or None when matcher.enabled is false or it cannot start.
    It loads in the background; until Ollama answers, every sentence just goes to the router as before."""
    try:
        if not (brain.load_config().get("matcher") or {}).get("enabled", True):
            return None
        import matcher
        return matcher.Matcher()
    except Exception:  # noqa: BLE001 - the box works without it
        return None


def runner():
    if RUNNER["r"] is None:
        RUNNER["r"] = command.CommandRunner(load_config=lambda: brain.load_config(), matcher=make_matcher())
        RUNNER["r"].play_path = PLAY_PATH["p"]
    return RUNNER["r"]


AGENT = {"a": None, "models": None}   # the chat agent (STATE_MODEL_AGENT.md); tests set "models" to a fake


def agent():
    """The chat agent, stored beside the command jobs like the chat (tests swap the runner, so it follows)."""
    r = runner()
    if AGENT["a"] is None or AGENT["a"].log_path.parent != r.dir:
        AGENT["a"] = agent_mod.Agent(models=AGENT["models"], state_dir=r.dir, matcher=r.matcher)
    return AGENT["a"]


def chat():
    """The chat drawer's conversation, stored beside the command jobs (tests swap the runner, so the store follows it)."""
    r = runner()
    if CHAT["c"] is None or CHAT["c"].path.parent != r.dir:
        CHAT["c"] = chat_mod.Chat(sys.modules[__name__], r.dir)
    return CHAT["c"]


def snapshot_tasks(config):
    try:
        return brain.read_json(brain.resolve("snapshotPath", config))["tasks"]
    except (OSError, ValueError, KeyError):
        return None


def _open_file(path):
    import subprocess
    subprocess.run(["open", path], check=False)


OPENER = {"fn": _open_file}


def snapshot_lists(config):
    """Names of QuickToDo's lists (empty ones too), or None when the snapshot can't be read."""
    try:
        lists = brain.read_json(brain.resolve("snapshotPath", config))["lists"]
        return [str(l) for l in lists]
    except (OSError, ValueError, KeyError):
        return None


def done_paths(config):
    return DONE_PATHS["p"] or done_actions.default_paths(config.get("snapshotPath"))


def write_presence(path=None):
    """Heartbeat from a visible dashboard page. The push layer reads this to stay quiet."""
    brain.write_json_atomic(path or PRESENCE_PATH, {"lastSeen": datetime.now().astimezone().isoformat()})


def block_ctx(result, config):
    """Context for the block state machine. tasks is None if the snapshot can't be read (never infer 'done')."""
    try:
        tasks = brain.read_json(brain.resolve("snapshotPath", config))["tasks"]
    except (OSError, ValueError, KeyError):
        tasks = None
    return {"rec": result, "tasks": tasks, "engine": config}


def block_step(result, config, action=None, args=None):
    """Tick (and optionally apply one action) under a lock; persist; return the dashboard view."""
    now = datetime.now().astimezone()
    ctx = block_ctx(result, config)
    with BLOCKS_LOCK:
        state, err = blocks.load_state(BLOCKS_PATHS["state"])
        if action:
            new, ev = blocks.advance(state, action, ctx, config, now, **(args or {}))   # ValueError leaves state untouched
        else:
            new, ev = blocks.tick(state, ctx, now, config)
        if ev or new != state or err:
            blocks.save_state(new, BLOCKS_PATHS["state"])
            blocks.append_history(ev, BLOCKS_PATHS["history"])
    v = blocks.view(new, ctx, config, now)
    v["error"] = err
    return v


def get_state(config=None, chat=True):
    config = config or brain.load_config()
    error = None
    try:
        result = brain.run(config)
    except SystemExit as e:  # snapshot unreadable: show last good output, flagged
        error = str(e)
        try:
            result = brain.read_json(brain.resolve("recommendationPath", config))
        except (OSError, ValueError):
            return {"error": error or "no data yet", "serverTime": datetime.now().astimezone().isoformat()}
    out = dict(result)
    try:
        out["blocks"] = block_step(result, config)
    except OSError as e:
        out["blocks"] = {"phase": "idle", "block": None, "next": None, "error": f"Block state unavailable: {e}"}
    try:
        r = runner()
        out["command"] = r.view(snapshot_tasks(config) or [], config)
        out["missionLog"] = r.mission_log(BLOCKS_PATHS["history"] or blocks.HISTORY_PATH, result)
    except OSError as e:
        out["command"] = {"busy": False, "jobs": [], "results": {}, "tasks": [], "errors": [f"Command box unavailable: {e}"]}
        out["missionLog"] = []
    try:
        out["actions"] = done_actions.sync(done_paths(config))
    except OSError as e:
        out["actions"] = {"pending": [], "recent": [], "error": f"Done requests unavailable: {e}"}
    try:
        import classes
        cp = Path(config.get("commitmentsPath", "inputs/commitments.json"))
        if not cp.is_absolute():
            cp = HERE.parent / "engine" / cp
        out["classes"] = classes.today(cp, [d for d in Path("~/Desktop/GSU MSIS").expanduser().glob("*") if d.is_dir()], datetime.now().astimezone())
    except Exception as e:
        out["classes"] = []
    try:
        tasks = snapshot_tasks(config) or []
        ecfg = config
        ps = play.load(PLAY_PATH["p"])
        now = datetime.now().astimezone()
        pj = [{"id": p["id"], "title": p["title"], "path": p.get("path")} for p in ps.get("projects", [])]
        autos = leftoff_auto.compute(play.visible_items(tasks, ecfg, category_for) + pj, BLOCKS_PATHS["history"] or blocks.HISTORY_PATH, now,
                                     roots=(ecfg.get("play") or {}).get("projectRoots"))
        off = play.offer(result, tasks, ps, ecfg, category_for, (out.get("blocks") or {}).get("phase", "idle"), now, autos=autos)
        out["play"] = play.view(ps, tasks, ecfg, category_for, off, autos)
        # Continuity: one "where you left off" line per project-like task (Play, brain projects, focus categories such as
        # Security Projects), typed lines winning over automatic ones. The skin shows it only where a project is on screen.
        focus = [t for t in tasks if category_for(t.get("list", ""), ecfg, t.get("title", "")).get("focus")]
        fa = leftoff_auto.compute(focus, BLOCKS_PATHS["history"] or blocks.HISTORY_PATH, now, roots=(ecfg.get("play") or {}).get("projectRoots"))
        acad = academy.compute(focus, now)  # Cyber Academy lesson/quiz progress, read-only
        lo = {}
        for i in set(ps.get("leftOff", {})) | set(autos) | set(fa) | set(acad):
            typed = (ps["leftOff"].get(i) or {}).get("text")
            text = typed or acad.get(i) or autos.get(i) or fa.get(i)
            if text:
                lo[i] = {"text": text, "auto": not typed}
        out["leftOff"] = lo
    except (OSError, ValueError, KeyError) as e:
        out["play"] = {"items": [], "parking": [], "offer": None, "error": f"Play unavailable: {e}"}
        out["leftOff"] = {}
    if chat:
        try:
            out["chat"] = globals()["chat"]().view(out)
        except (OSError, ValueError) as e:
            out["chat"] = {"rows": [], "pending": None, "error": f"Chat unavailable: {e}"}
    out["serverTime"] = datetime.now().astimezone().isoformat()
    out["error"] = error
    return out


def submit_command(body):
    config = brain.load_config()
    command.check_length(body.get("text", ""), config, bool(body.get("pasted")))   # before any rule reads the words: a long paste costs nothing
    tasks = snapshot_tasks(config)
    if tasks is None:
        tasks = []
    if body.get("kind", "ask") == "ask" and not body.get("skipCapture") and not body.get("taskId"):
        lists = snapshot_lists(config)
        text = plain.normalize(str(body.get("text", "")))
        # "done", "I'm stuck on lab 7", "what should I work on": settled by the runner, never a task card
        if lists and not undo.is_undo(text) and not intent.before_capture(text, tasks):
            proposal = capture.detect(text, lists, sector=body.get("sector"), tasks=tasks)
            if proposal:
                return {"capture": proposal}
    try:
        bview = block_step(brain.run(config), config)
    except (SystemExit, OSError):
        bview = None
    return runner().submit(body, tasks, bview)


def build_argv(body):
    action = body.get("action")
    if action not in ACTIONS:
        raise ValueError("unknown action")
    if action == "lowenergy":
        if body.get("state") not in ("on", "off"):
            raise ValueError("state must be on or off")
        return ["lowenergy", body["state"]]
    tid = str(body.get("taskId", ""))
    if len(tid) < 8:
        raise ValueError("taskId required")
    if action == "snooze":
        if body.get("until") == "tomorrow":
            t = datetime.now().astimezone() + timedelta(days=1)
            return ["snooze", tid, "--until", t.replace(hour=9, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")]
        hours = float(body.get("hours", 0))
        if not 0 < hours <= 72:
            raise ValueError("hours must be between 0 and 72")
        return ["snooze", tid, "--hours", str(hours)]
    return [action, tid]


def do_action(body, config=None):
    argv = build_argv(body)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            brain.main(argv + (["--config", config] if isinstance(config, str) else []))
    except SystemExit as e:
        raise ValueError(str(e.code) if e.code else "action failed")
    return get_state()


def make_handler(port):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class H(BaseHTTPRequestHandler):
        server_version = "BrainDash"

        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def host_ok(self):
            return self.headers.get("Host", "") in allowed_hosts

        def origin_ok(self):
            o = self.headers.get("Origin")
            return o is None or o in {"http://" + h for h in allowed_hosts}

        def do_GET(self):
            if not self.host_ok():
                return self.send(403, json.dumps({"error": "bad host"}))
            if self.path in ("/", "/index.html"):
                return self.send(200, (HERE / "index.html").read_bytes(), "text/html")
            if self.path.split("?")[0] == "/api/state":
                return self.send(200, json.dumps(get_state()))
            if self.path.startswith("/api/command/"):
                job = runner().get(self.path.rsplit("/", 1)[-1])
                return self.send(200 if job else 404, json.dumps({"job": job} if job else {"error": "no such job"}))
            self.send(404, json.dumps({"error": "not found"}))

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length", 0))
            except ValueError:
                n = 0
            cap = MAX_CHAT_BODY if self.path == "/api/chat" else MAX_BODY
            raw = self.rfile.read(n) if 0 < n <= cap else b""
            if not self.host_ok() or not self.origin_ok() or self.headers.get("X-Brain") != "1":
                return self.send(403, json.dumps({"error": "forbidden"}))
            if n > cap:
                return self.send(413, json.dumps({"error": "too large"}))
            if self.path == "/api/chat":
                try:
                    body = json.loads(raw or b"{}")
                    if not isinstance(body, dict) or not isinstance(body.get("pastes", []), list):
                        raise ValueError("bad body")
                    chat().send(body.get("text", ""), body.get("pastes") or [], sector=body.get("sector"))
                    return self.send(200, json.dumps(get_state()))
                except (ValueError, json.JSONDecodeError, TypeError) as e:
                    return self.send(400, json.dumps({"error": str(e)}))
            if self.path == "/api/command":
                try:
                    body = json.loads(raw or b"{}")
                    if not isinstance(body, dict):
                        raise ValueError("bad body")
                    out = submit_command(body)
                    if "capture" in out:
                        return self.send(200, json.dumps(out))
                    return self.send(202, json.dumps({"job": out}))
                except command.Busy as e:
                    return self.send(409, json.dumps({"error": str(e)}))
                except (ValueError, json.JSONDecodeError, TypeError) as e:
                    return self.send(400, json.dumps({"error": str(e)}))
            if self.path == "/api/command/undo":
                try:
                    body = json.loads(raw or b"{}")
                    if not isinstance(body, dict) or not str(body.get("undoId", "")).startswith("u-"):
                        raise ValueError("undoId required")
                    return self.send(200, json.dumps({"job": runner().undo(str(body["undoId"]), "Undo")}))
                except (ValueError, json.JSONDecodeError, TypeError) as e:
                    return self.send(400, json.dumps({"error": str(e)}))
            if self.path == "/api/command/cancel":
                try:
                    body = json.loads(raw or b"{}")
                    jid = str(body.get("id", "")) if isinstance(body, dict) else ""
                    if jid.startswith("ag-"):
                        ok = chat().cancel_agent(jid)
                        return self.send(200 if ok else 404, json.dumps({"job": {"id": jid, "status": "cancelled"}} if ok else {"error": "no such job"}))
                    job = runner().cancel(jid) if isinstance(body, dict) else None
                except (ValueError, json.JSONDecodeError):
                    job = None
                return self.send(200 if job else 404, json.dumps({"job": job} if job else {"error": "no such job"}))
            if self.path == "/api/open":
                try:
                    body = json.loads(raw or b"{}")
                    if not isinstance(body, dict):
                        raise ValueError("bad body")
                    real = lookup.safe_open_path(body.get("path", ""), brain.load_config())
                    if real is None:
                        return self.send(403, json.dumps({"error": "That file can't be opened from here"}))
                    OPENER["fn"](str(real))
                    return self.send(200, json.dumps({"ok": True, "name": real.name}))
                except (ValueError, json.JSONDecodeError, TypeError) as e:
                    return self.send(400, json.dumps({"error": str(e)}))
            if self.path in ("/api/capture/add", "/api/capture/undo"):
                try:
                    body = json.loads(raw or b"{}")
                    if not isinstance(body, dict):
                        raise ValueError("bad body")
                    config = brain.load_config()
                    if self.path == "/api/capture/add":
                        done_actions.request_add(body.get("title"), body.get("list"), body.get("due"),
                                                 snapshot_lists(config), done_paths(config))
                    else:
                        done_actions.request_unadd(str(body.get("actionId", "")), done_paths(config))
                    return self.send(200, json.dumps(get_state(config)))
                except done_actions.Busy as e:
                    return self.send(409, json.dumps({"error": str(e)}))
                except (ValueError, json.JSONDecodeError, TypeError, OSError) as e:
                    return self.send(400, json.dumps({"error": str(e)}))
            if self.path in ("/api/done", "/api/undo-done"):
                try:
                    body = json.loads(raw or b"{}")
                    if not isinstance(body, dict):
                        raise ValueError("bad body")
                    config = brain.load_config()
                    if self.path == "/api/done":
                        done_actions.request_done(body.get("taskId"), snapshot_tasks(config), done_paths(config))
                    else:
                        done_actions.request_undo(str(body.get("actionId", "")), done_paths(config))
                    return self.send(200, json.dumps(get_state(config)))
                except done_actions.Busy as e:
                    return self.send(409, json.dumps({"error": str(e)}))
                except (ValueError, json.JSONDecodeError, TypeError, OSError) as e:
                    return self.send(400, json.dumps({"error": str(e)}))
            if self.path == "/api/play":
                try:
                    body = json.loads(raw or b"{}")
                    if n > 4096 or not isinstance(body, dict):
                        raise ValueError("bad body")
                    now = datetime.now().astimezone()
                    act = str(body.pop("action", ""))
                    before = play.load(PLAY_PATH["p"])
                    st = play.apply(before, act, now, **body)
                    play.save(st, PLAY_PATH["p"])
                    ids = lambda s: {x["id"] for k in ("reminders", "habits", "projects", "parking") for x in s.get(k, [])}
                    new = sorted(ids(st) - ids(before))
                    out = get_state()
                    if new:
                        out["created"] = re.sub(r"-f\d+$", "", new[-1])       # (a reminder's follow-ups share its first id) lets the page offer an Undo for what it just added
                    return self.send(200, json.dumps(out))
                except (ValueError, json.JSONDecodeError, TypeError) as e:
                    return self.send(400, json.dumps({"error": str(e)}))
            if self.path == "/api/presence":
                write_presence()
                return self.send(200, json.dumps({"ok": True}))
            if self.path == "/api/block":
                try:
                    body = json.loads(raw or b"{}")
                    if not isinstance(body, dict) or body.get("action") not in BLOCK_ACTIONS:
                        raise ValueError("unknown block action")
                    args = {k: body[k] for k in ("taskId", "minutes", "answer", "countdown", "startedAgo") if k in body}
                    config = brain.load_config()
                    result = brain.run(config)
                    block_step(result, config, body["action"], args)
                    return self.send(200, json.dumps(get_state()))
                except (ValueError, json.JSONDecodeError, TypeError) as e:
                    return self.send(400, json.dumps({"error": str(e)}))
                except SystemExit as e:
                    return self.send(400, json.dumps({"error": str(e.code or "engine unavailable")}))
            if self.path != "/api/action":
                return self.send(404, json.dumps({"error": "not found"}))
            try:
                if n > 4096:
                    raise ValueError("too large")
                body = json.loads(raw or b"{}")
                if not isinstance(body, dict):
                    raise ValueError("bad body")
                self.send(200, json.dumps(do_action(body)))
            except (ValueError, json.JSONDecodeError) as e:
                self.send(400, json.dumps({"error": str(e)}))

    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    if a.host not in LOCAL_HOSTS:
        raise SystemExit("Refusing to bind to a non-local address. The command box runs models; keep it on 127.0.0.1.")
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(a.port))
    print(f"Priority Brain dashboard: http://127.0.0.1:{a.port}/")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
