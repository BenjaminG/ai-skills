---
name: babysit-prs
description: Babysit open PRs on a loop — one pass per tick reporting each PR's standing open threads, CI, and mergeability, triaging through `pr-feedback`, batching nits through `pr-respond`, and notifying on approval or merge-ready. Use when asked to babysit, watch, or surveiller open PRs, or to keep checking them on an interval.
argument-hint: "[--once]"
---

# Babysit PRs

Keep open PRs moving without polling them by hand. One pass per tick; `--once` runs a single pass.

**The boundary:** act unasked only on the **mechanical** — a nit reply through an already-gated skill. Every **judgment** — which P1/P2 to fix, the merge — is a **STOP**. This skill composes `pr-feedback` and `pr-respond`; it adds the scan and the **waiting**, no review logic of its own.

## Each tick

1. **List** open PRs in the current repo:

   ```bash
   gh pr list --author "@me" --state open --json number,url,title
   ```

2. **Read the standing state, then the delta.** In that order — **delta** alone is a trap: a backlog that predates the loop never changes, so a delta-only tick reports `—` while comments pile up unanswered.

   **a. Standing open threads** (every tick, changed or not) — `isResolved == false` and `isOutdated == false`, split by author type. One call gives both the count and the authors:

   ```bash
   gh api graphql -f query='query($owner:String!,$repo:String!,$pr:Int!){
     repository(owner:$owner,name:$repo){ pullRequest(number:$pr){
       reviewThreads(first:100){ nodes{ isResolved isOutdated
         comments(first:1){ nodes{ author{login __typename} } } } } } }
   }' -F owner=OWNER -F repo=REPO -F pr=<n>
   ```

   **b. Mergeability + CI** (every tick). `gh pr view <n> --json mergeable,mergeStateStatus` for the merge state, `gh pr checks <n>` for the rollup — count conclusions (`pass` / `fail` / `pending` / `skipping`). Report the raw numbers, not a synthesized verdict.

   **c. Delta** — which of those threads, reviews, checks, or mergeable state are new since the previous pass.

   > Loop state lives in this conversation, not on disk. A tick with no memory of the last one re-triages from scratch, which is safe: `pr-feedback` is read-only, so a repeat pass costs tokens, not correctness. That is the **waiting** ceiling — accept it rather than building a state store.

   **Author type is a label, not a filter.** Mark an author 🤖 when GraphQL `author{ __typename }` is `Bot`, the login ends in `[bot]`, or it's a known bot account (`naboo-ai-reviews`, `cursor`/Bugbot); everyone else is 👤. Report bot findings alongside human ones.

3. **Triage** through `pr-feedback` — **standing**, not delta: every open thread counted in 2a lands in the P1 / P2 / Nit classification, including ones raised before the loop started.

4. **Emit the tick report** — one table, one row per PR, carrying standing backlog *and* activity:

   | Column | Content |
   |---|---|
   | **PR** | `#num` + state glyph (✅ ready / ⚠️ blocked / 🚧 draft) |
   | **Mergeable** | `mergeable` + `mergeStateStatus` from 2b — `✅ CLEAN`, `⚠️ BEHIND` (rebase), `⛔ BLOCKED`, `❌ DIRTY` (conflicts) |
   | **CI** | rollup from 2b, failures first: `❌ 1 fail · 2 pending · 43 pass`; `✅ all pass` when green (omit `skipping` unless it's all there is) |
   | **To answer** | standing open threads from 2a, split e.g. `👤 2 · 🤖 6`; `0` when the PR is clean — this number persists across ticks |
   | **New** | delta only — each new comment/review this tick as `👤 <login>` or `🤖 <login>` + ≤5-word gist; `—` when nothing new since last tick |
   | **P1/P2/Nit** | counts from the step-3 triage; the table links to that triage, it doesn't replace it |

5. **Act**, by the boundary above:

   - Nits and clear agreements → batch through `pr-respond` (**mechanical** — it gates on one confirmation and runs replies through humanizer).
   - Which P1 / P2 to actually fix → surface it and **STOP**. That choice is the user's.

6. **Notify** via `PushNotification` (load it first: `ToolSearch "select:PushNotification"`) on:

   - an **APPROVE** → "merge-ready".
   - all checks green / PR ready for human review.
   - a push answering feedback → "re-solicit the reviewer". Re-soliciting is the user's: leave GitHub review requests and Slack untouched.

## Cadence

`/loop /babysit-prs` — ~20 min matches review latency. In dynamic mode, tighten via `ScheduleWakeup` when a PR is close to **green**, loosen otherwise.
