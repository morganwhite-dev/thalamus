# State model: the chat drawer (replaces the footer)

Written 2026-11-22, branch `feat/chat-drawer`. Decisions are in `CLAUDE.md` ("Decision (Morgan, 2026-11-22): no footer, chat instead" and the Phase 21 update). Mockups: `mockups/chat-nov22/drawer.html` (the drawer), `mockups/chat-nov22/index.html` third view (the `/` menu).

## Screen

- The screen is the brain only, with the top bar (clock, warnings, pinned jump, texts, low energy, low power, sync).
- At the bottom sits a quiet line: `> talk to thalamus` with `/ to type` on the right. While a work block or break runs, the same line shows what is going on (`● Read Chapter 6 · 12:04 of 50 min`), so the timer is always visible with the drawer shut.
- Clicking the line, or pressing `/` anywhere outside a text field, opens the drawer. The line grows into the drawer in one motion. The brain layer (canvas, dials, fibres) glides up and shrinks just enough to clear it.
- **Drawer:** centred, 460 px wide. Open with no messages, it is just the input. Each message makes it taller, with no empty space above, up to 220 px. After that it scrolls, with a fade at the top. The brain shrinks only as much as the drawer needs.
- **Esc** closes the `/` menu first, then the drawer. Clicking outside the drawer also closes it.
- **Messages:** hers are right-aligned bubbles. Replies are plain text on the left, with no label, 5 px apart, line height 1.4.
- **Replies are first person** and say what was done: "Added "Email Dr. Lee" to Personal, due Fri at 12 PM. Say undo to take it back."
- **Chat has no buttons.** File results stay as links, since opening a file is reading, not acting.
- **Gone from the screen:** the strip dock and its Do this now card, the up-next chips, the status lip, the Log sheet, the Why sheet, the add-a-task card and the `?` help panel. The "now" dial's NOW tag and glow still mark the current task.
- **Sector panels** (click a dial) keep their own task card with its buttons. They are not part of the footer.
- **A task added from the chat** flies as a small glowing chip from the reply into its sector's dial. The dial pulses and shows "+1".
- **Reduce Motion and low power** skip the glide and the flight. The drawer simply appears, and the dial still shows "+1".

## Conversation store

`command/state/chat.json` (gitignored with the rest of `state/`):

```
{version: 1, day: "2026-11-22", rows: [...], pending: {...}|null, seen: {phase, blockId, over}}
row = {id, at, who: "me"|"th", text, jobId?, addId?, fly?, tone?: "bad"|"ok"|"dim", files?: [...], undo?: {id, expires}}
```

