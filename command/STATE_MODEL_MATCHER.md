# State model: meaning matcher (local Ollama embeddings)

Status: matcher core built (`command/matcher.py`, `command/matcher_examples.py`), not wired into the box yet. Written 2026-11-22. Morgan approved the layer. Build on top of `feat/chat-phrasebook` once its fix round passes review.

## Where it sits

1. Plain-code rules (`intent`, `typed`, `capture`, `schedule_qa`, `lookup`, `park`, ...). If they are sure, they answer, as today.
2. **Meaning matcher (this phase).** It decides which kind of request the sentence is. It never decides the details.
3. Free translator model with the context card (`STATE_MODEL_PARSER.md`).
4. General questions go to the router, as today.

## How it works

- **Model:** `nomic-embed-text` on Ollama, with the prefix `classification: `, called with stdlib `urllib` on `http://127.0.0.1:11434/api/embed`. See "Tuning result" below.
  - The first spot test (10 sentences) favoured `all-minilm`, but the held-out set of 307 sentences reversed that (82% vs 77%). `all-minilm` stays as a config option.
- **Examples:** the phrase tables in `command/tests/phrasings.py` and `typed_cases.py` become the example set, one label per intent.
  - Labels: now, schedule, capture, lookup, park, project_status, action:<verb>, stuck, tiny, general.
  - The must-not-act and question lists are stored as their own labels (question, statement), so the matcher can recognise them too.
- **Cache:** example vectors are computed once and saved to `command/state/matcher-cache.json`, keyed by model plus a hash of the example tables. They rebuild automatically when the tables change. Each sentence costs one embed call (about 10 to 30 ms).
- **Decision:** k nearest examples (k = 5), scored per label.
  - It routes only when the top score is above a threshold AND beats the next label by a margin.
  - Both numbers live in `engine/config.json` under `matcher` and are tuned from a held-out test set, not guessed.
  - Anything below the threshold falls through to layer 3.
- **Details still come from code:** once the matcher says "snooze", `typed.parse_action` and its helpers read the time and the task. If they cannot find a safe target or time, the chat asks.
- **Safety:** an action found by the matcher (rather than by an exact rule) is never done silently.
  - The chat says it back in the first person and waits for a yes: "Snooze Read Chapter 5 for an hour?"
  - Questions and statements the matcher labels question or statement never act.
