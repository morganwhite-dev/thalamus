"""Priority engine: one pure function over the QuickToDo snapshot.

recommend(snapshot, overrides, commitments, config, now) -> (result, pruned_overrides)

No model calls, no network, no writes to QuickToDo. `now` is injected so tests control time.
Contract and rules: engine/STATE_MODEL.md.
"""
from __future__ import annotations

import re

from datetime import datetime, timedelta

PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}
UNMAPPED_RANK = 8
FAR = datetime.max.replace(tzinfo=None)


# ---------------------------------------------------------------- helpers

def parse_dt(value, tz):
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(tz)


def start_of_day(now):
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def end_of_day(now):
    return start_of_day(now) + timedelta(days=1)


def clock(now, hhmm):
    h, m = hhmm.split(":")
    if int(h) == 24:   # "24:00" = end of today (midnight)
        return start_of_day(now) + timedelta(days=1, minutes=int(m))
    return now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)


def naive(dt):
    return dt.replace(tzinfo=None) if dt else FAR


def day_word(due, now):
    today = start_of_day(now)
    days = (start_of_day(due) - today).days
    stamp = due.strftime("%-I:%M%p").lower()
    if days < 0:
        return f"{due.strftime('%a %b %-d')}"
    if days == 0:
        return f"today {stamp}"
    if days == 1:
        return f"tomorrow {stamp}"
    if days < 7:
        return f"{due.strftime('%a')} {stamp}"
    return f"{due.strftime('%b %-d')} {stamp}"


# ---------------------------------------------------------------- categories

def category_for(list_name, config, title=""):
    for cat in config["categories"]:
        if list_name in cat["lists"]:
            return cat
    # Tasks saved with no category land in "General"; title keywords can still place them.
    for rule in config.get("titleRules", []):
        if list_name in rule["lists"] and any(k in title.lower() for k in rule["match"]):
            return next(c for c in config["categories"] if c["name"] == rule["category"])
    return {"name": "Other", "rank": UNMAPPED_RANK, "hard": False, "lists": []}


# ---------------------------------------------------------------- overrides

def empty_overrides():
    return {"version": 1, "pins": [], "snoozes": [], "skips": [], "focus": {},
            "mode": {"lowEnergy": False, "since": None}}


def prune_overrides(overrides, tasks_by_id, now):
    """Drop expired entries and entries for tasks no longer open."""
    ov = empty_overrides()
    ov.update({k: v for k, v in (overrides or {}).items() if k in ov})
    tz = now.tzinfo
    today = now.date().isoformat()
    ov["pins"] = [p for p in ov["pins"] if p["taskId"] in tasks_by_id and p["forDate"] >= today]
    ov["skips"] = [s for s in ov["skips"] if s["taskId"] in tasks_by_id and s["forDate"] >= today]
    ov["snoozes"] = [s for s in ov["snoozes"]
                     if s["taskId"] in tasks_by_id and parse_dt(s["until"], tz) > now]
    mode = dict(ov["mode"] or {})
    if mode.get("lowEnergy") and mode.get("since") and mode["since"][:10] < today:
        mode = {"lowEnergy": False, "since": None}
    ov["mode"] = {"lowEnergy": bool(mode.get("lowEnergy")), "since": mode.get("since")}
    ov["focus"] = {k: v for k, v in (ov.get("focus") or {}).items() if v in tasks_by_id}
    return ov


# ---------------------------------------------------------------- derive

def rule_minutes(t, config):
    """Morgan's own estimate rules (list + whole-word title match), used when a task has no estimate."""
    words = set(re.findall(r"[a-z0-9]+", t.get("title", "").lower()))
    for r in config.get("estimateRules", []):
        if t.get("list") in r["lists"] and words & set(r["match"]):
            return int(r["minutes"])
    return None


def fmt_dur(m):
    """Minutes as hours and minutes: 45 -> '45 min', 90 -> '1 h 30 min', 120 -> '2 h'."""
    m = int(round(m))
    h, r = divmod(max(m, 0), 60)
    return f"{h} h {r} min" if h and r else (f"{h} h" if h else f"{r} min")


