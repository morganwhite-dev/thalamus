#!/usr/bin/env python3
"""Builds the drop-folder JSON that QuickToDo's folder watcher imports (Phase 3).

Reads the security status tracker and the internship application CSV and writes
`<name>_assignments.json` files into drop-folder/ in QuickToDo's import format.
Stdlib only. Writes a file only when its content changed, so the watcher is not
woken for nothing. Never touches QuickToDo's store.

    python3 importers/build_drop.py            # build all
    python3 importers/build_drop.py --check    # print what would be written
"""
import csv, json, re, sys
from datetime import date, datetime, timedelta
from pathlib import Path

HOME = Path.home()
SECURITY_SRC = HOME / "Desktop/Projects/Portfolio-Projects/Security-Engineering-Plan/CLAUDE.md"
INTERN_SRC = HOME / "Desktop/GSU MSIS/Internship Applications/Application Tracker.csv"
DROP = Path(__file__).resolve().parent.parent / "drop-folder"
WEEKLY_GOAL = 10
ACTIONABLE = {"ready to submit", "up next", "watch - not open yet"}
MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}


def security_rows(text):
    """Rows of the '## Status tracker' table that still need work."""
    m = re.search(r"^## Status tracker\s*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    rows = []
    for line in (m.group(1) if m else "").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 2 or cells[0] in ("Item", "") or set(cells[0]) <= set("-"):
            continue
        item, status = cells
        low = status.lower()
        if low.startswith("done") or item == "Applications":
            continue
        row = {"course": "Security Projects", "title": item, "dueDate": "none",
               "priority": "high" if low.startswith("next up") else "medium",
               "notes": f"Status: {status}"}
        rows.append(row)
    return rows


def apply_by(notes, today):
    """'apply by Sep 24 2026' in Notes -> 'YYYY-MM-DD', else None."""
    m = re.search(r"(?:apply by|deadline)\s+([A-Za-z]{3})[a-z]*\s+(\d{1,2}),?\s+(\d{4})", notes, re.I)
    if not m or m.group(1).lower() not in MONTHS:
        return None
    try:
        return date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2))).isoformat()
    except ValueError:
        return None


def week_bounds(today):
    start = today - timedelta(days=today.weekday())
    return start, start + timedelta(days=6)


def internship_rows(csv_rows, today):
    rows = []
    start, end = week_bounds(today)
    done = 0
    for r in csv_rows:
        d = (r.get("Date Applied") or "").strip()
        if d:
            try:
                if start <= date.fromisoformat(d) <= end and r["Status"].strip().lower() == "applied":
                    done += 1
            except ValueError:
                pass
    label = f"{start.strftime('%b')} {start.day}"
    rows.append({"course": "Internships", "title": f"Apply to {WEEKLY_GOAL} internships (week of {label})",
                 "dueDate": end.isoformat(), "dueTime": "23:59", "priority": "high",
                 "notes": f"{done} of {WEEKLY_GOAL} applied so far (as of {today.isoformat()})."})
    for r in csv_rows:
        status = (r.get("Status") or "").strip()
        if status.lower() not in ACTIONABLE:
            continue
        title_job = (r.get("Job Title") or "").strip()
        if title_job.startswith("(none"):
            title_job = "watch for postings"
        title = f"{'Watch' if status.lower().startswith('watch') else 'Apply'}: {r['Company'].strip()} - {title_job}"
        notes = (r.get("Notes") or "").strip()
        due = apply_by(notes, today)
        lines = [f"Status: {status}"]
        if (r.get("Handshake Link") or "").strip():
            lines.append(r["Handshake Link"].strip())
        if r.get("Resume Version Used", "").strip():
            lines.append(f"Resume: {r['Resume Version Used'].strip()}")
        rows.append({"course": "Internships", "title": title, "dueDate": due or "none",
                     "priority": "high" if status.lower() == "ready to submit" else "medium",
                     "notes": "\n".join(lines)})
    return rows


def write_if_changed(path, rows):
    new = json.dumps(rows, indent=2, ensure_ascii=False) + "\n"
    if path.exists() and path.read_text() == new:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(new)
    tmp.replace(path)
    return True


def main(argv):
    check = "--check" in argv
    today = date.today()
    jobs = {"security_assignments.json": security_rows(SECURITY_SRC.read_text())}
    with INTERN_SRC.open(newline="") as f:
        jobs["internships_assignments.json"] = internship_rows(list(csv.DictReader(f)), today)
    for name, rows in jobs.items():
        if check:
            print(name, json.dumps(rows, indent=2))
            continue
        changed = write_if_changed(DROP / name, rows)
        print(f"{name}: {len(rows)} rows, {'written' if changed else 'unchanged'}")
    if not check:  # Phase 11: refresh fixed commitments on the same hourly run
        import build_commitments
        build_commitments.main([])


if __name__ == "__main__":
    main(sys.argv[1:])
