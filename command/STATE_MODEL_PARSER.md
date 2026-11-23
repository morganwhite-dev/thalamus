# State model: chat fallback parser and context card (Phase 21)

Status: plan, not built. Written 2026-11-22. Builds on the phrasebook work (`feat/chat-phrasebook`: `parse_action`, `parse_reply`).

## Goal

Morgan types loosely: no capitals, typos, half sentences. The plain-code rules catch most of it for free. This phase covers the rest: sentences the rules miss should still reach the right place, without guessing and without spending Sonnet usage.

General questions ("why is the sky blue", "how do i center a div") keep working exactly as today. They go to a free model, which answers them, with Haiku as the backup.

## Where a sentence goes (in order)

1. **Rules.** The phrasebook, intent, schedule, lookup, capture, park and project-status rules all run as they do now. If one is sure, it handles the sentence: no model, no usage.
2. **Reply to the last question.** If the chat is waiting on an answer (for example "Add X to Personal?"), `parse_reply` reads the sentence against that question first.
3. **"About my stuff" gate (plain code, new).** The rules missed. Does the sentence mention her things?
   - Her signals: a task or list name (fuzzy, typo-tolerant), a course, file words (notes, slides, lab, module, week), "my" with a noun, or a verb of the actions (done, snooze, skip, pin, start, undo).
   - If yes, go to step 4.
   - If no, it is a general question: go to the router as today (free model, then Haiku). The router already sends short plain questions to a free model with no classifier call.
4. **Translator model (new).** A free model gets the sentence plus the context card (below). It returns only a structured intent, never an answer:
   `{kind: lookup|schedule|action|capture|park|project_status|general|unclear, fields...}`
   - `lookup`: words, course, module/week numbers, document kind
   - `action`: action, task id, args (minutes, until)
   - `capture`: title, list, due
5. **Validation (plain code).** Every field is checked against real data:
   - Task ids and list names must exist.
   - Title words must come from her sentence.
   - Dates must parse and must not be in the past.
   - Numbers must appear in her sentence.

   A field that fails is dropped, not guessed. If the intent is still usable, the same code the rules use runs it (the lookup search, the engine, the confirm card).
6. **Escalation.** If the free model's answer fails validation, a second free model gets the same card. If that fails too, Haiku tries. If Haiku also fails, the chat asks one short question ("Do you mean the Network Security teaching notes?"). It never climbs above Haiku.
7. **Actions still confirm when unsure.** Anything that changes data is said back before it acts if a model translated it ("Snooze Read Chapter 6 for 3 hours?"). Actions the rules were sure about act straight away, with undo available.

## Context card (what every translator call gets)

A short block of plain facts. It is rebuilt per call and kept small; no project notes and no CLAUDE.md.

- Her list names and which category each belongs to
- Course names, their short forms and the course folders (from `engine/config.json` `lookup.roots`, names only, no file contents)
- The current "do this now" task and any running block
- Open task titles with ids (top ~40 by rank)
- The chat's pending question, if any
- Today's date and time
- The allowed intent kinds and their fields, plus 3 to 4 worked examples

## Log

Every sentence that reached step 4 is appended to `command/state/parser-fallbacks.jsonl`. Each entry holds: the sentence, the model, the raw intent, what validation dropped, the final outcome, and whether Morgan corrected it. Common ones become rules, so fewer sentences reach a model over time.

## Never

- The translator never answers or acts by itself, and never reads files.
- A question never creates a task or triggers an action.
- It never goes above Haiku for a sentence about her stuff.
- General questions are not blocked or rerouted by this. They keep going to the router.

## Verify

- A table of unseen sloppy phrasings, run with the rules switched off, reaches the right intent.
- Questions never create tasks.
- An invalid model answer falls back to a clean question.
- "why is the sky blue" still gets a normal answer.
- The log records each fallback.
- One live run per kind with a real free model.
