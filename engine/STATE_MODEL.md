# Phase 4 state model: Priority engine

Status: DRAFT for Morgan's review, 2026-11-05. Nothing is built yet.

## 0. Shape

The engine is one pure function, plus a thin CLI around it:

    recommend(snapshot, overrides, commitments, config, now) -> recommendation

- No model calls, no network, no writes to QuickToDo. `now` is passed in, so tests can fake time.
- Three inputs it reads, one output it writes, one file it owns:

| File                               | Owner / writer                              | Engine access         |
| ---------------------------------- | ------------------------------------------- | --------------------- |
| `brain-snapshot.json`              | **QuickToDo app** (Swift, on data change)   | read only             |
| `engine/state/overrides.json`      | the engine CLI (pin, snooze, skip, mode)    | read + write (atomic) |
| `engine/config.json`               | Morgan                                      | read only             |
| `engine/inputs/commitments.json`   | planner calendar export (class times, work) | read only             |
| `engine/state/recommendation.json` | engine                                      | write (atomic)        |

QuickToDo's database and every QuickToDo task field are never written by the engine. Marking a task done, or changing its due date, stays in the app (or a `quicktodo://` deep link later).

## 1. Snapshot (what QuickToDo writes)

`brain-snapshot.json`, rewritten atomically (temp file + rename) after any save, import, or completion.

    {
      "schemaVersion": 1,
      "generatedAt": "2026-11-05T14:02:11-05:00",
      "lists": ["Cloud Computing", "Network Security", "Internships", "Security Projects", "Personal"],
      "tasks": [
        { "id": "<UUID>", "title": "...", "notes": "...", "list": "Network Security",
          "dueDate": "2026-11-08T23:59:00-05:00" | null,
          "priority": "high" | "medium" | "low" | null, "stage": "...", "estimatedMinutes": 45 | null,
          "dependsOnTaskID": "<UUID>" | null, "progressPercent": 0-100,
          "startedAt": ... | null, "rescheduleCount": 0 }
      ]
    }

Rules:

- Only **open, not-trashed** tasks are included (`completedAt == nil`, `deletedAt == nil`). A task finishing or being trashed simply disappears from the next snapshot; the engine needs no "done" state of its own.
- One list name per task. The engine maps list to category (section 3), so the snapshot carries no category logic.
- Written to the app container (readable by the engine, no new sandbox permission). Path is in `config.json`. Phase 6 copies this file for the cloud scheduler.
- Heartbeat is `generatedAt`. The engine marks the snapshot **stale** when `now - generatedAt` is over `staleAfterHours` (default 24, matches the sync-health rule).

## 2. Overrides (what Morgan's actions change)

`overrides.json`, keyed by task UUID, all times local:

    {
      "version": 1,
      "pins":    [ { "taskId": "...", "pinnedAt": "...", "forDate": "2026-11-05" } ],
      "snoozes": [ { "taskId": "...", "until": "2026-11-05T18:00:00-05:00" } ],
      "skips":   [ { "taskId": "...", "forDate": "2026-11-05" } ],
      "mode":    { "lowEnergy": false, "since": null }
    }

Every run starts by **pruning**: drop entries whose task is no longer in the snapshot, whose `forDate` is before today, or whose `until` has passed. Overrides never pile up, and nothing is shown as a backlog.

## 3. Derived state (computed every run, never stored)

Category from list, via `config.json` (no personal data in the logic):

    categories: [
      { "name": "Schoolwork",  "rank": 1, "lists": ["Cloud Computing", "Network Security"], "hard": true  },
      { "name": "Internships", "rank": 2, "lists": ["Internships"],                          "hard": true  },
      { "name": "Security",    "rank": 3, "lists": ["Security Projects"],                    "hard": false },
      { "name": "Personal",    "rank": 9, "lists": ["Personal"],                             "hard": false }
    ]
    unmappedList -> rank 8, soft   (shows up, never lost)

Per task, each run:

| Field          | How it is derived                                                                                               |
| -------------- | --------------------------------------------------------------------------------------------------------------- |
| `hard`         | category is hard **and** `dueDate` is set                                                                       |
| `effectiveDue` | hard: the real `dueDate`. soft with a past `dueDate`: **today** (reflow). soft future: real date. undated: none |
| `band`         | see below                                                                                                       |
| `blocked`      | `dependsOnTaskID` points at a task still in the snapshot (still open)                                           |
| `eligible`     | not blocked, not snoozed, not skipped today                                                                     |
| `minutes`      | `estimatedMinutes`, else the default for the category in config (editable)                                      |

Bands, in priority order:

1. **pinned** (pinned today)
2. **escalated** (hard, `dueDate < now`)
3. **dated** (anything with an `effectiveDue`)
4. **undated** (no deadline)

## 4. Ranking

Sort eligible tasks by, in order:

1. band (above)
2. `effectiveDue` ascending (nearest deadline wins regardless of category)
3. category rank (Schoolwork > Internships > Security > else), the stated tie-break
4. `priority` descending, then `rescheduleCount` ascending, then title, then id (stable, so the same snapshot always gives the same order)

Undated tasks skip step 2 and are ordered by category rank, then priority.

`current` = first eligible task. `queue` = next N (default 5).

## 5. How each action changes state

