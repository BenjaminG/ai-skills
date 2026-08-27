---
name: babysit-prs
description: Drive every open PR to merge-ready on a self-paced loop, with no `/loop` wrapper. Each tick triages through `pr-feedback --auto confirmed`, which answers and folds through `pr-respond` and `fixup`, then waits for CI and new reviews and goes again until the PR is green. Use when asked to babysit, watch, or surveiller open PRs, or to keep them moving until they can merge.
argument-hint: "[--once] [--every <interval>]"
---

# Babysit PRs

Keep open PRs moving without polling them by hand. This skill owns the scan, the waiting, and the stopping. Every judgment about the code belongs to the skills it calls.

## Each tick

1. List the PRs still in flight:

   ```bash
   gh pr list --author "@me" --state open --json number,url,title,isDraft
   ```

   None left? Say so and stop the loop.

2. Per PR, invoke `pr-feedback <n> --auto confirmed`. It fetches, adjudicates, and hands off to `pr-respond`, which applies the agreed changes, folds them through `fixup`, pushes, then replies and resolves. Don't re-fetch threads, re-classify, or draft replies here. All of that lives downstream, and duplicating it is how the two drift apart.

   `--auto confirmed` draws the line. Nits and confirmed items go through unattended. Unclear items, refuted-but-blocking ones, and any merge decision come back held. Report held items, never act on them.

3. Report the tick as one table, one row per PR:

   | PR | Mergeable | CI | Answered | Held | New |
   |---|---|---|---|---|---|
   | `#num` | `mergeable` + `mergeStateStatus` | `gh pr checks <n>` rollup, failures first | items closed out this tick | items waiting on the user, one gist each | new comments and reviews since last tick, `—` if none |

   A PR that is `CLEAN`, green on every check, and holding nothing is merge-ready. Notify via `PushNotification` (`ToolSearch "select:PushNotification"`) and drop it from the loop. The merge itself is the user's.

4. Wait. End the turn with `ScheduleWakeup`, always, including a turn that ends on a held item or a `fixup` blocker. A turn that ends without an armed wakeup kills the loop.

   ```
   ScheduleWakeup({ prompt: "/babysit-prs", delaySeconds: 300, noop: <nothing changed?>, reason: "<what you're waiting on>" })
   ```

   Use `300` while CI runs or reviews are expected. That is the cadence this loop is built around. Stretch to `1200` or `1800` once every remaining PR is held on the user, since nothing will move until they answer. `--every <interval>` pins it.

   Set `noop: true` on a tick where nothing changed, `false` when something moved.

## Stopping

Call `ScheduleWakeup({ stop: true })` and don't re-arm when every PR is merge-ready or closed, when `--once` was passed (never arm at all), or when the user says stop.

Everything else keeps ticking. A held item and a rebase conflict both mean report and come back, not give up.

## What lives where

| Concern | Skill |
|---|---|
| Fetching threads, verdicts, P1/P2/Nit | `pr-feedback` |
| Code changes, replies, reactions, resolving | `pr-respond` |
| Finding the introducing commit, fold, force-push | `fixup` |
| Restacking children after a fold | `gh-stack` |
| Scanning, cadence, stopping | here |

Loop state lives in this conversation, not on disk, so the ticks have to stay in one session. A tick that has forgotten the last one re-triages from scratch, which costs tokens, not correctness.
