"""Persistent state: usage counter (Step 5), audit scores (validator layer 3),
routing log (Step 6), conversation pinning. All plain JSON/JSONL under router/state/."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

FIVE_HOURS = 5 * 3600
WEEK = 7 * 24 * 3600


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row, default=str) + "\n")


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, default=str))


# ------------------------------------------------------------------ usage
class Usage:
    """Weighted units: each Claude call adds its picker multiplier (Haiku 0.1, Sonnet 2, Opus 4).
    Free calls are counted separately (calls, not units)."""

    def __init__(self, state_dir: Path, warn_limits: dict, now=time.time):
        self.path = state_dir / "usage.jsonl"
        self.plan_path = state_dir / "plan-notice.json"
        self.warn_limits = warn_limits
        self.now = now

    def record_claude(self, tier: str, model: str, multiplier: float, purpose: str, tokens: dict | None = None,
                      cost: float = 0.0) -> None:
        _append(self.path, {"ts": self.now(), "kind": "claude", "tier": tier, "model": model,
                            "units": multiplier, "purpose": purpose, "tokens": tokens or {}, "cost": cost})

    def record_free(self, model: str, outcome: str) -> None:
        _append(self.path, {"ts": self.now(), "kind": "free", "model": model, "outcome": outcome})

    def record_plan_notice(self, notice: str) -> None:
        _write_json(self.plan_path, {"ts": self.now(), "notice": notice})

    def totals(self) -> dict:
        now = self.now()
        midnight = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        windows = {"five_hour": now - FIVE_HOURS, "today": midnight, "week": now - WEEK}
        out = {}
        rows = _read_jsonl(self.path)
        for name, since in windows.items():
            sel = [r for r in rows if r["ts"] >= since]
            claude = [r for r in sel if r["kind"] == "claude"]
            by_tier: dict[str, dict] = {}
            for r in claude:
                t = by_tier.setdefault(r["tier"], {"calls": 0, "units": 0.0})
                t["calls"] += 1
                t["units"] = round(t["units"] + r["units"], 2)
            free = [r for r in sel if r["kind"] == "free"]
            free_by_model: dict[str, dict] = {}
            for r in free:
                m = free_by_model.setdefault(r["model"], {"calls": 0, "rate_limited": 0})
                m["calls"] += 1
                m["rate_limited"] += r["outcome"] == "rate_limit"
            out[name] = {
                "units": round(sum(r["units"] for r in claude), 2),
                "claude_calls": len(claude),
                "by_tier": by_tier,
                "top_tier": max(by_tier, key=lambda k: by_tier[k]["units"]) if by_tier else None,
                "free_calls": len(free),
                "free_by_model": free_by_model,
            }
        out["plan_notice"] = _read_json(self.plan_path, {}).get("notice")
        return out

    def warnings(self, totals: dict | None = None) -> list[str]:
        totals = totals or self.totals()
        warns = []
        for window, key in (("five_hour", "five_hour_units"), ("today", "today_units"), ("week", "week_units")):
            limit = self.warn_limits.get(key)
            if limit is not None and totals[window]["units"] > limit:
                warns.append(f"usage warning: {totals[window]['units']} units in {window.replace('_', '-')} "
                             f"window (limit {limit}); top tier {totals[window]['top_tier']}")
        return warns


# ------------------------------------------------------------------ audits
class Audits:
    """Per model and task type: audit count, mean score, failed audits.
    Also decides whether a result is sampled (all in week one, then 1 in N)."""

    def __init__(self, state_dir: Path, first_week_days: int, sample_every: int, now=time.time):
        self.path = state_dir / "audits.json"
        self.meta_path = state_dir / "meta.json"
        self.first_week = first_week_days * 86400
        self.every = sample_every
        self.now = now

    def should_audit(self) -> bool:
        meta = _read_json(self.meta_path, {})
        if "first_run" not in meta:
            meta["first_run"] = self.now()
        meta["free_results"] = meta.get("free_results", 0) + 1
        _write_json(self.meta_path, meta)
        if self.now() - meta["first_run"] < self.first_week:
            return True
        return meta["free_results"] % self.every == 0

    def record(self, model: str, task_type: str, score, passed: bool) -> None:
        data = _read_json(self.path, {})
        cell = data.setdefault(model, {}).setdefault(task_type, {"n": 0, "score_sum": 0.0, "failed": 0})
        cell["n"] += 1
        cell["score_sum"] += float(score) if isinstance(score, (int, float)) else 0.0
        cell["failed"] += 0 if passed else 1
        _write_json(self.path, data)

    def score(self, model: str, task_type: str, prior: float = 3.5, prior_weight: int = 2) -> float:
        """Smoothed mean audit score (0-5) for this model on this task type, falling back to
        the model's overall record. Unknown models get the prior."""
        data = _read_json(self.path, {}).get(model, {})
        cell = data.get(task_type)
        if not cell:
            n = sum(c["n"] for c in data.values())
            s = sum(c["score_sum"] for c in data.values())
            f = sum(c["failed"] for c in data.values())
        else:
            n, s, f = cell["n"], cell["score_sum"], cell["failed"]
        return (s + prior * prior_weight) / (n + prior_weight) - (f / (n + prior_weight))


# ------------------------------------------------------------------ log
class RoutingLog:
    def __init__(self, state_dir: Path, now=time.time):
        self.path = state_dir / "routing-log.jsonl"
        self.now = now

    def write(self, entry: dict) -> dict:
        entry = {"ts": datetime.fromtimestamp(self.now()).isoformat(timespec="seconds"), **entry}
        _append(self.path, entry)
        return entry

    def tail(self, n: int = 20) -> list[dict]:
        return _read_jsonl(self.path)[-n:]

    def failure_rate(self, model_key: str, days: int = 7) -> float:
        since = datetime.fromtimestamp(self.now()) - timedelta(days=days)
        tries = fails = 0
        for row in _read_jsonl(self.path):
            try:
                if datetime.fromisoformat(row["ts"]) < since:
                    continue
            except (KeyError, ValueError):
                continue
            for a in row.get("attempts", []):
                if a.get("model") == model_key:
                    tries += 1
                    fails += a.get("outcome") != "ok"
        return fails / tries if tries else 0.0


# ------------------------------------------------------------------ conversations
class Conversations:
    """Stay on one model within a conversation unless it failed or Morgan overrides."""

    def __init__(self, state_dir: Path):
        self.path = state_dir / "conversations.json"

    def get(self, conv_id: str) -> dict | None:
        return _read_json(self.path, {}).get(conv_id)

    def set(self, conv_id: str, tier: str, model: str, effort: str | None, session_id: str | None) -> None:
        data = _read_json(self.path, {})
        data[conv_id] = {"tier": tier, "model": model, "effort": effort, "session_id": session_id}
        _write_json(self.path, data)

    def drop(self, conv_id: str) -> None:
        data = _read_json(self.path, {})
        data.pop(conv_id, None)
        _write_json(self.path, data)
