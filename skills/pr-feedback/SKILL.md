---
name: pr-feedback
description: This skill should be used when the user wants to triage a pull request's review feedback and CI status — retrieving inline review comments, review summaries, conversation comments, and failing status checks, then classifying each item as P1 / P2 / Nit and proposing an ordered action plan. Triggers on "review PR feedback", "check PR comments", "what's blocking my PR", "classify review comments", "PR CI failures", "triage PR", or a bare PR number/URL.
argument-hint: "[pr-number-or-url]"
---

# PR Feedback Triage

Retrieve review feedback and status checks for a pull request, classify each item by priority, and propose an ordered action plan. Do not edit files, do not post replies, do not re-run CI.

## 1. Resolve the PR

- If the argument is a PR number or URL, use it.
- Otherwise, detect from the current branch: `gh pr view --json number,url,headRefName,baseRefName,state`.
- State the resolved PR (`#<n> — <url>`) so the user can confirm.

## 2. Fetch feedback and checks

Run these in parallel (single message, multiple tool calls). Cap any log output aggressively.

- **Inline review comments (threaded):** `gh pr view <n> --json reviewThreads` — keep `isResolved`, `isOutdated`, path, line, comments[].author/body.
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

End with: *"Tell me which items to apply, or say 'all P1' / 'all' to proceed."*