| Action                          | Effect on overrides            | Effect on ranking                                                                                                                                                                                                                            | Ends when                              |
| ------------------------------- | ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| **Pin**                         | add pin with `forDate = today` | moves to band 1. Several pins order by `pinnedAt`. The why-line adds "N overdue items waiting" if escalated items exist, so a pin never hides a missed hard deadline                                                                         | local midnight, or task done           |
| **Snooze** (until T)            | add snooze                     | removed from `eligible`. **A hard deadline that passes before T voids the snooze** (escalation beats snooze). Soft items just come back at T                                                                                                 | T, or the deadline passes              |
| **Skip** ("not this one")       | add skip for today             | removed from `eligible` for today, then **reflows** into its normal place tomorrow. No counter, no "skipped N times" shown. If it is the only eligible hard item due within 24h, it stays and the why-line says so                           | local midnight                         |
| **Low-energy mode on**          | `mode.lowEnergy = true`        | hard items due within `lowEnergyUrgentHours` (default 24) keep their place at the top. After those, tasks are ordered by shortest `minutes` first, then normal order. Pins still win | Morgan turns it off, or midnight       |
| **Task completed in QuickToDo** | none                           | task leaves the snapshot, next one becomes `current`                                                                                                                                                                                         | n/a                                    |
| **Missed hard deadline**        | none                           | auto band 2 (escalated), no quiet skipping                                                                                                                                                                                                   | task done or due date moved in the app |
| **Missed soft item**            | none                           | `effectiveDue` becomes today, so it reflows into the queue with no overdue label and no count                                                                                                                                                | n/a                                    |

Skip and snooze only hide a task from `current` and `queue`. They never change its due date, so QuickToDo is not touched.

## 6. Time model

Inputs: `minutes` per task, `commitments.json` (list of `{start, end, label}` for classes and work), and `config.workday` (09:00 to 24:00 since 2026-11-06: Morgan counts free time until midnight; "24:00" means end of day).

Output, per today:

    dayLoad: { freeMinutes, plannedMinutes, ratio, level: "light" | "normal" | "heavy" }

- `freeMinutes` = workday window minus commitments, minus the time already past.
- `plannedMinutes` = sum of `minutes` for tasks that are hard and due today or earlier, plus pinned.
- `level` thresholds live in config. Phase 7 reads `dayLoad` to size breaks; Phase 4 only computes and tests it.

## 7. Output (`recommendation.json`)

    {
      "generatedAt": "...",
      "snapshot": { "generatedAt": "...", "ageHours": 1.2, "stale": false },
      "mode": { "lowEnergy": false },
      "current": {
        "taskId": "...", "title": "...", "list": "...", "category": "...",
        "band": "dated", "dueDate": "...", "minutes": 45,
        "why": "Due tomorrow 23:59, ranked above Internships (Schoolwork wins ties).",
        "resources": "<task notes, passed through unchanged>"
      },
      "queue": [ { same fields, shorter } ],
      "categories": [ { "name": "Schoolwork", "open": 12, "escalated": 0, "dueToday": 1 } ],
      "dayLoad": { ... },
      "activeOverrides": { "pins": 0, "snoozes": 1, "skips": 0 },
      "empty": false
    }

"Why this?" is built from fixed templates over the same fields used to rank (band, due distance, category tie-break, pin/escalation notes). Same input, same sentence. No model.

## 8. Edge cases the tests will cover

- Empty snapshot, or everything snoozed/skipped: `current = null`, `empty = true`, with a reason.
- Two tasks, same due time, different categories: category rank breaks the tie.
- Missed hard deadline outranks a task due sooner in the future.
- Missed soft task shows no overdue wording.
- Snooze on a hard task whose deadline passes mid-snooze is voided.
- Skip expires at midnight; pin expires at midnight.
- Blocked task (open dependency) is never `current`.
- Stale or missing snapshot: ranks what it has, flags `stale`; a missing/corrupt file leaves the last good `recommendation.json` and reports the error.
- Same input twice gives byte-identical output.

## 9. Decisions I made that you may want to change

1. **Overrides live in the engine's own file, not in QuickToDo.** Your CLAUDE.md earlier suggested deep links for snooze/pin. That would need new QuickToDo fields and app code. The overlay keeps the app untouched; the cost is that snooze/pin/skip don't show in the QuickToDo UI.
2. **"Hard deadline" = Schoolwork or Internships with a due date.** Security Projects and Personal are always soft (reflow, no guilt). Change `hard` in config to alter this.
3. **Snapshot goes to the app container**, not into `priority-brain/`, so the sandboxed app needs no new write permission (it is read-only for user-selected files today).
4. **Fixed commitments come from a separate `commitments.json`** exported from the planner calendar files, not from the snapshot. QuickToDo's own calendar import (listed as "coming next") could replace it later.
5. **Minutes are kept simple (Morgan, 2026-11-05).** Use `estimatedMinutes` when set; otherwise a rough flat guess per category from `config.json`. No history learning, no title-keyword rules, no `history` list in the snapshot.

## Phase 11: commitments export (2026-11-06)

`importers/build_commitments.py` writes `engine/inputs/commitments.json` (`[{start, end, label}]`, yesterday to +21 days) from (1) timed events in each active course's `*-schedule.ics` (Network Security, Cloud Computing; folders listed in `COURSE_FOLDERS`; "due at" events with start == end are skipped) and (2) the optional `importers/work_schedule.json` (weekly `days` or one-off `dates`, `start`, `end`, `label`). Refreshed by the hourly drop launchd job (`build_drop.py` calls it). Refuses to overwrite when no calendars are found. Checked live: today's 2-hour mid-term cut free time 573 to 453 min and moved the day from light to normal.
