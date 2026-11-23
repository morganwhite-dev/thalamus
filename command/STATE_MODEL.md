# Phase 9 state model: Command box

Status: built 2026-11-05 (Opus 5.5). Code: `command/command.py` (logic), wired into `dashboard/server.py` and `dashboard/index.html`.

## 0. Shape

The command box is a thin front for the Phase 1b router. The dashboard server owns a small **job store**; the router does the routing, running, validating, usage counting and routing log exactly as it did standalone.

    POST /api/command  {text, taskId?, followUp?}          -> {job}        (returns at once)
    POST /api/command  {kind: "stuck", taskId}             -> {job}
    GET  /api/command/<jobId>                              -> {job}        (page polls every 2 s while running)
    GET  /api/state                                        -> ... + commands, results, missionLog, usage

Router calls can take minutes (Opus timeout is 20 min), so a job runs on a background thread and the page polls. **One job at a time**; a second submit while one runs is refused with "Busy with ..." (the router's folder lock would serialize them anyway, and a queue would hide that something is slow).

## 1. Job lifecycle

    queued -> running -> done | failed | interrupted

- **done**: the router returned an answer (`outcome` ok, ok-after-retry or step0).
- **failed**: the router returned `failed-needs-morgan`, or raised. The error text is shown; nothing retries (Sonnet/Opus never retry, per the plan).
- **interrupted**: the server stopped while a job was running. On start-up any `queued`/`running` job is marked interrupted, never silently dropped.

## 2. What answers what

| Input                                     | Handler                                                                 | Model call |
| ----------------------------------------- | ----------------------------------------------------------------------- | ---------- |
| "what should I do now", "what's due ..."  | router Step 0 -> **priority engine** (`engine/brain.py`)                | none       |
| `@free/@haiku/@sonnet/@opus [effort] ...` | router Step 1 (tag)                                                     | yes        |
| anything else                             | router Steps 2 to 4 (Jev rubric, tier table)                            | yes        |
| Stuck button                              | `@free` + fixed prompt (free models, then Haiku per the router's rules) | yes        |

The router's `priority_engine` stub is replaced by a real answer: "now" gives the current recommendation and its why-line (plus the active block if one is running); "due <window>" lists open tasks due in that window (today, tomorrow, this week, next week; anything else falls back to the next 7 days).

**Working folder:** every command runs in `router/workspace` (the router default). The page cannot pass a folder, path or attachment. Pointing a command at a real project folder is a later decision for Morgan.

**Follow-up:** a "Follow up on last answer" checkbox reuses the previous job's conversation id, so the router keeps the same model and OpenCode session (plan rule: stay on one model within a conversation). Unticked, every command is standalone.

## 3. Matching task and saved results

QuickToDo's store is never written from outside, so results are saved in the brain, keyed by QuickToDo task id, and shown under the task's category ("globe") in the dashboard.

- **Which task** (first match wins): the task chosen in the box's task menu; else an open task whose title appears in the text (longest title wins, titles under 6 characters ignored); else the task of the running work block; else none.
- **Long** = answer over `longChars` (default 600) characters or over `longLines` (default 12) lines. Long answers with a matching task are saved; short answers stay in the box only. Stuck answers are always saved to their task (they are the first step for that task).
- Long answers with no matching task stay in the box and in the job list, with a note that nothing was saved.
- Store: `command/state/results.json` = `{taskId: [{jobId, at, input, answer, routing}]}`, newest last, at most 10 per task (older ones move to `results-archive.jsonl`, never deleted). The dashboard shows them grouped by category with the task title; a task that left the snapshot keeps its results under "Finished tasks".

## 4. Routing line and mission log

Routing line, shown under every answer: `engine | no model` for Step 0, otherwise `<tier> · <model> · effort <e> · <outcome> · <attempts> attempt(s) · <units> units · <reason>`, plus any usage warning.

Mission log (`missionLog` in `/api/state`): the last 30 events, oldest first, merged from `blocks/state/history.jsonl` (block starts, breaks, check-ins) and `command/state/log.jsonl` (one line per finished command with its routing line). It ends on the current recommendation. Phase 8 restyles it; Phase 9 shows it plain.

## 5. Files and owners

| File                                  | Owner                         | Contents                                                                                  |
| ------------------------------------- | ----------------------------- | ----------------------------------------------------------------------------------------- |
| `command/state/jobs.json`             | command module (lock, atomic) | last 20 jobs: id, status, input, taskId, answer, routing line, error, times, conversation |
| `command/state/results.json`          | command module                | saved long results by task id                                                             |
| `command/state/results-archive.jsonl` | command module (append)       | results pushed out of the 10-per-task cap                                                 |
| `command/state/log.jsonl`             | command module (append)       | mission-log lines for commands                                                            |
| `router/state/*`                      | router (unchanged)            | routing log, usage, audits, cache                                                         |
| `engine/config.json` `command` key    | Morgan                        | `longChars`, `longLines`, `maxInputChars`                                                 |

## 6. Security (server bound to 127.0.0.1 only)

- Bind `127.0.0.1`; a `--host` other than 127.0.0.1/localhost is refused at start-up.
- Every POST needs Host in {127.0.0.1:port, localhost:port} and header `X-Brain: 1`. A custom header forces a CORS preflight the server never approves, so another web page cannot submit commands; the Host check blocks DNS rebinding. An `Origin` header, if present, must be this server's origin.
- GET of a job also requires the Host check (answers can hold personal data).
- Input capped at `maxInputChars` (default 4000); body capped at 16 KB.
- No path, folder, model id or attachment is accepted from the page; tags in the text are the only way to pick a model, as in the CLI.

## 7. Failure handling

- Router raises (OpenCode down, no model in the list): job `failed` with the error; the mission log gets the line.
- Router returns `failed-needs-morgan`: job `failed`, the router's last attempt error shown, with "Nothing was retried at this tier. Retag with @... to try another model."
- Corrupt `jobs.json` or `results.json`: moved to `.bad`, reset, banner shown (same pattern as blocks).

## 8. Tests (`command/tests/test_command.py`, `dashboard/tests/test_server.py`)

Fake router. Step 0 now/due answered with no model; tagged and untagged go through the router; routing line text; one job at a time; interrupted jobs on restart; task matching order; long vs short saving; stuck always saved; 10-per-task cap with archive; follow-up reuses conversation; mission log merge order; server: forbidden without X-Brain, bad Host, foreign Origin, oversize input, job polling, binding refuses a non-local host.
