"""Thin wrapper around the bundled OpenCode CLI.

Facts checked live on 2026-11-05 (OpenCode 2.2.5):
- `opencode-cli api model.list` returns the live model catalog (the console's
  enable/disable switches are NOT reflected there, and dropped models still answer).
- The classifier (Jev) is not in the catalog but answers on
  `api experimental.generate.decisions` with model opencode/jev-1.13-free (cost 0).
- Free chat models refuse the stateless `experimental.generate.text` endpoint
  ("Free usage limit reached") but work through a normal session (`opencode run`).
- Effort is passed as a model variant: `run -m provider/model#variant`. The Claude
  plugin turns the variant into `claude --effort <level>`.
- Claude works on the stateless text endpoint too (used for the cheap Haiku audit).
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunResult:
    ok: bool
    text: str = ""
    error: str | None = None
    error_kind: str | None = None  # timeout | rate_limit | provider | tool | exit | empty
    session_id: str | None = None
    cost: float = 0.0
    tokens: dict = field(default_factory=dict)
    duration_s: float = 0.0
    plan_notice: str | None = None  # "used 75% of the 7-day window, resets ..."
    tool_errors: int = 0          # 1 if the run ended on an unrecovered tool error
    tool_calls: int = 0
    tool_error_detail: str = ""


USAGE_NOTICE_RE = re.compile(r"used\s+(\d+)%\s+of\s+the\s+([\w-]+)\s+window[^.]*?resets\s+at\s+([0-9:\- ]+)", re.I)


class OpenCodeError(RuntimeError):
    pass


class OpenCodeClient:
    def __init__(self, cli_path: str, workspace: str, auto_approve: bool = False,
                 permissions: list[dict] | None = None, stall_seconds: float = 90,
                 agent: str | None = None):
        self.stall_seconds = stall_seconds
        self.agent = agent
        self.cli = cli_path
        self.workspace = workspace
        self.auto_approve = auto_approve
        self.permissions = permissions or []

    # ---- low level -------------------------------------------------------
    def _api(self, op: str, data: dict | None = None, timeout: int = 120) -> dict:
        cmd = [self.cli, "api", op]
        if data is not None:
            cmd += ["-d", json.dumps(data)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = proc.stdout.strip()
        try:
            body = json.loads(out.splitlines()[0]) if out else {}
        except json.JSONDecodeError:
            raise OpenCodeError(f"{op}: non-JSON reply: {out[:200]}")
        if proc.returncode != 0 or "_tag" in body:
            raise OpenCodeError(f"{op}: {body.get('message') or out[:300]}")
        return body

    # ---- catalog ---------------------------------------------------------
    def list_models(self) -> list[dict]:
        return self._api("model.list")["data"]

    def create_session(self, directory: str, title: str | None = None) -> str:
        body = {"location": {"directory": directory}, "permissions": self.permissions}
        if title:
            body["title"] = title[:80]
        return self._api("session.create", body)["data"]["id"]

    # ---- housekeeping ----------------------------------------------------
    def archive_session(self, session_id: str) -> None:
        """Archive (not delete) a finished router session; reversible in OpenCode."""
        subprocess.run([self.cli, "api", "session.update", "--param", f"sessionID={session_id}",
                        "-d", json.dumps({"archived": True})], capture_output=True, text=True, timeout=30)

    # ---- classifier ------------------------------------------------------
    def decisions(self, model: dict, input_text: str, questions: list[dict]) -> dict[str, Any]:
        """Returns {question_name: answer_dict}."""
        body = self._api(
            "experimental.generate.decisions",
            {"model": model, "input": [{"type": "text", "text": input_text}], "questions": questions},
        )
        return {a["name"]: a for a in body["data"]["answers"]}

    # ---- stateless text (Claude audit) ----------------------------------
    def generate_text(self, provider: str, model: str, prompt: str, variant: str | None = None, timeout: int = 300) -> str:
        ref = {"id": model, "providerID": provider}
        if variant:
            ref["variant"] = variant
        return self._api("experimental.generate.text", {"prompt": prompt, "model": ref}, timeout=timeout)["data"]["text"]

    # ---- full agent run --------------------------------------------------
    def run(self, provider: str, model: str, prompt: str, variant: str | None = None,
            timeout: int = 300, session_id: str | None = None, title: str | None = None,
            cwd: str | None = None, files: list[str] | None = None) -> RunResult:
        spec = f"{provider}/{model}" + (f"#{variant}" if variant else "")
        cmd = [self.cli, "run", "-m", spec, "--format", "json"]
        for f in files or []:
            cmd += ["-f", f]
        workdir = cwd or self.workspace
        if not session_id:
            # New sessions are created through the API so they carry the router's permission
            # rules (edits fenced to the folder, deletion/push commands denied).
            try:
                session_id = self.create_session(workdir, title)
            except OpenCodeError as e:
                return RunResult(ok=False, error=f"could not create session: {e}", error_kind="provider")
        cmd += ["-s", session_id]
        # Name the agent only where it is defined (OpenCode fails a run with 'Agent not found'
        # otherwise). Without it, runs fell back to the built-in plan agent (see config.json).
        if self.agent and agent_defined(workdir, self.agent):
            cmd += ["--agent", self.agent]
        if self.auto_approve:
            cmd += ["--auto"]
        cmd.append(prompt)
        start = time.time()
        # OpenCode takes its project folder from $PWD, not the real process cwd (checked
        # 2026-11-05: with only cwd= set, sessions landed in the parent folder).
        env = {**os.environ, "PWD": workdir}
        out, code, stop = _run_watched(cmd, workdir, env, timeout, self.stall_seconds)
        if stop == "stall":
            return RunResult(ok=False, error=f"OpenCode never started the model (no output in {self.stall_seconds:g}s)",
                             error_kind="stall", session_id=session_id, duration_s=time.time() - start)
        if stop == "timeout":
            return RunResult(ok=False, error=f"timed out after {timeout}s", error_kind="timeout",
                             session_id=session_id, duration_s=time.time() - start)
        res = parse_run_events(out, code)
        res.duration_s = time.time() - start
        return res


def agent_defined(folder: str, agent: str) -> bool:
    """True if `folder`'s opencode.json (or .opencode/agent/<agent>.md) defines `agent`."""
    from pathlib import Path
    p = Path(folder) / "opencode.json"
    try:
        if p.exists() and agent in (json.loads(p.read_text()).get("agent") or {}):
            return True
    except (OSError, json.JSONDecodeError):
        pass
    return (Path(folder) / ".opencode" / "agent" / f"{agent}.md").exists()


