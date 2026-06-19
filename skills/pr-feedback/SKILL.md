---
name: pr-feedback
description: This skill should be used when the user wants to triage a pull request's review feedback and CI status — retrieving inline review comments, review summaries, conversation comments, and failing status checks, then classifying each item as P1 / P2 / Nit and proposing an ordered action plan. Triggers on "review PR feedback", "check PR comments", "what's blocking my PR", "classify review comments", "PR CI failures", "triage PR", or a bare PR number/URL.
argument-hint: "[pr-number-or-url]"
---

# PR Feedback Triage

Retrieve review feedback and status checks for a pull request, classify each item by priority, and propose an ordered action plan. Triage (§1–§5) is read-only — do not edit files, post replies, or re-run CI until the user picks items. Once they do, §6 applies the agreed changes and posts responses (reply + reaction + resolve) after a single confirmation. Never re-run CI.

## 1. Resolve the PR

- If the argument is a PR number or URL, use it.
- Otherwise, detect from the current branch: `gh pr view --json number,url,headRefName,baseRefName,state`.
- State the resolved PR (`#<n> — <url>`) so the user can confirm.

## 2. Fetch feedback and checks

Run these in parallel (single message, multiple tool calls). Cap any log output aggressively.

- **Inline review comments (threaded):** `gh pr view <n> --json reviewThreads` — keep `isResolved`, `isOutdated`, path, line, comments[].author/body.
- **Thread IDs (needed only if §6 will resolve threads):** `gh pr view --json reviewThreads` omits the GraphQL node `id` required to resolve a thread. Fetch it (plus each first comment's `databaseId` for reply/reaction endpoints) with:

  ```bash
  gh api graphql -f query='query($owner:String!,$repo:String!,$pr:Int!){
    repository(owner:$owner,name:$repo){ pullRequest(number:$pr){
      reviewThreads(first:100){ nodes{ id isResolved isOutdated
        comments(first:1){ nodes{ databaseId author{login} body path } } } } } }
  }' -F owner=OWNER -F repo=REPO -F pr=<n>
  ```
- **Review summaries:** `gh pr view <n> --json reviews` — state (APPROVED / CHANGES_REQUESTED / COMMENTED), author, body.
- **Conversation comments:** `gh api repos/{owner}/{repo}/issues/<n>/comments` (owner/repo from step 1).
- **Status checks:** `gh pr checks <n>`. For each FAIL, fetch a short log tail: `gh run view --log-failed --job <job-id> | tail -n 50`.

Skip threads where `isResolved` or `isOutdated` is true, unless a later comment flags a regression.

## 3. Classify each item as P1 / P2 / Nit

- **P1 — blocking:** failing required checks; correctness / security bugs; reviewer submitted CHANGES_REQUESTED on this item; missing tests for new behavior.
- **P2 — important, non-blocking:** design concerns, maintainability, perf tradeoffs, ambiguous behavior, reviewer questions that need an answer before merge.
- **Nit:** naming, formatting, phrasing, optional refactors, style preferences. Clues: comment starts with `nit:`, `optional:`, `consider`, `suggestion:`, or is purely taste.

When in doubt, prefer the higher priority and note the uncertainty.

## 4. Emit the report

Group by priority (P1 → P2 → Nit). One entry per item:

- **Priority** — P1 / P2 / Nit
- **Source** — review-comment | review-summary | conversation | check
- **Where** — `path/to/file.ts:42` or check name
- **Author** — reviewer / bot
- **Quote** — ≤2 lines from the comment or check failure
- **Why** — one sentence on the classification
- **Proposed action** — fix | reply | defer | dismiss

## 5. Action plan

After the report, emit an ordered plan:

1. P1 items first, grouped by file when multiple items touch the same file (so edits batch cleanly).
2. Then P2, then Nits.
3. Close with 1–3 sentences summarizing overall health (e.g. "2 P1 CI failures + 1 P1 review comment, 3 P2s, 5 nits").

End with: *"Tell me which items to apply, or say 'all P1' / 'all' to proceed."* Once the user picks items, move to §6.

## 6. Apply & respond

Runs only after the user selects items. Process selected comments in priority order (P1 → P2 → Nit), batching edits by file. For each one:

1. **Apply** the agreed code change. Skip the edit when the disposition is decline / won't-fix, or when the item is a question rather than a change request.
2. **Draft the reply** by invoking the `humanizer` skill on a 1–3 sentence reply that states what was done (applied + how) or why it was declined. Never post a raw draft — always route it through humanizer first.
3. **Pick the reaction:** applied or agreed → 👍 (`+1`); declined / won't-fix → 👎 (`-1`).
4. **Show one batch preview** — per thread: the drafted reply, the planned reaction, and whether it will be resolved. Post everything only after a **single** confirmation.

After confirmation, post per comment:

- **Reply — inline review thread:** `gh api repos/{owner}/{repo}/pulls/<n>/comments -f body='…' -F in_reply_to=<databaseId>`
- **Reply — conversation / issue comment (e.g. some bugbot posts):** `gh api repos/{owner}/{repo}/issues/<n>/comments -f body='…'`
- **Reaction — review comment:** `gh api repos/{owner}/{repo}/pulls/comments/<databaseId>/reactions -f content=+1` (or `-1`)
- **Reaction — issue / conversation comment:** `gh api repos/{owner}/{repo}/issues/comments/<databaseId>/reactions -f content=+1` (or `-1`)
- **Resolve — inline threads only:** `gh api graphql -f query='mutation($id:ID!){ resolveReviewThread(input:{threadId:$id}){ thread{ isResolved } } }' -f id=<thread-id>` using the thread `id` from §2.

Notes:

- Issue-level conversation comments have no thread and **cannot be resolved** — reply + react only, and say so in the summary.
- CI-check items have nothing to reply to; they're fixed by editing code, not by posting.
