---
name: pr-respond
description: This skill should be used after pr-feedback triage, when the user has picked which review items to act on and wants them applied and answered — apply the agreed code change per item, then post the reply, reaction, and (for inline threads) thread resolution in one confirmed batch. Triggers on "apply the PR feedback", "respond to the reviewers", "resolve the threads", "post my replies", or selecting items after a pr-feedback report.
argument-hint: "[items — e.g. 'all P1' | 'all' | specific item numbers]"
---

# PR Respond

Apply the agreed code changes for the review items the user picked, then post the reply, reaction, and (for inline threads) thread resolution — all after a single confirmation.

## Prerequisites

This skill consumes the prior `pr-feedback` triage from the conversation. Each selected item carries:

- **disposition** — fix (apply the change) / reply (answer, no change) / decline (won't fix) / defer (track for later)
- **inline-thread `id`** — GraphQL node id (from §2 of pr-feedback), needed to resolve the thread
- **first-comment `databaseId`** — needed for the reply and reaction endpoints
- **`owner` / `repo` / PR number**

If that context is absent (no triage in this conversation), run `pr-feedback` first — this skill does not re-fetch.

**Selecting is not forcing a fix.** "apply all" / "apply all P1" / picking items means *act on each per its disposition* — only `fix` items get a code change. The verb `fix` is reserved for actually changing code; it is never how the user selects items. When the user's instruction contradicts a disposition (e.g. "apply all" over a `decline` item), the **disposition wins** — flag the mismatch in the batch preview ("you said apply, but this was recommended `decline`: replying without a code change — say so if you want to force a fix") rather than silently editing.

Replies are drafted through the `humanizer` skill (see below) — that dependency is mandatory, not optional.

## The loop

`disposition` drives each item. Process in priority order (P1 → P2 → Nit), batching edits by file. Per item:

1. **Apply** — for `fix`, make the agreed code change. Skip the edit for `reply`, `decline`, and `defer`.
2. **Draft the reply** — a 1–3 sentence reply stating what was done (applied + how) or why it was declined. Route it through the `humanizer` skill. **Never post a raw draft — always route it through humanizer first.**
3. **Pick the reaction** — `fix` / agreed → 👍 (`+1`); `decline` → 👎 (`-1`). `reply` / `defer` → no reaction unless you're agreeing.
4. **Add to the batch preview** — per thread: the drafted reply, the planned reaction, and whether it will be resolved.

Show the **one batch preview**, then post everything only after a **single** confirmation.

**Done when** every selected item has been either applied-and-answered or explicitly skipped with its reason, *and* the summary lists each item's outcome (reply posted / reaction set / thread resolved-or-not). Don't stop before every picked item is accounted for.

## Posting (after confirmation)

- **Reply — inline review thread:** `gh api repos/{owner}/{repo}/pulls/<n>/comments -f body='…' -F in_reply_to=<databaseId>`
- **Reply — conversation / issue comment (e.g. some bugbot posts):** `gh api repos/{owner}/{repo}/issues/<n>/comments -f body='…'`
- **Reaction — review comment:** `gh api repos/{owner}/{repo}/pulls/comments/<databaseId>/reactions -f content=+1` (or `-1`)
- **Reaction — issue / conversation comment:** `gh api repos/{owner}/{repo}/issues/comments/<databaseId>/reactions -f content=+1` (or `-1`)
- **Resolve — inline threads only:** `gh api graphql -f query='mutation($id:ID!){ resolveReviewThread(input:{threadId:$id}){ thread{ isResolved } } }' -f id=<thread-id>` using the thread `id` from triage.

Notes:

- Issue-level conversation comments have no thread and **cannot be resolved** — reply + react only, and say so in the summary.
- CI-check items have nothing to reply to; they're fixed by editing code, not by posting.
