# Phase 7 state model: Work blocks and the dynamic break loop

Status: built 2026-11-05 (Sonnet 5.5). Code: `blocks/blocks.py` (pure), wired into `dashboard/server.py`, `push/push_logic.py`, `push/pusher.py`.

## 0. Shape

A small state machine, one pure function, no model calls:

    advance(state, action, ctx, config, now) -> new_state     (raises ValueError on an illegal action)
    tick(state, ctx, now)                                      -> new_state  (time and task-completion driven)

`ctx` = the engine's recommendation + the QuickToDo snapshot tasks. Nothing here writes to QuickToDo. Marking a task done stays in the app.

## 1. Phases

    idle --start_work--> starting --(countdown ends / begin_now)--> work --take_break--> break --(timer ends / end_break)--> checkin --checkin--> idle (next block proposed)
                           |  \--skip_break--> idle
                           |--extend--> work (endsAt + N)
                           |--cancel--> idle

- **starting** (revised 2026-11-05): a 3-2-1 before the clock starts (`startCountdownSeconds`, default 3; a `countdown` argument overrides it, 0 begins at once; max 1800). The work clock starts when it ends. `begin_now` skips it, `cancel` abandons it. If the task leaves the snapshot meanwhile the block is cancelled (never on an unreadable snapshot). The pusher sees nothing during it. If the server was off past the end, the block begins and is immediately marked over.
- **work shows elapsed time**: `view().elapsedSeconds` counts up from the clock start and keeps counting past the planned end until you act. The planned end still drives the stop text. `work_end` events record `workedSeconds`.
- **work**: a timed block on one task. Length = the task's minutes, clamped to `blockMinMinutes`..`blockMaxMinutes` (a long task is several blocks).
- **work is "over"** when `now >= endsAt` or the task has left the snapshot (done in QuickToDo). `tick` stamps `overAt` and `overReason` (`timer` | `task-done`). The dashboard then offers: Take a break / Keep going (+15) / Skip break.
- **break**: time-boxed. Length from day load (section 2). Carries a suggestion from the Personal list (section 3). Ends by timer or "End break".
- **checkin**: break is over, waiting for "Did you do something for yourself?" (Yes / No / Not now). Answered in the dashboard only.
- **idle**: after the check-in (or skip), the view carries `next`: the top recommendation that is not Personal, with a Start button. This is the routing step ("let's apply to 10 jobs").

## 2. Break length

`config.json` `breakMinutes` by the engine's `dayLoad.level`: light 45, normal 25, heavy 10. A lighter day earns a longer break; a loaded day gets a short one. Low-energy mode does not change it. Edit the numbers in config; thresholds live in the engine config.

## 3. Break suggestion (real item from the Personal list)

Candidates: open snapshot tasks whose category is Personal (engine `category_for`). Order: skip any answered "yes" today; prefer ones that fit the break (`estimatedMinutes` unknown or <= break length); then least recently suggested; then title. Deterministic. Empty list: the break shows "Nothing on your Personal list yet. Add things you want to do in QuickToDo." and the check-in still works. `suggested` in the state records when each item was offered and whether Morgan did it.

## 4. Files and owners

| File                         | Owner                                              | Contents                                                                      |
| ---------------------------- | -------------------------------------------------- | ----------------------------------------------------------------------------- |
| `blocks/state/blocks.json`   | blocks module (atomic writes, server holds a lock) | `version`, `phase`, the active block/break fields, `suggested`, `lastCheckin` |
| `blocks/state/history.jsonl` | blocks module (append only)                        | one line per transition, for the Phase 8 mission log and the weekly summary   |
| `engine/config.json`         | Morgan                                             | `blockMinMinutes`, `blockMaxMinutes`, `extendMinutes`, `breakMinutes`         |

The pusher reads `blocks.json` through `blocks.push_view(state)` and gets `None` (idle) or `{id, kind: work|break, title, endsAt, breakMinutes?}`. That replaces the old hand-written `push/state/block.json`.

## 5. Pings (one-way, presence rule applies)

- Work block ends: existing `stop` ping: "Time's up on X. Take a N-minute break, then open the brain."
- Break ends: new `breakend` ping: "Break's over. Open the brain." It respects presence and quiet hours. **It bypasses the one-per-hour cap** (otherwise a stop ping 30 minutes earlier would swallow the one nudge that brings her back), still dedupes on the block id, and counts toward the cap for the next start ping.
- If the dashboard is open and visible, no text is sent; the page shows the prompt instead.
- The cloud pusher gets `block` through the same `queue.json`, so a break ending while the Mac is off still pings.

## 6. Failure handling

- Corrupt or unreadable `blocks.json`: moved to `blocks.json.bad`, state resets to idle, the view carries `error` and the dashboard shows a banner. Nothing is silently dropped.
- An action illegal for the phase returns 400 with the reason; the state is unchanged.
- A work task that disappears is treated as done (no error). A break suggestion that disappears is dropped at check-in.
- Overnight: a block or break still open from a previous day is closed by `tick` (to idle, logged `expired`), so nothing carries over as a guilt pile.

## 7. Tests (`blocks/tests/test_blocks.py`)

Fake clock. Start picks the top non-Personal task; length clamped; timer end marks over; task disappearing marks over; extend; break length per day level; Personal item chosen and rotated; fits-the-break preference; empty Personal list; break timer end moves to checkin; check-in answers; idle `next` skips Personal; illegal actions rejected; expiry across days; corrupt file recovery; push view projection; server endpoints; `decide()` breakend rules (cap bypass, presence, quiet hours, dedupe).
