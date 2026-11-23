# Phase 5 state model: Plain dashboard

Shape: `server.py` (Python stdlib, bound to 127.0.0.1) + `index.html` (no framework, no animation).
The dashboard owns NO state. Everything shown comes from `engine/brain.py` `run()`; every control calls the same engine code the CLI uses.

| Thing                            | Source / owner                  | Dashboard access               |
| -------------------------------- | ------------------------------- | ------------------------------ |
| tasks, due dates                 | QuickToDo snapshot (via engine) | read only                      |
| ranking, why-line                | engine `recommend()`            | read only                      |
| pin / snooze / skip / low-energy | engine `state/overrides.json`   | via POST /api/action -> engine |
| done / edit task                 | QuickToDo app                   | none (not here)                |

Endpoints

- `GET /` page. `GET /api/state` recomputes and returns the recommendation (+ `serverTime`, `error` if the snapshot was unreadable and the last good output is shown).
- `POST /api/action` body `{action: pin|unpin|skip|unskip|snooze|lowenergy, taskId?, hours?, state?}`; returns fresh state.

Page states

- loading -> ok | empty (nothing eligible, shows engine reason) | error (server unreachable, or snapshot unreadable with last good data shown and flagged).
- Sync stamp: "Snapshot synced HH:MM (N min ago)". Over `staleAfterHours` -> warning banner. Page also shows "Refreshed" time; auto-refresh every 30 s and on tab focus.
- Per task controls: Pin (toggles Unpin when pinned), Snooze (1h / 3h / until tomorrow 9:00 menu), Skip. Global: low-energy toggle.
- Controls disable while a request is in flight; failures show a message, never silent.

## Phase 8 additions: Thalamus skin (wiring plan, written 2026-11-06, nothing built yet)

Goal: the delivered Claude Design look (`Ui Designs/thalamus-final/Main.dc.html`) running on the real `/api/state`, with every backend feature reachable. No engine, blocks, router or command logic changes. The skin owns no state either: all state is the server's; the page keeps only UI state (which neuron is open, which task is expanded, loading-line jargon index).

### Facts found while reading the design (they shape the approach)

- The `.dc.html` files are templates for a design-host runtime: `<x-dc>`, `<sc-if>`, `<sc-for>`, `{{...}}`, a `DCLogic` base class, all from `./support.js`, which is NOT in the export. They cannot run as-is. The brain/neuron/fiber drawing code (`Eng`, `Brain3D`, WebGL + canvas) is plain JS and reusable unchanged; the template and the `Component` class (state, `renderVals`, mock jobs) must be rewritten as plain DOM code.
- The design runs on mock data (`ITEMS0`, `SEED_LOG`, `CATMETA`, a fake job simulator with `STAGES`, a regex `routeCat`). All of that is replaced by `/api/state`.
- `server.py` serves only `/` (index.html). So the skin ships **inside `dashboard/index.html`**, with the existing plain UI kept as the Plain skin and a one-click toggle between the two (choice remembered in `localStorage`). No server change needed. Fonts load from Google Fonts with system fallbacks.

### Skin state model (UI-only)

| UI state      | Values                              | Notes                                                                                           |
| ------------- | ----------------------------------- | ----------------------------------------------------------------------------------------------- |
| `skin`        | `thalamus` or `plain`               | toggle, saved in `localStorage`, default thalamus; `?plain` forces plain                        |
| `openCluster` | null or a category id               | neuron expanded into branches; Esc or backdrop closes                                           |
| `openTask`    | null or taskId                      | task expanded in place; Esc steps back one level                                                |
| `lowPower`    | bool                                | auto when `prefers-reduced-motion`, manual switch otherwise; also pauses when the tab is hidden |
| `cmdUi`       | idle, queued, running, done, failed | derived from `state.command.jobs[0]`, never invented                                            |

Brain mood is derived from real data: `missed` if any category has `escalated > 0`, `busy` if several are due today, else `calm`.

### Data mapping: design element to `/api/state`

| Design element                                          | Source                                                                                                                                                     |
| ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "Do this now" title, tag, due, est, why, resources      | `current` (`title`, `category`, `dueDate`, `minutes`, `why`, `resources`)                                                                                  |
| Cluster count and urgency glow                          | `categories[]` (`open`, `escalated`, `dueToday`)                                                                                                           |
| Neuron branches (tasks of a cluster)                    | `queue[]` + `current`, grouped by `category`; the list is the engine's own top items, so an expanded cluster shows only what the state carries (see gap 2) |
| Mission log lines                                       | `missionLog[]` (`at`, `kind`, `text`); only real events, the last line is the current recommendation with the blinking cursor                              |
| Sync stamp, stale warning                               | `snapshot.generatedAt`, `snapshot.stale`, `error`                                                                                                          |
| Loading bar, jargon, status line                        | `command.jobs[0]` (`status`, `stage.label/lo/hi`, `stageAt`, `startedAt`), same easing as the plain page                                                   |
| Answer, routing line, usage warnings, saved-to note     | `jobs[0].answer`, `routing`, `warnings`, `savedTo`                                                                                                         |
| Saved results under a cluster                           | `command.results[category]`                                                                                                                                |
| Work block, 3-2-1, elapsed, break, check-in, next block | `blocks` (`phase`, `block`, `over`, `next`, `elapsedSeconds`, `breakPreview`, `lastCheckin`)                                                               |
| Day load                                                | `dayLoad`; overrides `activeOverrides`                                                                                                                     |