# Cancel support: the command box sets this; every running and later attempt stops at once.
CANCEL = threading.Event()


def request_cancel():
    CANCEL.set()


def clear_cancel():
    CANCEL.clear()


def _run_watched(cmd, cwd, env, timeout, stall_seconds):
    """Run `cmd`, collecting stdout. Stop early if it prints nothing for `stall_seconds`
    before its first output line (OpenCode stalled before the model started; seen live
    2026-11-05: 0 messages, 0 tokens, 10 minutes lost), or after `timeout` overall.
    The child gets its own process group, which is killed as a whole, so helper processes
    holding the pipe can't keep us waiting (subprocess.run's timeout can hang on that).
    Returns (stdout, returncode, None | "stall" | "timeout")."""
    # stdin is closed on purpose: `opencode run` appends whatever it reads from stdin to the
    # message, so an inherited pipe (a heredoc, a parent's input) leaked into the prompt
    # (seen live 2026-11-05: Haiku got the caller's Python script and tried to run it).
    if CANCEL.is_set():
        return "", -9, "cancelled"
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True,
                            cwd=cwd, env=env, start_new_session=True)
    lines: list[str] = []
    first = threading.Event()

    def pump():
        for line in proc.stdout:
            lines.append(line)
            first.set()
    t = threading.Thread(target=pump, daemon=True)
    t.start()
    start = time.time()
    stop = None
    while proc.poll() is None:
        el = time.time() - start
        if CANCEL.is_set():
            stop = "cancelled"
        elif el >= timeout:
            stop = "timeout"
        elif stall_seconds and not first.is_set() and el >= stall_seconds:
            stop = "stall"
        if stop:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                proc.kill()
            break
        time.sleep(0.2)
    proc.wait()
    t.join(timeout=5)
    return "".join(lines), proc.returncode, stop


def parse_run_events(stdout: str, returncode: int = 0) -> RunResult:
    texts: list[str] = []
    statuses: list[tuple] = []
    res = RunResult(ok=False)
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        res.session_id = ev.get("sessionID") or res.session_id
        kind = ev.get("type")
        part = ev.get("part") or {}
        if kind == "text":
            t = part.get("text") or ""
            m = USAGE_NOTICE_RE.search(t)
            if m and "usage:" in t:
                res.plan_notice = f"{m.group(1)}% of {m.group(2)} window, resets {m.group(3).strip()}"
                continue  # plugin notice, not model output
            texts.append(t)
        elif kind == "step_finish":
            res.cost += float(part.get("cost") or 0)
            for k, v in (part.get("tokens") or {}).items():
                if isinstance(v, (int, float)):
                    res.tokens[k] = res.tokens.get(k, 0) + v
        elif kind == "tool_use" or kind == "tool":
            state = (part.get("state") or {})
            statuses.append((part.get("tool"), state.get("status"), str(state.get("error") or "")[:160]))
        elif kind == "error":
            err = ev.get("error") or {}
            msg = err.get("message") or json.dumps(err)[:300]
            res.error = msg
            low = (msg + str(err.get("type", ""))).lower()
            res.error_kind = "rate_limit" if ("rate" in low or "limit reached" in low or "429" in low) else "provider"
    res.text = "\n".join(t for t in texts if t).strip()
    # A tool error the model recovered from (a later tool call completed) is normal agent
    # behaviour; only an error that was never followed by a successful call counts.
    res.tool_calls = len(statuses)
    if statuses and statuses[-1][1] == "error":
        res.tool_errors = 1
        res.tool_error_detail = f"{statuses[-1][0]}: {statuses[-1][2]}"
    if res.error is None and returncode != 0:
        res.error, res.error_kind = f"opencode exited {returncode}", "exit"
    res.ok = res.error is None
    return res
