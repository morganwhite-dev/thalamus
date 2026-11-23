# Stage reporting (backend for the loading bar), 2026-11-05

Goal: the dashboard's loading bar shows the router's real stage and a percentage that comes from real progress, not elapsed time alone. Backend only; no UI change in this step.

Shape: `Router` gets an optional `on_stage` callback (default none, so every existing caller and test is unchanged). It calls `on_stage({"id", "label", "lo", "hi"})` when a stage starts. `command.py` sets the callback to store the stage on the job (`job["stage"]`, plus `job["stageAt"]`). `/api/state` and `/api/command/<id>` already return jobs, so the stage reaches the page with no server change.

| Thing         | Owner                                                                                                                 | Access                 |
| ------------- | --------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| current stage | router (emits) -> job record in `command/state`                                                                       | read only for the page |
| percentage    | page: starts at `lo`, eases toward `hi`, never passes `hi` until the next stage starts; 100% only when status is done | page computes          |

Stages (lo -> hi percent)

- `classify` 5 -> 20 "Reading the task" (only when the router classifies)
- `run` 25 -> 80 "Free model 2 of 3" / "Haiku" / "Sonnet (effort high)"; free attempts split 25..80 evenly, a retry or escalation starts at its own band
- `check` 85 -> 95 "Checking the answer"
- `audit` 95 -> 98 "Second opinion" (only when the Haiku audit samples this answer)
- done -> job status `done`, 100%

Rules: a stage callback that raises must never break a task (swallowed, logged nowhere else). Stages never go backward. Step 0 (engine answers) emits nothing and finishes at once. Failures keep the last stage so the bar can stop where it failed.

Failure states: no callback = no stage, the page falls back to the elapsed-time estimate it uses today.
