# Phase 6 state model: Text push

Status: DRAFT for Morgan's review, 2026-11-05. Nothing is built yet. Blocked on one decision (section 1).

## 0. Shape

One-way nudges only. Answers, snoozes and check-ins happen in the dashboard (decided 2026-11-05). Two senders share one decision function so they can never disagree:

    decide(recommendation, pushState, presence, config, now) -> [ping] | []

- **Local pusher** (Python stdlib, launchd, every minute): runs while the Mac is awake. Uses the engine output directly.
- **Cloud pusher** (small scheduled job): runs while the Mac is off. Reads the synced snapshot, runs the same engine code and `decide()`, sends via the cloud channel.
- No model calls. No replies read.

## 1. Decision needed: the laptop-off channel

| Option                 | Cost                           | Setup                                      | Notes                                                                                                   |
| ---------------------- | ------------------------------ | ------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| **ntfy** (recommended) | free                           | install app, pick a long random topic name | One-way push, exactly what is needed. Topic name acts as the secret, so keep it in config, not in docs. |
| Pushover               | one-time ~$5                   | account + app                              | Most reliable delivery, token-based.                                                                    |
| Twilio SMS             | monthly + carrier registration | heavy                                      | Real texts, but costs money and has setup friction.                                                     |
| iMessage               | free                           | already works                              | Mac must be awake and signed in; cannot run from the cloud. Keep for awake-Mac use only if wanted.      |

Recommendation: ntfy for both senders (one channel, one code path). Add iMessage on the local sender only if Morgan prefers it while the Mac is awake.

Second decision: the cloud runner and snapshot home. Recommended: a private GitHub repo holding only `queue.json` (see section 3), pushed by a launchd job, read by a GitHub Actions cron (free). Alternative: a Claude scheduled task. Actions is deterministic and costs no Claude usage.

## 2. State and owners

| File                         | Owner                                       | Contents                                                                                    |
| ---------------------------- | ------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `push/state/push-state.json` | pusher (atomic writes)                      | `lastPingAt`, `lastPingKey`, `lastBlock`, `lastOnlineAt`, `failureAlertedFor`               |
| `push/state/presence.json`   | dashboard server (new `POST /api/presence`) | `lastSeen` timestamp, written only while the page is visible                                |
| `push/config.json`           | Morgan                                      | channel, topic, recipient, `capMinutes` (60), `presenceSeconds` (90), quiet hours           |
| `push/state/queue.json`      | local sync job                              | thin snapshot: top N ranked items, why-lines, block end time, `generatedAt`, `lastImportAt` |

Cloud pusher keeps its own `push-state` in the private repo (committed back) so the hourly cap holds across runs.

## 3. Thin snapshot (laptop to cloud)

`queue.json` holds only: `generatedAt`, `lastImportAt`, current recommendation (title, category, why), next 3 titles, `currentBlockEnd` if any, `stale` flag. No notes, no full task list. Pushed whenever the engine output changes, plus every 10 minutes while the Mac is on.

## 4. Ping decision rules

Ping types: `start` ("time for X"), `stop` ("stop X, take a break"), `failure` (import failed or stale over a day), `catchup` (first ping after being offline).

`decide()` returns a ping only if all hold:

1. A transition happened: top recommendation key changed, a block ended, or a failure condition appeared (not a fixed interval).
2. **Presence:** `now - presence.lastSeen > presenceSeconds` (dashboard not being watched). If watched, nothing is sent and the dashboard shows the prompt.
3. **Cap:** `now - lastPingAt >= capMinutes`. Exception: `failure` pings bypass the cap but fire once per failure.
4. Not inside quiet hours.
5. Not a repeat: `lastPingKey` differs from this ping's key.

Capped transitions are not queued as a backlog: when the cap clears, only the current state is considered.

## 5. Catch-up

If `lastOnlineAt` (last time local engine ran) is older than 6 hours when a ping becomes due, send one `catchup` ping instead: "N due today, top: X". Never replay missed pings.

## 6. Failure alerts

`failure` fires when `now - lastImportAt > 24h` or the snapshot is stale beyond `staleAfterHours`. One text per incident (tracked in `failureAlertedFor`), cleared on recovery. The cloud pusher also alerts if `queue.json` itself is over 24 hours old (Mac off for a long stretch), once.

## 7. Failure handling in the pusher

- Send error: logged to `push/state/push.log`, retried next tick, never marks the ping as sent.
- Unreadable snapshot or config: log and skip; one `failure` ping if it persists over a day.
- Missing presence file: treated as "away".

## 8. Tests planned

Seeded tests with a fake clock: ping on transition; none while present; none inside the cap; failure bypasses cap once; catch-up after offline gap; quiet hours; repeated key suppressed; send failure not marked sent; cloud run from `queue.json` gives the same decision as the local run on identical input.

## 9. Build order

1. `decide()` + tests (no I/O). 2. Presence endpoint + page heartbeat. 3. Local pusher + launchd. 4. `queue.json` sync. 5. Cloud pusher. 6. Live check: trigger a ping, open the dashboard (no text), test the cap, turn the Mac's sender off and confirm the cloud text.