### Actions: design button to existing endpoint

| Button        | Call                                                                                                                                                    |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Pin / Unpin   | POST `/api/action` `{action: pin or unpin, taskId}`                                                                                                     |
| Snooze        | POST `/api/action` `{action: snooze, taskId, hours: 1 or 3, or until: "tomorrow"}` (design has one button; becomes a small 1 h / 3 h / tomorrow choice) |
| Not this one  | POST `/api/action` `{action: skip, taskId}`                                                                                                             |
| Low-energy    | POST `/api/action` `{action: lowenergy, state: on or off}`                                                                                              |
| Start         | POST `/api/block` `{action: start_work, taskId}`; then begin_now, extend, cancel, take_break, end_break, skip_break, checkin as in the plain page       |
| Send / Stuck  | POST `/api/command` `{text, taskId, followUp}` or `{kind: "stuck", taskId}`; poll `/api/command/<id>` every 2 s                                         |
| Presence beat | POST `/api/presence` every 30 s while visible (keep exactly as today)                                                                                   |

### Feature checklist (every item must be reachable in the Thalamus skin before the phase is ticked)

1. Recommendation with "Why this?" line; escalated and pinned tags
2. Pin, snooze (1 h / 3 h / tomorrow), "Not this one", low-energy mode
3. Start block with 3-2-1 countdown (Begin now, Cancel), elapsed timer, planned end, +15, Cancel
4. Block over (timer or task done): Take break, Keep going, Skip break
5. Break with Personal-list suggestion, sized note, End break; empty-Personal-list message
6. Check-in "did you do something for yourself?" (Yes / No / Not now); next block proposed with Start
7. Command box: send, follow-up toggle, save-to-task choice, loading bar with real stage, routing line, usage warnings, failure state with retry/dismiss
8. Stuck button (five-minute first step), saved to its task
9. Saved results shown under their cluster
10. Mission log (real events), ending on the current recommendation
11. Last-synced stamp, stale banner, unreadable-snapshot banner, import/command error banners
12. Per-cluster status (open, missed, due today), day-load line, active pins/snoozes/skips
13. Plain toggle; empty state "all quiet up here"; phone layout; low-power and reduced-motion
14. Presence heartbeat

### Gaps found (the design shows these, the backend does not support them; each needs Morgan's call, none is built here)

1. **Done** (design: check button on the recommendation and every task). The backend cannot complete a QuickToDo task yet (see Future ideas: "Mark done in Thalamus completes it in QuickToDo"). Until that exists, the button is hidden or replaced by "Done in QuickToDo", and the page's note says tasks leave when completed there.
2. **Per-cluster task lists.** `/api/state` carries `current`, the top 5 `queue` and `command.tasks` (id, title, category only, all 66 open tasks). An expanded neuron wants all of its cluster's tasks with due dates and why-lines. Options: show the queue items plus titles from `command.tasks` (no dates), or add the fields to the state (a small backend change, needs OK).
3. **Saved notes textarea** (task detail). No backend store for free notes exists. Options: drop it, or reuse `command/state/results.json` (needs a small backend addition).
4. **Usage counter and warnings** (5-hour, today, week; plan-usage line). The router tracks them but `/api/state` does not expose them, so only per-job warnings show. Needs a state field to display the totals.
5. **Command adds "+1 item" to a sector** in the design mock. The real command box does not create tasks; answers and saved results land under the matching task. The skin shows the real outcome ("saved under X"), and the burst animation plays on the cluster the result was saved to.
6. **Playground** and user-created clusters stay parked; the design has four clusters and the Personal one will show 0 until Morgan adds items.

### Build order (after Morgan approves this plan)

1. Port: extract CSS, markup, `Eng`, `Brain3D` into `index.html` under a `thalamus` skin wrapper; replace the runtime glue with a small `render(state)`; keep the plain skin and add the toggle. Confirm the missing `support.js` is not needed by the extracted code.
2. Read-only wiring first (recommendation, clusters, log, banners), checked against the real state in the browser pane.
3. Controls wiring (pin, snooze, skip, low-energy, blocks, break, check-in).
4. Command box wiring (send, stage bar, failure, Stuck, saved results).
5. Decide the gaps above with Morgan, wire what is approved.
6. Check desktop and phone width, Plain toggle, low-power/reduced-motion, no console errors; tick the checklist; show Morgan before calling it done. Server and tests: existing 16 dashboard tests must still pass.

Safety: bind 127.0.0.1 only; POST requires Host in {127.0.0.1:port, localhost:port} and header `X-Brain: 1` (blocks other web pages and DNS rebinding). No file paths or secrets leave the server.
