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

2. **Read each PR's standing state, then the delta.** Two things, in this order — the delta alone is a trap: a backlog of unresolved threads that predates the loop never changes, so a delta-only tick reports `—` while comments pile up unanswered.

   **a. Standing count (every tick, regardless of change).** Per PR, count **open review threads** — `isResolved == false` and `isOutdated == false` — split by author type. One GraphQL call gives both the count and the authors:

   ```bash
   gh api graphql -f query='query($owner:String!,$repo:String!,$pr:Int!){
     repository(owner:$owner,name:$repo){ pullRequest(number:$pr){
       reviewThreads(first:100){ nodes{ isResolved isOutdated
         comments(first:1){ nodes{ author{login __typename} } } } } } }
   }' -F owner=OWNER -F repo=REPO -F pr=<n>
   ```

   **b. Mergeability + CI (every tick).** `gh pr view <n> --json mergeable,mergeStateStatus` for the merge state, and `gh pr checks <n>` for the CI rollup — count conclusions (`pass` / `fail` / `pending` / `skipping`). Report the raw numbers, not a synthesized verdict.

   **c. Delta.** *Then* diff against last tick — which of those threads, reviews, checks, or mergeable state are new since the previous pass.

   > Loop state lives in this conversation, not on disk. If a tick has no memory of the last one, re-triaging from scratch is safe: `/pr-feedback` is read-only, so a repeat pass costs tokens, not correctness. This is the **waiting** ceiling — accept it rather than building a state store.

   **Author type is a label, not a filter.** Mark an author 🤖 when GraphQL `author{ __typename }` is `Bot`, OR the login ends in `[bot]`, OR it's a known bot account (`naboo-ai-reviews`, `cursor`/Bugbot); everyone else is 👤. **Never drop bot activity** — bot findings are shown alongside human ones. This composes with `/pr-feedback`, which does no author typing of its own.

3. **Triage new activity** through `/pr-feedback` (classifies P1 / P2 / Nit).

4. **Emit the tick report.** One table, one row per PR — standing backlog *and* activity, not just state, so neither a fresh comment nor a pile of unanswered ones can hide behind `—`:

   | Colonne | Contenu |
   |---|---|
   | **PR** | `#num` + state glyph (✅ ready / ⚠️ problème / 🚧 draft/WIP) |
   | **Mergeable** | `mergeable` + `mergeStateStatus` from step 2b, e.g. `✅ CLEAN`, `⚠️ BEHIND` (rebase), `⛔ BLOCKED`, `❌ DIRTY` (conflicts) |
   | **CI** | check rollup from step 2b — surface failures first: `❌ 1 fail · 2 pending · 43 pass` (skipping omitted unless it's all there is). `✅ all pass` when green. |
   | **À répondre** | standing count of open threads (step 2a), split e.g. `👤 2 · 🤖 6`; `0` when the PR is clean. This is the number that persists across ticks — never `—` just because nothing changed. |
   | **Nouveau** | delta only — new comments/reviews *this* tick, each `👤 <login>` or `🤖 <login>` + ≤5-word gist; `—` when nothing new since last tick. |
   | **P1/P2/Nit** | count of open actionable items from the `/pr-feedback` triage (the table links to the triage, it doesn't replace it) |

   Then act:
   - **Nits and clear agreements** → batch through `/pr-respond` (mechanical — it already gates on one confirmation and runs replies through humanizer).
   - **Which P1 / P2 to actually fix** → surface it and **STOP**. That choice is the user's.

5. **Notify** on the events worth coming back for, via `PushNotification` (load it first: `ToolSearch "select:PushNotification"`):
   - an **APPROVE** → "merge-ready."
   - all checks **green** / PR ready for human review.
   - After a push answering feedback: notify **"re-solicit the reviewer"** — do **not** re-request review on GitHub and do **not** ping Slack. The user re-solicits.

## Cadence

Launch with `/loop /babysit-prs` (~20 min is plenty for review latency). In dynamic mode, tighten the interval when a PR is close to **green** and loosen it otherwise via `ScheduleWakeup`.
