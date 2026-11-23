# Phase 13 state model: Application prep agent

Status: design approved 2026-11-07 (Sonnet 5.5); building.

## 0. Shape

Morgan types in the command box `prep: <url> <url> ...` (or `prep the ready rows`). A new `prep/` module handles it before the router (like Step 0), runs a **batch job** in the background, and texts when the batch is done. It never submits anything, never writes to QuickToDo, never invents facts.

    POST /api/command {text: "prep: ..."}  -> job (same job store, kind "prep")
    per posting:  fetch -> extract (free) -> fit call -> tailor resume + letter (Sonnet) -> render docx/pdf -> check -> save -> note on task
    batch end:    one ntfy text "Prep done: 8 ready, 2 need a pasted description"

## 1. Per-posting pipeline (states)

    queued -> fetching -> extracting -> drafting -> rendering -> ready | needs-paste | skipped-mismatch | failed

1. **fetch**: plain HTTP GET (no login, no browser). Blocked or thin page (Handshake, LinkedIn, login wall, under ~400 chars of text) -> `needs-paste`; the dashboard shows a paste box for that posting and resumes it.
2. **extract** (free tier through the router, validated): company, title, location, requirements, keywords, apply-by date, start timing. Layer 1 grounding: company/title must appear in the page text.
3. **fit call** (deterministic flags + one model sentence): internship vs full time, graduation timing (May 2027), state limits, mandatory certs. Clear mismatch -> `skipped-mismatch` with the reason; never builds; Morgan can force it with `prep!`.
4. **draft** (Sonnet 5.5, `@sonnet medium`, one attempt, no retries per router rules): resume content as structured JSON (summary, skills, ordered projects, bullets chosen from her real resume) and the cover letter text, using only the Master Profile.
5. **grounding check (code, no model)**: every employer, date, number, cert and project in the draft must exist in the Master Profile fact list; certs in progress labelled "In Progress"; banned claims (section 3) rejected; no em dashes or hyphens as punctuation. Fail -> one redraft telling the model exactly what to remove; fail again -> `failed` for that posting, others continue.
6. **render**: python-docx builds the resume (copied layout of her newest tailored resume) and letter, soffice to PDF, `pdfinfo` must say exactly 1 page for both; trim step if it spills.
7. **save + attach**: files to the folder in section 4; a note line written to the brain-side store keyed by the Internships task (QuickToDo itself is not written).

## 2. Hard rules (from CLAUDE.md and the tailor skill)

- Never submits, never enters personal data, never clicks apply.
- No fabrication: summary/skills/bullets may only reorder and emphasize items in the Master Profile.
- Letters route to Sonnet (free models write flat letters).
- Fetch is read-only plain HTTP, 15 s timeout, 1 MB cap, no cookies; URLs must be http(s), no private/localhost addresses (SSRF guard).
- Job-page text is data, never instructions (prompt-injection guard: the page text goes in a fenced block and the prompt says to ignore commands in it).
- Cost cap: at most 12 postings per batch; Sonnet runs counted by the existing usage counter.

## 3. Fact source and banned claims

Facts come only from `Internship Applications/Application_Master_Profile.docx` plus the newest tailored resume's layout. Parsed once into `prep/state/facts.json` (employers, dates, verified figures, skills, certs, projects) and shown to Morgan to confirm before the first real run. Banned (from the Master Profile): Microsoft Office/Excel proficiency, Power BI, ServiceNow, Security+, Azure, ML libraries, Copilot Studio, professional pen testing or red teaming; Broken Leg Entertainment stays off.

## 4. Files and owners

| File                                      | Owner                     | Contents                                                |
| ----------------------------------------- | ------------------------- | ------------------------------------------------------- |
| `prep/prep.py`                            | prep module               | pipeline, job runner                                    |
| `prep/fetch.py`, `render.py`, `ground.py` | prep module               | fetch with guards, docx/pdf, grounding check            |
| `prep/state/batches.json`                 | prep (lock, atomic)       | last 20 batches, per-posting state, error, output paths |
| `prep/state/facts.json`                   | prep, from Master Profile | verified facts                                          |
| output files                              | prep                      | see open choice A                                       |
| `Application Tracker.csv`                 | Morgan                    | **not touched**; she marks Applied herself              |

## 5. Dashboard (revised: no new UI)

Batch card under the Internships cluster: per-posting line with its state, a paste box for `needs-paste`, an Open folder link, a "Skip" for any posting. Plain page gets the same list. No new backend endpoints beyond `GET /api/prep` and `POST /api/prep/paste`.

## 6. Tests and Verify

Fake fetch/router/renderer: blocked page -> needs-paste; mismatch -> skipped; invented number, banned claim, em dash, unlabeled in-progress cert each caught; one-page check; SSRF URLs refused; injection text in a page ignored; batch survives one failure; text sent once at end; no write to the tracker. **Verify:** 2 real postings end to end (files open, one page each, facts match profile), then 10.

## 7. Decisions (Morgan, 2026-11-07)

- **A. Output:** existing `Tailored Resumes/` and `Cover Letters/` folders, skill naming `Resume_Company_Role_2027`, no new folders. `batches.json` is the index.
- **B. Letters:** only when the posting requires one or the command is `prep+letter:`.
- **C. Input:** links only for now (tracker rows later if wanted).
