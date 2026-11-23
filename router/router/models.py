"""Pick models from OpenCode's live catalog. Nothing here hardcodes a model roster:
the config only holds policy (exclusions, which family is which tier)."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field

MULT_RE = re.compile(r"\(([\d.]+)\s*[x×]\)")


@dataclass
class Model:
    provider: str
    id: str
    name: str
    family: str | None
    variants: list[str]
    inputs: list[str]
    released: int
    free: bool
    multiplier: float | None = None

    @property
    def key(self) -> str:
        return f"{self.provider}/{self.id}"


@dataclass
class Roster:
    free: list[Model] = field(default_factory=list)
    claude: dict[str, Model] = field(default_factory=dict)  # tier -> model
    excluded: list[str] = field(default_factory=list)


def _to_model(raw: dict) -> Model:
    costs = raw.get("cost") or []
    free = bool(costs) and all((c.get("input") or 0) == 0 and (c.get("output") or 0) == 0 for c in costs)
    m = MULT_RE.search(raw.get("name") or "")
    return Model(
        provider=raw["providerID"],
        id=raw["id"],
        name=raw.get("name") or raw["id"],
        family=raw.get("family"),
        variants=[v["id"] for v in raw.get("variants") or []],
        inputs=(raw.get("capabilities") or {}).get("input") or ["text"],
        released=(raw.get("time") or {}).get("released") or 0,
        free=free,
        multiplier=float(m.group(1)) if m else None,
    )


def _excluded(model: Model, cfg: dict) -> str | None:
    for pat in cfg.get("excluded_models", []):
        if fnmatch.fnmatch(model.key, pat):
            return f"excluded by config ({pat})"
    if model.family in cfg.get("excluded_families", []):
        return f"family {model.family} permanently excluded"
    if cfg.get("exclude_fast_variants", True) and model.id.endswith("-fast"):
        return "fast variant excluded"
    return None


def build_roster(raw_models: list[dict], cfg: dict) -> Roster:
    roster = Roster()
    newest: dict[str, Model] = {}
    family_to_tier = {fam: tier for tier, fam in cfg["tier_families"].items()}
    for raw in raw_models:
        if raw.get("enabled") is False or raw.get("status") not in (None, "active"):
            continue
        m = _to_model(raw)
        why = _excluded(m, cfg)
        if why:
            roster.excluded.append(f"{m.key}: {why}")
            continue
        if m.provider == cfg["free_provider"] and m.free:
            roster.free.append(m)
        elif m.provider == cfg["claude_provider"] and m.family in family_to_tier:
            tier = family_to_tier[m.family]
            if tier not in newest or m.released > newest[tier].released:
                newest[tier] = m
    for tier, m in newest.items():
        if m.multiplier is None:
            m.multiplier = cfg["fallback_multipliers"][tier]
        roster.claude[tier] = m
    return roster
