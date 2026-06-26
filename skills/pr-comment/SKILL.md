---
name: pr-comment
description: This skill should be used when reviewing someone else's pull request and you want to turn gate / gate-wf findings into a posted GitHub review — each comment drafted through humanizer, placed inline at its file:line, and submitted as a single COMMENT review after one confirmation. Triggers on "post these as review comments", "comment the gate findings on the PR", "draft and post my review", "leave review comments", after a gate / gate-wf run on a PR you're reviewing.
argument-hint: "[pr-number-or-url] [tiers — e.g. 'all' | 'B,M' | specific IDs]"
---

# PR Comment

Publish a **single** GitHub review on a PR you're reviewing, built from `gate` / `gate-wf` findings. Each comment is drafted through `humanizer`, placed inline where the finding sits on the diff, and submitted only after one confirmation. The review is always submitted as **COMMENT** — this skill never approves or requests changes; that stays a manual call.

## Prerequisites

Findings come from a prior `gate` / `gate-wf` run, in priority order:

1. The findings already in this conversation (the gate verdict you just saw), or
2. The gate-wf state file for the current branch: `~/.claude/gate-wf-state/<repo-slug>/<branch>.json` → `.findings[]`.

Both produce the same shape: `id` (B1/M1/N1), `tier` (BLOCKER/MAJOR/NIT), `file`, `line`, `location` (`diff-line` | `adjacent`), `message`, `suggested_fix`.

Also resolve the PR and its head commit:

- `gh pr view <n> --json number,headRefOid,headRepositoryOwner,headRepository` — owner/repo + `headRefOid` (the `commit_id` every inline comment needs).

Drafting goes through the `humanizer` skill — that dependency is mandatory, not optional.

## The loop

`tier` orders the work (BLOCKER → MAJOR → NIT). For each selected finding:

1. **Draft the comment** — turn `message` + `suggested_fix` into a 1–3 sentence reviewer comment. Route it through the `humanizer` skill. **Never post a raw draft — always route it through humanizer first.** For NIT findings, prefix the body with `nit:`.
2. **Place it** — `location: diff-line` → inline comment at `file:line`. `location: adjacent` (legacy code outside the diff) **cannot be inline** (GitHub only accepts comments on diff lines) → fold it into the review body under an "Out-of-diff notes" heading, citing `file:line`.
3. **Add to the batch** — the pending review's `comments[]` (inline) or its body (adjacent / summary).

Show the **one batch preview** — the review body plus each inline comment with its `file:line` — then submit the review only after a **single** confirmation.

**Done when** one review has been submitted containing every selected finding as either an inline comment (diff-line) or a body note (adjacent), *and* the summary reports the review URL and the counts (inline / body / skipped).

## Submit (after confirmation)

Build the whole review in one payload and post it atomically — `event` is always `COMMENT`:

```bash
gh api repos/{owner}/{repo}/pulls/<n>/reviews --input - <<'JSON'
{
  "commit_id": "<headRefOid>",
  "event": "COMMENT",
  "body": "Gate review — <verdict>. <N> findings.\n\n## Out-of-diff notes\n- `src/legacy.ts:88` …",
  "comments": [
    { "path": "src/db/users.ts", "line": 42, "body": "User input is concatenated into raw SQL — use a parameterized query." }
  ]
}
JSON
```

Notes:

- GitHub only accepts inline comments on lines present in the diff; `adjacent` findings live in the body, never as `comments[]`.
- COMMENT only — this skill never submits APPROVE or REQUEST_CHANGES.
- A finding whose `file:line` is not on the diff (stale location) drops to a body note rather than failing the whole review.
