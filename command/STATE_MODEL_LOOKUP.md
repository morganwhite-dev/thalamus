# Phase 16 state model: ask general things in plain language (no model for lookups)

Morgan (2026-11-08): "ask general things in plain language", e.g. "do you have teaching notes for module 5 and 6 for network security" and "where did I leave off on my network analyzer project". Answers must not float over the screen.

## Where answers show
Answers and the add-a-task card replace the Mission log inside the log column (same box, scrolls, Dismiss/Close brings the log back). Nothing covers the brain.

## Lookups (plain code, zero usage), tried before the model router
1. **Projects.** More phrasings: "where did I leave off on X", "where am I on X", "what was I working on in X", "how's X going", "status of X". Name matching also accepts all-words-in-title ("network analyzer" finds "Network traffic analyzer").
2. **Files.** A find-a-file question ("do you have / is there / find / where is / show me / open / pull up ... notes, slides, deck, quiz, study guide, outline, syllabus, reading, lecture, lab, assignment, module N, week N, exam") searches only the folders in `engine/config.json -> lookup.roots` (the two course folders). Module and week numbers, document kind (teaching notes, outline notes, quiz, slides) and course words narrow it. The answer lists what was found per module, says plainly what was NOT found, and gives an **Open** button per file.
3. Anything else goes to the normal router, unchanged.

## Open button
`POST /api/open {path}`: X-Brain + Host + Origin checks as everywhere; the real path (symlinks resolved) must be a file inside a lookup root, with an allowed document extension (pdf, pptx, ppt, docx, doc, html, md, txt, xlsx, csv, png, jpg, key); then macOS `open`. Nothing else can be opened.

## Not built
No reading of file contents, no model sees the files, no new macOS permission (the dashboard server already reads the Desktop for imports).

## Tests
Intent table (finds files vs not), module/kind/course narrowing on a temp tree, not-found wording, project fuzzy match and new phrasings, open endpoint refuses outside-root, symlink escape, bad extension, and missing file.
