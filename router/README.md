# Priority Brain router (Phase 1b)

Standalone model router. It decides which model handles a task, runs it through OpenCode,
checks free-model output, counts Claude usage and logs every turn. The rules come from
"Model routing" in `../CLAUDE.md`. Python 3 standard library only; nothing to install.

## Use

```bash
cd ~/Desktop/Projects/priority-brain/router
python3 -m router "rename tmp to total in budget.py"       # route and run (in ~/.local/share/priority-brain-router/workspace)
python3 -m router --dry-run "add caching to the API client" # classify only, no task model
python3 -m router "@opus max design the snapshot format"   # tag override (+ optional effort)
python3 -m router --conversation c1 "..."                   # stay on one model within c1
python3 -m router --source notes.txt "summarize this"       # grounding source for the validator
python3 -m router usage                                     # 5-hour / today / week units
python3 -m router log 20                                    # last 20 routing-log rows
python3 -m router models                                    # live roster and exclusions
python3 -m unittest -v                                      # offline tests (no model calls)
python3 samples.py [--run-free]                             # ~14 sample tasks, which model each
python3 verify_bad_outputs.py                               # bad outputs vs the live validator
```

## How a task flows

1. **Step 0:** "what should I do now / what's due ..." goes to the priority engine with no model call (a stub until Phase 4).
2. **Step 1:** `@free|@haiku|@sonnet|@opus [low|medium|high|xhigh|max]` skips classification.
3. **Conversation pin:** with `--conversation`, later turns reuse the same model and OpenCode session unless it failed or a tag overrides it.
4. **Step 2:** cache, then a keyword shortcut (short, mundane, no risk words: free tier with no model call), then **Jev** answers Q1 to Q7 plus two helper facts (several files; small function from a clear spec). If Jev is down, a keyword fallback answers instead (logged, not cached).
5. **Step 3:** `rules.start_tier` applies the table exactly: first matching row wins, effort +1 for Q3 below Opus, `xhigh`/`max` only by tag.
6. **Step 4:** run it.
   - **Free:** up to 3 different free models.
   - **Then Haiku:** one attempt, then stop.
   - **Haiku tier:** one retry at one effort level higher.
   - **Sonnet and Opus:** one attempt; on failure the router stops and asks.
   - Escalation goes one tier at a time (`rules.next_tier`), so nothing jumps straight to Opus.
7. **Steps 5 and 6:** usage units and the routing log are written.

## Validator (free-model output)

- **Layer 1 (deterministic):** catches empty answers, refusals, length bounds, JSON or Python format, truncation and grounding. Grounding means dates, times, codes and numbers must come from the source, and summaries must keep the key facts.
- **When the model edited files:** the change itself is checked. Changed `.py` files must compile and must not use undefined names (this catches half-done renames). Changed `.json` must parse. Free models may not delete files. An edit task that changed nothing fails.
- **Layer 2 (Jev):** grades the answer with the plan's five rubric questions, or grades a diff with "only requested edits?" and "everything done?". Tasks that ask for new content (no source, not summary, extraction or edit) skip the "invented details?" question; it rejected correct tips and first steps.
- **Layer 3 (Haiku audit):** every free result in week one, then 1 in 5. It never retries. Scores per model and task type go to `state/audits.json`, and low scorers drop in the free-model ranking.
- **Rollback:** a failed attempt's file edits are undone before the next attempt. Files it created go to `state/rollback/<time>/`; nothing is deleted.

## Facts found while building (2026-11-05, OpenCode 2.2.5)

- **CLI and API:** the CLI is `/Applications/OpenCode.app/Contents/Resources/opencode-cli`. Its `api` subcommand reaches the background server.
- **Effort:** effort is a model variant (`run -m claude-code/claude-opus-5-5#high`). The plugin turns it into `claude --effort high`.
- **Free models:** they refuse the stateless text endpoint ("Free usage limit reached") but work through `opencode run` sessions. Each session costs about 12k input tokens of agent prompt, which is free.
- **Jev:** it isn't in the model list. It answers on `experimental.generate.decisions` as `opencode/jev-1.13-free`, at cost 0. Described **choice** questions calibrate far better than yes/no: about 1.0 confidence vs. about 0.5 on borderline tasks. The rubric and the judge both use choices.
- **Console switches don't block models:** models switched off in the OpenCode console still answer through the API, so `config.json` keeps its own exclusion list.
- **Folder:** OpenCode takes its folder from `$PWD`, so the client sets it explicitly.
- **Plan usage:** the Claude plugin prints plan usage ("used N% of the 7-day window, resets ..."). The router stores the latest line in `state/plan-notice.json` and shows it in the log.

## Stability and housekeeping

- **Borderline answers:**
  - Any rubric answer within 0.1 of the threshold is asked twice more and averaged. Jev is free, so this costs nothing.
  - The "several files" question counts files a task reads, not only ones it changes. The old wording split Jev between 0.47 and 0.61 on an investigation task; the new wording reads 1.0 every time.
- **Folder lock:** only one router run per working folder at a time.
- **Finished sessions are archived:** each finished OpenCode session is archived, which is reversible, so router runs don't pile up in the OpenCode session list. A `--conversation` keeps its session open.
- **Rollback scope:** rollback covers text files up to 512 KB in the working folder; `.git`, `node_modules` and similar are skipped.
- **Usage thresholds:** warn limits in `config.json` are `null` (off) until about a week of log data exists. That's the plan's rule: thresholds are set from real data.

## Working folder and agent (2026-11-05)

- Models work in `~/.local/share/priority-brain-router/workspace`, outside `priority-brain/`, so the Claude CLI and OpenCode never load the brain's `CLAUDE.md`.
- Every run uses `--agent router`, defined in that folder's `opencode.json` (written by the router if missing). Without it, runs fell back to OpenCode's plan agent, which adds a "You are in Plan mode" turn.
- Runs get an empty stdin, because `opencode run` appends stdin to the message.
- Answers containing agent chatter ("plan mode", "confirm the model switch") fail layer 1.

## "Executable not found in $PATH: claude" (fixed 2026-11-12)

Claude-tier runs (Haiku, Sonnet, Opus) failed with this error while free models worked. Cause: the
OpenCode background server (`opencode-cli serve --service`, started by the app) has PATH
`/usr/bin:/bin:/usr/sbin:/sbin`, and the Claude plugin starts `claude` from inside that server, so the
router's own PATH never reaches it. Fix: `~/.config/opencode/opencode.json` now sets
`provider.claude-code.options.cliPath` to `/Users/morguewhite/.local/bin/claude` (backup:
`opencode.json.bak-before-cliPath`). If `claude` ever moves (it is a symlink into
`~/.local/share/claude/versions/`), update that path.