def in_progress(r):
    t = r["raw"]
    return bool("in progress" in (t.get("notes") or "").lower() or (t.get("progressPercent") or 0) > 0 or t.get("startedAt"))


def pick_focus(rows, current_id, pins, skips, snoozed):
    """One project at a time for a focus category (Security Projects). Sticky: keeps the current one until it is
    done, skipped or snoozed. A pin wins. Otherwise: already started, then high priority, then title order."""
    usable = [r for r in rows if not r["blocked"] and r["id"] not in skips and r["id"] not in snoozed]
    if not usable:
        return None
    for r in usable:
        if r["id"] in pins:
            return r["id"]
    started = [r for r in usable if in_progress(r)]
    if started:                      # work already under way outranks a project that was only picked
        if current_id and any(r["id"] == current_id for r in started):
            return current_id
        usable = started
    elif current_id and any(r["id"] == current_id for r in usable):
        return current_id
    usable.sort(key=lambda r: (not in_progress(r), r["priority"], r["title"], r["id"]))
    return usable[0]["id"]


def derive(snapshot, config, now):
    tz = now.tzinfo
    open_ids = {t["id"] for t in snapshot["tasks"]}
    defaults = config.get("defaultMinutes", {})
    rows = []
    for t in snapshot["tasks"]:
        cat = category_for(t["list"], config, t["title"])
        due = parse_dt(t.get("dueDate"), tz)
        hard = bool(cat["hard"] and due)
        reflowed = False
        eff = due
        if due and not hard and due < now:
            eff = start_of_day(now)   # soft + missed: carried to today, no overdue wording
            reflowed = True
        ruled = None if t.get("estimatedMinutes") else rule_minutes(t, config)
        minutes = t.get("estimatedMinutes") or ruled or defaults.get(cat["name"], defaults.get("Other", 30))
        dep = t.get("dependsOnTaskID")
        rows.append({
            "raw": t, "id": t["id"], "title": t["title"], "list": t["list"], "cat": cat,
            "due": due, "eff": eff, "hard": hard, "reflowed": reflowed,
            "escalated": bool(hard and due < now),
            "blocked": bool(dep and dep in open_ids),
            "minutes": int(minutes), "estimated": bool(t.get("estimatedMinutes") or ruled),
            "priority": PRIORITY_RANK.get(t.get("priority"), 3),
        })
    return rows


def base_key(r):
    return (naive(r["eff"]), r["cat"]["rank"], r["priority"],
            r["raw"].get("rescheduleCount", 0), r["title"], r["id"])


def urgent(r, now, hours):
    return r["hard"] and r["due"] <= now + timedelta(hours=hours)


# ---------------------------------------------------------------- recommend

