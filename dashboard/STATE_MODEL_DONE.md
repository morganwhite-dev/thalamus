# Phase 10 state model: Done in Thalamus completes it in QuickToDo

Status: BUILT and verified live 2026-11-06 (Opus 5.5). Morgan chose the action file (section 1).

## 0. Goal and rules

Pressing Done on a task in Thalamus (or the Plain page) completes that exact task in QuickToDo, with no second step. It must:

- complete it the same way QuickToDo's own checkbox does (completedAt, stage Done, progress 100, reminders cancelled, next copy spawned for repeating tasks, stage remembered for undo);
- never complete the wrong task, never complete twice, never complete a task that is waiting on another open task;
- be undoable for a short window;
- keep the existing boundary: the brain never opens QuickToDo's database; QuickToDo makes every change itself.

## 1. Transport: how the brain tells QuickToDo (decision needed)

**Recommended: an action file in the folder QuickToDo already watches.** The dashboard server writes one small file per request into `priority-brain/drop-folder/actions/`. QuickToDo's existing folder watcher (the Phase 1/3 one, already granted for `drop-folder`) sees it within about 2 seconds, completes the task by its id, and writes the outcome to a results file inside its own container, next to the snapshot. The brain reads that file and the refreshed snapshot to show the result.

Why this over the deep link the tracker assumed (`quicktodo://complete?...`):

|                                  | Action file (recommended)                                                                  | Deep link (`open quicktodo://...`)                                                        |
| -------------------------------- | ------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------- |
| Window pops or app jumps forward | No                                                                                         | Likely: SwiftUI opens a window for incoming URLs on macOS, and a closed app gets launched |
| App closed when you press Done   | Waits; done the moment QuickToDo next opens (completedAt = the time you pressed it)        | Launches QuickToDo                                                                        |
| Did it work?                     | Yes: QuickToDo writes a result (done / already done / waiting on another task / not found) | Fire-and-forget; only the snapshot hints at it                                            |
| Repeats safely                   | Yes: each request has an id, processed once                                                | A repeated link is a second request                                                       |
| New permissions                  | None (folder already granted, read-only is enough)                                         | None                                                                                      |

The existing `quicktodo://complete?title=...` link stays as it is; nothing removes it.

## 2. Files and owners

| File                                                                          | Owner                                                  | Contents                                                                                       |
| ----------------------------------------------------------------------------- | ------------------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| `drop-folder/actions/<actionId>.brainaction.json`                             | dashboard server writes; server deletes once processed | `{version:1, id, action: "complete" or "reopen", taskId, title, requestedAt}`                  |
| `<QuickToDo container>/Application Support/BrainSnapshot/actions-result.json` | QuickToDo (atomic write, last 200 entries)             | per action id: `{outcome, taskId, title, processedAt, detail, spawnedTaskId?, previousStage?}` |
| `dashboard/state/actions.json`                                                | dashboard server                                       | pending requests (id, taskId, title, requestedAt) until a result arrives                       |

`taskId` is the QuickToDo task UUID the snapshot already carries. `title` is only for logs and a safety check (see 3).

## 3. QuickToDo side (Swift)

New file `BrainActions.swift` (no edits to `RootShellView.swift` or other files with Morgan's uncommitted UI work):

- The watcher's scan also collects `*.brainaction.json` files (separate pattern constant; course folders never contain them).
- For each action id not already in the results file, in `requestedAt` order:
  - **complete**: fetch the task by UUID. Outcomes:
    - `notFound`: no such task, or it is in the Trash.
    - `alreadyDone`: already completed (no change, no second recurrence spawned).
    - `blocked`: `isBlocked(in:)` is true (waiting on another open task); no change.
    - `titleMismatch`: the stored title differs from the request's title after trimming and case-folding; no change (guards against acting on a different task than Morgan saw).
    - `done`: same steps as the checkbox's `completeTask` (stage remembered, isCompleted, completedAt = requestedAt, stage Done, progress 100, reminders cancelled, next occurrence spawned and its reminder scheduled), then save. Records `spawnedTaskId` and `previousStage`.
  - **reopen** (undo): only if the task was completed by a `done` result from this channel and is still completed. Restores isCompleted false, completedAt nil, progress back from 100, stage from memory, reminders rescheduled, and deletes the spawned next copy only if it is untouched (not started, no progress, same title/list/rule/due), mirroring the checkbox's untick. Otherwise `cannotReopen` with a reason.
- Every action is logged to `AutoImport/import.log` (`BRAIN ACTION complete <title>: done`).
- Results written even on failure, so nothing is silently dropped. A malformed file gets outcome `invalid`.
- The save triggers the existing snapshot write, so the task leaves `brain-snapshot.json` at once.

## 4. Brain side (Python)

- `POST /api/done {taskId}`: looks the task up in the current snapshot (must be open), writes the action file atomically, records it as pending, returns fresh state. A second Done on the same task while one is pending is refused (409), not queued.
- `POST /api/undo-done {actionId}`: allowed for 2 minutes after a `done` result; writes a `reopen` action.
- `/api/state` gains `actions: {pending: [...], recent: [...last 10 results with outcome text]}`. Housekeeping on each state read: match results to pending ids, delete processed action files, drop results older than a day from `recent`.
- Pending longer than 20 s with QuickToDo's snapshot older than its heartbeat: the UI says "Waiting for QuickToDo to pick this up. Is it open?" (still processed later).
- Blocks: unchanged. When the task leaves the snapshot, the existing `tick` already marks a running block on it as over with `task-done`, so the page shows "Nice, that task is done" and offers the break.

## 5. UI

- Thalamus: Done button (check icon, the design's own) on the "Do this now" panel and in each task's detail; while pending it reads "Marking done…"; then a log line plus a short "Done · Undo" for 2 minutes. Outcomes other than `done` show their plain reason ("That task is waiting on another one", "It was already done").
- Plain page: same Done button next to Pin / Snooze / Not this one.
- The task-detail note "Mark it done in QuickToDo" goes away.

## 6. Tests

- Swift (`QuickTodoTests/BrainActionsTests.swift`, in-memory store): done; already done; blocked; not found; trashed; title mismatch; repeating task spawns exactly one copy; the same action processed twice changes nothing; reopen restores and removes the untouched copy; reopen keeps a copy that was touched; invalid file recorded; completedAt equals requestedAt.
- Python (dashboard tests): done writes one well-formed file; refuses unknown, already-pending and non-open tasks; X-Brain/Host checks; housekeeping deletes processed files; undo window enforced; state carries pending and recent.

## 7. Verify (live)

On a throwaway task created for the test (never a real one): press Done in Thalamus, see it completed in QuickToDo with no other step and gone from Thalamus; press Undo, see it back; a block running on it ends with "task done"; a dependent (blocked) test task shows the blocked reason; with QuickToDo quit, Done waits and completes on next launch. QuickToDo store backed up before any of this.
