# The chat agent: free models with tools, Haiku as backup (design 2026-11-22; BUILT the same day, branch `feat/chat-agent`)

Replaces the Phase 21 parser plan (`STATE_MODEL_PARSER.md`). Decided by Morgan 2026-11-22 (see CLAUDE.md, Phase 21 replaced).

## Why

"mark read chapter 7 complete in network security" missed a rule and went to Sonnet (high effort) as a plain
question. That model saw no task list and had no tools, so no model could have marked the task done. Adding
hand-written rules for every phrasing does not scale.

## Order for each chat message

1. **Pending question.** If Thalamus asked something ("Which one?", "Sound right?"), the existing answer
   handling runs first (`dashboard/chat.py _answer_pending`).
2. **Instant rules (kept, frozen).** The existing rules in `chat.py _act`, `intent.py`, `capture.py`, `acts.py`
   and the Step 0 answers stay as the free, instant path. No new rules are added.
3. **Learned sentences.** The Ollama meaning matcher (`command/matcher.py`) also checks the message against
   sentences a model handled correctly before (see "Learning"). A close match (threshold tuned like the matcher,
   start at 0.90) replays the saved action through the same checks, with no model call.
4. **Free model with tools.** One call. It sees the context card and returns one JSON object (below).
5. **Haiku, same prompt, same tools.** Only when step 4 fails: an error or rate limit, a timeout (8 s), output
   that is not the JSON object, or an action the checks reject for a reason other than "ambiguous".
6. **Nothing else.** No Sonnet, no Opus in the chat. If Haiku also fails: "I couldn't do that one. Try saying it
   another way." Hard asks (write a cover letter, explain a whole chapter) get Haiku's best try in the reply.

Pasted text skips steps 2 and 3 and goes to step 4 with the paste expanded (as today, never logged).

## What the model sees (the context card)

Built fresh for every message, in plain code, from `/api/state` and the snapshot:

- Today's date, weekday and time; whether a work block or break is running (and on what).
- The current task ("Do this now") with its id.
- Open tasks: up to 60, nearest due first. Each line: `id | title | list | due | pinned/snoozed`.
  Play items and the Play parking lot are listed separately and marked "not for work blocks".