def recommend(snapshot, overrides, commitments, config, now):
    tz = now.tzinfo
    rows = derive(snapshot, config, now)
    by_id = {r["id"]: r for r in rows}
    ov = prune_overrides(overrides, by_id, now)
    low = ov["mode"]["lowEnergy"]
    urgent_hours = config.get("lowEnergyUrgentHours", 24)

    pins = {p["taskId"]: p for p in ov["pins"]}
    skips = {s["taskId"] for s in ov["skips"]}
    snoozed = set()
    snooze_ignored = {}
    for s in ov["snoozes"]:
        r = by_id[s["taskId"]]
        if r["hard"] and now >= r["due"]:      # escalation beats snooze
            snooze_ignored[s["taskId"]] = s.get("until")
            continue
        snoozed.add(s["taskId"])

    focus_ids = {}
    for cat in config["categories"]:
        if cat.get("focus"):
            mine = [r for r in rows if r["cat"]["name"] == cat["name"]]
            fid = pick_focus(mine, ov["focus"].get(cat["name"]), pins, skips, snoozed)
            if fid:
                focus_ids[cat["name"]] = fid
    ov["focus"] = dict(focus_ids)

    eligible, skip_kept = [], set()
    for r in rows:
        if r["blocked"] or r["cat"].get("play"):   # Play is offers only: never ranked, pinned or escalated
            continue
        if r["cat"].get("focus") and focus_ids.get(r["cat"]["name"]) != r["id"]:
            continue                                # one project at a time: the rest wait, hidden on purpose
        if r["id"] in pins:
            eligible.append(r)
        elif r["id"] not in snoozed and r["id"] not in skips:
            eligible.append(r)

    # A skip never hides the only urgent hard deadline.
    horizon = now + timedelta(hours=24)
    if not any(r["hard"] and r["due"] <= horizon for r in eligible):
        for r in rows:
            if r["id"] in skips and r["id"] not in pins and not r["blocked"] and r["id"] not in snoozed \
                    and r["hard"] and r["due"] <= horizon:
                eligible.append(r)
                skip_kept.add(r["id"])

    def band(r):
        if r["id"] in pins:
            return 1
        if r["escalated"]:
            return 2
        return 3 if r["eff"] else 4

    def sort_key(r):
        b = band(r)
        if b == 1:
            return (1, pins[r["id"]]["pinnedAt"]) + base_key(r)
        if low and not urgent(r, now, urgent_hours):
            return (5, r["minutes"]) + base_key(r)
        return (b, "") + base_key(r)

    eligible.sort(key=sort_key)
    n_queue = config.get("queueSize", 5)
    escalated_waiting = [r for r in eligible if band(r) == 2]

    def entry(i, r):
        why = why_line(r, i, eligible, band(r), pins, skip_kept, escalated_waiting, low, now)
        if r["cat"].get("focus"):
            why = "Your one project right now: finish it before starting another. " + why
        if r["id"] in snooze_ignored:
            why += " You snoozed it, but it is past its deadline, so it stays up here."
        return {
            "taskId": r["id"], "title": r["title"], "list": r["list"], "category": r["cat"]["name"],
            "band": ["", "pinned", "escalated", "dated", "undated"][band(r)],
            "dueDate": r["due"].isoformat() if r["due"] else None,
            "minutes": r["minutes"], "minutesEstimated": r["estimated"],
            "why": why, "resources": r["raw"].get("notes", ""),
        }

    out = [entry(i, r) for i, r in enumerate(eligible[: n_queue + 1])]
    current = out[0] if out else None
    queue = out[1:]

    snap_gen = parse_dt(snapshot.get("generatedAt"), tz)
    age = (now - snap_gen).total_seconds() / 3600 if snap_gen else None
    stale = age is None or age > config.get("staleAfterHours", 24)

    result = {
        "generatedAt": now.isoformat(),
        "snapshot": {"generatedAt": snap_gen.isoformat() if snap_gen else None,
                     "ageHours": round(age, 2) if age is not None else None, "stale": stale},
        "mode": {"lowEnergy": low},
        "current": current,
        "queue": queue,
        "categories": category_summary(rows, config, now, focus_ids),
        "dayLoad": day_load(rows, pins, commitments, config, now),
        "dayLoadByDate": load_by_date(rows, pins, commitments, config, now),
        "activeOverrides": {"pins": len(ov["pins"]), "snoozes": len(snoozed), "skips": len(ov["skips"])},
        "empty": current is None,
    }
    if current is None:
        result["emptyReason"] = empty_reason(rows, snoozed, skips)
    return result, ov


def empty_reason(rows, snoozed, skips):
    if not rows:
        return "Nothing needs you right now. That's allowed."
    if all(r["blocked"] or r["id"] in snoozed or r["id"] in skips for r in rows):
        return "Everything left is parked or waiting; nothing is behind."
    return "Nothing needs you right now. That's allowed."


# ---------------------------------------------------------------- why-lines

