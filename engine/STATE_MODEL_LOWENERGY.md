# Low-energy day (Phase 14)

Morgan's choices (2026-11-07): shorter blocks, gentler breaks, softer wording. Urgent window stays 24h. Pings are NOT changed.

State: `mode.lowEnergy` (engine overrides, resets at midnight). Everything below reads it from the recommendation (`rec.mode.lowEnergy`).

| Area | Normal | Low energy |
|---|---|---|
| Queue order | deadline, category | urgent (hard, due in 24h) first, then shortest first (already built) |
| Work block length | 10-50 min | 10-`lowEnergy.blockMaxMinutes` (20); longer tasks take more blocks |
| Break length | light 45 / normal 25 / heavy 10 | `lowEnergy.breakMinutes`: light 45 / normal 30 / heavy 20 |
| Past-deadline wording | "Missed deadline ..." | "Past its deadline, so it stays near the top. Take it one small piece at a time." |
| Thalamus brain | "missed" mood if anything escalated | calm mood; labels say "past due" |
| Pings | unchanged | unchanged |

Config: `engine/config.json` -> `lowEnergy`. Tests: engine + blocks.
