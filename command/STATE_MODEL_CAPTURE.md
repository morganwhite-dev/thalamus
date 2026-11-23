# Phase 15 state model: add tasks from the command box (plain language)

Morgan's rules (2026-11-08): no command syntax; she types plain sentences. Nothing is created without a one-click confirm.

## Flow
1. She types a sentence in the command box. `POST /api/command` first runs `command/capture.py:detect()` (plain code, no model).
2. Not a task, or a question ("what's due Friday?") -> normal command path, unchanged.
3. Looks like a task -> server answers `200 {capture: proposal}`, no job, nothing written. Proposal: `{id, text, title, list, listGuess, due (ISO or null), lists[], why}`.
4. The page shows a confirm card: title (editable), list (dropdown of REAL lists only; "pick a list" if unsure), due date/time (editable), **Add**, **Ask instead** (sends the same text to the router with `skipCapture`), **Cancel**.
5. Add -> `POST /api/capture/add {title, list, due}` -> server validates (list must exist in the snapshot, title 1-200 chars) and drops `drop-folder/actions/<id>.brainaction.json` with `action:"add"` (same transport, results file and housekeeping as Phase 10 `done_actions`).
6. QuickToDo creates the task in its own `ModelContext`, dedupes on title + list + due day (outcome `alreadyExists`, nothing created), refuses an unknown list (`noSuchList`, never auto-creates a list), writes the outcome to `actions-result.json`.
7. Card shows "Added to <list>" only after the result arrives; "Waiting for QuickToDo..." after 20 s. **Undo** for 2 minutes -> `action:"unadd"`: moves that exact task to Trash (recoverable) only if it is still untouched (open, same title, not started, no progress).

## Intent rules (code, deterministic)
- Question words / trailing `?` -> never a task.
- Triggers: "remind me to", "add ... to my list/todo", "put ... on my list", "I need to / have to / should / gotta / must", "don't forget to", "make a note to", "todo". Also an action verb first (email, call, text, buy, pay, renew, submit, finish, schedule, book, send, order, pick up, clean, fix, write, study, read) plus a date word.
- Date words: today, tonight, tomorrow, weekday names (next occurrence; "next friday"), this weekend, next week (Monday), in N days/weeks, month + day, "by/on/before/due". Time: "at 5pm", "5pm", "noon". Date without time = 12:00 (QuickToDo convention). Past times today roll to tomorrow.
- List guess: an exact existing list name or course name in the text; else keywords (internship/apply/resume -> Internships, security project -> Security Projects, golf/game -> Play, email/call/renew/pay/buy/appointment -> Personal). No guess -> the card asks.

## Safety
Brain never opens QuickToDo's store. Unknown list never creates a list. Same sentence sent twice dedupes in QuickToDo. A pending add blocks an identical second add (409).

## Tests
Python: intent yes/no table, dates (fixed clock), list guess, title cleanup, file contents, validation, 409. Swift: add, dedupe, unknown list, trashed duplicate allowed, unadd untouched vs touched, invalid.

## Check-ins on a due task (2026-11-13, Morgan: "add complete tier 1 by monday ... but remind me / check in daily")

**Why:** a task with a deadline gave no nudges before it, and adding "every day" turned it into a plain repeat that lost the due date.

**Sentence shape:** a due date (by / due / before / until + a day) plus a daily rhythm plus check-in wording (check in with me, remind me, nudge me, keep me honest, until then). Without a due date it stays a plain repeating item as before; without check-in wording a repeat stays a repeat.

**Proposal:** a normal task proposal (title, list, due) plus `checkin: {days, nudgeAt, label, until}`. `until` is the due day. No `habit` field, mode stays `task`.

**Card:** same add card; one extra line: "Daily check-in until Mon · 5:00 PM". Add creates the task (existing path), then a text-only repeating item in the play store tied to it (`forTask` title + list, `until`, `startOn`). Undo takes back both.

**Lifecycle of the check-in:** one gentle text a day at `nudgeAt` (default 5 PM) from `startOn` (today, or tomorrow when added after the nudge time) through the due day. It stops by itself when the due day has passed or the task is no longer open in the snapshot (done in Thalamus or QuickToDo). No streaks, no "you missed". The cloud copy gets `until` and `startOn` through queue.json, so it also stops there.

**Text:** "Check-in: Complete tier 1 is due Monday. Have you worked on it? No pressure."

**Not changed:** repeating items, reminders, study plans, ranking, the engine.
