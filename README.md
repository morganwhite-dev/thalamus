# Thalamus

A personal "mission control" for a student life: one screen that answers **what should I be doing right now?**
across schoolwork, internship applications, security projects and the fun stuff, and that never makes you feel
behind.

It is built for one person (me) on one Mac, so it leans on my own tools (a SwiftUI task app called QuickToDo,
OpenCode, ntfy). It is public so others can read how it works and borrow pieces, not as a polished product.

## What it does

- **Priority engine** (`engine/`): plain, deterministic code that ranks open tasks by nearest deadline, then by
  category. Snooze, skip, pin, low-energy days, and a "why this?" line for every pick. No model calls.
- **Hologram dashboard** (`dashboard/`): a point-cloud brain with one dial per category, served on localhost.
  A **chat drawer** handles everything else in plain sentences: "mark the chapter 7 reading done for cloud",
  "what's due friday", "remind me to email Dr. Lee tomorrow at 3".
- **Chat agent** (`command/agent.py`): instant rules first; then sentences it has learned; then a free model with
  tools; then Claude Haiku with the same tools. Every action is checked in code before it runs, ambiguous tasks
  are asked about (never guessed), and everything can be undone for two minutes.
- **Model router** (`router/`): sends bigger asks to the cheapest model that can do them, with a rubric
  classifier, output validation and a usage counter.
- **Work blocks and breaks** (`blocks/`): start a timed block, take a break sized to how loaded the day is, get a
  check-in afterwards.
- **Push** (`push/`): one-way ntfy nudges when you are away from the dashboard, with an hourly cap, quiet hours and
  a GitHub Actions copy that keeps working when the laptop is off.
- **Imports** (`importers/`, `launcher/`): course deadlines, tracker files and class times flow into the task app
  without manual steps.
- **Application prep** (`prep/`): tailors a one-page resume from a fixed set of verified facts. It never
  invents anything and never submits an application.
- **Play** (`play/`): side projects, parked ideas and "where I left off" lines, with no deadlines and no guilt.

## Running it (macOS)

Python 3.11+ with the standard library only (`python-docx` for `prep/`).

```sh
python3 dashboard/server.py            # http://127.0.0.1:8765/
python3 -m unittest discover -s dashboard/tests
python3 -m unittest discover -s command/tests
```

The dashboard reads a snapshot written by the task app. Without it, the engine has nothing to rank.
`push/config.example.json` shows the push settings; copy it to `push/config.json` with your own ntfy topic
(keep that file private: anyone with the topic can read and send your pings).

The dashboard page `dashboard/index.html` is generated: edit `dashboard/holo/*` and run
`python3 dashboard/skin/build.py`.

## Design notes

Each part has a `STATE_MODEL*.md` next to its code, written before the code: what it stores, what can happen, and
the decisions behind it. Start with `command/STATE_MODEL_AGENT.md` (the chat) and `engine/STATE_MODEL.md` (the
ranking).

## Privacy

Everything runs on localhost. The server refuses non-local hosts and requests without its own header. Free models
are cloud-hosted, so anything sent to them leaves the machine; the chat sends them the open task list with each
message.
