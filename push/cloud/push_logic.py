"""Pure ping decision. No I/O, no clock reads: everything arrives as arguments.

    decide(rec, state, last_seen, health, config, now, block=None) -> (ping | None, new_state)

`new_state` is only meant to be saved AFTER the ping was sent successfully.
Ping types: start, stop, breakend, failure, catchup, morning.
"""
from __future__ import annotations

from datetime import datetime, timedelta

DEFAULTS = {
    "capMinutes": 60,
    "presenceSeconds": 90,
    "quietHours": {"start": "22:30", "end": "07:30"},
    "catchupAfterHours": 6,
    "staleImportHours": 24,
    "morning": {"from": "08:00", "until": "11:00"},
    # Rotates by date (same pick on the Mac and in the cloud). Keep each one short; mix movement, outside, play.
    "morningTexts": [
        "Light day today. Go touch some grass: golf, a walk, anything outside.",
        "Easy day ahead. Get a workout in, then do something just for fun.",
        "Not much on today. Walk, golf or a game, your pick.",
        "Wide open day. Move your body first, the rest can be yours.",
        "Light one today. A few holes of golf would fit nicely.",
        "Lots of room today. Get outside for a bit, then take your time.",
        "Breathing room today. Workout, walk or a couple of hours on a project you like.",
    ],
}


def fmt_dur(m):
    m = int(round(m))
    h, r = divmod(max(m, 0), 60)
    return f"{h} h {r} min" if h and r else (f"{h} h" if h else f"{r} min")


def reminder_text(r, at, now):
    if r.get("followUp"):
        return f"Still on your list: {r['text']}."
    late = (now - at).total_seconds() > 15 * 60
    when = at.strftime("%-I:%M %p").lstrip("0")
    return f"Reminder: {r['text']}." if not late else f"Reminder (set for {when}): {r['text']}."


def habit_text(h):
    goal = " ".join(str(h.get("notes") or "").split()).rstrip(". ")
    for lead in ("my goal is to ", "my goal is ", "goal: ", "i want to "):
        if goal.lower().startswith(lead):
            goal = goal[len(lead):]
    goal = (goal[:1].upper() + goal[1:] + ". ") if goal else ""
    mins = h.get("minutes")
    amount = "one" if not mins else ("hour" if mins == 60 else f"{mins} minutes" if mins < 60 else f"{mins // 60} h {mins % 60} min" if mins % 60 else f"{mins // 60} hours")
    return f"{h['title']}: want your {amount} for today? {goal}No pressure."


def checkin_text(h, now):
    """A daily check-in on a due task: names the due day, no streaks, no pressure."""
    try:
        left = (datetime.fromisoformat(h["until"]).date() - now.date()).days
        when = "today" if left <= 0 else "tomorrow" if left == 1 else datetime.fromisoformat(h["until"]).strftime("%A")
    except (KeyError, ValueError):
        when = "soon"
    return f"Check-in: {h['title']} is due {when}. Have you worked on it? No pressure."


def morning_text(config, now):
    if config.get("morningText"):          # an explicit single text in config still wins
        return config["morningText"]
    texts = cfg(config, "morningTexts")
    return texts[now.date().toordinal() % len(texts)]


def cfg(config, key):
    return config.get(key, DEFAULTS[key])


def follow_slots(first, config):
    """Send times for a text she asked for: the first at `first` (HH:MM), then follow-ups every gapHours, three in all,
    never into quiet hours or past midnight."""
    fu = config.get("followUps") or {}
    count, gap = int(fu.get("count", 3)), int(fu.get("gapHours", 4))
    quiet = config.get("quietHours", DEFAULTS["quietHours"]) or {}
    limit = (lambda t: t.hour * 60 + t.minute)(datetime.strptime(quiet.get("start", "22:30"), "%H:%M").time())
    h, m = (int(x) for x in first.split(":"))
    out = []
    for i in range(count):
        mins = h * 60 + m + gap * 60 * i
        if i and mins >= limit:
            break
        out.append(f"{mins // 60:02d}:{mins % 60:02d}")
    return out


