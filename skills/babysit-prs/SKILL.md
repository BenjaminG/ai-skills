---
name: babysit-prs
description: Babysit your open PRs on a loop. Each tick scans your PRs for new reviews, bot comments, and CI, triages via /pr-feedback, batches clear nits through /pr-respond, and PushNotifications on APPROVE or a merge-ready PR. Triggers on "babysit my PRs", "surveille mes PRs", "watch my open PRs".
argument-hint: "[--once]"
disable-model-invocation: true
---

# Babysit PRs

Keep your open PRs moving without polling them by hand. Meant to run on a loop — `/loop /babysit-prs` — one pass per tick; `--once` runs a single pass.

**The boundary, one line:** act without asking only on the **mechanical** (a nit reply through an already-gated skill); every **judgment** (which P1/P2 to fix, the merge) is a **STOP**. This skill composes `/pr-feedback` and `/pr-respond` — it adds no new intelligence, only the scan and the waiting.

## Each tick

1. **List** your open PRs in the current repo:

   ```bash
   gh pr list --author "@me" --state open --json number,url,title
   ```

2. **Diff against last tick.** For each PR, look for what's new since the previous pass — reviews, bot comments, check results, mergeable state.

   > Loop state lives in this conversation, not on disk. If a tick has no memory of the last one, re-triaging from scratch is safe: `/pr-feedback` is read-only, so a repeat pass costs tokens, not correctness. This is the **waiting** ceiling — accept it rather than building a state store.

3. **Triage new activity** through `/pr-feedback` (classifies P1 / P2 / Nit). Then:
   - **Nits and clear agreements** → batch through `/pr-respond` (mechanical — it already gates on one confirmation and runs replies through humanizer).
   - **Which P1 / P2 to actually fix** → surface it and **STOP**. That choice is the user's.

4. **Notify** on the events worth coming back for, via `PushNotification` (load it first: `ToolSearch "select:PushNotification"`):
   - an **APPROVE** → "merge-ready."
   - all checks **green** / PR ready for human review.
   - After a push answering feedback: notify **"re-solicit the reviewer"** — do **not** re-request review on GitHub and do **not** ping Slack. The user re-solicits.

## Cadence

Launch with `/loop /babysit-prs` (~20 min is plenty for review latency). In dynamic mode, tighten the interval when a PR is close to **green** and loosen it otherwise via `ScheduleWakeup`.