- **Today only.** The day starts at 4 AM, so a late-night session doesn't reset at midnight. The view shows at most the last 50 rows. Rows from before today are dropped from `chat.json` but kept in `command/state/chat-log.jsonl`, one line each.
- **Pasted text** is never written to either file. The row keeps the chip text; the log keeps only lengths.
- **A pending question survives the trim:** it is stored apart from the rows.
- **A row tied to a model job** (`jobId`) shows "thinking…" with the job's stage until the job finishes. When the view sees the job finished, it copies the answer, routing line and files into the row and saves it. Jobs fall out of `jobs.json` after 20, so the copy is what lasts.
- **A row tied to an add** (`addId` = the QuickToDo action id) says "Adding…" until QuickToDo answers. It then becomes "Added …" (or QuickToDo's reason) and gets `fly` once, so the page plays the flight. Check-ins that wait on the add are saved at that moment, as the card did.

## What she types, in order

`POST /api/chat {text, pastes?: [string]}`. Pastes stand in the text as `[Pasted text #N · L lines]`.

1. **Pasted text** goes straight to the router with the pastes put back in. It skips the rules, capture and the meaning matcher.
2. **A pending question** gets first look:
   - Add confirmations:
     - "yes / yep / sure / ok / sounds good / do it / add it" adds the task.
     - "no / nope / cancel / never mind" drops it: "OK, I didn't add it."
     - A correction is applied: "make it saturday" (date), "put it in school" or "in personal" (list), "no date", "call it …" (title). If the add is then clear, it is added; if not, I ask again.
     - Anything else drops the question quietly and is handled as a new message.
   - Check-in ("Did you do something just for you?"):
     - "yes / yeah / I did" answers yes.
     - "no / nope / I didn't" answers no.
     - "not now / later / skip" answers later.
     - Then I name the next block.
3. **"undo"** takes back the newest change the chat made in the last 2 minutes: a chat add, a Done, snooze, pin, skip, park, a cancelled reminder or a status line.
4. **Typed actions** (new, chat only; the old box kept its "press the button" replies):

| She says | Does | Only when |
| --- | --- | --- |
| done, I finished it, done with lab 7 | completes the task in QuickToDo (same request as the Done button). Undo for 2 minutes. | names one task, or there is a current task |
| start, let's go, start lab 7 | starts a work block with no 3-2-1 | idle |
| begin now | skips the countdown | starting |
| 15 more minutes, more time, extend | +15 | work |
| break, take a break | ends the block, starts a break | work |
| done, no break / skip the break | ends the block, no break | work |
| cancel, stop the block | cancels the block | starting or work |
| I'm back, end break | ends the break early, asks the check-in | break |
| I started 20 minutes ago | starts the block 20 minutes in the past | idle |
| I'm tired, low energy (on/off) | low energy on or off | always |
| why this?, why | the current task's why line | always |

   Pin, unpin, snooze and skip already act from a sentence (`command/acts.py`).

   **"done" during a work block** means done with that block's task. It completes the task and offers the break, as "Done: take a break" did.

   **A typed action that can't run says why**, in one first-person line: "Nothing's running, so there's nothing to cancel."
5. **Everything else** goes to the existing order (`submit_command`: capture, then the runner's rules, matcher and router). The result is shown as a reply:
   - **Capture proposal, confident.** Two cases:
     - A plain task whose list came from her words or the open sector, with no date words left unread.
     - A text reminder with a time.

     It is added right away: "Added "X" to Personal, due Fri at 12 PM. Say undo to take it back."
   - **Capture proposal, not sure.** This covers no list, a repeating item, a study plan, a check-in, or "add X and text me". It becomes a pending question, in the first person: "I'll put "Get groceries" in Personal with no date. Sound right?" With no list: "Which list should "Get groceries" go in: School, Personal or …?"
   - **Runner job:** the reply row follows the job.
   - **Follow-ups:** a message sent within 10 minutes of a model answer that the rules don't settle goes as a follow-up in the same conversation, as Options > Follow up did.

## Block events in the chat

On each view, the chat compares the block state with `seen`:

- **Time is up:** "Time's up on "Read Chapter 6". Say break, 15 more, or done."
- **The task was completed elsewhere during a block:** "Read Chapter 6 is done. Say break for a 25-minute break, or start for the next one."
- **The break ends** (phase becomes check-in): "Break's over. Did you do something just for you?" This also sets the check-in pending question.

## Footer feature to chat (nothing dropped without a reason)

| Footer feature | In the chat |
| --- | --- |
| Do this now card, title, why | "what now" (engine), "why this?"; the NOW dial |
| Start, 3-2-1, elapsed timer | "start"; the timer shows on the quiet line |
| Done, Undo after Done | "done"; "undo" |
| Not now menu: snooze, not this one, pin, started earlier | typed (step 4) |
| I'm stuck | "I'm stuck" (`/stuck`) |
| +15, cancel block, break, skip break, end break, check-in, next block | typed (step 4), block events |
| Up next chips | "what's next in school" (schedule answers); the dials |
| Log sheet | dropped: the chat is the log for today; older lines stay in `log.jsonl` and `chat-log.jsonl` |
| Answer sheet, loading bar, error, Try again | reply rows; "thinking…" with the stage; "try again" resends the last message |
| Follow up | automatic within 10 minutes (above) |
| Save answers to (picker) | dropped: long answers still save to the task they match automatically. Explicit "save to X" is on the later list. |
| Add-a-task card | confident add or a first-person question (step 5) |
| Texts (✉), pinned jump, low energy, low power, sync, warnings | top bar, unchanged |
| Class note | "do I have class" (calendar answers) |
| Autofill of task titles | kept: grey completion in the chat input, Tab fills |
| `?` help panel | the `/` menu |

## `/` menu

Typing `/` as the first character lists /now, /due, /add, /done, /stuck, /find, /where, /park and /prep, each with a one-line description. There are no example lines.

- Arrows move, and Tab or Enter picks.
- Picking one fills the input with a starter, for example `what's due ` or `remind me to `, ready to edit.
- Typing narrows the list.
- The slash words are optional shortcuts; plain sentences always work.
- `command/tests/test_help_examples.py` checks that each entry's starter is understood.

## Never

- The chat never completes a task it is not sure of. Done needs one named task or the current one.
- It never claims "Added" before QuickToDo confirms.
- It never shows pasted text in a log.
- It never puts a button in the conversation.