def in_quiet(now, quiet):
    if not quiet:
        return False
    s = datetime.strptime(quiet["start"], "%H:%M").time()
    e = datetime.strptime(quiet["end"], "%H:%M").time()
    t = now.timetz().replace(tzinfo=None)
    return (s <= t or t < e) if s > e else (s <= t < e)


def watched(last_seen, config, now):
    """Dashboard counts as watched while its heartbeat is recent. Missing = away."""
    return last_seen is not None and (now - last_seen).total_seconds() <= cfg(config, "presenceSeconds")


def failure_key(health, rec, config):
    """Returns (key, text) when something needs an alert, else None. One key per incident."""
    if health.get("importFailed"):
        return "import-failed:" + str(health.get("importFailedKey", "")), "Import failed. Open the brain to see which file."
    hrs = cfg(config, "staleImportHours")
    if health.get("importAgeHours") is not None and health["importAgeHours"] > hrs:
        return "import-stale", f"No import for over {hrs} hours. Is QuickToDo running?"
    if rec and rec.get("snapshot", {}).get("stale"):
        return "snapshot-stale", "Task snapshot is over a day old. Is QuickToDo running?"
    return None


def decide(rec, state, last_seen, health, config, now, block=None):
    st = dict(state)
    st.setdefault("failureAlertedFor", None)
    fail = failure_key(health, rec, config)
    if fail is None:
        st["failureAlertedFor"] = None  # recovered: next incident alerts again

    # Failure alerts bypass the cap, fire once per incident, still respect presence and quiet hours.
    if fail and st["failureAlertedFor"] != fail[0] and not watched(last_seen, config, now) \
            and not in_quiet(now, config.get("quietHours", DEFAULTS["quietHours"])):
        st["failureAlertedFor"] = fail[0]
        st["lastPingAt"] = now.isoformat()
        return {"type": "failure", "key": fail[0], "title": "Thalamus", "text": fail[1]}, st

    # Morning nudge: once a day, only on a light day, inside the morning window. Not a transition, so no cap
    # check, but it sets lastPingAt so the next "start" ping waits out the cap. Respects presence and quiet hours.
    mw = cfg(config, "morning")
    today = now.date().isoformat()
    if mw and st.get("morningSentOn") != today and rec \
            and (rec.get("dayLoadByDate") or {}).get(today) == "light" \
            and datetime.strptime(mw["from"], "%H:%M").time() <= now.timetz().replace(tzinfo=None) < datetime.strptime(mw["until"], "%H:%M").time() \
            and not watched(last_seen, config, now) \
            and not in_quiet(now, config.get("quietHours", DEFAULTS["quietHours"])):
        st["morningSentOn"] = today
        st["lastPingAt"] = now.isoformat()
        return {"type": "morning", "key": "morning:" + today, "title": "Thalamus",
                "text": morning_text(config, now)}, st

    # Reminders she asked for: sent at their time. Explicit requests, so presence, quiet hours and the hourly cap do not apply,
    # and they do not reset the cap for other pings. Each is sent once (reminderSent keeps the ids until the store drops them).
    fired = set(st.get("reminderSent") or [])
    for r in ((rec or {}).get("reminders") or []):
        if r["id"] in fired:
            continue
        try:
            at = datetime.fromisoformat(r["at"])
        except (KeyError, ValueError):
            continue
        if at > now:
            continue
        fired.add(r["id"])
        st["reminderSent"] = sorted(fired)[-200:]
        return {"type": "reminder", "key": "reminder:" + r["id"], "title": "Thalamus", "text": reminder_text(r, at, now)}, st

    # Daily habit nudge (Play): once a day per habit, from its nudge time, only if today's one is not done.
    # Gentle on purpose: no streaks, no "you missed". Respects presence, quiet hours and the hourly cap.
    last_ping = datetime.fromisoformat(st["lastPingAt"]) if st.get("lastPingAt") else None
    capped = bool(last_ping and (now - last_ping) < timedelta(minutes=cfg(config, "capMinutes")))
    sent = dict(st.get("habitSent") or {})
    for h in ((rec or {}).get("habits") or []):
        text_only = bool(h.get("textOnly"))      # a repeating text reminder: no done-state, no cap, no presence check
        follow = text_only or bool(h.get("until"))      # reminders and check-ins she asked for follow up; Play offers stay once a day
        slots = follow_slots(h.get("nudgeAt", "09:00"), config) if follow else [h.get("nudgeAt", "09:00")]
        got = str(sent.get(h["id"]) or "")
        n_sent = 0 if not got.startswith(today) else (int(got.split("#")[1]) if "#" in got else 1)
        due_n = sum(1 for t in slots if now.strftime("%H:%M") >= t)       # slots already reached; missed ones are skipped, not replayed
        if (h.get("doneToday") and not text_only) or n_sent >= due_n or (capped and not text_only) \
                or now.weekday() not in h.get("days", range(7)):
            continue
        if h.get("until") and not (h.get("startOn", today) <= today <= h["until"]):
            continue                      # a check-in runs from its start day through the due day only
        if not text_only and (watched(last_seen, config, now) or in_quiet(now, config.get("quietHours", DEFAULTS["quietHours"]))):
            break
        sent[h["id"]] = f"{today}#{due_n}"
        st["habitSent"] = {k: v for k, v in sent.items() if str(v).startswith(today)}
        if not text_only:
            st["lastPingAt"] = now.isoformat()
        return {"type": "habit", "key": f"habit:{h['id']}:{today}:{due_n}", "title": "Thalamus",
                "text": (("Following up. " if n_sent else "") + checkin_text(h, now)) if h.get("until") else (f"Still on your list: {h['title']}." if n_sent else f"Reminder: {h['title']}.") if text_only else habit_text(h)}, st

    cur = (rec or {}).get("current")
    # Transition keys: stop beats start. A block that ended is a transition; a changed top item is too.
    ping_type, key = None, None
    if block and block.get("endsAt") and datetime.fromisoformat(block["endsAt"]) <= now:
        if block.get("kind") == "break":
            ping_type, key = "breakend", "breakend:" + str(block.get("id", block["endsAt"]))
        else:
            ping_type, key = "stop", "stop:" + str(block.get("id", block["endsAt"]))
    elif cur:
        ping_type, key = "start", "start:" + cur["taskId"]
    if not ping_type or key == st.get("lastPingKey"):
        return None, st
    if watched(last_seen, config, now):
        return None, st
    if in_quiet(now, config.get("quietHours", DEFAULTS["quietHours"])):
        return None, st
    last = datetime.fromisoformat(st["lastPingAt"]) if st.get("lastPingAt") else None
    # breakend is the one nudge that brings her back from a break, so the hourly cap does not apply to it.
    if ping_type != "breakend" and last and (now - last) < timedelta(minutes=cfg(config, "capMinutes")):
        return None, st  # capped; not queued, current state is re-evaluated later

    online = datetime.fromisoformat(st["lastOnlineAt"]) if st.get("lastOnlineAt") else None
    gap = online is not None and (now - online) > timedelta(hours=cfg(config, "catchupAfterHours"))
    if gap and rec:
        text = f"Welcome back. Nothing's lost. One thing to look at: {cur['title']}." if cur else "Welcome back. Nothing urgent."
        ping = {"type": "catchup", "key": key, "title": "Thalamus", "text": text}
    elif ping_type == "breakend":
        ping = {"type": "breakend", "key": key, "title": "Thalamus",
                "text": "Break's done. Whenever you're back, open Thalamus."}
    elif ping_type == "stop":
        ping = {"type": "stop", "key": key, "title": "Thalamus",
                "text": f"That's a good stretch on {block.get('title', 'this block')}. Go be a person for a bit."}
    else:
        ping = {"type": "start", "key": key, "title": "Thalamus",
                "text": f"Ready when you are: {cur['title']} (~{fmt_dur(cur['minutes'])}). {cur['why']}"}
    st["lastPingKey"] = key
    st["lastPingAt"] = now.isoformat()
    return ping, st