- **Log:** every sentence the matcher routed, plus every sentence that fell through, gets one line in `command/state/matcher-log.jsonl`: its length, a 12-character hash, the top labels with scores, and the outcome. **The text itself is never stored** (Morgan's rule: pasted text is never written to logs). New examples come from the translator's log and her real use, not from this file.

## Tuning result (2026-11-22, held-out set of 307 blind sentences, branch `test/matcher-eval`)

**Model.** Use `nomic-embed-text`, with the prefix `classification: `. It is right 82% of the time without any threshold, against 77% for `all-minilm`, and covers more at the same precision. Both take about 10 ms per sentence, so `all-minilm` is not the default after all.

**What the matcher may route.** Embeddings match the topic but miss *who* a sentence is about and whether it is a command. "my mom needs to buy a gift" scores 0.97 as `capture`, and "should i skip lab 7?" lands near `action`. No threshold makes those labels safe. So:
- **Routed by the matcher:** now, schedule, project, reminders, tiny, general. These are 95 to 100% precise at threshold 0.85 and margin 0.02. They only read, answer or chat, and never change data.
- **Never routed by the matcher:** action, capture, park, stuck, lookup and noact. These fall through to the free translator model, which can tell a command from a statement. It is still followed by the first-person confirmation.
  - lookup and stuck are excluded only because their recall is low. They can move to the routed list once more examples are added and the eval is re-run.
- The allowed list lives in config as `matcher.route_labels`, so it changes without code edits.

**Examples to add before wiring.** The suggested stuck, park, lookup, noact and capture sentences in the eval report, especially the "statement vs command" twins ("my mom needs to buy a gift" as noact next to "remind me to buy a gift for my mom" as capture).

**Re-run** `python3 command/matcher_eval.py` whenever the example tables change. After a week of real use, add her real logged sentences to the held-out set.

## Built and tuned (2026-11-22, `feat/matcher-core`)

- **Defaults** (`engine/config.json` key `matcher`, same in code): `nomic-embed-text`, `prefix` "classification: ", k 5, threshold 0.85, margin 0.02. The prefix is added to examples and queries alike, only when configured (`all-minilm` users set `"prefix": ""`). The cache key holds model, prefix and a hash of the examples.
- **Margin** = best label's score minus the nearest example of any other label (the same definition the eval measured).
- **`routable`:** `classify()` returns `{label, score, margin, routable, top}`. `routable` is true only when the label is in `matcher.route_labels` (now, schedule, project, reminders, tiny, general). Callers route only on `routable`.
- **Extra examples** live in `command/matcher_examples.py` (not in the phrase tables): 40 open factual questions (general), 25 statements about other people or plain facts (noact) with 25 matching commands (capture), and about 20 each of stuck, park and lookup in casual wording. None may appear in the held-out set.
- **Stuck vs action:** `typed_cases.ACTIONS["stuck"]` sentences are "I'm stuck" sentences. `load_examples` labels them `stuck`, not `action`, and adds them before the other action sentences so they win any duplicate.
- **Held-out result at 0.85 / 0.02, routable labels only:** 103 of 307 sentences routable, 2 wrong (old all-minilm at the same numbers: 35 routable, 0 wrong; at its old 0.5 / 0.05: 122 routable, 9 wrong). 0.88 gives 0 wrong but only 82 routable, so 0.85 stays.

## Hardening (2026-11-22, after the Codex review)

- **Routable is capped in code.** A hard-coded `SAFE` set (now, schedule, project, reminders, tiny, general) is intersected with `matcher.route_labels`. Config can narrow the list, never widen it.
- **300 ms covers all of `classify`, from entry.** See "Round 2" below for how. There is no `/api/version` probe on the hot path: one embed call per sentence.
- **classify never loads or builds the cache.** A background loader, started when the `Matcher` is made, loads the cache file, checks the model digest and rebuilds if needed. Until a cache is in memory, `classify` returns None. The build uses its own 120 s timeout. `warm()` is for scripts and tests only.
- **Cache validation.** On load: key matches, vectors, labels and examples all have the same length, labels equal the example labels, every vector has the same dimension and is finite and non-zero. Anything else is discarded and rebuilt in the background. A query vector must be finite, non-zero and the same dimension, else None.
- **Model digest.** The loader reads the model digest from `/api/tags` and stores it in the cache key. A re-pulled model rebuilds the cache. The check runs after the file is loaded, so the old cache serves while it runs.
- **Localhost only, no proxy.** Calls use an opener with an empty `ProxyHandler`, and any configured URL whose host is not 127.0.0.1, ::1 or localhost is refused (the matcher stays off).
- **One launch.** `ensure_ollama` takes an `flock` on the stamp file, re-checks the stamp, writes it, then spawns (fixed argv, no shell). Ollama is launched from the background threads when an embed fails, not from the hot path.
- **Input and log limits.** Sentences over 500 characters are never embedded. The log policy is in "Round 3" below. `matcher-log.jsonl` rotates at 1 MB (one `.1` file kept).
- **Scores.** Threshold and margin compare unrounded numbers; rounding is for display only, and negative scores show as they are.
- **Missing model.** A 404 or "model not found" is logged once (`event: model-missing`) and the matcher stays off for 10 minutes.

## Round 2 (2026-11-22, after the second Codex re-check)

- **Background loader.** The loader thread starts when the `Matcher` is made. `classify` only reads the cache already in memory, so a cold or large cache file (about 24 MB, about 0.3 s to load) never costs the caller anything. After a failed load or build, `classify` starts a new one at most every 15 s.
- **One lock for the cache.** One lock owns load, digest check, build and publish, so two of them can never interleave. A generation counter makes sure an older load or build never replaces a newer one. `warm()` joins a refresh that is already running instead of starting a second one.
- **One query worker.** One long-lived worker thread per `Matcher` runs the query embed and the scoring, one sentence at a time. If it is busy, `classify` returns None at once and nothing is queued, so a slow or trickling server can never pile up threads. The HTTP call has a total wall-clock limit (connect plus every byte), so a trickling server frees the worker by the deadline. A "model missing" reply that arrives after the caller gave up still starts the 10-minute cooldown.
- **Deadline.** The caller waits for the worker until `timeout_ms` from entry, minus 10 ms so the log line still fits. Scoring runs on the worker inside that wait. A late result is thrown away.
- **Vectors.** Only unit vectors are stored and scored: they are normalised on build and again on load, and a non-finite or near-zero vector makes the cache invalid. Vectors are stored at full precision (rounding could move a cosine across the threshold).
- **Ties.** A result whose gap to the next label is 0 or less (unrounded) is never routable, whatever margin the config allows.
- **Log policy.** Replaced in Round 3: the text is never logged. Still true: non-string input logs only its type name, and if the log is full and rotating fails (for example `.1` is a folder), the line is dropped, so the log never grows past 1 MB.
- **Never raises.** Everything in `classify`, logging included, is inside the guard. Non-string input returns None.
- **Live numbers (nomic-embed-text, 1,496 examples):** a cold process answers its first call in under 1 ms (None, cache still loading); the background load takes about 0.3 s; after that a call takes about 45 ms (max 67 ms over 20 calls, most of it scoring); against a server that trickles bytes, 12 calls each return within 300 ms and leave one query worker thread.

## Round 3 (2026-11-22, after the third Codex re-check)

- **Logging never blocks.** `classify` hands its log line to one background writer thread per `Matcher` and returns. If the writer is behind (256 lines waiting), the line is dropped. `flush_log()` waits for the writer (scripts and tests).
- **HTTP deadline from connect.** Calls to Ollama use plain `http.client` (never a proxy) with a watchdog timer that shuts the socket down at the deadline. Connect, the status line, the headers and the body all count, so a server that trickles even its status line frees the query worker by the deadline. The `/api/version` probe uses the same call.
- **Worker start failure.** If the query worker thread cannot start, the busy flag is cleared and that call returns None, so later calls work.
- **Stale cache retries.** If a rebuild fails while an older cache is in memory (for example the model was re-pulled), the old cache keeps serving and the rebuild is retried every 15 s, the same interval as a failed first load.
- **No text in the log.** The log stores length, a 12-character hash, the top labels with scores, and the outcome (label and routable). The secret-detecting regex is gone: it kept leaking short keys and passphrases while hiding normal sentences.
- **Cache format version.** The cache signature now starts with a format version (`v2`). Any older cache file, including the old rounded ones, rebuilds once.
- **Rounding-error gaps.** A gap to the next label must exceed 1e-9 as well as the configured margin, so a one-ULP gap is never routable, even with margin 0.

## Starting Ollama automatically

- When the matcher finds nothing answering on port 11434, it runs `open -g -j -a Ollama`, the same hidden-launch pattern as the QuickToDo launcher.
  - It does not wait. The sentence in hand falls through to the next layer.
  - Later sentences use the matcher once Ollama is up.
  - At most one launch attempt per 2 minutes.
- If the configured model is missing, the matcher logs it once and stays off. It never pulls models on its own.
- Optional, Morgan's call: add Ollama.app as a login item so it is always up.

## Never

- It never decides times, dates, task ids or list names.
- It never acts without the rules' safety checks.
- It never sends text anywhere but localhost.
- It never blocks a sentence: if Ollama is down or slow (over 300 ms, enforced by a deadline), the sentence skips the matcher.

## Verify

- A held-out set of casual sentences (not in the examples) reaches the right label at the tuned threshold, with the hit rate reported honestly.
- Must-not-act sentences never produce an action.
- With Ollama stopped, routing still works and Ollama gets launched.
- Changing the phrase tables rebuilds the cache.
- The route preview shows `matcher <label> <score>` for matcher-routed sentences.
- All suites pass.

## Wiring into the box (2026-11-22, branch `feat/matcher-wiring`)

**Where it runs.** In `CommandRunner.submit`, after every plain-code rule has passed on the sentence and before the job goes to the router. It never runs when:
- the sentence has a model tag (`@free`, `@sonnet`, ...) or matches the router's Step 0;
- the job is tied to a task (`taskId`), is a follow-up, or is a Stuck request;
- the rules already answered, or the sentence is a capture card or a prep command.

`route_preview.decide(..., matcher=m)` asks the matcher at the same point, so preview and box agree. `server.submit_command` needs no change (capture runs before the runner).

**What each routable label does.** All are read-only, so nothing asks for a yes:

| Label | Answer | Lead line (first person) |
| --- | --- | --- |
| now | engine answer, as Step 0 | "I read that as: what should I do now." |
| schedule | `schedule_qa.parse(force=True)` answer | "I read that as a question about what's due." |
| project | status of the project in focus (`_focus_project`); if none, ask which | "I read that as: where am I on <project>." |
| reminders | the waiting text reminders (list, never cancel) | "I read that as: which reminders are waiting." |
| tiny | "Got it. Ask what's next whenever you're ready." | none |
| general | no change: goes to the router as today | none |

The lead line is there so a wrong guess is obvious at once, and the answer costs nothing.

**Routing line:** `meaning match · <label> <score> · no model`. It shows in the answer and in the mission log.

**Turning it on.** The server makes one `Matcher()` at start when `matcher.enabled` is true. `CommandRunner(matcher=None)` is the default, so tests and scripts never touch Ollama unless they pass one. With Ollama down, `classify` returns None and the sentence goes to the router as before.