- Her lists (so an add can only name a real one).
- Today's classes and tests (from `engine/inputs/commitments.json`).
- The last 10 chat messages (hers and Thalamus's), so "the second one" and "that lab" make sense.
- The open question, if any.

Ids are shortened to `t1`, `t2`... in the card and mapped back in code, so the model never handles real ids.

## What the model returns

One JSON object, nothing else:

```json
{"reply": "first-person text for the chat",
 "action": null | {"tool": "<name>", ...args}}
```

At most one action per message. "mark 7 and 8 done" gets one action and a reply asking to confirm the second
(kept simple on purpose; revisit if she does this often).

## Tools

| tool | args | runs through (existing code) |
| --- | --- | --- |
| `done` | `task` | `done_actions.request_done` (QuickToDo completes it; undo for 2 min) |
| `add` | `title`, `list`, `due` (ISO or null), `remind` (bool) | `done_actions.request_add` / reminders (as today's capture) |
| `snooze` | `task`, `until` (ISO) or `hours` | `acts.py` snooze (undo store) |
| `skip` | `task` | `acts.py` skip |
| `pin` / `unpin` | `task` | `acts.py` pin |
| `start` | `task` or null | `chat.py _start` (block, no 3-2-1) |
| `break` / `back` / `extend` | `minutes` for extend | `chat.py` block actions |
| `park` | `idea` | `park.py` |
| `find` | `query` | `lookup.py` (the reply lists files with Open links) |
| `due` | `window` (today, this week, overdue...) and optional `list` | `schedule_qa.py` (code writes the list, not the model) |
| `where` | `project` | `project_status.py` |

`due`, `find` and `where` are read-only: code produces the facts and Thalamus shows them under the model's reply,
so dates and file paths are never typed by a model.

## Checks before any action runs (plain code)

- The task id is in the card and still open. The list for an add is one of her lists. Dates parse and are not in
  the past (a due date may be today). `hours` is 1 to 72.
- **Ambiguity is never guessed.** If her message's words fit more than one open task (`plain.match_target` says
  "many") and the action's task is not the current task, not named exactly, and not the one the last few messages
  were about, the action is refused and Thalamus asks "Which one: A (List) or B (List)?" (the existing which-one
  question, so her answer works the same way).
- Play items cannot be started as work blocks.
- A refused action is never retried on another model for "ambiguous"; the question goes to her.
- Every action is reported with the class or list ("Marked "Read Chapter 7" (Network Security) done. Say undo to
  take it back."), whatever the model wrote.

## Learning

- Every message a model handled whose action passed the checks, and was not undone within 2 minutes, is saved to
  `command/state/learned.jsonl`: the sentence (normalized), the tool, and the action in words that do not depend on
  today's ids (task title + list, or "current task"; relative dates like "tomorrow" kept as words).
- The matcher embeds these alongside its built-in examples. Step 3 replays a saved action only when it resolves to
  exactly one open task today; otherwise it falls through to step 4.
- An undone action is not saved; if it was replayed from a learned sentence, that sentence is removed.
- `python3 command/learned.py` lists and deletes saved sentences.

## Models

- **Free:** read the live list from OpenCode (it changed on 2026-11-22: GLM, Crouton and Big Pickle are gone).
  Start with `deepseek-v4.1-flash-free` (spike: 1.3 to 3.3 s, right task every time, valid JSON 8 of 8), then the
  next enabled free chat model. One free attempt per message, so a failure reaches Haiku within about 10 s.
- **Haiku:** `claude-haiku-5-5`, low effort, stateless (`experimental.generate.text`, which works for Claude).
- Calls run as plain text generation, not agent sessions with file tools: the model only writes the JSON object.
  Free models refuse the stateless endpoint, so they run as `opencode run` sessions with no tools allowed, archived
  after.
- Usage: Haiku calls count in the existing usage counter (0.1 each); free calls are counted separately.

## Logging

`command/state/agent-log.jsonl`, one line per message: step that answered (rule, learned, free, haiku), model,
time taken, tool, check result, whether she undid it. Pasted text is logged as its length only. This shows how
often each step answers and whether the free model is good enough.

## What changes in the code

- New `command/agent.py`: context card, prompt, model calls, JSON parsing, checks, tool dispatch.
- `dashboard/chat.py _route`: messages that reach it go to `agent.py` instead of the router. The router stays for
  `prep:` (Phase 13) and nothing else from the chat.
- `command/matcher.py`: also loads `learned.jsonl`.
- The `/` menu stays; its entries become examples, not the only words that work.

## Verify

- A table of everyday sentences (marking done with and without the class, adds, snoozes, "what's due", casual
  chat, vague ones that must ask which) runs against a fake model and real checks: every action is checked, every
  ambiguous one asks.
- Live on free models: 30 sentences, report right / asked / wrong and time per step.
- Undo after an agent action works and removes a learned sentence.
- No message from the chat ever reaches Sonnet or Opus (test on the router call).

## As built (2026-11-22)

- Code: `command/agent.py` (context card, prompt, checks, learned sentences, model calls), `dashboard/chat.py`
  (`_to_agent`, `_agent_start/_run/_finish/_dispatch`, `_read_tool`, `_start_checked`), `dashboard/server.py`
  (`agent()`, `/api/command/cancel` stops an `ag-` row). Tests: `dashboard/tests/test_chat.py` class `Agent` with a fake
  model (`FakeModels` in `test_server.py`).
- **What goes to the agent:** sentences the rules leave for a model (`route_preview` labels `free` and `jev`), pasted
  text, `@free` / `@haiku` tags (`@haiku` skips the free step), her answer to a question the model just asked (a short
  reply within 10 minutes), a request to do something that a read-only rule would have answered with a list ("keep
  week 6 at the top today"), and any sentence a rule answered with a dead end ("I don't see a project called ...").
- **Still on the router:** `@sonnet` / `@opus` tags she types herself, the Stuck step (free models then Haiku, as
  before) and `prep:`. Nothing else from the chat reaches a model above Haiku.
- **Learning as built:** exact sentence match first, then the meaning matcher's embeddings at 0.90 when Ollama is up.
  Adds and parks are never learned (their words are the content).
- **Short ids** the model leaks into a reply ("t1 AWS Intro Labs") are stripped in code.
- **Timeouts:** free 25 s, Haiku 60 s. Free model preference: `deepseek-v4.1-flash-free`, then the next live free model.
- **Live check (2026-11-22, real task list, test server):** 20 sentences. General questions, small talk, a quiz and its
  follow-up, done with a which-one question, pin, snooze, overdue, a file find and a project status all came back
  right; free answers took 1.3 to 3.7 s, Haiku 5.7 s, learned replays under 1 s.
- **Review fixes (Codex, same day):** her short answer to a model's question goes back to the model but is never
  learned, and a sentence is learned only when its words name the task (so "mark it done" is not replayed onto an old
  task); a learned replay re-runs the which-one check; two tasks with one name in the same list are asked about with
  their due dates; a model tag inside pasted text is content, not a model pick; Stop after the action has started says
  it is too late (say undo); undo after a learned replay forgets the sentence; a snooze to a date is not learned.
  Stopping while a model is still answering throws its answer away, but the model call itself runs to its timeout.
