# State model: undo for what the chat changes

Written 2026-11-22, branch `feat/matcher-wiring`. Morgan: "add undo for anything the chat changes" (the chat drawer relies on it as the safety net instead of more rule hardening).

## What the chat can change, and its undo

| Change (typed in the box) | Where it is stored | Undo puts back |
| --- | --- | --- |
| pin / unpin | engine `overrides.json` `pins` | that task's pin entry as it was |
| skip ("not this one") | `overrides.json` `skips` | that task's skip entry as it was |
| snooze | `overrides.json` `snoozes` | that task's snooze entry as it was (none, or the earlier snooze) |
| park an idea | play store `projects` | removes the new project |
| cancel a text reminder | play store `reminders` | the reminder, with its id and time |
| "update the status of X" | play store `leftOff[taskId]` | the earlier line (or none) |

Adding a task from the card already has its own Undo (Phase 15) and is not repeated here.

## How it works

- Every chat change records an undo entry in `command/state/undo.json`. Each entry holds an id, the job id, `createdAt`, `expires` (2 minutes, like the other Undo buttons) and a list of steps. Each step names one record and holds its value **before** and **after** the change.
- Undo is record by record. It only touches the records the change touched. A step is undone only if the record still holds the **after** value. If anything changed since (a button, another sentence), nothing is undone, and the reply says so: "That changed since, so I left it alone."
- The answer of a job that changed something carries `undo: {id, expires}`. The page shows an **Undo** button on that answer until it expires.
- Typing "undo", "undo that" or "take that back" undoes the newest chat change that has not expired. With none: "Nothing the box changed in the last 2 minutes. To take back a Done, press Undo on the status line."
- Replies are first person and name what was taken back: "Undone. I took back: Snoozed \"Read Chapter 5\" for 2 hours."
- An entry is used once. Entries older than 10 minutes are dropped when the file is written.

## Endpoint

`POST /api/command/undo {undoId}`: same checks as the other POSTs (localhost, `X-Brain`). It returns the reply as a finished job, so it shows like any answer.

## Never

- It never undoes a change someone made outside the chat.
- It never overwrites a record that changed after the chat's change.
- It never undoes after the 2 minutes are up.
