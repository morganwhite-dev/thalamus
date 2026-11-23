#!/usr/bin/env python3
"""Builds engine/inputs/commitments.json (Phase 11): fixed time blocks the day-load maths subtracts.

Sources (stdlib only, read-only):
  1. Class sessions from each active course's planner calendar (`*-schedule.ics`
     under the folders in COURSE_FOLDERS). Only timed events (end after start) count;
     "due at" events (start == end) are deadlines, not time blocks.
  2. An optional weekly work schedule, importers/work_schedule.json:
     [{"days": ["mon","tue"], "start": "09:00", "end": "17:00", "label": "Work"}]
     plus optional one-off "dates": ["2026-11-10"] instead of "days".

Output: a list of {start, end, label} (ISO, with offset) from yesterday to +21 days.
Written only when changed. Never touches QuickToDo.

    python3 importers/build_commitments.py          # write
    python3 importers/build_commitments.py --check  # print only
"""
import json, re, sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

HOME = Path.home()
GSU = HOME / "Desktop/GSU MSIS"
# Only the classes Morgan actually takes; add a folder for a new class.
COURSE_FOLDERS = [GSU / "Network Security", GSU / "Cloud Computing and Security"]
HERE = Path(__file__).resolve().parent
WORK_SRC = HERE / "work_schedule.json"
OUT = HERE.parent / "engine/inputs/commitments.json"
TZ = ZoneInfo("America/New_York")
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
LOOK_BACK, LOOK_AHEAD = 1, 21


def unfold(text):
    return re.sub(r"\r?\n[ \t]", "", text)


def parse_ics(text):
    """VEVENT dicts with start, end (aware datetimes) and summary. Floating/UTC times handled."""
    events = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", unfold(text), re.S):
        f = {}
        for line in block.splitlines():
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            f[key.split(";")[0].upper()] = (key, val)
        try:
            events.append({"start": _dt(*f["DTSTART"]), "end": _dt(*f["DTEND"]),
                           "summary": f.get("SUMMARY", ("", ""))[1].replace("\\,", ",").strip()})
        except (KeyError, ValueError):
            continue  # all-day or malformed events are not time blocks
    return events


def _dt(key, val):
    if "VALUE=DATE" in key and "T" not in val:
        raise ValueError("all-day")
    tz = TZ
    m = re.search(r"TZID=([^;:]+)", key)
    if m:
        tz = ZoneInfo(m.group(1))
    if val.endswith("Z"):
        return datetime.strptime(val, "%Y%m%dT%H%M%SZ").replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
    return datetime.strptime(val, "%Y%m%dT%H%M%S").replace(tzinfo=tz).astimezone(TZ)


def class_blocks(events):
    out = []
    for e in events:
        if e["end"] <= e["start"]:
            continue
        label = re.sub(r"^CIS \d+:\s*(Attend\s*)?", "", e["summary"]) or e["summary"]
        out.append({"start": e["start"], "end": e["end"], "label": "Class: " + label})
    return out


def work_blocks(entries, today):
    out = []
    for offset in range(-LOOK_BACK, LOOK_AHEAD + 1):
        d = today + timedelta(days=offset)
        for e in entries:
            hit = d.isoformat() in e.get("dates", []) or DAYS[d.weekday()] in [x.lower()[:3] for x in e.get("days", [])]
            if not hit:
                continue
            s = datetime.combine(d, datetime.strptime(e["start"], "%H:%M").time(), TZ)
            en = datetime.combine(d, datetime.strptime(e["end"], "%H:%M").time(), TZ)
            if en > s:
                out.append({"start": s, "end": en, "label": e.get("label", "Work")})
    return out


def build(today, ics_texts, work_entries):
    lo = datetime.combine(today - timedelta(days=LOOK_BACK), datetime.min.time(), TZ)
    hi = datetime.combine(today + timedelta(days=LOOK_AHEAD + 1), datetime.min.time(), TZ)
    blocks = []
    for t in ics_texts:
        blocks += class_blocks(parse_ics(t))
    blocks += work_blocks(work_entries, today)
    blocks = [b for b in blocks if b["end"] > lo and b["start"] < hi]
    blocks.sort(key=lambda b: (b["start"], b["label"]))
    seen, rows = set(), []
    for b in blocks:  # a test inside a class window repeats the same hours; keep distinct blocks only
        k = (b["start"], b["end"])
        if k in seen:
            continue
        seen.add(k)
        rows.append({"start": b["start"].isoformat(), "end": b["end"].isoformat(), "label": b["label"]})
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
    texts = [p.read_text() for folder in COURSE_FOLDERS for p in sorted(folder.glob("**/*-schedule.ics"))]
    if not texts:
        print("no class calendars found; refusing to overwrite commitments.json", file=sys.stderr)
        return 1
    work = json.loads(WORK_SRC.read_text()) if WORK_SRC.exists() else []
    rows = build(date.today(), texts, work)
    if "--check" in argv:
        print(json.dumps(rows, indent=2))
        return 0
    print(f"commitments.json: {len(rows)} blocks, {'written' if write_if_changed(OUT, rows) else 'unchanged'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