def why_line(r, i, eligible, band, pins, skip_kept, escalated_waiting, low, now):
    parts = []
    if band == 1:
        parts.append("Pinned for today.")
        others = [e for e in escalated_waiting if e["id"] != r["id"]]
        if others:
            parts.append(f"{len(others)} more need{'' if len(others) != 1 else 's'} a look, but only when you're ready.")
    elif band == 2:
        if low:
            parts.append(f"Past its deadline ({day_word(r['due'], now)}), so it stays near the top. Take it one small piece at a time.")
        else:
            parts.append(f"Slipped past {day_word(r['due'], now)}. Still worth doing first; it only takes one piece.")
    elif r["reflowed"]:
        parts.append("Carried over to today.")
    elif r["due"]:
        parts.append(f"Due {day_word(r['due'], now)}.")
    else:
        parts.append(f"No deadline, so it comes up in {r['cat']['name']} order.")
    if band in (2, 3) and not r["reflowed"] and i + 1 < len(eligible):
        nxt = eligible[i + 1]
        if nxt["eff"] == r["eff"] and nxt["cat"]["rank"] > r["cat"]["rank"]:
            parts.append(f"Ranked above {nxt['cat']['name']} ({r['cat']['name']} wins ties).")
    if r["id"] in skip_kept:
        parts.append("Skipped today, but it is the only urgent deadline.")
    if low and band in (3, 4) and not (r["hard"] and r["due"] <= now + timedelta(hours=24)):
        parts.append(f"Low-energy mode: short task (~{fmt_dur(r['minutes'])}).")
    return " ".join(parts)


# ---------------------------------------------------------------- summaries

def load_by_date(rows, pins, commitments, config, now):
    """Day-load level for today and tomorrow (tomorrow measured from 07:00, so its window is the full day).
    Lets the morning ping (and the cloud copy, which only has the last sync) know what a given date looks like."""
    nxt = start_of_day(now) + timedelta(days=1, hours=7)
    return {now.date().isoformat(): day_load(rows, pins, commitments, config, now)["level"],
            nxt.date().isoformat(): day_load(rows, set(), commitments, config, nxt)["level"]}


def category_summary(rows, config, now, focus_ids=None):
    names = [c["name"] for c in config["categories"]]
    if any(r["cat"]["name"] == "Other" for r in rows):
        names.append("Other")
    out = []
    for name in names:
        mine = [r for r in rows if r["cat"]["name"] == name]
        cat = next((c for c in config["categories"] if c["name"] == name), {})
        focus_id = (focus_ids or {}).get(name) if cat.get("focus") else None
        out.append({
            "name": name, "open": 1 if focus_id else len(mine),
            **({"focusId": focus_id, "later": len(mine) - 1} if focus_id else {}),
            "escalated": sum(1 for r in mine if r["escalated"]),
            "dueToday": sum(1 for r in mine if r["due"] and not r["escalated"]
                            and start_of_day(now) <= r["due"] < end_of_day(now)),
        })
    return out


def day_load(rows, pins, commitments, config, now):
    wd = config.get("workday", {"start": "09:00", "end": "21:00"})
    tz = now.tzinfo
    win_start, win_end = max(clock(now, wd["start"]), now), clock(now, wd["end"])
    free = 0.0
    if win_end > win_start:
        busy = []
        for c in commitments or []:
            s, e = parse_dt(c["start"], tz), parse_dt(c["end"], tz)
            s, e = max(s, win_start), min(e, win_end)
            if e > s:
                busy.append((s, e))
        busy.sort()
        merged = []
        for s, e in busy:
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            else:
                merged.append((s, e))
        free = (win_end - win_start).total_seconds() / 60 - sum((e - s).total_seconds() / 60 for s, e in merged)
    planned = sum(r["minutes"] for r in rows
                  if not r["blocked"] and ((r["hard"] and r["due"] < end_of_day(now)) or r["id"] in pins))
    free = int(round(free))
    ratio = round(planned / free, 2) if free > 0 else None
    th = config.get("dayLoadThresholds", {"light": 0.4, "heavy": 0.8})
    if ratio is None:
        level = "heavy" if planned > 0 else "light"
    elif ratio < th["light"]:
        level = "light"
    elif ratio > th["heavy"]:
        level = "heavy"
    else:
        level = "normal"
    return {"freeMinutes": free, "plannedMinutes": planned, "ratio": ratio, "level": level}
