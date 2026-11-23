# Phase 12 state model: Play (backend)

Status: backend built 2026-11-06 (Sonnet 5.5). UI not built (needs a mockup and Morgan's OK first). Code: `play/play.py`, `engine/config.json`, `engine/brain_engine.py`, `blocks/blocks.py`, `dashboard/server.py`.

## Decisions (Morgan, 2026-11-06)
- The cluster is called **Play** (not "Playground"). It holds fun and her own projects: games, golf, coding side projects (e.g. the network traffic analyzer). QuickToDo lists: `Play` and `Side Projects` (she creates them).
- **Personal is not Play.** Personal is life errands (send an email, appointments). It stays an ordinary soft category (rank 4, after Security, no hard deadline, reflows with no guilt pile) and is ranked and startable like any task.
- Play is **offers only**: never in "Do this now", never in the queue, never pinned, never escalated, never snoozed or skipped (nothing to skip). The engine config marks it `"play": true`; code checks the flag, not the name.

## Data
- Tasks: read from the QuickToDo snapshot (lists above). Nothing written to QuickToDo.
- `play/state/play.json` (brain-side): `parking` = `[{id, text, at}]` (max 50, one line of 140 chars); `leftOff` = `{taskId: {text, at}}` (one line per Play task).

## Behaviour
- Breaks pull from Play only (`blocks.pick_break_item`); an empty Play list shows the "add things" note.
- **Offer** (`play.offer`): one optional "Want a N-minute go at X?" in `state.play.offer`, only when no block is running, the day load is light, nothing is escalated or pinned, and no queued item is due within 24 h. Picks the Play task untouched longest; shows its left-off line. No ping, no log of ignored offers.
- Ignoring anything in Play creates nothing: no overdue wording, no counts of misses.

## API (dashboard server, same security checks as other POSTs)
- `GET /api/state` adds `play: {items:[{taskId,title,list,leftOff}], parking, offer}`.
- `POST /api/play` `{action: park|unpark|leftoff, text|id|taskId}` returns the full state.

## Not done yet
- UI: a Play neuron (the delivered design has four neurons; Personal is now errands, so Play is a fifth or replaces the fourth), parking-lot input, left-off line, offer card. Show Morgan a mockup first.
- Offers inside the break panel (UI only; the break already picks a Play item).
- User-defined clusters beyond this config flag stay parked.

## Verify
`python3 -m unittest discover -s play/tests` (5), engine (29), blocks (22), dashboard (30). Live: restarted the dashboard job; `/api/state` shows Play as its own category with 0 items and `play.offer` null.

## 12c: offer rules (2026-11-06)
`engine/config.json` `play.kinds`: game (min 90 min; list `Games`, tag `#game`, keywords) and project (min 60; list `Side Projects`, tag `#project`). Effective minutes = estimate (else 30) raised to the kind minimum. An offer shows only when that fits the free time left today (`freeMinutes - plannedMinutes`). Breaks skip any item whose kind minimum is longer than the break, so games and projects come from light-day offers, short things (golf range, a walk) from breaks. The Play category now reads lists `Play`, `Games` and `Side Projects`.

Update 2026-11-06: Morgan picks the game herself, so no `Games` list is needed. `play.generic` in `engine/config.json` adds a stand-in offer, "Want a game session (about 90 minutes)? Your pick of game, totally optional.", used when she has no game item; it needs 90 free minutes and rotates with real items (untouched first, real beats generic on a tie).

Update 2026-11-06 (Morgan): **golf is a built-in offer too.** Kind `golf` in `engine/config.json`: needs 4 h (240 min) of free time left today, only before 17:00 (daylight), and it does not need a light day (`anyDay`). Wording: "Want to get out for some golf? You have a free stretch and it's still daylight. Totally optional." A real Play item with "golf" in its title counts as the golf kind. Games and projects still need a light day. All offers stay blocked while anything is overdue, pinned or due within 24 h. Play holds her non-security, non-school side projects (the "overzealous" ones) in the `Side Projects` list; job-search projects live in Security Projects.

## 12h: automatic left-off lines (2026-11-07, Sonnet 5.5)
Goal: a Play item shows a "where I left off" line without Morgan typing one. Read-only, no model, nothing written to QuickToDo or to the projects.
- **Order of precedence:** a typed line (`play.json` `leftOff`) always wins; otherwise the automatic line; otherwise none.
- **Source 1, code projects (git):** a `path: <folder>` line in the task notes (`~` allowed) names the project. The brain runs read-only git there (`log -1`, `status --porcelain`) with a 5 s timeout and no optional locks, and writes e.g. `Last: "add parser" 2 days ago, 3 files uncommitted`. A folder that is missing or not a git repo gives no line (never an error shown, never a guess). A clean tree says "all committed".
- **Source 2, any item:** if a block on a task with that title appears in `blocks/state/history.jsonl` (`work_start`), `Last worked 3 days ago`. Used only when git gives nothing.
- **Cache:** results are cached 10 minutes per task (the page polls `/api/state`), so git runs rarely.
- **Shown:** `play.items[].leftOff` and `play.offer.leftOff` carry the line; `leftOffAuto: true` marks an automatic one so the UI can show it softer. Parking lot and left-off stay Play-only.
- **Not built (UI, later):** the one-tap line box when a Play block ends, and an optional free-model one-liner from the recent diff.
- Code: `play/leftoff_auto.py`, wired in `play.view` / `play.offer` via an `autos` map from `dashboard/server.py`. Tests: `play/tests/test_leftoff_auto.py`.

## 12i: projects and visibility (2026-11-07, Morgan's correction)
- **Golf and games are suggestions only.** They are never listed in the Play neuron and never get a left-off line. They stay as the if/else offers and break picks. Only project-kind items are visible (QuickToDo `Side Projects` items and the brain's own projects below).
- **Idea to project to started:** a parked idea can be turned into a project (`promote`), a project can be added directly (`addproject`), started (`startproject`), and then keeps a one-line "where I left off" (typed, via `leftoff`, or the one-tap "Worked on it today"). `dropproject` removes one (finished or abandoned, no guilt, nothing is kept).
- **Store (`play/state/play.json`):** `projects` = `[{id: "proj-...", title, state: "idea"|"started", at, startedAt, touchedAt}]` (max 30); `offered` = `{id: at}` (rotation only, never displayed; an accepted offer no longer writes a visible left-off line).
- **View:** `play.items` = project-kind QuickToDo tasks only; `play.projects` = the brain's projects (with `leftOff`, `leftOffAuto`); `play.count` = visible projects, used for the neuron number.
- **Offers:** a started project is an offer candidate (kind project, 60 min, shows its left-off line). Game and golf offers carry no left-off text.
- Tests: `play/tests/test_projects.py`.

## 12j: project status from the folder, by command or automatic (2026-11-07, Morgan)
**Logic.** One function, `project_status.status_line(folder)`, turns a project folder into one short plain line (max 140 chars). It runs two ways:
- **Automatic:** it is the source of the automatic left-off line (replaces the git-only one from 12h). Cached 10 minutes.
- **On command (no model, no cost):** typing "update the status of X", "status of X project" or "where did I leave off on X" in the command box finds the project, runs the same function, saves the line as that project's left-off line and shows it as the answer. A typed line by hand still overrides, until the next update command.

**Which folder.** (1) `path: <folder>` in the task notes or the brain project's `path`; else (2) a unique folder under `play.projectRoots` (engine config) whose name matches the title ignoring case, spaces and punctuation ("Network traffic analyzer" matches `NetworkTrafficAnalyzer`). No folder, a plain file, or an ambiguous match gives "Couldn't find a folder for X. Add a line `path: <folder>` to its notes." (never a guess).

**Which projects.** All of them: the brain's own projects, QuickToDo `Side Projects` items, and Security Projects tasks (the whole job-search portfolio set).

**Plain wording** (one line; the label comes from the newest activity, a commit or an edited file):
- Active (activity within 3 days), Slowing (within 14), Stale (older).
- Git repo with commits: `Active · last commit 2 days ago ("add parser") · 3 files uncommitted` (or `all committed`).
- Folder with no git, or a repo with no commits: `Slowing · no git · last edit 5 days ago (parser.py) · 2 files changed this week`.
- Hidden files and dependency/cache folders (`.git`, `node_modules`, `__pycache__`, `.venv`) are ignored; the walk stops at 20000 files.

**Not built yet:** showing the line on Security Projects in the Thalamus UI (it is saved and shown in the command answer; the Play neuron shows it for projects). A free-model summary of the diff stays out: a commit message is already plain wording and costs nothing.
Code: `play/project_status.py`, hook in `command/command.py` `submit`, `play.projectRoots` in `engine/config.json`. Tests: `play/tests/test_project_status.py`, `command/tests`.

## 12k: plain "where you left off" wording and continuity (2026-11-07, Morgan)
**Wording replaces the 12j format.** No git words, no Active/Slowing/Stale label; the age says how fresh it is. Built by plain code from the last 5 commit messages (no model):
- Phase: the first "phase/step/stage/milestone/week/sprint N" found, newest commit first; a range ("phases 0 to 12") counts as its end ("Phase 12").
- Activity from the newest message's first word: fix/bug/patch → "fixing bugs"; test → "writing tests"; refactor/clean/tidy/simplify → "cleaning up the code"; doc/readme → "writing docs"; init/setup/scaffold → "setting it up"; add/implement/build/create/feat/wire → "building"; update/improve/tweak/polish/rename → "improving". Then the rest of the message (cut at `:`/`(`, 40 chars) as the object.
- Shapes: `On Phase 12, building the playground · 2 days ago · unsaved work` / `Fixing bugs in the parser · 2 days ago` / `On Phase 12 · 23 h ago` (phase but no clear activity) / the cleaned message when nothing else parses. `unsaved work` appears only when files are uncommitted.
- No git: `Editing parser.py · 5 days ago · 2 files changed this week`.
- Not a repo with a tracker, unreadable folder, or no folder: same messages as 12j.

**Continuity: where the line shows.** `GET /api/state` now has `leftOff` = `{taskId: {text, auto}}` for Play items, the brain's projects, and every task in a focus category (Security Projects). Thalamus shows "Where you left off: ..." (a) in the "Do this now" card when the recommended task has one, and (b) in a project's detail inside its neuron (Security and Play). Nothing is shown when there is no line (no empty label). Typed lines still win over automatic ones.
Tests: `play/tests/test_project_status.py` (wording), `dashboard/tests` (state map).

## 12l: repeating items (daily and weekly goals), general (2026-11-09, Morgan)
Any item can repeat, in any cluster: "add tryhackme to playground. my goal is one practice lab a day" or "remind me to stretch every morning" or "review flashcards twice a week". No syntax to remember.
- **Capture (plain code):** a cadence phrase anywhere in the sentence makes the proposal a repeating item: `daily/every day/a day/every morning|evening|night`, `every <weekday>`, `weekdays`, `weekends`, `N times a week/once a week/weekly` (N spaced across the week: 2 = Mon+Thu, 3 = Mon+Wed+Fri). A time in the sentence ("at 4pm") sets the nudge time; otherwise morning 08:00, evening 18:00, night 20:00, else 17:00. A trailing sentence starting "my goal is", "the goal", "I want", "note" becomes the item's notes, not part of the title. "playground" means the Play list. A repeating item with no list defaults to Play. The confirm card says "Repeat this?" with the cadence and nudge time; Add stores it (it is not a QuickToDo task).
- **Store:** `play/state/play.json` `habits` = `[{id, title, notes, days[0-6], nudgeAt, cluster, at, doneDates[]}]` (max 10, last 60 done dates). Actions on `/api/play`: `addhabit`, `habitdone`, `habitundo`, `drophabit`. No streaks, no counts of misses.
- **View:** `play.habits[]` with `cadence`, `dueToday`, `doneToday`, `cluster`; shown first in the neuron of its cluster (Play, Schoolwork, Internships, Security, Personal) with "Did one today" / "Undo done" / "Stop repeating"; the Plain page lists them in the Play section.
- **Nudge:** ping type `habit` in `push/push_logic.py`: once per habit per day, only on its days, from its nudge time, if today's one is not done; skipped while the dashboard is watched, in quiet hours, or inside the hourly cap (retried later, not queued). Text: `<title>: want your one for today? <goal>. No pressure.` Works from the cloud copy too (habits go into `queue.json`; `habitSent` merges across Mac and cloud).
- Tests: `play/tests/test_habits.py`, `dashboard/tests/test_server.py` (habit through the API).

## 12m: text-only reminders (2026-11-09, Morgan)
"Remind me ..." with a time of day ("at 3pm", "in 30 minutes", "tomorrow at 9", "every morning") defaults to a **text reminder only**: nothing is added to QuickToDo or to any neuron. The confirm card has a checkbox "Text me only, don't add it to my list" (default on for these, off otherwise), so Morgan chooses per item. A date with no time ("remind me ... Friday") stays an ordinary task.
- **One-off:** `play.json` `reminders` = `[{id, text, at, created}]`; actions `addreminder`, `dropreminder`, `reminderdone`. Sent once at its time by `push_logic.decide` (type `reminder`), "Reminder: <text>." or "Reminder (set for 3:00 PM): <text>." when sent over 15 minutes late. Explicit requests, so presence, quiet hours and the hourly cap do not apply and they do not reset the cap. A sent reminder is removed from the store by the pusher (here or after the cloud copy sent it).
- **Repeating:** a habit with `textOnly: true`: a text at its time on its days, never shown as a node, no done-state, no cap or presence check.
- **Cloud:** reminders go into `queue.json` (`reminders`) and `reminderSent` merges across Mac and cloud like `habitSent`.
- **Ask in the box (plain code):** "what reminders do I have", "cancel reminder <words>" (`command/reminders_qa.py`).
- Tests: `command/tests/test_reminders.py`.

## 12n: natural wording and durations (2026-11-09, Morgan)
A repeat phrase alone makes a sentence a repeating item, with no trigger word: "do tryhack me for one hour a day", "practice scales for half an hour on weekdays", "study flashcards twice a week". "Do ..." with a repeat is a request, while "do you/i/we/it ..." is still a question. A length ("for one hour", "30 minutes", "half an hour") is stored as `minutes` on the habit, shown on the card, and used in the nudge: "<title>: want your hour for today? ... No pressure." A leading "do" is dropped from a repeating title; a one-off keeps it ("Do the dishes").

## Phase 22: Cyber Academy progress and retired Security tasks (2026-11-13, Morgan)
Two gaps: (1) the importer only adds, so tasks that left the Security tracker stay in Thalamus; (2) Cyber Academy lesson and quiz progress lives only in its own SQLite file.
- **Academy progress (built, brain side only, read-only):** `play/academy.py` opens `~/Desktop/Projects/Cyber-Academy/data/academy.sqlite3` read-only and reads `content/curriculum.json`. A Security task whose title says "Cyber Academy Tier N" gets one `leftOff` line from that tier: "Tier 1: 1 of 2 modules done, permissions in progress, last quiz 7/10 · 2 h ago". Order: typed line, then Academy, then git/history. Unreadable Academy data gives no line, never an error. Wired in `dashboard/server.py` (`leftOff`). Tests: `play/tests/test_academy.py`.
- **Retiring stale tasks (BUILT 2026-11-13, see CLAUDE.md Phase 22; also sweeps older tracker-made tasks the manifest forgot):** in `AutoImport.swift` `importRows`, for the brain's own drop files only (`security_assignments.json`, `internships_assignments.json`; never the school files), a row recorded in the manifest but no longer in the file is moved to Trash when its task is open, its due date is unchanged, it has no progress and was never started. Anything she touched is left alone and logged. Trash is reversible (`deletedAt`). Also store a notes hash per row so tracker notes (for example "on bandit13") update in place while she has not edited them. Backup the store first; Swift tests for retire, left-alone and notes-update.
